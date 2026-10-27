"""D4, architecture at schematic level (docs/PERMIT.md): construction type, fab areas, rooms, exits.

Nothing here moves a tool, a stocker or a rail. Exits are placed greedily until every point of the clean floor and the
support floor is within Table 1017.2's walk of an exit, the count meets Table 1006.3.3, the stairs carry the occupants
(1005.3.1) and two exits are a third of the diagonal apart (1007.1.1). Every size here is assumed unless it is a
limit read from the register.
"""

import math

import model as bmodel
from ctx import FT, IN, SQFT
from geom import Grid, overlap2
from rules import q

CORE_X, CORE_Y, CORE_TOP = 9.5, 3.4, 9.9      # spine stair core: plan and lid (assumed); the lid sits under the hoist vehicles
TOWER_Y, TOWER_TOP = 3.4, 13.5                # facade stair outside the long wall (assumed)
WALL_T = 0.2                                  # new partitions (assumed)
PASS_X0, PASS_X1, PASS_H = 2.0, 4.0, 3.0      # exit passageway beside the core's mid line, and its height (assumed)
ROOM_Y0, ROOM_H = 58.0, 3.0                   # HPM rooms on the support floor at the facade (assumed)
STORIES = 2                                   # support floor and clean floor; the waffle slab and the air space are not stories (assumed)
DOOR_W = 1.2                                  # exit door leaf (assumed), 47 in
ROOF_Y = (3.2, 66.5)                          # roof columns: inside the spine edge and in the perimeter strip (assumed)
GROSS = {"clean floor": ("IBC T1004.5", "H5_fab_sqft"), "support floor": ("IBC T1004.5", "mechanical_sqft")}
GAS = ("flammable gas", "pyrophoric gas", "toxic gas", "highly toxic gas", "oxidizing gas", "corrosive gas")
ORDER = ["VB", "VA", "IIIB", "IIIA", "IIB", "IIA", "IB", "IA"]


def cells(C, p):
    xs, _ = bmodel.grid_lines(C.S)
    b = C.blds[p]
    xs = [x for x in xs if b["x0"] - 1e-6 <= x <= b["x1"] + 1e-6]
    return [(xs[i], xs[i + 1], (xs[i] + xs[i + 1]) / 2) for i in range(len(xs) - 1)]


def rail_envelopes(S):
    """The hoist vehicles' path: each rail grown by half a vehicle's width, from the vehicle's bottom to the rail."""
    out = []
    half = S["vehicle"][0] / 2
    z0 = S["ride_z"] - S["vehicle"][2] / 2 - 0.1
    for a, c in S["rails"]:
        x0, x1, y0, y1 = min(a[0], c[0]), max(a[0], c[0]), min(a[1], c[1]), max(a[1], c[1])
        out.append((x0 - half, y0 - half, z0, x1 + half, y1 + half, a[2] + 0.1))
    return out


# ------------------------------------------------------------------ D4 a: construction, occupancy, fab areas

def construction(C):
    reg = C.reg["sections"]
    H, Ns, A = reg["IBC T504.3"]["facts"]["H5_ft"], reg["IBC T504.4"]["facts"]["H5_stories"], reg["IBC T506.2"]["facts"]["H5_SM_sqft"]
    ok = lambda lim, v: lim == "UL" or v <= lim
    top = C.S["floors"][-1]["z1"]
    out = {"by_building": {}}
    pick = 0
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        area = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) / SQFT
        h = top / FT
        t = next(t for t in ORDER if t in H and t in Ns and t in A and ok(H[t], h) and ok(Ns[t], STORIES) and ok(A[t], area))
        pick = max(pick, ORDER.index(t))
        out["by_building"][k] = {"height_ft": round(h, 2), "stories": STORIES, "story_area_sqft": round(area)}
    t = ORDER[pick]
    out["type"] = t
    out["ratings_h"] = C.fact("IBC T601", t)
    out["why"] = (f"The least combustible type is not needed: {t} is the first type, from the most combustible up, whose "
                  "height, stories and story area allow both buildings as H-5, sprinklered (Tables 504.3, 504.4, 506.2 SM).")
    for p, k in enumerate(C.keys):
        d = out["by_building"][k]
        d["height_limit_ft"], d["stories_limit"], d["area_limit_sqft"] = H[t], Ns[t], A[t]
        C.case("construction.height", k, height_ft=q(d["height_ft"]), height_limit_ft=q(H[t]))
        C.case("construction.stories", k, stories=q(STORIES, "assumed: the waffle slab and air space are not stories"),
               stories_limit=q(Ns[t]))
        C.case("construction.area", k, story_area_sqft=q(d["story_area_sqft"]), area_limit_sqft=q(A[t]))
        C.case("construction.ratings", k, ratings_ok=q(True, "design: every element rated as Table 601 asks"))
    C.P["construction"] = out
    C.made.add("construction")


def hpm(C, p, where=None, hazards=GAS, unit="cf"):
    """Hazardous material in building p from the cards: (value, lo, hi)."""
    v = lo = hi = 0.0
    for _, t in C.tools_in(p):
        for c in C.cards[t["kind"]]["chemistry"]:
            if c["hazard"] in hazards and c["unit"] == unit and (where is None or c["where"] in where):
                v += c["qty"]["value"]
                lo += c["qty"]["lo"]
                hi += c["qty"]["hi"]
    return v, lo, hi


