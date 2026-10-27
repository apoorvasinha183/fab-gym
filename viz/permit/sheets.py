"""D9, the document set (docs/PERMIT.md): 22 sheets as SVG in the place profile's paper and units, a specifications
outline, and the set as one PDF printed by headless Chrome. Every sheet carries the truth line and NOT FOR
CONSTRUCTION; the numbers on it come from permit.json, so the sheets, the IFC and the ledger never disagree.
"""

import hashlib
import math
import subprocess
import textwrap
from pathlib import Path

import blueprint as bp
from blueprint import GREY, INK, RED, Map, esc, line, rect, text
from ctx import FT, TRUTH

SHEETS = [
    ("G-001", "Cover, drawing index and project data"), ("G-002", "Code analysis"), ("G-003", "Readiness ledger"),
    ("G-101", "Life safety plan, phase 1"), ("G-102", "Life safety plan, phase 2"), ("C-101", "Site plan and lot"),
    ("C-201", "Site utilities"), ("S-001", "Structural notes, design data and loads"), ("S-101", "Foundation plan"),
    ("S-201", "Framing plan and roof structure"), ("A-401", "Enlarged plans: exits and rooms"),
    ("A-601", "Schedules: doors, rooms, fire ratings"), ("M-101", "Sub-fab plan, phase 1"), ("M-401", "Cleanroom air"),
    ("M-601", "Mechanical equipment schedules"), ("PP-101", "Process piping and tool connections"),
    ("PP-301", "Process exhaust and drains"), ("P-101", "Plumbing"), ("FP-101", "Fire sprinklers"),
    ("FA-101", "Fire alarm and gas detection"), ("E-001", "One-line diagram"), ("E-601", "Electrical schedules"),
]
DATE = "27 Oct 2026"
REV = "S1 schematic for review"
SUBTITLE = "Schematic permit set, all trades, for review"
PROJECT = "Fab Gym campus"
GREEN, AMBER, BLUE = "#2e7d32", "#b26a00", "#1f5fa8"
VCOL = {"met": GREEN, "not met": RED, "cannot say": AMBER}
SCOL = {"checked": GREEN, "assumed": BLUE, "drawn": INK, "open": AMBER, "licensed review": "#6a3fa0", "missing": RED}
from profiles import f  # noqa: E402


def frame(sid, title, body, sha):
    W, H = bp.W, bp.H
    FX0, FY0, FX1, FY1, TB = bp.FX0, bp.FY0, bp.FX1, bp.FY1, bp.TB
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(W)} {f(H)}" width="{f(W)}mm" height="{f(H)}mm" font-family="{bp.FONT}">',
         rect(0, 0, W, H, "none", 0, "#ffffff"), rect(FX0, FY0, FX1 - FX0, FY1 - FY0, INK, 0.7), body]
    y0 = FY1 - TB
    o.append(line(FX0, y0, FX1, y0, INK, 0.5))
    cols = [FX0, FX0 + 230, FX0 + 450, FX0 + 570, FX0 + 690, FX1]
    for c in cols[1:-1]:
        o.append(line(c, y0, c, FY1, INK, 0.35))
    o.append(text(cols[0] + 5, y0 + 10, PROJECT, 6, weight="bold"))
    o.append(text(cols[0] + 5, y0 + 18, SUBTITLE, 3.2))
    o.append(text(cols[0] + 5, y0 + 27, TRUTH, 2.8))
    o.append(text(cols[0] + 5, y0 + 33, "Codes: 2024 IBC and IFC as published, for a hypothetical jurisdiction that adopts them unamended.", 2.3, fill=GREY))
    o.append(text(cols[0] + 5, y0 + 39, bp.PR.units_line() + " Assumed numbers are marked; see G-002 and G-003.", 2.3, fill=GREY))
    o.append(text(cols[0] + 5, y0 + 45, f"Drawn from results/layout-real/layout.json, sha256 {sha}; no tool, stocker or rail moved.", 2.3, fill=GREY))
    o.append(text(cols[1] + 5, y0 + 8, "DRAWING", 2.2, fill=GREY))
    for i, ln in enumerate(textwrap.wrap(title, 40)):
        o.append(text(cols[1] + 5, y0 + 17 + i * 6.5, ln, 4.6, weight="bold"))
    o.append(text(cols[2] + 5, y0 + 8, "SCALE", 2.2, fill=GREY))
    o.append(text(cols[2] + 5, y0 + 18, SCALES.get(sid, f"as shown, {bp.PR.paper}"), 3.2))
    o.append(text(cols[2] + 5, y0 + 30, "DATE", 2.2, fill=GREY))
    o.append(text(cols[2] + 5, y0 + 39, DATE, 4.0))
    o.append(text(cols[3] + 5, y0 + 8, "REVISION", 2.2, fill=GREY))
    o.append(text(cols[3] + 5, y0 + 18, REV, 3.4))
    o.append(text(cols[3] + 5, y0 + 30, "STATUS", 2.2, fill=GREY))
    o.append(text(cols[3] + 5, y0 + 40, "NOT FOR CONSTRUCTION", 3.4, weight="bold", fill=RED))
    o.append(text(cols[4] + 5, y0 + 8, "SHEET", 2.2, fill=GREY))
    o.append(text((cols[4] + cols[5]) / 2, y0 + 34, sid, 15, "middle", "bold"))
    o.append("</svg>")
    return "".join(o)


SCALES = {}
CURRENT = SHEETS      # the stage's sheets; design development appends its own (dd_sheets)


def scale_label(ratio):
    lab = {480: '1" = 40\'-0"', 1500: '1" = 125\'-0"', 128: '3/32" = 1\'-0"', 384: '1/32" = 1\'-0"', 768: '1/64" = 1\'-0"', 1536: '1/128" = 1\'-0"', 96: '1/8" = 1\'-0"', 192: '1/16" = 1\'-0"',
           2400: '1" = 200\'-0"', 3000: '1" = 250\'-0"'}
    return (lab.get(ratio, f"1:{ratio}") if bp.PR.imperial else f"1:{ratio}") + f" on {bp.PR.paper}"


def scalebar(x, y, ratio, length_m):
    k = 1000.0 / ratio
    unit = FT if bp.PR.imperial else 1.0
    n = 4
    L = length_m / unit
    step = L / n
    o = []
    for i in range(n):
        o.append(rect(x + i * step * unit * k, y, step * unit * k, 1.8, INK, 0.15, INK if i % 2 == 0 else "#fff"))
        o.append(text(x + i * step * unit * k, y - 1.2, f(i * step, 0), 2.0, "middle"))
    o.append(text(x + L * unit * k, y - 1.2, f"{f(L, 0)} {'ft' if bp.PR.imperial else 'm'}", 2.0, "middle"))
    return "".join(o)


def table(x, y, cols, rows, size=2.3, rh=None, fill_head="#e8edf3", colors=None):
    """cols: [(title, width_mm)]; rows: lists of strings. Returns (svg, bottom y)."""
    rh = rh or size * 2.3
    o = [rect(x, y, sum(w for _, w in cols), rh, INK, 0.2, fill_head)]
    cx = x
    for t, w in cols:
        o.append(text(cx + 1.2, y + rh - size * 0.75, t, size, weight="bold"))
        cx += w
    yy = y + rh
    for r, row in enumerate(rows):
        if r % 2 == 1:
            o.append(rect(x, yy, sum(w for _, w in cols), rh, "none", 0, "#f6f8fa"))
        cx = x
        for c, ((t, w), v) in enumerate(zip(cols, row)):
            s = str(v)
            maxc = max(4, int(w / (size * 0.52)))
            if len(s) > maxc:
                s = s[:maxc - 1] + "~"
            col = (colors or {}).get((r, c), INK)
            o.append(text(cx + 1.2, yy + rh - size * 0.75, s, size, fill=col))
            cx += w
        yy += rh
    o.append(line(x, yy, x + sum(w for _, w in cols), yy, INK, 0.2))
    return "".join(o), yy


def notes(x, y, lines_, size=2.6, width=110, head=None):
    o = []
    if head:
        o.append(text(x, y, head, size + 0.8, weight="bold"))
        y += size * 2.4
    for ln in lines_:
        for i, w in enumerate(textwrap.wrap(ln, width)):
            o.append(text(x + (0 if i == 0 else 3), y, w, size))
            y += size * 1.45
        y += size * 0.4
    return "".join(o), y


