# Runs you can watch and find again

Written 1 November 2026, before the tests and the code. The founder, after a question ran 15 minutes behind a timer: "I
think we need live simulation logs ... You should actually assign an id to it so that folks can access it later ... we
need to graphically show the layout ... the big thing is simulator here which is modular and if that is bad the rest is
bullshit". Ideas page (private). By quiz: all six ideas; a run lives on its own
Runs page; run numbers by kind (Q-0004 for a question, S-0012 for Simulation settings). On a teaching fab of our own and
the SMT2020 testbed; not a real fab.

Found before: the simulator writes nothing until it ends (the same question took 14 min 52 s on 29 Oct and 15 min tonight:
5 setups, 10 random runs each, 240 days per run); the helper numbers jobs 1, 2, 3 from zero at every start, so a new run
overwrites an old one's folder; the page never shows the number; each layout candidate is a whole new floor plan (71
groups moved for "copies in the halls") that the answer names but never draws; the answer prints engine codes ("said",
"b-first") and says Muse Spark wrote the setup even when a hand-written example answered.

The work comes in three parts, each with its tests written first:
1. **Live, numbered runs** (this part): the engine reports as it works; runs get permanent numbers; the Runs page shows
   the list and a run card with the live log, the grid of runs and the intervals forming.
2. The layout drawn on the card, and any one run opened on the Floor.
3. Simulation settings, Build and Floor runs in the same list.

## Part 1: what changes

1. **The engine reports as it works.** With `--events`, `fabsim score` writes one JSON line per event to standard error,
   each starting `event `: the start (setups, random runs, days), each floor laid out (from the saved layouts or new,
   groups placed, groups copied, seconds), each run finished (setup, random run, profit a day, volume wafers a day,
   seconds) and the end. The report on standard output is unchanged, byte for byte.
2. **Permanent numbers.** A question's run is numbered Q-0001, Q-0002 and on; the number is never reused, across helper
   restarts, because the next number comes from the runs already on disk. Each run keeps its folder
   (`data/ask/runs/Q-0004/`: the setup, the log, the report). Old jobs in `data/ask/jobs/` are left as they are.
3. **The helper keeps the log.** It reads the engine's lines as they come, stamps each with the seconds since the start,
   saves them to the run's `log.jsonl`, and serves them: `/api/job/Q-0004?since=N` gives the events after the Nth, with
   the stage, runs done of runs in all, and, once two runs are done, the minutes left (from the pace so far).
   `/api/runs` lists every run on disk, newest first: number, kind, question, when, status, runs done, the leader.
4. **A Runs page** (`runs.html`, a Runs tab beside Evidence on every page). The list, and a run card opened by its
   address (`runs.html#run=Q-0004`), which shows:
   - the number, the question, where the setup came from (Muse Spark, a hand-written example, or written by hand), what
     you said, the setups compared in plain names, the random runs and days;
   - the stage rail (read the question, check the setup, lay out floors, simulate, compare, sign) and the log in plain
     words, newest at the bottom;
   - a grid with a square for each setup on each random run, filled as runs finish and coloured by profit against today
     on the same random run;
   - each change's 95% interval of profit a day against today, recomputed as runs finish (paired t, the run's own
     Bonferroni level), final when all are in, with the verdict and the leader.
5. **The ask panel** names the run and links to its card, with runs done and minutes left, while it runs.
6. **Plain words.** Setups go by plain names (prototypes first; copies in the halls; copies in the halls, and prototypes
   first; their own wing); "said" reads "You said"; the line about Muse Spark shows only when Muse Spark wrote the setup.

## Part 1: tests (written before the code)

`crates/fabsim/tests/progress.rs`:
- **RN1** on a small two-family question, the events come in order (start; one floor event per setup; one run event per
  setup and random run, carrying its profit; end last), and the report is the same with and without events.

`agent/tests/test_runs.py` (the helper with short smoke runs; nothing is spent):
- **RN2** a question's run is Q-0001, the next Q-0002; a new helper on the same folders numbers the next Q-0003; no run's
  folder is written twice.
- **RN3** a finished run's `log.jsonl` holds every event with its seconds; `/api/job/Q-0001?since=N` returns only the
  events after N, the stage, runs done and runs in all.
- **RN4** `/api/runs` lists the runs on disk newest first, with number, kind, question, status and leader, and still lists
  them after a restart.

`web/tests/runs.test.mjs` (headless Chrome and a helper with smoke runs):
- **RN5** every page has a Runs tab; the Runs page lists the runs; `#run=Q-0001` opens its card with the number, the
  question, the setups by plain name and no engine codes.
- **RN6** while a run works, the log grows, the grid's filled squares equal the runs done, and intervals appear once a
  change has two random runs; when it ends, the card shows the report's verdicts and leader.
