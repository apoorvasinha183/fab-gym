"""The campus as a drawing set for an architect (docs/BLUEPRINT.md): A1 sheets as SVG, the set as one HTML page
printed to PDF by headless Chrome, a DXF of the plan in metres, and the brief.

A gigafab-style layout of our own design on the SMT2020 model; not a real fab. Every placement number is assumed
unless the brief cites a source. A concept for review, NOT FOR CONSTRUCTION.

    python3 viz/blueprint/blueprint.py [--scene data/layout-real/scene-optimised.json]
        [--layout results/layout-real/layout.json] [--out data/layout-real/blueprint] [--no-pdf]

Standard library only; the same input gives the same files byte for byte (the PDF carries Chrome's date).
"""

import argparse
import hashlib
import json
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
W, H = 841.0, 594.0                    # A1 landscape, millimetres
FX0, FY0, FX1, FY1 = 20.0, 10.0, 831.0, 584.0   # the frame
TB = 50.0                              # title strip height
AX0, AY0, AX1, AY1 = FX0 + 8, FY0 + 8, FX1 - 8, FY1 - TB - 6   # drawing area
DATE = "27 Oct 2026"
REV = "P1 for review"
PROJECT = "Fab Gym campus"
TRUTH = "On the SMT2020 model. A layout of our own design. Not a real fab."
GRID = 12.0                            # assumed column grid, metres
PLANT_H = 4.0                          # assumed roof plant height
FONT = "Helvetica, Arial, sans-serif"
INK = "#1d2430"
GREY = "#6b7380"
RED = "#b3261e"

SHEETS = [
    ("A-000", "Cover, drawing list and general notes", None),
    ("A-100", "Site plan", 2000),
    ("A-101", "Clean floor plan, phase 1 (+7.50)", 500),
    ("A-102", "Clean floor plan, phase 2 (+7.50)", 500),
    ("A-110", "Enlarged plan of a typical bay", 100),
    ("A-301", "Building section across the bays", 200),
    ("A-900", "Brief: numbers to check and questions for the architect", None),
]

KIND_FILL = {
    "scanner": "#f3d36b", "track": "#f8e7a8", "metrology": "#f4b183", "inspection": "#f5b6c6",
    "etch": "#9cc9ea", "deposition": "#b7d89a", "epitaxy": "#cbb6e8", "furnace": "#f2a07f",
    "implanter": "#c3a6e0", "polisher": "#c8ccd2", "wet_bench": "#a9dbee", "stocker": "#9aa0a8",
}
KIND_NAME = {
    "scanner": "scanner", "track": "coat and develop track", "metrology": "metrology", "inspection": "inspection",
    "etch": "etch cluster tool", "deposition": "deposition cluster tool", "epitaxy": "epitaxy", "furnace": "vertical furnace",
    "implanter": "ion implanter", "polisher": "polisher (CMP)", "wet_bench": "wet bench", "stocker": "stocker",
}
# Sizes and their sources, from docs/FAB-LOOK.md (the look spec of this repo).
CITED = {
    "furnace": "footprint cited (secondary): Koyo Thermo Systems table as reproduced by Kiel University, "
               "Electronic Materials ch. 6, VF5300, 3.0 m2 a tube; height assumed",
    "implanter": "cited (secondary): used Purion M listing, mainframe 360 x 810 x 310 cm, labelled an estimate",
}
OTHER_CITED = [
    ("wafers in a lot", "25", "cited: SMT2020 order.txt, column PIECES"),
    ("carrier (FOUP), W x D x H", "0.426 x 0.355 x 0.338 m", "cited: Entegris A300 FOUPs datasheet, p. 2"),
    ("raised floor panel", "0.600 x 0.600 m, 38 mm thick, 38% open", "cited: DKC raised floor plate PFP3860ST-BL-P38, product page"),
    ("fan filter unit", "1.200 x 0.600 m, H14", "cited: item Filter Fan Unit 1200x600 (71642), product page"),
    ("lithography light", "blocks below 500 nm, passes above 540 nm", "cited: MicroChemicals Lithoprotect Yellowlight, product page"),
]


# ------------------------------------------------------------------ small helpers

def f(v, nd=2):
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def text(x, y, s, size=2.5, anchor="start", weight="normal", fill=INK, rot=None, extra=""):
    t = f' transform="rotate({f(rot)} {f(x)} {f(y)})"' if rot is not None else ""
    return (f'<text x="{f(x)}" y="{f(y)}" font-size="{f(size)}" text-anchor="{anchor}" font-weight="{weight}" '
            f'fill="{fill}"{t}{extra}>{esc(s)}</text>')


def rect(x, y, w, h, stroke=INK, sw=0.18, fill="none", extra=""):
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{f(sw)}"{extra}/>')


def line(x1, y1, x2, y2, stroke=INK, sw=0.18, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" stroke="{stroke}" stroke-width="{f(sw)}"{d}/>'


def lighten(hex_, k=0.8):
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * k) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class Map:
    """World metres to sheet millimetres: north up, 1 m = 1000/scale mm."""

    def __init__(self, scale, wx0, wy1, ox, oy):
        self.k = 1000.0 / scale
        self.wx0, self.wy1, self.ox, self.oy = wx0, wy1, ox, oy

    def __call__(self, x, y):
        return self.ox + (x - self.wx0) * self.k, self.oy + (self.wy1 - y) * self.k

    def box(self, x0, y0, x1, y1):
        a, b = self(min(x0, x1), max(y0, y1))
        return a, b, abs(x1 - x0) * self.k, abs(y1 - y0) * self.k


def dim(x1, y1, x2, y2, label, off=6.0, size=2.4):
    """A dimension between two sheet points, offset sideways, with slash ticks and the value above the line."""
    import math
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    a = (x1 + nx * off, y1 + ny * off)
    b = (x2 + nx * off, y2 + ny * off)
    o = [line(x1 + nx * 1.0, y1 + ny * 1.0, a[0] + nx * 1.5, a[1] + ny * 1.5, GREY, 0.13),
         line(x2 + nx * 1.0, y2 + ny * 1.0, b[0] + nx * 1.5, b[1] + ny * 1.5, GREY, 0.13),
         line(a[0], a[1], b[0], b[1], INK, 0.18)]
    for p in (a, b):
        o.append(line(p[0] - 1.1 * (dx / L - nx) / 1.414, p[1] - 1.1 * (dy / L - ny) / 1.414,
                      p[0] + 1.1 * (dx / L - nx) / 1.414, p[1] + 1.1 * (dy / L - ny) / 1.414, INK, 0.35))
    mx, my = (a[0] + b[0]) / 2 + nx * 1.4, (a[1] + b[1]) / 2 + ny * 1.4
    ang = math.degrees(math.atan2(dy, dx))
    if ang > 90 or ang <= -90:
        ang += 180
    o.append(text(mx, my, label, size, "middle", rot=ang if abs(ang) > 0.01 else None))
    return "".join(o)


def north(x, y, rot=0.0):
    return (f'<g data-north="1" transform="translate({f(x)} {f(y)}) rotate({f(rot)})">'
            f'<circle r="7" fill="none" stroke="{INK}" stroke-width="0.25"/>'
            f'<path d="M0 -9 L3 4 L0 2 L-3 4 Z" fill="{INK}"/>'
            f'{text(0, -10.5, "N", 4, "middle", "bold")}</g>')


def scalebar(x, y, metres, scale, step):
    mm = metres * 1000.0 / scale
    n = int(round(metres / step))
    o = [f'<g data-scalebar="{f(metres)}" data-mm="{f(mm, 3)}">']
    seg = mm / n
    for i in range(n):
        o.append(rect(x + i * seg, y, seg, 2.0, INK, 0.18, INK if i % 2 == 0 else "#ffffff"))
        o.append(text(x + i * seg, y - 1.5, f(i * step), 2.2, "middle"))
    o.append(text(x + mm, y - 1.5, f"{f(metres)} m", 2.2, "middle"))
    o.append(text(x, y + 6, f"Scale 1:{scale} on A1", 2.4))
    o.append("</g>")
    return "".join(o)


# ------------------------------------------------------------------ the sheet frame and title block

