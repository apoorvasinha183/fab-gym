# Evidence in plain words

Written 31 October 2026, before the tests and the code. The founder: "look at the evidence tab. Now question yerself like
a layman, how much of that makes sense to you?" The answer was about a quarter: the page opened on a profit table with
no setup, code-name labels ("Capped at the door", "Copies in the halls"), numbers without units ("103.9"), "never" for
"never pays back", a "BEST" mark on a $24.3M wing when holding prototypes back earns most of that for nothing, a study of
a different question stacked underneath, and a results list of mostly failed experiments, ending 29 Oct with the
strongest result missing (all 120 scored runs checked by the Lean referee). The founder: "yes rewrite evidence". From the
SMT2020 testbed; not a real fab. Every price is assumed.

## What changes

1. **What we found, first.** Evidence opens on four findings, each a plain sentence with one small picture, what we did,
   what it means for a fab, and how sure we are in words ("Sure", "Too close to call", "Exact: a check, not an
   estimate"). The numbers come from the same data files as the tables, through `web/evidence.js` (pure, run in Node
   too), so the words cannot drift from the tables.
   - **Rush prototypes.** A fab mostly makes one chip in bulk; a few customers send rush prototype orders that jump the
     queue. Holding prototypes at the door until there is room earns more at up to four times today's prototype
     orders, and costs nothing to build. At eight times it loses money on today's floor, and copies of the busiest tools
     in spare hall space pay instead.
   - **A cap on work inside.** Limiting how many lots are inside the fab gets each wafer out about a month sooner and
     costs no output we can measure in a normal fab; when machines break twice as often the same cap costs about 45
     wafers a day.
   - **Our trained AI.** On ten days it never practised on, it did worse than the fab's own rule for picking the next
     lot. Beating a well-tuned rule is the open problem this gym is for.
   - **Every scored run checked.** A separate program, whose rules are proved in Lean, re-read every one of the 120 runs
     behind our scores; all 120 passed.
2. **The lab notebook below.** The tables and the run list stay, under a heading that says they are the detail behind the
   findings, for readers who want it.
3. **Two fixes in the notebook.** Prototype cycle time carries its unit ("days"), and a change that never pays back says
   "never pays back".
4. **The Lean results as data.** `results/lean-check/summary.py` writes `web/data/lean-check.json` (runs, passed, jobs
   and state changes checked) from `results/lean-check/verdicts.tsv`; `web/build.sh` runs it with the page's other data.

## Tests (written before the code), `web/tests/evidence.test.mjs`

In Node:
- **EV1** `web/data/lean-check.json` agrees with `results/lean-check/verdicts.tsv`: 120 runs, 120 passed, and the jobs
  summed.
- **EV2** `FabEvidence.findings(...)` on the page's data gives four findings in order (prototypes, cap, AI, checked), each
  with a title, what we did, what it means, and how sure.
- **EV3** the prototype finding's numbers equal the profit grid's (holding at the door on today's floor at four times,
  and worse at eight times), and its text says it stops paying at eight times.
- **EV4** the cap finding uses the 1,800-lot cap: too close to call on output in a normal fab, about 30 days sooner, and
  about 45 wafers a day lost when machines break twice as often.
- **EV5** the AI finding comes from the contest with quality holds ×1: a score about 152 lower, sure.
- **EV6** plain words: no finding says Bonferroni, paired, seed, family A or B, a strategy or policy code, "policy", "×"
  or "interval".

In headless Chrome with a helper of its own in quick mode (skipped without Google Chrome):
- **EV7** `#evidence` opens on "What we found" with four finding cards, the first starting within the first screen.
- **EV8** a "Lab notebook" heading sits after the findings and before the profit table.
- **EV9** the notebook's prototype cycle time says "days", and a red cell reads "never pays back".
- **K7** (docs/SITE-CUTS.md) still holds: the cap study, the money table and the results are all on the page.

## Changes
