# A faithful BIM of the construction documents, and the model in Blender

A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. The model stays a concept for licensed
review, NOT FOR CONSTRUCTION, like every sheet.

Decided by quiz on 28 Oct 2026. The founder: "generate a faithful BIM for this and then use our pipeline for
converting this to Blender".

- **True shapes for every element.**
- **Blender on this laptop.** Blender 5.2.3 LTS from download.blender.org, checksum checked, in
  `~/Applications/Blender.app`.
- **The stair doors fixed from the construction documents on.**
- **The film's tool models placed in each tool's box in Blender**, marked as dressing outside the IFC.

Live timeline: a private plan page

## Why

The construction documents' IFC holds 20,043 elements in the right places and sizes, but every one is a rectangular
box:

- pipes and ducts are square;
- a stair is one block;
- doors sit in walls with no openings;
- an array box stands for many sprinkler heads or filter units;
- nothing has a material.

The sheets draw more than that.

## The rule

1. **Everything a sheet draws is in the model, with the shape the sheet draws.** The table below lists, sheet by
   sheet, what is drawn and the shape it gets.
2. **Every shape stays inside its element's box** (to 1 mm). The coordination check reads the boxes, so it still
   holds: 0 hard clashes.
   - Parts of an aggregate (a stair's flights, landings and handrails) stay inside the aggregate's box.
   - Openings are not shapes. An opening may pass through its host.
3. **Repeats are one shape placed many times.** In the IFC, an `IfcRepresentationMap` drawn by `IfcMappedItem`s.
   - An element is either all mapped items or all solids, never both.
   - The sprinkler heads, filter units and raised floor pedestals are repeats.
4. **Every element carries a material.** An `IfcMaterial` through `IfcRelAssociatesMaterial`, and the same colour as an
   `IfcSurfaceStyle` on its solids, so any IFC viewer shows it.
5. **What is unchanged:**
   - every element's box, key, GlobalId, name, class, predefined type, storey and property sets;
   - the schematic set and the design development set, byte for byte;
   - the 73 sheets, rules, verdicts and ledger, except where this spec changes them (the stair doors, and new
     fit-out drawn on the enlarged plans).

## How it runs

- `viz/permit/run.py --stage cd` (unchanged command) adds a shapes pass, `viz/permit/bim_shapes.py`, in two steps:
  - before coordination: the new elements (fit-out, ladders, stair parts), so the clash check sees them;
  - after coordination: shapes, openings, repeats and materials.
- `viz/blueprint/ifc.py` writes them when an element has them; elements without them are written as before.
  So the schematic and design development IFCs keep their bytes.
- `fab-permit.ifc` in the construction documents' folder is the faithful BIM.
- The run also writes `boxes.json`: each element's GlobalId with its class and box, so the inside-the-box check reads
  the same boxes the clash check reads.

## What each thing becomes

### Architecture (A-sheets)

| Drawn on | Thing | In the model |
|---|---|---|
| A-111 to A-122, A-611/612, A-521 | Every door (278) | An `IfcOpeningElement` voiding its one host wall (`IfcRelVoidsElement`), filled by the door (`IfcRelFillsElement`).<br>The door is a hollow metal frame and a leaf:<br>- jambs and head 50 mm on the face, the depth of the door's box;<br>- leaf 45 mm thick, centred, 3 mm clear at the jambs and head, 10 mm at the sill.<br>The box is the frame's outside; `OverallWidth` stays the box width. The clear width (box less frame and stop, 1.2 m boxes give 1.094 m, 43 in) goes in `FabGym_Door.ClearWidth` for licensed review. |
| A-141/142, A-531 | Roof hatches (2) | An opening in the roof slab, filled by the hatch: a 50 mm curb frame and a lid inside its box. |
| A-531 | Hatch ladder (2, new) | A fixed ladder under each hatch, from the top of the filter ceiling to the underside of the roof. `IfcStair` `USERDEFINED` "fixed ladder": two rails and 300 mm rungs, all round bars. |
| A-202, A-311 | Facade walls (IMP-1) | Insulated metal panels in 1.2 m modules: one solid per panel with 10 mm joints, inside the wall's box. Doors' openings cut through them. |
| A-202, A-531 | Parapets (8) | A body 0.95 m high and a metal coping (PC-1) 50 mm thick over the full width. |
| A-531 | Equipment curbs (16) | A hollow curb: 100 mm walls round the unit's footprint, inside the box. |
| A-531 | Roof drains (80) | A sump and a domed strainer: two coaxial cylinders inside the box. |
| A-411, A-412 | Every stair (24) | An `IfcStair` aggregating its parts (it keeps no body of its own):<br>- two `IfcStairFlight`s of 22 risers each, riser = clean floor height / 44 (170.5 mm), tread 280 mm, 1.45 m wide (at least 44 in), a sawtooth section swept across the width;<br>- the top landing at the clean floor and a mid landing (`IfcSlab` `LANDING`), at least the stair's width deep (the support floor is the bottom landing);<br>- handrails on both sides of each flight (`IfcRailing` `HANDRAIL`), 40 mm round, 0.9 m above the nosings (34 to 38 in).<br>Flights from the support floor to the clean floor, as the sheets draw them. |
| A-411, A-412 | Stair cores and lifts | An opening in each slab and covering they pass (waffle slab, raised floor), the core's outer footprint. |
| A-701 | Toilet rooms | Toilet partitions (`IfcWall` `PARTITIONING` "toilet partition", 25 mm, 1.8 m high, 0.15 m off the floor): one between and at the end of each row of water closets, as A-701 draws. A mirror over each lavatory (`IfcFurniture` "mirror", 6 mm). |
| A-413, A-702 | Gowning rooms | A bench, 8 locker bays, a garment rack (`IfcFurniture`), and an air shower at the fab door (`IfcUnitaryEquipment` `USERDEFINED` "air shower"), placed as A-702 draws them. |
| A-551, A-112/122 | Raised floor | The whole-floor covering becomes its 30 mm tile layer. A separate element per building holds the pedestals: a base, a 25 mm tube and a head on the 600 mm grid, as repeats. Over bay 09 the tile layer has an opening where the bay's own tiles lie. |
| A-131/132, A-541 | Filter ceiling | The ceiling covering keeps its body; the filter units are repeats (below). |

### Structure (S-sheets)

| Thing | In the model |
|---|---|
| Columns, footings, base plates, waffle ribs | Their boxes are their shapes (concrete and plate). |
| Roof beams | Wide-flange I sections (`IfcIShapeProfileDef`), depth and flange width from the box, web 12 mm and flanges 20 mm (assumed). |
| Roof trusses | Chords and a Warren web inside the box:<br>- top and bottom chords 0.3 m square tubes;<br>- verticals 0.16 m at the bay 09 spacing, with diagonals between them.<br>The three trusses whose members bay 09 models aggregate those members and keep no body. |
| Cross bracing | Two diagonal round rods (40 mm, assumed) crossing in the box's plane. |
| Anchor rods, reinforcing bars | Round. The bottom mats are the bars each way, as many as their numbers give. |
| Waffle slab | Its body, with an opening over bay 09 where the ribs lie. |

### The trades (M, P, FP, FA, E sheets)

| Thing | In the model |
|---|---|
| Pipe segments, conduit, hanger rods | Round (`IfcCircleProfileDef`) along the box's long axis. Diameter: the box's smaller cross dimension. |
| Ducts | Round where the box's section is square and its side is a round size (0.1 to 0.5 m); otherwise rectangular. |
| Cable trays | Open channels (`IfcUShapeProfileDef`), flanges up, 2 mm (assumed). |
| Isolation valves | A body along the pipe, a bonnet and a handwheel inside the box. |
| Sprinkler heads (158) and arrays (2,144 holding 11,289 heads) | A pendent head (a body and a deflector disk) as a repeat.<br>An array places exactly the number of heads its numbers give, on an even grid inside its box. |
| Fan filter units (1,914) and arrays (401 holding 38,546 units) | A 1.2 x 0.6 m unit (a frame and a filter face) as a repeat.<br>An array places exactly its count, in rows, turned where that fits more. |
| Spot smoke detectors, sampling ports | Round. |
| Emergency showers | A pipe column with a shower head and an eyewash bowl. |
| Water closets, lavatories, sinks | A pan and cistern; a basin; a sink, each inside its box. |
| Panelboards, transformers, gas cabinets, valve manifold boxes, lights, alarms, gas detectors | Their boxes are their shapes. |

### Plant and site

| Thing | In the model |
|---|---|
| Scrubbers, tanks, stacks | Vertical cylinders. |
| Chillers | Two shells on a frame. |
| Fans | A scroll housing and a motor. |
| Air handlers, generators, cooling towers, campus buildings, roads, pads | Their boxes. |
| Hoist rails | An I section along the rail. |
| Tools and stockers | Their boxes: the owner's equipment envelopes, as the tool cards give them. |

## Changes the faithful model makes to the design

### The stair doors

A two-flight stair arrives at the end it starts from. As drawn, no stair could be built:

- the spine stairs' clean floor doors sat at the west end (x - 2.5 m) and the passageway door at the east end
  (x + 3.0 m);
- the facade stairs' inner doors sat mid-wall over the flights.

**The fit.** The core's inside is 9.1 x 3.0 m. Each run of 21 treads takes 5.88 m, and the mid landing needs at
least the stair's width, 44 in (1.118 m, so 1.12 m). That leaves at most 2.10 m for the landings at the floors. So
from the construction documents on, every stair is laid out the same way:

- the floor landings are at the east end, 2.10 m deep, and the mid landing at the west end, 1.12 m deep;
- the two lanes are 1.5 m each with a 0.1 m well;
- flight A rises west from the support floor, in the lane away from the door that serves the support floor;
- flight B rises east to the clean floor, in the other lane, where the support floor walks freely under it (at least
  3.55 m of headroom);
- the top landing covers both lanes.

**The doors move to fit** (as built; see Changes):

| Stair | Door | Moves to |
|---|---|---|
| Spine | Clean floor doors | x + 3.1 m |
| Spine | Passageway door | stays at x + 3.0 m, opening into flight B's lane |
| Facade | Clean floor door | x + 3.1 m, or x - 3.1 m where the facade ends first (the stair mirrored) |
| Facade | Support floor door | stays at x: at that level the facade-side lane runs free under flight B |
| Facade | Discharge door | to the landing end, like the clean floor door |

Each door's near edge is then 2.5 m from the core's east end, inside the 2.10 m landing with 5 cm to spare.

The schematic and design development sets keep the old doors. Their stairs were blocks (LOD 200), and the fault
belongs to the detail.

### The passageway's discharge (decided 28 Oct by quiz)

An exit passageway runs from its spine stair to an outside door in the facade, 3.0 m east of the stair's mid line.
Passageway P2-XP15S's door landed behind facade stair P2-FS16S: the tower stands outside the facade from x 498.25,
and the door spanned x 498.2 to 499.4. An exit passageway should discharge outdoors.

From the construction documents on, where a facade stair's tower stands across a passageway's outside door:

- the door moves along the facade to the nearer side of the tower that is clear, 0.3 m from the tower's wall;
- the passageway's last 2.4 m widens to that side as a **discharge vestibule**, with its own walls (1 h, like the
  passageway's) and its own space, "Exit passageway ... discharge vestibule";
- the passageway's wall on that side stops at the vestibule's cross wall.

Every other passageway keeps its door. Only P2-XP15S changes in this layout; its door moves west to x 496.75 to
497.95.

### The gowning rooms' way in (decided 28 Oct by quiz)

Each gowning room had one door, to the fab, beside the air shower. The clean floor has no support corridor; people
reach it by the stairs, which open onto the spine, and by the passenger lift at the west end, which comes up from the
support floor.

From the construction documents on, each gowning room gets a second door, the **entry door**:

- in the room's end wall away from the spine (the north end of GW1, the south end of GW2), 0.3 m in from the
  fab-side wall;
- in GW1 it opens beside the passenger lift's landing (P1-L1 and P2-L1 stand against GW1's north end), so a person
  coming up from the support floor steps out of the lift and into the gowning room;
