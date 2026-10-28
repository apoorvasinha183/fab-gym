# A bill of materials from the BIM

Written 28 October 2026, before the code. A gigafab-style layout of our own design on the SMT2020 model; not a
real fab. NOT FOR CONSTRUCTION.

## What it does

`viz/bim/bom.py --ifc FILE --out DIR` reads the faithful construction-documents IFC (`docs/BIM-FAITHFUL.md`) and
counts what it holds, without meshing anything. Every shape in that IFC is an extruded profile or a placed copy of
one, so the quantities are exact for the modelled shapes:

- **Lengths** (metres) for linear things: pipe segments, duct segments, cable trays, beams, members, columns,
  reinforcing bars, railings. Length is the sum of the extrusion depths.
- **Volumes** (cubic metres) for footings, slabs, walls, plates, stair flights and coverings other than floor
  tiles: profile area times extrusion depth. Areas of rectangles, circles, I and U sections (fillets ignored) and
  closed polylines (shoelace).
- **Counts** (each) for everything else, and for repeats: each placed copy (IFC mapped item) is one unit, so a
  sprinkler array of 140 heads counts 140.

Each line groups elements by section (structure, architecture, mechanical, piping, fire, electrical, process
equipment), IFC class, type (ObjectType, else PredefinedType), material and size: the profile for linear things
(a circle's diameter, a rectangle's sides, an I or U section's depth and width), a door's width and height.

## Output

- `bom.json`: the truth line, the source IFC's name and SHA-256, units, and the lines (section, class, type,
  material, size, unit, quantity, elements, units, volume_m3).
- `bom.csv`: the same lines.
- `bom.md`: a summary by section and the full table.

The same IFC gives the same bytes every run.

## What it leaves out

Pipes and ducts are modelled as solid sections, so their "volume" is not material; only their lengths and sizes
matter. No fittings, supports beyond those modelled, waste allowance, spares or prices. Process tools are listed by
kind as equipment, not as building material.

## Tests (`viz/tests/test_bom.py`)

1. Every element with a shape is in exactly one line.
2. Units add up: one per element, or one per placed copy.
3. Pipe length equals the sum of the pipes' extrusion depths; footing volume equals the sum of width times length
   times depth.
4. Fan filter units count 38,546, as in the faithful BIM.
5. Units and sections come from the stated sets; the CSV has one row per line; the summary carries the truth line;
   the same IFC gives the same bytes twice.
