"""The drawn film's voice-over (docs/DRAWN-FILM.md, V1 to V3): each line sits inside its shot at a speaking pace, the
narrator's numbers are the script's, and Grain and Lou say little."""

import re

PACE = {"narrator": 2.8, "grain": 3.2, "lou": 3.2}       # words a second, at most (assumed comfortable)


def check(lines, shots):
    by = {s["id"]: s for s in shots}
    errs = []
    for ln in lines:
        s = by.get(str(ln["shot"]))
        if not s:
            errs.append(f"line {ln['text'][:40]!r}: no shot {ln['shot']}")
            continue
        a, b = float(ln["from"]), float(ln["to"])
        if b <= a:
            errs.append(f"line {ln['text'][:40]!r} ends before it starts")
            continue
        if a < float(s["start"]) - 0.01 or b > float(s["end"]) + 0.01:
            errs.append(f"line {ln['text'][:40]!r} runs outside shot {s['id']} ({s['start']} to {s['end']} s)")
        n = len(ln["text"].split())
        pace = PACE.get(ln["who"], 2.8)
        if n / (b - a) > pace:
            errs.append(f"line {ln['text'][:40]!r}: {n / (b - a):.1f} words a second, over {pace}")
    return errs


def numbers_not_in_script(texts, script):
    flat = script.replace(" ", " ")
    out = []
    for t in texts:
        for num in re.findall(r"\d[\d,]*(?:\.\d+)?", t):
            num = num.rstrip(",.")
            if num not in flat:
                out.append(num)
    return out


def cast_limits(lines):
    errs = []
    grain = [ln for ln in lines if ln["who"] == "grain"]
    lou = [ln for ln in lines if ln["who"] == "lou"]
    if len(grain) > 8:
        errs.append(f"Grain has {len(grain)} lines, at most 8")
    for ln in grain:
        if len(ln["text"].split()) > 8:
            errs.append(f"Grain's line {ln['text'][:40]!r} is over 8 words")
    if not 1 <= len(lou) <= 2:
        errs.append(f"Lou has {len(lou)} lines, 1 or 2 wanted")
    return errs


# ------------------------------------------------------------------ writing the script with Muse Spark

def write(tries=3):
    import json
    from pathlib import Path
    from . import music
    root = Path(__file__).resolve().parents[2]
    shots = json.loads((root / "film/drawn/shots.json").read_text())["shots"]
    script = (root / "docs/CHIP-FILM.md").read_text()
    brief = [{k: s.get(k) for k in ("id", "scene", "start", "end", "action", "grain", "caption")} for s in shots]
    shape = {"lines": [{"shot": "2-3", "who": "grain", "text": "Hey! Those are my twins!", "from": 27.2, "to": 28.6,
                        "note": "outraged, small voice"}]}
    prompt = (
        "Write the voice-over script for the hand-drawn animated short 'Sand to Chip' (164 s). Voices: a warm narrator "
        "who carries the science; Grain, a grain of sand (later the wafer coach), who says at most 8 short lines of at "
        "most 8 words each across the film, reacting in the moment; Lou Latency, a robot CEO, who has 1 or 2 lines at the "
        "fab door in scene 6. Each shot's 'caption' is the current narration for that shot: keep its meaning and its "
        "facts, keep its numbers exactly, and use no number that is not in it. Every line sits inside its shot (from and "
        "to are seconds on the film); the narrator speaks at most 2.8 words a second, Grain and Lou 3.2. Leave room: "
        "not every shot needs words. Give each line an acting note. End with Grain's last line paying off the film's "
        "first: the grain of sand is thinking. Answer with JSON only, in this shape: " + json.dumps(shape)
        + "\n\nThe shots:\n" + json.dumps(brief))
    cl = music.client()
    messages = [{"role": "user", "content": prompt}]
    for k in range(tries):
        d, messages = music.ask_json(cl, messages, f"voice-over script (try {k + 1})", 12000)
        lines = d.get("lines", [])
        errs = check(lines, shots) + cast_limits(lines)
        errs += [f"the number {n} is not in the script" for n in
                 numbers_not_in_script([ln["text"] for ln in lines if ln["who"] == "narrator"], script)]
        if not errs:
            break
        messages += [{"role": "user", "content": "Fix these and send the whole script again as JSON only:\n" + "\n".join(errs[:40])}]
    out = root / "film/drawn/voice.json"
    out.write_text(json.dumps({"about": "The drawn film's voice-over, written by Muse Spark from docs/CHIP-FILM.md and "
                                        "the shot list; checked by viz/drawn/voice.py (V1 to V3).", "lines": lines}, indent=1))
    who = {"narrator": "NARRATOR", "grain": "GRAIN", "lou": "LOU LATENCY"}
    md = ["# Sand to Chip: voice-over script", "",
          "For the voice actors. Times are seconds on the film; each line must fit between them. Written by Muse Spark "
          "from the film's script and checked by our code (pace, timing, numbers, cast limits).", "",
          "| Shot | From | To | Who | Line | How |", "| --- | --- | --- | --- | --- | --- |"]
    for ln in sorted(lines, key=lambda x: float(x["from"])):
        md.append(f"| {ln['shot']} | {float(ln['from']):.1f} | {float(ln['to']):.1f} | {who.get(ln['who'], ln['who'])} | "
                  f"{ln['text']} | {ln.get('note', '')} |")
    (root / "film/drawn/VOICE-SCRIPT.md").write_text("\n".join(md) + "\n")
    print(len(lines), "lines;", errs or "no problems", f"spent ${cl.spent():.4f}")
    return lines, errs


if __name__ == "__main__":
    write()