def sheet(sid, title, scale, body, sha):
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 841 594" width="841mm" height="594mm" '
         f'font-family="{FONT}">',
         rect(0, 0, W, H, "none", 0, "#ffffff"),
         rect(FX0, FY0, FX1 - FX0, FY1 - FY0, INK, 0.7)]
    o.append(body)
    y0 = FY1 - TB
    o.append(line(FX0, y0, FX1, y0, INK, 0.5))
    cols = [FX0, FX0 + 210, FX0 + 430, FX0 + 560, FX0 + 680, FX1]
    for c in cols[1:-1]:
        o.append(line(c, y0, c, FY1, INK, 0.35))
    o.append(text(cols[0] + 5, y0 + 10, PROJECT, 6, weight="bold"))
    o.append(text(cols[0] + 5, y0 + 18, "Concept drawing set for review", 3.2))
    o.append(text(cols[0] + 5, y0 + 27, TRUTH, 2.8))
    o.append(text(cols[0] + 5, y0 + 33, "Every placement number is assumed unless sheet A-900 cites a source.", 2.4, fill=GREY))
    o.append(text(cols[0] + 5, y0 + 39, "Units: metres. Levels above the support floor slab (+0.00).", 2.4, fill=GREY))
    o.append(text(cols[0] + 5, y0 + 45, f"Drawn from results/layout-real/layout.json, sha256 {sha}", 2.4, fill=GREY))
    o.append(text(cols[1] + 5, y0 + 8, "DRAWING", 2.2, fill=GREY))
    for i, ln in enumerate(textwrap.wrap(title, 40)):
        o.append(text(cols[1] + 5, y0 + 17 + i * 6.5, ln, 4.6, weight="bold"))
    o.append(text(cols[2] + 5, y0 + 8, "SCALE", 2.2, fill=GREY))
    o.append(text(cols[2] + 5, y0 + 18, f"1:{scale} on A1" if scale else "as shown", 4.2))
    o.append(text(cols[2] + 5, y0 + 30, "DATE", 2.2, fill=GREY))
    o.append(text(cols[2] + 5, y0 + 39, DATE, 4.0))
    o.append(text(cols[3] + 5, y0 + 8, "REVISION", 2.2, fill=GREY))
    o.append(text(cols[3] + 5, y0 + 18, REV, 4.0))
    o.append(text(cols[3] + 5, y0 + 30, "STATUS", 2.2, fill=GREY))
    o.append(text(cols[3] + 5, y0 + 40, "NOT FOR CONSTRUCTION", 3.4, weight="bold", fill=RED))
    o.append(text(cols[4] + 5, y0 + 8, "SHEET", 2.2, fill=GREY))
    o.append(text((cols[4] + cols[5]) / 2, y0 + 34, sid, 16, "middle", "bold"))
    o.append("</svg>")
    return "".join(o)


# ------------------------------------------------------------------ the plans

def phase_of_x(S, x):
    return 1 if x >= S["offsets"][1] - 1e-6 else 0


def building(S, p):
    return [c for c in S["campus"] if c["kind"] == "fab"][p]


def grid_lines(S):
    """The assumed 12 m column grid: x lines per building, y lines from the spine's edge outward to the bays' end."""
    xs = []
    for p in (0, 1):
        b = building(S, p)
        x = b["x0"]
        while x <= b["x1"] + 1e-6:
            xs.append(round(x, 3))
            x += GRID
        if abs(xs[-1] - b["x1"]) > 1e-6:
            xs.append(round(b["x1"], 3))
    half = S["spine"] / 2
    ys = []
    y = half
    while y <= half + S["depth"] + 1e-6:
        ys += [round(y, 3), round(-y, 3)]
        y += GRID
    return xs, sorted(ys, reverse=True)


def clip_seg(a, b, x0, x1):
    (ax, ay), (bx, by) = a, b
    if ax > bx:
        ax, ay, bx, by = bx, by, ax, ay
    if bx < x0 or ax > x1:
        return None
    if bx - ax < 1e-9:
        return (ax, ay), (bx, by)
    t0 = max(0.0, (x0 - ax) / (bx - ax))
    t1 = min(1.0, (x1 - ax) / (bx - ax))
    return (ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)


def section_x(S):
    st = S["stockers"][0]
    return round((st["x0"] + st["x1"]) / 2, 3)


