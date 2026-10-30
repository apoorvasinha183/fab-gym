"""The faithful BIM (docs/BIM-FAITHFUL.md): every element of the construction documents in the shape the sheets draw.

pre(C) runs before coordination and adds what the sheets draw but the model lacked (toilet partitions, mirrors, the
gowning rooms' fit-out, hatch ladders), placed so nothing clashes. post(C) runs after coordination and gives every
element its shape, inside its box: parts (swept solids in world coordinates), repeats (one shape placed many times),
openings and what fills them, aggregates (a stair's flights, landings and handrails), and a material.
Only --stage cd calls this, so the schematic and design development sets keep their bytes.
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. NOT FOR CONSTRUCTION.
"""

import math
import re

import model as bmodel
from dd_place import Index

UP = (0.0, 0.0, 1.0)
ROUND_M = [0.1, 0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5]
TREAD, RISERS, FLOOR_LANDING, MID_LANDING, WELL = 0.28, 44, 2.10, 1.12, 0.1
RAIL_R, RAIL_TOP = 0.02, 0.9
FRAME, LEAF, LEAF_GAP, SILL = 0.05, 0.045, 0.003, 0.01
TILE_T, PITCH = 0.03, 0.6
FACADE = re.compile(r".+ fab, (north|south|east|west) wall$")

# name: (colour as linear rgb, what it is, category); colours are plain, Blender puts its own looks on by name
MATERIALS = {
    "concrete": ((0.62, 0.62, 0.60), "cast-in-place concrete", "concrete"),
    "steel": ((0.45, 0.48, 0.52), "structural steel, painted", "steel"),
    "galvanised": ((0.70, 0.72, 0.74), "galvanised steel", "steel"),
    "stainless": ((0.78, 0.79, 0.81), "stainless steel, electropolished", "steel"),
    "pipe_fire": ((0.62, 0.08, 0.06), "black steel sprinkler pipe, red", "steel"),
    "pipe_plastic": ((0.82, 0.84, 0.86), "PVDF and polypropylene process pipe", "plastic"),
    "pipe_drain": ((0.35, 0.37, 0.40), "double-contained drain pipe", "plastic"),
    "duct_coated": ((0.30, 0.42, 0.52), "coated duct for corrosive exhaust", "steel"),
    "imp_panel": ((0.80, 0.82, 0.85), "IMP-1 insulated metal wall panel", "metal"),
    "coping": ((0.55, 0.57, 0.60), "PC-1 metal parapet coping", "metal"),
    "gypsum": ((0.88, 0.88, 0.86), "gypsum board on steel studs, rated where scheduled", "gypsum"),
    "cleanroom_panel": ((0.93, 0.94, 0.95), "WP-1 cleanroom wall panel", "metal"),
    "hm_frame": ((0.30, 0.33, 0.37), "hollow metal door frame", "steel"),
    "hm_door": ((0.50, 0.55, 0.62), "hollow metal door leaf", "steel"),
    "rf_tile": ((0.84, 0.86, 0.88), "RF-1 conductive raised floor tile", "metal"),
    "pedestal": ((0.60, 0.61, 0.63), "raised floor pedestal, zinc plated", "steel"),
    "filter_ceiling": ((0.90, 0.91, 0.92), "FF-1 fan filter grid", "aluminium"),
    "ffu_housing": ((0.88, 0.89, 0.90), "fan filter unit housing", "aluminium"),
    "filter_face": ((0.96, 0.96, 0.93), "ULPA filter face", "glass fibre"),
    "roof_deck": ((0.33, 0.35, 0.38), "single-ply membrane on insulation on metal deck", "roofing"),
    "laminate": ((0.80, 0.76, 0.68), "solid phenolic toilet partition and bench", "plastic"),
    "locker": ((0.55, 0.62, 0.70), "steel locker", "steel"),
    "mirror": ((0.75, 0.82, 0.88), "mirror glass", "glass"),
    "ceramic": ((0.95, 0.95, 0.94), "vitreous china", "ceramic"),
    "device": ((0.94, 0.94, 0.92), "device housing", "plastic"),
    "alarm": ((0.70, 0.07, 0.06), "fire alarm device, red", "plastic"),
    "luminaire": ((0.95, 0.95, 0.90), "luminaire", "aluminium"),
    "electrical": ((0.45, 0.48, 0.52), "electrical enclosure", "steel"),
    "plant": ((0.66, 0.68, 0.70), "packaged plant", "steel"),
    "tool": ((0.92, 0.92, 0.91), "process tool envelope (owner furnished)", "envelope"),
    "stocker": ((0.85, 0.86, 0.88), "stocker envelope (owner furnished)", "envelope"),
    "asphalt": ((0.18, 0.18, 0.19), "asphalt paving", "paving"),
    "site": ((0.70, 0.70, 0.68), "site block (drawn as one block)", "envelope"),
    "lift": ((0.55, 0.58, 0.62), "lift car and guide rails", "steel"),
}


# ------------------------------------------------------------------ geometry helpers

