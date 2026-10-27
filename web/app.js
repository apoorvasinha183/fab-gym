// Fab Gym floor: the simulator (Rust, compiled to WebAssembly) runs in the page, and the floor
// plays its run back. Units of the layout are tiles; a tool is 3 x 3 tiles.
"use strict";

const AREA_NAMES = {
  Litho: "Lithography", Litho_Met: "Litho checks", Def_Met: "Defect checks", TF_Met: "Film checks",
  Implant: "Implant", Diffusion: "Diffusion", Dielectric: "Dielectric", Wet_Etch: "Wet etch",
  TF: "Thin film", Dry_Etch: "Dry etch", Planar: "Polishing", Delay_32: "Holding",
};
// one hall an area, except the three check areas, which share one hall
const HALLS = [
  ["Lithography", ["Litho"]],
  ["Checks", ["Litho_Met", "Def_Met", "TF_Met"]],
  ["Implant", ["Implant"]],
  ["Diffusion", ["Diffusion"]],
  ["Dielectric", ["Dielectric"]],
  ["Wet etch", ["Wet_Etch"]],
  ["Thin film", ["TF"]],
  ["Dry etch", ["Dry_Etch"]],
  ["Polishing", ["Planar"]],
  ["Holding", ["Delay_32"]],
];
// checked for colour-blind viewers (Machado 2009): the closest two filled states stay at least
// 20 apart in CIE Lab for normal, protan, deutan and tritan vision; each is at least 3:1 against
// the hall floor. Idle tools are drawn as outlines and broken ones carry a cross, so state never
// rests on colour alone.
const STATE_COLORS = ["#7fcfa8", "#7a8592", "#7a8ce6", "#cf4f4a", "#e8bb4e"];
const STATE_NAMES = ["working", "idle", "maintenance", "broken down", "changing setup"];
const LOT = "#efe2c4", HOT = "#e8955a";
const TOOL = 3, PITCH = 4;
let TARGET_ASPECT = 1.8;

// ------------------------------------------------------------------ the simulator

const sim = { e: null, groups: [], tools: [], routes: [], lots: [] };

async function loadSim() {
  const [wasm, shopText, areasText] = await Promise.all([
    fetch("fabweb.wasm").then(r => r.arrayBuffer()),
    fetch("data/shop.txt").then(r => r.text()),
    fetch("data/areas.tsv").then(r => r.text()),
  ]);
  const { instance } = await WebAssembly.instantiate(wasm, {});
  sim.e = instance.exports;
  const bytes = new TextEncoder().encode(shopText);
  const p = sim.e.fg_alloc(bytes.length);
  new Uint8Array(sim.e.memory.buffer, p, bytes.length).set(bytes);
  if (sim.e.fg_load(p, bytes.length) !== 0) throw new Error(readJson().error);
  sim.area = {};
  for (const line of areasText.split("\n")) {
    const [g, a] = line.split("\t");
    if (g) sim.area[g] = a;
  }
}

function readJson() {
  const e = sim.e;
  const b = new Uint8Array(e.memory.buffer, e.fg_json_ptr(), e.fg_json_len());
  return JSON.parse(new TextDecoder().decode(b));
}

function simulate(opts) {
  const e = sim.e;
  const d = opts.dials || DEFAULT_DIALS;
  if (e.fg_dials(d.breakdowns, d.repair, d.demand, d.hot, d.rework, d.cap || 0) !== 0) throw new Error(readJson().error);
  const t0 = performance.now();
  const rc = e.fg_run(opts.seed, opts.days, opts.rule, opts.downGroup, opts.downAt * 60, opts.downHours);
  const secs = (performance.now() - t0) / 1000;
  if (rc !== 0) throw new Error("the simulator did not run");
  const j = readJson();
  const trace = new Float64Array(e.memory.buffer, e.fg_trace_ptr(), e.fg_trace_len()).slice();
  const states = new Float64Array(e.memory.buffer, e.fg_states_ptr(), e.fg_states_len()).slice();
  return { j, trace, states, secs };
}

// ------------------------------------------------------------------ the layout

function plainGroup(name, area) {
  const m = name.match(/(\d+)$/);
  const base = AREA_NAMES[area] || area;
  return m ? `${base} ${m[1]}` : base;
}

function groupBlock(n) {
  const cols = n <= 3 ? n : Math.ceil(Math.sqrt(n * 1.8));
  const rows = Math.ceil(n / cols);
  const w = Math.max(cols * PITCH + 1, 12);
  return { cols, rows, w, h: rows * PITCH + 1 + 3 + 3 }; // machines, label, queue belt
}

function buildLayout(groups) {
  // halls of groups
  const hallOfArea = {};
  HALLS.forEach(([h, areas], i) => areas.forEach(a => (hallOfArea[a] = i)));
  const halls = HALLS.map(([name, areas]) => ({ name, areas, groups: [] }));
  groups.forEach((g, gi) => {
    const a = sim.area[g.name];
    const hi = hallOfArea[a];
    if (hi === undefined) throw new Error("no hall for area " + a);
    halls[hi].groups.push(gi);
  });
  // pack each hall: shelves of group blocks, a section label where the area changes
  for (const h of halls) {
    const holding = h.areas[0] === "Delay_32";
    const blocks = h.groups.map(gi => (holding ? { cols: 0, rows: 0, w: 30, h: 9 } : groupBlock(groups[gi].count)));
    const area = blocks.reduce((s, b) => s + (b.w + 3) * (b.h + 3), 0);
    const W = Math.max(...blocks.map(b => b.w), Math.sqrt(area * 2.4));
    let x = 0, y = 5, shelf = 0, width = 0, lastArea = null;
    h.cells = [];
    h.groups.forEach((gi, k) => {
      const b = blocks[k];
      const a = sim.area[groups[gi].name];
      const newSection = h.areas.length > 1 && a !== lastArea;
      if (newSection && k > 0) { x = 0; y += shelf + 3; shelf = 0; }
      if (newSection) { h.cells.push({ label: AREA_NAMES[a], x: 0, y }); y += 3; }
      lastArea = a;
      if (x > 0 && x + b.w > W) { x = 0; y += shelf + 3; shelf = 0; }
      h.cells.push({ gi, x, y, ...b, holding });
      x += b.w + 3;
      width = Math.max(width, x - 3);
      shelf = Math.max(shelf, b.h);
    });
    h.w = Math.ceil(width + 6);
    h.h = Math.ceil(y + shelf + 4);
  }
  return halls;
}

// lots moving between halls, per hour, from the routes (each product starts at the same rate)
function hallFlows(halls, routes) {
  const hallOfGroup = {};
  halls.forEach((h, i) => h.groups.forEach(g => (hallOfGroup[g] = i)));
  const f = new Map();
  for (const [, steps] of routes) {
    for (let k = 1; k < steps.length; k++) {
      const a = hallOfGroup[steps[k - 1]], b = hallOfGroup[steps[k]];
      if (a === b) continue;
      const key = a * 100 + b;
      f.set(key, (f.get(key) || 0) + 1);
    }
  }
  return { f, hallOfGroup };
}

