"""The film's lot, captions and beats, from the re-packed run (docs/FAB-FILM-SCRIPT.md).

A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. The script fixes
the words; this fills its numbers from the run and chooses the lot by the script's rule.

    python3 viz/film/film.py [TRACE] [SCENE] [OUT]    writes data/layout-real/film.json
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "viz" / "look"))
import kit  # noqa: E402

SHOTS = json.loads((Path(__file__).resolve().parent / "shots.json").read_text())
MEASURE = ("metrology", "inspection")
STEP_NAME = {
    "track": "coat and develop", "scanner": "exposure", "metrology": "metrology", "inspection": "inspection",
    "etch": "dry etch", "deposition": "deposition", "epitaxy": "epitaxy", "furnace": "the furnaces",
    "implanter": "implant", "polisher": "polishing", "wet_bench": "wet etch", "stocker": "a timed hold",
}
VERB = {"metrology": "measured", "inspection": "inspected", "etch": "etched", "deposition": "coated",
        "polisher": "polished", "implanter": "implanted", "furnace": "baked", "wet_bench": "cleaned"}
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def kind_of_group(scene, g):
    return kit.kind_of(scene["groups"][g]["name"]) or "stocker"


def clip(trace, lot):
    return [x for x in lot["steps"] if x[0] >= trace["from"] - 30]


def shape(trace, scene, lot):
    """The script's shape, if the lot has it: after wet etch, the track, the scanner, one or more
    checks, etch, then a wait of over an hour at the next step. Returns the steps of that story."""
    prev = lot.get("prev")
    if not prev or prev[1] < 0 or scene["tools"][prev[1]]["kind"] != "wet_bench":
        return None
    st = clip(trace, lot)
    ks = [kind_of_group(scene, x[4]) for x in st]
    if len(ks) < 5 or ks[0] != "track" or ks[1] != "scanner":
        return None
    i = 2
    while i < len(ks) and ks[i] in MEASURE:
        i += 1
    if i == 2 or i >= len(ks) or ks[i] != "etch" or i + 1 >= len(st):
        return None
    last = st[i + 1]
    if last[1] - last[0] <= 60:
        return None
    return st[: i + 2]


def choose_lot(trace, scene):
    """The lot whose clip tells the script's story; among those, three beats after the scanner
    (two checks and etch) first, then the longest final wait, then the first id."""
    best = None
    for lot in trace["lots"]:
        story = shape(trace, scene, lot)
        if story is None:
            continue
        beats = len(story) - 3
        key = (abs(beats - 3), -(story[-1][1] - story[-1][0]), lot["id"])
        if best is None or key < best[0]:
            best = (key, lot)
    if best is None:
        raise SystemExit("no lot in the run tells the script's story")
    return best[1]


def lot_name(lot):
    return "Lot " + lot["id"].rsplit("_", 1)[-1]


def dur(m):
    m = int(round(m))
    h, r = divmod(m, 60)
    if h == 0:
        return f"{r} minutes"
    hs = f"{h} hour" + ("s" if h > 1 else "")
    return hs if r == 0 else f"{hs} {r} minutes"


def about(m):
    """Minutes as a spoken length: 'almost three hours', 'just over two hours', '26 minutes'."""
    if m < 90:
        return f"{int(round(m))} minutes"
    h = round(m / 60)
    if m < 60 * h - 0.5:
        return f"almost {WORDS.get(h, h)} hours"
    if m <= 60 * h + 5:
        return f"{WORDS.get(h, h)} hours"
    return f"just over {WORDS.get(h, h)} hours"


def phase_of(scene, g):
    return scene["groups"][g]["phase"]


def ride(scene, a_g, b_g, purpose, where="track"):
    pa, pb = (phase_of(scene, a_g), phase_of(scene, b_g))
    if pa != pb:
        return f"Across the bridge to Phase {pb + 1} for {purpose}."
    return f"Along Phase {pb + 1}'s spine to the {where} for {purpose}."


def fab_shares(trace):
    """Shares of lot time in the clip's hours: waiting for a tool, on a tool or a timed hold, moving."""
    a, b = trace["from"], trace["to"]
    tot = {"wait": 0.0, "tool": 0.0, "move": 0.0}

    def add(k, t0, t1):
        tot[k] += max(0.0, min(t1, b) - max(t0, a))

    for lot in trace["lots"]:
        t_prev = lot["prev"][0] if lot["prev"] else None
        for arrive, start, end, tool, g in lot["steps"]:
            if t_prev is not None:
                add("move", t_prev, arrive)
            add("wait", arrive, start)
            add("tool", start, end)
            t_prev = end
    s = sum(tot.values())
    return {k: v / s for k, v in tot.items()}


