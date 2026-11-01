# Double-checking the simulator

Written 1 November 2026, before the tests and the code. The founder chose "Double-check the simulator" by quiz the
same day: give a judge reasons to trust the numbers, from maths that needs no simulator, from laws every run must
obey, and from the published testbed. On the SMT2020 testbed and Build's teaching fab; not a real fab. Agents propose,
the simulator scores, a person signs.

What exists already: the layout checks (`docs/FAB-CHECKS.md`: reachability, traps), the capacity ceiling
(`crates/fabsim/src/bound.rs`: no schedule beats the busiest group), and the Lean referee, which checks every scored run
obeys the testbed's five rules (`docs/LEAN-CHECK.md`). These four parts add to them, one at a time, tests first.

## Part 1: every lot finishes its route (no simulator)

A route is a list of steps. After step k a lot goes to step k+1, or, when the step has rework (to, p), back to step
`to` with chance p. A step that samples is skipped by a draw. So each route is a small chain of chances, and it can be
worked out exactly without running anything.

- **Every lot finishes, with certainty:** a check over every route of a fab file that every rework target is a step of
  the route and every rework chance is below 1, and every sampling chance is between 0 and 1. With those, from every
  step the plain path forward has a chance above zero, so the chance of never finishing is exactly zero.
- **How many steps a lot does, and its raw processing time:** the expected visits to each step, from the chain's
  equations (solved in floating point; the answer states its largest residual), times each step's time. Published
  numbers count raw processing time without rework; both are given.
- **Matching the simulator:** on 10 random runs of the high-volume testbed, the mean steps per finished lot and their
  95% interval contain the exact expectation (a lot that started before the run is left out).
- Interfaces: `fabsim::routes::analyse(&shop) -> Vec<RouteChain>`; `fabsim routes FILE [--json]`; route issues join the
  layout checks as errors (`rework_target`, `rework_certain`, `bad_chance`).

Tests (`crates/fabsim/tests/routes.rs`):
- **DC1** a toy route's expected visits match the hand-worked answer (one rework loop: 1/(1−p) visits), and its
  residual is tiny.
- **DC2** every route of the high-volume and high-mix testbeds and the teaching fab passes; a rework to a step outside
  the route, a rework chance of 1 and a sampling chance of 1.5 are each refused with its code.
- **DC3** on the high-volume testbed the simulator's mean steps per finished lot, over 10 random runs, has a 95%
  interval containing the exact expectation for each product.

## Part 2: the track cannot jam below a count of cars (no simulator)

Vehicles block each other only while moving: a stretch of track holds `floor(length / gap)` cars (at least one), a
stop or junction holds one car while it passes or hoists, and idle cars park off the track. A car waits only for the
next piece along its way. So a jam where cars wait on each other for ever needs a loop of the track whose every piece
is full, which takes at least as many cars as that loop holds.

- **The rule:** with fewer moving cars than the smallest loop holds, the track cannot jam. The check finds that loop
  (a shortest cycle, weighting each stretch by its cars plus one for the stop at its end) and warns `may_jam` when the
  fab has at least that many cars, naming the loop and its number. Build shows it with the other warnings.
- **Exhaustive on small tracks:** a separate explorer tries every reachable placement of cars on every track of up to
  five stops (rings, figure eights, a loop with a shortcut), each car always wanting its next piece: below the loop's
  number no jam is ever reached; at it, on a ring, one is.
- **Lean:** the counting argument as a theorem: a closed walk of full pieces holds at least the sum of their sizes.

Tests (`crates/fabsim/tests/jam.rs`):
- **DC4** the smallest loop of a hand-drawn track is found, with its number.
- **DC5** the explorer finds no reachable jam below the number on any small track, and a jam at it on a ring.
- **DC6** `may_jam` appears exactly when the cars reach the number; the teaching fab's own track and car count are
  stated in this file's Changes.

## Part 3: laws every run obeys (from a run, checked with arithmetic)

- **Little's law on the run:** over a window of a run, the time-average of lots in the fab equals lots finished per
  minute times their mean time inside, once the lots inside at the window's ends are counted (exact, as an identity of
  the run's record; checked to rounding).
- **The utilisation law:** each group's busy share over a long run is within its 95% interval of the work released to
  it divided by its capacity, from part 1's expected visits and the group's tools (probable, on 10 runs).

Tests (`crates/fabsim/tests/laws.rs`): **DC7** Little's law to rounding on three runs; **DC8** the utilisation law on
the five busiest groups.

## Part 4: the published testbed

- Raw processing time per product, and the flow factor (cycle time over raw processing time) under the published
  release rate, beside the published figures. Each published figure is cited only after its source is opened; where only
  an abstract can be read, that is said. Our files are a later revision than the paper's (fewer tools and steps), so a
  difference is expected and named, never hidden.

Tests: **DC9** our raw processing times, recomputed from the files, are the ones the page shows.

## Changes
