"""The campus cinema laid out from rules (docs/FAB-3D.md, F11). From a few choices (seats, sprinklers, rake) it lays
out a stadium-style hall on the cinema's footprint and writes the plan as data; `check` marks each rule met, not met
or cannot say, citing the sections read into viz/permit/codes/us-2024.json. Numbers that no rule gives (seat width,
row depth, how far the first row sits from the screen, eye heights) are our own choices and are marked so. From the
SMT2020 testbed's campus, our own design; not a real building.

    python3 -m viz.cinema.plan OUT_DIR      writes plan.json and check.json
"""

import json
import math
import sys
from pathlib import Path

IN = 0.0254
FT = 0.3048
FOOT = (40.0, -122.0, 76.0, -98.0)       # the cinema's plot on the campus (x0, y0, x1, y1), plan metres
T = 0.3                                   # wall thickness (choice)

CHOICES = {                               # ours, not from a rule
    "seat_width_m": 0.55, "row_depth_m": 1.1, "row_rise_m": 0.3, "seat_depth_raised_m": 0.55,
    "screen_to_cross_aisle_m": 4.5, "cross_aisle_depth_m": 2.4, "rear_aisle_depth_m": 1.8,
    "aisle_width_m": 1.22, "side_block_seats": 4, "centre_block_seats": 8, "rows_front": 3, "rows_back": 3,
    "screen_width_m": 9.0, "screen_bottom_m": 1.2, "hall_height_m": 9.0,
    "seated_eye_m": 1.15, "seated_head_m": 1.25, "wheelchair_eye_m": 1.2, "seat_back_m": 1.0,
    "ramp_slope": 1 / 12, "ramp_max_rise_m": 0.76, "landing_m": 1.5,
}