def unit(v):
    L = math.sqrt(sum(c * c for c in v))
    return tuple(c / L for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def ref_for(z):
    """A reference direction across an extrusion: horizontal, so a horizontal member's profile has its y axis up."""
    x = cross(UP, z)
    if sum(c * c for c in x) < 1e-12:
        return (1.0, 0.0, 0.0)
    return unit(x)


def part(p, o, z, d, m, x=None):
    z = unit(z)
    return {"p": p, "o": tuple(round(c, 6) for c in o), "z": z, "x": x or ref_for(z), "d": round(d, 6), "m": m}


def block(x0, y0, z0, x1, y1, z1, m):
    return part(("rect", x1 - x0, y1 - y0), ((x0 + x1) / 2, (y0 + y1) / 2, z0), UP, z1 - z0, m)


def rod(a, b, radius, m):
    v = [b[k] - a[k] for k in range(3)]
    return part(("circle", radius), a, v, math.sqrt(sum(c * c for c in v)), m)


def dims(b):
    return (b[3] - b[0], b[4] - b[1], b[5] - b[2])


def long_axis(b):
    d = dims(b)
    return max(range(3), key=lambda k: d[k])


def along(b, k, prof, m, at=None):
    """A prism along axis k through the box's cross centre (or `at`, the cross centre to use)."""
    c = [(b[i] + b[i + 3]) / 2 for i in range(3)] if at is None else list(at)
    a = list(c)
    a[k] = b[k]
    z = [0.0, 0.0, 0.0]
    z[k] = 1.0
    return part(prof, a, z, b[k + 3] - b[k], m)


def round_along(b, m):
    k = long_axis(b)
    d = [x for i, x in enumerate(dims(b)) if i != k]
    return along(b, k, ("circle", min(d) / 2), m)


# ------------------------------------------------------------------ materials

def material(e):
    cls, pre, ot, nm = e["cls"], e["pre"] or "", (e["otype"] or ""), e["name"] or ""
    if cls in ("IfcColumn", "IfcFooting") or ot == "waffle rib" or (cls == "IfcSlab" and pre in ("FLOOR", "LANDING")):
        return "concrete"
    if cls == "IfcSlab":
        return "roof_deck" if e["key"].endswith("/roof") else "concrete"
    if cls in ("IfcBeam", "IfcPlate") or ot.startswith("truss member") or pre == "BRACE":
        return "steel"
    if cls == "IfcWall":
        if FACADE.match(nm) or ot == "parapet" or nm.startswith("Stair enclosure"):
            return "imp_panel" if FACADE.match(nm) or ot == "parapet" else "gypsum"
        if ot.startswith("chase partition") or e["storey"] == "cleanroom":
            return "cleanroom_panel"
        return "laminate" if ot == "toilet partition" else "gypsum"
    if cls == "IfcCovering":
        return "filter_ceiling" if pre == "CEILING" else "rf_tile"
    if cls == "IfcPipeSegment":
        if ot.startswith("sprinkler"):
            return "pipe_fire"
        if ot.startswith("drain"):
            return "pipe_drain"
        if ot.startswith("upw"):
            return "pipe_plastic"
        return "stainless"
    if cls == "IfcDuctSegment":
        return "duct_coated" if ("acid" in ot or "toxic" in ot) else "galvanised"
    if cls in ("IfcCableCarrierSegment", "IfcMechanicalFastener") or ot == "pipe hanger rod" or ot == "equipment curb":
        return "galvanised"
    if cls == "IfcReinforcingBar":
        return "steel"
    if cls == "IfcValve":
        return "stainless"
    if cls == "IfcFireSuppressionTerminal":
        return "galvanised"
    if cls == "IfcAirTerminal":
        return "ffu_housing" if "fan filter" in ot else "galvanised"
    if cls in ("IfcSensor",):
        return "device"
    if cls == "IfcAlarm":
        return "alarm"
    if cls == "IfcLightFixture":
        return "luminaire"
    if cls in ("IfcElectricDistributionBoard", "IfcTransformer", "IfcElectricGenerator"):
        return "electrical"
    if cls in ("IfcChiller", "IfcFan", "IfcFilter"):
        return "plant"
    if cls == "IfcUnitaryEquipment":
        return "stainless" if ot in ("gas cabinet", "air shower") else "plant"
    if cls in ("IfcSanitaryTerminal",):
        return "ceramic" if pre in ("TOILETPAN", "WASHHANDBASIN", "SINK") else "stainless"
    if cls == "IfcWasteTerminal":
        return "galvanised"
    if cls == "IfcDoor":
        return "hm_door"
    if cls == "IfcStair":
        return "galvanised" if ot == "fixed ladder" else "concrete"
    if cls == "IfcTransportElement":
        return "lift"
    if cls == "IfcFurniture":
        return {"mirror": "mirror", "locker": "locker"}.get(ot, "laminate" if ot == "bench" else "stainless")
    if cls == "IfcBuildingElementProxy":
        if (e["key"] or "").startswith("tool/"):
            return "tool"
        if ot in ("stocker", "hoist rail"):
            return "stocker" if ot == "stocker" else "steel"
        if ot in ("campus road", "campus parking"):
            return "asphalt"
        if ot in ("campus tank", "campus stack"):
            return "stainless"
        return "site"
    return "plant"


# ------------------------------------------------------------------ before coordination: what the sheets draw

def pre(C):
    X = Index(C)
    toilets(C, X)
    gowning(C, X)
    ladders(C, X)


def _cd(**kw):
    return dict(stage="BIM", lod=400, review="construction documents", **kw)


def toilets(C, X):
    for c in C.P["toilets"]["cores"]:
        cid = c["id"]
        p = C.keys.index(c["building"])
        front_is_low = abs(c["box"][1]) < abs(c["box"][4])     # the face toward the spine
        for who in ("men", "women"):
            wcs = sorted((e for e in C.new if e["key"].startswith(f"permit/fixture/{cid}/{who}/wc/")), key=lambda e: e["box"][0])
            lavs = [e for e in C.new if e["key"].startswith(f"permit/fixture/{cid}/{who}/lav/")]
            if not wcs:
                continue
            w0 = wcs[0]["box"]
            back = w0[4] + 0.05 if front_is_low else w0[1] - 0.05
            for i in range(len(wcs) + 1):
                x = w0[0] - 0.1 + i * 0.9
                cands = []
                for depth in (1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 0.9):
                    ya, yb = (back - depth, back) if front_is_low else (back, back + depth)
                    cands.append((x, ya, 0.15, x + 0.025, yb, 1.95))
                X.place(f"bim/partition/{cid}/{who}/{i}", "IfcWall", f"Toilet partition {cid}", cands, p, "support floor",
                        "PARTITIONING", "toilet partition", **_cd(numbers="25 mm solid phenolic, 1.8 m high, 0.15 m off the floor (A-701)"))
            for n, l in enumerate(sorted(lavs, key=lambda e: e["box"][1])):
                b = l["box"]
                wall = b[0] - 0.05          # the side wall's face: lavatories stand 0.05 off it
                X.place(f"bim/mirror/{cid}/{who}/{n}", "IfcFurniture", f"Mirror {cid}", [(wall, b[1], 1.1, wall + 0.006, b[4], 1.8)],
                        p, "support floor", "USERDEFINED", "mirror", **_cd(numbers="6 mm mirror over the lavatory, 1.1 to 1.8 m (A-701)"))


def gowning(C, X):
    for r in C.P["rooms"]:
        if r["kind"] != "gowning":
            continue
        rid = r["id"]
        p = C.keys.index(r["building"])
        x0, y0, z0, x1, y1, z1 = r["box"]
        t = 0.2
        ix0, iy0, ix1, iy1 = x0 + t, y0 + t, x1 - t, y1 - t
        door = next(e for e in C.new if e["key"] == f"permit/door/{rid}")
        db = door["box"]
        dx, dy = (db[0] + db[3]) / 2, (db[1] + db[4]) / 2
        # the fab wall is the room side nearest the door; positions below run in (a: off the fab wall, b: along it)
        sides = {"x0": abs(dx - x0), "x1": abs(dx - x1), "y0": abs(dy - y0), "y1": abs(dy - y1)}
        fab = min(sides, key=sides.get)
        a_ax = 0 if fab[0] == "x" else 1
        a_hi = fab.endswith("1")
        lo_a, hi_a = (ix0, ix1) if a_ax == 0 else (iy0, iy1)
        lo_b, hi_b = (iy0, iy1) if a_ax == 0 else (ix0, ix1)
        b_door = dy if a_ax == 0 else dx

        def box(a0, a1, b0, b1, h):
            """a measured off the fab wall (0 at its face), b along it; to a world box."""
            if a_hi:
                A0, A1 = hi_a - a1, hi_a - a0
            else:
                A0, A1 = lo_a + a0, lo_a + a1
            return (A0, b0, z0, A1, b1, z0 + h) if a_ax == 0 else (b0, A0, z0, b1, A1, z0 + h)

        depth = hi_a - lo_a

        def shifted(a0, a1, b0, b1, h):
            return [box(a0, a1, b0 + s, b1 + s, h) for s in (0, 0.2, -0.2, 0.4, -0.4, 0.6, -0.6)]

        X.place(f"bim/airshower/{rid}", "IfcUnitaryEquipment", f"Air shower {rid}", shifted(0.0, 1.2, b_door - 0.75, b_door + 0.75, 2.3),
                p, "cleanroom", "USERDEFINED", "air shower", **_cd(numbers="1.5 x 1.2 m, interlocked with the fab door (HW-7, A-702)"))
        for i in range(8):
            b0 = lo_b + 0.4 + i * 0.45
            X.place(f"bim/locker/{rid}/{i}", "IfcFurniture", f"Lockers {rid}", shifted(depth - 0.5, depth, b0, b0 + 0.42, 1.9),
                    p, "cleanroom", "USERDEFINED", "locker", **_cd(numbers="locker bay 0.42 m, 1.9 m high (A-702)"))
        X.place(f"bim/bench/{rid}", "IfcFurniture", f"Gowning bench {rid}", shifted(depth - 1.6, depth - 1.2, lo_b + 0.4, lo_b + 4.4, 0.45),
                p, "cleanroom", "USERDEFINED", "bench", **_cd(numbers="4.0 m bench, 0.45 m high (A-702)"))
        X.place(f"bim/rack/{rid}", "IfcFurniture", f"Garment rack {rid}", shifted(depth - 0.6, depth, hi_b - 2.0, hi_b - 0.6, 1.7),
                p, "cleanroom", "USERDEFINED", "garment rack", **_cd(numbers="1.4 m garment rack (A-702)"))


def ladders(C, X):
    air0 = C.fl["air space"]["z0"] + bmodel.FILTER
    roof0 = C.fl["roof"]["z0"]
    for h in [e for e in C.new if e["cls"] == "IfcDoor" and (e["door"] or ())[3:4] == ("TRAPDOOR",)]:
        b = h["box"]
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        cands = [(cx - 0.25 + dx, cy + sy - 0.1, air0, cx + 0.25 + dx, cy + sy + 0.1, roof0) for sy in (-0.25, 0.25, 0.0)
                 for dx in (0.0, -0.1, 0.1)]
        X.place(f"bim/ladder/{h['key'].split('/')[-1]}", "IfcStair", f"Hatch ladder {h['name'].split()[-1]}", cands, h["bld"], "air space",
                "USERDEFINED", "fixed ladder", **_cd(numbers="fixed ladder, rails 40 mm, rungs at 300 mm (assumed), to the roof hatch"))


# ------------------------------------------------------------------ after coordination: shapes

def post(C):
    S = C.S
    els = C.M["elements"] + C.new
    C.bim_extra = []
    maps = {}
    by_key = {e["key"]: e for e in els}
    for e in els:
        if e["rail"] is not None and e["box"] is None:
            e["box"] = rail_box(e)
    walls = [e for e in els if e["cls"] == "IfcWall"]
    ffu_allocate(els)
    for e in els:
        shape(C, e, maps)
    doors(C, els, walls)
    stairs(C, els)
    trusses(C, els)
    slab_openings(C, els)
    pedestals(C, els, maps)
    for e in els + C.bim_extra:
        if e["cls"] == "IfcSpace":
            continue
        if "mapped" in e:
            ms = [p["m"] for p in maps[e["mapped"]["map"]]["parts"]]
        elif "parts" in e:
            ms = [p["m"] for p in e["parts"]]
        elif e.get("nobody"):
            ms = [material(e)]
        else:
            ms = [material(e)]
        e["mats"] = sorted(set(ms), key=ms.index)
    C.bim = {"maps": maps, "materials": {k: {"rgb": v[0], "what": v[1], "category": v[2]} for k, v in MATERIALS.items()}}
    heads = sum(len(e["mapped"]["at"]) for e in els if (e["otype"] or "") == "sprinkler array")
    ffus = sum(len(e["mapped"]["at"]) for e in els if (e["otype"] or "") == "fan filter unit array" and "mapped" in e)
    peds = sum(len(e["mapped"]["at"]) for e in C.bim_extra if e.get("mapped"))
    C.P["bim"] = {"rule": "everything the sheets draw, in the shape they draw it, inside its element's box (docs/BIM-FAITHFUL.md)",
                  "sprinkler_heads_in_arrays": heads, "fan_filter_units_in_arrays": ffus, "pedestals": peds,
                  "openings": sum(len(e.get("voids", ())) for e in els), "parts_added": len(C.bim_extra),
                  "stairs": "two flights of 22 risers, floor landings at the end the doors open from (the doors moved there)"}
    return by_key


def rail_box(e):
    (ax, ay, az), (cx, cy, _) = e["rail"]
    L = math.hypot(cx - ax, cy - ay)
    ux, uy = (cx - ax) / L, (cy - ay) / L
    px, py = -uy * bmodel.RAIL_W / 2, ux * bmodel.RAIL_W / 2
    xs = [ax + px, ax - px, cx + px, cx - px]
    ys = [ay + py, ay - py, cy + py, cy - py]
    return (round(min(xs), 6), round(min(ys), 6), az, round(max(xs), 6), round(max(ys), 6), az + bmodel.RAIL_H)


def shape(C, e, maps):
    """Give e its parts or repeats. Elements the rules leave alone keep their box as their body."""
    cls, pre, ot, nm, b = e["cls"], e["pre"] or "", e["otype"] or "", e["name"] or "", e["box"]
    m = material(e)
    if cls == "IfcWall" and FACADE.match(nm):
        e["parts"] = facade(b, m)
    elif cls == "IfcWall" and pre == "PARAPET":
        e["parts"] = [block(b[0], b[1], b[2], b[3], b[4], b[5] - 0.05, m), block(b[0], b[1], b[5] - 0.05, b[3], b[4], b[5], "coping")]
    elif cls == "IfcCovering" and pre == "FLOORING" and not ot:
        e["parts"] = [block(b[0], b[1], b[5] - TILE_T, b[3], b[4], b[5], "rf_tile")]
    elif cls == "IfcPipeSegment" or (cls == "IfcCableCarrierSegment" and pre == "CONDUITSEGMENT") or ot == "pipe hanger rod":
        e["parts"] = [round_along(b, m)]
    elif cls == "IfcDuctSegment":
        k = long_axis(b)
        d = sorted(x for i, x in enumerate(dims(b)) if i != k)
        if abs(d[0] - d[1]) < 1e-6 and any(abs(d[0] - s) < 1e-6 for s in ROUND_M):
            e["parts"] = [round_along(b, m)]
    elif cls == "IfcCableCarrierSegment":
        k = long_axis(b)
        w = dims(b)[1 - k] if k < 2 else dims(b)[0]
        h = dims(b)[2]
        # a U whose opening points up: the profile's x is world up, its y across the tray
        pt = along(b, k, ("U", w, h, 0.002), m)
        z = pt["z"]
        y_dir = unit(cross(z, UP))
        pt["x"] = UP
        pt["p"] = ("U", w, h, 0.002)
        _ = y_dir
        e["parts"] = [pt]
    elif cls == "IfcBeam" and ot == "roof beam":
        k = long_axis(b)
        w = dims(b)[1 - k] if k < 2 else dims(b)[0]
        e["parts"] = [along(b, k, ("I", w, dims(b)[2], 0.012, 0.02), m)]
    elif cls == "IfcMember" and pre == "BRACE":
        e["parts"] = bracing(b, m)
    elif ot == "equipment curb":
        t = 0.1
        e["parts"] = [block(b[0], b[1], b[2], b[3], b[1] + t, b[5], m), block(b[0], b[4] - t, b[2], b[3], b[4], b[5], m),
                      block(b[0], b[1] + t, b[2], b[0] + t, b[4] - t, b[5], m), block(b[3] - t, b[1] + t, b[2], b[3], b[4] - t, b[5], m)]
    elif cls == "IfcMechanicalFastener":
        e["parts"] = [round_along(b, m)]
    elif cls == "IfcReinforcingBar":
        e["parts"] = rebar(e, b, m)
    elif cls == "IfcValve" and ot == "isolation valve":
        e["parts"] = valve(b)
    elif cls == "IfcFireSuppressionTerminal" and ot == "sprinkler array":
        mp = head_map(maps)
        e["mapped"] = {"map": mp, "at": head_grid(e, b)}
    elif cls == "IfcFireSuppressionTerminal":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        e["parts"] = moved(head_parts(), cx, cy, b[5])
    elif cls == "IfcAirTerminal" and ot == "fan filter unit array":
        at = ffu_pack(e, b)
        if at:
            e["mapped"] = {"map": ffu_map(maps), "at": at}
        else:                                   # a strip too narrow for a unit: a blank panel in the grid
            e["parts"] = [block(*b, "filter_ceiling")]
    elif cls == "IfcAirTerminal" and ot == "fan filter unit":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        yaw = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 90
        e["parts"] = moved(ffu_parts(), cx, cy, b[2], yaw)
    elif cls == "IfcSensor" and ot == "sampling point":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        e["parts"] = [rod((cx, cy, b[2]), (cx, cy, b[5]), min(dims(b)[:2]) / 2, m)]
    elif cls == "IfcSensor" and ot == "spot smoke detector":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        r0 = min(dims(b)[:2]) / 2
        e["parts"] = [rod((cx, cy, b[2]), (cx, cy, b[5] - 0.03), r0 * 0.8, m), rod((cx, cy, b[5] - 0.03), (cx, cy, b[5]), r0, m)]
    elif cls == "IfcSanitaryTerminal" and pre == "TOILETPAN":
        e["parts"] = water_closet(C, e, b)
    elif cls == "IfcSanitaryTerminal" and pre == "WASHHANDBASIN":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        e["parts"] = [block(b[0], b[1], b[5] - 0.03, b[3], b[4], b[5], "ceramic"),
                      rod((cx, cy, b[2]), (cx, cy, b[5] - 0.03), min(dims(b)[:2]) / 2 - 0.045, "ceramic")]
    elif cls == "IfcSanitaryTerminal" and pre == "SHOWER":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        e["parts"] = [rod((cx, cy, b[2]), (cx, cy, b[5]), 0.025, "stainless"),
                      rod((cx, cy, b[5] - 0.1), (cx, cy, b[5] - 0.05), 0.15, "stainless"),
                      rod((cx + 0.3, cy, b[2] + 0.9), (cx + 0.3, cy, b[2] + 1.0), 0.15, "stainless")]
    elif cls == "IfcWasteTerminal":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        r0 = min(dims(b)[:2]) / 2
        e["parts"] = [rod((cx, cy, b[2]), (cx, cy, b[2] + 0.05), r0, m), rod((cx, cy, b[2] + 0.05), (cx, cy, b[5]), r0 * 0.6, m)]
    elif cls == "IfcFilter" or ot in ("campus tank", "campus stack"):
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        e["parts"] = [rod((cx, cy, b[2]), (cx, cy, b[5]), min(dims(b)[:2]) / 2, m)]
    elif cls == "IfcChiller":
        e["parts"] = chiller(b, m)
    elif cls == "IfcFan":
        e["parts"] = fan(b, m)
    elif ot == "hoist rail":
        (ax, ay, az), (cx, cy, _) = e["rail"]
        h = bmodel.RAIL_H
        e["parts"] = [part(("I", bmodel.RAIL_W, h, 0.008, 0.012), (ax, ay, az + h / 2), (cx - ax, cy - ay, 0.0),
                           math.hypot(cx - ax, cy - ay), m)]
    elif cls == "IfcTransportElement":
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        g = 0.2
        e["parts"] = [block(cx - 1.0, cy - 1.0, b[2] + 0.05, cx + 1.0, cy + 1.0, b[2] + 2.45, m)] + [
            block(x, y, b[2], x + 0.1, y + 0.1, b[5], "steel") for x in (b[0] + g, b[3] - g - 0.1) for y in (b[1] + g, b[4] - g - 0.1)]
    elif cls == "IfcStair" and ot == "fixed ladder":
        e["parts"] = ladder(b)
    elif cls == "IfcDoor":
        if (e["door"] or ())[3:4] == ("TRAPDOOR",):
            t = 0.05
            z1 = b[5] - 0.05
            e["parts"] = [block(b[0], b[1], b[2], b[3], b[1] + t, z1, "galvanised"), block(b[0], b[4] - t, b[2], b[3], b[4], z1, "galvanised"),
                          block(b[0], b[1] + t, b[2], b[0] + t, b[4] - t, z1, "galvanised"),
                          block(b[3] - t, b[1] + t, b[2], b[3], b[4] - t, z1, "galvanised"),
                          block(b[0], b[1], z1, b[3], b[4], b[5], "galvanised")]
        else:
            e["parts"], e["door_clear"] = door_parts(b)


def moved(parts, x, y, z, yaw=0):
    """Map parts (local, origin at the instance point) to world."""
    c, s = round(math.cos(math.radians(yaw)), 9), round(math.sin(math.radians(yaw)), 9)

    def R(v):
        return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])
    out = []
    for p in parts:
        o = R(p["o"])
        q = dict(p)
        q["o"] = (round(o[0] + x, 6), round(o[1] + y, 6), round(o[2] + z, 6))
        q["z"], q["x"] = R(p["z"]), R(p["x"])
        out.append(q)
    return out


