"""Design development sheets (docs/DESIGN-DEV.md, DD11): elevations, sections, enlarged plans, wall types, schedules and
the plans of each trade, drawn from the same model as the IFC and the schematic sheets, so they never disagree. Every
sheet carries the truth line and NOT FOR CONSTRUCTION (the frame in sheets.py).
"""

import collections
import math

import blueprint as bp
import model as bmodel
from blueprint import GREY, INK, RED, Map, line, rect, text
from ctx import FT, IN
from sheets import (AMBER, BLUE, GREEN, SCALES, VCOL, boxes, bld_outline, notes, of, scale_label, scalebar, table)
from profiles import f

SHEETS = [
    ("A-201", "Exterior elevations"), ("A-301", "Building sections"), ("A-402", "Enlarged plans: toilet cores and lifts"),
    ("A-501", "Wall types and details"), ("A-602", "Schedules: walls, doors, firestops"), ("S-301", "Sections through the frame"),
    ("S-601", "Member schedule"), ("M-201", "Chases and exhaust systems"), ("M-602", "Fans, scrubbers and make-up air"),
    ("PP-201", "Gas cabinets and valve boxes"), ("P-201", "Toilet cores, fixtures, drains and showers"),
    ("FP-201", "Sprinkler mains, risers and standpipes"), ("FA-201", "Alarm boxes, notification and detection"),
    ("E-101", "Power and lighting plan, phase 1"), ("E-602", "Panel schedule"),
]
STYLE = {  # class: (stroke, fill, stroke width, order)
    "IfcFooting": (INK, "#e9e3d7", 0.12, 0), "IfcSlab": (INK, "#c9ced6", 0.12, 1), "IfcCovering": (GREY, "#e8e8e8", 0.08, 2),
    "IfcWall": (INK, "#6b6f78", 0.08, 3), "IfcColumn": (INK, "#30343c", 0.06, 4), "IfcMember": (RED, "none", 0.25, 5),
    "IfcBeam": (BLUE, "#dbe6f5", 0.12, 5), "IfcStair": (BLUE, "#e3ecf7", 0.12, 6), "IfcTransportElement": (INK, "#d8d2e8", 0.15, 6),
    "IfcBuildingElementProxy": (GREY, "#eceef1", 0.06, 7), "IfcUnitaryEquipment": (INK, "#f2e6c9", 0.12, 8),
    "IfcDuctSegment": (AMBER, "#fbefd9", 0.08, 9), "IfcPipeSegment": (BLUE, "none", 0.08, 10),
    "IfcCableCarrierSegment": (RED, "none", 0.08, 10), "IfcAirTerminal": ("#5a8f6a", "none", 0.05, 11),
    "IfcFireSuppressionTerminal": (RED, "none", 0.05, 11), "IfcDoor": (RED, "#f6d5d3", 0.1, 12),
}
STRUCT = ("IfcFooting", "IfcSlab", "IfcColumn", "IfcBeam", "IfcMember", "IfcStair")


def everything(C):
    return [e for e in C.M["elements"] + C.new if e["box"] is not None and not e["key"].startswith("campus/")]


def cut(C, elems, axis, val, M, ua, mirror=None):
    """A section: every element the plane axis = val passes through, drawn on (ua, z)."""
    i = "xyz".index(axis)
    j = "xyz".index(ua)
    out = []
    hit = [e for e in elems if e["cls"] in STYLE and e["box"][i] <= val <= e["box"][i + 3]]
    hit.sort(key=lambda e: STYLE[e["cls"]][3])
    for e in hit:
        st, fi, sw, _ = STYLE[e["cls"]]
        u0, u1 = e["box"][j], e["box"][j + 3]
        if mirror is not None:
            u0, u1 = mirror - u1, mirror - u0
        x, y, w, h = M.box(u0, e["box"][2], u1, e["box"][5])
        out.append(rect(x, y, max(w, 0.12), max(h, 0.12), st, sw, fi))
    return "".join(out)


def levels(C, M, u0, u1, tag=True):
    o = []
    for fl in C.S["floors"]:
        for z in (fl["z0"],):
            a, b = M(u0, z), M(u1, z)
            o.append(line(a[0], a[1], b[0], b[1], GREY, 0.12, "2 1"))
            if tag:
                o.append(text(b[0] + 2, b[1] + 0.8, f"{fl['name']} {bp.PR.level(z)}", 1.9, fill=GREY))
    return "".join(o)


# ------------------------------------------------------------------ A-201

