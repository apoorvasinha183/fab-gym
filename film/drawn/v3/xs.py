"""The fab's cross-section series drawn exactly (layers lying on the slab, the same three openings in every step), as
bases for Muse Image to repaint in the film's style (film/drawn/v3/direct.py, scene 7)."""
from pathlib import Path
from PIL import Image, ImageDraw

W, H = 1600, 900
BLUE, OCHRE, CORAL, PALE, PAPER, INK = (84, 110, 145), (214, 160, 52), (222, 120, 110), (246, 214, 206), (244, 240, 230), (40, 34, 28)
X0, X1, TOP, BOT = 140, 1460, 470, 800          # the slab
FILM, RES = 60, 70                              # layer thicknesses
GAPS = [(380, 520), (730, 870), (1080, 1220)]   # the three openings, the same in every step


def draw(film=0.0, res=False, exposed=False, mask=False, developed=False, etched=False, stripped=False):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle([X0, TOP, X1, BOT], fill=BLUE, outline=INK, width=4)
    ft = TOP - FILM
    if film:
        xe = X0 + (X1 - X0) * film
        d.rectangle([X0, ft, xe, TOP], fill=OCHRE, outline=INK, width=4)
        if etched:
            for a, b in GAPS:
                d.rectangle([a, ft, b, TOP], fill=PAPER)
                d.line([a, ft, a, TOP], fill=INK, width=4); d.line([b, ft, b, TOP], fill=INK, width=4)
    if res and not stripped:
        rt = ft - RES
        d.rectangle([X0, rt, X1, ft], fill=CORAL, outline=INK, width=4)
        for a, b in GAPS:
            if exposed and not developed:
                d.rectangle([a, rt + 3, b, ft - 3], fill=PALE)
            if developed:
                d.rectangle([a, rt, b, ft], fill=PAPER)
                d.line([a, rt, a, ft], fill=INK, width=4); d.line([b, rt, b, ft], fill=INK, width=4)
    if mask:
        d.rectangle([X0, 90, X1, 150], fill=(48, 44, 50), outline=INK, width=4)
        for a, b in GAPS:
            d.rectangle([a, 90, b, 150], fill=PAPER)
            d.polygon([(a, 150), (b, 150), (b + 10, ft - RES), (a - 10, ft - RES)], fill=(252, 238, 190))
    return im


STEPS = {"xs0": {}, "xs_half": {"film": 0.5}, "xs_film": {"film": 1}, "xs_res": {"film": 1, "res": True},
         "xs_exp": {"film": 1, "res": True, "exposed": True, "mask": True},
         "xs_dev": {"film": 1, "res": True, "developed": True},
         "xs_etch": {"film": 1, "res": True, "developed": True, "etched": True},
         "xs_strip": {"film": 1, "res": True, "developed": True, "etched": True, "stripped": True}}

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[3] / "data/drawn/theatrical/scenes/7"
    out.mkdir(parents=True, exist_ok=True)
    for k, kw in STEPS.items():
        draw(**kw).save(out / f"{k}_base.png")
    print(out)
