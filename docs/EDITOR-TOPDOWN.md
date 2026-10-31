# The editor, top down

Written 31 October 2026, before the tests and the code. The founder the same day: "go completely top down instead of
2.5D", "the buttons are not properly engraved", "Factorio tiles but let us not write the text on top of it, it is
distracting"; from the options page (private), tiles B (icons
engraved into the tiles) and buttons B (raised keys). From the SMT2020 testbed and a teaching fab of our own; not a
real fab.

## What changes

1. **Straight down.** The map is drawn from above: tiles are squares on a visible grid, x across and y down. Nothing
   stands up, so nothing hides the floor behind it (in the tilted view, free floor behind tall machines could not be
   clicked).
2. **Factorio tiles.** A machine group is a flat tile in its area's colour with a darker rim and a lit top edge;
   storage, wafers in and wafers out are tiles of their own colours. Vehicles are flat tokens on the track.
3. **Engraved icons.** Each tile's icon is cut into it: drawn in a dark shade of the tile's colour, with a light line
   along its lower edge (`FabEditor.engrave(colour)` gives the two).
4. **No text on the map.** No name pills, no "×3", no "+N". A group's name, machines and line show in the hover card
   when it is pointed at. Lots waiting show as up to eight pods inside the tile's lower edge, a ninth in amber when
   there are more.
5. **Raised keys.** The toolbar's and the palette's buttons are keycaps: raised with a shadow under them, pressed down
   (sunk, inset shadow, lit) while held or while chosen.

Everything else (picking, the ghost, the box, paste, zoom and pan, the checks, the run) works as before.

## Tests (written before the code), `web/tests/editortop.test.mjs`

In Node:
- **D1** `engrave(colour)` gives a cut darker than the colour and a light line that is a see-through white.

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **D2** the map is straight down: one tile to the right moves the screen point only across, one tile down only down,
  by the same distance.
- **D3** no text is drawn on the map while it plays, other than the one-line notice of a rerun.
- **D4** in challenge 1, a free 3 × 4 patch can now be pointed at (in the tilted view there was none).
- **D5** pointing at a machine tile shows its hover card with its name.
- **D6** the palette's buttons are raised (a shadow under them, none inset) and the chosen one is pressed (an inset
  shadow); the toolbar's play button is raised too.

## Changes

(none yet)
