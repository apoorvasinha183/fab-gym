# The floor page, redesigned

Written 29 October 2026, before the code. Directions and mockups: a private plan page.
On the SMT2020 model, with a layout of our own design; not a real fab. Agents propose, the simulator scores, a person
signs.

Decided by quiz on 29 October (`~/HACKATHON-README.md`): the blend of the four directions, plus a view of graphs and
solid numbers for every policy change, and the page opens on a question ready to ask.

## What a person sees

1. **Opening.** The floor runs quietly behind a centred prompt: "Ask the fab a question", the three example
   questions as buttons, and "or explore the floor". Nothing else is on screen until they choose.
2. **The floor (living diorama).** The fab drawn tilted in 2.5D: halls as raised slabs, each tool a raised block
   coloured by its state, lots riding a lit belt, prototype lots pink. The camera pans and zooms; clicking a hall
   selects it; "Follow a lot" keeps one lot in view along its route.
3. **Controls.** One command bar at the top (⌘K focuses it) for asking; lens chips (Day, Waiting heat, Prototype
   lots, Flows) change what the floor shows; one floating pill holds play, speed and time.
4. **An answer.** When a job finishes, the screen splits: today's fab on the left, the chosen candidate on the right,
   both played from the same seed on one shared clock and one scrubber; beneath them three verdict cards (money a day,
   volume wafers a day, prototype cycle time) with the mean, the 95% interval and better, worse or no clear effect.
5. **The numbers.** A view of graphs and solid numbers for the chosen share and measure: every change against today
   as a forest plot (mean dot, interval bar, exact numbers), the policies across shares as lines, and today's
   baseline. Every chart has titled axes with units and numbered ticks. It reads the two-family sweep's results, and
   a question's own report when there is one.
6. **The evidence.** A notebook view of one answer: what the model understood (said and assumed), what happened
   (play buttons for each arm), the answer, and "Sign this answer", which stores the person's name with a SHA-256
   of the question, the scenario and the report.

## The pure parts (`web/ui.js`)

- `iso(x, y, view)` maps floor tiles to the screen for a view (`{rot, tilt, scale, ox, oy}`); `isoInverse` maps back;
  `hallAt(halls, sx, sy, view)` picks the hall under a screen point.
- `niceTicks(lo, hi)` gives 3 to 7 round tick values spanning the range; `tickLabel(v)` signs them.
- `verdictOf(interval, higherIsBetter)` → `better`, `worse` or `no clear effect`; a missing interval is
  `no clear effect`.
- `sweepRows(summary, share, metric)` gives the forest plot's 14 rows (strategy, policy, mean, lo, hi, verdict,
  text) for one share and measure, and `sweepLines(summary, metric)` the four shared-floor policies across shares;
  `sweepBaseline(summaryMd, share)` is not needed: the baselines come from `summary.json`'s `baseline` field, which the
  build adds from the runs file (means of today's arm per share).
- `pairedClock(durA, durB)` drives two runs from one scrubber: `at(t)` gives both times, never past either run's end.
- `openingState(status)` gives the opening's prompt and its example questions, from the helper's status or, without
  a helper, from the recorded examples bundled in `web/data/examples.json`.

## Data

- `web/build.sh` copies `results/two-families/summary.json` to `web/data/two-families.json` with a `baseline` field
  (today's mean money, volume wafers and prototype cycle days per share, from `runs.tsv`), and the three recorded
  example questions to `web/data/examples.json`.

## Tests (`web/tests/ui.test.mjs`, `agent/tests/test_sign.py`)

1. `iso` and `isoInverse` round-trip within 1e-9 for any view; `hallAt` finds the hall whose slab holds the point and
   nothing outside every slab.
2. `niceTicks` returns 3 to 7 values, evenly spaced by 1, 2 or 5 times a power of ten, covering the range; labels
   carry a sign.
3. `verdictOf` on intervals above, below and across zero, both directions, and on a missing interval.
4. `sweepRows` at ×4 money: 14 rows, today's shared floor left out, family B first on the shared floor
   +750.5 (+720.6 to +780.5) better; a missing prototype cycle reads as "no prototype lot out".
5. `sweepLines` gives four lines of four points; family B first on money crosses zero between ×4 and ×8.
6. `pairedClock` keeps both runs on the same time until the shorter ends, then holds it at its end.
7. `openingState` lists the helper's examples when there is a status, else the bundled ones, and always offers
   exploring the floor.
8. The helper signs: `POST /api/sign {job, name}` stores the name, the time and SHA-256 of question, scenario and
   report; a second signature of the same job is refused; a changed report no longer matches its signature.

## Changes

- 29 Oct, found by test 4 before any code: `results/two-families/summary.json` held a bare `NaN` for the three
  cells where the family cap let no prototype lot out (prototype cycle time), which is not JSON and which no browser
  reads. `fabsim two-families` now writes `null` for a number that is not finite, and the committed file's nine
  `NaN`s are spelled `null`; no number changed.
