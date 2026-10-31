# The supervisor, a toy experiment

Written 31 October 2026, before the tests and the code. The founder: "wait let us do the supervisor first ... I want to do
a toy experiment first", then by quiz: the small Build fab first, then one short SMT2020 run with the same code;
breakdowns both ways side by side (wear by wafers, and on the clock); the simulator alone supervises first, then a
model is added and compared. The idea is the founder's (29 Oct): "periodically ... it looks at the current fab and state
since last time and proposes a top level policy and the low level policies still remain in action. My thesis is that
this kind of analysis will find out some correlated or load dependent breakdown areas." Looks every 24 h and 48 h (the
founder, 31 Oct). On a teaching fab of our own and the SMT2020 testbed; not a real fab. Agents propose, the simulator
scores, a person signs.

## The question

Does a supervisor that looks every day and resets the fab's top-level setting beat setting it well once? And is its
gain larger when breakdowns come with load (wear by wafers) than when they run on the clock?

## The setup

- **The fab.** The Build page's small fab (the free build's starting layout, `data/supervisor/toy.fab.txt`, written by
  `web/tools/toy-fab.mjs` from `web/editor-core.js`). Two kinds of breakdowns on its busiest group, side by side:
  **clock** (random, a mean time between breakdowns) and **wear** (after so many wafers, set so that at today's load it
  breaks as often as the clock kind). Everything else as the fab file says.
- **A setting** is the floor's rule (today's, FIFO, shortest first, critical ratio) and a cap on lots inside (none, 10,
  15, 20, 25, 30): 24 settings.
- **A run.** Two days to warm up under today's rule with no cap, then a ten-day window under the arm's choices, on
  held-out seeds 0 to 9. Looks every 24 h (ten) or 48 h (five).
- **A look.** The supervisor tries settings on copies of the fab as it stands at the look. Each copy gets **fresh luck**:
  breakdowns not yet happened are redrawn from a new seed, so no copy sees the real run's future. A wear counter is
  kept, since a real fab can read it. Each tried setting runs on three copies for 48 h (the stretch and a day of it
  playing on after, so a setting that wins a day by leaving a mess does not win), and the best mean of lots finished,
  less 0.01 a lot-hour waiting (the gym's usual measure), is applied until the next look.

## The arms (all on the same seeds)

| Arm | Who sets the fab at each look |
| --- | --- |
| A. Today | Nobody: today's rule, no cap, throughout |
| B. Best fixed | One setting for the whole window, the best of the 24 on training seeds 100 to 104 |
| C. Simulator | Tries all 24 settings on the copies at each look |
| D. Model | Muse Spark (contributor, low effort) reads the fab's state since the last look and proposes up to three settings, each with a reason; only those (and the current one) are tried on the copies |

The model sees only what a supervisor could: the measures since the last look (lots finished, waiting, queues by
group, machines down and for how long, wafers through each group since its last repair), the current setting and the
list of settings. It never sees a copy's results before proposing.

## Measures

Wafers out a day and days a wafer takes over the window; paired differences against A and against B with 95% t
intervals over the ten seeds; for the thesis, C minus B under wear against C minus B under clock. The same for D, and D
against C (does the model add anything over trying everything?).

## Then SMT2020, short

The same code on the SMT2020 testbed: 130 days of warm-up, a ten-day window, seeds 0 and 1, looks every 24 h, arms A,
C and D, wear on the polishing group (the bottleneck) against its clock breakdowns.

## What it costs (estimated before any run)

| Part | Runs | Simulator | Model calls | Model bill |
| --- | --- | --- | --- | --- |
| B's training (24 settings, 5 seeds, 2 kinds) | 240 short runs | under a minute | none | $0 |
| A, B, C on the toy (10 seeds, 2 kinds, 24 h and 48 h) | 120 runs; C tries 72 copies a look | about 5 to 10 minutes on 4 workers | none | $0 |
| D on the toy | 40 runs, 300 looks | about the same as C | 300 | about $0.10 (about $0.0003 a call, measured 30 Oct) |
| SMT2020, short (2 seeds, 2 kinds, 24 h) | 12 runs | about 10 to 20 minutes on 4 workers | 40 | about $0.02 |

Estimates, from the measured speeds (a two-day toy run in tens of milliseconds; a simulated SMT2020 day in about 0.03 s
on one core) and the contributor model's measured cost. Every run is niced, at most 4 workers, one heavy job at a time.
Nothing runs before the founder has seen this table.

## Tests (written before the code)

`crates/fabsim/tests/supervise.rs` (Rust):
- **SV1** a copy of a stepper, advanced alongside the original, ends exactly the same.
- **SV2** fresh luck on a copy moves its pending breakdowns and leaves the original untouched; two copies given the same
  fresh seed end exactly the same.
- **SV3** a cap set mid-run holds new releases: a day later the lots inside are no more than the larger of the cap and
  the lots inside when it was set.
- **SV4** a stepper built with an overrides file ends the same as the ordinary run with that file.
- **SV5** the simulator arm on the toy fab, over a short window, makes the same choices for the same seed, and every look
  records each setting tried, its score on the copies and the one chosen.
- **SV6** with a proposer, a look tries only the proposed settings and the current one, and chooses among them.

`agent/tests/test_supervise.py` (Python, no model called):
- **SP1** what the model is shown at a look holds only the past and the present, and lists the 24 settings.
- **SP2** a model's reply becomes at most three valid settings, each with its reason; anything else is dropped, and with
  none left the current setting stays.
- **SP3** the paired 95% interval on a known sample is right.

## Changes
