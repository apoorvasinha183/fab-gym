"""Producing each shot of the drawn film from its animation sheet (docs/DRAWN-FILM.md). Muse Image draws the plate and
every drawing (keys from the model sheet, in-betweens from their two keys, cycle drawings each from the one before,
effects each from the one before), four at a time; Muse Spark reads the plate's scale; our code keys, pegs and sizes
every cel, stacks the frames with the camera and burns in the captions. One silent MP4 per shot; then the cut.

    python3 -m viz.drawn.produce shots [SHOT ...]   data/drawn/shots/<shot>.mp4
    python3 -m viz.drawn.produce cut                data/drawn/sand-to-chip-drawn.mp4
"""

import base64
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import compose, meta, music, pilot, poses, scale, sheet as sh

ROOT = Path(__file__).resolve().parents[2]
ANIM = ROOT / "film/drawn/anim"
ART = ROOT / "data/drawn/art"
SHOTS_OUT = ROOT / "data/drawn/shots"
SHEETS = ROOT / "data/drawn/sheets"
W, H, FPS = 1920, 1080, 24
PW, PH = W + 240, H + 135
OX, OY = -120, -67
BACKDROP = ("on a solid flat bright green background (#00FF66), no ground, no shadow, no text, " + pilot.STYLE + ".")


def _try(c, prompts, refs):
    """A picture from Muse Image: busy or failing servers are waited out and asked again; a refused wording falls back
    to the plainer one."""
    import time
    for text in prompts:
        for attempt in range(4):
            try:
                return c.image(text, refs=refs)
            except meta.OverCap:
                raise
            except Exception as e:
                code = getattr(e, "code", None)
                body = e.read()[:160].decode("utf-8", "replace") if hasattr(e, "read") else str(e)[:160]
                if code in (429, 500, 502, 503, 504) or code is None:
                    time.sleep(20 * (attempt + 1))
                    continue
                print("   refused:", body.split('"message":"')[-1][:90])
                break
    return None


def draw_shot(a):
    """Every picture the shot needs, from Muse Image; returns name -> path."""
    c = pilot.client()
    out = ART / a["shot"]
    out.mkdir(parents=True, exist_ok=True)
    hero = pilot.HERO.read_bytes()
    paths = {}

    hero_m = float(a["characters"][0].get("height_m", 0.05)) if a.get("characters") else 0.05

    def plate(p, closer=""):
        f = out / f"plate_{p['name']}.png"
        if not f.exists() or closer:
            prompt = (pilot.PLATE + p["prompt"] + f" Seen at the hero's scale: a character {hero_m:g} m tall standing in the "
                      f"lower middle would fill about a third of the picture's height; {p.get('reference', 'a pebble')} "
                      "lies there, large in the picture." + closer)
            img = _try(c, [prompt, pilot.PLATE + p["prompt"] + closer], [hero])
            if img:
                f.write_bytes(img)
                f.with_suffix(".scale.json").unlink(missing_ok=True)
        return f

    def key(ch, d):
        f = out / f"{ch['name']}_{d['id']}.png"
        if not f.exists():
            base = (f"The same character as in the attached model sheet, same face, colours and outline, drawn once, full "
                    f"body, alone in the middle of the picture, {BACKDROP} Pose: ")
            img = _try(c, [base + d.get("pose", ""), base + d.get("pose", "").split(",")[0]],
                       [(SHEETS / f"{ch['sheet']}.png").read_bytes()])
            if img:
                f.write_bytes(img)
        return f

    jobs = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for p in a["plates"]:
            jobs.append((f"plate_{p['name']}", pool.submit(plate, p)))
        for ch in a["characters"]:
            for d in ch["drawings"]:
                if d.get("kind", "key") == "key":
                    jobs.append((f"{ch['name']}_{d['id']}", pool.submit(key, ch, d)))
        for n, fut in jobs:
            paths[n] = fut.result()
    # a plate where the hero would be a speck or a giant is painted again, closer or wider (once)
    for p in a["plates"]:
        f = paths.get(f"plate_{p['name']}")
        if f and f.exists():
            sc = read_plate(f, p.get("reference", "a pebble"), float(p.get("reference_m", 0.03)))
            hpx = scale.height_px(sc, ground_y(sc, "front"), hero_m)
            if hpx < 0.2 * H:
                plate(p, " Much closer: an extreme close-up at the character's own height.")
            elif hpx > 0.6 * H:
                plate(p, " Wider: step back so the character is smaller in the picture.")
    # cycles, each drawing from the one before (in order); in-betweens from their two keys
    for ch in a["characters"]:
        prev = None
        for d in ch["drawings"]:
            f = out / f"{ch['name']}_{d['id']}.png"
            if d.get("kind") == "cycle":
                if not f.exists():
                    refs = [(SHEETS / f"{ch['sheet']}.png").read_bytes()] + ([prev.read_bytes()] if prev and prev.exists() else [])
                    nxt = " It is the next drawing after the one in the second attached picture." if len(refs) > 1 else ""
                    base = (f"The same character as in the attached model sheet, same face, colours and outline, full body, "
                            f"alone in the middle of the picture, {BACKDROP} Pose: ")
                    img = _try(c, [base + d.get("pose", "") + nxt, base + d.get("pose", "").split(",")[0] + nxt], refs)
                    if img:
                        f.write_bytes(img)
                prev = f
            paths[f"{ch['name']}_{d['id']}"] = f
        for d in ch["drawings"]:
            if d.get("kind") == "inbetween":
                f = out / f"{ch['name']}_{d['id']}.png"
                ka, kb = (out / f"{ch['name']}_{k}.png" for k in d["between"])
                if not f.exists() and ka.exists() and kb.exists():
                    img = _try(c, ["The in-between drawing for animation: the same character exactly halfway between the pose "
                                   "in the first attached picture and the pose in the second, same size, same place, same "
                                   "face and colours, " + BACKDROP], [ka.read_bytes(), kb.read_bytes()])
                    if img:
                        f.write_bytes(img)
                paths[f"{ch['name']}_{d['id']}"] = f
    for e in a.get("effects", []):
        prev = None
        for k in range(int(e.get("drawings", 4))):
            f = out / f"fx_{e['name']}_{k + 1}.png"
            if not f.exists():
                text = e["prompt"] + (", the same effect a moment later, " if prev else ", ") + BACKDROP
                img = _try(c, [text], [prev.read_bytes()] if prev and prev.exists() else [hero])
                if img:
                    f.write_bytes(img)
            prev = f
            paths[f"fx_{e['name']}_{k + 1}"] = f
    return paths