def a201(C):
    ratio = 480
    SCALES["A-201"] = scale_label(ratio)
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "EXTERIOR ELEVATIONS: the facades, the facade stairs, exit doors, bracing and the roof plant", 4.2, weight="bold")]
    top = 22.0
    allx = everything(C)
    y = bp.AY0 + 24
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        for face in ("north", "south"):
            M = Map(ratio, 0, top, bp.AX0 + 10, y)
            sgn = 1 if face == "north" else -1
            u = (lambda x: b["x1"] - x) if face == "north" else (lambda x: x - b["x0"])
            W = b["x1"] - b["x0"]
            x0, y0, w, h = M.box(0, 0, W, C.fl["roof"]["z1"])
            o.append(rect(x0, y0, w, h, INK, 0.35, "#f7f7f5"))
            o.append(levels(C, M, 0, W, tag=(face == "north" and p == 0)))
            for e in allx:
                bx = e["box"]
                face_hit = (bx[4] >= b["y1"] - 0.45) if sgn > 0 else (bx[1] <= b["y0"] + 0.45)
                on_roof = bx[2] >= C.fl["roof"]["z1"] - 0.05 and b["x0"] <= bx[0] <= b["x1"]
                if not (e["cls"] in ("IfcStair", "IfcDoor", "IfcMember", "IfcUnitaryEquipment", "IfcWall") and (face_hit or on_roof)):
                    continue
                if e["cls"] == "IfcWall" and not e["key"].startswith("permit/"):
                    continue
                if not (b["x0"] - 1 <= bx[0] <= b["x1"] + 1):
                    continue
                st, fi, sw, _ = STYLE.get(e["cls"], (INK, "none", 0.1, 0))
                ua, ub = sorted((u(bx[0]), u(bx[3])))
                xx, yy, ww, hh = M.box(ua, bx[2], ub, bx[5])
                if e["cls"] == "IfcMember":
                    o.append(line(xx, yy, xx + ww, yy + hh, RED, 0.2) + line(xx, yy + hh, xx + ww, yy, RED, 0.2))
                else:
                    o.append(rect(xx, yy, max(ww, 0.2), max(hh, 0.2), st, sw, fi))
            o.append(text(bp.AX0 + 10, y - 2, f"{k} {face.upper()} ELEVATION (looking {'south' if face == 'north' else 'north'})", 3.0, weight="bold"))
            y += top * 1000 / ratio + 14
    o.append(scalebar(bp.AX0 + 10, bp.AY1 - 8, ratio, 60.96))
    t, _ = notes(bp.AX0 + 600, bp.AY0 + 24, [
        "Grey: the facade of each building (the concept model's walls). Blue: facade stair towers. Red: exit doors and braced bays. "
        "Tan: make-up air units on the roof.",
        f"Roof top {bp.PR.level(C.fl['roof']['z1'])}; levels dashed.",
        "Facade materials, glazing, louvres and the roof membrane are for licensed review; exterior wall ratings follow IBC 705 "
        "(fire separation distance), not read.",
    ], 2.6, 80, "NOTES")
    o.append(t)
    return "".join(o)


# ------------------------------------------------------------------ A-301 and S-301

