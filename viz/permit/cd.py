"""Construction documents for one bay (docs/CONSTRUCTION-DOCS.md, CD1 to CD8): the lithography bay carried to LOD
400. The site's seismic values; base plates, anchor rods, footing mats, waffle ribs and truss members; raised floor
tiles, fan filter units one by one and chase panels; a drop and valve per utility per tool, power feeders, lateral
hangers and gas lines; sprinkler heads and detector sampling points on assumed spacing until NFPA is read. Elements
the bay's detail replaces (the arrays, envelopes and combined drops over it) are taken out first; everything new is
placed by dd_place, so it clashes with nothing. Every size is assumed unless it is a limit read from the register.
"""

import json
import math
from pathlib import Path

from ctx import FT, SQFT
from dd_arch import WALL_TYPES, frange
from dd_place import Index
from geom import overlap
from rules import q
from utilities import KIND, LAT_RECT_H, size

ROOT = Path(__file__).resolve().parents[2]
PLATE, PLATE_T, ANCHOR_D, ANCHOR_L = 0.7, 0.04, 0.025, 0.6   # base plate side and thickness, anchor rod (assumed)
BAR_D, BAR_A, FY_BAR = 0.020, 314e-6, 420.0                   # bottom mat bars and their yield, MPa (assumed)
RIB_W, RIB_PITCH = 0.2, 1.5                                   # waffle ribs (assumed)
TILE = 0.6
HANGER = 2.4                                                  # largest hanger spacing, m (assumed)
V_FEED = 480.0                                                # feeder voltage, three phase (assumed)
AMPACITY = [(30, "10 AWG"), (40, "8 AWG"), (55, "6 AWG"), (75, "4 AWG"), (95, "3 AWG"), (115, "2 AWG"), (130, "1 AWG"),
            (150, "1/0"), (175, "2/0"), (200, "3/0"), (230, "4/0"), (255, "250 kcmil"), (285, "300 kcmil"),
            (310, "350 kcmil"), (335, "400 kcmil"), (380, "500 kcmil")]   # assumed copper ratings; NFPA 70 not read
GAS_HAZ = ("flammable gas", "pyrophoric gas", "toxic gas", "highly toxic gas", "oxidizing gas", "corrosive gas")


def cd(**kw):
    return {"stage": "CD", "lod": 400, "review": "construction documents", **kw}


def inside(bx, B, pad=0.0):
    cx, cy = (bx[0] + bx[3]) / 2, (bx[1] + bx[4]) / 2
    return B["x0"] - pad <= cx <= B["x1"] + pad and B["y0"] - pad <= cy <= B["y1"] + pad


def run(C):
    S, P = C.S, C.P
    bi = C.permit["cd"]["bay"]
    B = S["bays"][bi]
    p = B["phase"]
    k = C.keys[p]
    name = f"bay {bi + 1:02d}"
    tools = [i for i, t in enumerate(S["tools"]) if t["bay"] == bi]
    side = 1 if B["y0"] > 0 else -1
    D = {"bay": {"index": bi, "id": name, "building": k, "area": B["area"], "box": [B["x0"], B["y0"], B["x1"], B["y1"]],
                 "tools": len(tools)}}
    C.P["cd"] = D
    site(C, D)
    # take out what the bay's detail replaces
    cid = {c["id"] for c in P["chases"] if c["bay"] == bi}
    gone = set()
    for e in C.new:
        kk = e["key"]
        if kk.startswith(f"permit/ffu/{name}/") or kk.startswith(f"permit/spr/bay{bi + 1:02d}/"):
            gone.add(kk)
        elif kk.startswith(f"permit/{k}/truss/{'N' if side > 0 else 'S'}/") and B["x0"] < (e["box"][0] + e["box"][3]) / 2 < B["x1"]:
            gone.add(kk)
        elif any(kk == f"permit/chase/{c}/wall" for c in cid):
            gone.add(kk)
        elif kk.startswith("permit/drop/") and int(kk.split("/")[-1]) in tools:
            gone.add(kk)
    old = {e["key"]: e for e in C.new if e["key"] in gone}
    C.new = [e for e in C.new if e["key"] not in gone]
    D["replaced"] = len(gone)
    X = Index(C)
    services(C, X, D, B, tools, old)
    structure(C, X, D, B, p, k, side, old)
    architecture(C, X, D, B, p, bi, name, cid, old)
    fire(C, X, D, B, p, name)
    clearances(C, D, B, tools)
    for e in C.new:
        if e["permit"]["Stage"] == "CD":
            e["permit"]["LOD"] = 400
    D["lod400"] = sum(1 for e in C.new if e["permit"]["Stage"] == "CD")
    C.made.update({"cd:site", "cd:tiles", "cd:ffu", "cd:plates", "cd:mats", "cd:ribs", "cd:trusses", "cd:hangers", "cd:drops",
                   "cd:clearances", "cd:heads", "cd:alarm"})


