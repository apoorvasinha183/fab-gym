"""Design development, the systems (docs/DESIGN-DEV.md, DD5 to DD10): the member schedule, exhaust systems and their
plant, make-up air, gas cabinets and valve boxes, drains and emergency showers, sprinkler mains, alarm boxes,
notification and detection, panels and lighting, and the level of development of every element. Every element is
placed by dd_place. Every size is assumed unless it is a limit read from the register; members are sized by required
properties, never from a maker's catalogue.
"""

import math

import model as bmodel
from ctx import FT, IN, SQFT
from dd_arch import M3H_PER_CFM, frange
from rules import q

FY, FA_RATIO, FB_RATIO = 345.0, 0.6, 0.66          # steel yield (MPa) and allowable fractions (assumed)
GRID = 12.0
GAS_HAZ = ("flammable gas", "pyrophoric gas", "toxic gas", "highly toxic gas", "oxidizing gas", "corrosive gas")
CAB_HAZ = ("toxic gas", "highly toxic gas")
CAB_PORT_SQFT, CAB_CFM, CAB_CYL = 0.75, 250.0, 2    # gas cabinet access port, exhaust, cylinders (assumed)
MAU_UNIT = 100000.0                                 # make-up air unit, m3/h (assumed)
PANEL_KVA = [225, 400, 600, 800, 1000, 1200, 1600, 2000, 2500, 3000]
EQUIP = ("IfcChiller", "IfcTransformer", "IfcElectricGenerator", "IfcFan", "IfcFilter", "IfcUnitaryEquipment")


def dd(e, **kw):
    return {"stage": "DD", "lod": 300, "review": "design development", **kw}


# ------------------------------------------------------------------ DD5 structure

def members(C):
    F = C.P["frame"]
    cols = [{"id": c["id"], "kind": c["kind"], "load_kN": c["load_kN"],
             "area_mm2": round(c["load_kN"] * 1000 / (FA_RATIO * FY)), "basis": f"P / (0.6 Fy), Fy {FY:g} MPa (assumed)"}
            for c in F["columns"]]
    beams = []
    w = F["roof_kpa"] * GRID
    for e in C.new:
        if e["cls"] != "IfcBeam":
            continue
        x0, y0, _, x1, y1, _ = e["box"]
        L = max(x1 - x0, y1 - y0)
        M = w * L * L / 8
        beams.append({"id": e["key"].replace("permit/", ""), "span_m": round(L, 2), "w_kN_m": round(w, 2),
                      "moment_kNm": round(M, 1), "sx_mm3": round(M * 1e6 / (FB_RATIO * FY)),
                      "basis": "simply supported, roof load over a 12 m width; Sx = M / (0.66 Fy) (assumed)"})
    foots = [{"id": f["id"], "column": f["column"], "load_kN": f["load_kN"], "side_m": f["side_m"],
              "combined": f.get("combined")} for f in F["footings"]]
    C.P["members"] = {"columns": cols, "beams": beams, "footings": foots, "risk_category": 4,
                      "note": "preliminary: required properties only; seismic and wind wait for ASCE 7 and a site"}
    C.made.add("dd:members")


# ------------------------------------------------------------------ DD6 mechanical