def bay_mid(C, p):
    """A cut through the west row of tools of a bay near the building's middle (behind its chase)."""
    bays = [b for b in C.S["bays"] if b["phase"] == p and b["y0"] > 0]
    b = bays[len(bays) // 2]
    return b["x0"] + C.P["chase"]["width_m"] + 2.0


def sections(C, sid, structural):
    ratio = 192
    SCALES[sid] = scale_label(ratio) + "; long section " + scale_label(480)
    allx = [e for e in everything(C) if (e["cls"] in STRUCT if structural else True)]
    title = "SECTIONS THROUGH THE FRAME: footings, columns, waffle slab, trusses" if structural else \
        "BUILDING SECTIONS: across each building at a bay's middle, and along phase 1"
    o = [text(bp.AX0 + 10, bp.AY0 + 8, title, 4.2, weight="bold")]
    top = 22.0
    y = bp.AY0 + 20
    for p, b in enumerate(C.blds):
        xc = bay_mid(C, p)
        if structural:      # on a column line, so the cut passes through the columns
            xs = [x for x in bmodel.grid_lines(C.S)[0] if b["x0"] + 1 < x < b["x1"] - 1]
            xc = min(xs, key=lambda x: abs(x - xc))
        M = Map(ratio, b["y0"] - 2, top, bp.AX0 + 10, y)
        o.append(text(bp.AX0 + 10, y - 2, f"{C.keys[p]} CROSS SECTION at x = {bp.PR.distu(xc - b['x0'])} from the west wall, "
                      f"{'on a column line' if structural else 'through a row of tools'} (looking east)", 3.0, weight="bold"))
        o.append(levels(C, M, b["y0"] - 2, b["y1"] + 2, tag=True))
        o.append(cut(C, [e for e in allx if e["bld"] == p], "x", xc, M, "y"))
        y += (top + 1.5) * 1000 / ratio + 14
    b = C.blds[0]
    M = Map(480, b["x0"] - 2, top, bp.AX0 + 10, y)
    o.append(text(bp.AX0 + 10, y - 2, f"P1 LONG SECTION at y = {bp.PR.distu(34.0)} (through the cross aisles, looking north)", 3.0, weight="bold"))
    o.append(levels(C, M, b["x0"] - 2, b["x1"] + 2, tag=False))
    o.append(cut(C, [e for e in allx if e["bld"] == 0], "y", 34.0, M, "x"))
    F = C.P["frame"]
    t, _ = notes(bp.AX0 + 760, bp.AY0 + 20, ([
        f"Footings below the support floor slab (1.2 m deep, assumed); combined footings where pads would overlap.",
        f"Roof trusses {F['truss_depth_m']} m deep (assumed) on roof columns at the mid grid lines; waffle slab 0.9 m.",
        "Risk category IV (assumed, the stricter reading). Seismic and wind design wait for ASCE 7 and a site: cannot say.",
        "Every member preliminary, for licensed review; sizes by required properties on S-601.",
    ] if structural else [
        "Cut through a bay's middle: support floor with its mains and laterals, the waffle slab, the raised floor, the clean floor "
        "with its tools and chase partitions, the filter ceiling, the air space, the roof.",
        "The long section passes through the cross aisles at mid-depth; the chase doors open into them.",
        "Grey: tools (the concept model). Amber: ducts. Blue: pipes and structure. Red: sprinkler arrays.",
    ]), 2.6, 60, "NOTES")
    o.append(t)
    return "".join(o)


# ------------------------------------------------------------------ A-402

def window(C, M, x0, y0, x1, y1, zlo, zhi, side, key, ox, oy):
    o = [f'<clipPath id="{key}"><rect x="{f(ox)}" y="{f(oy)}" width="{f(side)}" height="{f(side)}"/></clipPath><g clip-path="url(#{key})">']
    order = sorted((e for e in everything(C) if e["box"][0] < x1 and e["box"][3] > x0 and e["box"][1] < y1 and e["box"][4] > y0
                    and e["box"][2] < zhi and e["box"][5] > zlo and e["cls"] != "IfcSpace" and e["cls"] != "IfcFireSuppressionTerminal"
                    and e["cls"] not in ("IfcSlab", "IfcCovering")),
                   key=lambda e: STYLE.get(e["cls"], (0, 0, 0, 20))[3])
    for e in order:
        st, fi, sw, _ = STYLE.get(e["cls"], (GREEN, "#e6f4ea", 0.1, 20))
        if e["cls"] == "IfcSanitaryTerminal":
            st, fi = GREEN, "#e6f4ea"
        o.append(boxes(M, [e["box"]], st, fi, sw))
    o.append("</g>")
    o.append(rect(ox, oy, side, side, INK, 0.3))
    return "".join(o)


def a402(C):
    ratio, half = 96, 7.5
    SCALES["A-402"] = scale_label(ratio)
    side = 2 * half * 1000 / ratio
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "ENLARGED PLANS: a toilet core in each building and each building's lift", 4.2, weight="bold")]
    T = C.P["toilets"]
    views = []
    for k in C.keys:
        c = next(c for c in T["cores"] if c["building"] == k)
        bx = c["box"]
        views.append((f"Toilet core {c['id']}, support floor", (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, 0.0, 3.0))
    for l in C.P["lifts"]:
        bx = l["box"]
        views.append((f"Lift {l['id']}, clean floor", (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2, C.S["clean_z"], C.S["clean_z"] + 3.0))
    for n, (title, cx, cy, zlo, zhi) in enumerate(views):
        ox, oy = bp.AX0 + 10 + n * 250, bp.AY0 + 26
        M = Map(ratio, cx - half, cy + half, ox, oy)
        o.append(text(ox, oy - 5, title, 3.2, weight="bold"))
        o.append(window(C, M, cx - half, cy - half, cx + half, cy + half, zlo + 0.05, zhi, side, f"a402v{n}", ox, oy))
        o.append(text(ox, oy + side + 6, f"{bp.PR.size(2 * half, 2 * half)} shown. Green: fixtures. Red: doors.", 2.4, fill=GREY))
    rows = [[c["id"], c["near"], c["wc"], c["lav"], c["df"], c["service_sinks"], f"{c['dfu']:g}"] for c in T["cores"]]
    t, _ = table(bp.AX0 + 10, bp.AY0 + 205, [("Core", 26), ("Beside", 30), ("WC each room", 26), ("Lav each room", 26), ("Fountains", 20),
                                             ("Service sinks", 22), ("dfu", 14)], rows, 2.4)
    o.append(t)
    t, _ = notes(bp.AX0+ 220, bp.AY0 + 210, [
        "Each core: a men's room, an alcove of drinking fountains, a women's room; doors face the spine stair.",
        "Fixture counts from IPC Table 403.1's factory and industrial row (H occupancies are not listed: the code official decides; assumed).",
        "Lifts: 2.6 x 2.6 m hoistways from the support floor to the clean floor at each building's west end (1104.4). The hoistway "
        "enclosure, machinery and car follow IBC 713, 3006 and ASME A17.1, not read: licensed review.",
        "Toilet room clearances, grab bars and the accessible stall follow ICC A117.1, not read.",
    ], 2.6, 100, "NOTES")
    o.append(t)
    return "".join(o)


# ------------------------------------------------------------------ A-501

def a501(C):
    W = C.P["wall_types"]
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "WALL TYPES AND DETAILS (diagrammatic, not to scale)", 4.2, weight="bold")]
    rows = [[t, f"{w['rating_h']} h" if w["rating_h"] else "unrated", w["assembly"], w["cite"]] for t, w in W.items()]
    tb, y = table(bp.AX0 + 10, bp.AY0 + 16, [("Type", 18), ("Rating", 18), ("Assembly", 220), ("Source", 60)], rows, 2.6)
    o.append(tb)
    # layer diagrams
    lay = {"WT-1": [("gyp", 16), ("stud", 92), ("gyp", 16)], "WT-2": [("gyp", 13), ("gyp", 13), ("stud", 92), ("gyp", 13), ("gyp", 13)],
           "WT-C": [("panel", 50), ("stud", 92)], "WT-P": [("gyp", 13), ("stud", 92), ("gyp", 13)]}
    x = bp.AX0 + 10
    yy = y + 14
    for t, layers in lay.items():
        o.append(text(x, yy - 3, t, 3.2, weight="bold"))
        cx = x
        for nm, mm in layers:
            w = mm * 0.25
            fill = {"gyp": "#f1efe8", "stud": "#ffffff", "panel": "#dfe8f3"}[nm]
            o.append(rect(cx, yy, w, 40, INK, 0.2, fill))
            if nm == "stud":
                for k in range(4):
                    o.append(line(cx, yy + k * 10, cx + w, yy + k * 10 + 10, GREY, 0.1))
            cx += w
        o.append(text(x, yy + 47, " | ".join(n for n, _ in layers), 2.2, fill=GREY))
        x += 60
    # details
    dx, dy = bp.AX0 + 270, y + 12
    o.append(text(dx, dy - 3, "DETAIL 1: chase partition at a tool (bulkhead), plan", 3.0, weight="bold"))
    o.append(rect(dx, dy, 120, 6, INK, 0.2, "#dfe8f3"))
    o.append(rect(dx + 40, dy - 20, 40, 46, GREY, 0.25, "#eceef1"))
    o.append(text(dx + 60, dy + 36, "tool through the partition; perimeter sealed (assumed)", 2.2, "middle", fill=GREY))
    o.append(text(dx, dy + 46, "chase side above, fab area below", 2.2, fill=GREY))
    dx2 = dx + 160
    o.append(text(dx2, dy - 3, "DETAIL 2: firestop at a rated wall, section", 3.0, weight="bold"))
    o.append(rect(dx2 + 40, dy - 10, 12, 60, INK, 0.2, "#f1efe8"))
    o.append(rect(dx2, dy + 16, 92, 6, BLUE, 0.3, "none"))
    o.append(rect(dx2 + 38, dy + 13, 16, 12, RED, 0.3, "none"))
    o.append(text(dx2 + 46, dy + 60, "listed system, F rating at least the wall's (714.4.1.2)", 2.2, "middle", fill=GREY))
    dx3 = dx2 + 170
    o.append(text(dx3, dy - 3, "DETAIL 3: spine stair lid under the hoist path, section", 3.0, weight="bold"))
    o.append(rect(dx3, dy + 30, 100, 4, INK, 0.2, "#c9ced6"))
    o.append(rect(dx3 + 10, dy - 6, 80, 8, GREY, 0.25, "none", ' stroke-dasharray="2 1"'))
    o.append(text(dx3 + 50, dy - 8, "hoist vehicles' path", 2.2, "middle", fill=GREY))
    o.append(text(dx3 + 50, dy + 42, "lid at 9.9 m, 2 h with the enclosure (assumed)", 2.2, "middle", fill=GREY))
    t, _ = notes(bp.AX0 + 10, bp.AY1 - 60, [
        "Rated assemblies are the prescriptive ones of IBC Table 721.1(2), item 13: steel studs with Type X gypsum board. "
        "Head-of-wall joints, deflection tracks and fastening follow the listing: licensed review.",
        "Cleanroom wall panels and seals are assumed to the cleanliness class (ISO 14644-1 not read).",
    ], 2.6, 160, "NOTES")
    o.append(t)
    return "".join(o)


