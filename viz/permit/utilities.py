"""D6, utilities and the central plant (docs/PERMIT.md).

Demand by bay from the tool cards (every value assumed by kind, with a range); plant sized to the diversified
demand with one spare unit; mains along the sub-fab beside the spine (y 4.4 to 15.6 m each side, under the waffle
slab), a lateral for each utility under each row of tools, one drop to every tool. Pipes and ducts are sized by
velocity from a list of sizes; where the largest size is too small, runs go in parallel. Gas flows are taken at
standard volume, which overstates the velocity in a pressurised line (the safe side).
"""

import math

import model as bmodel
from arch import cells
from ctx import CFM
from geom import overlap

KIND = {  # utility: (class, unit to m3/s, main velocity limit, lateral velocity limit)
    "pcw_lpm": ("pipe", 1 / 60000, 2.5, 2.5), "upw_lpm": ("pipe", 1 / 60000, 2.5, 2.5),
    "cda_slpm": ("pipe", 1 / 60000, 20.0, 20.0), "n2_slpm": ("pipe", 1 / 60000, 20.0, 20.0),
    "pv_slpm": ("pipe", 1 / 60000, 20.0, 20.0),
    "exhaust_general_m3h": ("duct", 1 / 3600, 12.0, 10.0), "exhaust_acid_m3h": ("duct", 1 / 3600, 12.0, 10.0),
    "exhaust_solvent_m3h": ("duct", 1 / 3600, 12.0, 10.0), "exhaust_toxic_m3h": ("duct", 1 / 3600, 12.0, 10.0),
    "drain_acid_lpm": ("pipe", 1 / 60000, 1.5, 1.5), "drain_fluoride_lpm": ("pipe", 1 / 60000, 1.5, 1.5),
    "drain_solvent_lpm": ("pipe", 1 / 60000, 1.5, 1.5), "drain_slurry_lpm": ("pipe", 1 / 60000, 1.5, 1.5),
    "power_kva": ("tray", None, None, None),
}
ORDER = list(KIND)
PIPES_MM = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400, 450, 500, 600]
ROUND_M = [0.1, 0.125, 0.16, 0.2, 0.25, 0.315, 0.4, 0.5]
RECT_W = [0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.4, 2.8]
MAIN_RECT_H, LAT_RECT_H = 1.2, 0.5   # duct heights: mains 3.3 to 4.5 m, pipes from 4.6 m
DIVERSITY = {"power_kva": 0.6, "pcw_lpm": 0.8, "upw_lpm": 0.7, "cda_slpm": 0.6, "n2_slpm": 0.7, "pv_slpm": 0.7,
             "exhaust_general_m3h": 1.0, "exhaust_acid_m3h": 1.0, "exhaust_solvent_m3h": 1.0, "exhaust_toxic_m3h": 1.0,
             "drain_acid_lpm": 0.6, "drain_fluoride_lpm": 0.6, "drain_solvent_lpm": 0.6, "drain_slurry_lpm": 0.6}   # assumed
UNIT = {"power_kva": 5000, "pcw_lpm": 10000, "upw_lpm": 5000, "cda_slpm": 30000, "n2_slpm": 50000, "pv_slpm": 20000,
        "exhaust_general_m3h": 100000, "exhaust_acid_m3h": 100000, "exhaust_solvent_m3h": 50000, "exhaust_toxic_m3h": 50000,
        "drain_acid_lpm": 2000, "drain_fluoride_lpm": 2000, "drain_solvent_lpm": 1000, "drain_slurry_lpm": 2000}  # assumed plant units
PLANT_NAME = {"power_kva": "main transformers", "pcw_lpm": "process cooling water pumps", "upw_lpm": "ultrapure water trains",
              "cda_slpm": "air compressors", "n2_slpm": "nitrogen generators", "pv_slpm": "process vacuum pumps",
              "exhaust_general_m3h": "general exhaust fans", "exhaust_acid_m3h": "acid scrubbers and fans",
              "exhaust_solvent_m3h": "solvent abatement and fans", "exhaust_toxic_m3h": "toxic exhaust and fans",
              "drain_acid_lpm": "acid waste neutralisation", "drain_fluoride_lpm": "fluoride waste treatment",
              "drain_solvent_lpm": "solvent collection", "drain_slurry_lpm": "slurry treatment"}
FAN_PA, FAN_EFF = 1500.0, 0.65     # assumed exhaust pressure and fan efficiency
BAND = (4.4, 15.6)
LAT_Y = (15.8, 63.8)
LAT_Z0, LAT_Z1 = 4.0, 5.8
MAIN_Z0 = 3.3
PIPE_Z0 = 4.6
DROP = 0.4


