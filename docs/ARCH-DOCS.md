# Architectural construction documents for the whole fab

A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. Every sheet stays NOT FOR
CONSTRUCTION; a permit still needs a real site and the seals of licensed people.

Decided by quiz on 28 Oct 2026 (the founder: "finish the arch drawing completely"): architecture for the whole fab,
both buildings and every floor, to construction documents. The other trades stay as they are: design development,
with lithography bay 09 in fabrication detail (`docs/CONSTRUCTION-DOCS.md`).

Live timeline: a private plan page

## How it runs

`--stage cd` (unchanged command) now also runs the architecture pass (`viz/permit/arch_cd.py`) and draws its sheets
(`viz/permit/arch_sheets.py`), after bay 09.

## AD1 Doors, rooms and finishes

- **Doors:** every door in the model gets a number, building, floor and running number (`P1-S-001` on the
  support floor, `P1-C-001` on the clean floor, `P1-R-001` on the roof).
  - Each number carries its size, rating (from design development), type and hardware set.
  - Hardware sets by use, assumed: exit stair, exit passageway, hazardous room, exterior exit, chase, toilet,
    gowning and roof hatch.
- **Rooms:** every space gets a number and a finish set by kind, assumed. The spaces are the model's bays, spine,
  perimeters and ends, and every room the passes add (gas, chemical, gowning, toilets, passageways, the emergency
  control station).
  - A finish set gives the floor, base, walls, ceiling and ceiling height.
  - The cleanroom finishes follow the space's class (ISO 14644-1 not read).

## AD2 The roofs

- **Parapets:** 1.0 m high around each roof (assumed).
- **Roof drains:** at most 900 m2 of roof each (assumed; IPC chapter 11 not read).
- **Hatches:** a roof hatch with a ladder in each building.
- **Curbs:** a curb under each make-up air unit.
- Everything is placed with no clash.

## AD3 Plans

- **Floor plans** at 1/32 in = 1 ft, one per floor per building:

  | Sheet | Shows |
  |---|---|
  | A-111 | P1 support floor |
  | A-112 | P1 clean floor |
  | A-121 | P2 support floor |
  | A-122 | P2 clean floor |

  Each is dimensioned with overall dimensions, the grid strings and the bays. It carries grid bubbles, room numbers
  and door numbers.
- **Reflected ceiling plans** of the clean floors: A-131 (P1) and A-132 (P2). They show the ceiling heights and the
  fan filter coverage by bay.
- **Roof plans:** A-141 (P1) and A-142 (P2). They show parapets, drains, hatches, plant and curbs.
- **Site:** A-100 is the architectural site plan, with the buildings dimensioned on the lot. A-001 holds the general
  notes, abbreviations and symbols.

## AD4 Elevations and sections

- **A-202:** exterior elevations with materials and heights. Wall panels, louvres and doors are tagged, and levels
  dimensioned.
- **A-311:** wall sections through the facade, the spine and a chase, with every level dimensioned.

## AD5 Enlarged plans and interior elevations

| Sheet | Shows |
|---|---|
| A-411 | Spine stairs: plan and section |
| A-412 | Facade stairs: plan and section |
| A-413 | Gowning rooms |
| A-414 | Every gas room and chemical dispense room |
| A-701 | Toilet rooms: interior elevations |
| A-702 | Gowning rooms: interior elevations |

## AD6 Schedules

| Sheet | Shows |
|---|---|
| A-611 and A-612 | The door schedule, every door |
| A-613 | The room finish schedule, every room |
| A-614 | The hardware sets |

## AD7 Details

| Sheet | Shows |
|---|---|
| A-521 | Door and frame details |
| A-531 | Roof details: parapet, drain, curb, hatch |
| A-541 | Cleanroom ceiling: fan filter grid and sprinkler head |
| A-551 | Raised floor, waffle slab penetrations, chase bulkhead |

## AD8 The set

- The sheets in order:
  - design development's 37;
  - bay 09's 10;
  - then A-001, A-100, A-111, A-112, A-121, A-122, A-131, A-132, A-141, A-142, A-202, A-311, A-411, A-412, A-413,
    A-414, A-521, A-531, A-541, A-551, A-611, A-612, A-613, A-614, A-701, A-702.
- That is 73 sheets in all, each with the truth line and NOT FOR CONSTRUCTION.
- The ledger adds the architectural items, none missing.
- 0 hard clashes; the IFC valid and the same bytes every run.

## Checks

`viz/tests/test_arch_cd.py`:

- every door numbered once, with a hardware set that exists and the rating design development gave it, and listed
  on the door schedule;
- every space numbered with a finish set and listed on the room finish schedule;
- the floor plans' overall dimensions equal to the buildings', with grid strings that add up;
- roof drains for every 900 m2, a hatch and parapets on each roof;
- 73 sheets, the ledger, the IFC and the PDF.

`viz/tests/test_cd.py` lists the 26 new sheets after bay 09's.
