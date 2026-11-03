"""A hand-directed scene of the drawn film (docs/DRAWN-FILM.md, docs/FILM-PLAYBOOK.md). The direction is written by
hand in film/drawn/scenes/<n>.json: plates (with painted variants for flicker), every drawing (a key from a model sheet,
an in-between from two drawings, or the next drawing after another) and each shot's exposure sheet. Muse Image draws
every picture in the chosen look (film/drawn/looks.json: how it is painted and the colour script's light for each
scene); a contact sheet of them is made for review before rendering; the engine renders each shot with its captions.
The direction is shared by every look; each look keeps its own pictures and shots.

    python3 -m viz.drawn.scene [--look L] sheets          the model sheets redrawn in the look
    python3 -m viz.drawn.scene [--look L] draw N          every picture of scene N, then its contact sheet
    python3 -m viz.drawn.scene [--look L] render N [IDS]  each shot of scene N (or only the shots named)
    python3 -m viz.drawn.scene [--look L] test IDS        the cohesion test: draw and render only these shots
    python3 -m viz.drawn.scene [--look L] cut             every shot joined, with the score

The comic look keeps the first cut's folders (data/drawn/scenes, sheets, shots); any other look lives in
data/drawn/<look>/. The look is --look, else looks.json's 'chosen'.
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
LOOKS = ROOT / "film/drawn/looks.json"
ART = ROOT / "data/drawn/scenes"
SHEETS = ROOT / "data/drawn/sheets"
SHOTS_OUT = produce.SHOTS_OUT
W, H, FPS = 1920, 1080, 24
PW, PH = W + 240, H + 135
FLICKER = 22.0   # mean difference (0-255) above which a painted variant is held as the first plate
CHAR = ("The same character as in the attached model sheet, same face, colours and outline, drawn once, full body, alone "
        "in the middle of the picture, " + produce.BACKDROP + " Pose: ")
LOOK = {"name": "comic"}      # set by use(); the comic look keeps the first cut's exact prompts (and so its cache)


def use(name=None):
    """Choose the look: its folders, how backgrounds and drawings are painted, and its colour script."""
    global ART, SHEETS, SHOTS_OUT, LOOK
    data = json.loads(LOOKS.read_text())
    name = name or data["chosen"]
    LOOK = dict(data["looks"][name], name=name)
    base = ROOT / "data/drawn" if name == "comic" else ROOT / "data/drawn" / name
    ART, SHEETS = base / "scenes", base / "sheets"
    SHOTS_OUT = base / "shots"
    return LOOK


def backdrop(n=None):
    """What every drawing is drawn on, and how: green to be keyed out, painted in the look, lit by the scene's light."""
    if LOOK["name"] == "comic":
        return produce.BACKDROP
    light = LOOK.get("colour", {}).get(str(n), "")
    return ("on a solid flat bright green background (#00FF66), no ground, no shadow on the ground, no text, drawn as "
            + LOOK["cel"] + (f", lit by {light}" if light else "") + ".")


def char(n=None):
    if LOOK["name"] == "comic":
        return CHAR
    return ("The same character as in the attached model sheet, same face, same shapes, proportions and colours, drawn "
            "once, full body, alone in the middle of the picture, " + backdrop(n) + " Pose: ")


def plate_text(n, p):
    if LOOK["name"] == "comic":
        return pilot.PLATE + p["prompt"]
    light = LOOK.get("colour", {}).get(str(n), "")
    return LOOK["plate"] + (f"The light: {light}. " if light else "") + p["prompt"]


def load(n):
    return json.loads((SCENES / f"{n}.json").read_text())


def needed(sc, only):
    """The pictures the named shots use, with every drawing they are made from."""
    names = set()
    for shot in sc["shots"]:
        if shot["id"] in only:
            for lv in shot["levels"]:
                names |= {x[0] for x in lv.get("cels", [])} | set(lv.get("cycle", []))
            for ins in shot.get("insets", []):
                names |= {x[0] for x in ins["cels"]}
    names = {x.split("~")[0] for x in names}
    grow = True
    while grow:
        grow = False
        for k in list(names):
            dd = sc.get("drawings", {}).get(k, {})
            for src in ([dd["after"]] if dd.get("kind") == "next" else []) + list(dd.get("between", [])):
                if src not in names:
                    names.add(src)
                    grow = True
    return names