def bld_outline(M, b, sw=0.4):
    x, y, w, h = M.box(b["x0"], b["y0"], b["x1"], b["y1"])
    return rect(x, y, w, h, INK, sw, "#ffffff")


def boxes(M, items, stroke=INK, fill="none", sw=0.12):
    o = []
    for bx in items:
        x, y, w, h = M.box(bx[0], bx[1], bx[3] if len(bx) == 6 else bx[2], bx[4] if len(bx) == 6 else bx[3])
        o.append(rect(x, y, max(w, 0.15), max(h, 0.15), stroke, sw, fill))
    return "".join(o)


def of(C, cls, pred=lambda e: True):
    return [e for e in C.new if e["cls"] == cls and pred(e)]


# ------------------------------------------------------------------ the sheets

def g001(C, V, L):
    dd = C.P.get("stage") in ("dd", "cd")
    head = {"dd": ": design development set", "cd": ": construction documents, lithography bay 09"}.get(C.P.get("stage"), ": schematic permit set")
    o = [text(bp.AX0 + 10, bp.AY0 + 20, PROJECT + head, 14, weight="bold"),
         text(bp.AX0 + 10, bp.AY0 + 31, TRUTH + " Every sheet is NOT FOR CONSTRUCTION.", 4.2, fill=GREY)]
    rows = [[sid, t] for sid, t in CURRENT]
    t, yb = table(bp.AX0 + 10, bp.AY0 + 42, [("Sheet", 22), ("Title", 120)], rows, 2.8 if len(rows) <= 22 else 2.4)
    o.append(t)
    t, _ = table(bp.AX0 + 10, yb + 6, [("File", 40), ("What", 102)], [["specs.md", "Specifications outline by MasterFormat division"],
                 ["fab-permit.ifc", "IFC4 model: every element, FabGym_Basis and FabGym_Permit"], ["permit.json", "Every number on these sheets"],
                 ["verdicts.json", "Every rule's verdict with its citation"], ["ledger.json", "The readiness ledger"]], 2.6)
    o.append(t)
    P = C.P
    c = P["construction"]
    lines_ = [
        f"Jurisdiction: {P['jurisdiction']}.",
        "Codes read and cited (register viz/permit/codes/us-2024.json): 2024 International Building Code and 2024 International Fire Code, "
        f"{len(C.reg['sections'])} sections, each with the SHA-256 of its text as shown in ICC's reader on 27 Oct 2026. No copy of the code is kept.",
        "Not read, so every rule resting on them says cannot say: " + "; ".join(n["id"] for n in C.reg["not_read"]) + ".",
        f"Occupancy: Group H-5 (both buildings). Construction type: {c['type']}, sprinklered throughout. "
        f"Height {c['by_building']['P1']['height_ft']} ft; {c['by_building']['P1']['stories']} stories above grade (assumed: the waffle slab and the air space are not stories).",
        f"Fab areas: one per building, each inside the aggregates of Table 415.11.1.1; fire barriers {P['fab_areas'][0]['barrier_h']} h.",
        "Site: a hypothetical lot 20 m outside the campus's roads (assumed). Design data (seismic, wind, snow, climate, soil) are assumed, with ranges; "
        "a real site's data replace them.",
        f"Readiness (G-003): " + ", ".join(f"{k} {v}" for k, v in L["counts"].items() if v) + ". Gate: no item missing.",
        "A permit needs a real site and the seals of an architect and engineers licensed where the fab is built. No pipeline gives either. "
        "This set is schematic design across every trade: what a design team would carry into design development.",
    ]
    if dd:
        lines_[-1] = ("A permit needs a real site and the seals of an architect and engineers licensed where the fab is built. No pipeline "
                      "gives either. This set is design development across every trade, at LOD 300: what a design team would carry "
                      "into construction documents.")
        if C.P.get("stage") == "cd":
            lines_.insert(-1, "Construction documents for one bay, lithography bay 09 in phase 1, at LOD 400 (sheets A-110 to FA-110), "
                              "as the sample the other bays would follow; the rest of the fab stays at design development. Seismic "
                              "values for a point near Salem in the Willamette Valley, Oregon (USGS, ASCE 7-22); no real site.")
        lines_.insert(-1, "Design development, on the stricter reading of two judgements (assumed, for the authority to confirm): the "
                          "chases are service corridors (IBC 415.11.3) and the risk category is IV (Table 1604.5). The layout has a "
                          "1.6 m chase and a 1.6 m cross aisle on every wall of tools; see results/layout-real-dd/rescore.md.")
    t, y = notes(bp.AX0 + 170, bp.AY0 + 46, lines_, 2.9, 120, "PROJECT DATA")
    o.append(t)
    y += 8
    o.append(text(bp.AX0 + 170, y, "SEALS", 3.8, weight="bold"))
    for i, who in enumerate(("Architect of record", "Structural engineer", "Mechanical and plumbing engineer", "Electrical and fire protection engineer")):
        x = bp.AX0 + 170 + i * 95
        o.append(rect(x, y + 4, 85, 55, GREY, 0.3, "#fafafa"))
        o.append(text(x + 42.5, y + 30, "No seal", 4, "middle", fill=RED, weight="bold"))
        o.append(text(x + 42.5, y + 52, who, 2.6, "middle", fill=GREY))
    return "".join(o)


def g002(C, V, L):
    o = [text(bp.AX0 + 5, bp.AY0 + 8, "CODE ANALYSIS: every rule, what it cites, and its verdict for everything it binds", 4.2, weight="bold"),
         text(bp.AX0 + 5, bp.AY0 + 14, "Met, not met, or cannot say: when an input is missing, the law it rests on is not read, it applies only if "
              "a judgement is made, or an assumed number's range could flip it.", 2.6, fill=GREY)]
    rows, colors = [], {}
    rules = C.rules
    for r, ru in enumerate(rules):
        vs = [v for v in V if v["rule"] == ru["id"]]
        cnt = {k: sum(1 for v in vs if v["verdict"] == k) for k in ("met", "not met", "cannot say")}
        worst = "not met" if cnt["not met"] else "cannot say" if cnt["cannot say"] else "met"
        ex = next((v for v in vs if v["verdict"] == worst), vs[0])
        summary = f"{worst}" + (f" ({cnt['met']} met, {cnt['not met']} not met, {cnt['cannot say']} cannot say)" if len(vs) > 1 else "")
        rows.append([ru["id"], ru["topic"], ", ".join(ru["cite"]), f"{len(vs)}: {', '.join(sorted({v['scope'] for v in vs}))}", summary, ex["why"]])
        colors[(r, 4)] = VCOL[worst]
    rh = min(4.95, (bp.AY1 - bp.AY0 - 22) / max(1, len(rows) + 1))
    t, _ = table(bp.AX0 + 5, bp.AY0 + 19, [("Rule", 52), ("Topic", 34), ("Cites", 80), ("Binds", 100), ("Verdict", 88), ("Why (first case)", 664)],
                 rows, 2.15 if rh >= 4.9 else 1.95, rh=rh, colors=colors)
    o.append(t)
    return "".join(o)


def g003(C, L):
    o = [text(bp.AX0 + 5, bp.AY0 + 8, "READINESS LEDGER: every item a fab permit set needs, before any of it is built", 4.2, weight="bold"),
         text(bp.AX0 + 5, bp.AY0 + 14, "Counts: " + ", ".join(f"{k} {v}" for k, v in L["counts"].items()) +
              ". Gate: no item missing. Licensed review: done as far as a pipeline can; a licensed person judges it.", 2.6, fill=GREY)]
    rows, colors = [], {}
    for r, i in enumerate(L["items"]):
        rows.append([i["id"], i["discipline"], i["item"], i["sheet"], i["stage"], i["status"], i["why"]])
        colors[(r, 5)] = SCOL[i["status"]]
    rh = min(6.6, (bp.AY1 - bp.AY0 - 22) / max(1, len(rows) + 1))
    t, _ = table(bp.AX0 + 5, bp.AY0 + 19, [("Item", 40), ("Disc.", 12), ("What", 150), ("Sheet", 26), ("Stage", 12), ("Status", 28), ("Why", 750)],
                 rows, 2.1 if rh >= 5.5 else 1.9, rh=rh, colors=colors)
    o.append(t)
    return "".join(o)