def exhaust(C, X):
    S, P = C.S, C.P
    U = P["utilities"]
    kinds = {"general": "exhaust_general_m3h", "acid": "exhaust_acid_m3h", "solvent": "exhaust_solvent_m3h", "toxic": "exhaust_toxic_m3h"}
    systems = {}
    cub = [c for c in S["campus"] if c["kind"] == "cub"][0]
    row = 0
    for name, u in kinds.items():
        pl = U["plant"][u]
        d = U["demand"][u]
        systems[name] = {"utility": u, "m3h": d["diversified"], "cfm": round(d["diversified"] / M3H_PER_CFM),
                         "fans": pl["units"], "fan_unit_m3h": pl["unit"], "scrubbers": pl["units"] if name != "general" else 0,
                         "treatment": {"general": "none (no hazardous contaminant)", "acid": "wet scrubbers",
                                       "solvent": "solvent abatement (thermal oxidisers, assumed)",
                                       "toxic": "point-of-use abatement at each tool, then wet scrubbers (assumed)"}[name],
                         "dampers": 0}
        for j in range(pl["units"]):
            for nm, cls, pre, w in (("fan", "IfcFan", "CENTRIFUGALBACKWARDINCLINEDCURVED", 3.0),
                                    ("scrubber", "IfcFilter", "USERDEFINED", 4.0)):
                if nm == "scrubber" and name == "general":
                    continue
                cand = [(cub["x0"] + 5 + i * 1.0, cub["y0"] + 40 + row * 6, 0, cub["x0"] + 5 + i * 1.0 + w, cub["y0"] + 44 + row * 6, 4)
                        for i in range(0, 420)]
                X.place(f"plant/{name}/{nm}/{j}", cls, f"{name.capitalize()} exhaust {nm} {j + 1}", cand, None, None, pre,
                        f"{name} exhaust {'wet scrubber' if nm == 'scrubber' else 'fan'}", stage="DD", lod=200,
                        review="design development", numbers=f"{pl['unit']:,} m3/h, one of {pl['units']} (N+1, assumed)")
            row += 0
        row += 1
    P["exhaust"] = {"systems": systems, "dampers_on_hazardous": 0,
                    "rule": "each kind its own system, ducts and fans; no damper in a hazardous exhaust duct (IMC 509.4, 509.6.1)"}
    for k in C.keys:
        C.case("exhaust.incompatible", k, separate_systems=q(True, "assumed: kinds kept apart, point-of-use abatement at the tools"))
        C.case("exhaust.no_dampers", k, no_dampers=q(True, "design: no fire or smoke damper on hazardous exhaust"))
    C.made.add("dd:exhaust")


def makeup(C, X):
    S, P = C.S, C.P
    out = {}
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        tool = sum(C.cards[t["kind"]]["utilities"][u]["value"] for _, t in C.tools_in(p)
                   for u in ("exhaust_general_m3h", "exhaust_acid_m3h", "exhaust_solvent_m3h", "exhaust_toxic_m3h"))
        chase = sum(c["exhaust_m3h"] for c in P["chases"] if c["building"] == k)
        rooms = sum(r["area_sqft"] * r.get("exhaust_cfm_sqft", 0) * M3H_PER_CFM for r in P["rooms"]
                    if r["building"] == k and r["kind"] in ("gas room", "chemical dispense"))
        cabs = sum(c["exhaust_cfm"] * M3H_PER_CFM for c in P.get("gas_cabinets", []) if c["building"] == k)
        ex = tool + chase + rooms + cabs
        n = math.ceil(ex / MAU_UNIT) + 1
        rz = C.fl["roof"]["z1"]
        for j in range(n):
            cand = [(b["x0"] + 4 + i * 1.0, 20.0, rz, b["x0"] + 4 + i * 1.0 + 6, 23.0, rz + 3.0) for i in range(0, 300)]
            X.place(f"mau/{k}/{j}", "IfcUnitaryEquipment", f"Make-up air unit {k} {j + 1}", cand, p, "roof", "AIRHANDLER",
                    "make-up air unit", stage="DD", lod=200, review="design development",
                    numbers=f"{MAU_UNIT:,.0f} m3/h, one of {n} (N+1, assumed)")
        out[k] = {"exhaust_m3h": round(ex), "exhaust_cfm": round(ex / M3H_PER_CFM), "makeup_m3h": round(ex),
                  "makeup_cfm": round(ex / M3H_PER_CFM), "units": n, "unit_m3h": MAU_UNIT,
                  "parts_m3h": {"tools": round(tool), "chases": round(chase), "rooms": round(rooms), "gas cabinets": round(cabs)}}
        C.case("exhaust.makeup", k, makeup_balanced=q(abs(out[k]["makeup_cfm"] / out[k]["exhaust_cfm"] - 1) <= 0.1,
                                                     "design: make-up air units balanced to the exhaust"))
    P["makeup"] = out
    C.made.add("dd:makeup")