def facade(b, m):
    k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1
    lo, hi = b[k], b[k + 3]
    n = math.ceil((hi - lo) / 1.2 - 1e-6)
    out = []
    for i in range(n):
        a0 = lo + i * 1.2
        a1 = min(a0 + 1.19, hi) if i < n - 1 else hi
        if k == 0:
            out.append(block(a0, b[1], b[2], a1, b[4], b[5], m))
        else:
            out.append(block(b[0], a0, b[2], b[3], a1, b[5], m))
    return out


def bracing(b, m):
    k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1
    t = 1 - k
    c = (b[t] + b[t + 3]) / 2
    i = 0.05

    def pt(u, z):
        return (u, c, z) if k == 0 else (c, u, z)
    return [rod(pt(b[k] + i, b[2] + i), pt(b[k + 3] - i, b[5] - i), 0.02, m),
            rod(pt(b[k] + i, b[5] - i), pt(b[k + 3] - i, b[2] + i), 0.02, m)]


def rebar(e, b, m):
    n = int(re.match(r"(\d+) bars", e["permit"]["Numbers"]).group(1))
    r0 = e["bar"][0] / 2
    out = []
    for layer, k in ((0, 0), (1, 1)):
        o = 1 - k
        z = b[2] + 0.0025 + r0 + layer * 2 * r0
        for i in range(n):
            c = b[o] + 0.02 + r0 + i * ((b[o + 3] - b[o]) - 0.04 - 2 * r0) / max(n - 1, 1)
            a, bb = [0.0, 0.0, z], [0.0, 0.0, z]
            a[k], bb[k] = b[k], b[k + 3]
            a[o] = bb[o] = c
            out.append(rod(tuple(a), tuple(bb), r0, m))
    return out