def occupancy_and_fab_areas(C):
    MAQ = [("highly toxic gas", "cf", "IBC T307.1(2)", "highly_toxic_gas_cf"), ("toxic gas", "cf", "IBC T307.1(2)", "toxic_gas_cf"),
           ("corrosive gas", "cf", "IBC T307.1(2)", "corrosive_gas_cf"), ("corrosive liquid", "gal", "IBC T307.1(2)", "corrosive_liquid_gal"),
           ("flammable gas", "cf", "IBC T307.1(1)", "flammable_gas_cf"), ("pyrophoric gas", "cf", "IBC T307.1(1)", "pyrophoric_gas_cf")]
    occ, areas = {}, []
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        over = []
        rows = []
        for hz, unit, sec, fact in MAQ:
            v = hpm(C, p, hazards=(hz,), unit=unit)
            maq = C.fact(sec, fact)
            rows.append({"hazard": hz, "quantity": round(v[0], 1), "range": [round(v[1], 1), round(v[2], 1)], "unit": unit, "maq": maq})
            # robust: the low end of the range above four times the table's quantity (both footnote increases)
            if v[1] > 4 * maq:
                over.append(hz)
        occ[k] = {"group": "H-5", "materials": rows, "over_maq": over,
                  "why": "semiconductor fabrication with hazardous production materials above the maximum allowable quantities"}
        C.case("occupancy.h5", k, designed_h5=q(bool(over), "computed: " + (", ".join(over) or "nothing") +
                                                 " above four times the base MAQ even at the low end; designed as H-5"))
        area = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) / SQFT
        gas = hpm(C, p, where=("in tool",))
        liq = hpm(C, p, where=("in tool",), hazards=("flammable liquid IB",), unit="gal")
        a = {"id": f"{k}-FA1", "building": k, "area_sqft": round(area),
             "gas_cf": round(gas[0], 2), "gas_cf_range": [round(gas[1], 2), round(gas[2], 2)],
             "gas_limit_cf": round(max(C.fact("IBC T415.11.1.1", "gas_aggregate_cf_per_sqft") * area,
                                       C.fact("IBC T415.11.1.1", "gas_aggregate_floor_cf")), 1),
             "flammable_liquid_gal": round(liq[0], 2), "flammable_liquid_range": [round(liq[1], 2), round(liq[2], 2)],
             "flammable_liquid_limit_gal": round(C.fact("IBC T415.11.1.1", "flammable_liquid_comb_gal_per_sqft") * area, 1),
             "barrier_h": C.fact("IBC 415.11.1.2", "barrier_h"), "stories": ["support floor", "clean floor"],
             "lowest_story": 1, "why": "one fab area per building: its hazardous material is far inside the aggregates, "
                                      "so no split at a bay line is needed; the exterior walls are its fire barriers"}
        areas.append(a)
        C.case("fabarea.gas", a["id"], gas_cf=q(a["gas_cf"], "assumed", *a["gas_cf_range"]), gas_limit_cf=q(a["gas_limit_cf"]))
        C.case("fabarea.flammable_liquid", a["id"], flammable_liquid_gal=q(a["flammable_liquid_gal"], "assumed", *a["flammable_liquid_range"]),
               flammable_liquid_limit_gal=q(a["flammable_liquid_limit_gal"]))
        C.case("fabarea.barrier", a["id"], barrier_h=q(a["barrier_h"], "design"))
        C.case("fabarea.location", a["id"], lowest_story=q(1, "design: the support floor is the first story above grade"))
    C.P["occupancy"] = occ
    C.P["fab_areas"] = areas
    C.made.add("fab_areas")


# ------------------------------------------------------------------ D4 b: rooms and reservations

def lot_distance(C, x0, x1, side):
    lot = C.permit["site"]["lot"]
    lx0, lx1 = min(p[0] for p in lot), max(p[0] for p in lot)
    ly0, ly1 = min(p[1] for p in lot), max(p[1] for p in lot)
    yw = C.blds[0]["y1"] if side > 0 else C.blds[0]["y0"]
    return min((ly1 - yw) if side > 0 else (yw - ly0), x0 - lx0, lx1 - x1)


def roof_columns(C):
    """Roof columns at the mid grid lines, inside the spine edge and in the perimeter strip, nudged clear of the
    hoist vehicles' path (never moving a rail)."""
    env = rail_envelopes(C.S)
    fixed = [t for t in C.S["tools"]] + C.S["stockers"]
    # design development and later keep a tool's side clearance free (docs/CONSTRUCTION-DOCS.md, CD4)
    pad = 0.1
    if C.P.get("stage") in ("dd", "cd"):
        pad = max(c["clearance_m"]["side"]["value"] for c in C.cards.values()) + 0.05
    out = []
    for p, b in enumerate(C.blds):
        for i, (xa, xb, m) in enumerate(cells(C, p)):
            for side in (1, -1):
                for y in (ROOF_Y if pad <= 0.1 else (3.04, ROOF_Y[1])):
                    yc = side * y
                    for dx in (0, 1.0, -1.0, 2.0, -2.0, 3.0, -3.0) + ((4.0, -4.0, 5.0, -5.0) if pad > 0.1 else ()):
                        x = m + dx
                        box = (x - 0.3, yc - 0.3, 0.0, x + 0.3, yc + 0.3, C.fl["roof"]["z0"])
                        if any(overlap2(box, e, 0.05) for e in env) or any(
                                overlap2(box, (t["x0"], t["y0"], 0, t["x1"], t["y1"], 0), pad) for t in fixed):
                            continue
                        out.append({"id": f"{C.keys[p]}/rcol/{i}/{'N' if side > 0 else 'S'}{int(y)}", "p": p, "x": round(x, 3),
                                    "y": yc, "box": box, "moved_m": dx})
                        break
                    else:
                        raise SystemExit(f"no place for a roof column near x {m:.1f}, y {yc}")
    C.roof_cols = out


