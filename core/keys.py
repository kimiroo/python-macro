"""SendInput keyboard input. Scan-code mode by default, so it also works with DirectInput-style programs."""
from .sendinput import INPUT, INPUT_KEYBOARD, KEYBDINPUT, send
from .winapi import user32

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# name -> (VK, is extended key)
_NAMED = {
    "backspace": (0x08, False), "tab": (0x09, False), "enter": (0x0D, False), "return": (0x0D, False),
    "shift": (0x10, False), "ctrl": (0x11, False), "control": (0x11, False), "alt": (0x12, False),
    "pause": (0x13, False), "capslock": (0x14, False), "esc": (0x1B, False), "escape": (0x1B, False),
    "space": (0x20, False), "pageup": (0x21, True), "pagedown": (0x22, True), "end": (0x23, True),
    "home": (0x24, True), "left": (0x25, True), "up": (0x26, True), "right": (0x27, True),
    "down": (0x28, True), "printscreen": (0x2C, True), "insert": (0x2D, True), "delete": (0x2E, True),
    "win": (0x5B, True), "windows": (0x5B, True), "numlock": (0x90, False),
}
for _i in range(1, 25):
    _NAMED[f"f{_i}"] = (0x6F + _i, False)
for _i in range(10):
    _NAMED[f"num{_i}"] = (0x60 + _i, False)

# Macro control hotkeys. The runtime registers these.
TOGGLE = "f1"      # ON/OFF
QUIT = "esc"       # quit
# Sending these would toggle/quit the macro itself, so ctx.key rejects them
RESERVED = {TOGGLE, QUIT, "escape"}


def parse(spec):
    """"ctrl+shift+a" -> [(vk, extended), ...] (the last one is the main key, the rest are modifiers)"""
    out = []
    for part in spec.lower().replace(" ", "").split("+"):
        if part in RESERVED:
            raise ValueError(f"'{part}' is a macro control hotkey and cannot be sent")
        if part in _NAMED:
            out.append(_NAMED[part])
        elif len(part) == 1:
            r = user32.VkKeyScanW(ord(part))
            if r == -1:
                raise ValueError(f"Unknown key: {part!r}")
            out.append((r & 0xFF, False))
        else:
            raise ValueError(f"Unknown key: {part!r}")
    return out


def _key_input(vk, up, extended, scan_mode):
    flags = KEYEVENTF_KEYUP if up else 0
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if scan_mode:
        scan = user32.MapVirtualKeyW(vk, 0)          # MAPVK_VK_TO_VSC
        return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, flags | KEYEVENTF_SCANCODE, 0, 0))
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, flags, 0, 0))


def key_down(vk, extended=False, scan=True):
    send(_key_input(vk, False, extended, scan))


def key_up(vk, extended=False, scan=True):
    send(_key_input(vk, True, extended, scan))


def type_unicode(text):
    """Send characters as unicode events (any language works; may not work in games)."""
    for ch in text:
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):              # a surrogate pair is sent in two parts
            unit = int.from_bytes(data[i:i + 2], "little")
            for up in (False, True):
                flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
                send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, unit, flags, 0, 0)))