def heat(C, M, key, story):
    g, dist, reach = C.grids[key]
    a = g.coarse(dist, 8)
    lim = C.fact("IBC T1017.2", "H5_sprinklered_ft") * FT
    o = []
    s = g.step * 8
    for iy in range(a.shape[0]):
        for ix in range(a.shape[1]):
            d = a[iy, ix]
            if d < 0:
                continue
            frac = min(1.0, d / lim)
            col = "#%02x%02x%02x" % (int(220 + 30 * frac), int(240 - 120 * frac), int(225 - 150 * frac))
            x0, y0 = g.x0 + ix * s, g.y0 + iy * s
            x, y, w, h = M.box(x0, y0, x0 + s, y0 + s)
            o.append(rect(x, y, w + 0.05, h + 0.05, "none", 0, col))
    return "".join(o)


def life_safety(C, p):
    S, P = C.S, C.P
    k = C.keys[p]
    b = C.blds[p]
    ratio = 480
    SCALES[f"G-10{p + 1}"] = scale_label(ratio)
    o = []
    tx = bp.AX0 + 8 + (b["x1"] - b["x0"] + 4) * 1000 / ratio + 15
    for n, story in enumerate(("clean floor", "support floor")):
        oy = bp.AY0 + 12 + n * 322
        M = Map(ratio, b["x0"] - 2, b["y1"] + 6, bp.AX0 + 8, oy)
        o.append(text(bp.AX0 + 8, oy - 3, f"{k} {story.upper()} ({bp.PR.level(S['clean_z'] if story == 'clean floor' else 0)}): "
                      "walking distance to the nearest exit, shaded to the limit", 3.4, weight="bold"))
        o.append(bld_outline(M, b))
        o.append(heat(C, M, (k, story), story))
        if story == "clean floor":
            o.append(boxes(M, [(t["x0"], t["y0"], t["x1"], t["y1"]) for _, t in C.tools_in(p)], GREY, "#e4e7eb", 0.05))
            o.append(boxes(M, [(s["x0"], s["y0"], s["x1"], s["y1"]) for s in S["stockers"] if (s["x0"] < b["x1"] and s["x1"] > b["x0"])], INK, "#9aa0a8"))
        else:
            o.append(boxes(M, [e["box"] for e in C.M["elements"] if e["cls"] == "IfcColumn" and e["bld"] == p], INK, INK, 0.05))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcStair", lambda e: e["bld"] == p)], RED, "#f6d5d3", 0.25))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcSpace", lambda e: e["bld"] == p and "passageway" in e["name"]
                                                 and story == "support floor")], RED, "#fbe9e7", 0.2))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcSpace", lambda e: e["bld"] == p and "passageway" not in e["name"]
                                                 and e["storey"] == ("cleanroom" if story == "clean floor" else "support floor"))], BLUE, "#dbe8f7", 0.2))
        for x in P["exits"]:
            if x["building"] != k or story not in x["serves"]:
                continue
            if x["kind"] == "exterior door":
                px, py = (x["x"], 70.0 * x["side"]) if x["wall"] == "F" else ((b["x0"] if x["wall"] == "W" else b["x1"]), x["y"])
            elif x["kind"] == "exit passageway":
                px, py = x["x"], 30.0 * x["side"]
            else:
                px, py = x["x"], (0.0 if x["kind"] == "spine stair" else 71.7 * x["side"])
            sx, sy = M(px, py)
            o.append(f'<circle cx="{f(sx)}" cy="{f(sy)}" r="1.3" fill="{GREEN}"/>')
            o.append(text(sx + 1.6, sy - 1.4, x["id"].split("-")[1], 1.9, fill=GREEN, weight="bold"))
        e = P["egress"][k][story]
        g, dist, reach = C.grids[(k, story)]
        far = max((d, i) for i, (d, r) in enumerate(zip(dist, reach)) if r)
        fx, fy = g.centre(far[1])
        sx, sy = M(fx, fy)
        o.append(f'<circle cx="{f(sx)}" cy="{f(sy)}" r="1.6" fill="none" stroke="{RED}" stroke-width="0.4"/>')
        o.append(text(sx + 2, sy + 3, f"farthest point: {bp.PR.distu(far[0])}", 2.2, fill=RED))
        rows = [["Occupant load", f"{e['occupant_load']} ({'200' if story == 'clean floor' else '300'} sq ft gross each, T1004.5)"],
                ["Exits", f"{e['exits']} (need {e['exits_needed']}, T1006.3.3)"],
                ["Longest walk to an exit", f"{bp.PR.distu(e['max_travel_m'])} (limit {bp.PR.distu(e['limit_m'])}, T1017.2)"],
                ["Common path", f"{bp.PR.distu(e['common_path_m'])} (limit 75 ft, T1006.2.1)"],
                ["Exits apart", f"{bp.PR.distu(e['max_separation_m'])} (need a third of {bp.PR.distu(e['diagonal_m'])}, 1007.1.1)"],
                ["Exit door width", f"{e['door_width_in']} in (need {round(0.2 * e['occupant_load'], 1)} in, 1005.3.2)"]]
        if story == "clean floor":
            rows.append(["Stair width", f"{e['stair_width_in']} in (need {round(0.3 * e['occupant_load'], 1)} in, 1005.3.1)"])
        t, _ = table(tx, oy + 10, [("Check", 45), ("This story", 120)], rows, 2.5)
        o.append(t)
    o.append(scalebar(bp.AX0 + 8, bp.AY1 - 6, ratio, 60.96))
    t, _ = notes(tx + (180 if p == 1 else 0), bp.AY0 + (22 if p == 1 else 75), [
        "Walks are measured around tools, stockers, columns and rooms on a 0.5 m grid in eight directions, which errs long by at most 8.3%.",
        "Spine stairs (SC) rise in the spine between stockers with a lid under the hoist vehicles, and discharge at grade into an exit passageway (XP) "
        "across the support floor to the long facade. Facade stairs (FS) stand outside the long walls. Exterior doors (ED) serve the support floor.",
        "Common path is the walk from any point to a corridor that leads two ways (the spine, an aisle, a chase or the perimeter): an approximation.",
        "Exits placed greedily: the farthest point gets the nearest free exit until every limit is met. Nothing in the fab moved.",
    ], 2.5, 70 if p == 0 else 95, "NOTES")
    o.append(t)
    return "".join(o)


def c101(C):
    S, P = C.S, C.P
    ratio = 1500
    SCALES["C-101"] = scale_label(ratio)
    lot = C.permit["site"]["lot"]
    M = Map(ratio, min(p[0] for p in lot) - 10, max(p[1] for p in lot) + 10, bp.AX0 + 10, bp.AY0 + 20)
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "SITE PLAN: the campus on a hypothetical lot (assumed), lot lines and the HPM rooms' distances", 4, weight="bold")]
    xs, ys = [p[0] for p in lot], [p[1] for p in lot]
    x, y, w, h = M.box(min(xs), min(ys), max(xs), max(ys))
    o.append(rect(x, y, w, h, RED, 0.5, "none", ' stroke-dasharray="4 1.5 1 1.5"'))
    o.append(text(x + 2, y - 2, "LOT LINE (hypothetical, assumed)", 2.6, fill=RED))
    for c in S["campus"]:
        x, y, w, h = M.box(c["x0"], c["y0"], c["x1"], c["y1"])
        fill = {"fab": "#dfe6ef", "road": "#d9d9d9", "parking": "#efefef"}.get(c["kind"], "#f4f1ea")
        o.append(rect(x, y, w, h, INK, 0.2, fill))
        if c["label"] and c["kind"] not in ("road",):
            o.append(text(x + w / 2, y + h / 2 + 1, c["label"], 2.0, "middle"))
    for r in P["rooms"]:
        if r["kind"] in ("gas room", "chemical dispense"):
            sx, sy = M((r["box"][0] + r["box"][3]) / 2, 70.0 * r["side"])
            o.append(f'<circle cx="{f(sx)}" cy="{f(sy)}" r="1.2" fill="{RED}"/>')
            o.append(text(sx + 1.5, sy + (4 if r["side"] < 0 else -2), f"{r['id']}: {bp.PR.distu(r['lot_distance_m'])} to the lot line", 1.9, fill=RED))
    t, _ = notes(bp.AX0 + 600, bp.AY0 + 30, [
        "The lot is a rectangle 20 m outside the campus's roads, assumed: there is no real site. Every distance to a lot line is measured to it.",
        f"HPM rooms need an exterior wall at least {C.fact('IBC 415.11.6.4', 'lot_line_ft')} ft from the lot lines (415.11.6.4): each room's distance is shown.",
        "Fire apparatus access, hydrants and zoning (setbacks, height, use) follow the fire code's chapter 5 and the local zoning, which are not read: "
        "licensed review.",
    ], 2.7, 80, "NOTES")
    o.append(t)
    return "".join(o)