# ------------------------------------------------------------------ A-602

def a602(C):
    P = C.P
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "SCHEDULES: wall types, doors by the wall they are in, firestops", 4.2, weight="bold")]
    cw = collections.Counter((w["type"], w["kind"]) for w in P["walls"])
    rows = [[t, k, n, f"{P['wall_types'][t]['rating_h']} h" if P["wall_types"][t]["rating_h"] else "-"] for (t, k), n in sorted(cw.items())]
    tb, y = table(bp.AX0 + 10, bp.AY0 + 16, [("Type", 18), ("Walls", 80), ("Count", 16), ("Rating", 16)], rows, 2.5)
    o.append(tb)
    cd = collections.Counter((d["wall_kind"], d["rating_h"]) for d in P["doors"])
    rows = [[k, f"{r:g} h" if r else "unrated", n, "T716.1(2)" if r else "-"] for (k, r), n in sorted(cd.items())]
    tb, _ = table(bp.AX0 + 160, bp.AY0 + 16, [("In a wall that is", 60), ("Door rating", 24), ("Count", 16), ("Source", 24)], rows, 2.5)
    o.append(tb)
    rows = [[x["element"].replace("permit/", ""), x["wall"].replace("permit/", ""), f"{x['wall_rating_h']:g} h", f"{x['f_rating_h']:g} h"]
            for x in P["firestops"]]
    tb, _ = table(bp.AX0 + 310, bp.AY0 + 16, [("Penetrating", 50), ("Wall", 50), ("Wall rating", 22), ("F rating", 18)], rows, 2.5)
    o.append(tb)
    t, _ = notes(bp.AX0 + 310, bp.AY0 + 30 + 6 * (len(rows) + 2), [
        "Doors: Table 716.1(2) by the wall: 2 h exit enclosure or fire barrier 90 min; 1 h exit passageway 1 h; exterior and "
        "unrated walls unrated here (exterior openings follow IBC 705.8, not read).",
        "Firestops: every pipe, duct or tray through a rated wall, a listed through-penetration system (714.4.1.2).",
    ], 2.6, 90, "NOTES")
    o.append(t)
    return "".join(o)


# ------------------------------------------------------------------ S-601

