# Blueprint to permit set: the drawing set carried toward what a permit needs

Written 27 Oct 2026, before the code (tests in `viz/tests/test_permit.py`). A gigafab-style layout of our own
design from the SMT2020 testbed; not a real fab. Every sheet stays NOT FOR CONSTRUCTION: a permit needs a real site
and the stamps of an architect and engineers licensed where it is built, which no pipeline gives.

The founder's architect friend said the concept set "was not construction ready". The founder: "let's make this
a part of the workflow". Plan page: a private plan page. Decided by quiz (27 Oct),
all on the recommendation: a US place first, read in **the 2024 IBC and IFC as published** for a hypothetical
jurisdiction that adopts them unamended; **schematic design across every trade first**, with the code analysis
and the ledger, then the fab rescored; **tool numbers as ranges by kind, each marked assumed**.

## The pipeline

```
scene-optimised.json ──> viz/blueprint/model.py (the one building model)
        │
        ├─ D1 place profile v2  (viz/blueprint/places/us.json "permit" block, codes register)
        ├─ D2 tool data cards   (viz/permit/tool-cards/<kind>.json)
        │
   viz/permit/run.py --place us
        D3 rules ── D4 architecture ── D5 structure ── D6 utilities ── D7 air and fire ── D8 coordination
                                                                                   │
        D9 the document set (sheets, schedules, specifications, IFC, PDF) <────────┘
        D0 the readiness ledger (every item a permit set needs, with its status)
        D10 rescore: what the code costs the fab (fabsim layout --chase, paired seeds)
```

Each pass reads what it declares and adds its own elements to the model; the sheets, the IFC and the ledger
are drawn from the result, so they never disagree. Nothing moves a tool, stocker or rail: what the code asks
of the layout goes to D10 as a constraint for the layout optimiser.

## How a code section is read and cited

A section is opened in ICC's free reader (`https://codes.iccsafe.org/content/IBC2024V1.0/...` and
`IFC2024V1.0`) before a rule cites it. No copy of the code is kept: ICC's text is copyrighted. The register
(`viz/permit/codes/us-2024.json`) keeps, for each section: the code, the chapter's URL, the date opened, the
number of characters read and the SHA-256 of the section's text as shown (whitespace collapsed; the reader's
"CDP" and "INSIGHTS" labels removed; the characters `= ? & %` as spaces, the browser tool's own filter), and
the numbers a rule uses, written in our own words. Anyone with the page open can hash the same span and
compare. A standard that is sold or not yet read (ASCE 7, NFPA 13, 70, 72 and 318, ISO 14644-1, SEMI S2,
FM Global data sheets, ASHRAE, the IMC, ICC A117.1, IFC chapters 50 and 60, IBC sections not opened) is listed
as not read, and any rule resting on it says **cannot say: law not read**.

Read on 27 Oct: IBC 307 (Group H-5, Tables 307.1(1) and 307.1(2)), 415.11 (the H-5 sections used below),
Tables 504.3, 504.4, 506.2 and 601, Table 1004.5, Tables 1006.2.1 and 1006.3.3, 1005.3.1, 1005.3.2, 1007.1.1,
1011.2, Table 1017.2, 1017.3, Tables 1020.2 and 1020.3, 1023.2, 903.2.5.2, 907.2.5, 916.6, Tables 1604.5 and
1607.1, 1609.3, 1613.1; IFC 2703.1, 2703.10.1, 2703.10.2, 2703.13.1, 2703.14.1, 2703.15.

## D0 The readiness ledger

`viz/permit/items.json` lists every item a fab permit set needs, before any of it is built: id, discipline
(G, C, S, A, M, PP, P, FP, FA, E, spec), the item, its home sheet, the IFC class that carries it (or none),
the pass that makes it, and whether it needs licensed review. `run.py` writes `ledger.json` and sheet G-003
with each item's status:

| status | means |
|---|---|
| missing | a permit set needs it and nothing makes it yet |
| drawn | on its sheet and in the IFC, no rule bound to it |
| checked | every rule bound to it was met, each with its citation |
| assumed | drawn and checked, but a number it rests on is assumed |
| open | a rule bound to it says cannot say, or a question has no answer |
| licensed review | done as far as a pipeline can; a licensed person judges it |

The gate: no item is missing.

## D1 Place profile v2