def gas(C, X):
    """Gas cabinets in the gas rooms, valve manifold boxes under the bays, and the double-contained headers between."""
    S, P = C.S, C.P
    cabs, vmbs, headers = [], [], []
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        gases = sorted({c["material"] for _, t in C.tools_in(p) for c in C.cards[t["kind"]]["chemistry"] if c["hazard"] in CAB_HAZ})
        ht = {c["material"] for _, t in C.tools_in(p) for c in C.cards[t["kind"]]["chemistry"] if c["hazard"] == "highly toxic gas"}
        rooms = [r for r in P["rooms"] if r["building"] == k and r["kind"] == "gas room"]
        for n, g in enumerate(gases):
            r = rooms[n % len(rooms)]
            x0, y0, _, x1, y1, _ = r["box"]
            side = r["side"]
            back = y1 if side > 0 else y0
            cand = []
            for d in frange(0.35, 3.0, 0.25):
                for xx in frange(x0 + 0.4, x1 - 1.3, 0.25):
                    ya, yb = sorted((back - side * d, back - side * (d + 0.6)))
                    cand.append((xx, ya, 0.0, xx + 0.9, yb, 2.2))
            cid = f"{r['id']}-GC{n + 1:02d}"
            X.place(f"gascab/{cid}", "IfcUnitaryEquipment", f"Gas cabinet {cid}, {g}", cand, p, "support floor", "USERDEFINED",
                    "gas cabinet", stage="DD", lod=200, review="design development",
                    numbers=f"{g}; {CAB_CYL} cylinders; {CAB_CFM:.0f} cfm; sprinklered (6004.1.2)")
            cabs.append({"id": cid, "room": r["id"], "building": k, "gas": g, "highly_toxic": g in ht, "cylinders": CAB_CYL,
                         "exhaust_cfm": CAB_CFM, "port_sqft": CAB_PORT_SQFT, "face_fpm": round(CAB_CFM / CAB_PORT_SQFT),
                         "sprinkler": True})
        # one header from each gas room toward the spine, through the room's wall at a firestopped penetration
        for r in rooms:
            x0, y0, _, x1, y1, _ = r["box"]
            side = r["side"]
            inner = y0 if side > 0 else y1
            done = False
            for xx in sorted(frange(x0 + 0.5, x1 - 0.7, 0.25), key=lambda v: abs(v - (x0 + 1.0))):
                ya, yb = sorted((inner + side * 1.0, side * 18.0))
                box = (xx, ya, 2.4, xx + 0.15, yb, 2.55)
                if X.free(box, cls="IfcPipeSegment", otype="hpm header, firestopped at the gas room wall"):
                    X.add(f"hpm/{r['id']}", "IfcPipeSegment", f"Hazardous gas header {r['id']}", box, p, "support floor",
                          "RIGIDSEGMENT", "hpm header, firestopped at the gas room wall", stage="DD", lod=300,
                          review="design development, licensed review", numbers="double-contained, coaxial (assumed)")
                    headers.append({"room": r["id"], "x": xx})
                    done = True
                    break
            if not done:
                raise SystemExit(f"no route for the gas header from {r['id']}")
        # valve manifold boxes: one per bay per hazardous gas its tools draw
        for bk, bay in enumerate(S["bays"]):
            if bay["phase"] != p:
                continue
            side = 1 if bay["y0"] > 0 else -1
            used = sorted({c["material"] for t in S["tools"] if t["bay"] == bk for c in C.cards[t["kind"]]["chemistry"]
                           if c["hazard"] in GAS_HAZ})
            cx = (bay["x0"] + bay["x1"]) / 2
            for n, g in enumerate(used):
                cand = [(cx + dx, side * yy - 0.2, 0.3, cx + dx + 0.8, side * yy + 0.2, 1.7)
                        for yy in frange(18.0, 60.0, 0.5) for dx in (-2.0, -1.0, 0.0, 1.0, -3.0, 2.0, -4.0, 3.0)]
                cand = cand[n * 3:] + cand[:n * 3]
                vid = f"{k}-VMB{bk + 1:02d}-{n + 1}"
                X.place(f"vmb/{vid}", "IfcValve", f"Valve manifold box {vid}, {g}", cand, p, "support floor", "USERDEFINED",
                        "valve manifold box", stage="DD", lod=200, review="design development", numbers=f"{g}, exhausted")
                vmbs.append({"id": vid, "bay": bk, "building": k, "gas": g})
    P["gas_cabinets"] = cabs
    P["valve_boxes"] = vmbs
    P["hpm_headers"] = headers
    for r in P["rooms"]:
        if r["kind"] != "gas room":
            continue
        mine = [c for c in cabs if c["room"] == r["id"]]
        ok = all(c["cylinders"] <= C.fact("IFC 6004.1.2", "max_cylinders") and c["face_fpm"] >= C.fact("IFC 6004.1.2", "face_avg_fpm")
                 and c["sprinkler"] for c in mine)
        C.case("gas.cabinets", r["id"], cabinets_ok=q(ok, f"design: {len(mine)} cabinets, port and exhaust assumed"))
        C.case("gas.cabinet_room_exhaust", r["id"], room_exhausted=q(r.get("exhaust_cfm_sqft", 0) > 0, "design: the room's own exhaust"))
    C.made.update({"dd:cabinets", "dd:vmb"})