def s601(C):
    M = C.P["members"]
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "MEMBER SCHEDULE: required properties, preliminary, for licensed review", 4.2, weight="bold")]
    cols = sorted(M["columns"], key=lambda c: -c["load_kN"])
    by = collections.defaultdict(list)
    for c in cols:
        by[c["kind"]].append(c)
    rows = []
    for kind, cs in by.items():
        for lo, hi in ((0, 2000), (2000, 4000), (4000, 8000), (8000, 1e9)):
            g = [c for c in cs if lo <= c["load_kN"] < hi]
            if g:
                rows.append([kind, len(g), f"{min(c['load_kN'] for c in g):,.0f} to {max(c['load_kN'] for c in g):,.0f}",
                             f"{max(c['area_mm2'] for c in g):,}"])
    tb, y = table(bp.AX0 + 10, bp.AY0 + 16, [("Columns", 28), ("Count", 16), ("Load, kN", 40), ("Area needed, mm2 (largest)", 50)], rows, 2.5)
    o.append(tb)
    bs = M["beams"]
    rows = collections.Counter((round(b["span_m"], 1), b["sx_mm3"]) for b in bs)
    rows = [[f"{s:g} m", n, f"{sx:,}"] for (s, sx), n in sorted(rows.items())][:40]
    tb, _ = table(bp.AX0 + 160, bp.AY0 + 16, [("Beams and trusses, span", 40), ("Count", 16), ("Sx needed, mm3", 40)], rows, 2.5)
    o.append(tb)
    fs = M["footings"]
    comb = sum(1 for x in fs if x["combined"])
    rows = [["pad footings", len(fs) - comb, f"{max(x['side_m'] for x in fs):.2f} m largest side"],
            ["columns on combined footings", comb, "pads that would overlap, joined and sized for their total load"]]
    tb, _ = table(bp.AX0 + 270, bp.AY0 + 16, [("Footings", 50), ("Count", 16), ("Note", 110)], rows, 2.5)
    o.append(tb)
    t, _ = notes(bp.AX0 + 270, bp.AY0 + 40, [
        f"Columns: area = P / (0.6 Fy), Fy {345} MPa (assumed). Beams and trusses: simply supported under the roof load over a 12 m "
        "width, Sx = M / (0.66 Fy) (assumed). No maker's section is named; a structural engineer picks them.",
        "Risk category IV (the stricter reading, assumed). Seismic and wind forces wait for ASCE 7 and a site: cannot say.",
    ], 2.6, 90, "NOTES")
    o.append(t)
    return "".join(o)


# ------------------------------------------------------------------ plans of phase 1

def plan_p1(C, sid, title, ratio, draw, floor_note):
    SCALES[sid] = scale_label(ratio)
    b = C.blds[0]
    M = Map(ratio, b["x0"] - 2, b["y1"] + 2, bp.AX0 + 10, bp.AY0 + 20)
    o = [text(bp.AX0 + 10, bp.AY0 + 12, title, 4.2, weight="bold"), bld_outline(M, b), draw(M, b)]
    o.append(text(bp.AX0 + 10, bp.AY0 + 17, floor_note, 2.4, fill=GREY))
    return "".join(o), (b["y1"] - b["y0"] + 4) * 1000 / ratio + 30


def m201(C):
    P = C.P

    def draw(M, b):
        o = [boxes(M, [(t["x0"], t["y0"], t["x1"], t["y1"]) for _, t in C.tools_in(0)], GREY, "#eceef1", 0.05)]
        o.append(boxes(M, [e["box"] for e in of(C, "IfcWall", lambda e: e["bld"] == 0 and e["name"].startswith("Chase partition"))], RED, RED, 0.1))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcDoor", lambda e: e["bld"] == 0 and "chase" in e["key"])], GREEN, GREEN, 0.15))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcAirTerminal", lambda e: e["bld"] == 0 and "chase" in e["key"])], AMBER, AMBER, 0.15))
        return "".join(o)
    o, h = plan_p1(C, "M-201", "CHASES AND EXHAUST SYSTEMS, PHASE 1: chase partitions, doors into the fab area, chase exhaust", 384, draw,
                   "Clean floor. Red: chase partitions. Green: chase doors (into the cross aisles). Amber: chase exhaust grilles.")
    X = P["exhaust"]["systems"]
    rows = [[k, f"{v['m3h']:,.0f}", f"{v['cfm']:,}", v["fans"], v["scrubbers"], v["treatment"]] for k, v in X.items()]
    tb, y = table(bp.AX0 + 10, bp.AY0 + h + 4, [("System", 22), ("m3/h", 26), ("cfm", 22), ("Fans", 12), ("Scrubbers", 18), ("Treatment", 110)], rows, 2.5)
    o += tb
    ch = P["chases"]
    t, _ = notes(bp.AX0 + 240, bp.AY0 + h + 6, [
        f"{len(ch)} chases of {ch[0]['width_m']} m ({ch[0]['width_m'] / FT:.2f} ft), each open to the spine and the perimeter, with a door "
        f"into the fab area at the cross aisle: the longest walk to an open end or a door is {max(c['max_travel_m'] for c in ch):.1f} m "
        f"({max(c['max_travel_m'] for c in ch) / FT:.0f} ft, limit 75 ft, 415.11.3.3); no dead end.",
        f"Chase exhaust {ch[0]['ach']} air changes an hour (6 asked, 415.11.3.2), {sum(c['exhaust_cfm'] for c in ch):,.0f} cfm in all, to the general exhaust.",
        "Hazardous exhaust: one system per kind, never shared by incompatible materials (IMC 509.4); no fire or smoke damper (509.6.1).",
    ], 2.6, 95, "NOTES")
    o += t
    return o