def valve(b):
    cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
    return [rod((cx, cy, b[2]), (cx, cy, b[5] - 0.06), 0.05, "stainless"),
            rod((cx, cy, b[5] - 0.06), (cx, cy, b[5] - 0.015), 0.018, "steel"),
            rod((cx, cy, b[5] - 0.015), (cx, cy, b[5]), 0.06, "alarm")]


def head_parts():
    return [part(("circle", 0.01), (0, 0, -0.07), UP, 0.07, "galvanised"),
            part(("circle", 0.024), (0, 0, -0.09), UP, 0.006, "galvanised")]


def head_map(maps):
    if "sprinkler head" not in maps:
        maps["sprinkler head"] = {"parts": head_parts()}
    return "sprinkler head"


def head_grid(e, b):
    m = re.match(r"(\d+) heads", e["permit"]["Numbers"])
    w, h = b[3] - b[0], b[4] - b[1]
    n = int(m.group(1)) if m else max(1, math.ceil(w * h / (130 * 0.3048 ** 2)))
    cols = max(1, min(n, round(math.sqrt(n * w / h)) if h > 0 else n))
    rows = math.ceil(n / cols)
    while (w / cols < 0.05 and cols > 1) or (h / rows < 0.05 and rows > 1):
        raise SystemExit(f"{e['key']}: no room for {n} heads")
    out = []
    for j in range(rows):
        for i in range(cols):
            if len(out) < n:
                out.append((round(b[0] + (i + 0.5) * w / cols, 6), round(b[1] + (j + 0.5) * h / rows, 6), b[5], 0))
    return out


