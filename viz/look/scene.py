"""The realistic scene: the re-packed campus (results/layout-real/layout.json) and a recorded run
window (data/layout-real/trace-PLAN.json) at true size, for the Blender film and the Godot scene.

A gigafab-style layout of our own design on the SMT2020 model; not a real fab. Tools stand on the
raised floor of the cleanroom at their kind's size (docs/FAB-LOOK.md). Carriers are drawn at true
size and move the way the run moves them: lifted from a load port by a hoist car, carried along
the rails, set down on a shelf beside the rail while they wait, lowered onto a port when a tool
takes them. Where the run says nothing (which port, which shelf, the path along the rails) the
choice is ours and drawn only; the times are the run's.

World axes: x east, y north, z up, in metres from the support floor. Times in fab minutes.

    python3 viz/prep.py --real [--plan optimised]
"""

import heapq
import json
import math
from pathlib import Path

import kit

HOIST_MIN = 0.4   # minutes to lift or lower a carrier (drawn only)
SLIDE_MIN = 0.3   # minutes to move a carrier between a shelf and the rail (drawn only)
DIRECT_MIN = 1.0  # a lot that waits less than this goes straight to its port
SHELF_STEP = 0.45  # vertical pitch of the shelves beside a rail
SHELF_OUT = 0.6   # a shelf's offset from its rail, toward the aisle's middle
INTERBAY_Y = 2.2  # the interbay rails run at y = +-2.2 along the spine
STOCKER_EVERY = 60.0
CROSS_EVERY = 20.0
SHELF_PITCH = 0.5  # along the rail

AREA_NAMES = {
    "Litho": "Lithography", "Litho_Met": "Litho metrology", "Def_Met": "Defect inspection",
    "TF_Met": "Film metrology", "Dry_Etch": "Dry etch", "Wet_Etch": "Wet etch and clean",
    "Diffusion": "Diffusion furnaces", "Dielectric": "Dielectric deposition", "TF": "Thin film (metal)",
    "Planar": "CMP", "Implant": "Implant and epitaxy",
}
AREA_COLOURS = {
    "Litho": "#f2c94c", "Litho_Met": "#f2994a", "Def_Met": "#ff8fab", "TF_Met": "#bb6bd9",
    "Dry_Etch": "#2d9cdb", "Wet_Etch": "#56ccf2", "Diffusion": "#ff7a59", "Dielectric": "#6fcf97",
    "TF": "#9b51e0", "Planar": "#27ae60", "Implant": "#b08968",
}


def rot(yaw_deg, u, v):
    a = math.radians(yaw_deg)
    return (u * math.cos(a) - v * math.sin(a), u * math.sin(a) + v * math.cos(a))


