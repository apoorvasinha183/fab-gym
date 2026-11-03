"""Muse Spark directs each shot (docs/DRAWN-FILM.md): an animation sheet per shot with its plate (painted at the hero's
scale, a reference object of known size named at the hero's spot), each character's drawings (keys, in-betweens,
cycles) with their timing and place, painted effects, and the camera. Our checks send a sheet back if it slides one
drawing, misses the shot's length, or goes over budget.

    python3 -m viz.drawn.direct [SHOT ...]      film/drawn/anim/<shot>.json
"""

import json
import sys
from pathlib import Path

from . import music, scale

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "film/drawn/anim"
SHOTS = ROOT / "film/drawn/shots.json"
SHEETS = ["grain-01-sand", "grain-02-quartz", "grain-03-grey", "grain-04-wisp", "grain-05-crystal", "grain-06-wafer",
          "grain-07-coach", "grain-08-die", "grain-10-packaged", "lou-latency", "carbon-thieves", "specks"]
FPS = 24
BUDGET = 40

SHAPE = {
    "plates": [{"name": "p1", "from": 0, "prompt": "what the background painting shows, with no characters",
                "reference": "a pebble about 3 cm across lying where the hero stands", "reference_m": 0.03}],
    "characters": [{"name": "grain", "sheet": "grain-02-quartz", "height_m": 0.03,
                    "drawings": [{"id": "g1", "kind": "key", "pose": "plain words: body, arms, face"},
                                 {"id": "g2", "kind": "key", "pose": "..."},
                                 {"id": "g1b", "kind": "inbetween", "between": ["g1", "g2"]},
                                 {"id": "w1", "kind": "cycle", "pose": "drawing 1 of a 4-drawing walk cycle, ..."}],
                    "timing": [["g1", 6], ["g1b", 2], ["g2", 8], ["none", 4]],
                    "place": [[0, 0.30, "front"], [47, 0.55, "front"]]}],
    "effects": [{"name": "fire", "prompt": "only flames, nothing else, ...", "drawings": 4, "on": 3,
                 "at": [0.5, 0.45], "height": 0.3}],
    "camera": [[0, {"x": 0, "y": 0, "zoom": 1.0}], [47, {"x": 40, "y": 0, "zoom": 1.08}]]}

RULES = (
    "Rules. It is cel animation: a character that moves changes drawing at least every third frame while it moves; no "
    "single drawing may slide across the screen. Use keys for the big poses, in-betweens (kind 'inbetween', naming the "
    "two drawings either side) to smooth big changes, and cycles (kind 'cycle', drawn in order) for walks, runs and "
    "loops. Hold a drawing when the character is still. 'none' hides a character. Each character's timing must add up "
    f"to exactly the shot's frames ({FPS} a second). At most {BUDGET} drawings in the whole shot, effects included. "
    "'place' keys say where the character's feet are: [frame, x as a share of the width from 0 to 1, ground 'front', "
    "'mid' or 'back']. Sizes must make sense: give each character its real height in metres (Grain's form and size are "
    "fixed by the scene), and paint each plate at the hero's scale, so the hero fills about a third of the frame's height: "
    "for a tiny hero a macro close-up (the camera at the hero's height, the ground's texture large, the big machine only "
    "a blurred shape behind); name a reference object of known size at the hero's spot. Keep pose words plain "
    "and gentle (body, arms, legs, face; no fear, violence, grabbing or hugging words), or the picture model refuses. "
    "Effects are painted cycles of 3 to 6 drawings (only the effect on its own: flames, steam, sparks, light), each "
    "placed once: 'at' is its centre as shares of the width and height, 'height' its size as a share of the frame's "
    "height (never a band across the whole picture); use effects sparingly, the plate is already painted. The "
    "camera moves gently; cut only where the shot list cuts. Characters and their sheets: Grain (its form's sheet); the "
    "oxygen twins exist only with quartz Grain and are drawn inside Grain's own drawings from grain-02-quartz (not a "
    "separate character); carbon thieves from carbon-thieves; specks (dust) from specks; Lou Latency from lou-latency; "
    "sibling dies are drawn inside Grain's die drawings.")

FORM_SIZE = {k: v for k, v in scale.SIZES_M.items()}


