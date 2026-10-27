# Blueprint: the campus as a drawing set for an architect

Written 27 Oct 2026, before the code (tests in `viz/tests/test_blueprint.py`).
A gigafab-style layout of our own design on the SMT2020 model; not a real fab. Every placement number is
assumed unless the brief cites a source. The set is a concept for review, marked NOT FOR CONSTRUCTION.

The founder asked for "a architecture like blueprint for the fab" to validate with an architect. Decided by
quiz (27 Oct): plan, section and site sheets plus a brief; a PDF set plus a DXF of the plan.

## What is drawn

Everything comes from the scene file the films and the explorer use (`data/layout-real/scene-optimised.json`,
written by `viz/prep.py --real` from `results/layout-real/layout.json`), so the drawings show the same campus
the simulator moves lots through. World metres: x east, y north; the origin is the west end of phase 1's
spine on its centre line; levels in metres above the support floor's slab (+0.00).

| Sheet | Title | Scale on A1 |
| --- | --- | --- |
| A-000 | Cover, drawing list and general notes | - |
| A-100 | Site plan | 1:2000 |
| A-101 | Clean floor plan, phase 1 (+7.50) | 1:500 |
| A-102 | Clean floor plan, phase 2 (+7.50) | 1:500 |
| A-110 | Enlarged plan of a typical bay | 1:100 |
| A-301 | Building section across the bays | 1:200 |
| A-900 | Brief: numbers to check and questions for the architect | - |

- Plans: the building outline, the 12 m column grid (assumed, lettered and numbered), the spine, every bay
  with its area named, every tool at its kind's size (1,043), the five stockers, the hoist rails, the bridge
  between the phases, dimension strings (phase lengths, bay depth, spine, building width), a north arrow and
  a scale bar.
- Enlarged bay: the lithography bay of phase 1 with its tools, load ports, aisle, chases and rails, dimensioned.
- Section: the six levels (support floor, waffle slab, raised floor, cleanroom, air space, roof) with
  elevation marks, the spine and a stocker, the hoist rail level, the tools cut, and plant on the roof.
- Site: both phases, the bridge, the pad for a third phase, the central utility building, ultrapure water,
  the gas yard and tanks, the office, the utility link, cooling towers, stacks, roads and parking. These are
  drawn only: the model holds none of them.
- Not drawn, and asked in the brief: exits and stairs, fire walls, gowning, sub-fab equipment, utility routes.

Each sheet has a title block: the project ("Fab Gym campus"), the sheet number and title, the scale, the date,
revision "P1 for review", the line "On the SMT2020 model. A layout of our own design. Not a real fab.",
"NOT FOR CONSTRUCTION", and the sha256 (first 12) of the layout file it was drawn from.

## Files

`python3 viz/blueprint/blueprint.py [--scene S] [--layout L] [--out DIR]` (default
`data/layout-real/blueprint/`) writes:

- `sheets/A-000.svg` ... `sheets/A-900.svg`, in millimetres on an 841 x 594 sheet (A1 landscape);
- `fab-blueprint.html`, the sheets in order, one per A1 page;
- `fab-blueprint.pdf`, printed from that page by headless Chrome when Chrome is installed (else skipped, and
  the script says so);
- `fab-plan.dxf`, AutoCAD R12 text, in metres (`$INSUNITS` 6), with layers `A-GRID`, `A-WALL`, `A-SPINE`,
  `A-BAY`, `A-EQPM`, `A-STKR`, `A-OHT`, `A-ANNO`, `A-SITE`: every tool a closed polyline on `A-EQPM`;
- `brief.md`, the brief as text (the same words as A-900).

The script uses the standard library only. The output is the same byte for byte on every run.

## Checks

- All sheets are written; each has the title block's words and a scale where it has one.
- The two floor plans draw every tool once (1,043 in all, split by phase as the scene says), every bay (39) and
  every stocker (5); a plan's scale bar is as long as its scale says.
- The section marks the six levels at the scene's heights and the rail at +11.70.
- The DXF holds the layers, every tool on `A-EQPM`, metres as units, and coordinates inside the site.
- The brief names every assumed number (layout and look), marks which are cited, and asks at least eight
  numbered questions.
- The PDF, when made, has seven A1 pages.
- Two runs give identical files.
