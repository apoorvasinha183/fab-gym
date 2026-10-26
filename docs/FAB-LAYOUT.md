# A gigafab-style campus on the SMT2020 model

Written 27 Oct 2026, before any layout code. Tests in `crates/fabsim/tests/layout.rs` are committed with this file and before the code they test.

This is a layout of our own design on the SMT2020 model. It is not a real fab, not TSMC's, and uses no real plant data. SMT2020 says nothing about where tools stand; every number below that places a tool is **assumed** and labelled so.

## What it is for

The founder asked for a floor plan that tries to optimise the SMT2020 structure, drawn and animated in 3D. The plan is scored two ways:

1. **Hoist distance** (exact for the stated flows): metres the overhead hoist (OHT) carries lots per day, summed over every move the routes make at the release rates.
2. **The simulator**: the engine moves lots by the layout's distances instead of SMT2020's flat 5 to 10 minutes, and the optimised plan is run against a plain plan on paired seeds.

## The campus

| Building | What it holds | How it is placed |
|---|---|---|
| Phase 1 (P1) | front end: every `_FE_` tool group, plus Implant and epitaxy (EPI_36, EPI_38) | west |
| Phase 2 (P2) | back end, copper: every `_BE_` tool group | east of P1, joined by an OHT bridge |
| Phase 3 (P3) | an empty pad for the next phase | east of P2 |
| Central utility building (CUB) | chillers, power, exhaust | south, drawn only |
| Ultrapure water plant, gas yard, office | | drawn only |

Copper tools sit in their own building because copper must not reach front-end tools (the reason real fabs fence copper areas off). SMT2020's routes still switch between front and back end (part_3: 25 times; part_4: 16), so lots cross the bridge and the optimiser has a reason to put the areas that hand over near it.

Delay_32 is a holding step with 400 "tools" and no machines. It is drawn as stockers along each spine and gets no floor space. A lot sent to it waits in the stocker at the spine end of the bay it came from.

## Inside a phase: bays and chases

One straight main aisle (the spine, carrying the interbay OHT) runs the phase's length west to east. Bays open off both sides, north and south. Each bay belongs to one area. Tools stand along both walls of a bay, with a service chase behind each wall and the bay's own aisle in the middle carrying the intrabay OHT.

| Assumed number | Value |
|---|---|
| bay depth (from spine to back wall) | 60 m |
| bay aisle | 3.5 m |
| chase behind each wall | 1.5 m |
| spine width | 8 m |
| bridge between phases | 60 m |
| bay width | 2 × (tool depth + chase) + aisle |
| the two sides' lengths may differ by at most (in the optimised plan; the plain plan may not manage it) | 40 m |

Tool footprints (along the wall × into the chase), assumed:

| Area | Footprint |
|---|---|
| Litho (scanner and track) | 5 × 12 m |
| Implant (with epitaxy) | 5 × 10 m |
| Planar (CMP) | 4 × 7 m |
| Dry_Etch, Dielectric, TF | 3.5 × 6 m |
| Wet_Etch | 3 × 8 m |
| Diffusion (vertical furnace) | 2.5 × 7 m |
| Def_Met, Litho_Met, TF_Met | 3 × 4 m |
| anything else | 3.5 × 6 m |

Tools are packed in slot order: bay by bay away from the west end, and inside a bay up the west wall from the spine, then down the east wall. A group's tools take consecutive slots. A group's **place** is the mean of its tools' positions (along the spine, and depth from the spine) and the bay that holds most of them.

## Distance

Points are (phase, side, bay, x along the spine, y depth from the spine).

- Same bay: |x₁ − x₂| + |y₁ − y₂|.
- Same phase and side, other bay: y₁ + |x₁ − x₂| + y₂.
- Same phase, other side: y₁ + |x₁ − x₂| + spine + y₂.
- Phase p to a later phase q: y₁ + (Lₚ − x₁) + bridge + (lengths of phases between, each plus a bridge) + x₂ + y₂, where Lₚ is phase p's length.

New lots enter at P1's west end on the spine.

## Flows

Lots per day between each pair of places, from the release streams (1440 / interval lots a day each, the stream's count ignored) and their routes:

- a step sampled with probability p is visited with probability p (an expectation over the routes, computed exactly);
- a Delay_32 step is merged, so A → Delay_32 → B counts as A → B (the stocker sits on A's spine end, so the metres are the same);
- rework loops and lots already in progress at the start are left out (stated, not modelled).

## The optimiser

What it chooses, for each phase: the order of area blocks along the spine, which side each block is on, and the order of groups inside each block. Cost: OHT metres per day, plus a penalty when the two sides' lengths differ by more than 40 m. Method: simulated annealing from the plain plan, seeded, with restarts, and the best plan kept. It is a heuristic with no optimality guarantee. Its result is exact for the stated flows and geometry.

**The plain plan** (the baseline a person without flow data might draw): areas in alphabetical order, each put on whichever side is shorter at that point, and groups in name order.

## In the simulator

A shop may carry an `oht` record. Without one, nothing changes (the golden logs stay byte-identical). With one, a move from place a to place b takes

  overhead + distance(a, b) / speed + U(−jitter, +jitter) minutes,

drawn with the lot's own random stream, one draw per move as before, so paired seeds stay paired.

| Assumed OHT number | Value |
|---|---|
| overhead (vehicle called, hoist down and up at both ends) | 4 min |
| effective speed | 150 m/min (2.5 m/s) |
| jitter | ±1 min |

SMT2020's own transport is 7.5 ± 2.5 min with no layout. Probes and the run's totals gain transport minutes and the number of moves carried.

## Pre-registered comparison

- **H1 (exact).** The optimised plan's OHT metres per day are below the plain plan's. We also report the bridge crossings per day and the building lengths.
- **H2 (simulator).** Optimised against the plain plan, both under the OHT model above. Seeds 3000 to 3009 (paired), 150 days, measured over days 60 to 150. The measures: transport minutes per move, cycle time (Little's law), wafers out per day, mean WIP and hot-lot cycle time. 95% paired t intervals, Bonferroni over the five measures. Expected: transport per move and cycle time fall. No clear effect on wafers out is expected, since throughput is set by the slowest tools. Whatever falls out is reported, including no clear effect.
- SMT2020's flat transport is run on the same seeds, for reference only.

## Deliverables, in order

1. This spec and its tests, committed first.
2. `fabsim::layout` (flows, plain plan, packing, distance, the optimiser, JSON export) and the `oht` record in the shop and engine; `fabsim layout` writes the plans and `fabsim layout-score` runs H2.
3. A 2D floor plan page for the founder (private artifact).
4. A Godot project of the campus with lots animated from a simulator trace (its scenes and scripts in `viz/godot/`, its generated data outside git).
5. A Blender scene and film rendered on the Mac mini (kept outside git, copied home).
6. A private artifact with the full-scale animation.

Every view says "a gigafab-style layout of our own design on the SMT2020 model".
