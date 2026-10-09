"""Build browser-like (fetch/XHR) request headers. Stateful parts such as cookies are not handled."""
import gzip
import re
import zlib
from urllib.parse import urlsplit

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")


def build_headers(url, ua=None, extra=None):
    """Headers that look like a same-site page calling an API with fetch().
    If `ua` is Chrome-based, sec-ch-ua* headers are added to match the UA version.
    `extra` adds/overrides headers (a value of None removes the header)."""
    ua = ua or DEFAULT_UA
    u = urlsplit(url)
    h = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate",      # br/zstd cannot be decoded with the standard library, so omitted
        "Referer": f"{u.scheme}://{u.netloc}/",
        "User-Agent": ua,
    }
    m = re.search(r"Chrome/(\d+)", ua)
    if m and "Firefox" not in ua:
        v = m.group(1)
        if "Edg/" in ua:
            brand = f'"Microsoft Edge";v="{v}"'
        else:
            brand = f'"Google Chrome";v="{v}"'
        h["sec-ch-ua"] = f'"Chromium";v="{v}", "Not.A/Brand";v="24", {brand}'
        h["sec-ch-ua-mobile"] = "?1" if "Mobile" in ua else "?0"
        h["sec-ch-ua-platform"] = f'"{_platform(ua)}"'
        h["Sec-Fetch-Dest"] = "empty"
        h["Sec-Fetch-Mode"] = "cors"
        h["Sec-Fetch-Site"] = "same-origin"
    for k, v in (extra or {}).items():
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    return h


def _platform(ua):
    if "Windows" in ua:
        return "Windows"
    if "Android" in ua:
        return "Android"
    if "Macintosh" in ua:
        return "macOS"
    if "Linux" in ua:
        return "Linux"
    return "Unknown"


def decode_body(body, encoding):
    """Decode Content-Encoding (gzip/deflate). Anything else is returned as is."""
    enc = (encoding or "").lower()
    if "gzip" in enc:
        return gzip.decompress(body)
    if "deflate" in enc:
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body
