# One bar for anything, on the Floor

Written 1 November 2026, before the tests and the code. The founder: "the ask the fab thing should be capable of
anything yeah? Keep things simple and intuitive". By quiz: rules first, the model only if unsure; in the first cut,
words and right now, a what-if as a run, take me there, and a change as a proposal you confirm; the Floor first. On the
SMT2020 testbed; not a real fab. Agents propose, the simulator scores, a person signs.

Found before: the Floor's bar sends every question to the simulator's question path (a scenario written by Muse
Spark or matched to an example), except questions about meaning, which go to the glossary since this morning. Asking
what the floor is doing now, opening a run or a challenge, or changing a setting by words is not possible.

## What changes

1. **The bar reads the question first, with plain rules** (`FabAsk.route`, no model):
   - **Take me there**: "open", "go to", "take me to", a run's number (Q-0002, S-0001, B-0003, F-0001), a challenge
     ("challenge 2", "Build"), Simulation settings, the glossary, Evidence or Runs; "show me" something the floor can
     light, or a machine group by name.
   - **A change**: "double the breakdowns", "breakdowns 50% worse", "cap lots at 400", "use first come, first served",
     "demand up 20%", "no urgent lots", "quality holds on", "take Planar_FE_79 down for 8 hours"; and a what-if whose
     change can be read the same way ("what if breakdowns double?").
   - **Right now**: "how many…", "now", "currently", "longest line", "busiest", "bottleneck", "backed up", naming what
     the run can count (broken machines, setups, lots waiting, an area, urgent lots, wafers out, cycle time).
   - **Words**: "what is…", "what does … mean", "why…", "explain…" (the glossary, as this morning).
   - **A what-if as a run**: "what if…", "would…", "should…", "which…": the simulator's question path, as today.
   - Anything else is **unsure**.
2. **Unsure goes to Muse Spark, which only picks a tool**: one of the five above with what it needs (a term, a place to
   go, a change, or the question for the simulator), or none. It writes no answer of its own and no numbers. With no
   model, or when it picks none, the bar says what it can do, with an example of each.
3. **Every answer has three parts**: the answer in plain words, where it came from (the live floor at its fab time, a
   glossary entry, a run's number), and one button (Show me, Open, Apply, Open the run).
4. **A change is a proposal.** The card names the change in words ("Breakdowns ×2") and changes nothing until you press
   Apply; Apply sets the Floor's Simulation settings to it and runs it against today on the same 10 random runs, which
   is kept as an S run. Cancel leaves everything as it was. Values beyond a setting's range are named, not applied.
5. **Right now** answers with the Floor's own count (the glossary's Right now lines, part 2) and Show me.
6. **Take me there** goes there: the page or tab opens, a run's card opens, Show me lights, a group is flown to.

## Tests (written before the code)

`web/tests/onebar.test.mjs`, in Node on `web/ask.js`:
- **OB1** the rules route a table of questions to their kinds, with what each needs; the three example questions stay
  what-ifs; words stay words.
- **OB2** changes are read from words: multiples (double, half, ×2, 2x, 50% worse, 20% fewer), caps, rules, urgent lots,
  quality holds, an outage of a named group for some hours; a value beyond a setting's range is marked.

In headless Chrome, the Floor from a helper started with `--no-model` (a recorded reply stands in for the model):
- **OB3** "How many machines are broken right now?" answers with the Floor's own count and Show me lights them.
- **OB4** "open challenge 2" opens Build on challenge 2; "open simulation settings" opens its panel; "open S-0001"
  opens that run's card; "show me the longest line" flies to it.
- **OB5** "double the breakdowns" shows a proposal and changes nothing; Apply sets breakdowns to ×2 and starts the
  comparison against today; Cancel on another proposal leaves the settings as they were.
- **OB6** "what if breakdowns get 50% worse?" is a proposal (×1.5); a question no rule can read goes to the model, whose
  recorded pick is followed; with no model it says what the bar can do.

`agent/tests/test_bar.py`:
- **OB7** `/api/bar/route` follows a recorded pick only when its kind is one of the five, its term is a glossary word
  and its change reads; anything else is none; with no model it calls nothing and says so.

## Changes
- Built 1 November 2026 (tests first, "Front desk"; code "Concierge"). All seven pass, with the Floor's other suites
  (cleanup, glossary, floor, Simulation settings, runs, stages, evidence) and the helper's tests.
- "How…" questions go to the glossary only as "how do/does/did…" ("How does a batch work?"); "how is the fab feeling"
  was read as a words question before, and the spec's list never had "how".
- A slider moves in steps (urgent lots, rework and quality holds by 0.5, breakdowns and repair by 0.25, the cap by 100),
  so a value between two steps is rounded to the nearer and the card says so ("×0.8 becomes ×1").
- Apply presses the Floor's own Run: the floor plays the change, then compares it with today. The panel names the
  change at once ("breakdowns ×2: simulating…").
- The model's pick spends from the glossary's budget (`spend-glossary.json`), under the helper's total. A go or a change
  it picks is rephrased into the bar's words and read again by the same rules on the page, so the rules decide what
  happens; the helper drops a pick whose words no rule could read (`agent/bar_route.py`).
- Settings you had already moved stay, and the card names them.

## Part 2: measure first

The founder, 1 November: "what if route the first question from a cheaper model first?" By quiz: measure first. Before
any cheaper model goes in front of Muse Spark, count how often the rules miss and what the model picks then.

1. **Every question typed in the bar is one line** in `bar-log.jsonl` beside the helper's spend files (under `data/`,
   never committed, never sent anywhere): the time, the question, who read it (`rules`, `model`, `stand-in` or
   `none`), the kind read and its detail, and the model's cost. The page sends the rules' reading
   (`/api/bar/log`); the helper writes the model's pick itself (`/api/bar/route`).
2. **A report**, `python -m agent.bar_route report [LOG]`: questions, the share the rules read and by kind, the misses,
   what the model picked for them (none included), what it cost, and the misses themselves, newest first.
3. Nothing in the bar's behaviour changes. A test helper writes its log into its own temporary folder.

Tests (written before the code), `agent/tests/test_bar.py`:
- **OB8** a question the model reads and one with no model each write one line, with who read it, the kind and the
  cost; `/api/bar/log` writes the rules' reading; a malformed reading is refused and writes nothing.
- **OB9** the report counts questions, the rules' share and kinds, misses and the model's picks and cost, and lists
  the misses newest first.
- Part 2 built 1 November 2026 (tests "Clipboard", code "Head count"); OB8 and OB9 pass with OB1 to OB7. The log sits
  beside the runs folder (`data/ask/bar-log.jsonl` by default). Page tests start their helpers with their own runs
  folder, so their questions land in a temporary folder and never reach the founder's log.
