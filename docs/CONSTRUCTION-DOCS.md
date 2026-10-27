# Construction documents: one lithography bay to fabrication detail

A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. Every sheet stays NOT FOR
CONSTRUCTION; a permit still needs a real site and the seals of licensed people.

This builds on `docs/DESIGN-DEV.md`. Decided by quiz on 28 Oct 2026:

- **How far:** one bay to fabrication detail (LOD 400), as the sample the rest would follow. The bay is lithography
  bay 09 in phase 1 (north side, 30 scanners and tracks), with its two chases, the sub-fab under it, its valve
  boxes and its gas room.
- **Site:** published hazard values for a point near Salem in the Willamette Valley, Oregon (44.9 N, 123.0 W,
  rounded to 0.1 degree). The lot stays hypothetical; soil (site class D) and utilities stay assumed. The set names
  the region only, never a parcel or a company.
- **Standards:** NFPA 13, 70 and 72 are read in NFPA's free reader in the founder's browser session once the founder
  has signed in. Until then the rules that rest on them say cannot say.
- **When:** now.

Live timeline: a private plan page

## How it runs

    .venv/bin/python viz/permit/run.py --place us --stage cd [--out data/layout-real-dd/permit-cd/us] [--no-pdf]

`--stage cd` runs design development, then the passes below on the bay. The earlier stages are unchanged. The
profile's `permit.cd` block names the bay, the site register (`viz/permit/codes/us-site-willamette.json`), the
rules (`viz/permit/rules/us-cd.json`) and the items (`viz/permit/items-cd.json`).

## CD1 Site values

- **Seismic:** the USGS design values for ASCE 7-22 (risk category IV, site class D assumed), queried on 28 Oct
  2026 at `earthquake.usgs.gov/ws/building-codes/asce7-22/calculate`. The register keeps the values, the query and
  the SHA-256 of the response. The values: SS 0.93, S1 0.38, SDS 0.80, SD1 0.54, seismic design category D.
  They replace the assumed seismic values for this stage.
- **Wind and snow:** stay assumed with their ranges. The free public service (ATC Hazards by Location) was down on
  28 Oct, and ASCE's hazard tool needs an account.
- **Seismic design:** ASCE 7's procedures are still not read, so the seismic and wind rules stay cannot say. The
  design values are shown on S-001 and S-510 with their source.

## CD2 Structure in the bay, LOD 400

- Every support-floor column under the bay gets a base plate and four anchor rods (sizes assumed).
- Its footing gets a bottom mat of reinforcement, sized from the footing's bending at an assumed steel stress.
- The waffle slab under the bay is drawn as its ribs (assumed 0.9 m deep at 1.5 m centres).
- The roof trusses over the bay are drawn as top chord, bottom chord and webs, replacing the truss envelopes.
- Every member stays preliminary, for licensed review.

## CD3 Architecture in the bay, LOD 400

- **Raised floor:** 600 mm tiles over the whole bay, perforated along the aisle (assumed), together covering the
  bay within 1%.
- **Fan filter units:** placed one by one, 1.2 x 0.6 m, at each array's coverage, replacing the arrays over the bay.
- **Chase partitions:** as panels at most 1.2 m wide.
- **Chase doors:** a hardware set in the schedule.

## CD4 Services in the bay, LOD 400

- **Drops:** each tool's combined drop is replaced by one drop per utility it needs, sized by its own flow. Each
  pipe drop has an isolation valve below the waffle slab, and each tool has a power feeder.
- **Hangers:** the laterals under the bay hang from the waffle slab, at most 2.4 m apart (assumed; MSS SP-58 is
  not read).
- **Gas lines:** each tool that draws a hazardous gas gets a double-contained line from that gas's valve box.
- **Clearances:** nothing the passes add stands in a tool's service clearance (from its card) on the clean floor.

## CD5 to CD7 NFPA

- **Reading:** once the founder has signed in, the needed sections of NFPA 13 (sprinkler spacing and pipe
  schedules for the hazard), NFPA 72 (detector and notification spacing) and NFPA 70 (conductor ampacity) are read
  and hashed, as before, into `viz/permit/codes/us-nfpa.json`.
- **Sprinklers:** heads one by one at the allowed spacing, with the branch lines sized.
- **Alarm:** detectors and appliances spaced as NFPA 72 asks.
- **Electrical:** each tool feeder's conductor within its ampacity.
- **Until the reading is done:** the heads, detectors and feeders are drawn on assumed spacing and sizes, and their
  rules say cannot say.

## CD8 Coordination at LOD 400

- The same clash check as before, with four new known joints:
  - a base plate on its column and footing;
  - reinforcement and ribs inside their footing or slab;
  - a valve on its pipe;
  - the bay's tiles inside the raised floor.
- The gate is zero hard clashes and zero elements in a tool's service clearance. The IFC is valid and the same
  bytes every run.

## CD9 The documents

- **Sheets:** design development's 37, then A-110, A-130, A-610, S-110, S-510, M-110, PP-110, E-110, FP-110 and
  FA-110:

  | Sheet | Shows |
  |---|---|
  | A-110 | Bay floor plan: tiles, panels, doors |
  | A-130 | Bay ceiling plan: fan filter units |
  | A-610 | Bay schedules: tiles, panels, door hardware |
  | S-110 | Bay framing: columns, base plates, ribs, trusses |
  | S-510 | Structural details: base plate, footing mat, truss joint, the site values |
  | M-110 | Bay sub-fab: laterals and hangers |
  | PP-110 | Bay process piping: drops, valves, gas lines |
  | E-110 | Bay power: feeders |
  | FP-110 | Bay sprinklers |
  | FA-110 | Bay alarm and detection |

- **Specifications:** in three parts (Part 1 General, Part 2 Products, Part 3 Execution) for the divisions the bay
  uses. Products are named by kind and performance, never by maker.
- **Ledger:** adds the bay's items, and none is missing.

## Checks

`viz/tests/test_cd.py`:

- **Data:**
  - the site register (the USGS query, its values and hash; wind and snow assumed with the reason);
  - the profile block, the rules and the items.
- **The run:**
  - the site values in the design data;
  - LOD 400 on the bay's elements;
  - a base plate and anchors on every column under the bay, and a mat in every footing;
  - truss members replacing the envelopes;
  - tile coverage, fan filter coverage, panel widths;
  - a drop and valve per utility per tool, and a feeder per tool;
  - hanger spacing, a gas line per tool per hazardous gas, no element in a service clearance;
  - the NFPA rules: met or not met once NFPA is read, cannot say before;
  - zero clashes, a valid IFC, the same bytes twice;
  - 47 sheets with the truth line and NOT FOR CONSTRUCTION;
  - three-part specifications, a ledger with nothing missing, the PDF's pages.

## Changes

- 28 Oct, before any construction documents code: the data test read the profile's paths from `viz/permit` instead
  of the repo root (fixed). Two more sections were read for the detail checks to cite: IBC 107.2.1 and 107.2.2
  (what construction documents and fire protection shop drawings show), and IBC 1603.1 and 1603.1.5 (structural
  and earthquake design data on the documents), in `viz/permit/codes/us-2024-cd.json`.
- 28 Oct, before any construction documents code: the services test asked an isolation valve on every drop; the spec
  asks one on every pipe drop, so exhaust duct drops (which take no valve, and never a damper on hazardous exhaust)
  are left out of that check.
