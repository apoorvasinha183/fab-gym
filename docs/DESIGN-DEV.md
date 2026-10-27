# Design development: the permit set carried from schematic design to LOD 300

A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. Every sheet stays NOT FOR
CONSTRUCTION; a permit still needs a real site and the seals of licensed people.

This builds on `docs/PERMIT.md` (D0 to D10). Decided by quiz on 27 Oct 2026:

- **Scope:** the whole fab, every trade, at once: sized and routed ducts and pipes, sections, elevations, wall types
  and details at LOD 300.
- **The two judgements:** the stricter reading. The chases are service corridors (IBC 415.11.3) and the risk
  category is IV (Table 1604.5). Both are marked as our assumption for the authority to confirm.
- **Standards:** only free ones are read. NFPA 13, 70 and 72, ISO 14644-1, ICC A117.1, ISEA Z358.1 and ASCE 7
  stay "cannot say".
- **When:** now (the founder: "do it right now").

Live timeline: a private plan page

## How it runs

    .venv/bin/python viz/permit/run.py --place us --stage dd
        [--scene data/layout-real-permit/scene-optimised.json] [--layout results/layout-real-permit/layout.json]
        [--out data/layout-real-permit/permit-dd/us] [--no-pdf]

`--stage dd` runs D4 to D8 on the scene, then the design development passes below, then the checks, the IFC, the
sheets, the specifications, the ledger and the PDF. `--stage full` and `--stage concept` are unchanged: the
schematic set and its tests stay as committed.

The place profile's `permit.dd` block names the second register (`viz/permit/codes/us-2024-dd.json`), the design
development rules (`viz/permit/rules/us-dd.json`), the new ledger items (`viz/permit/items-dd.json`), the
judgements with their basis, and the scene and layout it runs on. In this stage the register is the union of both
registers' sections with the second register's not-read list; a rule in `us-dd.json` whose id is already in
`us.json` replaces it; the ledger is `items.json` followed by `items-dd.json`.

## DD1 The codes read

Opened in ICC's free reader on 27 Oct 2026 and hashed the same way as the first register (the section's text as
shown, whitespace collapsed, the reader's labels removed); no code text is kept. 32 sections:

| Code | Sections | For |
|---|---|---|
| IPC 2024 | 403.1, 403.2, 403.3.3, 411.1, T709.1, T710.1(1), T710.1(2) | fixtures, separate rooms, toilet travel, showers, drains |
| IBC 2024 ch. 7 | T716.1(2), 714.4.1.2, T721.1(2) item 13 | door ratings, firestops, rated wall assemblies |
| IBC 2024 ch. 9 | 905.3.1, 907.4.2.1, 907.4.2.2, 907.5.2.1.1, 907.5.2.3.1 | standpipes, alarm boxes, notification |
| IBC 2024 ch. 10 | 1008.3.1, 1008.3.2, 1009.1, 1009.2.1, 1009.3.2, 1009.3.3, 1013.1 | emergency lighting, accessible egress, exit signs |
| IBC 2024 ch. 11 | 1103.2.2, 1104.3.1, 1104.4 | employee work areas, the route between stories |
| IFC 2024 ch. 60 | 6004.1.2, 6004.2.2.2, 6004.2.2.9 | gas cabinets, detection where highly toxic gas is used |
| IMC 2024 | 509.4, 509.5.5, 509.6.1, 509.7 | hazardous exhaust |

Found in reading:

- The fixture table has no row for hazardous occupancies; the code official decides. The factory and industrial
  row (1 water closet and 1 lavatory per 100 of each sex, 1 drinking fountain per 400, a service sink) is our
  proposal, marked assumed.
- Standpipes are not required: under four stories, and the highest floor (the clean floor, 24.6 ft) is under
  30 ft above fire department access.
- Employee work areas must be reachable (1103.2.2, 1104.3.1, 1104.4), so each building gets a lift.
- In a sprinklered building, stairs serve as accessible means of egress without 48 in between handrails or areas
  of refuge (1009.3.2, 1009.3.3).
- Incompatible materials may not share a hazardous exhaust system (IMC 509.4). The stricter IBC 415.11.12 duct
  sprinklers stay, although IMC 509.7 exempts metallic ducts in fabs.

## DD2 The 1.6 m chase layout, with cross aisles

- **Why the layout changes.** On the stricter reading the chases need 5 ft (1.524 m), so the 1.5 m layout fails;
  D10's 1.6 m chase layout meets the width.
- **What the 1.6 m layout still fails.** On it, the tools of many bays line a 60 m chase end to end. The middle of
  such a chase is then 30 m, about 98 ft, from either open end, and there is no gap for a door into the fab area.
  That fails the 75 ft of IBC 415.11.3.3.
- **The change.** `fabsim layout` gains `--cross`: a cross aisle of that width at mid-depth on every wall of tools,
  with no tool across it. Without the option the layout is unchanged byte for byte.