// four rows of halls around a clockwise spine: above the top run, below it, above the bottom run,
// below the bottom run. A seeded local search places the halls so lots' trips are short.
function placeHalls(halls, flows) {
  const n = halls.length;
  let rnd = 12345;
  const rand = () => ((rnd = (rnd * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  const GAP = 6, MARGIN = 10;
  function geometry(rows) {
    const widths = rows.map(r => r.reduce((s, h) => s + halls[h].w, 0) + GAP * Math.max(0, r.length - 1));
    const L = Math.max(...widths) + 2 * MARGIN;
    const hRow = rows.map(r => Math.max(0, ...r.map(h => halls[h].h)));
    const yTop = hRow[0] + 4;
    const yBot = yTop + 3 + hRow[1] + 6 + hRow[2] + 3;
    const pos = new Array(n);
    rows.forEach((r, ri) => {
      const total = widths[ri];
      let x = (L - total) / 2;
      for (const h of r) {
        const H = halls[h];
        let y;
        if (ri === 0) y = yTop - 3 - H.h;
        else if (ri === 1) y = yTop + 3;
        else if (ri === 2) y = yBot - 3 - H.h;
        else y = yBot + 3;
        const door = { x: x + H.w / 2, y: ri === 0 || ri === 2 ? y + H.h : y };
        const belt = ri <= 1 ? "top" : "bot";
        pos[h] = { x, y, row: ri, door, belt };
        x += H.w + GAP;
      }
    });
    const Hgt = yBot - yTop;
    const ring = 2 * L + 2 * Hgt;
    const s = h => (pos[h].belt === "top" ? pos[h].door.x : L + Hgt + (L - pos[h].door.x));
    return { L, yTop, yBot, Hgt, ring, pos, s, bottom: yBot + 3 + hRow[3] + 4 };
  }
  function cost(rows) {
    const g = geometry(rows);
    let c = 0;
    for (const [key, v] of flows.f) {
      const a = Math.floor(key / 100), b = key % 100;
      let d = g.s(b) - g.s(a);
      if (d < 0) d += g.ring;
      c += v * d;
    }
    // a compact fab that has the shape of the screen reads better
    const aspect = g.L / g.bottom;
    return c + 40 * (g.L + g.bottom) + 4e5 * Math.abs(Math.log(aspect / TARGET_ASPECT));
  }
  // start: halls by size, dealt round the rows
  const order = [...Array(n).keys()].sort((a, b) => halls[b].w * halls[b].h - halls[a].w * halls[a].h);
  let rows = [[], [], [], []];
  order.forEach((h, i) => rows[i % 4].push(h));
  let best = cost(rows), bestRows = rows.map(r => r.slice());
  let cur = best;
  for (let it = 0; it < 20000; it++) {
    const cand = rows.map(r => r.slice());
    const r1 = Math.floor(rand() * 4), r2 = Math.floor(rand() * 4);
    if (!cand[r1].length) continue;
    const i1 = Math.floor(rand() * cand[r1].length);
    if (rand() < 0.5 && cand[r2].length) {
      const i2 = Math.floor(rand() * cand[r2].length);
      [cand[r1][i1], cand[r2][i2]] = [cand[r2][i2], cand[r1][i1]];
    } else {
      const [h] = cand[r1].splice(i1, 1);
      cand[r2].splice(Math.floor(rand() * (cand[r2].length + 1)), 0, h);
    }
    const c = cost(cand);
    const temp = 2000 * (1 - it / 20000) + 1;
    if (c < cur || rand() < Math.exp((cur - c) / temp)) {
      rows = cand; cur = c;
      if (c < best) { best = c; bestRows = cand.map(r => r.slice()); }
    }
  }
  return geometry(bestRows);
}

// ------------------------------------------------------------------ the run, prepared for playback

function prepare(run, halls, hallOfGroup) {
  const { j, trace, states } = run;
  const toolGroup = j.tools;
  const nT = toolGroup.length, nG = j.groups.length;
  const lotHot = j.lots.map(l => l[2] >= 20);
  // queue events (+1 at arrival, -1 at start), sorted by time, arrivals first at equal times
  const nRows = trace.length / 6;
  const qe = [];
  const byLot = new Map();
  for (let r = 0; r < nRows; r++) {
    const lot = trace[r * 6], tool = trace[r * 6 + 2], arrive = trace[r * 6 + 3], start = trace[r * 6 + 4], end = trace[r * 6 + 5];
    const g = toolGroup[tool];
    if (start > arrive) {
      qe.push([arrive, g, 1, lotHot[lot] ? 1 : 0]);
      qe.push([start, g, -1, lotHot[lot] ? 1 : 0]);
    }
    let a = byLot.get(lot);
    if (!a) byLot.set(lot, (a = []));
    a.push([start, g, arrive, end]);
  }
  qe.sort((x, y) => x[0] - y[0] || y[2] - x[2]);
  // trips between halls: from the end of one step to the arrival at the next
  const trips = [];
  for (const [lot, rows] of byLot) {
    rows.sort((x, y) => x[0] - y[0]);
    for (let k = 1; k < rows.length; k++) {
      const [, g0, , end0] = rows[k - 1];
      const [, g1, arrive1] = rows[k];
      if (arrive1 > end0) trips.push([end0, arrive1, hallOfGroup[g0], hallOfGroup[g1], lotHot[lot], lot]);
    }
  }
  trips.sort((x, y) => x[0] - y[0]);
  // moves (step starts) and finishes over time, for the counters
  const starts = [];
  for (let r = 0; r < nRows; r++) starts.push(trace[r * 6 + 4]);
  starts.sort((a, b) => a - b);
  const done = j.lots.map(l => l[5]).filter(x => x !== null).sort((a, b) => a - b);
  // lots waiting over time, every 20 minutes, for the timeline
  const waitSeries = [];
  let k = 0, w = 0;
  for (let t = 0; t <= j.until; t += 20) {
    while (k < qe.length && qe[k][0] <= t) { w += qe[k][2]; k++; }
    waitSeries.push(w);
  }
  return { j, trace, states, nT, nG, qe, trips, starts, done, waitSeries, toolGroup, secs: run.secs };
}

// playback cursor: state of every tool and queue at time t, moved forward cheaply
function makeCursor(P) {
  const c = { t: -1, si: 0, qi: 0, ti: 0, toolState: new Uint8Array(P.nT), queue: new Int32Array(P.nG), hotQ: new Int32Array(P.nG), active: [] };
  c.reset = () => {
    c.t = -1; c.si = 0; c.qi = 0; c.ti = 0; c.toolState.fill(1); c.queue.fill(0); c.hotQ.fill(0); c.active = [];
  };
  c.reset();
  c.seek = t => {
    if (t < c.t) c.reset();
    const S = P.states;
    while (c.si < S.length / 3 && S[c.si * 3 + 1] <= t) { c.toolState[S[c.si * 3]] = S[c.si * 3 + 2]; c.si++; }
    const Q = P.qe;
    while (c.qi < Q.length && Q[c.qi][0] <= t) { const q = Q[c.qi]; c.queue[q[1]] += q[2]; c.hotQ[q[1]] += q[2] * q[3]; c.qi++; }
    const T = P.trips;
    while (c.ti < T.length && T[c.ti][0] <= t) { c.active.push(T[c.ti]); c.ti++; }
    c.active = c.active.filter(tr => tr[1] > t);
    c.t = t;
  };
  return c;
}

function countBelow(sorted, t) {
  let lo = 0, hi = sorted.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] <= t) lo = m + 1; else hi = m; }
  return lo;
}

// ------------------------------------------------------------------ drawing

const cv = document.getElementById("floor");
const ctx = cv.getContext("2d");
const view = { x: 0, y: 0, s: 4 }; // screen = (world - view) * s
let G = null; // geometry
let HALLS_L = null;
let P = null, cur = null;
let t = 0, playing = true, speed = 60; // fab minutes per second
let hover = null;

function resize() {
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.round(innerWidth * dpr);
  cv.height = Math.round(innerHeight * dpr);
  const sp = document.getElementById("spark");
  sp.width = Math.round(sp.clientWidth * dpr);
  sp.height = Math.round(sp.clientHeight * dpr);
  drawSpark();
}

function fit() {
  if (!G) return;
  const pad = { l: innerWidth > 900 && !$("compare").hidden ? 372 : 24, r: innerWidth > 900 ? 330 : 24, t: 110, b: 80 };
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  const s = Math.min(w / G.L, h / G.bottom);
  view.s = s;
  view.x = -(pad.l + (w - G.L * s) / 2) / s;
  view.y = -(pad.t + (h - G.bottom * s) / 2) / s;
}

function ringPoint(s) {
  // the clockwise spine: top run eastward, east side down, bottom run westward, west side up
  const { L, yTop, yBot, Hgt, ring } = G;
  s = ((s % ring) + ring) % ring;
  if (s < L) return [s, yTop];
  if (s < L + Hgt) return [L, yTop + (s - L)];
  if (s < 2 * L + Hgt) return [L - (s - L - Hgt), yBot];
  return [0, yBot - (s - 2 * L - Hgt)];
}

function tripPoint(tr, now) {
  const a = G.pos[tr[2]], b = G.pos[tr[3]];
  const sa = G.s(tr[2]), sb = G.s(tr[3]);
  let d = sb - sa;
  if (d <= 0) d += G.ring;
  const fa = Math.abs(a.door.y - (a.belt === "top" ? G.yTop : G.yBot));
  const fb = Math.abs(b.door.y - (b.belt === "top" ? G.yTop : G.yBot));
  const total = fa + d + fb;
  let u = Math.min(1, Math.max(0, (now - tr[0]) / (tr[1] - tr[0]))) * total;
  if (u < fa) { const dir = a.belt === "top" ? (a.row === 0 ? 1 : -1) : (a.row === 2 ? 1 : -1); return [a.door.x, a.door.y + dir * u]; }
  u -= fa;
  if (u < d) return ringPoint(sa + u);
  u -= d;
  const by = b.belt === "top" ? G.yTop : G.yBot;
  const dir = b.door.y > by ? 1 : -1;
  return [b.door.x, by + dir * u];
}

