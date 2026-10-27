"""D8, coordination (docs/PERMIT.md): every new element against every element, as boxes.

A hard clash is two elements overlapping by more than 0.0001 m3 that are not a known joint:
  - anything with a space (rooms, bays, the spine, passageways hold what is in them);
  - a door in a wall; walls meeting walls; a column in a wall;
  - an element passing through a slab or a covering (an opening: its height spans the slab's);
  - fan filter units in the filter ceiling;
  - anything inside a support building drawn as one block (the central utility building, the office);
  - design development: a tool through a chase partition (a bulkhead); a pipe through a rated wall at a firestopped
    penetration; sprinkler piping among its heads.
The hoist vehicles' path (each rail grown by half a vehicle) counts as an element: nothing new may enter it.
"""

from arch import rail_envelopes
from geom import inside, overlap

TOL = 1e-4
CELL = 12.0


def joint(a, b):
    ca, cb = a["cls"], b["cls"]
    pair = {ca, cb}
    if "IfcSpace" in pair:
        return "inside a space"
    if pair == {"IfcDoor", "IfcWall"}:
        return "door in a wall"
    if pair == {"IfcWall"}:
        return "walls meeting"
    if pair == {"IfcColumn", "IfcWall"}:
        return "column in a wall"
    for s, o in ((a, b), (b, a)):
        if s["cls"] == "IfcWall" and s["name"].startswith("Chase partition") and o["cls"] == "IfcBuildingElementProxy" \
                and (o["key"] or "").startswith("tool/"):
            return "tool through a chase partition (bulkhead)"
        if s["cls"] == "IfcWall" and o["cls"] in ("IfcPipeSegment", "IfcDuctSegment") and "firestopped" in (o["otype"] or ""):
            return "through a firestopped penetration"
        if s["cls"] == "IfcFireSuppressionTerminal" and o["cls"] == "IfcPipeSegment" and (o["otype"] or "").startswith("sprinkler"):
            return "sprinkler piping among its heads"
        if s["cls"] == "IfcFireSuppressionTerminal" and o["cls"] == "IfcTransportElement":
            return "a hoistway the sprinkler heads leave out"
        if s["cls"] in ("IfcSlab", "IfcCovering") and not s["key"].startswith("permit/"):
            if o["box"][2] <= s["box"][2] + 1e-6 and o["box"][5] >= s["box"][5] - 1e-6:
                return "through an opening in a slab"
        if s["cls"] == "IfcCovering" and o["cls"] == "IfcAirTerminal":
            return "fan filter units in the filter ceiling"
        if s["cls"] == "IfcBuildingElementProxy" and (s["otype"] or "").startswith("campus") and inside(o["box"], s["box"]):
            return "inside a support building drawn as a block"
    return None


def run(C):
    S = C.S
    old = [e for e in C.M["elements"] if e["box"] is not None]
    env = [{"key": f"hoist/{i}", "cls": "hoist path", "name": f"Hoist path {i + 1}", "box": b, "otype": None}
           for i, b in enumerate(rail_envelopes(S))]
    allx = old + env + C.new
    grid = {}
    for n, e in enumerate(allx):
        x0, y0, _, x1, y1, _ = e["box"]
        for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                grid.setdefault((i, j), []).append(n)
    first_new = len(old) + len(env)
    seen, clashes, joints = set(), [], {}
    for idx in grid.values():
        news = [n for n in idx if n >= first_new]
        for a in news:
            for b in idx:
                if b == a or (b >= first_new and b < a):
                    continue
                key = (min(a, b), max(a, b))
                if key in seen:
                    continue
                seen.add(key)
                v = overlap(allx[a]["box"], allx[b]["box"])
                if v <= TOL:
                    continue
                why = None if allx[b]["cls"] == "hoist path" else joint(allx[a], allx[b])
                if why:
                    joints[why] = joints.get(why, 0) + 1
                else:
                    clashes.append({"a": allx[a]["key"], "b": allx[b]["key"], "volume_m3": round(v, 5)})
    clashes.sort(key=lambda c: (c["a"], c["b"]))
    C.P["clashes"] = clashes
    C.P["joints"] = dict(sorted(joints.items()))
    C.P["elements_added"] = len(C.new)
    if not clashes:
        C.made.add("clashes_zero")
