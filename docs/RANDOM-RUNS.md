# Random runs to watch

Written 31 October 2026, before the tests and the code. The founder: "can you allow for some randomness in the window
simulations. I understand the background simulations being fair but there should be some variability". By quiz: the Floor
and Build both vary, and stars stay fair. On a teaching fab of our own and the SMT2020 testbed; not a real fab.

## What is fixed today

- The Floor always plays the same three days, random seed 0.
- Build always runs seed 1, so before and after an edit are comparable and the challenges' stars are calibrated on it
  (`editor-core.js`).
- Try a change and the experiments compare on the same seeds (paired), which stays as it is.

## What changes

The quiz said "a new day", but the clock already reads "Day 2 08:30", so a random history is called a **run**, shown as
"Run #4721".

1. **The Floor plays a random run on each visit,** numbered 1 to 9,999, shown in the play bar ("Run #4721") with a
   **New run** button. The number is in the address (`index.html?run=4721#floor`): opening that address replays the same
   run, so a run can be shared or watched again. `?run=0` is the run the Floor used to play.
2. **New run** on the Floor picks another number, puts it in the address and plays it; the first hours show at once and
   the full three days arrive behind them, as on a first visit.
3. **Build watches run #1, the challenge's own, at first.** Its **New run** button picks another number to watch. Edits
   rerun on the run being watched, so before and after stay comparable. The score cards, the goal bar, stars and "vs last
   run" always come from run #1, which is also run whenever another run is watched; a line says so ("Watching run #4721:
   698 wafers a day, 1.21 days a wafer takes. Stars count run #1, the challenge's own."). Changing challenge goes back to run #1.
4. Try a change, the experiments and Race the AI keep their fixed, paired seeds (Race the AI is scored like the player,
   on run #1).

## Tests (written before the code)

`web/tests/randomruns.test.mjs` (headless Chrome; nothing is spent):
- **RR1** the Floor with no run in the address picks one from 1 to 9,999, shows "Run #N" and puts `?run=N` in the
  address; three visits give at least two different numbers.
- **RR2** `?run=4721` twice gives the same run (moves and lots finished on day 2); `?run=0` gives the old run's 70,131
  moves.
- **RR3** New run on the Floor changes the number in the bar and the address, and the full run that arrives is a
  different one.
- **RR4** Build starts on run #1; after New run it watches another number while the score cards keep run #1's wafers a
  day, and a line names the run watched and its wafers a day.
- **RR5** an edit after New run asks the simulator for the run watched and for run #1, and nothing else.
- `web/tests/speed.test.mjs` **S2** opens `?run=0`, since its count of moves is the old run's.
- `web/tests/sitecuts.test.mjs` **K6** allows 18 controls on the Floor's first screen: New run is one more.

## Changes

- 31 Oct, while writing the code:
  - A new run on the Floor stops the full run still being worked out in the background and ignores anything it sends,
    so an older run can never be swapped in over a newer one.
  - Build runs the run watched and then run #1, one after the other, only while another run is watched; on run #1 there
    is one run, as before.
- 31 Oct, results: RR1 to RR5 pass, and the page suite (210 tests, the paused floor coach's three left out) passes run
  one file at a time, once K6 allowed New run.
- 31 Oct, seen live on challenge 1 (run #1: 650 wafers a day, 1.17 days a wafer takes): run #8614 also gave 650, since
  the small fab's output is set mostly by how fast lots are released, so the line about the run watched adds the days a
  wafer takes; runs #1332 and #2752 gave 738 wafers a day in 0.88 days and 625 in 1.19.
