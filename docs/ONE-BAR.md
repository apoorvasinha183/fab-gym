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
