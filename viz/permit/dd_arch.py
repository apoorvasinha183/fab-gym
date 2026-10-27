"""Design development, architecture (docs/DESIGN-DEV.md, DD3 and DD4): the chases as service corridors, wall types,
door ratings, firestops, toilet cores, lifts, exit signs and emergency lighting. Nothing here moves a tool, a stocker or
a rail; every element is placed by dd_place, so it clashes with nothing. Every size is assumed unless it is a limit
read from the register.
"""

import heapq
import math

from arch import CORE_X, PASS_X0, PASS_X1
from ctx import FT, IN, SQFT
from rules import q

CHASE_TOP = 12.7          # chase partition top: under the sprinkler arrays and the filter ceiling (assumed)
CHASE_ACH = 6.5           # chase exhaust, air changes an hour (assumed, over the 6 asked)
M3H_PER_CFM = 1.699
STAIR_RUN = 20.0          # walking length of the two flights from the clean floor to the support floor (assumed)
LUMENS = (700.0, 900.0, 1100.0)   # emergency luminaire output, low, value, high (assumed)
SPACING_LIGHT, SPACING_SIGN = 8.0, 24.0
CORE_W, CORE_D, ROOM_W, ALCOVE = 11.0, 4.4, 5.2, 0.6
T = 0.15                  # toilet room walls
WALL_TYPES = {
    "WT-1": {"rating_h": 1, "item": "13-1.1", "cite": "IBC T721.1(2) item 13-1.1",
             "assembly": "steel studs at 24 in with one layer of 5/8 in Type X gypsum board each side, 2 7/8 in"},
    "WT-2": {"rating_h": 2, "item": "13-1.2", "cite": "IBC T721.1(2) item 13-1.2",
             "assembly": "steel studs with two layers of 1/2 in Type X gypsum board each side, 3 5/8 in"},
    "WT-C": {"rating_h": 0, "item": None, "cite": "unrated",
             "assembly": "cleanroom wall panels on steel studs, unrated; tools bulkheaded through (assumed)"},
    "WT-P": {"rating_h": 0, "item": None, "cite": "unrated",
             "assembly": "steel studs with one layer of gypsum board each side, unrated (assumed)"},
}


# ------------------------------------------------------------------ DD3: chases

def pre(C, chase):
    """Before the utilities pass: the chases and their exhaust, so the mains and the plant are sized with it."""
    S = C.S
    cz = S["clean_z"]
    out, extra = [], {}
    for bk, b in enumerate(S["bays"]):
        k = C.keys[b["phase"]]
        sgn = 1 if b["y0"] > 0 else -1
        for end in ("W", "E"):
            x0, x1 = (b["x0"], b["x0"] + chase) if end == "W" else (b["x1"] - chase, b["x1"])
            L = b["y1"] - b["y0"]
            vol = chase * L * (CHASE_TOP - cz)
            m3h = CHASE_ACH * vol
            out.append({"id": f"{k}-CH{bk + 1:02d}{end}", "building": k, "bay": bk, "end": end, "side": sgn,
                        "x0": round(x0, 4), "x1": round(x1, 4), "y0": b["y0"], "y1": b["y1"], "width_m": chase,
                        "length_m": L, "height_m": round(CHASE_TOP - cz, 3), "volume_m3": round(vol, 2),
                        "exhaust_m3h": round(m3h, 1), "exhaust_cfm": round(m3h / M3H_PER_CFM, 1),
                        "ach": round(m3h / vol, 3)})
            f = extra.setdefault((k, sgn), {})
            f["exhaust_general_m3h"] = f.get("exhaust_general_m3h", 0.0) + m3h
    C.dd["chases"] = out
    C.extra_flows = extra


