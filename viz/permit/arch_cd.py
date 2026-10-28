"""Architectural construction documents for the whole fab (docs/ARCH-DOCS.md, AD1 to AD3): every door numbered with
its hardware set, every space numbered with its finish set, the roofs (parapets, drains, hatches, curbs) and the
dimensions the plans carry. Finishes, hardware and roof elements are assumed by kind; everything new is placed by
dd_place, so it clashes with nothing.
"""

import math

import model as bmodel
from dd_arch import frange
from dd_place import Index

PARAPET, DRAIN_M2 = 1.0, 900.0                 # parapet height and roof area per drain (assumed; IPC chapter 11 not read)
FLOOR = {"support floor": "S", "cleanroom": "C", "roof": "R"}
HARDWARE = {
    "HW-1": ("Exit stair door", "panic hardware, closer, positive latching, 90 min label, gasketing, no lock against egress"),
    "HW-2": ("Exit passageway door", "panic hardware, closer, positive latching, 60 min label, smoke gasketing"),
    "HW-3": ("Hazardous room door", "panic hardware, closer, 90 min label, gasketing, card reader on the corridor side"),
    "HW-4": ("Exterior exit door", "panic hardware, closer, weather seals, threshold, alarmed where it is exit only"),
    "HW-5": ("Chase door", "lever passage set, closer, cleanroom seals, kick plate"),
    "HW-6": ("Toilet room door", "push and pull plates, closer, privacy indicator not used (multi-user room)"),
    "HW-7": ("Gowning door", "lever passage set, closer, interlocked with the air shower"),
    "HW-8": ("Roof hatch", "hatch with gas springs, padlock hasp outside, ladder safety post"),
    "HW-9": ("Gowning entry door", "lever passage set, closer, card reader outside"),
}
FINISH = {   # kind: floor, base, walls, ceiling, height above the floor (m), all assumed
    "bay": ("RF-1 conductive raised floor tile", "none (panels to the floor)", "WP-1 cleanroom wall panel", "FF-1 fan filter grid", 5.5),
    "spine": ("RF-1 conductive raised floor tile", "none", "WP-1 cleanroom wall panel", "FF-1 fan filter grid", 5.5),
    "gowning": ("VF-1 conductive sheet vinyl", "VB-1 coved vinyl", "WP-1 cleanroom wall panel", "FF-1 fan filter grid", 3.0),
    "gas room": ("SC-2 sealed concrete, chemical-resistant coating", "CB-1 coved coating", "PT-2 epoxy paint on WT-2", "exposed structure", 3.0),
    "chemical dispense": ("SC-2 sealed concrete, chemical-resistant coating", "CB-1 coved coating", "PT-2 epoxy paint on WT-2", "exposed structure", 3.0),
    "exit passageway": ("SC-1 sealed concrete", "RB-1 rubber", "PT-1 paint on WT-1", "exposed structure", 3.0),
    "toilet room": ("PT-1 porcelain tile", "TB-1 tile base", "CT-1 ceramic tile to 2.1 m, paint above", "GB-1 moisture-resistant gypsum board", 2.7),
    "emergency control": ("CPT-1 carpet tile", "RB-1 rubber", "PT-1 paint", "ACT-1 acoustic tile", 2.7),
    "other": ("SC-1 sealed concrete", "RB-1 rubber", "PT-1 paint", "exposed structure", 3.0),
}


def run(C):
    S, P = C.S, C.P
    X = Index(C)
    roofs(C, X)
    A = {"hardware_sets": {k: {"name": n, "items": v} for k, (n, v) in HARDWARE.items()},
         "finishes": {k: {"floor": v[0], "base": v[1], "walls": v[2], "ceiling": v[3], "height_m": v[4]} for k, v in FINISH.items()}}
    A["doors"] = doors(C)
    A["rooms"] = rooms(C)
    A["roof"] = C.roof_info
    A["dims"] = dims(C)
    P["arch"] = A
    C.made.update({"ad:doors", "ad:rooms", "ad:roof", "ad:dims"})


# ------------------------------------------------------------------ AD2 roofs

