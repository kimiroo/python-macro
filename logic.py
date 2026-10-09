"""Macro logic. This is the only file you need to edit.

=== Hotkeys ===
  F1  ON/OFF (turning it OFF also stops a running flow immediately). With config.AUTO_START=True it starts ON.
  `   Quit (the ~ key, no Shift needed).  Note: neither key can be sent with ctx.key (see core/keys.py)

=== ctx: screen (images) ===   register template names in config.IMG_LIST
  ctx.find(name)                       -> (x, y) or None        (based on the current frame)
  ctx.refresh()                        -> update to the latest frame, False if there is no window
  ctx.wait_for(name, timeout=5)        -> wait until it appears, returns coordinates or None
  ctx.wait_click(name, timeout=10)     -> wait then click, stops the flow on timeout (TimeoutError)
  ctx.click_image(name, offset, after) -> click if visible and return True

=== ctx: input ===
  ctx.click(pos, offset=(0, 0))        -> click at coordinates
  ctx.key("enter") / ("ctrl+shift+a") / ("f5")   -> press keys (hold=0.03, after=0.05, scan=True)
  ctx.type("hello", interval=0.03)     -> type a string (unicode, any language / use key in games)
  ctx.key_down("w") / ctx.key_up("w")  -> hold a key down (released automatically when the flow ends)

=== ctx: target window ===   default is config.TARGET_WINDOW ('' = whole screen)
  ctx.set_window("title", timeout=10)  -> switch to the window whose title contains this, wait until it opens
  ctx.use_active_window()              -> pin the window that is currently in front
  ctx.use_full_screen()                -> go back to the whole screen

=== ctx: time ===
  ctx.sleep(sec)                       -> interruptible wait (use this instead of time.sleep inside a flow)
  ctx.sync_time()                      -> start server time sync (refreshes every 2-5 s). Automatic if config.SYNC=True
  ctx.now()                            -> current server time (system time before syncing)
  ctx.wait_until(when, precise=False)  -> wait until server time `when`
        when: "09:00" | "09:00:00.250000" | "2026-10-10 09:00:00.25" | datetime
        precise=True: busy-wait the last stretch (microsecond level, that stretch cannot be interrupted, <= 0.2 s)

=== How to run (decorators) ===   all of them only run while ON (needs F1 unless AUTO_START)
  @flow(loop=False, start_at=None, precise=False)
        Runs top to bottom, one step at a time. loop=True repeats it.
        start_at="09:00" starts at that time once ON (if you need time sync, use ctx.wait_until instead of start_at)
  @at("09:00", precise=False)          run the function once at the given time (server time)
  @every(seconds=60)                   run periodically (APScheduler)
  @cron(hour=9, minute=0)              repeat on a time-of-day schedule (APScheduler, no server-time correction)
  step(ctx)                            repeated every frame when there is no flow
  Note: flow / step / scheduled jobs share a lock, so they never use the mouse and keyboard at the same time.
"""
from core.jobs import flow
from core.runtime import Context


@flow(loop=False)          # loop=True restarts it after it finishes
def main(ctx: Context):
    ctx.wait_click("next_btn", timeout=10)      # 1) wait for next_btn to appear, then click it
    ctx.wait_for("popup", timeout=5)            # 2) wait for the popup to show up
    ctx.wait_click("ok_btn")                    # 3) click ok_btn
    ctx.sleep(1)                                # 4) short pause
    if ctx.click_image("next_btn"):             # 5) click it if present, otherwise move on
        ctx.sleep(0.5)
