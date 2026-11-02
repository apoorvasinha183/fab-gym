# The 3D fab and its guide

Written 2 Nov 2026, before the code. Tests in `viz/tests/test_fab3d.py` and `agent/tests/test_fab3d.py` are
committed with this file ("Hard hats") and before the code they test ("Grand tour"). Plan page (private). From the SMT2020 testbed; a gigafab-style layout of our own
design; not a real fab.

## What it is

A walkable 3D fab built fresh in Godot, on today's US building (the design-development layout with its rail and
160 vehicles: `web/data/building.json` and `web/data/shop-real.txt`). The robot CEO guides a visitor through both
phases, then steps back so the visitor can walk or fly anywhere. Questions are typed or spoken. A cinema outside
the fab plays the silicon film. It runs on the Mac and, exported, in the browser.

Decided by quiz on 2 Nov: tool models of our own made in Blender; typed and spoken questions; Mac and browser;
live from the helper; two phases with copper-only carriers. Added by the founder the same day: higher visual
quality in full colour, only what is near the viewer loaded with its state from the simulator (rail included), free
exploration that teaches, and a cinema.

## Streaming: only what is near

- `agent/fab3d.py` cuts the campus into square **cells** of 24 m (assumed), one function used by both the helper and
  `viz/fab3d/prep.py`, which writes
  `viz/fab3d/data/campus.json`: for each cell, its tools (index into `building.json`'s tools), its rail stretches
  (`from>to` node pairs), its stockers. Every tool lies in exactly one cell (by its centre); a stretch lies in every
  cell it crosses. The data folder is copied, never committed.
- The scene keeps a ring of cells loaded around the viewer: full detail within 48 m, simple boxes to 120 m, nothing
  beyond (both assumed). Cells load on a background thread (`ResourceLoader.load_threaded_request`); a cell's tools
  are one instance of their kind's scene each, so a kind's mesh and textures are loaded once and shared.
- Nothing far away is moved. The scene asks the helper only for the cells it holds.
- This is how open-world games keep their frame rate (the founder, 2 Nov: "Isn't it the way good games work? I
  think I can get 60 fps with that"): chunks streamed around the player, detail by distance, many copies of one
  object drawn together (a cell's simple boxes as one MultiMesh per kind), and what is hidden not drawn.

## Frame rate

The bar: 60 frames a second on this laptop at 1920 by 1080, Godot's Forward+ renderer, while the tour walks the
whole fab: the 99th-percentile frame at most 16.7 ms over the tour, measured with the window on top and every frame
drawn (a hidden window draws nothing and reads falsely fast). The browser export is not held to this bar; its frame
times are reported.

## The live run, held by the helper

- `POST /api/fab3d/run` `{seed, days}`: runs `fabsim moods` over the whole fab every 10 minutes (assumed), keeps it
  in memory, answers `{run, minutes, frames, score}`. The simulator is light (about 0.6 s for a day of the
  realistic campus on the laptop), so a run is made when the scene opens and again for a what-if.
- `GET /api/fab3d/state?run=ID&t=MIN&cells=a,b`: the tools of those cells with their state at the frame at or
  before `t` (`work`, `sleep`, `pm`, `hurt` and the rest of `tool_moods`), each group's queue there, and the carriers
  on those cells' stretches at `t`, each with its position along its stretch (0 to 1), loaded or not, hot or not, and
  **copper** when the lot it carries is next bound for a back-end (copper) group. Carrier moves come from `fabsim
  replay` for a 30-minute window around `t`, cached by window; `replay` is extended to give each loaded stay its
  lot's next group, so the copper rule can be applied.
- `POST /api/voice` `{audio, mime}`: the recording to Meta's speech model, the words back `{text}`; the helper's
  meter counts its cost; with `--stand-in` it answers a recorded text and calls nothing. Spoken and typed questions
  then go through `/api/bar/route` as on the Floor (rules first, the model only if unsure).

## The scene (`viz/fab3d/`)

Saved scenes and resources, a thin importer (as the founder asked on 27 Oct):

- `main.tscn`: the world, the visitor (walk with WASD, fly with F), the streamer, the guide, the panel.
- `tools/<kind>.tscn` for the eleven kinds (scanner, track, etch, deposition, furnace, implanter, polisher,
  wet_bench, metrology, inspection, epitaxy), `tools/stocker.tscn`, `carriers/standard.tscn`,
  `carriers/copper.tscn`, each from a glTF made in Blender by `viz/blender/tools/<name>.py`.
- `guide/ceo.tscn`: the robot CEO in the navy coat, walking and talking.
- `cinema/cinema.tscn`: a building beside the office with a lobby and a hall; its screen plays
  `res://data/film/from-sand-to-chip.ogv` (the film converted to Ogg Theora by ffmpeg; Godot plays Theora).
- A tool's colour carries its state as on the Floor; each area has its own colour; cards per kind and per area teach
  what the step does to the wafer (the ten stages of the Floor's "How a chip is made") with the live numbers.

## The guide

A tour along a fixed path through phase 1, over the bridge, through phase 2 and out to the cinema, stopping at
each area with a line about it and its live numbers. Then the visitor is free. "Show me X" walks the guide to the
group; "what if" asks the helper for a run with the change and shows before and after, naming what the change moved
(transport time and hoist metres as well as wafers out).

## Tests (written before the code)

- **F1** `prep.py`: every one of the 1,043 tools in exactly one cell; every rail stretch of the track in at least one
  cell; no cell outside the campus; every tool kind has a scene listed.
- **F2** The copper rule: a carrier is copper when its lot's next group is a back-end group, and only then.
- **F3** The helper: `/api/fab3d/run` keeps a run; `/api/fab3d/state` for one cell returns that cell's tools and no
  others, each tool's state equal to the moods frame at or before `t`, and carriers only on that cell's stretches,
  with positions between 0 and 1.
- **F4** `/api/voice` with `--stand-in` answers the recorded text and calls no network; a recording over 20 MB is
  refused with a message (the scene's recorder stops at 30 s); with no model and no stand-in it says so.
- **F5** The scene's text says it is from the SMT2020 testbed and not a real fab, and names no tool maker or fab
  company.
- **F6** Headless Godot (`godot --headless --path viz/fab3d -- --check OUT.json`): the main scene opens; every kind,
  the stocker, both carriers, the guide and the cinema have saved scenes; with the visitor at the bridge, at most
  the cells within 120 m are loaded; the cinema's player holds the film.
- **F7** Each Blender script exists and its glTF's footprint matches its kind's size within 5%.
- **F8** The frame-rate bar: a timed run of the tour on this laptop reports a 99th-percentile frame of at most
  16.7 ms, with at least 99% of frames drawn; the report is kept in `data/fab3d/perf.json`.

## Changes

Made while building, 2 Nov:

- The cells are cut by `agent/fab3d.py` (one function for the helper and `viz/fab3d/prep.py`).
- `fabsim replay` gives each loaded stay its lot's next group (its next job, else the route's next step), for the
  copper rule; `/api/fab3d/state` takes `span` and returns every stay over [t, t + span] with its times, so carriers
  glide between asks. The 3D runs call the simulator directly on our built shop (`shop-real.txt` has no floor plan for
  the editor's checks).
- Questions: the Floor's rules live in the page's JavaScript, so the scene answers "show me", "why is this queue
  long" and "what is" with its own rules from the live run, and passes anything else to the helper's glossary (Meta's
  model). "What if" is not built yet.
- The film is converted by Blender's own FFmpeg (Homebrew's ffmpeg has no Theora encoder).
- The characters come from turnarounds Meta's Muse Image drew from the founder's coat-CEO picture and the gym's hero
  picture (design A), modelled on the CC0 skeleton with its CC0 clips. Godot's importer drops "_Loop" from clip names.
- The building's glTF (1,004 meshes) is merged into one mesh per material in Blender (6 meshes).
- Workers appear only where they matter: kneeling at tools that are down nearby, and a few operators.
- The microphone needs audio input on, so macOS asks for permission when the scene opens; timed and still runs use
  Godot's dummy audio driver.
- F8 on this laptop (Apple M1): median and 99th-percentile frame 16.67 ms over 3,600 frames, 99.97% drawn. The run is
  held to the display's 60 Hz, so the headroom under the bar is not measured.
- Not yet: the browser export, the recorded tour, "what if" inside the 3D fab.

Made after the founder's review, 2 Nov ("it is not looking like a fab at all, you killed the rail details, also how
can it be so fast?", then "now nothing is moving on the rail"):

- The clock starts at real time (buttons: real time, 10×, 60×). At the old one simulated minute a second every vehicle
  moved 60 times too fast. The run is still worked out whole by the helper in about 1.2 s and polled once a second for
  the cells near the viewer; nothing is stepped live.
- Vehicles move at the shop's speed (150 m a minute) and reach the far end of a stretch when the simulator says they
  leave it, so time queued behind another vehicle is spent waiting at the near end (spreading a stay evenly had made
  queued vehicles creep). A stay sent open-ended at a 30-minute window's edge is driven at speed and then stands.
- `/api/fab3d/state` with a span also sends stays that ended up to 5 minutes before t (`PARK`), but only a vehicle's
  latest move anywhere in the fab, so one standing over a port is held there and one that drove on elsewhere is not
  left behind. Over a port or a stocker, a gap of at least half a minute before the next stay is the hoist transfer:
  the pod goes down on belts to the load port and back up (the carrier models now export the gripper and pod as their
  own piece, "hoist").
- The rail is an aluminium channel (cap and two flanges) hung from the filter ceiling by a rod every 3 m (a scaling
  bug had drawn it as wide beams). Cleanroom surfaces: perforated raised-floor tiles of 0.6 m, a ceiling of 1.2 m filter
  units glowing white, yellow filter light over lithography, white wall panels and columns; bay floors no longer
  tinted, a stripe of the area's colour at each bay's mouth and a small sign hung at its mouth. Sizes assumed.
- The follow camera is at eye height (1.75 m) on the spine. That view cost GPU fill under 2× MSAA (99th-percentile
  frame 18.8 to 19.4 ms); with SMAA instead, F8 is back at median and 99th percentile 16.67 ms, 99.97% drawn. The perf
  report lists each slow frame with its time. `--near-vehicle` frames the stills on one vehicle, one lowering its pod
  if there is one.
