# From Sand to Chip: a short film in Three.js

Script draft, 29 October 2026, for the founder to agree before anything is built. It animates the "How a chip is
made" journey (`web/stages.js`): eleven steps, the fab's part on the SMT2020 model and the rest from general
knowledge, labelled so on screen. No real fab, company or product is shown.

Running time about 2 minutes 30 seconds. Lines in quotes are the narration or captions; the rest is what we see.

---

## 0. Cold open (0:00–0:08)

Black. A single grain of sand drifts in, lit from one side, slowly turning. The camera pushes in until the grain fills
the screen and its surface turns out to be a lattice of glowing points.

"This is a grain of sand. By the end of this film, it will be thinking."

Title: **From Sand to Chip**.

## 1. Sand (0:08–0:20)

Pull back to a beach at dusk, low-poly dunes. Grains pour into a furnace that glows orange. Inside, oxygen atoms
(red spheres) peel away from silicon atoms (grey spheres) and fly off with carbon (black spheres) as little puffs.

"Most of the grains on a beach are quartz: silicon locked to oxygen. Heat them with carbon, hotter than lava, and the
carbon steals the oxygen. Grey silicon is left behind."

Caption: *about 99% pure. For a chip, that is filthy.*

## 2. Purify (0:20–0:32)

The grey lump dissolves into a swirling gas inside a glass column. Impurity atoms (a few coloured specks) are filtered
out at each pass, counted down on a little meter: 99% → 99.99% → 99.9999999%.

"So the silicon becomes a gas, is distilled again and again, and freezes back into solid rods."

Caption: *one stray atom in a billion.*

## 3. Grow a crystal (0:32–0:48)

A crucible of molten silicon glows white-orange. A thin seed on a rod dips in, then rises slowly while turning. Close
up: atoms snap into a perfect grid as they leave the melt. Pull back: a tall silver ingot rises out, about a person's
height, beside a small human figure for scale.

"Now the atoms have to line up. A seed crystal touches the melt and is pulled up slowly while it spins. Atom by atom,
the melt freezes onto it in perfect order: one giant crystal."

Caption: *silicon melts at about 1,414 °C.*

## 4. Slice and polish (0:48–1:00)

The ingot lies on its side. A taut wire glints and passes through it; discs fall away in sequence. One disc tilts up
to the camera and is polished until it reflects the scene like a mirror. It slides into a sealed box with 24 others.

"A diamond wire slices it into discs thinner than a coin, polished until they shine like mirrors."

Caption: *at this scale, a speck of dust is a boulder.*

## 5. Into the fab (1:00–1:10)

The box rides an overhead track into a dark building with teal light seams: the same diorama the floor page draws.
A label fades in at the door: **SMT2020 model · simulated**. From here on a teal border frames the picture.

"The wafers enter the fab in lots of 25. From this moment on, the simulator follows every one of them."

## 6. Layer by layer (1:10–1:46)

The heart of the film. One wafer, close up, goes round the loop; each stage is a two-second vignette, faster each lap.

- Thin film: a mist settles into an even blanket.
- Lithography: yellow-lit room; ultraviolet light through a mask projects a pattern onto the resist.
- Etch: a violet plasma rains straight down and carves trenches.
- Implant: a thin beam of atoms buries itself in the open silicon.
- Wash: a sheet of water sweeps the surface clean.
- Check: a scanning line passes over; a green tick.

Lap one at full speed, lap two at double, then a time-lapse of floors stacking up like a building under construction,
with a counter: *step 1 … 583*.

"Here is the trick: a chip is built like a city, one floor at a time. A film, a pattern printed with light, an etch, a
dose of atoms, a wash, a check. Then the loop begins again."

Caption: *583 steps on 105 groups of tools. A regular lot spends about 66 days here, most of it waiting in line.*

## 7. A finished wafer (1:46–1:56)

The wafer rises and turns to face us: a mosaic of identical dies catching the light like a stained-glass window. The
camera dives into one die: streets of transistors, wires stacked in layers like floors of a building.

"Out comes a wafer tiled with identical chips, millions to billions of tiny switches in each."

The teal border fades: **leaving the simulator**.

## 8. Test every die (1:56–2:04)

A bed of fine needles lowers onto a die. Most light up green; one blinks red and gets a small dot.

"Not every die works. Needles finer than a hair put each one through a quick exam."

Caption: *the share that passes is the yield. This simulator leaves yield out.*

## 9. Thin and cut (2:04–2:12)

The wafer flips, is ground thinner, flips back. A laser line runs along the streets between dies; the grid gently
separates like a chocolate bar breaking.

"Cut along the narrow streets between them, each die is finally on its own."

## 10. Package (2:12–2:20)

One die settles onto a green board square; hair-thin gold wires arc from its edges; a black lid closes over it.

"A bare die is tiny and fragile, so it gets a home that links it to the world."

## 11. Final test and ship (2:20–2:30)

Chips line up on a tray, a light sweeps over them and they sort into three bins by speed. One chip lifts out, flies
into a phone, and the phone's screen wakes up. The camera pulls back to the beach from the cold open.

"Tested, sorted and shipped. The journey that began on a beach ends in your pocket."

End card: **Fab Gym** · *The fab's part runs on the SMT2020 model, a published research model of a wafer fab. The steps
before and after it are general knowledge.*

---

## What has to be agreed

The look, how the film is delivered, the voice and any music, and the Three.js download (see the quiz). Then, in
order: a storyboard of stills for each scene, the scenes built one at a time, a full cut, then any voice.
