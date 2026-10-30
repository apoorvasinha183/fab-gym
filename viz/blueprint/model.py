"""One building model of the campus (docs/BIM.md), in metres, from the scene file the films and the explorer use.

Every element says where its numbers come from: "model" (SMT2020's groups and the layout file), "assumed", or
"cited: <source>". The sheets, the DXF and the IFC are all drawn from this, so they never disagree.
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab.
"""

TRUTH = "From the SMT2020 testbed. A layout of our own design. Not a real fab."
STATUS = "Concept for review, NOT FOR CONSTRUCTION"
GRID = 12.0          # assumed column grid
WALL = 0.3           # assumed wall thickness
COLUMN = 0.6         # assumed column size
FILTER = 0.35        # assumed filter ceiling depth
RAIL_W, RAIL_H = 0.15, 0.1   # assumed rail section
# Sizes and their sources, from docs/FAB-LOOK.md.
CITED = {
    "furnace": "cited: Koyo Thermo Systems VF5300 table as reproduced by Kiel University, Electronic Materials ch. 6 "
               "(secondary), 3.0 m2 a tube; height assumed",
    "implanter": "cited: used Purion M listing, mainframe 360 x 810 x 310 cm, labelled an estimate (secondary)",
}


def building(S, p):
    return [c for c in S["campus"] if c["kind"] == "fab"][p]


def phase_of_x(S, x):
    return 1 if x >= S["offsets"][1] - 1e-6 else 0


def grid_lines(S):
    """The assumed 12 m column grid: x lines per building from its west wall (and its east wall), y lines from each
    spine edge outward to the bays' end."""
    xs = []
    for p in (0, 1):
        b = building(S, p)
        x = b["x0"]
        while x <= b["x1"] + 1e-6:
            xs.append(round(x, 3))
            x += GRID
        if abs(xs[-1] - b["x1"]) > 1e-6:
            xs.append(round(b["x1"], 3))
    half = S["spine"] / 2
    ys = []
    y = half
    while y <= half + S["depth"] + 1e-6:
        ys += [round(y, 3), round(-y, 3)]
        y += GRID
    return xs, sorted(ys, reverse=True)


def _box(x0, y0, z0, x1, y1, z1):
    return (min(x0, x1), min(y0, y1), z0, max(x0, x1), max(y0, y1), z1)


