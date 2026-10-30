# Plain words on every screen

Written 31 Oct 2026, before the code. The founder: "Improve the language on the screens, it makes no fucking sense. As
I said talk like a human". A pass over the landing, the floor (labels, legend, Change, Numbers and Ask panels), the
Results cards and the editor: everyday words first; the technical terms (dispatch rule, WIP cap, PPO, seeds, paired
intervals) stay in the Glossary and in each run's details, where people who want them look. The founder's guidance
on the wording: "Use proper concise sentences. Inviting tone".

| Was | Now |
|---|---|
| Dispatch rule | Which lot a free machine picks next |
| Take a tool group down | Switch off a machine group |
| WIP cap | Cap on lots inside |
| Defect holds | Quality holds |
| Simulate and compare | Run it and compare with today |
| tools working / moves, last hour | machines busy / deliveries, last hour |
| Waiting heat / Flows | Queues / Routes |
| PPO, E2 | the trained AI, the evolved rule |
| spine stretch, vehicles, rail | main track, cars, track |
| hot lot, defect holds | urgent lot, quality holds |
| scenario | experiment |
| Cycle time / Worst queue / Spend on top | Days a wafer takes / Longest line / Extra spend |
| Process areas / Logistics / Wafer start / Ship point / Stocker | Machines / Moving wafers / Wafers in / Wafers out / Storage |

Challenge titles stay as the founder chose them. The example questions stay word for word, since recorded answers
are matched to them.

## Tests (written before the code)

`web/tests/plainwords.test.mjs`.

The tests commit also moves three older asserts to the new words (`cleanup.test.mjs`: the lens names, the cap's name in
a candidate, "urgent lot" in the floor key).
