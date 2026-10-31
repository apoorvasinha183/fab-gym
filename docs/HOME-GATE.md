# Home's gate: play or watch

Written 31 October 2026, before the tests and the code. The founder, after Home after review (docs/HOME-REVIEW.md):
"ask the fab can no longer be a welcome gate, see there is absolutely no context at the gate". By quiz: Home offers two
doors, Play a challenge and Watch the whole fab at work; Ask the fab leaves Home, and its suggestions move to the Floor's
ask bar, shown when you click into it, where the fab runs behind them. On a teaching fab of our own and the SMT2020
testbed; not a real fab.

## What changes

1. **Two doors.** Home keeps Play a challenge (the four tiles and Start) and Watch the whole fab at work (the CEO, Watch
   it live), side by side and of the same weight. The Ask the fab door and its box go.
2. **Suggestions on the Floor.** Clicking into the Floor's ask bar opens a short list under it: the same suggestions
   Home had. Picking one puts it in the bar to read or edit; Enter asks. Escape or clicking elsewhere closes the list.
3. **⌘K** on Home opens the Floor with its ask bar ready.

## Tests (written before the code)

`web/tests/home.test.mjs`:
- **HO1** (changed) Home has no question box; on the Floor, clicking into the ask bar shows the suggestions, and picking
  one fills the bar and asks nothing.
- **HO4** (changed) Home's two doors, Play a challenge and Watch the whole fab at work, sit side by side without
  overlapping and in view without scrolling; Watch it live opens the Floor.
- **HO6** ⌘K on Home opens the Floor with the ask bar focused; Escape closes the suggestions.
- HO5 (the models by their jobs) moves with the line under the headline, which stays; the Ask door's own line goes.
- `web/tests/sitecuts.test.mjs` **K3**, `web/tests/frontdoor.test.mjs` and `web/tests/demopath.test.mjs` change with
  item 1: two doors, Play and Watch; the demo picks its worked example from the Floor's suggestions.
- `web/tests/sitecuts.test.mjs` **K8** and `web/tests/cleanup.test.mjs` **1** change with item 2: the worked examples are
  the ask bar's suggestions, and the top strip holds the suggestions' own list.

## Changes