def plan_sheet(S, p):
    b = building(S, p)
    scale = 500
    bw = (b["x1"] - b["x0"]) * 2.0
    ox = AX0 + (22 if p == 0 else 75)
    M = Map(scale, b["x0"], b["y1"], ox, AY0 + 70)
    xsec = M(section_x(S), 0)[0] if p == 0 else None
    o = []
    xs, ys = grid_lines(S)
    gx = [x for x in xs if b["x0"] - 1e-6 <= x <= b["x1"] + 1e-6]
    xi0 = xs.index(gx[0])
    # grid
    for i, x in enumerate(gx):
        X, Y0 = M(x, b["y1"])
        _, Y1 = M(x, b["y0"])
        o.append(line(X, Y0 - 6, X, Y1 + 6, GREY, 0.13, "4 1 0.6 1"))
        o.append(f'<circle cx="{f(X)}" cy="{f(Y1 + 9)}" r="2.6" fill="#fff" stroke="{GREY}" stroke-width="0.18"/>')
        o.append(text(X, Y1 + 9.9, str(xi0 + i + 1), 2.4 if xi0 + i + 1 < 10 else 2.0, "middle", fill=GREY))
    letters = "ABCDEFGHJKLMNPQRSTU"
    for j, y in enumerate(ys):
        X0, Y = M(b["x0"], y)
        X1, _ = M(b["x1"], y)
        o.append(line(X0 - 6, Y, X1 + 6, Y, GREY, 0.13, "4 1 0.6 1"))
        o.append(f'<circle cx="{f(X0 - 9)}" cy="{f(Y)}" r="2.6" fill="#fff" stroke="{GREY}" stroke-width="0.18"/>')
        o.append(text(X0 - 9, Y + 0.9, letters[j], 2.4, "middle", fill=GREY))
    # bays
    for i, bay in enumerate(S["bays"]):
        if bay["phase"] != p:
            continue
        x, y, w, h = M.box(bay["x0"], bay["y0"], bay["x1"], bay["y1"])
        fill = lighten(S["areas"][bay["area"]]["colour"], 0.86)
        o.append(rect(x, y, w, h, GREY, 0.18, fill, f' data-bay="{i}"'))
        name = S["areas"][bay["area"]]["name"]
        top = bay["y1"] > 0
        X, Y = M((bay["x0"] + bay["x1"]) / 2, b["y1"] if top else b["y0"])
        ty = Y - 3 if top else Y + 13
        if xsec is not None and abs(X - xsec) < 3:
            X += 4
        o.append(text(X + 0.9, ty, f"Bay {i + 1:02d}  {name}", 2.0, "start" if top else "end", rot=-90))
    # spine
    lo, hi = S["offsets"][p], S["offsets"][p] + S["lengths"][p]
    x, y, w, h = M.box(b["x0"], -S["spine"] / 2, b["x1"], S["spine"] / 2)
    o.append(rect(x, y, w, h, GREY, 0.18, "#eef0f3"))
    # rails
    for a, c in S["rails"]:
        seg = clip_seg((a[0], a[1]), (c[0], c[1]), b["x0"], b["x1"])
        if seg:
            (x1, y1), (x2, y2) = seg
            P, Q = M(x1, y1), M(x2, y2)
            o.append(line(P[0], P[1], Q[0], Q[1], "#2f6db3", 0.13, "1.2 0.8"))
    # tools
    for i, t in enumerate(S["tools"]):
        if phase_of_x(S, t["x0"]) != p:
            continue
        x, y, w, h = M.box(t["x0"], t["y0"], t["x1"], t["y1"])
        o.append(rect(x, y, w, h, INK, 0.1, KIND_FILL[t["kind"]], f' data-tool="{i}"'))
    for i, st in enumerate(S["stockers"]):
        if phase_of_x(S, st["x0"]) != p:
            continue
        x, y, w, h = M.box(st["x0"], st["y0"], st["x1"], st["y1"])
        o.append(rect(x, y, w, h, INK, 0.18, KIND_FILL["stocker"], f' data-stocker="{i}"'))
    # walls
    x, y, w, h = M.box(b["x0"], b["y0"], b["x1"], b["y1"])
    o.append(rect(x, y, w, h, INK, 0.7))
    X, Y = M(b["x0"] + 1, 0)
    o.append(text(X + 1, Y + 0.8, "SPINE: interbay hoist rails and stockers", 2.2, fill=GREY))
    # bridge stub
    br = [c for c in S["campus"] if c["kind"] == "bridge"][0]
    if p == 0:
        x, y, w, h = M.box(b["x1"], br["y0"], b["x1"] + 12, br["y1"])
        o.append(rect(x, y, w, h, INK, 0.25, "#ffffff", ' stroke-dasharray="1.5 1"'))
        o.append(text(x, y - 2, "hoist bridge to phase 2 (A-102)", 2.4))
    else:
        x, y, w, h = M.box(b["x0"] - 12, br["y0"], b["x0"], br["y1"])
        o.append(rect(x, y, w, h, INK, 0.25, "#ffffff", ' stroke-dasharray="1.5 1"'))
        o.append(text(x + w, y - 2, "hoist bridge from phase 1 (A-101)", 2.4, "end"))
    # section mark
    if p == 0:
        xc = section_x(S)
        X, Y0 = M(xc, b["y1"])
        _, Y1 = M(xc, b["y0"])
        o.append(line(X, Y0 - 36.6, X, Y0 - 1, INK, 0.5))
        o.append(line(X, Y1 + 1, X, Y1 + 60.6, INK, 0.5))
        for yy in (Y0 - 40, Y1 + 64):
            o.append(f'<circle cx="{f(X)}" cy="{f(yy)}" r="3.4" fill="#fff" stroke="{INK}" stroke-width="0.35"/>')
            o.append(line(X - 3.4, yy, X + 3.4, yy, INK, 0.2))
            o.append(text(X, yy - 0.7, "1", 2.4, "middle", "bold"))
            o.append(text(X, yy + 2.6, "A-301", 1.6, "middle"))
    # dimensions
    BX0, BY1 = M(b["x0"], b["y0"])
    BX1, BY0 = M(b["x1"], b["y1"])
    o.append(dim(BX0, BY1 + 46, BX1, BY1 + 46, f"{f(b['x1'] - b['x0'], 1)} building", off=0))
    SX0, _ = M(lo, 0)
    SX1, _ = M(hi, 0)
    o.append(dim(SX0, BY1 + 54, SX1, BY1 + 54, f"{f(S['lengths'][p], 1)} spine (phase {p + 1} length)", off=0))
    o.append(dim(BX1 + 46, BY0, BX1 + 46, BY1, f"{f(b['y1'] - b['y0'], 1)} building", off=0))
    _, Ys0 = M(0, S["spine"] / 2)
    _, Ys1 = M(0, -S["spine"] / 2)
    _, Yd = M(0, S["spine"] / 2 + S["depth"])
    o.append(dim(BX1 + 36, Yd, BX1 + 36, Ys0, f"{f(S['depth'], 1)} bay depth", off=0, size=2.1))
    o.append(dim(BX1 + 36, Ys0, BX1 + 36, Ys1, f"{f(S['spine'], 1)}", off=0, size=2.1))
    # legend
    counts = {}
    for t in S["tools"]:
        if phase_of_x(S, t["x0"]) == p:
            counts[t["kind"]] = counts.get(t["kind"], 0) + 1
    lx, ly = AX1 - 150, BY1 + 48
    if p == 1:
        lx = BX1 + 70
        ly = AY0 + 70
    o.append(text(lx, ly, "TOOLS IN THIS PHASE, BY KIND (generic boxes, sizes on A-900)", 2.4, weight="bold"))
    row = 0
    for k in KIND_FILL:
        if k == "stocker":
            n = sum(1 for st in S["stockers"] if phase_of_x(S, st["x0"]) == p)
        else:
            n = counts.get(k, 0)
        if not n:
            continue
        kd = S["kinds"][k]
        yy = ly + 5 + row * 5
        o.append(rect(lx, yy - 2.6, 5, 3, INK, 0.1, KIND_FILL[k]))
        o.append(text(lx + 7, yy, f"{KIND_NAME[k]}: {n}, each {f(kd['w'])} x {f(kd['d'])} m, {f(kd['h'])} m tall", 2.3))
        row += 1
    yy = ly + 5 + row * 5 + 2
    o.append(line(lx, yy - 1, lx + 5, yy - 1, "#2f6db3", 0.25, "1.2 0.8"))
    o.append(text(lx + 7, yy, "hoist rail (underside +11.70)", 2.3))
    o.append(line(lx, yy + 4, lx + 5, yy + 4, GREY, 0.18, "4 1 0.6 1"))
    o.append(text(lx + 7, yy + 5, f"column grid, {f(GRID)} m, assumed (support floor below)", 2.3))
    o.append(north(AX1 - 20, AY0 + 22))
    o.append(scalebar(AX1 - 130, AY1 - 12, 50, scale, 10))
    tools_n = sum(counts.values())
    o.append(text(AX0 + 4, AY0 + 6, f"PHASE {p + 1} CLEAN FLOOR AT +7.50: {sum(1 for bb in S['bays'] if bb['phase'] == p)} bays, {tools_n} tools", 4, weight="bold"))
    o.append(text(AX0 + 4, AY0 + 12, "Bays open off the central spine; tools stand along both bay walls facing the aisle; service chases behind the tools.", 2.6, fill=GREY))
    return "".join(o)


# ------------------------------------------------------------------ the site

def site_sheet(S):
    scale = 2000
    g = [c for c in S["campus"] if c["kind"] == "road"]
    wx0 = min(c["x0"] for c in S["campus"]) - 10
    wy1 = max(c["y1"] for c in S["campus"]) + 10
    M = Map(scale, wx0, wy1, AX0 + 40, AY0 + 40)
    o = []
    fills = {"fab": "#dfe6ef", "bridge": "#ffffff", "pad": "#f4f4ef", "cub": "#e8e2d6", "upw": "#d9ecf3",
             "gas": "#f6efe0", "office": "#ece5f3", "corridor": "#eeeeee", "cooling_tower": "#d7e3e8",
             "stack": "#555b66", "tank": "#f1e2c4", "road": "#d5d7da", "parking": "#ededed"}
    order = ["road", "parking", "pad", "gas", "cub", "upw", "corridor", "office", "fab", "bridge", "cooling_tower", "tank", "stack"]
    for kind in order:
        for c in S["campus"]:
            if c["kind"] != kind:
                continue
            x, y, w, h = M.box(c["x0"], c["y0"], c["x1"], c["y1"])
            sw = 0.5 if kind == "fab" else 0.18
            dash = ' stroke-dasharray="1.5 1"' if kind in ("pad", "bridge") else ""
            o.append(rect(x, y, w, h, INK if kind != "road" else GREY, sw, fills[kind], dash))
    groups = {"cooling_tower": "Cooling towers (8)", "stack": "Exhaust scrubber stacks (6)", "tank": "Liquid gas tanks (5)"}
    for kind, lab in groups.items():
        last = max((c for c in S["campus"] if c["kind"] == kind), key=lambda c: c["x1"])
        x, y, w, h = M.box(last["x0"], last["y0"], last["x1"], last["y1"])
        o.append(text(x + w + 2, y + h / 2 + 0.9, lab, 2.4))
    done = set(groups)
    for c in S["campus"]:
        if c["kind"] in ("road",):
            continue
        lab = c["label"] or ""
        if c["kind"] in groups:
            if c["kind"] in done:
                continue
            done.add(c["kind"])
            lab = groups[c["kind"]]
        if not lab:
            continue
        x, y, w, h = M.box(c["x0"], c["y0"], c["x1"], c["y1"])
        if c["kind"] == "bridge":
            o.append(text(x + w / 2, y - 2, lab, 2.2, "middle"))
        else:
            o.append(text(x + w / 2, y + h / 2 + 1, lab, 2.8 if c["kind"] == "fab" else 2.4, "middle",
                          "bold" if c["kind"] == "fab" else "normal"))
    p1, p2 = building(S, 0), building(S, 1)
    br = [c for c in S["campus"] if c["kind"] == "bridge"][0]
    X0, Y = M(p1["x0"], p1["y0"])
    X1, _ = M(p1["x1"], p1["y0"])
    X2, _ = M(p2["x0"], p2["y0"])
    X3, _ = M(p2["x1"], p2["y0"])
    o.append(dim(X0, Y + 4, X1, Y + 4, f(p1["x1"] - p1["x0"], 1), off=0, size=2.0))
    o.append(dim(X1, Y + 4, X2, Y + 4, f(br["x1"] - br["x0"], 1), off=0, size=2.0))
    o.append(dim(X2, Y + 4, X3, Y + 4, f(p2["x1"] - p2["x0"], 1), off=0, size=2.0))
    o.append(north(AX1 - 20, AY0 + 22))
    o.append(scalebar(AX1 - 130, AY1 - 12, 200, scale, 50))
    o.append(text(AX0 + 4, AY0 + 6, "SITE PLAN", 4, weight="bold"))
    notes = ["Only the two fab phases and the bridge hold the model's tools. The pad, the utility buildings, the gas yard,",
             "the office, roads and parking are drawn only, at assumed places and sizes: the model holds none of them.",
             "Hoist bridge between the phases at +8.70; phase 3 is an empty pad."]
    for i, n in enumerate(notes):
        o.append(text(AX0 + 4, AY0 + 12 + i * 4.2, n, 2.6, fill=GREY))
    return "".join(o)


