# Floor: panels in the bottom corners

Written 1 November 2026, before the tests and the code. The founder sketched it (`~/redesign.png`: the folded Legend and
Fab status circled with arrows to the bottom corners) and said: "yes move both to the bottom corners also runs and the
ask bar collide now , fix that". On a teaching fab of our own and the SMT2020 testbed; not a real fab.

## What changes

1. **Legend in the bottom-left corner, Fab status in the bottom-right.** Each panel's title sits in its corner; opening a
   panel grows it upward, and a tall one scrolls inside rather than reaching the top bar.
2. **The play bar and the hint sit between the corners**, centred. Where the window is narrow the "Lots waiting" chart
   gets shorter and its label hides, so the bar never runs under a panel.
3. **The ask bar starts after the page's name and tabs**, so the Runs tab no longer runs under it.

## Tests (written before the code)

`web/tests/floorcorners.test.mjs` (headless Chrome, a static server; nothing is spent), at 1,280 x 720, 1,440 x 900 and
1,920 x 1,080, with both panels open and both folded:
- **FC1** the Legend's bottom-left corner and Fab status's bottom-right corner are within 24 px of the window's.
- **FC2** none of these overlap: the page's name and tabs, the ask bar, Simulation settings, the Legend, Fab status, the
  play bar, the map's buttons and the hint.
- **FC3** an open panel's top stays below the top bar, and every tab, Runs included, is clear of the ask bar.

## Changes
