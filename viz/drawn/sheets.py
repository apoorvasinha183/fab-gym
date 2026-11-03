"""Model sheets for the drawn film (docs/DRAWN-FILM.md, step 3): each character's design in three views and a few
expressions, drawn by Muse Image in the edit mode from Fab Gym's hero picture (the house style) and, for Grain's later
forms, from Grain's first sheet (so the face stays the same). A line-up page puts them side by side for sign-off.

    python3 -m viz.drawn.sheets draw       data/drawn/sheets/<name>.png
    python3 -m viz.drawn.sheets lineup     data/drawn/sheets-lineup.jpg
"""

import sys
from pathlib import Path

from . import meta

ROOT = Path(__file__).resolve().parents[2]
HERO = ROOT / "docs/img/fabgym-hero.jpg"
OUT = ROOT / "data/drawn/sheets"
FACE = ("two big round white eyes with large dark pupils and a white highlight, a small simple curved mouth; the same "
        "face on every form")
STYLE = ("in the style of the attached picture: hand-inked comic, bold clean black outlines of one even weight, flat "
         "cel colour with a single shade, no gradients")
SHEET = ("A character model sheet for an animated film, on a plain white background, no words or labels: the character "
         "in front view, three-quarter view and side view standing in a row, and below them three head close-ups showing "
         "happy, surprised and worried expressions. Same size and proportions in every view, ")

CAST = [
    ("grain-01-sand", "Grain as a single grain of sand: a small rounded pale golden-white pebble with a few facets"),
    ("grain-02-quartz", "Grain as a pale pinkish-white quartz pebble, holding hands with its two oxygen twins, small "
                        "round red balls with their own little eyes, one on each side"),
    ("grain-03-grey", "Grain as a dusty grey lump of raw silicon with a few brown specks of dirt on it, looking lost"),
    ("grain-04-wisp", "Grain as a curling lilac wisp of gas, soft rounded swirl shape"),
    ("grain-05-crystal", "Grain as a tall silver crystal ingot, a rounded cylinder with a thin seed rod on top, proud"),
    ("grain-06-wafer", "Grain as a thin mirror-bright silver wafer disc, seen standing up on its edge and tilted"),
    ("grain-07-coach", "Grain as the wafer coach: a round wafer tiled with a grid of small iridescent coloured squares "
                       "(chips), wearing a red sweatband headband, with skinny cartoon arms and legs and white sneakers"),
    ("grain-08-die", "Grain as one die: a flat square silicon chip tile, thin like a cracker, pale green with a fine "
                     "grid of circuit lines, no dots, no cube; with a tiny red headband stripe"),
    ("grain-10-packaged", "Grain as a packaged chip: a flat black square package with short gold wire legs along two "
                          "sides and a small red bow tie"),
    ("lou-latency", "Lou Latency, a boxy robot CEO: a square white head with a dark screen face showing simple glowing "
                    "eyes, a red cap with a small lamp on top, a navy suit with a red tie, white gloves (like the robot "
                    "in the attached picture's style, not the polishing machine)"),
    ("carbon-thieves", "two carbon thieves: small spiky black soot-ball characters with sly grins and little arms, "
                       "sneaky"),
    ("specks", "a group of tiny brown dust-speck characters, round with dot eyes, grumpy"),
]


def client():
    return meta.Client(ledger=ROOT / "data/drawn/ledger.jsonl", cache=ROOT / "data/drawn/cache", cap_usd=25.0)


def draw():
    OUT.mkdir(parents=True, exist_ok=True)
    c = client()
    hero = HERO.read_bytes()
    first = OUT / "grain-01-sand.png"
    for name, who in CAST:
        p = OUT / f"{name}.png"
        if p.exists():
            continue
        face = f" Face: {FACE}." if name.startswith("grain") else ""
        refs = [hero] + ([first.read_bytes()] if name.startswith("grain") and name != "grain-01-sand" and first.exists() else [])
        keep = " Keep the exact face of the character in the second attached picture." if len(refs) > 1 else ""
        prompt = f"{SHEET}{STYLE}. The character: {who}.{face}{keep}"
        try:
            img = c.image(prompt, refs=refs)
        except meta.OverCap as e:
            print("stopped:", e)
            break
        except Exception as e:
            body = e.read()[:300].decode("utf-8", "replace") if hasattr(e, "read") else ""
            print(name, "refused:", getattr(e, "code", e), body)
            continue
        p.write_bytes(img)
        print(name, f"spent ${c.spent():.2f}")


def lineup():
    from PIL import Image, ImageDraw, ImageFont
    W = 640
    files = [OUT / f"{n}.png" for n, _ in CAST if (OUT / f"{n}.png").exists()]
    cols = 3
    rows = (len(files) + cols - 1) // cols
    font = ImageFont.truetype(str(ROOT / "viz/fab3d/ui/fonts/kenpixel.ttf"), 22)
    sheet = Image.new("RGB", (cols * W, rows * (W + 40)), (13, 20, 48))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        im.thumbnail((W - 12, W - 12))
        x, y = (i % cols) * W, (i // cols) * (W + 40)
        sheet.paste(im, (x + 6, y + 6))
        d.text((x + 10, y + W - 4), f.stem, font=font, fill=(255, 211, 77))
    out = ROOT / "data/drawn/sheets-lineup.jpg"
    sheet.save(out, quality=85)
    print(out)


if __name__ == "__main__":
    {"draw": draw, "lineup": lineup}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
