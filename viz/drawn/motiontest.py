"""A 2-second frame-by-frame test (docs/DRAWN-FILM.md): every drawing of the motion from Muse Image. The thieves' run
as an 8-drawing cycle on threes, Grain's shout in 4 drawings, the fire in 4 painted drawings; each edited from the
model sheet and the cycle's first drawing (so mistakes do not pile up), keyed from green, pegged by contact point.

    python3 -m viz.drawn.motiontest draw      data/drawn/motion/*.png
    python3 -m viz.drawn.motiontest render    data/drawn/motion-test.mp4
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from . import compose, meta, pilot, poses, sheet as sh

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/drawn/motion"
SHEETS = ROOT / "data/drawn/sheets"
W, H, FPS = 1920, 1080, 24
START = 28.0

BASE = ("on a solid flat bright green background (#00FF66), no ground, no shadow, no text, " + pilot.STYLE + ". ")
RUN = ["Drawing 1 of an 8-drawing run cycle, side view, running to the right: front foot just touching the ground "
       "ahead, back leg stretched behind, body upright",
       "Drawing 2 of the run cycle: front foot flat on the ground, knee bent, body at its lowest",
       "Drawing 3 of the run cycle: back leg swinging forward past the standing leg, body rising",
       "Drawing 4 of the run cycle: pushing off the standing foot, both feet off the ground, body at its highest",
       "Drawing 5 of the run cycle: the other foot now just touching the ground ahead, the first leg stretched behind",
       "Drawing 6 of the run cycle: that foot flat on the ground, knee bent, body at its lowest",
       "Drawing 7 of the run cycle: the first leg swinging forward past the standing leg, body rising",
       "Drawing 8 of the run cycle: pushing off, both feet off the ground, body at its highest"]
RUNNERS = ("The same two carbon thieves as in the attached model sheet, side by side, each carrying a small round red "
           "ball character under one arm, ")
SHOUT = ["leaning back, breathing in, arms pulled to its sides, about to shout",
         "shouting, mouth wide open, both arms flung out forward",
         "still shouting, arms pumping forward, eyes squeezed",
         "arms dropping, mouth closing, shoulders slumping"]
GRAIN = "The same grey character as in the attached model sheet, same face, full body, alone in the middle of the picture, "
FIRE = ["Only flames, nothing else: a wide row of tall orange and yellow cartoon flames with curling tips, licking upward",
        "Only flames, nothing else: the same row of flames a moment later, tips curled the other way, a little taller",
        "Only flames, nothing else: the same row of flames, two tongues of flame leaping high on the left",
        "Only flames, nothing else: the same row of flames settling lower, embers lifting off the tips"]


def draw():
    OUT.mkdir(parents=True, exist_ok=True)
    c = pilot.client()
    thieves = (SHEETS / "carbon-thieves.png").read_bytes()
    grey = (SHEETS / "grain-03-grey.png").read_bytes()
    hero = pilot.HERO.read_bytes()
    jobs = [(f"run_{k + 1}", RUNNERS + RUN[k] + ", " + BASE, [thieves]) for k in range(8)]
    jobs += [(f"shout_{k + 1}", GRAIN + SHOUT[k] + ", " + BASE, [grey]) for k in range(4)]
    jobs += [(f"fire_{k + 1}", FIRE[k] + ", " + BASE, [hero]) for k in range(4)]
    for name, prompt, refs in jobs:
        p = OUT / f"{name}.png"
        if p.exists():
            continue
        first = OUT / (name.split("_")[0] + "_1.png")
        if not name.endswith("_1") and first.exists():
            refs = refs + [first.read_bytes()]
            prompt += " Keep the characters exactly as in the second attached picture, only the pose changes."
        for text in (prompt, prompt.split(":")[0] + ". " + BASE):
            try:
                p.write_bytes(c.image(text, refs=refs))
                print(name, f"${c.spent():.2f}")
                break
            except meta.OverCap:
                raise
            except Exception as e:
                body = e.read()[:200].decode("utf-8", "replace") if hasattr(e, "read") else ""
                print(name, "refused:", getattr(e, "code", e), body)


def render(out=None):
    d, anchors = {}, {}
    d["plate"] = Image.open(pilot.OUT / "smelt_cutaway.png").convert("RGBA").resize((W + 240, H + 135), Image.LANCZOS)
    for k in range(1, 9):
        cut = poses.fit(pilot.key(Image.open(OUT / f"run_{k}.png")), 300)
        d[f"run_{k}"], anchors[f"run_{k}"] = cut, poses.measure(cut)["contact"]
    for k in range(1, 5):
        cut = poses.fit(pilot.key(Image.open(OUT / f"shout_{k}.png")), 340)
        d[f"shout_{k}"], anchors[f"shout_{k}"] = cut, poses.measure(cut)["contact"]
        f = pilot.key(Image.open(OUT / f"fire_{k}.png"))
        f = f.resize((W + 200, int(f.height * (W + 200) / f.width)), Image.LANCZOS)
        d[f"fire_{k}"] = f
    s = {"shot": "test", "frames": 48, "fps": FPS, "camera": [[0, {"x": 0, "y": 0, "zoom": 1.0}], [47, {"x": 40, "y": 0, "zoom": 1.04}]],
         "levels": [
             {"name": "plate", "depth": 0.5, "at": [-120, -67], "cels": [["plate", 48]]},
             {"name": "fire_back", "depth": 0.45, "at": [-100, 260], "cycle": [f"fire_{k}" for k in (1, 2, 3, 4)], "on": 3},
             {"name": "grain", "depth": 0.2, "at": [720, 905], "cels": [["shout_1", 6], ["shout_2", 9], ["shout_3", 9], ["shout_2", 9], ["shout_4", 15]]},
             {"name": "thieves", "depth": 0.2, "cycle": [f"run_{k}" for k in range(1, 9)], "on": 3,
              "path": [[0, 1150, 900], [47, 1750, 900]]},
             {"name": "fire_front", "depth": 0.1, "at": [-100, 860], "cycle": [f"fire_{k}" for k in (3, 4, 1, 2)], "on": 3}]}
    sheet = sh.load(s)
    out = out or ROOT / "data/drawn/motion-test.mp4"
    r = compose.Renderer(d, (W, H), anchors=anchors)
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-ss", str(START), "-t", "2", "-i", str(ROOT / "data/drawn/score.mp3"), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-c:a", "aac", "-shortest", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fr in r.frames(sheet):
        p.stdin.write(np.ascontiguousarray(fr).tobytes())
    p.stdin.close()
    p.wait()
    # the same 2 seconds slowed to a quarter speed, so each drawing can be seen
    slow = out.with_name(out.stem + "-slow.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(out), "-an", "-vf", "setpts=4*PTS", str(slow)])
    print(out, slow, "drawings:", r.rendered)


if __name__ == "__main__":
    {"draw": draw, "render": render}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
