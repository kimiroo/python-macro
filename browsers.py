"""Browser window-title suffixes, chosen by config.TARGET_BROWSER.

Browsers append their name to the page title ("<page> - Chrome"), so a suffix lets a
title match stay unambiguous: ctx.set_window(f"{page}{BROWSER_STRING}")."""
from config import TARGET_BROWSER

BROWSER_TITLES = {
    "chrome":  " - Chrome",
    "firefox": " — Mozilla Firefox",       # em dash (U+2014), not a hyphen
}

try:
    BROWSER_STRING = BROWSER_TITLES[TARGET_BROWSER.lower()]
except KeyError:
    raise ValueError(f"config.TARGET_BROWSER must be one of {sorted(BROWSER_TITLES)}, got {TARGET_BROWSER!r}") from None


def title(page=""):
    """Window title text for a page: title("My page") -> "My page - Chrome"."""
    return f"{page}{BROWSER_STRING}"