- **The layout used.** Design development runs on `fabsim layout --real --chase 1.6 --cross 1.6`
  (`results/layout-real-dd`). Its run window is recorded the same way, and `fabsim layout-trace` reads `--chase` and
  `--cross` like `fabsim layout` does. The scene is `data/layout-real-dd/scene-optimised.json`.
- **Back into Fab Gym.** `viz/permit/rescore_dd.py` scores the 1.6 m chase layout against the same with cross aisles,
  on 10 paired seeds (`results/layout-real-dd/rescore.json`).
- **Checks.** D4 to D8 rerun on this scene. Every tool keeps the full chase clear and stays out of the cross aisle.
- **Combined footings.** Where two column pads overlap (columns close together at a building end), they become one
  combined footing sized for their total load. D5 changes nothing where pads do not overlap.

## DD3 The stricter readings

- Chases are service corridors. Each chase (the strip behind the tools at each bay edge, open to the spine and to
  the perimeter) gets a partition on the tool side, with the tools through it as a bulkhead.
- Doors from the chase into the fab area are added where the walk to the nearest end or door would exceed 75 ft,
  each at the nearest point with no tool behind it.
- The chase is exhausted at 6 air changes an hour or more.
- Checks: width ≥ 5 ft; travel ≤ 75 ft; dead end ≤ 4 ft; air changes ≥ 6. Each is met or not met, never cannot say.
- Risk category IV, assumed. `structure.risk_category` is met with its basis marked assumed.

## DD4 Architecture

- **Wall types:** every rated wall the passes add gets a type. WT-1 is 1 h, IBC T721.1(2) item 13-1.1. WT-2 is
  2 h, item 13-1.2. The facade and chase partitions are unrated types. The type and rating go in the IFC as the
  `FabGym_Rating` property set (Rating_h, Assembly, Cite).
- **Doors:** each door in a rated wall is rated per T716.1(2) for its wall:

  | Wall | Door rating |
  |---|---|
  | 2 h fire barrier or exit enclosure | 1.5 h |
  | 1 h exit passageway or exit enclosure | 1 h |
  | Other 1 h fire barrier | 0.75 h |
  | 1 h corridor | 1/3 h |

- **Firestops:** every pipe, duct or tray crossing a rated wall gets a firestop with an F rating at least the
  wall's (714.4.1.2). Firestops are scheduled, not modelled.
- **Toilet cores:** on the support floor beside the spine stairs, men's and women's rooms. They are counted from
  each building's occupant load (both floors, Table 1004.5 loads, half of each sex) at the factory row.
  - Walking distance is checked to the nearest toilet on the same floor or one floor down by a stair, at most
    500 ft (403.3.3). The walk is measured on the 0.5 m grid as before, plus the stair run, with each stair's
    own walk on the support floor to its nearest toilet.
- **Lift:** one per building at the west end, from grade to the clean floor (an accessible route between the
  stories, 1104.4). Its construction follows ASME A17.1, not read.
- **Exit signs and emergency lighting:**
  - Signs at every exit door and along the spine, perimeter and exit passageways, so every point of those paths
    is within 100 ft of a sign (1013.1).
  - Emergency luminaires along the same paths and in the stairs, on 90 minutes of battery or generator
    (1008.3.1). The check is average ≥ 1 fc and minimum ≥ 0.1 fc along the paths (1008.3.2). It is computed
    point by point from an assumed luminaire output with a range, so a range that crosses the limit says
    cannot say.
- **Sheets:**

  | Sheet | Shows |
  |---|---|
  | A-201 | Exterior elevations |
  | A-301 | Building sections |
  | A-402 | Enlarged toilet cores and lifts |
  | A-501 | Wall types and details |
  | A-602 | Wall, door and firestop schedules |

## DD5 Structure

- Risk category IV (assumed).
- A member schedule:
  - every column with its load and a required steel area at an assumed allowable stress;
  - every truss and spine beam with its span, moment and required section modulus;
  - every footing with its size and depth.
- Members are sized by required properties, never by a maker's catalogue. Every member is preliminary and goes
  to licensed review; seismic and wind stay cannot say.
- Sheets: S-301 sections through the frame, S-601 the member schedule.

## DD6 Mechanical

- **Chase exhaust:** at 6 air changes an hour or more, added to the general exhaust demand and the plant.
- **Hazardous exhaust:** systems by kind (general, acid, solvent, toxic); no segment carries two kinds (IMC
  509.4). Each tool's toxic exhaust is treated at the tool before the shared main (point-of-use abatement,
  assumed). No fire or smoke dampers on hazardous exhaust (509.6.1).
- **Exhaust plant:** fans and scrubbers by kind, N+1.
- **Make-up air units** per building, within 10% of the building's exhaust (509.5.5; the 10% is assumed).
- **Gas cabinets** in the gas rooms, one per highly toxic or toxic gas the room serves. Each has at most 3
  cylinders (2 assumed), is exhausted with a face velocity of at least 200 fpm over an assumed port area, and
  has a sprinkler (IFC 6004.1.2). The room keeps its own exhaust (6004.2.2.2).
