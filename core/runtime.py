"""Screen capture, target window, ON/OFF state, hotkeys, main loop, scheduler.
Logic is injected via the step callback and the jobs registered in core.jobs."""
import logging
import os
import threading
import time
from datetime import timedelta

import cv2
import dxcam
import keyboard
from apscheduler.schedulers.background import BackgroundScheduler

from . import jobs, keys, precise, timesync, winapi
from . import precise as precise_mod
from .banner import banner
from .mouse import click, move, scroll
from .ocr import ocr, resolve_key
from .vision import load_templates, match

log = logging.getLogger(__name__.removeprefix("core."))


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

    def crop(self, anchor=None, offset=(0, 0), size=(100, 100), scale=1.0, save=None):
        """Cut a region out of the current frame, positioned relative to an anchor so it follows the
        window / layout. anchor: screen (x, y) such as ctx.find(name) (None = top-left of the target
        window). The region's top-left is anchor + offset, `size` is (w, h) in pixels; scale multiplies
        offset and size (e.g. the browser zoom ratio). The part outside the window is dropped.
        save: PNG path to write (folders are created). Returns the BGR image, or None if empty."""
        if self._area is None:
            return None
        ax, ay = anchor if anchor is not None else self._origin
        x0 = round(ax + offset[0] * scale) - self._origin[0]
        y0 = round(ay + offset[1] * scale) - self._origin[1]
        h, w = self._area.shape[:2]
        x1, y1 = x0 + round(size[0] * scale), y0 + round(size[1] * scale)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        if x1 <= x0 or y1 <= y0:
            return None
        img = self._area[y0:y1, x0:x1].copy()
        if save:
            os.makedirs(os.path.dirname(os.path.abspath(save)), exist_ok=True)
            ok, buf = cv2.imencode(os.path.splitext(save)[1] or ".png", img)   # imwrite breaks on non-ASCII paths
            if ok:
                buf.tofile(save)
        return img

    def ocr(self, image):
        """Read the text in `image` with Google Cloud Vision: a BGR image such as ctx.crop(...), or an
        image file path. Returns the text with whitespace removed, or None (also when image is None
        or OCR is disabled because config.OCR_KEY is empty / the key file is missing)."""
        self._check()
        if self._rt.ocr_key is None:
            log.warning("OCR skipped: disabled (set config.OCR_KEY to the service-account key file)")
            return None
        if image is None:
            log.warning("OCR failed: no image")
            return None
        return ocr(image, self._rt.ocr_key)

    def click(self, pos=None, offset=(0, 0)):
        """Click at pos (+ offset), or at the current cursor position if pos is omitted."""
        self._check()
        if pos is None:
            click()
        else:
            click(pos[0] + offset[0], pos[1] + offset[1])

    def move(self, pos=None, offset=(0, 0), duration=0.0):
        """Move the cursor without clicking. Without `pos`, to the center of the target window / screen.
        duration > 0 moves in a straight line over that many seconds (0 = instant). Returns the position moved to, or None if the window is not available."""
        self._check()
        if pos is None:
            pos = self.center()
            if pos is None:
                return None
        pos = (pos[0] + offset[0], pos[1] + offset[1])
        move(*pos, duration, self.sleep)
        return pos

    def stop(self, message=None):
        """End the running flow/job and switch the macro OFF (press the toggle key to start again from
        the top). `message` is shown as a banner instead of the flow's on_stop message."""
        self._rt.running = False
        self._rt.stop_message = message
        raise Stopped

    def quit(self, message=None):
        """End the running flow/job and quit the whole app. `message` is shown as a banner."""
        self._rt.stop_message = message
        self._rt.request_quit()
        raise Stopped

    def banner(self, text, align="center"):
        """Print `text` in a box on the console (not the log) so it is noticed at a glance.
        Multi-line text works; align="left" keeps the lines flush left inside the box."""
        banner(text, align)

    def center(self):
        """Center (x, y) of the target window (or the whole screen). None if the window is not available."""
        if self._area is None:
            return None
        h, w = self._area.shape[:2]
        return self._origin[0] + w // 2, self._origin[1] + h // 2

    def scroll(self, notches, pos=None, at_center=True):
        """Mouse-wheel scroll: notches > 0 up, < 0 down (a notch is about 3 lines in most browsers).
        The cursor is moved to `pos` first; without `pos` it goes to the center of the target window
        (at_center=True), or stays where it is (at_center=False)."""
        self._check()
        if pos is None and at_center:
            pos = self.center()
            if pos is None:
                log.warning("scroll skipped: target window not available")
                return
        target = self._rt._target_hwnd() if (self._rt.target_title or self._rt._pinned) else None
        if pos is not None and target:
            under = winapi.window_at(*pos)
            if under != target:       # the wheel goes to whatever window is under the cursor
                log.warning("scroll: %s is covered by another window: %r", pos, winapi.window_title(under))
        scroll(notches, pos, wait=self.sleep)

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

    def set_window(self, title, timeout=10.0, exact=False):
        """Switch the search target to the window whose title contains `title` (exact=True: whose whole
        title equals it; both case-insensitive). Waits up to
        `timeout` seconds for it to appear; raises TimeoutError (stops the flow) if not found.
        timeout=0 sets the target without waiting. Afterwards find/click_image only search
        inside that window (persists after the flow ends)."""
        self._rt.set_target(title=title, exact=exact)
        if timeout and self._rt._target_hwnd() is None:
            end = time.monotonic() + timeout
            while self._rt._target_hwnd() is None:
                if time.monotonic() > end:
                    raise TimeoutError(f"Window '{title}' not found within {timeout}s")
                self.sleep(0.1)
        self.refresh()

    def focus_window(self, title=None, timeout=3.0, exact=False):
        """Bring a window to the front. With `title`, the first visible window whose title contains it
        (exact=True: whose whole title equals it; the search target is not changed; combine with set_window if needed). Without `title`, the
        current target window. Restores it if minimized. Retries for up to `timeout` seconds and
        raises TimeoutError (stops the flow) if it cannot be brought forward."""
        end = time.monotonic() + timeout
        while True:
            hwnd = winapi.find_window(title, exact) if title else self._rt._target_hwnd()
            if hwnd and winapi.bring_to_front(hwnd):
                self.sleep(0.05)
                self.refresh()
                return
            if time.monotonic() > end:
                raise TimeoutError(f"Could not bring window '{title or self._rt.target_title or 'target'}' to front")
            self.sleep(0.1)

    def resize_window(self, size, pos=None, title=None, exact=False, client=True, timeout=3.0):
        """Resize a window, optionally moving it to `pos` (screen x, y). `title` picks the window like
        focus_window (exact=True: whole title must match); without it the current target window is used.
        client=True: `size` is the client area, which is what find/crop see (browsers draw tabs and the
        address bar inside it); client=False: the outer window size. A maximized window is restored first.
        Raises TimeoutError if the window is not found. Returns the resulting client size (w, h);
        it differs from `size` when the app refuses it (e.g. below the minimum window size)."""
        end = time.monotonic() + timeout
        while True:
            hwnd = winapi.find_window(title, exact) if title else self._rt._target_hwnd()
            if hwnd:
                break
            if time.monotonic() > end:
                raise TimeoutError(f"Window '{title or self._rt.target_title or 'target'}' not found within {timeout}s")
            self.sleep(0.1)
        result = winapi.resize_window(hwnd, size[0], size[1], pos, client)
        self.sleep(0.05)
        self.refresh()
        if result is not None and client and tuple(result) != tuple(size):
            log.warning("resize_window: asked for %s, got %s", tuple(size), tuple(result))
        return result

    def use_active_window(self):
        """Pin the currently focused window as the search target."""
        hwnd = winapi.foreground_window()
        self._rt.set_target(hwnd=hwnd)
        log.info("Target window: %s", winapi.window_title(hwnd))
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

    def wait_any(self, names, timeout=5.0, interval=0.05):
        """Wait until ANY of `names` appears. Returns (name, (x, y)) of the first one found
        (in list order if several are visible in the same frame), or None on timeout."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.refresh():
                for name in names:
                    pos = self.find(name)
                    if pos:
                        return name, pos
            self.sleep(interval)
        return None

    def wait_for(self, name, timeout=5.0, interval=0.05):
        """Wait until `name` appears and return its coordinates. None on timeout."""
        hit = self.wait_any([name], timeout, interval)
        return hit[1] if hit else None

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
                 sync_ua=None, sync_headers=None, target_title="", auto_start=False, target_exact=False,
                 ocr_key=""):
        self.sync_url, self.sync_key, self.sync_interval = sync_url, sync_key, sync_interval
        self.ocr_key = resolve_key(ocr_key)   # None: OCR disabled
        self.sync_ua, self.sync_headers = sync_ua, sync_headers
        self._auto_sync = sync
        self._last_off = None
        self.templates = load_templates(img_list)
        self.target_title = target_title   # empty = full screen mode
        self.target_exact = target_exact   # False: title substring (greedy), True: whole title must match
        self._hwnd = None
        self._pinned = False      # True: _hwnd is a window pinned directly
        self.running = auto_start   # True: start ON without pressing the toggle key
        self.quit = False
        self.stop_message = None      # banner text set by ctx.stop / ctx.quit, shown instead of on_stop
        self.cam = None
        self._sched = None
        self._date_jobs = []     # [(job_id, server-time target, precise)]
        self.lock = threading.Lock()   # so step and scheduled jobs never use the mouse at the same time

    # --- hotkeys ---
    def toggle(self):
        self.running = not self.running
        log.info("ON" if self.running else "OFF")

    def request_quit(self):
        self.quit = True
        log.info("Quit")

    def register_hotkeys(self):
        keyboard.add_hotkey(keys.TOGGLE, self.toggle)
        keyboard.add_hotkey(keys.QUIT, self.request_quit)

    # --- search area ---
    def set_target(self, title=None, hwnd=None, exact=False):
        """Change the search target. title: substring match, or whole-title match with exact=True
        (re-found if the window changes), hwnd: pin a specific window, neither: whole screen."""
        self.target_title = title or ""
        self.target_exact = exact
        self._pinned = hwnd is not None
        self._hwnd = hwnd

    def _target_hwnd(self):
        """Target window hwnd. In title mode it is cached and re-found when closed.
        In pinned mode it becomes None once the window closes."""
        if self._pinned:
            return self._hwnd if winapi.user32.IsWindow(self._hwnd) else None
        if not (self._hwnd and winapi.user32.IsWindow(self._hwnd)):
            self._hwnd = winapi.find_window(self.target_title, self.target_exact)
            if self._hwnd:
                log.info("Target window: %s", winapi.window_title(self._hwnd))
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
                log.warning("[%s] skipped: macro is OFF (%s to turn on)", func.__name__, keys.TOGGLE.upper())
                return
            with self.lock:
                ctx = Context(self)
                try:
                    if target:            # precise job: busy-wait until the target time
                        precise.wait_until(target)
                    func(ctx)
                except Stopped:
                    log.info("[%s] stopped", func.__name__)
                    self._show_stop_message()
                finally:
                    ctx.release_all()
        run.__name__ = func.__name__
        return run

    def _show_stop_message(self, align="center"):
        """Show (once) the banner set by ctx.stop / ctx.quit. Returns True if there was one."""
        text, self.stop_message = self.stop_message, None
        if text:
            banner(text, align)
        return bool(text)

    def start_sync(self, url=None, key=None):
        """Start background time sync (ignored if already running)."""
        url = url or self.sync_url
        if not url:
            raise ValueError("sync_time: no url (pass one or set config.SYNC_URL)")
        if timesync.start(url, key or self.sync_key, interval=self.sync_interval, on_update=self._on_sync,
                          ua=self.sync_ua, headers=self.sync_headers):
            log.info("Time sync: syncing with %s", url)

    def _on_sync(self, off, rtt):
        log.debug("Time sync: syncing... offset %+.2f ms (best RTT %.1f ms, %d samples)",
                 off * 1000, rtt * 1000, timesync.sample_count())
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
            log.info("Auto start: ON (%s to stop, %s to quit)", keys.TOGGLE.upper(), keys.QUIT)
        if self._auto_sync:                           # SYNC enabled: start background sync right away
            try:
                self.start_sync()
            except ValueError as e:
                log.warning("SYNC is enabled but %s", e)
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
                    except Stopped:
                        log.info("Step stopped")
                        self._show_stop_message()
                    finally:
                        ctx.release_all()
                time.sleep(0.01 if ok else 0.05)   # rest a bit longer if the window is minimized/closed/off screen
        finally:
            timesync.stop()
            if sched:
                sched.shutdown(wait=False)
            self.cam.stop()

    def _run_flow(self, fn, loop, start_at, prec):
        msgs, align = jobs.flow_messages(), jobs.flow_banner_align()

        def say(kind, error=None):
            text = msgs.get(kind)
            if text:
                banner(text.replace("{error}", str(error)) if error is not None else text, align)

        try:
            if start_at:                                  # scheduled start: wait without holding the lock
                target = jobs.parse_when(start_at)
                log.info("Flow waiting, scheduled start: %s", target)
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
                        log.info("Flow finished")
                        say("done")
                        self.running = False
                        return
        except Stopped:
            log.info("Flow stopped")
            if not self._show_stop_message(align):    # ctx.stop / ctx.quit message replaces on_stop
                say("stop")
        except TimeoutError as e:
            log.error("Flow failed: %s", e)
            say("error", e)
            self.running = False
        except Exception as e:           # a bug in the flow: show the banner, then crash with the traceback as before
            say("error", e)
            raise