def rooms(C):
    """Gas rooms and a chemical dispense room at the facades of the support floor, gowning at the west end of the
    clean floor, the emergency control station in the office."""
    C.res = {}
    out = []
    plan = {0: [("gas room", 1, 0.25), ("gas room", 1, 0.7), ("gas room", -1, 0.4), ("gas room", -1, 0.8),
                ("chemical dispense", 1, 0.5)],
            1: [("gas room", 1, 0.6), ("gas room", -1, 0.4), ("chemical dispense", 1, 0.3)]}
    campus = [c for c in C.S["campus"] if c["kind"] not in ("fab",)]
    gas_by_p = {p: hpm(C, p, where=("gas room",)) for p in (0, 1)}
    liq_by_p = {p: hpm(C, p, where=("dispense room",), hazards=("flammable liquid IB", "corrosive liquid", "oxidizer liquid class 2"),
                       unit="gal") for p in (0, 1)}
    for p, b in enumerate(C.blds):
        cs = cells(C, p)
        k = C.keys[p]
        n_gas = sum(1 for r in plan[p] if r[0] == "gas room")
        for n, (kind, side, frac) in enumerate(plan[p]):
            i = min(max(1, round(frac * (len(cs) - 1))), len(cs) - 2)
            while True:
                xa, xb, m = cs[i]
                face = (xa + 0.5, side * 70 - 0.01, 0, m - 0.5, side * 70 + 0.01, ROOM_H)
                bad = (p, i, side) in C.res or any(overlap2(face, (c["x0"], c["y0"], 0, c["x1"], c["y1"], 0), 2.0)
                                                    and c.get("z0", 0) < ROOM_H for c in campus)
                if not bad:
                    break
                i += 1
            C.res[(p, i, side)] = {"room"}
            x0, x1 = xa + 0.5, m - 0.5
            y0, y1 = sorted((side * ROOM_Y0, side * (b["y1"] - 0.3)))
            area = (x1 - x0) * (y1 - y0) / SQFT
            rid = f"{k}-{'GR' if kind == 'gas room' else 'CD'}{n + 1}"
            big = C.fact("IBC 415.11.6.1", "large_sqft") if kind == "gas room" else C.fact("IBC 415.11.6.2", "large_over_sqft")
            need = 2 if (area >= big if kind == "gas room" else area > big) else 1
            r = {"id": rid, "kind": kind, "building": k, "storey": "support floor", "box": [round(v, 3) for v in (x0, y0, 0, x1, y1, ROOM_H)],
                 "area_sqft": round(area), "exterior_wall": True, "lot_distance_m": round(lot_distance(C, x0, x1, side), 2),
                 "rating_h": 2, "rating_needed_h": need, "in_fab_area": False, "side": side, "cell": i,
                 "exhaust_cfm_sqft": 2.0}
            if kind == "gas room":
                g = gas_by_p[p]
                r["hpm_gas_cf"] = round(g[0] / n_gas, 1)
            else:
                r["hpm_liquid_gal"] = round(liq_by_p[p][0], 1)
                r["exterior_door"] = area > C.fact("IBC 415.11.6.2", "exterior_door_over_sqft")
            out.append(r)
        for n, side in enumerate((1, -1)):
            x0, x1 = b["x0"] + 0.4, b["x0"] + 5.4
            y0, y1 = sorted((side * 10.0, side * 30.0))
            out.append({"id": f"{k}-GW{n + 1}", "kind": "gowning", "building": k, "storey": "cleanroom",
                        "box": [round(v, 3) for v in (x0, y0, C.S["clean_z"], x1, y1, C.S["clean_z"] + 3.0)],
                        "area_sqft": round((x1 - x0) * (y1 - y0) / SQFT), "exterior_wall": False, "rating_h": 0,
                        "in_fab_area": True, "side": side})
    off = [c for c in C.S["campus"] if c["kind"] == "office"][0]
    out.append({"id": "ECS", "kind": "emergency control", "building": "OFFICE", "storey": None,
                "box": [off["x0"] + 10, off["y0"] + 6, 0, off["x0"] + 22, off["y0"] + 16, 4.0],
                "area_sqft": round(12 * 10 / SQFT), "exterior_wall": True, "rating_h": 1, "in_fab_area": False})
    for p in (0, 1):
        cs = cells(C, p)
        for side in (1, -1):
            for i in (1, len(cs) - 2):
                while (p, i, side) in C.res:
                    i += 1 if i < len(cs) / 2 else -1
                C.res[(p, i, side)] = {"brace"}
    C.P["rooms"] = out
    for r in out:
        C.made.add("rooms:" + r["kind"])
        if r["kind"] in ("gas room", "chemical dispense"):
            ft = r["lot_distance_m"] / FT
            C.case("hpm.room_location", r["id"], lot_distance_ft=q(round(ft, 1), "computed from the hypothetical lot (assumed)"))
            C.case("hpm.exterior_wall", r["id"], exterior_wall=q(r["exterior_wall"], "design"))
            C.case("hpm.room_rating", r["id"], rating_h=q(r["rating_h"], "design"), rating_needed_h=q(r["rating_needed_h"]))
            C.case("hpm.room_exhaust", r["id"], exhaust_cfm_sqft=q(r["exhaust_cfm_sqft"], "design (assumed)"))
            if r["kind"] == "chemical dispense":
                C.case("hpm.liquid_exterior_door", r["id"], exterior_door_ok=q(r["exterior_door"] or r["area_sqft"] <= 500, "design"))
    C.case("alarm.ecs", "site", ecs_outside=q(True, "design: in the office, outside both fab areas"))


# ------------------------------------------------------------------ D4 c: exits

class Floor:
    def __init__(self, C, p, story):
        b = C.blds[p]
        self.p, self.story = p, story
        self.g = Grid(b["x0"] + 0.3, b["y0"] + 0.3, b["x1"] - 0.3, b["y1"] - 0.3)
        self.half = C.S["spine"] / 2
        self.depth = C.S["depth"]

    def lanes_and_circulation(self):
        g = self.g
        circ = []
        lane_cols = []
        for side in (1, -1):
            ys = [iy for iy in range(g.ny) if self.half + 0.3 < side * (g.y0 + (iy + 0.5) * g.step) < self.half + self.depth - 0.3]
            for ix in range(g.nx):
                if all(g.free[iy, ix] for iy in ys):
                    lane_cols.append((ix, ys))
        for i in range(g.nx * g.ny):
            x, y = g.centre(i)
            if abs(y) < self.half or abs(y) > self.half + self.depth:
                circ.append(i)
        for ix, ys in lane_cols:
            circ += [iy * g.nx + ix for iy in ys]
        return circ


