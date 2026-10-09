"""SendInput mouse click."""
import time

from .sendinput import INPUT, INPUT_MOUSE, MOUSEINPUT, send
from .winapi import user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


def move(x, y):
    """Move the cursor to (x, y) without clicking."""
    user32.SetCursorPos(int(x), int(y))


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    down = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0))
    up = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0))
    send(down)
    send(up)


def scroll(notches, pos=None):
    """Wheel-scroll under the cursor (or at `pos` if given). notches > 0 up, < 0 down.
    All notches go out in a single SendInput call."""
    if pos is not None:
        user32.SetCursorPos(int(pos[0]), int(pos[1]))
        time.sleep(0.05)               # let the target see the cursor before the wheel arrives
    step = WHEEL_DELTA if notches > 0 else -WHEEL_DELTA
    wheel = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, step & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, 0))
    send(*[wheel] * abs(int(notches)))
