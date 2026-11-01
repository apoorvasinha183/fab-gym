# Build: every machine in reach, every control in view

Written 1 November 2026, before the tests and the code. The founder: "In the editor how would I enter any tool lmao ,
there is no pallete accessible visually , and how would you adjust shit like cap ... How do I even know the knobs I have
access to ?". Ideas page (private). By quiz: all eight ideas; "Tell them what the
process of this fab is, that a real fab has 580 something steps and we wanna keep it simple"; a click places one
machine where it is clicked, and Shift-drag fills; Storage made real. On a teaching fab of our own, built from the
SMT2020 testbed's shapes; not a real fab. Prices are assumed, as in Build.

Found before: the palette lists a machine only when its group is not yet on the floor, and the teaching fab places all
11, so no machine ever shows; every control sits behind a click on the right thing (a machine, a piece of track, or
empty floor for the cars and the cap); challenges 2 to 4 show only Select, with no word on why.

The work comes in five parts, each with its own tests written first:
1. **The palette, the controls panel, the levers, the process** (this part).
2. Placing machines: a click places one where it is clicked, Shift-drag fills a stretch.
3. Storage made real: machines get a few load ports; lots beyond them wait in the nearest storage.
4. The Floor's settings in Build: dispatch rule, demand, urgent lots, rework, quality holds.
5. Gears on the map, find a control, your changes, and glossary links on every control.

## Part 1: what changes

1. **Every machine in the palette.** A Machines section lists all 11 kinds, each with its picture, name, how many are on
   the floor and the assumed price of one. Clicking one selects its group on the map and opens its controls. In a
   challenge, the kinds its levers name are marked as levers. Nothing is locked: Build has never stopped a change to a
   machine outside a challenge's levers (the budget is what limits it), and the palette should not claim otherwise.
2. **One controls panel** in place of the Selected card, with three tabs:
   - **Selected**: the controls of what you clicked, as today;
   - **Whole fab**: cars on the track and the cap on lots inside;
   - **All controls**: one table with a row per machine group (machines, breakdowns, when it breaks) and a row per
     track piece set to break (when it stops), editable in place; a change there is the same change as on the map.
   Every control carries one line on what it does.
3. **Your levers.** Under the challenge's goal, a row of buttons names what the challenge lets you change; each opens
   that control and lights it. Rush hour: the broken track's "When it stops", and the cap. The gassed polisher and Lean
   or redundant: polishing machines, when they break, and the cap. Breakdown, no spare: lithography machines, and when
   they break. Free build has none.
