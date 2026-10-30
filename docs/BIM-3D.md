# BIM to 3D: the IFC model in the viewer and the film

Written 27 Oct 2026, before the code (tests in `viz/tests/test_bim_gltf.py` and `viz/tests/test_explore.py`).
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. Concept for review, NOT FOR
CONSTRUCTION.

The founder's pipeline: blueprint, BIM, Blender for the render, Godot for the interactive view. Decided by quiz
(27 Oct): the IFC model, converted to glTF with IfcOpenShell, replaces the hand-built building structure in the
Godot viewer and then in the Blender film scene, so the drawings, the IFC, the viewer and the film share one
model. Unity is not used (it needs an account).

## What comes from the IFC and what stays

The IFC holds the structure: walls, columns, slabs (waffle slab, roof), the raised floor and the filter
ceiling. Those come from the IFC. The tools, stockers, rails, lots and the campus outside the fab buildings stay
drawn from the scene file with their detailed parts, as now: their places already match the IFC (checked to
1 mm in `viz/tests/test_bim.py`), and the IFC holds them only as boxes. The dressing that BIM does not model
(sub-fab pumps and scrubbers, ducts and pipes, the plenum's yellow lines, bay walls and signs, per-bay fan filter
faces, air-space trusses, roof plant, lamps) stays in the viewer, placed to fit the IFC's structure.

One change follows: the viewer's support-floor columns stood 3 m off the grid the drawings use. They now come
from the IFC, on the drawings' 12 m grid (assumed), so the viewer, the drawings and the IFC agree.

## The pipeline

```
fab-model.ifc ──> viz/bim/gltf.py (IfcOpenShell geometry, our own GLB writer) ──> fab-building.glb
                                                         │
                         viz/godot-real/bim/building.tscn  (instances the GLB, materials by name)
                         viz/blender/real.py (later: imports the GLB, materials by name)
```

- `viz/bim/gltf.py --ifc data/layout-real/blueprint/intl/fab-model.ifc --out data/layout-real/bim/fab-building.glb`
  (runs in `.venv`). IfcOpenShell triangulates every IfcWall, IfcColumn, IfcSlab and IfcCovering in world
  coordinates; the script writes a GLB (glTF 2.0, binary) with the standard library:
  - one node and one mesh per element, sorted by GlobalId, named `<Class>_<GlobalId>` (for example
    `IfcColumn_2xT...`); node `extras` carry GlobalId, Name, Class, PredefinedType, Storey, and from
    `FabGym_Basis` its Basis, Status and NumbersFrom;
  - axes: glTF is Y up, so IFC (x, y, z) is written (x, z, -y), the viewer's own mapping (`w()` in `main.gd`);
    metres throughout;
  - one material per kind of element, by name: `bim_wall`, `bim_column`, `bim_slab_floor`, `bim_slab_roof`,
    `bim_covering_flooring`, `bim_covering_ceiling`; plain colours in the file, replaced by the viewer's and the
    film's own materials;
  - the same bytes on every run; ASCII names.
- `viz/godot-real/bim/building.tscn` instances `res://data/fab-building.glb` (copied by `sync.sh`), with
  `bim/building.gd` (thin: materials by name, a box collider per element from its mesh's bounds, provenance from
  the extras as node metadata). Materials are saved resources in `viz/godot-real/bim/materials/<name>.tres`.
  Walls use `bim/wall_cut.gdshader`, which hides everything above a global height `bim_cut_z`, so the viewer's
  cut-away (key C or 4) still opens the building above the cleanroom; the roof and filter ceiling hide as before.
- `main.gd` instances `res://bim/building.tscn` and no longer builds the support-floor slab and columns, the
  waffle slab, the plenum and raised floor, the filter ceiling's top, the roof slab or the facade walls itself.
  Its floor and wall colliders for walking come from the building scene; bay walls keep their own.
- Blender (after the visitor film finishes on the mini): `real.py` imports the same GLB for the structure and
  keeps its dressing and materials. Its film shots peel the facade away by height bands, so its tests and the
  way the walls are split are written then, before that code.

## Checks

- `test_bim_gltf.py` (`.venv`): the GLB parses; one node for every wall, column, slab and covering in the IFC and
  nothing else; each node's bounds equal the element's bounds from IfcOpenShell, mapped to Y up, within 1 mm,
  and the building model's boxes (`model.py`); extras and materials as above; the same bytes twice; no brand names.
- `test_explore.py`: the project holds the building scene, its script, the six materials and the wall shader;
  `main.gd` instances the building and no longer types the structure in; `sync.sh` copies the GLB. The headless
  check (run with `GODOT`) reports the building's nodes by class, which equal the IFC's, sampled element bounds in
  Godot, which equal the model's within 1 mm, the cut height on and off, and walking still stops at a tool on the
  IFC's raised floor.
