#!/usr/bin/env python3
"""The difference sheet between today's fab and the variant with copies (docs/NARRATIVE.md, deliverable 3).

    python3 viz/variant/diff.py [--out results/layout-real-dd-copies/difference]

Reads today's US building (results/layout-real-dd, data/layout-real-dd) and the variant's (fabsim variant, then the
same pipeline into data/layout-real-dd-copies): the copies, the capital and the hoist travel from variant.json; every
code check of both permit stages; the bill of materials; the drawn sheets; where every tool stands. Writes
difference.json, difference.md and the sheet X-001.svg. The same inputs give the same bytes.

A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. Prices and placements assumed.
NOT FOR CONSTRUCTION.
"""

import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUTH = ("From the SMT2020 testbed, a published set of a fab's tool groups, routes and times: a gigafab-style layout of our own design, "
         "not a real fab. Prices and placements assumed. NOT FOR CONSTRUCTION.")
TODAY = {"layout": "results/layout-real-dd/layout.json", "scene": "data/layout-real-dd/scene-optimised.json",
         "dd": "data/layout-real-dd/permit/us", "cd": "data/layout-real-dd/permit-cd/us"}
VAR = {"layout": "results/layout-real-dd-copies/layout.json", "scene": "data/layout-real-dd-copies/scene-optimised.json",
       "dd": "data/layout-real-dd-copies/permit/us", "cd": "data/layout-real-dd-copies/permit-cd/us",
       "variant": "results/layout-real-dd-copies/variant.json"}
SECTIONS = ["structure", "architecture", "mechanical", "piping", "fire", "electrical", "process equipment", "site"]
INK, GREY, RED, SAFFRON, AMBER, PALE = "#1d2430", "#6b7380", "#b3261e", "#e8892b", "#b26a00", "#d9dde3"
FT = 0.3048


def load(p):
    return json.loads((ROOT / p).read_text())


def f(x, d=1):
    s = f"{x:,.{d}f}"
    return s


# ---------- what differs ----------

def checks(stage):
    a = {(x["rule"], x["scope"]): x for x in load(f"{TODAY[stage]}/verdicts.json")}
    b = {(x["rule"], x["scope"]): x for x in load(f"{VAR[stage]}/verdicts.json")}
    changed = []
    for k in sorted(k for k in a if k in b):
        if (a[k]["verdict"], a[k]["why"]) != (b[k]["verdict"], b[k]["why"]):
            changed.append({"rule": k[0], "scope": k[1], "cite": b[k].get("cite", []),
                            "before": {"verdict": a[k]["verdict"], "why": a[k]["why"]},
                            "after": {"verdict": b[k]["verdict"], "why": b[k]["why"]}})
    count = lambda d: {v: sum(1 for x in d.values() if x["verdict"] == v) for v in sorted({x["verdict"] for x in d.values()})}
    return {"today": len(a), "variant": len(b), "verdicts_today": count(a), "verdicts_variant": count(b),
            "only_today": [list(k) for k in sorted(set(a) - set(b))],
            "only_variant": [list(k) for k in sorted(set(b) - set(a))], "changed": changed}


def bom():
    key = lambda l: (l["section"], l["class"], l["type"], l["material"], l["size"], l["unit"])
    a = {key(l): l for l in load(f"{TODAY['cd']}/bom/bom.json")["lines"]}
    b = {key(l): l for l in load(f"{VAR['cd']}/bom/bom.json")["lines"]}
    out = []
    for k in set(a) | set(b):
        qa = a[k]["quantity"] if k in a else 0
        qb = b[k]["quantity"] if k in b else 0
        if qa != qb:
            out.append({"section": k[0], "class": k[1], "type": k[2], "material": k[3], "size": k[4], "unit": k[5],
                        "before": qa, "after": qb, "change": round(qb - qa, 6)})
    out.sort(key=lambda x: (SECTIONS.index(x["section"]) if x["section"] in SECTIONS else 99, x["type"], x["size"], x["material"]))
    return out


def masked(path):
    t = path.read_text()
    return re.sub(r"[0-9a-f]{12,64}", "HASH", t).replace("layout-real-dd-copies", "layout-real-dd")