def build(layout_path, trace_path, plan_name):
    lay = json.loads(Path(layout_path).read_text())
    tr = json.loads(Path(trace_path).read_text())
    plan = lay["plans"][plan_name]
    asm = lay["assumed"]
    spine, depth, bridge, aisle = asm["spine"], asm["bay_depth"], asm["bridge"], asm["bay_aisle"]
    offsets, lengths = tr["offsets"], plan["lengths"]
    assert [round(x, 2) for x in lengths] == [round(x, 2) for x in tr["lengths"]], "trace and layout differ"
    groups = lay["groups"]
    S = kit.SIZES
    CZ = kit.clean_floor_z()
    PORT_Z = CZ + S["port_seat"]
    RAIL_Z = CZ + S["rail_underside"]
    RIDE_Z = RAIL_Z - S["vehicle"]["h"] - S["carrier"]["h"]
    c = S["carrier"]

    def wy(side, y):
        d = spine / 2 + y
        return d if side == 0 else -d

    # ---------------------------------------------------------------- bays and their rails
    bays = []
    for b in plan["bays"]:
        x0, x1 = offsets[b["phase"]] + b["x0"], offsets[b["phase"]] + b["x1"]
        y0, y1 = sorted((wy(b["side"], 0), wy(b["side"], depth)))
        bays.append({"area": b["area"], "phase": b["phase"], "side": b["side"], "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                     "light": "yellow" if b["area"] == "Litho" else "white"})
    port_v = None  # every kind's ports sit this far in front of the tool, in the kit's frame
    port_cache = {}

    def ports_of(kind):
        if kind not in port_cache:
            pts = []
            for p in kit.model(kind):
                if p["role"] == "port":
                    pts.append(((p["min"][0] + p["max"][0]) / 2, (p["min"][1] + p["max"][1]) / 2))
            port_cache[kind] = sorted(pts)
        return port_cache[kind]

    port_v = ports_of("etch")[0][1]
    # a wall's rail runs over its ports: wall 0 faces east (+x) onto the aisle, wall 1 west
    for b in bays:
        cx = (b["x0"] + b["x1"]) / 2
        b["rails_x"] = [cx - aisle / 2 - port_v, cx + aisle / 2 + port_v]

    labels = []
    run = None
    for b in bays + [None]:
        if run and b and b["area"] == run["area"] and b["side"] == run["side"] and b["phase"] == run["phase"] and abs(b["x0"] - run["x1"]) < 1e-6:
            run["x1"] = b["x1"]
            continue
        if run:
            labels.append({"text": AREA_NAMES.get(run["area"], run["area"]), "x": (run["x0"] + run["x1"]) / 2,
                           "y": (run["y0"] + run["y1"]) / 2, "area": run["area"]})
        run = dict(b) if b else None

    # ---------------------------------------------------------------- tools
    tools = []
    for t in plan["tools"]:
        g, ph, side, bay, x0, x1, y0, y1 = t
        kind = kit.kind_of(groups[g]["name"])
        k = kit.KINDS[kind]
        wx0, wx1 = offsets[ph] + x0, offsets[ph] + x1
        wy0, wy1 = sorted((wy(side, y0), wy(side, y1)))
        bcx = (bays[bay]["x0"] + bays[bay]["x1"]) / 2
        wall = 0 if (wx0 + wx1) / 2 < bcx else 1
        # the kit's frame: x along the wall, y into the tool from its front; turned to stand here
        if wall == 0:
            yaw, o = 90.0, (wx1, wy0)
        else:
            yaw, o = -90.0, (wx0, wy1)
        pts = []
        for u, v in ports_of(kind):
            dx, dy = rot(yaw, u, v)
            pts.append([round(o[0] + dx, 3), round(o[1] + dy, 3)])
        tools.append({"g": g, "kind": kind, "x0": wx0, "x1": wx1, "y0": wy0, "y1": wy1, "h": k["h"], "bay": bay,
                      "wall": wall, "o": [round(o[0], 3), round(o[1], 3), CZ], "yaw": yaw, "ports": pts})

    # ---------------------------------------------------------------- stockers and the interbay rails
    stockers = []
    cross = []
    for ph, L in enumerate(lengths):
        n = max(1, int(L // STOCKER_EVERY))
        for i in range(n):
            cxs = offsets[ph] + (i + 0.5) * L / n
            k = kit.KINDS["stocker"]
            # long side along the spine, its front facing north
            stockers.append({"x0": cxs - k["d"] / 2, "x1": cxs + k["d"] / 2, "y0": -k["w"] / 2, "y1": k["w"] / 2,
                             "o": [round(cxs - k["d"] / 2, 3), round(k["w"] / 2, 3), CZ], "yaw": -90.0, "x": cxs})
        # crossovers every 20 m or so, clear of the stockers
        m = max(2, int(L // CROSS_EVERY))
        for i in range(m + 1):
            x = offsets[ph] + 1.0 + i * (L - 2.0) / m
            if all(abs(x - (offsets[ph] + (j + 0.5) * L / n)) > 7.5 for j in range(n)):
                cross.append(x)
    cross.sort()
    xa, xb = offsets[0], offsets[-1] + lengths[-1]
    rails = [[[xa, INTERBAY_Y, RAIL_Z], [xb, INTERBAY_Y, RAIL_Z]], [[xa, -INTERBAY_Y, RAIL_Z], [xb, -INTERBAY_Y, RAIL_Z]]]
    for x in cross:
        rails.append([[x, -INTERBAY_Y, RAIL_Z], [x, INTERBAY_Y, RAIL_Z]])
    for b in bays:
        far = b["y1"] if b["side"] == 0 else b["y0"]
        near = INTERBAY_Y if b["side"] == 0 else -INTERBAY_Y
        for rx in b["rails_x"]:
            rails.append([[rx, near, RAIL_Z], [rx, far, RAIL_Z]])
        rails.append([[b["rails_x"][0], far, RAIL_Z], [b["rails_x"][1], far, RAIL_Z]])

    # ---------------------------------------------------------------- where a carrier can be
    # A point is (x, y, z, how): how is ("port", bay, wall), ("shelf", bay, wall),
    # ("stocker", side) or ("rail", side), saying how it joins the rails.
    def rail_x_of(bay, wall):
        return bays[bay]["rails_x"][wall]

    def to_rail(p):
        """The point on the rails above or beside p, and the time to get there."""
        x, y, z, how = p
        if how[0] == "port":
            return (x, y), HOIST_MIN
        if how[0] == "shelf":
            return (rail_x_of(how[1], how[2]), y), SLIDE_MIN
        if how[0] == "stocker":
            return (x, INTERBAY_Y if how[1] == 0 else -INTERBAY_Y), SLIDE_MIN + HOIST_MIN
        return (x, y), 0.0

    def side_of(p):
        how = p[3]
        if how[0] in ("port", "shelf"):
            return bays[how[1]]["side"]
        return how[1]

    def rail_path(a, b):
        (ax, ay), (bx, by) = to_rail(a)[0], to_rail(b)[0]
        sa, sb = side_of(a), side_of(b)
        ya, yb = (INTERBAY_Y if sa == 0 else -INTERBAY_Y), (INTERBAY_Y if sb == 0 else -INTERBAY_Y)
        same_bay = a[3][0] in ("port", "shelf") and b[3][0] in ("port", "shelf") and a[3][1] == b[3][1] and a[3][2] == b[3][2]
        if same_bay:
            pts = [(ax, ay), (bx, by)]
        else:
            pts = [(ax, ay), (ax, ya)]
            if sa != sb:
                xc = min(cross, key=lambda x: (abs(x - ax) + abs(x - bx), abs(x - ax)))
                pts += [(xc, ya), (xc, yb)]
            pts += [(bx, yb), (bx, by)]
        out = []
        for p in pts:
            if not out or math.dist(out[-1], p) > 1e-6:
                out.append(p)
        return out

    def travel(keys, moves, t0, t1, a, b):
        """Carry a carrier from a to b between fab minutes t0 and t1, on the rails at ride height."""
        span = max(t1 - t0, 0.05)
        (r0, d0), (r1, d1) = to_rail(a), to_rail(b)
        scale = min(1.0, span / max(d0 + d1 + 0.05, 1e-9) * 0.5)
        d0, d1 = d0 * scale, d1 * scale
        path = rail_path(a, b)
        lens = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
        total = sum(lens) or 1.0
        keys.append([t0, a[0], a[1], a[2]])
        tt = t0
        if a[3][0] == "stocker":
            tt += d0 / 2
            keys.append([tt, a[0], r0[1], RIDE_Z])
        elif d0 > 0:
            tt += d0
            keys.append([tt, r0[0], r0[1], RIDE_Z])
        ride = span - d0 - d1
        for i, L in enumerate(lens):
            tt += ride * L / total
            keys.append([tt, path[i + 1][0], path[i + 1][1], RIDE_Z])
        keys.append([t1, b[0], b[1], b[2]])
        moves.append([t0, t1])

    def port_point(ti, i):
        t = tools[ti]
        pt = t["ports"][i % len(t["ports"])]
        return (pt[0], pt[1], PORT_Z, ("port", t["bay"], t["wall"]))

    def shelf_point(ti, s):
        """Shelf s by tool ti: beside the rail along the tool's front, layers going down."""
        t = tools[ti]
        w = t["y1"] - t["y0"]
        n_along = max(1, int(w / SHELF_PITCH))
        layers = int((RIDE_Z - PORT_Z) / SHELF_STEP) + 1
        i, layer = s % n_along, (s // n_along) % layers
        y = t["y0"] + (i + 0.5) * w / n_along
        x = bays[t["bay"]]["rails_x"][t["wall"]] + (SHELF_OUT if t["wall"] == 0 else -SHELF_OUT)
        return (x, y, RIDE_Z - layer * SHELF_STEP, ("shelf", t["bay"], t["wall"]))

    def stocker_point(si, s):
        st = stockers[si]
        n_x, n_y = 20, 2
        n_z = int((RIDE_Z - PORT_Z) / 0.75) + 1
        s = s % (n_x * n_y * n_z)
        ix, iy, iz = s % n_x, (s // n_x) % n_y, s // (n_x * n_y)
        x = st["x0"] + 0.6 + ix * 0.55 + c["w"] / 2
        y = -0.6 + iy * 1.2
        return (x, y, PORT_Z + iz * 0.75, ("stocker", 0 if y > 0 else 1))

    def nearest_stocker(x):
        return min(range(len(stockers)), key=lambda i: abs(stockers[i]["x"] - x))

    # ---------------------------------------------------------------- shelves: the lowest free one at arrival
    lots = tr["lots"]
    waits = []
    for li, lot in enumerate(lots):
        for si, st in enumerate(lot["steps"]):
            arrive, start, end, tool, g = st
            if tool < 0:
                src = lot["steps"][si - 1][3] if si > 0 else (lot["prev"][1] if lot["prev"] else -1)
                x = (tools[src]["x0"] + tools[src]["x1"]) / 2 if src is not None and src >= 0 else offsets[0]
                waits.append((arrive, end, ("stk", nearest_stocker(x)), li, si))
            elif start - arrive >= DIRECT_MIN:
                waits.append((arrive, start, ("q", tool), li, si))
    waits.sort()
    busy, slot_of, active = {}, {}, []
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

    # ---------------------------------------------------------------- every lot's keys
    out_lots = []
    t_from, t_to = tr["from"], tr["to"]
    release = stocker_point(0, 0)
    for li, lot in enumerate(lots):
        keys, moves = [], []
        steps = lot["steps"]
        if lot["prev"] and lot["prev"][1] >= 0:
            here = port_point(lot["prev"][1], li)
            t_prev = lot["prev"][0]
        else:
            here = release
            t_prev = steps[0][0] - 5.0
        for si, st in enumerate(steps):
            arrive, start, end, tool, g = st
            slot = slot_of.get((li, si))
            if tool < 0:
                dst = stocker_point(slot[0][1], slot[1])
                travel(keys, moves, t_prev, arrive, here, dst)
                keys.append([end, dst[0], dst[1], dst[2]])
                here = dst
            else:
                port = port_point(tool, li)
                if slot is None:
                    travel(keys, moves, t_prev, arrive, here, port)
                else:
                    shelf = shelf_point(tool, slot[1])
                    travel(keys, moves, t_prev, arrive, here, shelf)
                    hop = min(SLIDE_MIN + HOIST_MIN, (start - arrive) / 2)
                    keys.append([start - hop, shelf[0], shelf[1], shelf[2]])
                    keys.append([start - hop * HOIST_MIN / (SLIDE_MIN + HOIST_MIN), port[0], port[1], RIDE_Z])
                    moves.append([start - hop, start])
                keys.append([start, port[0], port[1], port[2]])
                keys.append([end, port[0], port[1], port[2]])
                here = port
            t_prev = end
        last = keys[-1]
        keys.append([last[0] + HOIST_MIN, last[1], last[2], RIDE_Z])
        moves.append([last[0], last[0] + HOIST_MIN])
        keys = [[round(k[0], 3), round(k[1], 3), round(k[2], 3), round(k[3], 3)] for k in keys]
        if keys[-1][0] < t_from or keys[0][0] > t_to:
            continue
        out_lots.append({"id": lot["id"], "hot": lot["hot"], "k": keys, "m": [[round(a, 3), round(b, 3)] for a, b in moves]})

    # ---------------------------------------------------------------- the building and the campus
    floors = kit.floors()
    roof_top = floors[-1]["z1"]
    half = spine / 2 + depth
    campus = []
    for ph, L in enumerate(lengths):
        campus.append({"kind": "fab", "name": f"P{ph + 1}", "label": f"Phase {ph + 1} fab",
                       "x0": offsets[ph] - 6, "x1": offsets[ph] + L + 6, "y0": -half - 6, "y1": half + 6, "h": roof_top})
    for ph in range(len(lengths) - 1):
        x0 = offsets[ph] + lengths[ph] + 6
        campus.append({"kind": "bridge", "name": f"B{ph + 1}", "label": "Hoist bridge", "x0": x0, "x1": offsets[ph + 1] - 6,
                       "y0": -6.0, "y1": 6.0, "z0": RAIL_Z - 3.0, "h": RAIL_Z + 3.0})
    east = offsets[-1] + lengths[-1] + 6
    p3 = east + bridge
    cub_y0, cub_y1 = -half - 120, -half - 50
    campus += [
        {"kind": "pad", "name": "P3", "label": "Pad for the next phase", "x0": p3, "x1": p3 + lengths[-1], "y0": -half, "y1": half, "h": 0.3},
        {"kind": "cub", "name": "CUB", "label": "Central utility building", "x0": 0, "x1": east - 20, "y0": cub_y0, "y1": cub_y1, "h": 24.0},
        {"kind": "upw", "name": "UPW", "label": "Ultrapure water", "x0": east, "x1": east + 90, "y0": cub_y0, "y1": cub_y1, "h": 14.0},
        {"kind": "gas", "name": "GAS", "label": "Bulk gas yard", "x0": 180, "x1": 300, "y0": half + 50, "y1": half + 100, "h": 0.3},
        {"kind": "office", "name": "OFFICE", "label": "Office and fab entry", "x0": 0, "x1": 130, "y0": half + 50, "y1": half + 100, "h": 22.0},
        {"kind": "corridor", "name": "LINK", "label": "Utility link", "x0": 60, "x1": 90, "y0": cub_y1, "y1": -half - 6, "z0": 6.0, "h": 14.0},
    ]
    for i in range(8):
        x = 20 + i * ((east - 60) / 7)
        campus.append({"kind": "cooling_tower", "name": f"CT{i + 1}", "label": "Cooling tower" if i == 0 else "",
                       "x0": x - 7, "x1": x + 7, "y0": cub_y0 - 30, "y1": cub_y0 - 16, "h": 12.0})
    for i in range(6):
        x = 40 + i * ((east - 80) / 5)
        campus.append({"kind": "stack", "name": f"S{i + 1}", "label": "Exhaust scrubber stack" if i == 0 else "",
                       "x0": x - 1.5, "x1": x + 1.5, "y0": cub_y1 - 6, "y1": cub_y1 - 3, "h": 40.0})
    for i in range(5):
        x = 195 + i * 22
        campus.append({"kind": "tank", "name": f"T{i + 1}", "label": "Liquid gas tank" if i == 0 else "",
                       "x0": x - 3, "x1": x + 3, "y0": half + 60, "y1": half + 66, "h": 22.0})
    road = 10.0
    campus += [
        {"kind": "road", "name": "R1", "label": "", "x0": -80, "x1": p3 + lengths[-1] + 60, "y0": half + 30, "y1": half + 30 + road, "h": 0.05},
        {"kind": "road", "name": "R2", "label": "", "x0": -80, "x1": p3 + lengths[-1] + 60, "y0": cub_y0 - 60, "y1": cub_y0 - 60 + road, "h": 0.05},
        {"kind": "road", "name": "R3", "label": "", "x0": -80, "x1": -80 + road, "y0": cub_y0 - 60, "y1": half + 180, "h": 0.05},
        {"kind": "parking", "name": "PARK", "label": "Parking", "x0": -60, "x1": 140, "y0": half + 110, "y1": half + 175, "h": 0.05},
    ]

    ground = {"x0": -200, "x1": p3 + lengths[-1] + 200, "y0": cub_y0 - 200, "y1": half + 300}
    kinds = {k["kind"]: {"w": k["w"], "d": k["d"], "h": k["h"], "ports": k["ports"]} for k in S["kinds"]}
    return {
        "model": "SMT2020",
        "what": "A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. Tools are generic shapes of our own at the size book's sizes; support buildings drawn only; which port, which shelf and the path along the rails are drawn only, the times are the run's.",
        "plan": plan_name,
        "from": t_from,
        "to": t_to,
        "metres_per_day": plan["metres_per_day"],
        "spine": spine,
        "depth": depth,
        "aisle": aisle,
        "clean_z": CZ,
        "floors": floors,
        "port_z": PORT_Z,
        "rail_z": RAIL_Z,
        "ride_z": RIDE_Z,
        "foup": [c["w"], c["d"], c["h"]],
        "vehicle": [S["vehicle"]["l"], S["vehicle"]["w"], S["vehicle"]["h"]],
        "kinds": kinds,
        "areas": {k: {"colour": v, "name": AREA_NAMES[k]} for k, v in AREA_COLOURS.items()},
        "groups": [{"name": g["name"], "area": g["area"], "phase": g["phase"], "kind": kit.kind_of(g["name"])} for g in groups],
        "lengths": lengths,
        "offsets": offsets,
        "bays": bays,
        "labels": labels,
        "tools": tools,
        "stockers": stockers,
        "rails": rails,
        "campus": campus,
        "ground": ground,
        "states": tr["states"],
        "lots": out_lots,
    }