def egress(C, stage):
    limit_ft = C.fact("IBC T1017.2", "H5_sprinklered_ft")
    limit_m = limit_ft * FT
    table = C.fact("IBC T1006.3.3", "exits")
    def need(occ):
        for upto, n in table:
            if upto is None or occ <= upto:
                return n
    out, exits = {}, []
    roof = getattr(C, "roof_cols", [])
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        out[k] = {}
        diag = math.hypot(b["x1"] - b["x0"], b["y1"] - b["y0"])
        loads = {}
        for story, (sec, fact) in GROSS.items():
            area = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) / SQFT
            loads[story] = math.ceil(area / C.fact(sec, fact))
        if stage == "concept":
            for story in GROSS:
                e = {"occupant_load": loads[story], "exits": 0, "exits_needed": need(loads[story]), "max_travel_m": None,
                     "diagonal_m": round(diag, 2), "max_separation_m": 0.0, "common_path_m": None}
                out[k][story] = e
                scope = f"{k} {story}"
                C.case("egress.travel", scope, max_travel_ft=q(1e9, "computed: no exit on the story"))
                C.case("egress.exit_count", scope, exits=q(0), exits_needed=q(e["exits_needed"]))
                C.case("egress.separation", scope, max_separation_m=q(0.0), separation_needed_m=q(round(diag / 3, 2)))
            continue
        ex = place_exits(C, p, loads, limit_m, need, diag)
        exits += ex["exits"]
        out[k] = ex["floors"]
    C.P["egress"] = out
    if stage != "concept":
        C.P["exits"] = exits
        C.made.update({"egress", "passageways"})