def sheets(stage):
    a, b = ROOT / TODAY[stage] / "sheets", ROOT / VAR[stage] / "sheets"
    names = sorted(p.name for p in a.glob("*.svg"))
    assert names == sorted(p.name for p in b.glob("*.svg")), f"{stage}: the two sets have different sheets"
    return {"total": len(names), "changed": [n for n in names if masked(a / n) != masked(b / n)]}


def places(scene):
    names = [g["name"] for g in scene["groups"]]
    seen, out = {}, {}
    for t in scene["tools"]:
        n = names[t["g"]]
        i = seen.get(n, 0)
        seen[n] = i + 1
        out[(n, i)] = t
    return out


def spot(t):
    return (t["bay"], round(t["x0"], 3), round(t["y0"], 3))


# ---------- drawing ----------

def rect(x, y, w, h, stroke=INK, sw=0.2, fill="none"):
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def text(x, y, s, size=2.6, anchor="start", weight="normal", fill=INK):
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" '
            f'fill="{fill}">{html.escape(str(s))}</text>')


def line(x0, y0, x1, y1, stroke=INK, sw=0.2):
    return f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke="{stroke}" stroke-width="{sw}"/>'


def world(scene, bay, x, y):
    # the scene's bays and tools are already in campus metres (x along the halls, y north of the spine positive)
    return x, y


def tool_box(scene, t):
    x0, y0 = world(scene, t["bay"], t["x0"], t["y0"])
    x1, y1 = world(scene, t["bay"], t["x1"], t["y1"])
    return min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)


def plan(scene, copies, moved, X, Y, k, label):
    """The whole fab in plan: buildings, bays, tools; the copies in saffron, moved tools outlined."""
    o = []
    fab = [c for c in scene["campus"] if c["kind"] in ("fab", "bridge")]
    xmin = min(c["x0"] for c in fab)
    ymax = max(c["y1"] for c in fab)
    M = lambda x, y: (X + (x - xmin) * k, Y + (ymax - y) * k)
    for c in fab:
        x, y = M(c["x0"], c["y1"])
        o.append(rect(x, y, (c["x1"] - c["x0"]) * k, (c["y1"] - c["y0"]) * k, INK, 0.4, "#ffffff"))
        if c["kind"] == "fab":
            o.append(text(x + 2, y + 4.5, c["label"], 2.8, weight="bold"))
    for i, b in enumerate(scene["bays"]):
        x0, y0 = world(scene, i, b["x0"], b["y0"])
        x1, y1 = world(scene, i, b["x1"], b["y1"])
        x, y = M(min(x0, x1), max(y0, y1))
        o.append(rect(x, y, abs(x1 - x0) * k, abs(y1 - y0) * k, "#c3c8cf", 0.12))
    names = [g["name"] for g in scene["groups"]]
    seen, labels = {}, []
    for t in scene["tools"]:
        n = names[t["g"]]
        i = seen.get(n, 0)
        seen[n] = i + 1
        bx, by, bw, bh = tool_box(scene, t)
        x, y = M(bx, by + bh)
        if n in copies:
            o.append(rect(x, y, bw * k, bh * k, INK, 0.15, SAFFRON))
            labels.append((n, x + bw * k / 2, y + bh * k / 2))
        elif (n, i) in moved:
            o.append(rect(x, y, bw * k, bh * k, AMBER, 0.18, "#fbe7cf"))
        else:
            o.append(rect(x, y, bw * k, bh * k, "none", 0, PALE))
    o.append(text(X, Y - 3, label, 3.2, weight="bold"))
    return o, labels


