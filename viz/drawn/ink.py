"""Ink and paint (docs/DRAWN-FILM.md): every cel is snapped to its scene's palette and given one outline weight, so
drawings made one at a time sit together like painted acetate."""

import numpy as np
from PIL import Image, ImageFilter

INK = (28, 22, 38)


def _rgba(img):
    return np.asarray(img.convert("RGBA")).astype(np.int32)


def colour_lock(img, palette, alpha_cut=128):
    """Each painted pixel becomes the nearest palette colour; alpha is made solid or clear, as paint on acetate (D8)."""
    a = _rgba(img)
    pal = np.asarray(palette, dtype=np.int32)
    rgb = a[..., :3]
    d = ((rgb[..., None, :] - pal[None, None, :, :]) ** 2).sum(-1)
    near = pal[d.argmin(-1)]
    solid = a[..., 3] >= alpha_cut
    out = np.zeros_like(a)
    out[..., :3] = np.where(solid[..., None], near, 0)
    out[..., 3] = np.where(solid, 255, 0)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def palette_distance(img, palette):
    """The largest distance from a painted pixel's colour to the nearest palette colour."""
    a = _rgba(img)
    m = a[..., 3] > 0
    if not m.any():
        return 0.0
    rgb = a[..., :3][m]
    pal = np.asarray(palette, dtype=np.int32)
    d = ((rgb[:, None, :] - pal[None, :, :]) ** 2).sum(-1).min(-1)
    return float(np.sqrt(d.max()))


def outline(img, px=4, colour=INK):
    """One ink line of px pixels round the cel's silhouette, under the paint."""
    a = img.convert("RGBA")
    mask = a.split()[3].point(lambda v: 255 if v >= 128 else 0)
    grown = mask.filter(ImageFilter.MaxFilter(2 * px + 1))
    line = Image.new("RGBA", a.size, colour + (0,))
    line.putalpha(grown)
    line.alpha_composite(a)
    return line


def palette_of(img, n=8):
    """The n main colours of a picture (its model sheet), for the scene's palette."""
    q = img.convert("RGB").quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    p = q.getpalette()[: 3 * n]
    return [tuple(p[i:i + 3]) for i in range(0, len(p), 3)]