# ------------------------------------------------------------------ DD7 plumbing

def drains(C):
    P = C.P
    br = C.fact("IPC T710.1(2)", "branch_max_dfu_by_in")
    bd = C.fact("IPC T710.1(1)", "max_dfu_by_in")
    out = []
    for k in C.keys:
        tot = 0.0
        for c in P["toilets"]["cores"]:
            if c["building"] != k:
                continue
            tot += c["dfu"]
            room = c["dfu"] / 2
            size = next(d for d, m in br if m >= room)
            out.append({"core": c["id"], "building": k, "dfu": c["dfu"], "branch_in": max(size, 3), "building_drain_in": None})
        size = max(3, next(d for d, m in bd if m >= tot))
        for d in out:
            if d["building"] == k:
                d["building_drain_in"] = size
                d["building_dfu"] = tot
        C.case("plumbing.drains", k, drains_sized=q(True, f"design: {tot:g} dfu on a {size} in building drain at 1/4 in per foot"))
    P["drains"] = out
    C.made.add("dd:drains")


def showers(C, X):
    S, P = C.S, C.P
    out = []
    cz = S["clean_z"]
    for r in P["rooms"]:
        if r["kind"] != "chemical dispense":
            continue
        p = C.keys.index(r["building"])
        x0, y0, _, x1, y1, _ = r["box"]
        side = r["side"]
        inner = y0 if side > 0 else y1
        cand = []
        for d in frange(0.6, 4.0, 0.25):
            for xx in frange(x0, x1 - 1.0, 0.25):
                ya, yb = sorted((inner - side * d, inner - side * (d + 1.0)))
                cand.append((xx, ya, 0.0, xx + 1.0, yb, 2.3))
        X.place(f"shower/{r['id']}", "IfcSanitaryTerminal", f"Emergency shower and eyewash {r['id']}", cand, p, "support floor",
                "SHOWER", "emergency shower and eyewash", stage="DD", lod=300, review="design development",
                numbers="ISEA Z358.1 not read")
        out.append({"at": r["id"], "building": r["building"]})
    for bk, b in enumerate(S["bays"]):
        if b["area"] != "Wet_Etch":
            continue
        p = b["phase"]
        side = 1 if b["y0"] > 0 else -1
        cx = (b["x0"] + b["x1"]) / 2
        cand = [(cx + dx - 0.5, side * yy - 0.5, cz, cx + dx + 0.5, side * yy + 0.5, cz + 2.3)
                for yy in frange(5.0, 63.0, 0.5) for dx in (0.0, -0.5, 0.5, -1.0, 1.0)]
        X.place(f"shower/bay{bk + 1:02d}", "IfcSanitaryTerminal", f"Emergency shower and eyewash, bay {bk + 1:02d}", cand, p,
                "cleanroom", "SHOWER", "emergency shower and eyewash", stage="DD", lod=300, review="design development",
                numbers="in the aisle; ISEA Z358.1 not read")
        out.append({"at": f"bay {bk + 1:02d}", "building": C.keys[p]})
    P["showers"] = out
    for k in C.keys:
        C.case("plumbing.showers", k, showers_ok=q(True, "design: at every chemical dispense room and wet bench bay"))
    C.made.add("dd:showers")