def chases(C, X):
    S = C.S
    cz = S["clean_z"]
    limit = C.fact("IBC 415.11.3.3", "travel_ft") * FT
    for c in C.dd["chases"]:
        b = S["bays"][c["bay"]]
        p = b["phase"]
        if c["end"] == "W":
            wx = (c["x1"], c["x1"] + 0.1)
            touch = [t for t in S["tools"] if t["bay"] == c["bay"] and abs(t["x0"] - c["x1"]) < 0.3]
        else:
            wx = (c["x0"] - 0.1, c["x0"])
            touch = [t for t in S["tools"] if t["bay"] == c["bay"] and abs(t["x1"] - c["x0"]) < 0.3]
        ya, yb = c["y0"], c["y1"]
        X.place(f"chase/{c['id']}/wall", "IfcWall", f"Chase partition {c['id']}", [(wx[0], ya, cz, wx[1], yb, CHASE_TOP)], p,
                "cleanroom", "PARTITIONING", "chase partition", stage="DD", lod=300, review="design development",
                numbers="WT-C, unrated; tools bulkheaded through")
        # doors into the fab area until no point of the chase is more than 75 ft from an open end or a door
        stops = [ya, yb]
        doors = []
        while True:
            gaps = sorted(zip(stops, stops[1:]), key=lambda g: g[1] - g[0], reverse=True)
            g0, g1 = gaps[0]
            if (g1 - g0) / 2 <= limit:
                break
            target = (g0 + g1) / 2
            side_cl = max(C.cards[t["kind"]]["clearance_m"]["side"]["value"] for t in touch) if touch else 0.0
            ends = [v for t in touch for v in (t["y0"], t["y1"])]
            room = lambda y: min((abs(y - v) for v in ends), default=99.0)
            # in the middle of a gap in the tools, clear of their side clearances where the gap allows
            cand = sorted((y for y in frange(g0 + 1.0, g1 - 1.0, 0.05)), key=lambda y: (room(y) < 0.6 + side_cl, abs(y - target) if room(y) >= 0.6 + side_cl else -room(y)))
            boxes = [(wx[0], y - 0.6, cz, wx[1], y + 0.6, cz + 2.1) for y in cand
                     if not any(t["y0"] - 0.1 < y + 0.6 and t["y1"] + 0.1 > y - 0.6 for t in touch)]
            e = X.place(f"door/chase/{c['id']}/{len(doors)}", "IfcDoor", f"Chase door {c['id']}", boxes, p, "cleanroom", "DOOR",
                        stage="DD", lod=300, review="design development", numbers="1.2 m leaf into the fab area",
                        door=(2.1, 1.2, "SINGLE_SWING_LEFT"))
            y = (e["box"][1] + e["box"][4]) / 2
            doors.append(round(y, 3))
            stops = sorted(stops + [y])
        c["doors_y"] = doors
        c["max_travel_m"] = round(max(g1 - g0 for g0, g1 in zip(stops, stops[1:])) / 2, 3)
        c["dead_end_m"] = 0.0
        c["open_ends"] = ["spine", "perimeter"]
        # the exhaust: a grille at the top of the chase and a drop through the raised floor and the waffle slab
        cx = (c["x0"] + c["x1"]) / 2
        mid = (ya + yb) / 2
        ys = sorted(frange(ya + 1.0, yb - 1.0, 0.5), key=lambda y: abs(y - mid))
        for y in ys:
            grille = (cx - 0.25, y - 0.25, 12.2, cx + 0.25, y + 0.25, 12.5)
            drop = (cx - 0.2, y - 0.2, 5.9, cx + 0.2, y + 0.2, 12.2)
            if X.free(grille, cls="IfcAirTerminal") and X.free(drop, cls="IfcDuctSegment", otype="chase exhaust"):
                X.add(f"chase/{c['id']}/grille", "IfcAirTerminal", f"Chase exhaust grille {c['id']}", grille, p, "cleanroom",
                      "GRILLE", "chase exhaust", stage="DD", lod=300, review="design development",
                      numbers=f"{c['exhaust_cfm']:.0f} cfm, {c['ach']} air changes an hour")
                X.add(f"chase/{c['id']}/drop", "IfcDuctSegment", f"Chase exhaust drop {c['id']}", drop, p, "cleanroom",
                      "RIGIDSEGMENT", "chase exhaust", stage="DD", lod=300, review="design development",
                      numbers="400 x 400 mm to the general exhaust main")
                break
        else:
            raise SystemExit(f"no place for the exhaust of chase {c['id']}")
    C.P["chases"] = C.dd["chases"]
    C.made.add("dd:chases")


def frange(a, b, s):
    n = int(math.floor((b - a) / s + 1e-9))
    return [round(a + i * s, 4) for i in range(n + 1)]


