"""Apply current source modules to the bundled Python 3.11 MaxTrack runtime."""
import importlib.util
import json
import marshal
from pathlib import Path
import struct
import sys
import zlib

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter


def compile_source(module):
    path = Path(module + '.py')
    return marshal.dumps(compile(path.read_bytes(), path.name, 'exec'))


def apply(original, output, config):
    reader = CArchiveReader(str(original))
    binary = original.read_bytes()
    cookie_at = binary.rindex(CArchiveReader._COOKIE_MAGIC_PATTERN)
    _, _, _, _, runtime, library = struct.unpack_from(CArchiveReader._COOKIE_FORMAT, binary, cookie_at)
    if runtime != 311 or sys.version_info[:2] != (3, 11):
        raise ValueError('Use o Python 3.11 com o executável original do MaxTrack.')

    old_pyz = reader.extract('PYZ-00.pyz')
    if old_pyz[:8] != b'PYZ\0' + importlib.util.MAGIC_NUMBER:
        raise ValueError('Arquivo de módulos incompatível com o Python 3.11.')
    old_index = struct.unpack_from('!i', old_pyz, 8)[0]
    old_modules = dict(marshal.loads(old_pyz[old_index:]))
    additions = {module: compile_source(module) for module in (
        'interface', 'settings_store', 'stabilization', 'ets2_install', 'game_config', 'windows_tray',
        'max_store', 'max_store_winhttp'
    )}
    old_modules.pop('max_release_config', None)
    if config is not None:
        from max_store import check_release_config

        settings = json.loads(config.read_text(encoding='utf-8-sig'))
        check_release_config(settings)
        additions['max_release_config'] = marshal.dumps(
            compile('SETTINGS = ' + repr(settings), 'max_release_config.py', 'exec')
        )
    pyz = bytearray(old_pyz[:17])
    entries = {}
    for name in dict.fromkeys((*old_modules, *additions)):
        if name in additions:
            kind, encoded = 0, zlib.compress(additions[name], 6)
        else:
            kind, offset, size = old_modules[name]
            encoded = old_pyz[offset:offset + size]
        entries[name] = (kind, len(pyz), len(encoded))
        pyz.extend(encoded)
    struct.pack_into('!i', pyz, 8, len(pyz))
    pyz.extend(marshal.dumps(list(entries.items())))

    archive = bytearray()
    toc = [(0, 0, 0, 0, 'o', option) for option in reader.options]
    changes = {'maxtrack': compile_source('maxtrack'), 'PYZ-00.pyz': pyz}
    if not changes.keys() <= reader.toc.keys():
        raise ValueError('Executável original incompatível.')
    for name, (offset, size, original_size, compressed, kind) in reader.toc.items():
        offset += reader._start_offset
        encoded = binary[offset:offset + size]
        if name in changes:
            data = changes[name]
            encoded = zlib.compress(data, 9) if compressed else data
            original_size = len(data)
        toc.append((len(archive), len(encoded), original_size, compressed, kind, name))
        archive.extend(encoded)
    index = CArchiveWriter._serialize_toc(toc)
    cookie = struct.pack(CArchiveReader._COOKIE_FORMAT, CArchiveReader._COOKIE_MAGIC_PATTERN,
                         len(archive) + len(index) + CArchiveReader._COOKIE_LENGTH,
                         len(archive), len(index), runtime, library)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(binary[:reader._start_offset] + archive + index + cookie)
    result = CArchiveReader(str(output))
    if any(result.extract(name) != data for name, data in changes.items()):
        raise ValueError('A verificação do executável atualizado falhou.')


if __name__ == '__main__':
    original_path, output_path, *config_path = map(Path, sys.argv[1:])
    sys.path.insert(0, str(Path.cwd()))
    apply(original_path, output_path, config_path[0] if config_path else None)
