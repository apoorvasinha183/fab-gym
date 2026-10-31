# Home after review

Written 31 October 2026, before the tests and the code. Argon reviewed Home; plan page ("Home Plan", private); the third door's name and its mascot from a private design page. By quiz: suggestions fill the box and run only on Go; all four
challenge tiles; the door "Watch the whole fab at work"; the robot CEO in the navy coat (founder: "The coat CEO"), made
with Muse Image from the gym's hero picture and two cast tiles ($0.01 a picture, on the poster's meter). On a teaching
fab of our own and the SMT2020 testbed; not a real fab.

## What changes

1. **An ask box you can read.** The placeholder is "Ask a what-if about the full fab…". Picking a suggestion puts its
   words in the box and nothing more; Go (or Enter) asks.
2. **Pictures that are the challenges.** The play door shows all four challenges, each with its name and a cast
   picture of its trouble (a full lithography bay, a gassed polisher, a broken-down lithography tool, a polisher on
   hold), each opening Build on that challenge (`editor.html?ch=N`, N from 1 to 4; Build learns to read it).
3. **A main button that looks like one.** "Start challenge 1 →" is a solid button, and a line says what is inside: "4
   challenges · a free build · up to 3 stars each".
4. **A door to the live fab.** A third door, as wide as the other two together: the robot CEO, "Watch the whole fab at
   work", "1,043 machines from the SMT2020 testbed, running live in your browser. A new random run each visit." and a
   "Watch it live →" button to the Floor.
5. **What Meta's models do.** The line under the headline names them by job: "Muse Spark sets up the what-ifs you ask,
   Muse Wonder plays the challenges against you, the simulator scores every change, and a person signs off." The ask
   door says Muse Spark sets up the experiment.

## Tests (written before the code)

`web/tests/home.test.mjs` (headless Chrome, a helper with no key; nothing is spent):
- **HO1** the ask box's placeholder is the short one and repeats no suggestion; picking a suggestion fills the box,
  starts no question (no request to `/api/ask` or `/api/run`) and leaves Home open.
- **HO2** the play door has four tiles named as the four challenges, each with a picture; each links to
  `editor.html?ch=N`; Build opened at `?ch=3` is on challenge 3.
- **HO3** the play door's only solid button is Start, it opens challenge 1, and the line about what is inside is there.
- **HO4** the third door shows the CEO's picture, the name "Watch the whole fab at work" and a button that opens the
  Floor; at 1440 x 1000 the three doors do not overlap and all show without scrolling Home.
- **HO5** the line under the headline names Muse Spark and Muse Wonder and what each does.
- `web/tests/sitecuts.test.mjs` **K3** (two doors) changes with item 4: the two doors stay, and a third is added.
- `web/tests/frontdoor.test.mjs`: the landing's chosen words change with item 5, and Play a challenge is checked by its
  Start button to `editor.html?ch=1`.

## Changes

- 31 Oct, results: HO1 to HO5 pass, and the page suite (216 tests, the paused floor coach's three left out) passes run one
  file at a time once the two landing tests followed items 2 and 5. The CEO on the door is a 384 px copy
  (`web/cast/ceo.webp`, 21 KB) of `~/fab-gym-paper/mascot/flex-robot-suit.webp`.