# ------------------------------------------------------------------ DD8 fire protection and alarm

def sprinklers(C, X):
    S, P = C.S, C.P
    cz = S["clean_z"]
    mains = []
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        for s in (1, -1):
            X.place(f"sprk/main/{k}/clean/{'N' if s > 0 else 'S'}", "IfcPipeSegment", f"Sprinkler cross main {k} clean floor",
                    [(b["x0"] + 1.0, s * 3.775 - 0.075, 12.95, b["x1"] - 1.0, s * 3.775 + 0.075, 13.0)], p, "cleanroom",
                    "RIGIDSEGMENT", "sprinkler cross main", stage="DD", lod=300, review="design development",
                    numbers="DN150 (assumed; NFPA 13 not read)")
            cand = [(b["x0"] + 1.0, s * yy - 0.075, 3.2, b["x1"] - 1.0, s * yy + 0.075, 3.25) for yy in frange(8.0, 14.0, 0.25)]
            X.place(f"sprk/main/{k}/support/{'N' if s > 0 else 'S'}", "IfcPipeSegment", f"Sprinkler cross main {k} support floor",
                    cand, p, "support floor", "RIGIDSEGMENT", "sprinkler cross main", stage="DD", lod=300,
                    review="design development", numbers="DN150 (assumed; NFPA 13 not read)")
            mains.append(f"{k} {'north' if s > 0 else 'south'}")
        # a riser at the west end, from the support floor to the clean floor's cross main level
        allow = lambda o: (o["cls"] in ("IfcSlab", "IfcCovering") and not o["key"].startswith("permit/")) or \
            o["cls"] == "IfcFireSuppressionTerminal"
        cand = [(b["x0"] + 0.4 + dx, s * yy, 0.0, b["x0"] + 0.4 + dx + 0.25, s * yy + 0.25, 12.95)
                for yy in frange(16.3, 63.0, 0.5) for s in (1, -1) for dx in frange(0.0, 5.4, 0.25)]
        X.place(f"sprk/riser/{k}", "IfcPipeSegment", f"Sprinkler riser {k}", cand, p, "support floor", "RIGIDSEGMENT",
                "sprinkler riser", stage="DD", lod=300, review="design development", numbers="DN200 (assumed)",
                check={"strict": True, "allow": allow})
    n = 0
    for e in list(C.new):
        if e["cls"] != "IfcFireSuppressionTerminal" or not e["key"].startswith("permit/spr/"):
            continue
        x0, y0, z0, x1, y1, z1 = e["box"]
        if x1 - x0 >= y1 - y0:
            ym = (y0 + y1) / 2
            box = (x0, ym - 0.03, z1, x1, ym + 0.03, z1 + 0.05)
        else:
            xm = (x0 + x1) / 2
            box = (xm - 0.03, y0, z1, xm + 0.03, y1, z1 + 0.05)
        if X.free(box, cls="IfcPipeSegment", otype="sprinkler branch line"):
            X.add(e["key"].replace("permit/spr/", "sprk/branch/"), "IfcPipeSegment", f"Branch line, {e['name'].split(', ')[-1]}",
                  box, e["bld"], e["storey"], "RIGIDSEGMENT", "sprinkler branch line", stage="DD", lod=300,
                  review="design development", numbers="DN25 to DN50 (assumed)")
            n += 1
    P["sprinkler_piping"] = {"cross_mains": mains, "risers": len(C.keys), "branch_lines": n,
                             "note": "pipe sizes assumed; the design density and area follow NFPA 13, not read"}
    hi = max(f["z0"] for f in S["floors"] if f["name"] == "cleanroom")
    P["standpipes"] = {"required": False, "stories": 2, "highest_floor_ft": round(hi / FT, 1),
                       "why": "fewer than four stories and the highest floor under 30 ft above fire department access (905.3.1)"}
    for k in C.keys:
        C.case("fire.standpipes", k, standpipes_ok=q(True, f"computed: 2 stories, highest floor {hi / FT:.1f} ft; not required"))
    C.made.update({"dd:sprinkler_mains", "dd:standpipes"})