def draw(n, only=None):
    sc = load(n)
    if only:
        keep = needed(sc, only)
        sc = dict(sc, plates={k: v for k, v in sc.get("plates", {}).items() if k in keep},
                  drawings={k: v for k, v in sc.get("drawings", {}).items() if k in keep},
                  machines={k: v for k, v in sc.get("machines", {}).items() if k in keep})
    out = ART / str(n)
    out.mkdir(parents=True, exist_ok=True)
    c = pilot.client()
    hero = (ROOT / LOOK.get("style_ref", "docs/img/fabgym-hero.jpg")).read_bytes()
    CHAR = char(n)

    def plate(name, p):
        f = out / f"{name}.png"
        if not f.exists():
            img = produce._try(c, [plate_text(n, p)], [hero])
            if img:
                f.write_bytes(img)
        prev = f
        for k in range(int(p.get("variants", 0))):
            v = out / f"{name}~{k + 1}.png"
            if not v.exists() and f.exists():
                step = p["variant"][k] if isinstance(p.get("variant"), list) else p.get("variant", "the light and flames "
                                                                                                       "shift a little")
                img = produce._try(c, ["The same painting as the attached picture, exactly the same place, framing, objects "
                                       "and style, only a moment later: " + step + f". No characters, no text. "
                                       f"(Variant {k + 1}.)"], [f.read_bytes()])
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
                img = produce._try(c, [f"{what}, drawn once, alone in the middle of the picture, " + backdrop(n)], [hero])
            else:
                img = produce._try(c, [f"{what}. The same machine as in the attached picture, same size, colours and "
                                       "outline, only its moving part has moved, " + backdrop(n)], [prev.read_bytes()])
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
                    "first attached picture and the pose in the second, same size, same face and colours, " + backdrop(n))
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


