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
