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

## Part 2: live numbers from the run, and Show me (written 1 November 2026, before its tests and code)

The founder, by quiz: "Live wire" and "Show and tell". Found before: an article says what a word means in general and
in this fab, but never what it is doing in the run on screen; the Floor already lights machines by their state, lights
the groups with lots waiting, and flies to a group, from its status panel.

1. **Right now.** On the Floor, an article whose word the run can count opens with a "Right now" line under the plain
   line: the number from the run on screen at the fab time shown, kept up to date while the article is open. Each
   number is the Floor's own (its status panel's, or counted the same way):
   - Breakdown and Repair time: machines broken down now; Setup change: machines changing setup now;
   - Tool: machines working, idle, in maintenance, broken down and changing setup now;
   - WIP and Lot: lots in the fab now, and how many wait for a machine; Wafer: wafers out so far;
   - Cycle time: days a wafer has taken, over the lots finished so far;
   - Tool group: the longest line now, and how many lots are in it;
   - Lithography, Etch, Polishing (CMP), Checks (metrology): that area's machines, and how many are working now;
   - Hot lot: urgent lots waiting for a machine now;
   - Track (overhead track): lots on the move now;
   - Seed: the run number; Simulator: the days this page simulated and how long it took.
   A word the run cannot count has no such line.
2. **Show me.** Where there is something to point at, the line carries a Show me button. It closes the glossary and
   lights it on the floor, as the status panel's rows do: the machines broken down or changing setup, the machines in
   that area, the groups with lots waiting, the groups with urgent lots waiting, or it flies to the longest line. A note
   says what is lit; Esc or a click on the note turns it off.

## Part 2: tests (written before the code)

`web/tests/glossarylive.test.mjs` (headless Chrome, the Floor from a static server, paused):
- **GL1** Breakdown, Setup change, WIP and Lithography each open with a Right now line whose number is the Floor's own
  at that moment (machines broken down, changing setup, lots in the fab, the area's machines working).
- **GL2** Show me on Breakdown closes the glossary and lights exactly the machines broken down now; on Lithography it
  lights that area's machines and no other; on Hot lot it lights the groups where urgent lots wait.
- **GL3** a word the run cannot count (Bonferroni) has no Right now line.
- **GL4** the number follows the clock: played on and paused again, the line matches the Floor again.
- **GL5** Esc turns the light off.

## Part 3: Ask the glossary (written 1 November 2026, before its tests and code)

The founder, by quiz: "Explain like I'm five" and "Cited"; and the same day, "No LLM in the testing path". Found
before: the glossary is searched by a word's name only; a newcomer's question in their own words ("why do lots wait at
the polisher?") finds nothing.

1. **The Floor's own question bar.** A question about what something means ("what is…", "what does … mean", "why…",
   "explain…") goes to the glossary, which opens with the answer at its top; a what-if, or a choice between setups,
   goes to the simulator as before. (Changed while writing the code, see below.)
2. **Only the glossary's own entries.** The helper picks the entries that share the most words with the question (the
   term and its other names count most, then its plain line and meaning), at most six, and sends only those to Muse
   Spark (muse-spark-1.3-contributor, at low effort) with the question. The answer is two to four short sentences in
   plain words, and names after each claim the entry it rests on, as `[[Term]]`.
3. **Cited, or it says so.** A cited name that is not among the entries sent is dropped (its words stay, without a
   link); an answer citing none says the glossary does not cover the question, and lists the closest entries. Each
   cited entry is a link that opens its article.
4. **What it costs.** Each answer counts on the glossary meter ($5 in all) and shows its cost; at the cap the box says
   so and asks nothing. With no model connected, the box lists the closest entries and calls nothing.
5. **No model in the tests.** The tests run the helper with `--no-model` and a recorded reply (`--stand-in`), as Race
   the AI's do.

## Part 3: tests (written before the code)

`agent/tests/test_glossary_ask.py` (no network):
- **GE1** the entries picked for a question share its words, the term's names first; a question sharing none picks none.
- **GE2** an answer keeps only the citations of entries that were sent; an unknown citation loses its brackets and is
  not cited; an answer citing none is marked not covered.