def read_plate(path, reference, reference_m):
    """Muse Spark reads the plate: horizon, the ground's front row, and the reference object's size in pixels."""
    f = path.with_suffix(".scale.json")
    if f.exists():
        return json.loads(f.read_text())
    img = Image.open(path).convert("RGB").resize((PW, PH))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    q = (f"This background painting is {PW} x {PH} pixels. Find {reference}, or the object most like it where a character "
         "would stand. Answer with JSON only: {\"horizon_y\": the pixel row of the horizon or vanishing line, "
         "\"ground_front_y\": the pixel row of the front of the ground a character would stand on, "
         "\"reference_px\": the width in pixels of that object}.")
    d, _ = music.ask_json(music.client(), [{"role": "user", "content": [{"type": "text", "text": q},
                                                                        {"type": "image_url", "image_url": {"url": url}}]}],
                          f"reading {path.parent.name}/{path.name}", 2000)
    out = {"horizon": float(d["horizon_y"]) + OY, "ref_y": float(d["ground_front_y"]) + OY,
           "px_per_m": max(1.0, float(d["reference_px"])) / float(reference_m), "read": d}
    f.write_text(json.dumps(out, indent=1))
    return out


def ground_y(plate, where):
    # the feet stay inside the frame, whatever the reading says
    h, r = plate["horizon"], min(float(plate["ref_y"]), H - 60.0)
    if r - h < 150:
        return r
    return {"front": r, "mid": h + 0.6 * (r - h), "back": h + 0.3 * (r - h)}.get(where, r)


def band(img, hgt, k):
    one = img.resize((max(1, int(img.width * hgt / img.height)), hgt), Image.LANCZOS)
    b = Image.new("RGBA", (W + 400, hgt), (0, 0, 0, 0))
    x = -(k * 97) % one.width - one.width
    while x < b.width:
        b.alpha_composite(one, (x, 0))
        x += one.width - 20
    return b