# ------------------------------------------------------------------ the enlarged bay

def bay_sheet(S):
    scale = 100
    k = 1000.0 / scale
    bi = next(i for i, b in enumerate(S["bays"]) if b["area"] == "Litho" and b["phase"] == 0)
    bay = S["bays"][bi]
    sgn = 1 if bay["y1"] > 0 else -1
    half = S["spine"] / 2
    ox, oy = AX0 + 70, AY0 + 70

    def P(x, y):   # rotated: depth from the spine's edge to the right, along-spine x downward
        return ox + (abs(y) - half) * k, oy + (x - bay["x0"]) * k

    o = []
    bw = bay["x1"] - bay["x0"]
    o.append(rect(ox - 8, oy, 8, bw * k, GREY, 0.18, "#eef0f3"))
    o.append(text(ox - 4, oy + bw * k / 2, "SPINE", 2.4, "middle", rot=-90, fill=GREY))
    o.append(rect(ox, oy, S["depth"] * k, bw * k, INK, 0.5, lighten(S["areas"]["Litho"]["colour"], 0.88), f' data-bay="{bi}"'))
    ch = 1.5
    for x0 in (bay["x0"], bay["x1"] - ch):
        a = P(x0, sgn * half)
        o.append(rect(a[0], a[1], S["depth"] * k, ch * k, GREY, 0.13, "#f3f3f3", ' stroke-dasharray="1 0.8"'))
    mid = (bay["x0"] + bay["x1"]) / 2
    a, c = P(mid, sgn * half), P(mid, sgn * (half + S["depth"]))
    o.append(line(a[0], a[1], c[0], c[1], GREY, 0.13, "6 1.5 1 1.5"))
    tools = [(i, t) for i, t in enumerate(S["tools"]) if t["x0"] >= bay["x0"] - 1e-6 and t["x1"] <= bay["x1"] + 1e-6
             and (t["y0"] > 0) == (sgn > 0) and phase_of_x(S, t["x0"]) == 0]
    for i, t in tools:
        a = P(t["x0"], t["y0"])
        c = P(t["x1"], t["y1"])
        x, y = min(a[0], c[0]), min(a[1], c[1])
        w, h = abs(c[0] - a[0]), abs(c[1] - a[1])
        o.append(rect(x, y, w, h, INK, 0.25, KIND_FILL[t["kind"]], f' data-tool-detail="{i}"'))
        g = S["groups"][t["g"]]["name"]
        o.append(text(x + w / 2, y + h / 2 + 0.8, g, 1.9 if w > 30 else 1.6, "middle"))
        for px, py in t.get("ports", []):
            q = P(px, py)
            o.append(rect(q[0] - 2.13, q[1] - 1.78, 4.26, 3.55, INK, 0.13, "#ffffff"))
    for rx in bay.get("rails_x", []):
        a, c = P(rx, sgn * half), P(rx, sgn * (half + S["depth"]))
        o.append(line(a[0], a[1], c[0], c[1], "#2f6db3", 0.3, "2 1"))
    # dimensions
    o.append(dim(ox, oy - 4, ox + S["depth"] * k, oy - 4, f"{f(S['depth'], 1)} bay depth", off=-6))
    o.append(dim(ox + S["depth"] * k + 6, oy, ox + S["depth"] * k + 6, oy + bw * k, f"{f(bw, 2)} bay width", off=-8))
    o.append(dim(ox + S["depth"] * k + 6, oy, ox + S["depth"] * k + 6, oy + ch * k, f"{f(ch, 1)} chase", off=6, size=2.0))
    aisle = S["aisle"]
    ya, yb = P(mid - aisle / 2, sgn * half)[1], P(mid + aisle / 2, sgn * half)[1]
    o.append(dim(ox + S["depth"] * k + 6, ya, ox + S["depth"] * k + 6, yb, f"{f(aisle, 1)} aisle", off=6, size=2.0))
    if tools:
        deep = max(tools, key=lambda it: it[1]["y1"] - it[1]["y0"] if False else it[1]["x1"] - it[1]["x0"])[1]
        a, c = P(deep["x0"], deep["y0"]), P(deep["x1"], deep["y0"])
        o.append(dim(ox - 14, min(a[1], c[1]), ox - 14, max(a[1], c[1]),
                     f"{f(deep['x1'] - deep['x0'], 1)} {KIND_NAME[deep['kind']]}", off=-2, size=1.9))
    o.append(north(AX1 - 20, AY0 + 22, 90.0 if sgn > 0 else -90.0))
    o.append(scalebar(AX1 - 130, AY1 - 12, 10, scale, 2))
    name = S["areas"]["Litho"]["name"]
    o.append(text(AX0 + 4, AY0 + 6, f"ENLARGED PLAN: BAY {bi + 1:02d}, {name.upper()}, PHASE 1 (plan turned so the spine is on the left)", 4, weight="bold"))
    notes = ["Small white boxes: load ports, one carrier (0.426 x 0.355 m) each. Blue dashed: intrabay hoist rails over the port rows.",
             "Grey strips: service chases behind the tools (1.5 m, assumed). Centre line: the aisle. Lithography bays run in yellow light (A-900).",
             "Tool sizes are by kind, generic boxes of our own; the model's tool groups are named on them."]
    for i, n in enumerate(notes):
        o.append(text(AX0 + 4, AY0 + 12 + i * 4.2, n, 2.6, fill=GREY))
    yk = oy + bw * k + 22
    row = 0
    for kd in ("scanner", "track", "metrology"):
        if any(t["kind"] == kd for _, t in tools):
            K = S["kinds"][kd]
            o.append(rect(ox, yk + row * 5 - 2.6, 5, 3, INK, 0.1, KIND_FILL[kd]))
            o.append(text(ox + 7, yk + row * 5, f"{KIND_NAME[kd]}: {f(K['w'])} x {f(K['d'])} m, {f(K['h'])} m tall, {K['ports']} load ports (assumed)", 2.4))
            row += 1
    return "".join(o)


# ------------------------------------------------------------------ the section

