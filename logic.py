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