- **GE3** the helper with a recorded reply answers with its citations and costs nothing.
- **GE4** the helper with no model and no recorded reply lists the closest entries, says no model is connected, and the
  meter does not move.
- **GE5** at the glossary meter's cap the helper refuses before calling anything.

`web/tests/glossaryask.test.mjs` (headless Chrome; the helper with `--no-model`):
- **GE6** with a recorded reply, an answer appears with a link for each cited entry, each among the entries sent, the
  made-up citation without one; a link opens its article; the line says it is a recorded reply that cost nothing.
- **GE7** with no model connected, the box lists the closest entries as links and says so.

## Changes
- 1 Nov, while writing the code: GP8's test gave the model no key file, and the model reads its key when it is made; the
  test now writes a stand-in key. The figures' first layout put yes and no labels on their arrows and cut off the hot
  lot's curve at the top; columns are wider, side labels sit beside diagonal lines, and a curve above the boxes gets room.
  Paired seeds are joined by dashed lines without arrowheads, since neither run leads to the other. The formula is set in
  the body font, which reads better than a code font for a sentence. The glossary has 66 terms (the plan said 69): 51
  new pictures and 15 from the cast.
- 1 Nov, newcomer lines: Muse Spark drafted all 66 in three requests for $0.15 on the glossary meter (the estimate was
  under a cent; the model spends most of its tokens thinking). Its drafts called wafers "plates", began 20 lines with
  "It is", and got five wrong (a dispatch rule picks a "batch", a move is "done for one batch"); we edited 59 and kept
  7, before the founder's sign-off.
- 1 Nov, pictures: 51 made for $0.51, none failed. The line drafter and the picture run each kept their own copy of the
  glossary meter's file, and the picture run wrote over the drafter's $0.15; the file was corrected by hand to $0.66 and
  the helper restarted to read it. Four pictures (Held-out seeds, PPO, Scenario, Genetic programming) mostly redrew the
  polishing robot from the references; at the founder's word they were redrawn ($0.04) with the polishing robot left out
  of their references, which a term may now name for itself in pictures.json. The glossary has spent $0.70 of $5.
- 1 Nov, results: GP1 to GP8 pass, and the page and helper suites pass run one file at a time, except the Floor's speed
  check S2 (the full run in within 6 s), which failed at 9.4 s with the laptop's load at 4 to 16 (a 15-minute question
  was scoring on 4 cores). Run alternately on the last commit and on this work under the same load, it failed 2 of 3
  times on each, so the load and not this change is the cause; the curves' calculation takes 9 ms of it.
- 1 Nov, part 2, while writing the code: the note naming what Show me lit first kept the count of the moment of the
  click ("20 machines broken down") while the run played on; it now names the thing ("the machines broken down now"),
  since the light follows the run. The Right now label first used a small monospace face, which the Floor's own rules
  forbid (`web/tests/cleanup.test.mjs` 13); it uses the page's face at 12 px.
- 1 Nov, part 2, results: GL1 to GL5 pass, with the Floor's and the glossary's page tests (review, health, names,
  corners, home, simulation settings, site cuts, journey, stages, chrome, evidence, cleanup, plain words, Build's find);
  the speed check S2 passes and fails by turns at this Mac's load, as before.
- 1 Nov, part 3, while writing the code:
  - GE2 first expected the entries in another order than the order they were sent; it now expects the order sent.
  - The first box sat at the top of the glossary, a second place to ask, which the Floor's own rule forbids
    (`web/tests/cleanup.test.mjs` 1: the top bar is the only question box). The founder had just asked for one bar that
    takes anything ("Keep things simple and intuitive"), so the question goes through the Floor's bar: a question about
    what something means goes to the glossary (`FabAsk.wordQuestion`, GE8), what-ifs and choices to the simulator.
    GE6 and GE7 ask through the bar.
  - Citations show as small chips that open their entry; a name the reply cites that was not among the entries sent
    keeps its words and gets no chip.
- 1 Nov, part 3, results: GE1 to GE8 pass, with the helper's tests and the Floor's and the glossary's page tests (the
  three example questions still go to the simulator); no test calls a model.
