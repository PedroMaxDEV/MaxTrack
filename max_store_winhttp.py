"""HTTPS transport for the Windows Hub, using the system trust and proxy settings."""
import ctypes
from ctypes import wintypes
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlsplit


HINTERNET = ctypes.c_void_p
LPVOID = ctypes.c_void_p
DWORD_PTR = ctypes.c_size_t
LPDWORD = ctypes.POINTER(wintypes.DWORD)
WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY = 4
WINHTTP_FLAG_SECURE = 0x00800000
WINHTTP_OPTION_REDIRECT_POLICY = 88
WINHTTP_OPTION_REDIRECT_POLICY_NEVER = 0
WINHTTP_QUERY_STATUS_CODE = 19
WINHTTP_QUERY_FLAG_NUMBER = 0x20000000


def winhttp():
    dll = ctypes.WinDLL('winhttp.dll', use_last_error=True, winmode=0x800)
    dword, string, boolean = wintypes.DWORD, wintypes.LPCWSTR, wintypes.BOOL
    signatures = {
        'WinHttpOpen': (HINTERNET, string, dword, string, string, dword),
        'WinHttpSetTimeouts': (boolean, HINTERNET, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int),
        'WinHttpConnect': (HINTERNET, HINTERNET, string, wintypes.WORD, dword),
        'WinHttpOpenRequest': (HINTERNET, HINTERNET, string, string, string, string, LPVOID, dword),
        'WinHttpSetOption': (boolean, HINTERNET, dword, LPVOID, dword),
        'WinHttpSendRequest': (boolean, HINTERNET, string, dword, LPVOID, dword, dword, DWORD_PTR),
        'WinHttpReceiveResponse': (boolean, HINTERNET, LPVOID),
        'WinHttpQueryHeaders': (boolean, HINTERNET, dword, string, LPVOID, LPDWORD, LPDWORD),
        'WinHttpReadData': (boolean, HINTERNET, LPVOID, dword, LPDWORD),
        'WinHttpCloseHandle': (boolean, HINTERNET),
    }
    for name, (result, *arguments) in signatures.items():
        function = getattr(dll, name)
        function.restype = result
        function.argtypes = arguments
    return dll


def checked(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class Response:
    def __init__(self, dll, handles, status):
        self.dll, self.handles, self.status = dll, handles, status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def close(self):
        while self.handles:
            self.dll.WinHttpCloseHandle(self.handles.pop())

    def read(self, size):
        buffer = ctypes.create_string_buffer(size)
        offset = 0
        count = wintypes.DWORD()
        while offset < size:
            checked(self.dll.WinHttpReadData(self.handles[-1], ctypes.byref(buffer, offset),
                                              size - offset, ctypes.byref(count)))
            if not count.value:
                break
            offset += count.value
        return buffer.raw[:offset]


def open_https(origin, path, agent, body, timeout):
    dll = winhttp()
    handles = []
    try:
        session = checked(dll.WinHttpOpen(agent, WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, None, None, 0))
        handles.append(session)
        millis = int(timeout * 1000)
        checked(dll.WinHttpSetTimeouts(session, millis, millis, millis, millis))
        connection = checked(dll.WinHttpConnect(session, urlsplit(origin).hostname, 443, 0))
        handles.append(connection)
        method = 'POST' if body is not None else 'GET'
        request = checked(dll.WinHttpOpenRequest(connection, method, path, None, None, None, WINHTTP_FLAG_SECURE))
        handles.append(request)
        redirect = wintypes.DWORD(WINHTTP_OPTION_REDIRECT_POLICY_NEVER)
        checked(dll.WinHttpSetOption(request, WINHTTP_OPTION_REDIRECT_POLICY,
                                     ctypes.byref(redirect), ctypes.sizeof(redirect)))
        headers = 'Content-Type: application/json\r\n' if body is not None else None
        size = len(body) if body is not None else 0
        checked(dll.WinHttpSendRequest(request, headers, len(headers or ''), body, size, size, 0))
        checked(dll.WinHttpReceiveResponse(request, None))
        status = wintypes.DWORD()
        length = wintypes.DWORD(ctypes.sizeof(status))
        checked(dll.WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                                         None, ctypes.byref(status), ctypes.byref(length), None))
    except BaseException:
        Response(dll, handles, None).close()
        raise
    response = Response(dll, handles, status.value)
    if not 200 <= response.status < 300:
        with response:
            try:
                message = response.read(4096)
            except OSError:
                message = b''
        raise HTTPError(origin + path, response.status, 'Resposta HTTP', None, BytesIO(message))
    return response
