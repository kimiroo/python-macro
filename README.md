# Macro

A Windows macro driven by on-screen image recognition, keyboard/mouse input, and server time sync.
You only need to edit two files: **`logic.py`** (behavior) and **`config.py`** (settings).

## Running

Run `start.bat`. It finds Python, creates `.venv`, installs dependencies, and launches `main.py`.

## Hotkeys

| Key | Action |
|-----|--------|
| `F1` | ON/OFF toggle. Turning it OFF also stops a running flow immediately. With `AUTO_START=True` it starts ON |
| `` ` `` | Quit (the `~` key, no Shift needed) |

> Neither key can be sent with `ctx.key` (see `core/keys.py`).

## config.py guide

### Images (`IMG_LIST`)

Register the template images to look for on screen as `name: (file path, threshold)`.
The registered name is what you pass to image functions such as `ctx.find("ok_btn")`.

```python
IMG_LIST = {
    "ok_btn":   ("img/ok.png",     0.90),
    "next_btn": ("img/next.png",   0.90),
    "popup":    ("img/popup.png",  0.85),
}
```

- **File path**: relative to the project folder. A wrong path raises `FileNotFoundError` at startup.
- **Threshold**: similarity from 0 to 1 (`cv2.TM_CCOEFF_NORMED`). A match counts only at or above this value.
  - Too high (close to 1.0) and even the same button is missed; too low and it matches the wrong place.
  - Start around `0.85 ~ 0.95` and adjust.
- Save the image **cropped from the real screen at its original size**. Templates are not scaled, so a different resolution or DPI scaling will not match.
- Crop **only the distinctive part**, as small as practical. Avoid areas where the background changes often.
- The returned coordinate is the **center** of the matched image, in screen coordinates.
- If the template is larger than the search area (the target window), the result is always `None`.

### Target window (`TARGET_WINDOW`)

```python
TARGET_WINDOW = ''   # '' = whole screen
```

- Matches a substring of the window title (case-insensitive). Image search and coordinates are relative to this window.
- If the window is not open yet or gets closed, it waits until it opens and re-acquires it.
- You can change it at runtime with `ctx.set_window()` / `ctx.use_active_window()` / `ctx.use_full_screen()`.

### Auto start (`AUTO_START`)

`True` starts ON right away, with no F1 needed. It starts immediately with no delay, so **setting `TARGET_WINDOW` as well is recommended**.

### Server time sync (`SYNC*`)

The system clock is never changed; only the offset from server time is computed and used by `ctx.now()` / `ctx.wait_until()`.

| Setting | Description |
|---------|-------------|
| `SYNC` | `True` starts background sync at startup. It takes 10 samples, then stops and keeps the best offset. Even if `False`, a flow can start it with `ctx.sync_time()` |
| `SYNC_URL` | URL to fetch the time from |
| `SYNC_KEY` | Key path in the JSON response holding the epoch **milliseconds** |
| `SYNC_INTERVAL` | Request interval range in seconds, random within it, one request at a time |
| `SYNC_UA` | User-Agent |
| `SYNC_HEADERS` | Add to / override the default browser headers. A value of `None` removes the header |

```python
SYNC_HEADERS = {"Origin": "https://example.com", "Referer": "https://example.com/event"}
```

## logic.py guide

### ctx: screen (images)

Uses the names registered in `config.IMG_LIST`.

| Function | Description |
|----------|-------------|
| `ctx.find(name)` | `(x, y)` or `None` (based on the current frame) |
| `ctx.refresh()` | Update to the latest frame; `False` if there is no window |
| `ctx.wait_for(name, timeout=5)` | Wait until it appears; returns coordinates or `None` |
| `ctx.wait_click(name, timeout=10)` | Wait then click; stops the flow on timeout (`TimeoutError`) |
| `ctx.click_image(name, offset, after)` | Click if visible and return `True` |

### ctx: input

| Function | Description |
|----------|-------------|
| `ctx.click(pos, offset=(0, 0))` | Click at coordinates |
| `ctx.key("enter")` / `("ctrl+shift+a")` / `("f5")` | Press keys (`hold=0.03, after=0.05, scan=True`) |
| `ctx.scroll(notches, pos=None, at_center=True)` | Mouse-wheel scroll: `> 0` up, `< 0` down. Moves the cursor to `pos`, or to the center of the target window if omitted (`at_center=False` keeps the cursor where it is). All notches go out in one call |
| `ctx.center()` | Center `(x, y)` of the target window / screen, or `None` |
| `ctx.type("hello", interval=0.03)` | Type a string (unicode, any language; use `key` in games) |
| `ctx.key_down("w")` / `ctx.key_up("w")` | Hold a key down (released automatically when the flow ends) |

### ctx: target window

Default is `config.TARGET_WINDOW` (`''` = whole screen).

| Function | Description |
|----------|-------------|
| `ctx.set_window("title", timeout=10)` | Switch to the window whose title contains this; wait until it opens |
| `ctx.focus_window("title", timeout=3)` | Bring the window to the front, restoring it if minimized. No title = the current target window. Does not change the target |
| `ctx.use_active_window()` | Pin the window currently in front |
| `ctx.use_full_screen()` | Go back to the whole screen |

### ctx: time

| Function | Description |
|----------|-------------|
| `ctx.sleep(sec)` | Interruptible wait (use instead of `time.sleep` inside a flow) |
| `ctx.sync_time()` | Start server time sync (refreshes every 2-5 s). Automatic if `config.SYNC=True` |
| `ctx.now()` | Current server time (system time before syncing) |
| `ctx.wait_until(when, precise=False)` | Wait until server time `when` |

`when` formats: `"09:00"` · `"09:00:00.250000"` · `"2026-10-10 09:00:00.25"` · `datetime`

`precise=True` busy-waits the last stretch (microsecond level, <= 0.2 s). That stretch cannot be interrupted.

### How to run (decorators)

All of them only run while ON (needs F1 unless `AUTO_START`).

| Decorator | Description |
|-----------|-------------|
| `@flow(loop=False, start_at=None, precise=False)` | Runs top to bottom, one step at a time. `loop=True` repeats it. `start_at="09:00"` starts at that time once ON (if you need time sync, use `ctx.wait_until` instead) |
| `@at("09:00", precise=False)` | Run the function once at the given time (server time) |
| `@every(seconds=60)` | Run periodically (APScheduler) |
| `@cron(hour=9, minute=0)` | Repeat on a time-of-day schedule (APScheduler, no server-time correction) |
| `step(ctx)` | Repeated every frame when there is no flow |

> flow / step / scheduled jobs share a lock, so they never use the mouse and keyboard at the same time.