4. **The process.** "About the sim" shows the teaching fab's process: one product, a lot of 25 wafers every 30
   minutes, 18 steps in order with each step's machine and minutes, and the line: a real fab's product takes hundreds
   of steps (583 for one of the SMT2020 testbed's two products); this one is kept small so every step can be seen.

## Part 1: tests (written before the code)

`web/tests/buildcontrols.test.mjs` (headless Chrome and a helper; nothing is spent):
- **BC1** in every challenge and in free build the palette's Machines section has the 11 kinds, each with a picture, its
  name, its count on the floor (the sum of its groups' machines) and its price; in a challenge, exactly the kinds its
  levers name are marked as levers, and none is locked.
- **BC2** clicking an unlocked kind selects its group: the Selected tab opens on it.
- **BC3** the panel has the three tabs; Whole fab holds the cars and the cap; All controls has a row per machine group,
  and one more machine there gives the next fab file one more machine in that group, the same as + in Selected.
- **BC4** each challenge's levers are as listed above; each opens its control and lights it.
- **BC5** every control in the three tabs has a line saying what it does.
- **BC6** "About the sim" lists the 18 steps in order with their machines and minutes, and says 583 steps for a real
  product of the SMT2020 testbed.
- **BC7** at 1,440 x 900, 1,440 x 760 and 1,280 x 720 the page does not scroll (as BR6).
- `web/tests/editorgame.test.mjs` **G8** reads the palette's tools (buttons with `data-t`), since the machines are now
  listed beside them.

## Part 2: placing machines (written 1 November 2026, before its tests and code)

The founder: "By 1 you mean it is placed there ? I would expect something of a "fill" which is what you are saying
require some button like Ctrl or Shift or something pressed". Found before: a group is one block with a count, so a
machine could only be added by + on its group; the fab file and the simulator already give every machine its own stop
on the track, and a group may have several station rectangles, so a group's machines can stand in several places.

1. **Pick up a machine.** Clicking a machine in the palette takes it in hand (and still opens its group's controls, as
   in part 1). V or Esc puts it down.
2. **A click places one machine where it is clicked.** On empty floor, a new block of that kind's group with one
   machine; on a block of the same kind, one more machine in that block. A kind with no group on the floor yet places
   that group, as before.
3. **Shift-drag fills.** Holding Shift and dragging places one machine at each free spot along the drag. The whole fill
   is one step to undo.
4. **One group, several places.** The fab file counts a group's machines across all its blocks; every machine has its
   own stop, numbered once; each block is a station. A group's breakdown settings belong to the group: a new block
   takes its group's, and changing them on one block changes them on all. Spending counts every machine once and a
   group's spares once. "Machines here" and "in the group in all" both show in Selected.

## Part 2: tests (written before the code)

`web/tests/buildplace.test.mjs` (headless Chrome and a helper; nothing is spent):
- **BP1** clicking a machine in the palette takes it in hand and opens its group's controls; Esc puts it down.
- **BP2** a click on a free spot beside the track places a new block with one machine of that group; the group's total
  rises by one, and the fab file has that total, one station per block, and one stop per machine, numbered 0 to the
  total minus one with none repeated.
- **BP3** a click on a block of the same kind adds one machine to that block and makes no new block.
- **BP4** a Shift-drag along free spots beside the track places a machine at each, and one undo takes them all away.
- **BP5** a new block takes its group's breakdown settings; changing them on one block changes them on all; the
  breakdown settings file has one entry for the group; spending counts each machine once and the spares once.
- **BP6** a layout with one group in two places passes the layout checks and runs; the run counts the group's
  machines.

## Part 3: storage made real (written 1 November 2026, before its tests and code)

By quiz: "Free build on; challenges off": Free build uses 2 load ports a machine and real storage by default, with a
setting in Whole fab; the four challenges keep their tuned setup, targets and stars, and if ports are switched on in a
challenge, that run earns no stars. Found before: a Storage block only holds lots for a waiting step (a group with no
machines), the teaching fab has none, so its storage did nothing; machine lines were unlimited; the full fab already
limits output ports (a machine stops while its finished lots fill its ports), Build's small fab does not.

1. **The simulator** reads `inports N` in a fab file: each machine takes at most N lots at its ports, counting lots on
   their way there. A lot whose group's ports are full is carried to the nearest storage instead (by track distance from
   the group's stop); when the group starts work on lots and frees ports, the oldest stored lots are carried up. Time in
   storage counts as waiting for that group; queue-time limits run as before. Without the line, or with no storage on
   the floor, nothing changes, so every earlier result stays as it was. A run reports the moves to and from storage, the
   most lots each group held at its ports, and the most each held in storage.
2. **The layout checks** warn when machines have a port limit but the floor has no storage: the extra lots then wait in
   an unlimited line, as before.
3. **Build** writes `inports 2` for Free build, and Whole fab gains "Load ports per machine" (unlimited, 1, 2, 3 or 4).
   In a challenge the setting starts at unlimited; a run with a limit is marked as an experiment and earns no stars.
4. **Storage says what it does**: "Holds lots whose next machine has its ports full; a car brings them back when a port
   frees", and, with unlimited ports, that nothing waits there.

## Part 3: tests (written before the code)

`crates/fabsim/tests/storage.rs` (the teaching fab's Free build file, `crates/fabsim/tests/data/teach-free.fab.txt`,
written by Build's own `fabText`):
- **ST1** without `inports`, and with a limit far above any line, a run is the same as before, event for event.
- **ST2** with `inports 1` and storage on the floor, no group ever holds more than one lot per machine at or headed to
  its ports, storage is used, and every lot sent to storage was brought back or is still there at the end.
- **ST3** with `inports 1` and no storage on the floor, the run is the same as without the line, and the checks warn.
- **ST4** with storage in use, every lot still follows its route (each step after the last, on the right group), and the
  receipt's finished lots match the run's.

`web/tests/buildstorage.test.mjs` (headless Chrome and a helper; nothing is spent):
- **BS1** Free build's fab file says `inports 2`; no challenge's does.
- **BS2** Whole fab's "Load ports per machine" sets the line; in a challenge a limit marks the run as an experiment and
  no stars are given.
- **BS3** Storage's description says what it does, and says nothing waits there when ports are unlimited.

## Part 4: the Floor's settings in Build (written 1 November 2026, before its tests and code)

The founder: "Part 4 go". Found before: the Floor's Simulation settings change the SMT2020 testbed with dials (the
dispatch rule, breakdowns, repair time, demand, urgent lots, rework, quality holds and a cap). Build's fab file
already has a record for four of them: demand is how often a `release` sends a lot in, urgent lots are a `release`
of a higher priority, rework is a `step`'s chance of sending a lot back, and quality holds are the `defects` record.
Build never wrote any of them. The dispatch rule has no record: it is handed to a run from outside, so a fab file
cannot carry it. Breakdowns and repair are already set per machine group in Build, and the cap and cars in Whole fab.

1. **The simulator reads `dispatch RULE`** (`today`, `fifo`, `spt`, `cr` or `random`, the rules of
   `docs/PROBLEM.md`). A run that is not handed a rule of its own uses the file's; with no line, or `dispatch today`,
   nothing changes, so every earlier result stays as it was. An unknown rule is refused with its line number. A
   receipt names the file's rule as its policy.
2. **The layout checks warn** (`holds_without_rework`) when quality holds are on and no step sends lots back: a hold
   only follows a check that finds a fault, so the setting would do nothing.
3. **Whole fab gains "How the fab runs"**, five rows under the cars, cap and ports, each with a line on what it does:
   - **Dispatch rule**: Today's rule (urgent first, then no re-setup, then oldest), First come, first served, or
     Quickest job first; the last two write `dispatch fifo` or `dispatch spt`.
   - **Demand**: ×0.5, ×0.75, ×1, ×1.25 or ×1.5; every `release` sends lots that much more often (the teaching fab
     sends a lot every 30 minutes at ×1 and every 20 at ×1.5).
   - **Urgent lots**: on the teaching fab, which has none, None, 1 for every 10 lots, or 1 for every 5: a second
     `release` of priority 20 named `Hot`, its gap the regular gap times 10 or 5, its first lot half a regular gap in.
     On the SMT2020 testbed, which has its own urgent lots, None, ×0.5, ×1 or ×2 of them, as the Floor's dial does.
   - **Rework**: on the teaching fab, which has none, None, 1%, 2% or 5%: each check (the five steps on the three
     measuring machines) sends that share of lots back to redo the step before, as the SMT2020 testbed's lithography
     checks do (0.7% to 1.8% of lots, back to the exposure). On the SMT2020 testbed, None, ×1, ×2 or ×4 of its own.
   - **Quality holds**: Off, On or ×2. On writes `defects 120 240 60`: when a check sends a lot back, the measuring
     machine that found it is held for 120 minutes, and the other lots it measured in the 240 minutes before are held
     for 60 (assumed, as on the Floor; `docs/RL-DEFECTS.md`).
   Demand scales the urgent lots too. At their first settings nothing is written, so Free build's fab file is as it was.
4. **Challenges start at today's settings.** Changing any of the five in a challenge makes the run an experiment that
   earns no stars, as a port limit does, and the banner names what changed.

## Part 4: tests (written before the code)

`crates/fabsim/tests/dispatch.rs`:
- **FD1** with no `dispatch` line and with `dispatch today`, a run of the Free build fixture is the same, event for
  event, on two seeds.
- **FD2** with `dispatch fifo`, and with `dispatch spt`, a run is the run `policy::run_with` gives under that rule on
  the file without the line; an unknown rule is refused naming its line; the record survives writing the shop out.
- **FD3** `fabsim receipt` on a file with `dispatch fifo` names `fifo` as the policy and lists the FIFO run's jobs.
- **FD4** the checks warn `holds_without_rework` for quality holds with no step sending lots back, and not once a step
  does.

`web/tests/buildsettings.test.mjs` (in Node on editor-core.js, and headless Chrome with a helper; nothing is spent):
- **BF1** at the first settings, the fab file is the one written before part 4, for Free build and every challenge.
- **BF2** each setting writes its lines on the teaching fab: `dispatch fifo`; demand ×1.5 gives a release every 20
  minutes; 1 urgent lot for every 5 gives a priority 20 release every 100 minutes at ×1.5; rework 5% sends lots back
  from each of the five check steps to the step before with chance 0.05; quality holds On give `defects 120 240 60`
  and ×2 give `defects 240 480 120`.
- **BF3** on a fab that has its own urgent lots and rework (as the SMT2020 testbed does), urgent ×2 halves those
  releases' gaps, None removes them, and rework ×2 doubles each rework chance (at most 1).
- **BF4** Whole fab shows the five rows, each with a line on what it does; choosing an option changes the next fab file.
- **BF5** a fab file with all five set passes the layout checks and runs through the helper; with quality holds On and
  no rework, the checks give the warning.
- **BF6** in a challenge the five start at today's settings; changing one makes the run an experiment with no stars,
  and the banner says so.
- **BF7** at 1,440 x 900, 1,440 x 760 and 1,280 x 720 the page does not scroll with Whole fab open.

## Part 5: gears, find a control, your changes, the glossary (written 1 November 2026, before its tests and code)

The founder: "finish all the Build parts. Go". From the ideas page, ideas 4, 5, 7 and 8. Found before: Build locks no
control (part 1), so the ideas page's grey gears for locked controls become lit gears for a challenge's levers. Cars,
load ports, storage and demand have no glossary entry; every other control has one.

1. **Gears on the map.** Holding G, or pressing the Controls button above the map, puts a small gear with a number on
   every machine block and every piece of track set to break: the number of controls it has (a machine block 3:
   machines, breakdowns, when it breaks; a breaking track piece 3: directions, when it stops, what cars do). In a
   challenge, the gears of the levers' machines and track are lit. Letting go of G, or pressing the button again,
   takes them away. Clicking a gear selects what it sits on.
2. **Find a control.** A box at the top of the controls panel, reached with /, finds a control by its name, its
   machine or a word it uses: "cap" finds Cap on lots inside, "spare" finds When it breaks (a spare is one of its
   choices), "polish" finds the polishing machines' controls, "rule" finds Dispatch rule. Enter, or a click, opens the
   right tab (selecting the machine or the track piece first) and lights the control. No match says so.
3. **Your changes.** Under the tabs, one line: "Your changes" with how many and what they cost; opened, it lists each
   change from the challenge's start (or Free build's): "+1 Polishing (CMP) machine, $5M", "Cap on lots inside: 400
   lots", "Dispatch rule: First come, first served", a breakdown or recovery setting, track pieces added or taken away,
   storage and doors added or taken away, cars, ports and the Floor's settings. Each has an undo that puts that one
   thing back as it started, as one step the undo button can take back. The costs add up to the banner's Extra spend.
   Every control that differs from the start carries a dot.
4. **Every control explains itself.** Beside each control's name, a small "?" opens its glossary entry in a card in
   Build: the picture, the plain line, the figure where the entry has one, and a link to the full entry on the Floor,
   which opens its glossary at that term. Four entries are added, each with every part an entry has and a picture
   reused from the cast: **Car (vehicle)** (`cast/lots/ride.webp`), **Load port** (`cast/cmp/full.webp`), **Storage
   (stocker)** (`cast/lots/bench.webp`) and **Demand (release rate)** (`cast/lots/line.webp`).

## Part 5: tests (written before the code)

`web/tests/buildfind.test.mjs` (headless Chrome and a helper; nothing is spent):
- **BG1** holding G shows a gear with its number on every machine block and every track piece set to break, and
  letting go hides them; the Controls button does the same; in challenge 2 the polishing machines' gears are lit.
- **BG2** a click on a machine's gear selects that machine block and opens Selected.
- **BK1** / puts the cursor in Find a control; "cap" lists Cap on lots inside first, and Enter opens Whole fab with it
  lit; "spare" lists When it breaks for machines; "polish" lists the polishing machines' controls, and choosing one
  selects a polishing block with that control lit; "rule" finds Dispatch rule; a word with no match says so.
- **BY1** at the start Your changes lists none; after one more polishing machine, a cap of 400 and First come, first
  served, it lists those three, the machine with its price, and its cost is the Extra spend.
- **BY2** the changed controls carry a dot, and the others do not.
- **BY3** undoing the cap from the list removes the cap and leaves the other two; undoing the machine puts the group
  back at its starting count; the undo button brings the cap back.
- **BL1** every control in the three tabs has a glossary link naming an entry that exists; clicking one opens the
  card with the entry's picture, its plain line, its figure where it has one, and a link to the Floor.
- **BL2** the Floor opened at `?term=WIP%20cap` opens its glossary at WIP cap.
- **BL3** the four new entries have every part an entry needs and their cast pictures (`web/tests/glossaryplus.test.mjs`
  GP2 and GP6 list them as reused).
- **BL4** at 1,440 x 900, 1,440 x 760 and 1,280 x 720 the page does not scroll with changes listed and a card open.

## Part 6: the machines as map icons, and a hover card that is never cut (written 1 November 2026, before its tests and code)

The founder: "On the machines part of the build editor, instead of the cartoon icons with name, just the icons which are
used on the map, if they hover over it you may show the cartoon fella. Stack them neatly like ms paint icons. Also when
i hover on an icon in the map some of it gets cut from below because it renders inside the nested window, fix that".
Found before: the map's hover card is drawn inside the map's box, which hides whatever runs past its edges; near the
bottom of the map, or on a short map, the card is taller than the room left and its bottom is cut off.

1. **The machines as a grid of map tiles.** Each of the 11 kinds is a square key in the area's colour with its map
   icon engraved, as the map draws it, and a small badge with how many are on the floor; the keys sit in even rows,
   like a paint program's tool box. The name, the count and the price are in the key's label for a screen reader. The
   levers' kinds keep their outline.
2. **The cartoon on hover.** Pointing at a key, or focusing it, shows a card beside the palette: the kind's cartoon,
   its name, how many are on the floor, the price of one and what it does.
3. **The map's hover card is never cut.** It is drawn over the page, placed beside the pointer and kept inside the
   window, flipping to the pointer's other side when the room runs out.

## Part 6: tests (written before the code)

`web/tests/buildcontrols.test.mjs`:
- **BC1** (rewritten) in every challenge and in free build the palette has the 11 kinds in order, each a key with the
  map's icon for its kind (the same drawing), the area's colour, the count on the floor as its badge, and its name in
  its label; the keys are all one size, three or more to a row; the levers' kinds are marked and none is locked.
- **BC8** pointing at a key shows the card with the kind's cartoon, its name, "N on the floor" and its price; leaving
  it hides the card.
- **BC9** pointing at the lowest machine on the map shows the map's card whole: inside the window, and inside every
  box around it that hides overflow.

## Changes
- 1 Nov, before the tests: the ideas page sketched locks on the machines outside a challenge's levers. Build does not
  stop those changes (the budget limits them), so the palette marks the levers' kinds and locks nothing.
- 1 Nov, while writing the code:
  - With 11 machines, the palette was taller than the map and the page scrolled. The palette and the right-hand column
    now scroll inside their own columns, so the map sets the row's height, and each machine is one compact row.
  - The levers row makes the banner taller. At 1,280 x 720 that left the map 320 px, under its 330 px minimum, so it
    fell back to a fixed size and the page scrolled 109 px. The minimum is now 300 px. The map also measures its room
    again once the levers are drawn and once the web fonts are in, since each changes the banner's height by a few
    pixels and the map ignores changes under 8 px.
  - Build's `.insp` style overrode the `hidden` attribute, so the Selected panel stayed visible under the other tabs.
    BC3 read each panel's text without checking it showed; it now checks that only the open tab's panel shows.
- 1 Nov, results: BC1 to BC7 pass, with Build's other tests (review, game, basics, moves, top, room, speed, third
  star, sketch, race, poster, random runs, curves, demo path).