def c201(C):
    S, P = C.S, C.P
    ratio = 1500
    SCALES["C-201"] = scale_label(ratio)
    M = Map(ratio, -90, 250, bp.AX0 + 10, bp.AY0 + 20)
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "SITE UTILITIES: the central utility building to the two fabs", 4, weight="bold")]
    for c in S["campus"]:
        if c["kind"] in ("road", "parking"):
            continue
        x, y, w, h = M.box(c["x0"], c["y0"], c["x1"], c["y1"])
        o.append(rect(x, y, w, h, INK, 0.2, "#dfe6ef" if c["kind"] == "fab" else "#f4f1ea"))
        if c["label"]:
            o.append(text(x + w / 2, y + h / 2 + 1, c["label"], 2.0, "middle"))
    link = [c for c in S["campus"] if c["kind"] == "corridor"][0]
    for i, col in enumerate((BLUE, GREEN, AMBER, RED)):
        xx = link["x0"] + 4 + i * 6
        a, b_ = M(xx, -150), M(xx, -66)
        o.append(line(a[0], a[1], b_[0], b_[1], col, 0.6))
    for p, b in enumerate(C.blds):
        a, c = M(b["x0"] + 2, -66), M(b["x1"] - 2, -66)
        o.append(line(a[0], a[1], c[0], c[1], BLUE, 0.5, "3 1"))
    rows = [[u, d["name"], d["units"], f"{d['capacity']:,}"] for u, d in P["utilities"]["plant"].items()]
    t, _ = table(bp.AX0 + 600, bp.AY0 + 30, [("Utility", 45), ("Plant", 70), ("Units (N+1)", 22), ("Capacity", 30)], rows, 2.4)
    o.append(t)
    t, _ = notes(bp.AX0 + 600, bp.AY0 + 140, ["Routes run from the central utility building through the utility link to a header along each fab's "
                                             "south support floor; site water, sewer, storm and gas services wait for a real site (licensed review)."], 2.6, 80)
    o.append(t)
    return "".join(o)


def s001(C):
    F = C.P["frame"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "STRUCTURAL NOTES: preliminary, for licensed review", 4.2, weight="bold")]
    rows = [[k, f"{v['value']} {v.get('unit', '')}", f"{v['lo']} to {v['hi']}", v["basis"]] for k, v in F["design_data"].items()]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Design data", 50), ("Value", 30), ("Range", 35), ("Basis", 70)], rows, 2.6)
    o.append(t)
    rows = [[k, f"{v} psf", "IBC T1607.1"] for k, v in F["live_load_psf"].items()]
    rows += [[k, f"{v} kPa", "assumed"] for k, v in {**F["dead_kpa"], **F["roof_dead_kpa"]}.items()]
    t, y = table(bp.AX0 + 10, y + 8, [("Load", 70), ("Value", 30), ("Source", 40)], rows, 2.6)
    o.append(t)
    vs = [v for v in C.V if v["topic"] == "structure"]
    rows = [[v["rule"], v["scope"], v["verdict"], v["why"]] for v in vs]
    t, y = table(bp.AX0 + 10, y + 8, [("Rule", 45), ("Scope", 30), ("Verdict", 22), ("Why", 300)], rows, 2.4,
                 colors={(i, 2): VCOL[v["verdict"]] for i, v in enumerate(vs)})
    o.append(t)
    t, _ = notes(bp.AX0 + 420, bp.AY0 + 20, [
        f"Total load to the footings {F['total_load_kN']:,.0f} kN (independent check {F['total_load_check_kN']:,.0f} kN).",
        f"Floor {F['floor_kpa']} kPa (dead plus {F['live_load_psf']['clean floor']} psf live); roof {F['roof_kpa']} kPa.",
        "Support floor columns take the waffle slab by tributary area; roof trusses span from the spine edge to the perimeter strip on roof "
        f"columns at the mid grid lines, on their own footings apart from the slab; truss depth {F['truss_depth_m']} m (assumed).",
        "Seismic and wind design wait for ASCE 7 (not read) and a real site; the risk category is a judgement for the authority (III or IV).",
        f"The waffle slab's first frequency per grid bay is estimated as a simply supported plate (the lower bound) against an assumed {F['waffle']['target_hz']} Hz.",
    ], 2.7, 85, "NOTES")
    o.append(t)
    return "".join(o)


def plan_both(C, ratio, title, draw):
    o = []
    oy = bp.AY0 + 22
    w0 = (C.blds[0]["x1"] - C.blds[0]["x0"] + 4) * 1000 / ratio
    for p, b in enumerate(C.blds):
        M = Map(ratio, b["x0"] - 2, b["y1"] + 2, bp.AX0 + 10 + (0 if p == 0 else w0 + 25), oy)
        o.append(text(M(b["x0"], 0)[0], M(0, b["y1"])[1] - 3, f"{C.keys[p]}: {title}", 3.0, weight="bold"))
        o.append(bld_outline(M, b))
        o.append(draw(M, p, b))
    return "".join(o)


def s101(C):
    F = C.P["frame"]
    SCALES["S-101"] = scale_label(480)
    pos = {c["id"]: c for c in F["columns"]}
    def draw(M, p, b):
        o = []
        for ft in F["footings"]:
            c = pos[ft["column"]]
            if c["p"] != p:
                continue
            s = ft["side_m"] / 2
            o.append(boxes(M, [(c["x"] - s, c["y"] - s, c["x"] + s, c["y"] + s)], INK, "#e9e3d7" if c["kind"] != "roof" else "#d7e3e9", 0.1))
        return "".join(o)
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "FOUNDATION PLAN: a pad footing under every column, sized on the assumed soil", 4.2, weight="bold"),
         plan_both(C, 480, "footings", draw)]
    big = max(F["footings"], key=lambda x: x["load_kN"])
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 340, [
        f"{len(F['footings'])} footings; the largest carries {big['load_kN']:,.0f} kN on {bp.PR.size(big['side_m'], big['side_m'])}.",
        f"Bearing {C.permit['design_data']['soil_bearing_kpa']['value']} kPa (assumed, range {C.permit['design_data']['soil_bearing_kpa']['lo']} to "
        f"{C.permit['design_data']['soil_bearing_kpa']['hi']}): a geotechnical report replaces it.",
        "Brown: support floor columns under the waffle slab. Blue: roof columns, on their own footings apart from the slab.",
    ], 2.8, 120, "NOTES")
    o.append(t)
    return "".join(o)


def s201(C):
    F = C.P["frame"]
    SCALES["S-201"] = scale_label(480)
    def draw(M, p, b):
        o = [boxes(M, [e["box"] for e in C.M["elements"] if e["cls"] == "IfcColumn" and e["bld"] == p], INK, INK, 0.05)]
        o.append(boxes(M, [e["box"] for e in of(C, "IfcColumn", lambda e: e["bld"] == p)], BLUE, BLUE, 0.05))
        for e in of(C, "IfcBeam", lambda e: e["bld"] == p):
            x0, y0, _, x1, y1, _ = e["box"]
            a, c = M((x0 + x1) / 2, y0), M((x0 + x1) / 2, y1)
            o.append(line(a[0], a[1], c[0], c[1], BLUE, 0.3))
        o.append(boxes(M, [e["box"] for e in of(C, "IfcMember", lambda e: e["bld"] == p)], RED, RED, 0.3))
        return "".join(o)
    fs = [x["f1_hz"] for x in F["bays"]]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "FRAMING PLAN: support floor columns, roof columns and trusses, facade bracing", 4.2, weight="bold"),
         plan_both(C, 480, "framing", draw)]
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 340, [
        f"{len([c for c in F['columns'] if c['kind'] == 'roof'])} roof columns at the mid grid lines; trusses span {66.5 - 3.2:.1f} m; "
        f"{sum(1 for c in F['columns'] if c['kind'] == 'roof' and c['moved_m'])} roof columns moved along the grid to keep clear of the hoist vehicles.",
        f"Waffle slab first frequency, {len(fs)} grid bays: {min(fs)} to {max(fs)} Hz against an assumed {F['waffle']['target_hz']} Hz "
        "(simply supported plate; the real slab is stiffer at its edges).",
        "Red: braced bays in the long facades, sized after ASCE 7 (not read). Every member is preliminary, for licensed review.",
    ], 2.8, 120, "NOTES")
    o.append(t)
    return "".join(o)


