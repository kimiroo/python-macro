"""Low-level Win32 calls (DPI, window info)."""
import ctypes
from ctypes import wintypes

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def foreground_window():
    return user32.GetForegroundWindow()


def client_rect(hwnd):
    """Client area of the window in screen coordinates (left, top, width, height). None if unusable."""
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):  # closed / minimized
        return None
    rc = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, rc.right, rc.bottom


def find_window(substr):
    """hwnd of the first visible top-level window whose title contains `substr` (case-insensitive). None if not found."""
    found = []
    needle = substr.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and needle in window_title(hwnd).lower():
            found.append(hwnd)
            return False        # found it, stop enumerating
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def bring_to_front(hwnd):
    """Restore (if minimized) and focus the window. Returns True if it ended up in front.
    Windows blocks SetForegroundWindow from background processes, so attach to the input
    queue of the current foreground thread first."""
    if not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)              # SW_RESTORE
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    attached = bool(fg_thread) and fg_thread != cur and user32.AttachThreadInput(cur, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur, fg_thread, False)
    return user32.GetForegroundWindow() == hwnd
