"""Text recognition with Google Cloud Vision (text_detection)."""
import os
import re

import cv2
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_clients = {}


def resolve_key(path):
    """Absolute path of the service-account key, or None (OCR disabled) if unset or the file is missing.
    Relative paths are from the project folder."""
    if not path:
        print("OCR disabled (config.OCR_KEY is empty)")
        return None
    path = os.path.join(_ROOT, path)
    if not os.path.isfile(path):
        print("OCR disabled: key file not found:", path)
        return None
    return path


def _client(key_path):
    """Vision client for the service-account key, created on first use (importing it is slow)."""
    if key_path not in _clients:
        from google.cloud import vision
        _clients[key_path] = vision.ImageAnnotatorClient.from_service_account_file(key_path)
    return _clients[key_path]


def ocr(image, key_path):
    """Read the text in `image`: a BGR image (e.g. from ctx.crop) or an image file path.
    Returns the text with all whitespace removed, or None on failure / no text."""
    from google.cloud import vision
    if isinstance(image, np.ndarray):
        ok, buf = cv2.imencode(".png", image)
        if not ok:
            print("OCR failed: could not encode image")
            return None
        content = buf.tobytes()
    else:
        with open(image, "rb") as f:
            content = f.read()

    response = _client(key_path).text_detection(image=vision.Image(content=content))
    if response.error.message:
        print("OCR failed:", response.error.message)
        return None
    if not response.text_annotations:
        print("OCR failed: no text")
        return None

    text = re.sub(r"\s", "", response.text_annotations[0].description)
    print("OCR result:", text)
    return text