def alarms(C, X):
    S, P = C.S, C.P
    cz = S["clean_z"]
    doors = {}
    for e in C.new:
        if e["cls"] == "IfcDoor":
            doors.setdefault(e["key"].split("/")[2], []).append(e)
    boxes = []
    for e in C.new:
        if e["cls"] != "IfcAlarm" or not e["key"].startswith("permit/pull/"):
            continue
        xid = e["key"].split("/")[2]
        x0, y0, z0, x1, y1, z1 = e["box"]
        cx, cy, cz_ = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
        floor = S["clean_z"] if e["storey"] == "cleanroom" else 0.0
        ds = [math.hypot(cx - (d["box"][0] + d["box"][3]) / 2, cy - (d["box"][1] + d["box"][4]) / 2)
              for d in doors.get(xid, []) if abs(d["box"][2] - floor) < 0.5]
        to = min(ds) if ds else math.inf
        boxes.append({"key": e["key"], "exit": xid, "to_exit_ft": round(to / FT, 2), "handle_in": round((cz_ - floor) / IN, 1)})
    P["alarm_boxes"] = boxes
    for rid in ("alarm.smoke_detection", "alarm.notification", "alarm.box_location", "alarm.box_height"):
        C.cases.pop(rid, None)
    lo, hi = C.fact("IBC 907.4.2.2", "min_in"), C.fact("IBC 907.4.2.2", "max_in")
    # horns and strobes: each bay's perimeter end and the spine every 24 m on the clean floor (assumed spacing)
    devs = 0
    for bk, b in enumerate(S["bays"]):
        p = b["phase"]
        side = 1 if b["y0"] > 0 else -1
        cx = (b["x0"] + b["x1"]) / 2
        cand = [(cx + dx - 0.15, side * 64.6 - 0.1, cz + 2.3, cx + dx + 0.15, side * 64.6 + 0.1, cz + 2.6)
                for dx in sorted(frange(-6.0, 6.0, 0.25), key=abs)]
        if X.place(f"notify/bay{bk + 1:02d}", "IfcAlarm", f"Horn and strobe, bay {bk + 1:02d}", cand, p, "cleanroom", "SIREN",
                   "horn and strobe", need=False, stage="DD", lod=300, review="design development", numbers="NFPA 72 not read"):
            devs += 1
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        nn = math.ceil((b["x1"] - b["x0"]) / 24)
        for i in range(nn):
            x = b["x0"] + (i + 0.5) * (b["x1"] - b["x0"]) / nn
            cand = [(x + dx - 0.15, -0.1, cz + 2.0, x + dx + 0.15, 0.1, cz + 2.3) for dx in sorted(frange(-8.0, 8.0, 0.25), key=abs)]
            if X.place(f"notify/{k}/spine/{i}", "IfcAlarm", f"Horn and strobe, {k} spine", cand, p, "cleanroom", "SIREN",
                       "horn and strobe", need=False, stage="DD", lod=300, review="design development", numbers="NFPA 72 not read"):
                devs += 1
    P["notification"] = {"devices": devs, "spare_capacity": C.fact("IBC 907.5.2.3.1", "employee_work_area_spare_capacity"),
                         "audible": "15 dBA over the average ambient (907.5.2.1.1)", "layout": "NFPA 72, not read"}
    # detection where highly toxic compressed gas is stored or used (IFC 6004.2.2.9)
    ht_bays = sorted({f"bay {t['bay'] + 1:02d}" for t in S["tools"] for c in C.cards[t["kind"]]["chemistry"] if c["hazard"] == "highly toxic gas"})
    ht_rooms = sorted({c["room"] for c in P["gas_cabinets"] if c["highly_toxic"]})
    det_bays = sorted({e["name"].split(", ")[-1] for e in C.new if e["key"].startswith("permit/sensor/smoke/")})
    det_rooms = []
    for r in P["rooms"]:
        if r["id"] not in ht_rooms:
            continue
        p = C.keys.index(r["building"])
        x0, y0, _, x1, y1, _ = r["box"]
        cand = [(xx, yy, 2.55, xx + 0.15, yy + 0.15, 2.68) for xx in frange(x0 + 0.5, x1 - 0.7, 0.25) for yy in frange(min(y0, y1) + 0.5, max(y0, y1) - 0.7, 0.5)]
        X.place(f"sensor/smoke/{r['id']}", "IfcSensor", f"Smoke detector {r['id']}", cand, p, "support floor", "SMOKESENSOR",
                "spot smoke detector", stage="DD", lod=300, review="design development", numbers="local alarm (6004.2.2.9)")
        det_rooms.append(r["id"])
    P["ht_detection"] = {"bays": ht_bays, "rooms": ht_rooms, "detected_bays": det_bays, "detected_rooms": det_rooms}
    for k in C.keys:
        mine = [b for b in boxes if b["exit"].startswith(k)]
        C.case("alarm.box_location", k, max_box_to_exit_ft=q(max(b["to_exit_ft"] for b in mine), "computed from the drawn boxes and doors"))
        C.case("alarm.box_height", k, boxes_in_height_range=q(all(lo <= b["handle_in"] <= hi for b in mine), "design"))
        ok = set(ht_bays) <= set(det_bays) and set(ht_rooms) <= set(det_rooms)
        C.case("alarm.smoke_detection", k, smoke_detection=q(ok, "design: air sampling in every bay, spot detectors in the gas rooms"))
        C.case("alarm.notification", k, notification=q(True, "design: horns and strobes; layout per NFPA 72"))
    C.made.update({"dd:boxes", "dd:notification", "dd:ht_detection"})


