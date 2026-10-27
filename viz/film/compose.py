"""Put the words on the film: captions, the clock and step card of Act 3, the bar of shot 11, the
shares of shot 12, the campus labels of shot 2 and the end card, over the frames Blender rendered
(viz/blender/real.py). A gigafab-style layout of our own design on the SMT2020 model.

    python3 viz/film/compose.py FRAMES_DIR FILM.json OVERLAY.json OUT.mp4 [--from N --to M]

Needs Pillow and ffmpeg. Writes the composed frames next to OUT, then the film.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

argv = sys.argv[1:]
FR_DIR, FILM, OVER, OUT = (Path(x) for x in argv[:4])
F = json.loads(FILM.read_text())
O = json.loads(OVER.read_text())
FPS = 24
SHOTS = {s["id"]: s for s in F["shots"]}
TM = F["timemap"]
BEATS = F["beats"]
LEAVE = BEATS[0]["t"]
FONT = "/System/Library/Fonts/Avenir Next.ttc"


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT, size, index=5 if bold else 0)
    except OSError:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)


F_CAP = font(40)
F_CAP_B = font(40, True)
F_SMALL = font(24)
F_SMALL_B = font(24, True)
F_CLOCK = font(54, True)
F_LABEL = font(28, True)
F_END = font(60, True)
F_END2 = font(30)
CYAN = (57, 213, 255)
WHITE = (245, 247, 250)


def sim_at(s):
    for a, b, c, d in TM:
        if a <= s <= b:
            return c + (d - c) * (s - a) / (b - a), (d - c) * 60 / (b - a)
    a, b, c, d = TM[-1]
    return c + (d - c) * (s - a) / (b - a), (d - c) * 60 / (b - a)


def shot_at(s):
    for sh in F["shots"]:
        if sh["start"] <= s < sh["end"]:
            return sh
    return F["shots"][-1]


def fade(s, a, b, ramp=0.35):
    if s < a or s > b:
        return 0.0
    return min(1.0, (s - a) / ramp, (b - s) / ramp)


def hm(m):
    m = int(round(m))
    h, r = divmod(m, 60)
    return f"{h} h {r:02d} min" if h else f"{r} min"


def panel(d, box, alpha):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=14, fill=(12, 16, 22, int(170 * alpha)))


def text(d, xy, s, f, alpha, fill=WHITE):
    d.text(xy, s, font=f, fill=fill + (int(255 * alpha),))


def wrap(d, s, f, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def captions(d, s, W, H):
    sh = shot_at(s)
    caps = F["captions"][sh["id"]]
    n = len(caps)
    span = (sh["end"] - sh["start"]) / n
    for i, c in enumerate(caps):
        a = fade(s, sh["start"] + i * span + 0.2, sh["start"] + (i + 1) * span - 0.1)
        if a <= 0 or sh["id"] == "end":
            continue
        lines = wrap(d, c, F_CAP, W * 0.52)
        h = 54 * len(lines) + 28
        y0 = H - 70 - h
        panel(d, (60, y0, 60 + max(d.textlength(x, font=F_CAP) for x in lines) + 48, y0 + h), a)
        for j, x in enumerate(lines):
            text(d, (84, y0 + 14 + j * 54), x, F_CAP, a)


def step_now(t):
    """The hero's state at fab minute t: (step index, 'moving' | 'waiting' | 'on the tool')."""
    prev_end = LEAVE
    for i, b in enumerate(BEATS[1:], 1):
        if t < b["arrive"]:
            return i, "moving to"
        if t < b["start"]:
            return i, "waiting for"
        if t < b["end"]:
            return i, "on"
        prev_end = b["end"]
    return len(BEATS) - 1, "done"


def act3(d, s, W, H):
    a = fade(s, SHOTS["5"]["start"] + 0.5, SHOTS["10"]["end"], ramp=0.6)
    if a <= 0:
        return
    t, speed = sim_at(s)
    since = t - LEAVE
    x1 = W - 60
    box = (x1 - 470, 60, x1, 60 + 168)
    panel(d, box, a)
    text(d, (box[0] + 26, 74), "since leaving wet etch", F_SMALL, a, (190, 200, 210))
    sign = "-" if since < 0 else "+"
    text(d, (box[0] + 26, 104), f"{sign}{hm(abs(since))}", F_CLOCK, a)
    text(d, (box[0] + 26, 178), f"fab time  ×{speed:,.0f}", F_SMALL_B, a, CYAN)
    # the step card
    i, what = step_now(t)
    b = BEATS[i]
    lines = [f"{F['name']}", f"{what} {b['what']}" if what != "done" else "", b["group"]]
    if SHOTS["9"]["start"] <= s < SHOTS["10"]["end"]:
        done = [x for x in BEATS[3:-1] if x["end"] <= t]
        lines += [f"· {x['what']}  {hm(x['end'] - x['start'])}" for x in done]
    y = box[3] + 18
    h = 36 * len([x for x in lines if x]) + 26
    panel(d, (box[0], y, x1, y + h), a)
    k = 0
    for j, x in enumerate(lines):
        if not x:
            continue
        text(d, (box[0] + 26, y + 13 + 36 * k), x, F_SMALL_B if j < 2 else F_SMALL, a, CYAN if j == 0 else WHITE)
        k += 1


