"""D5, preliminary structure (docs/PERMIT.md): loads, roof trusses, columns, footings, bracing, the waffle slab's
first frequency. Every member is preliminary and for licensed review; seismic and wind design wait for ASCE 7.

Loads go to the columns by tributary area: each support-floor column takes the floor between the mid lines to its
neighbours (to the wall at the edge), so the tributaries tile the floor and every kilonewton reaches one footing.
The roof is carried by trusses on the roof columns at the mid grid lines, apart from the waffle slab.
"""

import math

import model as bmodel
from ctx import FT
from rules import q

PSF = 0.04788          # kPa in one psf
DEAD = {"waffle slab": 13.2, "raised floor": 1.0, "services under the slab": 1.5}   # kPa, assumed
ROOF_DEAD = {"roof deck and finishes": 1.2, "filter ceiling hung from the trusses": 0.5, "trusses": 0.6}  # kPa, assumed
WAFFLE = {"E_gpa": 30.0, "nu": 0.2, "stiff_depth_m": 0.75, "mass_kg_m2": 1786.0, "target_hz": 15.0}   # assumed
TRUSS_DEPTH = 3.65     # assumed, about a seventeenth of the span


def tributary(lines, lo, hi):
    """For sorted grid lines inside [lo, hi], each line's strip: halfway to its neighbours, to the edge at the ends."""
    out = []
    for i, x in enumerate(lines):
        a = lo if i == 0 else (lines[i - 1] + x) / 2
        b = hi if i == len(lines) - 1 else (x + lines[i + 1]) / 2
        out.append((a, b))
    return out


