# Moods from a run (the modular gym, deliverable 6)

Written 31 Oct 2026, before the code. The cast's cards (`web/cast/cast.json`) show each machine and each lot in a
mood. This deliverable reads those moods off a recorded run, so a card says what the simulator did. On the SMT2020
model; never a real fab.

## Settings (decided by quiz 31 Oct, except where marked assumed)

- Window: the last **8 hours** of fab time. Dozing off below **30%** working with nothing waiting; Gassed above
  **90%** working with the queue longer than at the window's start.
- Pulled a muscle: the first **15 minutes** of a breakdown (assumed); after that, At the physio.
- Losing patience: a lot waiting more than **8 hours** for its next step (assumed, the same window).
- Fresh recruit: a lot within **60 minutes** of release that has not started a step (assumed).

## A machine's mood at a moment

From its last state change before the moment (`RunResult::states`):

| State, reason | Mood |
|---|---|
| unscheduled down, hold | Benched (`hold`) |
| unscheduled down, first 15 min | Pulled a muscle (`hurt`) |
| unscheduled down, after | At the physio (`physio`) |
| scheduled down, setup | Changing kit (`setup`) |
| scheduled down, other | Rest day (`pm`) |

Otherwise, in order: **Hands full** (`full`) when, with a fleet, as many of its finished lots as it has ports are
still waiting to be picked up; **Waiting for the class** (`batch`) when standing by with lots waiting at a group that
works in batches; **Dozing off** (`sleep`); **Gassed** (`tired`); else **In the zone** (`work`). A group's queue at a
moment is its lots that have arrived and not started; a lot still waiting when the run ends has no start in the
record, so queues near the run's end are undercounted.

## A lot's mood at a moment

Not yet released: none. Finished: **Graduate** (`grad`). In a step: **On the bench** (`bench`). Aboard a vehicle
(between its hoist up and its hoist down): **Riding the rail** (`ride`). Waiting for its next step, the first that
applies: **Quarantined** (`hold`, held by a finding or a breakdown and not started since); **Missed the clock**
(`missed`, a queue-time limit from a finished step has run out); **On the clock** (`clock`, inside such a limit);
**Do-over** (`redo`, its next step is one it has done before); **Waiting for the class** (`batch`, the next step works
in batches); **Losing patience** (`impatient`); **Fresh recruit** (`fresh`); else **In line** (`line`). A lot whose
priority is at the hot level is marked **hot** in every mood.

## A rail stretch at a moment (with a fleet)

Its **jam**: over the window, the average minutes each vehicle spent on the stretch beyond the time at the layout's
speed. Zero on a free stretch.

## Interfaces

- `fabsim::moods::snapshot(&shop, &run, t, &Settings) -> Snapshot` (tools, lots and stretches at `t`).
- `fabsim moods SHOP SEED --until T --every M [--overrides FILE]`: JSON with the mood names, the tool names, and a
  frame every M minutes: each tool's mood, the count of lots in each mood, the hot lots' moods, and each stretch's
  jam.

## Tests (written before the code: `crates/fabsim/tests/moods.rs`)

1. Down states map to their moods: a breakdown is `hurt` in its first 15 minutes and `physio` after; a hold is
   `hold`; a setup `setup`; maintenance `pm` (on the SMT2020 model, from the run's own state changes).
2. A machine with little work dozes; one with more work than it can do is gassed.
3. A batch tool standing by with too few lots waits for the class.
4. With one vehicle and one port, a fast tool's finished lots pile up: it shows Hands full at some moment.
5. Lots: graduate after finishing, on the bench in a step, fresh just after release, in line while waiting, losing
   patience after 8 hours, hot when hot, riding the rail between hoists.
6. A lot past a queue-time limit (a recorded breach) shows Missed the clock just before its late step starts; a lot
   inside a limit shows On the clock.
7. A stretch with vehicles queuing behind a broken one shows more jam than without the break.
8. `fabsim moods` writes a frame every M minutes with a mood for every tool.
