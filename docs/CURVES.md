# Live curves

Written 1 November 2026, before the tests and the code. The founder: "we need to generate live curves". By quiz: a
drawer of charts on the Floor and in Build, after Simulation settings and before the glossary (ideas page (private)). On a teaching fab of our own and the SMT2020 testbed; not a real
fab.

## What changes

1. **A Curves button** in the play bar opens a drawer of small charts above it; the button closes it again.
2. **On the Floor, four charts**, read from the run on screen every 20 fab minutes: lots waiting for a tool, lots
   finished, the mean wait for a tool over the last hour, and the share of tools working. **In Build, three**, from its
   hourly frames: lots waiting, lots finished and tools busy (Build's frames do not record waits per step).
3. **They draw as the clock runs:** each line stops at the playhead, a thin line marks now, and the latest value is
   written beside the chart's name. Scrubbing the time moves them back.
4. **Your settings against today.** After a Simulation settings run, the Floor plays the changed run, and each chart
   draws it over today's line on the same random run, with a key ("today", "your settings"). One line each: the
   comparison's ten runs keep only their totals, so there is no band.
5. **Nothing new is simulated** and no model is called.

## Tests (written before the code)

`web/tests/curves.test.mjs` (headless Chrome; the Floor from a static server, Build with a helper of its own):
- **CU1** on the Floor, Curves opens a drawer of four charts named as above, and closes it again.
- **CU2** each line ends at the playhead: moved to day 2, a chart's line ends within 2 px of its now line.
- **CU3** the latest values agree with the page's own readings at that time: lots waiting and lots finished equal the
  health panel's, the share of tools working its working count over 1,043.
- **CU4** after a Simulation settings run, each chart draws two lines and a key naming today and your settings.
- **CU5** in Build, Curves opens three charts whose lines end at the playhead, and the page still does not scroll at
  1,440 x 760.
- `web/tests/sitecuts.test.mjs` **K6** allows 19 controls on the Floor's first screen: Curves is one more.

## Changes
