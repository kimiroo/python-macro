"""Low-level Win32 calls (DPI, window info)."""
import ctypes
from ctypes import wintypes

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def set_console_title(text):
    """Set the title of this process's console window (the start.bat window)."""
    ctypes.windll.kernel32.SetConsoleTitleW(str(text))


def foreground_window():
    return user32.GetForegroundWindow()


def cursor_pos():
    """Current cursor position in screen coordinates (x, y)."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def window_at(x, y):
    """Top-level window under the screen point (x, y), or 0."""
    hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return user32.GetAncestor(hwnd, 2) if hwnd else 0     # GA_ROOT


def client_rect(hwnd):
    """Client area of the window in screen coordinates (left, top, width, height). None if unusable."""
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):  # closed / minimized
        return None
    rc = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, rc.right, rc.bottom


def find_window(title, exact=False):
    """hwnd of the first visible top-level window matching `title` (case-insensitive). None if not found.
    exact=False: the title only has to CONTAIN `title` (greedy). exact=True: the whole title must equal it."""
    found = []
    needle = title.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            name = window_title(hwnd).lower()
            if (name == needle) if exact else (needle in name):
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


def window_rect(hwnd):
    """Outer rectangle of the window in screen coordinates (left, top, width, height)."""
    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top


def resize_window(hwnd, width, height, pos=None, client=True):
    """Resize (and optionally move to `pos`) a window. client=True: width x height is the client area
    (what image search sees), so the frame is added on top; client=False: the outer size.
    width/height None keeps the current size (move only).
    A maximized / minimized window is restored first. Returns the resulting client size (w, h), or None
    if the window is gone."""
    if not user32.IsWindow(hwnd):
        return None
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, 9)              # SW_RESTORE
    flags = 0x0004 | 0x0010                      # SWP_NOZORDER | SWP_NOACTIVATE
    if pos is None:
        flags |= 0x0002                          # SWP_NOMOVE
    if width is None or height is None:
        flags |= 0x0001                          # SWP_NOSIZE
        client = False                           # nothing to compute from the frame
    x, y = pos if pos is not None else (0, 0)

    def apply():
        w, h = width, height
        if client:                               # outer = wanted client + current frame
            _, _, ow, oh = window_rect(hwnd)
            c = client_rect(hwnd)
            if c is None:
                return
            w, h = width + ow - c[2], height + oh - c[3]
        user32.SetWindowPos(hwnd, 0, int(x), int(y), int(w or 0), int(h or 0), flags)

    apply()
    rect = client_rect(hwnd)
    if client and rect and (rect[2], rect[3]) != (width, height):
        apply()                                  # the frame can change after the first resize (DPI, restore)
        rect = client_rect(hwnd)
    return (rect[2], rect[3]) if rect else None