- hardware set HW-9, "Gowning entry door": lever passage set, closer, card reader outside.

The way in is then: lift, entry door, benches and lockers, air shower, fab door. The spine is still open to the bays
and the stairs still open onto it: zoning the spine away from the bays is not part of this change.

The schematic and design development sets keep the old passageway door and the single gowning door.

## The model to glTF

`viz/bim/gltf.py --all --ifc <ifc> --out <glb>` (the default, structure only, is unchanged).

- **One tree:** site, buildings, storeys, then every element with a body, as nodes. Spaces are under their storey.
  Aggregates have their parts as children.
- **Node names and extras:**
  - each node is named `<Class>_<GlobalId>`;
  - its extras hold GlobalId, Name, Class, PredefinedType, ObjectType, Storey and every property set, as
    `"<Pset>.<Prop>"`;
  - one primitive per material, each material named after its IFC material.
- **Repeats** are written once per map. The element's node holds a child carrying the map's mesh and
  `EXT_mesh_gpu_instancing` (TRANSLATION, ROTATION), listed in `extensionsUsed` only.
- **Checks:**
  - each node's bounds (instances included) equal the element's from IfcOpenShell, to 1 mm;
  - the same bytes every run;
  - no brand names.

## Into Blender

`Blender -b -P viz/blender/bim.py -- <glb> <scene> <models> <out> [--stills] [--res WxH] [--samples N]`

