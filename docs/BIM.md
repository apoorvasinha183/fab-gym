# BIM: one building model, drawn for any country

Written 27 Oct 2026, before the code (tests in `viz/tests/test_bim.py` and `viz/tests/test_blueprint.py`).
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. Every placement number is
assumed unless the brief cites a source. Concept for review, NOT FOR CONSTRUCTION.

The founder asked whether the fab should be BIM, and noted that both the building and its drawings change with
the country. Decided by quiz (27 Oct): an IFC model plus a cutaway sheet, built as a pipeline from the layout;
country profiles for drawing conventions now, with building codes listed as "not checked" until they are read
and cited; IfcOpenShell (LGPL, PyPI, in `.venv`) to check the IFC against the schema. No Revit licence is
needed: IFC is an open format the architect opens in their own tool, and free tools (IfcOpenShell, Bonsai,
FreeCAD) read it here. The simulation and the films stay in our engine, Blender and Godot.

## The pipeline

```
results/layout-real/layout.json ──> viz/prep.py --real ──> scene-optimised.json
                                                               │
                                          viz/blueprint/model.py  (one building model, metres)
                                                               │
               ┌──────────────────────┬────────────────────────┼────────────────────────┐
     sheets (SVG, PDF)            fab-plan.dxf              fab-model.ifc               brief.md
               └──── drawn for a country profile (viz/blueprint/places/<id>.json) ────┘
```

- `viz/blueprint/model.py` builds one model from the scene: the site, the two fab buildings and the bridge,
  their six levels, walls, columns on the 12 m grid, slabs, the raised floor and filter ceiling, the bays and
  spine as spaces, all 1,043 tools, the 5 stockers, the 135 hoist rail runs, and the campus buildings drawn
  only. Every element carries where its numbers come from: `model` (SMT2020's groups and the layout file),
  `assumed`, or a citation. Walls are 0.3 m thick (assumed, new); everything else was already in the scene.
- `viz/blueprint/places/<id>.json` is a country profile: its paper, its units and how lengths and levels are
  written, the scale of each sheet, and a list of building-code topics, each with a status. Two profiles now:
  - `intl`: metric, ISO A1 (841 x 594 mm), today's scales; the set built before this spec is this profile.
  - `us`: feet and inches, ARCH E1 (30 x 42 in), US architectural scales (A-100 1" = 200'-0", A-101 and
    A-102 1/32" = 1'-0", A-110 and the section detail 1/8" = 1'-0", A-301 1/16" = 1'-0",
    A-500 1/64" = 1'-0"), levels as EL. +24'-7".
  Codes on both: seismic design, fire and hazardous-materials occupancy, exits and egress, hazardous gas
  storage, cleanroom classification and air, accessibility. Every one is "not checked": no code has been read
  for this set, so the drawings change nothing for them, and A-000 and the brief say so.
- `viz/blueprint/ifc.py` writes `fab-model.ifc` (IFC4, metres) with the standard library: one project, one
  site, a building per phase with a storey per level, walls, slabs, coverings, columns, spaces, and tools,
  stockers, rails and campus buildings as proxies typed by kind. Each tool carries a property set
  `FabGym_Tool` (its index in the scene, tool group, area, kind, bay, width, depth, height, load ports,
  where its size comes from);
  every element and space carries `FabGym_Basis` (Basis: "From the SMT2020 testbed. A layout of our own design.
  Not a real fab."; Status: "Concept for review, NOT FOR CONSTRUCTION"; NumbersFrom: `model`, `assumed` or
  `cited: <source>`). Ids are fixed from each element's name, so the file is the
  same on every run and for every profile.
- `viz/blueprint/blueprint.py --place intl|us` (default `intl`) draws the set into
  `data/layout-real/blueprint/<place>/`: the seven sheets, a new **A-500 exploded axonometric of phase 1**
  (support floor and columns, waffle slab, the clean floor with every tool, filter ceiling, roof, pulled apart
  and labelled), the PDF (eight pages), the DXF (metres for `intl`, inches for `us`), the IFC and the brief
  (with a "Building codes" section).

## Checks

- The IFC passes IfcOpenShell's schema validation with no errors and opens as IFC4.
- It holds 1 project, 1 site, 2 fab buildings with 6 storeys each at the scene's levels, 39 bay spaces and
  2 spines, 1,043 tools whose kinds and groups match the scene, 5 stockers, 135 rails, 8 walls, a column at
  every grid crossing, and every campus item.
- Sampled tools' geometry, computed by IfcOpenShell, sits where the scene puts them (to 1 mm).
- Every element has `FabGym_Basis`; ids are unique; two runs give the same bytes; both profiles give the same
  IFC.
- Both profiles give eight sheets with their paper and scales; the US set writes lengths and levels in feet and
  inches, its DXF in inches inside the site; A-000 and the brief list every code topic as not checked.
- A-500 draws every phase 1 tool once and five labelled layers.
- The PDF has eight pages of the profile's paper.