def section_sheet(S):
    scale = 200
    k = 1000.0 / scale
    b = building(S, 0)
    xc = section_x(S)
    top = S["floors"][-1]["z1"] + PLANT_H
    ox = AX0 + 50
    oy = AY0 + 40 + top * k   # z = 0 here

    def P(y, z):   # looking east: north (+y) to the left
        return ox + (b["y1"] - y) * k, oy - z * k

    o = []
    gl0, gl1 = P(b["y1"] + 8, 0), P(b["y0"] - 1, 0)
    o.append(line(gl0[0], gl0[1], gl1[0], gl1[1], INK, 0.7))
    names = {}
    for fl in S["floors"]:
        names[fl["name"]] = fl
    # slabs
    for nm, fill in (("waffle slab", "#cfd3d8"), ("roof", "#cfd3d8")):
        fl = names[nm]
        a = P(b["y1"], fl["z1"])
        o.append(rect(a[0], a[1], (b["y1"] - b["y0"]) * k, (fl["z1"] - fl["z0"]) * k, INK, 0.35, fill))
    rf = names["raised floor"]
    a = P(b["y1"], rf["z1"])
    o.append(rect(a[0], a[1], (b["y1"] - b["y0"]) * k, (rf["z1"] - rf["z0"]) * k, INK, 0.18, "#eef0f3"))
    y = b["y0"] + 0.3
    while y < b["y1"]:
        p, q = P(y, rf["z0"]), P(y, rf["z1"] - 0.04)
        o.append(line(p[0], p[1], q[0], q[1], GREY, 0.1))
        y += 0.6
    # walls
    for yw in (b["y1"], b["y0"]):
        p, q = P(yw, 0), P(yw, names["roof"]["z1"])
        o.append(line(p[0], p[1], q[0], q[1], INK, 0.7))
    # support floor columns on the grid
    _, ys = grid_lines(S)
    for yg in ys + [b["y1"], b["y0"]]:
        p = P(yg + 0.3, names["support floor"]["z1"])
        o.append(rect(p[0], p[1], 0.6 * k, (names["support floor"]["z1"]) * k, INK, 0.18, "#e6e8eb"))
    # filter ceiling
    cz = names["cleanroom"]["z1"]
    p, q = P(b["y1"], cz), P(b["y0"], cz)
    o.append(line(p[0], p[1], q[0], q[1], INK, 0.35))
    y = b["y0"]
    while y < b["y1"] - 1e-6:
        if abs(y) >= S["spine"] / 2 + 1.5:
            p = P(y + 1.2, cz + 0.35)
            o.append(rect(p[0], p[1], 1.2 * k * 0.9, 0.35 * k, GREY, 0.1, "#f2f4f6"))
        y += 1.2
    # tools cut at x = xc
    for t in S["tools"]:
        if t["x0"] <= xc <= t["x1"]:
            p = P(t["y1"], S["clean_z"] + t["h"])
            o.append(rect(p[0], p[1], (t["y1"] - t["y0"]) * k, t["h"] * k, INK, 0.25, KIND_FILL[t["kind"]]))
    for st in S["stockers"]:
        if st["x0"] <= xc <= st["x1"]:
            h = S["kinds"]["stocker"]["h"]
            p = P(st["y1"], S["clean_z"] + h)
            o.append(rect(p[0], p[1], (st["y1"] - st["y0"]) * k, h * k, INK, 0.35, KIND_FILL["stocker"]))
            o.append(text(p[0] + (st["y1"] - st["y0"]) * k / 2, p[1] - 1.5, "stocker", 2.2, "middle"))
    # rail level
    rz = S["rail_z"]
    p, q = P(b["y1"], rz), P(b["y0"], rz)
    o.append(line(p[0], p[1], q[0], q[1], "#2f6db3", 0.25, "2 1"))
    for yr in (2.2, -2.2):
        c = P(yr, rz)
        o.append(rect(c[0] - 0.6, c[1] - 0.6, 1.2, 1.2, "#2f6db3", 0.2, "#2f6db3"))
    # roof plant (assumed)
    rz1 = names["roof"]["z1"]
    for yy in (40, 10, -25, -55):
        p = P(yy + 6, rz1 + PLANT_H)
        o.append(rect(p[0], p[1], 12 * k, PLANT_H * k, INK, 0.25, "#f1f1ee"))
    p = P(46, rz1 + PLANT_H + 1)
    o.append(text(p[0], p[1], "roof plant, make-up air (assumed 4.0 m)", 2.4))
    # level marks on the right
    xr = P(b["y0"], 0)[0] + 10
    marks = []
    for fl in S["floors"]:
        marks.append((fl["z0"], fl["name"]))
    marks.append((S["floors"][-1]["z1"], "top of roof"))
    marks.append((rz, "hoist rail underside"))
    marks.append((rz1 + PLANT_H, "top of roof plant (assumed)"))
    ty = 1e9
    for z, nm in sorted(marks):
        yy = oy - z * k
        o.append(line(xr - 4, yy, xr + 3, yy, INK, 0.25))
        o.append(f'<path d="M{f(xr)} {f(yy)} l-1.6 -2.2 h3.2 Z" fill="{INK}"/>')
        ty = min(yy + 0.9, ty - 3.2)
        if ty < yy + 0.9 - 0.01:
            o.append(line(xr + 3, yy, xr + 4.6, ty - 0.9, GREY, 0.13))
        o.append(text(xr + 5, ty, f"+{z:.2f}  {nm}", 2.4))
    # floor names inside
    yl = P(b["y1"] - 3, 0)[0]
    for fl in S["floors"]:
        zm = (fl["z0"] + fl["z1"]) / 2 if fl["name"] != "cleanroom" else fl["z1"] - 0.9
        if fl["name"] in ("waffle slab", "raised floor", "roof"):
            continue
        o.append(text(yl, oy - zm * k + 1, f"{fl['name'].upper()}  {f(fl['z1'] - fl['z0'], 1)} m", 2.6, weight="bold"))
    # dims
    a0, a1 = P(b["y1"], 0), P(b["y0"], 0)
    o.append(dim(a0[0], a0[1] + 10, a1[0], a1[1] + 10, f"{f(b['y1'] - b['y0'], 1)} building width", off=0))
    s0, s1 = P(S["spine"] / 2, 0), P(-S["spine"] / 2, 0)
    d0 = P(S["spine"] / 2 + S["depth"], 0)
    o.append(dim(d0[0], d0[1] + 4, s0[0], s0[1] + 4, f"{f(S['depth'], 1)} bay depth", off=0, size=2.2))
    o.append(dim(s0[0], s0[1] + 4, s1[0], s1[1] + 4, f"{f(S['spine'], 1)}", off=0, size=2.2))
    o.append(scalebar(AX1 - 130, AY1 - 12, 20, scale, 5))
    o.append(text(AX0 + 4, AY0 + 6, f"SECTION 1-1 ACROSS PHASE 1 AT x = {f(xc, 1)} m, LOOKING EAST (cut through a stocker; marked on A-101)", 4, weight="bold"))
    notes = ["Tools are cut where the section line crosses them, at their kind's height. Blue dashed: hoist rail level; the two blue squares are",
             "the interbay rails in the spine. Columns in the support floor on the assumed 12 m grid. The cleanroom air returns through the chases (assumed).",
             "Every height on this sheet is assumed (A-900)."]
    for i, n in enumerate(notes):
        o.append(text(AX0 + 4, AY0 + 12 + i * 4.2, n, 2.6, fill=GREY))
    o.append(section_detail(S, oy + 40))
    return "".join(o)


