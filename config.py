# Template images. name -> (file path, threshold)
IMG_LIST = {
    "ok_btn":   ("img/ok.png",     0.90),
    "next_btn": ("img/next.png",   0.90),
    "popup":    ("img/popup.png",  0.85),
}

# True: start ON right away (no toggle key needed). It starts immediately with no delay,
# so setting TARGET_WINDOW to pin the target window is recommended.
AUTO_START = True

# Target window title (substring match, case-insensitive). Empty ('') searches the whole screen.
# If the window is not open yet or gets closed, it waits until the window opens and re-acquires it.
TARGET_WINDOW = ''
# False: the window title only has to contain TARGET_WINDOW (greedy). True: the whole title must equal it.
TARGET_EXACT = False

# Server time sync (the system clock is never changed)
# SYNC = True starts background sync right at startup. Even if False, a flow can start it with ctx.sync_time().
# The value at the SYNC_KEY path in the JSON response is read as epoch milliseconds.
SYNC = True
SYNC_URL = ''
SYNC_KEY = 'data'
SYNC_INTERVAL = (2.0, 5.0) # request interval (seconds), random within this range, one request at a time
SYNC_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36'
# Add to / override the default browser headers (Accept, Accept-Language, Referer, sec-ch-ua*, Sec-Fetch-*, ...).
# A value of None removes the header.
# Example: {"Origin": "https://example.com", "Referer": "https://example.com/event"}
SYNC_HEADERS = {}
