"""Windows notification icon backed by Tk's existing message loop."""
import ctypes as c
from ctypes import wintypes as w
import sys


CALLBACK_MESSAGE = 0x8000 + 1  # WM_APP + 1
ICON_ID = 1
SUBCLASS_ID = 1
NIM_ADD, NIM_DELETE = 0, 2
OPEN, EXIT = 1, 2


class NotifyIconData(c.Structure):
    # NOTIFYICONDATAW_V2_SIZE: fields through the balloon title and flags.
    _fields_ = [('size', w.DWORD), ('window', w.HWND), ('id', w.UINT),
                ('flags', w.UINT), ('message', w.UINT), ('icon', w.HICON),
                ('tip', w.WCHAR * 128), ('state', w.DWORD), ('state_mask', w.DWORD),
                ('info', w.WCHAR * 256), ('timeout', w.UINT),
                ('info_title', w.WCHAR * 64), ('info_flags', w.DWORD)]


WindowSubclass = c.WINFUNCTYPE if sys.platform == 'win32' else c.CFUNCTYPE
WindowSubclass = WindowSubclass(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM,
                                c.c_size_t, c.c_size_t)


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


class WindowsTray:
    def __init__(self, root, restore, exit_app):
        self.root = root
        self.restore = restore
        self.exit_app = exit_app
        self.visible = False
        self.pending_action = None
        self.data = None
        self.owned_icon = None
        user = c.WinDLL('user32', use_last_error=True)
        shell = c.WinDLL('shell32', use_last_error=True)
        controls = c.WinDLL('comctl32', use_last_error=True)
        self.ancestor = bind(user, 'GetAncestor', w.HWND, w.HWND, w.UINT)
        self.load_icon = bind(user, 'LoadIconW', w.HICON, w.HINSTANCE, c.c_void_p)
        self.extract_icon = bind(shell, 'ExtractIconW', w.HICON, w.HINSTANCE, w.LPCWSTR, w.UINT)
        self.destroy_icon = bind(user, 'DestroyIcon', w.BOOL, w.HICON)
        self.notify = bind(shell, 'Shell_NotifyIconW', w.BOOL, w.DWORD, c.POINTER(NotifyIconData))
        self.set_subclass = bind(controls, 'SetWindowSubclass', w.BOOL, w.HWND,
                                 WindowSubclass, c.c_size_t, c.c_size_t)
        self.remove_subclass = bind(controls, 'RemoveWindowSubclass', w.BOOL, w.HWND,
                                    WindowSubclass, c.c_size_t)
        self.default_proc = bind(controls, 'DefSubclassProc', c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.cursor = bind(user, 'GetCursorPos', w.BOOL, c.POINTER(w.POINT))
        self.create_menu = bind(user, 'CreatePopupMenu', w.HMENU)
        self.append_menu = bind(user, 'AppendMenuW', w.BOOL, w.HMENU, w.UINT, c.c_size_t, w.LPCWSTR)
        self.track_menu = bind(user, 'TrackPopupMenu', w.UINT, w.HMENU, w.UINT, c.c_int, c.c_int,
                               c.c_int, w.HWND, c.c_void_p)
        self.destroy_menu = bind(user, 'DestroyMenu', w.BOOL, w.HMENU)
        self.foreground = bind(user, 'SetForegroundWindow', w.BOOL, w.HWND)
        self.post = bind(user, 'PostMessageW', w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        register_message = bind(user, 'RegisterWindowMessageW', w.UINT, w.LPCWSTR)
        self.taskbar_created = register_message('TaskbarCreated')
        self.callback = WindowSubclass(self.window_proc)

    def show(self):
        if self.visible:
            return True
        if self.data is None:
            self.root.update_idletasks()
            window = self.ancestor(self.root.winfo_id(), 2)  # GA_ROOT
            if not window or not self.set_subclass(window, self.callback, SUBCLASS_ID, 0):
                return False
            if getattr(sys, 'frozen', False):
                icon = self.extract_icon(None, sys.executable, 0)
                if icon and icon != 1:
                    self.owned_icon = icon
            icon = self.owned_icon or self.load_icon(None, 32512)  # IDI_APPLICATION
            self.data = NotifyIconData(c.sizeof(NotifyIconData), window, ICON_ID,
                                       0x07, CALLBACK_MESSAGE, icon, 'MaxTrack Pro')
        self.visible = bool(self.notify(NIM_ADD, c.byref(self.data)))
        if self.visible:
            self.root.after(50, self.poll)
        return self.visible

    def hide(self):
        if self.visible:
            self.notify(NIM_DELETE, c.byref(self.data))
            self.visible = False
        self.pending_action = None

    def close(self):
        self.hide()
        if self.data is not None:
            self.remove_subclass(self.data.window, self.callback, SUBCLASS_ID)
            self.data = None
        if self.owned_icon:
            self.destroy_icon(self.owned_icon)
            self.owned_icon = None

    def window_proc(self, window, message, wparam, lparam, _subclass, _data):
        # Tk cannot be reentered directly from its native window procedure.
        if message == CALLBACK_MESSAGE and wparam == ICON_ID and self.visible:
            if lparam == 0x0203:  # WM_LBUTTONDBLCLK
                self.pending_action = self.restore
            elif lparam == 0x0205:  # WM_RBUTTONUP
                self.pending_action = self.popup
            return 0
        if message == self.taskbar_created and self.visible:
            if not self.notify(NIM_ADD, c.byref(self.data)):
                self.pending_action = self.restore
        return self.default_proc(window, message, wparam, lparam)

    def poll(self):
        action = self.pending_action
        self.pending_action = None
        if action is not None:
            action()
        if self.visible:
            self.root.after(50, self.poll)

    def popup(self):
        if not self.visible:
            return
        position = w.POINT()
        if not self.cursor(c.byref(position)):
            return
        menu = self.create_menu()
        if not menu:
            return
        window = self.data.window
        try:
            self.append_menu(menu, 0, OPEN, 'Abrir MaxTrack')
            self.append_menu(menu, 0, EXIT, 'Sair')
            self.foreground(window)
            chosen = self.track_menu(menu, 0x0102, position.x, position.y, 0, window, None)
            self.post(window, 0, 0, 0)  # WM_NULL dismisses the notification menu cleanly.
        finally:
            self.destroy_menu(menu)
        if chosen == OPEN:
            self.restore()
        elif chosen == EXIT:
            self.exit_app()