def section_detail(S, top):
    """Detail 2: the levels at the spine's north edge at 1:100, cut on the same line as section 1-1."""
    k = 10.0
    xc = section_x(S)
    fl = {x["name"]: x for x in S["floors"]}
    y_lo, y_hi = -2.0, 20.0           # spine centre side to 16 m into the north bay
    ox = AX0 + 60
    oy = top + 30 + fl["roof"]["z1"] * k

    def P(y, z):                      # looking east: north to the left
        return ox + (y_hi - y) * k, oy - z * k

    o = [text(AX0 + 4, top + 6, "DETAIL 2: THE LEVELS AT THE SPINE, ON SECTION LINE 1-1", 4, weight="bold"),
         text(AX0 + 4, top + 12, "Scale 1:100 on A1. Every height and size here is assumed unless A-900 cites it.", 2.6, fill=GREY)]
    W = (y_hi - y_lo) * k
    a = P(y_hi, 0)
    o.append(line(a[0] - 4, a[1], a[0] + W + 4, a[1], INK, 0.7))
    # columns on the 12 m grid, in the support floor
    _, ys = grid_lines(S)
    for yg in ys:
        if y_lo < yg < y_hi:
            c = P(yg + 0.3, fl["support floor"]["z1"])
            o.append(rect(c[0], c[1], 0.6 * k, fl["support floor"]["z1"] * k, INK, 0.25, "#e6e8eb"))
            o.append(text(c[0] + 3, a[1] + 5, "column", 2.2, "middle", fill=GREY))
    # waffle slab with its open cells
    ws = fl["waffle slab"]
    c = P(y_hi, ws["z1"])
    o.append(rect(c[0], c[1], W, (ws["z1"] - ws["z0"]) * k, INK, 0.35, "#cfd3d8"))
    y = y_lo + 0.4
    while y + 0.6 < y_hi:
        c = P(y + 0.6, ws["z1"] - 0.15)
        o.append(rect(c[0], c[1], 0.6 * k, (ws["z1"] - ws["z0"] - 0.3) * k, GREY, 0.1, "#ffffff"))
        y += 1.0
    # raised floor: panels on pedestals
    rf = fl["raised floor"]
    c = P(y_hi, rf["z1"])
    o.append(rect(c[0], c[1], W, 0.038 * k * 4, INK, 0.25, "#eef0f3"))
    y = y_lo
    while y <= y_hi + 1e-6:
        c, d = P(y, rf["z0"]), P(y, rf["z1"] - 0.15)
        o.append(line(c[0], c[1], d[0], d[1], GREY, 0.25))
        y += 0.6
    # filter ceiling and the air space
    cl = fl["cleanroom"]
    y = y_lo
    while y + 1.2 <= y_hi + 1e-6:
        c = P(y + 1.2, cl["z1"] + 0.35)
        o.append(rect(c[0] + 0.3, c[1], 1.2 * k - 0.6, 0.35 * k, INK, 0.15, "#f2f4f6"))
        y += 1.2
    rf_ = fl["roof"]
    c = P(y_hi, rf_["z1"])
    o.append(rect(c[0], c[1], W, (rf_["z1"] - rf_["z0"]) * k, INK, 0.35, "#cfd3d8"))
    # the spine's edge and the first tools of the bay, cut
    se = S["spine"] / 2
    c, d = P(se, rf["z1"]), P(se, cl["z1"])
    o.append(line(c[0], c[1], d[0], d[1], GREY, 0.18, "2 1"))
    o.append(text(P(se, 0)[0] + 2, P(0, cl["z1"] - 0.6)[1], "spine", 2.4, fill=GREY))
    o.append(text(P(se, 0)[0] - 2, P(0, cl["z1"] - 0.6)[1], "bay", 2.4, "end", fill=GREY))
    tools = sorted((t for t in S["tools"] if t["x0"] <= xc <= t["x1"] and t["y0"] > 0 and t["y1"] <= y_hi), key=lambda t: t["y0"])
    for t in tools:
        c = P(t["y1"], cl["z0"] + t["h"])
        o.append(rect(c[0], c[1], (t["y1"] - t["y0"]) * k, t["h"] * k, INK, 0.3, KIND_FILL[t["kind"]]))
    if tools:
        tm = tools[len(tools) // 2]
        c = P((tm["y0"] + tm["y1"]) / 2, cl["z0"] + tm["h"] / 2)
        o.append(text(c[0], c[1], f"{KIND_NAME[tm['kind']]}s, cut", 2.3, "middle"))
        t = tools[0]
        # beyond the cut: a carrier on the tool's first load port, and a hoist vehicle on the rail above it
        py = t["ports"][0][1]
        seat = cl["z0"] + 0.9
        c = P(py + 0.355 / 2, seat + 0.338)
        o.append(rect(c[0], c[1], 0.355 * k, 0.338 * k, INK, 0.25, "#ffffff"))
        rz = S["rail_z"]
        c = P(py + 0.45, rz)
        o.append(rect(c[0], c[1], 0.9 * k, 0.8 * k, INK, 0.25, "#dbe7f5"))
        r0, r1 = P(y_hi, rz), P(y_lo, rz)
        o.append(line(r0[0], r0[1], r1[0], r1[1], "#2f6db3", 0.35, "2 1"))
        q, q2 = P(py, rz - 0.8), P(py, seat + 0.338)
        o.append(line(q[0], q[1], q2[0], q2[1], GREY, 0.15, "0.8 0.8"))
        lx = P(y_lo, 0)[0] + 44
        for zz, msg, yy0 in ((rz - 0.4, "hoist vehicle on the intrabay rail (beyond the cut), 0.9 x 0.6 x 0.8 m", py - 0.45),
                             (seat + 0.17, "carrier on a load port, seat 0.9 m above the raised floor (beyond)", py - 0.18)):
            q = P(yy0, zz)
            o.append(line(q[0], q[1], lx - 1, q[1], GREY, 0.13))
            o.append(text(lx, q[1] + 0.8, msg, 2.3))
    # the interbay rails in the spine
    for yr in (2.2,):
        c = P(yr, S["rail_z"])
        o.append(rect(c[0] - 0.6 * k / 2, c[1] - 0.6 * k / 2, 0.6 * k, 0.6 * k, "#2f6db3", 0.2, "#2f6db3"))
    o.append(text(P(2.2, 0)[0], P(0, S["rail_z"] + 0.7)[1], "interbay rail", 2.2, "middle"))
    # labels on the left, a height chain on the right
    xl = P(y_hi, 0)[0] - 6
    for nm, z in (("support floor", fl["support floor"]["z1"] / 2), ("waffle slab", (ws["z0"] + ws["z1"]) / 2),
                  ("raised floor, 0.6 x 0.6 m panels", (rf["z0"] + rf["z1"]) / 2), ("cleanroom", cl["z0"] + 3.6),
                  ("filter ceiling, fan filter units", cl["z1"] + 0.17), ("air space (return air)", (cl["z1"] + fl["air space"]["z1"]) / 2),
                  ("roof", (rf_["z0"] + rf_["z1"]) / 2)):
        o.append(text(xl, P(0, z)[1] + 0.9, nm, 2.4, "end"))
    xr = P(y_lo, 0)[0] + 10
    chain = [0.0] + [x["z1"] for x in S["floors"]]
    for z0, z1 in zip(chain, chain[1:]):
        p0, p1 = P(y_lo, z0), P(y_lo, z1)
        o.append(dim(xr, p0[1], xr, p1[1], f(z1 - z0, 2), off=0, size=2.0))
    p0, p1 = P(y_lo, cl["z0"]), P(y_lo, S["rail_z"])
    o.append(dim(xr + 14, p0[1], xr + 14, p1[1], f"{f(S['rail_z'] - cl['z0'], 1)} to rail", off=0, size=2.0))
    p1 = P(y_lo, cl["z0"] + 0.9)
    o.append(dim(xr + 24, p0[1], xr + 24, p1[1], "0.9", off=0, size=2.0))
    nx, ny = xr + 150, top + 30
    o.append(text(nx, ny, "WHAT TO CHECK ON THIS SHEET (questions 1 to 3 and 6 on A-900)", 3.0, weight="bold"))
    for i, ln in enumerate([
            "Cleanroom height, raised floor to filter ceiling: is it enough for the tallest tools and the hoist rail above them?",
            "Support floor height under the waffle slab: is it enough for pumps, abatement and chemical distribution?",
            "Waffle slab depth and the 12 m column grid: would they meet vibration criteria for lithography?",
            "Air space above the filters and the roof build-up: are they reasonable for return air and plant?",
            "Return air: we assume it falls through the raised floor and rises in the chases; is that a sensible scheme?",
            "Every height on this sheet is a starting guess of ours, not taken from a real building."]):
        o.append(text(nx, ny + 7 + i * 5.2, f"- {ln}", 2.6))
    return "".join(o)


# ------------------------------------------------------------------ the brief

def brief_blocks(S, L, sha):
    A = L["assumed"]
    B = []
    B.append(("h1", "Brief for the architect: Fab Gym campus"))
    B.append(("p", f"{TRUTH} This drawing set shows the campus layout that Fab Gym's simulator uses: 39 bays and 1,043 tools in two "
                   "phases, joined by a hoist bridge. Hoist travel on this layout sets how long each move of a lot takes in the "
                   "simulation, so the numbers below change the results. We would like a quick check of whether the layout is "
                   "buildable and which numbers are wrong."))
    B.append(("p", f"Drawn from results/layout-real/layout.json (sha256 {sha}). Concept for review, NOT FOR CONSTRUCTION. "
                   "Every placement number is assumed unless a source is named below."))
    B.append(("h2", "How the layout was made"))
    B.append(("p", "Each tool group of the SMT2020 model (105 groups and a holding group) is placed in the phase that sends it most "
                   "of its lots. Within a phase, areas are packed into bays on both sides of a central spine, and an optimiser "
                   f"orders the bays to cut hoist travel: {f(L['plans']['optimised']['metres_per_day'] / 1000, 0)} km a day "
                   f"against {f(L['plans']['plain']['metres_per_day'] / 1000, 0)} km for a plain alphabetical plan. A hoist move "
                   f"takes {f(A['overhead_min'])} min plus the distance at {f(A['speed_m_per_min'])} m/min, give or take "
                   f"{f(A['jitter_min'])} min (assumed)."))
    B.append(("h2", "Numbers to check: the layout"))
    rows = [
        ("bay depth", f"{f(A['bay_depth'])} m from the spine's edge", "assumed"),
        ("bay aisle", f"{f(A['bay_aisle'])} m between the two rows of tools", "assumed"),
        ("chase", f"{f(A['chase'])} m service chase behind each row", "assumed"),
        ("spine", f"{f(A['spine'])} m wide, interbay rails and stockers", "assumed"),
        ("bridge", f"{f(A['bridge'])} m between the phases' spines; bridge building "
                   f"{f([c for c in S['campus'] if c['kind'] == 'bridge'][0]['x1'] - [c for c in S['campus'] if c['kind'] == 'bridge'][0]['x0'], 1)} m long at +8.70", "assumed"),
        ("balance", f"the two sides of a spine within {f(A['balance'])} m of each other in length", "assumed"),
        ("bay width", "2 x (deepest tool + chase) + aisle; 17.5 m in most bays", "follows from the above"),
        ("column grid", f"{f(GRID)} x {f(GRID)} m in the support floor; the spine and aisles avoid columns", "assumed"),
        ("building", f"phase 1 {f(building(S, 0)['x1'] - building(S, 0)['x0'], 1)} x {f(building(S, 0)['y1'] - building(S, 0)['y0'], 1)} m, "
                     f"phase 2 {f(building(S, 1)['x1'] - building(S, 1)['x0'], 1)} x {f(building(S, 1)['y1'] - building(S, 1)['y0'], 1)} m", "follows from the above"),
    ]
    B.append(("table", rows))
    B.append(("h2", "Numbers to check: the levels (A-301)"))
    rows = [(fl["name"], f"+{fl['z0']:.2f} to +{fl['z1']:.2f}, {f(fl['z1'] - fl['z0'], 1)} m", "assumed") for fl in S["floors"]]
    rows += [("hoist rail underside", f"+{S['rail_z']:.2f}, 4.2 m above the raised floor", "assumed"),
             ("load port carrier seat", "0.9 m above the raised floor", "assumed"),
             ("roof plant", f"{f(PLANT_H, 1)} m on the roof", "assumed")]
    B.append(("table", rows))
    B.append(("break", None))
    B.append(("h2", "Numbers to check: tools by kind (W x D x H, metres)"))
    rows = []
    for kd, v in A["kinds"].items():
        K = S["kinds"][kd]
        rows.append((kd.replace("_", " "), f"{f(K['w'])} x {f(K['d'])} x {f(K['h'])}", CITED.get(kd, "assumed")))
    B.append(("table", rows))
    B.append(("h2", "Cited items"))
    B.append(("table", OTHER_CITED))
    B.append(("break", None))
    B.append(("h2", "Questions for the architect"))
    qs = [
        "Is a 5.5 m cleanroom, raised floor to filter ceiling, enough for scanners about 2.9 m tall with hoist rails 4.2 m above the floor?",
        "Is a 6.0 m support floor (sub-fab) enough for pumps, abatement and chemical distribution under the tools?",
        "Does a 0.9 m waffle slab on a 12 m column grid meet vibration criteria for lithography, or should the grid or slab change?",
        "Do 60 m deep bays with a 3.5 m aisle and 1.5 m chases work for service access, return air and egress?",
        "Is an 8 m spine wide enough for two interbay rails, stockers 3 x 12 x 5 m and people moving?",
        "Is 4.0 m of air space above the filters and a 1.5 m roof with 4.0 m plant reasonable for this floor area?",
        "Phase 1 is about 251 x 140 m with no exits, stairs or fire walls drawn: how would it be compartmented, and where must exits go?",
        "Can a hoist bridge 48 m long at +8.70 join two cleanroom buildings, and what separation does it need?",
        "Is the site plan sensible: utility building to the south with a 30 m link, ultrapure water beside it, gas yard and tanks to the north near the office?",
        "Which of our numbers would you change first, and by about how much?",
        "Which drawings or formats would you want from us next (more sections, sub-fab plan, IFC model)?",
        "Would the lithography bays need separating from the others for their yellow light, vibration or temperature?",
    ]
    B.append(("ol", qs))
    B.append(("h2", "Not drawn"))
    B.append(("p", "Exits, stairs and lifts; fire walls; gowning rooms and air showers; sub-fab equipment; utility routes "
                   "(exhaust, process gases, chemicals, ultrapure water, power); the office's inside. The model holds none of "
                   "them, and we would rather ask than invent them."))
    B.append(("p", "The SMT2020 model: Kopp, Hassoun, Kalir and Mönch, \"SMT2020: A semiconductor manufacturing testbed\", "
                   "IEEE Transactions on Semiconductor Manufacturing, 2020. A published model, not a real fab."))
    return B


def brief_md(blocks):
    o = []
    for kind, v in blocks:
        if kind == "h1":
            o.append(f"# {v}\n")
        elif kind == "h2":
            o.append(f"## {v}\n")
        elif kind == "p":
            o.append(textwrap.fill(v, 110) + "\n")
        elif kind == "table":
            o.append("| item | value | source |\n| --- | --- | --- |")
            o += [f"| {a} | {b} | {c} |" for a, b, c in v]
            o.append("")
        elif kind == "ol":
            o += [f"{i + 1}. {q}" for i, q in enumerate(v)]
            o.append("")
    return "\n".join(o).rstrip() + "\n"


def brief_sheet(blocks):
    cols = [AX0 + 2, AX0 + 2 + 265, AX0 + 2 + 530]
    cw = 250.0
    size = 3.4
    lh = size * 1.5
    chars = int(cw / (size * 0.52))
    ci, y = 0, AY0 + 4
    o = []

    def need(n):
        nonlocal ci, y
        if y + n * lh > AY1 - 2:
            ci += 1
            y = AY0 + 4

    for kind, v in blocks:
        if kind == "break":
            ci += 1
            y = AY0 + 4
        elif kind == "h1":
            need(3)
            o.append(text(cols[ci], y + 5, v, 5, weight="bold"))
            y += 10
        elif kind == "h2":
            need(4)
            y += 3
            o.append(text(cols[ci], y + 3, v.upper(), 3.6, weight="bold"))
            y += 7
        elif kind == "p":
            lines = textwrap.wrap(v, chars)
            for ln in lines:
                need(1)
                o.append(text(cols[ci], y + 3, ln, size))
                y += lh
            y += 1.5
        elif kind == "table":
            for a, b, c in v:
                ls = textwrap.wrap(f"{a}: {b}  [{c}]", chars - 3)
                need(len(ls))
                for j, ln in enumerate(ls):
                    o.append(text(cols[ci] + (0 if j == 0 else 3), y + 3, ("- " if j == 0 else "") + ln, size,
                                  fill=INK if j == 0 else INK))
                    y += lh
            y += 1.5
        elif kind == "ol":
            for i, q in enumerate(v):
                ls = textwrap.wrap(q, chars - 4)
                need(len(ls))
                for j, ln in enumerate(ls):
                    o.append(text(cols[ci] + 7, y + 3, ln, size))
                    if j == 0:
                        o.append(text(cols[ci], y + 3, f"{i + 1}.", size, weight="bold"))
                    y += lh
                y += 0.8
            y += 1.5
    return "".join(o)


# ------------------------------------------------------------------ the cover

def cover_sheet(S, L):
    o = [text(AX0 + 20, AY0 + 50, PROJECT, 16, weight="bold"),
         text(AX0 + 20, AY0 + 64, "Concept drawing set for review by an architect", 7),
         text(AX0 + 20, AY0 + 76, TRUTH, 4.5, fill=GREY)]
    y = AY0 + 100
    o.append(text(AX0 + 20, y, "DRAWING LIST", 3.6, weight="bold"))
    for sid, title, scale in SHEETS:
        y += 8
        o.append(text(AX0 + 20, y, sid, 3.4, weight="bold"))
        o.append(text(AX0 + 45, y, title, 3.4))
        o.append(text(AX0 + 230, y, f"1:{scale}" if scale else "-", 3.4))
    y += 18
    o.append(text(AX0 + 20, y, "GENERAL NOTES", 3.6, weight="bold"))
    notes = [
        "Units are metres. Levels are above the support floor's slab, +0.00; the clean floor is at +7.50.",
        "Plan origin: the west end of phase 1's spine, on its centre line; x east, y north.",
        "The layout is our own design, made by an optimiser over the SMT2020 model's tool groups and lot flows. It is not a real fab.",
        "Tools are generic boxes at the size of their kind (A-900), not any maker's equipment.",
        "Every placement number is assumed unless A-900 cites a source. The site outside the two fab buildings is drawn only.",
        "Not drawn: exits, stairs, fire walls, gowning, sub-fab equipment, utility routes. A-900 asks about them.",
        "A DXF of the plans in metres comes with this set (fab-plan.dxf), with layers for grid, walls, spine, bays, tools, stockers,",
        "hoist rails, labels and site.",
    ]
    for i, n in enumerate(notes):
        y += 6.5
        o.append(text(AX0 + 20, y, (f"{i + 1}. " if not n.startswith("hoist") else "    ") + n, 3.0))
    # key plan
    M = Map(2500, -10, 80, AX0 + 470, AY0 + 115)
    o.append(text(AX0 + 470, AY0 + 105, "KEY PLAN", 3.6, weight="bold"))
    for p in (0, 1):
        b = building(S, p)
        x, yy, w, h = M.box(b["x0"], b["y0"], b["x1"], b["y1"])
        o.append(rect(x, yy, w, h, INK, 0.35, "#dfe6ef"))
        o.append(text(x + w / 2, yy + h / 2 + 1.2, f"Phase {p + 1}: A-10{p + 1}", 3.0, "middle"))
    br = [c for c in S["campus"] if c["kind"] == "bridge"][0]
    x, yy, w, h = M.box(br["x0"], br["y0"], br["x1"], br["y1"])
    o.append(rect(x, yy, w, h, INK, 0.25, "#ffffff"))
    o.append(north(AX0 + 700, AY0 + 112))
    n_tools = len(S["tools"])
    o.append(text(AX0 + 470, AY0 + 190, f"{len(S['bays'])} bays, {n_tools} tools, {len(S['stockers'])} stockers; "
                                       f"{f(L['plans']['optimised']['metres_per_day'] / 1000, 0)} km of hoist travel a day", 3.0))
    o.append(text(AX0 + 470, AY0 + 196, "at the model's release rates.", 3.0))
    return "".join(o)


# ------------------------------------------------------------------ the DXF

class Dxf:
    LAYERS = [("A-GRID", 8), ("A-WALL", 7), ("A-SPINE", 9), ("A-BAY", 3), ("A-EQPM", 4), ("A-STKR", 6),
              ("A-OHT", 5), ("A-ANNO", 2), ("A-SITE", 8)]

    def __init__(self):
        self.ents = []
        self.xs, self.ys = [], []

    def _pt(self, x, y):
        self.xs.append(x)
        self.ys.append(y)
        return f"10\n{x:.3f}\n20\n{y:.3f}\n30\n0.0\n"

    def poly(self, layer, pts):
        s = f"0\nPOLYLINE\n8\n{layer}\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n"
        for x, y in pts:
            s += f"0\nVERTEX\n8\n{layer}\n" + self._pt(x, y)
        s += f"0\nSEQEND\n8\n{layer}\n"
        self.ents.append(s)

    def box(self, layer, x0, y0, x1, y1):
        self.poly(layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    def line(self, layer, x1, y1, x2, y2):
        s = f"0\nLINE\n8\n{layer}\n" + self._pt(x1, y1)
        self.xs.append(x2)
        self.ys.append(y2)
        s += f"11\n{x2:.3f}\n21\n{y2:.3f}\n31\n0.0\n"
        self.ents.append(s)

    def text(self, layer, x, y, h, s, rot=0.0):
        s = s.replace("\n", " ")
        e = f"0\nTEXT\n8\n{layer}\n" + self._pt(x, y) + f"40\n{h:.3f}\n1\n{s}\n"
        if rot:
            e += f"50\n{rot:.1f}\n"
        self.ents.append(e)

    def dump(self):
        o = ["0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n9\n$INSUNITS\n70\n6\n",
             f"9\n$EXTMIN\n10\n{min(self.xs):.3f}\n20\n{min(self.ys):.3f}\n30\n0.0\n",
             f"9\n$EXTMAX\n10\n{max(self.xs):.3f}\n20\n{max(self.ys):.3f}\n30\n0.0\n0\nENDSEC\n",
             "0\nSECTION\n2\nTABLES\n",
             "0\nTABLE\n2\nLTYPE\n70\n1\n0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid line\n72\n65\n73\n0\n40\n0.0\n0\nENDTAB\n",
             f"0\nTABLE\n2\nLAYER\n70\n{len(self.LAYERS)}\n"]
        for name, colour in self.LAYERS:
            o.append(f"0\nLAYER\n2\n{name}\n70\n0\n62\n{colour}\n6\nCONTINUOUS\n")
        o.append("0\nENDTAB\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n")
        o += self.ents
        o.append("0\nENDSEC\n0\nEOF\n")
        return "".join(o)


def dxf(S):
    D = Dxf()
    xs, ys = grid_lines(S)
    for p in (0, 1):
        b = building(S, p)
        for x in xs:
            if b["x0"] - 1e-6 <= x <= b["x1"] + 1e-6:
                D.line("A-GRID", x, b["y0"], x, b["y1"])
        for y in ys:
            D.line("A-GRID", b["x0"], y, b["x1"], y)
        D.box("A-WALL", b["x0"], b["y0"], b["x1"], b["y1"])
        D.box("A-SPINE", b["x0"], -S["spine"] / 2, b["x1"], S["spine"] / 2)
    for i, bay in enumerate(S["bays"]):
        D.box("A-BAY", bay["x0"], bay["y0"], bay["x1"], bay["y1"])
        cy = (bay["y0"] + bay["y1"]) / 2
        D.text("A-ANNO", (bay["x0"] + bay["x1"]) / 2, cy, 1.2, f"Bay {i + 1:02d} {S['areas'][bay['area']]['name']}", 90.0)
    for t in S["tools"]:
        D.box("A-EQPM", t["x0"], t["y0"], t["x1"], t["y1"])
        D.text("A-ANNO", t["x0"] + 0.2, (t["y0"] + t["y1"]) / 2, 0.35, S["groups"][t["g"]]["name"])
    for st in S["stockers"]:
        D.box("A-STKR", st["x0"], st["y0"], st["x1"], st["y1"])
    for a, c in S["rails"]:
        D.line("A-OHT", a[0], a[1], c[0], c[1])
    for c in S["campus"]:
        if c["kind"] == "fab":
            continue
        D.box("A-SITE", c["x0"], c["y0"], c["x1"], c["y1"])
        if c["label"]:
            D.text("A-SITE", c["x0"] + 1, (c["y0"] + c["y1"]) / 2, 2.5, c["label"])
    D.text("A-ANNO", 0, -80, 3.0, "Fab Gym campus. " + TRUTH + " Units metres. NOT FOR CONSTRUCTION.")
    return D.dump()


# ------------------------------------------------------------------ main

def build(scene, layout, out, pdf=True):
    S = json.loads(Path(scene).read_text())
    L = json.loads(Path(layout).read_text())
    sha = hashlib.sha256(Path(layout).read_bytes()).hexdigest()[:12]
    out = Path(out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    blocks = brief_blocks(S, L, sha)
    bodies = {
        "A-000": cover_sheet(S, L),
        "A-100": site_sheet(S),
        "A-101": plan_sheet(S, 0),
        "A-102": plan_sheet(S, 1),
        "A-110": bay_sheet(S),
        "A-301": section_sheet(S),
        "A-900": brief_sheet(blocks),
    }
    svgs = []
    for sid, title, scale in SHEETS:
        svg = sheet(sid, title, scale, bodies[sid], sha)
        (out / "sheets" / f"{sid}.svg").write_text(svg)
        svgs.append((sid, svg))
    html = ["<!doctype html><html><head><meta charset=\"utf-8\"><title>Fab Gym campus: drawing set</title><style>",
            "@page{size:841mm 594mm;margin:0}html,body{margin:0;padding:0;background:#fff}",
            ".s{width:841mm;height:594mm;break-after:page;page-break-after:always;overflow:hidden}",
            ".s:last-child{break-after:auto;page-break-after:auto}.s svg{display:block;width:841mm;height:594mm}",
            "</style></head><body>"]
    for sid, svg in svgs:
        html.append(f'<section class="s" data-sheet="{sid}">{svg}</section>')
    html.append("</body></html>\n")
    (out / "fab-blueprint.html").write_text("".join(html))
    (out / "brief.md").write_text(brief_md(blocks))
    (out / "fab-plan.dxf").write_text(dxf(S))
    msg = [f"wrote {out}: {len(SHEETS)} sheets, fab-blueprint.html, fab-plan.dxf, brief.md"]
    if pdf:
        if CHROME.exists():
            pdf_path = (out / "fab-blueprint.pdf").resolve()
            subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf_path}", (out / "fab-blueprint.html").resolve().as_uri()],
                           capture_output=True, timeout=180)
            msg.append(f"pdf {pdf_path}" if pdf_path.exists() else "pdf: Chrome ran but wrote no file")
        else:
            msg.append("pdf skipped: Google Chrome is not installed")
    return "\n".join(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=str(ROOT / "data/layout-real/scene-optimised.json"))
    ap.add_argument("--layout", default=str(ROOT / "results/layout-real/layout.json"))
    ap.add_argument("--out", default=str(ROOT / "data/layout-real/blueprint"))
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    print(build(a.scene, a.layout, a.out, pdf=not a.no_pdf))


if __name__ == "__main__":
    main()