def place_exits(C, p, loads, limit_m, need, diag):
    S, b, k = C.S, C.blds[p], C.keys[p]
    cs = cells(C, p)
    stockers = [(s["x0"], s["y0"], s["x1"], s["y1"]) for s in S["stockers"] if bmodel.phase_of_x(S, s["x0"]) == p]
    my_rooms = [r for r in C.P["rooms"] if r["building"] == k]
    my_roof = [c for c in C.roof_cols if c["p"] == p]
    campus = [c for c in S["campus"] if c["kind"] != "fab"]

    # candidates
    cores, towers = [], []
    for i, (xa, xb, m) in enumerate(cs):
        x0, x1 = m - CORE_X / 2, m + CORE_X / 2
        if x0 >= b["x0"] + 0.6 and x1 <= b["x1"] - 0.6 and not any(x0 < s[2] + 1.0 and x1 > s[0] - 1.0 for s in stockers):
            cores.append(i)
        for side in (1, -1):
            box = (m - CORE_X / 2, min(side * 70, side * (70 + TOWER_Y)), 0, m + CORE_X / 2, max(side * 70, side * (70 + TOWER_Y)), TOWER_TOP)
            if not any(overlap2(box, (c["x0"], c["y0"], 0, c["x1"], c["y1"], 0), 0.5) and c.get("z0", 0) < TOWER_TOP for c in campus):
                towers.append((i, side))

    # the clean floor
    cf = Floor(C, p, "clean floor")
    g = cf.g
    for i, t in C.tools_in(p):
        g.block((t["x0"], t["y0"], 0, t["x1"], t["y1"], 0))
    for s in stockers:
        g.block((s[0], s[1], 0, s[2], s[3], 0))
    for c in my_roof:
        g.block(c["box"])
    for r in my_rooms:
        if r["storey"] == "cleanroom":
            g.block(r["box"])
    for (pp, i, side), use in C.res.items():
        if pp == p and "brace" in use:
            xa, xb, m = cs[i]
            g.block((xa + 0.4, side * 69.35 - 0.125, 0, xb - 0.4, side * 69.35 + 0.125, 0))
    g.prepare()
    seed = g.cell(b["x0"] + 3, 67.5)      # the perimeter strip: no core, room or tower ever stands there
    chosen = []    # ("core", i, side of its passageway) or ("tower", i, side)

    def door_cells(c):
        kind, i, side = c
        m = cs[i][2]
        if kind == "core":
            return [g.cell(m - 2.5, 1.95), g.cell(m - 2.5, -1.95)]
        return [g.cell(m, side * 69.45)]

    def point(c):
        kind, i, side = c
        m = cs[i][2]
        return (m, 0.0) if kind == "core" else (m, side * 70.0)

    def free_side(i):
        for side in (-1, 1) if i % 2 else (1, -1):
            u = C.res.get((p, i, side), set())
            if not u & {"tower", "passageway", "door"}:
                return side
        return None

    def can(c):
        kind, i, side = c
        if kind == "core":
            return i in cores and not any(x[0] == "core" and x[1] == i for x in chosen) and free_side(i) is not None
        return (i, side) in towers and not C.res.get((p, i, side))

    def take(c):
        kind, i, side = c
        if kind == "core":
            side = free_side(i)
            c = ("core", i, side)
            m = cs[i][2]
            g_block_core(g, m)
            C.res.setdefault((p, i, side), set()).add("passageway")
        else:
            C.res[(p, i, side)] = {"tower"}
        chosen.append(c)
        g.walk(door_cells(c))
        return c

    def all_candidates():
        out = [("core", i, 0) for i in cores] + [("tower", i, s) for i, s in towers]
        return [c for c in out if can(c)]

    reach = g.component(seed)
    for _ in range(80):
        while True:
            far, fi = g.farthest(reach) if chosen else (math.inf, seed)
            if far <= limit_m:
                break
            fx, fy = g.centre(fi)
            cand = all_candidates()
            if not cand:
                raise SystemExit(f"{k} clean floor: no exit left to place; {far:.1f} m from ({fx:.1f}, {fy:.1f}) with {len(chosen)} exits")
            c = min(cand, key=lambda c: math.hypot(point(c)[0] - fx, point(c)[1] - fy))
            take(c)
        # recheck on the grid with every core blocked
        g.prepare()
        for c in chosen:
            g.walk(door_cells(c))
        reach = g.component(seed)
        far, fi = g.farthest(reach)
        n = len(chosen)
        occ = loads["clean floor"]
        w_in = max(C.fact("IBC 1011.2", "min_in"), math.ceil(C.fact("IBC 1005.3.1", "in_per_occupant") * occ / max(n, 1)))
        sep = max((math.dist(point(a), point(c)) for a in chosen for c in chosen), default=0.0)
        if far > limit_m:
            continue
        if n < need(occ) or w_in > 55 or sep < diag / 3:
            cand = all_candidates()
            c = max(cand, key=lambda c: min(math.dist(point(c), point(x)) for x in chosen))
            take(c)
            continue
        break
    else:
        raise SystemExit(f"{k}: exits could not be placed")
    clean = {"g": g, "reach": reach, "far": far}
    C.grids[(k, "clean floor")] = (g, list(g.dist), reach)
    circ = cf.lanes_and_circulation()
    cp = g.walk(circ, [math.inf] * (g.nx * g.ny))
    common = max(d for d, r in zip(cp, reach) if r)
    stair_w_in = w_in
    exits = []
    for c in chosen:
        kind, i, side = c
        xa, xb, m = cs[i]
        eid = f"{k}-{'SC' if kind == 'core' else 'FS'}{i:02d}{'' if kind == 'core' else ('N' if side > 0 else 'S')}"
        exits.append({"id": eid, "kind": "spine stair" if kind == "core" else "facade stair", "building": k, "cell": i, "x": round(m, 3),
                      "side": side, "width_m": round(stair_w_in * IN, 4), "width_in": stair_w_in, "door_width_in": round(DOOR_W / IN, 1),
                      "serves": ["clean floor", "support floor"], "rating_h": 2})
        if kind == "core":
            exits.append({"id": f"{k}-XP{i:02d}{'N' if side > 0 else 'S'}", "kind": "exit passageway", "building": k, "cell": i,
                          "x": round(m + (PASS_X0 + PASS_X1) / 2, 3), "side": side, "width_m": round(PASS_X1 - PASS_X0 - 2 * WALL_T, 4),
                          "door_width_in": round(DOOR_W / IN, 1), "serves": ["support floor"], "rating_h": 1, "from": eid})
    floors = {"clean floor": {
        "occupant_load": loads["clean floor"], "area_sqft": round((b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) / SQFT),
        "exits": len(chosen), "exits_needed": need(loads["clean floor"]),
        "max_travel_m": round(far, 3), "limit_m": round(limit_m, 3), "diagonal_m": round(diag, 2),
        "max_separation_m": round(sep, 2), "common_path_m": round(common, 2),
        "stair_width_in": stair_w_in * len(chosen), "stair_width_each_in": stair_w_in,
        "door_width_in": round(len(chosen) * DOOR_W / IN, 1),
        "unreachable_cells": sum(1 for f, r in zip(g.flat, reach) if f and not r)}}

    # the support floor
    sf = Floor(C, p, "support floor")
    h = sf.g
    for e in C.M["elements"]:
        if e["cls"] == "IfcColumn" and e["bld"] == p:
            h.block(e["box"])
    for c in my_roof:
        h.block(c["box"])
    for r in my_rooms:
        if r["storey"] == "support floor":
            h.block(r["box"])
    for kind, i, side in chosen:
        m = cs[i][2]
        if kind == "core":
            g_block_core(h, m)
            y0, y1 = sorted((side * CORE_Y / 2, side * (b["y1"] - 0.3)))
            h.block((m + PASS_X0, y0, 0, m + PASS_X1, y1, 0), pad=0.05)
    h.prepare()
    srcs = []      # (exit id, [cells], point)
    for kind, i, side in chosen:
        m = cs[i][2]
        if kind == "core":
            cells_ = []
            for y in (10.0, 22.0, 34.0, 46.0, 58.0):
                for x in (m + PASS_X0 - 0.3, m + PASS_X1 + 0.3):
                    cells_.append(h.cell(x, side * y))
            srcs.append((f"{k}-XP{i:02d}{'N' if side > 0 else 'S'}", cells_, (m + 3.0, side * 34.0)))
        else:
            srcs.append((f"{k}-FS{i:02d}{'N' if side > 0 else 'S'}", [h.cell(m, side * 69.45)], (m, side * 70.0)))
    for _, cl, _ in srcs:
        h.walk(cl)
    seed2 = h.cell(b["x0"] + 3, 10.0)
    reach2 = h.component(seed2)
    doors = []     # exterior doors added for the support floor
    door_cands = []
    for i, (xa, xb, m) in enumerate(cs):
        for side in (1, -1):
            door_cands.append(("F", i, side, m + 1.1, side * 69.45))
    for side_x, x in (("W", b["x0"] + 0.55), ("E", b["x1"] - 0.55)):
        for y in (-58.0, -46.0, -34.0, -22.0, -10.0, 10.0, 22.0, 34.0, 46.0, 58.0):
            door_cands.append((side_x, 0, 0, x, y))
    used = set()

    def door_ok(d):
        kind, i, side, x, y = d
        if (kind, i, side, x, y) in used:
            return False
        if kind == "F":
            return not (C.res.get((p, i, side), set()) & {"tower", "passageway", "door"})
        return True

    occ2 = loads["support floor"]
    for _ in range(80):
        far2, fi = h.farthest(reach2)
        pts = [s[2] for s in srcs]
        n2 = len(srcs)
        sep2 = max((math.dist(a, c) for a in pts for c in pts), default=0.0)
        dw = n2 * DOOR_W / IN
        if far2 <= limit_m and n2 >= need(occ2) and sep2 >= diag / 3 and dw >= C.fact("IBC 1005.3.2", "in_per_occupant") * occ2:
            break
        fx, fy = h.centre(fi)
        cand = [d for d in door_cands if door_ok(d)]
        if far2 > limit_m:
            d = min(cand, key=lambda d: math.hypot(d[3] - fx, d[4] - fy))
        else:
            d = max(cand, key=lambda d: min(math.dist((d[3], d[4]), s) for s in pts))
        used.add(d)
        kind, i, side, x, y = d
        if kind == "F":
            C.res.setdefault((p, i, side), set()).add("door")
        did = f"{k}-ED{len(doors) + 1:02d}"
        doors.append({"id": did, "kind": "exterior door", "building": k, "x": round(x, 3), "y": round(y, 3),
                      "wall": kind, "cell": i, "side": side, "width_m": DOOR_W, "door_width_in": round(DOOR_W / IN, 1),
                      "serves": ["support floor"]})
        cl = [h.cell(x, y)]
        srcs.append((did, cl, (x if kind == "F" else (b["x0"] if kind == "W" else b["x1"]), y if kind != "F" else side * 70.0)))
        h.walk(cl)
    else:
        raise SystemExit(f"{k}: support floor exits could not be placed")
    C.grids[(k, "support floor")] = (h, list(h.dist), reach2)
    circ2 = sf.lanes_and_circulation()
    cp2 = h.walk(circ2, [math.inf] * (h.nx * h.ny))
    common2 = max(d for d, r in zip(cp2, reach2) if r)
    floors["support floor"] = {
        "occupant_load": occ2, "area_sqft": floors["clean floor"]["area_sqft"], "exits": len(srcs), "exits_needed": need(occ2),
        "max_travel_m": round(far2, 3), "limit_m": round(limit_m, 3), "diagonal_m": round(diag, 2),
        "max_separation_m": round(sep2, 2), "common_path_m": round(common2, 2),
        "door_width_in": round(len(srcs) * DOOR_W / IN, 1),
        "unreachable_cells": sum(1 for f, r in zip(h.flat, reach2) if f and not r)}
    for story, e in floors.items():
        scope = f"{k} {story}"
        C.case("egress.travel", scope, max_travel_ft=q(round(e["max_travel_m"] / FT, 1), "computed on a 0.5 m grid, 8 directions"))
        C.case("egress.exit_count", scope, exits=q(e["exits"]), exits_needed=q(e["exits_needed"]))
        C.case("egress.separation", scope, max_separation_m=q(e["max_separation_m"]), separation_needed_m=q(round(e["diagonal_m"] / 3, 2)))
        C.case("egress.common_path", scope, common_path_ft=q(round(e["common_path_m"] / FT, 1), "computed: walk to a corridor that leads two ways"))
        C.case("egress.door_capacity", scope, door_width_in=q(e["door_width_in"], "design"),
               door_width_needed_in=q(round(C.fact("IBC 1005.3.2", "in_per_occupant") * e["occupant_load"], 1)))
        C.case("egress.corridor_rating", scope, corridor_rating_h=q(1, "design"))
        C.case("structure.live_load", scope, design_live_psf=q(C.fact("IBC T1607.1", "manufacturing_heavy_psf"), "design"))
        C.case("egress.exit_discharge", scope, all_discharge=q(True, "design: each spine stair has an exit passageway to the facade"))
    c = floors["clean floor"]
    C.case("egress.stair_capacity", f"{k} clean floor", stair_width_in=q(c["stair_width_in"], "design"),
           stair_width_needed_in=q(round(C.fact("IBC 1005.3.1", "in_per_occupant") * c["occupant_load"], 1)))
    return {"exits": exits + doors, "floors": floors}