`places/us.json` gains a `permit` block: the jurisdiction (hypothetical, adopting the 2024 IBC and IFC as
published), the register's path, design data (seismic, wind, snow, cooling and heating design temperatures,
soil bearing) each as `{value, lo, hi, basis}` with basis `assumed` (no real site, so no hazard maps are read),
and a hypothetical lot (a rectangle 20 m outside the campus's roads, assumed) with its lot lines. The `intl`
profile has no codes read: `run.py --place intl` stops and says so.

## D2 Tool data cards

One card per kind in the scene (12, the stocker included): service clearances, operating mass, power (kVA,
whether backed up), heat to room air and to process cooling water, process cooling water, ultrapure water,
clean dry air and nitrogen flows, process vacuum, exhaust by kind (general, acid, solvent, toxic) in m3/h,
drains by kind (acid, fluoride, solvent, slurry) in L/min, the hazardous production materials it holds in the
tool or draws from a gas room (material, hazard class, quantity, where), its vibration criterion, the
cleanliness class around it and whether it needs yellow light. Every value is `{value, lo, hi, basis}`.
SMT2020 has no such data, so every value starts assumed, by kind, with a range; none is claimed as a maker's
number.

## D3 Code analysis

Rules live as data in `viz/permit/rules/us.json`: id, topic, the sections cited, what it binds (a building, a
story, a fab area, a room, an element), its input, its test (a comparison with a limit read from the register)
and a fix. The engine (`viz/permit/rules.py`) gives each rule, for each thing it binds: **met**, **not met**, or
**cannot say**, when an input is missing, when the law it rests on is not read, or when an assumed input could
flip the verdict within its range. Topics: occupancy (H-5), construction type, height and area, fab areas
(hazardous material per area, separation, location), exits and egress, service corridors, HPM and gas rooms,
ventilation and exhaust, gas detection, alarms and the emergency control station, emergency power,
sprinklers, structure (loads, risk category, seismic, wind), cleanroom air, accessibility. Sheet G-002 is the
code analysis.

## D4 Architecture, schematic

- Fab areas: hazardous material per area from the cards against Table 415.11.1.1, so each building is one fab
  area or is split at bay lines; bounded by 1-hour fire barriers (415.11.1.2).
- Construction type: the least type the height, stories and story area allow (Tables 504.3, 504.4, 506.2), and
  its ratings (Table 601).
- Exits: stair cores in the spine between stockers, with a lid under the hoist vehicles, discharging at grade
  into exit passageways across the support floor to the long facade; stair towers outside the long facades.
  Placed greedily until the walking distance from every point of the clean floor and the support floor to the
  nearest exit is within Table 1017.2 (measured around tools, stockers and bay walls on a 0.5 m grid in eight
  directions, which overestimates a straight walk by at most 8%), the number per story meets Table 1006.3.3, the
  stairs' width meets 1005.3.1 and 1011.2, and two exits are at least a third of the diagonal apart (1007.1.1).
- Gas rooms and a chemical dispense room on the support floor at the long facades, with an exterior wall at
  least 30 ft from the lot lines (415.11.6), rated by area; gowning rooms at each building's west end; the
  emergency control station in the office (415.11.10).
- Doors, rooms and fire ratings as schedules.

## D5 Structure, preliminary

Loads from Table 1607.1 (heavy manufacturing 250 psf on the clean floor; stairs 100 psf; roof 20 psf) and
assumed dead loads; roof trusses spanning from the spine edge to the bay ends on columns at bay lines, carried
down to their own footings apart from the waffle slab; support-floor columns checked by area and footings sized
on the assumed soil; a braced bay in the facades; the waffle slab's first frequency per bay estimated against an
assumed target. Seismic and wind design say cannot say (ASCE 7 not read; no real site). Every member is marked
preliminary, for licensed review.

## D6 Utilities and the central plant

Demand by bay from the cards and the tool counts, with an assumed diversity; plant sizes (chillers, ultrapure
water, compressed air, nitrogen, transformers, emergency generators sized for the loads of 415.11.11.1, with
exhaust fans at half speed as 415.11.11.2 allows); mains along the sub-fab beside the spine, a lateral under
each row of tools, a drop to every tool; pipes and ducts sized by velocity from an assumed list of sizes; the
one-line diagram.

## D7 Cleanroom air and fire protection

A cleanliness class per space (assumed: ISO 5 where the cards ask for it, ISO 6 in other bays and the spine,
ISO 7 at the perimeter) and fan filter coverage by class; recirculated air against 415.11.1.8; make-up air;
the cooling load against the chillers. Sprinklers throughout with the hazard classes of Table 903.2.5.2 (the
density waits for NFPA 13: cannot say), heads in exhaust ducts of 10 in or more, gas detection at every tool
that draws hazardous gas, in every gas room and gas cabinet (415.11.8.1), air-sampling smoke detection per bay,
pull stations at exits and alarms outside gas rooms.

## D8 Coordination

Every element is a box in one list; a hard clash is two elements overlapping by more than 0.0001 m3 that are
not a known joint (a column through a slab, a drop through the waffle slab, a wall meeting a wall, anything
inside a space). The gate is zero hard clashes. The IFC (`fab-permit.ifc`) carries every element with
`FabGym_Basis` and `FabGym_Permit` (stage, level of development 100 to 350, review, and its numbers), passes
IfcOpenShell's validation and is the same bytes on every run.

## D9 The document set

Sheets in the profile's naming and units: G-001 cover and index, G-002 code analysis, G-003 readiness
ledger, G-101 and G-102 life safety plans, C-101 site and lot, C-201 site utilities, S-001 structural notes and
loads, S-101 foundation plan, S-201 framing plan, A-401 enlarged plans, A-601 schedules, M-101 sub-fab plan,
M-401 cleanroom air, M-601 equipment schedules, PP-101 process piping, PP-301 exhaust and drains, P-101
plumbing, FP-101 sprinklers, FA-101 alarms and detection, E-001 one-line diagram, E-601 electrical schedules;
`specs.md`, a specifications outline by MasterFormat division; `permit-set.pdf`; `fab-permit.ifc`. The
concept sheets A-000 to A-900 stay in `data/layout-real/blueprint/us/`.

## D10 Back into Fab Gym

Fab Gym's chases are 1.5 m. If the authority treats them as service corridors, 415.11.3.4 asks 5 ft
(1.524 m). `fabsim layout --chase` lets the optimiser lay the fab out with a wider chase; `viz/permit/rescore.py`
runs both layouts on the same seeds and reports the change in hoist metres and in the simulator's measures with
paired intervals, from the SMT2020 testbed.

## Checks

`viz/tests/test_permit.py` (the repo's `.venv`; skips without the scene or IfcOpenShell): the rule engine on
hand cases; the register, the profile, the cards and the items; the concept model fails the exit rules and the
set passes them; no tool moved; travel, exit count, capacity and separation; rooms and lot lines; footings
carry the whole load; every tool connected; plant covers demand; air and cooling; detection and sprinklers; zero
hard clashes; the IFC valid and the same twice; every sheet with the truth line and NOT FOR CONSTRUCTION;
every rule on G-002 and every item on G-003; the specifications' divisions; no brand names.