def ffu_parts():
    return [block(-0.6, -0.3, 0.05, 0.6, 0.3, 0.35, "ffu_housing"), block(-0.59, -0.29, 0.0, 0.59, 0.29, 0.05, "filter_face")]


def ffu_map(maps):
    if "fan filter unit" not in maps:
        maps["fan filter unit"] = {"parts": ffu_parts()}
    return "fan filter unit"


def ffu_slots(b):
    """Every unit position a box holds, in rows, turned where that fits more."""
    W, H = b[3] - b[0], b[4] - b[1]

    def grid(x0, y0, w, h, uw, uh, yaw):
        cols, rows = int(w / uw + 1e-9), int(h / uh + 1e-9)
        return [(round(x0 + (i + 0.5) * uw, 6), round(y0 + (j + 0.5) * uh, 6), b[2], yaw) for j in range(rows) for i in range(cols)]
    options = []
    for uw, uh, yaw in ((1.2, 0.6, 0), (0.6, 1.2, 90)):
        main = grid(b[0], b[1], W, H, uw, uh, yaw)
        options.append(main)
        cols, rows = int(W / uw + 1e-9), int(H / uh + 1e-9)
        ow, oh, oyaw = uh, uw, 90 - yaw
        options.append(main + grid(b[0] + cols * uw, b[1], W - cols * uw, H, ow, oh, oyaw))
        options.append(main + grid(b[0], b[1] + rows * uh, W, H - rows * uh, ow, oh, oyaw))
    return max(options, key=len)


def ffu_pack(e, b):
    n = int(re.match(r"(\d+) units", e["permit"]["Numbers"]).group(1))
    slots = ffu_slots(b)
    if len(slots) < n:
        raise SystemExit(f"{e['key']}: {n} fan filter units do not fit in rows ({len(slots)})")
    return slots[:n]