def layout_result():
    lay = json.loads((ROOT / "results/layout-real/layout.json").read_text())
    p = lay["plans"]
    cut = 1 - p["optimised"]["metres_per_day"] / p["plain"]["metres_per_day"]
    sc = json.loads((ROOT / "results/layout-real/score.json").read_text())
    ct = next(m for m in sc["measures"] if m["name"].startswith("cycle time"))
    return cut, ct


def captions(trace, scene, lot):
    story = shape(trace, scene, lot)
    prev_end = lot["prev"][0]
    ends = [prev_end] + [x[2] for x in story]
    moved = [x[0] - e for x, e in zip(story, ends)]
    waited = [x[1] - x[0] for x in story]
    on = [x[2] - x[1] for x in story]
    tr_, sc_ = story[0], story[1]
    checks, etch, last = story[2:-2], story[-2], story[-1]
    prev_g = scene["tools"][lot["prev"][1]]["g"]
    n_tools = len(scene["tools"])

    c = {}
    c["1"] = ["A wafer fab campus of our own design, run from the SMT2020 testbed."]
    c["2"] = [f"{n_tools:,} tools in two buildings, joined by an overhead hoist."]
    c["3"] = ["Air space: fans push filtered air down.", "Cleanroom.", "Support floor: pumps, chillers, exhaust."]
    c["4"] = ["Each lot is one carrier of wafers."]
    c["5"] = [f"{lot_name(lot)} leaves {STEP_NAME[kind_of_group(scene, prev_g)]}."]
    c["6"] = [f"{ride(scene, prev_g, tr_[4], 'coat and develop')} {int(round(moved[0]))} minutes on the hoist."]
    c["7"] = [f"It waits {int(round(waited[0]))} minutes, then spends {int(round(on[0]))} on the track."]
    to_scan = "Back to Phase 2 for exposure" if phase_of(scene, sc_[4]) != phase_of(scene, tr_[4]) else "Next, exposure"
    if waited[1] < 1:
        c["8"] = [f"{to_scan}: straight onto the scanner for {int(round(on[1]))} minutes."]
    else:
        c["8"] = [f"{to_scan}: {int(round(waited[1]))} minutes waiting, {int(round(on[1]))} on the scanner."]
    beats = checks + [etch]
    verbs = []
    for x in beats:
        v = VERB[kind_of_group(scene, x[4])]
        verbs.append("checked" if v in verbs and v == "measured" else v)
    vs = ", ".join(verbs).capitalize()
    c["9"] = [f"{vs}: {dur(sum(x[2] - x[1] for x in beats))} on {WORDS.get(len(beats), len(beats))} tools."]
    c["10"] = [f"Then it waits. {dur(waited[-1]).capitalize()} in the queue for {STEP_NAME[kind_of_group(scene, last[4])]}."]
    c["11"] = [f"Moving: {int(round(sum(moved)))} minutes. Waiting: {about(sum(waited))}."]
    sh = fab_shares(trace)
    w = sh["wait"]
    wt = "half" if 0.45 <= w <= 0.55 else f"{w:.0%}"
    cut, ct = layout_result()
    ct_words = "Cycle time did not clearly change." if ct["lo"] <= 0 <= ct["hi"] else (
        f"Cycle time fell by {-ct['mean']:.1f} days." if ct["mean"] < 0 else f"Cycle time rose by {ct['mean']:.1f} days.")
    c["12"] = [f"Across the fab, {wt} of lot time was spent waiting for a tool and {sh['move']:.0%} moving.",
               f"Our layout cut hoist travel by {cut:.0%}. {ct_words}"]
    c["13"] = ["Which lot should go next? In Fab Gym, an agent proposes, the simulator scores, a person signs."]
    c["end"] = ["Fab Gym. A gigafab-style layout of our own design on the SMT2020 testbed. Not a real fab."]
    return c