function W(x, y) { return [(x - view.x) * view.s, (y - view.y) * view.s]; }

function rr(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// The look, in the spirit of Factorio and drawn here: concrete floors, yellow-railed belts with
// moving chevrons, machines as sprites with a state panel and a status light, lots as carrier boxes.
const LOOK = {
  ground: "#262420", hallFloor: "#3a3833", wall: "#6e695e", wallDark: "#1b1a17",
  rail: "#d9a12b", beltTop: "#2b2926", chevron: "rgba(140, 104, 34, 0.95)",
  body: "#5a564d", bodyEdge: "#1b1a17", plate: "rgba(22, 21, 18, 0.82)",
  title: "#f3e4c4", sub: "#bcae92", label: "#d6cbb4", section: "#e3a83a",
  lot: "#eadfc4", lotTop: "#b7a88a", hot: "#f08a3c", hotTop: "#b8602a",
};

function noiseTile(base, spread, lines, seed) {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = base;
  g.fillRect(0, 0, 64, 64);
  let r = seed;
  const rand = () => ((r = (r * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let i = 0; i < 900; i++) {
    const v = (rand() - 0.5) * spread;
    g.fillStyle = v > 0 ? `rgba(255,255,255,${v})` : `rgba(0,0,0,${-v})`;
    g.fillRect(Math.floor(rand() * 64), Math.floor(rand() * 64), 1 + Math.floor(rand() * 2), 1 + Math.floor(rand() * 2));
  }
  if (lines) {
    g.strokeStyle = lines;
    g.lineWidth = 1;
    g.strokeRect(0.5, 0.5, 63, 63);
    g.beginPath(); g.moveTo(32, 0); g.lineTo(32, 64); g.moveTo(0, 32); g.lineTo(64, 32); g.stroke();
  }
  return c;
}
const TILES = {};
function pattern(name) {
  if (!TILES[name]) {
    const src = name === "ground" ? noiseTile(LOOK.ground, 0.10, "rgba(0,0,0,0.22)", 7) : noiseTile(LOOK.hallFloor, 0.07, "rgba(0,0,0,0.18)", 11);
    TILES[name] = ctx.createPattern(src, "repeat");
  }
  // anchored to the world: one 64 px tile spans 4 floor tiles
  const p = TILES[name];
  p.setTransform(new DOMMatrix().translate(-view.x * view.s, -view.y * view.s).scale((view.s * 4) / 64));
  return p;
}

// machine sprites, cached by state and pixel size
const SPRITES = new Map();
function sprite(st, px) {
  const key = st * 1000 + px;
  let c = SPRITES.get(key);
  if (c) return c;
  if (SPRITES.size > 400) SPRITES.clear();
  c = document.createElement("canvas");
  c.width = c.height = px;
  const g = c.getContext("2d");
  const S = px;
  const R = (x, y, w, h, r) => { g.beginPath(); g.roundRect(x, y, w, h, r); };
  // body with a bevel
  R(S * 0.03, S * 0.03, S * 0.94, S * 0.94, S * 0.12);
  g.fillStyle = LOOK.body; g.fill();
  g.lineWidth = Math.max(1, S * 0.06); g.strokeStyle = LOOK.bodyEdge; g.stroke();
  g.strokeStyle = "rgba(255,255,255,0.14)"; g.lineWidth = Math.max(1, S * 0.04);
  g.beginPath(); g.moveTo(S * 0.12, S * 0.85); g.lineTo(S * 0.12, S * 0.12); g.lineTo(S * 0.85, S * 0.12); g.stroke();
  // the state panel
  const a = S * 0.2, w = S * 0.6;
  R(a, a, w, w, S * 0.08);
  if (st === 1) {
    g.fillStyle = "#2a2925"; g.fill();
    g.strokeStyle = STATE_COLORS[1]; g.lineWidth = Math.max(1, S * 0.07); g.stroke();
  } else {
    g.fillStyle = STATE_COLORS[st]; g.fill();
    g.strokeStyle = "rgba(0,0,0,0.45)"; g.fillStyle = "rgba(0,0,0,0.45)"; g.lineWidth = Math.max(1, S * 0.07);
    const m = S / 2;
    if (st === 0) { // a gear
      g.beginPath(); g.arc(m, m, S * 0.13, 0, 2 * Math.PI); g.stroke();
      for (let k = 0; k < 6; k++) {
        const an = (k * Math.PI) / 3;
        g.beginPath(); g.moveTo(m + Math.cos(an) * S * 0.16, m + Math.sin(an) * S * 0.16);
        g.lineTo(m + Math.cos(an) * S * 0.24, m + Math.sin(an) * S * 0.24); g.stroke();
      }
    } else if (st === 2) { // a pause: maintenance
      g.fillRect(m - S * 0.12, m - S * 0.14, S * 0.07, S * 0.28);
      g.fillRect(m + S * 0.05, m - S * 0.14, S * 0.07, S * 0.28);
    } else if (st === 3) { // a cross: broken down
      g.lineWidth = Math.max(1.2, S * 0.09); g.strokeStyle = "rgba(20,10,10,0.75)";
      g.beginPath(); g.moveTo(m - S * 0.15, m - S * 0.15); g.lineTo(m + S * 0.15, m + S * 0.15);
      g.moveTo(m + S * 0.15, m - S * 0.15); g.lineTo(m - S * 0.15, m + S * 0.15); g.stroke();
    } else if (st === 4) { // a turning arrow: changing setup
      g.beginPath(); g.arc(m, m, S * 0.14, 0.3, 1.6 * Math.PI); g.stroke();
      g.beginPath(); g.moveTo(m + S * 0.14, m - S * 0.02); g.lineTo(m + S * 0.2, m + S * 0.08); g.lineTo(m + S * 0.07, m + S * 0.07); g.fill();
    }
  }
  // status light
  g.beginPath(); g.arc(S * 0.84, S * 0.84, Math.max(1, S * 0.065), 0, 2 * Math.PI);
  g.fillStyle = st === 0 ? "#d6ffe6" : st === 3 ? "#ff8a80" : st === 1 ? "#3a3833" : "#ffe7a8";
  g.fill();
  SPRITES.set(key, c);
  return c;
}

function drawBelt(points, phase, chevrons = true, small = false) {
  const s = view.s;
  const m = small ? 0 : 1; // small belts scale with zoom only
  const pts = points.map(([x, y]) => W(x, y));
  const path = () => { ctx.beginPath(); pts.forEach(([X, Y], i) => (i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y))); };
  ctx.lineCap = "butt";
  ctx.lineJoin = "miter";
  path();
  ctx.strokeStyle = LOOK.wallDark; ctx.lineWidth = Math.max(10 * m, (small ? 2.0 : 2.7) * s); ctx.stroke();
  ctx.strokeStyle = LOOK.rail; ctx.lineWidth = Math.max(8 * m, (small ? 1.7 : 2.3) * s); ctx.stroke();
  ctx.strokeStyle = LOOK.beltTop; ctx.lineWidth = Math.max(5 * m, (small ? 1.25 : 1.7) * s); ctx.stroke();
  if (!chevrons) return;
  // chevrons pointing along the belt, moving with it
  const gap = Math.max(1.6, 9 / s); // world tiles between chevrons
  const half = Math.max(2, 0.55 * s);
  ctx.strokeStyle = LOOK.chevron;
  ctx.lineWidth = Math.max(1.3, 0.28 * s);
  ctx.beginPath();
  let carried = (phase * gap) % gap;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1], [x1, y1] = points[i];
    const len = Math.hypot(x1 - x0, y1 - y0);
    const dx = (x1 - x0) / len, dy = (y1 - y0) / len;
    for (let d = carried; d < len; d += gap) {
      const [X, Y] = W(x0 + dx * d, y0 + dy * d);
      ctx.moveTo(X - dx * half - dy * half, Y - dy * half + dx * half);
      ctx.lineTo(X, Y);
      ctx.lineTo(X - dx * half + dy * half, Y - dy * half - dx * half);
    }
    carried = (carried - len) % gap;
    if (carried < 0) carried += gap;
  }
  ctx.stroke();
}

