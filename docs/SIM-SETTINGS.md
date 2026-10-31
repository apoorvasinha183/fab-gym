# Simulation settings

Written 1 November 2026, before the tests and the code. The founder: "When we run a sim where the fuck does it appear?
Is 'Try a change' really useful?", then, asked what it should become: "Cant we use something factual? Modify simulation
parameters or something?" By quiz: the name "Simulation settings"; this first, then the curves, then the glossary
(ideas page (private)). On the SMT2020 testbed; not a real fab.

## What was wrong (seen 1 Nov)

- The answer (the change against today on 10 paired runs, with intervals) sits under the Run button inside the panel,
  off screen at a laptop's size: breakdowns x2 gave −180 wafers a day (95%: −312 to −48) in 6 s, never in view.
- The run used random day 0 (the panel's own number, default 0), not the run on screen (Run #3665).
- The panel's title and its heading both said "Try a change", a name that says nothing about what is in it.

## What changes

1. **The name.** The button, the panel's title and the saved runs say "Simulation settings"; the panel opens on one
   line: "Change a setting, then run it against today on the same 10 random days."
2. **The run on screen.** The panel's run number follows the run on screen (Run #N), and the Floor's note names it
   ("run #N"). A different number can still be typed.
3. **The answer in view.** When the comparison arrives, the panel brings it into view.

## Tests (written before the code)

`web/tests/simsettings.test.mjs` (headless Chrome, a static server):
- **SS1** the button and the panel's title read Simulation settings, the panel's first line says what it does, and no
  "Try a change" shows.
- **SS2** opened at `?run=4721`, the panel's run number is 4721, and after a run the Floor's note names run #4721.
- **SS3** after a run at 1,440 x 760, the comparison's first row is in view inside the panel.
- `web/tests/sitecuts.test.mjs` **K4** and `web/tests/floorreview.test.mjs` **FR1** follow the name.

## Changes