- **RN7** asking on the Floor shows the run's number with a link to its card.
- **RN8** the Muse Spark line shows only when a model answered; an example's card says no model ran.
- `web/tests/sitecuts.test.mjs` **K1** lists the Runs tab on both pages, and **K6** allows 21 controls on the Floor's first
  screen: the Runs tab is one more.
- `web/tests/frontdoor.test.mjs` lists the Runs tab in the top bar on both pages.

## Part 2: each setup's floor on the card, and any run on the Floor (written 1 November 2026, before its tests and code)

The founder: "Runs part 2 go". Found before: a two-family question keeps each setup's fab file in its report (the
Floor's "On the floor" loads it), but a question with one family keeps none, so its setups cannot be opened anywhere; the
card names each setup's floor without drawing it; the grid's squares are not links; and the Floor plays its own random
run, never the one a question measured. The Floor's simulator in the page is the build of 31 October and does not read
the `dispatch` record (Build, part 4).

1. **Every setup keeps its fab file.** The scorer writes each setup's file into the report for every question, today
   first and then the candidates, as it ran them: the shocks and the candidate's changes applied, and its dispatch rule
   as a `dispatch` record when it is not today's ("prototypes first" stays a rule the page names). Scoring is unchanged.
   The page's simulator is rebuilt from today's engine, so it reads the record.
2. **The floor drawn on the card.** For a setup whose file places groups in the halls, the card draws its floor from
   above: each phase's spine, and each group as a mark on its side of the spine at its distance along it and its depth,
   coloured by area; copies are drawn in prototype pink, groups that stand somewhere else than in today's floor are
   ringed, and a line says how many of each. A question whose setups keep today's floor says so. The helper sends each
   setup's plan with the run (`plan`: the phases' lengths, every group's place and tools, the moved and the copies).
3. **Any run on the Floor.** Once a run is done, each square of the grid is a link, and each setup has one, that opens the
   Floor at `index.html?q=Q-0002&arm=3&run=4#floor`: the Floor loads that setup's file and plays that random run from
   its start, the whole run when it is 14 days or less, else its first 3 days. Its note names the run, the setup, the
   random run and the days shown, links back to the card, and says it is the run as scored: the same engine on the same
   file and random run.

## Part 2: tests (written before the code)

`crates/fabsim/tests/arms.rs`:
- **RN9** a one-family question's report carries one fab file per setup, today first; a setup with a rule carries its
  `dispatch` record and the others none; each file, run with no rule handed in, gives the same jobs, event for event, as
  the scorer's own setup run with its rule.

`agent/tests/test_runs.py`:
- **RN10** a two-family run's setups each carry a plan: every placed group with its phase, side, bay, place along the
  spine, depth and tools, and, against today, the copies and the moved groups; a one-family run's setups carry a file
  and no plan.

`web/tests/runs.test.mjs`:
- **RN11** a two-family run's card draws a floor for each setup, a mark for each placed group, the copies marked.
- **RN12** once the run is done every square of the grid links to the Floor with the run, the setup and the random run.
- **RN13** the Floor opened from such a link names the run and the setup, and its jobs and finished lots equal the
  engine's receipt of that setup's file on that random run for the days shown; for a one-family setup with its own rule
  too.

## Part 3: Simulation settings, Build and Floor runs in the same list (written 1 November 2026, before its tests and code)

The founder: "Attack them in that order", Runs part 3 first. Found before: a comparison in the Floor's Simulation
settings lives only in that page's session list; Build's runs and the Floor's own runs are kept nowhere; the Runs list
shows questions only; and some page tests start a helper with no runs folder of its own, so their runs would land in
the real `data/ask/runs/`.

1. **Every kind of run is numbered and kept.** A comparison in Simulation settings is S-0001 and on, a Build run B-0001,
   a run of today's fab on the Floor F-0001, beside the questions' Q-0001. Each keeps its folder (`run.json`, its log,
   what it needs to be opened again). A run is the same every time it is played, so playing the same thing again
   (the same layout, settings and random run) is the same run and keeps its number; anything else gets the next one.
2. **Simulation settings.** When a comparison ends, the page sends it to the helper: the change in plain words, the
   settings, each of the 10 random runs for today and for the change with its four measures, and the four measures'
   intervals and verdicts. Its card shows the change, the table of measures (today, the change, 95% interval,
   verdict), the grid of the 10 random runs coloured by wafers out against today, and a link to open the Floor.
3. **Build.** Each scored run Build asks for is kept with its fab file, its breakdown settings and Build's own layout,
   its challenge or Free build, its random run and its score. Its card draws the layout from the fab file (each
   machine block and storage, the track), shows wafers a day, days a wafer and the extra spend, and "Open in Build"
   opens that layout again (`editor.html?run=B-0003`), as Free build, to change from there.
4. **The Floor.** When the Floor finishes playing today's fab on a random run, the run is kept with its days and
   numbers (lots finished, wafers out, moves). Its card links back to it (`index.html?run=4721#floor`). A question's
   run being watched on the Floor is that question's, and is not kept again.
