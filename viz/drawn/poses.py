"""Keeping poses registered (docs/DRAWN-FILM.md, D13 to D15): each pose's anchors are measured from its cut-out, poses
of one form are scaled to one height, and a planted pose may not slide."""

import numpy as np
from PIL import Image

FACE_ROW = 0.42      # the face point's row, as a share of the body's height from its top (Grain's eyes sit there)


def _mask(img):
    return np.asarray(img.convert("RGBA"))[..., 3] >= 128


def measure(img):
    """The pose's peg: its contact point (the middle of its lowest painted row), its painted height and its face point
    (the middle of the painted row FACE_ROW of the way down)."""
    m = _mask(img)
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        raise ValueError("the pose has no painted pixels")
    top, bottom = int(ys.min()), int(ys.max())
    contact = (float(xs[ys == bottom].mean()), float(bottom))
    fy = int(round(top + FACE_ROW * (bottom - top)))
    row = xs[ys == fy]
    face = (float(row.mean()) if len(row) else float(xs.mean()), float(fy))
    return {"contact": contact, "height": float(bottom - top), "face": face,
            "box": [int(xs.min()), top, int(xs.max()), bottom]}


def fit(img, height):
    """The pose scaled so its painted height is `height` (poses of one form share one height)."""
    h = measure(img)["height"]
    k = float(height) / h
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def sliding(sheet, planted):
    """Frames on which a planted pose, still showing, has moved on its level (its contact point would slide)."""
    out = []
    for lv in sheet.levels:
        for f in range(1, sheet.frames):
            n = lv.timeline[f]
            if n in planted and lv.timeline[f - 1] == n:
                a, b = sheet.place(lv, f - 1), sheet.place(lv, f)
                if abs(a[0] - b[0]) > 0.5 or abs(a[1] - b[1]) > 0.5:
                    out.append(f)
    return sorted(set(out))


def lineup(images, anchors, height=None, gap=24, bg=(255, 250, 242, 255)):
    """Every pose of a form side by side, standing on one ground line by its contact point, for checking by eye."""
    hs = [measure(i)["height"] for i in images]
    tall = height or max(hs)
    up = max(anchors[k][1] for k in range(len(images)))
    down = max(i.height - anchors[k][1] for k, i in enumerate(images))
    W = sum(i.width for i in images) + gap * (len(images) + 1)
    out = Image.new("RGBA", (int(W), int(up + down + 2 * gap)), bg)
    x = gap
    for k, i in enumerate(images):
        out.alpha_composite(i.convert("RGBA"), dest=(int(x), int(gap + up - anchors[k][1])))
        x += i.width + gap
    return out
