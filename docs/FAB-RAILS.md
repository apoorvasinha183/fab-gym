# The track is what you drew (the modular gym, deliverable 3)

Written 31 Oct 2026, before the code. With a fleet, vehicles drive on the simulator's track. Until now that track
was always built from the campus settings (`Track::drawn`). From this deliverable, when a fab file has a plan with
links, **the track is the plan's own nodes and links**, so any shape a person or the editor draws is what vehicles
drive on. On the SMT2020 model; layouts are of our own design or a person's, never a real fab.

## Two kinds of plan

- **A plan with spots: today's campus.** `fabsim fab-export` also writes, for every node, where it sits on the
  campus: a `spot` record (node, phase, side, bay, x, y along and into the bay, the port it serves or `-`, stocker 0
  or 1). Read back, the track is built node for node and link for link as `Track::drawn` builds it, so today's
  campus as a file gives exactly today's runs.
- **A plan of its own: anything drawn.** No spots and no `oht` record. The run takes the plan's coordinates as the
  floor (shifted so none is negative), a lot's place as its group's first stop, new lots at the entry, and lots for a
  stored group at the stocker nearest by the plan's straight-line distance. Vehicles move at today's 150 m a minute
  (assumed). A `fleet` record needs an `oht` record or a plan with links.

## What changes in a run

Nothing for a shop without plan links. With them: the track, the stops (each tool's stop from the plan), the stockers,
and the names of rail stretches in the overrides file and in `RunResult::due`, which are the plan's node ids
(`FROM>TO`). Every rule for vehicles (no passing, gaps, holds at stops, detours, going round a broken stretch) is
unchanged; they now run on any shape.

## Tests (written before the code: `crates/fabsim/tests/fab_rails.rs`)

1. Today's campus exported with spots builds a track equal to the drawn one: the same nodes, stretches and lengths,
   stops, ports and every shortest way.
2. Run on that file, a fleet's half day is the same as today's: the same log, the same vehicle entries.
3. Lengthening one bay's stretch in the file changes the run, so the file's track is the one driven.
4. A small fab of its own (two tools, a loop with a bypass, no `oht`) runs with a fleet and finishes its lots.
5. On that fab, with the main stretch breaking, going round beats waiting: fewer vehicle-minutes held up, at least as
   many moves delivered (the test promised in docs/OVERRIDES.md, Changes).
6. A spot naming an unknown node, and a `fleet` with neither `oht` nor plan links, are refused with their line.

## Changes

- 31 Oct, the first run: test 4 asked for more than 200 moves in two days, counting two moves a lot. A lot there
  makes one move (it starts at A's stop and leaves from B), so 192 lots made 192. The test now asks that every
  finished lot made its move.