def a401(C):
    P = C.P
    ratio, half = 128, 11.0
    SCALES["A-401"] = scale_label(ratio)
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "ENLARGED PLANS: a spine stair and its exit passageway, a facade stair, a gas room, a gowning room", 4.2, weight="bold")]
    core = next(x for x in P["exits"] if x["kind"] == "spine stair")
    tower = next(x for x in P["exits"] if x["kind"] == "facade stair")
    gas = next(r for r in P["rooms"] if r["kind"] == "gas room")
    gown = next(r for r in P["rooms"] if r["kind"] == "gowning")
    mid = lambda r: ((r["box"][0] + r["box"][3]) / 2, (r["box"][1] + r["box"][4]) / 2)
    cz = C.S["clean_z"]
    views = [(f"Spine stair {core['id']}, clean floor", core["x"], 0.0, cz),
             (f"Facade stair {tower['id']}, clean floor", *mid({"box": next(e["box"] for e in C.new if e["cls"] == "IfcStair" and tower["id"] in e["key"])}), cz),
             (f"Gas room {gas['id']}, support floor", *mid(gas), 0.0),
             (f"Gowning {gown['id']}, clean floor", *mid(gown), cz)]
    show = {"IfcWall", "IfcDoor", "IfcStair", "IfcSpace", "IfcSensor", "IfcAlarm", "IfcColumn"}
    side = 2 * half * 1000 / ratio
    for n, (title, cx, cy, fz) in enumerate(views):
        ox, oy = bp.AX0 + 10 + n * 255, bp.AY0 + 30
        x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
        M = Map(ratio, x0, y1, ox, oy)
        o.append(text(ox, oy - 6, title, 3.2, weight="bold"))
        o.append(f'<clipPath id="a401v{n}"><rect x="{f(ox)}" y="{f(oy)}" width="{f(side)}" height="{f(side)}"/></clipPath><g clip-path="url(#a401v{n})">')
        win = lambda bx: bx and bx[0] < x1 and bx[3] > x0 and bx[1] < y1 and bx[4] > y0 and bx[2] < fz + 3 and bx[5] > fz
        old = [e for e in C.M["elements"] if not e["key"].startswith("campus/") and win(e["box"])]
        o.append(boxes(M, [e["box"] for e in old if e["cls"] in ("IfcBuildingElementProxy", "IfcColumn")], GREY, "#eceef1", 0.08))
        o.append(boxes(M, [e["box"] for e in old if e["cls"] == "IfcWall"], INK, "#666", 0.1))
        for e in C.new:
            if e["cls"] not in show or not win(e["box"]):
                continue
            col = {"IfcWall": INK, "IfcDoor": RED, "IfcStair": BLUE, "IfcSpace": GREY, "IfcSensor": GREEN, "IfcAlarm": RED}.get(e["cls"], INK)
            fill = {"IfcWall": "#444", "IfcStair": "#e3ecf7", "IfcDoor": "#f6d5d3", "IfcColumn": INK}.get(e["cls"], "none")
            o.append(boxes(M, [e["box"]], col, fill, 0.15))
        o.append("</g>")
        o.append(rect(ox, oy, side, side, INK, 0.3))
        o.append(text(ox, oy + side + 6, f"{bp.PR.size(2 * half, 2 * half)} shown. Grey: tools, columns and outer walls already in the model.", 2.4, fill=GREY))
    rows = [[x["id"], x["kind"], f"{x.get('width_in', round(x['width_m'] / 0.0254))} in", f"{x.get('rating_h', '')} h" if x.get("rating_h") else "-",
             ", ".join(x["serves"])] for x in P["exits"]]
    t, _ = table(bp.AX0 + 10, bp.AY0 + 225, [("Exit", 28), ("Kind", 35), ("Width", 22), ("Rating", 18), ("Serves", 55)], rows[:52], 2.15, rh=5.0)
    o.append(t)
    t, _ = notes(bp.AX0 + 200, bp.AY0 + 230, [
        "Spine stairs: two flights in a 2 h enclosure 9.5 x 3.4 m (assumed), lid at 9.9 m under the hoist vehicles; doors on both sides of the spine; "
        "at grade a door into the exit passageway (1 h, 1024), doors from the support floor every 12 m, and a discharge door in the long facade.",
        "Facade stairs: outside the long walls, doors at the clean floor and the support floor, discharge door at grade.",
        "Gas rooms: support floor at the facade, exterior wall, 2 h barriers (415.11.6.1), exhausted at 2 cfm/sq ft (assumed), two gas detectors and an "
        "alarm at the door. Chemical dispense rooms the same, with an exterior door (415.11.6.2).",
        "Gowning: the west end of each clean floor. Emergency control station: in the office, outside both fab areas (415.11.10).",
    ], 2.6, 110, "NOTES")
    o.append(t)
    return "".join(o)


def a601(C):
    P = C.P
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "SCHEDULES: rooms, doors and fire ratings", 4.2, weight="bold")]
    rows = [[r["id"], r["kind"], r["building"], r["storey"] or "office", r["area_sqft"], f"{r['rating_h']} h", r.get("exhaust_cfm_sqft", "-"),
             "yes" if r.get("exterior_wall") else "no", round(r.get("lot_distance_m", 0) / FT) if r.get("lot_distance_m") else "-"] for r in P["rooms"]]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Room", 22), ("Kind", 35), ("Bldg", 14), ("Storey", 28), ("Sq ft", 16), ("Rating", 16),
                                             ("Exhaust cfm/sq ft", 30), ("Ext. wall", 16), ("To lot, ft", 18)], rows, 2.4)
    o.append(t)
    import collections
    doors = collections.Counter(e["name"].split(" ")[0] + " " + e["name"].split(" ")[1] for e in of(C, "IfcDoor"))
    rows = [[k, v, "1.2 m (47 in)"] for k, v in sorted(doors.items())]
    t, y2 = table(bp.AX0 + 10, y + 8, [("Door", 60), ("Count", 20), ("Leaf", 40)], rows, 2.4)
    o.append(t)
    rt = P["construction"]["ratings_h"]
    rows = [[k.replace("_h", "").replace("_", " "), f"{v} h", "IBC T601, type " + P["construction"]["type"]] for k, v in rt.items()]
    rows += [["fab area barriers", f"{P['fab_areas'][0]['barrier_h']} h", "IBC 415.11.1.2"], ["exit stair enclosures", "2 h", "IBC 1023.2 (1 h asked)"],
             ["exit passageways", "1 h", "IBC 1024.3"], ["HPM rooms", "2 h", "IBC 415.11.6.1, 415.11.6.2"], ["spine as corridor", "1 h", "IBC T1020.2"]]
    t, _ = table(bp.AX0 + 260, y + 8, [("Element", 50), ("Rating", 20), ("Source", 70)], rows, 2.4)
    o.append(t)
    t, _ = notes(bp.AX0 + 10, max(y2, y + 80) + 10, ["Door hardware, opening protectives and penetration firestopping follow IBC 716 and chapter 7, not read: "
                                                     "licensed review. Cleanroom finishes are assumed to the cleanliness class (M-401)."], 2.6, 160)
    o.append(t)
    return "".join(o)


