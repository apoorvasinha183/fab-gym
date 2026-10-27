"""Placement for design development (docs/DESIGN-DEV.md, DD10): every element the design development passes add is
checked, before it is added, against everything already in the model and the hoist vehicles' path. A spot is free when
nothing overlaps it by more than 0.0001 m3 except a known joint (the same joints D8 counts), so the clash check at the
end has nothing to find. The first free candidate wins; when none is free the pass stops and says where.
"""

from arch import rail_envelopes
from coord import joint
from geom import overlap

CELL = 12.0
TOL = 1e-4


class Index:
    def __init__(self, C):
        self.C = C
        self.items = []
        self.grid = {}
        for e in C.M["elements"]:
            if e["box"] is not None:
                self._add(e)
        for i, b in enumerate(rail_envelopes(C.S)):
            self._add({"key": f"hoist/{i}", "cls": "hoist path", "name": "", "box": b, "otype": None})
        for e in C.new:
            self._add(e)

    def _add(self, e):
        n = len(self.items)
        self.items.append(e)
        x0, y0, _, x1, y1, _ = e["box"]
        for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                self.grid.setdefault((i, j), []).append(n)

    def near(self, box):
        x0, y0, _, x1, y1, _ = box
        seen = set()
        for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                for n in self.grid.get((i, j), ()):
                    if n not in seen:
                        seen.add(n)
                        yield self.items[n]

    def hits(self, box, cls="IfcBuildingElementProxy", name="", otype=None, strict=False, allow=None):
        """What a box at this spot would clash with: elements overlapping it that are not a known joint (with strict,
        joints do not count either, except what allow accepts)."""
        probe = {"key": "permit/probe", "cls": cls, "name": name, "box": box, "otype": otype}
        out = []
        for o in self.near(box):
            if overlap(box, o["box"]) <= TOL:
                continue
            if o["cls"] == "hoist path":
                out.append(o)
                continue
            if allow and allow(o):
                continue
            if not strict and joint(probe, o):
                continue
            out.append(o)
        return out

    def free(self, box, **kw):
        return not self.hits(box, **kw)

    def add(self, key, cls, name, box, bld, storey, pre, otype=None, **kw):
        e = self.C.add(key, cls, name, box, bld, storey, pre, otype, **kw)
        self._add(e)
        return e

    def place(self, key, cls, name, boxes, bld, storey, pre, otype=None, need=True, check=None, **kw):
        """Add the element at the first free box of the candidates. Returns the element, or None (need=False)."""
        tried = 0
        for b in boxes:
            tried += 1
            b = tuple(round(v, 4) for v in b)
            if self.free(b, cls=cls, name=name, otype=otype, **(check or {})):
                return self.add(key, cls, name, b, bld, storey, pre, otype, **kw)
        if need:
            raise SystemExit(f"design development: no free spot for {key} ({cls}) after {tried} tries")
        return None


def around(x, y, steps=(0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0)):
    """Candidate offsets around a point, nearest first."""
    pts = [(x + dx, y + dy) for dx in steps for dy in steps]
    return sorted(pts, key=lambda p: (abs(p[0] - x) + abs(p[1] - y), p))
