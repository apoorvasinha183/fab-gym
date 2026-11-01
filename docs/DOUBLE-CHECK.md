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
stop or junction holds one car while it passes or hoists, and idle cars park off the track. A car waits for the next
piece along its way, and when the stretch it wants is full it takes any other way out with room that still leads to
its target (`FleetState::way`).

- **The rule:** cars that wait on each other for ever fill a whole connected part of the track (a part where every
  stop reaches every other), not just one loop: inside such a part every way out leads to the stuck car's target, so
  every way out must be full too. So fewer cars than the smallest connected part holds (its stops plus its stretches'
  cars) can never jam. The check finds that part and warns `may_jam` when the fab has at least that many cars, naming
  the part's first stops and the number. Build shows it with the other warnings.
- **Exhaustive on small tracks:** an explorer tries every placement of cars on small tracks (rings, a figure eight, a
  loop with a shortcut, two loops joined both ways, a ring with a siding), each car always wanting to move on: below
  the number no jam exists; at it one does, and on the ring with a siding a car can drive into it.
- **Lean** (`lean/FabCheck/Jam.lean`, checked by `lean/run.sh prove`): a jam closed inside a connected part and meeting
  it holds the whole part, so the cars on the track are at least the part's room (`no_jam_below`). Why the engine's
  stuck cars form such a closed set is argued from the engine's rules in `crates/fabsim/src/jam.rs`, not proved in Lean.

Tests (`crates/fabsim/tests/jam.rs`):
- **DC4** the number for a hand-drawn figure eight (14: all 5 stops and 9 stretch cars), a ring with a siding (the
  ring, 6), a line (none), and the teaching fab's track (its part's stops plus inside stretches' cars).
- **DC5** the explorer finds no jam below the number on any of the six small tracks and one at it; a jam can be driven
  into on the ring with a siding.
- **DC6** `may_jam` appears exactly when the cars reach the number, and not for the teaching fab's own 12 cars.

## Part 3: laws every run obeys (from a run, checked with arithmetic)

- **Little's law on the run:** over a window of a run, the time-average of lots in the fab equals lots finished per
  minute times their mean time inside, once the lots inside at the window's ends are counted (exact, as an identity of
  the run's record; checked to rounding).
- **The utilisation law:** each group's busy share over a long run is within its 95% interval of the work released to
  it divided by its capacity, from part 1's expected visits and the group's tools (probable, on 10 runs).

- Interfaces: `fabsim::routes::loads(&shop) -> Vec<GroupLoad>`, each group's work a day at the release rates, its
  machines and the busy share that work needs; `exact` when no step at the group batches (a batch's lots per job are not
  known before the run, so there the share counts the largest batch, a floor). `fabsim routes FILE --load` prints them.

Tests (`crates/fabsim/tests/laws.rs`): **DC7** Little's law to rounding on three runs of the high-volume testbed (days
5 to 15), with the lots finished and the lots inside at the window's end; **DC8** the utilisation law on the five
busiest groups with no batch step, over days 60 to 90 of 10 runs from an empty fab at four fifths of the release rate
(why, in the Changes).

## Part 4: the published testbed

- Raw processing time per product, and the flow factor (cycle time over raw processing time) under the published
  release rate, beside the published figures. Each published figure is cited only after its source is opened; where only
  an abstract can be read, that is said. Our files are a later revision than the paper's (fewer tools and steps), so a
  difference is expected and named, never hidden.

Tests: **DC9** our raw processing times, recomputed from the files, are the ones the page shows.

## Changes
- Part 1 built 1 November 2026 (tests "Snakes and ladders", code "Dice math"). DC1 to DC3 pass, with every other
  engine test. `fabsim routes` on the high-volume testbed: part_3 has 583 steps, a lot does 522.223 of them on average
  and gets 24.68 days of processing (25.52 days once through every step); part_4 has 343 steps, 308.523 done, 14.49
  days (15.00). Residuals 2e-16 or less. The teaching fab's route of 18 steps has no sampling and no rework.
