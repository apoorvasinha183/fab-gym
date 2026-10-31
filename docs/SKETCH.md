# Sketch to fab

Written 31 October 2026, before the tests and the code. Step 4 of "Five Meta features for the 2D gym"; the founder: "go with sketch to fab". Cap $1 (by quiz). On a
teaching fab of our own; not a real fab.

## First call (31 Oct, about $0.0001)

Muse Spark 1.3 (contributor) was sent a 480 x 320 pencil-style test drawing (two boxes, one line with two corners) and
asked for each box's pixel box and each line's corners. It answered in 5.3 s, 296 tokens in and 486 out:
`{"boxes": [[62,63,168,147],[313,63,419,147]], "lines": [[[110,147],[110,253],[366,253],[366,147]]]}` against boxes
drawn at (60, 60)–(160, 140) and (300, 60)–(400, 140) and a line through (110, 240) and (350, 240). Spark reads the
drawing; SAM 3.1 had found no "rectangle" in the same picture, so Spark does the reading.

## What changes

1. **From a sketch.** A button in Build: pick a photo of a fab drawn on paper (boxes for machines, with a word in
   each; lines for track, arrows for which way it runs). The page shrinks it to at most 1,024 pixels on its long side
   and sends it to the helper.
2. **Spark reads it.** The helper asks Muse Spark 1.3 (contributor, low effort) for every box (its pixels, the word
   written in it, and which piece it is: one of the eleven machine areas, storage, wafers in or wafers out) and every
   line (its corners in order, following an arrow when one is drawn). Its own $1 meter, under the helper's $5 total; a
   stand-in answers in tests.
3. **Snapped to the grid.** A typical drawn box becomes a machine two tiles wide; each box's centre lands on the
   nearest tiles; each line becomes neighbouring tiles of track, straight between its corners, and stops at a piece.
   A word the helper cannot match to a piece is left out with a note.
4. **Built in Free build.** The page opens Free build on an empty floor sized to the sketch, places each piece and lays
   each track with the editor's own moves, and runs the checks, which say what is missing.
5. **Keep or discard.** A panel says what was read (machines by name, storage, wafers in and out, track pieces) and
   what was left out and why, which model read it and the cost; Discard puts back the layout from before.

## Tests (written before the code)

`agent/tests/test_sketch.py` (Python, no model called):
- **SK1** pieces: kinds read as given; a word that names a machine stands in when the kind is missing ("polish" is
  polishing, "store" is storage, "in" is wafers in); a word that names nothing is left out with a note.
- **SK2** the scale and the snap: two boxes 100 pixels wide become 2-tile machines with their centres on the right
  tiles, and the floor is the drawing's extent plus a margin.
- **SK3** lines: corners become neighbouring tiles, straight between corners; tiles under a piece are dropped, splitting
  the line.
- **SK7** the stretch of a line between a machine and the nearest crossing of other track is a spur, laid there and
  back so cars can leave the way they came (added after the first live sketches; see Changes).
- **SK4** the route: only a PNG or JPEG data URL under 8 MB is taken; a stand-in answers from `sketch.json` and costs
  nothing; live against a fake endpoint, Spark is sent the picture as an image part and its usage counted on the
  sketch's meter; a meter at its $1 cap sends nothing.

`web/tests/sketch.test.mjs` (headless Chrome, a helper with a stand-in):
- **SK5** picking a picture opens Free build on a floor sized to the sketch with the pieces and track read, and a
  panel naming them.
- **SK6** Discard puts back the layout from before.
- **SK8** when the checks refuse the sketched layout, the last run is no longer drawn on it (no cars, no Run again)
  and its numbers read "before your changes" (added after the first live sketch; see Changes).

## Changes

- 31 Oct, while writing the code: a reading still running when Discard is pressed is dropped when it arrives (SK6 had
  raced it); a hidden card had been drawn anyway because `.card` set its own display, which also showed an empty AI
  panel beside the sketch's.
- 31 Oct, the first live sketches (a pencil-style drawing of wafers in, lithography, dry etch, polishing, storage and
  wafers out on one spine; five readings, 13 to 17 s each, $0.0018 in all on the sketch's meter):
  - Spark read 6 boxes and 4 lines every time, but drew the lines differently between readings (once a single line
    from dry etch across the spine to storage). A line ending at a machine was laid one way only, a dead end the checks
    flagged. Any stretch between a machine and the nearest crossing of other track is now laid there and back (SK7's
    three cases, each failing before the fix). The last reading built 6 pieces and 21 track pieces with no dead end.
  - When the checks refused the new layout, the last run's cars and lots went on being drawn over it and its numbers
    read as this layout's. The run is now marked out of date the moment the checks fail (SK8).
  - The checks name the missing machines in their own codes, so the panel adds one plain line naming the machine
    types a wafer's route still visits.
- 31 Oct, results: SK1 to SK8 pass; the page suite (191) and the helper's tests (92) pass, the 500 ms editor timing
  test and the demo path passing alone after a miss each under the full suite's load.