def m602(C):
    P = C.P
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "FANS, SCRUBBERS AND MAKE-UP AIR", 4.2, weight="bold")]
    rows = []
    for k, v in P["exhaust"]["systems"].items():
        rows.append([f"{k} exhaust fans", v["fans"], f"{v['fan_unit_m3h']:,}", "N+1 (assumed)"])
        if v["scrubbers"]:
            rows.append([f"{k} scrubbers or abatement", v["scrubbers"], f"{v['fan_unit_m3h']:,}", "N+1 (assumed)"])
    tb, y = table(bp.AX0 + 10, bp.AY0 + 16, [("Equipment", 60), ("Units", 14), ("Each, m3/h", 26), ("Note", 40)], rows, 2.6)
    o.append(tb)
    rows = [[k, f"{m['exhaust_cfm']:,}", f"{m['makeup_cfm']:,}", m["units"], f"{m['unit_m3h']:,.0f}",
             ", ".join(f"{a} {b:,}" for a, b in m["parts_m3h"].items())] for k, m in P["makeup"].items()]
    tb, _ = table(bp.AX0 + 10, y + 10, [("Building", 18), ("Exhaust, cfm", 28), ("Make-up, cfm", 28), ("Units", 14), ("Each, m3/h", 24),
                                        ("Exhaust parts, m3/h", 160)], rows, 2.6)
    o.append(tb)
    t, _ = notes(bp.AX0 + 300, bp.AY0 + 16, [
        "Make-up air balanced to each building's exhaust (IMC 509.5.5 asks approximately equal; within 10% assumed).",
        "Fans, scrubbers and make-up air units are sized from the tool cards and assumed units; makers' data replace them.",
        "Duct construction, insulation, supports and balancing: licensed review.",
    ], 2.6, 90, "NOTES")
    o.append(t)
    return "".join(o)


def pp201(C):
    P = C.P
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "GAS CABINETS AND VALVE MANIFOLD BOXES", 4.2, weight="bold")]
    rows = [[c["id"], c["room"], c["gas"], "yes" if c["highly_toxic"] else "no", c["cylinders"], f"{c['exhaust_cfm']:.0f}", c["face_fpm"],
             "yes"] for c in P["gas_cabinets"]]
    tb, y = table(bp.AX0 + 10, bp.AY0 + 16, [("Cabinet", 36), ("Room", 22), ("Gas", 34), ("Highly toxic", 22), ("Cylinders", 18),
                                             ("cfm", 14), ("fpm at port", 20), ("Sprinkler", 18)], rows, 2.5)
    o.append(tb)
    by = collections.Counter((v["building"], v["gas"]) for v in P["valve_boxes"])
    rows = [[b, g, n] for (b, g), n in sorted(by.items())]
    tb, _ = table(bp.AX0 + 220, bp.AY0 + 16, [("Building", 18), ("Gas", 40), ("Valve boxes", 20)], rows, 2.5)
    o.append(tb)
    r = next(r for r in P["rooms"] if r["id"] == P["gas_cabinets"][0]["room"])
    x0, y0, _, x1, y1, _ = r["box"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half, ratio = 7.5, 96
    side = 2 * half * 1000 / ratio
    ox, oy = bp.AX0 + 360, bp.AY0 + 26
    M = Map(ratio, cx - half, cy + half, ox, oy)
    SCALES["PP-201"] = scale_label(ratio)
    o.append(text(ox, oy - 5, f"Gas room {r['id']}, support floor", 3.2, weight="bold"))
    o.append(window(C, M, cx - half, cy - half, cx + half, cy + half, 0.05, 3.0, side, "pp201v", ox, oy))
    t, _ = notes(ox, oy + side + 10, [
        f"Gas cabinets per IFC 6004.1.2: at most 3 cylinders ({P['gas_cabinets'][0]['cylinders']} assumed), exhausted, 200 fpm average at "
        "the access port (port and exhaust assumed), sprinklered; the room keeps its own exhaust (6004.2.2.2).",
        "Double-contained headers leave each gas room at a firestopped penetration to the valve boxes under the bays.",
        "Gas piping materials, purge panels and SEMI S2 tool connections: licensed review.",
    ], 2.6, 70, "NOTES")
    o.append(t)
    return "".join(o)


def p201(C):
    P = C.P
    T = P["toilets"]
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "TOILET CORES, FIXTURES, DRAINS AND EMERGENCY SHOWERS", 4.2, weight="bold")]
    rows = []
    for k, t in T["by_building"].items():
        rows.append([k, t["occupants"], t["per_sex_needed"], t["wc_men"], t["wc_women"], t["lav_men"], t["lav_women"],
                     f"{t['drinking_fountains']} ({t['drinking_fountains_needed']})", t["service_sinks"],
                     f"{t['travel_m']['clean floor'] / FT:.0f}", f"{t['travel_m']['support floor'] / FT:.0f}"])
    tb, y = table(bp.AX0 + 10, bp.AY0 + 16, [("Bldg", 12), ("Occupants", 20), ("Each sex needs", 26), ("WC men", 16), ("WC women", 18),
                                             ("Lav men", 16), ("Lav women", 18), ("Fountains (need)", 28), ("Service sinks", 22),
                                             ("Walk, clean floor ft", 32), ("Walk, support ft", 30)], rows, 2.5)
    o.append(tb)
    rows = [[d["core"], f"{d['dfu']:g}", f"{d['branch_in']} in", f"{d['building_dfu']:g}", f"{d['building_drain_in']} in"] for d in P["drains"]]
    tb, y2 = table(bp.AX0 + 10, y + 10, [("Core", 26), ("dfu", 14), ("Branch", 18), ("Building dfu", 22), ("Building drain at 1/4 in/ft", 40)], rows, 2.5)
    o.append(tb)
    rows = [[s["at"], s["building"]] for s in P["showers"]]
    tb, _ = table(bp.AX0 + 200, y + 10, [("Emergency shower and eyewash at", 60), ("Bldg", 14)], rows, 2.5)
    o.append(tb)
    t, _ = notes(bp.AX0 + 320, y + 12, [
        "Counts: IPC Table 403.1, factory and industrial row (assumed for H-5: the table has no H row, the code official decides); "
        "separate rooms for each sex (403.2); a toilet within 500 ft of walking, one story away at most (403.3.3).",
        "Drains: Table 709.1 fixture units; branches by Table 710.1(2); building drains by Table 710.1(1) at 1/4 in per foot.",
        "Emergency showers and eyewashes follow ISEA Z358.1 (411.1), not read: placement and flow cannot say.",
        "Domestic water sizing and the site services wait for a real site: licensed review.",
    ], 2.6, 90, "NOTES")
    o.append(t)
    return "".join(o)