def inset(scene, bay, mark, moved, X, Y, k, title):
    """One bay, enlarged: its tools, the copy in saffron and the tools that moved outlined."""
    o = []
    b = scene["bays"][bay]
    w, h = (b["x1"] - b["x0"]) * k, (b["y1"] - b["y0"]) * k
    o.append(rect(X, Y, w, h, INK, 0.3, "#ffffff"))
    names = [g["name"] for g in scene["groups"]]
    seen = {}
    for t in scene["tools"]:
        n = names[t["g"]]
        i = seen.get(n, 0)
        seen[n] = i + 1
        if t["bay"] != bay:
            continue
        # bay-local: x along the hall, y away from the spine; drawn with the spine at the top
        dy = (t["y0"] - b["y0"]) if b["side"] == 0 else (b["y1"] - t["y1"])
        x, y = X + (t["x0"] - b["x0"]) * k, Y + dy * k
        tw, th = (t["x1"] - t["x0"]) * k, (t["y1"] - t["y0"]) * k
        if n == mark:
            o.append(rect(x, y, tw, th, INK, 0.2, SAFFRON))
        elif (n, i) in moved:
            o.append(rect(x, y, tw, th, AMBER, 0.25, "#fbe7cf"))
        else:
            o.append(rect(x, y, tw, th, GREY, 0.12, PALE))
    o.append(text(X, Y - 2.5, title, 2.6, weight="bold"))
    o.append(text(X, Y + h + 4, f"{b['area']} bay, phase {b['phase'] + 1}, {'north' if b['side'] == 0 else 'south'} side", 2.2, fill=GREY))
    return o, h


def table(x, y, cols, rows, size=3.0, colors=None):
    rh = size * 2.3
    o = [rect(x, y, sum(w for _, w in cols), rh, INK, 0.2, "#e8edf3")]
    cx = x
    for t, w in cols:
        o.append(text(cx + 1.2, y + rh - size * 0.75, t, size, weight="bold"))
        cx += w
    yy = y + rh
    for r, row in enumerate(rows):
        if r % 2 == 1:
            o.append(rect(x, yy, sum(w for _, w in cols), rh, "none", 0, "#f6f8fa"))
        cx = x
        for c, ((_, w), v) in enumerate(zip(cols, row)):
            s = str(v)
            maxc = max(4, int(w / (size * 0.52)))
            if len(s) > maxc:
                s = s[:maxc - 1] + "~"
            o.append(text(cx + 1.2, yy + rh - size * 0.75, s, size, fill=(colors or {}).get((r, c), INK)))
            cx += w
        yy += rh
    o.append(line(x, yy, x + sum(w for _, w in cols), yy, INK, 0.2))
    return o, yy


