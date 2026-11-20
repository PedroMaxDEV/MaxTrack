"""Desktop launcher for the Max Hub and the local Max GPS service."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser
import winreg

from ets2_install import configure_profiles, running_programs, write_atomic
from hub.server import Service, lan_addresses, read_map
from hub.tablet import Tablet, handle_media
from hub import map_builder
from max_store import (Licenses, PRODUCT_NAMES, StoreError, StoreResponseError, available_release,
                       download_release, launch_update, release_config, request_json)


APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA_DIR = Path(os.environ['LOCALAPPDATA']) / 'MaxHub'
DATA_FILE = DATA_DIR / 'hub.json'
GAME_EXE = Path('bin/win_x64/eurotrucks2.exe')
STEAM_KEY = r'Software\Valve\Steam'
PLUGIN = 'MaxTrackHubTelemetry.dll'
BACKGROUND, PANEL, INK, MUTED, ACCENT = '#0d141a', '#16232b', '#f5faf9', '#abbabe', '#b5f45b'


def load_settings():
    try:
        data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save_settings(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_atomic(DATA_FILE, json.dumps(data).encode('utf-8'))


def registry_value(root, key, name, flags=0):
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ | flags) as handle:
            return winreg.QueryValueEx(handle, name)[0]
    except OSError:
        return ''


def find_game():
    key = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 227300'
    for flag in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        location = registry_value(winreg.HKEY_LOCAL_MACHINE, key, 'InstallLocation', flag)
        if location and (Path(location) / GAME_EXE).is_file():
            return Path(location)
    steam_locations = (registry_value(winreg.HKEY_CURRENT_USER, STEAM_KEY, 'SteamPath'),
                       registry_value(winreg.HKEY_LOCAL_MACHINE, STEAM_KEY, 'InstallPath', winreg.KEY_WOW64_32KEY),
                       str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Steam'))
    for steam in dict.fromkeys(filter(None, steam_locations)):
        libraries = [Path(steam)]
        try:
            config = (Path(steam) / 'steamapps/libraryfolders.vdf').read_text(encoding='utf-8-sig')
            libraries += [Path(path.replace('\\\\', '\\'))
                          for path in re.findall(r'^\s*"path"\s+"([^"]+)"', config, re.MULTILINE)]
        except (OSError, UnicodeError):
            pass
        for library in libraries:
            steamapps = library / 'steamapps'
            common = steamapps / 'common'
            game = common / 'Euro Truck Simulator 2'
            if (game / GAME_EXE).is_file():
                return game
            try:
                manifest = (steamapps / 'appmanifest_227300.acf').read_text(encoding='utf-8-sig')
                found = re.search(r'^\s*"installdir"\s+"([^"\\/:]+)"', manifest, re.MULTILINE)
                if found and found[1] not in ('.', '..'):
                    game = common / found[1]
                    if (game / GAME_EXE).is_file():
                        return game
            except (OSError, UnicodeError):
                continue
    return None


def documents_game():
    documents = Path.home() / 'Documents'
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
        documents = Path(buffer.value)
    return documents / 'Euro Truck Simulator 2'


def telemetry_files():
    assets = APP_DIR / 'telemetry'
    if not getattr(sys, 'frozen', False) and not assets.is_dir():
        assets = APP_DIR.parent / 'dist' / 'MaxHub' / 'telemetry'
    return {PLUGIN: (assets / PLUGIN).read_bytes(),
            'MaxHub-SCS-license.txt': (assets / 'sdk_license.txt').read_bytes()}


def configure_plugin(game):
    if not (game / GAME_EXE).is_file():
        raise ValueError('Selecione a pasta do ETS2 que contém bin/win_x64/eurotrucks2.exe.')
    if 'eurotrucks2.exe' in running_programs():
        raise ValueError('Feche o ETS2 antes de instalar ou atualizar a telemetria.')
    files = telemetry_files()
    plugins = game / 'bin/win_x64/plugins'
    plugins.mkdir(exist_ok=True)
    for name, content in files.items():
        write_atomic(plugins / name, content)


def apply_ets2_profiles(game, include_gps):
    if {'eurotrucks2.exe', 'maxtrackpro.exe'}.intersection(running_programs()):
        raise ValueError('Feche o ETS2 e o MaxTrack Pro antes de configurar os perfis.')
    bridge = APP_DIR / 'bridge' / 'MaxTrackBridge.dll'
    if not getattr(sys, 'frozen', False) and not bridge.is_file():
        bridge = APP_DIR.parent / 'dist' / 'MaxTrackPro' / 'bridge' / bridge.name
    config = DATA_DIR.parent / 'MaxTrackPro' / 'config.json'
    count, backup = configure_profiles(game, documents_game(), config, bridge,
                                       additional_plugins=telemetry_files() if include_gps else None)
    return f'{count} perfil(is) configurado(s).\nBackup dos arquivos\n{backup}'


class Hub:
    def __init__(self):
        self.settings = load_settings()
        self.service = None
        self.known_status = ''
        self.media = None
        self.game = None
        self.generating_map = False
        self.next_map_check = 0
        self.checked_inputs = None
        self.closing = False
        self.checking_update = False
        self.updating = False
        self.activating = False
        self.update_candidate = None
        self.root = tk.Tk()
        self.root.title('Max Hub')
        self.root.geometry('920x675')
        self.root.minsize(790, 625)
        self.root.configure(bg=BACKGROUND)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        try:
            self.licenses = Licenses(release_config(), DATA_DIR)
        except StoreError as exc:
            self.root.withdraw()
            messagebox.showerror('Max Hub', str(exc), parent=self.root)
            self.root.destroy()
            raise SystemExit(1)
        self.style()
        self.build()
        self.root.after(75, self.initialize)
        if self.licenses.config:
            self.root.after(300, self.refresh_license)
            self.root.after(1500, self.check_updates)

    def style(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=BACKGROUND, foreground=INK, font=('Segoe UI', 10))
        style.configure('TButton', background='#243840', foreground=INK, bordercolor='#405661', padding=(11, 8))
        style.map('TButton', background=[('active', '#3b565e')], foreground=[('disabled', '#7d8b8d')])
        style.configure('Action.TButton', background=ACCENT, foreground='#102215', font=('Segoe UI', 10, 'bold'))
        style.map('Action.TButton', background=[('active', '#cffca1')])
        style.configure('TEntry', fieldbackground='#203139', foreground=INK)
        style.configure('TCombobox', fieldbackground='#203139', foreground=INK)
        style.map('TCombobox', fieldbackground=[('readonly', '#203139')],
                  foreground=[('readonly', INK)])

    def label(self, parent, text, font=10, color=INK, bg=BACKGROUND, **options):
        return tk.Label(parent, text=text, font=('Segoe UI', font), fg=color, bg=bg,
                        justify='left', anchor='w', **options)

    def build(self):
        self.root.geometry('985x680')
        self.root.minsize(850, 640)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        rail = tk.Frame(self.root, bg='#111e2d', padx=18, pady=24)
        rail.grid(row=0, column=0, sticky='nsew')
        self.label(rail, 'Max Hub', 25, '#84f0dd', '#111e2d').pack(fill='x')
        self.label(rail, 'Euro Truck Simulator 2', 10, MUTED, '#111e2d').pack(fill='x', pady=(0, 25))
        for title, command in (('MaxTrack Pro', self.open_track), ('Abrir GPS no PC', self.open_gps),
                               ('Max Multimídia', self.open_media), ('Configurar todos os perfis ETS2', self.install_profiles)):
            ttk.Button(rail, text=title, command=command).pack(fill='x', pady=4)
        if self.licenses.config:
            ttk.Separator(rail).pack(fill='x', pady=(16, 8))
            ttk.Button(rail, text='Ativar com chave', command=self.activate_license).pack(fill='x', pady=4)
            ttk.Button(rail, text='Minha conta na loja', command=self.open_account).pack(fill='x', pady=4)
            self.license_state = tk.StringVar(value='Nenhum produto ativo')
            self.label(rail, '', 9, MUTED, '#111e2d', textvariable=self.license_state,
                       wraplength=190).pack(fill='x', pady=(0, 8))
            self.update_button = ttk.Button(rail, text='Procurar atualizações', command=self.check_updates)
            self.update_button.pack(fill='x', pady=4)
            self.update_state = tk.StringVar(value=f'Versão {self.licenses.config.version}')
            self.label(rail, '', 9, MUTED, '#111e2d', textvariable=self.update_state,
                       wraplength=190).pack(fill='x')
            self.show_license()
        ttk.Button(rail, text='Demonstração do GPS', command=lambda: self.open_gps(demo=True)).pack(fill='x', side='bottom')

        page = tk.Frame(self.root, bg=BACKGROUND, padx=29, pady=24)
        page.grid(row=0, column=1, sticky='nsew')
        self.state = tk.StringVar(value='Iniciando serviço local')
        self.label(page, 'Max GPS', 30).pack(fill='x')
        self.label(page, '', 11, '#84f0dd', textvariable=self.state).pack(fill='x', pady=(0, 16))
        gps = tk.Frame(page, bg='#1b2c3d', padx=18, pady=15)
        gps.pack(fill='x')
        self.label(gps, 'Parear com o Android', 16, INK, '#1b2c3d').pack(fill='x')
        self.label(gps, 'No app, toque em Conectar, escolha este PC e digite o código.',
                   10, MUTED, '#1b2c3d').pack(fill='x', pady=(4, 0))
        self.pair_code = tk.StringVar(value='— — —   — — —')
        tk.Label(gps, bg='#1b2c3d', fg='#84f0dd', font=('Cascadia Mono', 36, 'bold'),
                 anchor='w', textvariable=self.pair_code).pack(fill='x', pady=(2, 0))
        self.label(gps, 'Celular e PC precisam estar na mesma rede.', 10, MUTED, '#1b2c3d').pack(fill='x')
        self.address = tk.StringVar()
        ttk.Button(gps, text='Parear por QR', command=self.show_pair_qr).pack(anchor='w', pady=(8, 0))
        ttk.Button(gps, text='Copiar endereço para conexão manual', command=self.copy_address).pack(anchor='w', pady=(10, 0))

        connections = tk.Frame(page, bg=BACKGROUND)
        connections.pack(fill='x', pady=(16, 0))
        self.label(connections, 'Telemetria e mapas', 16).pack(fill='x')
        buttons = tk.Frame(connections, bg=BACKGROUND)
        buttons.pack(fill='x', pady=(8, 0))
        ttk.Button(buttons, text='Instalar telemetria', style='Action.TButton', command=self.install_plugin).pack(side='left', padx=(0, 7))
        self.generate_button = ttk.Button(buttons, text='Gerar mapa do ETS2', command=self.generate_map)
        self.generate_button.pack(side='left', padx=(0, 7))
        ttk.Button(buttons, text='Importar JSON', command=self.import_map).pack(side='left')
        options = tk.Frame(connections, bg=BACKGROUND)
        options.pack(fill='x', pady=(7, 0))
        ttk.Button(options, text='Escolher mods .scs', command=lambda: self.generate_map(manual=True)).pack(side='left', padx=(0, 7))
        self.auto_map = tk.BooleanVar(value=bool(self.settings.get('auto_map')))
        def toggle_auto():
            self.settings['auto_map'] = self.auto_map.get()
            self.checked_inputs = None
            self.next_map_check = 0
            save_settings(self.settings)
        ttk.Checkbutton(options, text='Atualizar com o perfil', variable=self.auto_map,
                        command=toggle_auto).pack(side='left', padx=5)
        self.voice_button = ttk.Button(options, text='Testar voz no PC', command=self.test_voice)
        self.voice_button.pack(side='left')
        self.voice_state = tk.StringVar()
        self.label(connections, '', 10, MUTED, textvariable=self.voice_state, wraplength=540).pack(fill='x', pady=(4, 0))
        self.map_label = tk.StringVar(value='Mapa rodoviário: nenhum importado.')
        self.label(connections, '', 10, MUTED, textvariable=self.map_label, wraplength=535).pack(fill='x', pady=(8, 0))
        self.label(connections, 'O app Android baixa o mapa ativo pela rede local.',
                   10, MUTED).pack(fill='x', pady=(4, 0))

    def initialize(self):
        token = self.settings.get('pairing')
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', token):
            token = self.settings['pairing'] = secrets.token_urlsafe(20)
            try:
                save_settings(self.settings)
            except OSError:
                pass
        try:
            self.service = Service(token=token, youtube_key=self.settings.get('youtube_api_key', ''),
                                   alert_path=DATA_DIR / 'road-alerts.json', features=self.licenses.active_products,
                                   commercial=self.licenses.config is not None)
        except OSError as exc:
            self.state.set(f'GPS indisponível. Feche outras instâncias do Max Hub. ({exc})')
            return
        code = self.service.pairing.code
        self.pair_code.set(code[:3] + '  ' + code[3:])
        addresses = [self.service.url(ip) for ip in lan_addresses()]
        self.address.set(addresses[0] if addresses else '')
        if self.settings.get('map'):
            self.use_map(Path(self.settings['map']), show_error=False)
        self.check_status()
        self.dispatch_media()

    def show_license(self):
        products = self.licenses.active_products()
        self.license_state.set(', '.join(name for product, name in PRODUCT_NAMES.items() if product in products)
                               or 'Nenhum produto ativo')
        if self.media and 'media' not in products:
            self.media.close()

    def refresh_license(self):
        def refresh():
            try:
                self.licenses.refresh()
            except StoreError:
                pass
            if not self.closing:
                self.root.after(0, finished)

        def finished():
            self.show_license()
            self.root.after(15 * 60_000, self.refresh_license)

        threading.Thread(target=refresh, daemon=True).start()

    def open_account(self):
        webbrowser.open(self.licenses.config.origin + '/#conta')

    def require(self, product):
        if self.licenses.allows(product):
            return True
        messagebox.showinfo(PRODUCT_NAMES[product], 'Use Ativar com chave no Max Hub para liberar este produto.')
        return False

    def activate_license(self):
        if self.activating:
            return
        key = simpledialog.askstring('Ativar produto', 'Cole a chave que aparece na sua conta da loja.',
                                     parent=self.root, show='•')
        if not key:
            return
        self.activating = True
        self.license_state.set('Validando a chave…')

        def activate():
            error = ''
            try:
                self.licenses.activate(key)
            except StoreError as exc:
                error = str(exc)
            if not self.closing:
                self.root.after(0, finished, error)

        def finished(error):
            self.activating = False
            self.show_license()
            if error:
                messagebox.showerror('Ativar produto', error)
            else:
                messagebox.showinfo('Ativar produto', 'Chave ativada neste computador.')

        threading.Thread(target=activate, daemon=True).start()

    def check_updates(self):
        if self.checking_update or self.updating:
            return
        if self.update_candidate:
            self.install_update()
            return
        self.checking_update = True
        self.update_button.configure(state='disabled')
        self.update_state.set('Consultando o site…')

        def check():
            try:
                version = available_release(self.licenses.config)
                error = ''
            except StoreError as exc:
                version, error = None, str(exc)
            if not self.closing:
                self.root.after(0, finished, version, error)

        def finished(version, error):
            self.checking_update = False
            self.update_candidate = version
            if version:
                self.update_button.configure(state='normal', text=f'Atualizar para {version.version}')
                self.update_state.set('Nova versão disponível')
            else:
                self.update_button.configure(state='normal', text='Procurar atualizações')
                self.update_state.set(error or f'Site conectado · versão {self.licenses.config.version} em dia')

        threading.Thread(target=check, daemon=True).start()

    def install_update(self):
        if not getattr(sys, 'frozen', False) or not (APP_DIR / 'unins000.exe').is_file():
            messagebox.showinfo('Atualizar Max Hub', 'Abra a instalação do Max Hub para atualizar por aqui.')
            return
        if {'eurotrucks2.exe', 'maxtrackpro.exe'}.intersection(running_programs()) or self.generating_map:
            messagebox.showinfo('Atualizar Max Hub', 'Feche o ETS2 e o MaxTrack e aguarde a geração de mapas em andamento.')
            return
        release = self.update_candidate
        if not messagebox.askyesno('Atualizar Max Hub',
                                   f'Baixar a versão {release.version} e reiniciar o Hub?'):
            return
        self.updating = True
        self.update_button.configure(state='disabled')
        self.update_state.set('Baixando a atualização…')

        def update():
            last = -1

            def progress(percent):
                nonlocal last
                if percent != last and not self.closing:
                    last = percent
                    self.root.after(0, self.update_state.set, f'Baixando a atualização · {percent}%')

            try:
                installer = download_release(self.licenses.config, release, DATA_DIR / 'updates', progress)
            except (StoreError, OSError) as exc:
                if not self.closing:
                    self.root.after(0, failed, str(exc))
            else:
                if not self.closing:
                    self.root.after(0, finished, installer)

        def failed(error):
            self.updating = False
            self.update_button.configure(state='normal')
            self.update_state.set(error)

        def finished(installer):
            if {'eurotrucks2.exe', 'maxtrackpro.exe'}.intersection(running_programs()) or self.generating_map:
                failed('Feche o ETS2 e o MaxTrack para aplicar a atualização.')
                return
            try:
                launch_update(installer, APP_DIR)
            except OSError as exc:
                failed(f'Não foi possível iniciar a atualização. {exc}')
            else:
                self.close()

        threading.Thread(target=update, daemon=True).start()

    def check_status(self):
        if self.service:
            connected = self.service.telemetry.snapshot()
            status = 'ETS2 ao vivo' if connected else 'Aguardando o ETS2 na cabine'
            if not self.address.get():
                status += ' · IP de rede local indisponível'
            self.state.set(status)
            if (connected and self.auto_map.get() and not self.generating_map
                    and time.monotonic() >= self.next_map_check and self.licenses.allows('gps')):
                self.next_map_check = time.monotonic() + 60
                self.generate_map(automatic=True)
            self.root.after(800, self.check_status)

    def open_track(self):
        if not self.require('track'):
            return
        candidates = [APP_DIR / 'MaxTrackPro.exe', APP_DIR.parent / 'MaxTrackPro/MaxTrackPro.exe',
                      Path(os.environ['LOCALAPPDATA']) / 'Programs/MaxTrackPro/MaxTrackPro.exe']
        for path in candidates:
            if path.is_file():
                subprocess.Popen([str(path)], cwd=path.parent)
                return
        messagebox.showinfo('MaxTrack Pro', 'Instale o MaxTrack Pro ou use o instalador completo do Max Hub.')

    def open_gps(self, demo=False):
        if self.service and (demo or self.require('gps')):
            webbrowser.open(self.service.url('127.0.0.1') + ('&demo=1' if demo else ''))

    def show_pair_qr(self):
        from urllib.parse import urlsplit
        if not self.address.get() or not self.service:
            return
        try:
            import cv2
            from PIL import Image, ImageTk
        except ImportError:
            messagebox.showinfo('Parear com o Max GPS', 'QR indisponível neste ambiente de desenvolvimento. '
                                'Use Conectar no celular e o código de seis dígitos do Hub.')
            return
        address = urlsplit(self.address.get())
        link = f'maxgps://parear/{address.hostname}/{address.port}?codigo={self.service.pairing.code}'
        matrix = cv2.QRCodeEncoder_create().encode(link)
        image = Image.fromarray(cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255))
        dialog = tk.Toplevel(self.root)
        dialog.title('Parear com o Max GPS')
        label = ttk.Label(dialog, text='Leia com a câmera do celular na mesma rede.')
        label.pack(padx=16, pady=8)
        photo = ImageTk.PhotoImage(image.resize((image.width*6, image.height*6), Image.Resampling.NEAREST))
        qr = ttk.Label(dialog, image=photo)
        qr.image = photo
        qr.pack(padx=16, pady=8)

    def copy_address(self):
        if self.address.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.address.get())
            self.state.set('Endereço copiado')

    def select_game(self):
        game = self.game or find_game()
        if game is None:
            selected = filedialog.askdirectory(title='Selecione a pasta do Euro Truck Simulator 2')
            game = Path(selected) if selected else None
        return game

    def elevate_integration(self, operation, game):
        if not getattr(sys, 'frozen', False):
            messagebox.showerror('Integração ETS2', 'A pasta do ETS2 requer permissão de administrador.')
            return
        shell = ctypes.windll.shell32.ShellExecuteW
        shell.restype = ctypes.c_ssize_t
        result = shell(None, 'runas', sys.executable, subprocess.list2cmdline([operation, str(game)]),
                       str(APP_DIR), 1)
        if result <= 32:
            messagebox.showerror('Integração ETS2', 'Autorize o Max Hub a configurar a integração no Windows.')

    def install_plugin(self):
        if not self.require('gps'):
            return
        game = self.select_game()
        if game is None:
            return
        try:
            configure_plugin(game)
        except PermissionError:
            self.elevate_integration('--install-plugin', game)
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror('Max GPS', str(exc))
            return
        self.game = game
        messagebox.showinfo('Max GPS', 'Telemetria instalada. Abra o ETS2 e entre na cabine.')

    def install_profiles(self):
        if not self.require('track'):
            return
        game = self.select_game()
        if game is None or not messagebox.askyesno('Configurar todos os perfis ETS2',
                'Aplicar o rastreamento em todos os perfis locais e da Steam? O Max Hub salva um backup.\n'
                'Feche o ETS2 e o MaxTrack Pro antes de continuar.'):
            return
        try:
            result = apply_ets2_profiles(game, self.licenses.allows('gps'))
        except PermissionError:
            self.elevate_integration('--install-profiles', game)
            return
        except (OSError, ValueError) as exc:
            messagebox.showerror('Integração ETS2', str(exc))
            return
        self.game = game
        messagebox.showinfo('Integração ETS2', result)

    def use_map(self, path, show_error=True):
        try:
            name, payload = read_map(path)
        except (OSError, ValueError, RecursionError) as exc:
            if show_error:
                messagebox.showerror('Mapa do Max GPS', str(exc))
            return False
        self.service.telemetry.set_map(payload)
        self.map_label.set(f'{name} · disponível no Max GPS pela rede local')
        return True

    def import_map(self):
        if not self.service or not self.require('gps'):
            return
        selected = filedialog.askopenfilename(title='Importar mapa rodoviário do Max GPS',
                                             filetypes=[('Mapa Max GPS', '*.json')])
        if selected and self.use_map(Path(selected)):
            self.auto_map.set(False)
            self.settings.update(auto_map=False, map_inputs=None)
            self.remember_map(Path(selected))

    def remember_map(self, path):
        self.settings['map'] = str(path)
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showwarning('Mapa do Max GPS', f'Mapa ativo nesta sessão. {exc}')

    def generate_map(self, manual=False, automatic=False):
        if not self.service or self.generating_map or not self.require('gps'):
            return
        game = self.game or find_game()
        if game is None or not (game / 'base_map.scs').is_file():
            if automatic:
                return
            chosen = filedialog.askdirectory(title='Escolha a pasta do ETS2 que contém base_map.scs')
            if not chosen:
                return
            game = Path(chosen)
        game_docs = documents_game()
        fingerprint = None
        expected_module = None
        if manual:
            selected = filedialog.askopenfilenames(title='Selecione os pacotes do mapa e suas dependências',
                                                   initialdir=game_docs / 'mod',
                                                   filetypes=[('Pacotes do ETS2', '*.scs *.zip')])
            if not selected:
                return
            mods = list(map(Path, selected))
        else:
            try:
                mods, missing = map_builder.active_mods(game_docs, game)
                log = game_docs / 'game.log.txt'
                if log.exists():
                    modules = re.findall(r"Map '/map/([^/']+)\.mbd' loading started", log.read_text(
                        encoding='utf-8-sig', errors='replace'), re.IGNORECASE)
                    expected_module = modules[-1] if modules else None
                if automatic and (not expected_module or missing):
                    return
                inputs = []
                for path in [*sorted(game.glob('*.scs')), *mods]:
                    entries = sorted(path.rglob('*')) if path.is_dir() else [path]
                    for entry in entries:
                        stat = entry.stat()
                        inputs.append((str(entry), stat.st_size, stat.st_mtime_ns))
                fingerprint = hashlib.sha256(repr((expected_module, inputs)).encode()).hexdigest()
                if automatic and (fingerprint == self.checked_inputs or
                                  (fingerprint == self.settings.get('map_inputs') and self.service.telemetry.map_state()[1])):
                    return
                self.checked_inputs = fingerprint
                if automatic and fingerprint != self.settings.get('map_inputs'):
                    self.service.telemetry.set_map(None)
            except OSError as exc:
                if not automatic:
                    messagebox.showerror('Mapa do Max GPS', f'Não foi possível ler o log do ETS2. {exc}')
                return
            if missing:
                messagebox.showerror('Mapa do Max GPS', 'Um pacote ativo do último perfil não foi encontrado.\n' +
                                     '\n'.join(missing[:5]) + '\nAbra o perfil correto ou use Escolher mods .scs.')
                return
        self.generating_map = True
        self.generate_button.configure(state='disabled')

        def progress(message):
            self.root.after(0, self.map_label.set, message)

        def run():
            try:
                path = map_builder.build(game, mods, DATA_DIR / 'map-builder', progress,
                                         APP_DIR / 'map-tools' / 'map-builder.zip', expected_module)
                self.root.after(0, finish, path, '')
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                self.root.after(0, finish, None, str(exc))

        def finish(path, error):
            self.generating_map = False
            self.generate_button.configure(state='normal')
            if error:
                self.map_label.set('Geração do mapa interrompida. O mapa ativo foi mantido.')
                if automatic:
                    self.map_label.set(error)
                else:
                    messagebox.showerror('Mapa do Max GPS', error)
            elif self.use_map(path):
                self.settings['map_inputs'] = fingerprint
                self.remember_map(path)

        threading.Thread(target=run, daemon=True).start()

    def test_voice(self):
        if not self.service or not self.require('gps'):
            return
        voice = self.service.voice
        self.voice_button.configure(state='disabled')
        self.voice_state.set('Preparando a voz do Max GPS…')

        def run():
            try:
                notice = voice.play(voice.payload({'text': 'Max GPS. Teste de voz no computador.'}))
            except RuntimeError as exc:
                notice = str(exc)
            self.root.after(0, finish, notice)

        def finish(notice):
            self.voice_state.set(notice)
            self.voice_button.configure(state='normal')

        threading.Thread(target=run, daemon=True).start()

    def open_media(self):
        if not self.service or not self.require('media'):
            return
        if self.media:
            self.media.window.deiconify()
            self.media.window.lift()
            return
        self.media = Tablet(self.root, self.service, self.media_closed, self.open_gps, self.configure_youtube)

    def media_closed(self):
        self.media = None

    def configure_youtube(self):
        key = simpledialog.askstring('API do YouTube',
            'Informe a chave do YouTube Data API v3 para ver resultados numerados.\n'
            'Deixe vazio para usar a busca no navegador.', parent=self.media.window, show='•')
        if key is None:
            return
        key = key.strip()
        if key and not re.fullmatch(r'[A-Za-z0-9_-]{15,120}', key):
            messagebox.showerror('API do YouTube', 'Formato de chave inválido.', parent=self.media.window)
            return
        self.settings['youtube_api_key'] = key
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showwarning('API do YouTube', f'Configuração ativa nesta sessão. {exc}')
        if self.service:
            with self.service.media.lock:
                self.service.media.key = key

    def dispatch_media(self):
        for _ in range(12):
            try:
                action, url = self.service.media.actions.get_nowait()
            except queue.Empty:
                break
            if action in ('trip', 'apps', 'expand'):
                if self.media:
                    self.media.expand() if action == 'expand' else self.media.show(action)
            else:
                handle_media(action, url)
        self.root.after(100, self.dispatch_media)

    def close(self):
        self.closing = True
        if self.media:
            self.media.close()
        if self.service:
            self.service.close()
        self.root.destroy()


def store_diagnostic(report):
    """Exercise the live HTTPS paths without a customer's key or device identifier."""
    config = release_config()
    if config is None:
        raise StoreError('Este executável não tem uma loja configurada.')
    result = {'version': config.version, 'origin': config.origin}
    try:
        update = available_release(config)
        result['updates'] = update.version if update else 'em dia'
    except StoreError as exc:
        result['updates'] = str(exc)
    try:
        request_json(config, '/api/activate', {
            'key': 'MAX-00000000-00000000-00000000-00000000-00000000',
            'deviceId': 'maxhub-diagnostic-device',
        })
    except StoreResponseError as exc:
        result['activation'] = {'http': exc.status, 'message': str(exc)}
    except StoreError as exc:
        result['activation'] = str(exc)
    else:
        result['activation'] = 'Resposta inesperada para chave fictícia'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--diagnostico-loja':
        store_diagnostic(Path(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] in ('--install-plugin', '--install-profiles'):
        window = tk.Tk()
        window.withdraw()
        try:
            install_profiles = sys.argv[1] == '--install-profiles'
            licenses = Licenses(release_config(), DATA_DIR)
            if not licenses.allows('track' if install_profiles else 'gps'):
                raise StoreError('Ative o produto no Max Hub antes de configurar a integração.')
            game = Path(sys.argv[2])
            if install_profiles:
                result = apply_ets2_profiles(game, licenses.allows('gps'))
            else:
                configure_plugin(game)
                result = 'Telemetria instalada. Abra o ETS2 e entre na cabine.'
            messagebox.showinfo('Integração ETS2', result)
        except (OSError, ValueError, StoreError) as exc:
            messagebox.showerror('Integração ETS2', str(exc))
        finally:
            window.destroy()
    else:
        Hub().root.mainloop()
