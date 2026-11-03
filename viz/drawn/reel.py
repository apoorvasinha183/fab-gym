"""The story reel for the drawn film (docs/DRAWN-FILM.md, step 2): Muse Spark writes the shot list from the script,
Muse Image draws one rough board per shot, and the reel holds each board for its shot over the soundtrack, with the
script's words as captions. Everything Meta is called through the metered client (cap $25).

    python3 -m viz.drawn.reel shots      film/drawn/shots.json from docs/CHIP-FILM.md
    python3 -m viz.drawn.reel boards     data/drawn/boards/<shot>.png, one per shot
    python3 -m viz.drawn.reel reel       data/drawn/story-reel.mp4
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from . import captions, meta

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/CHIP-FILM.md"
SHOTS = ROOT / "film/drawn/shots.json"
DATA = ROOT / "data/drawn"
SOUND = ROOT / "data/film/out/from-sand-to-chip.mp4"
CAP = 25.0

FORMS = {"0": "a grain of sand", "1": "quartz holding hands with its two oxygen twins (red balls)",
         "2": "grey silicon lump, its oxygen twins stolen by black carbon thieves", "3": "a lilac wisp of gas shaking off dark specks",
         "4": "a tall silver crystal ingot with a seed rod on top", "5": "a thin mirror-bright wafer disc",
         "6": "the wafer in a sealed box of 25 riding into the fab", "7": "the wafer being built layer by layer, becoming the wafer coach "
         "(a wafer tiled with coloured dies, wearing a red headband)", "8": "one die among hundreds of identical sibling dies",
         "9": "a die under fine test needles", "10": "a single die cut free", "11": "the die in a black package with gold wires",
         "12": "the packaged chip flying into a phone that wakes up"}

STYLE = ("Fab Gym's comic house style: hand-inked cartoon, bold clean black outlines of one even weight, flat cel colour "
         "with a single shade, no gradients, no text.")


def client():
    return meta.Client(ledger=DATA / "ledger.jsonl", cache=DATA / "cache", cap_usd=CAP)


def scenes():
    """(number, title, start seconds, length seconds, narration) from the script's headings and quotes."""
    text = SCRIPT.read_text()
    out = []
    for m in re.finditer(r"^## (\d+)\. (.+?) \((\d+):(\d+), (\d+) s\).*?$(.*?)(?=^## |\Z)", text, re.S | re.M):
        body = m.group(6)
        narr = " ".join(q.strip() for q in re.findall(r"^> (.+)$", body, re.M))
        out.append({"n": m.group(1), "title": m.group(2), "start": int(m.group(3)) * 60 + int(m.group(4)),
                    "seconds": int(m.group(5)), "narration": narr, "body": body.strip()})
    return out


def ask_shots():
    sc = scenes()
    spec = {"shots": [{"id": "2-1", "scene": "2", "start": 22.0, "end": 26.0, "plate": "what the painted background shows, no characters",
                       "action": "what happens", "grain": "Grain's poses in order, each a short name and what it shows",
                       "others": "other characters and their poses", "effects": "fire, gas, sparks... drawn by code",
                       "camera": "hold, push in, pan left...", "caption": "the narration words spoken during this shot, copied exactly",
                       "board": "a one-sentence picture of the shot for a rough storyboard sketch"}]}
    prompt = (
        "You are the director of a short hand-drawn animated film, 'Sand to Chip', 2 minutes 44 seconds, 13 scenes. "
        "The hero is Grain, a grain of sand with big round eyes, who keeps its face through every form. Its form per scene: "
        + json.dumps(FORMS) + ". Lou Latency, a boxy robot CEO in a suit, has one cameo in scene 6, stamping the wafer box "
        "'simulated from here'. Supporting cast: the oxygen twins, the carbon thieves, the specks, the sibling dies.\n\n"
        "Break every scene into shots (about 40 in all, 2 to 6 seconds each). Shots must run back to back from 0 to 164 "
        "seconds with no gaps, inside each scene's start and length. Keep the science of the script. Each shot's caption "
        "copies exactly the narration words spoken during it (split a scene's narration across its shots in order, every "
        "word used once; empty if none). Answer with JSON only, in this shape: " + json.dumps(spec) + "\n\nThe scenes:\n"
        + json.dumps([{k: s[k] for k in ("n", "title", "start", "seconds", "narration", "body")} for s in sc]))
    c = client()
    text = c.chat([{"role": "user", "content": prompt}], "shot list for the drawn film", effort="low", max_tokens=16000)
    m = re.search(r"\{.*\}", text, re.S)
    shots = json.loads(m.group(0))["shots"]
    return shots, sc, c.spent()


