"""Following a character through a rendered shot (docs/DRAWN-FILM.md, D17): the centre of its painted area on every
frame, and the frames where that centre jumps."""

import math

import numpy as np


def centres(frames, colour, tol=6):
    out = []
    key = np.asarray(colour[:3], dtype=np.int16)
    for fr in frames:
        a = np.asarray(fr, dtype=np.int16)[..., :3]
        m = (np.abs(a - key) <= tol).all(-1)
        ys, xs = np.nonzero(m)
        out.append((float(xs.mean()), float(ys.mean())) if len(xs) else None)
    return out


def jumps(cs, limit=12.0, allowed=()):
    """Frames whose centre is more than `limit` pixels from the frame before, unless the sheet allows it there."""
    out = []
    for f in range(1, len(cs)):
        if cs[f] is None or cs[f - 1] is None or f in set(allowed):
            continue
        if math.dist(cs[f], cs[f - 1]) > limit:
            out.append(f)
    return out