function drawLot(X, Y, sz, hot) {
  ctx.fillStyle = LOOK.bodyEdge;
  ctx.fillRect(X - sz / 2 - 1, Y - sz / 2 - 1, sz + 2, sz + 2);
  ctx.fillStyle = hot ? LOOK.hot : LOOK.lot;
  ctx.fillRect(X - sz / 2, Y - sz / 2, sz, sz);
  ctx.fillStyle = hot ? LOOK.hotTop : LOOK.lotTop;
  ctx.fillRect(X - sz / 2, Y - sz / 2, sz, Math.max(1, sz * 0.3));
}

function plateText(text, X, Y, size, weight, color) {
  ctx.font = `${weight} ${size}px -apple-system, Inter, sans-serif`;
  const w = ctx.measureText(text).width;
  ctx.fillStyle = LOOK.plate;
  ctx.fillRect(X - size * 0.35, Y - size * 0.2, w + size * 0.7, size * 1.35);
  ctx.fillStyle = color;
  ctx.fillText(text, X, Y);
  return w;
}

function hazard(X, Y, w, h) {
  ctx.save();
  ctx.beginPath(); ctx.rect(X, Y, w, h); ctx.clip();
  ctx.fillStyle = "#d9a12b"; ctx.fillRect(X, Y, w, h);
  ctx.strokeStyle = "#1b1a17"; ctx.lineWidth = Math.max(1.5, h * 0.35);
  ctx.beginPath();
  for (let x = X - h * 2; x < X + w + h; x += h * 1.4) { ctx.moveTo(x, Y + h); ctx.lineTo(x + h, Y); }
  ctx.stroke();
  ctx.restore();
}

function draw() {
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = LOOK.ground;
  ctx.fillRect(0, 0, innerWidth, innerHeight);
  if (!G || !P) return;
  const s = view.s;
  ctx.fillStyle = pattern("ground");
  ctx.fillRect(0, 0, innerWidth, innerHeight);
  // belts: the spine and each hall's feeder
  const phase = (t * 0.35) % 1;
  HALLS_L.forEach((h, i) => {
    const p = G.pos[i];
    const by = p.belt === "top" ? G.yTop : G.yBot;
    drawBelt([[p.door.x, p.door.y], [p.door.x, by]], phase, false);
  });
  drawBelt([[0, G.yTop], [G.L, G.yTop], [G.L, G.yBot], [0, G.yBot], [0, G.yTop]], phase);
  // halls
  const showLabels = s > 2.6;
  HALLS_L.forEach((h, i) => {
    const p = G.pos[i];
    const [X, Y] = W(p.x, p.y);
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fillRect(X + 0.6 * s, Y + 0.8 * s, h.w * s, h.h * s); // shadow
    ctx.fillStyle = pattern("hall");
    ctx.fillRect(X, Y, h.w * s, h.h * s);
    ctx.strokeStyle = LOOK.wallDark; ctx.lineWidth = Math.max(3, 1.0 * s);
    ctx.strokeRect(X, Y, h.w * s, h.h * s);
    ctx.strokeStyle = LOOK.wall; ctx.lineWidth = Math.max(1.5, 0.6 * s);
    ctx.strokeRect(X, Y, h.w * s, h.h * s);
    // the door, hazard-striped
    const [DX, DY] = W(p.door.x - 2.5, p.door.y - 0.6);
    hazard(DX, DY, 5 * s, Math.max(3, 1.2 * s));
    // title on a plate
    ctx.textBaseline = "top";
    const tsz = Math.max(12, 2.6 * s);
    const tw = plateText(h.name, X + 1.6 * s, Y + 1.2 * s, tsz, 700, LOOK.title);
    const toolsN = h.groups.reduce((a, g) => a + P.j.groups[g][1], 0);
    if (h.w * s > tw + 80) {
      const ssz = Math.max(11, 1.5 * s);
      const label = h.areas[0] === "Delay_32" ? "between steps" : `${toolsN} tools`;
      plateText(label, X + 1.6 * s + tw + tsz * 0.7 + 4, Y + 1.2 * s + (tsz - ssz) * 0.7, ssz, 500, LOOK.sub);
    }
    for (const c of h.cells) {
      const cx = p.x + 3 + c.x, cy = p.y + c.y;
      if (c.label) {
        if (showLabels) {
          ctx.fillStyle = LOOK.section;
          ctx.font = `700 ${1.6 * s}px -apple-system, Inter, sans-serif`;
          const [LX, LY] = W(cx, cy + 0.3);
          ctx.fillText(c.label.toUpperCase(), LX, LY);
        }
        continue;
      }
      drawGroup(c, cx, cy, showLabels);
    }
  });
  // lots in transit, as carrier boxes on the belts
  const sz = Math.max(4, 1.15 * s);
  for (const tr of cur.active) {
    const [x, y] = tripPoint(tr, t);
    const [X, Y] = W(x, y);
    drawLot(X, Y, sz, tr[4]);
  }
  drawFlash();
}

function drawGroup(c, cx, cy, showLabels) {
  const s = view.s;
  const g = c.gi;
  const toolIds = P.groupTools[g];
  if (c.holding) {
    const [X, Y] = W(cx, cy + 2);
    // a row of chests
    const n = 6;
    for (let k = 0; k < n; k++) {
      const [CX, CY] = W(cx + 1 + k * 4.6, cy + 2.4);
      ctx.fillStyle = "#7a5a33"; ctx.fillRect(CX, CY, 3.6 * s, 3 * s);
      ctx.fillStyle = "#5a4024"; ctx.fillRect(CX, CY + 1.1 * s, 3.6 * s, 0.5 * s);
    }
    ctx.textBaseline = "top";
    plateText(`${cur.holdingBusy} lots`, X + 1.2 * s, Y + 4.6 * s, Math.max(11, 2 * s), 700, LOOK.title);
    return;
  }
  const px = Math.round(TOOL * s * (window.devicePixelRatio || 1));
  const big = TOOL * s >= 7;
  for (let k = 0; k < toolIds.length; k++) {
    const col = k % c.cols, row = Math.floor(k / c.cols);
    const [X, Y] = W(cx + 1 + col * PITCH, cy + 1 + row * PITCH);
    const st = cur.toolState[toolIds[k]];
    if (big) {
      ctx.drawImage(sprite(st, px), X, Y, TOOL * s, TOOL * s);
    } else if (st === 1) {
      ctx.strokeStyle = STATE_COLORS[1]; ctx.lineWidth = 1;
      ctx.strokeRect(X + 0.5, Y + 0.5, TOOL * s - 1, TOOL * s - 1);
    } else {
      ctx.fillStyle = STATE_COLORS[st];
      ctx.fillRect(X, Y, TOOL * s, TOOL * s);
      if (st === 3) {
        ctx.strokeStyle = LOOK.bodyEdge; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(X, Y); ctx.lineTo(X + TOOL * s, Y + TOOL * s);
        ctx.moveTo(X + TOOL * s, Y); ctx.lineTo(X, Y + TOOL * s); ctx.stroke();
      }
    }
  }
  const yLabel = cy + 1 + c.rows * PITCH;
  if (showLabels) {
    const [LX, LY] = W(cx + 1, yLabel + 0.2);
    ctx.fillStyle = LOOK.label;
    ctx.font = `500 ${1.5 * s}px -apple-system, Inter, sans-serif`;
    ctx.textBaseline = "top";
    ctx.fillText(P.plain[g], LX, LY);
  }
  // the group's queue belt and its waiting lots
  const qy = yLabel + 3;
  const bw = c.w - 2;
  drawBelt([[cx + 1, qy], [cx + 1 + bw, qy]], 0, false, true);
  const n = cur.queue[g], hot = cur.hotQ[g];
  const fits = Math.max(0, Math.floor((bw - 0.5) / 1.6));
  const shown = Math.min(n, n > fits ? fits - 2 : fits);
  const lsz = Math.max(3, 1.05 * s);
  for (let k = 0; k < shown; k++) {
    const [X, Y] = W(cx + 1.8 + k * 1.6, qy);
    drawLot(X, Y, lsz, k < hot);
  }
  if (n > shown && s > 1.2) {
    ctx.textBaseline = "middle";
    const [X, Y] = W(cx + 1.8 + shown * 1.6 - 0.4, qy);
    ctx.font = `700 ${Math.max(9, 1.4 * s)}px -apple-system, Inter, sans-serif`;
    ctx.fillStyle = LOOK.title;
    ctx.fillText(`+${n - shown}`, X, Y);
    ctx.textBaseline = "top";
  }
}