def ffu_allocate(els):
    """Design development shared a space's units among its carved pieces by area, the remainder to the last piece, so
    some pieces held units they cannot fit. Keep each space's total and share it by what each piece holds in rows."""
    spaces = {}
    for e in els:
        if (e["otype"] or "") == "fan filter unit array":
            spaces.setdefault(e["key"].rsplit("/", 1)[0], []).append(e)
    for key, ps in spaces.items():
        rx = re.compile(r"^(\d+) units")
        n = sum(int(rx.match(p["permit"]["Numbers"]).group(1)) for p in ps)
        cap = [len(ffu_slots(p["box"])) for p in ps]
        if sum(cap) < n:
            raise SystemExit(f"bim: {key} needs {n} fan filter units and its pieces hold {sum(cap)}")
        share = [n * c // sum(cap) for c in cap]
        left = n - sum(share)
        order = sorted(range(len(ps)), key=lambda i: (-(n * cap[i] % sum(cap)), i))
        while left:
            for i in order:
                if left and share[i] < cap[i]:
                    share[i] += 1
                    left -= 1
        for p, m in zip(ps, share):
            p["permit"] = dict(p["permit"], Numbers=rx.sub(f"{m} units", p["permit"]["Numbers"]))


def water_closet(C, e, b):
    cid = e["key"].split("/")[2]
    core = next(c for c in C.P["toilets"]["cores"] if c["id"] == cid)
    back_hi = abs(core["box"][1]) < abs(core["box"][4])
    cx = (b[0] + b[3]) / 2
    if back_hi:
        cis = (cx - 0.225, b[4] - 0.18, b[2], cx + 0.225, b[4], b[5])
        pan = (cx - 0.19, b[4] - 0.18 - 0.52, b[2], cx + 0.19, b[4] - 0.18, b[2] + 0.4)
    else:
        cis = (cx - 0.225, b[1], b[2], cx + 0.225, b[1] + 0.18, b[5])
        pan = (cx - 0.19, b[1] + 0.18, b[2], cx + 0.19, b[1] + 0.18 + 0.52, b[2] + 0.4)
    return [block(*cis, "ceramic"), block(*pan, "ceramic")]


def chiller(b, m):
    k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1
    t = 1 - k
    w = b[t + 3] - b[t]
    r0 = min(w / 4 - 0.05, (b[5] - b[2] - 0.2) / 2)
    out = [block(b[0], b[1], b[2], b[3], b[4], b[2] + 0.2, "steel")]
    for f in (0.25, 0.75):
        c = [0.0, 0.0, b[2] + 0.2 + r0]
        c[t] = b[t] + f * w
        c[k] = b[k]
        z = [0.0, 0.0, 0.0]
        z[k] = 1.0
        out.append(part(("circle", r0), tuple(c), z, b[k + 3] - b[k], m))
    return out


def fan(b, m):
    d = dims(b)
    k = 0 if d[0] <= d[1] else 1           # the scroll's axis: the short side
    o = 1 - k
    r0 = min(d[o], d[2]) / 2
    c = [0.0, 0.0, b[2] + r0]
    c[o] = (b[o] + b[o + 3]) / 2
    a = list(c)
    a[k] = b[k]
    z = [0.0, 0.0, 0.0]
    z[k] = 1.0
    L = d[k]
    out = [part(("circle", r0), tuple(a), z, L * 0.65, m)]
    a2 = list(c)
    a2[k] = b[k] + L * 0.65
    out.append(part(("circle", min(0.4, r0 / 2)), tuple(a2), z, L * 0.35, "electrical"))
    return out


def ladder(b):
    k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1
    t = 1 - k
    c = (b[t] + b[t + 3]) / 2
    out = []
    for u in (b[k] + 0.02, b[k + 3] - 0.02):
        p0 = [0.0, 0.0, b[2]]
        p0[k], p0[t] = u, c
        p1 = list(p0)
        p1[2] = b[5]
        out.append(rod(tuple(p0), tuple(p1), 0.02, "galvanised"))
    z = b[2] + 0.3
    while z < b[5] - 0.1:
        p0, p1 = [0.0, 0.0, z], [0.0, 0.0, z]
        p0[k], p1[k] = b[k] + 0.04, b[k + 3] - 0.04
        p0[t] = p1[t] = c
        out.append(rod(tuple(p0), tuple(p1), 0.0125, "galvanised"))
        z += 0.3
    return out


def door_parts(b):
    k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1     # along the wall
    t = 1 - k
    lo, hi = b[k], b[k + 3]
    z0, z1 = b[2], b[5]

    def bx(a0, a1, t0, t1, za, zb):
        p = [0.0] * 6
        p[k], p[k + 3], p[t], p[t + 3], p[2], p[5] = a0, a1, t0, t1, za, zb
        return p
    tc = (b[t] + b[t + 3]) / 2
    parts = [block(*bx(lo, lo + FRAME, b[t], b[t + 3], z0, z1), "hm_frame"),
             block(*bx(hi - FRAME, hi, b[t], b[t + 3], z0, z1), "hm_frame"),
             block(*bx(lo + FRAME, hi - FRAME, b[t], b[t + 3], z1 - FRAME, z1), "hm_frame"),
             block(*bx(lo + FRAME + LEAF_GAP, hi - FRAME - LEAF_GAP, tc - LEAF / 2, tc + LEAF / 2, z0 + SILL, z1 - FRAME - LEAF_GAP),
                   "hm_door")]
    return parts, round(hi - lo - 2 * FRAME - 2 * LEAF_GAP, 4)


# ------------------------------------------------------------------ doors in openings

def _ov(a, b):
    return all(min(a[k + 3], b[k + 3]) - max(a[k], b[k]) > 1e-6 for k in range(3))


def _vol(a, b):
    v = 1.0
    for k in range(3):
        v *= max(0.0, min(a[k + 3], b[k + 3]) - max(a[k], b[k]))
    return v


def doors(C, els, walls):
    roofs = {e["bld"]: e for e in els if e["cls"] == "IfcSlab" and e["key"].endswith("/roof")}
    grid = {}
    for w in walls:
        for i in range(int(w["box"][0] // 12), int(w["box"][3] // 12) + 1):
            for j in range(int(w["box"][1] // 12), int(w["box"][4] // 12) + 1):
                grid.setdefault((i, j), []).append(w)
    for d in [e for e in els if e["cls"] == "IfcDoor"]:
        b = d["box"]
        if (d["door"] or ())[3:4] == ("TRAPDOOR",):
            host = roofs[d["bld"]]
            hb = host["box"]
            i = 0.05
            ob = (b[0] + i, b[1] + i, hb[2] - 0.005, b[3] - i, b[4] - i, hb[5] + 0.005)
            host.setdefault("voids", []).append({"key": d["key"], "box": ob, "fill": d["key"]})
            continue
        k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1
        t = 1 - k
        near = {id(w): w for i in range(int(b[0] // 12) - 1, int(b[3] // 12) + 2) for j in range(int(b[1] // 12) - 1, int(b[4] // 12) + 2)
                for w in grid.get((i, j), ())}.values()
        cands = sorted((w for w in near if _vol(b, w["box"]) > 1e-6), key=lambda w: (-_vol(b, w["box"]), w["key"]))
        if not cands:
            raise SystemExit(f"bim: no wall holds door {d['key']}")
        same = [w for w in near if w not in cands and (0 if (w["box"][3] - w["box"][0]) >= (w["box"][4] - w["box"][1]) else 1) == k
                and w["box"][k] <= b[k] + 1e-6 and w["box"][k + 3] >= b[k + 3] - 1e-6 and w["box"][2] <= b[2] + 1e-6
                and w["box"][5] >= b[5] - 1e-6 and (abs(w["box"][t] - b[t + 3]) < 0.011 or abs(w["box"][t + 3] - b[t]) < 0.011)]
        for n, w in enumerate(cands + same):
            hb = w["box"]
            ob = [0.0] * 6
            ob[k], ob[k + 3] = max(b[k], hb[k]), min(b[k + 3], hb[k + 3])     # a door across two panels cuts each
            ob[t], ob[t + 3] = hb[t] - 0.005, hb[t + 3] + 0.005
            ob[2], ob[5] = b[2], b[5]
            w.setdefault("voids", []).append({"key": d["key"] + ("" if n == 0 else f"/{n}"), "box": tuple(ob),
                                              "fill": d["key"] if n == 0 else None})


# ------------------------------------------------------------------ stairs

def stairs(C, els):
    cz = C.S["clean_z"]
    r = cz / RISERS
    for s in [e for e in els if e["cls"] == "IfcStair" and (e["otype"] or "") != "fixed ladder"]:
        sid = s["key"].split("/")[-1]
        x = next(x for x in C.P["exits"] if x["id"] == sid)
        b = s["box"]
        ym = (b[1] + b[4]) / 2
        lanes = {"lo": (b[1], ym - WELL / 2), "hi": (ym + WELL / 2, b[4])}
        if x["kind"] == "spine stair":
            xp = next((e for e in C.P["exits"] if e.get("from") == sid), None)
            side = xp["side"] if xp else 1
            lane_b = "hi" if side > 0 else "lo"
        else:
            lane_b = "lo" if x["side"] > 0 else "hi"          # the lane against the fab's facade
        lane_a = "lo" if lane_b == "hi" else "hi"
        if abs(b[3] - b[0] - FLOOR_LANDING - 21 * TREAD - MID_LANDING) > 1e-6:
            raise SystemExit(f"bim: stair {sid} is {b[3] - b[0]:.3f} m long; the flights and landings need 9.10 m")
        # the floor landings sit at the end the doors open from: east, or west where the fab ends first (mirrored)
        mine = [e for e in els if e["cls"] == "IfcDoor" and e["name"].endswith(" " + sid) and e["box"][2] > cz - 0.01]
        east = sum((d["box"][0] + d["box"][3]) / 2 for d in mine) / len(mine) >= (b[0] + b[3]) / 2
        sg = 1.0 if east else -1.0
        xe = b[3] - FLOOR_LANDING if east else b[0] + FLOOR_LANDING      # the floor landings' edge
        xw = xe - sg * 21 * TREAD                                         # the mid landing's edge
        h = cz / 2
        kids = []

        def child(name, cls, pre, parts, **kw):
            e = {"key": f"{s['key']}/{name}", "cls": cls, "name": f"{s['name']}, {name}", "box": b, "bld": s["bld"],
                 "storey": s["storey"], "otype": None, "pre": pre, "from": "assumed", "tool": None, "rail": None, "door": None,
                 "parent": s["key"], "permit": {"Stage": "BIM", "LOD": 400, "Review": "construction documents",
                                                "Numbers": kw.pop("numbers", "")}, "parts": parts}
            e.update(kw)
            kids.append(e)
        for nm, lane, x0, z0, west in (("flight A", lane_a, xe, 0.0, east), ("flight B", lane_b, xw, h, not east)):
            y0, y1 = lanes[lane]
            pts = [(0.0, 0.0)]
            for i in range(21):
                pts += [(i * TREAD, (i + 1) * r), ((i + 1) * TREAD, (i + 1) * r)]
            pts += [(21 * TREAD, 21 * r - 0.25), (0.25 * TREAD / r, 0.0)]
            pts = [pts[0]] + [p for i, p in enumerate(pts[1:], 1) if p != pts[i - 1]]
            # profile in the vertical plane: its x along the run, its y up; extruded across the lane
            run = (-1.0, 0.0, 0.0) if west else (1.0, 0.0, 0.0)
            ext = cross(run, UP)                                 # x cross up: the extrusion direction
            start_y = y0 if ext[1] > 0 else y1
            child(nm, "IfcStairFlight", "STRAIGHT", [part(("poly", [(round(u, 6), round(v, 6)) for u, v in pts]), (x0, start_y, z0), ext,
                                                          y1 - y0, "concrete", x=run)],
                  flight=(22, 21, r, TREAD), numbers=f"22 risers of {r * 1000:.1f} mm, treads {TREAD * 1000:.0f} mm")
            cos = math.cos(math.atan(r / TREAD))
            for rn, yy in (("left", y0 + 0.06), ("right", y1 - 0.06)):
                lift = RAIL_TOP - RAIL_R / cos
                a = (x0, yy, z0 + r + lift)
                bb = (x0 + run[0] * 20 * TREAD, yy, z0 + 21 * r + lift)
                child(f"{nm} handrail {rn}", "IfcRailing", "HANDRAIL", [rod(a, bb, RAIL_R, "steel")],
                      numbers=f"40 mm round, {RAIL_TOP} m over the nosings")
        mx0, mx1 = (b[0], xw) if east else (xw, b[3])
        fx0, fx1 = (xe, b[3]) if east else (b[0], xe)
        child("mid landing", "IfcSlab", "LANDING", [block(mx0, b[1], h - 0.2, mx1, b[4], h, "concrete")], numbers=f"{MID_LANDING} m deep")
        child("clean floor landing", "IfcSlab", "LANDING", [block(fx0, b[1], cz - 0.2, fx1, b[4], cz, "concrete")],
              numbers=f"{FLOOR_LANDING} m deep")
        s["nobody"] = True
        C.bim_extra += kids


def trusses(C, els):
    """Bay 09's construction documents replaced three trusses by their chords and verticals (S-110), with the diagonals
    on the truss detail (S-510). Each comes back as a truss that holds its members, with its diagonals added; every
    other truss gets chords, verticals and diagonals inside its own box."""
    groups = {}
    for e in els:
        ot = e["otype"] or ""
        if ot.startswith("truss member "):
            groups.setdefault(ot[len("truss member "):], []).append(e)
    for g, ms in sorted(groups.items()):
        lo = [min(m["box"][k] for m in ms) for k in range(3)]
        hi = [max(m["box"][k + 3] for m in ms) for k in range(3)]
        tk = f"bim/truss/{g}"
        C.bim_extra.append({"key": tk, "cls": "IfcBeam", "name": f"Roof truss {g}", "box": tuple(lo + hi), "bld": ms[0]["bld"],
                            "storey": ms[0]["storey"], "otype": "roof truss", "pre": "BEAM", "from": "assumed", "tool": None,
                            "rail": None, "door": None, "nobody": True,
                            "permit": {"Stage": "BIM", "LOD": 400, "Review": "construction documents",
                                       "Numbers": "chords, verticals and diagonals (S-110, S-510)"}})
        for m in ms:
            m["parent"] = tk
        verts = sorted((m for m in ms if m["pre"] == "MEMBER"), key=lambda m: (m["box"][0] + m["box"][1]))
        k = 0 if (hi[0] - lo[0]) >= (hi[1] - lo[1]) else 1
        for i, (a, b) in enumerate(zip(verts, verts[1:])):
            ab, bb = a["box"], b["box"]
            ca = [(ab[j] + ab[j + 3]) / 2 for j in range(2)]
            cb = [(bb[j] + bb[j + 3]) / 2 for j in range(2)]
            za, zb = (ab[2], ab[5]) if i % 2 == 0 else (ab[5], ab[2])
            p0, p1 = (ca[0], ca[1], za), (cb[0], cb[1], zb)
            v = [q - p for p, q in zip(p0, p1)]
            d = math.sqrt(sum(c * c for c in v))
            # pulled in so the square section's corners stay between the chords
            u = [c / d for c in v]
            pad = 0.12
            p0 = tuple(p0[j] + u[j] * pad for j in range(3))
            d -= 2 * pad
            C.bim_extra.append({"key": f"{tk}/diag/{i}", "cls": "IfcMember", "name": "Truss diagonal", "box": tuple(lo + hi),
                                "bld": ms[0]["bld"], "storey": ms[0]["storey"], "otype": f"truss member {g}", "pre": "MEMBER",
                                "from": "assumed", "tool": None, "rail": None, "door": None, "parent": tk,
                                "permit": {"Stage": "BIM", "LOD": 400, "Review": "construction documents", "Numbers": "diagonal (S-510)"},
                                "parts": [part(("rect", 0.16, 0.16), p0, v, d, "steel")]})
        _ = k
    for t in [e for e in els if (e["otype"] or "") == "roof truss"]:
        t["parts"] = truss_parts(t["box"])


def truss_parts(b):
    k = 0 if (b[3] - b[0]) >= (b[4] - b[1]) else 1
    t = 1 - k
    c = (b[t] + b[t + 3]) / 2
    ch, v = 0.3, 0.16

    def pt(u, z):
        return (u, c, z) if k == 0 else (c, u, z)
    z_ = [0.0, 0.0, 0.0]
    z_[k] = 1.0
    out = [part(("rect", ch, ch), pt(b[k], b[2] + ch / 2), z_, b[k + 3] - b[k], "steel"),
           part(("rect", ch, ch), pt(b[k], b[5] - ch / 2), z_, b[k + 3] - b[k], "steel")]
    n = 21
    us = [b[k] + v / 2 + i * (b[k + 3] - b[k] - v) / (n - 1) for i in range(n)]
    za, zb = b[2] + ch, b[5] - ch
    for u in us:
        out.append(block(*((u - v / 2, c - v / 2) if k == 0 else (c - v / 2, u - v / 2)), za,
                         *((u + v / 2, c + v / 2) if k == 0 else (c + v / 2, u + v / 2)), zb, "steel"))
    for i in range(n - 1):
        a, bb = (us[i], za), (us[i + 1], zb)
        if i % 2:
            a, bb = (us[i], zb), (us[i + 1], za)
        out.append(part(("rect", v, v), pt(*a), [p1 - p0 for p0, p1 in zip(pt(*a), pt(*bb))],
                        math.dist(pt(*a), pt(*bb)), "steel"))
    return out


# ------------------------------------------------------------------ slabs: cores, bay 09, pedestals

def slab_openings(C, els):
    floors = [e for e in els if e["cls"] in ("IfcSlab", "IfcCovering") and e["pre"] in ("FLOOR", "FLOORING") and not e["otype"]
              and not e["key"].startswith("permit/")]
    cores = [e for e in els if (e["cls"] == "IfcStair" and (e["otype"] or "") != "fixed ladder") or e["cls"] == "IfcTransportElement"]
    for s in cores:
        b = s["box"]
        g = 0.2 if s["cls"] == "IfcStair" else 0.0
        for f in floors:
            fb = f["box"]
            if b[2] < fb[2] and b[5] > fb[5] and _ov(b, fb):
                f.setdefault("voids", []).append({"key": f"{f['key']}/core/{s['key']}",
                                                  "box": (b[0] - g, b[1] - g, fb[2] - 0.005, b[3] + g, b[4] + g, fb[5] + 0.005)})
    for otype, cls in (("raised floor tile", "IfcCovering"), ("waffle rib", "IfcSlab")):
        ms = [e for e in els if (e["otype"] or "") == otype]
        if not ms:
            continue
        lo = [min(m["box"][k] for m in ms) for k in range(2)]
        hi = [max(m["box"][k + 3] for m in ms) for k in range(2)]
        for f in floors:
            fb = f["box"]
            if f["cls"] == cls and fb[0] <= lo[0] and fb[3] >= hi[0] and f["bld"] == ms[0]["bld"]:
                z0, z1 = (fb[5] - TILE_T - 0.005, fb[5] + 0.005) if cls == "IfcCovering" else (fb[2] - 0.005, fb[5] + 0.005)
                f.setdefault("voids", []).append({"key": f"{f['key']}/bay09/{otype}", "box": (lo[0], lo[1], z0, hi[0], hi[1], z1)})


def pedestal_parts(H):
    return [block(-0.05, -0.05, 0.0, 0.05, 0.05, 0.005, "pedestal"), part(("circle", 0.0125), (0, 0, 0.005), UP, H - 0.01, "pedestal"),
            block(-0.05, -0.05, H - 0.005, 0.05, 0.05, H, "pedestal")]


def pedestals(C, els, maps):
    rf = C.fl["raised floor"]
    H = round(rf["z1"] - rf["z0"] - TILE_T, 6)
    maps["raised floor pedestal"] = {"parts": pedestal_parts(H)}
    z0, z1 = rf["z0"], rf["z0"] + H
    block_ = [e["box"] for e in els if e["box"] is not None and e["cls"] != "IfcSpace" and e["box"][2] < z1 - 1e-4 and e["box"][5] > z0 + 1e-4
              and not (e["cls"] == "IfcCovering" and e["pre"] == "FLOORING") and not (e["cls"] == "IfcSlab" and not e["key"].startswith("permit/"))]
    grid = {}
    for bb in block_:
        for i in range(int(bb[0] // 3), int(bb[3] // 3) + 1):
            for j in range(int(bb[1] // 3), int(bb[4] // 3) + 1):
                grid.setdefault((i, j), []).append(bb)
    for f in [e for e in els if e["cls"] == "IfcCovering" and e["pre"] == "FLOORING" and not e["otype"] and not e["key"].startswith("permit/")]:
        fb = f["box"]
        at = []
        nx, ny = math.floor((fb[3] - fb[0]) / PITCH + 1e-6), math.floor((fb[4] - fb[1]) / PITCH + 1e-6)
        for i in range(1, nx):
            x = round(fb[0] + i * PITCH, 6)
            for j in range(1, ny):
                y = round(fb[1] + j * PITCH, 6)
                pb = (x - 0.05, y - 0.05, z0, x + 0.05, y + 0.05, z1)
                if any(_ov(pb, bb) for bb in grid.get((int(x // 3), int(y // 3)), ())):
                    continue
                at.append((x, y, z0, 0))
        k = f["key"].split("/")[0]
        C.bim_extra.append({"key": f"bim/pedestals/{k}", "cls": "IfcBuildingElementPart", "name": f"Raised floor pedestals {k}",
                            "box": (fb[0], fb[1], z0, fb[3], fb[4], z1), "bld": f["bld"], "storey": f["storey"],
                            "otype": "raised floor pedestals", "pre": "USERDEFINED", "from": "assumed", "tool": None, "rail": None,
                            "door": None, "permit": {"Stage": "BIM", "LOD": 400, "Review": "construction documents",
                                                     "Numbers": f"{len(at)} pedestals on the {PITCH * 1000:.0f} mm grid (A-551)"},
                            "mapped": {"map": "raised floor pedestal", "at": at}})