def m101(C):
    SCALES["M-101"] = scale_label(384)
    b = C.blds[0]
    M = Map(384, b["x0"] - 2, b["y1"] + 2, bp.AX0 + 10, bp.AY0 + 20)
    o = [text(bp.AX0 + 10, bp.AY0 + 12, "SUB-FAB PLAN, PHASE 1: mains beside the spine, a lateral under every row, a drop to every tool", 4.2, weight="bold"),
         bld_outline(M, b)]
    col = {"IfcDuctSegment": AMBER, "IfcPipeSegment": BLUE, "IfcCableCarrierSegment": RED}
    for e in C.new:
        if e["bld"] == 0 and e["cls"] in col and "drop" not in e["key"]:
            o.append(boxes(M, [e["box"]], col[e["cls"]], "none", 0.08))
    o.append(boxes(M, [e["box"] for e in C.M["elements"] if e["cls"] == "IfcColumn" and e["bld"] == 0], INK, INK, 0.05))
    o.append(boxes(M, [e["box"] for e in of(C, "IfcSpace", lambda e: e["bld"] == 0 and e["storey"] == "support floor")], GREY, "#eee", 0.1))
    U = C.P["utilities"]
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 410, [
        "Amber: exhaust ducts. Blue: process pipes and drains. Red: cable trays. Grey: rooms and exit passageways. Ducts on the lower level (3.3 to "
        "4.5 m), pipes and trays above (from 4.6 m), laterals between 4.0 and 5.8 m; nothing below 3.0 m crosses an exit passageway.",
        f"{len(U['segments'])} pipe and duct segments sized by velocity (PP-101, PP-301); {len(U['connections'])} tools, each with one drop.",
    ], 2.7, 150, "NOTES")
    o.append(t)
    return "".join(o)


def m401(C):
    A = C.P["air"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "CLEANROOM AIR: cleanliness class, fan filter units and recirculated air by space", 4.2, weight="bold")]
    rows = [[s["bay"], f"ISO {s['iso_class']}", round(s["area_m2"]), s["ffu"], f"{s['coverage']:.0%}", f"{s['target']:.0%}", s["recirc_cfm_sqft"]] for s in A["bays"]]
    half = (len(rows) + 1) // 2
    cols = [("Space", 40), ("Class", 16), ("m2", 16), ("FFU", 14), ("Cover", 16), ("Target", 16), ("cfm/sq ft", 18)]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, cols, rows[:half], 2.3, rh=5.4)
    o.append(t)
    t, _ = table(bp.AX0 + 160, bp.AY0 + 18, cols, rows[half:], 2.3, rh=5.4)
    o.append(t)
    fe = A["fab_exhaust"]
    t, _ = notes(bp.AX0 + 320, bp.AY0 + 20, [
        f"{A['ffu_total']:,} fan filter units of 1.2 x 0.6 m at {A['face_m_s']} m/s (assumed). Coverage by class (assumed): "
        + ", ".join(f"ISO {k} {v:.0%}" for k, v in A["coverage_by_class"].items()) + ".",
        f"Recirculated air: {A['recirc_cfm_sqft_avg']} cfm/sq ft on average, {A['recirc_cfm_sqft_min']} at the least; 415.11.1.8 asks four and three "
        "times the 1 cfm/sq ft of 415.11.1.6 for the hazardous-location wiring waiver.",
        "Exhaust and make-up air: " + "; ".join(f"{x['fab_area']} {x['exhaust_cfm_sqft']} cfm/sq ft ({x['tool_exhaust_cfm']:,} from tools, "
                                               f"{x['general_exhaust_cfm']:,} general)" for x in fe) + ".",
        "If the chases are service corridors they need 6 air changes an hour (415.11.3.2): a judgement waits (G-002).",
        "Cleanliness classes are assumed by kind; ISO 14644-1 is not read, so their verification says cannot say.",
    ], 2.7, 100, "NOTES")
    o.append(t)
    return "".join(o)


def m601(C):
    A, U = C.P["air"], C.P["utilities"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "MECHANICAL EQUIPMENT SCHEDULES", 4.2, weight="bold")]
    rows = [[k.replace("_", " "), f"{v:,} kW"] for k, v in A["cooling"].items()] + [["total cooling", f"{A['cooling_kw']:,} kW"],
            ["chillers", f"{A['chillers']} x 3,500 kW = {A['chiller_kw']:,.0f} kW (N+1)"]]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Cooling load", 50), ("Value", 80)], rows, 2.6)
    o.append(t)
    rows = [[u.replace("_", " "), f"{d['connected']:,}", d["diversity"], f"{d['diversified']:,}", U["plant"][u]["name"], U["plant"][u]["units"],
             f"{U['plant'][u]['capacity']:,}"] for u, d in U["demand"].items()]
    t, _ = table(bp.AX0 + 10, y + 10, [("Utility", 40), ("Connected", 28), ("Diversity", 18), ("Diversified", 28), ("Plant", 70), ("Units", 14),
                                        ("Capacity", 28)], rows, 2.5)
    o.append(t)
    t, _ = notes(bp.AX0 + 10, bp.AY1 - 30, ["Units: L/min for liquids, standard L/min for gases, m3/h for exhaust, kVA for power. Every demand comes from "
                                           "the tool cards (assumed by kind, with ranges) and an assumed diversity; mechanical design to the IMC and "
                                           "ASHRAE (not read) is for licensed review."], 2.6, 180)
    o.append(t)
    return "".join(o)


def segs_sheet(C, title, pick):
    U = C.P["utilities"]
    segs = [s for s in U["segments"] if pick(s) and s["kind"] == "main"]
    lat = [s for s in U["segments"] if pick(s) and s["kind"] == "lateral"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, title, 4.2, weight="bold")]
    rows = [[s["id"], s["utility"], f"{s['flow_m3s']}", s["size"], s["runs"], s["velocity"], s["limit"]] for s in segs]
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Main", 60), ("Utility", 42), ("m3/s", 20), ("Size", 34), ("Runs", 12), ("m/s", 16), ("Limit", 14)], rows, 2.4)
    o.append(t)
    import collections
    byu = collections.defaultdict(list)
    for s in lat:
        byu[s["utility"]].append(s)
    rows = [[u, len(v), min(x["size"] for x in v), max(x["size"] for x in v), max(x["velocity"] for x in v), v[0]["limit"]] for u, v in sorted(byu.items())]
    t, y = table(bp.AX0 + 10, y + 10, [("Laterals", 42), ("Count", 16), ("Smallest", 34), ("Largest", 34), ("Fastest m/s", 22), ("Limit", 14)], rows, 2.4)
    o.append(t)
    return o, y


def pp101(C):
    U = C.P["utilities"]
    o, y = segs_sheet(C, "PROCESS PIPING: mains and laterals sized by velocity; every tool's connections",
                      lambda s: not s["utility"].startswith(("exhaust", "drain")))
    import collections
    kinds = collections.Counter()
    for i, t in enumerate(C.S["tools"]):
        kinds[(t["kind"], tuple(U["connections"][str(i)]))] += 1
    rows = [[k, n, ", ".join(c)] for (k, c), n in sorted(kinds.items())]
    t, _ = table(bp.AX0 + 260, bp.AY0 + 18, [("Tool kind", 24), ("Tools", 14), ("Connections at its drop", 220)], rows, 2.3)
    o.append(t)
    t, _ = notes(bp.AX0 + 10, y + 10, ["Velocity limits (assumed): water 2.5 m/s, gases 20 m/s at standard volume (overstates a pressurised line's "
                                       "velocity: the safe side). Hazardous gas from the gas rooms to the tools (double-contained, coaxial) follows "
                                       "the fire code's chapter 60 and SEMI S2, not read: licensed review."], 2.6, 120)
    o.append(t)
    return "".join(o)


def pp301(C):
    o, y = segs_sheet(C, "PROCESS EXHAUST AND DRAINS: by kind, sized by velocity", lambda s: s["utility"].startswith(("exhaust", "drain")))
    U, F = C.P["utilities"], C.P["fire"]
    t, _ = notes(bp.AX0 + 10, y + 10, [
        "Exhaust ducts 12 m/s in mains, 10 m/s in laterals; drains 1.5 m/s (assumed). Each kind runs to its own treatment in the central plant.",
        f"Sprinklers in solvent exhaust ducts of 10 in or more at {C.fact('IBC 415.11.12.3', 'horizontal_interval_ft')} ft: {F['duct_heads']} heads (415.11.12).",
        "Exhaust total, m3/s: " + ", ".join(f"{k.replace('exhaust_', '').replace('_m3h', '')} {v}" for k, v in U["exhaust_m3s"].items()) + ".",
    ], 2.7, 150, "NOTES")
    o.append(t)
    return "".join(o)