function drawSpark() {
  const sp = document.getElementById("spark");
  const c = sp.getContext("2d");
  c.clearRect(0, 0, sp.width, sp.height);
  if (!P) return;
  const ws = P.waitSeries, max = Math.max(...ws, 1);
  c.beginPath();
  ws.forEach((v, i) => {
    const x = (i / (ws.length - 1)) * sp.width, y = sp.height - (v / max) * sp.height * 0.85 - 2;
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  });
  c.lineTo(sp.width, sp.height);
  c.lineTo(0, sp.height);
  c.closePath();
  c.fillStyle = "rgba(201,163,78,0.18)";
  c.fill();
  c.strokeStyle = "rgba(201,163,78,0.7)";
  c.lineWidth = 1.5;
  c.stroke();
  // day marks
  c.fillStyle = "rgba(255,255,255,0.15)";
  for (let d = 1440; d < P.j.until; d += 1440) c.fillRect((d / P.j.until) * sp.width, 0, 1, sp.height);
}

// ------------------------------------------------------------------ the page

const $ = id => document.getElementById(id);

function hud() {
  const day = Math.floor(t / 1440) + 1;
  const m = Math.floor(t % 1440);
  $("day").textContent = `Day ${day}`;
  $("time").textContent = `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  $("k-done").textContent = countBelow(P.done, t).toLocaleString();
  let waiting = 0;
  for (let g = 0; g < P.nG; g++) if (g !== P.holdingGroup) waiting += cur.queue[g];
  $("k-wait").textContent = waiting.toLocaleString();
  $("k-moves").textContent = (countBelow(P.starts, t) - countBelow(P.starts, t - 60)).toLocaleString();
  let busy = 0, all = 0;
  for (let k = 0; k < P.nT; k++) {
    if (P.toolGroup[k] === P.holdingGroup) continue;
    all++;
    if (cur.toolState[k] === 0) busy++;
  }
  $("k-busy").textContent = `${Math.round((100 * busy) / Math.max(1, all))}%`;
  $("scrub").value = t;
  ticker();
}

// ------------------------------------------------------------------ floor log

function clock(t) {
  const m = Math.floor(t % 1440);
  return `Day ${Math.floor(t / 1440) + 1} ${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

// breakdowns and repairs, in time order: [time, tool, 1 broke | 0 fixed]
function breakdownEvents(P) {
  const S = P.states, last = new Uint8Array(P.nT).fill(1), ev = [];
  for (let i = 0; i < S.length / 3; i++) {
    const k = S[i * 3], tm = S[i * 3 + 1], st = S[i * 3 + 2];
    if (st === 3 && last[k] !== 3) ev.push([tm, k, 1]);
    else if (st !== 3 && last[k] === 3) ev.push([tm, k, 0]);
    last[k] = st;
  }
  return ev;
}

let tickShown = "";
function ticker() {
  const ev = P.breakdowns;
  const n = countBelow(P.breakdownTimes, t);
  const rows = [];
  for (let i = n - 1; i >= 0 && rows.length < 4; i--) {
    const [tm, k, broke] = ev[i];
    const g = P.toolGroup[k];
    const idx = P.groupTools[g].indexOf(k) + 1;
    rows.push(`<li class="${broke ? "broke" : "fixed"}"><span class="tm">${clock(tm)}</span><b>${P.plain[g]}</b>&nbsp;tool ${idx} ${broke ? "broke down" : "back up"}</li>`);
  }
  const html = rows.join("");
  if (html !== tickShown) { $("ticker").innerHTML = html; tickShown = html; }
}

let lastFrame = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;
  stepFly(now);
  if (playing && P) {
    t = Math.min(P.j.until, t + dt * speed);
    if (t >= P.j.until) playing = false, ($("play").textContent = "▶");
  }
  if (P) {
    cur.seek(t);
    let hb = 0;
    for (const k of P.groupTools[P.holdingGroup] || []) if (cur.toolState[k] === 0) hb++;
    cur.holdingBusy = hb;
    hud();
  }
  draw();
  if (hover) showTip(hover);
  requestAnimationFrame(frame);
}

function groupAt(mx, my) {
  if (!G) return null;
  const wx = mx / view.s + view.x, wy = my / view.s + view.y;
  for (let i = 0; i < HALLS_L.length; i++) {
    const p = G.pos[i];
    for (const c of HALLS_L[i].cells) {
      if (c.label) continue;
      const x = p.x + 3 + c.x, y = p.y + c.y;
      if (wx >= x && wx <= x + c.w && wy >= y && wy <= y + c.h) return { g: c.gi, mx, my };
    }
  }
  return null;
}

function showTip(h) {
  const tip = $("tip");
  const g = h.g;
  const counts = [0, 0, 0, 0, 0];
  for (const k of P.groupTools[g]) counts[cur.toolState[k]]++;
  const G0 = P.j.groups[g];
  const avgWait = G0[4] ? G0[3] / G0[4] : 0;
  const parts = counts.map((n, i) => (n ? `<span style="color:${STATE_COLORS[i]}">■</span> ${n} ${STATE_NAMES[i]}` : "")).filter(Boolean);
  tip.innerHTML = `<b>${P.plain[g]}</b> <span class="m">(${G0[0]})</span><br>${parts.join("<br>")}<br>` +
    `<span class="m">waiting now:</span> ${cur.queue[g]} lots<br>` +
    `<span class="m">mean wait over the run:</span> ${avgWait.toFixed(0)} min` +
    (tipCards[g] || (tipCards[g] = (() => {
      // the stage this group belongs to: what it does to the silicon (an illustration, not to scale)
      const st = FabStages.byKey(FabStages.stageOfArea(sim.area[G0[0]]));
      if (!st) return "";
      const pic = FabStages.crossSection(st.key, "tip-" + st.key);
      return (pic ? `<div class="xs">${pic}</div>` : "<br>") + `<span class="st"><b style="color:${st.color}">${st.name}:</b> ${st.what}</span>`;
    })()));
  tip.hidden = false;
  tip.style.left = Math.min(innerWidth - 240, h.mx + 14) + "px";
  tip.style.top = Math.max(8, Math.min(innerHeight - tip.offsetHeight - 8, h.my + 14)) + "px";
}

function setupInput() {
  let drag = null;
  cv.addEventListener("mousedown", e => { drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; cv.classList.add("drag"); });
  addEventListener("mouseup", () => { drag = null; cv.classList.remove("drag"); });
  addEventListener("mousemove", e => {
    if (drag) {
      view.x = drag.vx - (e.clientX - drag.x) / view.s;
      view.y = drag.vy - (e.clientY - drag.y) / view.s;
      hover = null; $("tip").hidden = true;
    } else if (e.target === cv) {
      hover = groupAt(e.clientX, e.clientY);
      if (!hover) $("tip").hidden = true;
    }
  });
  cv.addEventListener("mouseleave", () => { hover = null; $("tip").hidden = true; });
  cv.addEventListener("wheel", e => {
    e.preventDefault();
    const k = Math.exp(-e.deltaY * 0.0015);
    const wx = e.clientX / view.s + view.x, wy = e.clientY / view.s + view.y;
    view.s = Math.min(40, Math.max(0.5, view.s * k));
    view.x = wx - e.clientX / view.s;
    view.y = wy - e.clientY / view.s;
  }, { passive: false });
  $("play").onclick = () => { playing = !playing; $("play").textContent = playing ? "❚❚" : "▶"; if (playing && P && t >= P.j.until) t = 0; };
  document.querySelectorAll(".speeds button").forEach(b => (b.onclick = () => {
    speed = +b.dataset.speed;
    document.querySelectorAll(".speeds button").forEach(x => x.classList.toggle("on", x === b));
  }));
  $("scrub").oninput = e => { t = +e.target.value; };
  $("fit").onclick = fit;
  addEventListener("keydown", e => {
    if (e.key === "Escape" && !$("stages").hidden) { stagesClose(); return; }
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (!$("stages").hidden && $("stages").contains(e.target)) return;
    if (e.key === " ") { e.preventDefault(); $("play").click(); }
    if (e.key === "f" || e.key === "F") fit();
  });
  addEventListener("resize", () => { resize(); });
  $("run").onclick = rerun;
  $("tab-long").onclick = () => showTab("long");
  $("tab-change").onclick = () => showTab("change");
  for (const k of DIAL_KEYS) $("d-" + k).oninput = showDials;
  $("reset").onclick = () => {
    for (const k of DIAL_KEYS) $("d-" + k).value = k === "cap" ? CAP_NONE : DEFAULT_DIALS[k];
    showDials();
  };
  showDials();
}

// ------------------------------------------------------------------ dials and the comparison

const DEFAULT_DIALS = { breakdowns: 1, repair: 1, demand: 1, hot: 1, rework: 1, cap: 0 };
const DIAL_KEYS = ["breakdowns", "repair", "demand", "hot", "rework", "cap"];
const CAP_NONE = 3600;
const COMPARE_SEEDS = Array.from({ length: 10 }, (_, i) => 100 + i);

function readDials() {
  const d = {};
  for (const k of DIAL_KEYS) d[k] = +$("d-" + k).value;
  d.cap = d.cap >= CAP_NONE ? 0 : d.cap;
  return d;
}

function showDials() {
  const d = readDials();
  for (const k of DIAL_KEYS) {
    const o = $("o-" + k);
    if (k === "cap") o.textContent = d.cap ? `${d.cap.toLocaleString()} lots` : "none";
    else o.textContent = d[k] === 0 && (k === "breakdowns" || k === "hot" || k === "rework") ? "none" : `×${d[k]}`;
    o.classList.toggle("moved", d[k] !== DEFAULT_DIALS[k]);
  }
}

function readOpts() {
  return {
    seed: +$("seed").value || 0,
    days: Math.min(14, Math.max(1, +$("days").value || 3)),
    rule: +$("rule").value,
    downGroup: +$("down-group").value,
    downAt: +$("down-at").value || 0,
    downHours: +$("down-hours").value || 0,
    dials: readDials(),
  };
}

function isToday(o) {
  return o.rule === 0 && (o.downGroup < 0 || o.downHours <= 0) && DIAL_KEYS.every(k => o.dials[k] === DEFAULT_DIALS[k]);
}

function describe(o) {
  const parts = [];
  if (o.rule !== 0) parts.push($("rule").selectedOptions[0].textContent.toLowerCase());
  if (o.downGroup >= 0 && o.downHours > 0) parts.push(`${$("down-group").selectedOptions[0].textContent} down from hour ${o.downAt} for ${o.downHours} h`);
  const names = { breakdowns: "breakdowns", repair: "repair time", demand: "demand", hot: "hot lots", rework: "rework" };
  for (const k of Object.keys(names)) if (o.dials[k] !== 1) parts.push(`${names[k]} ×${o.dials[k]}`);
  if (o.dials.cap) parts.push(`WIP cap ${o.dials.cap.toLocaleString()} lots`);
  return parts.join(", ");
}

let pool = null;
function workers() {
  if (pool) return pool;
  const n = Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 2) - 1));
  pool = { list: Array.from({ length: n }, () => new Worker("worker.js")), next: 0, waiting: new Map() };
  for (const w of pool.list) w.onmessage = ({ data }) => { const cb = pool.waiting.get(data.id); pool.waiting.delete(data.id); cb && cb(data); };
  return pool;
}