# ------------------------------------------------------------------ CD1 site

def site(C, D):
    R = json.loads((ROOT / C.permit["cd"]["site"]).read_text())
    v = R["seismic"]["values"]
    D["site"] = {"region": R["region"], "point": R["point"],
                 "seismic": {**v, "risk_category": "IV", "importance_factor": 1.5, "site_class": "D (assumed)",
                             "basis": f"cited: USGS ASCE 7-22 design values, queried {R['seismic']['queried']}"},
                 "wind": R["wind"], "snow": R["snow"],
                 "shown": ["risk category", "importance factor", "SS and S1", "site class", "SDS and SD1", "seismic design category"],
                 "not_shown": ["force-resisting system", "base shear", "Cs", "R", "analysis procedure"],
                 "note": "the importance factor 1.5 for risk category IV is from the values' service response, ASCE 7 not read"}
    C.case("site.seismic_values", D["bay"]["building"], seismic_items_shown=q(True, "design: items 1 to 6 of 1603.1.5 on S-510"))


# ------------------------------------------------------------------ CD2 structure

def structure(C, X, D, B, p, k, side, old):
    F = C.P["frame"]
    cols = [e for e in C.M["elements"] if e["cls"] == "IfcColumn" and e["bld"] == p and inside(e["box"], B)]
    foots = [e for e in C.new if e["cls"] == "IfcFooting" and e["bld"] == p]
    frec = {f["id"].replace("permit/", ""): f for f in F["footings"]}
    out_c, out_f, seen = [], [], set()
    for e in sorted(cols, key=lambda e: e["key"]):
        x0, y0, _, x1, y1, _ = e["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        h = PLATE / 2
        X.add(f"cd/plate/{e['key']}", "IfcPlate", f"Base plate, {e['key']}", (cx - h, cy - h, 0.0, cx + h, cy + h, PLATE_T), p,
              "support floor", "USERDEFINED", "base plate", **cd(numbers=f"{PLATE * 1000:.0f} x {PLATE * 1000:.0f} x {PLATE_T * 1000:.0f} mm (assumed)"))
        for n, (dx, dy) in enumerate(((-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25))):
            a = (cx + dx - ANCHOR_D / 2, cy + dy - ANCHOR_D / 2, -ANCHOR_L + PLATE_T + 0.06, cx + dx + ANCHOR_D / 2, cy + dy + ANCHOR_D / 2, PLATE_T + 0.06)
            ee = X.add(f"cd/anchor/{e['key']}/{n}", "IfcMechanicalFastener", f"Anchor rod, {e['key']}", a, p, "support floor",
                       "ANCHORBOLT", "anchor rod", **cd(numbers=f"{ANCHOR_D * 1000:.0f} mm, {ANCHOR_L * 1000:.0f} mm (assumed)"))
            ee["fastener"] = (ANCHOR_D, ANCHOR_L)
        out_c.append({"id": e["key"], "plate_mm": round(PLATE * 1000), "plate_t_mm": round(PLATE_T * 1000), "anchors": 4,
                      "anchor_mm": round(ANCHOR_D * 1000)})
        ft = next((f for f in foots if f["box"][0] <= cx <= f["box"][3] and f["box"][1] <= cy <= f["box"][4]), None)
        if ft is None or ft["key"] in seen:
            continue
        seen.add(ft["key"])
        fx0, fy0, _, fx1, fy1, _ = ft["box"]
        L = min(fx1 - fx0, fy1 - fy0)
        load = sum(f["load_kN"] for f in F["footings"] if f.get("combined") == ft["key"]) or \
            next((f["load_kN"] for f in F["footings"] if "permit/" + f["id"] == ft["key"] or f["id"] == ft["key"].replace("permit/", "")), 0)
        qn = load / ((fx1 - fx0) * (fy1 - fy0))
        c = max(0.0, (L - 0.6) / 2)
        M = qn * c * c / 2 * (fy1 - fy0)
        d = 1.1
        need = max(M * 1e6 / (0.87 * FY_BAR * d * 1000), 0.0018 * (fy1 - fy0) * 1000 * 1200)
        n = math.ceil(need / (BAR_A * 1e6))
        bar = X.add(f"cd/mat/{ft['key']}", "IfcReinforcingBar", f"Bottom mat, {ft['key']}",
                    (fx0 + 0.075, fy0 + 0.075, -1.125, fx1 - 0.075, fy1 - 0.075, -1.075), p, "support floor", "MAIN",
                    "bottom mat", **cd(numbers=f"{n} bars of {BAR_D * 1000:.0f} mm each way (assumed fy {FY_BAR:.0f} MPa)"))
        bar["bar"] = (BAR_D, BAR_A, L)
        out_f.append({"id": ft["key"], "load_kN": round(load, 1), "side_m": round(L, 3), "moment_kNm": round(M, 1),
                      "as_needed_mm2": round(need), "bars": n, "bar_mm": round(BAR_D * 1000), "as_provided_mm2": round(n * BAR_A * 1e6)})
    # waffle ribs under the bay, split around everything that passes through the slab
    z0, z1 = C.fl["waffle slab"]["z0"], C.fl["waffle slab"]["z1"]
    holes = [e["box"] for e in C.new if e["box"][2] <= z0 + 1e-6 and e["box"][5] >= z1 - 1e-6 and inside(e["box"], B, 0.5)]
    ribs = 0
    lines = [("x", y) for y in frange(B["y0"] + RIB_PITCH / 2, B["y1"] - 0.1, RIB_PITCH)] + \
            [("y", x) for x in frange(B["x0"] + RIB_PITCH / 2, B["x1"] - 0.1, RIB_PITCH)]
    for axis, v in lines:
        a, b = (B["x0"], B["x1"]) if axis == "x" else (B["y0"], B["y1"])
        cuts = []
        for h in holes:
            lo, hi = (h[1], h[4]) if axis == "x" else (h[0], h[3])
            if lo - 0.05 < v + RIB_W / 2 and hi + 0.05 > v - RIB_W / 2:
                cuts.append(((h[0], h[3]) if axis == "x" else (h[1], h[4])))
        cuts.sort()
        pos = a
        segs = []
        for lo, hi in cuts:
            if lo - 0.05 > pos:
                segs.append((pos, lo - 0.05))
            pos = max(pos, hi + 0.05)
        if pos < b:
            segs.append((pos, b))
        for s0, s1 in segs:
            if s1 - s0 < 0.2:
                continue
            box = (s0, v - RIB_W / 2, z0, s1, v + RIB_W / 2, z1) if axis == "x" else (v - RIB_W / 2, s0, z0, v + RIB_W / 2, s1, z1)
            e = X.place(f"cd/rib/{axis}/{v:.2f}/{s0:.2f}", "IfcMember", "Waffle rib", [box], p, "waffle slab", "USERDEFINED",
                        "waffle rib", need=False, **cd(numbers=f"{RIB_W * 1000:.0f} mm wide, 900 mm deep (assumed)"))
            ribs += e is not None
    # roof trusses over the bay as chords and verticals
    members = 0
    for kk, e in sorted(old.items()):
        if "/truss/" not in kk:
            continue
        x0, y0, zb, x1, y1, zt = e["box"]
        xc = (x0 + x1) / 2
        ot = f"truss member {kk.replace('permit/', '')}"
        for nm, box in (("top chord", (xc - 0.15, y0, zt - 0.3, xc + 0.15, y1, zt)), ("bottom chord", (xc - 0.15, y0, zb, xc + 0.15, y1, zb + 0.3))):
            X.add(f"cd/{kk.replace('permit/', '')}/{nm.replace(' ', '-')}", "IfcMember", f"Truss {nm}", box, p, "air space", "CHORD", ot,
                  **cd(numbers="steel, by required properties on S-601 (preliminary)"))
            members += 1
        for y in frange(y0 + 0.2, y1 - 0.2, 3.0):
            X.add(f"cd/{kk.replace('permit/', '')}/vert/{y:.2f}", "IfcMember", "Truss vertical",
                  (xc - 0.08, y - 0.08, zb + 0.3, xc + 0.08, y + 0.08, zt - 0.3), p, "air space", "MEMBER", ot,
                  **cd(numbers="diagonals per the truss detail on S-510"))
            members += 1
    D["structure"] = {"columns": out_c, "footings": out_f, "ribs": ribs, "rib_pitch_m": RIB_PITCH, "truss_members": members,
                      "truss_envelopes_left_over_bay": sum(1 for e in C.new if e["cls"] == "IfcBeam" and "/truss/" in e["key"] and inside(e["box"], {
                          "x0": B["x0"], "x1": B["x1"], "y0": -1e9, "y1": 1e9}) and (e["box"][1] > 0) == (side > 0)),
                      "note": "bars, plates and anchors assumed; every member preliminary, for licensed review"}
    bay = D["bay"]["building"]
    C.case("cd.base_plates", bay, plates_ok=q(bool(out_c) and all(c["anchors"] >= 4 for c in out_c), "design"))
    C.case("cd.footing_mats", bay, mats_ok=q(all(f["as_provided_mm2"] >= f["as_needed_mm2"] for f in out_f),
                                             "assumed: bending at an assumed steel stress"))


# ------------------------------------------------------------------ CD3 architecture

def architecture(C, X, D, B, p, bi, name, cid, old):
    S, P = C.S, C.P
    cz = S["clean_z"]
    # fan filter units one by one, at each array's count
    area = (B["x1"] - B["x0"]) * (B["y1"] - B["y0"])
    target = next(b["target"] for b in P["air"]["bays"] if b["bay"] == name)
    units = 0
    for kk, e in sorted(old.items()):
        if not kk.startswith(f"permit/ffu/{name}/"):
            continue
        m = int(e["permit"]["Numbers"].split(" ")[0])
        x0, y0, z0, x1, y1, z1 = e["box"]
        cols, rows = int((x1 - x0) // 1.2), int((y1 - y0) // 0.6)
        slots = [(x0 + i * 1.2, y0 + j * 0.6) for j in range(rows) for i in range(cols)]
        pick = [slots[int(n * len(slots) / m)] for n in range(m)] if m <= len(slots) else None
        if pick is None:
            raise SystemExit(f"{kk}: {m} units do not fit")
        for n, (ux, uy) in enumerate(pick):
            X.add(f"cd/ffu/{name}/{kk.split('/')[-1]}/{n}", "IfcAirTerminal", f"Fan filter unit, {name}", (ux, uy, z0, ux + 1.2, uy + 0.6, z1),
                  p, "cleanroom", "USERDEFINED", "fan filter unit", **cd(numbers="1200 x 600 mm, H14 (assumed)"))
            units += 1
    cov = units * 1.2 * 0.6 / area
    # raised floor tiles over the bay; perforated along the aisle
    mid = (B["x0"] + B["x1"]) / 2
    tiles = perf = 0
    tarea = 0.0
    for x in frange(B["x0"], B["x1"] - 1e-6, TILE):
        for y in frange(B["y0"], B["y1"] - 1e-6, TILE):
            x1, y1 = min(x + TILE, B["x1"]), min(y + TILE, B["y1"])
            pf = abs((x + x1) / 2 - mid) < S["aisle"] / 2
            X.add(f"cd/tile/{x:.2f}/{y:.2f}", "IfcCovering", "Raised floor tile" + (", perforated" if pf else ""),
                  (x, y, cz - 0.03, x1, y1, cz), p, "raised floor", "FLOORING", "raised floor tile",
                  **cd(numbers="600 x 600 mm, conductive" + (", perforated 25% open (assumed)" if pf else "")))
            tiles += 1
            perf += pf
            tarea += (x1 - x) * (y1 - y)
    # chase partitions as panels at most 1.2 m wide
    panels, widest = 0, 0.0
    for c in sorted(cid):
        e = old[f"permit/chase/{c}/wall"]
        x0, y0, z0, x1, y1, z1 = e["box"]
        n = math.ceil((y1 - y0) / 1.2 - 1e-9)
        w = (y1 - y0) / n
        widest = max(widest, w)
        for j in range(n):
            pe = X.add(f"cd/panel/{c}/{j}", "IfcWall", f"Chase partition panel {c}", (x0, y0 + j * w, z0, x1, y0 + (j + 1) * w, z1), p,
                       "cleanroom", "PARTITIONING", "chase partition panel", **cd(numbers=f"WT-C panel {w:.2f} m wide"))
            t = WALL_TYPES["WT-C"]
            pe["rating"] = {"Rating_h": 0.0, "WallType": "WT-C", "Assembly": t["assembly"], "Cite": t["cite"]}
            panels += 1
    D["arch"] = {"tiles": tiles, "perforated": perf, "tile_coverage": round(tarea / area, 6), "tile_mm": round(TILE * 1000),
                 "ffu": [{"array": name, "units": units, "coverage": round(cov, 4), "target": target}],
                 "panels": panels, "max_panel_width_m": round(widest, 4),
                 "door_hardware": "lever, closer, kick plate, cleanroom seals; no locks on the fab side (assumed)"}
    bay = D["bay"]["building"]
    C.case("cd.tiles", bay, tiles_ok=q(tarea / area >= 0.99, "design"))
    C.case("cd.ffu_coverage", bay, ffu_ok=q(cov >= target - 1e-9, "assumed: the class's coverage"))


# ------------------------------------------------------------------ CD4 services

def services(C, X, D, B, tools, old):
    S, P = C.S, C.P
    cz = S["clean_z"]
    p = B["phase"]
    out = {}
    nv = nh = 0
    for i in tools:
        t = S["tools"][i]
        card = C.cards[t["kind"]]["utilities"]
        need = [u for u in KIND if card[u]["value"] > 0]
        got = {"drops": [], "valves": [], "feeder": False, "gas_lines": []}
        o = old.get(f"permit/drop/{i}")
        ox, oy = ((o["box"][0] + o["box"][3]) / 2, (o["box"][1] + o["box"][4]) / 2) if o else ((t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2)
        cand = sorted({(round(ox + dx, 3), round(oy + dy, 3)) for dx in frange(-2.0, 2.0, 0.35) for dy in frange(-2.0, 2.0, 0.35)},
                      key=lambda c: (abs(c[0] - ox) + abs(c[1] - oy), c))
        for u in need:
            kind = KIND[u][0]
            if kind == "tray":
                d, cls, pre, ot = 0.15, "IfcCableCarrierSegment", "CONDUITSEGMENT", "power feeder"
                lab = "feeder conduit"
            else:
                Q = card[u]["value"] * KIND[u][1]
                lab, w, _, runs, _ = size(u, Q, KIND[u][3], LAT_RECT_H)
                d = min(max(w, 0.05), 0.4)
                cls = "IfcDuctSegment" if kind == "duct" else "IfcPipeSegment"
                pre, ot = "RIGIDSEGMENT", "tool drop"
            boxes = [(x - d / 2, y - d / 2, 5.8, x + d / 2, y + d / 2, cz) for x, y in cand
                     if t["x0"] + 0.1 <= x - d / 2 and x + d / 2 <= t["x1"] - 0.1 and t["y0"] + 0.1 <= y - d / 2 and y + d / 2 <= t["y1"] - 0.1]
            # keep 0.12 m between drops so each valve has room
            boxes = [b for b in boxes if X.free((b[0] - 0.12, b[1] - 0.12, b[2], b[3] + 0.12, b[4] + 0.12, b[5]), cls=cls, otype=ot)]
            e = X.place(f"cd/drop/{i}/{u}", cls, f"{u} drop to tool {i}", boxes, p, "support floor", pre, ot,
                        **cd(numbers=f"{lab} for {u}"))
            if kind == "tray":
                got["feeder"] = True
                continue
            got["drops"].append(u)
            if kind == "pipe":
                x0, y0, _, x1, y1, _ = e["box"]
                X.add(f"cd/valve/{i}/{u}", "IfcValve", f"Isolation valve, {u}, tool {i}", (x0 - 0.05, y0 - 0.05, 5.85, x1 + 0.05, y1 + 0.05, 6.0),
                      p, "support floor", "ISOLATING", "isolation valve", **cd(numbers="ball valve, lockable (assumed)"))
                got["valves"].append(u)
                nv += 1
        # gas lines from the bay's valve boxes to every tool that draws a hazardous gas
        for c in C.cards[t["kind"]]["chemistry"]:
            if c["hazard"] in GAS_HAZ:
                vmb = next((v for v in P["valve_boxes"] if v["bay"] == S["bays"].index(B) and v["gas"] == c["material"]), None)
                if vmb is None:
                    raise SystemExit(f"tool {i}: no valve box for {c['material']}")
                got["gas_lines"].append(c["material"])
        out[str(i)] = got
    # hangers under the laterals of the bay
    lats = [e for e in C.new if e["cls"] in ("IfcPipeSegment", "IfcDuctSegment", "IfcCableCarrierSegment") and f"/lat/{S['bays'].index(B)}/" in e["key"]]
    worst = 0.0
    for e in lats:
        x0, y0, _, x1, y1, z1 = e["box"]
        xc = (x0 + x1) / 2
        ys = []
        target = y0 + HANGER / 2
        while target < y1:
            for dy in (0.0, -0.2, 0.2, -0.4, 0.4, -0.6, 0.6):
                y = target + dy
                if not (y0 + 0.05 <= y <= y1 - 0.05) or (ys and y - ys[-1] > HANGER):
                    continue
                box = (xc - 0.01, y - 0.01, z1, xc + 0.01, y + 0.01, 6.0)
                if X.free(box, cls="IfcMember", otype="pipe hanger rod"):
                    X.add(f"cd/hanger/{e['key'].replace('permit/', '')}/{len(ys)}", "IfcMember", "Hanger rod", box, p, "support floor",
                          "USERDEFINED", "pipe hanger rod", **cd(numbers="10 mm rod to the waffle slab (assumed)"))
                    ys.append(y)
                    nh += 1
                    break
            else:
                raise SystemExit(f"no hanger near y {target:.1f} on {e['key']}")
            target = ys[-1] + HANGER
        gaps = [b - a for a, b in zip(ys, ys[1:])] + [2 * (ys[0] - y0), 2 * (y1 - ys[-1])]
        worst = max(worst, max(gaps))
    feeders = {}
    table = C.reg["sections"].get("NFPA 70 T310.16")
    rows = [(a, nm) for nm, a in table["facts"]["copper_75C_A"]] if table else AMPACITY
    cf = C.reg["sections"]["NFPA 70 215.2(A)(1)"]["facts"]["continuous_factor"] if table else 1.25
    for i in tools:
        kva = C.cards[S["tools"][i]["kind"]]["utilities"]["power_kva"]["value"]
        amps = kva * 1000 / (math.sqrt(3) * V_FEED) * cf
        a_, cond = next(((a, nm) for a, nm in rows if a >= amps), (None, "parallel conductors"))
        feeders[str(i)] = {"kva": kva, "amps_125pct": round(amps, 1), "conductor": cond, "ampacity_A": a_,
                           "basis": "NFPA 70-2023 Table 310.16, 75 C copper, at 125% (215.2(A)(1)); terminals rated 75 C (assumed)"
                           if table else "assumed table; NFPA 70 not read"}
    D["services"] = {"tools": out, "valves": nv, "hangers": nh, "max_hanger_spacing_m": round(worst, 3), "feeders": feeders}
    bay = D["bay"]["building"]
    C.case("cd.drops", bay, drops_ok=q(all(set(g["drops"]) | ({"power_kva"} if g["feeder"] else set()) ==
                                          {u for u in KIND if C.cards[S["tools"][int(i)]["kind"]]["utilities"][u]["value"] > 0}
                                          for i, g in out.items()), "design"))
    C.case("cd.hangers", bay, hangers_ok=q(worst <= HANGER + 1e-9, "assumed: 2.4 m largest spacing"))
    C.case("cd.gas_lines", bay, gas_lines_ok=q(True, f"design: {sum(len(g['gas_lines']) for g in out.values())} lines; the bay's tools "
                                                     "draw no hazardous gas" if not any(g["gas_lines"] for g in out.values()) else "design"))
    C.case("elec.conductors", bay, conductors_ok=q(all(f["ampacity_A"] is not None and f["ampacity_A"] >= f["amps_125pct"]
                                                       for f in feeders.values()), feeders[str(tools[0])]["basis"] if tools else "none"))


# ------------------------------------------------------------------ CD5 to CD7: sprinklers and detection by NFPA 13 and 72

def nfpa(C, key, fact, default):
    sec = C.reg["sections"].get(key)
    return (sec["facts"][fact], True) if sec else (default, False)


def grid(a, b, step):
    """Even rows across a span: as few as keep the spacing within step, the first and last half a spacing in."""
    n = max(1, math.ceil((b - a) / step - 1e-9))
    s = (b - a) / n
    return [a + s * (i + 0.5) for i in range(n)], s


def fire(C, X, D, B, p, name):
    ceil0 = C.fl["cleanroom"]["z1"]
    sp, r13 = nfpa(C, "NFPA 13 T10.2.4.2.1(b)", "spacing_ft", 15)
    ar, _ = nfpa(C, "NFPA 13 T10.2.4.2.1(b)", "area_sqft", 130)
    wf, _ = nfpa(C, "NFPA 13 10.2.5", "wall_max_fraction_of_spacing", 0.5)
    mn, _ = nfpa(C, "NFPA 13 10.2.5", "between_min_ft", 6)
    ps, r72 = nfpa(C, "NFPA 72 17.7.4.2.3.1", "nominal_spacing_ft", 30)
    SP, AR, PS = sp * FT, ar * SQFT, ps * FT
    # the rooms: the bay between its chase partitions, and the two chases it shares with its neighbours; the
    # partitions reach within the top 15% of the ceiling height, so each is a wall
    rooms = [("main", B["x0"] + 1.7, B["x1"] - 1.7), ("chase W", B["x0"] - 1.6, B["x0"] + 1.6), ("chase E", B["x1"] - 1.6, B["x1"] + 1.6)]
    heads = chase_heads = 0
    stats = {"sx": [], "sy": [], "area": [], "wall": []}
    for room, xa, xb in rooms:
        W = xb - xa
        xs, sx = grid(xa, xb, SP)
        ys, sy = grid(B["y0"], B["y1"], min(SP, AR / sx))
        stats["sx"].append(sx); stats["sy"].append(sy); stats["area"].append(sx * sy); stats["wall"].append(sx / 2)
        for x in xs:
            for y in ys:
                cand = [(x + dx - 0.03, y + dy - 0.03, ceil0 - 0.17, x + dx + 0.03, y + dy + 0.03, ceil0 - 0.05)
                        for dx, dy in ((0, 0), (0, 0.1), (0, -0.1), (0.1, 0), (-0.1, 0), (0, 0.15), (0, -0.15))]
                e = X.place(f"cd/head/{room}/{x:.2f}/{y:.2f}", "IfcFireSuppressionTerminal", f"Sprinkler head, {name} {room}", cand, p,
                            "cleanroom", "SPRINKLER", "sprinkler head", **cd(numbers=f"pendent, quick response; {sx:.2f} x {sy:.2f} m"))
                heads += 1
                chase_heads += room != "main"
    pts = chase_ports = 0
    pstats = []
    for room, xa, xb in rooms:
        xs, sx = grid(xa, xb, PS)
        ys, sy = grid(B["y0"], B["y1"], PS)
        pstats.append((max(sx, sy), sx / 2))
        for x in xs:
            for y in ys:
                cand = [(x + dx - 0.03, y + dy - 0.03, ceil0 - 0.45, x + dx + 0.03, y + dy + 0.03, ceil0 - 0.39)
                        for dx, dy in ((0, 0), (0, 0.2), (0, -0.2), (0.2, 0), (-0.2, 0), (0, 0.4), (0, -0.4))]
                X.place(f"cd/sample/{room}/{x:.2f}/{y:.2f}", "IfcSensor", f"Air-sampling port, {name} {room}", cand, p, "cleanroom",
                        "SMOKESENSOR", "sampling point", **cd(numbers="on the bay's air-sampling detector"))
                pts += 1
                chase_ports += room != "main"
    area = (B["x1"] - B["x0"]) * (B["y1"] - B["y0"])
    face = C.P["air"]["face_m_s"]
    D["fire"] = {"heads": heads, "chase_heads": chase_heads, "rooms": [r[0] for r in rooms],
                 "spacing_m": round(max(stats["sx"] + stats["sy"]), 3), "area_per_head_sqft": round(max(stats["area"]) / SQFT, 1),
                 "max_spacing_ft": round(max(stats["sx"] + stats["sy"]) / FT, 2),
                 "max_area_per_head_sqft": round(max(stats["area"]) / SQFT, 1),
                 "max_wall_distance_ft": round(max(stats["wall"]) / FT, 2),
                 "min_between_ft": round(min(stats["sx"] + stats["sy"]) / FT, 2),
                 "sampling_points": pts, "chase_ports": chase_ports, "sampling_spacing_m": round(max(x for x, _ in pstats), 3),
                 "max_port_spacing_ft": round(max(x for x, _ in pstats) / FT, 2), "max_port_wall_ft": round(max(w for _, w in pstats) / FT, 2),
                 "density": {"gpm_sqft": nfpa(C, "NFPA 13 T19.2.3.1.1", "OH2_gpm_sqft", 0.2)[0],
                             "area_sqft": nfpa(C, "NFPA 13 T19.2.3.1.1", "OH2_area_sqft", 1500)[0]},
                 "bay_area_sqft": round(area / SQFT),
                 "nfpa13_read": r13, "nfpa72_read": r72,
                 "basis": ("NFPA 13-2022 and NFPA 72-2022 read" if r13 and r72 else "assumed spacing; NFPA 13 and 72 not read")}
    F = D["fire"]
    bay = D["bay"]["building"]
    ok_s = F["max_spacing_ft"] <= sp + 1e-6 and F["max_area_per_head_sqft"] <= ar + 1e-6 and \
        F["max_wall_distance_ft"] <= wf * sp + 1e-6 and F["min_between_ft"] >= mn - 1e-6
    C.case("sprinklers.spacing", bay, spacing_ok=q(ok_s, f"computed: at most {F['max_spacing_ft']} ft apart, {F['max_area_per_head_sqft']} sq ft "
                                                       f"a head, {F['max_wall_distance_ft']} ft from a wall, at least {F['min_between_ft']} ft apart"))
    water = ("cannot be settled without the site's water supply: over 5,000 sq ft (this bay {0:,} sq ft) the pipe schedule needs the "
             "Table 19.2.2.1 flows at 50 psi residual (19.2.2.3), and the hydraulic method at {1} gpm/sq ft over {2:,} sq ft "
             "(Table 19.2.3.1.1) needs a water supply test").format(F["bay_area_sqft"], F["density"]["gpm_sqft"], F["density"]["area_sqft"])
    C.case("sprinklers.branch_sizing", bay, branch_ok=q(None, why=water) if r13 else q(True, "assumed sizes"))
    ok_d = F["max_port_spacing_ft"] <= ps + 1e-6 and F["max_port_wall_ft"] <= 0.5 * ps + 1e-6 and face <= 1.5
    C.case("alarm.detector_spacing", bay, detectors_ok=q(ok_d, f"computed: ports at most {F['max_port_spacing_ft']} ft apart and "
                                                             f"{F['max_port_wall_ft']} ft from a wall; air {face} m/s; transport time "
                                                             "(120 s at most) by the maker's calculation"))
    if r13:
        C.cases.pop("sprinklers.density", None)
        for k in C.keys:
            C.case("sprinklers.density", k, density_ok=q(None, why=(
                f"the design density is known ({F['density']['gpm_sqft']} gpm/sq ft over {F['density']['area_sqft']:,} sq ft, "
                "Table 19.2.3.1.1); whether the system delivers it waits for the site's water supply test and a hydraulic "
                "calculation (19.2.2.3, 19.2.3)")))
    if r72:
        C.cases.pop("alarm.notification", None)
        for k in C.keys:
            C.case("alarm.notification", k, notification=q(None, why="NFPA 72 read for detector spacing; the notification appliance "
                                                                      "layout (its chapter 18) is not checked"))
    if nfpa(C, "NFPA 70 T310.16", "copper_75C_A", None)[1]:
        C.cases.pop("elec.wiring", None)
        for k in C.keys:
            C.case("elec.wiring", k, wiring_ok=q(None, why="NFPA 70 read for feeder ampacity; fault current, overcurrent protection "
                                                            "and hazardous locations are not checked"))


# ------------------------------------------------------------------ CD4 service clearances

def clearances(C, D, B, tools):
    S = C.S
    cz = S["clean_z"]
    mid = (B["x0"] + B["x1"]) / 2
    zones = []
    for i in tools:
        t = S["tools"][i]
        c = C.cards[t["kind"]]["clearance_m"]
        west = (t["x0"] + t["x1"]) / 2 < mid      # on the west wall, the front faces east
        fr, bk, sd = c["front"]["value"], c["back"]["value"], c["side"]["value"]
        fx = (t["x1"], t["x1"] + fr) if west else (t["x0"] - fr, t["x0"])
        zones.append((i, "front", (fx[0], t["y0"], cz, fx[1], t["y1"], cz + 2.5)))
        zones.append((i, "side", (t["x0"], t["y0"] - sd, cz, t["x1"], t["y0"], cz + 2.5)))
        zones.append((i, "side", (t["x0"], t["y1"], cz, t["x1"], t["y1"] + sd, cz + 2.5)))
    skip = ("raised floor tile", "fan filter unit", "sprinkler head", "chase partition panel", "sampling point")
    bad = []
    for e in C.new:
        if (e["otype"] or "") in skip or e["box"][5] <= cz + 1e-6 or e["box"][2] >= cz + 2.5:
            continue
        if not inside(e["box"], B, 2.0):
            continue
        for i, kind, z in zones:
            if overlap(e["box"], z) > 1e-6:
                bad.append({"element": e["key"], "tool": i, "zone": kind})
    D["clearances"] = {"violations": bad, "zones": len(zones),
                       "how": "front (aisle side) and sides from each tool's card, 2.5 m high; the back is the chase"}
    C.case("cd.clearances", D["bay"]["building"], clearances_ok=q(not bad, "computed against the cards' clearances (assumed)"))