def g_block_core(g, m):
    g.block((m - CORE_X / 2, -CORE_Y / 2, 0, m + CORE_X / 2, CORE_Y / 2, 0), pad=0.05)


# ------------------------------------------------------------------ D4 d: the elements

def elements(C):
    S = C.S
    cz = S["clean_z"]
    for r in C.P["rooms"]:
        x0, y0, z0, x1, y1, z1 = r["box"]
        bi = C.keys.index(r["building"]) if r["building"] in C.keys else None
        storey = r["storey"]
        num = f"area {r['area_sqft']} sq ft; rating {r['rating_h']} h"
        C.add(f"room/{r['id']}", "IfcSpace", f"{r['kind'].capitalize()} {r['id']}", (x0, y0, z0, x1, y1, z1), bi, storey,
              "INTERNAL", r["kind"], numbers=num)
        if r["kind"] == "emergency control":
            continue
        t = WALL_T
        walls = [(x0, y0, z0, x0 + t, y1, z1), (x1 - t, y0, z0, x1, y1, z1)]
        inner_y = y0 if abs(y0) < abs(y1) else y1     # the wall facing the floor (the other is the facade or the strip)
        side = 1 if y0 > 0 else -1
        if r["kind"] == "gowning":
            walls += [(x0 + t, y0, z0, x1 - t, y0 + t, z1), (x0 + t, y1 - t, z0, x1 - t, y1, z1)]
            dx = x1 - t
            C.add(f"door/{r['id']}", "IfcDoor", f"Door, {r['id']}", (dx, (y0 + y1) / 2 - 0.6, z0, x1, (y0 + y1) / 2 + 0.6, z0 + 2.4),
                  bi, storey, "DOOR", numbers="1.2 m leaf", door=(2.4, 1.2, "SINGLE_SWING_RIGHT"))
        else:
            yi0 = inner_y if side > 0 else inner_y - t
            walls.append((x0 + t, yi0, z0, x1 - t, yi0 + t, z1))
            xm = (x0 + x1) / 2
            C.add(f"door/{r['id']}", "IfcDoor", f"Door, {r['id']}", (xm - 0.6, yi0, z0, xm + 0.6, yi0 + t, z0 + 2.4),
                  bi, storey, "DOOR", numbers="1.2 m leaf, rated", door=(2.4, 1.2, "SINGLE_SWING_LEFT"))
            if r.get("exterior_door"):
                yw = 70.0 * side
                C.add(f"door/{r['id']}/ext", "IfcDoor", f"Exterior door, {r['id']}",
                      (xm - 0.6, min(yw, yw - side * 0.3), z0, xm + 0.6, max(yw, yw - side * 0.3), z0 + 2.4),
                      bi, storey, "DOOR", numbers="1.2 m leaf", door=(2.4, 1.2, "SINGLE_SWING_LEFT"))
        for n, w in enumerate(walls):
            C.add(f"wall/{r['id']}/{n}", "IfcWall", f"Rated wall, {r['id']}", w, bi, storey, "SOLIDWALL",
                  numbers=f"fire barrier {r['rating_h']} h" if r["rating_h"] else "partition")
    cs = {p: cells(C, p) for p in (0, 1)}
    # construction documents (docs/BIM-FAITHFUL.md): a two-flight stair lands at its east end, so its doors move there
    landed = C.P.get("stage") == "cd"
    for x in C.P["exits"]:
        p = C.keys.index(x["building"])
        b = C.blds[p]
        if x["kind"] == "spine stair":
            m = x["x"]
            x0, x1, y0, y1 = m - CORE_X / 2, m + CORE_X / 2, -CORE_Y / 2, CORE_Y / 2
            t = WALL_T
            C.add(f"stair/{x['id']}", "IfcStair", f"Exit stair {x['id']}", (x0 + t, y0 + t, 0, x1 - t, y1 - t, CORE_TOP - t), p,
                  "support floor", "HALF_TURN_STAIR", numbers=f"two flights of {x['width_in']} in; enclosure 2 h", lod=200)
            for n, w in enumerate([(x0, y0, 0, x1, y0 + t, CORE_TOP), (x0, y1 - t, 0, x1, y1, CORE_TOP),
                                   (x0, y0 + t, 0, x0 + t, y1 - t, CORE_TOP), (x1 - t, y0 + t, 0, x1, y1 - t, CORE_TOP)]):
                C.add(f"wall/{x['id']}/{n}", "IfcWall", f"Stair enclosure {x['id']}", w, p, "support floor", "SOLIDWALL", numbers="2 h")
            C.add(f"lid/{x['id']}", "IfcSlab", f"Stair lid {x['id']}", (x0 + t, y0 + t, CORE_TOP - t, x1 - t, y1 - t, CORE_TOP), p,
                  "support floor", "ROOF", numbers=f"top {CORE_TOP} m, under the hoist vehicles")
            dx = 3.1 if landed else -2.5
            for s in (1, -1):
                yw = (y1 - t, y1) if s > 0 else (y0, y0 + t)
                C.add(f"door/{x['id']}/{'N' if s > 0 else 'S'}", "IfcDoor", f"Stair door {x['id']}",
                      (m + dx - DOOR_W / 2, yw[0], cz, m + dx + DOOR_W / 2, yw[1], cz + 2.1), p, "cleanroom", "DOOR",
                      numbers="1.2 m leaf, 90 min (assumed)", door=(2.1, DOOR_W, "SINGLE_SWING_LEFT"))
        elif x["kind"] == "exit passageway":
            m = x["x"] - (PASS_X0 + PASS_X1) / 2
            s = x["side"]
            y0, y1 = sorted((s * CORE_Y / 2, s * (b["y1"] - 0.3)))
            t = WALL_T
            C.add(f"space/{x['id']}", "IfcSpace", f"Exit passageway {x['id']}", (m + PASS_X0 + t, y0, 0, m + PASS_X1 - t, y1, PASS_H), p,
                  "support floor", "INTERNAL", "exit passageway", numbers=f"{x['width_m']} m clear, 1 h")
            C.add(f"wall/{x['id']}/W", "IfcWall", f"Exit passageway wall {x['id']}", (m + PASS_X0, y0, 0, m + PASS_X0 + t, y1, PASS_H), p,
                  "support floor", "SOLIDWALL", numbers="1 h")
            C.add(f"wall/{x['id']}/E", "IfcWall", f"Exit passageway wall {x['id']}", (m + PASS_X1 - t, y0, 0, m + PASS_X1, y1, PASS_H), p,
                  "support floor", "SOLIDWALL", numbers="1 h")
            yw = s * 70.0
            C.add(f"door/{x['id']}/ext", "IfcDoor", f"Exit discharge door {x['id']}",
                  (m + 3.0 - DOOR_W / 2, min(yw, yw - s * 0.3), 0, m + 3.0 + DOOR_W / 2, max(yw, yw - s * 0.3), 2.4), p,
                  "support floor", "DOOR", numbers="1.2 m leaf", door=(2.4, DOOR_W, "SINGLE_SWING_LEFT"))
            C.add(f"door/{x['id']}/core", "IfcDoor", f"Stair to passageway door {x['id']}",
                  (m + 3.0 - DOOR_W / 2, min(s * (CORE_Y / 2 - t), s * CORE_Y / 2), 0, m + 3.0 + DOOR_W / 2,
                   max(s * (CORE_Y / 2 - t), s * CORE_Y / 2), 2.4), p, "support floor", "DOOR", door=(2.4, DOOR_W, "SINGLE_SWING_LEFT"))
            for y in (10.0, 22.0, 34.0, 46.0, 58.0):
                for wx, nm in ((m + PASS_X0, "W"), (m + PASS_X1 - t, "E")):
                    C.add(f"door/{x['id']}/{nm}{int(y)}", "IfcDoor", f"Passageway door {x['id']}",
                          (wx, s * y - DOOR_W / 2, 0, wx + t, s * y + DOOR_W / 2, 2.4), p, "support floor", "DOOR",
                          numbers="1 h, self-closing", door=(2.4, DOOR_W, "SINGLE_SWING_LEFT"))
        elif x["kind"] == "facade stair":
            m, s = x["x"], x["side"]
            y0, y1 = sorted((s * 70.0, s * (70.0 + TOWER_Y)))
            x0, x1 = m - CORE_X / 2, m + CORE_X / 2
            t = WALL_T
            C.add(f"stair/{x['id']}", "IfcStair", f"Exit stair {x['id']}", (x0 + t, y0 + t, 0, x1 - t, y1 - t, TOWER_TOP - t), p,
                  "support floor", "HALF_TURN_STAIR", numbers=f"two flights of {x['width_in']} in; enclosure 2 h")
            for n, w in enumerate([(x0, y0, 0, x1, y0 + t, TOWER_TOP), (x0, y1 - t, 0, x1, y1, TOWER_TOP),
                                   (x0, y0 + t, 0, x0 + t, y1 - t, TOWER_TOP), (x1 - t, y0 + t, 0, x1, y1 - t, TOWER_TOP)]):
                C.add(f"wall/{x['id']}/{n}", "IfcWall", f"Stair enclosure {x['id']}", w, p, "support floor", "SOLIDWALL", numbers="2 h")
            C.add(f"lid/{x['id']}", "IfcSlab", f"Stair roof {x['id']}", (x0 + t, y0 + t, TOWER_TOP - t, x1 - t, y1 - t, TOWER_TOP), p,
                  "support floor", "ROOF")
            yw = (69.7, 70.0) if s > 0 else (-70.0, -69.7)
            # the landing end: east, unless the fab's facade ends before the clean floor door (then west, mirrored).
            # The support floor door keeps its place: at that level the facade-side lane runs free under the upper flight.
            def clear(c):
                return b["x0"] + 0.5 <= c - DOOR_W / 2 and c + DOOR_W / 2 <= b["x1"] - 0.5
            dx = (3.1 if clear(m + 3.1) else -3.1) if landed else 0.0
            for z, nm, st in ((cz, "clean", "cleanroom"), (0.0, "support", "support floor")):
                c = m + dx if nm == "clean" else m
                C.add(f"door/{x['id']}/{nm}", "IfcDoor", f"Stair door {x['id']}", (c - DOOR_W / 2, yw[0], z, c + DOOR_W / 2, yw[1], z + 2.1),
                      p, st, "DOOR", numbers="1.2 m leaf, 90 min (assumed)", door=(2.1, DOOR_W, "SINGLE_SWING_LEFT"))
            yo = (y1 - t, y1) if s > 0 else (y0, y0 + t)
            ox = m + dx - DOOR_W / 2 if landed else m + 2.0
            C.add(f"door/{x['id']}/out", "IfcDoor", f"Exit discharge door {x['id']}", (ox, yo[0], 0, ox + DOOR_W, yo[1], 2.4),
                  p, "support floor", "DOOR", door=(2.4, DOOR_W, "SINGLE_SWING_LEFT"))
        elif x["kind"] == "exterior door":
            if x["wall"] == "F":
                s = x["side"]
                yw = (69.7, 70.0) if s > 0 else (-70.0, -69.7)
                box = (x["x"] - DOOR_W / 2, yw[0], 0, x["x"] + DOOR_W / 2, yw[1], 2.4)
            else:
                xw = (b["x0"], b["x0"] + 0.3) if x["wall"] == "W" else (b["x1"] - 0.3, b["x1"])
                box = (xw[0], x["y"] - DOOR_W / 2, 0, xw[1], x["y"] + DOOR_W / 2, 2.4)
            C.add(f"door/{x['id']}", "IfcDoor", f"Exterior exit door {x['id']}", box, p, "support floor", "DOOR",
                  numbers="1.2 m leaf, panic hardware", door=(2.4, DOOR_W, "SINGLE_SWING_LEFT"))
    for e in C.P["exits"]:
        if e["kind"] in ("spine stair", "facade stair"):
            C.case("egress.stair_width", e["id"], width_in=q(e["width_in"], "design"))
            C.case("egress.stair_enclosure", e["id"], rating_h=q(e["rating_h"], "design"),
                   rating_needed_h=q(C.fact("IBC 1023.2", "rating_h_4_or_more_stories" if STORIES >= 4 else "rating_h_fewer")))
            C.case("structure.stair_load", e["id"], stair_live_psf=q(C.fact("IBC T1607.1", "stairs_psf"), "design"))
        if e["kind"] == "exit passageway":
            C.case("egress.passageway_width", e["id"], width_in=q(round(e["width_m"] / IN, 1), "design"))
            C.case("egress.passageway_rating", e["id"], rating_h=q(e["rating_h"], "design"))
    # the chases: are they service corridors? a judgement for the authority
    chase = 1.5
    for k in C.keys:
        C.case("service.corridor_width", k, chase_width_ft=q(round(chase / FT, 2)), chase_is_service_corridor=None)
        C.case("service.corridor_travel", k, chase_travel_ft=None, chase_is_service_corridor=None)
        C.case("service.corridor_ventilation", k, chase_ach=None, chase_is_service_corridor=None)
        C.case("access.route", k, accessible=None)
    C.P["chase"] = {"width_m": chase, "width_ft": round(chase / FT, 2), "service_corridor": None,
                    "question": "Are the 1.5 m chases behind the tools service corridors (415.11.3)? If so they need 5 ft; "
                                "D10 rescored a 1.6 m chase."}


def run(C, stage="full"):
    construction(C)
    occupancy_and_fab_areas(C)
    if stage == "concept":
        C.roof_cols = []
        egress(C, stage)
        return
    roof_columns(C)
    rooms(C)
    egress(C, stage)
    elements(C)
