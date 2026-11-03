"""The review folder (docs/FILM-PLAYBOOK.md, step 9): everything a second opinion needs in one folder, numbered in the
order to look at it. The film; the storyboard against the finished film (each shot's board beside the same moment in the
cut, with what happens and what is said); the model sheets; every scene's contact sheet; the score; the voice script;
earlier attempts if any are kept; the edit timeline. The how-it-was-made README is written by hand for each review.

    python3 -m viz.drawn.pack [--look L] [OUT]     default ~/Sand to Chip/Second opinion (<look>)
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import scene, timeline

ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home() / "Sand to Chip"
EARLIER = HOME / "7 Earlier attempts"          # kept by hand: rejected cuts and tests worth showing


def font(size):
    return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)


def wrap(dr, text, f, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=f) > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = t
    return out + ([cur] if cur else [])


def storyboard(film, out_pdf):
    """Each shot's board beside the middle frame of the same shot in the cut, four shots to an A4 page."""
    shots = json.loads((ROOT / "film/drawn/shots.json").read_text())["shots"]
    lines = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    F, FB, FS = font(26), font(34), font(22)
    tmp = Path(tempfile.mkdtemp())
    pages, page, dr, rows = [], None, None, 0
    for s in shots:
        if rows == 0:
            page = Image.new("RGB", (2480, 3508), (255, 252, 246))
            dr = ImageDraw.Draw(page)
            dr.text((80, 50), "Sand to Chip, drawn: storyboard and finished frames", font=FB, fill=(30, 30, 40))
            dr.text((80, 100), "left: the board drawn first  ·  middle: the same moment in the finished film  ·  right: what "
                    "happens and what is said", font=FS, fill=(110, 110, 120))
        y = 160 + rows * 800
        fr = tmp / f"{s['id']}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str((float(s["start"]) + float(s["end"])) / 2), "-i",
                        str(film), "-frames:v", "1", str(fr)], check=True)
        for k, img in enumerate((ROOT / f"data/drawn/boards/{s['id']}.png", fr)):
            im = Image.open(img).convert("RGB")
            im.thumbnail((860, 700))
            page.paste(im, (80 + k * 900, y + 20))
        dr.text((1880, y + 20), f"Shot {s['id']}", font=FB, fill=(30, 30, 40))
        dr.text((1880, y + 66), f"{s['start']:.0f} to {s['end']:.0f} s", font=FS, fill=(110, 110, 120))
        yy = y + 110
        for t in wrap(dr, s["action"], F, 540):
            dr.text((1880, yy), t, font=F, fill=(40, 40, 50))
            yy += 34
        yy += 16
        for ln in [x for x in lines if x.get("shot") == s["id"]]:
            who = {"grain": "Grain", "lou": "Lou"}.get(ln["who"], "Narrator")
            for t in wrap(dr, f"{who}: “{ln['text']}”", F, 540):
                dr.text((1880, yy), t, font=F, fill=(150, 90, 0) if who != "Narrator" else (60, 60, 120))
                yy += 34
        rows += 1
        if rows == 4:
            pages.append(page)
            rows = 0
    if rows:
        pages.append(page)
    pages[0].save(out_pdf, save_all=True, append_images=pages[1:], resolution=200)
    return len(pages)


def pack(out=None):
    look = scene.LOOK["name"]
    film = scene.SHOTS_OUT.parent / "sand-to-chip.mp4"
    if look == "comic" and not film.exists():
        film = ROOT / "data/drawn/sand-to-chip-drawn.mp4"
    if not film.exists():
        raise SystemExit(f"no cut yet: run python3 -m viz.drawn.scene --look {look} cut")
    R = Path(out or HOME / f"Second opinion ({look})")
    if R.exists():
        shutil.rmtree(R)
    d = {k: R / k for k in ("1 Film", "2 Storyboard", "3 Characters", "4 Scenes, every drawing", "5 Music", "6 Voice",
                            "7 Earlier attempts", "8 Edit timeline")}
    for p in d.values():
        p.mkdir(parents=True)
    shutil.copy2(film, d["1 Film"] / "Sand to Chip (1080p).mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(film), "-vf", "scale=1280:-2", "-c:v", "libx264", "-crf",
                    "26", "-c:a", "aac", "-b:a", "128k", str(d["1 Film"] / "Sand to Chip (720p, smaller).mp4")], check=True)
    pages = storyboard(film, d["2 Storyboard"] / "storyboard (board vs finished).pdf")
    shutil.copytree(ROOT / "data/drawn/boards", d["2 Storyboard"] / "boards, one per shot")
    for f in (ROOT / "data/drawn/story-reel-scored.mp4",):
        if f.exists():
            shutil.copy2(f, d["2 Storyboard"] / "story reel (boards timed to the music).mp4")
    for f in sorted(scene.SHEETS.glob("*.png")):
        if "-v1" not in f.stem:
            shutil.copy2(f, d["3 Characters"] / f.name)
    for f in sorted(scene.ART.glob("*/contact.jpg"), key=lambda p: int(p.parent.name)):
        shutil.copy2(f, d["4 Scenes, every drawing"] / f"scene {int(f.parent.name):02d}, contact sheet.jpg")
    shutil.copy2(ROOT / "data/drawn/score.pdf", d["5 Music"] / "score (full orchestra).pdf")
    shutil.copy2(ROOT / "data/drawn/score.mp3", d["5 Music"] / "score (played by MuseScore).mp3")
    shutil.copy2(ROOT / "film/drawn/score/sand-to-chip.musicxml", d["5 Music"] / "score (open in MuseScore).musicxml")
    shutil.copy2(ROOT / "film/drawn/VOICE-SCRIPT.md", d["6 Voice"] / "voice script.md")
    lines = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    (d["6 Voice"] / "voice lines, timed (subtitles).srt").write_text(timeline.srt(lines))
    if EARLIER.exists():
        for f in sorted(EARLIER.iterdir()):
            shutil.copy2(f, d["7 Earlier attempts"] / f.name)
    timeline.SHOTS = scene.SHOTS_OUT
    timeline.OUT = d["8 Edit timeline"]
    timeline.main()
    print(R, f"{pages} storyboard pages; write README.md by hand (docs/FILM-PLAYBOOK.md, step 9)")
    return R


if __name__ == "__main__":
    args = sys.argv[1:]
    look = None
    if args and args[0] == "--look":
        look, args = args[1], args[2:]
    scene.use(look)
    pack(*args)
