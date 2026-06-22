# Win32 helpers: async key state and window styling via ctypes.
import ctypes

user32 = ctypes.windll.user32
GetKey = user32.GetAsyncKeyState


def key(vk: int) -> bool:
    return (GetKey(vk) & 0x8000) != 0


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
