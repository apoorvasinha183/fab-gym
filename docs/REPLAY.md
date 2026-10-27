# Replay: a rule against today's rule, side by side

Written 27 Oct 2026, before the code (tests in `viz/tests/test_replay.py`).
Everything here runs on the SMT2020 model of a fab, on a gigafab-style layout of our own design. Not a real
fab. Agents propose, the simulator scores, a person signs.

## What it shows

Two copies of the same campus play the same simulated hours on the same seed, one under today's rule and
one under a written rule, on one clock and one camera. A panel under each side counts, from the start of
the window, the moves made and the lot-hours spent waiting, and the queue at one watched tool group.
The rule is named on screen. Until a model has written one, the rule is hand-written and the screen says
so.

## Pieces

1. `fabrule trace RULE.rs [--real] [--data D] [--plan P] [--seed S] [--day N] [--hours H] --out FILE`
   runs the campus's shop (`D/P.shop.txt`) with the rule in the sandbox (docs/AGENT.md) and writes the
   same trace as `fabsim layout-trace`, with the same defaults. Under today's rule the two files are
   identical byte for byte.
2. `viz/replay.py RULE.rs --name NAME [--hand-written] [--card CARD.json] [--seed S] [--day N] [--hours H]`
   writes `data/layout-real/replay/`: `scene-today.json` and `scene-rule.json` (the scene builder of
   `viz/look/scene.py`, one per trace) and `replay.json`:
   - `what`, the seed and the window (`from`, `to`, fab minutes);
   - `rule`: name, source, its sha256, whether it is hand-written, and the card's held-out reward line
     when a card is given (else null);
   - `watch`: the tool group whose mean queue differs most between the two sides over the window, with
     its name, area and the plan position the camera looks at;
   - `series`: every 10 fab minutes, for each side, moves so far, lot-hours waited so far and the watched
     group's queue, all counted from the window's start. They are counted from the traces alone:
     a move is a step that ends in the window; waiting is the part of each step's arrive-to-start
     inside the window; the queue is the lots of the watched group arrived and not started.
   `--copy` also writes the three files into `viz/godot-real/data/replay/`.
3. Godot: `viz/godot-real/compare.tscn`, a scene built in the editor's terms: two `SubViewportContainer`s,
   each holding a `SubViewport` with its own world and an instance of `main.tscn` whose `scene_path`
   points at its side's scene, and a panel under each. `main.gd` gains `scene_path` (default the
   explore scene's) and `embedded` (no HUD, no input and no clock of its own). `compare.gd` keeps one
   clock and one camera pose for both sides and fills the panels from `series`.
   Keys: Space pause, +/- speed, arrows orbit, PageUp/PageDown height, W the watched group, 1 the
   campus, R restart.
   A headless check: `godot --headless --path viz/godot-real res://compare.tscn -- --compare-check OUT`.

## Checks

- Both sides draw all 1,043 tools from the same layout; their clocks and camera poses are equal after
  any number of frames.
- The panels show the series' numbers for the current time.
- The screen says "on the SMT2020 model", "not a real fab", names "Today's rule" and the rule, and says
  "hand-written" when it is.
- The counters are from one seed, so they show one run, not an effect. The rule's scored effect is the
  card's, from paired seeds; the panel quotes it when a card is given, and otherwise says "not scored".
  The card is scored on the SMT2020 model with its own transport times; the replay runs the campus
  layout's shop, and the panel says so.

Not in this step: a model-written rule (it waits on the key), a voice-over, the Blender version.
