"""Architectural construction documents sheets for the whole fab (docs/ARCH-DOCS.md, AD3 to AD8): general notes, the
site, dimensioned floor plans, reflected ceiling and roof plans, elevations, wall sections, enlarged plans, interior
elevations, schedules and details. Drawn from the same model as the IFC; every sheet carries the truth line and NOT FOR
CONSTRUCTION (the frame in sheets.py). Details and interior elevations are diagrammatic, with their dimensions.
"""

import math

import blueprint as bp
from blueprint import GREY, INK, RED, Map, dim, line, rect, text
from ctx import FT
from dd_sheets import STYLE, levels, window
from profiles import f
from sheets import AMBER, BLUE, GREEN, SCALES, boxes, notes, scale_label, table

SHEETS = [
    ("A-001", "General notes, abbreviations and symbols"), ("A-100", "Architectural site plan"),
    ("A-111", "P1 support floor plan"), ("A-112", "P1 clean floor plan"), ("A-121", "P2 support floor plan"),
    ("A-122", "P2 clean floor plan"), ("A-131", "P1 reflected ceiling plan"), ("A-132", "P2 reflected ceiling plan"),
    ("A-141", "P1 roof plan"), ("A-142", "P2 roof plan"), ("A-202", "Exterior elevations, materials and levels"),
    ("A-311", "Wall sections"), ("A-411", "Spine stairs"), ("A-412", "Facade stairs"), ("A-413", "Gowning rooms"),
    ("A-414", "Gas rooms and chemical dispense rooms"), ("A-521", "Door and frame details"), ("A-531", "Roof details"),
    ("A-541", "Cleanroom ceiling details"), ("A-551", "Raised floor and penetration details"), ("A-611", "Door schedule, part 1"),
    ("A-612", "Door schedule, part 2"), ("A-613", "Room finish schedule"), ("A-614", "Hardware sets"),
    ("A-701", "Toilet room interior elevations"), ("A-702", "Gowning room interior elevations"),
]
RATIO = 384
ZB = {"support floor": (0.0, 3.0), "clean floor": None}


def everything(C):
    return [e for e in C.M["elements"] + C.new if e["box"] is not None and not e["key"].startswith("campus/")]


def band(C, floor):
    cz = C.S["clean_z"]
    return (0.05, 2.5) if floor == "support floor" else (cz + 0.05, cz + 2.5)


def grid_marks(C, M, d, b):
    """Grid lines with bubbles (numbers along x, letters along y) and the dimension strings."""
    o = []
    xs, ys = d["grid_x"], d["grid_y"]
    top, left = M(b["x0"], b["y1"])
    bot, right = M(b["x1"], b["y0"])
    for i, x in enumerate(xs[1:-1], start=1):
        sx, _ = M(x, 0)
        o.append(line(sx, left - 18, sx, right + 4, GREY, 0.08, "4 1 1 1"))
        o.append(f'<circle cx="{f(sx)}" cy="{f(left - 21)}" r="2.6" fill="#fff" stroke="{INK}" stroke-width="0.2"/>')
        o.append(text(sx, left - 20.1, str(i), 2.2, "middle", "bold"))
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    for i, y in enumerate(sorted(ys[1:-1], reverse=True)):
        _, sy = M(0, y)
        o.append(line(top - 18, sy, bot + 4, sy, GREY, 0.08, "4 1 1 1"))
        o.append(f'<circle cx="{f(top - 21)}" cy="{f(sy)}" r="2.6" fill="#fff" stroke="{INK}" stroke-width="0.2"/>')
        o.append(text(top - 21, sy + 0.8, letters[i % len(letters)], 2.2, "middle", "bold"))
    # strings: the grid along the top, the overall above it; the same down the left
    for a, c in zip(xs, xs[1:]):
        (x1, _), (x2, _) = M(a, 0), M(c, 0)
        o.append(dim(x1, left - 6, x2, left - 6, bp.PR.dist(c - a, 1), off=0, size=1.6))
    (x1, _), (x2, _) = M(xs[0], 0), M(xs[-1], 0)
    o.append(dim(x1, left - 12, x2, left - 12, bp.PR.dist(xs[-1] - xs[0], 1) + " overall", off=0, size=2.0))
    yy = sorted(ys)
    for a, c in zip(yy, yy[1:]):
        (_, y1), (_, y2) = M(0, c), M(0, a)
        o.append(dim(top - 6, y1, top - 6, y2, bp.PR.dist(c - a, 1), off=0, size=1.6))
    (_, y1), (_, y2) = M(0, yy[-1]), M(0, yy[0])
    o.append(dim(top - 12, y1, top - 12, y2, bp.PR.dist(yy[-1] - yy[0], 1) + " overall", off=0, size=2.0))
    return "".join(o)


