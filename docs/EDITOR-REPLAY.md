# The replay and the score (editor take two)

Written 31 Oct 2026, before the code. Decided by quiz the same day: the editor opens on the fab running, with a
challenge and five scores on top, and the motion is **an exact replay** of the simulator's run. From the SMT2020 testbed
or a layout of its own; never a real fab. (Not to be confused with `docs/REPLAY.md`, the earlier floor-page replay.)

## The score (`fabsim::moods::score`, and `score` in `fabsim moods`)

| Score | How it is counted |
|---|---|
| Wafers out a day | wafers in lots finished during the run, divided by the run's days |
| Cycle time | by Little's law: the average wafers in the fab over the run's frames divided by wafers out a day, in days |
| Worst queue | the largest number of lots waiting at one group at any frame, and that group |
| Jams | rail stretches whose average time beyond free flow over the run is more than a minute |
| Spend | the plan's prices times its tool counts, in dollars (none when the plan has no prices) |

Each frame of `fabsim moods` also gives every group's queue (lots arrived and not started), in `group_names` order.

## The replay (`fabsim::moods::replay`, `fabsim replay`)

A vehicle crosses a 3 m tile in about a second, so a whole day of moves is millions of records. The replay is a
window: every stay of every vehicle on a rail stretch that overlaps `[from, to]` (`fabsim replay SHOP SEED --from T
--to T2`): the vehicle, the stretch and its two node names, the time in and out, whether it is loaded, and whether its
lot is hot. The page plays the window slowly and draws each vehicle along its stretch at its exact time.

## Tests (written before the code: `crates/fabsim/tests/replay.rs`)

1. Wafers out a day is the wafers finished divided by the days; cycle time is the average wafers in the fab divided
   by that.
2. The worst queue is the largest group queue in any frame, and the frame queues agree with the moods' queue count.
3. Jams count only stretches with more than a minute's average excess, so a free-running fab has none.
4. Spend is the prices times the counts, or none without prices.
5. A replay window holds only stays that overlap it; each vehicle's stays never overlap in time, and each starts
   where the vehicle's previous one ended.
6. Some vehicle in the window carries a hot lot when hot lots are released; loaded stays exist.
7. `fabsim replay` and `fabsim moods` (with `score`, `group_names` and frame `queues`) answer.