let jobId = 0;
function runJob(job) {
  const p = workers();
  const id = ++jobId;
  return new Promise(res => {
    p.waiting.set(id, res);
    p.list[p.next++ % p.list.length].postMessage({ ...job, id });
  });
}

const METRICS = [
  { key: "wafers_out", name: "Wafers out", higher: true, unit: "" },
  { key: "moves", name: "Moves (steps done)", higher: true, unit: "" },
  { key: "breaches", name: "Spoiled lots (queue-time limit broken)", higher: false, unit: "" },
  { key: "wait_lot_hours", name: "Waiting, lot-hours", higher: false, unit: "" },
];

function stats(d) {
  const n = d.length;
  const mean = d.reduce((a, b) => a + b, 0) / n;
  if (n < 2) return { n, mean, lo: -Infinity, hi: Infinity };
  const sd = Math.sqrt(d.reduce((a, x) => a + (x - mean) ** 2, 0) / (n - 1));
  const h = sim.e.fg_t(0.975, n - 1) * sd / Math.sqrt(n);
  return { n, mean, lo: mean - h, hi: mean + h };
}

function fmt(x) {
  const a = Math.abs(x);
  const s = a >= 100 ? Math.round(a).toLocaleString() : a >= 10 ? a.toFixed(1) : a.toFixed(2);
  return (x < 0 ? "−" : x > 0 ? "+" : "") + s;
}

function strip(d, st) {
  const m = Math.max(1e-9, ...d.map(Math.abs), Math.abs(st.lo), Math.abs(st.hi)) * 1.1;
  const X = v => 150 + (v / m) * 145;
  const dots = d.map(v => `<circle cx="${X(v).toFixed(1)}" cy="11" r="2.6" fill="#efe2c4" opacity="0.8"/>`).join("");
  const bar = isFinite(st.lo) ? `<rect x="${X(st.lo).toFixed(1)}" y="7" width="${Math.max(1, X(st.hi) - X(st.lo)).toFixed(1)}" height="8" rx="2" fill="#f0a63c" opacity="0.35"/>
    <line x1="${X(st.mean).toFixed(1)}" x2="${X(st.mean).toFixed(1)}" y1="4" y2="18" stroke="#f0a63c" stroke-width="2"/>` : "";
  return `<svg viewBox="0 0 300 22" preserveAspectRatio="none" aria-hidden="true"><line x1="150" x2="150" y1="1" y2="21" stroke="#8a8170" stroke-dasharray="2 2"/>${bar}${dots}</svg>`;
}

function renderCompare(o, base, chg, done, total) {
  showTab("change");
  $("cmp-what").textContent = `${describe(o)}, over ${o.days} day${o.days > 1 ? "s" : ""}. Each dot is one seed: the change minus today on the same draws.`;
  const seeds = COMPARE_SEEDS.filter(s => base.has(s) && chg.has(s));
  $("cmp-rows").innerHTML = METRICS.map(m => {
    const d = seeds.map(s => chg.get(s)[m.key] - base.get(s)[m.key]);
    if (d.length < 2) return `<div class="metric"><div class="head"><span class="name">${m.name}</span><span class="pill wait">running</span></div></div>`;
    const st = stats(d);
    const v = st.lo > 0 ? (m.higher ? "better" : "worse") : st.hi < 0 ? (m.higher ? "worse" : "better") : "unclear";
    const label = v === "unclear" ? "no clear effect" : v;
    const baseMean = seeds.reduce((a, s) => a + base.get(s)[m.key], 0) / seeds.length;
    return `<div class="metric"><div class="head"><span class="name">${m.name}</span><span class="pill ${v}">${label}</span></div>
      <div class="head"><span class="val">${fmt(st.mean)}</span><span class="iv">95%: ${fmt(st.lo)} to ${fmt(st.hi)} · today ${Math.round(baseMean).toLocaleString()}</span></div>${strip(d, st)}</div>`;
  }).join("");
  $("cmp-note").textContent = done < total
    ? `${done} of ${total} runs done…`
    : `On the SMT2020 model, seeds ${COMPARE_SEEDS[0]} to ${COMPARE_SEEDS[COMPARE_SEEDS.length - 1]}, paired. 95% t intervals, each on its own. A first look: a claim is checked once on held-out seeds. Real-fab effect: cannot say.`;
}

let compareToken = 0;
async function compare(o) {
  const token = ++compareToken;
  if (isToday(o)) {
    $("cmp-what").textContent = "This is today's fab. Set a rule, an outage or the dials, then Simulate and compare.";
    $("cmp-rows").innerHTML = "";
    $("cmp-note").textContent = "";
    showTab("change");
    return;
  }
  const today = { ...o, rule: 0, downGroup: -1, downAt: 0, downHours: 0, dials: { ...DEFAULT_DIALS } };
  const base = new Map(), chg = new Map();
  const total = COMPARE_SEEDS.length * 2;
  let done = 0;
  renderCompare(o, base, chg, 0, total);
  const jobs = [];
  for (const seed of COMPARE_SEEDS) {
    for (const [cfg, into] of [[today, base], [o, chg]]) {
      jobs.push(runJob({ ...cfg, seed }).then(r => {
        if (token !== compareToken) return;
        if (r.error) throw new Error(r.error);
        into.set(seed, r.q);
        done++;
        renderCompare(o, base, chg, done, total);
      }));
    }
  }
  try { await Promise.all(jobs); } catch (err) { if (token === compareToken) $("cmp-note").textContent = "Could not compare: " + err.message; }
}