def fp201(C):
    P = C.P

    def draw(M, b):
        o = [boxes(M, [(t["x0"], t["y0"], t["x1"], t["y1"]) for _, t in C.tools_in(0)], GREY, "#f2f3f5", 0.04)]
        o.append(boxes(M, [e["box"] for e in of(C, "IfcPipeSegment", lambda e: e["bld"] == 0 and "sprk/branch" in e["key"] and e["storey"] == "cleanroom")], RED, RED, 0.08))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcPipeSegment", lambda e: e["bld"] == 0 and "sprk/main" in e["key"])], INK, INK, 0.4))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcPipeSegment", lambda e: e["bld"] == 0 and "sprk/riser" in e["key"])], BLUE, BLUE, 0.6))
        return "".join(o)
    o, h = plan_p1(C, "FP-201", "SPRINKLER MAINS, RISERS AND STANDPIPES, PHASE 1", 384, draw,
                   "Clean floor branch lines (red), cross mains along the spine edges (black), the riser at the west end (blue).")
    sp = P["standpipes"]
    s = P["sprinkler_piping"]
    t, _ = notes(bp.AX0 + 10, bp.AY0 + h + 6, [
        f"Each building: a riser, cross mains on the clean floor and the support floor, {s['branch_lines']:,} branch lines over the head arrays.",
        "Pipe sizes assumed; the design density, area and hydraulic calculation follow NFPA 13, not read: cannot say.",
        f"Standpipes not required (905.3.1): {sp['stories']} stories, the highest floor {sp['highest_floor_ft']} ft above fire department "
        "access (under 30 ft).",
        "Fire water supply, the fire department connection and the pumps wait for a real site: licensed review.",
    ], 2.6, 150, "NOTES")
    return o + t


def fa201(C):
    P = C.P
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "ALARM BOXES, NOTIFICATION AND DETECTION", 4.2, weight="bold")]
    rows = [[a["key"].replace("permit/pull/", ""), f"{a['to_exit_ft']:.1f}", f"{a['handle_in']:.1f}"] for a in P["alarm_boxes"]]
    n = (len(rows) + 2) // 3
    for i in range(3):
        tb, _ = table(bp.AX0 + 10 + i * 100, bp.AY0 + 16, [("Box", 44), ("To exit, ft", 22), ("Handle, in", 22)], rows[i * n:(i + 1) * n], 2.3)
        o.append(tb)
    h = P["ht_detection"]
    rows = [[x, "air-sampling detector"] for x in h["bays"]] + [[x, "spot smoke detector"] for x in h["rooms"]]
    tb, _ = table(bp.AX0 + 320, bp.AY0 + 16, [("Where highly toxic gas is used or stored", 60), ("Detection", 40)], rows, 2.3)
    o.append(tb)
    nt = P["notification"]
    t, _ = notes(bp.AX0 + 440, bp.AY0 + 16, [
        f"Every manual alarm box within 5 ft of the entrance to its exit (907.4.2.1) and its handle 42 to 48 in above the floor (907.4.2.2).",
        f"{nt['devices']} horns and strobes on an assumed spacing; audible 15 dBA over the ambient (907.5.2.1.1); circuits in employee "
        f"work areas with {nt['spare_capacity']:.0%} spare capacity (907.5.2.3.1). The layout follows NFPA 72, not read: cannot say.",
        "Automatic fire detection where highly toxic compressed gases are stored or used, with a local alarm (IFC 6004.2.2.9).",
        "Gas detection at every tool that draws hazardous gas and in every gas room (FA-101).",
    ], 2.6, 80, "NOTES")
    o.append(t)
    return "".join(o)


