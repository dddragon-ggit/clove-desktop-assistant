from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QWidget


DWMWA_NCRENDERING_POLICY = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMNCRP_DISABLED = 1
DWMWCP_DONOTROUND = 1
DWMWA_COLOR_NONE = 0xFFFFFFFE
GWL_STYLE = -16
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
WS_BORDER = 0x00800000
WS_CAPTION = 0x00C00000
WS_DLGFRAME = 0x00400000
WS_THICKFRAME = 0x00040000
LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long


def remove_native_window_frame(widget: QWidget) -> bool:
    if sys.platform != "win32":
        return False
    hwnd = int(widget.winId())
    _clear_window_styles(hwnd)
    changed = False
    changed |= _set_dwm_int(hwnd, DWMWA_NCRENDERING_POLICY, DWMNCRP_DISABLED)
    changed |= _set_dwm_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND)
    changed |= _set_dwm_color(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
    return changed


def _clear_window_styles(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_long.restype = LONG_PTR
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
    set_long.restype = LONG_PTR
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    style = int(get_long(hwnd, GWL_STYLE))
    style &= ~(WS_BORDER | WS_CAPTION | WS_DLGFRAME | WS_THICKFRAME)
    set_long(hwnd, GWL_STYLE, style)
    user32.SetWindowPos(
        hwnd,
        0,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
    )


def _set_dwm_int(hwnd: int, attribute: int, value: int) -> bool:
    return _set_dwm_value(hwnd, attribute, ctypes.c_int(value))


def _set_dwm_color(hwnd: int, attribute: int, value: int) -> bool:
    return _set_dwm_value(hwnd, attribute, ctypes.c_uint(value))


def _set_dwm_value(hwnd: int, attribute: int, value: ctypes._SimpleCData) -> bool:
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        ctypes.windll.dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            attribute,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except OSError:
        return False
    return result == 0