// ------------------------------------------------------------------ tabs and the 300-day runs

function showTab(which) {
  $("compare").hidden = false;
  for (const [tab, pane, key] of [["tab-long", "pane-long", "long"], ["tab-change", "pane-change", "change"]]) {
    const on = key === which;
    $(tab).classList.toggle("on", on);
    $(tab).setAttribute("aria-selected", on);
    $(pane).hidden = !on;
  }
}

function signed(x, d = 1) {
  const a = Math.abs(x).toFixed(d);
  if (+a === 0) return a;
  return (x < 0 ? "−" : "+") + a;
}

async function loadLong() {
  let L;
  try { L = await fetch("data/lean-long.json").then(r => (r.ok ? r.json() : null)); } catch { L = null; }
  if (!L) { $("tab-long").hidden = true; showTab("change"); return; }
  const cell = (metric, k, cap) => L.cells.find(c => c.metric === metric && c.k === k && c.cap === cap);
  const ks = [...new Set(L.cells.map(c => c.k))];
  const caps = [...new Set(L.cells.map(c => c.cap))];
  const verdict = c => (/better/.test(c.verdict) ? "better" : /worse/.test(c.verdict) ? "worse" : "unclear");
  $("long-lead").textContent = `Wafers out a day with a WIP cap, against no cap, over days ${L.warmup} to ${L.days} of ${L.days}-day runs. ${L.seeds.length} paired seeds per cell.`;
  let g = `<div class="h">break­downs</div>` + caps.map(c => `<div class="h">cap ${c.toLocaleString()}</div>`).join("");
  for (const k of ks) {
    g += `<div class="r">×${k}</div>`;
    for (const cap of caps) {
      const w = cell("wafers_per_day", k, cap), ct = cell("cycle_days", k, cap);
      const v = verdict(w);
      const title = `Breakdowns ×${k}, cap ${cap}: wafers out ${signed(w.mean)} a day (${signed(w.lo)} to ${signed(w.hi)}), ${v === "unclear" ? "no clear effect" : v}; cycle time ${signed(ct.mean)} days (${signed(ct.lo)} to ${signed(ct.hi)})`;
      g += `<div class="c ${v}" title="${title}"><b>${signed(w.mean, 0)}</b><span>${signed(ct.mean, 0)} d</span></div>`;
    }
  }
  $("long-grid").innerHTML = g;
  // the flip: a cap free at the calmest rate and costing wafers at a harsher one
  const lines = [];
  for (const cap of caps) {
    const calm = cell("wafers_per_day", ks[0], cap);
    const worst = ks.map(k => cell("wafers_per_day", k, cap)).find(c => verdict(c) === "worse");
    if (verdict(calm) !== "worse" && worst) {
      const ctc = cell("cycle_days", ks[0], cap);
      lines.push(`A cap of <b>${cap.toLocaleString()} lots</b> costs no wafers on today's fab (${signed(calm.mean)} a day, 95% ${signed(calm.lo)} to ${signed(calm.hi)}) and cuts cycle time by ${Math.abs(ctc.mean).toFixed(0)} days. With breakdowns ×${worst.k} it costs <b>${Math.abs(worst.mean).toFixed(0)} wafers a day</b> (${Math.abs(worst.hi).toFixed(0)} to ${Math.abs(worst.lo).toFixed(0)}).`);
    }
  }
  const gains = caps.filter(cap => verdict(cell("wafers_per_day", ks[0], cap)) === "better");
  if (gains.length) lines.push(`Caps of ${gains[0].toLocaleString()} to ${gains[gains.length - 1].toLocaleString()} lots give more wafers out on this model; why is not traced yet.`);
  $("long-finding").innerHTML = lines.join("<br><br>");
  $("long-note").textContent = `Each cell: wafers out a day (cycle time in days below), cap minus no cap. Green better, red worse, grey no clear effect: 95% intervals for all ${L.cells.length / 3} cells at once (Bonferroni). Precomputed natively in ${Math.round(L.seconds)} s; the page's own runs go up to 14 days, too short for wafers to cross the fab. On the SMT2020 model. Real-fab effect: cannot say.`;
  showTab("long");
}

function rerun() {
  const opts = readOpts();
  $("runnote").textContent = "Simulating…";
  setTimeout(() => {
    let run;
    try { run = simulate(opts); } catch (err) { $("runnote").textContent = "Could not run: " + err.message; return; }
    load(run);
    const moves = run.j.moves.toLocaleString();
    $("runnote").textContent = `Seed ${opts.seed}: ${opts.days} day${opts.days > 1 ? "s" : ""}, ${moves} moves, ${run.j.decisions.toLocaleString()} dispatch decisions, simulated in ${run.secs.toFixed(2)} s here in your browser.`;
    compare(opts);
  }, 20);
}

function load(run) {
  const hallOfGroup = HALLS_L.hallOfGroup;
  P = prepare(run, HALLS_L, hallOfGroup);
  P.groupTools = Array.from({ length: P.nG }, () => []);
  P.toolGroup.forEach((g, k) => P.groupTools[g].push(k));
  P.plain = P.j.groups.map(g => plainGroup(g[0], sim.area[g[0]]));
  P.holdingGroup = P.j.groups.findIndex(g => sim.area[g[0]] === "Delay_32");
  P.breakdowns = breakdownEvents(P);
  P.breakdownTimes = P.breakdowns.map(e => e[0]);
  cur = makeCursor(P);
  t = 0;
  playing = true;
  $("play").textContent = "❚❚";
  $("scrub").max = P.j.until;
  drawSpark();
}

// ------------------------------------------------------------------ how a chip is made (docs/STAGES.md)
// The loop of stages around a wafer, a cross-section for each (our own drawings, not to scale), the counts
// from the routes the simulator returned, and a way to the stage's hall on the floor.

const ST = { key: "litho", route: 0, routes: null, flash: null, fly: null, opener: null };
const tipCards = {};

function stagesOpen() {
  $("stages").hidden = false;
  ST.opener = document.activeElement;
  stagesDraw();
  $("stages-close").focus();
}

function stagesClose() {
  $("stages").hidden = true;
  if (ST.opener && ST.opener.focus) ST.opener.focus();
}

function stagesDraw() {
  const svg = $("stages-loop");
  const cx = 270, cy = 270, rr0 = 196, nw = 112, nh = 70;
  let s = `<circle cx="${cx}" cy="${cy}" r="78" fill="#2f3a44" stroke="#8893a1" stroke-width="2"/>`;
  for (let x = cx - 72; x < cx + 72; x += 12)
    for (let y = cy - 72; y < cy + 72; y += 12)
      if (Math.hypot(x + 5 - cx, y + 5 - cy) < 70) s += `<rect x="${x}" y="${y}" width="10" height="10" fill="#3f4d5a" stroke="#56677a" stroke-width=".6"/>`;
  s += `<text x="${cx}" y="${cy + 104}" text-anchor="middle" fill="#6fd1c0" font-size="13">checked between steps</text>`;
  s += `<text x="${cx}" y="${cy + 121}" text-anchor="middle" fill="#b6a98f" font-size="12">cleaned between steps</text>`;
  s += `<defs><marker id="loop-ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#b6a98f"/></marker></defs>`;
  const ang = i => ((-90 + i * 45) * Math.PI) / 180;
  const pt = a => [cx + rr0 * Math.cos(a), cy + rr0 * Math.sin(a)];
  FabStages.LOOP.forEach((k, i) => {
    const [x1, y1] = pt(ang(i) + 0.33), [x2, y2] = pt(ang(i + 1) - 0.33);
    s += `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} A${rr0} ${rr0} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}" fill="none" stroke="#b6a98f" stroke-width="2" marker-end="url(#loop-ah)"/>`;
  });
  FabStages.LOOP.forEach((k, i) => {
    const st = FabStages.byKey(k);
    const x = cx + rr0 * Math.cos(ang(i)) - nw / 2, y = cy + rr0 * Math.sin(ang(i)) - nh / 2;
    const pic = FabStages.crossSection(k, "loop-" + k).replace(/<text[^>]*>[^<]*<\/text>/g, "").replace("<svg ", `<svg x="${x + 6}" y="${y}" width="${nw - 12}" height="${((nw - 12) * 150) / 240}" `);
    s += `<g class="node${k === ST.key ? " on" : ""}" data-k="${k}" tabindex="0" role="button" aria-label="${st.name}">` +
      `<rect class="frame" x="${x}" y="${y - 6}" width="${nw}" height="${nh + 18}" rx="4" stroke="${st.color}"/>${pic}` +
      `<text x="${x + nw / 2}" y="${y + nh + 7}" text-anchor="middle">${st.short}</text></g>`;
  });
  svg.innerHTML = s;
  stagesSelect(ST.key);
  stagesStrip();
}

