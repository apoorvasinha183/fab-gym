# Ask the fab: the scenario and the scorer

Written 27 October 2026, before the code. The protocol is the one fixed in `docs/PROBLEM.md`.

## The flow

1. A person asks a question.
2. Muse Spark Open answers with a scenario in JSON (`agent/schema.json`): the shocks the question
   describes, each tagged **said** (in the question) or **assumed** (with a range), and up to six
   candidate answers.
3. `agent` checks the JSON against the schema and refuses anything it does not allow (unknown
   groups, values out of range, more than six candidates, an assumed value without a range).
4. `agent` writes the scenario as text (`fabgym-scenario 1`) and runs `fabsim score`.
5. The card quotes only the scorer's numbers. The certificate records the question, the model's
   answer as received, the scenario, the scores and their SHA-256 hashes; a person signs it.

Until a key for Muse Spark Open is in place, the tests use recorded example answers, kept under
`agent/tests/fixtures/` and marked as fixtures. Nothing shown to a judge comes from a fixture.

## The scenario text (`fabgym-scenario 1`)

Tab-separated lines:

    fabgym-scenario 1
    question    <the question, one line>
    shock       breakdowns  <multiplier>              said|assumed
    shock       repair      <multiplier>              said|assumed
    shock       demand      <multiplier>              said|assumed
    shock       outage      <group> <from hour> <hours>  said|assumed
    shock       hot         <lots made hot>           said|assumed
    candidate   <name>      rule    today|fifo|spt|cr|random
    candidate   <name>      cap     <lots>
    candidate   <name>      spare   <group> <tools>
    candidate   <name>      demand  <multiplier>
    sweep       <shock>     <field> <low> <high> <points>

- Shocks apply to today's fab and to every candidate alike.
- Lines with the same candidate name build one candidate; each candidate starts from today's rule
  with no cap.
- One sweep at most, over an assumed shock value (the outage's hours, a multiplier, the hot lots).
- Hot lots: the n lots in progress at even spacing over the lot list sorted by id get priority 20
  (assumed choice).
- Spare tools: n more tools in the group; existing tools keep their random draws.

## The scorer (`fabsim score SCENARIO [--seeds 0..9] [--threads T]`)

- Each run: 24 hours of warm-up, then a 3-day window (days 1 to 4).
- Seeds 0 to 9 unless given; every arm on the same seeds (paired).
- Today's fab is today's rule under the shocks. Each candidate is scored against it.
- Measures over the window: moves, lots finished, lot-hours waiting, wait per move (minutes),
  queue-time breaches (lots that broke a limit in the window), lots in the fab (mean), and reward:
  lots finished minus 0.01 per lot-hour waiting.
- Intervals: paired t at level 0.05/m for m candidates (Bonferroni), so all m intervals on a
  measure cover at once with probability at least 95%.
- Verdict per measure: better, worse or no clear effect. The best candidate is the one with the
  highest reward lower bound among those better than today; if none is better, today stands.
- With a sweep: every point scored the same way, and `uq::crossover` of each candidate against
  today on reward over the swept value.
- Policies: today's rule (the engine's own), first in first out, shortest processing first,
  critical ratio (due date assumed at release plus 3 times the route's raw processing time;
  smallest (due − now) / work left first) and seeded random.
- Output: JSON with every arm's per-seed values, the intervals, the verdicts, the best candidate
  and the crossover, and "Real-fab effect: cannot say".
