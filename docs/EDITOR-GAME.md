# The editor as a game: a drawing look, the jam, the first move, the change

Written 31 October 2026, before the tests and the code. From "Where's the Jam?": the map never shows why you are short. The founder chose
fix A, then C, then B, and on the look: "Editor looks boring af how can I make it look drawing friendly. Looks extremely
unapproachable"; then "finish these, go" (the defaults below are chosen without a quiz and reported). On a teaching fab
of our own and the SMT2020 testbed; not a real fab.

## L · A look made for drawing

1. **Paper you can draw on.** The floor shows its tile grid (a fine line per tile, a stronger one every five), so a
   player can see where a piece will land.
2. **The cell under the pointer lights up** in the tool's colour: teal for Track, red for Erase, the area's colour for
   a machine, white for Select.
3. **A hint line over the map** says what the tool in hand does, in one sentence ("Drag across the floor to lay track.
   Cars run the way you drag.").
4. **The palette is a grid of keys**: two columns of square keys, the icon over a short name. A key you cannot use is
   left out, never greyed (see C).

## A · See the jam

5. **Badges only for trouble.** A machine shows a badge when it is broken (red), benched or blocked or flat out with its
   line growing (amber), down on purpose (blue), or busy with a line of four lots or more (amber, the new "line" badge).
   A busy machine with a short line, or an idle one, shows nothing. No number goes on the map: the pile shows it.
6. **The line piles up on the tile**: lots waiting sit in rows of six from the tile's lower edge, up to three rows; a
   red pod marks more than eighteen.
7. **Jammed track gets thick and red**: track a car waits more than a minute on is drawn twice as wide in red, with a
   glow; amber (more than 0.2 minutes) at one and a half times.
8. **J for the jam map** (and a key on the toolbar): the floor dims and only waits show: piles, jammed track, broken
   machines.

## C · Know your first move

9. **The challenge marks its spot**: a pulsing ring on the broken track (challenge 1) or the machine the challenge is
   about (2 to 4).
10. **One line of advice under the map**, from the hour on screen: the broken track's queue, else the longest line and
    where it is, else that the challenge is met.
11. **The palette shows only this challenge's tools**: challenge 1 Select, Track, Erase and the three moving-wafer
    pieces (wafers in, wafers out, storage); challenges 2 to 4 Select (the fix is a + on the machine); Free build
    everything that can still be placed.

## B · See your change work

12. **The result floats up where you changed**: after a rerun, "+12 wafers a day" (or "−5", or "same output") rises
    from the last place edited, as page text over the map (so no text is drawn into the map).
13. **Cleared jams flash teal** for a second and a half: track that was jammed at this hour in the last run and is not
    now.
14. **Hold H to see the last run's jams** over this one (H, for history; Tab stays for moving between controls).

## Tests (written before the code), `web/tests/editorgame.test.mjs`

In Node, on `web/editor-core.js`:
- **G1** `trouble(mood, queue)`: work with 0 or 3 lots none; work with 4 "line"; hurt and physio "broken"; tired
  "gassed"; full "blocked"; hold "held"; pm and setup with no line "planned"; sleep none; a line beats planned.
- **G2** `pile(q)`: 17 lots show 17 pods and no "more"; 30 show 17 and "more".
- **G3** `jamStyle(j)`: 0 calm at width 1; 0.5 amber at 1.5; 2 red at 2.
- **G4** `advise(...)`: a jammed broken track names the break; else the longest line names the machine and the lots;
  a met challenge says so.
- **G5** `floatText(prev, now)`: +12 and −5 with "wafers a day"; equal "same output".
- **G6** every challenge has a spot and a tool list with Select in it.

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **G7** L: picking Track changes the hint line to one about laying track, and the lit cell follows the pointer.
- **G8** L, C: challenge 1's palette holds exactly Select, Track, Erase, wafers in, wafers out and storage; challenge 2's holds Select; Free build's holds
  every machine area that can still be placed, and no key is disabled.
- **G9** A: at the opening hour of challenge 1 no badge is drawn on a machine without trouble, and every badge drawn
  has a kind from G1.
- **G10** A: J turns the jam map on (the toolbar key pressed) and off again.
- **G11** C: challenge 1 marks a spot on the broken track and the advice line is filled.
- **G12** B: after an edit (one more car) a float shows its text over the map within 1.5 s.
- **G13** B: holding H shows the last run's jams (the page says so) and letting go hides them.
- **D3** (docs/EDITOR-TOPDOWN.md) still holds: no text is drawn into the map.

## Changes