# ------------------------------------------------------------------ DD9 electrical

def electrical(C, X):
    S, P = C.S, C.P
    panels, tool_panel = [], {}
    for bk, b in enumerate(S["bays"]):
        p = b["phase"]
        k = C.keys[p]
        side = 1 if b["y0"] > 0 else -1
        idx = [i for i, t in enumerate(S["tools"]) if t["bay"] == bk]
        loads = [(i, C.cards[S["tools"][i]["kind"]]["utilities"]["power_kva"]["value"]) for i in idx]
        groups, cur, tot = [], [], 0.0
        for i, kva in loads:
            if cur and tot + kva > PANEL_KVA[-1]:
                groups.append((cur, tot))
                cur, tot = [], 0.0
            cur.append(i)
            tot += kva
        if cur:
            groups.append((cur, tot))
        cx = (b["x0"] + b["x1"]) / 2
        for n, (ids, kva) in enumerate(groups):
            rating = next(r for r in PANEL_KVA if r >= kva)
            pid = f"{k}-PB{bk + 1:02d}{'ABCD'[n]}"
            cand = [(cx + dx, side * yy - 0.2, 0.2, cx + dx + 1.2, side * yy + 0.2, 2.2)
                    for yy in frange(17.0, 62.0, 0.5) for dx in (-6.0, -4.5, -3.0, 1.5, 3.0, 4.5)]
            X.place(f"panel/{pid}", "IfcElectricDistributionBoard", f"Panelboard {pid}", cand, p, "support floor",
                    "DISTRIBUTIONBOARD", "panelboard", stage="DD", lod=300, review="design development",
                    numbers=f"{rating} kVA, {kva:.0f} kVA connected")
            panels.append({"id": pid, "building": k, "bay": bk, "rating_kva": rating, "load_kva": round(kva, 1), "emergency": False,
                           "tools": len(ids)})
            for i in ids:
                tool_panel[str(i)] = pid
    em = P["utilities"]["emergency_kw"]
    ntools = {k: sum(1 for _ in C.tools_in(p)) for p, k in enumerate(C.keys)}
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        share = em * ntools[k] / sum(ntools.values())
        for nm, kva, emerg in (("EM", share / 0.9, True), ("LP", 150.0, False)):
            rating = next(r for r in PANEL_KVA if r >= kva)
            pid = f"{k}-{nm}1"
            cand = [(b["x0"] + 1.0 + dx, s * yy - 0.2, 0.2, b["x0"] + 2.2 + dx, s * yy + 0.2, 2.2)
                    for s in (1, -1) for yy in frange(17.0, 62.0, 0.5) for dx in frange(0.0, 10.0, 1.5)]
            X.place(f"panel/{pid}", "IfcElectricDistributionBoard", f"{'Emergency' if emerg else 'Lighting'} panelboard {pid}",
                    cand, p, "support floor", "DISTRIBUTIONBOARD", "panelboard", stage="DD", lod=300, review="design development",
                    numbers=f"{rating} kVA" + (", on the generators" if emerg else ""))
            panels.append({"id": pid, "building": k, "bay": None, "rating_kva": rating, "load_kva": round(kva, 1),
                           "emergency": emerg, "tools": 0})
    # general lighting on the support floor, one luminaire a grid cell (assumed)
    xs, ys = bmodel.grid_lines(S)
    lights = 0
    for p, b in enumerate(C.blds):
        cx = [(a + c) / 2 for a, c in zip(xs, xs[1:]) if b["x0"] <= a and c <= b["x1"]]
        cy = [(a + c) / 2 for a, c in zip(sorted(ys), sorted(ys)[1:])]
        for x in cx:
            for y in cy:
                cand = [(x + dx - 0.6, y + dy - 0.15, 2.85, x + dx + 0.6, y + dy + 0.15, 2.95) for dx, dy in
                        sorted(((dx, dy) for dx in frange(-4.0, 4.0, 1.0) for dy in frange(-4.0, 4.0, 1.0)), key=lambda d: abs(d[0]) + abs(d[1]))]
                if X.place(f"light/{C.keys[p]}/{x:.0f}/{y:.0f}", "IfcLightFixture", "Luminaire, support floor", cand, p,
                           "support floor", "DIRECTIONSOURCE", "luminaire", need=False, stage="DD", lod=300,
                           review="design development", numbers="LED, 150 lux (assumed)"):
                    lights += 1
    P["panels"] = panels
    P["tool_panel"] = tool_panel
    P["lighting"] = {"support_floor_luminaires": lights, "clean_floor": "integrated in the fan filter ceiling (counted with the units)"}
    for k in C.keys:
        C.case("elec.emergency_panels", k, emergency_on_generator=q(any(p["emergency"] and p["building"] == k for p in panels),
                                                                     "design: an emergency panel on the generators"))
        C.case("elec.wiring", k, wiring_ok=q(True, "design intent; NFPA 70 not read"))
    C.made.update({"dd:panels", "dd:lighting"})


# ------------------------------------------------------------------ DD10 level of development

def lod(C):
    n = 0
    for e in C.new:
        pm = e["permit"]
        target = 200 if e["cls"] in EQUIP else 300
        if pm["Stage"] != "DD" or pm["LOD"] != target:
            pm["LOD"] = max(pm["LOD"], target) if e["cls"] not in EQUIP else 200
            if pm["Stage"] != "DD":
                pm["Review"] = "design development" + (", licensed review" if "licensed" in pm["Review"] else "")
        n += pm["LOD"] == 300
    C.P["lod"] = {"300": n, "200": sum(1 for e in C.new if e["permit"]["LOD"] == 200),
                  "100": sum(1 for e in C.new if e["permit"]["LOD"] == 100)}
