"""Precise waiting: sleep most of the time, busy-wait only the last stretch."""
import ctypes
import time

from . import timesync

SPIN = 0.002      # busy-wait for this many seconds right before the target
LEAD = 0.2        # the scheduler wakes precise jobs this many seconds before the target

_boosted = False


def boost():
    """1 ms timer resolution + higher process priority. Applied only once."""
    global _boosted
    if _boosted:
        return
    ctypes.windll.winmm.timeBeginPeriod(1)
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x80)  # HIGH
    _boosted = True


def wait_until(target):
    """Wait until the server-time datetime `target`. Returns immediately if already past."""
    end = time.perf_counter() + (target - timesync.now()).total_seconds()
    coarse = end - SPIN
    while True:
        left = coarse - time.perf_counter()
        if left <= 0:
            break
        time.sleep(min(left, 0.05))
    while time.perf_counter() < end:
        pass
