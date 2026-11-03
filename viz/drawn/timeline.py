"""The drawn film as an editor's timeline (docs/DRAWN-FILM.md): an MLT project (the format Kdenlive is built on) with
the 38 shots on one video track, the score on one audio track and an empty track for the voices, plus every voice
line as subtitles (SRT) at its time, so the recordings can be laid in by hand.

    python3 -m viz.drawn.timeline      data/drawn/edit/sand-to-chip.mlt, data/drawn/edit/voice.srt
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
SCENES = ROOT / "film/drawn/scenes"
SHOTS = ROOT / "data/drawn/shots"
OUT = ROOT / "data/drawn/edit"
FPS = 24


def shots():
    rows = []
    for f in sorted(SCENES.glob("*.json"), key=lambda p: int(p.stem)):
        for s in json.loads(f.read_text())["shots"]:
            rows.append((s["id"], float(s["start"]), int(s["frames"])))
    return rows


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def srt(lines):
    out = []
    for i, ln in enumerate(lines, 1):
        who = {"grain": "GRAIN: ", "lou": "LOU: "}.get(ln["who"], "")
        out.append(f"{i}\n{srt_time(float(ln['from']))} --> {srt_time(float(ln['to']))}\n{who}{ln['text']}\n")
    return "\n".join(out)


def mlt(rows, score):
    total = sum(r[2] for r in rows)
    x = ['<?xml version="1.0" encoding="utf-8"?>',
         '<mlt LC_NUMERIC="C" version="7.0.0" title="Sand to Chip, drawn" producer="main">',
         f'<profile description="HD 1080p {FPS} fps" width="1920" height="1080" progressive="1" sample_aspect_num="1" '
         f'sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" frame_rate_num="{FPS}" '
         'frame_rate_den="1" colorspace="709"/>']
    for sid, _, n in rows:
        x.append(f'<producer id="shot_{sid}" in="0" out="{n - 1}"><property name="resource">'
                 f'{escape(str(SHOTS / (sid + ".mp4")))}</property><property name="kdenlive:clipname">shot {sid}'
                 '</property><property name="audio_index">-1</property></producer>')
    x.append(f'<producer id="score" in="0" out="{total - 1}"><property name="resource">{escape(str(score))}</property>'
             '<property name="kdenlive:clipname">score</property><property name="video_index">-1</property></producer>')
    x.append('<playlist id="video"><property name="kdenlive:track_name">Shots</property>')
    x += [f'<entry producer="shot_{sid}" in="0" out="{n - 1}"/>' for sid, _, n in rows]
    x.append('</playlist>')
    x.append(f'<playlist id="music"><property name="kdenlive:track_name">Score</property>'
             f'<property name="kdenlive:audio_track">1</property><entry producer="score" in="0" out="{total - 1}"/>'
             '</playlist>')
    x.append(f'<playlist id="voices"><property name="kdenlive:track_name">Voices</property>'
             f'<property name="kdenlive:audio_track">1</property><blank length="{total}"/></playlist>')
    x.append(f'<tractor id="main" in="0" out="{total - 1}"><track producer="video"/><track producer="music" '
             'hide="video"/><track producer="voices" hide="video"/>'
             '<transition mlt_service="mix" a_track="1" b_track="2"><property name="always_active">1</property>'
             '<property name="sum">1</property></transition></tractor>')
    x.append('</mlt>')
    return "\n".join(x) + "\n", total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = shots()
    text, total = mlt(rows, ROOT / "data/drawn/score.mp3")
    (OUT / "sand-to-chip.mlt").write_text(text)
    lines = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
    (OUT / "voice.srt").write_text(srt(lines))
    print(OUT / "sand-to-chip.mlt", f"{len(rows)} shots, {total} frames ({total / FPS:.1f} s), {len(lines)} voice lines")


if __name__ == "__main__":
    main()