def sheet(D, today, var, moved):
    W, H = 1066.8, 762.0
    FX0, FY0, FX1, FY1, TB = 20.0, 10.0, 1046.8, 752.0, 50.0
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}mm" height="{H}mm" '
         f'font-family="Helvetica, Arial, sans-serif">', rect(0, 0, W, H, "none", 0, "#ffffff"),
         rect(FX0, FY0, FX1 - FX0, FY1 - FY0, INK, 0.7)]
    o.append(text(36, 27, "WHAT THE COPIES CHANGE: today's fab and the variant, drawn from the same pipeline", 3.4, weight="bold"))
    copies = {c["copy"] for c in D["copies"]}
    k = 1.15
    p, labels = plan(var, copies, moved, 40, 46, k, "Variant, clean floor plan (copies in saffron; tools that moved within their bay outlined)")
    o += p
    # leader labels for the copies, above the plan
    for j, (n, x, y) in enumerate(sorted(labels, key=lambda t: t[1])):
        ly = 40 + 175 + 8 + j * 5.5
        o.append(line(x, y, x, ly - 2, SAFFRON, 0.3))
        o.append(text(x + 1.5, ly, n, 2.6, weight="bold", fill=INK))
    # insets: each copy's bay, today and with the copy
    X, Y = 40.0, 262.0
    ki = 3.6
    o.append(text(X, Y - 10, "Each copy's bay, enlarged: today (left) and the variant (right)", 3.2, weight="bold"))
    vp, tp = places(var), places(today)
    for j, c in enumerate(D["copies"]):
        t = vp[(c["copy"], 0)]
        vb = var["bays"][t["bay"]]
        # today's bay of the same block: same phase, side, area and start along the hall
        tb = next(i for i, b in enumerate(today["bays"]) if (b["phase"], b["side"], b["area"], round(b["x0"], 2)) ==
                  (vb["phase"], vb["side"], vb["area"], round(vb["x0"], 2)))
        x0 = X + sum(2 * (var["bays"][vp[(e["copy"], 0)]["bay"]]["x1"] - var["bays"][vp[(e["copy"], 0)]["bay"]]["x0"]) * ki + 40
                     for e in D["copies"][:j])
        a, h = inset(today, tb, None, moved, x0, Y, ki, f"{c['original']}: today")
        o += a
        b, _ = inset(var, t["bay"], c["copy"], moved, x0 + (vb["x1"] - vb["x0"]) * ki + 14, Y, ki, f"with {c['copy']}")
        o += b
    # legend
    ly = Y + 60 * ki + 16
    for j, (fill, stroke, lab) in enumerate([(SAFFRON, INK, "a copy for prototype orders (new tool)"),
                                             ("#fbe7cf", AMBER, "a tool that moved along its wall to make room"),
                                             (PALE, GREY, "a tool where it stands today")]):
        o.append(rect(X + j * 130, ly - 3.5, 8, 4.5, stroke, 0.2, fill))
        o.append(text(X + j * 130 + 11, ly, lab, 2.6))
    o.append(text(X, ly + 9, "Insets drawn with the spine at the top. No bay, wall, chase or column moves; the halls keep their lengths.", 2.6, fill=GREY))
    # tables on the right
    TX = 640.0
    ty = 46.0
    cap = D["capital"]
    rows = [[c["copy"], c["area"], c["tools"]] for c in D["copies"]]
    t, ty = table(TX, ty, [("Copy", 70), ("Area", 40), ("Tools", 20)], rows)
    o.append(text(TX, 42, "The decision: one copy of each group prototype orders load most", 3.0, weight="bold"))
    o += t
    tr = D["travel"]
    rows = [
        ["Tools in the fab", f(D["tools"]["today"], 0), f(D["tools"]["variant"], 0)],
        ["Tools that moved within their bay", "", f(len(D["tools"]["moved"]), 0)],
        ["Bays", f(D["floor"]["bays"][0], 0), f(D["floor"]["bays"][1], 0)],
        ["Hall lengths, m", " / ".join(f(x) for x in D["floor"]["lengths"][0]), " / ".join(f(x) for x in D["floor"]["lengths"][1])],
        ["Fab footprint, m2", f(D["floor"]["footprint_m2"][0], 0), f(D["floor"]["footprint_m2"][1], 0)],
        ["Hoist travel, km a day", f(tr["before"] / 1000, 1), f(tr["after"] / 1000, 1)],
        ["Capital once, $M", "", f(cap["total"] / 1e6, 2)],
        ["Depreciation and upkeep, $ a day", "", f(cap["depreciation_day"] + cap["upkeep_day"], 0)],
    ]
    ty += 12
    o.append(text(TX, ty - 4, "What changes", 3.0, weight="bold"))
    t, ty = table(TX, ty, [("", 150), ("Today", 115), ("Variant", 115)], rows)
    o += t
    ty += 12
    o.append(text(TX, ty - 4, "Code checks rerun (2024 IBC and IFC, hypothetical US jurisdiction)", 3.0, weight="bold"))
    rows = []
    for st, name in (("dd", "Design development"), ("cd", "Construction documents")):
        c = D["checks"][st]
        rows.append([name, f"{c['today']} checks", f"{c['variant']} checks",
                     f"{sum(1 for x in c['changed'] if x['before']['verdict'] != x['after']['verdict'])} verdicts changed"])
    t, ty = table(TX, ty, [("Stage", 110), ("Today", 70), ("Variant", 70), ("", 130)], rows)
    o += t
    for x in D["checks"]["cd"]["changed"]:
        ty += 5
        o.append(text(TX, ty, f"{x['rule']} ({x['scope']}), {', '.join(x['cite'])}: {x['after']['verdict']}", 2.4, weight="bold"))
        ty += 4
        o.append(text(TX + 3, ty, "today: " + x["before"]["why"][:150], 2.2, fill=GREY))
        ty += 3.6
        o.append(text(TX + 3, ty, "variant: " + x["after"]["why"][:150], 2.2))
    ty += 12
    o.append(text(TX, ty - 4, "Bill of materials, lines that change (construction documents)", 3.0, weight="bold"))
    rows = [[x["section"], x["type"], x["size"] or x["material"], x["unit"], f(x["before"], 1 if x["unit"] != "each" else 0),
             f(x["after"], 1 if x["unit"] != "each" else 0), ("+" if x["change"] > 0 else "") + f(x["change"], 1 if x["unit"] != "each" else 0)]
            for x in D["bom"]]
    t, ty = table(TX, ty, [("Section", 55), ("Item", 85), ("Size", 50), ("Unit", 20), ("Today", 55), ("Variant", 55), ("Change", 60)], rows, size=2.8)
    o += t
    ty += 12
    for st, name in (("dd", "Design development"), ("cd", "Construction documents")):
        s = D["sheets"][st]
        o.append(text(TX, ty, f"{name}: {len(s['changed'])} of {s['total']} sheets change", 2.6, weight="bold"))
        ty += 4
        o.append(text(TX + 3, ty, ", ".join(x.removesuffix(".svg") for x in s["changed"])[:170], 2.2, fill=GREY))
        ty += 6
    # title block
    y0 = FY1 - TB
    o.append(line(FX0, y0, FX1, y0, INK, 0.5))
    cols = [FX0, FX0 + 230, FX0 + 450, FX0 + 570, FX0 + 690, FX1]
    for c in cols[1:-1]:
        o.append(line(c, y0, c, FY1, INK, 0.35))
    o.append(text(cols[0] + 5, y0 + 10, "Fab Gym campus", 6, weight="bold"))
    o.append(text(cols[0] + 5, y0 + 18, "Difference sheet: today and the variant with copies", 3.2))
    o.append(text(cols[0] + 5, y0 + 27, TRUTH[:150], 2.4))
    o.append(text(cols[0] + 5, y0 + 33, "Codes: 2024 IBC and IFC as published, for a hypothetical jurisdiction that adopts them unamended.", 2.3, fill=GREY))
    o.append(text(cols[0] + 5, y0 + 39, f"Drawn from {D['sources']['variant']} and both permit sets; see difference.json.", 2.3, fill=GREY))
    o.append(text(cols[1] + 5, y0 + 8, "DRAWING", 2.2, fill=GREY))
    o.append(text(cols[1] + 5, y0 + 17, "What the copies change", 4.6, weight="bold"))
    o.append(text(cols[2] + 5, y0 + 8, "SCALE", 2.2, fill=GREY))
    o.append(text(cols[2] + 5, y0 + 18, "plan and insets as shown", 3.2))
    o.append(text(cols[3] + 5, y0 + 8, "REVISION", 2.2, fill=GREY))
    o.append(text(cols[3] + 5, y0 + 18, "V1 variant for review", 3.4))
    o.append(text(cols[3] + 5, y0 + 30, "STATUS", 2.2, fill=GREY))
    o.append(text(cols[3] + 5, y0 + 40, "NOT FOR CONSTRUCTION", 3.4, weight="bold", fill=RED))
    o.append(text(cols[4] + 5, y0 + 8, "SHEET", 2.2, fill=GREY))
    o.append(text((cols[4] + cols[5]) / 2, y0 + 34, "X-001", 15, "middle", "bold"))
    o.append("</svg>")
    return "".join(o)


