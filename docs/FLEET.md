# The faithful floor, rungs L2 to L4: the track, the fleet and traffic

Decided by quiz on 29 Oct 2026 (page: "The Faithful Floor"). On the SMT2020 model, with a gigafab-style layout of our
own design; not a real fab. Every number below is assumed unless it says otherwise.

SMT2020 puts every tool at one location, `Fab`, and gives one move time for every move (uniform 7.5 ± 2.5 min).
Fab Gym's layout (`oht` in a shop) turns a move into 4 min + metres along the aisles ÷ 150 m/min, ± 1 min, in either
direction, with as many vehicles as needed. This adds, opt in, three things the model did not hold:

- **L2, the track.** A one-way graph built from the layout in the shop:
  - Each phase has a spine loop. Its north lane runs east past the north bays and its south lane runs west past the south bays, with a U-turn of the spine's width at each end.
  - Each bay has a loop. It leaves the spine lane at the bay's upstream end, passes every tool group's stop in order of depth, turns at the far end and rejoins the lane at the downstream end.
  - Crossovers between the two lanes come every `cross` metres, both ways.
  - The bridge has one lane each way, joining one phase's east end to the next phase's west end.
  - A trip to a stop just behind you goes round the loop.
- **L3, the fleet.** `vehicles` vehicles, each with a position and a job.
  - A finished lot waits at its tool group's stop until a vehicle comes for it.
  - The vehicle drives there empty, hoists the lot up, drives to the next group's stop, hoists it down, and the lot joins that group's queue.
  - Hoisting takes `hoist` minutes each way.
  - A tool cannot start new work while `ports` or more of its finished lots are waiting to be picked up.
  - An idle vehicle waits on a parking spur at the stop where it last dropped a lot, clear of the track.
- **L4, traffic.** Vehicles never pass one another.
  - Each stretch of rail between two stops or junctions holds at most its length ÷ `gap` vehicles (at least one).
  - Vehicles enter a stretch at least `gap` ÷ speed apart and leave it in the order they entered.
  - A vehicle stopped at a stop holds that stop, so the vehicles behind it wait.
  - A vehicle that cannot go on waits where it is.

Speed is the layout's (`oht` speed, 150 m/min). The `oht` overhead and jitter are not used once a fleet is given: the
empty trip, the hoists and the waiting replace them.

**The controller.** Each move is a request: the lot, the stop it waits at, the stop it goes to and when it was asked.
Requests are served oldest first. For each one, a vehicle controller picks one of the idle vehicles. It is given each
idle vehicle's stop and its track distance to the lot.
- Built in: `nearest`, the idle vehicle with the shortest track distance to the lot (ties to the lower number), and `first`, the lowest-numbered idle vehicle.
- A controller's pick that is not one of the idle vehicles is refused and counted, and `nearest` is used instead.
- Lots keep today's dispatching at the tools. Vehicles only, first.

**Shop record.** `fleet <vehicles> <gap m> <hoist min> <ports> <cross m> <controller>` after the `oht` records; it
needs an `oht`. Defaults for the realistic campus: hoist 1 min, from Yang (2023, Table 13: 60 s to load and 60 s to
unload); gap 3 m, ports 2 and crossovers every 60 m, assumed; `nearest`. A shop without `fleet` runs and writes
exactly as before.

**What a run reports** (`RunResult::fleet`):
- moves asked for and delivered;
- the wait from a lot's request to its pickup (sum, count and largest);
- request to delivery;
- loaded and empty metres;
- vehicle-minutes busy;
- vehicle-minutes held up, measured against free flow;
- tool-minutes blocked by full ports;
- refused picks.

With `record`, every vehicle's entries to each stretch and every hoist are also kept, so the viewer and the game can
replay the fleet.

`transport_minutes` with a fleet is counted when a lot is delivered, from request to drop.

## Tests (written before the code: `crates/fabsim/tests/fleet.rs`)

1. The track from the realistic campus reaches every stop from every stop, every stretch is longer than zero, and every
   tool group with a place has a stop.
2. No trip on the track is shorter than the aisle distance between the same two places.
3. The track is one way: some trips back to a stop just passed are longer than the trip forward, by at least a loop.
4. The `fleet` record reads and writes back; a shop without it writes no fleet line.
5. Every move asked for is delivered or still under way at the end, and the lots that finish are the lots delivered to
   their last step.
6. No passing: on every stretch vehicles leave in the order they entered, at least `gap` ÷ speed apart, never more on
   it than it holds.
7. A stop holds one hoist at a time.
8. Fewer vehicles, longer waits for pickup (30 against 150 vehicles, the same seeds).
9. Full ports block tools: one port and a small fleet blocks tools for some minutes; four ports and a large fleet blocks
   them for fewer.
10. The same seed gives the same run.
11. A vehicle controller is asked for every pick and its picks are used; a pick that is not an idle vehicle is refused,
    counted, and `nearest` is used instead.
12. A delivery takes at least the two hoists.

## Sources

- Yang Hyun, "Vehicle dispatching and idle vehicle operation of AMHS in FAB", master's thesis, Ajou University,
  February 2023, pp. 29 to 43 read: a spine layout of the author's own for SMT2020's dataset 4 (1,468 tools; 40 bay
  loops and 3 interbay loops, one-way rails), 250 vehicles at 5.0 m/s on straights and 1.0 m/s on curves,
  accelerating at 2.0 m/s² and braking at 3.5 m/s², 60 s to load and 60 s to unload. Rules compared: closest,
  oldest and least-used idle vehicle, and the fastest arrival counting busy vehicles. Idle vehicles circle their bay
  under a cap per bay.
- Nazzal and McGinnis, WSC 2005, p. 1: one-way closed loops, no passing even when a vehicle stops at a port.
- Schmaler et al., WSC 2017, pp. 1 to 2: empty vehicle management, the time tools wait for empty vehicles.

## Changes

- 29 Oct, before any code: the default hoist time changed from 0.3 min (assumed) to 1 min, cited from Yang (2023).
  The tests set their own values and are unchanged. One speed for straights and curves stays (the layout's
  150 m/min); Yang's curve speed and acceleration are a later refinement.
