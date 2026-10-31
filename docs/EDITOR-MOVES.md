# The editor's foreman keys: turn, pick, hotbar, copy and paste

Written 31 October 2026, before the tests and the code. Decided by quiz the same day (`~/HACKATHON-README.md`): after
the basics (`docs/EDITOR-BASICS.md`), "More [factory-builder] moves": R to turn, Q to pick up what is under the pointer, a 1–9
hotbar, box select with copy and paste. From the SMT2020 testbed and a teaching fab of our own; not a real fab.

## What the moves mean here

The editor's pieces are machine groups (2 × 2 tiles), storage (2 × 2), wafers in and wafers out (1 × 2) and track.
A piece serves the track on any side of it (`beside`), so a square piece looks and works the same turned.

1. **R turns.** With wafers in or out in hand, R turns the ghost between 1 × 2 and 2 × 1. With a placed piece selected,
   R turns it where it stands if the turned footprint is free, and says why not otherwise. With a track piece selected,
   R turns its directions (as today). With a square piece, the status line says it looks the same turned.
2. **Q picks.** Over a machine, Q takes that kind of machine in hand (the next unplaced group of it, or says none is
   left); over storage, wafers in or out, the same piece; over track, the Track tool; over empty floor, Q empties the
   hand (Select).
3. **A 1–9 hotbar.** 1 Select, 2 Track, 3 Erase; 4 to 9 the six pieces used most recently, filled at first with
   storage, wafers in, wafers out and the first three kinds of machine. The palette shows each slot's number.
4. **Box select, copy and paste.** In Select, Shift-drag draws a box; the pieces and track wholly inside it are
   selected and outlined. ⌘C or Ctrl+C copies them; ⌘V or Ctrl+V takes the copy in hand as a ghost that follows the
   pointer, teal where it all fits and red otherwise; a click places it; Esc drops it. A copied machine is pasted as
   the next unplaced group of its kind with the same number of machines, or left out with the reason when none is
   left. Delete or Backspace removes the selection. A paste, and a delete of a selection, are one undo step each.

The logic lives in `web/editor-core.js`: `turn`, `pickAt`, `inBox`, `copySel`, `pasteAt` and `hotbar`.
`window.FabEditorPage` gains read-only `tool()`, `selection()`, `hotbar()` and `clipboard()`.

## Tests (written before the code), `web/tests/editormoves.test.mjs`

In Node, on `editor-core.js`:
- **M1** turning: wafers in and out swap 1 × 2 and 2 × 1; square pieces stay as they are.
- **M2** picking: a machine gives its kind, storage and wafers in or out themselves, track the Track tool, empty floor
  Select.
- **M3** a box selects exactly the pieces and track wholly inside it.
- **M4** a copy keeps each piece's place relative to the box's corner; a paste on free floor gives the same layout
  moved, track directions kept; a machine becomes the next unplaced group of its kind or is left out with a reason; a
  paste over anything taken does not fit, with a reason; pasting changes nothing until placed.
- **M5** the hotbar is Select, Track, Erase, then the six most recent pieces, filled at first in a fixed order, with
  no piece twice.

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **P1** with wafers in in hand, R turns the ghost; a selected wafers-in piece turns where it stands.
- **P2** Q over storage takes storage, over track the Track tool, over empty floor Select.
- **P3** keys 1, 2 and 3 take Select, Track and Erase; 4 takes the fourth slot; the palette shows the numbers.
- **P4** Shift-drag selects two storage blocks and a run of track; copy, paste and a click place the same layout
  elsewhere; one undo takes the whole paste back; Delete removes the selection, and one undo puts it back.

## Changes

- 31 Oct, while writing the code: P4 lays its two storage blocks stacked with two pieces of track under them, in a
  2 × 5 patch, because challenge 1's 17 × 13 floor has no free 4 × 3 patch that can be pointed at (its free strip on the
  right lies behind taller machines in the tilted view; the one on the left is two tiles wide); what P4 checks is
  unchanged. `FabEditorPage` also gives the floor's `size()` and its `railKeys()`, read only, to see a floor's free
  space in tests.
- 31 Oct, results: M1 to M5 and P1 to P4 pass (twice in a row), and all 124 page tests. Found on the way: in the tilted
  view, taller machines hide the floor cells behind them, so free floor there cannot be clicked; a flat view (as the
  floor page's T key gives) would fix it.

