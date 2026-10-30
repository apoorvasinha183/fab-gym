# Two wafer families in one fab

Written 28 October 2026, before the code. From the SMT2020 testbed, with a gigafab-style layout of our own design; not a
real fab. Agents propose, the simulator scores, a person signs.

## The question

A fab runs family A, SMT2020's volume products, and takes in family B, a stream of small, urgent prototype lots.
Which operating policy, and which 2D layout strategy, makes the most money a day, and at what share of family B does
the answer change?

Decided by quiz on 28 October (`~/HACKATHON-README.md`):

- **Family B** is SMT2020's engineering lots, rebuilt from their published facts on product 3's route (the
  MIT-licensed `data/smt2020/hvlm/route_3.txt`). The official engineering-lot files state no licence and stay out of
  the repository; only facts read from them are used: 1 to 10 wafers a lot (5.5 on average), 20 lots a release,
  releases on alternating gaps of 2 and 5 days from day 0 at 08:00, one lot in five at priority 20 and the rest at
  10. Their route copies product 3's steps (the official file differs only in setup columns, not reproduced here).
- **The engine is extended behind switches.** With none of the new records in a shop, every run is byte for byte
  what it is today, and the exact match with the reference engine keeps passing.
- **Layout strategies:** share (D1), a wing on pad P3 (D2), copies near family B (D3).
- **Policy levers:** priority between families; a WIP cap and release rate per family; capacity reserved for family
  B; which tools are qualified for family B.

## The shop, extended (`fabgym-shop 1`, new records)

| Record | Fields | Meaning |
|---|---|---|
| `family` | route, name | lots on that route belong to that family; routes not named belong to family "" |
| `famcap` | name, lots | at most that many lots of the family in the fab; releases and timed arrivals of the family wait, oldest first |
| `qual` | group, family, tools | only the group's first that-many tools may process the family's lots |
| `reserve` | group, family, tools | the group's first that-many tools take the family's waiting lots first, and others only when none of the family waits |

`reserve` needs `qual` to cover at least as many tools when both are given. Lots listed one by one with a start
time after 0 and at step 0 count as arrivals of their family for `famcap`.

## The engine, extended

- Each lot carries its family; each candidate in a decision carries `family` (so rules, including those Meta's
  model writes, can read it). The candidate's field set grows by one; the no-leakage test changes with it.
- A free tool considers only lots whose family it is qualified for; a reserved tool takes the reserved family's
  waiting lots before any other, keeping today's order (priority, setup, oldest) within each.
- Family caps hold releases and timed arrivals per family; a lot leaving the fab frees one place in its family.

## Family B and the layout strategies (`fabsim::twofam`)

- `engineering_lots(cfg)` lists family B's lots for a horizon, deterministic by seed; a scale multiplies the lots per
  release, giving the share of family B.
- `copy_groups(shop, groups, family)` adds a copy of each named group (`G@B`, with its own tool count, the same
  times, maintenance and breakdowns), and points the family's steps at the copy. Family A never uses a copy.
- `contested(shop, family, n)` ranks the groups family B visits by the load both families put on them.
- Strategies, each packed on the 2D campus with transport by distance (`docs/FAB-LAYOUT.md`):
  - **D1, share:** no copies.
  - **D2, wing:** copies of the groups family B loads most, in a third phase on pad P3, reached over the bridge.
  - **D3, copies:** copies of the most contested groups, placed in the halls by family B's flow.

## Money (`fabsim::money`)

Money a day over a window = family A's wafers out × margin per wafer + Σ over family B's lots out of size × price
at its cycle time − tools added × cost per tool per day − hall metres added × cost per metre per day. Family B's
price per wafer falls linearly after a free period: `price0 × max(0, 1 − decay × (days − free_days)⁺)`, its cycle
time counted from the scheduled arrival (so holding counts). Every price is assumed, tagged and swept.

## Tests (`crates/fabsim/tests/two_families.rs`)

1. **Switches off:** a shop with families named but no caps, qualifications or reservations runs to the same log as
   without them; the new records round-trip through the text form.
2. **Family cap:** family B never has more lots in the fab than its cap; family A's releases are not delayed by it.
3. **Qualification:** a tool not qualified for family B never starts a family-B lot.
4. **Reservation:** a reserved tool never starts another family's lot while a lot of its reserved family waits in
   the group.
5. **Rules see the family:** candidates carry the family; preferring family B lowers family B's mean cycle time
   against preferring family A, on the same seed.
6. **Engineering lots:** 20 lots per release on alternating 2- and 5-day gaps from 08:00 on day 0; sizes 1 to 10;
   exactly one in five at priority 20; the same lots for the same seed; the route copies product 3's steps.
7. **Copies:** the copy exists with its tool count; family B's steps use it and family A's never do, in a run.
8. **Strategies from the SMT2020 testbed:** D1 adds no group; D2 puts every copy in a third phase and D3 in the first
   two; every group has a place; a day runs.
9. **Money:** a hand-worked case gives the exact figure; the same run gives the same money twice.

## Changes

- 28 Oct, test 5: in the toy shop the arrivals are evenly spaced and the families never waited together (0 of 800
  decisions offered both), so preferring either family changed nothing. The test now starts eight lots of each family
  at time 0 and also asserts that more than five decisions offer both families. The engine was not changed for it.
- 28 Oct, strategies: D2 and D3 copy the same groups (the most contested ones family B visits), so the two differ
  only in where the copies stand. "Metres added" is the wall length the copies' tools take (by tool kind), plus one
  OHT bridge for the wing.
- 28 Oct, before any sweep run: `contested` estimated a batch step's load as if batch sizes were in lots (they are
  in wafers) and left out load and unload minutes and cascade intervals, so wet benches ranked first. It now uses the
  engine's own job times (first piece plus the cascade interval per further piece, load and unload on every job,
  a lot's wafer share of a mean batch). From the SMT2020 testbed the top groups are then thin film, polishing
  (Planar_FE_79 and 77) and lithography metrology. The estimates exceed 1 for several groups, as SMT2020's
  release rate runs above capacity without a cap (`docs/LEAN-LONG.md`); only the order is used.
