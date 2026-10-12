import logging

from config import (AUTO_START, IMG_LIST, LOG_LEVEL, MACRO_TITLE, OCR_KEY, SYNC, SYNC_HEADERS, SYNC_INTERVAL, SYNC_KEY, SYNC_UA,
                    SYNC_URL, TARGET_EXACT, TARGET_WINDOW, TOGGLE_KEY)
from core import keys
from core.runtime import Runtime
import logic  # noqa: F401  (importing registers @flow/@every/@at)

keys.configure(TOGGLE_KEY)

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    level=getattr(logging, str(LOG_LEVEL).upper(), logging.INFO),
    datefmt='%Y-%m-%d %H:%M:%S',
)

if __name__ == "__main__":
    Runtime(IMG_LIST, SYNC_URL, SYNC_KEY, SYNC, SYNC_INTERVAL, SYNC_UA, SYNC_HEADERS,
            TARGET_WINDOW, AUTO_START, TARGET_EXACT, OCR_KEY, MACRO_TITLE).run(getattr(logic, "step", None))