def roofs(C, X):
    rz = C.fl["roof"]["z1"]
    info = {}
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        x0, y0, x1, y1 = b["x0"], b["y0"], b["x1"], b["y1"]
        t = 0.2
        for n, box in enumerate(((x0, y0, rz, x1, y0 + t, rz + PARAPET), (x0, y1 - t, rz, x1, y1, rz + PARAPET),
                                 (x0, y0 + t, rz, x0 + t, y1 - t, rz + PARAPET), (x1 - t, y0 + t, rz, x1, y1 - t, rz + PARAPET))):
            X.place(f"ad/parapet/{k}/{n}", "IfcWall", f"Parapet {k}", [box], p, "roof", "PARAPET", "parapet",
                    stage="AD", lod=300, review="construction documents", numbers=f"{PARAPET} m, metal coping (assumed)")
        # curbs under the make-up air units
        maus = [e for e in C.new if e["cls"] == "IfcUnitaryEquipment" and e["bld"] == p and (e["otype"] or "") == "make-up air unit"]
        for e in maus:
            bx = e["box"]
            X.add(f"ad/curb/{e['key'].replace('permit/', '')}", "IfcMember", f"Equipment curb, {e['name']}",
                  (bx[0], bx[1], rz, bx[3], bx[4], rz + 0.35), p, "roof", "USERDEFINED", "equipment curb",
                  stage="AD", lod=300, review="construction documents", numbers="insulated curb 350 mm, flashed to the membrane")
        # drains on a grid, at most DRAIN_M2 of roof each
        area = (x1 - x0) * (y1 - y0)
        n_need = math.ceil(area / DRAIN_M2)
        nx = max(1, round(math.sqrt(n_need * (x1 - x0) / (y1 - y0))))
        ny = math.ceil(n_need / nx)
        drains = 0
        for i in range(nx):
            for j in range(ny):
                cx = x0 + (i + 0.5) * (x1 - x0) / nx
                cy = y0 + (j + 0.5) * (y1 - y0) / ny
                cand = [(cx + dx - 0.2, cy + dy - 0.2, rz, cx + dx + 0.2, cy + dy + 0.2, rz + 0.1)
                        for dx, dy in sorted(((dx, dy) for dx in frange(-3, 3, 0.5) for dy in frange(-3, 3, 0.5)),
                                             key=lambda d: (abs(d[0]) + abs(d[1]), d))]
                X.place(f"ad/drain/{k}/{i}/{j}", "IfcWasteTerminal", f"Roof drain {k}", cand, p, "roof", "ROOFDRAIN", "roof drain",
                        stage="AD", lod=300, review="construction documents", numbers=f"at most {DRAIN_M2:.0f} m2 each (assumed)")
                drains += 1
        # a roof hatch near the west end, over a ladder from the air space
        cand = [(x0 + 3 + dx, y + dy, rz, x0 + 3.9 + dx, y + 0.9 + dy, rz + 0.3) for y in (30.0, -31.0) for dx in frange(0, 12, 0.5)
                for dy in (0, 1, -1)]
        X.place(f"ad/hatch/{k}", "IfcDoor", f"Roof hatch {k}", cand, p, "roof", "TRAPDOOR", "roof hatch", stage="AD", lod=300,
                review="construction documents", numbers="900 x 900 mm, with a ladder (assumed)", door=(0.3, 0.9, "SINGLE_SWING_LEFT", "TRAPDOOR"))
        info[k] = {"area_m2": round(area, 1), "drains": drains, "drain_area_m2_each": DRAIN_M2, "hatches": 1, "parapet_m": PARAPET,
                   "curbs": len(maus), "plant_units": len(maus), "slope": "1:50 to the drains (assumed)",
                   "membrane": "single-ply membrane on insulation on metal deck (assumed)"}
    C.roof_info = info


# ------------------------------------------------------------------ AD1 doors and rooms

def hardware(e):
    k = e["key"]
    if "/hatch/" in k:
        return "HW-8"
    if "/chase/" in k:
        return "HW-5"
    if "/toilet/" in k:
        return "HW-6"
    parts = k.split("/")
    rid, suf = parts[2], (parts[3] if len(parts) > 3 else "")
    if "-GW" in rid:
        return "HW-9" if suf == "in" else "HW-7"
    if suf in ("ext", "out") or "-ED" in rid:
        return "HW-4"
    if "-XP" in rid and suf not in ("core",):
        return "HW-2"
    if "-SC" in rid or "-FS" in rid or suf == "core":
        return "HW-1"
    if "-GR" in rid or "-CD" in rid:
        return "HW-3"
    return "HW-4"