def render_shot(a, paths, captions):
    d, anchors = {}, {}
    plates = sorted(a["plates"], key=lambda p: int(p.get("from", 0)))
    scales = {}
    for p in plates:
        pp = paths[f"plate_{p['name']}"]
        if not pp.exists():
            continue
        d[f"plate_{p['name']}"] = Image.open(pp).convert("RGBA").resize((PW, PH), Image.LANCZOS)
        scales[p["name"]] = read_plate(pp, p.get("reference", "a pebble"), float(p.get("reference_m", 0.03)))
    pl = scales.get(plates[0]["name"]) or {"horizon": 500, "ref_y": 960, "px_per_m": 2000}
    N = int(a["frames"])
    timeline = []
    for k, p in enumerate(plates):
        end = int(plates[k + 1].get("from", N)) if k + 1 < len(plates) else N
        timeline.append([f"plate_{p['name']}" if f"plate_{p['name']}" in d else list(d)[0], end - int(p.get("from", 0))])
    levels = [{"name": "plate", "depth": 0.5, "at": [OX, OY], "cels": timeline}]
    for e in a.get("effects", []):
        names, size = [], None
        hgt = max(60, int(float(e.get("height", 0.25)) * H))
        for k in range(int(e.get("drawings", 4))):
            f = paths.get(f"fx_{e['name']}_{k + 1}")
            if f and f.exists():
                img = pilot.key(Image.open(f))
                img = img.resize((max(1, int(img.width * hgt / img.height)), hgt), Image.LANCZOS)
                nm = f"fx_{e['name']}_{k + 1}"
                d[nm] = img
                size = img.size
                names.append(nm)
        if names:
            cx, cy = (float(v) for v in e.get("at", [0.5, 0.5]))
            levels.append({"name": f"fx_{e['name']}", "depth": 0.35, "at": [cx * W - size[0] / 2, cy * H - size[1] / 2],
                           "cycle": names, "on": max(1, int(e.get("on") or 3))})
    blank = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    d["none"] = blank
    for ch in a["characters"]:
        place = sorted(ch.get("place", [[0, 0.5, "front"]]), key=lambda p: p[0])
        y0 = ground_y(pl, place[0][2])
        hpx = scale.height_px(pl, y0, float(ch.get("height_m", 0.05)))
        hpx = max(40.0, min(hpx, 0.9 * H))
        for dd in ch["drawings"]:
            f = paths.get(f"{ch['name']}_{dd['id']}")
            nm = f"{ch['name']}_{dd['id']}"
            if f and f.exists():
                cut = poses.fit(pilot.key(Image.open(f)), hpx)
                d[nm], anchors[nm] = cut, poses.measure(cut)["contact"]
        cels = [[(f"{ch['name']}_{n}" if n != "none" else "none") if (n == "none" or f"{ch['name']}_{n}" in d) else "none", int(k)]
                for n, k in ch["timing"]]
        path = [[int(fr), float(x) * W, ground_y(pl, g)] for fr, x, g in place]
        levels.append({"name": ch["name"], "depth": 0.2, "cels": cels, "path": path})
    s = sh.load({"shot": a["shot"], "frames": N, "fps": FPS, "levels": levels, "camera": a.get("camera", []),
                 "cuts": [int(p.get("from", 0)) for p in plates[1:]]})
    errs = sh.validate(s, set(d))
    r = compose.Renderer(d, (W, H), anchors=anchors)
    SHOTS_OUT.mkdir(parents=True, exist_ok=True)
    out = SHOTS_OUT / f"{a['shot']}.mp4"
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    small = []
    for f in range(N):
        fr = Image.fromarray(r.frame(s, f))
        t = float(a["start"]) + f / FPS
        caps = [ln for ln in captions if float(ln["from"]) <= t < float(ln["to"])]
        if caps:
            dr = ImageDraw.Draw(fr, "RGBA")
            for k, ln in enumerate(caps[:2]):
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
    pops = compose.pops(small, cuts=[c // 4 for c in s.cuts])
    return out, errs, pops, r.rendered


def shots(ids, parallel=3):
    """Draw several shots at once (Meta's side), render one at a time (ours), in story order."""
    captions = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    todo = []
    for f in sorted(ANIM.glob("*.json"), key=lambda p: [int(x) for x in p.stem.split("-")]):
        a = json.loads(f.read_text())
        if ids and a["shot"] not in ids:
            continue
        if (SHOTS_OUT / f"{a['shot']}.mp4").exists() and not ids:
            continue
        todo.append(a)
    report = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        drawn = [(a, pool.submit(draw_shot, a)) for a in todo]
        for a, fut in drawn:
            paths = fut.result()
            out, errs, pops, n = render_shot(a, paths, captions)
            line = f"{a['shot']}: {n} drawings, problems {errs[:2] or 'none'}, pops {pops or 'none'}, spent ${pilot.client().spent():.2f}"
            print(line, flush=True)
            report.append(line)
    return report


def cut():
    order = sorted(SHOTS_OUT.glob("*.mp4"), key=lambda p: [int(x) for x in p.stem.split("-")])
    lst = SHOTS_OUT / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in order))
    out = ROOT / "data/drawn/sand-to-chip-drawn.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i",
                    str(ROOT / "data/drawn/score.mp3"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", str(out)], check=True)
    print(out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "shots":
        shots(sys.argv[2:])
    elif cmd == "cut":
        cut()
    else:
        print(__doc__)
