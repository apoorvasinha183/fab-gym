# The glossary, for newcomers and experts

Written 1 November 2026, before the tests and the code. The founder: "Let's go back to the glossary, why don't we have
the meta tools improve the glossary with pictures ... we are targetting both the experts and the noobs", and the same
day, "Add images and flowcharts or figures inside the glossary as well". By quiz: all four ideas from the ideas page: a picture for every term by Muse Image, a newcomer line with an
expert fold, live numbers with Show me, and Ask the glossary; caps raised to a $5 glossary budget. On a teaching fab of
our own and the SMT2020 testbed; not a real fab.

The work comes in three parts, each with its own tests written first:
1. **Pictures, figures and two depths** (this part).
2. Live numbers from the run and Show me.
3. Ask the glossary.

## Part 1: what changes

1. **A picture for every term.** Each article opens with a picture in the cast's cartoon style. Where the cast already
   has one, it is reused at no cost:
   - Wafer, Lithography, Etch, Polishing (CMP) and Checks (metrology) use the cast's machines and wafer;
   - Lot, Hot lot, Batch, Rework, Defect hold, Queue-time limit and Move use the lots' pictures;
   - Breakdown, Repair time and Setup change use the polishing robot's moods.
   The other terms get a new picture from Muse Image (muse-image-1.0, $0.01 a picture), made once by
   `agent/glossary_pictures.py` with the cast's hero picture and two cast members as references, counted on the
   glossary meter, and kept with the page in `web/glossary/` (WebP, at most 384 px, at most 60 KB). The prompts are
   kept in `web/glossary/pictures.json` with every result. A picture is never bought twice: the script skips a term
   whose picture is on disk. The founder looks over a contact sheet before the pictures ship.
2. **Figures and flowcharts drawn by us.** Terms that are a process or a comparison get a figure drawn in the page as
   SVG from data (`web/glossary-figs.js`), each with a one-line caption. Twenty figures:
   - flows: Route, Lot (its life in the fab), Dispatch rule, Rework, Defect hold, Batch, WIP cap, Simulator,
     Reinforcement learning, E2 (evolutionary search);
   - states: Tool (idle, working, changing setup, maintenance, broken down, under repair);
   - timelines: Breakdown and Repair time (one figure), Queue-time limit, Setup change, Warm-up and Window (one figure);
   - comparisons: Hot lot (jumping the queue), Paired seeds, 95% interval, Verdict, WIP and Cycle time (Little's law,
     one figure).
   The figures use the page's own colours, name things as the page does, and invent no numbers: where a figure shows
   a number it is one the glossary already states (583 steps, 25 wafers).
3. **Two depths.** Each article leads with one plain line a newcomer can use (at most 20 words), beside the picture.
   Below it: the figure, "In this fab" and the example, as today. A fold, closed at first, holds the expert's version:
   the definition, a formula where one applies (Little's law, Kingman's queueing estimate, the paired difference, the
   t interval, Bonferroni, net present value, payback, straight-line depreciation, PPO's clipped objective), where the
   term comes from, and the range tried. Muse Spark (muse-spark-1.3-contributor) drafts the newcomer lines from each
   term's text, on the glossary meter; the founder signs them off before they ship, and the article says nothing about
   who drafted them.
4. **Plain words.** The new copy avoids our own jargon and machine-sounding phrasing.

## Part 1: tests (written before the code)

`web/tests/glossaryplus.test.mjs` (Node, and headless Chrome on a static server; nothing is spent):
- **GP1** every term has a newcomer line of 1 to 20 words ending in a full stop, different from its definition.
- **GP2** every term has a picture: a file in `web/glossary/` or `web/cast/` that exists, is WebP, is at most 60 KB and
  at most 384 px wide; the article shows it with the newcomer line as its alt text.
- **GP3** the twenty terms above have a figure; each draws as an SVG with a caption, every label sits inside the
  figure's view box, and no two boxes overlap.
- **GP4** the expert fold is a closed `details` holding the definition and where the term comes from, and the formula for
  the terms that have one; above the fold, no source label shows.
- **GP5** at 1,440 x 760 the picture, the term and the newcomer line are in view when an article opens.
- **GP6** `web/glossary/pictures.json` names a prompt for every new picture and the cast file for every reused one.

`agent/tests/test_glossary_pictures.py` (a stand-in for the model; nothing is spent):
- **GP7** the script makes only missing pictures, counts each on the glossary meter, stops at the cap with a plain
  message, and never writes the key into a file or a log.
- **GP8** the newcomer-line drafter sends only the glossary's own text, returns one line per term, and counts its tokens
  on the glossary meter.

## Changes
