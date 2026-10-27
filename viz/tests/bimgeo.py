"""Geometry helpers for the faithful BIM's tests (docs/BIM-FAITHFUL.md): world bounds of every element from
IfcOpenShell, and the world box of every repeat an element places. Test code only; needs IfcOpenShell (.venv).
A gigafab-style layout of our own design on the SMT2020 model; not a real fab.
"""

import multiprocessing

import numpy as np

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement as upl


def items(e):
    if not e.Representation:
        return []
    return [it for r in e.Representation.Representations for it in r.Items]


def is_mapped(e):
    its = items(e)
    return bool(its) and all(it.is_a("IfcMappedItem") for it in its)


def world_bounds(f, elements, keep_verts=()):
    """{GlobalId: (lo, hi)} for elements whose bodies are solids, from IfcOpenShell in world coordinates; verts too for
    the GlobalIds in keep_verts."""
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    s.set("disable-opening-subtractions", True)
    out, verts = {}, {}
    els = [e for e in elements if e.Representation and not is_mapped(e)]
    if not els:
        return out, verts
    it = ifcopenshell.geom.iterator(s, f, min(4, multiprocessing.cpu_count()), include=els)
    if it.initialize():
        while True:
            sh = it.get()
            v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
            if len(v):
                out[sh.guid] = (v.min(0), v.max(0))
                if sh.guid in keep_verts:
                    verts[sh.guid] = v
            if not it.next():
                break
    return out, verts


_MAP_BOX = {}


def map_box(rep_map):
    """Local bounds of a representation map's items (in the map's own coordinates)."""
    if rep_map.id() not in _MAP_BOX:
        s = ifcopenshell.geom.settings()
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for it in rep_map.MappedRepresentation.Items:
            v = np.asarray(ifcopenshell.geom.create_shape(s, it).verts, dtype=float).reshape(-1, 3)
            lo, hi = np.minimum(lo, v.min(0)), np.maximum(hi, v.max(0))
        _MAP_BOX[rep_map.id()] = (lo, hi)
    return _MAP_BOX[rep_map.id()]


def instance_boxes(e):
    """World bounds of each mapped item an element places: an (n, 2, 3) array."""
    P = upl.get_local_placement(e.ObjectPlacement)
    out = []
    for it in items(e):
        lo, hi = map_box(it.MappingSource)
        corners = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        w = (P @ upl.get_mappeditem_transformation(it) @ corners.T).T[:, :3]
        out.append((w.min(0), w.max(0)))
    return np.array(out).reshape(-1, 2, 3)


def overlapping(boxes, tol=1e-4):
    """Pairs of boxes (n, 2, 3) whose insides overlap by more than tol on every axis; a grid keeps it near linear."""
    if len(boxes) < 2:
        return []
    cell = float(max((boxes[:, 1, :2] - boxes[:, 0, :2]).max(), 1e-3))
    grid = {}
    for i, (lo, hi) in enumerate(boxes):
        for gx in range(int(np.floor(lo[0] / cell)), int(np.floor(hi[0] / cell)) + 1):
            for gy in range(int(np.floor(lo[1] / cell)), int(np.floor(hi[1] / cell)) + 1):
                grid.setdefault((gx, gy), []).append(i)
    bad = set()
    for ids in grid.values():
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                i, j = ids[a], ids[b]
                lo = np.maximum(boxes[i, 0], boxes[j, 0])
                hi = np.minimum(boxes[i, 1], boxes[j, 1])
                if np.all(hi - lo > tol):
                    bad.add((min(i, j), max(i, j)))
    return sorted(bad)


def boxes_overlap(a, b, tol=1e-4):
    lo = np.maximum(np.asarray(a[0]), np.asarray(b[0]))
    hi = np.minimum(np.asarray(a[1]), np.asarray(b[1]))
    return bool(np.all(hi - lo > tol))
