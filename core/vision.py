"""Template loading and matching."""
import cv2


def load_templates(img_list):
    """{name: (path, threshold)} -> {name: {img, h, w, thresh}}"""
    templates = {}
    for name, (path, thresh) in img_list.items():
        img = cv2.imread(path)
        if img is None:  # imread returns None on a wrong path, so catch it right away
            raise FileNotFoundError(path)
        h, w = img.shape[:2]
        templates[name] = {"img": img, "h": h, "w": w, "thresh": thresh}
    return templates


def match(area, origin, t):
    """Find template t in `area` and return its center (x, y) in screen coordinates, or None."""
    ah, aw = area.shape[:2]
    if ah < t["h"] or aw < t["w"]:      # area smaller than the template: cannot match
        return None
    res = cv2.matchTemplate(area, t["img"], cv2.TM_CCOEFF_NORMED)
    _, score, _, (lx, ly) = cv2.minMaxLoc(res)
    if score < t["thresh"]:
        return None
    return origin[0] + lx + t["w"] // 2, origin[1] + ly + t["h"] // 2
