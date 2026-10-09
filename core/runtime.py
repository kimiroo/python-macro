"""Screen capture, target window, ON/OFF state, hotkeys, main loop, scheduler.
Logic is injected via the step callback and the jobs registered in core.jobs."""
import threading
import time
from datetime import timedelta

import dxcam
import keyboard
from apscheduler.schedulers.background import BackgroundScheduler

from . import jobs, keys, precise, timesync, winapi
from . import precise as precise_mod
from .mouse import click
from .vision import load_templates, match


class Stopped(Exception):
    """The flow was interrupted by turning the macro OFF or by the quit key."""


class Context:
    """Object handed to the logic. The logic only needs to know this. find() works on the frame grabbed at creation/refresh."""

    def __init__(self, rt):
        self._rt = rt
        self._held = set()          # keys pressed via key_down and still held
        self.ready = self.refresh()

    def refresh(self):
        """Update to the latest frame. Returns False if there is no window."""
        self._area, self._origin = self._rt.search_area(self._rt.cam.get_latest_frame())
        self.ready = self._area is not None
        return self.ready

    def find(self, name):
        """Screen coordinates (x, y) of template `name`, or None."""
        if self._area is None:
            return None
        return match(self._area, self._origin, self._rt.templates[name])

    def click(self, pos, offset=(0, 0)):
        self._check()
        click(pos[0] + offset[0], pos[1] + offset[1])

    def key(self, spec, hold=0.03, after=0.05, scan=True):
        """Press a key: ctx.key("enter"), ctx.key("ctrl+shift+a"), ctx.key("f5").
        hold: seconds the key stays down. scan=False uses virtual-key (VK) mode.
        Combo keys are always released, even if interrupted midway."""
        self._check()
        seq = keys.parse(spec)
        pressed = []
        try:
            for vk, ext in seq:                 # press from the front
                keys.key_down(vk, ext, scan)
                pressed.append((vk, ext))
            self.sleep(hold)
        finally:                                # release from the back
            for vk, ext in reversed(pressed):
                keys.key_up(vk, ext, scan)
        self.sleep(after)

    def key_down(self, spec, scan=True):
        """Hold a key down (must be released with key_up). Single key only, no combos."""
        self._check()
        (vk, ext), = keys.parse(spec)
        keys.key_down(vk, ext, scan)
        self._held.add((vk, ext, scan))

    def key_up(self, spec, scan=True):
        (vk, ext), = keys.parse(spec)
        keys.key_up(vk, ext, scan)
        self._held.discard((vk, ext, scan))

    def type(self, text, interval=0.03):
        """Type a string (unicode mode, so any language works). `interval` seconds between characters."""
        for ch in text:
            self._check()
            keys.type_unicode(ch)
            self.sleep(interval)

    def set_window(self, title, timeout=10.0):
        """Switch the search target to the window whose title contains `title`. Waits up to
        `timeout` seconds for it to appear; raises TimeoutError (stops the flow) if not found.
        timeout=0 sets the target without waiting. Afterwards find/click_image only search
        inside that window (persists after the flow ends)."""
        self._rt.set_target(title=title)
        if timeout and self._rt._target_hwnd() is None:
            end = time.monotonic() + timeout
            while self._rt._target_hwnd() is None:
                if time.monotonic() > end:
                    raise TimeoutError(f"Window '{title}' not found within {timeout}s")
                self.sleep(0.1)
        self.refresh()

    def use_active_window(self):
        """Pin the currently focused window as the search target."""
        hwnd = winapi.foreground_window()
        self._rt.set_target(hwnd=hwnd)
        print("Target window:", winapi.window_title(hwnd))
        self.refresh()

    def use_full_screen(self):
        """Go back to searching the whole screen."""
        self._rt.set_target()
        self.refresh()

    def release_all(self):
        """Release every key left held by key_down. Called automatically when a flow ends or is stopped."""
        for vk, ext, scan in list(self._held):
            keys.key_up(vk, ext, scan)
        self._held.clear()

    def click_image(self, name, offset=(0, 0), after=0.3):
        """Click `name` if it is visible and return True."""
        pos = self.find(name)
        if not pos:
            return False
        self.click(pos, offset)
        self.sleep(after)
        return True

    def wait_for(self, name, timeout=5.0, interval=0.05):
        """Wait until `name` appears and return its coordinates. None on timeout."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.refresh():
                pos = self.find(name)
                if pos:
                    return pos
            self.sleep(interval)
        return None

    def wait_click(self, name, timeout=10.0, offset=(0, 0), after=0.3):
        """Wait for `name` and click it. Raises TimeoutError on timeout (stops the flow)."""
        pos = self.wait_for(name, timeout)
        if pos is None:
            raise TimeoutError(f"'{name}' not found within {timeout}s")
        self.click(pos, offset)
        self.sleep(after)

    def now(self):
        """Current server time (system time before sync_time)."""
        return timesync.now()

    def sync_time(self, url=None, key=None, min_samples=3, timeout=30.0):
        """Start server time sync (no-op if already running) and wait until min_samples samples
        are collected. Keeps refreshing in the background every 2-5 s. The system clock is not
        changed. Returns the offset in seconds. url/key default to config.SYNC_URL/SYNC_KEY.
        @at schedules are recomputed on every update."""
        self._rt.start_sync(url, key)
        end = time.monotonic() + timeout
        while timesync.sample_count() < min_samples:
            if time.monotonic() > end:
                raise TimeoutError("sync_time: not enough samples from the server")
            self.sleep(0.05)
        return timesync.offset()

    def wait_until(self, when, precise=False):
        """Wait until server time `when` ("09:00", "09:00:00.250000", "YYYY-MM-DD HH:MM:SS.ffffff", datetime).
        precise=True busy-waits the last stretch (cannot be interrupted, within 0.2 s)."""
        target = jobs.parse_when(when)
        remain = (target - timesync.now()).total_seconds()
        if precise:
            precise_mod.boost()
            self.sleep(max(0.0, remain - precise_mod.LEAD))
            precise_mod.wait_until(target)
        else:
            self.sleep(max(0.0, remain))

    def sleep(self, sec):
        end = time.monotonic() + sec
        while True:
            self._check()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, 0.05))

    def _check(self):
        if not self._rt.running or self._rt.quit:
            raise Stopped


class Runtime:
    def __init__(self, img_list, sync_url=None, sync_key="data", sync=False, sync_interval=(2.0, 5.0),
                 sync_ua=None, sync_headers=None, target_title="", auto_start=False):
        self.sync_url, self.sync_key, self.sync_interval = sync_url, sync_key, sync_interval
        self.sync_ua, self.sync_headers = sync_ua, sync_headers
        self._auto_sync = sync
        self._last_off = None
        self.templates = load_templates(img_list)
        self.target_title = target_title   # empty = full screen mode
        self._hwnd = None
        self._pinned = False      # True: _hwnd is a window pinned directly
        self.running = auto_start   # True: start ON without pressing the toggle key
        self.quit = False
        self.cam = None
        self._sched = None
        self._date_jobs = []     # [(job_id, server-time target, precise)]
        self.lock = threading.Lock()   # so step and scheduled jobs never use the mouse at the same time

    # --- hotkeys ---
    def toggle(self):
        self.running = not self.running
        print("ON" if self.running else "OFF")

    def request_quit(self):
        self.quit = True
        print("Quit")

    def register_hotkeys(self):
        keyboard.add_hotkey(keys.TOGGLE, self.toggle)
        keyboard.add_hotkey(keys.QUIT, self.request_quit)

    # --- search area ---
    def set_target(self, title=None, hwnd=None):
        """Change the search target. title: substring match (re-found if the window changes),
        hwnd: pin a specific window, neither: whole screen."""
        self.target_title = title or ""
        self._pinned = hwnd is not None
        self._hwnd = hwnd

    def _target_hwnd(self):
        """Target window hwnd. In title mode it is cached and re-found when closed.
        In pinned mode it becomes None once the window closes."""
        if self._pinned:
            return self._hwnd if winapi.user32.IsWindow(self._hwnd) else None
        if not (self._hwnd and winapi.user32.IsWindow(self._hwnd)):
            self._hwnd = winapi.find_window(self.target_title)
            if self._hwnd:
                print("Target window:", winapi.window_title(self._hwnd))
        return self._hwnd

    def search_area(self, frame):
        """(cropped image, origin on screen). (None, None) if not possible."""
        if not self.target_title and not self._pinned:
            return frame, (0, 0)
        hwnd = self._target_hwnd()
        if hwnd is None:                 # window not open yet
            return None, None
        r = winapi.client_rect(hwnd)
        if r is None:
            return None, None
        left, top, w, h = r
        H, W = frame.shape[:2]
        x0, y0 = max(left, 0), max(top, 0)
        x1, y1 = min(left + w, W), min(top + h, H)   # drop the part that is off screen
        if x1 <= x0 or y1 <= y0:
            return None, None
        return frame[y0:y1, x0:x1], (x0, y0)

    # --- scheduler ---
    def _wrap(self, func, target=None):
        def run():
            if not self.running:          # scheduled jobs also stay quiet while OFF
                print(f"[{func.__name__}] skipped: macro is OFF ({keys.TOGGLE.upper()} to turn on)")
                return
            with self.lock:
                ctx = Context(self)
                try:
                    if target:            # precise job: busy-wait until the target time
                        precise.wait_until(target)
                    func(ctx)
                finally:
                    ctx.release_all()
        run.__name__ = func.__name__
        return run

    def start_sync(self, url=None, key=None):
        """Start background time sync (ignored if already running)."""
        url = url or self.sync_url
        if not url:
            raise ValueError("sync_time: no url (pass one or set config.SYNC_URL)")
        if timesync.start(url, key or self.sync_key, interval=self.sync_interval, on_update=self._on_sync,
                          ua=self.sync_ua, headers=self.sync_headers):
            print("Time sync: syncing with", url)

    def _on_sync(self, off, rtt):
        print(f"Time sync: syncing... offset {off * 1000:+.2f} ms (best RTT {rtt * 1000:.1f} ms, "
              f"{timesync.sample_count()} samples)")
        if self._last_off is None or abs(off - self._last_off) > 1e-4:   # reschedule if it moved by 0.1 ms or more
            self._last_off = off
            self._reschedule_dates()

    def _reschedule_dates(self):
        """The offset changed, so recompute the run times (system clock) of @at jobs."""
        if not self._sched:
            return
        for job_id, target, prec in list(self._date_jobs):
            try:
                self._sched.reschedule_job(job_id, trigger="date", run_date=self._run_date(target, prec))
            except Exception:       # job already ran and was removed
                pass

    @staticmethod
    def _run_date(target, prec):
        return timesync.to_local(target) - timedelta(seconds=precise.LEAD if prec else 0)

    def start_scheduler(self):
        registered = jobs.registered()
        if not registered:
            return None
        if any(prec for *_, prec in registered):
            precise.boost()
        sched = self._sched = BackgroundScheduler()
        for trigger, kw, func, when, prec in registered:
            target = None
            if trigger == "date":       # convert server time -> system clock for the scheduler
                target = jobs.parse_when(when)
                kw = {"run_date": self._run_date(target, prec)}
            # if the previous run has not finished, skip instead of overlapping
            job = sched.add_job(self._wrap(func, target if prec else None), trigger,
                                max_instances=1, coalesce=True, **kw)
            if trigger == "date":
                self._date_jobs.append((job.id, target, prec))
        sched.start()
        self._sched = sched
        return sched

    # --- main loop ---
    def run(self, step=None):
        self.register_hotkeys()
        if self.running:
            print(f"Auto start: ON ({keys.TOGGLE.upper()} to stop, {keys.QUIT} to quit)")
        if self._auto_sync:                           # SYNC enabled: start background sync right away
            try:
                self.start_sync()
            except ValueError as e:
                print("SYNC is enabled but", e)
        self.cam = dxcam.create(output_color="BGR")   # whole primary monitor
        self.cam.start(target_fps=60)
        sched = self.start_scheduler()
        flow_fn, loop, start_at, prec = jobs.registered_flow()
        try:
            while not self.quit:
                if not self.running or (step is None and flow_fn is None):
                    time.sleep(0.01)
                    continue
                if flow_fn:
                    self._run_flow(flow_fn, loop, start_at, prec)
                    continue
                with self.lock:
                    ctx = Context(self)
                    ok = ctx.ready
                    try:
                        if ok:
                            step(ctx)
                    finally:
                        ctx.release_all()
                time.sleep(0.01 if ok else 0.05)   # rest a bit longer if the window is minimized/closed/off screen
        finally:
            timesync.stop()
            if sched:
                sched.shutdown(wait=False)
            self.cam.stop()

    def _run_flow(self, fn, loop, start_at, prec):
        try:
            if start_at:                                  # scheduled start: wait without holding the lock
                target = jobs.parse_when(start_at)
                print("Flow waiting, scheduled start:", target)
                ctx = Context(self)
                if prec:
                    precise.boost()
                    ctx.sleep(max(0.0, (target - timesync.now()).total_seconds() - precise.LEAD))
                    precise.wait_until(target)      # last stretch is a busy-wait (not interruptible, within 0.2 s)
                else:
                    ctx.sleep(max(0.0, (target - timesync.now()).total_seconds()))
            with self.lock:
                while True:
                    ctx = Context(self)
                    try:
                        fn(ctx)
                    finally:
                        ctx.release_all()     # release held keys even on stop/error
                    if not loop:
                        print("Flow finished")
                        self.running = False
                        return
        except Stopped:
            print("Flow stopped")
        except TimeoutError as e:
            print("Flow failed:", e)
            self.running = False