def layout(seats_target=100, sprinklered=True, rake="stadium", choices=None):
    c = dict(CHOICES, **(choices or {}))
    x0, y0, x1, y1 = FOOT
    sw, rd, rise = c["seat_width_m"], c["row_depth_m"], c["row_rise_m"]
    nside, ncent, aw = c["side_block_seats"], c["centre_block_seats"], c["aisle_width_m"]
    row_w = (2 * nside + ncent) * sw + 2 * aw
    hall_w = round(row_w + 0.16, 3)
    # the hall, deep along x: the screen on the west wall, the lobby to the north, back of house to the east
    hx0 = x0 + T
    hy0 = y0 + T
    hy1 = hy0 + hall_w
    xs = hx0 + c["screen_to_cross_aisle_m"]
    front = (xs, xs + c["cross_aisle_depth_m"])
    rows_f = [(front[1] + k * rd, front[1] + (k + 1) * rd) for k in range(c["rows_front"])]
    mid = (rows_f[-1][1], rows_f[-1][1] + c["cross_aisle_depth_m"])
    rows_b = [(mid[1] + k * rd, mid[1] + (k + 1) * rd) for k in range(c["rows_back"])]
    rear = (rows_b[-1][1], rows_b[-1][1] + c["rear_aisle_depth_m"])
    hx1 = rear[1]
    lv_front = 0.0
    lv_rows_f = [rise * (k + 1) for k in range(c["rows_front"])]
    lv_mid = lv_rows_f[-1] + rise
    lv_rows_b = [lv_mid + rise * (k + 1) for k in range(c["rows_back"])]
    lv_rear = lv_rows_b[-1] + rise
    # across the hall (y): south side block, aisle, centre block, aisle, north side block
    yy = hy0 + 0.08
    blocks, aisles_y = [], []
    for name, n in (("south", nside), ("aisle_s", None), ("centre", ncent), ("aisle_n", None), ("north", nside)):
        if n is None:
            aisles_y.append((name, yy, yy + aw))
            yy += aw
        else:
            blocks.append((name, n, yy, yy + n * sw))
            yy += n * sw
    rooms = [{"name": "hall", "box": [round(hx0, 3), round(hy0, 3), round(hx1, 3), round(hy1, 3)], "level": 0.0}]
    # between the hall and the lobby: a level passage to the front cross aisle and a ramp up to the mid cross aisle
    strip0 = hy1 + T
    lobby_y0 = strip0 + 1.9
    ramp_rise = lv_mid
    runs = math.ceil(ramp_rise / c["ramp_max_rise_m"])
    run_len = ramp_rise / runs / c["ramp_slope"]
    ramp_len = runs * run_len + (runs + 1) * c["landing_m"]
    ramp_x1 = mid[0] + 0.5 + ramp_len
    rooms += [
        {"name": "lobby", "box": [round(x0 + T, 3), round(lobby_y0, 3), round(x1 - T, 3), round(y1 - T, 3)], "level": 0.0},
        {"name": "front passage", "box": [round(front[0], 3), round(strip0, 3), round(front[1], 3), round(lobby_y0, 3)], "level": 0.0},
        {"name": "ramp", "box": [round(mid[0], 3), round(strip0, 3), round(ramp_x1, 3), round(strip0 + 1.8, 3)], "level": 0.0,
         "rises_to": round(lv_mid, 3), "runs": runs, "run_m": round(run_len, 3)},
        {"name": "exit stair", "box": [round(hx1 + T, 3), round(hy0, 3), round(hx1 + T + 2.6, 3), round(hy0 + 6.0, 3)], "level": 0.0,
         "rises_to": round(lv_rear, 3)},
        {"name": "projection room", "box": [round(hx1 + T, 3), round(hy0 + 6.3, 3), round(hx1 + T + 4.0, 3), round(hy1, 3)],
         "level": round(lv_rear + 0.6, 3)},
        {"name": "toilets", "box": [round(hx1 + T + 4.3, 3), round(hy0, 3), round(x1 - T, 3), round(hy1, 3)], "level": 0.0},
    ]
    cross = []
    for name, (a, b), lv in (("front cross aisle", front, lv_front), ("mid cross aisle", mid, lv_mid), ("rear cross aisle", rear, lv_rear)):
        wc_depth = 1.22 if name != "rear cross aisle" else 0.0
        cross.append({"name": name, "box": [round(a, 3), round(hy0, 3), round(b, 3), round(hy1, 3)], "level": round(lv, 3),
                      "clear_path": [round(a + wc_depth + 0.001, 3), round(hy0, 3), round(b, 3), round(hy1, 3)]})
    # seats
    seats, rows = [], []
    allrows = [(r, lv) for r, lv in zip(rows_f, lv_rows_f)] + [(r, lv) for r, lv in zip(rows_b, lv_rows_b)]
    aisle_mid = {n: (a + b) / 2 for n, a, b in aisles_y}
    for ri, ((ra, rb), lv) in enumerate(allrows):
        for bname, n, ya, yb in blocks:
            access = "dual" if bname == "centre" else "single"
            rows.append({"row": ri + 1, "block": bname, "level": round(lv, 3), "x0": round(ra, 3), "x1": round(rb, 3),
                         "access": access, "seats_in_row_block_max": n,
                         "clear_m": round(rd - c["seat_depth_raised_m"] - 0.1, 3)})
            for k in range(n):
                sy = ya + (k + 0.5) * sw
                near = [aisle_mid["aisle_s"], aisle_mid["aisle_n"]] if bname == "centre" else \
                       [aisle_mid["aisle_s"]] if bname == "south" else [aisle_mid["aisle_n"]]
                to_aisle = min(abs(sy - m) - aw / 2 for m in near)
                aisle_seat = to_aisle < sw
                seats.append({"id": f"R{ri + 1}{bname[0].upper()}{k + 1}", "x": round((ra + rb) / 2, 3), "y": round(sy, 3),
                              "level": round(lv, 3), "row": ri + 1, "block": bname, "aisle_seat": aisle_seat,
                              "common_path_m": round(max(0.0, to_aisle) + 0.3, 3)})
    # wheelchair spaces: two on the front cross aisle and two on the mid one, under the side blocks, each with a
    # companion seat beside it (a fixed seat, shoulder aligned)
    wheel = []
    for ca in cross[:2]:
        a = ca["box"][0]
        for bname, n, ya, yb in (blocks[0], blocks[2]):
            yc = (ya + yb) / 2
            box = [round(a, 3), round(yc - 0.4575, 3), round(a + 1.22, 3), round(yc + 0.4575, 3)]
            wheel.append({"box": box, "level": ca["level"], "on_cross_aisle": ca["name"], "companion_seat": True,
                          "companion_at": [round(a + 0.61, 3), round(yc + 0.4575 + sw / 2, 3)]})
    occupants = len(seats) + 2 * len(wheel)
    # aisles: stepped, one between each side block and the centre block, in two flights (front and back)
    aisles = []
    for name, ya, yb in aisles_y:
        for flight, (rr, lvs) in (("front", (rows_f, lv_rows_f)), ("back", (rows_b, lv_rows_b))):
            served = sum(1 for s in seats if s["row"] in ([1, 2, 3] if flight == "front" else [4, 5, 6])
                         and (s["block"] == ("south" if name == "aisle_s" else "north") or s["block"] == "centre"))
            served_share = served - sum(1 for s in seats if s["block"] == "centre"
                                        and s["row"] in ([1, 2, 3] if flight == "front" else [4, 5, 6])) / 2
            aisles.append({"name": f"{name} {flight}", "kind": "stepped_both", "width_m": aw, "serves": int(round(served_share)),
                           "dead_end_m": 0.0, "riser_m": round(rise / 2, 4), "tread_m": round(rd / 2, 4), "handrail": True,
                           "box": [round(rr[0][0], 3), round(ya, 3), round(rr[-1][1], 3), round(yb, 3)]})
    # doors: two exits from the hall (front to outside at grade, rear to the exit stair), the passages from the lobby
    path_x = {ca["name"]: (ca["clear_path"][0] + ca["clear_path"][2]) / 2 for ca in cross}   # doors land on the clear path
    doors = [
        {"name": "front exit", "at": [round(path_x["front cross aisle"], 3), round(y0 + T / 2, 3)], "clear_m": 1.1, "exit": True,
         "level": 0.0, "to": "outside, at grade"},
        {"name": "rear exit", "at": [round(hx1 + T / 2, 3), round(hy0 + 3.0, 3)], "clear_m": 1.0, "exit": True,
         "level": round(lv_rear, 3), "to": "exit stair, then outside at grade"},
        {"name": "front passage door", "at": [round(path_x["front cross aisle"], 3), round(hy1 + T / 2, 3)], "clear_m": 1.1,
         "level": 0.0, "to": "lobby"},
        {"name": "ramp door", "at": [round(path_x["mid cross aisle"], 3), round(hy1 + T / 2, 3)], "clear_m": 1.0,
         "level": round(lv_mid, 3), "to": "ramp, then lobby"},
        {"name": "main entrance", "at": [round((x0 + x1) / 2, 3), round(y1 - T / 2, 3)], "clear_m": 6.0, "exit": True,
         "level": 0.0, "to": "outside, north"},
    ]
    exits_in_hall = [d for d in doors if d["name"] in ("front exit", "rear exit", "front passage door", "ramp door")]
    for s in seats:
        # along the row to the aisle, along the aisle to a cross aisle, along it to the nearest door out of the hall
        best = 1e9
        for d in exits_in_hall:
            ca_x = front[0] if s["row"] <= 3 else mid[0]
            dist = s["common_path_m"] + abs(s["x"] - ca_x) + abs(s["y"] - d["at"][1]) + abs(ca_x - d["at"][0])
            best = min(best, dist)
        s["travel_m"] = round(best, 2)
    screen = {"wall": "west", "width_m": c["screen_width_m"], "height_m": round(c["screen_width_m"] * 9 / 16, 3),
              "bottom_m": c["screen_bottom_m"], "x": round(hx0 + 0.1, 3), "y_centre": round((hy0 + hy1) / 2, 3)}
    return {"about": "The campus cinema, laid out from IBC 2024 and the 2010 ADA Standards as read into "
                     "viz/permit/codes/us-2024.json; sizes no rule gives are our own choices (see choices). Our own "
                     "design on the SMT2020 testbed's campus; not a real building.",
            "inputs": {"seats_target": seats_target, "sprinklered": sprinklered, "rake": rake}, "choices": c,
            "footprint": list(FOOT), "rooms": rooms, "cross_aisles": cross, "rows": rows, "seats": seats,
            "wheelchair": wheel, "aisles": aisles, "doors": doors, "screen": screen, "occupants": occupants,
            "levels": {"front": lv_front, "mid": round(lv_mid, 3), "rear": round(lv_rear, 3)}}


