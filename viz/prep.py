"""Turn the campus (results/layout/layout.json) and a recorded run window
(data/layout/trace-PLAN.json) into one scene file for the Godot and Blender views.

A gigafab-style layout of our own design on the SMT2020 model; not a real fab. The support
buildings (central utility building, ultrapure water, gas yard, office) are drawn only, at
assumed places. Lots are drawn larger than life so they show at campus scale.

World axes: x east, y north, z up, in metres. Times stay in fab minutes.

    python3 viz/prep.py [--plan optimised] [--out data/layout/scene-optimised.json]
    python3 viz/prep.py --real     the realistic campus at true size (viz/look/scene.py)
"""

import argparse
import json
import math
from pathlib import Path

RAIL_Z = 7.0  # interbay and intrabay hoist track height (assumed)
FOUP = 1.2  # a lot's drawn size, larger than life
STACK_COLS = 3
HOIST_MIN = 0.6  # minutes the hoist takes to lift or lower a lot (drawn only)
HOP_MIN = 1.0  # minutes for the short hop from the queue to the tool (drawn only)

AREA_COLOURS = {
    "Litho": "#f2c94c",
    "Litho_Met": "#f2994a",
    "Def_Met": "#ff8fab",
    "TF_Met": "#bb6bd9",
    "Dry_Etch": "#2d9cdb",
    "Wet_Etch": "#56ccf2",
    "Diffusion": "#ff7a59",
    "Dielectric": "#6fcf97",
    "TF": "#9b51e0",
    "Planar": "#27ae60",
    "Implant": "#b08968",
}
TOOL_HEIGHT = {"Litho": 3.2, "Implant": 3.0, "Diffusion": 4.0, "Wet_Etch": 2.2}


