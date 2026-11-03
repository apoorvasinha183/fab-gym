"""The drawn film's score (docs/DRAWN-FILM.md): Muse Spark spots the film and writes Grain's theme, our code sets each
cue's tempo so its bars fill its place and its hits land, Muse Spark composes every part, our checks send back what is
wrong, and MuseScore prints and plays the whole film's score.

    python3 -m viz.drawn.music spot      film/drawn/score/spotting.json
    python3 -m viz.drawn.music compose   film/drawn/score/<cue>.json, each checked
    python3 -m viz.drawn.music render    film/drawn/score/sand-to-chip.musicxml; data/drawn/score.pdf and score.mp3
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from . import meta, score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "film/drawn/score"
DATA = ROOT / "data/drawn"
SHOTS = ROOT / "film/drawn/shots.json"
MSCORE = Path.home() / "Applications/MuseScore 4.app/Contents/MacOS/mscore"
SYMPHONY = ["Piccolo", "Flute", "Oboe", "Clarinet in B♭", "Bassoon", "Horn in F", "Trumpet in B♭", "Trombone", "Tuba",
            "Timpani", "Glockenspiel", "Xylophone", "Celesta", "Harp", "Violin I", "Violin II", "Viola", "Violoncello", "Contrabass"]
FORMAT = ('Notes are [pitch, beats] at concert pitch: "D5" or "C#4" or "Bb3"; "r" is a rest; "C4+E4+G4" is a chord; '
          'beats are quarter notes (1 = a quarter, 0.5 = an eighth, 1.5 = a dotted quarter, 4 = a whole note).')


def client():
    return meta.Client(ledger=DATA / "ledger.jsonl", cache=DATA / "cache", cap_usd=25.0)


def _json(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def ask_json(cl, messages, what, max_tokens, repairs=2):
    """Spark's answer as JSON; a broken answer goes back once or twice with the parser's complaint."""
    messages = list(messages)
    for k in range(repairs + 1):
        text = cl.chat(messages, what + (f" (repair {k})" if k else ""), effort="low", max_tokens=max_tokens)
        try:
            return _json(text), messages + [{"role": "assistant", "content": text}]
        except (ValueError, AttributeError) as e:
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"That was not valid JSON ({e}). Send the whole answer again as "
                                                     "valid JSON only, nothing else."}]
    raise RuntimeError(f"{what}: no valid JSON after {repairs} repairs")


def spot():
    shots = json.loads(SHOTS.read_text())["shots"]
    brief = [{k: s.get(k) for k in ("id", "scene", "start", "end", "action", "grain", "camera")} for s in shots]
    total = float(shots[-1]["end"])
    old = OUT / "v1/spotting.json" if (OUT / "v1/spotting.json").exists() else OUT / "spotting.json"
    keep = (" Keep Grain's theme exactly as it is, so the re-timed score is the same film's: " +
            json.dumps(json.loads(old.read_text())["theme"]) + ".") if old.exists() else ""
    shape = {"theme": {"key": "D major", "meter": [4, 4], "notes": [["D5", 1], ["F#5", 0.5]]},
             "cues": [{"cue": "c01", "title": "The grain", "from": 0.0, "to": 8.0, "mood": "...", "key": "D major",
                       "meter": [4, 4], "instruments": ["Celesta", "Violin I"], "hits": [{"t": 4.0, "what": "lattice glows"}],
                       "arc": "how the music moves through the cue"}]}
    prompt = (
        f"You are the composer of a short hand-drawn animated film, 'Sand to Chip' ({total:.0f} s): a grain of sand called Grain "
        "travels from a quarry, through a furnace, purification, crystal growing, slicing, a chip factory and testing, "
        "into a phone that wakes up; it becomes the wafer coach in the factory. Score it for a full symphony orchestra "
        "in the classic style of hand-drawn feature films: melodic, warm, and catching the big moments of the picture.\n\n"
        "1. Write Grain's theme: a memorable melody of 4 bars, in the JSON note format below, to be reused and varied in "
        f"every cue.{keep}\n2. Spot the film into 8 to 14 cues that run back to back from 0 to {total:.0f} seconds, each starting and "
        "ending on a shot boundary. For each: a title, from and to (seconds), mood, key, meter ([4,4], [3,4] or [6,8]), "
        "the instruments it uses (choose from " + json.dumps(SYMPHONY) + "; across the film use every family: strings, "
        "woodwinds, brass, percussion and harp), 2 to 4 hit points (seconds on the film, at the moments the picture "
        "most needs the music to land: a flare, a grab, a rise, a reveal), and the arc of the music. " + FORMAT +
        "\nAnswer with JSON only, in this shape: " + json.dumps(shape) + "\n\nThe shots:\n" + json.dumps(brief))
    c = client()
    d, _ = ask_json(c, [{"role": "user", "content": prompt}], "spotting the drawn film", 12000)
    # set each cue's tempo so its bars fill its place and its hits land (M6)
    for cue in d["cues"]:
        cue["moments"] = cue.pop("hits", [])               # [{"t": seconds on the film, "what": ...}]
        hits = [float(h["t"]) for h in cue["moments"]]
        cue.update(score.plan_cue(float(cue["from"]), float(cue["to"]), hits, cue.get("meter", [4, 4])))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "spotting.json").write_text(json.dumps(d, indent=1))
    errs = []
    t = 0.0
    for cue in d["cues"]:
        if abs(float(cue["from"]) - t) > 0.05:
            errs.append(f"{cue['cue']} starts at {cue['from']}, expected {t}")
        t = float(cue["to"])
        grid = cue["tempo"] * (2 if cue["half_beats"] else 1)        # half beats: a beat grid twice as fast
        errs += [f"{cue['cue']}: {e}" for e in score.check_hits(float(cue["from"]), [float(h["t"]) for h in cue["moments"]], grid)]
    if abs(t - total) > 0.05:
        errs.append(f"the cues end at {t}")
    missing = score.families_missing([i for c in d["cues"] for i in c["instruments"]])
    if missing:
        errs.append(f"no part for {missing}")
    print(len(d["cues"]), "cues;", errs or "no problems", f"spent ${c.spent():.4f}")
    return d


def compose_one(c, spotting, shots, tries=3):
    c = dict(c, instruments=[score.canon(i) for i in c["instruments"]])
    bpb = score.beats_per_bar(c.get("meter", [4, 4]))
    beats = c["bars"] * bpb
    inside = [{k: s.get(k) for k in ("id", "start", "end", "action")} for s in shots
              if float(s["start"]) < float(c["to"]) and float(s["end"]) > float(c["from"])]
    ranges = {i: [score.name(score.RANGES[i][0]), score.name(score.RANGES[i][1])] for i in c["instruments"]}
    prompt = (
        f"Compose cue '{c['title']}' of the film 'Sand to Chip' for these instruments: {json.dumps(c['instruments'])}.\n"
        f"Key {c['key']}, meter {c['meter']}, tempo {c['tempo']} quarter notes a minute, exactly {c['bars']} bars, so every "
        f"part adds up to exactly {beats:g} beats. Mood: {c['mood']}. Arc: {c.get('arc', '')}.\n"
        f"Hit points the music must land on: "
        f"{json.dumps([{'bar': b, 'beat': bt, 'what': m.get('what')} for (b, bt), m in zip(c['hits'], c['moments'])])}.\n"
        f"What happens on screen: {json.dumps(inside)}.\n"
        f"Grain's theme, to quote or vary: {json.dumps(spotting['theme'])}.\n"
        f"Each instrument's concert range: {json.dumps(ranges)}. {FORMAT}\n"
        "Write it like a film composer for a full symphony orchestra: a clear melody, real counterlines and harmony, the "
        "brass and percussion saved for the hits. Answer with JSON only: {\"parts\": {\"Instrument\": [[pitch, beats], ...]}}.")
    cl = client()
    messages = [{"role": "user", "content": prompt}]
    for k in range(tries):
        d, messages = ask_json(cl, messages, f"composing {c['cue']} (try {k + 1})", 16000)
        full = dict(c, parts={score.canon(k): v for k, v in d.get("parts", {}).items()})
        errs = score.check(full) if full["parts"] else ["no parts in the answer"]
        if not errs:
            return full, k + 1
        messages += [{"role": "user", "content": "These problems were found; fix them and send the whole cue again as JSON "
                                                 "only:\n" + "\n".join(errs[:40])}]
    raise RuntimeError(f"{c['cue']}: still wrong after {tries} tries: {errs[:5]}")


def compose():
    spotting = json.loads((OUT / "spotting.json").read_text())
    shots = json.loads(SHOTS.read_text())["shots"]
    for c in spotting["cues"]:
        p = OUT / f"{c['cue']}.json"
        if p.exists():
            continue
        full, tries = compose_one(c, spotting, shots)
        p.write_text(json.dumps(full, indent=1))
        print(c["cue"], c["title"], f"{c['bars']} bars at {c['tempo']}", f"{tries} tries", f"spent ${client().spent():.4f}")


def render():
    spotting = json.loads((OUT / "spotting.json").read_text())
    cues = [json.loads((OUT / f"{c['cue']}.json").read_text()) for c in spotting["cues"]]
    xml = score.film_musicxml(cues)
    mx = OUT / "sand-to-chip.musicxml"
    mx.write_text(xml)
    for ext in ("pdf", "mp3"):
        subprocess.run(["nice", str(MSCORE), "-o", str(DATA / f"score.{ext}"), str(mx)], capture_output=True)
    print(mx, DATA / "score.pdf", DATA / "score.mp3")


if __name__ == "__main__":
    {"spot": spot, "compose": compose, "render": render}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