def hero_tag(d, s, fr, W, H):
    if not (SHOTS["6"]["start"] <= s < SHOTS["10"]["end"]):
        return
    p = O["frames"].get(str(fr), {}).get("hero")
    if not p or p[2] <= 2.0 or not (0.03 < p[0] < 0.97 and 0.05 < p[1] < 0.95):
        return
    x, y = p[0] * W, p[1] * H
    r = max(14, min(40, 400 / p[2]))
    d.ellipse((x - r, y - r, x + r, y + r), outline=CYAN + (230,), width=3)
    d.line((x + r * 0.7, y - r * 0.7, x + r * 0.7 + 34, y - r * 0.7 - 34), fill=CYAN + (230,), width=3)
    text(d, (x + r * 0.7 + 40, y - r * 0.7 - 58), F["name"], F_SMALL_B, 1.0, CYAN)


def bar(d, s, W, H):
    a = fade(s, SHOTS["11"]["start"] + 1.0, SHOTS["11"]["end"] + 0.3)
    if a <= 0:
        return
    on = sum(b["end"] - b["start"] for b in BEATS[1:])
    wait = sum(b["start"] - b["arrive"] for b in BEATS[1:])
    ends = [LEAVE] + [b["end"] for b in BEATS[1:]]
    move = sum(b["arrive"] - e for b, e in zip(BEATS[1:], ends))
    tot = on + wait + move
    grow = min(1.0, (s - SHOTS["11"]["start"] - 1.0) / 4.0)
    x0, y0, w, h = 60, 60, W * 0.5, 34
    panel(d, (x0 - 20, y0 - 20, x0 + w + 20, y0 + h + 92), a)
    x = x0
    for v, c, name in ((on, (120, 200, 140), "on tools"), (wait, (255, 176, 32), "waiting"), (move, CYAN, "moving")):
        ww = w * v / tot * grow
        d.rectangle((x, y0, x + ww, y0 + h), fill=c + (int(255 * a),))
        x += ww
    lx = x0
    for v, c, name in ((on, (120, 200, 140), "on tools"), (wait, (255, 176, 32), "waiting"), (move, CYAN, "moving")):
        lab = f"{name} {hm(v)}"
        d.rectangle((lx, y0 + h + 22, lx + 18, y0 + h + 40), fill=c + (int(255 * a),))
        text(d, (lx + 26, y0 + h + 14), lab, F_SMALL_B, a)
        lx += d.textlength(lab, font=F_SMALL_B) + 60


def shares(d, s, W, H):
    a = fade(s, SHOTS["12"]["start"] + 0.8, SHOTS["12"]["end"] + 0.3)
    if a <= 0:
        return
    sh = F["shares"]
    x0, y0, w, h = 60, 60, W * 0.5, 34
    panel(d, (x0 - 20, y0 - 20, x0 + w + 20, y0 + h + 92), a)
    text(d, (x0, y0 - 6), "", F_SMALL, a)
    x = x0
    parts = ((sh["tool"], (120, 200, 140), "on tools or timed holds"), (sh["wait"], (255, 176, 32), "waiting for a tool"),
             (sh["move"], CYAN, "moving"))
    for v, c, name in parts:
        d.rectangle((x, y0, x + w * v, y0 + h), fill=c + (int(255 * a),))
        x += w * v
    lx = x0
    for v, c, name in parts:
        lab = f"{name} {v:.0%}"
        d.rectangle((lx, y0 + h + 22, lx + 18, y0 + h + 40), fill=c + (int(255 * a),))
        text(d, (lx + 26, y0 + h + 14), lab, F_SMALL_B, a)
        lx += d.textlength(lab, font=F_SMALL_B) + 50
    text(d, (x0, y0 + h + 52), "all lots in the clip's hours, on the SMT2020 model", F_SMALL, a, (190, 200, 210))


