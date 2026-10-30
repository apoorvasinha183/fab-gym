# The way in

Written 31 Oct 2026, before the code. A tour of the landing, the floor and the editor in Chrome found the editor and
its challenges reachable only by typing their address, words that describe an ask box, and the editor's map below the
fold on a laptop. Options page (private). Chosen by quiz:

- **Tagline:** "A gym for wafer fabs." Under it: "Build a fab, watch every machine work out, and fix what hurts. Meta's
  models propose changes, the simulator scores them, and a person signs off."
- **Way in (option A):** two doors on the landing, Play a challenge (the editor on Challenge 1) and Ask the fab (the
  question box and its examples); "or explore the floor" stays. One top bar on both pages: Home, Floor, Build, Ask.
  The floor page opens on the floor for `#floor` and with the ask panel for `#ask`. The editor's scores move into the
  challenge band so the running floor shows without scrolling.
- **SMT2020 is a testbed** (the founder: "Technically SMT isnt a fab, it is a bunch of initial conditions"): a
  published set of a fab's tool groups, routes, times and release plans (Kopp, Hassoun, Kalir, Mönch 2020, "SMT2020:
  A Semiconductor Manufacturing Testbed"). The fab is what our simulator builds and runs from it. Pages, README, the
  agent's text and the docs say "the SMT2020 testbed"; never "the SMT2020 model" or "a model of a fab".

## Tests (written before the code)

`web/tests/frontdoor.test.mjs`; the wording asserts in `stages`, `ui`, `results` and `agent/tests/test_loop.py` now look
for the testbed.