def size(u, Q, vmax, rect_h):
    """Smallest size from the list that keeps the velocity within vmax; parallel runs when none does.
    Returns (label, width, height, runs, velocity)."""
    cls = KIND[u][0]
    if Q <= 0:
        return None
    for runs in range(1, 40):
        q = Q / runs
        if cls == "pipe":
            for d in PIPES_MM:
                a = math.pi * (d / 1000) ** 2 / 4
                if q / a <= vmax:
                    return f"DN{d}", d / 1000, d / 1000, runs, q / a
        else:
            for d in ROUND_M:
                if d > rect_h:
                    break
                a = math.pi * d * d / 4
                if q / a <= vmax:
                    return f"{round(d * 1000)} mm round", d, d, runs, q / a
            for w in RECT_W:
                a = w * rect_h
                if q / a <= vmax:
                    return f"{round(w * 1000)} x {round(rect_h * 1000)} mm", w, rect_h, runs, q / a
    raise SystemExit(f"cannot size {u} for {Q:.3f} m3/s")


def tray(kva):
    w = min(0.9, max(0.3, 0.15 * math.ceil(kva / 400)))
    return f"{round(w * 1000)} mm tray", w, 0.15


def rows_of(C, p):
    """Rows of tools: (bay, side of the aisle) -> tool indices, with the half bay they stand in."""
    S = C.S
    out = {}
    for i, t in C.tools_in(p):
        bay = S["bays"][t["bay"]]
        mid = (bay["x0"] + bay["x1"]) / 2
        half = 0 if (t["x0"] + t["x1"]) / 2 < mid else 1
        out.setdefault((t["bay"], half), []).append(i)
    return out


