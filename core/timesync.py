"""Offset calculation against the server clock. The system clock is never changed; only now() is corrected.

server time = local time + offset. All times used by logic/schedules are in 'server time'.

A background thread sends ONE request every 2-5 s (random), collects samples,
and adopts the offset of the sample with the shortest RTT among them (no bursts).
It stops by itself after `count` successful samples (default 10); the final offset stays in use.
"""
import http.client
import json
import logging
import random
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from . import browser

log = logging.getLogger(__name__.removeprefix("core."))
_offset = 0.0      # seconds. 0 before syncing (= system time as is)
_samples = deque(maxlen=10)    # [(rtt, offset)]
_thread = None
_finished = False   # True once the sample quota was reached (start() is then a no-op)
_stop = threading.Event()


def offset():
    return _offset


def now():
    """Current server time (naive, local timezone)."""
    return datetime.now() + timedelta(seconds=_offset)


def to_local(server_dt):
    """Server-time datetime -> the same instant on the system clock (for APScheduler)."""
    return server_dt - timedelta(seconds=_offset)


def sample_count():
    return len(_samples)


def running():
    return _thread is not None and _thread.is_alive()


def start(url, key="data", interval=(2.0, 5.0), window=10, timeout=3.0, on_update=None,
          ua=None, headers=None, count=10):
    """Start background sync. Leaves it alone and returns False if already running or already finished.
    count: stop after this many successful samples.
    on_update(offset, rtt) is called from the sync thread each time a sample comes in.
    ua/headers: browser-like request headers (see core.browser.build_headers)."""
    global _thread, _samples
    if running() or _finished:
        return False
    _stop.clear()
    _samples = deque(maxlen=window)
    hdrs = browser.build_headers(url, ua, headers)
    _thread = threading.Thread(target=_loop, args=(url, key, interval, timeout, on_update, hdrs, count),
                               daemon=True, name="timesync")
    _thread.start()
    return True


def stop():
    _stop.set()


def _loop(url, key, interval, timeout, on_update, headers, count):
    global _offset, _finished
    done = 0
    u = urlsplit(url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    conn = cls(u.netloc, timeout=timeout)
    conn.auto_open = 0                 # connect explicitly, outside the timed section
    warned = False
    try:
        while not _stop.is_set():
            sample = None
            for _ in range(2):         # if the keep-alive connection dropped, reconnect and retry once
                try:
                    if conn.sock is None:
                        conn.connect()
                    sample = _measure(conn, path, key, headers)
                    break
                except Exception as e:
                    conn.close()
                    if not warned:
                        log.warning("Time sync request failed: %s", e)
                        warned = True
            if sample:
                warned = False
                _samples.append(sample)
                rtt, off = min(_samples)       # sample with the minimum RTT
                _offset = off
                if on_update:
                    on_update(off, rtt)
                done += 1
                if done >= count:
                    _finished = True
                    log.info("Time sync: done after %d samples, offset %+.2f ms", done, off * 1000)
                    break
            _stop.wait(random.uniform(*interval))
    finally:
        conn.close()


def _measure(conn, path, key, headers):
    """One request -> (rtt seconds, offset seconds).
    Assumes the server timestamp was taken midway between request and response, and adds 0.5 ms
    because the server value is truncated to whole milliseconds."""
    t0, p0 = time.time(), time.perf_counter()
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    rtt = time.perf_counter() - p0
    if resp.status != 200:
        raise RuntimeError(f"HTTP {resp.status}")
    body = browser.decode_body(body, resp.getheader("Content-Encoding"))   # decompression is outside the RTT
    server = _extract(json.loads(body), key) / 1000.0 + 0.0005
    return rtt, server - (t0 + rtt / 2)


def _extract(obj, key):
    for k in key.split("."):
        obj = obj[k]
    return float(obj)
