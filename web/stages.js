// What each hall does to the silicon (docs/STAGES.md). On the SMT2020 model, a published model of a fab;
// not a real fab. The model holds steps, tools and times, not chemistry: the drawings are generic textbook
// steps of our own, not to scale, and every number shown beside them comes from the page's data.
// In the page this defines window.FabStages; under Node, module.exports.
(function (root) {
  "use strict";

  const STAGES = [
    { key: "diff", name: "Diffusion", short: "Diffusion", areas: ["Diffusion"], hall: "Diffusion", color: "#e07b4f",
      mats: ["si", "ox"],
      what: "A furnace heats a batch of wafers. Oxygen grows a thin skin of glass (oxide) into the silicon, or dopants already put in settle deeper.",
      why: "The oxide insulates and protects the silicon, and the heat heals the damage implant leaves behind.",
      note: "The furnaces take several lots at once as one batch, so a lot may wait for the batch to fill." },
    { key: "diel", name: "Dielectric", short: "Dielectric", areas: ["Dielectric"], hall: "Dielectric", color: "#8fc46a",
      mats: ["si", "ox", "film"],
      what: "Gases react on the hot wafer and lay an insulating film over everything (chemical vapour deposition).",
      why: "Insulators keep wires and transistors apart, and the film is what the next pattern is cut into.",
      note: "Most of these steps sit in the repeating block near the end of the route, one round per wiring layer." },
    { key: "litho", name: "Lithography", short: "Lithography", areas: ["Litho"], hall: "Lithography", color: "#f2c94c",
      mats: ["si", "ox", "film", "resist"],
      what: "The wafer is coated with light-sensitive resist, light shines through a mask, and the lit resist is washed away.",
      why: "It draws the pattern: every later step acts only where the resist is open. The bays use yellow light so the resist is not exposed by accident.",
      note: "Coating and developing (the track) and exposure (the scanner) are separate steps on separate tool groups." },
    { key: "dry", name: "Dry etch", short: "Dry etch", areas: ["Dry_Etch"], hall: "Dry etch", color: "#d46ab0",
      mats: ["si", "ox", "film", "resist"],
      what: "A plasma of charged gas fires straight down and cuts the film where the resist is open.",
      why: "It carves the drawn pattern into the wafer as trenches and holes with straight walls.",
      note: "This area has more tool groups than any other." },
    { key: "imp", name: "Implant", short: "Implant", areas: ["Implant"], hall: "Implant", color: "#a98be8",
      mats: ["si", "dope", "ox", "film", "resist"],
      what: "An accelerator fires dopant ions at the wafer. They stop in the resist and enter the silicon only where it is open.",
      why: "Dopants set where the silicon conducts and how well. This is how the transistors are made.",
      note: "Most implant steps come in the first half of the route, while the transistors are being built." },
    { key: "wet", name: "Wet etch and clean", short: "Wet etch", areas: ["Wet_Etch"], hall: "Wet etch", color: "#5fb0d9",
      mats: ["si", "dope", "ox", "film"],
      what: "Chemical baths dissolve used resist and thin layers, then rinse away particles.",
      why: "Every step leaves something behind and one speck can ruin a chip, so the wafer is cleaned again and again.",
      note: "No area is visited more often." },
    { key: "tf", name: "Thin film (metal)", short: "Thin film", areas: ["TF"], hall: "Thin film", color: "#d9a95a",
      mats: ["si", "dope", "ox", "film", "metal"],
      what: "Metal atoms knocked off a target land on the wafer and coat it, filling the trenches (physical vapour deposition).",
      why: "Metal makes the wires that join the transistors.",
      note: "Most of these steps sit in the repeating block near the end of the route, one round per wiring layer." },
    { key: "cmp", name: "Polishing (CMP)", short: "Polishing", areas: ["Planar"], hall: "Polishing", color: "#9aa7b5",
      mats: ["si", "dope", "ox", "film", "metal"],
      what: "A spinning pad and a slurry grind the top flat. The extra metal comes off and metal stays only in the trenches.",
      why: "The next layer needs a flat floor, and the wires must be separate from each other.",
      note: "Few steps and few tool groups, so one slow polishing group can hold up the whole fab." },
    { key: "chk", name: "Checks", short: "Checks", areas: ["Litho_Met", "Def_Met", "TF_Met"], hall: "Checks", color: "#6fd1c0",
      mats: ["si", "dope", "ox", "film", "metal"],
      what: "Tools measure film thickness, how well a layer lines up with the one below, and count defects. The wafer is not changed.",
      why: "A bad step is caught before more work is spent on the wafer.",
      note: "Three areas of the model (litho checks, defect checks, film checks) share one hall on the floor." },
    { key: "hold", name: "Holding", short: "Holding", areas: ["Delay_32"], hall: "Holding", color: "#8a8172",
      mats: [],
      what: "The lot waits a set time between some steps, with no tool.",
      why: "Some steps need the wafer to rest before the next one.",
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

  const api = { STAGES, LOOP, MATERIALS, stageOfArea, byKey, visits, groupsPerStage, strip, crossSection };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.FabStages = api;
})(typeof window !== "undefined" ? window : this);
