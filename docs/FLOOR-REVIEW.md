# The Floor after review

Written 31 October 2026, before the tests and the code. Argon reviewed the Floor from a screenshot; the founder: "Try a
change and Words seem weirdly placed". Plan page ("Floor Layout Plan",
private); the founder: "lgtm" (all seven changes, in order, areas as muted mats). On the SMT2020 testbed; not a real fab.

## What changes

1. **One strip for actions.** Try a change sits beside the ask bar. Words becomes Glossary, beside How a chip is made.
   Follow one lot moves into the Lots in the fab card. The rail in the bottom-right corner goes.
2. **Two bugs.** The Lots waiting chart in the play bar drew only its cursor: its canvas was sized while the Floor was
   hidden behind Home, at 0 pixels. It is sized when drawn. The output rows name their unit: "55 lots (1,375 wafers)".
3. **Colours that mean one thing.** Areas become muted mats, darker than any state light; bright colours are kept for
   state. Measured as OKLab distance x100, normal vision and the three common colour blindnesses (Machado 2009, full
   severity): today the nearest area and state colours are 0.7 apart (Diffusion and broken down, tritan); the mats keep
   every area at least 12 from every state light, and the areas at least 7 from one another (normal vision; the labels
   name each area as well). Lithography `#6A5420`; metrology and inspection `#5C5C60`; etch `#6E3923`; Diffusion
   `#64284A`; films `#1F476E`; Ion implant `#4D3170`; Polishing `#075F55`. The legend gains an Areas key. Build keeps its
   colours.
4. **A panel you can point with.** Clicking a row in The fab now dims the floor and lights only what it names: a tool
   state lights the machines in that state; waiting lights the groups with lots waiting. Clicking the longest queue flies
   the map to that group. Clicking the row again clears it.
5. **A quieter map with visible tools.** Buttons on the map for zoom in, zoom out, fit and tilt (the keys stay). The
   Running badge is drawn only on the hovered group.
6. **Same hour yesterday.** Lots waiting, availability and the mean wait for a tool over the last hour carry an arrow
   and the change against the same time 24 hours earlier in this run. On day 1 there is no comparison and none shows.
   (Argon asked for a target; the full fab has none, so none is made up.) The mean wait row becomes the last hour's
   steps, so the comparison is like for like.
7. **A legend that folds.** Its title folds it; folded, the map takes the room. Remembered in this browser.

## Tests (written before the code)

`web/tests/floorreview.test.mjs` (headless Chrome; nothing is spent):
- **FR1** Try a change is on the ask bar's row and opens the change panel; Glossary is beside How a chip is made and
  opens the glossary; Follow one lot is inside The fab now; no rail is left in the bottom-right corner.
- **FR2** the play bar's chart canvas is its drawn size, and it has a line across at least half its width.
- **FR3** every count in Output says lots or wafers.
- **FR4** the legend's Areas key names all eleven areas; the mats keep the distances above against the state lights and
  one another.
- **FR5** after clicking broken down, exactly the machines broken down are lit; again clears it; clicking waiting lights
  exactly the groups with lots waiting; clicking the longest queue brings that group to the middle of the map.
- **FR6** the four map buttons do what their keys do; with nothing hovered, no Running badge is drawn.
- **FR7** on day 2, each comparison equals the reading now minus the reading 24 hours earlier, and the panel shows it; on
  day 1 none shows.
- **FR8** folding the legend widens the map; a reload keeps it folded; unfolding and reloading opens it.
- `web/tests/floorhealth.test.mjs` **FH1** changes with item 6: the wait row is the last hour's.
- `web/tests/sitecuts.test.mjs` **K4** changes with item 1: the rail of two is gone; Try a change and Glossary are
  checked where they now are.
- `web/tests/cleanup.test.mjs` **1** changes with item 1 the same way.
- `web/tests/sitecuts.test.mjs` **K6** (at most 13 controls on the first screen) changes with items 5 and 7: the map's
  four buttons and the legend's fold make 17.

## Changes