def floor_plan(C, sid):
    A = C.P["arch"]
    d = A["dims"][sid]
    k, floor = d["building"], d["floor"]
    p = C.keys.index(k)
    b = C.blds[p]
    SCALES[sid] = scale_label(RATIO)
    ox, oy = bp.AX0 + 34, bp.AY0 + 44
    M = Map(RATIO, b["x0"], b["y1"], ox, oy)
    z0, z1 = band(C, floor)
    inz = lambda e: e["box"][2] < z1 and e["box"][5] > z0 and e["bld"] == p
    allx = [e for e in everything(C) if inz(e)]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, f"{k} {floor.upper()} PLAN: dimensioned, rooms and doors numbered", 4.2, weight="bold")]
    o.append(grid_marks(C, M, d, b))
    order = [("IfcSpace", "#9aa3b2", "#f7f8fa", 0.08), ("IfcBuildingElementProxy", GREY, "#eceef1", 0.04), ("IfcColumn", INK, INK, 0.04),
             ("IfcStair", BLUE, "#e3ecf7", 0.12), ("IfcTransportElement", INK, "#d8d2e8", 0.15), ("IfcWall", INK, "#555", 0.06),
             ("IfcSanitaryTerminal", GREEN, "#e6f4ea", 0.04), ("IfcDoor", RED, RED, 0.1)]
    for cls, st, fi, sw in order:
        sel = [e["box"] for e in allx if e["cls"] == cls and not (cls == "IfcSpace" and e["key"].startswith("bay/") and floor == "support floor")]
        o.append(boxes(M, sel, st, fi, sw))
    x0, y0, w, h = M.box(b["x0"], b["y0"], b["x1"], b["y1"])
    o.append(rect(x0, y0, w, h, INK, 0.45))
    for r in A["rooms"]:
        if r["building"] != k or r["storey"] != floor:
            continue
        e = next((e for e in allx if e["key"] == r["key"]), None)
        if e is None:
            continue
        cx, cy = M((e["box"][0] + e["box"][3]) / 2, (e["box"][1] + e["box"][4]) / 2)
        o.append(text(cx, cy, r["no"], 1.5, "middle", "bold", fill=BLUE))
    for dr in A["doors"]:
        if dr["building"] != k or dr["floor"] != floor:
            continue
        sx, sy = M(dr["x"], dr["y"])
        o.append(text(sx + 0.8, sy - 0.6, dr["no"], 1.05, fill=RED))
    t, _ = notes(bp.AX0 + 34 + w + 30, bp.AY0 + 44, [
        f"Overall {bp.PR.dist(d['overall_x_m'])} x {bp.PR.dist(d['overall_y_m'])}; grid strings along the top and the left add up to "
        "the overall dimensions.",
        "Blue numbers: rooms (A-613). Red numbers: doors (A-611, A-612). Grey: tools (the concept model).",
        "Wall types on A-501; enlarged plans on A-401, A-402 and A-411 to A-414.",
        "Dimensions are to grid lines and to the outside face of the building (assumed); verify on site.",
    ], 2.5, 60, "NOTES")
    o.append(t)
    return "".join(o)


def rcp(C, sid, p):
    k = C.keys[p]
    b = C.blds[p]
    SCALES[sid] = scale_label(RATIO)
    M = Map(RATIO, b["x0"], b["y1"], bp.AX0 + 34, bp.AY0 + 44)
    o = [text(bp.AX0 + 10, bp.AY0 + 10, f"{k} REFLECTED CEILING PLAN, CLEAN FLOOR: fan filter coverage, class and ceiling height", 4.2, weight="bold")]
    x0, y0, w, h = M.box(b["x0"], b["y0"], b["x1"], b["y1"])
    o.append(rect(x0, y0, w, h, INK, 0.45, "#ffffff"))
    air = {a["bay"]: a for a in C.P["air"]["bays"]}
    ceil = C.fl["cleanroom"]["z1"]
    for i, B in enumerate(C.S["bays"]):
        if B["phase"] != p:
            continue
        a = air.get(f"bay {i + 1:02d}")
        if not a:
            continue
        bx, by, bw, bh = M.box(B["x0"], B["y0"], B["x1"], B["y1"])
        g = int(250 - 120 * a["coverage"])
        o.append(rect(bx, by, bw, bh, GREY, 0.1, f"#{g:02x}{min(255, g + 20):02x}{min(255, g + 30):02x}"))
        cx, cy = bx + bw / 2, by + bh / 2
        o.append(text(cx, cy - 1.5, f"ISO {a['iso_class']}", 1.6, "middle", "bold"))
        o.append(text(cx, cy + 1.0, f"{a['coverage']:.0%}", 1.5, "middle"))
        o.append(text(cx, cy + 3.3, bp.PR.level(ceil), 1.3, "middle", fill=GREY))
    o.append(boxes(M, [e["box"] for e in C.new if (e["otype"] or "") == "fan filter unit" and e["bld"] == p], "#5a8f6a", "none", 0.02))
    t, _ = notes(bp.AX0 + 34 + w + 30, bp.AY0 + 44, [
        f"Ceiling (underside of the fan filter grid) at {bp.PR.level(ceil)} throughout the clean floor.",
        "Each bay shaded by its fan filter coverage, with its class (assumed by kind; ISO 14644-1 not read).",
        "Bay 09 drawn unit by unit (A-130); elsewhere arrays by count.",
        "Sprinklers, sampling ports, lights and grilles on the trade sheets.",
    ], 2.5, 60, "NOTES")
    o.append(t)
    return "".join(o)