# ---------- the note ----------

def note(D):
    cap, tr = D["capital"], D["travel"]
    L = ["# What the copies change", "", TRUTH, "",
         "The decision: one copy of each of the three tool groups prototype orders load most, each placed right after "
         "its original in today's plan. Everything below comes from the same pipeline that draws today's fab.", "",
         "| copy | area | tools |", "|---|---|---|"]
    L += [f"| {c['copy']} | {c['area']} | {c['tools']} |" for c in D["copies"]]
    L += ["", f"- Tools: {D['tools']['today']} today, {D['tools']['variant']} with the copies; "
              f"{len(D['tools']['moved'])} tools moved within their bay to make room, none changed bay block.",
          f"- Bays {D['floor']['bays'][0]} and {D['floor']['bays'][1]}; hall lengths {D['floor']['lengths'][0]} m and "
          f"{D['floor']['lengths'][1]} m; fab footprint {f(D['floor']['footprint_m2'][0], 0)} and {f(D['floor']['footprint_m2'][1], 0)} m2.",
          f"- Hoist travel at the two-family flows: {f(tr['before'] / 1000)} km a day today, {f(tr['after'] / 1000)} km with "
          f"the copies ({100 * (tr['after'] - tr['before']) / tr['before']:+.2f}%). Exact for the stated flows.",
          f"- Capital from the central price sheet: ${f(cap['total'] / 1e6, 2)}M once (tools ${f(cap['tools'] / 1e6, 2)}M, "
          f"qualifying ${f(cap['qualify'] / 1e6, 2)}M, floor ${f(cap['floor'] / 1e6, 2)}M); "
          f"${f(cap['depreciation_day'] + cap['upkeep_day'], 0)} a day in depreciation and upkeep.", "",
          "## Code checks rerun", ""]
    for st, name in (("dd", "Design development"), ("cd", "Construction documents")):
        c = D["checks"][st]
        flips = [x for x in c["changed"] if x["before"]["verdict"] != x["after"]["verdict"]]
        L.append(f"- {name}: {c['today']} checks today, {c['variant']} for the variant; {len(flips)} verdicts change, "
                 f"{len(c['changed'])} reasons change.")
        for x in c["changed"]:
            L.append(f"  - {x['rule']} ({x['scope']}; {', '.join(x['cite'])}): {x['before']['verdict']} to "
                     f"{x['after']['verdict']}. Today: {x['before']['why']}. Variant: {x['after']['why']}.")
    L += ["", "## Bill of materials, lines that change", "", "| section | item | size | unit | today | variant | change |",
          "|---|---|---|---|---|---|---|"]
    L += [f"| {x['section']} | {x['type']} | {x['size'] or x['material']} | {x['unit']} | {x['before']} | {x['after']} | {x['change']:+} |"
          for x in D["bom"]]
    L += ["", "## Sheets that change", ""]
    for st, name in (("dd", "Design development"), ("cd", "Construction documents")):
        s = D["sheets"][st]
        L.append(f"- {name}: {len(s['changed'])} of {s['total']}: {', '.join(x.removesuffix('.svg') for x in s['changed'])}.")
    L += ["", "A sheet counts as changed when anything on it differs other than the source file named in its title block."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/layout-real-dd-copies/difference")
    a = ap.parse_args()
    v = load(VAR["variant"])
    today, var = load(TODAY["scene"]), load(VAR["scene"])
    pa, pb = places(today), places(var)
    moved = sorted(k for k in pa if k in pb and spot(pa[k]) != spot(pb[k]))
    lt, lv = load(TODAY["layout"]), load(VAR["layout"])
    foot = lambda s: round(sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in s["campus"] if c["kind"] == "fab"), 3)
    D = {
        "truth": TRUTH,
        "sources": {"today": TODAY, "variant": VAR["variant"], "variant_paths": VAR},
        "copies": v["copies"],
        "capital": v["capital"],
        "travel": v["travel"],
        "tools": {"today": len(pa), "variant": len(pb), "moved": [list(k) for k in moved]},
        "floor": {"bays": [len(lt["plans"]["optimised"]["bays"]), len(lv["plans"]["optimised"]["bays"])],
                  "lengths": [lt["plans"]["optimised"]["lengths"], lv["plans"]["optimised"]["lengths"]],
                  "footprint_m2": [foot(today), foot(var)]},
        "checks": {"dd": checks("dd"), "cd": checks("cd")},
        "bom": bom(),
        "sheets": {"dd": sheets("dd"), "cd": sheets("cd")},
    }
    out = ROOT / a.out if not Path(a.out).is_absolute() else Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "difference.json").write_text(json.dumps(D, indent=1, sort_keys=True) + "\n")
    (out / "difference.md").write_text(note(D))
    (out / "X-001.svg").write_text(sheet(D, today, var, set(moved)))
    print(f"wrote {out}: {len(moved)} tools moved, {len(D['bom'])} bill of materials lines change, "
          f"{len(D['sheets']['dd']['changed'])} + {len(D['sheets']['cd']['changed'])} sheets change")


if __name__ == "__main__":
    main()
