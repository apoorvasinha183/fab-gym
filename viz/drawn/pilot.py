"""The pilot shot (docs/DRAWN-FILM.md, step 4): Smelt, 22 to 34 s, finished end to end. Muse Image paints three plates
and ten poses (edited from the model sheets, on a flat green backdrop our code keys out); our code draws the furnace
glow, sparks, puffs and steam, pegs every pose by its contact point, writes the exposure sheet and renders it on twos
with a multiplane camera at 1920 x 1080 under the score.

    python3 -m viz.drawn.pilot assets      data/drawn/pilot/*.png (Meta's pictures, cached)
    python3 -m viz.drawn.pilot render      data/drawn/pilot-smelt.mp4
"""

import json
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import compose, meta, poses, sheet as sh

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/drawn/pilot"
SHEETS = ROOT / "data/drawn/sheets"
HERO = ROOT / "docs/img/fabgym-hero.jpg"
W, H, FPS = 1920, 1080, 24
START = 22.0                      # the pilot's place on the film (seconds)

STYLE = ("in the style of the attached picture: hand-inked comic, bold clean black outlines of one even weight, flat cel "
         "colour with a single shade, no gradients")
PLATE = "A wide 16:9 background painting for an animated film, no characters, no people, no faces, no text, " + STYLE + ". "
PLATES = {
    "smelt_furnace": "Inside a smelting hall: a huge round arc furnace in the middle glowing white-orange from its open "
                     "top, three thick dark carbon electrodes going down into it, a chute on the left pouring grey gravel "
                     "into it, dark steel walls and pipes, warm orange light, a few sparks; open floor in the foreground.",
    "smelt_cutaway": "A close-up inside the furnace: swirling orange and yellow heat filling the picture, a flat dark rock "
                     "ledge across the lower third like a small stage, glowing embers.",
    "smelt_pour": "The furnace's pour spout on the left pouring a stream of grey liquid silicon into a long mould on the "
                  "floor, the metal cooling to a dull grey slab, soft steam, a darker industrial wall behind, empty floor "
                  "in the lower middle.",
}
POSE = ("The same character as in the attached model sheet, same face, colours and outline, drawn once, full body, alone "
        "in the middle of the picture, on a solid flat bright green background (#00FF66), no ground, no shadow, no text, "
        + STYLE + ". Pose: ")
POSES = {
    "Q_fall": ("grain-02-quartz", "tumbling down head first, arms flung up, holding hands with its two oxygen twins who "
                                  "tumble with it, all three wide-eyed and worried"),
    "Q_cling": ("grain-02-quartz", "standing between its two small red oxygen twins, holding one twin in each arm close "
                                   "to its body so all three are clearly visible, all three scared, eyes wide"),
    "T_lurk": ("carbon-thieves", "both thieves crouching low side by side, sly grins, rubbing their hands"),
    "T_grab": ("carbon-thieves", "both thieves leaning forward, each grabbing a small red oxygen twin by the arm and pulling"),
    "T_run1": ("carbon-thieves", "both thieves running to the right, each carrying a small red oxygen twin under its arm, "
                                 "left legs forward"),
    "T_run2": ("carbon-thieves", "both thieves running to the right, each carrying a small red oxygen twin under its arm, "
                                 "right legs forward, mid stride"),
    "G_reach": ("grain-03-grey", "reaching out with both arms, shouting, mouth wide open, desperate"),
    "G_sad": ("grain-03-grey", "standing alone, arms hanging down, head low, sad"),
    "G_sit": ("grain-03-grey", "sitting on the ground, glum, a little steam rising off its head"),
    "G_look": ("grain-03-grey", "looking down at its own grey body, surprised and a bit dismayed"),
}
HEIGHT = {"Q_": 330, "T_": 300, "G_": 340}           # on-screen body height in pixels, by character


def client():
    return meta.Client(ledger=ROOT / "data/drawn/ledger.jsonl", cache=ROOT / "data/drawn/cache", cap_usd=25.0)


def assets():
    OUT.mkdir(parents=True, exist_ok=True)
    c = client()
    hero = HERO.read_bytes()
    for name, what in PLATES.items():
        p = OUT / f"{name}.png"
        if not p.exists():
            p.write_bytes(c.image(PLATE + what, refs=[hero]))
            print(name, f"${c.spent():.2f}")
    for name, (src, pose) in POSES.items():
        p = OUT / f"{name}.raw.png"
        if not p.exists():
            refs = [(SHEETS / f"{src}.png").read_bytes()]
            if name.startswith("T_") and name != "T_lurk":
                refs.append((SHEETS / "grain-02-quartz.png").read_bytes())       # the oxygen twins they carry
            for text in (POSE + pose, POSE + pose.split(",")[0] + "."):
                try:
                    p.write_bytes(c.image(text, refs=refs))
                    print(name, f"${c.spent():.2f}")
                    break
                except meta.OverCap:
                    raise
                except Exception as e:
                    body = e.read()[:300].decode("utf-8", "replace") if hasattr(e, "read") else ""
                    print(name, "refused:", getattr(e, "code", e), body)


