// From Sand to Chip (docs/CHIP-FILM.md): the scene list the film plays, generated from the agreed script draft 2.
// The fab's part runs from the SMT2020 testbed; the rest is general knowledge, labelled so on screen.
// In the page this defines window.FilmScript; under Node, module.exports.
(function (root) {
  "use strict";
  const SCENES = [
 {
  "key": "open",
  "title": "Cold open",
  "act": "open",
  "d": 8,
  "say": "This is a grain of sand. By the end of this film, it will be thinking.",
  "cap": "Title: From Sand to Chip",
  "see": "Black. A single grain of sand drifts in, lit from one side, slowly turning. The camera pushes in until the grain fills the screen and its surface turns out to be a lattice of glowing points.",
  "cam": "slow push-in",
  "still": 5,
  "fx": [
   {
    "kind": "scale",
    "from": "1 mm",
    "to": "0.3 nm"
   }
  ],
  "simulated": false
 },
 {
  "key": "quarry",
  "title": "The quarry",
  "act": "before",
  "d": 14,
  "say": "A beach is mostly quartz, but chips start from something cleaner: quartz rock, dug out of the ground. It is silicon locked to oxygen.",
  "cap": "quartz = SiO₂, silicon dioxide",
  "see": "Dawn over an open-pit quartz quarry cut into stepped terraces. An excavator scoops white rock into a haul truck; the truck rolls to a crusher that turns the rock into gravel on a conveyor. A callout pops out of one pebble: a molecule, one silicon between two oxygens, labelled SiO₂.",
  "cam": "wide drone shot, then follow the truck",
  "still": 8,
  "fx": [
   {
    "kind": "callout",
    "text": "quartz = SiO₂",
    "sub": "one silicon, two oxygen"
   },
   {
    "kind": "arrows",
    "text": "crushed to gravel"
   }
  ],
  "simulated": false
 },
 {
  "key": "smelt",
  "title": "Smelt",
  "act": "before",
  "d": 12,
  "say": "Heat it with carbon, hotter than lava, and the carbon steals the oxygen. Grey silicon is left behind.",
  "cap": "about 99% pure. For a chip, that is filthy.",
  "see": "The gravel pours into an arc furnace glowing white-orange, with carbon in the mix. Cutaway: red oxygen atoms peel off grey silicon and fly away with black carbon as little puffs. Grey silicon pours out and cools.",
  "cam": "push into the furnace, then the atom cutaway",
  "still": 7,
  "fx": [
   {
    "kind": "callout",
    "text": "about 2,000 °C",
    "sub": "inside the arc furnace"
   },
   {
    "kind": "inset",
    "text": "carbon takes the oxygen"
   }
  ],
  "simulated": false
 },
 {
  "key": "purify",
  "title": "Purify",
  "act": "before",
  "d": 12,
  "say": "So the silicon becomes a gas, is distilled again and again, and freezes back into solid rods.",
  "cap": "one stray atom in a billion.",
  "see": "The grey lump dissolves into a swirling gas inside a glass column. Coloured specks of impurity are filtered out at each pass while a meter counts up: 99% → 99.99% → 99.9999999%.",
  "cam": "slow rise up the column",
  "still": 7,
  "fx": [
   {
    "kind": "counter",
    "text": "purity",
    "values": [
     "99%",
     "99.99%",
     "99.9999%",
     "99.9999999%"
    ]
   }
  ],
  "simulated": false
 },
 {
  "key": "crystal",
  "title": "Grow a crystal",
  "act": "before",
  "d": 16,
  "say": "Now the atoms have to line up. A seed crystal touches the melt and is pulled up slowly while it spins. Atom by atom, the melt freezes onto it in perfect order: one giant crystal.",
  "cap": "silicon melts at about 1,414 °C.",
  "see": "A crucible of molten silicon glows white-orange. A thin seed on a rod dips in, then rises slowly while turning. Close up, atoms snap into a perfect grid as they leave the melt. Pull back: a silver ingot as tall as the small human figure beside it.",
  "cam": "macro on the growth front, then a crane up",
  "still": 11,
  "fx": [
   {
    "kind": "dial",
    "text": "silicon melts at about 1,414 °C"
   },
   {
    "kind": "scale",
    "text": "about the height of a person"
   }
  ],
  "simulated": false
 },
 {
  "key": "slice",
  "title": "Slice and polish",
  "act": "before",
  "d": 12,
  "say": "A diamond wire slices it into discs thinner than a coin, polished until they shine like mirrors.",
  "cap": "at this scale, a speck of dust is a boulder.",
  "see": "The ingot lies on its side. A taut wire glints through it and discs fall away in sequence. One disc tilts to the camera and is polished until it mirrors the scene, then slides into a sealed box with 24 others.",
  "cam": "track along the ingot",
  "still": 7,
  "fx": [
   {
    "kind": "callout",
    "text": "about 0.78 mm thick",
    "sub": "thinner than a coin"
   },
   {
    "kind": "split",
    "text": "a speck of dust is a boulder"
   }
  ],
  "simulated": false
 },
 {
  "key": "arrive",
  "title": "Into the fab",
  "act": "fab",
  "d": 10,
  "say": "The wafers enter the fab in lots of 25. From this moment on, the simulator follows every one of them.",
  "cap": "SMT2020 testbed · simulated",
  "see": "The box rides an overhead track into a dark building with teal light seams, the same diorama the floor page draws. At the door: SMT2020 testbed · simulated. From here a teal border frames the picture.",
  "cam": "follow the box through the door",
  "still": 6,
  "fx": [
   {
    "kind": "frame",
    "text": "SMT2020 testbed · simulated"
   },
   {
    "kind": "callout",
    "text": "a lot: 25 wafers"
   }
  ],
  "simulated": true
 },
 {
  "key": "loop",
  "title": "Layer by layer",
  "act": "fab",
  "d": 36,
  "say": "Here is the trick: a chip is built like a city, one floor at a time. A film, a pattern printed with light, an etch, a dose of atoms, a wash, a check. Then the loop begins again.",
  "cap": "583 steps on 105 groups of tools. A regular lot spends about 66 days here, most of it waiting in line.",
  "see": "One wafer, close up, goes round the loop, a two-second vignette per stage: film settles as a mist; UV light through a mask in a yellow room; a violet plasma carves trenches; a beam of atoms buries itself; a sheet of water sweeps it clean; a scanning line and a green tick. Lap two at double speed, then a time-lapse of floors stacking like a building, with a counter running to 583.",
  "cam": "orbit the wafer, faster each lap",
  "still": 14,
  "fx": [
   {
    "kind": "stage",
    "values": [
     "thin film",
     "print with light",
     "etch",
     "implant",
     "wash",
     "check"
    ]
   },
   {
    "kind": "counter",
    "text": "step",
    "values": [
     "1",
     "583"
    ]
   }
  ],
  "simulated": true
 },
 {
  "key": "done",
  "title": "A finished wafer",
  "act": "fab",
  "d": 10,
  "say": "Out comes a wafer tiled with identical chips, millions to billions of tiny switches in each.",
  "cap": "leaving the simulator",
  "see": "The wafer rises and turns to face us, a mosaic of identical dies catching the light like stained glass. The camera dives into one die: streets of transistors and wires stacked in layers. The teal border fades: leaving the simulator.",
  "cam": "reveal, then a dive into one die",
  "still": 6,
  "fx": [
   {
    "kind": "scale",
    "from": "30 cm",
    "to": "10 nm"
   },
   {
    "kind": "callout",
    "text": "one die",
    "sub": "millions to billions of switches"
   }
  ],
  "simulated": true
 },
 {
  "key": "probe",
  "title": "Test every die",
  "act": "after",
  "d": 8,
  "say": "Not every die works. Needles finer than a hair put each one through a quick exam.",
  "cap": "the share that passes is the yield. This simulator leaves yield out.",
  "see": "A bed of fine needles lowers onto a die. Most dies light up green; one blinks red and gets a small dot.",
  "cam": "top-down",
  "still": 5,
  "fx": [
   {
    "kind": "tally",
    "text": "pass / fail"
   },
   {
    "kind": "gauge",
    "text": "yield (not modelled)"
   }
  ],
  "simulated": false
 },
 {
  "key": "dice",
  "title": "Thin and cut",
  "act": "after",
  "d": 8,
  "say": "Cut along the narrow streets between them, each die is finally on its own.",
  "cap": "",
  "see": "The wafer flips, is ground thinner, flips back. A laser line runs along the streets between dies; the grid gently separates like a chocolate bar breaking.",
  "cam": "low angle across the wafer",
  "still": 5,
  "fx": [
   {
    "kind": "callout",
    "text": "the streets between dies"
   }
  ],
  "simulated": false
 },
 {
  "key": "package",
  "title": "Package",
  "act": "after",
  "d": 8,
  "say": "A bare die is tiny and fragile, so it gets a home that links it to the world.",
  "cap": "",
  "see": "One die settles onto a green board square; hair-thin gold wires arc from its edges; a black lid closes over it.",
  "cam": "close three-quarter view",
  "still": 5,
  "fx": [
   {
    "kind": "exploded",
    "values": [
     "lid",
     "wires",
     "die",
     "board"
    ]
   }
  ],
  "simulated": false
 },
 {
  "key": "ship",
  "title": "Final test and ship",
  "act": "after",
  "d": 10,
  "say": "Tested, sorted and shipped. The journey that began on a beach ends in your pocket.",
  "cap": "End card: Fab Gym · the fab's part runs from the SMT2020 testbed; the rest is general knowledge.",
  "see": "Chips line up on a tray; a light sweeps over them and they sort into three bins by speed. One chip lifts out, flies into a phone, and the phone's screen wakes up. Pull back to the beach from the cold open.",
  "cam": "follow the chip, then a wide pull-back",
  "still": 4,
  "fx": [
   {
    "kind": "bins",
    "values": [
     "fastest",
     "fast",
     "standard"
    ]
   }
  ],
  "simulated": false
 }
];
  // music: The Budding of Consciousness (Yoiyami, CC0) until the fab, crossfading into New Sunrise (nene, CC0)
  const MUSIC = [
    { file: "budding/the_budding_of_consciousness.wav", start: 0, end: 77, from: 0, fadeOut: 4 },
    { file: "new-sunrise/new_sunrise_V2.wav", start: 73, end: 164, from: 0, fadeIn: 4, fadeOut: 3 },
  ];
  const total = () => SCENES.reduce((a, s) => a + s.d, 0);
  const startOf = (key) => { let t = 0; for (const s of SCENES) { if (s.key === key) return t; t += s.d; } return -1; };
  // the scene and the time inside it at film time T
  const at = (T) => { let t = 0; for (const s of SCENES) { if (T < t + s.d) return { scene: s, t: T - t }; t += s.d; } const s = SCENES[SCENES.length - 1]; return { scene: s, t: s.d }; };
  // how dark a frame is at time t of scene s: through black at each cut (0.45 s each way), clear between
  const FADE = 0.45;
  const fade = (s, t) => Math.max(0, Math.min(1, Math.max(1 - t / FADE, 1 - (s.d - t) / FADE)));
  const api = { SCENES, MUSIC, total, startOf, at, fade, FADE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FilmScript = api;
})(typeof window !== "undefined" ? window : globalThis);
