# The editor at the floor's speed

Written 31 October 2026, before the tests and the code. The founder: "you gotta speed up the sims bruh takes forever in
the editor, the floor one is so snappy this one is slow af". On a teaching fab of our own and the SMT2020 testbed; not a
real fab.

## What was slow (measured 31 Oct, headless Chrome, 1440 x 900)

- **The runs are fast.** Every run the editor asks for takes 33 to 108 ms in the helper (all four challenges and Free
  build), and drawing holds 60 frames a second with about 33 ms of script a second.
- **Playback is slow.** The editor plays at "60×", which is 60 fab seconds a real second: one fab minute a second, an
  hour in a minute, a two-day run in 48 minutes. The floor opens at 60 fab minutes a second, 60 times faster.
- **Edits wait.** After each edit the page waits 600 ms before checking and running again, and a pause mid-drag can start
  a run before the drag ends.
- **A whole run's cars are too big to fetch after every edit**: 14 MB, 269,072 stays, 628 ms for two days.

## What changes

1. **One speed button, the floor's.** 1×, 3× and 12× are 20, 60 and 240 fab minutes a real second, the floor's own
   steps. The editor opens at 1×: an hour in 3 seconds, a two-day run in under 3 minutes. The menu with "15× slow
   motion" goes. Cars that are moving blur at the faster steps; cars that are stuck stand still, so a jam stays readable.
2. **Replay windows grow with the speed.** Each request for cars holds about 4 real seconds of play (at least 30 fab
   minutes), and the next one is fetched when 2 real seconds are left, so playback does not wait for the helper.
3. **Edits run sooner.** The checks and the new run start 250 ms after an edit, and never while a drag is still held:
   they wait for the release.

## Tests (written before the code), `web/tests/editorspeed.test.mjs`

In Node, on the page's files:
- **V1** the editor has one speed button (`<button id="speed">`), no speed menu and no "slow motion".

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **V2** the button starts at 1× and cycles 1×, 3×, 12× and back.
- **V3** at 1× the clock moves 30 to 60 fab minutes in 2 real seconds.
- **V4** at 12×, sampled every 100 ms for 3 s, the clock stands still at most twice (a jump back to the start of the run
  and the samples just after it do not count).
- **V5** after an edit (one more car), the new run is in within 500 ms of the click.
- **V6** a track drag held still for 900 ms starts no run; after the release a run starts within 1 s.
- **V7** a rerun keeps the tool in your hand (added while writing the code; see Changes).

## Max, on both pages

Added 31 October 2026, before its code. The founder: "Can you allow an uncapped option?", then by quiz: Max, as fast as
the page draws, on the editor and the floor.

4. **A fourth step, Max**, after 12× on both pages' speed button: one fab hour each drawn frame (about 60 fab hours a
   second on a 60 Hz screen), so a two-day run goes by in about a second. In the editor the run loops back to its
   opening hour; the floor stops at the end, as it does at every speed. The editor draws no cars at Max and asks for no
   car replay (they would only flicker); machines, lines of lots and jams still change hour by hour. Going back to 1×
   brings the cars back.

- **V2** (changed with this section) the button cycles 1×, 3×, 12×, Max and back.
- **V8** at Max the editor's clock moves an hour or more between at least 14 of 20 samples taken 30 ms apart.
- **V9** at Max the editor draws no cars and asks for no car replay for a second.
- **V10** back from Max to 1×, the cars are drawn again within 1.5 s.
- **V11** the floor has Max too: its clock moves 10 fab hours or more in half a second, or reaches the end.
- The floor's **K9** (`web/tests/sitecuts.test.mjs`) changes with it: the button cycles 1×, 3×, 12×, Max and is back
  where it started after four presses.

## Changes

- 31 Oct, while writing the code: the helper does one job at a time and answers "busy" to the rest. A check or a run that
  met a car-replay request was treated as an error and dropped (V6 failed 2 runs in 3), and the first window after a
  jump could freeze playback the same way. Checks, runs and that first window now wait their turn (`postWait`), and the
  prefetch steps aside while a run is pending and backs off 120 ms after a "busy".
- 31 Oct, while running the older tests: a finished rerun put the editor back in its old "run" mode, which emptied the
  hand (a leftover of the Run and Build modes cut in docs/SITE-CUTS.md). With reruns 250 ms after an edit, the foreman
  keys' P2 caught it under load: Q picked up Track and a rerun put Select back. A rerun now keeps the tool in hand. V7
  added for it, failing before the fix and passing after.
- 31 Oct, results: V1 to V7 pass (V6 failed once in four right after the busy fix, then passed ten in ten), and 147 of
  148 page tests. The one failure is the floor's S2 (the full run within 6 s: 7.3 s), with the laptop's load near 13
  (desktop browser windows, the Lean batch and this suite); this change touches only a comment in the floor's code, and
  S2 passed in every earlier full run.
- 31 Oct, the disk: the page tests made a headless Chrome profile per browser in the temp folder and never removed it
  (about 2.4 GB by this afternoon), which helped fill the laptop's disk. Every browser test now removes its profiles
  when its file's tests end (`profileDir`); a full run of the 152 page tests leaves none behind.
- 31 Oct, Max: V2 to V11 pass and all 152 page tests, the floor's K9 with its fourth step.
