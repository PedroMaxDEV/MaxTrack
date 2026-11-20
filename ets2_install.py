"""Configure the ETS2 bridge and back up affected profiles."""
import json
import re
import sys
import tempfile
from pathlib import Path

from game_config import prepare


def write_atomic(path, contents):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        staging = Path(temporary.name)
        try:
            temporary.write(contents)
            temporary.close()
            staging.replace(path)
        finally:
            staging.unlink(missing_ok=True)


PROFILE_FOLDERS = ('profiles', 'steam_profiles')


def find_profiles(documents_game):
    return [profile for folder in PROFILE_FOLDERS
            for profile in sorted((documents_game / folder).glob('*/controls.sii'))
            if profile.is_file()]


def configure(game, profile, config, bridge):
    return _configure(game, {profile: Path('controls.sii')}, config, bridge)


def configure_profiles(game, documents_game, config, bridge, additional_plugins=None):
    profiles = find_profiles(documents_game)
    if not profiles:
        raise ValueError('Nenhum controls.sii encontrado em profiles ou steam_profiles. Abra o ETS2 e carregue um perfil primeiro.')
    backup = _configure(game, {profile: profile.relative_to(documents_game) for profile in profiles}, config, bridge,
                        game_config=documents_game / 'config.cfg', additional_plugins=additional_plugins)
    return len(profiles), backup


def _configure(game, profile_backups, config, bridge, game_config=None, additional_plugins=None):
    game_bin = game / 'bin' / 'win_x64'
    if not (game_bin / 'eurotrucks2.exe').is_file():
        raise ValueError('Selecione a pasta de instalação do ETS2 de 64 bits.')

    originals, updated = {}, {}
    for profile in profile_backups:
        if profile.name.lower() != 'controls.sii' or not profile.is_file():
            raise ValueError(f'Arquivo de perfil indisponível: {profile}')
        original = profile.read_bytes()
        encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
        try:
            updated[profile] = prepare(original.decode(encoding), 'sdk.maxtrack.yaw',
                                       'sdk.maxtrack.pitch', depth=True, lateral=True).encode(encoding)
        except ValueError as exc:
            raise ValueError(f'{profile}: {exc}') from exc
        originals[profile] = original
    if game_config is not None and game_config.is_file():
        original = game_config.read_bytes()
        modified, count = re.subn(rb'(?m)^(uset g_trackir[ \t]+)"[^"\r\n]*"', rb'\g<1>"1"', original)
        if count:
            originals[game_config] = original
            updated[game_config] = modified
    old_config = config.read_bytes() if config.exists() else None
    preferences = json.loads(old_config) if old_config is not None else {}
    if not isinstance(preferences, dict):
        raise ValueError('O arquivo de configurações do MaxTrack não contém um objeto JSON.')
    preferences['direct_bridge'] = True
    preferences['active_profile'] = 'ETS2'
    profiles = preferences.get('profiles')
    if isinstance(profiles, dict) and isinstance(profiles.get('ETS2'), dict):
        preferences.update({key: value for key, value in profiles['ETS2'].items()
                            if key in ('sensitivity_x','sensitivity_y','deadzone','smoothing','lowlight','vertical',
                                       'invert_x','invert_y','max_yaw','max_pitch','anti_tremor','responsive','cabin_mode')})

    plugins = game_bin / 'plugins'
    plugins.mkdir(exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    changes = {
        plugins / 'MaxTrackBridge.dll': bridge.read_bytes(),
        plugins / 'MaxTrackBridge-SCS-license.txt': bridge.with_name('sdk_license.txt').read_bytes(),
        **{plugins / name: data for name, data in (additional_plugins or {}).items()},
        **updated,
        config: json.dumps(preferences, indent=2).encode('utf-8'),
    }
    previous = {path: originals[path] if path in originals else path.read_bytes() if path.exists() else None
                for path in changes}
    backup = Path(tempfile.mkdtemp(prefix='ets2-backup-', dir=config.parent))
    for path, contents in previous.items():
        if contents is not None:
            target = backup / profile_backups.get(path, Path(path.name))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
    written = []
    try:
        for path, contents in changes.items():
            if previous[path] != contents:
                write_atomic(path, contents)
                written.append(path)
    except OSError:
        for path in reversed(written):
            if previous[path] is None:
                path.unlink()
            else:
                write_atomic(path, previous[path])
        raise
    return backup


def run_setup(game, profile, config, bridge, report):
    return _run_setup(lambda: (1, configure(game, profile, config, bridge)), report)


def _run_setup(apply, report):
    try:
        running = running_programs()
        maxtrack_processes = 1 if Path(sys.executable).name.lower() == 'maxtrackpro.exe' else 0
        if 'eurotrucks2.exe' in running or running.count('maxtrackpro.exe') > maxtrack_processes:
            raise ValueError('Feche o ETS2 e o MaxTrack e tente novamente.')
        count, backup = apply()
        report.write_text(f'Perfis configurados: {count}.\nBackup: {backup}', encoding='utf-8-sig')
        return 0
    except (ValueError, OSError) as exc:
        report.write_text(str(exc), encoding='utf-8-sig')
        return 5 if isinstance(exc, PermissionError) else 1


def running_programs():
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        # PROCESSENTRY32W from tlhelp32.h.
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                    ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                    ('name', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    snapshot = kernel.CreateToolhelp32Snapshot
    snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    snapshot.restype = wintypes.HANDLE
    first, advance = kernel.Process32FirstW, kernel.Process32NextW
    for step in (first, advance):
        step.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        step.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    names = []
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        if not first(handle, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            names.append(entry.name.lower())
            if not advance(handle, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(error)
                return names
    finally:
        kernel.CloseHandle(handle)


if __name__ == '__main__':
    game, documents_game, config, bridge, report = map(Path, sys.argv[1:])
    sys.exit(_run_setup(lambda: configure_profiles(game, documents_game, config, bridge), report))
