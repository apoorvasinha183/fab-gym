# Evidence after review

Written 31 October 2026, before the tests and the code. Argon reviewed Evidence; plan page ("Evidence Layout Plan", private); the founder: "lgtm go on quiz me".
By quiz: the contents bar slim at the top, staying as you scroll. On the SMT2020 testbed; not a real fab.

Found before: the first finding's chart draws every bar from the left by the size of its value, so the −$185k loss at
eight times the orders reads like a gain (`web/app.js`, the findings' bars); Evidence is 3,341 px of content in a
575 px box with two more scrolling boxes inside; every run's note is the same SMT2020 sentence; a notebook cell with
no capital and no gain prints a blank second line; amounts under $10,000 print in plain dollars.

## What changes

1. **Bars that cross zero.** The findings' bars grow from a $0 line, gains to the right and losses to the left, in
   proportion to their values.
2. **One word for each kind of run.** A run's badge uses the filter's word (study, search, training, contest, your
   change, your question; "sweep" goes), and each filter shows how many runs it holds.
3. **Money in one format.** Amounts of $1,000 or more print in k or M (`FabUI.usd3`: $7,527 is $7.53k); a notebook cell
   with no capital says "no capital", never a blank line.
4. **The contest side by side.** A contest's numbers have one row per measure: today's rule, then the change for the
   trained AI and for the evolved rule, each with its interval and verdict.
5. **A page, not a box.** Evidence fills the window under the title with no close button; inside it nothing scrolls on
   its own (the tables open to their full height), so there is one scroll; a contents bar (What we found · Lab notebook
   · Runs) stays at the top and jumps to each part. Evidence stays inside the Floor's panel: a separate page would mean
   re-plumbing the Floor, for the same result.
6. **Each finding links to its proof.** Every finding card ends with a link to the table or runs behind it.
7. **The disclaimer once.** "From the SMT2020 testbed, no real company's data, prices made up" is said once, at the
   foot; the runs' identical notes go.
8. **The right subtitle.** On Evidence the title card reads "What the simulator found, and every run behind it".

## Tests (written before the code)

`web/tests/evidencereview.test.mjs` (headless Chrome, a static server; nothing is spent):
- **EV1** every findings bar sits on the right side of the $0 line for a gain and the left for a loss, its length in
  proportion to its value.
- **EV2** every run's badge is one of the filters' words; no "sweep" shows; each filter's count equals the runs it shows.
- **EV3** `usd3(8000)` is "$8k" and `usd3(7527, true)` "+$7.53k"; no notebook cell prints plain dollars of $1,000 or
  more, and none has a blank second line.
- **EV4** a contest's table has one row per measure and a column for each contestant.
- **EV5** on Evidence the close button is hidden, nothing inside the panel scrolls on its own, the contents bar stays at
  the top, and each of its links brings its part to the top.
- **EV6** every finding card has a link that brings its proof into view.
- **EV7** the sentence about no real company's data appears once; the runs' SMT2020 notes are gone.
- **EV8** on Evidence the subtitle does not say running live.
- `web/tests/cleanup.test.mjs` (the money formatter) changes with item 3: $8,000 is $8k.

## Changes

- 31 Oct, while writing the code: replacing the bars' lines took the closing brace of their block with them (a syntax
  error caught before any run); the contents bar was see-through (the panel's colour is translucent) and stopped below
  the panel's top padding, so text scrolled visibly behind and above it; it is opaque and flush with the top.
- 31 Oct, results: EV1 to EV8 pass, and the page suite (238 tests, the paused floor coach's three left out) passes run
  one file at a time. Seen on the way: in every contest the evolved rule's changes are 0.0 (0.0 to 0.0), so on those days
  it chose exactly as today's rule did; the table now shows that plainly, side by side with the trained AI.
