"""A guide video for recording the demo: your lines as subtitles at speaking pace, Lou's box typing out at each cue
(with a "press ]" flash), and a strip naming the screen to be on. Silent; play it beside you while you record.

    python3 video/guide.py [OUT.mp4] [--wps 2.6]

Reads video/script.json and video/lou-cues.json. Needs Pillow and ffmpeg.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
W, H, FPS = 1920, 1080, 30
TYPE_RATE = 48.0                      # Lou's characters a second, as in the pages and the 3D fab
NAVY, EDGE, GOLD, INK, DIM = (18, 26, 84), (247, 247, 247), (255, 216, 74), (243, 244, 255), (150, 158, 210)


def font(name, size, index=0):
    for p in (f"/System/Library/Fonts/{name}", f"/Library/Fonts/{name}"):
        if Path(p).exists():
            return ImageFont.truetype(p, size, index=index)
    return ImageFont.load_default()


SUB = font("HelveticaNeue.ttc", 46, 0)
SUB_B = font("HelveticaNeue.ttc", 30, 1)
SMALL = font("HelveticaNeue.ttc", 28, 0)
MONO = font("Menlo.ttc", 34, 1)
MONO_S = font("Menlo.ttc", 22, 1)


def timeline(wps):
    """Every event with its start and length in seconds: subtitles, Lou's cues, and the screen each beat is on."""
    cues = {c["id"]: (i, c["text"]) for i, c in enumerate(json.loads((HERE / "lou-cues.json").read_text())["cues"], 1)}
    beats = json.loads((HERE / "script.json").read_text())["beats"]
    t, ev = 1.0, []
    for b in beats:
        start = t
        for kind, val in b["items"]:
            if kind == "you":
                d = len(val.split()) / wps + 0.5
                ev.append({"kind": "you", "t": t, "d": d, "text": val})
            else:
                n, text = cues[val]
                d = len(text) / TYPE_RATE + max(2.2, len(text) / 22.0)
                ev.append({"kind": "lou", "t": t, "d": d, "text": text, "n": n})
            t += d + 0.25
        ev.append({"kind": "screen", "t": start, "d": t - start, "text": b["screen"], "do": b.get("do", "")})
        t += 0.6
    return ev, t + 1.5


def wrap(draw, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if draw.textlength(nxt, font=f) <= width:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def frame(t, ev, total, portrait):
    im = Image.new("RGB", (W, H), (14, 19, 48))
    d = ImageDraw.Draw(im)
    # the screen strip
    for e in ev:
        if e["kind"] == "screen" and e["t"] <= t < e["t"] + e["d"]:
            d.rectangle([0, 0, W, 132], fill=(27, 33, 96))
            d.text((60, 26), "SCREEN", font=MONO_S, fill=GOLD)
            d.text((60, 54), e["text"], font=SUB_B, fill=INK)
            d.text((60, 94), e["do"], font=SMALL, fill=DIM)
    m, s = divmod(int(t), 60)
    d.text((W - 60, 40), f"{m}:{s:02d} / {int(total) // 60}:{int(total) % 60:02d}", font=MONO_S, fill=DIM, anchor="ra")
    # progress
    d.rectangle([0, 132, int(W * min(t / total, 1.0)), 138], fill=GOLD)
    # your line, as a subtitle in the middle of the screen
    for e in ev:
        if e["kind"] == "you" and e["t"] <= t < e["t"] + e["d"]:
            lines = wrap(d, e["text"], SUB, 1500)
            y = 420 - len(lines) * 32
            d.text((W // 2, y - 60), "YOU", font=MONO_S, fill=GOLD, anchor="ma")
            for ln in lines:
                d.text((W // 2, y), ln, font=SUB, fill=INK, anchor="ma")
                y += 64
    # Lou's box, typing, at the bottom as on the pages
    for e in ev:
        if e["kind"] == "lou" and e["t"] - 0.6 <= t < e["t"] + e["d"]:
            if t < e["t"] + 0.5:
                d.rounded_rectangle([W // 2 - 190, 560, W // 2 + 190, 640], 12, fill=GOLD)
                d.text((W // 2, 600), f"PRESS ]  ·  LOU {e['n']}", font=MONO, fill=(20, 26, 74), anchor="mm")
            if t < e["t"]:
                continue
            x0, y0, x1, y1 = 40, H - 300, W - 40, H - 40
            d.rounded_rectangle([x0, y0, x0 + 250, y1], 10, fill=NAVY, outline=EDGE, width=5)
            im.paste(portrait, (x0 + 25, y0 + 18))
            d.text((x0 + 125, y1 - 34), "LOU LATENCY", font=MONO_S, fill=GOLD, anchor="ma")
            d.rounded_rectangle([x0 + 270, y0, x1, y1], 10, fill=NAVY, outline=EDGE, width=5)
            d.text((x0 + 305, y0 + 24), "LOU LATENCY, CEO", font=MONO_S, fill=GOLD)
            shown = e["text"][: int((t - e["t"]) * TYPE_RATE)].upper()
            yy = y0 + 70
            for ln in textwrap.wrap(shown, 62):
                d.text((x0 + 305, yy), ln, font=MONO, fill=INK)
                yy += 50
    return im


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    wps = float(sys.argv[sys.argv.index("--wps") + 1]) if "--wps" in sys.argv else 2.6
    out = Path(args[0]) if args else ROOT / "data" / "video" / "guide.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    ev, total = timeline(wps)
    portrait = Image.open(ROOT / "web" / "cast" / "lou-portrait.png").convert("RGB").resize((200, 200))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", str(out)],
                          stdin=subprocess.PIPE)
    for k in range(int(total * FPS)):
        ff.stdin.write(frame(k / FPS, ev, total, portrait).tobytes())
    ff.stdin.close()
    ff.wait()
    print(f"{out}: {total:.0f} s at {wps} words a second")


if __name__ == "__main__":
    main()
