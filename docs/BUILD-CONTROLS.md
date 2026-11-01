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

## Part 7: select and act on a selection (written 1 November 2026, before its tests and code)

The founder: "Allow for advanced controls like drag a free form rectangle to select, delete or something like that ...
Intelligent editing", and by quiz all three layers of the proposal: the selection grammar of design and CAD tools,
acting on a selection, and editing that knows it is a fab (part 8). Found before: Build has box select, copy, paste and
delete since 31 October (`docs/EDITOR-MOVES.md`), but only with Shift held, because a plain drag on empty floor pans
the view; a pasted machine whose kind has no unplaced group is left out, although a group may stand in several places
since part 2.

**Selecting**
1. **A plain drag on empty floor draws a box** (Select). Dragging right selects what lies wholly inside the box (a
   solid outline); dragging left selects whatever the box touches (a dashed outline), as CAD programs do. The view
   moves with Space-drag, the middle or right button, the W A S D keys, or the arrows when nothing is selected.
2. **Adding and taking away.** Shift-click adds a piece or takes it away again; Shift-drag adds a box; Alt-drag takes a
   box away. ⌘A (Ctrl+A) selects everything; Esc clears.
3. **Double-click** a machine to select every block of its group, wherever they stand; double-click track to select
   all the track joined to it.

**Acting on a selection**
4. **Move.** Dragging a selected piece moves the whole selection; the arrows nudge it one tile. A move that does not
   fit says why and changes nothing. Each move is one undo step.
5. **Duplicate.** ⌘D (Ctrl+D) takes a copy in hand, as ⌘C then ⌘V does. A pasted machine takes an unplaced group of
   its kind if one is left, and otherwise becomes more machines of its own group in a new place (it was left out).
6. **Turn and mirror.** R turns the selection a quarter clockwise in its box, Shift-R mirrors it left to right; track
   directions turn with it. A turn that does not fit says why and changes nothing.
7. **Edit them all.** With pieces selected, Selected shows what is in the selection and controls that apply to all of
   it: the machine groups' breakdowns and what happens when they break, the track's breakdowns; and buttons to delete
   all of it, only the track, only the machines, or only storage and doors. Delete or Backspace deletes all of it.

The logic is in `web/editor-core.js`: `inBox` (with crossing), `connectedRail`, `moveSel`, `turnSel`, `deleteSel`,
and `pasteAt`; each returns a new floor and leaves the old one as it was.

## Part 7: tests (written before the code)

`web/tests/editorselect.test.mjs`, in Node on `editor-core.js`:
- **SE1** a box selects what is wholly inside it, or, crossing, whatever it touches.
- **SE2** the track joined to a piece, in either direction of travel, and nothing else.
- **SE3** a move shifts pieces and track, directions kept; a move onto something not selected, or off the floor, does
  not fit and says why; the old floor is unchanged.
- **SE4** a quarter turn moves and turns pieces in the selection's box and turns track directions; four turns, or two
  mirrors, give the selection back; a turn that does not fit says why.
- **SE5** deleting all, only track, only machines, or only storage and doors.
- **SE6** a pasted machine with no unplaced group of its kind becomes more machines of its own group.

In headless Chrome with a helper:
- **SB1** a drag on empty floor selects: to the right what is wholly inside, to the left whatever is touched, which is
  more; Space-drag moves the view.
- **SB2** Shift-click adds and takes away; Alt-drag takes a box away; ⌘A selects everything; Esc clears.
- **SB3** double-clicking a machine selects every block of its group; double-clicking track selects the track joined
  to it.
- **SB4** the arrows nudge the selection, one undo step; dragging a selected piece moves the selection; ⌘D takes a copy
  in hand.
- **SB5** R turns the selection and Shift-R mirrors it, as `turnSel` says, or says why not and changes nothing.
- **SB6** with everything selected, Selected sets every machine group's breakdowns at once, and "only the track"
  deletes the track and nothing else.
- `web/tests/editorbasics.test.mjs` **B2** moves the view with Space-drag, and `web/tests/editormoves.test.mjs` **M4**
  pastes a machine with no unplaced group as more machines of its own group.

## Part 8: editing that knows it is a fab (written 1 November 2026, before its tests and code)

The third layer the founder chose. Found before: track is laid tile by tile by dragging; erasing a piece in a run
leaves the run cut; a machine dropped one tile away from the track has no stop and the checks refuse the layout; the
checks name what is wrong but offer no fix; a machine group's breakdown settings are set one group at a time; a
selection can be copied but not kept.

