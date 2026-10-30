# The editor, take two

Written 31 Oct 2026, before the code. The founder on the first editor: "it has no soul". Agreed by quiz on the
prototype: the page opens on a fab already running, with a
challenge and five scores on top; the motion is an exact replay of the simulator's run; four challenges ship for 4
Nov; the palette's small icons and the selection widget come back. On a teaching fab of our own and the SMT2020
model; never a real fab.

## The loop

1. **Watch.** The page opens on Challenge 1 already run: the floor plays an exact replay window (every vehicle where
   the simulator had it), queues of pods stand in front of machines, every machine wears its mood, the clock ticks.
2. **Spot it.** The challenge says what is wrong and what to reach; the five scores (wafers out a day, cycle time,
   worst queue, jammed stretches, spend on top) show how far off it is.
3. **Build.** Pausing switches to Build: the palette places tool groups, stockers, the start and the ship point and
   lays rail; the selection widget sets a group's count, its breakdowns and recovery, a rail piece's ways out and
   its breakdowns and recovery, and the fab's work-in-fab cap.
4. **Run again.** The simulator runs the new layout on the same seed; every score shows its change against the last
   run, and the challenge's bar fills or does not.

## The challenges (calibrated on the simulator, 31 Oct; each starts below its target and has a fix that meets it)

| Id | Fab | The problem | Target |
|---|---|---|---|
| `rush` | teaching | a north spine stretch inside a bay's span keeps breaking, and vehicles wait at the break | the wafers a day set in `editor-core.js`, nothing jammed |
| `polisher` | teaching | one polisher (CMP) for the whole fab: gassed | as set, within a budget |
| `breakdown` | teaching | lithography breaks every few hours and repairs in place | as set, within a budget |
| `lean` | teaching | a polishing outage on day two | as set, within a budget |

Measured while designing them (two days, seed 1, not scored runs): one polisher gives 312 wafers a day and two give
812; lithography breaking every 4 hours for 3 gives 437, a spare 587, a fourth tool 500; a 10-hour polishing outage
gives 600, a work-in-fab cap of 10 alone 500, a spare polisher 662, both 737. Vehicles barely matter on these
layouts (2 to 12 on the teaching fab give 812; 40 to 300 on SMT2020 give 675 to 750 in a day).

## Going round a break, from the split before it

A break on the spine first made going round and waiting identical: a vehicle only looked for a way round when the
broken stretch was its very next one, by which time it had passed the split. While any stretch is broken and set to
go round, a vehicle at a split now takes the shortest way to its target that avoids every broken stretch, as a
control system routes round a known break. Runs with no broken stretch are unchanged.

## Prices, failures, the cap and the replay

- Prices per area (dollars to buy a tool, assumed for the gym) are written as `price` records for every placed group,
  so the simulator's spend is theirs.
- The selection widget's settings become the overrides file (docs/OVERRIDES.md); nothing set, no file.
- A cap is written as the shop's `cap` record.
- The replay window comes from `fabsim replay` through `/api/fab/replay`; the page draws each vehicle along its stretch
  at its time.

## Tests (written before the code)

`web/tests/editor2.test.mjs` (the four challenges, each starting below target with a fix that meets it, with the real
simulator; prices and spend; the widget's overrides; the cap; the replay drawing), `agent/tests/test_editor.py`
(`TakeTwo`: a run takes an overrides file, a bad one is refused plainly, a replay window comes back),
`crates/fabsim/tests/fab_rails.rs` (going round starts at the split before the break).