def inset(fr, d, ins, f):
    """A magnifying circle (a 'simplified view'): it opens over 6 frames, shows its pictures in turn, closes over 6, and
    sits in screen space, so the camera does not move it. Its label says it is simplified."""
    f0, f1 = int(ins["from"]), int(ins["to"])
    if not f0 <= f < f1:
        return
    k, name = f - f0, None
    for nm, n in ins["cels"]:
        if k < n:
            name = nm
            break
        k -= n
    name = name or ins["cels"][-1][0]
    if name not in d:
        return
    grow = min(1.0, (f - f0 + 1) / 6.0, (f1 - f) / 6.0)
    r = max(2, int(int(ins.get("r", 240)) * (1 - (1 - grow) ** 3)))
    x, y = (int(v) for v in ins["at"])
    pic = d[name].convert("RGB")
    side = min(pic.size)
    pic = pic.crop(((pic.width - side) // 2, (pic.height - side) // 2, (pic.width + side) // 2, (pic.height + side) // 2))
    pic = pic.resize((2 * r, 2 * r), Image.LANCZOS)
    mask = Image.new("L", (2 * r, 2 * r), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    fr.paste(pic, (x - r, y - r), mask)
    dr = ImageDraw.Draw(fr)
    dr.ellipse([x - r, y - r, x + r, y + r], outline=(42, 33, 24), width=10)
    dr.ellipse([x - r + 8, y - r + 8, x + r - 8, y + r - 8], outline=(245, 232, 200), width=3)
    if grow >= 1 and ins.get("label", "simplified view"):
        lf = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
        text = ins.get("label", "simplified view")
        w = dr.textlength(text, font=lf)
        dr.rounded_rectangle([x - w / 2 - 14, y + r + 8, x + w / 2 + 14, y + r + 52], 10, fill=(42, 33, 24))
        dr.text((x - w / 2, y + r + 14), text, font=lf, fill=(245, 232, 200))


def render(n, only=None):
    sc = load(n)
    out = ART / str(n)
    captions = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 120) \
        if Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf").exists() else font
    results = []
    for shot in sc["shots"]:
        if only and shot["id"] not in only:
            continue
        d, anchors = {"none": Image.new("RGBA", (4, 4), (0, 0, 0, 0))}, {}
        levels = []
        for ins in shot.get("insets", []):
            for nm, _ in ins["cels"]:
                if nm not in d and (out / f"{nm}.png").exists():
                    d[nm] = Image.open(out / f"{nm}.png").convert("RGBA")
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
                    limit = float(LOOK.get("flicker", FLICKER))
                    spec["cycle"] = [x if np.abs(np.asarray(d[x].convert("RGB"), float) - base).mean() <= limit
                                     else spec["cycle"][0] for x in spec["cycle"]]
            levels.append(spec)
        s = sh.load({"shot": shot["id"], "frames": int(shot["frames"]), "fps": FPS, "levels": levels,
                     "camera": shot.get("camera", []), "cuts": shot.get("cuts", [])})
        errs = sh.validate(s, set(d))
        r = compose.Renderer(d, (W, H), anchors=anchors)
        SHOTS_OUT.mkdir(parents=True, exist_ok=True)
        mp4 = SHOTS_OUT / f"{shot['id']}.mp4"
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r",
               str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        small = []
        for f in range(s.frames):
            fr = Image.fromarray(r.frame(s, f))
            dr = ImageDraw.Draw(fr, "RGBA")
            t = float(shot["start"]) + f / FPS
            for ins in shot.get("insets", []):
                inset(fr, d, ins, f)
            for tt in shot.get("titles", []):
                if tt["from"] <= f < tt["to"]:
                    a = min(1.0, (f - tt["from"]) / 12.0, (tt["to"] - f) / 12.0)
                    tf = title_font if "size" not in tt else title_font.font_variant(size=int(tt["size"]))
                    title(dr, tt["text"], tt.get("y", H * 0.42), tf, a)
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


def sheets():
    """The model sheets redrawn in the look: the same characters, poses and layout as the first sheets, painted as the
    look paints its drawings (the look's 'cel_ref' is an example drawing in it)."""
    if LOOK["name"] == "comic":
        return
    SHEETS.mkdir(parents=True, exist_ok=True)
    c = pilot.client()
    example = (ROOT / LOOK["cel_ref"]).read_bytes()
    first = ROOT / "data/drawn/sheets"
    todo = [f for f in sorted(first.glob("*.png")) if "-v1" not in f.stem and not (SHEETS / f.name).exists()]

    def one(f):
        img = produce._try(c, ["Redraw the character model sheet in the first attached picture: exactly the same characters, "
                               "the same poses, faces, shapes, proportions and layout, and every colour exactly as in the first picture (a silver "
                               "character stays silver, a grey one grey), on plain light paper, no text, "
                               "drawn as " + LOOK["cel"] + ", in the painting style of the character in the second attached "
                               "picture."], [f.read_bytes(), example])
        if img:
            (SHEETS / f.name).write_bytes(img)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, todo))
    lineup = Image.new("RGB", (4 * 480, ((len(list(SHEETS.glob("*.png"))) + 3) // 4) * 300), (250, 248, 240))
    for i, f in enumerate(sorted(SHEETS.glob("*.png"))):
        im = Image.open(f).convert("RGB")
        im.thumbnail((470, 290))
        lineup.paste(im, ((i % 4) * 480 + 5, (i // 4) * 300 + 5))
    lineup.save(SHEETS.parent / "sheets.jpg", quality=85)
    print(SHEETS.parent / "sheets.jpg")


def scene_of(shot_id):
    return shot_id.split("-")[0]


def test(ids):
    """The cohesion test: draw the scenes these shots belong to, render only these shots, and lay one frame of each
    side by side, so Grain and its rooms can be judged together in paused frames."""
    for n in dict.fromkeys(scene_of(i) for i in ids):
        draw(n, set(ids))
        render(n, only=set(ids))
    frames = []
    for i in ids:
        f = SHOTS_OUT / f"{i}.mp4"
        shot = next(s for s in load(scene_of(i))["shots"] if s["id"] == i)
        out = SHOTS_OUT / f"{i}-mid.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(int(shot["frames"]) / FPS / 2), "-i", str(f),
                        "-frames:v", "1", str(out)], check=True)
        frames.append(Image.open(out).convert("RGB").resize((960, 540)))
    board = Image.new("RGB", (960 * min(3, len(frames)), 540 * ((len(frames) + 2) // 3)))
    for k, im in enumerate(frames):
        board.paste(im, ((k % 3) * 960, (k // 3) * 540))
    board.save(SHOTS_OUT / "cohesion-test.jpg", quality=86)
    print(SHOTS_OUT / "cohesion-test.jpg")


def cut(out=None):
    """Every shot of every scene joined in order, with the score under it."""
    rows = []
    for f in sorted(SCENES.glob("*.json"), key=lambda p: int(p.stem)):
        rows += [(s["id"], int(s["frames"])) for s in json.loads(f.read_text())["shots"]]
    missing = [i for i, _ in rows if not (SHOTS_OUT / f"{i}.mp4").exists()]
    if missing:
        raise SystemExit(f"shots not rendered yet: {', '.join(missing)}")
    lst = SHOTS_OUT / "cut.txt"
    lst.write_text("".join(f"file '{SHOTS_OUT / i}.mp4'\n" for i, _ in rows))
    out = Path(out or SHOTS_OUT.parent / "sand-to-chip.mp4")
    seconds = sum(n for _, n in rows) / FPS
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i",
                    str(ROOT / "data/drawn/score.mp3"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-t", str(seconds), str(out)], check=True)
    print(out, f"{len(rows)} shots, {seconds:.1f} s")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    look = None
    if args and args[0] == "--look":
        look, args = args[1], args[2:]
    use(look)
    cmd, rest = args[0], args[1:]
    if cmd == "sheets":
        sheets()
    elif cmd == "test":
        test(rest)
    elif cmd == "cut":
        cut(*rest)
    elif cmd == "render":
        render(rest[0], set(rest[1:]) or None)
    else:
        {"draw": draw, "contact": contact}[cmd](rest[0])