def check_shots(shots, sc):
    """What is wrong with a shot list: gaps, overlaps, shots outside their scene, captions not in the script."""
    errs = []
    shots = sorted(shots, key=lambda s: float(s["start"]))
    t = 0.0
    for s in shots:
        if abs(float(s["start"]) - t) > 0.05:
            errs.append(f"shot {s['id']} starts at {s['start']}, expected {t:.1f}")
        if float(s["end"]) <= float(s["start"]):
            errs.append(f"shot {s['id']} ends before it starts")
        t = float(s["end"])
        scene = next((x for x in sc if x["n"] == str(s["scene"])), None)
        if scene and not (scene["start"] - 0.05 <= float(s["start"]) and float(s["end"]) <= scene["start"] + scene["seconds"] + 0.05):
            errs.append(f"shot {s['id']} runs outside scene {s['scene']}")
    if abs(t - 164.0) > 0.05:
        errs.append(f"the shots end at {t:.1f} s, not 164")
    bad = captions.not_in_script([s["caption"] for s in shots if s.get("caption")], SCRIPT.read_text())
    errs += [f"caption not in the script: {b[:60]}" for b in bad]
    return errs


def boards(shots):
    c = client()
    out = DATA / "boards"
    out.mkdir(parents=True, exist_ok=True)
    for s in shots:
        p = out / f"{s['id']}.png"
        if p.exists():
            continue
        prompt = (f"A rough storyboard sketch for an animated film, loose grey pencil on white paper, 16:9, simple shapes, "
                  f"no colour, no words. {s['board']} The hero Grain is {FORMS.get(str(s['scene']), 'a grain of sand')}, "
                  f"with big round eyes. Camera: {s['camera']}.")
        try:
            img = c.image(prompt)
        except meta.OverCap as e:
            print("stopped:", e)
            break
        p.write_bytes(img)
        print(s["id"], "board", f"spent ${c.spent():.2f}")
    return c.spent()


def reel(shots):
    """Each board held for its shot, its caption under it, over the soundtrack; streamed to ffmpeg."""
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    W, H, fps = 1280, 720, 24
    font_path = ROOT / "viz/fab3d/ui/fonts/kenpixel.ttf"
    font = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default()
    out = DATA / "story-reel.mp4"
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-i", str(SOUND), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
           "-c:a", "aac", "-shortest", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for s in sorted(shots, key=lambda s: float(s["start"])):
        n = int(round((float(s["end"]) - float(s["start"])) * fps))
        bp = DATA / "boards" / f"{s['id']}.png"
        img = Image.open(bp).convert("RGB").resize((W, H - 120)) if bp.exists() else Image.new("RGB", (W, H - 120), (240, 240, 240))
        frame = Image.new("RGB", (W, H), (13, 20, 48))
        frame.paste(img, (0, 0))
        d = ImageDraw.Draw(frame)
        d.text((16, H - 112), f"{s['id']}  {s.get('action', '')}"[:110], font=font, fill=(255, 211, 77))
        words = s.get("caption", "")
        lines, line = [], ""
        for w in words.split():
            if len(line) + len(w) > 92:
                lines.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        lines.append(line)
        for k, ln in enumerate(lines[:3]):
            d.text((16, H - 80 + 26 * k), ln, font=font, fill=(238, 241, 255))
        buf = np.asarray(frame, dtype=np.uint8).tobytes()
        for _ in range(n):
            p.stdin.write(buf)
    p.stdin.close()
    p.wait()
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "shots":
        shots, sc, spent = ask_shots()
        SHOTS.parent.mkdir(parents=True, exist_ok=True)
        SHOTS.write_text(json.dumps({"about": "The drawn film's shot list, written by Muse Spark from docs/CHIP-FILM.md, "
                                     "checked by viz/drawn/reel.py.", "shots": shots}, indent=1))
        errs = check_shots(shots, sc)
        print(len(shots), "shots;", len(errs), "problems; spent", f"${spent:.4f}")
        for e in errs[:30]:
            print(" ", e)
    elif cmd == "boards":
        print("spent", boards(json.loads(SHOTS.read_text())["shots"]))
    elif cmd == "reel":
        print(reel(json.loads(SHOTS.read_text())["shots"]))
    else:
        print(__doc__)