def doors(C):
    rated = {d["key"]: d for d in C.P.get("doors", [])}
    ds = [e for e in C.new if e["cls"] == "IfcDoor"]
    for e in ds:
        if e["bld"] is None:
            raise SystemExit(f"door {e['key']} is in no building")
    groups = {}
    for e in ds:
        k = C.keys[e["bld"]]
        fl = FLOOR.get(e["storey"], "S")
        groups.setdefault((k, fl), []).append(e)
    out = []
    for (k, fl), es in sorted(groups.items()):
        for n, e in enumerate(sorted(es, key=lambda e: (round(e["box"][0], 2), round(e["box"][1], 2), e["key"])), start=1):
            bx = e["box"]
            h, w = (e.get("door") or (2.1, 1.2))[:2]
            r = rated.get(e["key"], {})
            no = f"{k}-{fl}-{n:03d}"
            e["permit"]["Numbers"] = f"{no}; " + e["permit"]["Numbers"]
            out.append({"no": no, "key": e["key"], "building": k, "floor": {"S": "support floor", "C": "clean floor", "R": "roof"}[fl],
                        "x": round((bx[0] + bx[3]) / 2, 2), "y": round((bx[1] + bx[4]) / 2, 2), "width_mm": round(w * 1000),
                        "height_mm": round(h * 1000), "rating_h": r.get("rating_h", 0), "wall": r.get("wall_kind", "roof" if fl == "R" else "partition"),
                        "type": "D3 hatch" if fl == "R" else ("D2 hollow metal, labelled" if r.get("rating_h") else "D1 hollow metal"),
                        "hardware": hardware(e), "name": e["name"]})
    return out


def kind_of(e):
    n = (e["name"] or "").lower()
    ot = (e["otype"] or "").lower()
    if e["key"].startswith("bay/") or n.startswith("bay "):
        return "bay"
    if "spine" in n:
        return "spine"
    for k in ("gowning", "gas room", "chemical dispense", "exit passageway", "toilet room", "emergency control"):
        if k in n or k in ot:
            return k
    return "other"


def rooms(C):
    sp = [e for e in C.M["elements"] + C.new if e["cls"] == "IfcSpace"]
    groups = {}
    for e in sp:
        k = C.keys[e["bld"]] if e["bld"] is not None else "SITE"
        fl = FLOOR.get(e["storey"], "S")
        groups.setdefault((k, fl), []).append(e)
    out = []
    for (k, fl), es in sorted(groups.items()):
        for n, e in enumerate(sorted(es, key=lambda e: (round(e["box"][0], 2), round(e["box"][1], 2), e["key"])), start=1):
            kd = kind_of(e)
            f = FINISH[kd]
            bx = e["box"]
            out.append({"no": f"{k}.{fl}{n:03d}", "key": e["key"], "name": e["name"], "kind": kd, "building": k,
                        "floor": {"S": "support floor", "C": "clean floor", "R": "roof"}[fl],
                        "area_m2": round((bx[3] - bx[0]) * (bx[4] - bx[1]), 1), "floor_finish": f[0], "floor": f[0], "base": f[1],
                        "walls": f[2], "ceiling": f[3], "ceiling_height_m": min(f[4], round(bx[5] - bx[2], 2)),
                        "storey": {"S": "support floor", "C": "clean floor", "R": "roof"}[fl]})
    return out


# ------------------------------------------------------------------ AD3 plan dimensions

def dims(C):
    xs_all, ys_all = bmodel.grid_lines(C.S)
    out = {}
    for sid, p, floor in (("A-111", 0, "support floor"), ("A-112", 0, "clean floor"), ("A-121", 1, "support floor"), ("A-122", 1, "clean floor")):
        b = C.blds[p]
        xs = [b["x0"]] + sorted(x for x in xs_all if b["x0"] + 1e-6 < x < b["x1"] - 1e-6) + [b["x1"]]
        ys = [b["y0"]] + sorted(y for y in ys_all if b["y0"] + 1e-6 < y < b["y1"] - 1e-6) + [b["y1"]]
        out[sid] = {"building": C.keys[p], "floor": floor, "overall_x_m": round(b["x1"] - b["x0"], 4), "overall_y_m": round(b["y1"] - b["y0"], 4),
                    "grid_x_m": [b_ - a for a, b_ in zip(xs, xs[1:])], "grid_y_m": [b_ - a for a, b_ in zip(ys, ys[1:])],
                    "grid_x": xs, "grid_y": ys}
    return out
