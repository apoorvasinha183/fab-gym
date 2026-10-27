# Problem: make a simulated wafer fab look like a real one

## Context

We have a discrete-event simulator of a 300 mm front-end wafer fab, running the
published SMT2020 high-volume testbed (Kopp, Hassoun, Kalir and Mönch, 2020):
105 tool groups, 1,043 tools in 11 process areas, two product routes of 583 and
343 steps. On top of it sits a campus layout of our own design, gigafab-style:

- Phase 1 (front end), Phase 2 (back end, copper), Phase 3 an empty pad, laid
  west to east and joined by overhead hoist (OHT) bridges.
- Each phase has a central spine (8 m) with bays 60 m deep on both sides; tools
  stand along each bay; an optimiser orders the bays to cut hoist travel.
- The simulator times every lot move by its distance on this layout.

Today the layout is drawn as coloured boxes on a dark floor, with lots drawn
four times larger than life so they can be seen from the air. A scene file
(JSON) holds the campus buildings, bays, the 1,043 tools (position, footprint,
height, group), the rails, stockers, every tool's state over time and every
lot's path as keyframes `[t, x, y, z]` over a 6-hour window of simulated day 30.

## The problem

Produce a film and an explorable 3D scene of this campus that a person who has
worked in a fab would recognise as a fab, outside and inside, without it being
any real fab. The pictures must stay true to the simulation: every lot is where
the simulator says it is, and every tool shows its simulated state.

## What "looks real" means

1. **True size.** Every object at its real dimensions: wafer carriers (FOUPs),
   hoist vehicles and rails, each kind of tool, bay widths, floor heights.
2. **Real tool shapes by kind, in close-up detail** (panels, screens, load
   ports with latches, piping and cables at the back, signs and gauges, built
   for the camera to stop 1 m away), recognisable but carrying no maker's
   design or name. At least: lithography scanner with its coat and develop track,
   vertical furnace stack, wet bench, CMP polisher, ion implanter, etch and
   deposition cluster tool, inspection and metrology tool, stocker.
3. **A real cleanroom**: raised perforated floor, ceiling grid of fan filter
   units, bay walls and service chases, yellow light in lithography bays,
   hoist rails at ceiling height with vehicles that lower carriers onto load
   ports, a few people in cleanroom suits.
4. **A real building**: the fab block in section over its floors (support floor
   with pumps, chillers and exhaust ducts; the cleanroom; the air plenum above),
   and around it the central utility building, cooling towers, exhaust stacks,
   bulk gas yard, water plant, roads and parking, under a real sky.

## Deliverables

1. **A size book**: a table of every dimension and look used, each with a
   published source (document, page) or marked assumed.
2. **Tests, written and committed before the code** (see acceptance below).
3. **A tool kit**: one parametric model per tool kind, built in code, and a
   map from each of the 105 SMT2020 tool groups to a kind.
4. **The layout re-packed at true size**: the optimiser rerun with the size
   book's footprints, and the layout's effect rescored on the simulator (paired
   seeds, 95% intervals), so the film shows the layout that was scored.
5. **A film script** with every shot's camera move, lens, timing, captions
   and the narrative, signed off before the film is built
   (`docs/FAB-FILM-SCRIPT.md`).
6. **A Blender film** (about 2 minutes, 1920×1080) that follows the script:
   the campus from the air; the building cut open floor by floor; inside;
   one lot followed through lithography, metrology, etch and a long queue,
   with a clock; where its time went; back out to the campus.
7. **A Godot scene** using the same models: walk at eye height in the
   cleanroom, fly outside, play and pause simulated time.
8. **Both projects saved** so they can be opened and inspected later.

## Acceptance

- Every one of the 105 groups maps to a kind; no tool is drawn as a plain box.
- Every model's bounding box matches its size-book entry within 5%.
- Carriers are drawn at true size and ride at rail height; a carrier's position
  at every frame matches the simulator's keyframes.
- Every tool's colour or light at every frame matches its simulated state.
- The scene has the three floors; the film's shots run outside, inside, one
  lot, outside.
- No maker's name, logo or trademark appears on any model, texture or caption.
- The film and page say "a gigafab-style layout of our own design on the
  SMT2020 model", and never claim a real fab or real data.

## Constraints

- Tools, building and cleanroom are modelled in our own code. Free CC0 assets
  may be used for the sky, materials, people and cars, each licence read and
  each download approved before it is made.
- Rendering runs on a Mac mini (Apple silicon) with little free disk: frames
  are copied off and deleted as they finish. One heavy job at a time.
- The simulator decides positions and states; the views only draw them.

## Not in scope

- Any real company's fab, floor plan, tool designs or photographs.
- Changing the simulator's rules or the SMT2020 data.
- Physics of air flow, contamination or vibration.