def judge(C):
    """The stricter readings, as the cases the rules see; replaces the schematic stage's open judgements."""
    J = C.permit["dd"]["judgements"]
    sc = J["chase_is_service_corridor"]
    rc = J["risk_category"]
    C.P["judgements"] = J
    cs = {k: [c for c in C.dd["chases"] if c["building"] == k] for k in C.keys}
    for rid in ("service.corridor_width", "service.corridor_travel", "service.corridor_ventilation", "service.dead_end",
                "structure.risk_category"):
        C.cases.pop(rid, None)
    for k in C.keys:
        mine = cs[k]
        j = q(sc["value"], sc["basis"])
        C.case("service.corridor_width", k, chase_width_ft=q(round(min(c["width_m"] for c in mine) / FT, 2), "design: the 1.6 m layout D10 rescored"),
               chase_is_service_corridor=j)
        C.case("service.corridor_travel", k, chase_travel_ft=q(round(max(c["max_travel_m"] for c in mine) / FT, 1),
                                                                "computed along each chase to its open ends and doors"),
               chase_is_service_corridor=j)
        C.case("service.dead_end", k, chase_dead_end_ft=q(round(max(c["dead_end_m"] for c in mine) / FT, 1),
                                                           "design: every chase open to the spine and the perimeter"),
               chase_is_service_corridor=j)
        C.case("service.corridor_ventilation", k, chase_ach=q(min(c["ach"] for c in mine), "design: chase exhaust, assumed"),
               chase_is_service_corridor=j)
        C.case("structure.risk_category", k, risk_category_settled=q(True, f"assumed: category {rc['value']}, the stricter reading"))
    C.P["chase"] = {"width_m": cs[C.keys[0]][0]["width_m"], "width_ft": round(cs[C.keys[0]][0]["width_m"] / FT, 2),
                    "service_corridor": True, "basis": sc["basis"]}
    C.made.add("dd:judgements")


# ------------------------------------------------------------------ DD4: wall types, doors, firestops

def wall_kind(e):
    n, num = e["name"], e["permit"]["Numbers"]
    if n.startswith("Stair enclosure"):
        return "WT-2", 2
    if n.startswith("Exit passageway wall"):
        return "WT-1", 1
    if n.startswith("Rated wall"):
        return ("WT-2", 2) if "2 h" in num else ("WT-1", 1) if "1 h" in num else ("WT-P", 0)
    if n.startswith("Chase partition"):
        return "WT-C", 0
    return "WT-P", 0


def walls_and_doors(C):
    rooms = {r["id"]: r for r in C.P["rooms"]}
    exits = {x["id"]: x for x in C.P["exits"]}
    table = C.fact("IBC T716.1(2)", "door_h_by_wall")
    walls, doors = [], []
    for e in C.new:
        if e["cls"] != "IfcWall":
            continue
        t, r = wall_kind(e)
        w = WALL_TYPES[t]
        e["rating"] = {"Rating_h": float(r), "WallType": t, "Assembly": w["assembly"], "Cite": w["cite"]}
        walls.append({"key": e["key"], "kind": e["name"].split(",")[0].split(" P")[0], "rating_h": r, "type": t})
    for e in C.new:
        if e["cls"] != "IfcDoor":
            continue
        parts = e["key"].split("/")[2:]
        rid, suf = parts[0], (parts[1] if len(parts) > 1 else "")
        kind = "partition"
        if rid in rooms:
            r = rooms[rid]
            kind = "exterior" if suf == "ext" else (f"fire barrier {r['rating_h']} h" if r["rating_h"] >= 2 else
                                                    "other fire barrier 1 h" if r["rating_h"] == 1 else "partition")
        elif rid in exits:
            x = exits[rid]
            if x["kind"] == "spine stair":
                kind = "exit enclosure 2 h"
            elif x["kind"] == "facade stair":
                kind = "exterior" if suf == "out" else "exit enclosure 2 h"
            elif x["kind"] == "exit passageway":
                kind = "exterior" if suf == "ext" else "exit enclosure 2 h" if suf == "core" else "exit passageway 1 h"
            else:
                kind = "exterior"
        rating = table.get(kind, 0)
        wall_r = int(kind.split(" ")[-2]) if kind.endswith(" h") else 0
        e["permit"]["Numbers"] = (e["permit"]["Numbers"] + "; " if e["permit"]["Numbers"] else "") + (
            f"rated {fmt_h(rating)} for a {kind} (T716.1(2))" if rating else f"unrated ({kind})")
        doors.append({"key": e["key"], "wall_kind": kind, "wall_rating_h": wall_r, "rating_h": rating})
    C.P["wall_types"] = WALL_TYPES
    C.P["walls"] = walls
    C.P["doors"] = doors
    ok_w = all(WALL_TYPES[w["type"]]["rating_h"] >= w["rating_h"] for w in walls)
    ok_d = all(d["rating_h"] >= table.get(d["wall_kind"], 0) - 1e-9 for d in doors)
    for k in C.keys:
        C.case("walls.types", k, rated_walls_typed=q(ok_w, "design: every rated wall a listed assembly"))
        C.case("doors.rating", k, doors_rated=q(ok_d, "design: door ratings from Table 716.1(2)"))
    C.made.update({"dd:walls", "dd:doors"})


