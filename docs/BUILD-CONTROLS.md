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