- 1 Nov, part 2, while writing the code: a group's machines were counted from one block, its stops numbered from 0 in
  each block and its spares counted per block; all three now run across the group's places. Taking a machine in hand
  no longer refuses when every group of its kind is placed: it places one more machine of the group. The AI's "set
  machines" move sets the group's total across its places. The hint for a machine in hand dropped "R turns it", which
  does nothing for a square machine. The page gains read-only test hooks (`freeBeside`, `freeRowBeside`, `select`,
  `spend`, `overrides`, `checks`); the row search looks both ways along the track.
- 1 Nov, part 2, results: BP1 to BP6 pass, with Build's other tests, the helper's Build tests and R9.
- 1 Nov, part 3, while writing the code: BS2 read the ports setting's options before opening Whole fab, which draws
  only when opened; the test opens it first. Storage's description now reads "whose next machine's ports are full"
  (BS3 looks for "ports are full", and it reads better). The layout checks became an inner function so the storage
  warning is added to what they find.
- 1 Nov, part 3, results: ST1 to ST4 and BS1 to BS3 pass; the simulator's whole suite passes with its golden runs
  unchanged; Build's other tests and the helper's pass. The referee accepts storage-on runs (one port a machine; 12
  and 2 cars). Measured on Free build's starting fab (two days, run #1; it has no random breakdowns, so every run is
  the same): with 3 or more cars, one, two or three ports a machine leave output at 812.5 wafers a day, since a
  stored lot is carried up while its machine works on the lot ahead; with 2 cars, one or two ports give 800, against
  812.5 unlimited. Storage changes where lots wait and adds car trips; it costs output only when cars are scarce or
  storage is far from its machines.
