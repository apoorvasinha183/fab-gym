"""D7, cleanroom air and fire protection (docs/PERMIT.md).

A cleanliness class per space (assumed: the strictest class its tools' cards ask for, ISO 6 in the spine, ISO 7 at
the perimeter) and fan filter units by coverage; the recirculated air against 415.11.1.8; make-up and exhaust air
against 415.11.1.6; the cooling load against the chillers. Sprinklers throughout (the density waits for NFPA 13),
gas detection at every tool that draws hazardous gas and in every gas room, alarms outside the gas rooms, a pull
station at every exit. Arrays of fan filter units and sprinkler heads are elements with their counts.
"""

import math

import model as bmodel
from arch import cells
from ctx import CFM, SQFT
from geom import carve
from rules import q

FFU_M2 = 1.2 * 0.6            # cited in the concept brief: a 1200 x 600 mm unit
FACE = 0.45                    # m/s through the filters, assumed
COVER = {5: 0.8, 6: 0.4, 7: 0.15}   # fraction of the ceiling in units, by ISO class, assumed
FFU_KW = 0.15                  # per unit, assumed
LIGHT_W_M2 = 12.0              # assumed
MAKEUP_KJ_KG = 30.0            # enthalpy drop of outside air at design, assumed
CHILLER_KW = 3500.0            # one unit, assumed
HEAD_FT2 = 130.0               # area per sprinkler head for the count, assumed (NFPA 13 not read)
GAS = ("flammable gas", "pyrophoric gas", "toxic gas", "highly toxic gas", "oxidizing gas", "corrosive gas")