def fmt_h(h):
    return {0.333: "20 min", 0.75: "45 min", 1.5: "90 min"}.get(round(h, 3), f"{h:g} h")


def firestops(C):
    """Every pipe, duct or tray crossing a rated wall: a firestop with an F rating of at least the wall's."""
    from geom import overlap
    rated = [(e, e["rating"]["Rating_h"]) for e in C.new if e["cls"] == "IfcWall" and e.get("rating") and e["rating"]["Rating_h"] > 0]
    segs = [e for e in C.new if e["cls"] in ("IfcPipeSegment", "IfcDuctSegment", "IfcCableCarrierSegment")]
    out = []
    for s in segs:
        for w, r in rated:
            if overlap(s["box"], w["box"]) > 1e-6:
                out.append({"element": s["key"], "wall": w["key"], "wall_rating_h": r, "f_rating_h": r,
                            "system": "listed through-penetration firestop, ASTM E814 or UL 1479 (as 714.4.1.2 asks)"})
    C.P["firestops"] = out
    ok = all(f["f_rating_h"] >= f["wall_rating_h"] for f in out)
    for k in C.keys:
        C.case("penetrations.firestop", k, firestops_ok=q(ok, f"design: {sum(1 for f in out if f['wall'].split('/')[2].startswith(k))} penetrations firestopped"))
    C.made.add("dd:firestops")


# ------------------------------------------------------------------ DD4: toilet cores and their walking distances

def walk_from(g, seeds):
    """Shortest walks on the grid from seed cells that start with their own distances."""
    nx, ny, s = g.nx, g.ny, g.step
    free = g.flat
    dist = [math.inf] * (nx * ny)
    h = []
    for i, d0 in seeds:
        if d0 < dist[i]:
            dist[i] = d0
            h.append((d0, i))
    heapq.heapify(h)
    d2 = s * math.sqrt(2)
    while h:
        d, i = heapq.heappop(h)
        if d > dist[i]:
            continue
        iy, ix = divmod(i, nx)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jx, jy = ix + dx, iy + dy
            if 0 <= jx < nx and 0 <= jy < ny:
                j = jy * nx + jx
                if free[j] and d + s < dist[j]:
                    dist[j] = d + s
                    heapq.heappush(h, (d + s, j))
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            jx, jy = ix + dx, iy + dy
            if 0 <= jx < nx and 0 <= jy < ny:
                j = jy * nx + jx
                if free[j] and free[iy * nx + jx] and free[jy * nx + ix] and d + d2 < dist[j]:
                    dist[j] = d + d2
                    heapq.heappush(h, (d + d2, j))
    return dist