function stagesSelect(k) {
  ST.key = k;
  const st = FabStages.byKey(k);
  document.querySelectorAll("#stages-loop .node").forEach(n => n.classList.toggle("on", n.dataset.k === k));
  const pic = FabStages.crossSection(k, "detail-" + k);
  const mats = st.mats.map(m => `<span><i style="background:${FabStages.MATERIALS[m][0]}"></i>${FabStages.MATERIALS[m][1]}</span>`).join("");
  let facts = "";
  if (ST.routes) {
    const cells = ST.routes.map(([name, steps]) => {
      const v = FabStages.visits(steps, sim.area)[k];
      return `<div class="fact"><div class="v">${v}</div><div class="l">steps on ${productName(name)} (of ${steps.length})</div></div>`;
    });
    const g = FabStages.groupsPerStage(sim.area)[k];
    facts = `<div class="facts">${cells.join("")}<div class="fact"><div class="v">${g}</div><div class="l">${k === "hold" ? "holding group" : "tool groups"}</div></div></div>`;
  }
  $("stages-info").innerHTML =
    `<div><h3 style="color:${st.color}">${st.name}</h3><div class="code">SMT2020 area${st.areas.length > 1 ? "s" : ""}: ${st.areas.join(", ")}</div></div>` +
    (pic ? `<div class="xs">${pic}</div><div class="mats">${mats}</div>` : `<div class="nopic">Nothing happens to the wafer here.</div>`) +
    `<div class="qa"><b>What</b><p>${st.what}</p><b>Why</b><p>${st.why}</p></div>` + facts +
    `<p class="note">${st.note}</p>`;
  $("stages-hall").textContent = `Show the ${st.hall} hall`;
  stagesPaint();
}

function productName(name) {
  const m = /(\d+)$/.exec(name);
  return m ? "product " + m[1] : name;
}

function stagesStrip() {
  const el = $("stages-strip");
  if (!ST.routes) { el.innerHTML = ""; $("stages-readout").textContent = "The route appears once the simulator has loaded."; return; }
  const [, steps] = ST.routes[ST.route];
  el.innerHTML = FabStages.strip(steps, sim.area)
    .map(c => `<i data-i="${c.i}" data-k="${c.stage}" style="background:${FabStages.byKey(c.stage).color}"></i>`).join("");
  document.querySelectorAll(".stages-route .seg button").forEach(b => b.classList.toggle("on", +b.dataset.route === ST.route));
  stagesPaint();
}

function stagesPaint() {
  document.querySelectorAll("#stages-strip i").forEach(c => c.classList.toggle("dim", c.dataset.k !== ST.key));
}

function stagesSetup() {
  $("stages-open").onclick = stagesOpen;
  $("stages-close").onclick = stagesClose;
  $("stages-hall").onclick = () => {
    const i = HALLS_L ? HALLS_L.findIndex(h => h.name === FabStages.byKey(ST.key).hall) : -1;
    stagesClose();
    if (i >= 0) flyToHall(i);
  };
  const loop = $("stages-loop");
  loop.addEventListener("click", e => { const n = e.target.closest(".node"); if (n) stagesSelect(n.dataset.k); });
  loop.addEventListener("keydown", e => {
    const n = e.target.closest(".node");
    if (n && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); stagesSelect(n.dataset.k); }
  });
  const strip = $("stages-strip");
  strip.addEventListener("mouseover", e => {
    const c = e.target.closest("i");
    if (!c || !ST.routes) return;
    const [name, steps] = ST.routes[ST.route];
    const i = +c.dataset.i, g = steps[i];
    $("stages-readout").textContent = `Step ${i + 1} of ${steps.length} on ${productName(name)}: ${FabStages.byKey(c.dataset.k).name} (${sim.area[g]}, ${g})`;
  });
  strip.addEventListener("click", e => { const c = e.target.closest("i"); if (c) stagesSelect(c.dataset.k); });
  document.querySelectorAll(".stages-route .seg button").forEach(b => (b.onclick = () => { ST.route = +b.dataset.route; stagesStrip(); }));
}

// move the view so hall i fills the middle of the floor, and outline it for a few seconds
function flyToHall(i) {
  if (!G || !HALLS_L[i]) return;
  const H = HALLS_L[i], p = G.pos[i];
  const pad = { l: innerWidth > 900 && !$("compare").hidden ? 372 : 24, r: innerWidth > 900 ? 330 : 24, t: 110, b: 90 };
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  const sx = pad.l + w / 2, sy = pad.t + h / 2;
  const to = { cx: p.x + H.w / 2, cy: p.y + H.h / 2, s: Math.min(40, Math.max(0.5, Math.min(w / (H.w + 16), h / (H.h + 16)))) };
  const from = { cx: view.x + sx / view.s, cy: view.y + sy / view.s, s: view.s };
  ST.fly = { from, to, sx, sy, t0: performance.now(), ms: 900 };
  ST.flash = { i, until: performance.now() + 4500 };
}

function stepFly(now) {
  const f = ST.fly;
  if (!f) return;
  const u = Math.min(1, (now - f.t0) / f.ms);
  const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
  const s = Math.exp(Math.log(f.from.s) + (Math.log(f.to.s) - Math.log(f.from.s)) * e);
  view.s = s;
  view.x = f.from.cx + (f.to.cx - f.from.cx) * e - f.sx / s;
  view.y = f.from.cy + (f.to.cy - f.from.cy) * e - f.sy / s;
  if (u >= 1) ST.fly = null;
}

function drawFlash() {
  const f = ST.flash;
  if (!f) return;
  const now = performance.now();
  if (now > f.until) { ST.flash = null; return; }
  const H = HALLS_L[f.i], p = G.pos[f.i], s = view.s;
  const [X, Y] = W(p.x, p.y);
  const a = 0.55 + 0.45 * Math.sin(now / 180);
  ctx.save();
  ctx.strokeStyle = `rgba(240,166,60,${a.toFixed(3)})`;
  ctx.lineWidth = Math.max(3, 0.9 * s);
  ctx.strokeRect(X - 1.2 * s, Y - 1.2 * s, (H.w + 2.4) * s, (H.h + 2.4) * s);
  ctx.restore();
}

async function main() {
  resize();
  setupInput();
  stagesSetup();
  requestAnimationFrame(frame);
  try {
    await loadSim();
  } catch (err) {
    $("runnote").textContent = "Could not load the simulator: " + err.message;
    return;
  }
  const first = simulate({ seed: 0, days: 3, rule: 0, downGroup: -1, downAt: 0, downHours: 0 });
  const groups = first.j.groups.map(g => ({ name: g[0], count: g[1] }));
  HALLS_L = buildLayout(groups);
  const flows = hallFlows(HALLS_L, first.j.routes);
  HALLS_L.hallOfGroup = flows.hallOfGroup;
  const padR = innerWidth > 900 ? 330 : 24, padL = innerWidth > 900 ? 372 : 24;
  TARGET_ASPECT = Math.max(1.0, Math.min(2.4, (innerWidth - padR - padL) / (innerHeight - 220)));
  G = placeHalls(HALLS_L, flows);
  const sel = $("down-group");
  groups
    .map((g, i) => [plainGroup(g.name, sim.area[g.name]), i])
    .filter(([, i]) => sim.area[groups[i].name] !== "Delay_32")
    .sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
    .forEach(([name, i]) => { const o = document.createElement("option"); o.value = i; o.textContent = name; sel.appendChild(o); });
  load(first);
  ST.routes = first.j.routes.map(([name, steps]) => [name, steps.map(gi => first.j.groups[gi][0])]);
  if (!$("stages").hidden) stagesDraw();
  await loadLong();
  fit();
  $("runnote").textContent = `Simulated 3 days (${first.j.moves.toLocaleString()} moves) in ${first.secs.toFixed(2)} s, here in your browser.`;
}

main();