# ------------------------------------------------------------------ cut-outs

def key(img, tol=110):
    """The pose off its green backdrop: the backdrop's colour from the picture's border, everything near it made clear,
    green spill at the edge pulled out, cropped to the body with a margin."""
    a = np.asarray(img.convert("RGB")).astype(np.int32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    d = np.sqrt(((a - bg) ** 2).sum(-1))
    alpha = np.clip((d - tol * 0.6) / (tol * 0.4), 0, 1)
    g_spill = (a[..., 1] > a[..., 0] + 40) & (a[..., 1] > a[..., 2] + 40)
    alpha[g_spill] = np.minimum(alpha[g_spill], 0.0)
    m = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    rgba = Image.fromarray(a.astype(np.uint8), "RGB").convert("RGBA")
    rgba.putalpha(m)
    box = rgba.getbbox()
    if box:
        x0, y0, x1, y1 = box
        rgba = rgba.crop((max(0, x0 - 8), max(0, y0 - 8), min(rgba.width, x1 + 8), min(rgba.height, y1 + 8)))
    return rgba


# ------------------------------------------------------------------ effects, drawn by our code

def hot_spot(plate):
    g = np.asarray(plate.convert("L").resize((96, 54)).filter(ImageFilter.GaussianBlur(4))).astype(float)
    y, x = np.unravel_index(g.argmax(), g.shape)
    return (x + 0.5) * plate.width / 96, (y + 0.5) * plate.height / 54


def glow(cx, cy, k, size):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    yy, xx = np.mgrid[0:size[1], 0:size[0]]
    r = 420 + 30 * math.sin(k * 1.1)
    a = np.clip(1 - np.hypot(xx - cx, yy - cy) / r, 0, 1) ** 2 * (0.32 + 0.08 * math.sin(k * 2.3))
    arr = np.zeros((size[1], size[0], 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = 255, 150, 50
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def particles(kind, k, size, cx, cy, n=40, seed=3):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rnd = random.Random(seed)
    for i in range(n):
        x0, y0 = cx + rnd.uniform(-420, 420), cy + rnd.uniform(-160, 200)
        sp = rnd.uniform(14, 40)
        t = (k + i * 0.37) % 8
        if kind == "spark":
            x, y = x0 + rnd.uniform(-6, 6) * t, y0 - sp * t
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 236, 140, int(255 * (1 - t / 8))))
            d.line([x, y, x + 2, y + 14], fill=(255, 190, 80, int(180 * (1 - t / 8))), width=3)
        elif kind == "steam":
            x, y = x0 + 8 * math.sin(t + i), y0 - 22 * t
            rr = 26 + 8 * t
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(235, 238, 242, int(70 * (1 - t / 8))))
        else:  # puff
            x, y = x0 + 30 * t, y0 - 10 * t
            rr = 16 + 5 * t
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(90, 90, 96, int(150 * (1 - t / 8))), outline=(28, 22, 38, int(150 * (1 - t / 8))), width=3)
    if kind == "steam":
        img = img.filter(ImageFilter.GaussianBlur(6))
    return img


# ------------------------------------------------------------------ the exposure sheet and the render

