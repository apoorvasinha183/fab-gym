"""Turn a playtest log into faults (viz/playtest/README.md). Reads OUT/log.jsonl and OUT/frames.csv written by
res://playtest/playtest.gd and writes OUT/faults.json and OUT/summary.md. Every fault names when it happened, what the
game was doing (the tour's stop) and the nearest still, so a person can look. Standard library only. From the SMT2020
testbed; not a real fab.

    python3 viz/playtest/analyse.py OUT
"""

import csv
import json
import math
import sys
from pathlib import Path

BAR_MS = 16.7          # the 60 fps bar (docs/FAB-3D.md, F8)
READ_CPS = 17.0        # characters a second a visitor can comfortably read (assumed)
CLIP_SPEED = 0.94      # the walk clip's planted-foot speed (guide.gd)


def load(out):
    rows, events = [], []
    for line in (out / "log.jsonl").read_text().splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        (rows if d.get("ev") == "row" else events).append(d)
    frames = []
    with open(out / "frames.csv") as f:
        for r in csv.DictReader(f):
            frames.append((float(r["t"]), float(r["ms"])))
    shots = sorted(p.name for p in (out / "shots").glob("*.jpg"))
    return rows, events, frames, shots


FROZEN = set()


def shot_near(shots, t):
    best, bd = "", 1e9
    for s in shots:
        if s in FROZEN:
            continue
        try:
            st = float(s.split("-")[1])
        except (IndexError, ValueError):
            continue
        if abs(st - t) < bd:
            bd, best = abs(st - t), s
    return best


def runs(rows, pred, min_s=0.4):
    """Spans of consecutive rows where pred holds, at least min_s long: [(t0, t1, first row)]."""
    out, start, first = [], None, None
    for r in rows:
        if pred(r):
            if start is None:
                start, first = r["t"], r
        elif start is not None:
            if r["t"] - start >= min_s:
                out.append((start, r["t"], first))
            start = None
    if start is not None and rows and rows[-1]["t"] - start >= min_s:
        out.append((start, rows[-1]["t"], first))
    return out


def where(r):
    k = r.get("stop_kind", "")
    a = r.get("stop_area", "")
    return f"{k}{' ' + a if a else ''}{' (on the way)' if r.get('stop_via') else ''}; {r.get('stop_label', '')}"


