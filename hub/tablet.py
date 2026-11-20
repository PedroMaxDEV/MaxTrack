"""Resizable Max Multimídia overlay for the Windows desktop."""
import ctypes as c
from ctypes import wintypes as w
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

from hub.media import APPS
from windows_tray import WindowSubclass, bind

BACKGROUND, PANEL, TEXT, MUTE, ACCENT = '#101828', '#202d49', '#f4f7ff', '#bdc9e0', '#a9c6ff'
MEDIA_KEYS = {'playpause': 0xB3, 'next': 0xB0, 'previous': 0xB1, 'mute': 0xAD,
              'volumeup': 0xAF, 'volumedown': 0xAE}
WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x20, 0x08000000
WM_HOTKEY, HOTKEY_ID, GWL_EXSTYLE = 0x0312, 29, -20


def handle_media(action, url=None):
    if action == 'open':
        webbrowser.open(url)
    elif action in MEDIA_KEYS:
        send = c.windll.user32.keybd_event
        send.argtypes = (w.BYTE, w.BYTE, w.DWORD, c.c_size_t)
        key = MEDIA_KEYS[action]
        send(key, 0, 0, 0)
        send(key, 0, 2, 0)


class OverlayInput:
    def __init__(self, window):
        user = c.WinDLL('user32', use_last_error=True)
        controls = c.WinDLL('comctl32', use_last_error=True)
        self.get_style = bind(user, 'GetWindowLongPtrW', c.c_ssize_t, w.HWND, c.c_int)
        self.set_style = bind(user, 'SetWindowLongPtrW', c.c_ssize_t, w.HWND, c.c_int, c.c_ssize_t)
        self.register = bind(user, 'RegisterHotKey', w.BOOL, w.HWND, c.c_int, w.UINT, w.UINT)
        self.unregister = bind(user, 'UnregisterHotKey', w.BOOL, w.HWND, c.c_int)
        self.get_foreground = bind(user, 'GetForegroundWindow', w.HWND)
        self.foreground = bind(user, 'SetForegroundWindow', w.BOOL, w.HWND)
        self.release_clip = bind(user, 'ClipCursor', w.BOOL, c.c_void_p)
        self.set_window_pos = bind(user, 'SetWindowPos', w.BOOL, w.HWND, w.HWND,
                                   c.c_int, c.c_int, c.c_int, c.c_int, w.UINT)
        ancestor = bind(user, 'GetAncestor', w.HWND, w.HWND, w.UINT)
        subclass = bind(controls, 'SetWindowSubclass', w.BOOL, w.HWND, WindowSubclass, c.c_size_t, c.c_size_t)
        self.remove = bind(controls, 'RemoveWindowSubclass', w.BOOL, w.HWND, WindowSubclass, c.c_size_t)
        self.default = bind(controls, 'DefSubclassProc', c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.hwnd = ancestor(window.winfo_id(), 2)
        self.callback = WindowSubclass(self.window_proc)
        self.pending = False
        self.previous = None
        self.listening = bool(self.hwnd and subclass(self.hwnd, self.callback, HOTKEY_ID, 0))
        self.registered = self.listening and bool(self.register(self.hwnd, HOTKEY_ID, 0x4000, 0x77))

    def window_proc(self, hwnd, message, wparam, lparam, _id, _ref):
        if message == WM_HOTKEY and wparam == HOTKEY_ID:
            self.pending = True
            return 0
        return self.default(hwnd, message, wparam, lparam)

    def change(self, locked, focus=True):
        if not self.hwnd:
            return
        flags = WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        style = self.get_style(self.hwnd, GWL_EXSTYLE)
        self.set_style(self.hwnd, GWL_EXSTYLE, style | flags if locked else style & ~flags)
        self.set_window_pos(self.hwnd, None, 0, 0, 0, 0, 0x37)  # FRAMECHANGED, NOACTIVATE, NOZORDER, NOMOVE, NOSIZE
        if locked and self.previous:
            self.foreground(self.previous)
        elif not locked and focus:
            active = self.get_foreground()
            if active and active != self.hwnd:
                self.previous = active
            self.release_clip(None)
            self.foreground(self.hwnd)

    def close(self):
        if self.registered:
            self.unregister(self.hwnd, HOTKEY_ID)
        if self.listening:
            self.remove(self.hwnd, self.callback, HOTKEY_ID)


class Tablet:
    def __init__(self, root, service, on_close, open_gps, configure_youtube):
        self.service = service
        self.on_close = on_close
        self.open_gps = open_gps
        self.configure_youtube = configure_youtube
        self.tab = 'trip'
        self.expanded = False
        self.locked = False
        self.job = None
        self.last_status = None
        self.last_results = None
        self.window = tk.Toplevel(root)
        self.window.title('Max Multimídia')
        self.window.geometry('780x465')
        self.window.minsize(620, 400)
        self.window.configure(bg=BACKGROUND)
        self.window.attributes('-topmost', True, '-alpha', .99)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.build()
        self.window.update_idletasks()
        self.input = OverlayInput(self.window)
        self.refresh()

    def label(self, parent, text, size, color=TEXT, background=PANEL, **options):
        return tk.Label(parent, text=text, font=('Segoe UI', size), fg=color, bg=background,
                        anchor='w', justify='left', **options)

    def button(self, parent, text, command):
        return ttk.Button(parent, text=text, command=command)

    def build(self):
        frame = tk.Frame(self.window, bg=BACKGROUND, padx=10, pady=10)
        frame.pack(fill='both', expand=True)
        rail = tk.Frame(frame, bg='#182440', padx=10, pady=10, width=112)
        rail.pack(side='left', fill='y', padx=(0, 9))
        self.label(rail, 'MAX', 20, ACCENT, '#182440').pack(fill='x')
        self.label(rail, 'MULTIMÍDIA', 9, MUTE, '#182440').pack(fill='x', pady=(0, 18))
        for label, command in (('Viagem', lambda: self.show('trip')), ('Apps', lambda: self.show('apps')),
                               ('Max GPS', self.open_gps), ('Expandir', self.expand)):
            self.button(rail, label, command).pack(fill='x', pady=3)
        self.lock_button = self.button(rail, 'Travar · F8', self.toggle_lock)
        self.lock_button.pack(fill='x', side='bottom', pady=3)

        content = tk.Frame(frame, bg=BACKGROUND)
        content.pack(side='left', fill='both', expand=True)
        header = tk.Frame(content, bg=BACKGROUND)
        header.pack(fill='x', pady=(0, 7))
        self.label(header, 'Tablet da cabine', 19, TEXT, BACKGROUND).pack(side='left')
        self.mode = tk.StringVar()
        self.label(header, '', 9, MUTE, BACKGROUND, textvariable=self.mode).pack(side='right')

        self.body = tk.Frame(content, bg=BACKGROUND)
        self.body.pack(fill='both', expand=True)
        self.trip = tk.Frame(self.body, bg=BACKGROUND)
        self.trip.columnconfigure((0, 1), weight=1, uniform='trip')
        self.trip.rowconfigure((0, 1), weight=1, uniform='trip')
        self.values = {}
        for i, (key, title) in enumerate((('route','Percurso'),('cargo','Carga'),('fuel','Combustível'),('speed','Velocidade'))):
            card = tk.Frame(self.trip, bg=PANEL, padx=12, pady=10)
            card.grid(row=i//2, column=i%2, sticky='nsew', padx=4, pady=4)
            self.label(card, title.upper(), 9, ACCENT).pack(fill='x')
            value = self.values[key] = tk.StringVar(value='—')
            self.label(card, '', 13, textvariable=value, wraplength=217).pack(fill='both', expand=True)

        self.apps = tk.Frame(self.body, bg=PANEL, padx=12, pady=8)
        launchers = tk.Frame(self.apps, bg=PANEL)
        launchers.pack(fill='x')
        for column, (_, (name, url)) in enumerate(APPS.items()):
            launchers.columnconfigure(column, weight=1)
            self.button(launchers, name, lambda address=url: handle_media('open', address)).grid(
                row=0, column=column, sticky='ew', padx=2, pady=3)
        search = tk.Frame(self.apps, bg=PANEL)
        search.pack(fill='x', pady=(7, 4))
        self.query = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.query)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda _event: self.search())
        self.button(search, 'Buscar no YouTube', self.search).pack(side='left', padx=(5, 0))
        self.results = tk.Listbox(self.apps, height=4, bg='#132039', fg=TEXT, selectbackground='#365597',
                                  borderwidth=0, highlightthickness=0, font=('Segoe UI', 10))
        self.results.pack(fill='both', expand=True)
        self.results.bind('<Double-Button-1>', lambda _event: self.play_result())
        self.results.bind('<Return>', lambda _event: self.play_result())
        row = tk.Frame(self.apps, bg=PANEL)
        row.pack(fill='x', pady=(4, 0))
        self.button(row, 'Abrir vídeo', self.play_result).pack(side='left')
        self.button(row, 'API do YouTube', self.configure_youtube).pack(side='right')
        self.notice = tk.StringVar()
        self.label(self.apps, '', 9, MUTE, textvariable=self.notice, wraplength=450).pack(fill='x', pady=(4, 0))

        controls = tk.Frame(content, bg=BACKGROUND)
        controls.pack(fill='x', pady=(8, 0))
        for text, action in (('Anterior', 'previous'), ('Tocar / pausar', 'playpause'), ('Próxima', 'next'),
                             ('− Volume', 'volumedown'), ('+ Volume', 'volumeup')):
            self.button(controls, text, lambda name=action: handle_media(name)).pack(side='left', padx=2)
        self.show('trip')

    def search(self):
        query = self.query.get().strip()
        if query and self.service:
            threading.Thread(target=self.service.media.perform,
                             args=({'action': 'search', 'query': query},), daemon=True).start()

    def play_result(self):
        picked = self.results.curselection()
        if picked and self.service:
            snapshot = self.service.media.snapshot()
            if snapshot['results'] == self.last_results:
                self.service.media.perform({'action': 'result', 'index': picked[0]+1, 'query': snapshot['query']})

    def show(self, tab):
        self.trip.pack_forget()
        self.apps.pack_forget()
        (self.trip if tab == 'trip' else self.apps).pack(fill='both', expand=True)
        self.tab = tab
        if self.service:
            self.service.media.update_layout(self.tab, self.expanded)

    def expand(self):
        self.expanded = self.window.state() != 'zoomed'
        self.window.state('zoomed' if self.expanded else 'normal')
        if self.locked:
            self.input.change(True, focus=False)
        if self.service:
            self.service.media.update_layout(self.tab, self.expanded)

    def toggle_lock(self):
        if not self.input.registered:
            return
        self.locked = not self.locked
        self.input.change(self.locked)
        self.lock_button.configure(text='Destravar · F8' if self.locked else 'Travar · F8')

    def refresh(self):
        if self.input.pending:
            self.input.pending = False
            self.toggle_lock()
        self.lock_button.configure(state='normal' if self.input.registered else 'disabled')
        self.mode.set('Cliques passam ao jogo · F8 destrava' if self.locked else
                      'Interativo · F8 trava' if self.input.registered else 'Atalho F8 ocupado')
        if self.service:
            expanded = self.window.state() == 'zoomed'
            if expanded != self.expanded:
                self.expanded = expanded
                self.service.media.update_layout(self.tab, expanded)
            truck = self.service.telemetry.snapshot() or {}
            endpoint = ' → '.join(filter(None, (truck.get('origin'), truck.get('delivery'))))
            km = truck.get('distance', 0) / 1000
            left = int(truck.get('seconds', 0) / 60)
            self.values['route'].set(f'{endpoint}\n{km:.0f} km · {left//60}h {left%60:02d}m' if km > 0 else endpoint or 'Sem destino no ETS2')
            self.values['cargo'].set(truck.get('cargo') or 'Sem carga ativa')
            fuel = truck.get('fuel', -1)
            self.values['fuel'].set(f'{fuel:.0f} L' if fuel >= 0 else '—')
            speed = truck.get('speed', -1)
            self.values['speed'].set(f'{abs(speed)*3.6:.0f} km/h' if speed != -1 else '—')
            media = self.service.media.snapshot()
            if media['results'] != self.last_results:
                self.results.delete(0, tk.END)
                for i, item in enumerate(media['results'], 1):
                    self.results.insert(tk.END, f"{i}. {item['title']}")
                self.last_results = media['results']
            self.notice.set(media['notice'])
        self.job = self.window.after(120, self.refresh)

    def close(self):
        if self.job is not None:
            self.window.after_cancel(self.job)
        self.input.close()
        self.window.destroy()
        self.on_close()