1. **Route.** A Route tool (T) lays track by itself: click where it starts (a track piece or empty floor), point where
   it should go, and the shortest way over free floor shows as a ghost; a click lays it, running from the start to the
   end, joined to the track at both ends. Where no way is free, it says so. One undo step. (Added 1 Nov at the
   founder's word, "make route grow the floor too": the way may run up to 4 tiles past the floor's edges, and may
   start or end there; the floor grows to take it, as it does for Track, everything moving over when it grows left
   or up, up to the floor's limit of 120 tiles a side.)
2. **Reconnect a cut.** Erasing track that a run passed through (with Erase, or deleting a selection) shows a button,
   "Reconnect the track around the cut": the pieces that led into the cut are routed around it to the pieces it led
   to, avoiding the cut tiles. It is offered and never done by itself, since a cut may be meant.
3. **Snap beside the track.** A machine, storage or door pointed at free floor that does not touch the track snaps to
   the nearest free spot within 3 tiles that does; the ghost shows where it will go. Alt places it exactly where
   pointed.
4. **One-click fixes from the checks.** A check that has a fix carries a Fix button:
   - a machine with no track beside it ("missing stops"): moved to the nearest free spot beside the track;
   - a stop the entry cannot reach ("unreachable"): routed from the nearest track the entry reaches;
   - a stop or track with no way to an exit ("no way out", "trap"): routed from its dead end to the nearest track
     that reaches an exit;
   - ports with no storage: storage placed at the nearest free spot beside the track to the middle of the floor;
   - quality holds with no rework: rework set (1% at each check on the teaching fab, the fab's own elsewhere).
   Each fix is one undo step, and the checks run again after it.
5. **The same for every one of a kind.** A machine group's controls in Selected gain "Same for every machine group",
   and, where a kind has more than one group (the SMT2020 testbed), "Same for every <kind> group": both copy this
   group's breakdowns and what happens when it breaks.
6. **Blueprints.** A selection can be saved as a named blueprint ("Save as a blueprint" in its panel). Blueprints are
   listed in the palette with a small drawing of their pieces; a click takes one in hand, a click on the floor places
   it, as a paste does. They are kept in this browser. A blueprint's machine whose group is not in this fab takes an
   unplaced group of its kind, or is left out with the reason.

The logic is in `web/editor-core.js`: `route`, `cutGaps`, `heal`, `snapBeside`, `reach`, `sameForKind`, and `pasteAt`
with the groups this fab knows.

## Part 8: tests (written before the code)

`web/tests/editorsmart.test.mjs`, in Node on `editor-core.js`:
- **SM1** a route takes the shortest way over free floor, around pieces and track, one way from start to end, and
  joins a start piece by giving it the way out; where nothing is free it says why; the old floor is unchanged.
- **SM2** a cut's gaps are the pieces that led into it and the pieces it led to; healing routes the first to the
  second around the cut tiles.
- **SM3** a free spot not beside the track snaps to the nearest free spot beside it within 3 tiles; a spot already
  beside it stays; with none near, nothing.
- **SM4** what the entry reaches and what reaches an exit, following the track's directions.
- **SM5** the same for every machine group, or every group of one kind, copies breakdowns and recovery.
- **SM6** a pasted machine whose group this fab does not know takes an unplaced group of its kind, or is left out with
  the reason.

In headless Chrome with a helper:
- **SR1** the Route tool lays the track `route` gives between two clicks; one undo takes it all away.
- **SR2** erasing a piece in the middle of a run offers the reconnect button, and it reconnects as `heal` says.
- **SR3** storage pointed one tile off the track is placed beside it; with Alt, where pointed.
- **SR4** a machine moved off the track gets a Fix that puts it beside the track and clears the check; quality holds
  with no rework get a Fix that sets rework and clears the warning.
- **SR5** "Same for every machine group" gives every group the selected group's breakdowns.
- **SR6** a selection saved as a blueprint shows in the palette, is kept after a reload, and a click on it then on the
  floor places its pieces.
- **SM7** (added with the growing floor) where the way inside is blocked, a route runs past the floor's edge and the
  floor grows to take it; a route starting left of the floor moves everything over; past the limit it says so.
- **SR7** on Free build, whose layout fills its floor's width, a route from past the left edge to the track grows the
  floor and lays the track `route` gives; one undo puts the floor and the track back.

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
- 1 Nov, part 6, while writing the code: the key's card first sat beside the key and covered the palette's other keys;
  it now sits beside the whole palette. Its badge showed "N on the floor" in capitals, as the map's card styles that
  badge; the palette's card keeps the words as written. The map's card is moved out of the map's box onto the page
  (fixed to the window), so no box around the map can cut it.
- 1 Nov, part 6, results: BC1, BC8 and BC9 pass, with the rest of the palette and hover tests (controls, placing, game,
  top-down, find, room). Before the change, BC9 failed at 1,280 x 720 with the map's box cutting the card, as the
  founder saw.
- 1 Nov, part 7, while writing the code:
  - SB1 first put the box's edge on a row where no machine straddled it, so both directions selected the same; its
    edge now runs through a machine's second row. SB4 first nudged a storage block boxed in by track and machines;
    it now moves the whole layout, which has floor around it.
  - A click on one piece clears a box selection; a pasted machine of a group already on the floor takes the group's
    breakdown settings; the right button pans, so the map has no right-click menu.
- 1 Nov, part 7, results: SE1 to SE6 and SB1 to SB6 pass, with B2 and M4 as changed and every other Build page test.
- 1 Nov, part 8, while writing the code:
  - Route sits in the palette beside Track and comes wherever Track does, so `web/tests/editorgame.test.mjs` G8 lists it
    in challenge 1's tools. `web/tests/editormoves.test.mjs` P1 places wafers in on free floor off the track, which now
    snaps beside it; it holds Alt to place them where pointed, as the spec says.
  - Recording a film of the editing showed the checks once refusing the layout as "not a fabgym-shop 1 file": the
    helper names a layout's file by its contents, and a run and a check of the same layout wrote the same file at
    once, so one could read half of it. The helper now writes the file whole under another name and renames it into
    place.
  - Route first laid track only inside the floor: on Free build's starting fab, which fills its floor's width, it could
    run along the free rows only. At the founder's word ("make route grow the floor too") it now runs up to 4 tiles
    past the edges and the floor grows to take it (SM7, SR7); reconnecting a cut stays on the floor.
  - Running part 8's tests once hung for ten minutes: the page tests' helper took a port from 8800 to 9399 and their
    headless Chrome one from 9300 to 9699, and both drew 9349. The helpers now take 8800 to 9199 in every page test.
- 1 Nov, part 8, results: SM1 to SM7 and SR1 to SR7 pass, with every other Build page test (G8 and P1 as changed) and
  the helper's Build tests.
