# The floor's health panel and legend

Written 31 October 2026, before the tests and the code. The founder, with two screenshots (`~/bug1.png`, the legend;
`~/bug2.png`, the counters reading 157 lots finished and 0 waiting): "fix the legend and have them a proper layout. Also
the gym language won't work there. Use the factual description. The status bar also should show the current health of
the fab, as in how many lots done, how many tools broken, how many tools active etc. etc. Think you were a fab inspector
what would you require? As I said the frontend does not spark Joy". On the SMT2020 testbed; not a real fab.

## What was wrong

1. **The legend** packed the tool lights, the group badges, the lot marks, two notes and the event log into one card, in
   rows that wrap mid-list, with most of it behind "More about the marks". The badges were named in gym words ("in the
   zone", "gassed", "at the physio", "benched") that say nothing about what the tool is doing.
2. **The counters** showed two numbers. At the end of the run (day 4 00:00) lots waiting read 0: the run's last events
   start every lot still waiting at the closing time, so the queues read empty at that instant (seen live: 1,005 waiting
   on day 3 10:55, 0 at day 4 00:00).

## What changes

1. **A health panel** on the right, "The fab now", read from the run on screen at the current fab time:
   - **Output.** Lots finished so far and their wafers; lots finished in the last 24 hours (since the start, before the
     first day is over); the mean wait for a tool per step so far (see Changes).
   - **Lots in the fab** (released and not finished), split into waiting for a tool, being processed, moving between
     tools and resting in storage between steps. The parts add up to the whole.
   - **Tools** (1,043): working, idle, changing setup, in maintenance and broken down, each a count and a share of one
     bar; availability (tools not broken down or in maintenance, as a share of all tools) and the share of available
     tools working.
   - **Longest queue:** the tool group with the most lots waiting, by its plain name, and how many.
   - **Latest events:** the last three breakdowns and repairs (the log that sat in the legend).
2. **The legend**, on the left, "What the marks mean", in three headed sections laid out in aligned columns:
   - **Tool light** (each tool's state): working, idle, changing setup, maintenance, broken down; and that a block's
     colour is its area.
   - **Group badge** (the most common state among a group's tools, a tie to the more serious), each a factual name and
     the rule behind it, taken from the simulator's rules (`crates/fabsim/src/moods.rs`, defaults): Running; Under 30%
     busy (busy under 30% of the last 8 hours, nothing waiting); Over 90% busy, queue growing (busy over 90% of the last 8
     hours and more lots waiting than 8 hours before); Output full (finished lots fill every output port, none picked
     up); Filling a batch (a batch tool standing by while lots gather); Changing setup; Planned maintenance; Just broke
     down (down under 15 minutes); Under repair (down 15 minutes or more); On hold (taken out of service).
   - **Lots:** a lot (25 wafers), an urgent lot, a prototype lot; +N for lots beyond those drawn; storage for lots resting
     between steps.
   No gym words on the Floor's legend, health panel or hover card (the hover card names the badge the same way and
   describes the area without its exercise). Build keeps its game words.
3. **The end of the run** reads the fab as it stood just before closing, so lots waiting never drops to 0 at the end.
4. **Room for both:** the map fits between the two panels; Try a change and Words move to the bottom right, beside the
   play bar.

## Tests (written before the code)

`web/tests/floorhealth.test.mjs` (headless Chrome, the Floor served by its own helper; nothing is spent):
- **FH1** the health panel shows lots finished, lots in the fab, waiting, being processed, moving, resting, the five
  tool counts, availability, busy share, the mean wait per step and the longest queue; its numbers equal the page's own reading
  (`FabFloorPage.health()`); the tool counts add up to 1,043 and the lot parts add up to lots in the fab.
- **FH2** the numbers follow the clock: moved to day 2 and day 3, lots finished never falls and the panel changes.
- **FH3** at the very end of the run lots waiting is not 0 and equals the reading a minute before the end.
- **FH4** the legend has the three sections, the ten badges by their factual names with their rules, and no gym word
  anywhere on the Floor's legend, panel or hover card.
- **FH5** layout at 1440 x 1000 and 1280 x 800: no legend label wraps onto a second line, the legend, the health panel,
  the ask bar, the rail and the play bar do not overlap one another, and both panels fit in the window.
- `web/tests/sitecuts.test.mjs` **K4** changes with this: the key's three marks behind a closed disclosure and the two
  numbers give way to the sections above and the health panel.

## Changes
