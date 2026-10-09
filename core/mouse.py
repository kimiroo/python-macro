"""SendInput mouse click."""
from .sendinput import INPUT, INPUT_MOUSE, MOUSEINPUT, send
from .winapi import user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    down = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, 0))
    up = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, 0))
    send(down)
    send(up)