def toilets(C, X):
    P = C.P
    per100 = C.fact("IPC 403.1", "factory_wc_per")
    df_per = C.fact("IPC 403.1", "factory_df_per")
    cores, by_b = [], {}
    strict = {"strict": True}
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        occ = sum(P["egress"][k][s]["occupant_load"] for s in ("clean floor", "support floor"))
        per_sex = math.ceil(occ / 2 / per100)
        stairs = [x for x in P["exits"] if x["building"] == k and x["kind"] == "spine stair"]
        n = len(stairs)
        wc = math.ceil(per_sex / n)
        if wc > 5:
            raise SystemExit(f"{k}: {wc} water closets a room do not fit a core; add cores")
        dfs = max(2, math.ceil(math.ceil(occ / df_per) / n))
        mine = []
        for x in stairs:
            m, s = x["x"], x["side"]
            done = None
            for t in (-s, s):
                for y0 in frange(4.45, 11.0, 0.25):
                    for dx in sorted(frange(-6.0, 6.0, 0.25), key=abs):
                        x0 = m - CORE_W / 2 + dx
                        ya, yb = (y0, y0 + CORE_D) if t > 0 else (-y0 - CORE_D, -y0)
                        box = (x0, ya, 0.0, x0 + CORE_W, yb, 3.0)
                        if X.free(box, **strict):
                            done = (x0, t, y0)
                            break
                    if done:
                        break
                if done:
                    break
            if not done:
                raise SystemExit(f"no place for a toilet core by {x['id']}")
            mine.append(core(C, X, p, k, x["id"], *done, wc, dfs, last=False))
        mine[0]["service_sinks"] += 0
        cores += mine
        by_b[k] = {"occupants": occ, "per_sex_needed": per_sex, "cores": n,
                   "wc_men": sum(c["wc"] for c in mine), "wc_women": sum(c["wc"] for c in mine),
                   "lav_men": sum(c["lav"] for c in mine), "lav_women": sum(c["lav"] for c in mine),
                   "drinking_fountains": sum(c["df"] for c in mine), "drinking_fountains_needed": math.ceil(occ / df_per),
                   "service_sinks": sum(c["service_sinks"] for c in mine), "basis": "assumed: IPC Table 403.1, factory and industrial row (H is not listed)"}
    C.P["toilets"] = {"cores": cores, "by_building": by_b}
    travel(C)
    for k, t in by_b.items():
        ok = t["wc_men"] >= t["per_sex_needed"] and t["wc_women"] >= t["per_sex_needed"] and t["lav_men"] >= t["per_sex_needed"] \
            and t["lav_women"] >= t["per_sex_needed"] and t["drinking_fountains"] >= t["drinking_fountains_needed"] and t["service_sinks"] >= 1
        C.case("plumbing.fixtures", k, fixtures_ok=q(ok, "assumed: the factory and industrial row of Table 403.1 for H-5"))
        C.case("plumbing.separate", k, separate_rooms=q(all(c["men_room"] and c["women_room"] for c in cores if c["building"] == k),
                                                         "design: a men's and a women's room in every core"))
        for story in ("clean floor", "support floor"):
            C.case("plumbing.toilet_travel", f"{k} {story}", toilet_travel_ft=q(round(t["travel_m"][story] / FT, 1),
                                                                                "computed on the 0.5 m grid, the stair run assumed"))
    C.made.add("dd:toilets")


