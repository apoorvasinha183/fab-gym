# The last star's hint

Written 31 October 2026, before the tests and the code. The founder: "Is the gassed polisher even possible to 3 star",
then "yes add the third star hint". On a teaching fab of our own; not a real fab.

## What was found (run #1, the run stars count; three stars at 5% over the target)

| Challenge | Its intended fix | The last stars |
|---|---|---|
| 1 · Rush hour on the spine | 675 wafers a day, one star | a cap of 20 lots inside: 713, three stars (18 or 25: two) |
| 2 · The gassed polisher | a second polisher: 813, two stars (needs 819) | plus a cap of 20: 838, three stars (15: two; 12 or less: none) |
| 3 · Breakdown, no spare | one spare to swap in: 587, three stars | none needed |
| 4 · Lean or redundant? | a third polisher: 663, one star | plus a cap of 18 to 25: 700 to 738, three stars (15 or less: none) |

No challenge's text mentions the cap, so three of the four stop short of three stars for most players.

## What changes

1. A challenge can carry a tip for the last stars. Rush hour, the gassed polisher and Lean or redundant? carry one: try a
   cap on the lots inside (click empty floor, then Cap on lots inside); too low a cap starves the fab.
2. Once a run meets the challenge with one or two stars, the advice line names the stars and gives the tip ("Two stars.
   For the next star, try a cap on the lots inside …"). At three stars it says so and suggests another challenge. A
   challenge with no tip keeps today's line.

## Tests (written before the code)

`web/tests/thirdstar.test.mjs`:
- **TS1** `advise` with the challenge met: one or two stars and a tip give the stars and the tip; three stars give no
  tip; no tip gives today's line.
- **TS2** Rush hour, the gassed polisher and Lean or redundant? carry a tip naming the cap; Breakdown, no spare carries
  none.
- **TS3** in Build (headless Chrome, its own helper) on the gassed polisher: two polishers (two stars) show the tip on
  the advice line; adding a cap of 20 (three stars) takes it away.
- `web/tests/editorgame.test.mjs` **G4** keeps passing: with no stars or tip given, `advise` says what it said.

## Changes