- **Reading the GLB:** our reader, not Blender's importer. The importer makes one object per instance, which does
  not scale to 230,000 repeats.
  - One object per element node, its mesh shared where the GLB shares it, its extras as custom properties.
  - A repeat is one object: a point cloud of the instances, with a Geometry Nodes "Instance on Points" of the map's
    mesh.
- **Collections:** building, then storey, then trade.
  - Architecture, Structure, Mechanical, Plumbing, Fire, Electrical, Process, Site, by class (the table in
    `bim.py`).
  - Spaces go in a hidden collection.
- **Materials** by name, Principled. Each has a look table: concrete, steel, panel, glass, copper, stainless,
  galvanised, vinyl and so on.
- **Tools:** the film's tool models (`data/layout-real/models.json`) placed by each tool's origin and turn from the
  scene.
  - They sit in a collection "Dressing (not in the IFC)".
  - The IFC's tool boxes go in a hidden collection.
- **Output:** saves `fab-bim.blend`. With `--stills`, it renders six stills: the campus, a cutaway through phase 1,
  the sub-fab, bay 09, a spine stair and a gowning room. Each still carries the truth line in the corner.

## Checks

`viz/tests/test_bim_faithful.py` (.venv; runs `--stage cd` into a temporary folder):

- **Doors:** every door fills one opening that voids one wall. The opening lies inside that wall's footprint on the
  wall's long axis and spans its thickness.
