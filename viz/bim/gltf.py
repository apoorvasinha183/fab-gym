"""The IFC model's structure as glTF (docs/BIM-3D.md): IfcOpenShell triangulates each wall, column, slab and
covering; this writes them as one GLB with the standard library, one node per element, Y up, in metres.

    .venv/bin/python viz/bim/gltf.py [--ifc data/layout-real/blueprint/intl/fab-model.ifc]
        [--out data/layout-real/bim/fab-building.glb] [--all]

--all (docs/BIM-FAITHFUL.md) writes every element of the faithful BIM: site, buildings, storeys and elements as one tree,
every property set in the node's extras, one primitive per material named after the IFC's, and each repeat once with
EXT_mesh_gpu_instancing. The same IFC gives the same bytes. A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab.
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
    ("IfcWall", "PARTITIONING"): ("bim_wall", (0.84, 0.85, 0.87)),
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
        "source": Path(ifc_path).name, "note": "Structure of the IFC model, Y up, metres. From the SMT2020 testbed. "
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


def flat(pos3):
    """Flat-shaded triangles in glTF axes from world triangles (n, 3, 3) in IFC axes."""
    import numpy as np
    p = pos3[:, :, [0, 2, 1]].copy()
    p[:, :, 2] *= -1
    p = p.astype("<f4").astype(float)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    L = np.linalg.norm(n, axis=1, keepdims=True)
    L[L == 0] = 1.0
    n = np.round(n / L, 6) + 0.0
    return p.reshape(-1, 3), np.repeat(n, 3, axis=0)


def quat(R):
    """A unit quaternion (x, y, z, w) from a rotation matrix."""
    import math as m
    tr = R[0][0] + R[1][1] + R[2][2]
    if tr > 0:
        s = m.sqrt(tr + 1.0) * 2
        q = ((R[2][1] - R[1][2]) / s, (R[0][2] - R[2][0]) / s, (R[1][0] - R[0][1]) / s, 0.25 * s)
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        s = m.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2]) * 2
        q = (0.25 * s, (R[0][1] + R[1][0]) / s, (R[0][2] + R[2][0]) / s, (R[2][1] - R[1][2]) / s)
    elif R[1][1] > R[2][2]:
        s = m.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2]) * 2
        q = ((R[0][1] + R[1][0]) / s, 0.25 * s, (R[1][2] + R[2][1]) / s, (R[0][2] - R[2][0]) / s)
    else:
        s = m.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1]) * 2
        q = ((R[0][2] + R[2][0]) / s, (R[1][2] + R[2][1]) / s, 0.25 * s, (R[1][0] - R[0][1]) / s)
    return tuple(round(c, 7) + 0.0 for c in q)


def write_all(ifc_path, out):
    """Every element of the IFC as glTF (docs/BIM-FAITHFUL.md)."""
    import multiprocessing
    import numpy as np
    import ifcopenshell.util.placement as upl
    f = ifcopenshell.open(str(ifc_path))
    blob = bytearray()
    views, accessors, meshes, nodes, mats = [], [], [], [], {}

    def view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            v["target"] = target
        views.append(v)
        blob.extend(data)
        return len(views) - 1

    def accessor(arr, kind, target=34962, bounds=False):
        arr = np.ascontiguousarray(arr, dtype="<f4")
        a = {"bufferView": view(arr.tobytes(), target), "componentType": 5126, "count": int(arr.shape[0]), "type": kind}
        if bounds:
            a["min"] = [float(x) for x in arr.min(0)]
            a["max"] = [float(x) for x in arr.max(0)]
        accessors.append(a)
        return len(accessors) - 1

    def mat(name):
        if name not in mats:
            mats[name] = len(mats)
        return mats[name]

    style_of = {}

    def item_style(i):
        if i not in style_of:
            it = f.by_id(i)
            st = it.StyledByItem[0].Styles[0] if it.StyledByItem else None
            style_of[i] = st.Name if st is not None else "unstyled"
        return style_of[i]

    colours = {}
    for st in f.by_type("IfcSurfaceStyle"):
        for x in st.Styles:
            if x.is_a("IfcSurfaceStyleShading"):
                c = x.SurfaceColour
                colours[st.Name] = (c.Red, c.Green, c.Blue)

    def mesh(name, tris_by_mat):
        prims = []
        for m in sorted(tris_by_mat):
            pos, nrm = flat(np.asarray(tris_by_mat[m], dtype=float).reshape(-1, 3, 3))
            prims.append({"attributes": {"POSITION": accessor(pos, "VEC3", bounds=True), "NORMAL": accessor(nrm, "VEC3")},
                          "material": mat(m), "mode": 4})
        meshes.append({"name": name, "primitives": prims})
        return len(meshes) - 1

    def is_mapped(e):
        its = [it for r in e.Representation.Representations for it in r.Items] if e.Representation else []
        return bool(its) and all(it.is_a("IfcMappedItem") for it in its)

    prods = sorted((e for e in f.by_type("IfcProduct") if e.Representation and not e.is_a("IfcOpeningElement")), key=lambda e: e.GlobalId)
    aggs = sorted((e for e in f.by_type("IfcElement") if not e.Representation and e.IsDecomposedBy), key=lambda e: e.GlobalId)
    # solids: IfcOpenShell's triangles in world coordinates, openings cut, faces sorted to their materials
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    plain = [e for e in prods if not is_mapped(e)]
    geo = {}
    it = ifcopenshell.geom.iterator(s, f, min(4, multiprocessing.cpu_count()), include=plain)
    if it.initialize():
        while True:
            sh = it.get()
            g = sh.geometry
            v = np.asarray(g.verts, dtype=float).reshape(-1, 3)
            fc = np.asarray(g.faces, dtype=int).reshape(-1, 3)
            ids = list(g.item_ids)
            by = {}
            for k, tri in enumerate(fc):
                by.setdefault(item_style(ids[k]) if k < len(ids) else "unstyled", []).append(v[tri])
            geo[sh.guid] = by
            if not it.next():
                break
    # repeats: each map triangulated once in its own coordinates
    ls = ifcopenshell.geom.settings()
    map_mesh = {}

    def map_index(rm):
        if rm.id() not in map_mesh:
            by = {}
            for item in rm.MappedRepresentation.Items:
                g = ifcopenshell.geom.create_shape(ls, item)
                v = np.asarray(g.verts, dtype=float).reshape(-1, 3)
                for tri in np.asarray(g.faces, dtype=int).reshape(-1, 3):
                    by.setdefault(item_style(item.id()), []).append(v[tri])
            map_mesh[rm.id()] = mesh(f"map_{rm.id()}", by)
        return map_mesh[rm.id()]

    P = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)        # IFC (x, y, z) to glTF (x, z, -y)

    def extras(e):
        x = {"GlobalId": e.GlobalId, "Name": e.Name or "", "Class": e.is_a(),
             "PredefinedType": str(getattr(e, "PredefinedType", "") or ""), "ObjectType": getattr(e, "ObjectType", None) or "",
             "Storey": ""}
        c = uel.get_container(e)
        if c is None and getattr(e, "Decomposes", None):
            up = e.Decomposes[0].RelatingObject
            c = up if up.is_a("IfcSpatialStructureElement") else uel.get_container(up)
        x["Storey"] = c.Name if c is not None and c.is_a("IfcBuildingStorey") else ""
        for pset, props in sorted(uel.get_psets(e).items()):
            for k, val in sorted(props.items()):
                if k != "id":
                    x[f"{pset}.{k}"] = val
        return x

    index = {}

    def add_node(e, children=None):
        nodes.append({"name": f"{e.is_a()}_{e.GlobalId}", "extras": extras(e), "children": children or []})
        index[e.GlobalId] = len(nodes) - 1
        return len(nodes) - 1

    for e in prods + aggs:
        n = add_node(e)
        if e.GlobalId in geo:
            nodes[n]["mesh"] = mesh(nodes[n]["name"], geo[e.GlobalId])
        elif e.Representation and is_mapped(e):
            Pl = upl.get_local_placement(e.ObjectPlacement)
            groups = {}
            for item in [i for r in e.Representation.Representations for i in r.Items]:
                M = Pl @ upl.get_mappeditem_transformation(item)
                groups.setdefault(item.MappingSource.id(), (item.MappingSource, []))[1].append(M)
            for rid, (rm, Ms) in sorted(groups.items()):
                tr = np.array([P @ M[:3, 3] for M in Ms])
                rot = np.array([quat(P @ M[:3, :3] @ P.T) for M in Ms])
                at = {"TRANSLATION": accessor(tr, "VEC3", target=None)}
                if np.abs(rot - np.array([0, 0, 0, 1.0])).max() > 1e-9:
                    at["ROTATION"] = accessor(rot, "VEC4", target=None)
                nodes.append({"name": f"{nodes[n]['name']}_repeats", "mesh": map_index(rm),
                              "extensions": {"EXT_mesh_gpu_instancing": {"attributes": at}}})
                nodes[n]["children"].append(len(nodes) - 1)
    # the tree: site, buildings, storeys, then elements by container or aggregate
    for c in ("IfcSite", "IfcBuilding", "IfcBuildingStorey"):
        for e in sorted(f.by_type(c), key=lambda e: e.GlobalId):
            add_node(e)
    roots = []
    for e in prods + aggs + [x for c in ("IfcSite", "IfcBuilding", "IfcBuildingStorey") for x in sorted(f.by_type(c), key=lambda x: x.GlobalId)]:
        up = None
        if getattr(e, "Decomposes", None):
            up = e.Decomposes[0].RelatingObject
        elif getattr(e, "ContainedInStructure", None):
            up = e.ContainedInStructure[0].RelatingStructure
        if up is None or up.is_a("IfcProject"):
            roots.append(index[e.GlobalId])
        else:
            nodes[index[up.GlobalId]]["children"].append(index[e.GlobalId])
    for nd in nodes:
        if "children" in nd:
            if nd["children"]:
                nd["children"] = sorted(nd["children"], key=lambda i: nodes[i]["name"])
            else:
                del nd["children"]
    nodes.append({"name": "fab_bim", "children": roots, "extras": {
        "source": Path(ifc_path).name, "note": "Every element of the faithful BIM, Y up, metres. From the SMT2020 testbed. "
                                               "A layout of our own design. Not a real fab. NOT FOR CONSTRUCTION."}})
    blob.extend(b"\x00" * (-len(blob) % 4))
    doc = {
        "asset": {"version": "2.0", "generator": "Fab Gym viz/bim/gltf.py --all (IfcOpenShell geometry)"},
        "extensionsUsed": ["EXT_mesh_gpu_instancing"],
        "scene": 0, "scenes": [{"name": "fab_bim", "nodes": [len(nodes) - 1]}],
        "nodes": nodes, "meshes": meshes, "accessors": accessors, "bufferViews": views,
        "materials": [{"name": n, "pbrMetallicRoughness": {"baseColorFactor": [*[round(c, 6) for c in colours.get(n, (0.8, 0.8, 0.8))], 1.0],
                                                           "metallicFactor": 0.0, "roughnessFactor": 0.8}}
                      for n, _ in sorted(mats.items(), key=lambda kv: kv[1])],
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("ascii")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
                    + struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob))
    inst = sum(accessors[nd["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]["TRANSLATION"]]["count"]
               for nd in nodes if "extensions" in nd)
    return f"wrote {out}: {len(prods) + len(aggs)} elements, {inst} repeats, {len(blob) // 1024} KB of geometry"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ifc", default=str(ROOT / "data/layout-real/blueprint/intl/fab-model.ifc"))
    ap.add_argument("--out", default=str(ROOT / "data/layout-real/bim/fab-building.glb"))
    ap.add_argument("--all", action="store_true", help="every element of the faithful BIM (docs/BIM-FAITHFUL.md)")
    a = ap.parse_args()
    print(write_all(a.ifc, a.out) if a.all else write(a.ifc, a.out))


if __name__ == "__main__":
    main()