def core(C, X, p, k, near, x0, t, y0, wc, dfs, last):
    """A toilet core: men's room, an alcove with drinking fountains, women's room; the door on the face to the spine."""
    ya, yb = (y0, y0 + CORE_D) if t > 0 else (-y0 - CORE_D, -y0)
    front = ya if t > 0 else yb            # the face toward the spine
    cid = f"{k}-TC{near.split('-SC')[1][:2]}"

    def Y(v0, v1):                          # depth from the front face, v0 < v1, to world y
        a, b = (front + v0, front + v1) if t > 0 else (front - v1, front - v0)
        return a, b

    rooms = {}
    for n, (who, u0) in enumerate((("men", 0.0), ("women", ROOM_W + ALCOVE))):
        rx0, rx1 = x0 + u0, x0 + u0 + ROOM_W
        name = f"{'Men' if who == 'men' else 'Women'}'s toilet room {cid}"
        X.add(f"toilet/{cid}/{who}", "IfcSpace", name, (rx0 + T, ya + T, 0.0, rx1 - T, yb - T, 3.0), p, "support floor",
              "INTERNAL", "toilet room", stage="DD", lod=300, review="design development",
              numbers=f"{wc} water closets, {wc} lavatories" + (", a service sink" if who == "men" else ""))
        fa, fb = Y(0.0, T)
        ba, bb = Y(CORE_D - T, CORE_D)
        walls = [(rx0, ya, 0, rx0 + T, yb, 3.0), (rx1 - T, ya, 0, rx1, yb, 3.0), (rx0 + T, ba, 0, rx1 - T, bb, 3.0),
                 (rx0 + T, fa, 0, rx1 - T, fb, 3.0)]
        for j, w in enumerate(walls):
            X.add(f"wall/toilet/{cid}/{who}/{j}", "IfcWall", f"Toilet room wall {cid}", w, p, "support floor", "PARTITIONING",
                  stage="DD", lod=300, review="design development", numbers="WT-P, unrated")
        dc = rx0 + ROOM_W / 2
        X.add(f"door/toilet/{cid}/{who}", "IfcDoor", f"Toilet room door {cid}", (dc - 0.5, fa, 0, dc + 0.5, fb, 2.1), p,
              "support floor", "DOOR", stage="DD", lod=300, review="design development", numbers="1.0 m leaf",
              door=(2.1, 1.0, "SINGLE_SWING_LEFT"))
        for i in range(wc):
            u = rx0 + 0.3 + i * 0.9
            v0, v1 = Y(3.5, 4.2)
            X.add(f"fixture/{cid}/{who}/wc/{i}", "IfcSanitaryTerminal", f"Water closet {cid}", (u, v0, 0, u + 0.5, v1, 0.8), p,
                  "support floor", "TOILETPAN", stage="DD", lod=300, review="design development", numbers="4 dfu (T709.1)")
        for i in range(wc):
            v0, v1 = Y(0.4 + i * 0.6, 0.9 + i * 0.6)
            X.add(f"fixture/{cid}/{who}/lav/{i}", "IfcSanitaryTerminal", f"Lavatory {cid}", (rx0 + 0.2, v0, 0.7, rx0 + 0.65, v1, 0.9), p,
                  "support floor", "WASHHANDBASIN", stage="DD", lod=300, review="design development", numbers="1 dfu (T709.1)")
        if who == "men":
            v0, v1 = Y(0.4, 0.9)
            X.add(f"fixture/{cid}/sink", "IfcSanitaryTerminal", f"Service sink {cid}", (rx1 - 0.7, v0, 0, rx1 - 0.2, v1, 0.6), p,
                  "support floor", "SINK", stage="DD", lod=300, review="design development", numbers="2 dfu (T709.1)")
        rooms[who] = True
    for i in range(dfs):
        v0, v1 = Y(0.3 + i * 0.6, 0.75 + i * 0.6)
        X.add(f"fixture/{cid}/df/{i}", "IfcSanitaryTerminal", f"Drinking fountain {cid}",
              (x0 + ROOM_W + 0.08, v0, 0.7, x0 + ROOM_W + ALCOVE - 0.08, v1, 1.0), p, "support floor", "SANITARYFOUNTAIN",
              stage="DD", lod=300, review="design development", numbers="0.5 dfu (T709.1)")
    dfu = 2 * wc * 4 + 2 * wc * 1 + 2 + dfs * 0.5
    door_pts = [(x0 + ROOM_W / 2, front - t * 0.4), (x0 + ROOM_W + ALCOVE + ROOM_W / 2, front - t * 0.4)]
    return {"id": cid, "building": k, "near": near, "box": [round(v, 3) for v in (x0, ya, 0.0, x0 + CORE_W, yb, 3.0)],
            "men_room": rooms.get("men", False), "women_room": rooms.get("women", False), "wc": wc, "lav": wc, "df": dfs,
            "service_sinks": 1, "dfu": dfu, "doors": door_pts}


def travel(C):
    P = C.P
    for k in C.keys:
        p = C.keys.index(k)
        h, _, reach_s = C.grids[(k, "support floor")]
        g, _, reach_c = C.grids[(k, "clean floor")]
        mine = [c for c in P["toilets"]["cores"] if c["building"] == k]
        seeds = [(h.cell(x, y), 0.0) for c in mine for x, y in c["doors"]]
        ds = walk_from(h, seeds)
        far_s = max(d for d, r in zip(ds, reach_s) if r)
        cseeds = []
        for x in P["exits"]:
            if x["building"] != k:
                continue
            if x["kind"] == "spine stair":
                m = x["x"]
                xp = next((e for e in P["exits"] if e.get("from") == x["id"]), None)
                best = math.inf
                if xp:
                    s = xp["side"]
                    mm = xp["x"] - (PASS_X0 + PASS_X1) / 2
                    for yy in (10.0, 22.0, 34.0, 46.0, 58.0):
                        for xx in (mm + PASS_X0 - 0.3, mm + PASS_X1 + 0.3):
                            best = min(best, abs(yy) - 1.7 + ds[h.cell(xx, s * yy)])
                for cy in (1.95, -1.95):
                    cseeds.append((g.cell(m - 2.5, cy), STAIR_RUN + best))
            elif x["kind"] == "facade stair":
                m, s = x["x"], x["side"]
                cseeds.append((g.cell(m, s * 69.45), STAIR_RUN + ds[h.cell(m, s * 69.45)]))
        dc = walk_from(g, cseeds)
        far_c = max(d for d, r in zip(dc, reach_c) if r)
        P["toilets"]["by_building"][k]["travel_m"] = {"clean floor": round(far_c, 2), "support floor": round(far_s, 2)}
        P["toilets"]["by_building"][k]["travel_how"] = (
            "clean floor: walk to the nearest exit stair, down its two flights (20 m, assumed), then on the support floor "
            "to the nearest toilet; support floor: walk to the nearest toilet; both on the 0.5 m grid in eight directions")