- **Stairs:** every stair has two flights of 22 risers (riser 170.5 mm within 1 mm, tread 280 mm), a top and a mid
  landing at least 1.118 m deep, and four handrails 0.864 to 0.965 m above the nosings. Each stair's doors open onto
  a landing: inside the floor landings' 2.10 m at the east end, at the support floor or the clean floor.
- **Round things:** every pipe segment, conduit, hanger rod, anchor rod and reinforcing bar is round, and every duct
  of a round size.
- **Repeats:**
  - sprinkler and filter arrays hold exactly their counts;
  - the pedestals cover each raised floor on the 600 mm grid;
  - instances never overlap each other.
- **Fit-out:** toilet partitions and mirrors in every toilet core, gowning fit-out in every gowning room, a ladder
  under each hatch.
- **Discharge:** every exit passageway's outside door is in a facade wall, clear of every facade stair tower by
  0.3 m, and inside the x span of the passageway or its discharge vestibule. P2-XP15S has a vestibule.
- **Gowning:** every gowning room has its fab door and an entry door in its end wall away from the spine, hardware
  HW-9; the 1.2 m outside the entry door is clear of the lift; GW1's entry door is within 3 m of its building's lift.
- **Facade and parapets:** facade panels in 1.2 m modules; parapets with copings.
- **Trusses and bracing:** chords and webs in every truss; X bracing.
- **Inside the box:** every element's geometry (IfcOpenShell) inside its box to 1 mm.
- **Materials:** every element has a material and a surface style.
- **The set:** 0 clashes; the IFC valid; the same bytes twice; the schematic and design development IFCs equal
  their hashes before this work.