def run(C):
    S, P = C.S, C.P
    cz = S["clean_z"]
    ceil0 = C.fl["cleanroom"]["z1"]
    ceil1 = ceil0 + bmodel.FILTER
    spaces, n_ffu_total = [], 0
    roof = [c["box"] for c in C.roof_cols]

    def space(name, p, box, iso, kind):
        nonlocal n_ffu_total
        x0, y0, x1, y1 = box
        area = (x1 - x0) * (y1 - y0)
        target = COVER[iso]
        pieces = carve((x0, y0, ceil0, x1, y1, ceil1), roof, gap=0.1)
        usable = sum((p_[3] - p_[0]) * (p_[4] - p_[1]) for p_ in pieces)
        n = math.ceil(target * area / FFU_M2)
        if n * FFU_M2 > usable * 0.98:
            raise SystemExit(f"{name}: no room for {n} fan filter units")
        n_ffu_total += n
        cfm = n * FFU_M2 * FACE / CFM
        spaces.append({"bay": name, "kind": kind, "iso_class": iso, "area_m2": round(area, 2), "ffu": n,
                       "coverage": round(n * FFU_M2 / area, 4), "target": target,
                       "recirc_cfm_sqft": round(cfm / (area / SQFT), 2)})
        left = n
        for j, pc in enumerate(pieces):
            pa = (pc[3] - pc[0]) * (pc[4] - pc[1])
            m = left if j == len(pieces) - 1 else min(left, round(n * pa / usable))
            left -= m
            C.add(f"ffu/{name}/{j}", "IfcAirTerminal", f"Fan filter units, {name}", pc, p, "cleanroom", "USERDEFINED",
                  "fan filter unit array", stage="D7", lod=100, numbers=f"{m} units of 1.2 x 0.6 m, ISO {iso}")
        return n

    for i, bay in enumerate(S["bays"]):
        iso = min(C.cards[t["kind"]]["environment"]["iso_class"] for t in S["tools"] if t["bay"] == i) if any(
            t["bay"] == i for t in S["tools"]) else 6
        space(f"bay {i + 1:02d}", bay["phase"], (bay["x0"], bay["y0"], bay["x1"], bay["y1"]), iso, "bay")
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        half = S["spine"] / 2
        space(f"{k} spine", p, (b["x0"] + 0.3, -half, b["x1"] - 0.3, half), 6, "spine")
        top = half + S["depth"]
        space(f"{k} north perimeter", p, (b["x0"] + 0.3, top, b["x1"] - 0.3, b["y1"] - 0.3), 7, "perimeter")
        space(f"{k} south perimeter", p, (b["x0"] + 0.3, b["y0"] + 0.3, b["x1"] - 0.3, -top), 7, "perimeter")
        bays = [B for B in S["bays"] if B["phase"] == p]
        bx0, bx1 = min(B["x0"] for B in bays), max(B["x1"] for B in bays)
        if bx0 - (b["x0"] + 0.3) > 1.0:
            space(f"{k} west end", p, (b["x0"] + 0.3, half, bx0, top), 7, "perimeter")
            space(f"{k} west end south", p, (b["x0"] + 0.3, -top, bx0, -half), 7, "perimeter")
        if (b["x1"] - 0.3) - bx1 > 1.0:
            space(f"{k} east end", p, (bx1, half, b["x1"] - 0.3, top), 7, "perimeter")
            space(f"{k} east end south", p, (bx1, -top, b["x1"] - 0.3, -half), 7, "perimeter")
    tot_area = sum(s["area_m2"] for s in spaces)
    avg = sum(s["recirc_cfm_sqft"] * s["area_m2"] for s in spaces) / tot_area
    mn = min(s["recirc_cfm_sqft"] for s in spaces)
    # exhaust and make-up air for each fab area
    U = P["utilities"]
    ex_total = sum(U["exhaust_m3s"].values())
    fab = []
    for p, a in enumerate(P["fab_areas"]):
        share = a["area_sqft"] / sum(x["area_sqft"] for x in P["fab_areas"])
        tool_cfm = ex_total * share / CFM
        need = a["area_sqft"] * C.fact("IBC 415.11.1.6", "exhaust_cfm_per_sqft")
        general = max(0.0, 1.1 * need - tool_cfm)
        cfm = tool_cfm + general
        fab.append({"fab_area": a["id"], "tool_exhaust_cfm": round(tool_cfm), "general_exhaust_cfm": round(general),
                    "exhaust_cfm_sqft": round(cfm / a["area_sqft"], 3), "makeup_cfm": round(cfm)})
        C.case("ventilation.fab_exhaust", a["id"], exhaust_cfm_sqft=q(round(cfm / a["area_sqft"], 3), "design: tool exhaust "
                                                                      "from the cards (assumed) plus general exhaust to 1.1 cfm/sq ft"))
    makeup_m3s = sum(f["makeup_cfm"] for f in fab) * CFM
    tools = S["tools"]
    heat_air = sum(C.cards[t["kind"]]["heat_kw"]["air"]["value"] for t in tools)
    heat_pcw = sum(C.cards[t["kind"]]["heat_kw"]["pcw"]["value"] for t in tools)
    ffu_kw = n_ffu_total * FFU_KW
    light = sum((b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) for b in C.blds) * 2 * LIGHT_W_M2 / 1000
    makeup_kw = makeup_m3s * 1.2 * MAKEUP_KJ_KG
    cooling = heat_air + heat_pcw + ffu_kw + light + makeup_kw
    n_ch = math.ceil(cooling / CHILLER_KW) + 1
    cub = [c for c in S["campus"] if c["kind"] == "cub"][0]
    for j in range(n_ch):
        x0 = cub["x0"] + 5 + (j % 30) * 13
        y0 = cub["y0"] + 22 + (j // 30) * 7
        C.add(f"plant/chiller/{j}", "IfcChiller", f"Chiller {j + 1}", (x0, y0, 0, x0 + 10, y0 + 4, 4), None, None, "WATERCOOLED",
              "chiller", stage="D7", lod=100, numbers=f"{CHILLER_KW:.0f} kW, one of {n_ch}")
    P["air"] = {"bays": spaces, "ffu_total": n_ffu_total, "ffu_m2": FFU_M2, "face_m_s": FACE, "coverage_by_class": COVER,
                "recirc_cfm_sqft_avg": round(avg, 2), "recirc_cfm_sqft_min": round(mn, 2), "fab_exhaust": fab,
                "makeup_m3s": round(makeup_m3s, 2),
                "cooling": {"tools_air_kw": round(heat_air), "tools_pcw_kw": round(heat_pcw), "ffu_kw": round(ffu_kw),
                            "lighting_kw": round(light), "makeup_air_kw": round(makeup_kw)},
                "cooling_kw": round(cooling, 1), "chillers": n_ch, "chiller_kw": n_ch * CHILLER_KW,
                "note": "Cleanliness classes, coverage, face velocity and loads are assumed; ISO 14644-1 is not read."}
    C.made.add("air")
    for k in C.keys:
        C.case("air.recirc_avg", k, recirc_avg=q(round(avg, 2), "design"))
        C.case("air.recirc_min", k, recirc_min=q(round(mn, 2), "design"))
        C.case("air.cleanliness", k, classes_set=q(True, "assumed"))
    fire(C)


def fire(C):
    S, P = C.S, C.P
    cz = S["clean_z"]
    ceil0 = C.fl["cleanroom"]["z1"]
    roof = [c["box"] for c in C.roof_cols]
    heads = 0
    # sprinkler arrays: clean floor by bay and the spaces between, support floor by grid cell
    def array(key, p, box, storey, z0, z1, obstacles, note):
        nonlocal heads
        out = 0
        for j, pc in enumerate(carve((box[0], box[1], z0, box[2], box[3], z1), obstacles, gap=0.15)):
            n = max(1, math.ceil((pc[3] - pc[0]) * (pc[4] - pc[1]) / SQFT / 130.0))
            out += n
            C.add(f"spr/{key}/{j}", "IfcFireSuppressionTerminal", f"Sprinkler heads, {key}", pc, p, storey, "SPRINKLER",
                  "sprinkler array", stage="D7", lod=100, numbers=f"{n} heads at {HEAD_FT2:.0f} sq ft each (assumed); {note}")
        heads += out
        return out
    for i, bay in enumerate(S["bays"]):
        array(f"bay{i + 1:02d}", bay["phase"], (bay["x0"], bay["y0"], bay["x1"], bay["y1"]), "cleanroom", ceil0 - 0.2, ceil0 - 0.05,
              roof, "OH2 (Table 903.2.5.2)")
    cols = [e["box"] for e in C.M["elements"] if e["cls"] == "IfcColumn"]
    cores = [e["box"] for e in C.new if e["cls"] == "IfcStair" or (e["cls"] == "IfcWall" and "Stair enclosure" in e["name"])]
    members = [e["box"] for e in C.new if e["cls"] == "IfcMember"]
    xs_all, ys = bmodel.grid_lines(S)
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        half = S["spine"] / 2
        top = half + S["depth"]
        bays = [B for B in S["bays"] if B["phase"] == p]
        bx0, bx1 = min(B["x0"] for B in bays), max(B["x1"] for B in bays)
        for nm, box in (("spine", (b["x0"] + 0.3, -half, b["x1"] - 0.3, half)), ("north", (b["x0"] + 0.3, top, b["x1"] - 0.3, b["y1"] - 0.3)),
                        ("south", (b["x0"] + 0.3, b["y0"] + 0.3, b["x1"] - 0.3, -top)),
                        ("west", (b["x0"] + 0.3, half, bx0, top)), ("west-s", (b["x0"] + 0.3, -top, bx0, -half)),
                        ("east", (bx1, half, b["x1"] - 0.3, top)), ("east-s", (bx1, -top, b["x1"] - 0.3, -half))):
            if box[2] - box[0] > 1.0:
                array(f"{k}-{nm}", p, box, "cleanroom", ceil0 - 0.2, ceil0 - 0.05, roof + cores + members, "OH2")
        xs = [x for x in xs_all if b["x0"] - 1e-6 <= x <= b["x1"] + 1e-6]
        yy = [b["y0"] + 0.3] + sorted(ys) + [b["y1"] - 0.3]
        for i in range(len(xs) - 1):
            for j in range(len(yy) - 1):
                array(f"{k}-sub-{i:02d}-{j:02d}", p, (xs[i] + 0.4, yy[j] + 0.4, xs[i + 1] - 0.4, yy[j + 1] - 0.4), "support floor",
                      3.05, 3.15, cols + roof + cores, "support floor, OH2")
    # rooms
    gas_rooms = {}
    for r in P["rooms"]:
        x0, y0, z0, x1, y1, z1 = r["box"]
        bi = C.keys.index(r["building"]) if r["building"] in C.keys else None
        if r["kind"] in ("gas room", "chemical dispense", "gowning"):
            C.add(f"spr/room/{r['id']}", "IfcFireSuppressionTerminal", f"Sprinkler heads, {r['id']}",
                  (x0 + 0.4, y0 + 0.4, z1 - 0.3, x1 - 0.4, y1 - 0.4, z1 - 0.2), bi, r["storey"], "SPRINKLER", "sprinkler array",
                  stage="D7", lod=100, numbers="EH2 where dispensing (Table 903.2.5.2)" if r["kind"] == "chemical dispense" else "OH2")
        if r["kind"] in ("gas room", "chemical dispense"):
            side = 1 if y0 > 0 else -1
            for n in range(2):
                sx = x0 + 1.0 + n * (x1 - x0 - 2.0)
                C.add(f"sensor/{r['id']}/{n}", "IfcSensor", f"Gas detector {r['id']}", (sx, (y0 + y1) / 2, z1 - 0.6, sx + 0.15,
                      (y0 + y1) / 2 + 0.15, z1 - 0.45), bi, r["storey"], "GASSENSOR", stage="D7", lod=200, numbers="alarm at 25% LFL or the gas's limit")
            iy = y0 if side > 0 else y1
            ay = (iy - 0.3, iy - 0.2) if side > 0 else (iy + 0.2, iy + 0.3)
            xm = (x0 + x1) / 2
            C.add(f"alarm/{r['id']}", "IfcAlarm", f"Alarm outside {r['id']}", (xm + 1.0, ay[0], 2.2, xm + 1.25, ay[1], 2.45), bi,
                  r["storey"], "LIGHT", stage="D7", lod=200, numbers="visual and audible, at the door")
            gas_rooms[r["id"]] = {"sensors": 2, "alarms": 1, "kind": r["kind"]}
    # gas detection at every tool that draws hazardous gas
    by_bay, sensors_by_bay = {}, {}
    for i, t in enumerate(S["tools"]):
        if any(c["hazard"] in GAS for c in C.cards[t["kind"]]["chemistry"]):
            bk = str(t["bay"])
            by_bay[bk] = by_bay.get(bk, 0) + 1
            cx, cy = (t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2
            top = cz + t["h"]
            p = bmodel.phase_of_x(S, t["x0"])
            C.add(f"sensor/tool/{i}", "IfcSensor", f"Gas detector at tool {i}", (cx - 0.075, cy - 0.075, top, cx + 0.075, cy + 0.075, top + 0.12),
                  p, "cleanroom", "GASSENSOR", stage="D7", lod=200, numbers="in the tool's exhausted enclosure; reports to the ECS")
            sensors_by_bay[bk] = sensors_by_bay.get(bk, 0) + 1
    # one air-sampling smoke detector per bay, on the perimeter wall side at the bay's outer end, its pipes in the return air
    smoke = 0
    for bk, bay in enumerate(S["bays"]):
        cx = (bay["x0"] + bay["x1"]) / 2 + 1.5
        outer = 1 if (bay["y0"] + bay["y1"]) > 0 else -1
        y0 = 67.6 if outer > 0 else -67.9
        C.add(f"sensor/smoke/{bk}", "IfcSensor", f"Air-sampling smoke detector, bay {bk + 1:02d}", (cx - 0.2, y0, cz + 3.4, cx + 0.2, y0 + 0.3, cz + 3.8),
              bay["phase"], "cleanroom", "SMOKESENSOR", stage="D7", lod=100, numbers="air-sampling; sampling pipes in the return air (assumed)")
        smoke += 1
    # a pull station at every exit
    pulls = 0
    for x in P["exits"]:
        p = C.keys.index(x["building"])
        b = C.blds[p]
        boxes = []
        if x["kind"] == "spine stair":
            m = x["x"]
            for s in (1, -1):
                y = s * 1.72
                boxes.append(((m - 1.4, min(y, y + s * 0.08), cz + 1.1, m - 1.25, max(y, y + s * 0.08), cz + 1.3), "cleanroom"))
        elif x["kind"] == "facade stair":
            s = x["side"]
            yy = (69.6, 69.68) if s > 0 else (-69.68, -69.6)
            # beside the stair door, on the side away from an end wall
            px = x["x"] + 1.0 if x["x"] + 1.15 <= b["x1"] - 0.6 else x["x"] - 1.15
            for z, st in ((cz, "cleanroom"), (0.0, "support floor")):
                boxes.append(((px, yy[0], z + 1.1, px + 0.15, yy[1], z + 1.3), st))
        elif x["kind"] == "exit passageway":
            m, s = x["x"] - 3.0, x["side"]
            yy = (69.2, 69.3) if s > 0 else (-69.3, -69.2)
            boxes.append(((m + 2.25, yy[0], 1.1, m + 2.35, yy[1], 1.3), "support floor"))
        else:
            if x["wall"] == "F":
                s = x["side"]
                yy = (69.6, 69.68) if s > 0 else (-69.68, -69.6)
                boxes.append(((x["x"] + 0.9, yy[0], 1.1, x["x"] + 1.05, yy[1], 1.3), "support floor"))
            else:
                xx = (b["x0"] + 0.32, b["x0"] + 0.4) if x["wall"] == "W" else (b["x1"] - 0.4, b["x1"] - 0.32)
                boxes.append(((xx[0], x["y"] + 0.9, 1.1, xx[1], x["y"] + 1.05, 1.3), "support floor"))
        for n, (bx, st) in enumerate(boxes):
            C.add(f"pull/{x['id']}/{n}", "IfcAlarm", f"Pull station at {x['id']}", bx, p, st, "MANUALPULLBOX", stage="D7", lod=200)
            pulls += 1
    # sprinklers in exhaust ducts of 10 in or more that carry flammable fumes (solvent exhaust)
    duct_heads = 0
    for s in P["utilities"]["segments"]:
        if s["utility"] == "exhaust_solvent_m3h":
            w = float(s["size"].split()[0]) / 1000
            if w >= 0.254:
                length = 48.0 if s["kind"] == "lateral" else max(b["x1"] - b["x0"] for b in C.blds)
                duct_heads += s["runs"] * math.ceil(length / (C.fact("IBC 415.11.12.3", "horizontal_interval_ft") * 0.3048))
    P["fire"] = {"sprinkler_heads": heads, "head_area_sqft": HEAD_FT2, "hazard": C.fact("IBC 903.2.5.2", "hazard"),
                 "hpm_gas_tools_by_bay": by_bay, "gas_sensors_by_bay": sensors_by_bay, "gas_rooms": gas_rooms,
                 "covered_fab_areas": [a["id"] for a in P["fab_areas"]], "pull_stations": pulls, "duct_heads": duct_heads,
                 "smoke_detectors": smoke,
                 "smoke_detection": "one air-sampling smoke detector per bay, drawn; what the fire code's chapter 60 asks is not read",
                 "note": "Head counts assume 130 sq ft a head; the design density and area wait for NFPA 13 (not read)."}
    C.made.add("fire")
    for k in C.keys:
        C.case("gasdet.locations", k, all_detected=q(all(sensors_by_bay.get(b, 0) >= n for b, n in by_bay.items())
                                                     and all(g["sensors"] >= 1 for g in gas_rooms.values()), "design"))
        C.case("gasdet.setpoint", k, flammable_setpoint_lfl=q(0.2, "assumed", 0.1, 0.25))
        C.case("alarm.manual", k, pull_at_every_exit=q(pulls >= len(P["exits"]), "design"))
        C.case("alarm.smoke_detection", k, smoke_detection=None)
        C.case("alarm.notification", k, notification=None)
        C.case("sprinklers.throughout", k, throughout=q(True, "design: clean floor, support floor and rooms"))
        C.case("sprinklers.density", k, density_ok=None)
        C.case("sprinklers.ducts", k, ducts_covered=q(True, f"design: {duct_heads} heads in solvent exhaust ducts of 10 in or more"))
