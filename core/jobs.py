"""Scheduling decorators used in logic.py. The Runtime does the actual running via APScheduler."""

from datetime import datetime, timedelta

from . import timesync

_flow = {}       # {"func": f, "loop": bool, "start_at": spec}
_registry = []   # [(trigger, trigger_kwargs, func, when (@at only), precise)]


def every(**kw):
    """@every(seconds=30) / @every(minutes=5) - run periodically."""
    return _register("interval", kw)


def cron(**kw):
    """@cron(hour=9, minute=0) - run on a time-of-day schedule."""
    return _register("cron", kw)


def at(when, precise=False):
    """@at("2026-10-10 09:00:00.250000") / @at("09:00") - run once at the given time (server time).
    "09:00" means the next 09:00. precise=True sleeps until just before the target, then busy-waits
    to aim for sub-millisecond error."""
    return _register("date", {}, when, precise)


def parse_when(spec):
    """(server time) datetime | "YYYY-MM-DD HH:MM[:SS[.ffffff]]" | "HH:MM[:SS[.ffffff]]" (today, tomorrow if already past) -> datetime"""
    if isinstance(spec, datetime):
        return spec
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(spec, fmt)
        except ValueError:
            pass
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(spec, fmt).time()
        except ValueError:
            continue
        now = timesync.now()
        target = datetime.combine(now.date(), t)
        return target if target > now else target + timedelta(days=1)
    raise ValueError(f"Invalid time format: {spec!r}")


def _register(trigger, kw, when=None, precise=False):
    def deco(func):
        _registry.append((trigger, kw, func, when, precise))
        return func
    return deco


def registered():
    return list(_registry)


def flow(loop=False, start_at=None, precise=False):
    """@flow() - a scenario that runs top to bottom. loop=True restarts it after it finishes.
    start_at="09:00" starts at that time once the macro is ON (it waits until then).
    precise=True makes that wait precise."""
    def deco(func):
        _flow.update(func=func, loop=loop, start_at=start_at, precise=precise)
        return func
    return deco


def registered_flow():
    return _flow.get("func"), _flow.get("loop", False), _flow.get("start_at"), _flow.get("precise", False)
