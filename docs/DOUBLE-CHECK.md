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

Every published figure below was read in its source on 1 November 2026 (with the founder's approval to read both):
[WSC 2019] Hassoun, Kopp, Mönch and Kalir, the paper that introduced the high-volume testbed (pp. 2419 to 2428), and
[Tassel 2023] Tassel et al., arXiv:2302.07162v1, which ran the same family of files in PySCFabSim, the source of ours.
The figures, with pages, are in `results/double-check/published-figures.json`; ours are in
`results/double-check/ours.json`, written by `fabsim published data/smt2020/hvlm --days 180 --seeds 10` (today's rule:
highest priority, then no setup change, then oldest; 10 runs of 180 days; about 15 s on 4 cores).

| | Published | Ours | Note |
|---|---|---|---|
| Toolsets and machines | 105 and 1,054 [WSC 2019, p. 2422 and Table 2] | 105 and 1,043 | Our files are a later revision. The testbed's holding group is left out of ours. |
| Steps, products 3 and 4 | 632 and 374 [WSC 2019, p. 2422] | 583 and 343 | As above. |
| Processing a lot gets, products 3 and 4 | theoretical cycle time 24.75 and 14.54 days [Tassel 2023, appendix Table 2(a), p. 10] | 24.68 and 14.49 days, exact (part 1) | 0.3% under. All ten high-mix products are within 0.6% of the same table's Table 2(b), every one under or equal. |
| Raw processing time measured in an empty fab | 28.7 and 17.1 days [WSC 2019, p. 2425] | not measured | It includes waits for maintenance and sampling. In our engine a lone lot at a batch step waits until enough lots come, so an empty fab cannot be timed the same way. |
| Flow factor at full load, regular lots | median 2.63, 90% between 2.39 and 2.91 [WSC 2019, p. 2426] | median 2.41, 90% between 2.07 and 2.83 (69,123 lots) | Not like for like: their model is an earlier revision with lithography designed as the constraint, first come first served, in AutoSched AP. Ours counts lots released and finished within 180 days, which leaves out the slowest. |
| Regular lots' cycle time over 6 months, products 3 and 4 | 93.61 (sd 0.71) and 51.52 (sd 0.5) days, hierarchical FIFO, 100 seeds [Tassel 2023, appendix Table 2(a), p. 10] | 60.24 (95%: 59.66 to 60.83) and 34.98 (34.48 to 35.48) days | Mostly how full the fab is when measured: see below. |
| Hot lots, products 3 and 4; super-hot, product 3 | 34.02, 19.80; 33.99 days [as above] | 30.98, 17.86; 30.91 days | |
| What binds | lithography, by design [WSC 2019, p. 2425] | polishing: Planar_FE_77 passes at most 1,302 wafers a day against 1,430 released | In our engine the fab does not keep up at the release rate: lots inside grow from 2,223 to 3,155 on average over the 180 days (part 3). |

What this supports: the routes, steps and times of our files are the published ones, to within 0.6% on every product of
both testbeds. What it does not: a single cycle time. At its own release rate the fab cannot keep up, so its cycle time
has no steady value: it grows with how full the fab is when the measuring starts, and keeps growing while it is
measured. A cycle time from this gym should be quoted as the gym's, with its start and horizon, never as the published
testbed's.

### Why the cycle times differ (1 November 2026, at the founder's request)

- **Same files.** Tassel 2023's code (github.com/ingambe/RL4SemiconductorFabSched) holds the SMT2020 files it ran. Every
  one of the 12 high-volume files has the same git hash as ours, the starting work list (`WIP.txt`, 2,255 lots) included;
  the high-mix work list (2,156 lots) is identical too. Only the repository's file list was read; no file was fetched.
- **A fuller fab at the start.** Tassel 2023 (p. 2) reports 3,635 lots in progress at the start of its high-volume
  horizon and 2,700 for the high-mix one, 1.6 and 1.25 times what the identical files list. How their simulator comes
  to those counts (a warm-up, or a different reading of the list) is not stated in the paper and was not read in their
  code.
- **Our engine, made as full** (10 runs of 6 months, today's rule; `crates/fabsim/examples/gap_probe.rs`,
  `warm_probe.rs`):

  | Start | Regular lots, product 3 | Product 4 | Hot lots, 3 and 4 |
  |---|---|---|---|
  | the files' own work (2,223 lots inside) | 60.2 days | 35.0 | 31.0, 17.9 |
  | copies of those lots, to 3,635 inside | 84.2 | 49.8 | 31.1, 17.9 |
  | as above, lots under a queue-time limit first (their rule's first stage) | 84.8 | 47.9 | 31.8, 18.2 |
  | after running the files about 240 days, to 3,450 to 3,640 inside | 98.8 | 58.5 | 31.0, 17.9 |
  | **published** [Tassel 2023, appendix Table 2(a), p. 10] | **93.6** | **51.5** | **34.0, 19.8** |

  With as many lots inside at the start as theirs, our regular lots take 84 to 99 and 48 to 59 days, around the published
  94 and 52. Which starting fill matches theirs exactly cannot be said without their simulator's start. Their rule's
  queue-time stage moves cycle times by under 2 days (today's rule written as a chooser reproduced the engine's own
  exactly, as a control).
- **Hot lots** do not depend on how full the fab is in any of these: ours take 31.0 and 17.9 days against Tassel 2023's
  34.0 and 19.8. The testbed's own paper puts hot lots near a flow factor of 1.0 even at full load [WSC 2019, Figure 1,
  p. 2426], about 29 days for product 3 by its 28.7-day raw processing time. Ours lie between the two published figures;
  this is not settled.
- **Decided by the founder, 1 November 2026:** cycle times are quoted from the files' own start (the 2,255 lots of
  `WIP.txt`), with their horizon: under today's rule over 180 days, regular lots of products 3 and 4 take 60.2 and 35.0
  days (`results/double-check/ours.json`). No warm-up and no lighter release rate in what the gym reports.

Tests: **DC9** every published figure names its source and page; our raw processing times are the exact chain's and
within 1% of the published theoretical cycle times, for both products of the high-volume testbed and all ten of the
high-mix one; `ours.json` holds 10 runs of 180 days for each lot type.

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
- Corrected in part 4: the high-mix testbed's files do load (`fabsim::smt2020::load` reads `tool.txt.1l` in both
  folders). DC2 now covers them too: all ten routes pass.
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
- Part 4 built 1 November 2026 (tests "Peer review", code "Published"). DC9 passes. Reading Tassel 2023 settled a doubt
  about figures quoted earlier in Chetnova's notes (24.75 and 14.54 days, called raw processing times): the paper's
  main Table 1 (p. 7) lists 24.75 beside super-hot lots, which looked like a lot type's figure, but its appendix Table 2
  (p. 10) gives it per product as a theoretical cycle time. The values were right; the name is the paper's
  "theoretical cycle time". The fetch tool kept both PDFs in a local folder, outside
  the repo; nothing was added to the repo.
- `ours.json`'s first run counted lots listed in the starting work with a later start (`wip.*`) as released lots, and
  its machine count included the testbed's holding group (1,443). Both fixed before it was kept.
