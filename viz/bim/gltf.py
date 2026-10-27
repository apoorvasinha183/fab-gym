"""The IFC model's structure as glTF (docs/BIM-3D.md): IfcOpenShell triangulates each wall, column, slab and
covering; this writes them as one GLB with the standard library, one node per element, Y up, in metres.

    .venv/bin/python viz/bim/gltf.py [--ifc data/layout-real/blueprint/intl/fab-model.ifc]
        [--out data/layout-real/bim/fab-building.glb]

The same IFC gives the same bytes. A gigafab-style layout of our own design on the SMT2020 model; not a real fab.
"""

import argparse
import json
import math
import struct
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as uel

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ["IfcWall", "IfcColumn", "IfcSlab", "IfcCovering"]
# material name and its plain colour in the file; the viewer and the film put their own materials on by name
MATERIALS = {
    ("IfcWall", "SOLIDWALL"): ("bim_wall", (0.84, 0.85, 0.87)),
    ("IfcColumn", "COLUMN"): ("bim_column", (0.65, 0.64, 0.62)),
    ("IfcSlab", "FLOOR"): ("bim_slab_floor", (0.65, 0.64, 0.62)),
    ("IfcSlab", "ROOF"): ("bim_slab_roof", (0.60, 0.63, 0.66)),
    ("IfcCovering", "FLOORING"): ("bim_covering_flooring", (0.87, 0.89, 0.91)),
    ("IfcCovering", "CEILING"): ("bim_covering_ceiling", (0.95, 0.96, 0.96)),
}


def f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def triangles(shape):
    """Flat-shaded triangles in glTF axes: IFC (x, y, z) becomes (x, z, -y)."""
    v = shape.geometry.verts
    pos, nrm = [], []
    fc = shape.geometry.faces
    for i in range(0, len(fc), 3):
        p = [(v[3 * k], v[3 * k + 2], -v[3 * k + 1]) for k in fc[i:i + 3]]
        ax, ay, az = (p[1][j] - p[0][j] for j in range(3))
        bx, by, bz = (p[2][j] - p[0][j] for j in range(3))
        n = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
        L = math.sqrt(sum(c * c for c in n)) or 1.0
        n = tuple(round(c / L, 6) + 0.0 for c in n)
        for q in p:
            pos.append(tuple(f32(c) for c in q))
            nrm.append(n)
    return pos, nrm


def write(ifc_path, out):
    f = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    elems = sorted((e for c in CLASSES for e in f.by_type(c)), key=lambda e: e.GlobalId)
    mat_names = sorted({m[0] for m in MATERIALS.values()})
    mat_index = {n: i for i, n in enumerate(mat_names)}
    colour = {m[0]: m[1] for m in MATERIALS.values()}
    blob = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1

    for e in elems:
        cls = e.is_a()
        key = (cls, e.PredefinedType)
        if key not in MATERIALS:
            raise SystemExit(f"no material for {key}")
        pos, nrm = triangles(ifcopenshell.geom.create_shape(settings, e))
        pv = view(b"".join(struct.pack("<3f", *p) for p in pos), 34962)
        nv = view(b"".join(struct.pack("<3f", *n) for n in nrm), 34962)
        lo = [min(p[k] for p in pos) for k in range(3)]
        hi = [max(p[k] for p in pos) for k in range(3)]
        accessors.append({"bufferView": pv, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": lo, "max": hi})
        accessors.append({"bufferView": nv, "componentType": 5126, "count": len(nrm), "type": "VEC3"})
        name = f"{cls}_{e.GlobalId}"
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": len(accessors) - 2, "NORMAL": len(accessors) - 1},
                                                      "material": mat_index[MATERIALS[key][0]], "mode": 4}]})
        basis = uel.get_psets(e).get("FabGym_Basis", {})
        container = uel.get_container(e)
        nodes.append({"name": name, "mesh": len(meshes) - 1, "extras": {
            "GlobalId": e.GlobalId, "Name": e.Name, "Class": cls, "PredefinedType": e.PredefinedType,
            "Storey": container.Name if container else "", "Basis": basis.get("Basis", ""),
            "Status": basis.get("Status", ""), "NumbersFrom": basis.get("NumbersFrom", "")}})
    root = {"name": "fab_building", "children": list(range(len(nodes))), "extras": {
        "source": Path(ifc_path).name, "note": "Structure of the IFC model, Y up, metres. On the SMT2020 model. "
                                               "A layout of our own design. Not a real fab."}}
    nodes.append(root)
    blob.extend(b"\x00" * (-len(blob) % 4))
    doc = {
        "asset": {"version": "2.0", "generator": "Fab Gym viz/bim/gltf.py (IfcOpenShell geometry)"},
        "scene": 0, "scenes": [{"name": "fab_building", "nodes": [len(nodes) - 1]}],
        "nodes": nodes, "meshes": meshes, "accessors": accessors, "bufferViews": views,
        "materials": [{"name": n, "pbrMetallicRoughness": {"baseColorFactor": [*colour[n], 1.0], "metallicFactor": 0.0,
                                                           "roughnessFactor": 0.8}} for n in mat_names],
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("ascii")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
                    + struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob))
    return f"wrote {out}: {len(elems)} elements, {len(blob) // 1024} KB of geometry"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ifc", default=str(ROOT / "data/layout-real/blueprint/intl/fab-model.ifc"))
    ap.add_argument("--out", default=str(ROOT / "data/layout-real/bim/fab-building.glb"))
    a = ap.parse_args()
    print(write(a.ifc, a.out))


if __name__ == "__main__":
    main()