def build():
    d, anchors = {}, {}
    pw, ph = W + 240, H + 135                            # plates a little larger than the frame, for the camera
    spots = {}
    for name in PLATES:
        pl = Image.open(OUT / f"{name}.png").convert("RGBA").resize((pw, ph), Image.LANCZOS)
        d[name] = pl
        hx, hy = hot_spot(pl)
        spots[name] = (hx - 120, hy - 67)               # in frame coordinates (the plate sits at -120, -67)
    for name in POSES:
        cut = key(Image.open(OUT / f"{name}.raw.png"))
        cut = poses.fit(cut, HEIGHT[name[:2]])
        d[name] = cut
        anchors[name] = poses.measure(cut)["contact"]
    for k in range(6):
        d[f"glow_{k}"] = glow(*spots["smelt_furnace"], k, (W, H))
        d[f"glowB_{k}"] = glow(*spots["smelt_cutaway"], k, (W, H))
    for k in range(8):
        d[f"spark_{k}"] = particles("spark", k, (W, H), *spots["smelt_furnace"])
        d[f"puff_{k}"] = particles("puff", k, (W, H), 1250, 760, n=14, seed=7)
        d[f"steam_{k}"] = particles("steam", k, (W, H), 980, 860, n=16, seed=11)
    blank = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    d["none"] = blank

    def cels(*runs):
        return [[n, k] for n, k in runs]

    A, B, C, N = 96, 96, 96, 288
    levels = [
        {"name": "plate", "depth": 0.5, "at": [-120, -67],
         "cels": cels(("smelt_furnace", A), ("smelt_cutaway", B), ("smelt_pour", C))},
        {"name": "glow", "depth": 0.45, "cels": [[f"glow_{k % 6}", 2] for k in range(A // 2)] + [[f"glowB_{k % 6}", 2] for k in range(B // 2)]
         + [["none", C]]},
        # Grain's shout lands on its line (28.6 to 29.9 s on the film: frames 158 to 190)
        {"name": "grain", "depth": 0.2, "cels": cels(("Q_fall", 48), ("Q_cling", 48), ("Q_cling", 24), ("G_look", 38),
                                                      ("G_reach", 34), ("G_sad", 36), ("G_sit", 60)),
         "path": [[0, 600, 380], [47, 860, 760], [48, 900, 820], [95, 900, 820], [96, 760, 900], [119, 760, 900],
                  [120, 700, 900], [191, 700, 900], [192, 960, 930], [287, 960, 930]]},
        {"name": "thieves", "depth": 0.2, "cels": cels(("none", 40), ("T_lurk", 56), ("none", 24), ("T_grab", 24))
         + [[("T_run1", "T_run2")[k % 2], 3] for k in range(16)] + [["none", C]],
         "path": [[0, 1520, 900], [95, 1520, 900], [96, 1180, 900], [143, 1180, 900], [144, 1180, 900], [191, 2300, 880]]},
        {"name": "fx", "depth": 0.3, "cels": [[f"spark_{k % 8}", 2] for k in range(A // 2)]
         + [[f"puff_{k % 8}", 2] for k in range(B // 2)] + [[f"steam_{k % 8}", 2] for k in range(C // 2)]},
    ]
    camera = [[0, {"x": 0, "y": 0, "zoom": 1.0}], [95, {"x": 50, "y": 20, "zoom": 1.12}],
              [96, {"x": 0, "y": 0, "zoom": 1.0}], [191, {"x": 30, "y": 0, "zoom": 1.03}],
              [192, {"x": 0, "y": -40, "zoom": 1.05}], [287, {"x": 0, "y": 40, "zoom": 1.05}]]
    s = {"shot": "2", "frames": N, "fps": FPS, "palette": "smelt", "levels": levels, "camera": camera, "cuts": [96, 192]}
    return s, d, anchors


def captions_at(t):
    lines = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    return [ln for ln in lines if float(ln["from"]) <= t + START < float(ln["to"])]


def render(out=None):
    s, d, anchors = build()
    sheet = sh.load(s)
    errs = sh.validate(sheet, set(d))
    if errs:
        raise SystemExit(errs)
    out = out or ROOT / "data/drawn/pilot-smelt.mp4"
    (ROOT / "film/drawn/sheets").mkdir(parents=True, exist_ok=True)
    (ROOT / "film/drawn/sheets/2-smelt.json").write_text(json.dumps(s, indent=1))
    r = compose.Renderer(d, (W, H), anchors=anchors)
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    audio = ROOT / "data/drawn/score.mp3"
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-ss", str(START), "-t", "12", "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-crf", "17", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frames = []
    for f in range(sheet.frames):
        fr = Image.fromarray(r.frame(sheet, f))
        caps = captions_at(f / FPS)
        if caps:
            dr = ImageDraw.Draw(fr, "RGBA")
            for k, ln in enumerate(caps[:2]):
                text = ("GRAIN: " if ln["who"] == "grain" else "") + ln["text"]
                w = dr.textlength(text, font=font)
                y = H - 110 - 60 * k
                dr.rounded_rectangle([W / 2 - w / 2 - 22, y - 10, W / 2 + w / 2 + 22, y + 52], 12, fill=(10, 12, 24, 170))
                dr.text((W / 2 - w / 2, y), text, font=font, fill=(255, 214, 90) if ln["who"] == "grain" else (245, 245, 250))
        a = np.asarray(fr)
        if f % 6 == 0:
            frames.append(a[::4, ::4].copy())
        p.stdin.write(a.tobytes())
    p.stdin.close()
    p.wait()
    print(out, "drawings:", r.rendered, "frames:", sheet.frames, "pops:", compose.pops(frames, cuts=[16, 32]))
    return out


if __name__ == "__main__":
    {"assets": assets, "render": render}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