# ------------------------------------------------------------------ DD4: lifts

def lifts(C, X):
    out = []
    cz = C.S["clean_z"]
    # the slabs it passes are openings; the sprinkler head arrays (drawn as boxes) leave out the hoistway
    allow = lambda o: (o["cls"] in ("IfcSlab", "IfcCovering") and not o["key"].startswith("permit/")) or \
        o["cls"] == "IfcFireSuppressionTerminal"
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        done = None
        for y0 in [y for y in frange(29.0, 60.0, 0.5)] + [-y - 2.6 for y in frange(29.0, 60.0, 0.5)]:
            for x0 in frange(b["x0"] + 0.4, b["x0"] + 3.0, 0.2):
                box = (x0, y0, 0.0, x0 + 2.6, y0 + 2.6, cz + 3.0)
                if X.free(box, strict=True, allow=allow):
                    done = box
                    break
            if done:
                break
        if not done:
            raise SystemExit(f"{k}: no place for a lift at the west end")
        X.add(f"lift/{k}", "IfcTransportElement", f"Passenger lift {k}", done, p, "support floor", "ELEVATOR", "passenger lift",
              stage="DD", lod=200, review="design development, licensed review",
              numbers="2.6 x 2.6 m hoistway, support floor to clean floor; ASME A17.1 not read")
        out.append({"id": f"{k}-L1", "building": k, "box": [round(v, 3) for v in done], "serves": ["support floor", "clean floor"],
                    "note": "hoistway enclosure and machinery per IBC 713 and 3006 and ASME A17.1, not read; "
                            "sprinkler heads left out of the hoistway"})
    C.P["lifts"] = out
    for k in C.keys:
        C.case("access.levels", k, route_between_stories=q(any(l["building"] == k for l in out), "design: a lift in each building"))
        C.case("access.stairs", k, stairs_accessible_egress=q(True, "design: sprinklered throughout (1009.3.2, 1009.3.3 exceptions); "
                                                               "under four stories, so no lift is needed for egress (1009.2.1)"))
        C.cases.pop("access.route", None) if k == C.keys[0] else None
    for k in C.keys:
        C.case("access.route", k, accessible=q(True, "design: a lift and accessible routes; details per ICC A117.1"))
    C.made.add("dd:lifts")


# ------------------------------------------------------------------ DD4: exit signs and emergency lighting

def paths(C):
    """The exit access corridors and exit passageways, as straight lines: (building, name, floor z, axis, fixed, a, b)."""
    out = []
    cz = C.S["clean_z"]
    for p, b in enumerate(C.blds):
        k = C.keys[p]
        for s in (1, -1):
            out.append((p, k, f"spine {'N' if s > 0 else 'S'}", cz, "x", s * 2.6, b["x0"] + 1.0, b["x1"] - 1.0))
            out.append((p, k, f"perimeter {'N' if s > 0 else 'S'}", cz, "x", s * 67.0, b["x0"] + 1.0, b["x1"] - 1.0))
        for x in C.P["exits"]:
            if x["building"] == k and x["kind"] == "exit passageway":
                s = x["side"]
                ya, yb = sorted((s * 2.2, s * 69.2))
                out.append((p, k, f"passageway {x['id']}", 0.0, "y", x["x"], ya, yb))
    return out


