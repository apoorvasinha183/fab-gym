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
- **F9** From the parking lot to the cleanroom (the founder, 2 Nov: "I want the boss to take you from the parking lot
  to the clean room"; by quiz: the full gowning route, the CEO wiped down and not gowned). `agent.fab3d.entrance`
  reads the permit set (`data/layout-real-dd/permit-cd/us/boxes.json`): the passenger lift, gowning room P1-GW1, its
  entry door and cleanroom door, the air shower, eight lockers, the bench and the garment rack, each with its permit
  key and box unchanged. What the permit set lacks is ours and marked assumed: a parking lot west of phase 1, a
  visitor pavilion, a ground door in the west wall into the lift, and the lift lobby's two walls. The route goes lot,
  pavilion, lift (ground), lift (clean floor), gowning room, air shower, cleanroom, then the spine where the tour
  goes on. Each leg stays on one level, except the ride, which stays inside the lift's footprint; no leg crosses a
  permit wall, an assumed wall, a column or a tool at its level except through a door or opening. The openings the
  building needs (the ground door, both gowning doors, the lift shaft through the waffle slab and raised floor) each
  meet the wall or slab they open. The headless check reports the entrance scene and the lift car, and the tour's
  first stop is the lot.
- **F10** A drone opening (the founder, 2 Nov: "Start with a drone shot of the campus where you fly around the campus
  and introduce fabgym"; by quiz: fly it and dress the outside first). `agent.fab3d.exterior` reads the permit set's
  rooftop make-up air units with their curbs, chillers and transformers, each with its key and box unchanged (16, 16,
  27, 18), and adds ours, marked assumed: roads, trees, exhaust stacks and signs; no road crosses a building, the lot
  or the cinema; no tree stands on a road, a building or the lot; every stack stands on a roof clear of the air units.
  `agent.fab3d.drone` gives the flight as timed keys (camera point, look point, an optional line from Lou and a
  label): 25 to 35 s; it starts at least 60 m up and stays at least 25 m up until its last two keys; along the path
  (Catmull-Rom through the keys, sampled every 0.1 s, the same curve the scene flies) it never enters a building
  below its parapet plus 2 m; it passes within 110 m of the centres of both phases, the bridge, the cinema and the
  utility yard; it ends at eye height within 0.5 m of where the tour's first stop puts the visitor. Its numbers
  come from the data: the tools in the campus, the vehicles in the shop and the areas of each phase. Space skips it.
  The headless check reports the drone scene and its key count, and the tour waits for the flight to end.
  The bridge between the phases (the founder: "the bridge didn't render"): the permit set holds only its outline
  (`campus/B1`), kept unchanged; ours, assumed: a deck whose top is the clean floor (7.5 m), spanning the whole gap,
  a roof, and a doorway through each fab's end wall (`P1/wall/E`, `P2/wall/W`) that the tour walks through.

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

Made for F9, 2 Nov:

- The tour starts in the parking lot. The route, the permit set's pieces and our assumed ones are worked out once by
  `agent.fab3d.entrance` and written into the campus data; Blender models the entrance from it
  (`viz/blender/buildings/entrance.py`: the lot with 84 parked cars, the pavilion, the lift shaft and car, the lobby
  walls, door frames, lockers, bench, garment rack with suits and boots, the air shower with its nozzles), and the
  building merge cuts the openings (`merge_bim.py` with the campus file: seven cuts).
- On the way in the CEO turns to talk to you and the camera holds still on its face; in the lift the camera rides in
  the car's far corner; near the building and in the gowning rooms it follows close. The air shower's jets run for a
  few seconds at that stop. A worker sits on the bench pulling on boots; another takes a suit from the rack.
- `--stop-shots` takes a still three seconds after each stop on the way in.
- Not yet: F8 on the new opening minute. One run held a 16.67 ms 99th percentile but drew 97.4% of frames; the next
  was taken with the window hidden (13% drawn), so the bar is unmeasured until a run with the screen free.


The screen and the walk, 2 Nov (by quiz from three looks drawn over the scene: a JRPG dialogue):

- `ui/ui.tscn` with the theme `ui/jrpg.tres`: framed navy windows with white borders, the CC0 Kenney pixel font
  (`ui/fonts/kenpixel.ttf`, licence beside it), a menu (ask the CEO, walk alone, speed: real time, 10x, 60x), a
  status window (clock, stop n of 29 and its name, what this is), the CEO's portrait beside a text window whose line
  types out and ends in a bobbing arrow; Space or a click finishes the line, then moves on. The text window closes
  while nobody talks. The window scales with the screen (canvas items).
- The CEO walks at 1.6 m/s with the walk clip at its own rate, eases in and out of stops, turns at a limited rate so
  corners and doors become arcs, slows for sharp turns and turns on the spot when facing away, and turns smoothly to
  the facing a stop asks for.
- On the clean floor's first minute: the air shower's jets are CPU particles (the GPU ones compiled their shader on
  first use, a hitch), and cells near the visitor stay boxes while the visitor is outside on the ground, building
  their tools (12 a frame) on the ride up.

Made for F10, 2 Nov:

- The outside is modelled in Blender from the campus data (`viz/blender/buildings/exterior.py`, 13,080 faces): the
  permit set's 16 make-up air units on their curbs, 27 chillers and 18 transformers (on a concrete pad of ours), and
  ours: six roads with dashed centre lines (the west one runs between the lot and the visitors' entrance, so the
  walkway crosses it), 102 trees, 24 exhaust stacks. The drawn building already holds the 16 stair towers. Signs
  (FAB GYM twice, PHASE 2) hang in the screen's pixel font (`exterior/exterior.gd`).
- The flight (`drone/drone.tscn`, `drone.gd`): 10 keys over 34.5 s, the camera on the Catmull-Rom curve the tests
  check; Lou's five lines go to the text window and six labels pop up. While it flies the campus loads no cells (the
  roofs stay on) and Space skips it. `--no-intro` (also implied by `--near-vehicle`) starts at the lot.

After the founder's play-through, 3 Nov:

- Flicker and shimmer, found by comparing frames on a fixed camera sweep: the slab, raised-floor, ceiling and roof
  edges lay on the walls' outside faces (z-fighting bands), now 6 cm inside; the outer walls carry the outside finish on
  their outward faces only; temporal AA on; the outside in flat panels (ribbed sheet shimmered at any setting), floor
  dots gone, ceiling grid fainter. Shimmer score outside 5.31 to 2.25, inside 5.51 to 4.03; no added flicker with the
  camera held; F8 holds.
- The walk clip's rate follows Lou's speed every frame (it had kept its rate from the first, slowest step).
- Lift: Lou stands at the car's far wall and the camera is fixed inside the car; steel doors slide open at the floor
  the car stands at. Air shower: he is 2.3 m to his stack light against a 2.2 m ceiling, so BONK!, "Ow! Somebody log
  that defect: one cracked CEO. There goes the yield." (by quiz) and he ducks through.
- Outside: the heading picture's FabGYM logo on white panels, PHASE 1 and PHASE 2 in the pixel font. The drone looks
  down at the cinema when Lou mentions it.
- The polished models (16) replaced ours after a check against the brief; ours are kept outside git.
- 3 Nov, later: tools are drawn 2% smaller across the floor, because a footprint ending on a bay's partition put two
  faces in one plane (the flickering patch seen walking from the air shower to the bay; corridor shimmer score 2.53 to
  0.71). Inside walls and columns plain; inside surfaces on render layer 2, which the sun does not light. Lou ducks
  through the air shower by squashing (2.3 m to 2.1 m) with a slight lean, so his head stays in the booth. The FabGYM
  logo is over the visitors' entrance; the phases are named by the drone's labels, now larger. `--corridor` is a fixed
  6 s camera move down that strip, for comparing shimmer.