def labels(d, s, fr, W, H):
    a0 = fade(s, SHOTS["2"]["start"] + 0.3, SHOTS["2"]["end"] - 0.2, ramp=0.8)
    if a0 <= 0:
        return
    pts = O["frames"].get(str(fr), {}).get("labels", [])
    placed = []
    for name, p in zip(O["labels"], pts):
        if p[2] <= 0 or not (0.06 < p[0] < 0.94 and 0.08 < p[1] < 0.9):
            continue
        edge = min(p[0] - 0.06, 0.94 - p[0], p[1] - 0.08, 0.9 - p[1])
        a = a0 * min(1.0, edge / 0.06)
        x, y = p[0] * W, p[1] * H
        tw = d.textlength(name, font=F_LABEL)
        bx = (x - tw / 2 - 14, y - 74, x + tw / 2 + 14, y - 30)
        if any(not (bx[2] < q[0] or bx[0] > q[2] or bx[3] < q[1] or bx[1] > q[3]) for q in placed):
            continue
        placed.append(bx)
        d.line((x, y, x, y - 30), fill=WHITE + (int(220 * a),), width=2)
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=WHITE + (int(240 * a),))
        panel(d, bx, a)
        text(d, (bx[0] + 14, bx[1] + 4), name, F_LABEL, a)


def end_card(img, d, s, W, H):
    a = fade(s, SHOTS["end"]["start"], SHOTS["end"]["end"] + 1, ramp=0.8)
    if a <= 0:
        return
    d.rectangle((0, 0, W, H), fill=(8, 11, 16, int(200 * a)))
    t1 = "Fab Gym"
    text(d, ((W - d.textlength(t1, font=F_END)) / 2, H * 0.36), t1, F_END, a)
    for i, line in enumerate(wrap(d, F["captions"]["end"][0].replace("Fab Gym. ", ""), F_END2, W * 0.7)):
        text(d, ((W - d.textlength(line, font=F_END2)) / 2, H * 0.36 + 96 + i * 44), line, F_END2, a, (210, 218, 228))
    small = ["SMT2020 high-volume testbed: Kopp, Hassoun, Kalir and Mönch, 2020.",
             "Buildings, tools and carriers are generic shapes of our own design.",
             "Sky: Poly Haven. Ground textures: ambientCG. Cars: Kenney. People: Quaternius. All CC0.",
             "Tool sizes, floors and the campus are cited or assumed in docs/FAB-LOOK.md."]
    for i, line in enumerate(small):
        text(d, ((W - d.textlength(line, font=F_SMALL)) / 2, H * 0.72 + i * 34), line, F_SMALL, a, (160, 170, 182))


def badge(d, s, W, H):
    if s >= SHOTS["end"]["start"]:
        return
    t = "On the SMT2020 model · a layout of our own design · not a real fab"
    text(d, (W - 60 - d.textlength(t, font=F_SMALL), H - 52), t, F_SMALL, 0.7, (215, 222, 230))


def _add(a, b):
    from PIL import ImageChops

    return ImageChops.add(a, b, scale=1.0)


def compose(fr):
    s = (fr - 1) / FPS
    img = Image.open(FR_DIR / f"f{fr:04d}.jpg").convert("RGB")
    img = _add(img, img.resize((img.width // 4, img.height // 4)).point(lambda v: max(0, v - 205) * 3).filter(ImageFilter.GaussianBlur(5)).resize(img.size))
    W, H = img.size
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    labels(d, s, fr, W, H)
    hero_tag(d, s, fr, W, H)
    act3(d, s, W, H)
    bar(d, s, W, H)
    shares(d, s, W, H)
    captions(d, s, W, H)
    end_card(img, d, s, W, H)
    badge(d, s, W, H)
    return Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")


def main():
    frames = sorted(int(p.stem[1:]) for p in FR_DIR.glob("f*.jpg"))
    a = int(argv[argv.index("--from") + 1]) if "--from" in argv else frames[0]
    b = int(argv[argv.index("--to") + 1]) if "--to" in argv else frames[-1]
    tmp = OUT.parent / (OUT.stem + "-frames")
    tmp.mkdir(parents=True, exist_ok=True)
    for fr in frames:
        if a <= fr <= b:
            compose(fr).save(tmp / f"c{fr:04d}.jpg", quality=92)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-start_number", str(a), "-i", str(tmp / "c%04d.jpg"),
                    "-frames:v", str(b - a + 1), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow",
                    "-movflags", "+faststart", str(OUT)], check=True)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