def roof_plan(C, sid, p):
    k = C.keys[p]
    b = C.blds[p]
    R = C.P["arch"]["roof"][k]
    SCALES[sid] = scale_label(RATIO)
    M = Map(RATIO, b["x0"], b["y1"], bp.AX0 + 34, bp.AY0 + 44)
    rz = C.fl["roof"]["z1"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, f"{k} ROOF PLAN: parapets, drains, hatch, plant on curbs", 4.2, weight="bold")]
    x0, y0, w, h = M.box(b["x0"], b["y0"], b["x1"], b["y1"])
    o.append(rect(x0, y0, w, h, INK, 0.45, "#f6f6f3"))
    on = [e for e in C.new if e["bld"] == p and e["box"][2] >= rz - 0.01]
    o.append(boxes(M, [e["box"] for e in on if e["name"].startswith("Parapet")], INK, "#777", 0.05))
    o.append(boxes(M, [e["box"] for e in on if (e["otype"] or "") == "equipment curb"], AMBER, "#fbefd9", 0.1))
    o.append(boxes(M, [e["box"] for e in on if e["cls"] == "IfcUnitaryEquipment"], INK, "#f2e6c9", 0.1))
    for e in on:
        if e["cls"] == "IfcWasteTerminal":
            cx, cy = M((e["box"][0] + e["box"][3]) / 2, (e["box"][1] + e["box"][4]) / 2)
            o.append(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="1.1" fill="none" stroke="{BLUE}" stroke-width="0.3"/>')
            for dx, dy in ((-6, 0), (6, 0), (0, -6), (0, 6)):
                o.append(line(cx + dx, cy + dy, cx + dx * 0.35, cy + dy * 0.35, BLUE, 0.15))
        if e["cls"] == "IfcDoor":
            o.append(boxes(M, [e["box"]], RED, "#f6d5d3", 0.2))
    t, _ = notes(bp.AX0 + 34 + w + 30, bp.AY0 + 44, [
        f"Roof {R['area_m2']:,.0f} m2 at {bp.PR.level(rz)}: {R['membrane']}; {R['slope']} (arrows).",
        f"{R['drains']} roof drains (blue), at most {R['drain_area_m2_each']:.0f} m2 each (assumed); sizing and overflow per IPC "
        "chapter 11, not read: licensed review.",
        f"Parapet {R['parapet_m']} m with a metal coping; {R['hatches']} roof hatch (red) over a ladder from the air space.",
        f"{R['plant_units']} make-up air units on insulated curbs (tan); see M-602.",
    ], 2.5, 60, "NOTES")
    o.append(t)
    return "".join(o)


def a001(C):
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "GENERAL NOTES, ABBREVIATIONS AND SYMBOLS", 4.2, weight="bold")]
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 22, [
        "1. These architectural documents cover both fab buildings of the Fab Gym campus: a gigafab-style layout of our own design on "
        "the SMT2020 model. Not a real fab. NOT FOR CONSTRUCTION.",
        "2. Codes: the 2024 IBC and IFC as published, for a hypothetical jurisdiction; the IPC and IMC 2024 where cited; NFPA 13-2022, "
        "72-2022 and 70-2023 where cited. Standards not read are listed on G-002 and their items stay open.",
        "3. Dimensions are to grid lines, the face of structure or the face of the building, as noted. Do not scale the drawings.",
        "4. Levels are above the support floor slab (+0.00 / EL. 0'-0\").",
        "5. Every number is cited, computed or assumed; assumed numbers are marked and listed on G-003.",
        "6. Products are named by kind and performance, never by maker (specifications).",
        "7. Lithography bay 09 is drawn to fabrication detail (A-110 to FA-110); the other bays follow it.",
        "8. A permit needs a real site and the seals of an architect and engineers licensed where the fab is built.",
    ], 2.7, 110, "GENERAL NOTES")
    o.append(t)
    rows = [["AFF", "above finished floor"], ["CH", "ceiling height"], ["CL", "centre line"], ["ECS", "emergency control station"],
            ["EL", "elevation (level)"], ["FFU", "fan filter unit"], ["GB", "gypsum board"], ["HM", "hollow metal"],
            ["HPM", "hazardous production material"], ["HW", "hardware set"], ["IMP", "insulated metal panel"],
            ["ISO", "cleanliness class (ISO 14644-1, not read)"], ["LOD", "level of development"], ["RF", "raised floor"],
            ["SC", "sealed concrete"], ["TYP", "typical"], ["UNO", "unless noted otherwise"], ["VMB", "valve manifold box"],
            ["WP", "wall panel"], ["WT", "wall type (A-501)"], ["XP", "exit passageway"]]
    tb, _ = table(bp.AX0 + 360, bp.AY0 + 22, [("Abbreviation", 26), ("Meaning", 80)], rows, 2.5)
    o.append(tb)
    sx, sy = bp.AX0 + 520, bp.AY0 + 26
    o.append(text(sx, sy - 4, "SYMBOLS", 3.3, weight="bold"))
    sym = [("grid line and bubble", lambda x, y: f'<circle cx="{f(x)}" cy="{f(y)}" r="3" fill="#fff" stroke="{INK}" stroke-width="0.25"/>' + text(x, y + 1, "4", 2.4, "middle", "bold")),
           ("room number", lambda x, y: text(x, y + 1, "P1.C012", 2.2, "middle", "bold", fill=BLUE)),
           ("door number", lambda x, y: text(x, y + 1, "P1-S-014", 2.0, "middle", fill=RED)),
           ("section or elevation mark", lambda x, y: f'<circle cx="{f(x)}" cy="{f(y)}" r="3" fill="#fff" stroke="{INK}" stroke-width="0.25"/>' + line(x - 3, y, x + 3, y, INK, 0.2) + text(x, y - 0.6, "2", 1.6, "middle") + text(x, y + 2.4, "A-311", 1.3, "middle")),
           ("roof drain", lambda x, y: f'<circle cx="{f(x)}" cy="{f(y)}" r="1.5" fill="none" stroke="{BLUE}" stroke-width="0.3"/>'),
           ("dimension", lambda x, y: dim(x - 8, y, x + 8, y, "12'-0\"", off=0, size=1.8))]
    for n, (lab, fn) in enumerate(sym):
        yy = sy + n * 14
        o.append(fn(sx + 10, yy))
        o.append(text(sx + 26, yy + 1, lab, 2.5))
    return "".join(o)


def a100(C):
    SCALES["A-100"] = scale_label(1500)
    lot = C.permit["site"]["lot"]
    lx0, lx1 = min(q[0] for q in lot), max(q[0] for q in lot)
    ly0, ly1 = min(q[1] for q in lot), max(q[1] for q in lot)
    M = Map(1500, lx0 - 10, ly1 + 10, bp.AX0 + 20, bp.AY0 + 25)
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "ARCHITECTURAL SITE PLAN: the fab buildings dimensioned on the hypothetical lot", 4.2, weight="bold")]
    x, y, w, h = M.box(lx0, ly0, lx1, ly1)
    o.append(rect(x, y, w, h, RED, 0.4, "none", ' stroke-dasharray="4 1.5 1 1.5"'))
    for c in C.S["campus"]:
        bx, by, bw, bh = M.box(c["x0"], c["y0"], c["x1"], c["y1"])
        o.append(rect(bx, by, bw, bh, INK, 0.2, {"fab": "#dfe6ef", "road": "#d9d9d9", "parking": "#efefef"}.get(c["kind"], "#f4f1ea")))
    for p, b in enumerate(C.blds):
        (x1, y1), (x2, _) = M(b["x0"], b["y1"]), M(b["x1"], b["y1"])
        o.append(dim(x1, y1 - 4, x2, y1 - 4, bp.PR.dist(b["x1"] - b["x0"]), off=0, size=1.8))
        (_, ya), (_, yb) = M(b["x0"], b["y1"]), M(b["x0"], b["y0"])
        o.append(dim(x1 - 4, ya, x1 - 4, yb, bp.PR.dist(b["y1"] - b["y0"]), off=0, size=1.8))
        o.append(text((x1 + x2) / 2, (ya + yb) / 2, C.keys[p], 3, "middle", "bold"))
    b = C.blds[0]
    (sx, sy), (tx, ty) = M(b["x0"] + 20, b["y1"]), M(b["x0"] + 20, ly1)
    o.append(dim(sx - 0, ty, sx, sy, bp.PR.dist(ly1 - b["y1"]), off=0, size=1.8))
    t, _ = notes(bp.AX0 + 620, bp.AY0 + 30, [
        "The lot is hypothetical (assumed), 20 m outside the campus roads; no survey, no zoning.",
        "Building dimensions to the outside face; distances to the lot line shown for phase 1 north.",
        "Site values (seismic) for a point near Salem in the Willamette Valley, Oregon (S-510); no parcel is meant.",
    ], 2.6, 80, "NOTES")
    o.append(t)
    return "".join(o)