def e101(C):
    P = C.P

    def draw(M, b):
        o = [boxes(M, [e["box"] for e in C.M["elements"] if e["cls"] == "IfcColumn" and e["bld"] == 0], INK, INK, 0.04)]
        o.append(boxes(M, [e["box"] for e in of(C, "IfcSpace", lambda e: e["bld"] == 0 and e["storey"] == "support floor")], GREY, "#f1f1f1", 0.08))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcElectricDistributionBoard", lambda e: e["bld"] == 0)], RED, RED, 0.2))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcLightFixture", lambda e: e["bld"] == 0 and e["otype"] == "luminaire")], AMBER, "#fff2cc", 0.1))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcLightFixture", lambda e: e["bld"] == 0 and e["otype"] in ("emergency luminaire", "exit sign"))], GREEN, GREEN, 0.15))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcTransportElement", lambda e: e["bld"] == 0)], INK, "#d8d2e8", 0.2))
        return "".join(o)
    o, h = plan_p1(C, "E-101", "POWER AND LIGHTING PLAN, PHASE 1", 384, draw,
                   "Support floor panelboards (red), luminaires (amber); emergency luminaires and exit signs on both floors (green); the lift.")
    E, S = P["emergency_lighting"], P["exit_signs"]
    t, _ = notes(bp.AX0 + 10, bp.AY0 + h + 6, [
        f"Exit signs along the spine, the perimeter and every exit passageway: at most {S['P1']['max_to_sign_ft']} ft and "
        f"{S['P2']['max_to_sign_ft']} ft from a sign (100 ft limit, 1013.1).",
        f"Emergency lighting on 90 minutes of battery (1008.3.1): average {E['P1']['avg_fc_lo']} to {E['P1']['avg_fc_hi']} fc and minimum "
        f"{E['P1']['min_fc_lo']} to {E['P1']['min_fc_hi']} fc along the paths in phase 1 (1 and 0.1 asked, 1008.3.2), over the assumed "
        "luminaire output.",
        "Wiring, fault currents and hazardous locations follow NFPA 70, not read: cannot say.",
    ], 2.6, 150, "NOTES")
    return o + t


def e602(C):
    P = C.P
    o = [text(bp.AX0 + 10, bp.AY0 + 8, "PANEL SCHEDULE", 4.2, weight="bold")]
    rows = [[p["id"], "-" if p["bay"] is None else f"bay {p['bay'] + 1:02d}", p["rating_kva"], f"{p['load_kva']:,.0f}", p["tools"],
             "generators" if p["emergency"] else "normal"] for p in P["panels"]]
    n = (len(rows) + 1) // 2
    cols = [("Panel", 26), ("Serves", 18), ("Rating kVA", 20), ("Load kVA", 20), ("Tools", 14), ("Source", 22)]
    tb, _ = table(bp.AX0 + 10, bp.AY0 + 16, cols, rows[:n], 2.4)
    o.append(tb)
    tb, _ = table(bp.AX0 + 140, bp.AY0 + 16, cols, rows[n:], 2.4)
    o.append(tb)
    t, _ = notes(bp.AX0 + 280, bp.AY0 + 16, [
        "One panelboard for each bay's tools (split where a bay's connected load exceeds the largest panel), a lighting panel and an "
        "emergency panel on the generators in each building (the loads of 415.11.11).",
        "Ratings from an assumed list of sizes; loads are the tool cards' connected kVA.",
        "Feeders, breakers, fault currents, grounding and hazardous-location wiring follow NFPA 70, not read: cannot say.",
    ], 2.6, 90, "NOTES")
    o.append(t)
    return "".join(o)


BODIES = {"A-201": a201, "A-301": lambda C: sections(C, "A-301", False), "A-402": a402, "A-501": a501, "A-602": a602,
          "S-301": lambda C: sections(C, "S-301", True), "S-601": s601, "M-201": m201, "M-602": m602, "PP-201": pp201,
          "P-201": p201, "FP-201": fp201, "FA-201": fa201, "E-101": e101, "E-602": e602}


def specs_dd(C, sec):
    """The specifications outline grown for design development: what each division now holds."""
    P = C.P
    sec = {k: (n, list(v)) for k, (n, v) in sec.items()}
    sec["03"][1].append(f"Combined footings where pads would overlap ({sum(1 for x in P['members']['footings'] if x['combined'])} columns).")
    sec["05"][1].append("Members by required properties (S-601): column areas and beam section moduli; risk category IV (assumed).")
    sec["07"][1].append(f"Listed through-penetration firestops at {len(P['firestops'])} penetrations of rated walls (714.4.1.2).")
    sec["08"][1].append("Door ratings by Table 716.1(2): 90 min in 2 h exit enclosures and fire barriers, 1 h in exit passageways; "
                        "chase doors and toilet doors unrated.")
    sec["09"][1].append("Wall types WT-1 and WT-2 (IBC Table 721.1(2) items 13-1.1 and 13-1.2), WT-C cleanroom panels, WT-P partitions.")
    sec["10"] = ("Specialties", ["Exit signs, internally lit, 90 min battery (1013.1); toilet accessories and partitions in the toilet cores "
                                 "(ICC A117.1 not read)."])
    sec["13"][1].append("Chase partitions with the tools bulkheaded through; gas cabinets for highly toxic and toxic gases (6004.1.2).")
    sec["14"] = ("Conveying equipment", ["A passenger lift in each building, support floor to clean floor (1104.4); ASME A17.1 not read."])
    sec["21"][1].append("Sprinkler risers, cross mains and branch lines (pipe sizes assumed); standpipes not required (905.3.1).")
    sec["22"][1].append("Toilet cores by IPC Table 403.1 (factory row, assumed for H); drains by Tables 709.1 and 710.1; emergency "
                        "showers and eyewashes (ISEA Z358.1 not read).")
    sec["23"][1].append("Chase exhaust at 6.5 air changes an hour; hazardous exhaust by kind (IMC 509.4), no dampers (509.6.1); "
                        "make-up air units balanced to the exhaust (509.5.5).")
    sec["26"][1].append(f"{len(P['panels'])} panelboards; emergency lighting along the paths of egress, 90 min (1008.3).")
    sec["28"][1].append("Manual alarm boxes within 5 ft of each exit at 42 to 48 in (907.4.2); horns and strobes with 20% spare "
                        "capacity (NFPA 72 not read); detection where highly toxic gas is used (IFC 6004.2.2.9).")
    return dict(sorted(sec.items()))
