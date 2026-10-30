# The cast: prompt for the icon sheets

Written 30 Oct 2026 for an image model (Gemini, Meta's Muse Image, or Argon). From the SMT2020 testbed; the machines
are generic types, never a real company's tools. Default style: the boot-camp comic of `docs/img/fabgym-hero.jpg`
(not yet chosen by the founder; to change it, replace the STYLE block only).

How to use:
- Attach `docs/img/fabgym-hero.jpg` as the style reference with every prompt.
- Sheet A (the 11 machines and the wafer coach) is the one that matters. Sheet B (logistics) is optional.
- If the model cannot hold 12 characters in one picture, use the single-character prompt at the end, once per cell,
  with the same reference image.
- Bring the files back as they come (PNG, the largest size offered). We slice the grid, remove the white
  background, and check each tile at 64 px.

---

## Sheet A prompt (paste everything in the box)

```
Create one character sheet: 12 cartoon characters on a 4 × 3 grid of equal square cells, landscape 4:3, the largest
size you can make (at least 2048 × 1536 pixels). One character per cell, centred, full body, nothing else in the cell.

WHAT THIS IS
A cast of anthropomorphised semiconductor fab machines for "Fab Gym", a game-like simulator of a chip factory. Every
machine is a gym-goer with a "gym bro" attitude, doing the exercise that matches its real job. The joke only works if
each machine still looks like the real kind of equipment it is, so every character must have its own body shape,
size and silhouette, and its own clearly visible exercise. No two characters may share a body shape or a pose.

STYLE (match the attached reference image)
- Hand-inked comic illustration: bold, clean black outlines of one even weight; flat cel colour with a single shade
  tone; a little cross-hatching in the shadows; small sweat drops and motion lines where they help.
- Cute but determined: chunky proportions, slightly oversized heads, expressive.
- Plain flat white background in every cell, with only a soft grey oval shadow under each character. No floor, no
  room, no scenery, no grid lines, no borders, no labels.
- Three-quarter front view, the same camera height and lighting from the upper left for all twelve.
- Each character fills about 75% of its cell with even margins; big readable silhouettes that still read when the
  cell is shrunk to 64 × 64 pixels.

WHAT EVERY MACHINE SHARES (the family look)
- The body IS the machine: an off-white / light grey cleanroom casing in the machine's real shape, with coloured
  accent panels in its family colour (given per cell).
- A face on a rounded rectangular screen set into the front of the body: dark screen, simple glowing mint-green
  eyes and mouth drawn as lines and dots.
- A red sweatband headband wrapped around the top of the body, its two ends flying, and red wristbands. This is the
  signature of the cast: every machine wears it.
- A small three-colour signal light tower (red, amber, green) on top, with green lit.
- Cartoon robot arms and legs, jointed, light grey, with chunky feet in the family colour.

CELLS, left to right, top row first
1. LITHOGRAPHY ("The Poser"), family colour amber #E3A21A. Body: the biggest machine on the sheet, a long, tall
   rectangular cabinet with a thick cylindrical lens column rising from its top. Exercise: a bodybuilder's front
   double-biceps pose, both arms flexed high, standing in a cone of warm amber-yellow stage light from above.
2. LITHO METROLOGY ("The Balancer"), family colour grey #7D8A93. Body: a compact upright cabinet with a microscope
   turret on top. Exercise: balancing on one leg on a half-dome balance trainer, arms straight out to the sides,
   perfectly level; small crosshair marks in its eyes.
3. DRY ETCH ("The Boxer"), family colour orange #E0703F. Body: a cluster tool, a central hexagonal hub with three
   round process chambers attached around it like huge shoulder pads. Exercise: landing a punch on a hanging heavy
   bag, boxing gloves glowing violet-pink like plasma, sparks and tiny chips flying from the bag.
4. WET ETCH ("The Swimmer"), family colour orange #E0703F. Body: a long, low, wide wet bench, a row of three open
   tanks, with a small overhead gantry for arms. Exercise: swimming front crawl inside its own tank of pale blue
   liquid, wearing a swim cap and goggles over its screen face, splashes everywhere.
5. DIFFUSION ("The Yogi"), family colour rose red #D2455E. Body: the tallest and narrowest machine, a vertical furnace
   tower with a window showing a stack of wafers inside. Exercise: tree pose on a yoga mat, palms together overhead,
   calm face, wavy heat-haze lines rising around it.
6. DIELECTRIC ("The Squatter"), family colour blue #3B7DD8. Body: a squat cube with a domed lid. Exercise: the
   bottom of a barbell back squat, the bar loaded with many thin plates stacked in visible layers on each side.
7. THIN FILM ("The Kettlebell"), family colour blue #3B7DD8. Body: a short, round, drum-shaped vacuum chamber with a
   flat disc lid on top. Exercise: a two-handed kettlebell swing at the top of the swing, a thin, even veil of white
   chalk dust drifting down over it.
8. THIN FILM METROLOGY ("The Little Lifter"), family colour grey #7D8A93. Body: the smallest machine, a little
   benchtop box with one thin probe on a short arm. Exercise: standing on a bathroom scale doing curls with tiny
   dumbbells, chest puffed out, very proud.
9. ION IMPLANT ("The Thrower"), family colour violet #8A62D6. Body: a long L-shaped beamline: a boxy source at one
   end, a bent magnet elbow, a long tube ending in a round end station. Exercise: throwing a medicine ball from the
   end of its tube at a round target on a small wall, two more balls already flying in a straight line.
10. CMP POLISHER ("The Plank"), family colour teal #1E9E93. The star, the same character as the sweating robot in the
    reference image. Body: a large flat round polishing table as its torso, with a polishing head on a swing arm.
    Exercise: a perfect forearm plank, body horizontal and dead flat, a yellow spirit level balanced on its back
    with the bubble centred, heavy sweat, gritted teeth.
11. DEFECT INSPECTION ("The Spotter"), family colour grey #7D8A93. Body: a cabinet with a scanning camera dome on top
    and one big round magnifying lens in front of its face. Exercise: spotting a bench press: leaning over an empty
    barbell resting on a rack, hands hovering under the bar, staring hard through the magnifier.
12. THE WAFER ("The Drill Coach"), the same character as the wafer in the reference image: a round silicon wafer with
    a shimmering rainbow grid of chips on its face, an angry face, a red headband, a whistle on a cord, white
    sneakers, thin black arms and legs, pointing and shouting.

DO NOT
- No text, letters, numbers, logos, brand names or watermarks anywhere.
- No real company's equipment or branding; generic machines only.
- No humans and no extra characters; each cell holds exactly its one character.
- No photorealism, no 3D render, no anime style, no heavy gradients.
- No injuries, blood, syringes, pills or drugs.
- Nothing outside the twelve cells; keep the white gaps between cells clean so the sheet can be cut apart.
```

## Sheet B prompt (optional, the logistics)

```
Same style, rules and family look as the attached sheet. Create 4 characters on a 2 × 2 grid of equal square
cells, square picture, white background, one character per cell, full body, no text.
1. THE STOCKER ("The Locker"), family colour grey #7D8A93: a tall locker cabinet with its doors open, shelves holding
   small grey wafer pods; doing a standing hamstring stretch with one foot up on its own lower shelf.
2. THE OVERHEAD VEHICLE ("The Zip-liner"), family colour amber #E3A21A: a small car hanging from an overhead rail
   like a zip line, lowering a grey wafer pod on straps, a towel over its shoulder, cheering.
3. THE WAFER START ("The Sign-up Desk"), family colour green #2E9E5B: a small kiosk with a hatch, handing a fresh
   wafer pod out through the hatch, thumbs up.
4. THE SHIP POINT ("The Podium"), family colour gold #D9A400: a winner's podium with a wafer pod standing on top
   wearing a medal, confetti.
```

## Single-character prompt (fallback, one cell at a time)

```
Using the attached reference image's style exactly, draw ONE character on a plain white square canvas, full body,
centred, filling about 75% of the frame, three-quarter front view, light from the upper left, soft grey oval
shadow, no text or logos. It is a cartoon semiconductor fab machine with a gym-bro attitude: off-white cleanroom
casing in the machine's real shape with accent panels in <FAMILY COLOUR>, a face on a dark rounded screen with
mint-green line eyes, a red sweatband headband with flying ends, red wristbands, a small red-amber-green signal
light tower on top with green lit, light grey jointed robot arms and legs, chunky feet in the family colour.
The machine: <BODY, copied from the sheet A cell>. Exercise: <EXERCISE, copied from the sheet A cell>.
No humans, no extra characters, no injuries or drugs, no photorealism or 3D render.
```

## What makes a sheet acceptable

1. Twelve cells, one character each, nothing crossing into another cell.
2. Every machine is recognisable by its silhouette alone: the litho cabinet the widest, the diffusion tower the
   tallest, TF Met the smallest, implant L-shaped, wet etch long and low, CMP flat and round.
3. Every exercise reads at 64 px: you can name it without the caption.
4. All twelve wear the red headband and have a screen face.
5. No text, logos or real brands.
6. The CMP and the wafer look like the same characters as in the hero picture.

## Next, once a sheet is accepted

The ten moods (in the zone, dozing off, gassed, hands full, waiting for the class, changing kit, rest day, pulled a
muscle, at the physio, benched) become one sheet per machine, using the accepted tile as the reference so the
character stays the same. Those prompts come after this sheet.

---

## Results (30 Oct 2026)

Made with Meta's Muse Image (`muse-image-1.0`, `POST https://api.meta.ai/v1/images/edits`, $0.01 an image), with
`docs/img/fabgym-hero.jpg` as the style reference.

- **Sheet A:** four variants; the founder chose variant 1 ("Let's do 1. and improvise"). Lithography, litho metrology,
  implant and CMP were redrawn singly with variant 1 as the reference, for bodies less alike (4 variants each).
- **Moods:** one 5 × 2 sheet per machine with its accepted tile as the reference, 2 variants each; the more
  consistent kept. The ten moods and the simulator signal behind each are in `web/cast/cast.json`.
- **Lots:** one 4 × 3 sheet of a wafer pod in 12 moods (the hot lot in sunglasses and a gold chain), 2 variants,
  variant 1 kept.
- About 48 images in all, about $0.48 of the Meta credit.

In the repository: `web/cast/` (WebP, transparent background): `base/` the 12 cast tiles at 384 px, `<machine>/<mood>.webp`
and `lots/<mood>.webp` at 224 px, and `cast.json`. The full-size sheets stay outside the repository.

Known drift: dielectric's second screen comes and goes; thin film's kettlebell sometimes reads as its head; at 64 px
thin film metrology and dielectric look alike. The provider's terms on generated images are to be read before the
repository is made public.