`viz/tests/test_bim_glb_all.py` (.venv):

- **The tree:** one node per element with a body.
- **Extras and materials:** extras and property sets; materials named after the IFC's.
- **Instances:** instance counts equal the mapped items.
- **Bounds:** sampled bounds equal IfcOpenShell's to 1 mm.
- **The default mode:** structure only, with the same bytes as before.
- **The rest:** the same bytes twice; no brand names.

`viz/tests/test_bim_blender.py` (runs Blender headless; skips without it):

- the objects and instance counts equal the GLB's;
- custom properties carry GlobalId;
- collections by building, storey and trade;
- every tool's dressing lies inside its IFC box to 5 cm;
- one still renders, not blank, with the truth line.

## Changes

Made while building, 28 Oct 2026, before the code was committed:

1. **Stairs.** A stair's landings sit at the east end unless the fab's facade ends before the clean floor door. Then
   they sit at the west end, mirrored; P1-FS22S and P2-FS16S straddle the end of their building.
   - The facade stairs' support floor doors keep their places. Moving them put P2-FS16S's door on top of exit
     passageway P2-XP15S's outside door. At the support floor the lane under the upper flight is free (at least 3.55 m
     of headroom), so the door needs no landing.
   - The test now asks this: the clean floor doors, and any door on the lower flight's lane, open onto the top
     landing's span. A support floor door on the other lane may sit anywhere along the stair.
2. **Hatch ladders** stand on the filter ceiling (the air space's floor plus 0.35 m). The test had used the air
   space's floor.
3. **Fan filter units.** Design development shared a space's units among its carved pieces by area, and gave the
   remainder to the last piece. So some pieces held units they cannot fit: 29 units on a 0.8 x 2.8 m piece, and one
   on 0.2 m strips.
   - Each space keeps its total, 38,546 in all, shared by what each piece holds in rows. Every space fits.
   - A piece too narrow for a unit becomes a blank panel in the grid ("0 units"). The test accepts those.
4. **Bay 09's trusses.** The construction documents had replaced the three trusses over bay 09 with chords and
   verticals, leaving no truss element. Each comes back as a truss that holds its members, with the diagonals the
   truss detail (S-510) gives added inside it.
5. **A door across two panels** (bay 09's chase partition is in 1.2 m panels) cuts an opening in each panel, clipped
   to it. The door fills the opening in the panel that holds most of it.
6. **The glTF test** compares a material set (a door's frame and leaf) by the materials in it.
7. **Tool dressing in Blender.** Each film tool model's body lies inside its IFC box (to 5 cm). Its status light
   tower stands on top, up to 0.6 m above the box (the furnace's pole), as in the film. So the tower is a separate
   object, and the test checks the body.

Found while building and fixed after the founder's quiz (28 Oct; see "Changes the faithful model makes to the design"):

8. **Exit passageway P2-XP15S** discharged through its outside door into facade stair P2-FS16S's tower. Its door
   moves west of the tower, through a discharge vestibule.
9. **The gowning rooms** had one door, to the fab. Each gains an entry door at its end away from the spine, beside
   the lift in GW1. The door count goes from 278 to 282.