- **Valve manifold boxes:** one per bay per hazardous gas the bay's tools draw.
- **Sheets:** M-201 chase and exhaust systems, M-602 fans, scrubbers and make-up air, PP-201 gas cabinets and
  valve boxes.

## DD7 Plumbing

- **Fixtures** in the toilet cores (DD4). Drinking fountains and service sinks, counted per building.
- **Drains** sized by drainage fixture units (T709.1): branches by T710.1(2), the building drain at 1/4 in per
  foot by T710.1(1), at least 3 in where it serves a water closet.
- **Emergency showers and eyewashes:** at every chemical dispense room and in every wet bench bay. Their
  location and flow follow ISEA Z358.1, which is not read: cannot say.
- **Sheet:** P-201 toilet cores, fixtures, drains and showers.

## DD8 Fire protection and alarm

- **Sprinklers:** a riser and a cross main per fab area and story, and a branch line per array. Pipe sizes are
  assumed (NFPA 13 not read): the density stays cannot say.
- **Standpipes:** determined not required by 905.3.1 (met: does not apply).
- **Alarm boxes:** every manual alarm box within 5 ft of its exit's entrance, its handle 42 to 48 in above the
  floor (907.4.2.1, 907.4.2.2).
- **Notification:** horns and strobes on an assumed spacing, with 20% spare circuit capacity in employee work
  areas (907.5.2.3.1). The layout follows NFPA 72, not read: cannot say.
- **Detection where highly toxic gas is used:** in every gas room and every bay where highly toxic compressed
  gas is stored or used (IFC 6004.2.2.9). Spot detectors in the rooms, the air-sampling detectors in the bays.
- **Sheets:** FP-201 sprinkler mains and risers, FA-201 alarm boxes, notification and detection.

## DD9 Electrical

- A panelboard for every bay and the support floor, each tool on a panel, and each panel's connected load within
  its rating (assumed sizes).
- Emergency loads on generator-backed panels.
- Lighting fixtures on an assumed spacing.
- Wiring, fault currents and hazardous locations follow NFPA 70, not read: cannot say.
- Sheets: E-101 power and lighting plan, phase 1; E-602 panel schedule.

## DD10 Coordination at LOD 300

- Every element the design development passes add or confirm carries LOD 300 in `FabGym_Permit`, except
  equipment whose numbers rest on assumed cards (plant, fans, scrubbers, make-up air units, gas cabinets), which
  stays 200.
- The same clash check as D8, with the known joints it already has (a lift spans the slabs it passes; fixtures stand
  in a room), plus four new ones:
  - a tool through a chase partition (a bulkhead);
  - a pipe through a rated wall at a firestopped penetration.
  - sprinkler piping among its heads (the head arrays are drawn as boxes).
  - a lift's hoistway, which the sprinkler head arrays leave out.
- The gate is zero hard clashes. The IFC passes IfcOpenShell's validation and is the same bytes every run.

## DD11 The document set

- The 22 schematic sheets and the 15 above, in this order:
  - G-001 to E-601 as before;
  - then A-201, A-301, A-402, A-501, A-602, S-301, S-601, M-201, M-602, PP-201, P-201, FP-201, FA-201, E-101,
    E-602.
- G-002 lists every rule of this stage, G-003 every item.
- The specifications add divisions 10 (specialties: signs, toilet accessories) and 14 (conveying: the lifts).
- The ledger has no item missing, and every licensed item shows licensed review.
- One PDF. The cover says design development, and every sheet keeps the truth line and NOT FOR CONSTRUCTION.

## Checks

`viz/tests/test_dd.py` (the repo's `.venv`; it skips without the 1.6 m scene or IfcOpenShell):

- **Data:**
  - the second register (codes, hashes, the not-read list);
  - the rules (they cite the merged register, and what they rest on is not read);
  - the items (new ids, stage DD, home sheets).
- **The scene:** built from the 1.6 m layout, with every chase clear.
- **Every check above, by its numbers:**
  - service corridors, risk category, wall types, door ratings, firestops;
  - toilets (counts, separate rooms, travel), drains, showers, the lift;
  - signs and lighting, alarm boxes, detection, notification, standpipes;
  - gas cabinets, exhaust systems and make-up air, chase air changes, plant against demand;
  - the member schedule, panels.
- **The model and the set:**
  - zero clashes, a valid IFC, LOD 300, the same bytes every run;
  - 37 sheets, each with the truth line and NOT FOR CONSTRUCTION;
  - the specifications' divisions, a ledger with nothing missing, the PDF's page count;
  - no "TSMC" anywhere.

## Changes

- 27 Oct, while building DD3 (before any design development code was committed): the 1.6 m layout cannot give
  every chase a door within 75 ft, so DD2 adds the cross aisles, the rescore and combined footings. The tests read
  the new layout and scene and check the rescore. The clash joints are listed as built.