def a202(C):
    SCALES["A-202"] = scale_label(RATIO)
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "EXTERIOR ELEVATIONS: materials and levels", 4.2, weight="bold")]
    top = C.fl["roof"]["z1"] + 1.0
    y = bp.AY0 + 26
    for p, b in enumerate(C.blds):
        for face in ("north", "south"):
            M = Map(RATIO, 0, top + 1, bp.AX0 + 40, y)
            W = b["x1"] - b["x0"]
            u = (lambda x: b["x1"] - x) if face == "north" else (lambda x: x - b["x0"])
            x0, y0, w, h = M.box(0, 0, W, C.fl["roof"]["z1"])
            o.append(rect(x0, y0, w, h, INK, 0.3, "#f2f4f6"))
            for xx in [v * 1.2 for v in range(1, int(W / 1.2))]:
                a, c = M(xx, 0), M(xx, C.fl["roof"]["z1"])
                o.append(line(a[0], a[1], c[0], c[1], "#c5cad3", 0.04))
            px0, py0, pw, ph = M.box(0, C.fl["roof"]["z1"], W, top)
            o.append(rect(px0, py0, pw, ph, INK, 0.2, "#d9dde3"))
            sgn = 1 if face == "north" else -1
            for e in C.new:
                bx = e["box"]
                if e["bld"] != p or not ((bx[4] >= b["y1"] - 0.45) if sgn > 0 else (bx[1] <= b["y0"] + 0.45)):
                    continue
                if e["cls"] not in ("IfcDoor", "IfcStair", "IfcMember"):
                    continue
                ua, ub = sorted((u(bx[0]), u(bx[3])))
                xx, yy, ww, hh = M.box(ua, bx[2], ub, min(bx[5], top))
                st, fi = {"IfcDoor": (RED, "#f6d5d3"), "IfcStair": (BLUE, "#e3ecf7"), "IfcMember": (RED, "none")}[e["cls"]]
                o.append(rect(xx, yy, max(ww, 0.3), max(hh, 0.3), st, 0.15, fi))
            for z, lab in ((0.0, "support floor"), (C.S["clean_z"], "clean floor"), (C.fl["roof"]["z1"], "roof"), (top, "parapet")):
                a = M(0, z)
                o.append(line(a[0] - 8, a[1], a[0], a[1], INK, 0.15))
                o.append(text(a[0] - 9, a[1] + 0.7, f"{bp.PR.level(z)}", 1.6, "end"))
            o.append(text(bp.AX0 + 40, y - 2, f"{C.keys[p]} {face.upper()} ELEVATION", 2.8, weight="bold"))
            y += (top + 1) * 1000 / RATIO + 14
    t, _ = notes(bp.AX0 + 760, bp.AY0 + 26, [
        "IMP-1: insulated metal wall panels, 1.2 m modules (grey joints), 150 mm, mineral wool core where the wall is rated (assumed).",
        "PC-1: metal parapet coping. Red: exit doors, hollow metal (A-611) and braced bays. Blue: facade stair towers, IMP-1.",
        "Exterior wall ratings follow IBC 705 (fire separation distance), not read: licensed review.",
    ], 2.5, 70, "MATERIALS")
    o.append(t)
    return "".join(o)


def a311(C):
    SCALES["A-311"] = scale_label(96)
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "WALL SECTIONS: facade, spine, chase (dimensioned to the levels)", 4.2, weight="bold")]
    L = {fl["name"]: (fl["z0"], fl["z1"]) for fl in C.S["floors"]}
    rz = L["roof"][1]
    cols = [("1 FACADE", 0), ("2 SPINE", 1), ("3 CHASE", 2)]
    for title, n in cols:
        ox = bp.AX0 + 30 + n * 300
        M = Map(96, -4, rz + 2.0, ox, bp.AY0 + 26)
        o.append(text(ox, bp.AY0 + 22, title, 3.0, weight="bold"))
        for nm, (z0, z1) in L.items():
            if nm in ("waffle slab", "raised floor", "roof"):
                x, y, w, h = M.box(-3, z0, 6, z1)
                o.append(rect(x, y, w, h, INK, 0.2, {"waffle slab": "#c9ced6", "raised floor": "#e8eaee", "roof": "#c9ced6"}[nm]))
            a = M(-3.6, z0)
            o.append(text(a[0] - 1, a[1] + 0.8, f"{bp.PR.level(z0)} {nm}", 1.7, "end"))
        ft = M.box(-1.5, -1.2, 1.5, 0)
        o.append(rect(*ft, INK, 0.2, "#e9e3d7"))
        ceil = C.fl["cleanroom"]["z1"]
        x, y, w, h = M.box(-3, ceil, 6, ceil + 0.1)
        o.append(rect(x, y, w, h, "#5a8f6a", 0.2, "#e6f4ea"))
        if n == 0:
            x, y, w, h = M.box(-0.15, 0, 0.0, rz + 1.0)
            o.append(rect(x, y, w, h, INK, 0.2, "#777"))
            o.append(text(M(0.2, rz + 0.5)[0], M(0.2, rz + 0.5)[1], "IMP-1 to the parapet, coping PC-1", 1.8))
        if n == 1:
            x, y, w, h = M.box(-1.5, C.S["clean_z"], 1.5, 9.9)
            o.append(rect(x, y, w, h, BLUE, 0.2, "#e3ecf7"))
            o.append(text(M(1.7, 9.4)[0], M(1.7, 9.4)[1], "stair core, lid +9.90 under the hoist path", 1.8))
            env = [e for e in __import__("arch").rail_envelopes(C.S)][0]
            x, y, w, h = M.box(-0.5, env[2], 0.5, env[5])
            o.append(rect(x, y, w, h, GREY, 0.2, "none", ' stroke-dasharray="2 1"'))
        if n == 2:
            x, y, w, h = M.box(1.6, C.S["clean_z"], 1.7, 12.7)
            o.append(rect(x, y, w, h, RED, 0.2, RED))
            x, y, w, h = M.box(1.7, C.S["clean_z"], 5.0, C.S["clean_z"] + 2.6)
            o.append(rect(x, y, w, h, GREY, 0.2, "#eceef1"))
            o.append(text(M(-2.8, 12.4)[0], M(-2.8, 12.4)[1], "chase 1.6 m; partition to +12.70, 0.30 below the ceiling", 1.8))
        for z0, z1 in ((0.0, C.S["clean_z"]), (C.S["clean_z"], ceil), (ceil, rz)):
            (xa, ya), (xb, yb) = M(5.5, z1), M(5.5, z0)
            o.append(dim(xa, ya, xb, yb, bp.PR.dist(z1 - z0), off=4, size=1.7))
    return "".join(o)


