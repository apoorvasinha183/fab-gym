# The floor in under a second

Written 31 October 2026, before the tests and the code. Decided by quiz the same day (`~/HACKATHON-README.md`): the
review "The first five minutes", direction A (story
first, then sandbox), and speed first, then the editor basics. From the SMT2020 testbed; not a real fab.

## The problem, measured

A cold link to `index.html#floor` draws nothing for 5.4 s (headless Chrome on this M1, 31 Oct), then plays at 60 fps.
All of it runs before the first frame, on the page's only thread:

| Part | Seconds |
|---|---|
| files (page, simulator, building, fab file) | 0.3 |
| `fg_run`, 3 days of the fab with its fleet | 0.9 |
| `fg_moods`, every group's mood every 30 minutes | 2.5 |
| `prepare`, the run's 420,726 trace numbers and 24,141,490 fleet numbers turned into playback lists | 0.8 |
| setup and the first draw | 0.8 |

Home already loads the fab in the background, so the wait shows mostly to people arriving by a link.

## What changes

1. **The first hours first.** The page runs the first 6 hours of the same run (same seed, same fab), which takes a
   small fraction of the time, draws it and starts playing. The simulator is exact and deterministic, so those hours
   are the start of the full run, event for event (test S1).
2. **The full run off the page's thread.** A worker (`web/simworker.js`) loads the simulator, runs the 3 days and
   works out the moods, and hands the arrays over without copying them. The page swaps the full run in at the moment
   it is playing, so the clock never jumps.
3. **No long freeze after the first frame.** Turning the full run into playback lists either happens in the worker or
   in slices short enough that no task on the page's thread lasts over 250 ms.
4. **Moods when they are ready.** Until the moods are in, a hover card says "Working out how it's doing…" instead of
   a mood.
5. **Nothing else changes.** Seed 0, 3 days: 70,131 moves, as today; every earlier page test still passes.

Page markers for the tests: `document.body.dataset.floor` is `drawn` once machines are on screen, `full` once the
3-day run is in; `dataset.moods` is `in` once moods are in. `window.FabFloorPage` (read only) gives the run's moves
and a group's mood now.

## Tests (written before the code), `web/tests/speed.test.mjs`

- **S1** the first 6 hours of a run equal the start of the 3-day run: every trace row and every state change with a
  time up to 6 hours is the same, in the same order (the simulator in Node, the US building's fab file with its fleet).
- **S2** from a cold link in headless Chrome at 1440 × 900: machines drawn within 1,000 ms of navigation; the clock
  moving within 1,500 ms; the full run in within 6,000 ms, with 70,131 moves; and no task on the page's thread over
  250 ms between the first draw and the full run.
- **S3** before the moods are in, a group has no mood and the hover card says so; once they are in, every group has
  one.

S2 and S3 need Google Chrome at its usual place and skip without it. Times are this laptop's.

## Changes

(none yet)
