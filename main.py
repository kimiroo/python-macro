from config import (AUTO_START, IMG_LIST, OCR_KEY, SYNC, SYNC_HEADERS, SYNC_INTERVAL, SYNC_KEY, SYNC_UA,
                    SYNC_URL, TARGET_EXACT, TARGET_WINDOW)
from core.runtime import Runtime
import logic  # noqa: F401  (importing registers @flow/@every/@at)

if __name__ == "__main__":
    Runtime(IMG_LIST, SYNC_URL, SYNC_KEY, SYNC, SYNC_INTERVAL, SYNC_UA, SYNC_HEADERS,
            TARGET_WINDOW, AUTO_START, TARGET_EXACT, OCR_KEY).run(getattr(logic, "step", None))