def run(C):
    S, P = C.S, C.P
    live = C.fact("IBC T1607.1", "manufacturing_heavy_psf")
    roof_live = C.fact("IBC T1607.1", "roof_psf")
    floor_kpa = sum(DEAD.values()) + live * PSF
    roof_kpa = sum(ROOF_DEAD.values()) + roof_live * PSF
    soil = C.permit["design_data"]["soil_bearing_kpa"]["value"]
    columns, footings, bays = [], [], []
    total_expect = 0.0
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        area = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
        cols = [e for e in C.M["elements"] if e["cls"] == "IfcColumn" and e["bld"] == p]
        xs = sorted({round((e["box"][0] + e["box"][3]) / 2, 3) for e in cols})
        ys = sorted({round((e["box"][1] + e["box"][4]) / 2, 3) for e in cols})
        tx = dict(zip(xs, tributary(xs, b["x0"], b["x1"])))
        ty = dict(zip(ys, tributary(ys, b["y0"], b["y1"])))
        for e in cols:
            cx, cy = round((e["box"][0] + e["box"][3]) / 2, 3), round((e["box"][1] + e["box"][4]) / 2, 3)
            a = (tx[cx][1] - tx[cx][0]) * (ty[cy][1] - ty[cy][0])
            load = a * floor_kpa + 0.6 * 0.6 * 6.0 * 24.0
            columns.append({"id": e["key"], "p": p, "kind": "support floor", "x": cx, "y": cy, "trib_m2": round(a, 3), "load_kN": round(load, 2)})
        total_expect += area * floor_kpa + len(cols) * 0.6 * 0.6 * 6.0 * 24.0
        # roof: trusses at the roof columns' lines
        rc = [c for c in C.roof_cols if c["p"] == p]
        rxs = sorted({c["x"] for c in rc if c["y"] > 0})
        rx_n = dict(zip(rxs, tributary(rxs, b["x0"], b["x1"])))
        rxs_s = sorted({c["x"] for c in rc if c["y"] < 0})
        rx_s = dict(zip(rxs_s, tributary(rxs_s, b["x0"], b["x1"])))
        mid_y = (3.2 + 66.5) / 2
        bands = {3.2: (0.0, mid_y), 3.04: (0.0, mid_y), 66.5: (mid_y, b["y1"])}   # inner columns at 3.04 m from design development on
        h = C.fl["roof"]["z0"]
        for c in rc:
            ax = (rx_n if c["y"] > 0 else rx_s)[c["x"]]
            ay = bands[abs(c["y"])]
            a = (ax[1] - ax[0]) * (ay[1] - ay[0])
            load = a * roof_kpa + 0.6 * 0.6 * h * 24.0
            columns.append({"id": "permit/" + c["id"], "p": p, "kind": "roof", "x": c["x"], "y": c["y"], "trib_m2": round(a, 3),
                            "load_kN": round(load, 2), "moved_m": c["moved_m"]})
        total_expect += area * roof_kpa + len(rc) * 0.6 * 0.6 * h * 24.0
        # waffle slab frequency per grid panel (simply supported plate, the lower bound)
        E, nu, d, m = WAFFLE["E_gpa"] * 1e9, WAFFLE["nu"], WAFFLE["stiff_depth_m"], WAFFLE["mass_kg_m2"]
        D = E * d ** 3 / (12 * (1 - nu * nu))
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                ax, by = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
                f1 = math.pi / 2 * (1 / ax ** 2 + 1 / by ** 2) * math.sqrt(D / m)
                bays.append({"id": f"{k}-x{i:02d}-y{j:02d}", "a_m": round(ax, 3), "b_m": round(by, 3), "f1_hz": round(f1, 2),
                             "target_hz": WAFFLE["target_hz"], "basis": "assumed: simply supported plate, stiffness and mass assumed"})
        # elements: roof columns, trusses, spine beams, bracing
        top = C.fl["roof"]["z0"]
        filt = C.fl["cleanroom"]["z1"] + bmodel.FILTER
        load_of = {c["id"]: c["load_kN"] for c in columns}
        for c in rc:
            C.add(c["id"], "IfcColumn", f"Roof column {c['id']}", c["box"], p, "support floor", "COLUMN", stage="D5", lod=200,
                  review="preliminary, licensed review", numbers=f"steel, 0.6 m (assumed); load {round(load_of['permit/' + c['id']])} kN")
        for x in rxs:
            C.add(f"{k}/truss/N/{x}", "IfcBeam", f"Roof truss at x {x}", (x - 0.25, 3.5, filt, x + 0.25, 66.2, top), p, "air space",
                  "BEAM", "roof truss", stage="D5", lod=200, review="preliminary, licensed review",
                  numbers=f"span {66.5 - 3.2:.1f} m, depth {TRUSS_DEPTH} m (assumed)")
        for x in rxs_s:
            C.add(f"{k}/truss/S/{x}", "IfcBeam", f"Roof truss at x {x}", (x - 0.25, -66.2, filt, x + 0.25, -3.5, top), p, "air space",
                  "BEAM", "roof truss", stage="D5", lod=200, review="preliminary, licensed review",
                  numbers=f"span {66.5 - 3.2:.1f} m, depth {TRUSS_DEPTH} m (assumed)")
        ybeam = min(abs(c["y"]) for c in C.roof_cols) - 0.3   # to the inner roof columns' faces
        for x in sorted(set(rxs) & set(rxs_s)):
            C.add(f"{k}/spinebeam/{x}", "IfcBeam", f"Spine roof beam at x {x}", (x - 0.2, -ybeam, top - 0.8, x + 0.2, ybeam, top), p,
                  "air space", "BEAM", "roof beam", stage="D5", lod=200, review="preliminary, licensed review", numbers="span 6.4 m")
        for (pp, i, side), use in sorted(C.res.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
            if pp != p or "brace" not in use:
                continue
            from arch import cells
            xa, xb, _ = cells(C, p)[i]
            C.add(f"{k}/brace/{i}/{side}", "IfcMember", f"Facade bracing, bay {i}", (xa + 0.4, side * 69.35 - 0.125, C.S["clean_z"],
                  xb - 0.4, side * 69.35 + 0.125, C.fl["cleanroom"]["z1"]), p, "cleanroom", "BRACE", "cross bracing", stage="D5",
                  lod=100, review="preliminary, licensed review", numbers="steel X, sized after ASCE 7 (not read)")
    for c in columns:
        side = math.sqrt(c["load_kN"] / soil)
        footings.append({"id": "footing/" + c["id"], "column": c["id"], "load_kN": c["load_kN"], "side_m": round(side, 3),
                         "bearing_kpa": soil})
    # footing elements: pads whose plans overlap become one combined footing sized for their total load
    pos = {c["id"]: (c["x"], c["y"], c["p"]) for c in columns}
    for grp in combine(footings, pos, soil):
        if len(grp["members"]) == 1:
            f = grp["members"][0]
            x, y, bi = pos[f["column"]]
            s = f["side_m"] / 2
            C.add(f["id"].replace("permit/", ""), "IfcFooting", f"Footing under {f['column'].replace('permit/', '')}",
                  (x - s, y - s, -1.2, x + s, y + s, 0.0), bi, "support floor", "PAD_FOOTING", stage="D5", lod=100,
                  review="preliminary, licensed review", numbers=f"{f['load_kN']:.0f} kN on {f['bearing_kpa']} kPa soil (assumed)")
            continue
        x0, y0, x1, y1 = grp["box"]
        first = grp["members"][0]
        key = first["id"].replace("permit/", "").replace("footing/", "footing/combined/")
        load = sum(f["load_kN"] for f in grp["members"])
        for f in grp["members"]:
            f["combined"] = "permit/" + key
        C.add(key, "IfcFooting", f"Combined footing under {len(grp['members'])} columns", (x0, y0, -1.2, x1, y1, 0.0),
              pos[first["column"]][2], "support floor", "PAD_FOOTING", stage="D5", lod=100, review="preliminary, licensed review",
              numbers=f"{load:.0f} kN on {first['bearing_kpa']} kPa soil (assumed), columns too close for separate pads")
    total = sum(f["load_kN"] for f in footings)
    P["frame"] = {"columns": columns, "footings": footings, "bays": bays, "total_load_kN": round(total, 2),
                  "total_load_check_kN": round(total_expect, 2),
                  "live_load_psf": {"clean floor": live, "support floor": live, "stairs": C.fact("IBC T1607.1", "stairs_psf"),
                                    "roof": roof_live},
                  "dead_kpa": DEAD, "roof_dead_kpa": ROOF_DEAD, "floor_kpa": round(floor_kpa, 3), "roof_kpa": round(roof_kpa, 3),
                  "waffle": WAFFLE, "truss_depth_m": TRUSS_DEPTH,
                  "design_data": C.permit["design_data"],
                  "note": "Preliminary. Loads by tributary area; the slab's frequency as a simply supported plate. Seismic and "
                          "wind design wait for ASCE 7 and a real site."}
    C.made.add("frame")
    for k in C.keys:
        C.case("structure.seismic", k, seismic_ok=None)
        C.case("structure.wind", k, wind_ok=None)
        rc = C.permit["design_data"]["risk_category"]
        C.case("structure.risk_category", k, risk_category_settled=q(None, why="risk category III or IV turns on whether the "
                                                                              "toxic quantities threaten the public: a judgement (assumed 3, range 2 to 4)"))

def combine(footings, pos, soil):
    """Group pads whose plans overlap; a group becomes one rectangle covering its pads, grown across its long side
    until its area carries the group's load on the assumed soil. Repeats until no two groups overlap."""
    groups = []
    for f in footings:
        x, y, _ = pos[f["column"]]
        s = f["side_m"] / 2
        groups.append({"members": [f], "box": (x - s, y - s, x + s, y + s)})

    def hit(a, b):
        return min(a[2], b[2]) - max(a[0], b[0]) > 1e-6 and min(a[3], b[3]) - max(a[1], b[1]) > 1e-6

    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                if hit(a["box"], b["box"]):
                    m = a["members"] + b["members"]
                    x0, y0 = min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1])
                    x1, y1 = max(a["box"][2], b["box"][2]), max(a["box"][3], b["box"][3])
                    need = sum(f["load_kN"] for f in m) / soil
                    w, h = x1 - x0, y1 - y0
                    if w * h < need:
                        if w >= h:
                            g = (need / w - h) / 2
                            y0, y1 = y0 - g, y1 + g
                        else:
                            g = (need / h - w) / 2
                            x0, x1 = x0 - g, x1 + g
                    groups[i] = {"members": m, "box": tuple(round(v, 4) for v in (x0, y0, x1, y1))}
                    del groups[j]
                    changed = True
                    break
            if changed:
                break
    return groups