def overlap(a, b):
    if not a or not b:
        return 0.0
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def analyse(out):
    rows, events, frames, shots = load(out)
    faults = []

    def add(sev, kind, t0, t1, what, r=None, **extra):
        faults.append({"severity": sev, "kind": kind, "t0": round(t0, 1), "t1": round(t1, 1), "what": what,
                       "where": where(r) if r else "", "shot": shot_near(shots, (t0 + t1) / 2), **extra})

    # ---------------------------------------------------------------- was the window drawn?
    # macOS stops drawing a window that is out of sight: a still identical to the one before means nothing was drawn
    # between them (the clock on screen always moves), so its frame times and stills mean nothing
    import hashlib
    digests = [(s, hashlib.md5((out / "shots" / s).read_bytes()).hexdigest()) for s in shots]
    frozen = {b[0] for a, b in zip(digests, digests[1:]) if a[1] == b[1]}
    drawn_share = 1.0 - len(frozen) / max(1, len(shots))
    FROZEN.clear()
    FROZEN.update(frozen)

    # ---------------------------------------------------------------- frame time
    # a still is read back from the GPU, which holds that frame and the next: those are the harness's, not the game's
    shot_t = sorted(float(s.split("-")[1]) for s in shots if s.count("-") >= 2)

    def near_shot(t):
        import bisect
        k = bisect.bisect_left(shot_t, t - 0.15)
        return k < len(shot_t) and shot_t[k] <= t + 0.05

    frames = [(t, m) for t, m in frames if not near_shot(t)]
    ms = sorted(m for _, m in frames[30:])
    perf = {}
    if ms:
        perf = {"frames": len(ms), "median_ms": ms[len(ms) // 2], "p99_ms": ms[int(len(ms) * 0.99)], "max_ms": ms[-1],
                "over_bar": sum(1 for m in ms if m > BAR_MS), "over_33": sum(1 for m in ms if m > 33.4)}
        perf["drawn_share"] = round(drawn_share, 3)
        perf["valid"] = drawn_share > 0.97
        if not perf["valid"]:
            add("Polish", "harness", frames[0][0], frames[-1][0], f"the window was not drawn for {100 * (1 - drawn_share):.0f}% "
                "of the stills (hidden or covered): frame times are not valid and those stills are stale")
        if perf["valid"] and perf["p99_ms"] > BAR_MS:
            add("Major", "frame time", frames[0][0], frames[-1][0],
                f"99th-percentile frame {perf['p99_ms']:.1f} ms over the {BAR_MS} ms bar (median {perf['median_ms']:.1f})")
        stalls = [(t, m) for t, m in frames[30:] if m > 100.0]
        for t, m in stalls[:25]:
            r = min(rows, key=lambda x: abs(x["t"] - t)) if rows else None
            add("Major" if m > 250 else "Minor", "stall", t, t, f"a {m:.0f} ms frame (a visible hitch)", r)

    # ---------------------------------------------------------------- the camera
    for t0, t1, r in runs(rows, lambda r: r["cam_in_solid"] != "" and not r.get("film_full")):
        add("Major", "camera inside something", t0, t1, f"the camera is inside {r['cam_in_solid']} for {t1 - t0:.1f} s", r)
    for t0, t1, r in runs(rows, lambda r: not r["fly"] and not r["intro"] and r["cam"][2] - r["cam_floor"] < 0.9):
        add("Major", "camera under the floor", t0, t1,
            f"the camera is {r['cam'][2] - r['cam_floor']:.2f} m over the floor under it", r)
    prev = None
    for r in rows:
        if prev and not r["intro"] and not prev["intro"]:
            jump = math.dist(r["cam"], prev["cam"])
            if jump > 6.0 and r["t"] - prev["t"] < 0.5:
                add("Minor", "camera jump", prev["t"], r["t"], f"the camera jumps {jump:.0f} m in one step (a hard cut)", r)
        prev = r

    # ---------------------------------------------------------------- Lou on screen
    by_stop = {}
    for r in rows:
        if r["lou_mode"] == "talk" and r["touring"] and not r["intro"]:
            key = (r["stop_i"], r["stop_kind"], r["stop_area"])
            s = by_stop.setdefault(key, {"n": 0, "off": 0, "hidden": 0, "far": 0, "r": r})
            s["n"] += 1
            s["off"] += 0 if r["lou_in_frustum"] else 1
            s["hidden"] += 1 if r["lou_hidden_by"] else 0
            s["far"] += 1 if r["lou_dist"] > 15 else 0
    for (i, kind, area), s in by_stop.items():
        r = s["r"]
        if s["off"] / s["n"] > 0.5:
            add("Major", "Lou off screen while talking", r["t"], r["t"] + s["n"] * 0.2,
                f"Lou is out of the frame for {100 * s['off'] / s['n']:.0f}% of his line", r)
        elif s["hidden"] / s["n"] > 0.3:
            add("Major", "Lou hidden while talking", r["t"], r["t"] + s["n"] * 0.2,
                f"something stands between the camera and Lou for {100 * s['hidden'] / s['n']:.0f}% of his line", r)
        elif s["far"] / s["n"] > 0.5:
            add("Minor", "Lou far while talking", r["t"], r["t"] + s["n"] * 0.2,
                f"Lou is more than 15 m from the camera for most of his line", r)
    for t0, t1, r in runs(rows, lambda r: r["lou_mode"] == "walk" and r["follow"] and not r["intro"]
                          and (not r["lou_in_frustum"] or r["lou_hidden_by"] != ""), 2.0):
        add("Minor", "lost sight of Lou", t0, t1, f"following Lou but he is {'hidden by ' + r['lou_hidden_by'] if r['lou_hidden_by'] else 'out of frame'} for {t1 - t0:.1f} s", r)

    # ---------------------------------------------------------------- Lou in the world
    for t0, t1, r in runs(rows, lambda r: r["lou_in_solid"] != "" and r["stop_kind"] != "air_shower", 0.3):
        add("Major", "Lou inside something", t0, t1, f"Lou's body is inside {r['lou_in_solid']}", r)
    # riding the lift he stands still while his height changes: that is not stuck
    for a, b in zip(rows, rows[1:]):
        b["_dz"] = abs(b["lou"][2] - a["lou"][2])
    for t0, t1, r in runs(rows, lambda r: r["lou_mode"] == "walk" and r["lou_v"] < 0.05 and r.get("_dz", 0) < 0.01
                          and r["stop_kind"] not in ("lift",), 3.0):
        add("Major", "Lou stuck", t0, t1, f"Lou is walking but has not moved for {t1 - t0:.1f} s", r)
    for a, b in zip(rows, rows[1:]):
        if a["lou_mode"] == "walk" and b["lou_mode"] == "walk" and "Walk" in a["clip"] and b["t"] > a["t"]:
            v = math.dist(a["lou"][:2], b["lou"][:2]) / (b["t"] - a["t"])
            a["_v"] = v
    for t0, t1, r in runs(rows, lambda r: "_v" in r and r["rate"] > 0.2 and not 0.7 < r["_v"] / (r["rate"] * CLIP_SPEED) < 1.35, 1.0):
        add("Minor", "feet slide", t0, t1, f"Lou moves at {r['_v']:.2f} m/s while his feet step for {r['rate'] * CLIP_SPEED:.2f} m/s", r)

    # ---------------------------------------------------------------- doors
    for t0, t1, r in runs(rows, lambda r: any((d["lou_m"] < 0.7 or d["cam_m"] < 0.7) and d["open"] < 0.7 for d in r["doors"]), 0.2):
        d = next(d for d in r["doors"] if (d["lou_m"] < 0.7 or d["cam_m"] < 0.7) and d["open"] < 0.7)
        add("Major", "door shut in someone's way", t0, t1, f"the {d['door']} is {100 * d['open']:.0f}% open with Lou {d['lou_m']:.1f} m and the camera {d['cam_m']:.1f} m from it", r)

    # ---------------------------------------------------------------- the words on screen
    for t0, t1, r in runs(rows, lambda r: r["line_overflow"] and r["talk_visible"], 0.2):
        add("Major", "line overflows its window", t0, t1, f"the line is taller than the text window (some of it is cut off)", r)
    said = [e for e in events if e["ev"] == "said"]
    for a, b in zip(said, said[1:] + [None]):
        end = b["t"] if b else (rows[-1]["t"] if rows else a["t"])
        # how long the window shows it: until the next line, or until the window closes
        shown = [r for r in rows if a["t"] <= r["t"] < end and r["talk_visible"] and r["talk_alpha"] > 0.5]
        secs = len(shown) * 0.2
        if secs > 0 and a["chars"] / secs > READ_CPS and a["chars"] > 40:
            r = shown[0] if shown else None
            add("Minor", "line too short to read", a["t"], a["t"] + secs,
                f"{a['chars']} characters on screen for {secs:.1f} s ({a['chars'] / secs:.0f} a second): \"{a['text'][:90]}\"", r)
    for e in events:
        if e["ev"] == "said" and len(e["text"]) > 260:
            add("Polish", "long line", e["t"], e["t"], f"a {len(e['text'])}-character line: \"{e['text'][:90]}...\"")

    # ---------------------------------------------------------------- the screen's windows
    pairs = {}
    for r in rows:
        rc = r["rects"]
        names = [k for k in rc if rc[k]]
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                if overlap(rc[x], rc[y]) > 200:
                    pairs.setdefault((x, y), []).append(r)
    for (x, y), rs in pairs.items():
        add("Minor", "windows overlap", rs[0]["t"], rs[-1]["t"], f"the {x} and {y} windows overlap ({len(rs)} samples)", rs[0])
    pchanges = [e["t"] for e in events if e["ev"] == "prompt"]
    k = 0
    while k < len(pchanges):
        j = k
        while j + 1 < len(pchanges) and pchanges[j + 1] - pchanges[k] < 2.0:
            j += 1
        if j - k >= 3:
            r = min(rows, key=lambda x: abs(x["t"] - pchanges[k]))
            add("Minor", "prompt flickers", pchanges[k], pchanges[j], f"the key prompt changes {j - k + 1} times in {pchanges[j] - pchanges[k]:.1f} s", r)
        k = j + 1

    # ---------------------------------------------------------------- nothing happening
    for t0, t1, r in runs(rows, lambda r: r["touring"] and not r["intro"] and r["lou_mode"] != "walk"
                          and not (r["talk_visible"] and r["talk_alpha"] > 0.5) and not r["film_full"], 8.0):
        add("Minor", "dead time", t0, t1, f"{t1 - t0:.0f} s with Lou not walking and nothing said", r)

    # ---------------------------------------------------------------- the scripted visitor's actions
    def after(t, secs, pred):
        return any(pred(r) for r in rows if t < r["t"] <= t + secs)

    checks = {
        "e: sit down": (1.5, lambda r: r["seated"], "did not sit down"),
        "enter: play the film full screen": (1.5, lambda r: r["film_full"] and r["film_started"], "the film did not open full screen"),
        "space: pause": (1.0, lambda r: r["film_paused"], "the film did not pause"),
        "space: resume": (1.0, lambda r: not r["film_paused"], "the film did not resume"),
        "esc: back to the hall": (1.0, lambda r: not r["film_full"] and r["seated"], "did not return to the hall seated"),
        "e: stand up": (1.0, lambda r: not r["seated"], "did not stand up"),
        "menu: walk alone": (1.0, lambda r: not r["touring"], "the tour did not end"),
        "click the nearest tool for its card": (1.5, lambda r: r["card"], "no tool card opened"),
        "esc: close the card": (1.0, lambda r: not r["card"], "the card did not close"),
        "f: fly": (1.0, lambda r: r["fly"], "flying did not start"),
        "f: land": (1.0, lambda r: not r["fly"], "flying did not stop"),
    }
    steps = [e for e in events if e["ev"] == "step"]
    for e in steps:
        c = checks.get(e["name"])
        if c and not after(e["t"], c[0], c[1]):
            r = min(rows, key=lambda x: abs(x["t"] - e["t"]))
            add("Major", "action did nothing", e["t"], e["t"] + c[0], f"\"{e['name']}\": {c[2]}", r)
        if e["name"].startswith("ask:"):
            reply = [s for s in said if e["t"] <= s["t"] <= e["t"] + 8.0]
            if not reply:
                r = min(rows, key=lambda x: abs(x["t"] - e["t"]))
                add("Major", "question unanswered", e["t"], e["t"] + 8, f"\"{e['name'][5:]}\" got no answer in 8 s", r)
    for e in events:
        if e["ev"] == "walk_end" and e["left_m"] > 0.6:
            r = min(rows, key=lambda x: abs(x["t"] - e["t"]))
            add("Minor", "visitor could not get there", e["t"] - e["seconds"], e["t"],
                f"walking with W, the visitor stopped {e['left_m']:.1f} m short after {e['seconds']:.0f} s", r)
    for e in events:
        if e["ev"] == "fault_harness":
            add("Polish", "harness", e["t"], e["t"], e["why"])

    order = {"Blocker": 0, "Major": 1, "Minor": 2, "Polish": 3}
    faults.sort(key=lambda f: (order[f["severity"]], f["t0"]))
    arrived = [e for e in events if e["ev"] == "arrived"]
    summary = {"seconds": rows[-1]["t"] if rows else 0, "stops": len(arrived), "lines": len(said), "perf": perf,
               "faults": len(faults), "by_kind": {}}
    for f in faults:
        summary["by_kind"][f["kind"]] = summary["by_kind"].get(f["kind"], 0) + 1
    (out / "faults.json").write_text(json.dumps({"summary": summary, "faults": faults}, indent=1))
    lines = [f"# Playtest {out.name}", "", f"{summary['seconds']:.0f} s played, {summary['stops']} stops, "
             f"{summary['lines']} lines; {summary['faults']} faults", "", "| Severity | Kind | When | What | Where | Still |",
             "| --- | --- | --- | --- | --- | --- |"]
    for f in faults:
        lines.append(f"| {f['severity']} | {f['kind']} | {f['t0']}-{f['t1']} s | {f['what']} | {f['where']} | {f['shot']} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return summary


if __name__ == "__main__":
    s = analyse(Path(sys.argv[1]))
    print(json.dumps(s, indent=1))