def enlarged(C, sid, title, picks, ratio, half, zlo, zhi):
    SCALES[sid] = scale_label(ratio)
    side = 2 * half * 1000 / ratio
    o = [text(bp.AX0 + 10, bp.AY0 + 8, title, 4.2, weight="bold")]
    per = max(1, int((bp.AX1 - bp.AX0 - 10) // (side + 14)))
    for n, (lab, cx, cy, z0, z1) in enumerate(picks):
        ox = bp.AX0 + 10 + (n % per) * (side + 14)
        oy = bp.AY0 + 24 + (n // per) * (side + 22)
        M = Map(ratio, cx - half, cy + half, ox, oy)
        o.append(text(ox, oy - 4, lab, 2.8, weight="bold"))
        o.append(window(C, M, cx - half, cy - half, cx + half, cy + half, z0, z1, side, f"{sid}v{n}", ox, oy))
        (x1, y1), (x2, _) = (ox, oy + side + 4), (ox + side, oy + side + 4)
        o.append(dim(x1, y1, x2, y1, bp.PR.dist(2 * half), off=0, size=1.6))
    return "".join(o), side


def a411(C, kind, sid):
    ex = [x for x in C.P["exits"] if x["kind"] == kind]
    cz = C.S["clean_z"]
    picks = []
    for x in ex[:6]:
        stair = next(e for e in C.new if e["cls"] == "IfcStair" and x["id"] in e["key"])
        bx = stair["box"]
        picks.append((f"{x['id']}, clean floor", (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, cz + 0.05, cz + 2.5))
    o, side = enlarged(C, sid, f"{'SPINE' if kind == 'spine stair' else 'FACADE'} STAIRS: enlarged plans, a section, every stair listed", picks, 192, 8.0,
                       0, 0)
    rows = [[x["id"], x["building"], f"{x['width_in']} in", f"{x['rating_h']} h", x.get("door_width_in", ""), ", ".join(x["serves"])] for x in ex]
    tb, _ = table(bp.AX0 + 10, bp.AY0 + 24 + 2 * (side + 22) + 8, [("Stair", 30), ("Bldg", 12), ("Width", 16), ("Enclosure", 18),
                                                                  ("Door in", 16), ("Serves", 60)], rows, 2.3)
    o += tb
    # a section through the two flights (diagrammatic, dimensioned)
    sx, sy = bp.AX0 + 420, bp.AY0 + 300
    M = Map(96, 0, 10.5, sx, sy)
    o += text(sx, sy - 4, "SECTION THROUGH THE FLIGHTS (diagrammatic)", 2.8, weight="bold")
    steps = 22
    for i in range(steps):
        a = M(i * 0.28, i * cz / 2 / steps)
        b_ = M((i + 1) * 0.28, (i + 1) * cz / 2 / steps)
        o += line(a[0], a[1], a[0], b_[1], INK, 0.2) + line(a[0], b_[1], b_[0], b_[1], INK, 0.2)
    for i in range(steps):
        a = M(6.16 - i * 0.28, cz / 2 + i * cz / 2 / steps)
        b_ = M(6.16 - (i + 1) * 0.28, cz / 2 + (i + 1) * cz / 2 / steps)
        o += line(a[0], a[1], a[0], b_[1], BLUE, 0.2) + line(a[0], b_[1], b_[0], b_[1], BLUE, 0.2)
    (xa, ya), (xb, yb) = M(7.0, cz), M(7.0, 0)
    o += dim(xa, ya, xb, yb, bp.PR.dist(cz), off=4, size=1.7)
    o += text(sx, sy + 40, f"Two flights of 22 risers of {cz / 44 * 1000:.0f} mm (assumed), landing at mid-height; handrails both sides.", 2.2, fill=GREY)
    return o


def a413(C):
    cz = C.S["clean_z"]
    picks = []
    for r in C.P["rooms"]:
        if r["kind"] == "gowning":
            bx = r["box"]
            picks.append((f"{r['id']}", (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, cz + 0.05, cz + 2.5))
    o, side = enlarged(C, "A-413", "GOWNING ROOMS: enlarged plans (interior elevations on A-702)", picks, 192, 12.0, 0, 0)
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 24 + side + 30, [
        "Each gowning room at the west end of a clean floor: benches, lockers, garment racks and an air shower at the door to the "
        "fab (assumed layout, A-702). Finishes on A-613.", "The door to the fab is interlocked with the air shower (HW-7).",
        "The entry door is in the end wall away from the spine (HW-9, card reader outside); in GW1 it opens beside the "
        "lift's landing: lift, entry door, benches and lockers, air shower, fab."], 2.6, 160, "NOTES")
    return o + t


def a414(C):
    picks = []
    for r in C.P["rooms"]:
        if r["kind"] in ("gas room", "chemical dispense"):
            bx = r["box"]
            picks.append((f"{r['id']} ({r['kind']})", (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, 0.05, 2.5))
    o, side = enlarged(C, "A-414", "GAS ROOMS AND CHEMICAL DISPENSE ROOMS: every one, enlarged", picks, 192, 7.0, 0, 0)
    t, _ = notes(bp.AX0 + 10, bp.AY1 - 40, [
        "Rooms at the facade on the support floor with an exterior wall at least 30 ft from the lot line (415.11.6.4), 2 h barriers "
        "(WT-2), doors 90 min (HW-3); gas cabinets (PP-201), detectors and alarms (FA-101, FA-201)."], 2.6, 160, "NOTES")
    return o + t


def detail_box(o, x, y, w, h, title, draw):
    o.append(rect(x, y, w, h, GREY, 0.2, "#fcfcfb"))
    o.append(text(x + 3, y + 6, title, 2.6, weight="bold"))
    draw(x, y + 10, w, h - 12)


def details(C, sid, title, items):
    o = [text(bp.AX0 + 10, bp.AY0 + 8, title + " (diagrammatic, not to scale)", 4.2, weight="bold")]
    w, h = 240, 300
    for n, (t, fn, note) in enumerate(items):
        x = bp.AX0 + 10 + (n % 4) * (w + 12)
        y = bp.AY0 + 18 + (n // 4) * (h + 12)
        detail_box(o, x, y, w, h, f"{n + 1}  {t}", lambda X, Y, W, H, fn=fn: o.append(fn(X, Y, W, H)))
        tt, _ = notes(x + 4, y + h - 50, [note], 2.3, 70)
        o.append(tt)
    return "".join(o)


def d_door_head(X, Y, W, H):
    return rect(X + 40, Y + 20, 150, 12, INK, 0.3, "#d9dde3") + rect(X + 60, Y + 32, 12, 150, INK, 0.3, "#9aa3b2") + \
        rect(X + 158, Y + 32, 12, 150, INK, 0.3, "#9aa3b2") + text(X + 115, Y + 15, "HM frame, grouted where rated", 2.2, "middle")


def d_layers(colors):
    def fn(X, Y, W, H):
        o, x = [], X + 40
        for c, wdt, lab in colors:
            o.append(rect(x, Y + 20, wdt, 180, INK, 0.25, c))
            o.append(text(x + wdt / 2, Y + 210, lab, 1.8, "middle"))
            x += wdt
        return "".join(o)
    return fn


def d_drain(X, Y, W, H):
    return rect(X + 20, Y + 120, 200, 14, INK, 0.3, "#c9ced6") + rect(X + 100, Y + 100, 40, 34, BLUE, 0.4, "#dbe8f7") + \
        line(X + 20, Y + 112, X + 100, Y + 118, INK, 0.4) + line(X + 140, Y + 118, X + 220, Y + 112, INK, 0.4) + \
        text(X + 120, Y + 95, "drain body and clamping ring", 2.2, "middle")


def d_parapet(X, Y, W, H):
    return rect(X + 100, Y + 30, 16, 160, INK, 0.3, "#777") + rect(X + 92, Y + 22, 32, 10, INK, 0.3, "#d9dde3") + \
        rect(X + 20, Y + 160, 80, 12, INK, 0.3, "#c9ced6") + text(X + 120, Y + 18, "coping PC-1", 2.2, "middle")


def d_curb(X, Y, W, H):
    return rect(X + 50, Y + 40, 140, 70, INK, 0.3, "#f2e6c9") + rect(X + 40, Y + 110, 160, 30, AMBER, 0.3, "#fbefd9") + \
        rect(X + 20, Y + 140, 200, 12, INK, 0.3, "#c9ced6") + text(X + 120, Y + 75, "make-up air unit", 2.2, "middle")


def d_hatch(X, Y, W, H):
    return rect(X + 60, Y + 60, 120, 20, RED, 0.3, "#f6d5d3") + line(X + 120, Y + 80, X + 120, Y + 220, INK, 0.6) + \
        line(X + 105, Y + 80, X + 105, Y + 220, INK, 0.3) + line(X + 135, Y + 80, X + 135, Y + 220, INK, 0.3)


def d_threshold(X, Y, W, H):
    return rect(X + 20, Y + 150, 200, 20, INK, 0.3, "#c9ced6") + rect(X + 90, Y + 40, 14, 108, INK, 0.3, "#d9dde3") + \
        rect(X + 70, Y + 144, 60, 6, AMBER, 0.3, "#fbefd9") + text(X + 120, Y + 30, "door leaf, sweep and saddle", 2.2, "middle")


def d_lid(X, Y, W, H):
    return rect(X + 40, Y + 110, 160, 10, INK, 0.3, "#c9ced6") + rect(X + 40, Y + 120, 12, 90, INK, 0.3, "#555") + \
        rect(X + 188, Y + 120, 12, 90, INK, 0.3, "#555") + rect(X + 60, Y + 60, 120, 30, GREY, 0.25, "none", ' stroke-dasharray="2 1"') + \
        text(X + 120, Y + 55, "hoist path above the lid", 2.2, "middle") + text(X + 120, Y + 105, "lid +9.90, 2 h", 2.2, "middle")


def d_firestop(X, Y, W, H):
    return rect(X + 110, Y + 20, 20, 200, INK, 0.3, "#d9dde3") + rect(X + 20, Y + 110, 200, 14, BLUE, 0.4, "none") + \
        rect(X + 106, Y + 104, 28, 26, RED, 0.4, "none") + text(X + 120, Y + 95, "listed firestop, F rating at least the wall's", 2.2, "middle")


def d_grid(X, Y, W, H):
    o = []
    for i in range(5):
        o.append(rect(X + 20 + i * 42, Y + 40, 40, 20, "#5a8f6a", 0.3, "#e6f4ea"))
    o.append(line(X + 20, Y + 62, X + 230, Y + 62, INK, 0.6))
    o.append(rect(X + 118, Y + 62, 4, 14, RED, 0.3, RED))
    o.append(text(X + 125, Y + 90, "head below the grid; gel seal at every unit", 2.2, "middle"))
    return "".join(o)


def d_floor(X, Y, W, H):
    o = [rect(X + 20, Y + 140, 200, 30, INK, 0.3, "#c9ced6")]
    for i in range(5):
        o.append(rect(X + 20 + i * 40, Y + 60, 38, 6, INK, 0.3, "#e8eaee"))
        o.append(line(X + 39 + i * 40, Y + 66, X + 39 + i * 40, Y + 140, INK, 0.3))
    o.append(rect(X + 100, Y + 40, 12, 140, BLUE, 0.3, "#dbe8f7"))
    o.append(text(X + 120, Y + 30, "drop through a cut tile and a sleeve in the waffle", 2.2, "middle"))
    return "".join(o)


def d_bulkhead(X, Y, W, H):
    return rect(X + 110, Y + 20, 12, 200, RED, 0.3, RED) + rect(X + 60, Y + 90, 120, 60, GREY, 0.3, "#eceef1") + \
        text(X + 120, Y + 85, "tool through the chase partition; perimeter sealed", 2.2, "middle")


def schedule(C, sid, rows, cols, part, parts, title):
    o = [text(bp.AX0 + 10, bp.AY0 + 8, title, 4.2, weight="bold")]
    rh = 4.6
    per_col = int((bp.AY1 - bp.AY0 - 24) // rh) - 1
    width = sum(w for _, w in cols)
    ncol = max(1, int((bp.AX1 - bp.AX0 - 10) // (width + 8)))
    cap = per_col * ncol
    share = math.ceil(len(rows) / parts)          # an even share on each sheet
    chunk = rows[part * share:(part + 1) * share]
    if len(chunk) > cap:
        raise SystemExit(f"{sid}: {len(chunk)} rows do not fit")
    for c in range(ncol):
        sub = chunk[c * per_col:(c + 1) * per_col]
        if not sub:
            break
        tb, _ = table(bp.AX0 + 10 + c * (width + 8), bp.AY0 + 16, cols, sub, 1.9, rh=rh)
        o.append(tb)
    return "".join(o), cap


def door_rows(C):
    return [[d["no"], d["name"][:28], d["wall"], d["width_mm"], d["height_mm"], f"{d['rating_h']:g} h" if d["rating_h"] else "-", d["type"],
             d["hardware"]] for d in C.P["arch"]["doors"]]


DOOR_COLS = [("No", 18), ("Door", 46), ("In a wall", 32), ("W mm", 11), ("H mm", 11), ("Rating", 12), ("Type", 30), ("HW", 10)]


def a611(C, part):
    rows = door_rows(C)
    o, cap = schedule(C, f"A-61{1 + part}", rows, DOOR_COLS, part, 2, f"DOOR SCHEDULE, PART {part + 1} OF 2")
    return o


def a613(C):
    rows = [[r["no"], r["name"][:26], f"{r['area_m2']:,.0f}", r["floor"][:30], r["base"][:18], r["walls"][:30], r["ceiling"][:26],
             f"{r['ceiling_height_m']:.2f}"] for r in C.P["arch"]["rooms"]]
    cols = [("Room", 16), ("Name", 44), ("m2", 12), ("Floor", 54), ("Base", 30), ("Walls", 54), ("Ceiling", 46), ("CH m", 11)]
    o, cap = schedule(C, "A-613", rows, cols, 0, 1, "ROOM FINISH SCHEDULE: every space")
    if len(rows) > cap:
        raise SystemExit(f"{len(rows)} rooms do not fit the finish schedule")
    return o


def a614(C):
    H = C.P["arch"]["hardware_sets"]
    rows = [[k, v["name"], v["items"], sum(1 for d in C.P["arch"]["doors"] if d["hardware"] == k)] for k, v in H.items()]
    tb, _ = table(bp.AX0 + 10, bp.AY0 + 18, [("Set", 14), ("For", 40), ("Items (by kind and performance, never by maker)", 200), ("Doors", 14)], rows, 2.6)
    return text(bp.AX0 + 10, bp.AY0 + 8, "HARDWARE SETS", 4.2, weight="bold") + tb


def interior(C, sid, title, walls, note):
    o = [text(bp.AX0 + 10, bp.AY0 + 8, title + " (diagrammatic, dimensioned)", 4.2, weight="bold")]
    M_k = 1000 / 48
    for n, (lab, w, items) in enumerate(walls):
        ox = bp.AX0 + 20 + (n % 2) * 500
        oy = bp.AY0 + 30 + (n // 2) * 200
        H = 3.0
        o.append(text(ox, oy - 4, lab, 2.8, weight="bold"))
        o.append(rect(ox, oy, w * M_k, H * M_k, INK, 0.3, "#ffffff"))
        for x0, z0, x1, z1, fill, txt in items:
            o.append(rect(ox + x0 * M_k, oy + (H - z1) * M_k, (x1 - x0) * M_k, (z1 - z0) * M_k, INK, 0.2, fill))
            if txt:
                o.append(text(ox + (x0 + x1) / 2 * M_k, oy + (H - z1) * M_k - 1.5, txt, 1.8, "middle"))
        o.append(dim(ox, oy + H * M_k + 6, ox + w * M_k, oy + H * M_k + 6, bp.PR.dist(w), off=0, size=1.8))
        o.append(dim(ox - 6, oy, ox - 6, oy + H * M_k, bp.PR.dist(H), off=0, size=1.8))
    t, _ = notes(bp.AX0 + 20, bp.AY1 - 40, [note], 2.6, 170, "NOTES")
    o.append(t)
    return "".join(o)


def a701(C):
    SCALES["A-701"] = scale_label(48)
    c = C.P["toilets"]["cores"][0]
    wc = c["wc"]
    stall = [(0.3 + i * 0.9, 0.0, 0.8 + i * 0.9, 0.8, "#e6f4ea", "WC" if i == 0 else "") for i in range(wc)]
    parts = [(0.2 + i * 0.9, 0.15, 0.25 + i * 0.9, 1.9, "#d9dde3", "") for i in range(wc + 1)]
    lavs = [(0.4 + i * 0.6, 0.7, 0.85 + i * 0.6, 0.9, "#e6f4ea", "lav" if i == 0 else "") for i in range(wc)] + \
           [(0.4 + i * 0.6, 1.1, 0.85 + i * 0.6, 1.8, "#eef3f8", "mirror" if i == 0 else "") for i in range(wc)]
    tile = [(0.0, 2.1, 5.2, 2.12, "#999", "tile CT-1 to 2.1 m, paint above")]
    return interior(C, "A-701", f"TOILET ROOM INTERIOR ELEVATIONS, core {c['id']} (typical of every core)",
                    [("1 MEN'S ROOM, BACK WALL", 5.2, stall + parts + tile), ("2 MEN'S ROOM, SIDE WALL", 4.4, lavs + tile),
                     ("3 WOMEN'S ROOM, BACK WALL", 5.2, stall + parts + tile), ("4 WOMEN'S ROOM, SIDE WALL", 4.4, lavs + tile)],
                    "Fixture counts on P-201; mounting heights, grab bars and the accessible stall follow ICC A117.1, not read: licensed review.")


def a702(C):
    SCALES["A-702"] = scale_label(48)
    bench = [(0.5, 0.0, 4.5, 0.45, "#eceef1", "bench")]
    lockers = [(0.3 + i * 0.45, 0.0, 0.72 + i * 0.45, 1.9, "#dfe6ef", "lockers" if i == 0 else "") for i in range(8)]
    racks = [(4.2, 1.2, 5.6, 1.6, "#eef3f8", "garment rack")]
    shower = [(1.5, 0.0, 3.0, 2.4, "#e3ecf7", "air shower")]
    return interior(C, "A-702", "GOWNING ROOM INTERIOR ELEVATIONS (typical)",
                    [("1 ENTRY WALL", 5.0, lockers), ("2 LONG WALL", 6.0, bench + racks), ("3 FAB WALL", 5.0, shower), ("4 END WALL", 5.0, [])],
                    "Layout assumed for a gowning room 5 x 20 m; the air shower door interlocks with the fab door (HW-7). Finishes on A-613.")


BODIES = {
    "A-001": a001, "A-100": a100,
    "A-111": lambda C: floor_plan(C, "A-111"), "A-112": lambda C: floor_plan(C, "A-112"),
    "A-121": lambda C: floor_plan(C, "A-121"), "A-122": lambda C: floor_plan(C, "A-122"),
    "A-131": lambda C: rcp(C, "A-131", 0), "A-132": lambda C: rcp(C, "A-132", 1),
    "A-141": lambda C: roof_plan(C, "A-141", 0), "A-142": lambda C: roof_plan(C, "A-142", 1),
    "A-202": a202, "A-311": a311,
    "A-411": lambda C: a411(C, "spine stair", "A-411"), "A-412": lambda C: a411(C, "facade stair", "A-412"),
    "A-413": a413, "A-414": a414,
    "A-521": lambda C: details(C, "A-521", "DOOR AND FRAME DETAILS", [
        ("Head and jamb, hollow metal frame", d_door_head, "Frames grouted in rated walls; label on the hinge edge."),
        ("Door types D1, D2 (labelled)", d_layers([("#d9dde3", 14, "face"), ("#ffffff", 30, "core"), ("#d9dde3", 14, "face")]),
         "D1 hollow metal 45 mm; D2 the same with a label for its rating (A-611)."),
        ("Threshold at an exterior exit", d_threshold, "Saddle and weather seals; the slab steps 0 mm (level threshold)."),
        ("Cleanroom door seal", d_door_head, "Gaskets at head and jambs; drop seal at the sill.")]),
    "A-531": lambda C: details(C, "A-531", "ROOF DETAILS", [
        ("Parapet and coping", d_parapet, "Membrane turned up and under the coping; parapet 1.0 m."),
        ("Roof drain", d_drain, "Sump at each drain; overflow per IPC chapter 11 (not read)."),
        ("Equipment curb", d_curb, "Insulated curb 350 mm, flashed and counter-flashed."),
        ("Roof hatch and ladder", d_hatch, "Hatch 900 x 900 mm; ladder with a safety post (assumed).")]),
    "A-541": lambda C: details(C, "A-541", "CLEANROOM CEILING DETAILS", [
        ("Fan filter grid and gel seal", d_grid, "Grid hung from the air space structure; units 1200 x 600 mm."),
        ("Sprinkler head through the grid", d_grid, "Head below the grid, escutcheon sealed (NFPA 13 spacing on FP-110)."),
        ("Chase partition head", d_bulkhead, "Partition stops at +12.70, 0.30 below the ceiling; it counts as a wall for heads and ports."),
        ("Grid at a stair core lid", d_lid, "Grid stops at the core; the lid at +9.90 under the hoist path.")]),
    "A-551": lambda C: details(C, "A-551", "RAISED FLOOR AND PENETRATION DETAILS", [
        ("Raised floor and pedestals", d_floor, "Tiles 600 mm on pedestals over the waffle slab; perforated along the aisle."),
        ("Drop through a cut tile", d_floor, "Sleeve in the waffle, cut tile with a sealed edge."),
        ("Tool bulkhead at the chase", d_bulkhead, "Seal around the tool; the chase side kept clear 1.6 m."),
        ("Firestop at a rated wall", d_firestop, "Listed system, F rating at least the wall's (714.4.1.2).")]),
    "A-611": lambda C: a611(C, 0), "A-612": lambda C: a611(C, 1),
    "A-613": a613, "A-614": a614, "A-701": a701, "A-702": a702,
}
