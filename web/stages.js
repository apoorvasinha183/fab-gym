// What each hall does to the silicon (docs/STAGES.md). From the SMT2020 testbed, a published set of a fab's tool groups, routes and times;
// not a real fab. The model holds steps, tools and times, not chemistry: the drawings are generic textbook
// steps of our own, not to scale, and every number shown beside them comes from the page's data.
// In the page this defines window.FabStages; under Node, module.exports.
(function (root) {
  "use strict";

  const STAGES = [
    { key: "diff", name: "Diffusion", short: "Diffusion", areas: ["Diffusion"], hall: "Diffusion", color: "#e07b4f",
      mats: ["si", "ox"],
      what: "Dozens of wafers bake together in a glowing furnace. Oxygen sinks into the silicon and grows a skin of glass a few hundred atoms thick, or atoms planted earlier settle deeper.",
      why: "That glass is an insulator and a shield. The heat also heals the silicon after implant has shot it full of atoms.",
      note: "The furnaces take several lots at once as one batch, so a lot may wait for the batch to fill." },
    { key: "diel", name: "Dielectric", short: "Dielectric", areas: ["Dielectric"], hall: "Dielectric", color: "#8fc46a",
      mats: ["si", "ox", "film"],
      what: "Gases meet on the hot wafer and react, raining down an even blanket of insulating film over everything (chemical vapour deposition).",
      why: "Without insulation, every wire would short into its neighbour. The film is also the canvas the next pattern is carved into.",
      note: "Most of these steps sit in the repeating block near the end of the route, one round per wiring layer." },
    { key: "litho", name: "Lithography", short: "Lithography", areas: ["Litho"], hall: "Lithography", color: "#f2c94c",
      mats: ["si", "ox", "film", "resist"],
      what: "The wafer is coated with a light-sensitive resist. Ultraviolet light shines through a mask, like a slide in a projector, and where it lands the resist washes away.",
      why: "This is where the shapes of the chip are drawn: every later step acts only where the resist is open. The bays glow yellow because ordinary white light would expose the resist.",
      note: "Coating and developing (the track) and exposure (the scanner) are separate steps on separate tool groups." },
    { key: "dry", name: "Dry etch", short: "Dry etch", areas: ["Dry_Etch"], hall: "Dry etch", color: "#d46ab0",
      mats: ["si", "ox", "film", "resist"],
      what: "A plasma, a gas so energised it glows, is fired straight down at the wafer. Where the resist is open, it eats into the film.",
      why: "It turns the printed pattern into real trenches and holes with walls straight as cliffs.",
      note: "This area has more tool groups than any other." },
    { key: "imp", name: "Implant", short: "Implant", areas: ["Implant"], hall: "Implant", color: "#a98be8",
      mats: ["si", "dope", "ox", "film", "resist"],
      what: "A particle accelerator fires atoms such as boron or phosphorus at the wafer. The resist catches them; where it is open they bury themselves in the silicon.",
      why: "Those planted atoms decide where the silicon conducts. That is what turns plain silicon into transistors, the switches of the chip.",
      note: "Most implant steps come in the first half of the route, while the transistors are being built." },
    { key: "wet", name: "Wet etch and clean", short: "Wet etch", areas: ["Wet_Etch"], hall: "Wet etch", color: "#5fb0d9",
      mats: ["si", "dope", "ox", "film"],
      what: "Chemical baths strip away used resist and thin layers, then ultra-pure water rinses off every loose particle.",
      why: "Every step leaves something behind, and one speck of dust can kill a chip. So the wafer gets washed again and again, more than almost anything else in the fab.",
      note: "No area is visited more often." },
    { key: "tf", name: "Thin film (metal)", short: "Thin film", areas: ["TF"], hall: "Thin film", color: "#d9a95a",
      mats: ["si", "dope", "ox", "film", "metal"],
      what: "Atoms are knocked off a metal target and fly onto the wafer, coating it and filling the trenches (physical vapour deposition).",
      why: "That metal becomes the wiring: kilometres of it, folded into a chip, joining billions of transistors.",
      note: "Most of these steps sit in the repeating block near the end of the route, one round per wiring layer." },
    { key: "cmp", name: "Polishing (CMP)", short: "Polishing", areas: ["Planar"], hall: "Polishing", color: "#9aa7b5",
      mats: ["si", "dope", "ox", "film", "metal"],
      what: "A spinning pad and a gritty slurry sand the top flat. The extra metal comes off and only the metal inside the trenches stays.",
      why: "The next layer needs a flat floor to stand on, and the wires must end up separate from each other.",
      note: "Few steps and few tool groups, so one slow polishing group can hold up the whole fab." },
    { key: "chk", name: "Checks", short: "Checks", areas: ["Litho_Met", "Def_Met", "TF_Met"], hall: "Checks", color: "#6fd1c0",
      mats: ["si", "dope", "ox", "film", "metal"],
      what: "Tools measure how thick each film is, check that a layer lines up with the one below, and count defects. They look; they never touch.",
      why: "A mistake caught now is cheap. Caught twenty layers later, it has wasted weeks of work.",
      note: "Three areas of the model (litho checks, defect checks, film checks) share one hall on the floor." },
    { key: "hold", name: "Holding", short: "Holding", areas: ["Delay_32"], hall: "Holding", color: "#8a8172",
      mats: [],
      what: "The lot rests for a set time between certain steps, with no tool involved.",
      why: "Some steps need the wafer to settle before the next one can begin.",
      note: "The model holds these waits as one group with room for every lot." },
  ];

  const LOOP = ["diff", "diel", "litho", "dry", "imp", "wet", "tf", "cmp"];

  const MATERIALS = {
    si: ["#6f7a88", "silicon"], ox: ["#a9d7e6", "oxide (glass)"], film: ["#8fbf73", "insulating film"],
    resist: ["#d4664f", "photoresist"], metal: ["#d9a25a", "metal"], dope: ["#7e64ad", "doped silicon"],
  };

  const BY = {};
  const OF_AREA = {};
  for (const s of STAGES) {
    BY[s.key] = s;
    for (const a of s.areas) OF_AREA[a] = s.key;
  }
  const stageOfArea = a => OF_AREA[a];
  const byKey = k => BY[k];

  function zero() {
    const o = {};
    for (const s of STAGES) o[s.key] = 0;
    return o;
  }
  function visits(steps, areaOf) {
    const o = zero();
    for (const g of steps) o[stageOfArea(areaOf[g])]++;
    return o;
  }
  function groupsPerStage(areaOf) {
    const o = zero();
    for (const g of Object.keys(areaOf)) o[stageOfArea(areaOf[g])]++;
    return o;
  }
  function strip(steps, areaOf) {
    return steps.map((g, i) => ({ i, group: g, area: areaOf[g], stage: stageOfArea(areaOf[g]) }));
  }

  // ------------------------------------------------------------------ the drawings (240 x 150)
  // One story: oxide, film, resist patterned, trench cut, silicon doped, resist stripped, metal laid,
  // polished flat, measured. Silicon below y 104, oxide 96-104, film 80-96, resist 66-80, opening x 100-140.
  function crossSection(key, id) {
    const st = BY[key];
    if (!st || key === "hold") return null;
    const p = id || "xs";
    const W = 240;
    const R = (x, y, w, h, f, o = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${f}" ${o}/>`;
    const L = (x1, y1, x2, y2, c, o = "") => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" ${o}/>`;
    const T = (x, y, s, a = "start", c = "#f1e6cf") =>
      `<text x="${x}" y="${y}" text-anchor="${a}" fill="${c}" font-family="ui-monospace, Menlo, monospace" font-size="8">${s}</text>`;
    const arrow = (n, c) => `<marker id="${p}-${n}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`;
    const SI = `url(#${p}-si)`, DOPE = `url(#${p}-dope)`;
    const M = { ox: MATERIALS.ox[0], film: MATERIALS.film[0], resist: MATERIALS.resist[0], metal: MATERIALS.metal[0] };
    const si = d => R(0, 104, W, 46, SI) + (d ? `<rect x="98" y="104" width="44" height="18" rx="7" fill="${DOPE}"/>` : "");
    const band = (y, h, f, gap) => (gap ? R(0, y, 100, h, f) + R(140, y, 100, h, f) : R(0, y, W, h, f));
    const ox = g => band(96, 8, M.ox, g);
    const film = g => band(80, 16, M.film, g);
    const resist = () => band(66, 14, M.resist, true);
    const trenchMetal = () => R(100, 80, 40, 24, M.metal);
    let defs = `<pattern id="${p}-si" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#6f7a88"/>` +
      `<circle cx="2" cy="2" r="0.9" fill="#8893a1"/><circle cx="6" cy="6" r="0.9" fill="#8893a1"/></pattern>`;
    if (st.mats.includes("dope")) defs += `<pattern id="${p}-dope" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#7e64ad"/><circle cx="3" cy="3" r="1.2" fill="#d7c4ff"/></pattern>`;
    let s = "";
    if (key === "diff") {
      defs += `<linearGradient id="${p}-heat" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e07b4f" stop-opacity="0"/><stop offset="1" stop-color="#e07b4f" stop-opacity=".45"/></linearGradient>` + arrow("a", "#cfe9f2");
      s += R(0, 0, W, 96, `url(#${p}-heat)`);
      for (const x of [30, 90, 150, 210]) s += `<path d="M${x} 18 q6 6 0 12 q-6 6 0 12 q6 6 0 12" fill="none" stroke="#e07b4f" stroke-width="2" opacity=".8"/>`;
      for (const [x, y] of [[58, 64], [120, 54], [182, 70]])
        s += `<circle cx="${x}" cy="${y}" r="3" fill="#cfe9f2"/><circle cx="${x + 5}" cy="${y}" r="3" fill="#cfe9f2"/>` +
          L(x + 2.5, y + 6, x + 2.5, y + 20, "#cfe9f2", `stroke-width="1.2" marker-end="url(#${p}-a)"`);
      s += si(false) + ox(false) + T(6, 12, "hot furnace", "start", "#e8a07a") + T(234, 92, "oxide grows", "end");
    } else if (key === "diel") {
      defs += arrow("a", "#a6d98a");
      for (const [x, y] of [[40, 30], [96, 18], [150, 40], [200, 22], [70, 52], [176, 60]]) {
        s += `<circle cx="${x}" cy="${y}" r="2.6" fill="#a6d98a"/><circle cx="${x + 4}" cy="${y - 3}" r="1.8" fill="#dfe9d5"/><circle cx="${x + 4}" cy="${y + 3}" r="1.8" fill="#dfe9d5"/>`;
        s += L(x + 1, y + 7, x + 1, Math.min(y + 18, 76), "#a6d98a", `stroke-width="1.2" marker-end="url(#${p}-a)"`);
      }
      s += si(false) + ox(false) + film(false) + T(6, 12, "gas reacts on the surface", "start", "#bfe0ad") + T(234, 74, "film builds up", "end");
    } else if (key === "litho") {
      defs += arrow("a", "#c9a8ff");
      s += si(false) + ox(false) + film(false) + resist();
      for (let x = 14; x <= 226; x += 12) s += L(x, 2, x, 13, "#c9a8ff", 'stroke-width="1.4" opacity=".7"');
      s += R(0, 14, 100, 8, "#1a1c22", 'stroke="#9aa3ad" stroke-width="1"') + R(140, 14, 100, 8, "#1a1c22", 'stroke="#9aa3ad" stroke-width="1"');
      for (let x = 106; x <= 134; x += 7) s += L(x, 23, x, 63, "#c9a8ff", `stroke-width="1.6" marker-end="url(#${p}-a)"`);
      s += T(6, 34, "mask", "start", "#cbd2da") + T(234, 34, "UV light", "end", "#c9a8ff") + T(6, 62, "resist", "start", "#f0a08f") + T(120, 76, "open", "middle");
    } else if (key === "dry") {
      defs += `<radialGradient id="${p}-plasma" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#ff7ab8" stop-opacity=".85"/><stop offset="1" stop-color="#ff7ab8" stop-opacity="0"/></radialGradient>` + arrow("a", "#ff7ab8");
      s += `<ellipse cx="120" cy="24" rx="112" ry="20" fill="url(#${p}-plasma)"/>`;
      s += si(false) + ox(true) + film(true) + resist();
      for (let x = 106; x <= 134; x += 7) s += L(x, 40, x, 100, "#ff7ab8", `stroke-width="1.6" marker-end="url(#${p}-a)"`);
      for (const x of [30, 60, 180, 210]) s += L(x, 40, x, 62, "#ff7ab8", `stroke-width="1.4" opacity=".55" marker-end="url(#${p}-a)"`);
      s += T(6, 12, "plasma", "start", "#ff9fcb") + T(234, 62, "resist shields", "end", "#f0a08f") + T(120, 146, "trench cut through the film", "middle");
    } else if (key === "imp") {
      s += si(true) + ox(true) + film(true) + resist();
      for (const x of [24, 54, 84, 156, 186, 216]) s += L(x, 30, x, 62, "#e8d27a", 'stroke-width="1" opacity=".55"') + `<circle cx="${x}" cy="63" r="1.8" fill="#f4e7a5"/>`;
      for (const x of [106, 113, 120, 127, 134]) s += L(x, 30, x, 106, "#e8d27a", 'stroke-width="1"') + `<circle cx="${x}" cy="108" r="2" fill="#f4e7a5"/>`;
      s += T(6, 20, "dopant ions", "start", "#f4e7a5") + T(234, 62, "stopped in resist", "end", "#f0a08f") + T(120, 140, "doped pocket", "middle", "#e3d6ff");
    } else if (key === "wet") {
      s += R(0, 40, W, 64, "#5fb0d9", 'opacity=".35"') + `<path d="M0 40 q15 -5 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0" fill="none" stroke="#8fd0ee" stroke-width="1.5"/>`;
      for (const [x, y, r] of [[40, 54, 3], [72, 66, 2], [160, 50, 2.5], [196, 64, 3.5], [118, 58, 2]])
        s += `<circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="#cfe9f2" stroke-width="1"/>`;
      s += si(true) + ox(true) + film(true) + T(6, 30, "bath: resist and dirt dissolve", "start", "#8fd0ee");
    } else if (key === "tf") {
      defs += arrow("a", "#e8b46a");
      s += R(10, 4, 220, 10, "#9a7440", 'stroke="#d9a25a" stroke-width="1"');
      for (const [x, y, dx] of [[30, 26, 6], [64, 40, -4], [96, 22, 3], [128, 44, -2], [160, 28, 5], [196, 38, -5], [214, 22, 2]])
        s += `<circle cx="${x}" cy="${y}" r="2.2" fill="#f0c890"/>` + L(x + dx * 0.2, y + 4, x + dx, y + 16, "#e8b46a", `stroke-width="1.1" marker-end="url(#${p}-a)"`);
      s += si(true) + ox(true) + film(true) + band(66, 14, M.metal, false) + trenchMetal();
      s += T(234, 24, "metal target", "end", "#f0c890") + T(6, 62, "metal coats all", "start", "#f0c890");
    } else if (key === "cmp") {
      defs += arrow("a", "#b6a98f");
      s += `<path d="M60 30 A60 12 0 0 1 180 30" fill="none" stroke="#b6a98f" stroke-width="1.5" marker-end="url(#${p}-a)"/>`;
      s += R(8, 48, 224, 20, "#4a4f57", 'rx="3" stroke="#6d737c"');
      for (const x of [20, 44, 70, 96, 150, 176, 204, 226]) s += `<circle cx="${x}" cy="74" r="1.6" fill="#d9d2c2"/>`;
      s += si(true) + ox(true) + film(true) + trenchMetal();
      s += T(120, 61, "spinning pad", "middle", "#dfe3e8") + T(6, 140, "flat top, metal only in the trench", "start");
    } else if (key === "chk") {
      s += si(true) + ox(true) + film(true) + trenchMetal();
      s += R(14, 8, 34, 16, "#3a4048", 'rx="2" stroke="#6fd1c0"') + R(192, 8, 34, 16, "#3a4048", 'rx="2" stroke="#6fd1c0"');
      s += L(36, 24, 120, 79, "#6fd1c0", 'stroke-width="1.5"') + L(120, 79, 204, 24, "#6fd1c0", 'stroke-width="1.5" stroke-dasharray="3 2"');
      s += L(232, 80, 232, 96, "#f1e6cf") + L(228, 80, 236, 80, "#f1e6cf") + L(228, 96, 236, 96, "#f1e6cf");
      s += T(31, 36, "light in", "middle", "#9fe5d8") + T(209, 36, "reading", "middle", "#9fe5d8") + T(226, 92, "thickness", "end") + T(6, 140, "measured, not changed", "start");
    }
    return `<svg viewBox="0 0 ${W} 150" role="img" aria-label="Cross-section, illustration: ${st.name}"><defs>${defs}</defs>${s}</svg>`;
  }

  // ---------------------------------------------------------------- the whole journey, sand to chip
  // Only the fab's part is in the simulator (SMT2020 holds steps, tools and times). The steps before and after it are
  // general knowledge, told plainly, with typical figures; none is a particular company's.
  const JOURNEY = [
    { key: "sand", act: "before", name: "Sand", inModel: false,
      what: "Look at a beach. Most of those grains are quartz: silicon locked to oxygen. Your phone's brain starts right here. Heat the sand with carbon in a furnace hotter than lava, the carbon steals the oxygen, and grey silicon is left behind.",
      facts: ["That silicon is about 99% pure. Good enough for solar panels and steel. For a chip, it is filthy."] },
    { key: "purify", act: "before", name: "Purify", inModel: false,
      what: "For a chip, 99% is hopeless. So the silicon is turned into a gas, distilled again and again, and frozen back into solid rods. Every pass strips out more of the stray atoms.",
      facts: ["Chip-grade silicon is about 99.9999999% pure. Picture a billion marbles with one of the wrong colour."] },
    { key: "crystal", act: "before", name: "Grow a crystal", inModel: false,
      what: "Now the atoms have to line up. The pure silicon is melted, a pencil-thin seed crystal touches the surface, and it is pulled up slowly while it spins. Atom by atom the melt freezes onto the seed in perfect order: one giant crystal.",
      facts: ["Silicon melts at about 1,414 °C.", "The finished ingot is about 30 cm wide and roughly as long as a person is tall."] },
    { key: "slice", act: "before", name: "Slice and polish", inModel: false,
      what: "A wire coated in diamond saws the ingot into discs thinner than a coin. Each is ground and polished until it shines like a mirror, then sealed in a box, because at this scale a speck of dust is a boulder.",
      facts: ["A 300 mm wafer is about 0.78 mm thick."] },
    { key: "arrive", act: "fab", name: "Into the fab", inModel: true,
      what: "The bare wafers enter the fab in lots of 25, riding the overhead track in sealed boxes. From this moment on, the simulator follows every one of them.",
      facts: ["In SMT2020 a lot is 25 wafers; prototype lots are 1 to 10.", "Urgent lots, called hot lots, jump every queue."] },
    { key: "loop", act: "fab", name: "Layer by layer", inModel: true,
      what: "Here is the trick: a chip is built like a city, one floor at a time. For every layer the wafer gets a thin film, a pattern printed with light, an etch that carves it, a dose of atoms, a wash and a check. Then the loop begins again.",
      facts: ["Product 3 goes round it on a route of 583 steps across 105 groups of tools.", "From the SMT2020 testbed a regular lot spends about 66 days in the fab. Most of that time it is waiting in line."] },
    { key: "done", act: "fab", name: "A finished wafer", inModel: true,
      what: "Out comes a wafer tiled with identical chips, called dies, still joined together. Zoom into one and you would find millions to billions of tiny switches, wired together in stacked layers like the floors of a building.",
      facts: ["How many dies fit depends on their size: tens of large ones, or thousands of small ones.", "In the simulator, a lot is done when it finishes its last step."] },
    { key: "probe", act: "after", name: "Test every die", inModel: false,
      what: "Not every die works. Needles finer than a hair touch each one and put it through a quick electrical exam. The ones that fail are marked, so nobody wastes a package on them.",
      facts: ["The share that passes is called the yield. This simulator leaves yield out."] },
    { key: "dice", act: "after", name: "Thin and cut", inModel: false,
      what: "The wafer is ground thinner from the back, then cut along the narrow streets between the dies by a saw or a laser. Each die is finally on its own, and smaller than a fingernail.",
      facts: ["Those gaps between dies really are called streets."] },
    { key: "package", act: "after", name: "Package", inModel: false,
      what: "A bare die is tiny and fragile, so it gets a home: a package that shields it and links its microscopic pads to a circuit board, through fine wires or little balls of solder.",
      facts: ["The package is the black or metal-lidded square you see on a board."] },
    { key: "ship", act: "after", name: "Final test and ship", inModel: false,
      what: "One last exam. Each chip is tested again and sorted by how fast and how cool it runs. Then it ships to the makers of phones, cars and laptops, and the journey that began on a beach ends in your pocket.",
      facts: ["Chips cut from the same wafer can be sold as different models. The sorting is called binning."] },
  ];

  // a small drawing for each step: our own shapes, 160 × 100, one type family
  function journeyPicture(key) {
    const j = JOURNEY.find((x) => x.key === key);
    if (!j) return "";
    const ink = "#CFE3E0", soft = "#5F7F88", si = "#8893a1", accent = "#7EE8D8", warm = "#FFB347";
    const R = (x, y, w, h, f, o = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${f}" ${o}/>`;
    let g = "";
    if (key === "sand") {
      for (let i = 0; i < 60; i++) { const x = 20 + ((i * 37) % 120), y = 60 + ((i * 53) % 30); g += `<circle cx="${x}" cy="${y}" r="${1.5 + (i % 3) * 0.6}" fill="${i % 4 ? "#d8c39a" : "#b89f74"}"/>`; }
      g += `<path d="M20 90 Q80 40 140 90 Z" fill="#c9b285" opacity="0.35"/>`;
    } else if (key === "purify") {
      g += `<path d="M62 20 h36 v22 l22 44 a6 6 0 0 1 -5 8 h-70 a6 6 0 0 1 -5 -8 l22 -44 z" fill="none" stroke="${ink}" stroke-width="2"/>`;
      g += `<path d="M47 70 l-4 10 a5 5 0 0 0 5 6 h64 a5 5 0 0 0 5 -6 l-4 -10 z" fill="${si}"/>`;
      for (const [x, y] of [[74, 30], [86, 22], [80, 12]]) g += `<circle cx="${x}" cy="${y}" r="3" fill="${accent}" opacity="0.7"/>`;
    } else if (key === "crystal") {
      g += R(78, 4, 4, 30, ink) + `<rect x="60" y="34" width="40" height="40" rx="6" fill="${si}"/>`;
      g += `<path d="M40 88 h80 l-8 -12 h-64 z" fill="${warm}" opacity="0.8"/><path d="M44 80 q36 -8 72 0" fill="none" stroke="#ffd29a" stroke-width="2"/>`;
      g += `<path d="M110 30 a18 18 0 0 1 0 22" fill="none" stroke="${accent}" stroke-width="2"/><path d="M110 52 l-4 -6 l7 0 z" fill="${accent}"/>`;
    } else if (key === "slice") {
      g += `<rect x="14" y="36" width="64" height="30" rx="15" fill="${si}"/>`;
      for (let i = 0; i < 4; i++) g += `<ellipse cx="${96 + i * 14}" cy="51" rx="5" ry="16" fill="#aab4c0" stroke="${ink}" stroke-width="1"/>`;
      g += `<line x1="84" y1="20" x2="84" y2="82" stroke="${accent}" stroke-width="1.5" stroke-dasharray="3 3"/>`;
    } else if (key === "arrive") {
      g += `<rect x="40" y="24" width="80" height="62" rx="8" fill="none" stroke="${ink}" stroke-width="2"/>`;
      for (let i = 0; i < 6; i++) g += R(48, 32 + i * 8, 64, 3, "#aab4c0");
      g += `<path d="M126 55 h22 m-6 -6 l6 6 l-6 6" fill="none" stroke="${accent}" stroke-width="2"/>`;
    } else if (key === "loop") {
      g += `<circle cx="80" cy="50" r="34" fill="none" stroke="${soft}" stroke-width="6"/>`;
      g += `<path d="M80 16 a34 34 0 0 1 34 34" fill="none" stroke="${accent}" stroke-width="6"/><path d="M114 50 l-7 -9 l12 0 z" fill="${accent}"/>`;
      g += `<circle cx="80" cy="50" r="14" fill="${si}"/>`;
    } else if (key === "done") {
      g += `<circle cx="80" cy="50" r="40" fill="#3f4d5a" stroke="${ink}" stroke-width="1.5"/>`;
      for (let x = 46; x < 114; x += 9) for (let y = 16; y < 84; y += 9) if (Math.hypot(x + 3.5 - 80, y + 3.5 - 50) < 36) g += R(x, y, 7, 7, accent, 'opacity="0.75"');
    } else if (key === "probe") {
      g += `<circle cx="80" cy="66" r="30" fill="#3f4d5a"/>`;
      for (let x = 58; x < 102; x += 9) for (let y = 48; y < 84; y += 9) if (Math.hypot(x + 3.5 - 80, y + 3.5 - 66) < 26) g += R(x, y, 7, 7, x === 76 && y === 57 ? "#FF6262" : accent, 'opacity="0.75"');
      for (const x of [70, 80, 90]) g += `<line x1="${x}" y1="8" x2="${x}" y2="44" stroke="${ink}" stroke-width="1.5"/>`;
      g += R(62, 4, 36, 8, soft);
    } else if (key === "dice") {
      for (let i = 0; i < 3; i++) for (let k = 0; k < 3; k++) g += R(44 + i * 26 + (i === 2 && k === 0 ? 10 : 0), 18 + k * 24 - (i === 2 && k === 0 ? 8 : 0), 20, 18, accent, 'opacity="0.75"');
      g += `<line x1="38" y1="40" x2="122" y2="40" stroke="${warm}" stroke-width="1.5" stroke-dasharray="4 3"/>`;
    } else if (key === "package") {
      g += `<rect x="46" y="26" width="68" height="48" rx="5" fill="#1c2628" stroke="${ink}" stroke-width="1.5"/>`;
      g += R(68, 40, 24, 20, accent, 'opacity="0.8"');
      for (let i = 0; i < 6; i++) { g += R(50 + i * 11, 74, 4, 10, ink) + R(50 + i * 11, 16, 4, 10, ink); }
    } else if (key === "ship") {
      g += `<rect x="40" y="30" width="56" height="40" rx="5" fill="#1c2628" stroke="${ink}" stroke-width="1.5"/>`;
      g += R(58, 42, 20, 16, accent, 'opacity="0.8"');
      g += `<circle cx="118" cy="40" r="14" fill="#4FE3A3" opacity="0.9"/><path d="M111 40 l5 5 l9 -10" fill="none" stroke="#0B1418" stroke-width="3"/>`;
      g += `<path d="M100 78 h40" stroke="${soft}" stroke-width="2"/>`;
    }
    return `<svg viewBox="0 0 160 100" role="img" aria-label="${j.name}" xmlns="http://www.w3.org/2000/svg">${g}</svg>`;
  }

  const api = { STAGES, LOOP, MATERIALS, stageOfArea, byKey, visits, groupsPerStage, strip, crossSection, JOURNEY, journeyPicture };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.FabStages = api;
})(typeof window !== "undefined" ? window : this);
