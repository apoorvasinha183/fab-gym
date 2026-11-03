"""A hand-directed scene of the drawn film (docs/DRAWN-FILM.md). The direction is written by hand in
film/drawn/scenes/<n>.json: plates (with painted variants for flicker), every drawing (a key from a model sheet, an
in-between from two drawings, or the next drawing after another) and each shot's exposure sheet. Muse Image draws every
picture; a contact sheet of them is made for review before rendering; the engine renders each shot with its captions.

    python3 -m viz.drawn.scene draw N       data/drawn/scenes/N/*.png, then data/drawn/scenes/N/contact.jpg
    python3 -m viz.drawn.scene render N     data/drawn/shots/<shot>.mp4 for each shot of the scene
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import compose, pilot, poses, produce, sheet as sh

ROOT = Path(__file__).resolve().parents[2]
SCENES = ROOT / "film/drawn/scenes"
ART = ROOT / "data/drawn/scenes"
SHEETS = ROOT / "data/drawn/sheets"
W, H, FPS = 1920, 1080, 24
PW, PH = W + 240, H + 135
FLICKER = 22.0   # mean difference (0-255) above which a painted variant is held as the first plate
CHAR = ("The same character as in the attached model sheet, same face, colours and outline, drawn once, full body, alone "
        "in the middle of the picture, " + produce.BACKDROP + " Pose: ")


def load(n):
    return json.loads((SCENES / f"{n}.json").read_text())


def draw(n):
    sc = load(n)
    out = ART / str(n)
    out.mkdir(parents=True, exist_ok=True)
    c = pilot.client()
    hero = pilot.HERO.read_bytes()

    def plate(name, p):
        f = out / f"{name}.png"
        if not f.exists():
            img = produce._try(c, [pilot.PLATE + p["prompt"]], [hero])
            if img:
                f.write_bytes(img)
        prev = f
        for k in range(int(p.get("variants", 0))):
            v = out / f"{name}~{k + 1}.png"
            if not v.exists() and f.exists():
                img = produce._try(c, ["The same painting as the attached picture, exactly the same place, framing, objects "
                                       "and style, only a moment later: " + p.get("variant", "the light and flames shift "
                                       "a little") + f". No characters, no text. (Variant {k + 1}.)"], [f.read_bytes()])
                if img:
                    v.write_bytes(img)
        return prev

    def key(name, dd):
        f = out / f"{name}.png"
        if not f.exists():
            pose = dd["pose"]
            img = produce._try(c, [CHAR + pose, CHAR + pose.split(",")[0]], [(SHEETS / f"{dd['sheet']}.png").read_bytes()])
            if img:
                f.write_bytes(img)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(plate, k, v) for k, v in sc.get("plates", {}).items()]
        futs += [pool.submit(key, k, v) for k, v in sc.get("drawings", {}).items() if v.get("kind", "key") == "key"]
        for f in futs:
            f.result()
    # machines (no model sheet): the first in the house style, each next one edited from the one before
    prev = None
    for name, what in sc.get("machines", {}).items():
        f = out / f"{name}.png"
        if not f.exists():
            if prev is None:
                img = produce._try(c, [f"{what}, drawn once, alone in the middle of the picture, " + produce.BACKDROP], [hero])
            else:
                img = produce._try(c, [f"{what}. The same machine as in the attached picture, same size, colours and "
                                       "outline, only its moving part has moved, " + produce.BACKDROP], [prev.read_bytes()])
            if img:
                f.write_bytes(img)
        prev = f
    # drawings made from other drawings, in the order written: the next drawing after one, or an in-between of two
    for name, dd in sc.get("drawings", {}).items():
        kind = dd.get("kind", "key")
        f = out / f"{name}.png"
        if kind == "key" or f.exists():
            continue
        if kind == "next":
            src = out / f"{dd['after']}.png"
            refs = [(SHEETS / f"{dd['sheet']}.png").read_bytes(), src.read_bytes()]
            text = (CHAR + dd["pose"] + " It is the next drawing of the animation after the one in the second attached "
                    "picture: the same character, same size, only the pose moves on a little.")
        else:
            a, b = (out / f"{k}.png" for k in dd["between"])
            refs = [a.read_bytes(), b.read_bytes()]
            text = ("The in-between drawing for animation: the same character exactly halfway between the pose in the "
                    "first attached picture and the pose in the second, same size, same face and colours, " + produce.BACKDROP)
        img = produce._try(c, [text], refs)
        if img:
            f.write_bytes(img)
    contact(n)


def contact(n):
    """Every picture of the scene on one sheet: plates as painted, drawings keyed onto a light card, each named."""
    out = ART / str(n)
    files = sorted(out.glob("*.png"))
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    tiles = []
    for f in files:
        im = Image.open(f).convert("RGBA")
        if "~" not in f.stem and f.stem not in load(n).get("plates", {}):
            im = pilot.key(im)
            card = Image.new("RGBA", (im.width + 20, im.height + 20), (255, 250, 242, 255))
            card.alpha_composite(im, (10, 10))
            im = card
        im.thumbnail((420, 300))
        t = Image.new("RGB", (430, 330), (13, 20, 48))
        t.paste(im.convert("RGB"), (5, 5))
        ImageDraw.Draw(t).text((8, 306), f.stem, font=font, fill=(255, 211, 77))
        tiles.append(t)
    cols = 5
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 430, max(1, rows) * 330), (13, 20, 48))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 430, (i // cols) * 330))
    sheet.save(out / "contact.jpg", quality=82)
    return out / "contact.jpg"


SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def title(dr, text, y, font, a):
    """A title centred with an outline; subscript digits (as in SiO₂) drawn small and lowered, since the title font has
    no glyphs for them."""
    small = font.font_variant(size=int(font.size * 0.6))
    runs, cur = [], ""
    for ch in text:
        sub = ch != ch.translate(SUB)
        if runs and runs[-1][1] == sub:
            runs[-1][0] += ch.translate(SUB)
        else:
            runs.append([ch.translate(SUB), sub])
    w = sum(dr.textlength(s, font=small if sub else font) for s, sub in runs)
    x = W / 2 - w / 2
    for s, sub in runs:
        f = small if sub else font
        dr.text((x, y + (font.size * 0.5 if sub else 0)), s, font=f, fill=(255, 240, 200, int(255 * a)),
                stroke_width=7 if not sub else 5, stroke_fill=(28, 22, 38, int(255 * a)))
        x += dr.textlength(s, font=f)


def render(n):
    sc = load(n)
    out = ART / str(n)
    captions = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 120) \
        if Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf").exists() else font
    results = []
    for shot in sc["shots"]:
        d, anchors = {"none": Image.new("RGBA", (4, 4), (0, 0, 0, 0))}, {}
        levels = []
        for lv in shot["levels"]:
            names = [x[0] for x in lv.get("cels", [])] + list(lv.get("cycle", []))
            for nm in names:
                if nm in d or nm == "none":
                    continue
                f = out / f"{nm}.png"
                if not f.exists():
                    continue
                img = Image.open(f).convert("RGBA")
                if lv.get("plate"):
                    d[nm] = img.resize((PW, PH), Image.LANCZOS)
                else:
                    cut = poses.fit(pilot.key(img), float(lv["height"]))
                    d[nm] = cut
                    # a hanging thing (a box on a rail) is pegged by the middle of its top edge, not by its feet
                    anchors[nm] = (cut.width / 2, 0) if lv.get("anchor") == "top" else poses.measure(cut)["contact"]
            spec = {k: v for k, v in lv.items() if k not in ("plate", "height", "anchor")}
            if lv.get("plate"):
                spec.setdefault("at", [-120, -67])
            for key in ("cels",):
                if key in spec:
                    spec[key] = [[x[0] if x[0] in d else "none", x[1]] for x in spec[key]]
            if "cycle" in spec:
                spec["cycle"] = [x for x in spec["cycle"] if x in d] or ["none"]
                if lv.get("plate") and spec["cycle"][0] != "none":
                    # a painted variant that repaints the light or framing flickers; hold the first plate instead
                    base = np.asarray(d[spec["cycle"][0]].convert("RGB"), float)
                    spec["cycle"] = [x if np.abs(np.asarray(d[x].convert("RGB"), float) - base).mean() <= FLICKER
                                     else spec["cycle"][0] for x in spec["cycle"]]
            levels.append(spec)
        s = sh.load({"shot": shot["id"], "frames": int(shot["frames"]), "fps": FPS, "levels": levels,
                     "camera": shot.get("camera", []), "cuts": shot.get("cuts", [])})
        errs = sh.validate(s, set(d))
        r = compose.Renderer(d, (W, H), anchors=anchors)
        produce.SHOTS_OUT.mkdir(parents=True, exist_ok=True)
        mp4 = produce.SHOTS_OUT / f"{shot['id']}.mp4"
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r",
               str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        small = []
        for f in range(s.frames):
            fr = Image.fromarray(r.frame(s, f))
            dr = ImageDraw.Draw(fr, "RGBA")
            t = float(shot["start"]) + f / FPS
            for tt in shot.get("titles", []):
                if tt["from"] <= f < tt["to"]:
                    a = min(1.0, (f - tt["from"]) / 12.0, (tt["to"] - f) / 12.0)
                    title(dr, tt["text"], tt.get("y", H * 0.42), title_font, a)
            for k, ln in enumerate([ln for ln in captions if float(ln["from"]) <= t < float(ln["to"])][:2]):
                text = ({"grain": "GRAIN: ", "lou": "LOU: "}.get(ln["who"], "")) + ln["text"]
                w = dr.textlength(text, font=font)
                yy = H - 110 - 60 * k
                dr.rounded_rectangle([W / 2 - w / 2 - 22, yy - 10, W / 2 + w / 2 + 22, yy + 52], 12, fill=(10, 12, 24, 170))
                dr.text((W / 2 - w / 2, yy), text, font=font, fill=(255, 214, 90) if ln["who"] != "narrator" else (245, 245, 250))
            arr = np.asarray(fr)
            if f % 4 == 0:
                small.append(arr[::4, ::4].copy())
            p.stdin.write(arr.tobytes())
        p.stdin.close()
        p.wait()
        results.append((shot["id"], errs, compose.pops(small, cuts=[c // 4 for c in s.cuts]), r.rendered))
        print(shot["id"], "drawings", r.rendered, "problems", errs or "none", "pops", results[-1][2] or "none", flush=True)
    return results


if __name__ == "__main__":
    cmd, n = sys.argv[1], sys.argv[2]
    {"draw": draw, "render": render, "contact": contact}[cmd](n)