- DC3's setup changed twice before it passed, never its claim. First, 30 lots from each release record: the
  super-hot record sends one every 19 days, so they could not all come within the run. Second, a fixed number of lots
  with no releases after them: about 1 in 6 lots then waited for ever at a batch step whose smallest batch (125 to 150
  wafers) never filled, since no partners came. A finding: in this engine a lot at a batch step with no wait limit
  waits until enough lots arrive, so a fab that stops releasing can strand lots. The final setup keeps releases coming
  at a quarter of the usual rate and counts only the lots released in the first week (about 50 a product a run, all
  of them finished by day 55).
- Two engine facts the exact chain now follows. A released lot does its first step for certain: release puts it in
  that step's queue with no sampling draw (a lot in progress at the start does draw). And a lot's own record
  (`LotOut.steps`, and so the canonical run log) leaves out a released lot's first job, since the record opens at the
  lot's first arrival and release skips it. The golden logs match the reference engine with this, so the engine is
  unchanged and DC3 counts jobs from the trace, which has every job.
- The high-mix testbed's files have no loader yet (its tool file is `tool.txt.1l`), so part 1 covers the high-volume
  testbed, the Floor's fab and the teaching fab.
- Route errors join `fabsim::checks::check` first: `bad_chance`, `rework_target`, and `rework_certain` (a step from
  which no path with a chance above zero reaches the end).
- Part 2 built 1 November 2026 (tests "Musical chairs", code "One chair spare"). DC4 to DC6 pass, with all 281 engine
  tests; the Lean file checks on the Mac mini with only the standard axioms. The teaching fab's track is one connected
  part of 78 stops holding 160 cars, and Build gives it 12. The real-layout fab (`web/data/shop-real.txt`) is one part of
  1,275 of its 1,279 stops holding 3,300 cars, and runs 160. Neither warns.
- The rule changed while writing the code, and the tests with it (after "Musical chairs" was committed; DC4 to DC6
  were rewritten before any code passed them). The first rule used the smallest loop: a jam holds a loop of full pieces,
  so fewer cars than the smallest loop holds cannot jam. That is true but loose. On the real-layout fab the smallest
  loop is a crossover pair at the end of the spine (n1 to n44 and back, 4 cars), so it warned at 160 cars. Reading
  `FleetState::way` showed that a car facing a full stretch takes any other way out with room that leads to its
  target, so a jam must fill a whole connected part. The smallest loop is kept as `smallest_loop` for comparison.
- A second fix in the first tests: on a plain ring the loop's number is all the room on the track, so the only
  placement with that many cars is the full ring, and nothing leads into it. Reaching a jam is tested on a ring with a
  siding instead.
- Part 3 built 1 November 2026 (tests "Little's law", code "Big deal"). DC7 and DC8 pass. Little's law holds to
  rounding on three runs: the lot-minutes the run counts (which the scorer's cycle time divides) equal each lot's time
  inside the window, and the lots finished and inside match the lots' own records. `fabsim routes DIR --load` gives
  each group's work at the release rates with no simulator; the two polishing groups Planar_FE_77 and Planar_FE_79 are
  the busiest, at 89.6% and 88.8% of their machines' time.
- A finding: at the testbed's own release rate the fab cannot keep up. The releases ask 1,430 wafers a day; the
  capacity ceiling (`bound.rs`, with maintenance by wafer count, which takes the polishers down for about a fifth more
  time than their work) is 1,302, at Planar_FE_77. So its line grows without end, and over days 10 to 40 it is busy
  80.1% of the time (95%: 78.0% to 82.1%) against the 89.6% the releases send it. This fits the 1,246 wafers a day
  today's rule gets out over days 130 to 190 (docs/LONG-RESCORE.md). It holds for our files as the engine reads them
  (a later revision than the published paper's, with fewer tools and steps); part 4 compares with what was published.
- DC8's setup changed before it passed, never its claim. On days 10 to 40 at the full rate, the bottleneck is busy less
  than its work (above). At lower rates with the given lots in progress, groups were busier than their work by the same
  amount at four fifths and two thirds of the rate: those lots, set for the full rate, were still being worked off. From
  an empty fab at four fifths of the rate, days 60 to 90, the five busiest groups without batches match within their
  95% intervals (Planar_FE_77 71.8% busy against 71.7% of work). The eighth busiest, Litho_REG_BE_63, a back-end group
  lots reach late, was 2.1 points under (95% half-width 1.8), likely still warming up.