5. **One list.** The Runs list names each run's kind (Question, Simulation settings, Build, Floor) and title, newest
   first, with chips to show one kind.
6. **Tests keep their runs to themselves.** Every page test that starts a helper gives it a runs folder of its own.

## Part 3: tests (written before the code)

`agent/tests/test_runs.py`:
- **RN14** a Simulation settings run sent to the helper is S-0001 and the next S-0002; a Floor run sent twice with the
  same key keeps one number; after a restart the numbers go on; the list names each run's kind and title, with the
  questions' Q- numbers unchanged.
- **RN15** a Build run asked for with `record` is B-0001 and keeps its fab file and Build's layout; the same layout on
  the same random run keeps B-0001; another random run is B-0002; the run serves its fab file, layout and score.

`web/tests/runs.test.mjs`:
- **RN16** a comparison in the Floor's Simulation settings is kept as an S run: the Runs list labels it Simulation
  settings, and its card shows the change, the four measures with the same intervals and verdicts as the Floor's
  panel, and a square for each of today's and the change's 10 random runs.
- **RN17** a run in Build is kept as a B run: its card draws a block for each machine group and storage in the fab file
  and a line for each track link, shows Build's wafers a day, and "Open in Build" opens a Build whose fab file is the
  run's.
- **RN18** today's fab played on the Floor is kept as an F run that links back to it; the list's chips show one kind
  at a time.
- Every page test that starts a helper passes it `--runs` with a folder of its own.

## Changes
- 1 Nov, while writing the code:
  - The engine's report goes to a file rather than a pipe, since a large report (3 MB) would fill the pipe and stop the
    events coming through.
  - A hand-written setup carries its question in its own question line, which the run now keeps.
  - `agent/tests/test_ask.py` and `test_sign.py` give their helpers a runs folder of their own, as do the page tests
    that ask questions (home, demo path, site cuts). Without it their runs landed in the real `data/ask/runs/`, and the
    five that did were moved out.
  - RN5 first started its second run while the first worked; the helper takes one at a time, so the test now waits.
  - RN6 first watched a run that ended in about a second, before the card opened. The helper gains `--threads`; the
    test helper uses one core and four changes, and opens the Runs page before starting the run, so the card is seen
    while it works. RN8 waits for RN7's run to end before asking.
- 1 Nov, part 2, while writing the code: RN13 first compared the Floor's lot-steps with the receipt's jobs, but a
  receipt's job is one batch on one tool, holding several lots; it now compares them with the lots the receipt's job
  lines list. The page's simulator (`web/fabweb.wasm`) is rebuilt from today's engine.
  `crates/fabsim/tests/ask_families.rs` once asserted that a one-family question keeps no setup files; it now asserts
  today's and the candidate's. The page hands in the three rules it runs itself (prototypes first, first come first
  served, quickest first) as before, and runs any other rule exactly only when the setup's file carries it: reports
  saved before this part do not, and the helper says which with `rule_in_file`; `web/tests/ask.test.mjs` checks both.
  On the Floor, the note naming the run sat inside the settings panel, out of sight, and the run's label read "Run #4"
  where the card says random run 5: a watched run now shows a banner in the row under the top bar (the run, the setup,
  the random run, the days shown, links back to the run and to today's fab), and the label reads "Q-0002 · run 5".
- 1 Nov, part 2, results: RN9 to RN13 pass; the simulator's whole suite, the helper's tests and every page test pass,
  run one file at a time (the paused floor coach's left out), with the two tests changed above. On the Floor, a
  two-family setup (copies in the halls) and a one-family setup with its own rule (first come, first served) play
  their scored runs exactly: the same lot-steps and finished lots as the engine's receipt.
- 1 Nov, the founder: "i hope the simulation tests are not burning any tokens? Check before interfering", and "No LLM in
  the testing path". Checked first: no test spent anything (Race the AI, posters and sketches run on recorded replies;
  questions use the examples or a written setup), but a test helper could see the real Meta key, so one test asking a
  question outside the examples would have spent. Now a helper started with `--no-model`, or under
  `FABGYM_NO_MODEL=1`, looks for keys nowhere; every page test's helper passes `--no-model`, the Python tests set the
  variable, and `agent/tests/test_no_model.py` checks all of it ("Air gap", tests; "Unplugged", code).
- 1 Nov, part 3, while writing the code: RN5 visits Build to check its Runs tab, and Build now keeps a run, so RN5
  reads the questions' rows only (the list also gained a Kind column). A runs test that failed partway left its headless
  browser playing the Floor for half an hour, slowing everything after it; the runs tests now stop every browser they
  started when the file ends.
- 1 Nov, part 3, results: RN14 to RN18 pass, with the helper's tests and every page test, run one file at a time (the
  paused floor coach's left out). `web/tests/speed.test.mjs` S2 (the floor drawn within one second from a cold link)
  passes and fails by turns at this Mac's load (about 6), with this part's code and without it alike, as noted before.
