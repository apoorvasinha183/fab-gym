"""Grain's face (docs/DRAWN-FILM.md, D16): eyes and mouths drawn by our code, each with its anchor at the face
point, so the face never drifts and blinks and lip sync cost no pictures."""

from PIL import Image, ImageDraw

INK = (28, 22, 38, 255)
WHITE = (255, 255, 255, 255)
SS = 4               # drawn four times larger, then shrunk: smooth ink


def _canvas(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def _done(img):
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


def eyes(state, scale=1.0, look=(0.0, 0.0)):
    w, h = int(64 * scale), int(36 * scale)
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    lw = max(2, int(3.2 * scale * SS))
    for cx in (w * 0.28, w * 0.72):
        rx, ry = w * 0.2, h * 0.42
        box = [(cx - rx) * SS, (h / 2 - ry) * SS, (cx + rx) * SS, (h / 2 + ry) * SS]
        if state == "shut":
            d.arc(box, 20, 160, fill=INK, width=lw)
            continue
        d.ellipse(box, fill=WHITE, outline=INK, width=lw)
        pr = rx * 0.52
        px, py = cx + look[0] * rx * 0.4, h / 2 + look[1] * ry * 0.4
        d.ellipse([(px - pr) * SS, (py - pr) * SS, (px + pr) * SS, (py + pr) * SS], fill=INK)
        d.ellipse([(px - pr * 0.75) * SS, (py - pr * 0.9) * SS, (px - pr * 0.15) * SS, (py - pr * 0.3) * SS], fill=WHITE)
        if state == "half":
            d.rectangle([box[0] - lw, box[1] - lw, box[2] + lw, (h / 2) * SS], fill=(0, 0, 0, 0))
            d.line([box[0], (h / 2) * SS, box[2], (h / 2) * SS], fill=INK, width=lw)
    return _done(img), (w / 2.0, h / 2.0)


def mouth(shape, scale=1.0):
    w, h = int(30 * scale), int(22 * scale)
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    lw = max(2, int(3.0 * scale * SS))
    c = (w * SS / 2, h * SS / 2)
    if shape == "rest":
        d.arc([c[0] - 8 * scale * SS, c[1] - 6 * scale * SS, c[0] + 8 * scale * SS, c[1] + 4 * scale * SS], 20, 160, fill=INK, width=lw)
    elif shape == "smile":
        d.arc([c[0] - 11 * scale * SS, c[1] - 9 * scale * SS, c[0] + 11 * scale * SS, c[1] + 6 * scale * SS], 15, 165, fill=INK, width=lw)
    elif shape == "m":
        d.line([c[0] - 7 * scale * SS, c[1], c[0] + 7 * scale * SS, c[1]], fill=INK, width=lw)
    else:
        rx, ry = {"a": (7, 8), "o": (5, 6), "e": (9, 4)}[shape]
        d.ellipse([c[0] - rx * scale * SS, c[1] - ry * scale * SS, c[0] + rx * scale * SS, c[1] + ry * scale * SS],
                  fill=(120, 30, 40, 255), outline=INK, width=lw)
    return _done(img), (w / 2.0, h / 2.0)


def face_set(scale=1.0):
    """The fixed set: three eye states and six mouths, each with its anchor at its centre."""
    drawings, anchors = {}, {}
    for st in ("open", "half", "shut"):
        drawings[f"eyes_{st}"], anchors[f"eyes_{st}"] = eyes(st, scale)
    for sh in ("rest", "a", "o", "e", "m", "smile"):
        drawings[f"mouth_{sh}"], anchors[f"mouth_{sh}"] = mouth(sh, scale)
    return drawings, anchors