def build(S):
    """Return the model: buildings with their storeys, and a flat list of elements in a fixed order."""
    fl = {x["name"]: x for x in S["floors"]}
    top = S["floors"][-1]["z1"]
    clean = "cleanroom"
    blds = []
    for p in (0, 1):
        b = building(S, p)
        blds.append({"key": f"P{p + 1}", "name": b["label"], "x0": b["x0"], "x1": b["x1"], "y0": b["y0"], "y1": b["y1"]})
    E = []

    def add(key, cls, name, box=None, bld=None, storey=None, otype=None, pre=None, frm="assumed", tool=None, rail=None):
        E.append({"key": key, "cls": cls, "name": name, "box": box, "bld": bld, "storey": storey, "otype": otype,
                  "pre": pre, "from": frm, "tool": tool, "rail": rail})

    xs, ys = grid_lines(S)
    for p, b in enumerate(blds):
        t = WALL
        k = b["key"]
        add(f"{k}/wall/S", "IfcWall", f"{b['name']}, south wall", _box(b["x0"], b["y0"], 0, b["x1"], b["y0"] + t, top), p, "support floor", pre="SOLIDWALL")
        add(f"{k}/wall/N", "IfcWall", f"{b['name']}, north wall", _box(b["x0"], b["y1"] - t, 0, b["x1"], b["y1"], top), p, "support floor", pre="SOLIDWALL")
        add(f"{k}/wall/W", "IfcWall", f"{b['name']}, west wall", _box(b["x0"], b["y0"] + t, 0, b["x0"] + t, b["y1"] - t, top), p, "support floor", pre="SOLIDWALL")
        add(f"{k}/wall/E", "IfcWall", f"{b['name']}, east wall", _box(b["x1"] - t, b["y0"] + t, 0, b["x1"], b["y1"] - t, top), p, "support floor", pre="SOLIDWALL")
        n = 0
        for x in xs:
            if not (b["x0"] - 1e-6 <= x <= b["x1"] + 1e-6):
                continue
            for y in ys:
                h = COLUMN / 2
                cx = min(max(x, b["x0"] + h), b["x1"] - h)
                add(f"{k}/col/{n}", "IfcColumn", f"{b['name']}, column {n + 1}",
                    _box(cx - h, y - h, 0, cx + h, y + h, fl["support floor"]["z1"]), p, "support floor", pre="COLUMN")
                n += 1
        ws, rf, cl, rr = fl["waffle slab"], fl["raised floor"], fl[clean], fl["roof"]
        add(f"{k}/waffle", "IfcSlab", f"{b['name']}, waffle slab", _box(b["x0"], b["y0"], ws["z0"], b["x1"], b["y1"], ws["z1"]), p, "waffle slab", pre="FLOOR")
        add(f"{k}/raised", "IfcCovering", f"{b['name']}, raised floor", _box(b["x0"], b["y0"], rf["z0"], b["x1"], b["y1"], rf["z1"]), p, "raised floor", pre="FLOORING")
        add(f"{k}/filters", "IfcCovering", f"{b['name']}, filter ceiling", _box(b["x0"], b["y0"], cl["z1"], b["x1"], b["y1"], cl["z1"] + FILTER), p, clean, pre="CEILING")
        add(f"{k}/roof", "IfcSlab", f"{b['name']}, roof", _box(b["x0"], b["y0"], rr["z0"], b["x1"], b["y1"], rr["z1"]), p, "roof", pre="ROOF")
        add(f"{k}/spine", "IfcSpace", f"Spine, phase {p + 1}", _box(b["x0"], -S["spine"] / 2, cl["z0"], b["x1"], S["spine"] / 2, cl["z1"]), p, clean, pre="INTERNAL")
    for i, bay in enumerate(S["bays"]):
        name = S["areas"][bay["area"]]["name"]
        add(f"bay/{i}", "IfcSpace", f"Bay {i + 1:02d} {name}", _box(bay["x0"], bay["y0"], fl[clean]["z0"], bay["x1"], bay["y1"], fl[clean]["z1"]),
            bay["phase"], clean, pre="INTERNAL", frm="model")
    for i, t in enumerate(S["tools"]):
        g = S["groups"][t["g"]]
        K = S["kinds"][t["kind"]]
        src = CITED.get(t["kind"], "assumed")
        add(f"tool/{i}", "IfcBuildingElementProxy", f"{g['name']} #{i}", _box(t["x0"], t["y0"], S["clean_z"], t["x1"], t["y1"], S["clean_z"] + t["h"]),
            phase_of_x(S, t["x0"]), clean, otype=t["kind"], pre="USERDEFINED", frm=src,
            tool={"SceneIndex": i, "ToolGroup": g["name"], "Area": g["area"], "Kind": t["kind"], "Bay": t["bay"],
                  "Width": t["x1"] - t["x0"], "Depth": t["y1"] - t["y0"], "Height": t["h"], "LoadPorts": K["ports"],
                  "SizeSource": src})
    hs = S["kinds"]["stocker"]["h"]
    for i, st in enumerate(S["stockers"]):
        add(f"stocker/{i}", "IfcBuildingElementProxy", f"Stocker {i + 1}", _box(st["x0"], st["y0"], S["clean_z"], st["x1"], st["y1"], S["clean_z"] + hs),
            phase_of_x(S, st["x0"]), clean, otype="stocker", pre="USERDEFINED")
    for i, (a, c) in enumerate(S["rails"]):
        add(f"rail/{i}", "IfcBuildingElementProxy", f"Hoist rail {i + 1}", None, phase_of_x(S, min(a[0], c[0])), clean,
            otype="hoist rail", pre="USERDEFINED", rail=(tuple(a), tuple(c)))
    for c in S["campus"]:
        if c["kind"] == "fab":
            continue
        z0 = c.get("z0", 0.0)
        add(f"campus/{c['name']}", "IfcBuildingElementProxy", c["label"] or c["name"], _box(c["x0"], c["y0"], z0, c["x1"], c["y1"], z0 + c["h"]),
            None, None, otype=f"campus {c['kind'].replace('_', ' ')}", pre="USERDEFINED")
    return {"truth": TRUTH, "status": STATUS, "floors": S["floors"], "buildings": blds, "elements": E}
