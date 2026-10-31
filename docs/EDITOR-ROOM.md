# Room to draw, and a reward you can see

Written 31 October 2026, before the tests and the code. The founder: "I think you need to allow more room to draw bro. It
should infinite. Also the reward is not apparent." Then, after the Evidence rewrite: "then do the room and stars". On a
teaching fab of our own and the SMT2020 testbed; not a real fab.

## Room to draw

The simulator never reads the floor's size; only the editor did, as a hard edge. Now:

1. **Paper all round.** Grid paper fills the whole map, and the view opens with a tile and a half of empty paper on every side
   of the floor, so there is visibly room to draw. The floor in use is drawn a shade lighter, with a faint dashed edge.
2. **The floor grows as you draw.** Laying track or placing a piece past the edge grows the floor to take it, on any side
   (past the left or top edge, everything moves over by the same amount). The view holds still while it grows, so what
   you are drawing stays under the pointer. F fits the grown floor.
3. **A limit far away.** The floor stops at 120 by 120 tiles (360 m a side); past it the status line says "That is as
   far as the floor goes." The map keeps at least 430 px of height so the floor stays readable in short windows.

## A reward you can see

4. **Stars.** A challenge met earns a star; beating its target by 2% earns two; by 5%, three. The challenge's own limits
   (such as its budget) still have to hold for any star.
5. **The moment.** The run that first meets a challenge, or beats your best stars, brings up a card over the map:
   "Challenge met!" (or "New best!"), the stars, the wafers a day against the target, what the next star needs, a "Next
   challenge" button and "Keep improving". Confetti falls for a moment, unless the viewer prefers reduced motion.
6. **Stars stay.** Each challenge's tab shows its best stars (★★☆), kept in the browser, and the goal bar marks where
   each star starts.

## Tests (written before the code), `web/tests/editorroom.test.mjs`

In Node, on `web/editor-core.js`:
- **R1** `stars(score, target, extra)`: below the target 0; at it 1; 2% over 2; 5% over 3; over budget 0.
- **R2** `isFree(..., grow)`: with growing allowed, a spot past any edge is free (still refused when something is in the
  way, and past 120 tiles); without it, "Off the edge of the floor." as before.
- **R3** `grow(state, x, y, w, h)`: past the right edge the floor widens and nothing moves; past the left edge everything
  moves right by the same amount (pieces and track) and the floor widens by it; past 120 tiles nothing changes.

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **R4** the opening view shows paper round the floor: at least one tile between the floor and each edge of the map.
- **R5** dragging track two tiles past the right edge grows the floor by two, lays the track, and leaves a machine where
  it was on screen (within 1 px).
- **R6** dragging track one tile past the left edge grows the floor by one, moves every piece right by one, and leaves
  the machine where it was on screen.
- **R7** "Stuck? Show me a fix" meets challenge 1: the card shows with at least one star lit and a "Next challenge"
  button, and the tab shows its stars.
- **R8** the goal bar marks the three stars.
- **D7, D8** (docs/EDITOR-TOPDOWN.md) still hold: the map fits a 1440 x 900 window, and keeps a usable size in a short
  one.

## Changes

- 31 Oct, while writing the code: two tiles of paper and a 460 px floor for the map pushed it 11 px past a 1440 x 900
  window (D7) now that the advice line sits above the map; the paper is a tile and a half and the floor 430 px, which
  keeps D8's 300 px for the floor itself. R5 failed once under load with a machine 1.1 px off: the advice line wrapped to
  two lines and moved the map; it is now one line high, cut with an ellipsis when long.
- 31 Oct, results: R1 to R8 pass and all 182 page tests.