- 1 Nov, part 4, while writing the code: the file's rule rides on the run as its built-in player, the way a copied run
  carries its rule, so every run of the file uses it (the score, a watched run, the receipt) and a rule handed in still
  wins. The long rule names widened the controls card past its 300 px column; the card may now shrink, and each of
  the five settings puts its menu on its own line under its name. On the teaching fab the three rules give the same
  runs until urgent lots come in (no machine needs a re-setup, and a step takes the same time on every machine of its
  kind), so Whole fab says so under the rule; the demand line now says output can fall past what the fab can carry.
- 1 Nov, part 4, results: FD1 to FD4 and BF1 to BF7 pass; the simulator's whole suite passes with its golden runs
  unchanged; Build's other page tests pass, one file at a time. Measured on Free build's starting fab (two days,
  runs #1 to #3; 812.5 wafers a day and 0.68 days a wafer at today's settings, the same on all three runs):
  - first come, first served and quickest job first: 812.5 and 0.68 on all three runs; with 1 urgent lot for every
    10, today's rule gives 787.5 on run #1 and first come, first served 775;
  - demand ×1.5: 750 wafers a day and 1.59 days a wafer; ×0.75: 737.5 and 0.42 (fewer lots in over two days);
  - 1 urgent lot for every 5: 750 and 1.12;
  - rework 2%: 775 to 800; 5%: 737.5 to 775;
  - rework 5% with quality holds On: 500 to 600 wafers a day and 1.35 to 1.74 days a wafer; ×2: 250 to 387.5. Each
    check is one machine, so a hold stops every lot that needs it.
- 1 Nov, part 5, while writing the code:
  - BL3 first asked every part of a new entry to run past 10 characters, which a topic such as "The fab" does not;
    it now asks for a topic the glossary already uses.
  - Demand's entry reuses the lot holding a ticket (`cast/lots/line.webp`), since the fresh lot is the Lot entry's.
  - A click on a gear selects what it sits on and opens Selected even when another tab is open.
  - The "?" sits beside each control's name; in the five Floor settings it sits above the menu.
  - With a setting changed in a challenge, part 4's experiment line ran to five lines in the banner's narrow column.
    At 1,280 x 720 that left the map under its 300 px minimum, so the page scrolled 141 px (BL4). The line now names
    at most two changes ("and 1 more" for the rest); why the run earns no stars moved to its tooltip.
  - The glossary card closes when the window changes size, so it is never left off the screen.
  - The card's figure drew as black boxes: its colours live in the Floor's stylesheet, so Build now carries the same
    figure rules. The glossary still named the Floor's panel "Try a change" in six places; they now say Simulation
    settings, and WIP cap's entry names Build's Whole fab too.
  - The runs tests (`web/tests/runs.test.mjs`) passed but never ended: their shared helper kept the file alive, so a
    run of the whole page suite waited on it. The helper is now stopped when the file's tests end.
- 1 Nov, part 5, results: BG1 to BL4 pass; every page test file passes, run one at a time (the paused floor coach's
  left out), and the simulator's suite is unchanged by this part. With part 5, every part of Build's redesign is built.