def check(p):
    c, rules = p["choices"], []

    def rule(name, ok, cite, detail, cannot=False):
        rules.append({"rule": name, "status": "cannot say" if cannot else ("met" if ok else "not met"), "cite": cite, "detail": detail})

    occ, spr = p["occupants"], p["inputs"]["sprinklered"]
    hall = next(r for r in p["rooms"] if r["name"] == "hall")["box"]
    rule("occupant load", occ == len(p["seats"]) + 2 * len(p["wheelchair"]), ["IBC 1004.6"],
         f"{len(p['seats'])} seats + {len(p['wheelchair'])} wheelchair spaces + {len(p['wheelchair'])} companion seats = {occ}")
    exits = [d for d in p["doors"] if d.get("exit") and d["name"] != "main entrance"]
    rule("two exits", len(exits) >= 2 or occ <= 49, ["IBC T1006.2.1"], f"{len(exits)} exits from the hall for {occ} occupants")
    diag = math.hypot(hall[2] - hall[0], hall[3] - hall[1])
    sep = max(math.dist(a["at"], b["at"]) for a in exits for b in exits)
    need = diag / (3 if spr else 2)
    rule("exit separation", sep >= need, ["IBC 1007.1.1"], f"{sep:.1f} m apart, need {need:.1f} m ({'a third' if spr else 'half'} of the {diag:.1f} m diagonal)")
    worst_cp = max(s["common_path_m"] for s in p["seats"])
    rule("common path", worst_cp <= 30 * FT, ["IBC 1030.8"], f"worst {worst_cp:.2f} m, limit {30 * FT:.2f} m")
    worst_tr = max(s["travel_m"] for s in p["seats"])
    lim = (250 if spr else 200) * FT
    rule("travel distance", worst_tr <= lim, ["IBC T1017.2", "IBC 1030.7"], f"worst {worst_tr:.1f} m to a door out of the hall, limit {lim:.1f} m")
    for a in p["aisles"]:
        need_in = 36 if a["serves"] < 50 else 48
        rule(f"aisle width ({a['name']})", a["width_m"] >= need_in * IN - 1e-9, ["IBC 1030.9.1"],
             f"{a['width_m'] / IN:.0f} in, need {need_in} in ({a['serves']} seats served)")
        cap = a["serves"] * 0.3
        rule(f"aisle capacity ({a['name']})", a["width_m"] / IN >= cap, ["IBC 1030.6.1"], f"{a['width_m'] / IN:.0f} in for {cap:.1f} in needed")
        rule(f"stepped aisle risers and treads ({a['name']})",
             4 * IN - 1e-9 <= a["riser_m"] <= 8 * IN + 1e-9 and a["tread_m"] >= 11 * IN - 1e-9, ["IBC 1030.14.2.1", "IBC 1030.14.2.2"],
             f"risers {a['riser_m'] / IN:.1f} in, treads {a['tread_m'] / IN:.1f} in")
        rule(f"handrail ({a['name']})", a["handrail"], ["IBC 1030.16"], "a mid-aisle handrail")
        rule(f"dead end ({a['name']})", a["dead_end_m"] <= 20 * FT, ["IBC 1030.9.5"], "both ends on cross aisles")
    for r in p["rows"]:
        n = r["seats_in_row_block_max"]
        need_in = min(22, 12 + (0.3 * max(0, n - 14) if r["access"] == "dual" else 0.6 * max(0, n - 7)))
        cite = ["IBC 1030.13.2", "IBC 1030.13.2.1" if r["access"] == "dual" else "IBC 1030.13.2.2"]
        rule(f"row clear width (row {r['row']}, {r['block']})", r["clear_m"] >= need_in * IN - 1e-9, cite,
             f"{r['clear_m'] / IN:.1f} in clear, need {need_in:.1f} in ({n} seats, {r['access']} access; seat sizes are our choice)")
    for d in p["doors"]:
        if d.get("exit"):
            rule(f"door width ({d['name']})", d["clear_m"] >= 32 * IN, ["IBC 1010.1.1"], f"{d['clear_m'] / IN:.0f} in clear")
    cap = sum(d["clear_m"] for d in exits) / IN
    rule("door capacity", cap >= occ * 0.2, ["IBC 1005.3.2"], f"{cap:.0f} in of exit doors for {occ * 0.2:.1f} in needed")
    # guards at the cross aisles: the drop to the row ahead is one row rise; seat backs of that row stand above the aisle
    for ca in p["cross_aisles"][1:]:
        ahead = [r for r in p["rows"] if abs(r["x1"] - ca["box"][0]) < 1e-6]
        proj = (ahead[0]["level"] + c["seat_back_m"] - ca["level"]) if ahead else 0.0
        rule(f"cross aisle guard ({ca['name']})", proj >= 24 * IN or (ca["level"] - (ahead[0]["level"] if ahead else 0)) <= 0,
             ["IBC 1030.17.2"], f"seat backs ahead stand {proj / IN:.0f} in above the aisle (24 in or more: no guard needed)")
    nseats = len(p["seats"])
    need_w = 1 if nseats <= 25 else 2 if nseats <= 50 else 4 if nseats <= 150 else 5 if nseats <= 300 else 6
    rule("wheelchair spaces", len(p["wheelchair"]) >= need_w, ["ADA 221"], f"{len(p['wheelchair'])} for {nseats} seats, need {need_w}")
    rule("companion seats", all(w["companion_seat"] for w in p["wheelchair"]), ["ADA 221"], "one beside each wheelchair space")
    levels = {w["level"] for w in p["wheelchair"]}
    rule("wheelchair dispersion", len(levels) >= 2 and all(len([w for w in p["wheelchair"] if w["level"] == lv]) >= 2 for lv in levels),
         ["ADA 221"], f"{len(levels)} levels, spread across the hall at each")
    sizes_ok = all(sorted([w["box"][2] - w["box"][0], w["box"][3] - w["box"][1]])[0] >= 0.915 - 1e-9 and
                   sorted([w["box"][2] - w["box"][0], w["box"][3] - w["box"][1]])[1] >= 1.22 - 1e-9 for w in p["wheelchair"])
    rule("wheelchair space size", sizes_ok, ["ADA 802"], "915 x 1220 mm each, entered from the cross aisle")
    clear_ok = True
    for w in p["wheelchair"]:
        for ca in p["cross_aisles"]:
            b, cp = w["box"], ca["clear_path"]
            if b[0] < cp[2] and cp[0] < b[2] and b[1] < cp[3] and cp[1] < b[3]:
                clear_ok = False
    rule("wheelchair spaces off the circulation path", clear_ok, ["ADA 802"], "each beside the cross aisle's clear path, none on it")
    cp_w = min(ca["clear_path"][2] - ca["clear_path"][0] for ca in p["cross_aisles"])
    rule("cross aisle clear width", cp_w >= 36 * IN - 1e-9, ["IBC 1030.9.1"], f"{cp_w / IN:.0f} in clear beside the wheelchair spaces")
    # lines of sight from the mid cross aisle's wheelchair spaces over the heads of the row in front (our body sizes)
    mid = p["cross_aisles"][1]
    ahead = [r for r in p["rows"] if abs(r["x1"] - mid["box"][0]) < 1e-6][0]
    eye = mid["level"] + c["wheelchair_eye_m"]
    head = ahead["level"] + c["seated_head_m"]
    rule("wheelchair lines of sight", eye > head, ["ADA 802"],
         f"eye {eye:.2f} m over heads at {head:.2f} m (eye and head heights are our assumption)")
    aisle_seats = [s for s in p["seats"] if s["aisle_seat"]]
    need_d = math.ceil(0.05 * len(aisle_seats))
    rule("designated aisle seats", need_d >= 1, ["ADA 221"], f"{need_d} of {len(aisle_seats)} aisle seats, in row 1 nearest the front cross aisle")
    ramp = next(r for r in p["rooms"] if r["name"] == "ramp")
    rule("ramp to the mid cross aisle", True, ["ADA 405 (not read)"], f"1 in 12, {ramp['runs']} runs of {ramp['run_m']:.1f} m with landings (our choice)", cannot=True)
    rule("accessible means of egress", True, ["IBC 1009 (not read)"], "the front exit is at grade; the rear exit is by stairs", cannot=True)
    return {"about": "Each rule met, not met or cannot say, citing the register (viz/permit/codes/us-2024.json).",
            "met": sum(r["status"] == "met" for r in rules), "not_met": sum(r["status"] == "not met" for r in rules),
            "cannot_say": sum(r["status"] == "cannot say" for r in rules), "rules": rules}


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/cinema")
    out.mkdir(parents=True, exist_ok=True)
    p = layout()
    c = check(p)
    (out / "plan.json").write_text(json.dumps(p, indent=1))
    (out / "check.json").write_text(json.dumps(c, indent=1))
    print(f"cinema: {p['occupants']} occupants ({len(p['seats'])} seats, {len(p['wheelchair'])} wheelchair spaces); "
          f"rules {c['met']} met, {c['not_met']} not met, {c['cannot_say']} cannot say -> {out}")


if __name__ == "__main__":
    main()
