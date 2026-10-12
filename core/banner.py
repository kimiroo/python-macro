"""Boxed message printed straight to the console (not through logging), so it stands out."""
import ctypes
import os
import sys
import textwrap
import unicodedata

PAD = 3         # spaces between the border and the text
EDGE = "###"
MARGIN_X = 2    # blank cells left and right of the border; the colored background extends over them
MARGIN_Y = 1    # blank lines above and below
STYLE = "\x1b[1;38;5;88;107m"     # bold dark red text on a bright white background
RESET = "\x1b[0m"


def _width(s):
    """Display width in console columns (full-width characters such as Korean take two)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _lines(text):
    """Split `text` into banner lines: CRLF and tabs are normalized, an indented triple-quoted string is
    dedented, and blank lines around it are dropped (blank lines inside are kept)."""
    text = textwrap.dedent(str(text).replace("\r\n", "\n").replace("\r", "\n").expandtabs(4))
    return [line.rstrip() for line in text.strip("\n").split("\n")] or [""]


def render(text, align="center"):
    """Return the banner for `text` (one or more lines) as a plain string.
    align: "center" (default) or "left" for how the lines sit inside the box."""
    lines = _lines(text)
    inner = max(_width(line) for line in lines) + 2 * PAD
    total = inner + 2 * len(EDGE)

    def row(content=""):
        left = PAD if align == "left" else (inner - _width(content)) // 2
        return EDGE + " " * left + content + " " * (inner - _width(content) - left) + EDGE

    border = "#" * total
    rows = [border, border, row(), *[row(line) for line in lines], row(), border, border]
    blank = " " * (total + 2 * MARGIN_X)
    side = " " * MARGIN_X
    return "\n".join([*[blank] * MARGIN_Y, *[side + r + side for r in rows], *[blank] * MARGIN_Y])


def _color_ok():
    """True if ANSI colors can be used: a real console, NO_COLOR unset, and on Windows virtual terminal
    processing could be enabled."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)                      # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(k32.SetConsoleMode(handle, mode.value | 0x0004))   # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        return False


def banner(text, align="center"):
    """Print the banner with inverted colors (plain text if the console does not support color).
    Multi-line text is supported; align="left" keeps the lines flush left inside the box."""
    lines = render(text, align).split("\n")
    if _color_ok():
        lines = [f"{STYLE}{line}{RESET}" for line in lines]    # color each line so nothing bleeds past it
    print("\n" + "\n".join(lines) + "\n", flush=True)
