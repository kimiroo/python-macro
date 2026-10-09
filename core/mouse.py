"""SendInput mouse click."""
import time

from .sendinput import INPUT, INPUT_MOUSE, MOUSEINPUT, send
from .winapi import cursor_pos, user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
WHEEL_DELTA = 120


def _move(x, y):
    """One real mouse-move event (SendInput), so pages see a genuine mousemove.
    Coordinates are normalized to 0..65535 over the whole virtual desktop."""
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)    # virtual screen origin
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)    # virtual screen size
    nx = round((x - vx) * 65535 / max(vw - 1, 1))
    ny = round((y - vy) * 65535 / max(vh - 1, 1))
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(nx, ny, 0, flags, 0, 0)))


def move(x, y, duration=0.0, wait=time.sleep):
    """Move the cursor to (x, y) without clicking. duration > 0 moves in a straight line over that
    many seconds (progress is time-based, so the total stays ~duration). `wait` is the sleep used
    between steps; pass an interruptible one."""
    x, y = int(x), int(y)
    if duration > 0:
        sx, sy = cursor_pos()
        t0 = time.perf_counter()
        while True:
            t = (time.perf_counter() - t0) / duration
            if t >= 1:
                break
            _move(sx + (x - sx) * t, sy + (y - sy) * t)
            wait(0.005)
    _move(x, y)                        # always end exactly on the target


def click(x=None, y=None):
    """Left-click at (x, y), or at the current cursor position if no coordinates are given."""
    if x is not None and y is not None:
        user32.SetCursorPos(int(x), int(y))
    down = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0))
    up = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0))
    send(down)
    send(up)


def scroll(notches, pos=None):
    """Wheel-scroll under the cursor (or at `pos` if given). notches > 0 up, < 0 down.
    All notches go out in a single SendInput call."""
    if pos is not None:
        _move(int(pos[0]), int(pos[1]))
        time.sleep(0.05)               # let the target see the cursor before the wheel arrives
    step = WHEEL_DELTA if notches > 0 else -WHEEL_DELTA
    wheel = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, step & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, 0))
    send(*[wheel] * abs(int(notches)))