def area_name(a):
    return {
        "Litho": "Lithography",
        "Litho_Met": "Litho metrology",
        "Def_Met": "Defect metrology",
        "TF_Met": "Film metrology",
        "Dry_Etch": "Dry etch",
        "Wet_Etch": "Wet etch and clean",
        "Diffusion": "Diffusion furnaces",
        "Dielectric": "Dielectric deposition",
        "TF": "Thin film (metal)",
        "Planar": "CMP",
        "Implant": "Implant and epitaxy",
    }.get(a, a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="optimised")
    ap.add_argument("--layout", default="results/layout/layout.json")
    ap.add_argument("--trace", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--copy", default=None, help="also write the scene here (the Godot project's data folder)")
    ap.add_argument("--real", action="store_true", help="the realistic campus at true size (docs/FAB-LOOK.md)")
    a = ap.parse_args()
    if a.real:
        return real(a)
    lay = json.load(open(a.layout))
    tr = json.load(open(a.trace or f"data/layout/trace-{a.plan}.json"))
    plan = lay["plans"][a.plan]
    asm = lay["assumed"]
    spine, depth, bridge = asm["spine"], asm["bay_depth"], asm["bridge"]
    offsets = tr["offsets"]
    lengths = plan["lengths"]
    assert [round(x, 2) for x in lengths] == [round(x, 2) for x in tr["lengths"]], "trace and layout differ"
    groups = lay["groups"]

    def world(phase, side, x, y):
        d = spine / 2 + y
        return (offsets[phase] + x, d if side == 0 else -d)

    half = spine / 2 + depth
    buildings = []
    for ph, L in enumerate(lengths):
        buildings.append(
            {"name": f"P{ph + 1}", "label": ["Phase 1: front end", "Phase 2: back end (copper)"][ph] if ph < 2 else f"Phase {ph + 1}",
             "kind": "fab", "x0": offsets[ph] - 4, "x1": offsets[ph] + L + 4, "y0": -half - 4, "y1": half + 4, "h": 34.0}
        )
    p3x = offsets[-1] + lengths[-1] + bridge
    buildings.append({"name": "P3", "label": "Phase 3: pad for the next phase", "kind": "pad", "x0": p3x, "x1": p3x + lengths[-1], "y0": -half, "y1": half, "h": 0.3})
    east = offsets[-1] + lengths[-1]
    buildings += [
        {"name": "CUB", "label": "Central utility building", "kind": "support", "x0": 0, "x1": east, "y0": -half - 110, "y1": -half - 45, "h": 24.0},
        {"name": "UPW", "label": "Ultrapure water", "kind": "support", "x0": east + 30, "x1": east + 130, "y0": -half - 110, "y1": -half - 45, "h": 14.0},
        {"name": "GAS", "label": "Bulk gas yard", "kind": "gas", "x0": 170, "x1": 300, "y0": half + 45, "y1": half + 95, "h": 18.0},
        {"name": "OFFICE", "label": "Office and fab entry", "kind": "support", "x0": 0, "x1": 120, "y0": half + 45, "y1": half + 95, "h": 22.0},
    ]
    bridges = []
    for ph in range(len(lengths)):
        x0 = offsets[ph] + lengths[ph]
        bridges.append({"x0": x0, "x1": x0 + bridge, "y": 0.0, "z": RAIL_Z + 3, "label": "OHT bridge"})

    bays = []
    for b in plan["bays"]:
        x0, y0 = world(b["phase"], b["side"], b["x0"], 0)
        x1, y1 = world(b["phase"], b["side"], b["x1"], depth)
        bays.append({"area": b["area"], "x0": x0, "x1": x1, "y0": min(y0, y1), "y1": max(y0, y1), "side": b["side"], "phase": b["phase"]})

    # area labels over each run of bays of one area on one side
    labels = []
    run = None
    for b in bays + [None]:
        if run and b and b["area"] == run["area"] and b["side"] == run["side"] and b["phase"] == run["phase"] and abs(b["x0"] - run["x1"]) < 1e-6:
            run["x1"] = b["x1"]
            continue
        if run:
            labels.append({"text": area_name(run["area"]), "x": (run["x0"] + run["x1"]) / 2, "y": (run["y0"] + run["y1"]) / 2, "area": run["area"]})
        run = dict(b) if b else None

    tools = []
    for t in plan["tools"]:
        g, ph, side, bay, x0, x1, y0, y1 = t
        wx0, wy0 = world(ph, side, x0, y0)
        wx1, wy1 = world(ph, side, x1, y1)
        area = groups[g]["area"]
        tools.append({"g": g, "x0": wx0, "x1": wx1, "y0": min(wy0, wy1), "y1": max(wy0, wy1), "h": TOOL_HEIGHT.get(area, 2.6), "bay": bay})

    rails = []
    for ph, L in enumerate(lengths):
        rails.append([[offsets[ph], 0, RAIL_Z], [offsets[ph] + L, 0, RAIL_Z]])
        if ph + 1 < len(lengths):
            rails.append([[offsets[ph] + L, 0, RAIL_Z], [offsets[ph + 1], 0, RAIL_Z]])
    bay_x = []
    for b in bays:
        cx = (b["x0"] + b["x1"]) / 2
        bay_x.append(cx)
        sgn = 1 if b["side"] == 0 else -1
        rails.append([[cx, sgn * spine / 2, RAIL_Z], [cx, sgn * (spine / 2 + depth), RAIL_Z]])

    # where each place is: (phase, side, aisle x in the world, y in the world)
    places = plan["places"]

    def place_of_tool(i):
        t = tools[i]
        b = bays[t["bay"]]
        return (b["phase"], b["side"], bay_x[t["bay"]], (t["y0"] + t["y1"]) / 2, (t["x0"] + t["x1"]) / 2)

    def queue_of_group(g):
        ph, side, bay, x, y = places[g]
        if bay < 0:
            bx = offsets[ph] + x
        else:
            bx = bay_x[bay]
        sgn = 1 if side == 0 else -1
        return (ph, side, bx, sgn * (spine / 2 - 1.2), bx)

    def rail_path(a, b):
        """Waypoints at rail height from place a to place b (phase, side, aisle x, y, x)."""
        pa, _, ax, ay, _ = a
        pb, _, bx, by, _ = b
        pts = [(ax, ay), (ax, 0.0)]
        if pa == pb:
            pts.append((bx, 0.0))
        elif pa < pb:
            for ph in range(pa, pb):
                pts += [(offsets[ph] + lengths[ph], 0.0), (offsets[ph + 1], 0.0)]
            pts.append((bx, 0.0))
        else:
            for ph in range(pa, pb, -1):
                pts += [(offsets[ph], 0.0), (offsets[ph - 1] + lengths[ph - 1], 0.0)]
            pts.append((bx, 0.0))
        pts.append((bx, by))
        out = []
        for p in pts:
            if not out or math.dist(out[-1], p) > 1e-6:
                out.append(p)
        return out

    def travel(keys, t0, t1, a_pt, b_pt, a, b, z_a, z_b):
        """Hoist up at a, ride the rails, lower at b, between fab minutes t0 and t1."""
        span = max(t1 - t0, 0.05)
        hoist = min(HOIST_MIN, span / 4)
        path = rail_path(a, b)
        path[0] = (a_pt[0], a_pt[1])
        path[-1] = (b_pt[0], b_pt[1])
        lens = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
        total = sum(lens) or 1.0
        keys.append([t0, a_pt[0], a_pt[1], z_a])
        tt = t0 + hoist
        keys.append([tt, a_pt[0], a_pt[1], RAIL_Z])
        ride = span - 2 * hoist
        for i, L in enumerate(lens):
            tt += ride * L / total
            keys.append([tt, path[i + 1][0], path[i + 1][1], RAIL_Z])
        keys.append([t1, b_pt[0], b_pt[1], z_b])

    stockers = []
    for ph, L in enumerate(lengths):
        n = max(1, int(L // 60))
        stockers += [offsets[ph] + (i + 0.5) * L / n for i in range(n)]

    def nearest_stocker(x):
        return round(min(stockers, key=lambda s: abs(s - x)), 2)

    # queue slots: the lowest free slot at arrival, kept until the lot leaves the queue
    waits = []  # (arrive, leave, key, lot index, step index)
    lots = tr["lots"]
    for li, lot in enumerate(lots):
        prev_tool = lot["prev"][1] if lot["prev"] else None
        for si, st in enumerate(lot["steps"]):
            arrive, start, end, tool, g = st
            if tool < 0:
                # a stocker on the spine, at the aisle the lot came from
                src = None
                if si > 0 and lot["steps"][si - 1][3] >= 0:
                    src = lot["steps"][si - 1][3]
                elif si == 0 and prev_tool is not None and prev_tool >= 0:
                    src = prev_tool
                x = place_of_tool(src)[2] if src is not None else offsets[0] + 10
                key = ("stk", nearest_stocker(x))
                waits.append((arrive, end, key, li, si))
            else:
                waits.append((arrive, start, ("q", g), li, si))
    waits.sort()
    busy = {}
    slot_of = {}
    import heapq

    active = []  # (leave, key, slot)
    for arrive, leave, key, li, si in waits:
        while active and active[0][0] <= arrive:
            _, k, s = heapq.heappop(active)
            busy[k].discard(s)
        used = busy.setdefault(key, set())
        s = 0
        while s in used:
            s += 1
        used.add(s)
        slot_of[(li, si)] = (key, s)
        heapq.heappush(active, (leave, key, s))

    def stack_point(key, s):
        """Waiting lots stand in towers: queues at the bay's mouth, stockers on the spine's middle."""
        col, row, layer = s % 8, (s // 8) % 2, s // 16
        if key[0] == "stk":
            return (key[1] - 4.9 + col * 1.4, -0.65 + row * 1.3, 0.6 + layer * (FOUP + 0.1))
        ph, side, bx, y, _ = queue_of_group(key[1])
        sgn = 1 if side == 0 else -1
        return (bx - 4.9 + col * 1.4, sgn * (2.0 + row * 1.3), 0.6 + layer * (FOUP + 0.1))

    out_lots = []
    t_from, t_to = tr["from"], tr["to"]
    start_pt = (offsets[0] + 2.0, 0.0)
    for li, lot in enumerate(lots):
        keys = []
        steps = lot["steps"]
        # where the lot comes from before its first step in the window
        if lot["prev"] and lot["prev"][1] >= 0:
            pt = place_of_tool(lot["prev"][1])
            src = (pt[0], pt[1], pt[2], pt[3], pt[4])
            src_pt = (pt[4], pt[3])
            src_z = tools[lot["prev"][1]]["h"] + FOUP / 2
            t_prev = lot["prev"][0]
        else:
            src = (0, 0, start_pt[0], 0.0, start_pt[0])
            src_pt = start_pt
            src_z = RAIL_Z
            t_prev = steps[0][0] - 5.0
        for si, st in enumerate(steps):
            arrive, start, end, tool, g = st
            key, s = slot_of[(li, si)]
            qx, qy, qz = stack_point(key, s)
            if tool >= 0:
                dst = queue_of_group(g)
            else:
                dst = (src[0], src[1], key[1], 0.0, key[1])
            travel(keys, t_prev, arrive, src_pt, (qx, qy), src, dst, src_z, qz)
            if tool >= 0:
                tp = place_of_tool(tool)
                tz = tools[tool]["h"] + FOUP / 2
                hop = min(HOP_MIN, max((end - start) / 4, 0.05))
                keys.append([start, qx, qy, qz])
                keys.append([start + hop, tp[4], tp[3], tz])
                keys.append([end, tp[4], tp[3], tz])
                src, src_pt, src_z = tp, (tp[4], tp[3]), tz
            else:
                keys.append([end, qx, qy, qz])
                src, src_pt, src_z = dst, (qx, qy), qz
            t_prev = end
        # after its last step in the window the lot is lifted away
        last = keys[-1]
        keys.append([last[0] + HOIST_MIN, last[1], last[2], RAIL_Z])
        keys = [[round(k[0], 2), round(k[1], 2), round(k[2], 2), round(k[3], 2)] for k in keys]
        # keep only what touches the window
        if keys[-1][0] < t_from or keys[0][0] > t_to:
            continue
        out_lots.append({"id": lot["id"], "hot": lot["hot"], "k": keys})

    scene = {
        "model": "SMT2020",
        "what": "A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. Support buildings drawn only; lots drawn larger than life.",
        "plan": a.plan,
        "from": t_from,
        "to": t_to,
        "metres_per_day": plan["metres_per_day"],
        "spine": spine,
        "depth": depth,
        "rail_z": RAIL_Z,
        "foup": FOUP,
        "areas": {k: {"colour": v, "name": area_name(k)} for k, v in AREA_COLOURS.items()},
        "groups": [{"name": g["name"], "area": g["area"], "phase": g["phase"]} for g in groups],
        "buildings": buildings,
        "bridges": bridges,
        "bays": bays,
        "labels": labels,
        "tools": tools,
        "rails": rails,
        "stockers": stockers,
        "states": tr["states"],
        "lots": out_lots,
    }
    out = Path(a.out or f"data/layout/scene-{a.plan}.json")
    out.write_text(json.dumps(scene, separators=(",", ":")))
    if a.copy:
        Path(a.copy).parent.mkdir(parents=True, exist_ok=True)
        Path(a.copy).write_text(out.read_text())
    nk = sum(len(l["k"]) for l in out_lots)
    print(f"wrote {out}: {len(tools)} tools, {len(bays)} bays, {len(out_lots)} lots, {nk} keys, {out.stat().st_size // 1024} KB")


def real(a):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent / "look"))
    import scene as real_scene

    lay = a.layout if a.layout != "results/layout/layout.json" else "results/layout-real/layout.json"
    tr = a.trace or f"data/layout-real/trace-{a.plan}.json"
    s = real_scene.build(lay, tr, a.plan)
    out = Path(a.out or f"data/layout-real/scene-{a.plan}.json")
    out.write_text(json.dumps(s, separators=(",", ":")))
    if a.copy:
        Path(a.copy).parent.mkdir(parents=True, exist_ok=True)
        Path(a.copy).write_text(out.read_text())
    nk = sum(len(l["k"]) for l in s["lots"])
    print(f"wrote {out}: {len(s['tools'])} tools, {len(s['bays'])} bays, {len(s['lots'])} lots, {nk} keys, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