def p101(C):
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "PLUMBING", 4.2, weight="bold")]
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 25, [
        "Plumbing fixtures for the occupants: the counts follow the IPC 2024 and IBC chapter 29, not read. Open.",
        "Emergency showers and eyewashes at the chemical dispense rooms and wet benches: the standard is not read. Open.",
        "Process waste: acid, fluoride, solvent and slurry drains run to their treatment in the central plant (PP-301). Domestic water, sanitary and "
        "storm services wait for a real site.",
        f"Occupants for fixture counts: {sum(C.P['egress'][k]['clean floor']['occupant_load'] for k in C.keys)} on the clean floors and "
        f"{sum(C.P['egress'][k]['support floor']['occupant_load'] for k in C.keys)} on the support floors (egress loads, T1004.5; the fixture "
        "count uses its own loads).",
    ], 3.0, 150, "NOTES")
    o.append(t)
    return "".join(o)


def fp101(C):
    SCALES["FP-101"] = scale_label(384)
    b = C.blds[0]
    M = Map(384, b["x0"] - 2, b["y1"] + 2, bp.AX0 + 10, bp.AY0 + 20)
    o = [text(bp.AX0 + 10, bp.AY0 + 12, "FIRE SPRINKLERS, PHASE 1: arrays on the clean floor (shown) and the support floor", 4.2, weight="bold"), bld_outline(M, b)]
    o.append(boxes(M, [e["box"] for e in of(C, "IfcFireSuppressionTerminal", lambda e: e["bld"] == 0 and e["storey"] == "cleanroom")], RED, "#fde7e4", 0.08))
    F = C.P["fire"]
    rows = [[k, v] for k, v in F["hazard"].items()]
    t, _ = table(bp.AX0 + 400, bp.AY0 + 410, [("Space", 60), ("Hazard (T903.2.5.2)", 40)], rows, 2.5)
    o.append(t)
    t, _ = notes(bp.AX0 + 10, bp.AY0 + 410, [
        f"Sprinklers throughout (903.2.5.2): {F['sprinkler_heads']:,} heads counted at {F['head_area_sqft']} sq ft a head (assumed).",
        "The design density and area wait for NFPA 13 (not read): cannot say. Fire water supply and pumps: licensed review. Standpipes: IBC 905, not read.",
        f"Heads in solvent exhaust ducts of 10 in or more: {F['duct_heads']}.",
    ], 2.7, 110, "NOTES")
    o.append(t)
    return "".join(o)


def fa101(C):
    F = C.P["fire"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "FIRE ALARM AND GAS DETECTION", 4.2, weight="bold")]
    rows = [[f"bay {int(k) + 1:02d}", v, F["gas_sensors_by_bay"].get(k, 0)] for k, v in sorted(F["hpm_gas_tools_by_bay"].items(), key=lambda kv: int(kv[0]))]
    half = (len(rows) + 1) // 2
    t, y = table(bp.AX0 + 10, bp.AY0 + 18, [("Bay", 20), ("Tools drawing HPM gas", 38), ("Gas detectors", 28)], rows[:half], 2.4)
    o.append(t)
    t, _ = table(bp.AX0 + 100, bp.AY0 + 18, [("Bay", 20), ("Tools drawing HPM gas", 38), ("Gas detectors", 28)], rows[half:], 2.4)
    o.append(t)
    rows = [[k, v["kind"], v["sensors"], v["alarms"]] for k, v in F["gas_rooms"].items()]
    t, _ = table(bp.AX0 + 200, bp.AY0 + 18, [("Room", 24), ("Kind", 35), ("Detectors", 20), ("Alarms", 16)], rows, 2.4)
    o.append(t)
    t, _ = notes(bp.AX0 + 320, bp.AY0 + 20, [
        "Gas detection (415.11.8.1): at every tool that draws hazardous gas, in every gas room and gas cabinet; flammable gas alarms at a quarter of "
        "the lower flammable limit (415.11.8.2).",
        f"Manual fire alarm (907.2.5): {F['pull_stations']} pull stations, one at every exit on every floor it serves.",
        f"Smoke detection: {F['smoke_detectors']} air-sampling detectors, one per bay, sampling the return air (assumed).",
        "Alarms, detection and emergency power report to the emergency control station in the office (415.11.10).",
        "Smoke detection where highly toxic gas is used follows the fire code's chapter 60, and occupant notification 907.4.2, 907.5 and NFPA 72: not read, "
        "cannot say.",
    ], 2.7, 100, "NOTES")
    o.append(t)
    return "".join(o)


def e001(C):
    U = C.P["utilities"]
    pl = U["plant"]
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "ONE-LINE DIAGRAM (schematic)", 4.2, weight="bold")]
    x, y = bp.AX0 + 40, bp.AY0 + 40
    def node(x, y, w, h, label, col=INK):
        return rect(x, y, w, h, col, 0.35, "#fff") + text(x + w / 2, y + h / 2 + 1, label, 2.6, "middle")
    o.append(node(x, y, 70, 12, "Utility service (site, assumed)"))
    o.append(line(x + 35, y + 12, x + 35, y + 30, INK, 0.5))
    n = pl["power_kva"]["units"]
    for i in range(n):
        xx = bp.AX0 + 20 + i * 52
        o.append(line(x + 35, y + 30, xx + 20, y + 30, INK, 0.3))
        o.append(line(xx + 20, y + 30, xx + 20, y + 40, INK, 0.3))
        o.append(node(xx, y + 40, 40, 10, f"TX{i + 1} {pl['power_kva']['unit']:,} kVA"))
        o.append(line(xx + 20, y + 50, xx + 20, y + 62, INK, 0.3))
    o.append(line(bp.AX0 + 20, y + 62, bp.AX0 + 20 + (n - 1) * 52 + 40, y + 62, INK, 1.0))
    o.append(text(bp.AX0 + 20, y + 68, "Normal bus: tools, fan filter units, chillers, lighting", 2.6))
    gy = y + 110
    for i in range(pl["emergency_kw"]["units"]):
        xx = bp.AX0 + 20 + i * 60
        o.append(node(xx, gy, 48, 10, f"G{i + 1} {pl['emergency_kw']['unit']:,} kW", RED))
        o.append(line(xx + 24, gy + 10, xx + 24, gy + 22, RED, 0.3))
    o.append(line(bp.AX0 + 20, gy + 22, bp.AX0 + 200, gy + 22, RED, 1.0))
    o.append(text(bp.AX0 + 20, gy + 28, "Emergency bus (415.11.11):", 2.8, weight="bold", fill=RED))
    for i, s in enumerate(U["emergency_loads"]):
        o.append(text(bp.AX0 + 24, gy + 35 + i * 5, s, 2.5))
    o.append(text(bp.AX0 + 20, gy + 35 + len(U["emergency_loads"]) * 5 + 4,
                  f"Total {U['emergency_kw']:,} kW against {U['generator_kw']:,} kW of generators; exhaust fans at half speed as 415.11.11 allows.", 2.6))
    t, _ = notes(bp.AX0 + 520, bp.AY0 + 30, ["Electrical design to NFPA 70 (not read): licensed review. Fault currents, protection and grounding wait for it.",
                                            "Hazardous-location wiring in the fab areas is waived by the recirculated air (415.11.1.8; M-401)."], 2.7, 90, "NOTES")
    o.append(t)
    return "".join(o)


def e601(C):
    U = C.P["utilities"]
    S = C.S
    o = [text(bp.AX0 + 10, bp.AY0 + 10, "ELECTRICAL SCHEDULES: load by bay, cable trays", 4.2, weight="bold")]
    import collections
    kva = collections.Counter()
    for i, t in enumerate(S["tools"]):
        kva[t["bay"]] += C.cards[t["kind"]]["utilities"]["power_kva"]["value"]
    rows = [[f"bay {b + 1:02d}", S["areas"][S["bays"][b]["area"]]["name"], f"{v:,.0f}", f"{v * 0.6:,.0f}",
             "yes" if any(C.cards[t["kind"]]["environment"]["yellow_light"] for t in S["tools"] if t["bay"] == b) else "no"] for b, v in sorted(kva.items())]
    half = (len(rows) + 1) // 2
    cols = [("Bay", 18), ("Area", 40), ("Connected kVA", 26), ("Diversified", 22), ("Yellow light", 22)]
    t, _ = table(bp.AX0 + 10, bp.AY0 + 18, cols, rows[:half], 2.4)
    o.append(t)
    t, _ = table(bp.AX0 + 150, bp.AY0 + 18, cols, rows[half:], 2.4)
    o.append(t)
    rows = [[x["id"], f"{x['kva']:,}", x["size"]] for x in U["trays"]]
    t, _ = table(bp.AX0 + 300, bp.AY0 + 18, [("Main tray", 60), ("kVA", 22), ("Size", 30)], rows, 2.4)
    o.append(t)
    return "".join(o)