def check(a, frames):
    errs = []
    n = sum(len(c.get("drawings", [])) for c in a.get("characters", [])) + sum(int(e.get("drawings", 0)) for e in a.get("effects", []))
    n += len(a.get("plates", []))
    if n > BUDGET + 3:
        errs.append(f"{n} drawings, over the budget of {BUDGET}")
    for c in a.get("characters", []):
        ids = {d["id"] for d in c.get("drawings", [])} | {"none"}
        total = sum(int(t[1]) for t in c.get("timing", []))
        if total != frames:
            errs.append(f"{c['name']}: timing adds up to {total} frames, the shot has {frames}")
        for t in c.get("timing", []):
            if t[0] not in ids:
                errs.append(f"{c['name']}: timing names {t[0]}, which is not one of its drawings")
        for d in c.get("drawings", []):
            if d.get("kind") == "inbetween" and not set(d.get("between", [])) <= ids:
                errs.append(f"{c['name']}: in-between {d['id']} names keys it does not have")
        if c.get("sheet") not in SHEETS:
            errs.append(f"{c['name']}: no model sheet called {c.get('sheet')}")
        # moving on one drawing for more than 3 frames is sliding (D19)
        place = sorted(c.get("place", []), key=lambda p: p[0])
        seq = []
        for name, k in c.get("timing", []):
            seq += [name] * int(k)
        for (f0, x0, g0), (f1, x1, g1) in zip(place, place[1:]):
            if abs(float(x1) - float(x0)) > 0.02 and f1 > f0:
                speed_frames = [seq[f] for f in range(int(f0), min(int(f1), len(seq))) if f < len(seq)]
                run, longest = 1, 1
                for p, q in zip(speed_frames, speed_frames[1:]):
                    run = run + 1 if p == q and p != "none" else 1
                    longest = max(longest, run)
                if longest > 3:
                    errs.append(f"{c['name']}: moves from frame {f0} to {f1} while holding one drawing {longest} frames")
    return errs


def direct(shot, shots, tries=3):
    frames = int(round((float(shot["end"]) - float(shot["start"])) * FPS))
    i = [s["id"] for s in shots].index(shot["id"])
    context = {"before": shots[i - 1]["action"] if i else None, "after": shots[i + 1]["action"] if i + 1 < len(shots) else None}
    lines = [ln for ln in json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"] if ln["shot"] == shot["id"]]
    prompt = (
        "You are the animation director of a hand-drawn (cel) short film, 'Sand to Chip', in Fab Gym's comic style. "
        "Direct this one shot as an animation sheet. The hero is Grain; its model sheets: " + json.dumps(SHEETS) +
        f"; real sizes in metres: {json.dumps(FORM_SIZE)}. The shot: {json.dumps(shot)}; it lasts {frames} frames. "
        f"Around it: {json.dumps(context)}. Lines spoken in it (seconds on the film): {json.dumps(lines)}; a speaking "
        "character's mouth should be open on its lines (give it talking drawings).\n" + RULES +
        "\nAnswer with JSON only, in this shape: " + json.dumps(SHAPE))
    cl = music.client()
    messages = [{"role": "user", "content": prompt}]
    for k in range(tries):
        a, messages = music.ask_json(cl, messages, f"directing shot {shot['id']} (try {k + 1})", 10000)
        errs = check(a, frames)
        if not errs:
            return a, frames
        messages += [{"role": "user", "content": "Fix these and send the whole sheet again as JSON only:\n" + "\n".join(errs[:30])}]
    raise RuntimeError(f"shot {shot['id']}: {errs[:5]}")


def main(ids):
    shots = json.loads(SHOTS.read_text())["shots"]
    OUT.mkdir(parents=True, exist_ok=True)
    for s in shots:
        if ids and s["id"] not in ids:
            continue
        p = OUT / f"{s['id']}.json"
        if p.exists():
            continue
        a, frames = direct(s, shots)
        a.update({"shot": s["id"], "frames": frames, "start": s["start"], "end": s["end"]})
        p.write_text(json.dumps(a, indent=1))
        n = sum(len(c.get("drawings", [])) for c in a["characters"]) + sum(int(e.get("drawings", 0)) for e in a.get("effects", [])) + len(a["plates"])
        print(s["id"], f"{n} drawings", f"spent ${music.client().spent():.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