def beats(trace, scene, lot):
    """The lot's story as events in fab minutes, for the camera and the clock."""
    story = shape(trace, scene, lot)
    out = [{"what": "leaves", "t": lot["prev"][0], "tool": lot["prev"][1]}]
    for x in story:
        out.append({"what": STEP_NAME[kind_of_group(scene, x[4])], "kind": kind_of_group(scene, x[4]), "group": scene["groups"][x[4]]["name"],
                    "arrive": x[0], "start": x[1], "end": x[2], "tool": x[3]})
    return out


def timemap(trace, scene, lot):
    """Film seconds to fab minutes, shot by shot: segments (film from, film to, fab from, fab to).
    Between segments the clock jumps (the hard cuts of shot 9)."""
    sh = {x["id"]: x for x in SHOTS["shots"]}
    st = shape(trace, scene, lot)
    leave = lot["prev"][0]
    trk, scn, *mid, last = st
    lift = 0.4  # viz/look/scene.py HOIST_MIN
    seg = []

    def add(shot_from, shot_to, a, b):
        seg.append([shot_from, shot_to, a, b])

    s5 = sh["5"]["start"]
    add(0, s5, leave - 0.3 - s5 / 60.0, leave - 0.3)  # x1 up to the pick-up
    add(s5, sh["5"]["end"], leave - 0.3, leave + lift)
    add(sh["6"]["start"], sh["6"]["end"], leave + lift, trk[0])
    add(sh["7"]["start"], sh["7"]["end"], trk[0], trk[2])
    s8, e8 = sh["8"]["start"], sh["8"]["end"]
    add(s8, s8 + 3, trk[2], scn[0])
    add(s8 + 3, e8, scn[0], scn[2])
    s9, e9 = sh["9"]["start"], sh["9"]["end"]
    beats = mid
    for i, x in enumerate(beats):
        a = s9 + i * (e9 - s9) / len(beats)
        b = s9 + (i + 1) * (e9 - s9) / len(beats)
        add(a, b, x[0], x[2])
    add(sh["10"]["start"], sh["10"]["end"], beats[-1][2], last[1])
    add(sh["11"]["start"], sh["11"]["end"], last[1], last[2])
    add(sh["12"]["start"], sh["end"]["end"], last[2], last[2] + (sh["end"]["end"] - sh["12"]["start"]))  # x60
    return [[round(v, 4) for v in x] for x in seg]


def main():
    tp = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/layout-real/trace-optimised.json"
    sp = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/layout-real/scene-optimised.json"
    op = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "data/layout-real/film.json"
    tr, sc = json.loads(tp.read_text()), json.loads(sp.read_text())
    lot = choose_lot(tr, sc)
    caps = captions(tr, sc, lot)
    out = {"what": "The film's lot and captions, from the SMT2020 testbed; a gigafab-style layout of our own design.",
           "lot": lot["id"], "name": lot_name(lot), "beats": beats(tr, sc, lot), "captions": caps,
           "shares": fab_shares(tr), "timemap": timemap(tr, sc, lot), "shots": SHOTS["shots"]}
    op.write_text(json.dumps(out, indent=1))
    print(f"{lot['id']} ({lot_name(lot)})")
    for s in SHOTS["shots"]:
        for t in caps[s["id"]]:
            n = len(t.split())
            flag = "" if n / 3 <= s["end"] - s["start"] + 0.5 else "  <-- too long"
            print(f"  {s['id']:>3}  {t}{flag}")


if __name__ == "__main__":
    main()