def run(C):
    S, P = C.S, C.P
    tools = S["tools"]
    val = lambda i, u: C.cards[tools[i]["kind"]]["utilities"][u]["value"]
    connections = {str(i): [u for u in ORDER if val(i, u) > 0] for i in range(len(tools))}
    demand = {}
    for u in ORDER:
        add = sum(f.get(u, 0.0) for f in getattr(C, "extra_flows", {}).values())
        tot = sum(val(i, u) for i in range(len(tools))) + add
        lo = sum(C.cards[t["kind"]]["utilities"][u]["lo"] for t in tools) + add
        hi = sum(C.cards[t["kind"]]["utilities"][u]["hi"] for t in tools) + add
        demand[u] = {"connected": round(tot, 1), "connected_range": [round(lo, 1), round(hi, 1)], "diversity": DIVERSITY[u],
                     "diversified": round(tot * DIVERSITY[u], 1), "basis": "assumed: tool cards by kind, diversity assumed"}
    plant = {}
    for u in ORDER:
        need = demand[u]["diversified"] * (1.3 if u == "power_kva" else 1.0)
        n = math.ceil(need / UNIT[u]) + 1
        plant[u] = {"name": PLANT_NAME[u], "unit": UNIT[u], "units": n, "spare_units": 1, "capacity": n * UNIT[u],
                    "note": "one spare unit (N+1, assumed)" + ("; transformers carry the tools x 1.3 for the building's own loads (assumed)" if u == "power_kva" else "")}
    segments, trays = [], []
    xs, ys = bmodel.grid_lines(S)
    cols = [e["box"] for e in C.M["elements"] if e["cls"] == "IfcColumn"]
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        rows = rows_of(C, p)
        # mains, each side of the spine
        for side in (1, -1):
            flows = {u: 0.0 for u in ORDER}
            for (bay, half), idx in rows.items():
                if (S["bays"][bay]["y0"] > 0) == (side > 0):
                    for i in idx:
                        for u in ORDER:
                            flows[u] += val(i, u)
            for u, f in getattr(C, "extra_flows", {}).get((k, side), {}).items():
                flows[u] += f
            cursor = {"duct": BAND[0], "pipe": BAND[0]}     # ducts on the lower level, pipes and trays above them
            for u in ORDER:
                lvl = "duct" if KIND[u][0] == "duct" else "pipe"
                y = cursor[lvl]
                z0 = MAIN_Z0 if lvl == "duct" else PIPE_Z0
                f = flows[u] * DIVERSITY[u]
                if f <= 0:
                    continue
                if KIND[u][0] == "tray":
                    w = min(1.2, max(0.3, 0.15 * math.ceil(f / 2000)))
                    runs = 1
                    lab, ww, hh = f"{round(w * 1000)} mm tray", w, 0.15
                    boxes = [(y, y + ww)]
                    y += ww + 0.15
                    trays.append({"id": f"{k}/{'N' if side > 0 else 'S'}/main/{u}", "kva": round(f), "size": lab})
                    cls = "IfcCableCarrierSegment"
                else:
                    Q = f * KIND[u][1]
                    lab, ww, hh, runs, v = size(u, Q, KIND[u][2], MAIN_RECT_H)
                    boxes = []
                    for r in range(runs):
                        boxes.append((y, y + ww))
                        y += ww + 0.15
                    segments.append({"id": f"{k}/{'N' if side > 0 else 'S'}/main/{u}", "utility": u, "kind": "main", "building": k,
                                     "flow_m3s": round(Q, 4), "size": lab, "runs": runs, "velocity": round(v, 3), "limit": KIND[u][2]})
                    cls = "IfcDuctSegment" if KIND[u][0] == "duct" else "IfcPipeSegment"
                cursor[lvl] = y
                if y > BAND[1] + 1e-9:
                    raise SystemExit(f"{k}: mains do not fit in the band beside the spine ({y:.2f} m)")
                for r, (ya, yb) in enumerate(boxes):
                    y0, y1 = sorted((side * ya, side * yb))
                    C.add(f"{k}/main/{'N' if side > 0 else 'S'}/{u}/{r}", cls, f"{u} main, {k} {'north' if side > 0 else 'south'}",
                          (b["x0"] + 0.6, y0, z0, b["x1"] - 0.6, y1, z0 + hh), p, "support floor",
                          "CABLETRAYSEGMENT" if cls == "IfcCableCarrierSegment" else "RIGIDSEGMENT", u, stage="D6", lod=200,
                          numbers=f"{lab}" + (f", run {r + 1} of {len(boxes)}" if len(boxes) > 1 else ""))
        # laterals under each row, and drops
        for (bay, half), idx in sorted(rows.items()):
            B = S["bays"][bay]
            side = 1 if B["y0"] > 0 else -1
            mid = (B["x0"] + B["x1"]) / 2
            xa, xb = (B["x0"] + 0.2, mid - 0.2) if half == 0 else (mid + 0.2, B["x1"] - 0.2)
            bad = [(x - 0.45, x + 0.45) for x in xs]
            x = xa
            y0, y1 = sorted((side * LAT_Y[0], side * LAT_Y[1]))
            placed = []
            for u in ORDER:
                f = sum(val(i, u) for i in idx) * DIVERSITY[u]
                if f <= 0:
                    continue
                if KIND[u][0] == "tray":
                    lab, ww, hh = tray(f)
                    cls, pre, runs, v = "IfcCableCarrierSegment", "CABLETRAYSEGMENT", 1, None
                else:
                    Q = f * KIND[u][1]
                    lab, ww, hh, runs, v = size(u, Q, KIND[u][3], LAT_RECT_H)
                    cls = "IfcDuctSegment" if KIND[u][0] == "duct" else "IfcPipeSegment"
                    pre = "RIGIDSEGMENT"
                    segments.append({"id": f"{k}/bay{bay}/{half}/{u}", "utility": u, "kind": "lateral", "building": k,
                                     "flow_m3s": round(Q, 5), "size": lab, "runs": runs, "velocity": round(v, 3), "limit": KIND[u][3]})
                for r in range(runs):
                    while any(x < hi and x + ww > lo for lo, hi in bad):
                        x = min(hi for lo, hi in bad if x < hi and x + ww > lo)
                    z0 = LAT_Z0 if (x + ww <= xb) else LAT_Z0
                    if x + ww > xb + 1e-9:
                        raise SystemExit(f"{k} bay {bay}: laterals do not fit under the row")
                    C.add(f"{k}/lat/{bay}/{half}/{u}/{r}", cls, f"{u} lateral, bay {bay + 1}", (x, y0, z0, x + ww, y1, z0 + hh), p,
                          "support floor", pre, u, stage="D6", lod=200, numbers=lab)
                    placed.append(u)
                    x += ww + 0.1
            for i in idx:
                t = tools[i]
                cx, cy = (t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2
                for dx, dy in ((0, 0), (0.8, 0), (-0.8, 0), (0, 0.8), (0, -0.8), (1.2, 0.8), (-1.2, -0.8)):
                    box = (cx + dx - DROP / 2, cy + dy - DROP / 2, LAT_Z1, cx + dx + DROP / 2, cy + dy + DROP / 2, S["clean_z"])
                    if all(overlap(box, c) <= 0 for c in cols) and t["x0"] <= box[0] and box[3] <= t["x1"] and t["y0"] <= box[1] and box[4] <= t["y1"]:
                        break
                else:
                    raise SystemExit(f"no place for the drop to tool {i}")
                C.add(f"drop/{i}", "IfcPipeSegment", f"Drop to tool {i}", box, p, "support floor", "RIGIDSEGMENT", "tool drop",
                      stage="D6", lod=200, numbers="; ".join(connections[str(i)]))
    # emergency loads (415.11.11): exhaust fans at half speed draw an eighth of full power (fan laws, assumed)
    ex = {u: demand[u]["diversified"] / 3600 for u in ORDER if u.startswith("exhaust")}
    fan = lambda q: q * FAN_PA / FAN_EFF / 1000
    rooms_cfm = sum(r["area_sqft"] * r.get("exhaust_cfm_sqft", 0) for r in P["rooms"] if r["kind"] in ("gas room", "chemical dispense"))
    rooms_kw = fan(rooms_cfm * CFM)
    sensors = sum(1 for t in tools if any(c["hazard"] in ("flammable gas", "pyrophoric gas", "toxic gas", "highly toxic gas",
                                                         "oxidizing gas", "corrosive gas") for c in C.cards[t["kind"]]["chemistry"]))
    loads = {
        "HPM exhaust ventilation": fan(ex["exhaust_acid_m3h"] + ex["exhaust_solvent_m3h"]) / 8,
        "gas cabinet ventilation": rooms_kw / 8 / 2,
        "exhausted enclosure ventilation": fan(ex["exhaust_toxic_m3h"]) / 8,
        "gas room ventilation": rooms_kw / 8 / 2,
        "gas detection": sensors * 0.02 + 10.0,
        "emergency alarm": 20.0,
        "fire alarm": 30.0,
        "sprinkler monitoring": 5.0,
    }
    for name in C.fact("IBC 415.11.11", "loads"):
        loads.setdefault(name, 5.0)
    em_kw = sum(loads.values())
    gen_unit = 2500
    n_gen = math.ceil(em_kw / gen_unit) + 1
    plant["emergency_kw"] = {"name": "emergency generators", "unit": gen_unit, "units": n_gen, "spare_units": 1,
                             "capacity": n_gen * gen_unit, "note": "exhaust fans at half speed (415.11.11); one spare (assumed)"}
    # plant elements in the central utility building
    cub = [c for c in S["campus"] if c["kind"] == "cub"][0]
    def row(name, cls, pre, n, w, d, h, y0):
        for j in range(n):
            x0 = cub["x0"] + 5 + j * (w + 3)
            C.add(f"plant/{name}/{j}", cls, f"{name.capitalize()} {j + 1}", (x0, y0, 0, x0 + w, y0 + d, h), None, None, pre, name,
                  stage="D6", lod=100, numbers=f"one of {n}")
    row("transformer", "IfcTransformer", "VOLTAGE", plant["power_kva"]["units"], 4, 3, 3, cub["y0"] + 4)
    row("generator", "IfcElectricGenerator", "ENGINEGENERATOR", n_gen, 12, 3, 4, cub["y0"] + 12)
    P["utilities"] = {"connections": connections, "demand": demand, "plant": plant, "segments": segments, "trays": trays,
                      "emergency_loads": [f"{k}: {v:.0f} kW" for k, v in loads.items()], "emergency_kw": round(em_kw, 1),
                      "generator_kw": n_gen * gen_unit, "fan_assumed": {"pressure_pa": FAN_PA, "efficiency": FAN_EFF},
                      "exhaust_m3s": {u: round(v, 2) for u, v in ex.items()}}
    C.made.add("utilities")
    gas_tools_ok = all(any(val(i, u) > 0 for u in ("exhaust_toxic_m3h", "exhaust_general_m3h", "exhaust_acid_m3h"))
                       for i, t in enumerate(tools) if any(c["hazard"].endswith("gas") for c in C.cards[t["kind"]]["chemistry"]))
    from rules import q
    for k in C.keys:
        C.case("ventilation.continuous_gas_exhaust", k, gas_tools_exhausted=q(gas_tools_ok, "computed from the cards"))
        C.case("power.emergency_loads", k, all_loads_backed=q(True, "design: every load of 415.11.11 on the generators"))
        C.case("power.generator_capacity", k, generator_kw=q(n_gen * gen_unit, "design"),
               emergency_kw=q(round(em_kw, 1), "assumed", round(em_kw * 0.6, 1), round(em_kw * 1.6, 1)))
