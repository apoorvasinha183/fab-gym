// Builds the storyboard page for the chip film from the script and the journey's own drawings.
const S = require(process.argv[2]);
const fs = require("fs");
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const QUARRY = `<svg class="art" viewBox="0 0 160 100" role="img" aria-label="A quartz quarry"><path d="M0 70 L30 52 L60 60 L90 44 L120 54 L160 40 L160 100 L0 100Z" fill="#8a8f98"/><path d="M10 78 h140 M20 86 h120" stroke="#c9ccd2" stroke-width="2"/><rect x="96" y="58" width="30" height="12" rx="2" fill="#ffb347"/><circle cx="102" cy="72" r="4" fill="#222"/><circle cx="120" cy="72" r="4" fill="#222"/><path d="M60 62 l-14 -14 l-10 8" stroke="#ffb347" stroke-width="4" fill="none"/><circle cx="34" cy="58" r="4" fill="#f4f4f4"/><circle cx="40" cy="60" r="3" fill="#e9e9e9"/></svg>`;
const STILLS = fs.existsSync(require("path").join(__dirname, "stills")) ? Object.fromEntries(fs.readdirSync(require("path").join(__dirname, "stills")).filter((f) => f.endsWith(".jpg")).map((f) => [Number(f.slice(0, 2)), f])) : {};
const pic = (k) => S.journeyPicture(k).replace("<svg ", '<svg class="art" ');
const grain = `<svg class="art" viewBox="0 0 160 100" role="img" aria-label="A grain of sand"><defs><radialGradient id="g0" cx="40%" cy="35%" r="60%"><stop offset="0" stop-color="#f3dfb4"/><stop offset="1" stop-color="#9c7f52"/></radialGradient></defs><path d="M80 18 C108 16 126 38 120 60 C114 82 88 88 66 82 C44 76 34 54 44 36 C52 24 64 19 80 18 Z" fill="url(#g0)"/>${Array.from({length: 24}, (_, i) => { const x = 58 + (i % 6) * 9, y = 36 + Math.floor(i / 6) * 9; return `<circle cx="${x}" cy="${y}" r="1.6" fill="#7EE8D8" opacity="${0.35 + (i % 3) * 0.2}"/>`; }).join("")}</svg>`;
const scenes = [
  { n: 0, t: "0:00", d: 8, act: "open", title: "Cold open", art: grain,
    see: "Black. A single grain of sand drifts in, lit from one side, slowly turning. The camera pushes in until the grain fills the screen and its surface turns out to be a lattice of glowing points.",
    say: "This is a grain of sand. By the end of this film, it will be thinking.", cap: "Title: From Sand to Chip", cam: "slow push-in", fx: "a powers-of-ten scale bar runs from 1 mm down to atoms as the camera pushes in" },
  { n: 1, t: "0:08", d: 14, act: "before", title: "The quarry", art: QUARRY,
    see: "Dawn over an open-pit quartz quarry cut into stepped terraces. An excavator scoops white rock into a haul truck; the truck rolls to a crusher that turns the rock into gravel on a conveyor. A callout pops out of one pebble: a molecule, one silicon between two oxygens, labelled SiO₂.",
    say: "A beach is mostly quartz, but chips start from something cleaner: quartz rock, dug out of the ground. It is silicon locked to oxygen.", cap: "quartz = SiO₂, silicon dioxide", cam: "wide drone shot, then follow the truck", fx: "molecule pop-out with leader line; flow arrows along the conveyor" },
  { n: 2, t: "0:22", d: 12, act: "before", title: "Smelt", art: pic("sand"),
    see: "The gravel pours into an arc furnace glowing white-orange, with carbon in the mix. Cutaway: red oxygen atoms peel off grey silicon and fly away with black carbon as little puffs. Grey silicon pours out and cools.",
    say: "Heat it with carbon, hotter than lava, and the carbon steals the oxygen. Grey silicon is left behind.", cap: "about 99% pure. For a chip, that is filthy.", cam: "push into the furnace, then the atom cutaway", fx: "atom cutaway inset; temperature callout" },
  { n: 3, t: "0:34", d: 12, act: "before", title: "Purify", art: pic("purify"),
    see: "The grey lump dissolves into a swirling gas inside a glass column. Coloured specks of impurity are filtered out at each pass while a meter counts up: 99% → 99.99% → 99.9999999%.",
    say: "So the silicon becomes a gas, is distilled again and again, and freezes back into solid rods.", cap: "one stray atom in a billion.", cam: "slow rise up the column", fx: "a purity counter climbs to 99.9999999%; a grid of a billion marbles with one wrong colour" },
  { n: 4, t: "0:46", d: 16, act: "before", title: "Grow a crystal", art: pic("crystal"),
    see: "A crucible of molten silicon glows white-orange. A thin seed on a rod dips in, then rises slowly while turning. Close up, atoms snap into a perfect grid as they leave the melt. Pull back: a silver ingot as tall as the small human figure beside it.",
    say: "Now the atoms have to line up. A seed crystal touches the melt and is pulled up slowly while it spins. Atom by atom, the melt freezes onto it in perfect order: one giant crystal.", cap: "silicon melts at about 1,414 °C.", cam: "macro on the growth front, then a crane up", fx: "a human figure for scale beside the ingot; a temperature dial at 1,414 °C" },
  { n: 5, t: "1:02", d: 12, act: "before", title: "Slice and polish", art: pic("slice"),
    see: "The ingot lies on its side. A taut wire glints through it and discs fall away in sequence. One disc tilts to the camera and is polished until it mirrors the scene, then slides into a sealed box with 24 others.",
    say: "A diamond wire slices it into discs thinner than a coin, polished until they shine like mirrors.", cap: "at this scale, a speck of dust is a boulder.", cam: "track along the ingot", fx: "split screen: a speck of dust beside a transistor, drawn to the same scale" },
  { n: 6, t: "1:14", d: 10, act: "fab", title: "Into the fab", art: pic("arrive"),
    see: "The box rides an overhead track into a dark building with teal light seams, the same diorama the floor page draws. At the door: SMT2020 model · simulated. From here a teal border frames the picture.",
    say: "The wafers enter the fab in lots of 25. From this moment on, the simulator follows every one of them.", cap: "SMT2020 model · simulated", cam: "follow the box through the door", fx: "a teal frame and the tag SMT2020 · simulated stay on screen until the wafer leaves" },
  { n: 7, t: "1:24", d: 36, act: "fab", title: "Layer by layer", art: pic("loop"),
    see: "One wafer, close up, goes round the loop, a two-second vignette per stage: film settles as a mist; UV light through a mask in a yellow room; a violet plasma carves trenches; a beam of atoms buries itself; a sheet of water sweeps it clean; a scanning line and a green tick. Lap two at double speed, then a time-lapse of floors stacking like a building, with a counter running to 583.",
    say: "Here is the trick: a chip is built like a city, one floor at a time. A film, a pattern printed with light, an etch, a dose of atoms, a wash, a check. Then the loop begins again.", cap: "583 steps on 105 groups of tools. A regular lot spends about 66 days here, most of it waiting in line.", cam: "orbit the wafer, faster each lap", fx: "each stage named by a callout as it happens; a step counter running to 583; a lap counter" },
  { n: 8, t: "2:00", d: 10, act: "fab", title: "A finished wafer", art: pic("done"),
    see: "The wafer rises and turns to face us, a mosaic of identical dies catching the light like stained glass. The camera dives into one die: streets of transistors and wires stacked in layers. The teal border fades: leaving the simulator.",
    say: "Out comes a wafer tiled with identical chips, millions to billions of tiny switches in each.", cap: "leaving the simulator", cam: "reveal, then a dive into one die", fx: "a powers-of-ten zoom from the wafer into one die; a label with its transistor count" },
  { n: 9, t: "2:10", d: 8, act: "after", title: "Test every die", art: pic("probe"),
    see: "A bed of fine needles lowers onto a die. Most dies light up green; one blinks red and gets a small dot.",
    say: "Not every die works. Needles finer than a hair put each one through a quick exam.", cap: "the share that passes is the yield. This simulator leaves yield out.", cam: "top-down", fx: "a pass and fail tally; a yield gauge marked not modelled" },
  { n: 10, t: "2:18", d: 8, act: "after", title: "Thin and cut", art: pic("dice"),
    see: "The wafer flips, is ground thinner, flips back. A laser line runs along the streets between dies; the grid gently separates like a chocolate bar breaking.",
    say: "Cut along the narrow streets between them, each die is finally on its own.", cap: "", cam: "low angle across the wafer", fx: "the gaps between dies labelled streets" },
  { n: 11, t: "2:26", d: 8, act: "after", title: "Package", art: pic("package"),
    see: "One die settles onto a green board square; hair-thin gold wires arc from its edges; a black lid closes over it.",
    say: "A bare die is tiny and fragile, so it gets a home that links it to the world.", cap: "", cam: "close three-quarter view", fx: "an exploded view: die, wires and lid, each labelled" },
  { n: 12, t: "2:34", d: 10, act: "after", title: "Final test and ship", art: pic("ship"),
    see: "Chips line up on a tray; a light sweeps over them and they sort into three bins by speed. One chip lifts out, flies into a phone, and the phone's screen wakes up. Pull back to the beach from the cold open.",
    say: "Tested, sorted and shipped. The journey that began on a beach ends in your pocket.", cap: "End card: Fab Gym · the fab's part runs on the SMT2020 model; the rest is general knowledge.", cam: "follow the chip, then a wide pull-back", fx: "a small chart of chips sorted into three bins by speed" },
];
const ACT = { open: "Opening", before: "Before the fab", fab: "In the fab · simulated", after: "After the fab" };
const total = scenes.reduce((a, s) => a + s.d, 0);
const bar = scenes.map((s) => `<a class="seg ${s.act}" href="#scene-${s.n}" style="flex:${s.d}" title="${esc(s.title)} · ${s.d} s"><span>${s.n}</span></a>`).join("");
const cards = scenes.map((s) => `
<article class="scene ${s.act}" id="scene-${s.n}">
  <div class="frame">${STILLS[s.n] ? `<img src="stills/${STILLS[s.n]}" alt="${esc(s.title)}: a still from the scene" loading="lazy">` : s.art}<span class="tc">${s.t}</span>${s.act === "fab" ? '<span class="sim">SMT2020 · simulated</span>' : ""}</div>
  <div class="body">
    <div class="meta"><span class="no">Scene ${s.n}</span><span class="act">${ACT[s.act]}</span><span class="dur">${s.d} s</span></div>
    <h3>${esc(s.title)}</h3>
    <p class="see">${esc(s.see)}</p>
    <blockquote>${esc(s.say)}</blockquote>
    ${s.cap ? `<p class="cap"><span>On screen</span>${esc(s.cap)}</p>` : ""}
    <p class="cam"><span>Camera</span>${esc(s.cam)}</p>
    ${s.fx ? `<p class="cam"><span>Explainer</span>${esc(s.fx)}</p>` : ""}
  </div>
</article>`).join("");
const choices = [
  { q: "Look", opts: [
    { name: "Explainer, flat-shaded", rec: true, note: "Clean low-poly shapes, soft gradients, bold colours on dark, simple light. Readable and warm; light enough to run in a browser.", sw: ["#1d2a4a", "#ff9a52", "#7ee8d8", "#f3dfb4"] },
    { name: "Match the floor page", note: "The Fab Gym night palette with glowing teal seams, so the film and the page feel like one product.", sw: ["#0b1418", "#12262d", "#7ee8d8", "#4fe3a3"] },
    { name: "Semi-real", note: "Physically based materials, reflections and depth of field. Strongest stills; heaviest to build and to play.", sw: ["#202428", "#8893a1", "#d8dde3", "#ffb347"] },
    { name: "Blueprint", note: "Line drawings on deep blue that assemble from outlines. Very clear, less emotional.", sw: ["#0d2a52", "#2e5d9a", "#cfe3ff", "#ffffff"] } ] },
  { q: "Delivery", opts: [
    { name: "In the page, plus an MP4", rec: true, note: "Plays inside How a chip is made with play, pause and one chapter per journey step; the same scenes rendered frame by frame to a video file for sharing." },
    { name: "In the page only", note: "Live, with play, pause and chapters; no video file." },
    { name: "Video file only", note: "A rendered MP4; nothing interactive." } ] },
  { q: "Sound", opts: [
    { name: "Captions now, voice later", rec: true, note: "On-screen lines first. Once the picture is agreed, the script is voiced with Chatterbox on the Mac mini, as before. No music yet." },
    { name: "Captions only", note: "A silent film with captions." },
    { name: "Voice and music now", note: "Chatterbox voice plus a music bed; the music would be a download, asked about first." } ] },
  { q: "Three.js", opts: [
    { name: "Vendor it from npm", rec: true, note: "three@0.169.0 (MIT), the module build only, about 0.7 MB, stored in the repo with its licence. A download, so it waits for your yes." },
    { name: "Load it from a CDN", note: "Nothing stored; the film needs the internet to play." },
    { name: "Not yet", note: "Stop at the script and a storyboard; no code." } ] },
];
const choiceHtml = choices.map((c) => `<section class="choice"><h3>${c.q}</h3><div class="opts">${c.opts.map((o) => `<div class="opt${o.rec ? " rec" : ""}">${o.rec ? '<span class="badge">Recommended</span>' : ""}<h4>${esc(o.name)}</h4>${o.sw ? `<div class="sw">${o.sw.map((x) => `<i style="background:${x}"></i>`).join("")}</div>` : ""}<p>${esc(o.note)}</p></div>`).join("")}</div></section>`).join("");
const tpl = fs.readFileSync(process.argv[3], "utf8");
fs.writeFileSync(process.argv[4], tpl.replace("{{BAR}}", bar).replace("{{SCENES}}", cards).replace("{{CHOICES}}", choiceHtml).replaceAll("{{TOTAL}}", `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`));
console.log("scenes", scenes.length, "total", total, "s");
// the script as markdown, for the repo (docs/CHIP-FILM.md)
if (process.argv[5]) {
  const md = [`# From Sand to Chip: a short film in Three.js`, ``,
    `Script draft 2, 29 October 2026. Direction agreed by the founder the same day: a semi-real look with explainer-style animation (a mining scene added), delivered as one MP4, with voice (Chatterbox on the Mac mini) and music (The Budding of Consciousness by Yoiyami, crossfading into New Sunrise by nene; both CC0 from OpenGameArt). The fab's part runs on the SMT2020 model; the steps before and after it are general knowledge and say so on screen. No real fab, company or product is shown.`, ``,
    `Running time ${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}, ${scenes.length} scenes.`, ``];
  for (const s of scenes) {
    md.push(`## ${s.n}. ${s.title} (${s.t}, ${s.d} s) · ${ACT[s.act]}`, ``, s.see, ``, `> ${s.say}`, ``);
    if (s.cap) md.push(`On screen: *${s.cap}*`, ``);
    md.push(`Camera: ${s.cam}.`, ``);
    if (s.fx) md.push(`Explainer: ${s.fx}.`, ``);
  }
  md.push(`## Then, in order`, ``, `1. Storyboard stills, one per scene in the agreed look, for a second sign-off.`, `2. Scenes built one at a time, starting with Layer by layer.`, `3. A full cut with captions, rendered to MP4.`, `4. Voice and music laid in and mixed to the picture.`, ``);
  fs.writeFileSync(process.argv[5], md.join("\n"));
}
if (process.env.DUMP) fs.writeFileSync(process.env.DUMP, JSON.stringify(scenes.map(({ art, ...s }) => s), null, 1));
