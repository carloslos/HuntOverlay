# Win32 helpers: async key state and window styling via ctypes.
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GetKey = user32.GetAsyncKeyState

# Access right needed to query an image name without full read access.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Declare signatures so 64-bit handles are not truncated to 32-bit ints.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def key(vk: int) -> bool:
    return (GetKey(vk) & 0x8000) != 0


def foreground_process_name() -> str:
    """
    Return the executable name (without extension) of the process that owns the
    current foreground window, lowercased. Returns "" if it cannot be resolved.
    Cheap enough to call on demand (a few Win32 calls, no polling).
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""

        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""

        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return ""
            path = buf.value
        finally:
            kernel32.CloseHandle(h)

        name = path.rsplit("\\", 1)[-1]
        if name.lower().endswith(".exe"):
            name = name[:-4]
        return name.lower()
    except:
        return ""


def topmost(hwnd: int) -> None:
    try:
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10 | 0x40)
    except:
        pass


def click_through(hwnd: int) -> None:
    try:
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x80 | 0x8000000 | 0x20)
    except:
        pass
