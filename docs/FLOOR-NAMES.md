# Floor: Legend and Fab status

Written 1 November 2026, before the tests and the code. The founder: ""What the marks mean" -> Legends , "The Fab now "
--> "Fab status/Usgae" something like this on the floor, and allow the status thing on the right to be hidden too , for
symmetry". On a teaching fab of our own and the SMT2020 testbed; not a real fab.

## What changes

1. The left panel's title reads **Legend**; the right panel's reads **Fab status**.
2. Fab status folds like the legend: its title is a button, folding hides everything under it, the map takes the room,
   and the browser remembers it (`fabgym.healthFolded`), as the legend remembers `fabgym.keyFolded`.

## Tests (written before the code)

`web/tests/floornames.test.mjs` (headless Chrome, a static server; nothing is spent):
- **FN1** the panels' titles are Legend and Fab status; the old titles appear nowhere on the page.
- `web/tests/sitecuts.test.mjs` **K6** allows 20 controls on the Floor's first screen: the fold button is one more.
- **FN2** the Fab status button folds the panel (only its title stays), the map is no narrower than before, the fold
  survives a reload, and a second press opens it again.

## Changes
- 1 Nov, results: FN1 and FN2 pass, with the Floor's other tests (health, review, curves, random runs, site cuts).