def specs(C):
    P = C.P
    U, A, F = P["utilities"], P["air"], P["fire"]
    md = [f"# {PROJECT}: specifications outline\n", f"{TRUTH} Schematic for review, NOT FOR CONSTRUCTION.\n",
          "Products are named by kind and performance, never by maker. Every number traces to permit.json; assumed numbers are marked.\n"]
    sec = {
        "03": ("Concrete", [f"Waffle slab 0.9 m deep over the support floor, stiffness taken as {P['frame']['waffle']['stiff_depth_m']} m solid (assumed); "
                            f"first frequency at least {P['frame']['waffle']['target_hz']} Hz per grid bay (assumed target).",
                            f"Pad footings, {len(P['frame']['footings'])} in all, on {C.permit['design_data']['soil_bearing_kpa']['value']} kPa soil (assumed)."]),
        "05": ("Metals", [f"Roof trusses spanning {66.5 - 3.2:.1f} m, depth {P['frame']['truss_depth_m']} m (assumed); roof columns 0.6 m steel (assumed).",
                          "Braced bays in the long facades; exit stairs in steel with 100 psf live load (T1607.1)."]),
        "07": ("Thermal and moisture protection", ["Firestopping of every penetration of a rated barrier: IBC 714 and chapter 7, not read (licensed review).",
                                                   "Roof assembly rated 1 h (Table 601, type " + P["construction"]["type"] + ")."]),
        "08": ("Openings", [f"{len(of(C, 'IfcDoor'))} doors; exit doors 1.2 m leaves with panic hardware; doors in 2 h enclosures 90 min (assumed); "
                            "opening protectives per IBC 716 (not read)."]),
        "09": ("Finishes", ["Cleanroom wall and ceiling panels, non-shedding, to the space's class (M-401, assumed); conductive raised floor panels."]),
        "13": ("Special construction", [f"Cleanroom: {A['ffu_total']:,} fan filter units, H14 filters; recirculated air {A['recirc_cfm_sqft_avg']} cfm/sq ft "
                                        "on average (415.11.1.8). Gas rooms and dispense rooms as HPM rooms (415.11.6)."]),
        "21": ("Fire suppression", [f"Wet sprinklers throughout, {F['sprinkler_heads']:,} heads (count at 130 sq ft, assumed); hazard classes of Table 903.2.5.2; "
                                    "density per NFPA 13 (not read).", f"{F['duct_heads']} heads in solvent exhaust ducts (415.11.12)."]),
        "22": ("Plumbing", ["Process drains by kind (acid, fluoride, solvent, slurry) to treatment; fixtures per IPC (not read)."]),
        "23": ("Heating, ventilating and air conditioning", [f"{A['chillers']} chillers of 3,500 kW (N+1); exhaust by kind with continuous operation; "
                                                              "make-up air to 1.1 cfm/sq ft or more (415.11.1.6)."]),
        "26": ("Electrical", [f"{U['plant']['power_kva']['units']} main transformers of 5,000 kVA (N+1); {U['plant']['emergency_kw']['units']} emergency "
                              f"generators of 2,500 kW for the loads of 415.11.11 ({U['emergency_kw']:,} kW)."]),
        "28": ("Electronic safety and security", ["Gas detection at every HPM gas tool and room (415.11.8); manual fire alarm with a pull station at every "
                                                  "exit (907.2.5); emergency control station in the office (415.11.10)."]),
    }
    if C.P.get("stage") in ("dd", "cd"):
        import dd_sheets
        sec = dd_sheets.specs_dd(C, sec)
    for d, (name, items) in sec.items():
        md.append(f"## Division {d} {name}\n")
        md += [f"- {x}" for x in items]
        md.append("")
    return "\n".join(md) + "\n"


BODIES = {"G-001": None, "G-002": None, "G-003": None, "G-101": lambda C: life_safety(C, 0), "G-102": lambda C: life_safety(C, 1),
          "C-101": c101, "C-201": c201, "S-001": s001, "S-101": s101, "S-201": s201, "A-401": a401, "A-601": a601, "M-101": m101,
          "M-401": m401, "M-601": m601, "PP-101": pp101, "PP-301": pp301, "P-101": p101, "FP-101": fp101, "FA-101": fa101,
          "E-001": e001, "E-601": e601}


def write(C, V, out, layout):
    """Every sheet but G-003 (it needs the ledger, which needs the rest) and the specifications. Returns every sheet id."""
    global SUBTITLE, REV, CURRENT
    bp.use(C.profile)
    C.V = V
    out = Path(out)
    bodies = dict(BODIES)
    if C.P.get("stage") in ("dd", "cd"):
        import dd_sheets
        SUBTITLE, REV = "Design development set, all trades, for review", "DD1 design development for review"
        CURRENT = SHEETS + dd_sheets.SHEETS
        bodies.update(dd_sheets.BODIES)
    if C.P.get("stage") == "cd":
        import cd_sheets
        SUBTITLE, REV = "Construction documents, lithography bay 09, for review", "CD1 construction documents for review"
        import arch_sheets
        CURRENT = CURRENT + cd_sheets.SHEETS + arch_sheets.SHEETS
        bodies.update(cd_sheets.BODIES)
        bodies.update(arch_sheets.BODIES)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(Path(layout).read_bytes()).hexdigest()[:12]
    C.sha = sha
    titles = dict(CURRENT)
    for sid, fn in bodies.items():
        if sid in ("G-001", "G-002", "G-003"):
            continue
        (out / "sheets" / f"{sid}.svg").write_text(frame(sid, titles[sid], fn(C), sha))
    (out / "sheets" / "G-002.svg").write_text(frame("G-002", titles["G-002"], g002(C, V, None), sha))
    md = specs(C)
    if C.P.get("stage") == "cd":
        import cd_sheets
        md += cd_sheets.specs_cd(C)
    (out / "specs.md").write_text(md)
    return [s for s, _ in CURRENT]


def write_ledger_sheet(C, L, out, layout):
    out = Path(out)
    titles = dict(CURRENT)
    (out / "sheets" / "G-003.svg").write_text(frame("G-003", titles["G-003"], g003(C, L), C.sha))
    (out / "sheets" / "G-001.svg").write_text(frame("G-001", titles["G-001"], g001(C, C.V, L), C.sha))
    import json
    (out / "index.json").write_text(json.dumps([{"id": s, "title": t, "file": f"sheets/{s}.svg"} for s, t in CURRENT], indent=1) + "\n")
    W, H = bp.W, bp.H
    html = ["<!doctype html><html><head><meta charset=\"utf-8\"><title>Fab Gym campus: " +
            {"dd": "design development set", "cd": "construction documents"}.get(C.P.get("stage"), "schematic permit set") + "</title><style>",
            f"@page{{size:{f(W)}mm {f(H)}mm;margin:0}}html,body{{margin:0;padding:0;background:#fff}}",
            f".s{{width:{f(W)}mm;height:{f(H)}mm;break-after:page;page-break-after:always;overflow:hidden}}",
            f".s:last-child{{break-after:auto;page-break-after:auto}}.s svg{{display:block;width:{f(W)}mm;height:{f(H)}mm}}",
            "</style></head><body>"]
    for sid, _ in CURRENT:
        html.append(f'<section class="s" data-sheet="{sid}">{(out / "sheets" / f"{sid}.svg").read_text()}</section>')
    html.append("</body></html>\n")
    (out / "permit-set.html").write_text("".join(html))


def pdf(out):
    out = Path(out)
    if not bp.CHROME.exists():
        return "pdf skipped: Google Chrome is not installed"
    p = (out / "permit-set.pdf").resolve()
    subprocess.run([str(bp.CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={p}",
                    (out / "permit-set.html").resolve().as_uri()], capture_output=True, timeout=300)
    return f"pdf {p}" if p.exists() else "pdf: Chrome ran but wrote no file"