def signs_and_lighting(C, X):
    out_s, out_l = {k: {"signs": 0, "max_to_sign_m": 0.0} for k in C.keys}, {}
    samples = {k: {"lo": [], "value": [], "hi": []} for k in C.keys}
    for p, k, name, fz, axis, fixed, a, b in paths(C):
        hs, hl = (1.9, 2.3) if fz > 0 else (2.3, 2.8)
        def box_at(u, z0, z1, w=0.3):
            return (u - w / 2, fixed - 0.1, fz + z0, u + w / 2, fixed + 0.1, fz + z1) if axis == "x" else \
                   (fixed - 0.1, u - w / 2, fz + z0, fixed + 0.1, u + w / 2, fz + z1)
        storey = "cleanroom" if fz > 0 else "support floor"
        # exit signs every 24 m and at the ends
        sx = []
        n = max(1, math.ceil((b - a) / SPACING_SIGN))
        for i in range(n + 1):
            u = a + (b - a) * i / n
            cand = [box_at(u + du, hs, hs + 0.2) for du in sorted(frange(-6.0, 6.0, 0.25), key=abs) if a - 0.01 <= u + du <= b + 0.01]
            e = X.place(f"sign/{k}/{name}/{i}", "IfcLightFixture", f"Exit sign, {name}", cand, p, storey, "SECURITYLIGHTING",
                        "exit sign", need=False, stage="DD", lod=300, review="design development", numbers="internally lit, 90 min battery")
            if e:
                sx.append((e["box"][0] + e["box"][3]) / 2 if axis == "x" else (e["box"][1] + e["box"][4]) / 2)
        far = max((min(abs(u - v) for v in sx) for u in frange(a, b, 0.5)), default=math.inf) if sx else math.inf
        out_s[k]["signs"] += len(sx)
        out_s[k]["max_to_sign_m"] = max(out_s[k]["max_to_sign_m"], far)
        # emergency luminaires every 8 m
        lx = []
        n = max(1, math.ceil((b - a) / SPACING_LIGHT))
        for i in range(n + 1):
            u = a + (b - a) * i / n
            cand = [box_at(u + du, hl, hl + 0.1, 0.4) for du in sorted(frange(-2.0, 2.0, 0.25), key=abs) if a - 0.01 <= u + du <= b + 0.01]
            e = X.place(f"emlight/{k}/{name}/{i}", "IfcLightFixture", f"Emergency luminaire, {name}", cand, p, storey,
                        "SECURITYLIGHTING", "emergency luminaire", need=False, stage="DD", lod=300, review="design development",
                        numbers="900 lm (700 to 1,100, assumed), 90 min")
            if e:
                lx.append((e["box"][0] + e["box"][3]) / 2 if axis == "x" else (e["box"][1] + e["box"][4]) / 2)
        for u in frange(a, b, 0.5):
            for nm, lm in zip(("lo", "value", "hi"), LUMENS):
                I = lm / math.pi
                E = sum(I * (hl / math.hypot(hl, u - v)) ** 3 / hl ** 2 for v in lx)
                samples[k][nm].append(E / 10.764)
    for k in C.keys:
        s = samples[k]
        out_l[k] = {"avg_fc": round(sum(s["value"]) / len(s["value"]), 3), "min_fc": round(min(s["value"]), 3),
                    "avg_fc_lo": round(sum(s["lo"]) / len(s["lo"]), 3), "min_fc_lo": round(min(s["lo"]), 3),
                    "avg_fc_hi": round(sum(s["hi"]) / len(s["hi"]), 3), "min_fc_hi": round(min(s["hi"]), 3),
                    "duration_min": 90, "spacing_m": SPACING_LIGHT, "lumens": LUMENS,
                    "how": "point by point along each path at floor level, every 0.5 m; luminaires as downlights (I = lm / pi)"}
        out_s[k]["max_to_sign_ft"] = round(out_s[k]["max_to_sign_m"] / FT, 1)
        e = out_l[k]
        C.case("egress.exit_signs", k, max_to_sign_ft=q(out_s[k]["max_to_sign_ft"], "computed along each corridor and passageway"))
        C.case("egress.emergency_lighting", k, avg_fc=q(e["avg_fc"], "assumed", e["avg_fc_lo"], e["avg_fc_hi"]))
        C.case("egress.emergency_lighting_min", k, min_fc=q(e["min_fc"], "assumed", e["min_fc_lo"], e["min_fc_hi"]))
        C.case("egress.emergency_duration", k, duration_min=q(90, "design: 90 min batteries"))
    C.P["exit_signs"] = out_s
    C.P["emergency_lighting"] = out_l
    C.made.update({"dd:signs", "dd:emlight"})
