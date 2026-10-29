// Fab Gym floor: the simulator (Rust, compiled to WebAssembly) runs in the page, and the floor
// plays its run back. Units of the layout are tiles; a tool is 3 x 3 tiles.
"use strict";

const AREA_NAMES = {
  Litho: "Lithography", Litho_Met: "Litho checks", Def_Met: "Defect checks", TF_Met: "Film checks",
  Implant: "Implant", Diffusion: "Diffusion", Dielectric: "Dielectric", Wet_Etch: "Wet etch",
  TF: "Thin film", Dry_Etch: "Dry etch", Planar: "Polishing", Delay_32: "Holding", "P3 wing": "Wing (P3)",
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
const STATE_COLORS = ["#4FE3A3", "#8FB3AE", "#7F9CFF", "#FF6262", "#FFC857"];
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
  // a P3 wing gets a hall of its own when the setup on the floor has one (docs/ASK-FAMILIES.md)
  const list = HALLS.concat(FabAsk.extraHalls(groups.map(g => sim.area[g.name])));
  list.forEach(([h, areas], i) => areas.forEach(a => (hallOfArea[a] = i)));
  const halls = list.map(([name, areas]) => ({ name, areas, groups: [] }));
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
  const isB = FabAsk.familyB(j);
  const lotB = j.lots.map(l => (isB[l[1]] ? 1 : 0));
  // queue events (+1 at arrival, -1 at start), sorted by time, arrivals first at equal times
  const nRows = trace.length / 6;
  const qe = [];
  const byLot = new Map();
  for (let r = 0; r < nRows; r++) {
    const lot = trace[r * 6], tool = trace[r * 6 + 2], arrive = trace[r * 6 + 3], start = trace[r * 6 + 4], end = trace[r * 6 + 5];
    const g = toolGroup[tool];
    if (start > arrive) {
      // family B's lots are counted apart from hot ones, so a hot prototype counts once
      qe.push([arrive, g, 1, lotHot[lot] && !lotB[lot] ? 1 : 0, lotB[lot]]);
      qe.push([start, g, -1, lotHot[lot] && !lotB[lot] ? 1 : 0, lotB[lot]]);
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
      if (arrive1 > end0) trips.push([end0, arrive1, hallOfGroup[g0], hallOfGroup[g1], lotHot[lot], lot, lotB[lot]]);
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
  const c = { t: -1, si: 0, qi: 0, ti: 0, toolState: new Uint8Array(P.nT), queue: new Int32Array(P.nG), hotQ: new Int32Array(P.nG), bQ: new Int32Array(P.nG), active: [] };
  c.reset = () => {
    c.t = -1; c.si = 0; c.qi = 0; c.ti = 0; c.toolState.fill(1); c.queue.fill(0); c.hotQ.fill(0); c.bQ.fill(0); c.active = [];
  };
  c.reset();
  c.seek = t => {
    if (t < c.t) c.reset();
    const S = P.states;
    while (c.si < S.length / 3 && S[c.si * 3 + 1] <= t) { c.toolState[S[c.si * 3]] = S[c.si * 3 + 2]; c.si++; }
    const Q = P.qe;
    while (c.qi < Q.length && Q[c.qi][0] <= t) { const q = Q[c.qi]; c.queue[q[1]] += q[2]; c.hotQ[q[1]] += q[2] * q[3]; c.bQ[q[1]] += q[2] * (q[4] || 0); c.qi++; }
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
  if (SPLIT.on && !SPLIT.fitting) { layoutSplit(); return; }
  const pad = floorPad();
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  updateTilt();
  const M = 6; // the board's margin around the fab, in tiles
  const xs = [], ys = [];
  for (const [x, y] of [[-M, -M], [G.L + M, -M], [G.L + M, G.bottom + M], [-M, G.bottom + M]]) { xs.push(TM.a * x + TM.c * y); ys.push(TM.b * x + TM.d * y); }
  const s = Math.min(w / (Math.max(...xs) - Math.min(...xs)), h / (Math.max(...ys) - Math.min(...ys) + 3));
  view.s = s;
  const [px, py] = untilt(pad.l + w / 2, pad.t + h / 2);
  view.x = G.L / 2 - px / s;
  view.y = G.bottom / 2 - py / s;
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

// The living diorama: the flat drawing is turned by TILT.rot and its depth squashed by TILT.k, about the canvas
// centre, with one canvas transform. TM maps the flat picture to the screen; labels and lots are drawn upright at
// their projected points; walls rise from the projected hall outlines. T toggles it.
const TILT = { on: true, rot: -0.30, k: 0.6 };
let TM = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }, TMi = TM;
function updateTilt() {
  const cx = VP ? VP.x + VP.w / 2 : innerWidth / 2, cy = VP ? VP.y + VP.h / 2 : innerHeight / 2;
  const m = TILT.on ? new DOMMatrix().translate(cx, cy).scale(1, TILT.k).rotate((TILT.rot * 180) / Math.PI).translate(-cx, -cy) : new DOMMatrix();
  const i = m.inverse();
  TM = { a: m.a, b: m.b, c: m.c, d: m.d, e: m.e, f: m.f };
  TMi = { a: i.a, b: i.b, c: i.c, d: i.d, e: i.e, f: i.f };
}
function T(X, Y) { return [TM.a * X + TM.c * Y + TM.e, TM.b * X + TM.d * Y + TM.f]; }
function untilt(X, Y) { return [TMi.a * X + TMi.c * Y + TMi.e, TMi.b * X + TMi.d * Y + TMi.f]; }
function floorSpace() { const r = window.devicePixelRatio || 1; ctx.setTransform(r * TM.a, r * TM.b, r * TM.c, r * TM.d, r * TM.e, r * TM.f); }
function screenSpace() { const r = window.devicePixelRatio || 1; ctx.setTransform(r, 0, 0, r, 0, 0); }
// a point of the floor (world tiles) on the screen
function S(x, y) { const [X, Y] = W(x, y); return T(X, Y); }

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
  sky0: "#16323A", sky1: "#0B1418", sky2: "#070C0F", boardSide: "#071013",
  ground: "#0F1D22", hallFloor: "#12262D", wall: "#2C5560", wallDark: "#0A1418", wallTop: "#7EE8D8",
  rail: "#FFB347", beltTop: "#1F3A42", chevron: "rgba(255, 179, 71, 0.85)", glow: "rgba(255, 179, 71, 0.16)",
  body: "#3A4A52", bodyEdge: "#0A1418", plate: "rgba(14, 27, 31, 0.86)",
  title: "#E8F2F0", sub: "#8FB3AE", label: "#A9C4C0", section: "#7EE8D8",
  lot: "#F4E7C6", lotTop: "#c9bc9c", hot: "#FF8A4C", hotTop: "#c25e2c", proto: "#FF8AD8", protoTop: "#c25aa6",
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
    const src = name === "ground" ? noiseTile(LOOK.ground, 0.05, "rgba(126,232,216,0.07)", 7) : noiseTile(LOOK.hallFloor, 0.05, "rgba(126,232,216,0.10)", 11);
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
    g.fillStyle = "#16262c"; g.fill();
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
  g.fillStyle = st === 0 ? "#d6ffe6" : st === 3 ? "#ffb0aa" : st === 1 ? "#2C5560" : "#fff0c2";
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
  if (!small && chevrons) { path(); ctx.strokeStyle = LOOK.glow; ctx.lineWidth = Math.max(26, 6 * s); ctx.stroke(); }
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

// X, Y are flat-picture coordinates; the caller is in floor space and stays there
function drawLot(X, Y, sz, hot, proto) {
  const [x, y] = T(X, Y);
  const dim = (UI.lens === "proto" && !proto) || (UI.lens === "flows" && !FLOW.wafer);
  if (dim) ctx.globalAlpha = 0.14;
  else if (UI.lens === "proto") sz *= 1.6;
  const h = sz * 0.75, top = sz * 0.38;
  screenSpace();
  ctx.fillStyle = LOOK.bodyEdge;
  ctx.fillRect(x - sz / 2 - 1, y - h - top - 1, sz + 2, h + top + 2);
  ctx.fillStyle = proto ? LOOK.protoTop : hot ? LOOK.hotTop : LOOK.lotTop;
  ctx.fillRect(x - sz / 2, y - h, sz, h);
  ctx.fillStyle = proto ? LOOK.proto : hot ? LOOK.hot : LOOK.lot;
  ctx.fillRect(x - sz / 2, y - h - top, sz, top);
  if (dim) ctx.globalAlpha = 1;
  floorSpace();
}

// X, Y are flat-picture coordinates; dx, dy a screen offset. Drawn upright; the caller stays in floor space.
function plateText(text, X, Y, size, weight, color, dx = 0, dy = 0) {
  const [x0, y0] = T(X, Y), x = x0 + dx, y = y0 + dy;
  screenSpace();
  ctx.font = `${weight} ${size}px -apple-system, Inter, sans-serif`;
  const w = ctx.measureText(text).width;
  ctx.fillStyle = LOOK.plate;
  ctx.fillRect(x - size * 0.35, y - size * 0.2, w + size * 0.7, size * 1.35);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
  floorSpace();
  return w;
}
function uprightText(text, X, Y, font, color) {
  const [x, y] = T(X, Y);
  screenSpace();
  ctx.font = font; ctx.fillStyle = color;
  ctx.fillText(text, x, y);
  floorSpace();
}

// a hall's walls: the four sides of its outline raised by h screen pixels. Sides facing away are solid,
// sides facing the viewer are glass, drawn after the hall's contents.
function hallWalls(x, y, w, hgt, h, front) {
  const P = [S(x, y), S(x + w, y), S(x + w, y + hgt), S(x, y + hgt)];
  screenSpace();
  for (let i = 0; i < 4; i++) {
    const [ax, ay] = P[i], [bx, by] = P[(i + 1) % 4];
    const ny = -(bx - ax); // the outward normal's screen y, for a clockwise outline
    if ((ny > 0) !== front) continue;
    ctx.beginPath();
    ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.lineTo(bx, by - h); ctx.lineTo(ax, ay - h); ctx.closePath();
    if (front) {
      ctx.fillStyle = "rgba(126, 232, 216, 0.05)"; ctx.fill();
      ctx.strokeStyle = "rgba(126, 232, 216, 0.30)"; ctx.lineWidth = 1; ctx.stroke();
    } else {
      const gr = ctx.createLinearGradient(0, Math.min(ay, by) - h, 0, Math.max(ay, by));
      gr.addColorStop(0, LOOK.wall); gr.addColorStop(1, "#16323A");
      ctx.fillStyle = gr; ctx.fill();
    }
    ctx.beginPath(); ctx.moveTo(ax, ay - h); ctx.lineTo(bx, by - h);
    ctx.strokeStyle = front ? "rgba(126, 232, 216, 0.75)" : LOOK.wallTop; ctx.lineWidth = front ? 1.5 : 1.2; ctx.stroke();
  }
  floorSpace();
}

// the board the fab stands on: a slab with a visible edge
function board() {
  const M = 6;
  const P = [S(-M, -M), S(G.L + M, -M), S(G.L + M, G.bottom + M), S(-M, G.bottom + M)];
  const D = Math.max(8, 1.6 * view.s);
  screenSpace();
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 60; ctx.shadowOffsetY = 40;
  ctx.beginPath(); P.forEach(([x, y], i) => (i ? ctx.lineTo(x, y + D) : ctx.moveTo(x, y + D))); ctx.closePath();
  ctx.fillStyle = LOOK.boardSide; ctx.fill();
  ctx.restore();
  for (let i = 0; i < 4; i++) {
    const [ax, ay] = P[i], [bx, by] = P[(i + 1) % 4];
    if (-(bx - ax) <= 0) continue;
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.lineTo(bx, by + D); ctx.lineTo(ax, ay + D); ctx.closePath();
    ctx.fillStyle = "#0E1B1F"; ctx.fill();
  }
  floorSpace();
  const [x0, y0] = W(-M, -M);
  ctx.fillStyle = pattern("ground");
  ctx.fillRect(x0, y0, (G.L + 2 * M) * view.s, (G.bottom + 2 * M) * view.s);
  ctx.strokeStyle = "rgba(126, 232, 216, 0.25)"; ctx.lineWidth = 1.5 / TILT.k;
  ctx.strokeRect(x0, y0, (G.L + 2 * M) * view.s, (G.bottom + 2 * M) * view.s);
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

function draw(clear = true) {
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (clear) drawSky();
  if (!G || !P) return;
  updateTilt();
  const s = view.s;
  board();
  drawFloorBody(s);
}

function drawSky() {
  const sky = ctx.createRadialGradient(innerWidth / 2, innerHeight * 0.4, 0, innerWidth / 2, innerHeight * 0.4, Math.max(innerWidth, innerHeight) * 0.75);
  sky.addColorStop(0, LOOK.sky0); sky.addColorStop(0.6, LOOK.sky1); sky.addColorStop(1, LOOK.sky2);
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, innerWidth, innerHeight);
}

function drawFloorBody(s) {
  // belts: the spine and each hall's feeder
  const phase = (t * 0.35) % 1;
  HALLS_L.forEach((h, i) => {
    const p = G.pos[i];
    const by = p.belt === "top" ? G.yTop : G.yBot;
    drawBelt([[p.door.x, p.door.y], [p.door.x, by]], phase, false);
  });
  drawBelt([[0, G.yTop], [G.L, G.yTop], [G.L, G.yBot], [0, G.yBot], [0, G.yTop]], phase);
  // halls: back walls first, then floors and contents, then the glass fronts
  const showLabels = s > 2.6;
  const wallH = Math.max(5, 2.2 * s * TILT.k);
  if (TILT.on) HALLS_L.forEach((h, i) => hallWalls(G.pos[i].x, G.pos[i].y, h.w, h.h, wallH, false));
  const titles = []; // hall titles go on top of everything
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
    titles.push(() => {
      ctx.textBaseline = "top";
      const lift = TILT.on ? -wallH - tsz * 1.4 : 0;
      ctx.font = `700 ${tsz}px -apple-system, Inter, sans-serif`;
      if (ctx.measureText(h.name).width > h.w * s * 0.95) return; // too small to carry its name: the tooltip has it
      const tw = plateText(h.name, X + 1.6 * s, Y + 1.2 * s, tsz, 700, LOOK.title, 0, lift);
      const toolsN = h.groups.reduce((a, g) => a + P.j.groups[g][1], 0);
      if (h.w * s > tw + 80) {
        const ssz = Math.max(11, 1.5 * s);
        const label = h.areas[0] === "Delay_32" ? "between steps" : `${toolsN} tools`;
        plateText(label, X + 1.6 * s, Y + 1.2 * s, ssz, 500, LOOK.sub, tw + tsz * 0.7 + 4, lift + (tsz - ssz) * 0.7);
      }
    });
    for (const c of h.cells) {
      const cx = p.x + 3 + c.x, cy = p.y + c.y;
      if (c.label) {
        if (showLabels) {
          const [LX, LY] = W(cx, cy + 0.3);
          uprightText(c.label.toUpperCase(), LX, LY, `700 ${1.6 * s}px -apple-system, Inter, sans-serif`, LOOK.section);
        }
        continue;
      }
      drawGroup(c, cx, cy, showLabels);
    }
  });
  if (TILT.on) HALLS_L.forEach((h, i) => hallWalls(G.pos[i].x, G.pos[i].y, h.w, h.h, wallH, true));
  // lots in transit, as carrier boxes on the belts
  const sz = Math.max(4, 1.15 * s);
  for (const tr of cur.active) {
    const [x, y] = tripPoint(tr, t);
    const [X, Y] = W(x, y);
    drawLot(X, Y, sz, tr[4], tr[6]);
  }
  if (UI.lens === "flows") drawFlows();
  for (const f of titles) f();
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
  if (UI.lens === "proto" || UI.lens === "flows") ctx.globalAlpha = 0.3;
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
  ctx.globalAlpha = 1;
  if (UI.lens === "heat") {
    // waiting heat: the group's cell glows with the lots waiting at it
    const q = cur.queue[g], a = Math.min(0.75, q / 30);
    if (q > 0) {
      const [HX, HY] = W(cx + 0.3, cy + 0.3);
      ctx.fillStyle = `rgba(255, ${Math.round(140 - 90 * a)}, 70, ${(0.12 + a * 0.7).toFixed(3)})`;
      ctx.fillRect(HX, HY, (c.w - 0.6) * s, (c.h - 0.6) * s);
    }
  }
  const yLabel = cy + 1 + c.rows * PITCH;
  if (showLabels) {
    const [LX, LY] = W(cx + 1, yLabel + 0.2);
    ctx.textBaseline = "top";
    uprightText(P.plain[g], LX, LY, `500 ${1.5 * s}px -apple-system, Inter, sans-serif`, LOOK.label);
  }
  // the group's queue belt and its waiting lots
  const qy = yLabel + 3;
  const bw = c.w - 2;
  drawBelt([[cx + 1, qy], [cx + 1 + bw, qy]], 0, false, true);
  const n = cur.queue[g], hot = cur.hotQ[g], protos = cur.bQ[g];
  const fits = Math.max(0, Math.floor((bw - 0.5) / 1.6));
  const shown = Math.min(n, n > fits ? fits - 2 : fits);
  const lsz = Math.max(3, 1.05 * s);
  for (let k = 0; k < shown; k++) {
    const [X, Y] = W(cx + 1.8 + k * 1.6, qy);
    drawLot(X, Y, lsz, k < hot, k >= hot && k < hot + protos);
  }
  if (n > shown && s > 1.2) {
    ctx.textBaseline = "middle";
    const [X, Y] = W(cx + 1.8 + shown * 1.6 - 0.4, qy);
    uprightText(`+${n - shown}`, X, Y, `700 ${Math.max(9, 1.4 * s)}px -apple-system, Inter, sans-serif`, LOOK.title);
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

let lensShown = "";
function lensNote() {
  let txt = "";
  if (UI.lens === "heat") txt = "Each tool group glows with the lots waiting at it. The brighter the glow, the longer the queue.";
  else if (UI.lens === "flows") txt = flowNote();
  else if (UI.lens === "proto") {
    let n = 0;
    for (const tr of cur.active) if (tr[6]) n++;
    for (const q of cur.bQ || []) n += q;
    txt = n ? (n === 1 ? "1 prototype lot is in the fab now. It is drawn large and pink, and everything else is dimmed." : `${n} prototype lots are in the fab now. They are drawn large and pink, and everything else is dimmed.`)
      : "Today's fab has no prototype lots. To see some, ask a question about prototypes and press “Show on the floor” on one of the answers.";
  }
  if (txt !== lensShown) { $("lens-note").textContent = txt; lensShown = txt; }
}

function hud() {
  lensNote();
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
  if (SPLIT.on) { splitFrame(dt); requestAnimationFrame(frame); return; }
  if (UI.lens === "flows") FLOW.secs += dt;
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
  const [ux, uy] = untilt(mx, my);
  const wx = ux / view.s + view.x, wy = uy / view.s + view.y;
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
  cv.addEventListener("mousedown", e => { splitPick(e.clientX); const [ux, uy] = untilt(e.clientX, e.clientY); drag = { x: ux, y: uy, vx: view.x, vy: view.y, scene: SPLIT.active }; cv.classList.add("drag"); });
  addEventListener("mouseup", () => { drag = null; cv.classList.remove("drag"); });
  addEventListener("mousemove", e => {
    if (drag) {
      if (SPLIT.on) useScene(drag.scene);
      const [ux, uy] = untilt(e.clientX, e.clientY);
      view.x = drag.vx - (ux - drag.x) / view.s;
      view.y = drag.vy - (uy - drag.y) / view.s;
      keepScene();
      hover = null; $("tip").hidden = true;
    } else if (e.target === cv) {
      splitPick(e.clientX);
      hover = groupAt(e.clientX, e.clientY);
      if (hover) hover.scene = SPLIT.active;
      if (!hover) $("tip").hidden = true;
    }
  });
  cv.addEventListener("mouseleave", () => { hover = null; $("tip").hidden = true; });
  cv.addEventListener("wheel", e => {
    e.preventDefault();
    splitPick(e.clientX);
    const k = Math.exp(-e.deltaY * 0.0015);
    const [ux, uy] = untilt(e.clientX, e.clientY);
    const wx = ux / view.s + view.x, wy = uy / view.s + view.y;
    view.s = Math.min(40, Math.max(0.5, view.s * k));
    view.x = wx - ux / view.s;
    view.y = wy - uy / view.s;
    keepScene();
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
    if (e.key === "t" || e.key === "T") { TILT.on = !TILT.on; fit(); }
  });
  addEventListener("resize", () => { resize(); });
  $("run").onclick = rerun;
  $("tab-long").onclick = () => showTab("long");
  $("tab-ask").onclick = () => showTab("ask");
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
    : `Simulated on the SMT2020 model with seeds ${COMPARE_SEEDS[0]} to ${COMPARE_SEEDS[COMPARE_SEEDS.length - 1]}. Each run is paired with today's fab on the same seed, and each range is a 95% interval on its own. Treat this as a first look: a claim is made only after one more check on fresh seeds. What the change would do in a real fab is unknown.`;
}

let compareToken = 0;
async function compare(o) {
  const token = ++compareToken;
  if (isToday(o)) {
    $("cmp-what").textContent = "This is today's fab. Choose a dispatch rule, take a tool group down or turn a dial. Then press Simulate and compare.";
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

function showTab(which, open = true) {
  if (open) openDrawer("compare");
  for (const [tab, pane, key] of [["tab-ask", "pane-ask", "ask"], ["tab-long", "pane-long", "long"], ["tab-change", "pane-change", "change"]]) {
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
  if (!L) { $("tab-long").hidden = true; showTab("change", false); return; }
  const cell = (metric, k, cap) => L.cells.find(c => c.metric === metric && c.k === k && c.cap === cap);
  const ks = [...new Set(L.cells.map(c => c.k))];
  const caps = [...new Set(L.cells.map(c => c.cap))];
  const verdict = c => (/better/.test(c.verdict) ? "better" : /worse/.test(c.verdict) ? "worse" : "unclear");
  $("long-lead").textContent = `How many wafers come out a day with a cap on lots in the fab (WIP cap), compared with no cap. Measured from day ${L.warmup} to day ${L.days} of each run, with ${L.seeds.length} paired seeds in every cell.`;
  let g = `<div class="h">break­downs</div>` + caps.map(c => `<div class="h">cap ${c.toLocaleString()}</div>`).join("");
  for (const k of ks) {
    g += `<div class="r">×${k}</div>`;
    for (const cap of caps) {
      const w = cell("wafers_per_day", k, cap), ct = cell("cycle_days", k, cap);
      const v = verdict(w);
      const title = `Breakdowns ×${k}, cap ${cap}. Wafers out: ${signed(w.mean)} a day (95%: ${signed(w.lo)} to ${signed(w.hi)}), ${v === "unclear" ? "no clear effect" : v}. Cycle time: ${signed(ct.mean)} days (${signed(ct.lo)} to ${signed(ct.hi)}).`;
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
      lines.push(`In today's fab, a cap of <b>${cap.toLocaleString()} lots</b> costs no wafers (${signed(calm.mean)} a day, 95%: ${signed(calm.lo)} to ${signed(calm.hi)}) and cuts cycle time by ${Math.abs(ctc.mean).toFixed(0)} days. When breakdowns are ×${worst.k}, the same cap costs <b>${Math.abs(worst.mean).toFixed(0)} wafers a day</b> (95%: ${Math.abs(worst.hi).toFixed(0)} to ${Math.abs(worst.lo).toFixed(0)}).`);
    }
  }
  const gains = caps.filter(cap => verdict(cell("wafers_per_day", ks[0], cap)) === "better");
  if (gains.length) lines.push(`Caps of ${gains[0].toLocaleString()} to ${gains[gains.length - 1].toLocaleString()} lots give more wafers out on this model. We have not yet traced why.`);
  $("long-finding").innerHTML = lines.join("<br><br>");
  $("long-note").textContent = `Each cell shows wafers out a day with the cap minus without it, and the change in cycle time in days below. Green is better, red is worse and grey is no clear effect. The 95% intervals hold for all ${L.cells.length / 3} cells at once (Bonferroni). These runs were computed ahead of time in ${Math.round(L.seconds)} s. The page's own runs last at most 14 days, too short for a wafer to cross the fab. On the SMT2020 model. What a cap would do in a real fab is unknown.`;
  showTab("long", false);
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
  const pad = floorPad();
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  updateTilt();
  const [sx, sy] = untilt(pad.l + w / 2, pad.t + h / 2);
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
  chromeSetup();
  stagesSetup();
  requestAnimationFrame(frame);
  try {
    await loadSim();
  } catch (err) {
    $("runnote").textContent = "Could not load the simulator: " + err.message;
    return;
  }
  const first = simulate({ seed: 0, days: 3, rule: 0, downGroup: -1, downAt: 0, downHours: 0 });
  setFloor(first);
  await loadLong();
  fit();
  $("runnote").textContent = `Simulated 3 days (${first.j.moves.toLocaleString()} moves) in ${first.secs.toFixed(2)} s, right here in your browser.`;
  askSetup();
}

// lay the floor out for a run's groups (today's fab, or a setup from the ask box) and play the run
function setFloor(run) {
  if (!SPLIT.building) leaveSplit(false);
  const groups = run.j.groups.map(g => ({ name: g[0], count: g[1] }));
  HALLS_L = buildLayout(groups);
  const flows = hallFlows(HALLS_L, run.j.routes);
  HALLS_L.hallOfGroup = flows.hallOfGroup;
  HALLS_L.flows = flows.f;
  HALLS_L.routes = run.j.routes;
  TARGET_ASPECT = Math.max(1.0, Math.min(2.4, (innerWidth - 48) / (innerHeight - 220)));
  G = placeHalls(HALLS_L, flows);
  const sel = $("down-group");
  sel.length = 1;
  groups
    .map((g, i) => [plainGroup(g.name, sim.area[g.name]), i])
    .filter(([, i]) => sim.area[groups[i].name] !== "Delay_32")
    .sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
    .forEach(([name, i]) => { const o = document.createElement("option"); o.value = i; o.textContent = name; sel.appendChild(o); });
  load(run);
  ST.routes = run.j.routes.map(([name, steps]) => [name, steps.map(gi => run.j.groups[gi][0])]);
  if (!$("stages").hidden) stagesDraw();
}

// ------------------------------------------------------------------ the ask box (docs/ASK-FAMILIES.md)
// A question goes to the helper on this Mac (agent/helper.py), which asks the model, checks its scenario and runs
// the simulator natively; the page shows the scenario, the answer, and any arm played on this floor.

const ASK = { job: null, timer: null, helper: false, baseText: null, extra: [] };

function esc(x) {
  return String(x).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ error: `the helper answered ${r.status}` }));
  return j;
}

async function askSetup() {
  $("ask-form").onsubmit = e => { e.preventDefault(); ask($("ask-q").value); };
  $("ask-run").onclick = () => runText($("ask-text").value);
  let st;
  try { st = await api("/api/status"); } catch { st = null; }
  if (!st || st.error) {
    $("ask-model").innerHTML = "The ask box needs the helper running on this Mac. In the fab-gym folder, run <code>python3 -m agent.helper</code>, then open <b>http://127.0.0.1:8766</b>.";
    $("ask-go").disabled = true; $("ask-run").disabled = true;
    return;
  }
  ASK.helper = true;
  $("ask-model").textContent = st.model_connected
    ? `Questions go to ${st.model}. It turns your question into a scenario, and the simulator runs it.`
    : "No model is connected yet. The example questions use answers we wrote by hand, and you can write your own scenario below.";
  $("ask-examples").innerHTML = st.examples.map((e, i) => `<button type="button" data-i="${i}">${esc(e.question)}</button>`).join("");
  $("ask-examples").querySelectorAll("button").forEach(b => (b.onclick = () => { $("ask-q").value = st.examples[+b.dataset.i].question; ask($("ask-q").value); }));
  if (!$("ask-text").value) $("ask-text").value = "fabgym-scenario 1\nquestion\tPrototype orders double. Their own wing?\nfamily\tshare\t2\tsaid\ncandidate\town-wing\tfloor\twing\n";
  showTab("ask", false);
}

async function ask(q) {
  if (!q.trim()) return;
  stage("Sending the question…");
  const r = await api("/api/ask", { question: q });
  if (r.no_model) { stage(r.message); return; }
  if (r.error) { stage(r.error); return; }
  follow(r.job);
}

async function runText(text) {
  stage("Checking the scenario…");
  const r = await api("/api/run", { scenario: text });
  if (r.error) { stage(r.error); return; }
  follow(r.job);
}

function stage(msg) {
  $("ask-stage").hidden = !msg;
  $("ask-stage").textContent = msg || "";
}

function follow(id) {
  clearInterval(ASK.timer);
  $("ask-result").innerHTML = "";
  $("ask-scenario").hidden = true;
  ASK.timer = setInterval(async () => {
    const j = await api(`/api/job/${id}`);
    if (j.error && !j.stage) { clearInterval(ASK.timer); stage(j.error); return; }
    ASK.job = j;
    if (j.scenario) showScenario(j);
    if (j.stage === "done") { clearInterval(ASK.timer); stage(`Done in ${Math.round(j.seconds)} s.`); showResult(j); }
    else if (j.stage === "failed") { clearInterval(ASK.timer); stage(j.error); }
    else stage(`${j.stage[0].toUpperCase()}${j.stage.slice(1)}… ${Math.round(j.elapsed)} s`);
  }, 1000);
}

function showScenario(j) {
  const s = FabAsk.scenarioLines(j.scenario);
  const src = j.answer_source === "example" ? "an example answer we wrote by hand"
    : j.answer_source === "model" ? "the model's answer, after checking" : "your scenario";
  $("ask-scenario").hidden = false;
  $("ask-scenario").innerHTML = `<p class="note">This scenario comes from ${src}:</p>
    <ul class="given">${s.given.map(g => `<li><span class="tag ${g.said ? "said" : "assumed"}">${g.said ? "said" : "assumed"}</span>${esc(g.text)}</li>`).join("") || "<li>Today's fab as it is.</li>"}</ul>
    <p class="note">Compared with today's fab:</p>
    <ul class="cands">${s.candidates.map(c => `<li><b>${esc(c.name)}</b>: ${esc(c.changes.join(", "))}</li>`).join("")}</ul>`;
  $("ask-text").value = j.scenario;
}

function cellText(c) {
  if (c.mean === null) return "—";
  const unit = c.key === "money" ? "" : "";
  return `${fmt(c.mean)}${unit}`;
}

function showResult(j) {
  const r = j.report;
  const rows = FabAsk.resultRows(r);
  const arms = r.arms || [];
  const armBtn = name => {
    const i = arms.findIndex(a => a.name === name);
    return i < 0 ? "" : `<button type="button" class="show" data-arm="${i}">Show on the floor</button>` +
      (name === "today" ? "" : ` <button type="button" class="show sbs" data-arm="${i}">Side by side</button>`);
  };
  const head = r.families
    ? `<p class="note">Each row compares a candidate with today's fab on the same seeds and gives a 95% interval. Today's values: ${rows[0] ? rows[0].cells.map(c => `${c.label.toLowerCase()} ${c.today === null ? "—" : Math.round(c.today * 10) / 10}`).join(", ") : ""}.</p>`
    : `<p class="note">Each row compares a candidate with today's fab on the same seeds and gives a 95% interval.</p>`;
  $("ask-result").innerHTML = `<p class="what">${esc(FabAsk.summaryLine(r))}</p>${head}` +
    (arms.length ? `<div class="arm"><div class="top"><b>today</b>${armBtn("today")}</div></div>` : "") +
    rows.map(row => `<div class="arm"><div class="top"><b>${esc(row.name)}${row.best ? '<span class="best">best</span>' : ""}</b>${armBtn(row.name)}</div>
      <table>${row.cells.map(c => `<tr><td>${esc(c.label)}</td><td class="v">${cellText(c)}</td><td class="v">${c.lo === null || c.mean === null ? "" : `${fmt(c.lo)} to ${fmt(c.hi)}`}</td><td class="p"><span class="pill ${c.verdict === "no clear effect" ? "unclear" : c.verdict}">${c.verdict}</span></td></tr>`).join("")}</table></div>`).join("") +
    `<p class="note small">${r.families ? "Money a day is counted in volume-wafer margins, and every price is assumed. " : ""}The intervals hold together at 95% across all the candidates (Bonferroni). Simulated on the SMT2020 model, a published research model of a wafer fab. What these changes would do in a real fab is unknown.</p>`;
  $("ask-result").querySelectorAll("button.show:not(.sbs)").forEach(b => (b.onclick = () => showArm(j, +b.dataset.arm)));
  $("ask-result").querySelectorAll("button.sbs").forEach(b => (b.onclick = () => sideBySide(j, +b.dataset.arm)));
  {
    const pick = rows.find(r => r.best) || rows[0];
    const k = pick ? arms.findIndex(a => a.name === pick.name) : -1;
    if (k >= 0 && arms.some(a => a.name === "today")) sideBySide(j, k);
  }
  $("ask-result").insertAdjacentHTML("afterbegin", verdictCards(rows));
  const nb = document.createElement("button");
  nb.type = "button"; nb.className = "show"; nb.textContent = "See the numbers";
  nb.onclick = () => openNumbers();
  $("ask-result").appendChild(nb);
  $("ask-result").appendChild(signBox(j));
}

async function loadShopText(text) {
  const bytes = new TextEncoder().encode(text);
  const p = sim.e.fg_alloc(bytes.length);
  new Uint8Array(sim.e.memory.buffer, p, bytes.length).set(bytes);
  if (sim.e.fg_load(p, bytes.length) !== 0) throw new Error(readJson().error);
  if (pool) await Promise.all(pool.list.map(() => runJob({ load: text })));
}

async function showArm(j, k) {
  const arm = j.report.arms[k];
  $("runnote").textContent = `Loading “${arm.name}” onto the floor…`;
  try {
    const text = await fetch(arm.shop_url).then(r => (r.ok ? r.text() : Promise.reject(new Error("the helper has no such setup"))));
    for (const g of ASK.extra) delete sim.area[g];
    ASK.extra = [];
    for (const [g, a] of arm.extra_areas) { sim.area[g] = a; ASK.extra.push(g); }
    await loadShopText(text);
    const rc = FabAsk.ruleCode(arm);
    $("rule").value = rc.code < 3 ? String(rc.code) : "0";
    const run = simulate({ seed: 0, days: 3, rule: rc.code, downGroup: -1, downAt: 0, downHours: 0 });
    setFloor(run);
    fit();
    ASK.onFloor = arm.name;
    $("runnote").innerHTML = `On the floor: <b>${esc(arm.name)}</b>, seed 0, first 3 days.${rc.exact ? "" : " The page's simulator cannot run this candidate's rule, so it uses today's rule."} Prototype lots are pink. <button type="button" class="link" id="back-today">Back to today's fab</button>`;
    $("back-today").onclick = backToToday;
  } catch (err) {
    $("runnote").textContent = "Could not show it: " + err.message;
  }
}

async function backToToday() {
  for (const g of ASK.extra) delete sim.area[g];
  ASK.extra = [];
  const text = await fetch("data/shop.txt").then(r => r.text());
  await loadShopText(text);
  $("rule").value = "0";
  const run = simulate({ seed: 0, days: 3, rule: 0, downGroup: -1, downAt: 0, downHours: 0 });
  setFloor(run);
  fit();
  $("runnote").textContent = `Today's fab: simulated 3 days (${run.j.moves.toLocaleString()} moves) in ${run.secs.toFixed(2)} s, right here in your browser.`;
}


// ------------------------------------------------------------------ the redesigned chrome (docs/FLOOR-UI.md)
// The opening, the command bar (⌘K), lens chips, drawers for the tools, the numbers view and signing.

const UI = { lens: "day", sweep: null, metric: "profit", share: 4 };

let VP = null; // the part of the window a scene is drawn in; null for all of it
function floorPad() {
  if (VP) return { l: VP.x + 6, r: innerWidth - VP.x - VP.w + 6, t: 170, b: 175 };
  const wide = innerWidth > 900;
  return { l: wide && !$("compare").hidden ? 420 : 24, r: wide && !$("panel").hidden ? 340 : 24, t: 116, b: 86 };
}

function openDrawer(id, on = true) {
  $(id).hidden = !on;
  if (id === "compare") document.body.classList.toggle("drawer-left", on);
  if (id === "panel") $("panel-open").classList.toggle("on", on);
}

function closeOpening() {
  if (!document.body.classList.contains("opening-on")) return;
  document.body.classList.remove("opening-on");
  resize();
  fit();
}

// a question from the opening, the command bar or an example
function askFrom(q) {
  q = (q || "").trim();
  if (!q) return;
  closeOpening();
  showTab("ask");
  fit();
  $("ask-q").value = q;
  if (ASK.helper) ask(q);
  else stage("To ask a question, start the helper on this Mac. In the fab-gym folder, run python3 -m agent.helper.");
}

async function chromeSetup() {
  let st = null, bundled = [];
  try { st = await api("/api/status"); if (st.error) st = null; } catch { st = null; }
  try { bundled = await fetch("data/examples.json").then(r => r.json()); } catch { bundled = []; }
  const o = FabUI.openingState(st, bundled);
  $("open-title").textContent = o.prompt;
  $("open-explore").textContent = o.explore;
  $("open-examples").innerHTML = o.examples.map((q, i) => `<button type="button" data-i="${i}">${esc(q)}</button>`).join("");
  $("open-examples").querySelectorAll("button").forEach(b => (b.onclick = () => askFrom(o.examples[+b.dataset.i])));
  $("open-form").onsubmit = e => { e.preventDefault(); askFrom($("open-q").value); };
  $("open-explore").onclick = closeOpening;
  setTimeout(() => $("open-q").focus(), 60);

  $("cmd").onsubmit = e => { e.preventDefault(); askFrom($("cmd-q").value); $("cmd-q").value = ""; $("cmd-q").blur(); };
  addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (document.body.classList.contains("opening-on")) $("open-q").focus();
      else { $("numbers").hidden = true; $("cmd-q").focus(); }
    } else if (e.key === "Escape") {
      if (!$("numbers").hidden) $("numbers").hidden = true;
      else if (document.activeElement === $("cmd-q")) $("cmd-q").blur();
    }
  });
  document.querySelectorAll("[data-close]").forEach(b => (b.onclick = () => {
    const id = b.dataset.close;
    if (id === "numbers") $("numbers").hidden = true;
    else { openDrawer(id, false); fit(); }
  }));
  $("panel-open").onclick = () => { openDrawer("panel", $("panel").hidden); fit(); };
  $("ask-open").onclick = () => { showTab("ask"); fit(); $("ask-q").focus(); };
  $("numbers-open").onclick = () => openNumbers();
  document.querySelectorAll(".lenses button").forEach(b => (b.onclick = () => {
    UI.lens = b.dataset.lens;
    FLOW.secs = 0;
    document.querySelectorAll(".lenses button").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
  }));
  document.querySelectorAll("#num-metric button").forEach(b => (b.onclick = () => { UI.metric = b.dataset.m; drawNumbers(); }));
  document.querySelectorAll("#num-share button").forEach(b => (b.onclick = () => { UI.share = +b.dataset.s; drawNumbers(); }));
}

// The Flows view: one wafer's whole route replayed on the track. A lot runs from hall to hall along the spine with
// a glowing tail; every stretch of track brightens each time it passes, so the map fills from nothing. Slow at first,
// faster later (FabUI.journeyDone); after a pause it starts again.
const FLOW = { secs: 0, T: 36, hold: 8, key: null, trips: [], route: "", steps: 0, sOf: [], fin: null, finMax: 1, feedFin: [], feedMax: 1 };
const FLOW_BINS = 260;

function flowSetup() {
  const routes = HALLS_L.routes || [];
  const key = HALLS_L;
  if (FLOW.key === key) return FLOW.trips.length > 0;
  FLOW.key = key;
  const k = Math.max(0, routes.findIndex(([name]) => /(^|_)3$/.test(name)));
  const [name, steps] = routes[k] || ["", []];
  FLOW.route = name.replace(/^part_/, "product ");
  FLOW.steps = steps.length;
  FLOW.trips = FabUI.journey(steps, HALLS_L.hallOfGroup);
  FLOW.sOf = HALLS_L.map((_, i) => G.s(i));
  FLOW.fin = FabUI.ringUse(FLOW.trips.map(tr => [FLOW.sOf[tr.a], FLOW.sOf[tr.b]]), G.ring, FLOW_BINS);
  FLOW.finMax = Math.max(1, ...FLOW.fin);
  FLOW.feedFin = HALLS_L.map(() => 0);
  for (const tr of FLOW.trips) { FLOW.feedFin[tr.a]++; FLOW.feedFin[tr.b]++; }
  FLOW.feedMax = Math.max(1, ...FLOW.feedFin);
  return FLOW.trips.length > 0;
}

function flowNow() {
  const N = FLOW.trips.length, cyc = FLOW.T + FLOW.hold;
  const secs = FLOW.secs % cyc;
  const done = FabUI.journeyDone(N, secs, FLOW.T);
  return { N, done, finished: done >= N };
}

function flowColor(f, a) {
  // dim violet for a stretch passed once, bright pink-white for the busiest
  const r = Math.round(150 + 105 * f), g = Math.round(90 + 140 * f * f), b = Math.round(200 + 45 * f);
  return `rgba(${r},${g},${b},${a})`;
}

function drawFlows() {
  if (!flowSetup()) return;
  const s = view.s, { N, done, finished } = flowNow();
  const n = Math.floor(done), u = done - n;
  // track use so far: the finished trips and the part of the current one already run
  const pairs = FLOW.trips.slice(0, n).map(tr => [FLOW.sOf[tr.a], FLOW.sOf[tr.b]]);
  const curTrip = !finished && n < N ? FLOW.trips[n] : null;
  if (curTrip) {
    const sa = FLOW.sOf[curTrip.a];
    let d = FLOW.sOf[curTrip.b] - sa;
    if (d <= 0) d += G.ring;
    pairs.push([sa, sa + d * Math.min(1, u * 1.15)]);
  }
  const use = FabUI.ringUse(pairs, G.ring, FLOW_BINS);
  const bw = G.ring / FLOW_BINS;
  // each hall fills with pink by how often the wafer has come to it so far
  const feed = HALLS_L.map(() => 0);
  for (let k = 0; k < n; k++) { feed[FLOW.trips[k].a]++; feed[FLOW.trips[k].b]++; }
  HALLS_L.forEach((h, i) => {
    if (!feed[i]) return;
    const p = G.pos[i], f = feed[i] / FLOW.feedMax, [X, Y] = W(p.x, p.y);
    ctx.fillStyle = `rgba(255,138,216,${(0.06 + 0.42 * f).toFixed(3)})`;
    ctx.fillRect(X, Y, h.w * s, h.h * s);
  });
  ctx.lineCap = "butt";
  for (let i = 0; i < FLOW_BINS; i++) {
    if (use[i] <= 0) continue;
    const f = Math.sqrt(use[i] / FLOW.finMax);
    const [x0, y0] = ringPoint(i * bw), [x1, y1] = ringPoint(Math.min((i + 1) * bw, G.ring - 1e-6));
    const [X0, Y0] = W(x0, y0), [X1, Y1] = W(x1, y1);
    if (Math.hypot(X1 - X0, Y1 - Y0) > bw * s * 1.5) continue; // a bin across a corner: skip the chord
    ctx.beginPath(); ctx.moveTo(X0, Y0); ctx.lineTo(X1, Y1);
    ctx.strokeStyle = flowColor(f, 0.25); ctx.lineWidth = Math.max(14, (3 + 10 * f) * s); ctx.stroke();
    ctx.strokeStyle = flowColor(f, 0.95); ctx.lineWidth = Math.max(4, (1 + 4.5 * f) * s); ctx.stroke();
  }
  // the feeders into each hall, by trips in and out so far
  HALLS_L.forEach((h, i) => {
    if (!feed[i]) return;
    const p = G.pos[i], by = p.belt === "top" ? G.yTop : G.yBot, f = Math.sqrt(feed[i] / FLOW.feedMax);
    const [X0, Y0] = W(p.door.x, p.door.y), [X1, Y1] = W(p.door.x, by);
    ctx.beginPath(); ctx.moveTo(X0, Y0); ctx.lineTo(X1, Y1);
    ctx.strokeStyle = flowColor(f, 0.95); ctx.lineWidth = Math.max(3, (0.8 + 3.5 * f) * s); ctx.stroke();
  });
  // chevrons drifting clockwise along the lit track, so the direction reads at a glance
  const phase = (FLOW.secs * 0.6) % 1, gapBins = 6, half = Math.max(3, 0.7 * s);
  ctx.strokeStyle = "rgba(255,240,250,0.85)"; ctx.lineWidth = Math.max(1.5, 0.3 * s);
  ctx.beginPath();
  for (let i = 0; i < FLOW_BINS; i += gapBins) {
    if (use[i] <= 0) continue;
    const at = (i + phase * gapBins) * bw;
    const [x, y] = ringPoint(at), [xn, yn] = ringPoint(at + 0.5);
    const len = Math.hypot(xn - x, yn - y) || 1, dx = (xn - x) / len, dy = (yn - y) / len;
    const [X, Y] = W(x, y);
    ctx.moveTo(X - dx * half - dy * half, Y - dy * half + dx * half);
    ctx.lineTo(X, Y);
    ctx.lineTo(X - dx * half + dy * half, Y - dy * half - dx * half);
  }
  ctx.stroke();
  if (!curTrip) return;
  // the two halls of the current trip, outlined
  for (const i of [curTrip.a, curTrip.b]) {
    const p = G.pos[i], h = HALLS_L[i], [X, Y] = W(p.x, p.y);
    ctx.strokeStyle = i === curTrip.b ? "rgba(255,138,216,0.95)" : "rgba(255,138,216,0.45)";
    ctx.lineWidth = Math.max(2, 0.7 * s);
    ctx.strokeRect(X, Y, h.w * s, h.h * s);
  }
  // the wafer: a comet with a fading tail along the track
  const tr = [0, 1, curTrip.a, curTrip.b];
  for (let k = 30; k >= 1; k--) {
    const [x, y] = tripPoint(tr, Math.max(0, u - k * 0.009));
    const [X, Y] = W(x, y);
    ctx.beginPath(); ctx.arc(X, Y, Math.max(3, (2.4 - k * 0.06) * s), 0, 2 * Math.PI);
    ctx.fillStyle = `rgba(255,${180 + Math.round(60 * (1 - k / 31))},240,${(0.6 * (1 - k / 31)).toFixed(3)})`; ctx.fill();
  }
  const [hx, hy] = tripPoint(tr, u);
  const [HX, HY] = W(hx, hy);
  ctx.beginPath(); ctx.arc(HX, HY, Math.max(14, 5 * s), 0, 2 * Math.PI); ctx.fillStyle = "rgba(255,138,216,0.3)"; ctx.fill();
  FLOW.wafer = true;
  drawLot(HX, HY, Math.max(10, 2.6 * s), false, true);
  FLOW.wafer = false;
}

function flowNote() {
  if (!flowSetup()) return "";
  const { N, done, finished } = flowNow();
  const name = i => HALLS_L[i].name;
  if (!finished) {
    const tr = FLOW.trips[Math.min(N - 1, Math.floor(done))];
    return `One wafer of ${FLOW.route} rides the track from hall to hall, step ${tr.step + 1} of ${FLOW.steps}: ${name(tr.a)} to ${name(tr.b)}. ` +
      `The track glows brighter each time the wafer passes, and the arrows show the way it runs.`;
  }
  const visits = HALLS_L.map(() => 0);
  for (const tr of FLOW.trips) visits[tr.b]++;
  const top = visits.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 3);
  return `On its ${FLOW.steps} steps, one wafer of ${FLOW.route} makes ${N} trips between halls. It comes back to ${name(top[0][1])} ${top[0][0]} times, ` +
    `${name(top[1][1])} ${top[1][0]} and ${name(top[2][1])} ${top[2][0]}: the pinker the hall, the more often the wafer returns. ` +
    `On the SMT2020 model. The replay starts again in a moment.`;
}

// ------------------------------------------------------------------ the numbers

const FLOOR_WORDS = { "D1 share": "Shared floor", "D2 wing": "Prototype wing", "D3 copies": "Copies in the halls" };
const POLICY_WORDS = { "P0 today": "today's order", "P1 family B first": "prototypes first", "P2 family cap": "prototypes capped at the door",
  "P3 reservation": "a tool kept for prototypes", "P4 qualification": "prototypes on half the tools" };
const METRIC = {
  profit: { name: "Operating profit a day", unit: "dollars a day", higher: true, base: v => FabUI.usd(v), tick: v => FabUI.usd(v) },
  a_wafers: { name: "Volume wafers a day", unit: "wafers a day", higher: true, base: v => fmtN(v, 0) },
  b_cycle: { name: "Prototype cycle time", unit: "days", higher: false, base: v => fmtN(v, 1) },
};
const LINE_COLORS = ["#7EE8D8", "#FF8AD8", "#FFC857", "#7F9CFF"];
const VERDICT_COLOR = { better: "#4FE3A3", worse: "#FF6262", "no clear effect": "#8FB3AE" };

function fmtN(v, d = 1) { return v === null || v === undefined ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }

async function openNumbers() {
  closeOpening();
  $("numbers").hidden = false;
  if (!UI.sweep) {
    try {
      UI.sweep = await fetch("data/two-families.json").then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))));
      if (UI.sweep.pl) UI.sweep = FabUI.withPl(UI.sweep, UI.sweep.pl);
    }
    catch (err) { $("num-lead").textContent = "The sweep's results are not in this build (run web/build.sh)."; return; }
  }
  drawNumbers();
  $("numbers").querySelector(".close").focus();
}

// a forest plot: one row per change, the mean as a dot, the 95% interval as a bar, the exact numbers on the right
function forestSVG(rows, m, xTitle) {
  const vals = rows.flatMap(r => (r.group || r.mean === null || r.mean === undefined ? [] : [r.lo, r.hi, r.mean])).concat([0]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const padV = (hi - lo) * 0.06 || 1; lo -= padV; hi += padV;
  const ticks = FabUI.niceTicks(lo, hi);
  lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
  const W0 = 760, L = 210, R = 196, top = 30, rh = 22;
  const lines = [];
  let y = top;
  const rowsY = rows.map(r => { if (r.group) y += 8; const yy = y; y += rh; return yy; });
  const H = y + 64;
  const X = v => L + ((v - lo) / (hi - lo)) * (W0 - L - R);
  // gridlines and ticks
  for (const t of ticks) {
    lines.push(`<line x1="${X(t)}" x2="${X(t)}" y1="${top - 4}" y2="${y + 2}" stroke="${t === 0 ? "#A9C4C0" : "#1A2E35"}" stroke-width="${t === 0 ? 1.5 : 1}"/>`);
    lines.push(`<text x="${X(t)}" y="${y + 18}" fill="#A9C4C0" font-size="11" text-anchor="middle">${(m.tick || FabUI.tickLabel)(t)}</text>`);
  }
  lines.push(`<line x1="${L}" x2="${W0 - R}" y1="${y + 2}" y2="${y + 2}" stroke="#2C5560"/>`);
  rows.forEach((r, i) => {
    const yy = rowsY[i] + rh / 2;
    if (r.group) {
      lines.push(`<text x="4" y="${yy + 4}" fill="#E8F2F0" font-size="12" font-weight="700">${esc(r.group)}</text>`);
      return;
    }
    lines.push(`<text x="16" y="${yy + 4}" fill="#A9C4C0" font-size="12">${esc(r.label)}</text>`);
    if (r.mean === null) {
      lines.push(`<text x="${X(0) + 8}" y="${yy + 4}" fill="#8FB3AE" font-size="11" font-style="italic">${esc(r.text)}</text>`);
      return;
    }
    const c = VERDICT_COLOR[r.verdict];
    lines.push(`<line x1="${X(r.lo)}" x2="${X(r.hi)}" y1="${yy}" y2="${yy}" stroke="${c}" stroke-width="4" stroke-linecap="round" opacity="0.55"/>`);
    lines.push(`<circle cx="${X(r.mean)}" cy="${yy}" r="5" fill="${c}" stroke="#0A1418" stroke-width="1.5"><title>${esc(r.label)}: ${esc(r.text)}, ${r.verdict}</title></circle>`);
    lines.push(`<text x="${W0 - R + 12}" y="${yy + 4}" fill="${r.verdict === "no clear effect" ? "#A9C4C0" : c}" font-size="11" font-family="ui-monospace, Menlo, monospace">${esc(r.text)}</text>`);
  });
  // axis titles
  const better = m.higher ? "better →" : "← better";
  lines.push(`<text x="${(L + W0 - R) / 2}" y="${y + 38}" fill="#E8F2F0" font-size="12" text-anchor="middle" font-weight="600">${esc(xTitle)}</text>`);
  lines.push(`<text x="${m.higher ? W0 - R : L}" y="${y + 54}" fill="#8FB3AE" font-size="11" text-anchor="${m.higher ? "end" : "start"}">${better}</text>`);
  lines.push(`<text x="4" y="14" fill="#E8F2F0" font-size="12" font-weight="600">Floor and policy</text>`);
  lines.push(`<text x="${W0 - R + 12}" y="14" fill="#E8F2F0" font-size="12" font-weight="600">Mean (95% interval)</text>`);
  return { svg: lines.join(""), w: W0, h: H };
}

// the shared-floor policies across prototype orders: change against today with intervals
function linesSVG(lines, m, share) {
  const W0 = 520, L = 64, R = 16, top = 14, B = 54, H = 330;
  const shares = lines[0].points.map(p => p.share);
  const vals = lines.flatMap(l => l.points.flatMap(p => (p.mean === null ? [] : [p.lo, p.hi]))).concat([0]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const ticks = FabUI.niceTicks(lo, hi);
  lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
  const X = i => L + 20 + (i / (shares.length - 1)) * (W0 - L - R - 40);
  const Y = v => top + (1 - (v - lo) / (hi - lo)) * (H - top - B);
  const out = [];
  const si = shares.indexOf(share);
  if (si >= 0) out.push(`<rect x="${X(si) - 18}" y="${top}" width="36" height="${H - top - B}" fill="rgba(126,232,216,0.07)" rx="6"/>`);
  for (const t of ticks) {
    out.push(`<line x1="${L}" x2="${W0 - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="${t === 0 ? "#A9C4C0" : "#1A2E35"}" stroke-width="${t === 0 ? 1.5 : 1}"/>`);
    out.push(`<text x="${L - 8}" y="${Y(t) + 4}" fill="#A9C4C0" font-size="11" text-anchor="end">${(m.tick || FabUI.tickLabel)(t)}</text>`);
  }
  shares.forEach((s, i) => out.push(`<text x="${X(i)}" y="${H - B + 18}" fill="#A9C4C0" font-size="11.5" text-anchor="middle">×${s}</text>`));
  out.push(`<line x1="${L}" x2="${L}" y1="${top}" y2="${H - B}" stroke="#2C5560"/><line x1="${L}" x2="${W0 - R}" y1="${H - B}" y2="${H - B}" stroke="#2C5560"/>`);
  lines.forEach((l, k) => {
    const c = LINE_COLORS[k % LINE_COLORS.length], dx = (k - 1.5) * 5;
    const pts = l.points.map((p, i) => (p.mean === null ? null : [X(i) + dx, Y(p.mean), p]));
    const d = pts.filter(Boolean).map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
    out.push(`<path d="${d}" fill="none" stroke="${c}" stroke-width="2"/>`);
    for (const q of pts) if (q) {
      const [x, yv, p] = q;
      out.push(`<line x1="${x}" x2="${x}" y1="${Y(p.lo)}" y2="${Y(p.hi)}" stroke="${c}" stroke-width="2" opacity="0.6"/>`);
      out.push(`<circle cx="${x}" cy="${yv}" r="3.5" fill="${c}"><title>${esc(POLICY_WORDS[l.policy])} at ×${p.share}: ${(m.tick || fmtN)(p.mean)} (${(m.tick || fmtN)(p.lo)} to ${(m.tick || fmtN)(p.hi)})</title></circle>`);
    }
  });
  out.push(`<text x="${(L + W0 - R) / 2}" y="${H - 14}" fill="#E8F2F0" font-size="12" text-anchor="middle" font-weight="600">Prototype orders, times today's</text>`);
  out.push(`<text transform="translate(16 ${(top + H - B) / 2}) rotate(-90)" fill="#E8F2F0" font-size="12" text-anchor="middle" font-weight="600">Change against today, ${esc(m.unit)}</text>`);
  return { svg: out.join(""), w: W0, h: H };
}

function setSVG(el, o, label) {
  el.setAttribute("viewBox", `0 0 ${o.w} ${o.h}`);
  el.setAttribute("aria-label", label);
  el.innerHTML = o.svg;
}

function drawNumbers() {
  const d = UI.sweep;
  if (!d) return;
  const m = METRIC[UI.metric], share = UI.share;
  document.querySelectorAll("#num-metric button").forEach(b => b.classList.toggle("on", b.dataset.m === UI.metric));
  document.querySelectorAll("#num-share button").forEach(b => b.classList.toggle("on", +b.dataset.s === share));
  const k = Math.round(0.05 / d.alpha_each);
  $("num-lead").textContent = `The two-family sweep on the SMT2020 model. Each change ran for ${d.days} simulated days after ${d.warmup} days of warm-up, on ${d.seeds.length} seeds, ` +
    `and is compared with today's fab on the same seeds. Today's fab means one shared floor and today's dispatch order. ` +
    `Each interval is set at 1 − 0.05/${k}, so all ${k} hold together at 95%. Every price is assumed: see How money is counted below. What these changes would do in a real fab is unknown.`;
  const base = { ...(d.baseline[String(share)] || {}), profit: d.plToday && d.plToday[String(share)] ? d.plToday[String(share)].profit : null };
  $("num-base").innerHTML = Object.entries(METRIC).map(([key, mm]) =>
    `<div class="fact${key === UI.metric ? " on" : ""}"><div class="v">${mm.base(base[key])}</div><div class="l">Today's fab with ×${share} prototype orders: ${mm.name.toLowerCase()} (${mm.unit})</div></div>`).join("");
  // the forest: rows grouped by floor
  const rows = [];
  let last = null;
  for (const r of FabUI.sweepRows(d, share, UI.metric)) {
    if (r.strategy !== last) { rows.push({ group: FLOOR_WORDS[r.strategy] }); last = r.strategy; }
    rows.push({ ...r, label: POLICY_WORDS[r.policy] });
  }
  const f = forestSVG(rows, m, `Change against today's fab, ${m.unit}`);
  $("num-forest-t").innerHTML = `${esc(m.name)}: every change at ×${share} prototype orders<span>Each dot is the average paired difference and each bar is its interval. Green is better, red is worse and grey is no clear effect.</span>`;
  setSVG($("num-forest"), f, `${m.name}, every change against today at ×${share}`);
  const ls = FabUI.sweepLines(d, UI.metric);
  setSVG($("num-lines"), linesSVG(ls, m, share), `${m.name} on the shared floor across prototype orders`);
  $("num-lines-t").innerHTML = `${esc(m.name)} on the shared floor as prototype orders grow<span>Each line is one policy compared with today's order at the same share of prototype orders. The bars are the intervals.</span>`;
  $("num-lines-key").innerHTML = ls.map((l, i) => `<span><i style="background:${LINE_COLORS[i]}"></i>${esc(POLICY_WORDS[l.policy])}</span>`).join("");
  // the question being answered, when there is one
  const j = ASK.job;
  const qkey = UI.metric === "b_cycle" ? "b_cycle_days" : UI.metric;
  const priced = UI.metric !== "profit" || (j && j.report && j.report.candidates && j.report.candidates.some(c => c.measures && c.measures.profit));
  if (j && j.stage === "done" && j.report && j.report.families && priced) {
    const qrows = FabAsk.resultRows(j.report).map(r => {
      const c = r.cells.find(x => x.key === qkey) || {};
      const has = c.mean !== null && c.mean !== undefined && c.lo !== null;
      return { label: r.name, mean: has ? c.mean : null, lo: has ? c.lo : null, hi: has ? c.hi : null, verdict: c.verdict || "no clear effect",
        text: has ? `${FabUI.tickLabel(Math.round(c.mean * 10) / 10)} (${FabUI.tickLabel(Math.round(c.lo * 10) / 10)} to ${FabUI.tickLabel(Math.round(c.hi * 10) / 10)})` : "no prototype lot out" };
    });
    const q = forestSVG(qrows, m, `Change against today's fab, ${m.unit}`);
    $("num-question").innerHTML = `<figure><figcaption>Your question: ${esc(j.question || "a written scenario")}<span>${esc(m.name)}: each candidate compared with today's fab on ${j.report.seeds.length} paired seeds. The intervals hold together at 95%.</span></figcaption><svg role="img"></svg></figure>`;
    setSVG($("num-question").querySelector("svg"), q, `${m.name} for each candidate in your question`);
  } else $("num-question").innerHTML = "";
  $("num-note").textContent = `Operating profit a day is revenue less materials, running costs and depreciation, in dollars. Capital, payback and the five-year value count what a change buys: tools, their qualification, floor space and, for a wing, a building and a bridge. Every price is assumed. Simulated on the SMT2020 model (Kopp, Hassoun, Kalir, Mönch 2020), a published research model of a wafer fab. No real fab's data is used.`;
  drawCapital(d, share);
}

// what each change buys and when it pays back, at one share of prototype orders (docs/MONEY-PL.md)
function paybackText(p) {
  const words = x => (x < 1 ? "at once" : x < 60 ? `${Math.round(x)} days` : `${(x / 30.4).toFixed(x < 365 ? 0 : 1).replace(/\.0$/, "")} months`);
  if (!p || p.soonest === null) return "never";
  if (p.latest === null) return `${words(p.soonest)}, or never`;
  return p.soonest === p.latest ? words(p.soonest) : `${words(p.soonest)} to ${words(p.latest)}`;
}
function drawCapital(d, share) {
  const el = $("num-capital");
  if (!d.pl) { el.innerHTML = ""; return; }
  const rows = FabUI.sweepRows(d, share, "profit").map(r => {
    const c = d.cells.find(x => x.share === share && x.strategy === r.strategy && x.policy === r.policy);
    return { r, p: c && c.pl };
  }).filter(x => x.p);
  const U = FabUI.usd;
  const body = rows.map(({ r, p }) => `<tr><td>${esc(FLOOR_WORDS[r.strategy])}, ${esc(POLICY_WORDS[r.policy])}</td>` +
    `<td class="v">${p.capital ? U(p.capital) : "none"}</td><td class="v">${U(p.cash.mean, true)}</td>` +
    `<td class="v">${p.capital ? paybackText(p.payback_days) : p.cash.lo > 0 ? "no capital needed" : "—"}</td>` +
    `<td class="v">${U(p.npv.mean, true)} <span class="iv">(${U(p.npv.lo, true)} to ${U(p.npv.hi, true)})</span></td>` +
    `<td><span class="pill ${r.verdict === "no clear effect" ? "unclear" : r.verdict}">${r.verdict}</span></td></tr>`).join("");
  const ck = (d.pl.checks || []).find(x => x.share === share);
  let check = "";
  if (ck) {
    const name = `${FLOOR_WORDS[ck.strategy].toLowerCase()} with ${POLICY_WORDS[ck.policy]}`;
    const item = k => (d.pl.sheet.find(x => x.key === k) || {}).label || k;
    const moves = ck.items.flatMap(it => [["low", it.low], ["high", it.high]].filter(([, v]) => v.verdict !== ck.verdict).map(([end, v]) => `${item(it.key)} at its ${end} value (${v.verdict})`));
    check = `<p class="note">The best change here is the ${esc(name)}, ${esc(ck.verdict)} on operating profit. ` +
      (moves.length ? `Its verdict changes with ${esc(moves.join("; "))}. Every other price can move to its low or high value and the verdict holds.`
        : "Its verdict holds when any one price moves to its low or high value.") + "</p>";
  }
  const sheet = FabUI.priceSheetRows(d.pl).map(r => `<tr><td>${esc(r.label)}</td><td class="v">${esc(r.central)}</td><td class="v">${esc(r.range)}</td><td>${r.note}</td></tr>`).join("");
  el.innerHTML = `<h4>What each change buys at ×${share} prototype orders</h4>` +
    `<table class="captab"><thead><tr><th>Floor and policy</th><th>Capital</th><th>Change in cash a day</th><th>Pays back in</th><th>Value over 5 years</th><th>Profit</th></tr></thead><tbody>${body}</tbody></table>` +
    check +
    `<details class="sheet"><summary>How money is counted: the price sheet</summary><table class="captab"><thead><tr><th>Item</th><th>Used</th><th>Range tried</th><th></th></tr></thead><tbody>${sheet}</tbody></table>` +
    `<p class="note small">Today's tools already run the prototype route, so only new tools are qualified. Copies in the halls use spare space there; a wing is a new building. The value over 5 years discounts each day's cash at 10% a year and subtracts the capital.</p></details>`;
}

// ------------------------------------------------------------------ the evidence: verdict cards and signing

function verdictCards(rows) {
  const best = rows.find(r => r.best) || rows[0];
  if (!best) return "";
  return `<p class="note">${esc(best.name)} compared with today's fab:</p><div class="verdicts">${best.cells.map(c => {
    const v = c.mean === null ? "no clear effect" : c.verdict;
    return `<div class="vcard ${v === "no clear effect" ? "" : v}"><div class="l">${esc(c.label)}</div><div class="v">${c.mean === null ? "—" : FabUI.tickLabel(Math.round(c.mean * 10) / 10)}</div>` +
      `<div class="iv">${c.lo === null || c.mean === null ? "" : `${fmtN(c.lo)} to ${fmtN(c.hi)}`}</div><span class="pill ${v === "no clear effect" ? "unclear" : v}">${v}</span></div>`;
  }).join("")}</div>`;
}

function signedCard(card) {
  return `<div class="signed"><b>Signed by ${esc(card.name)}</b> at ${esc(card.at)}<br><span class="note">SHA-256 of the question, the scenario and the report:</span><br>` +
    `<code>question ${esc(card.sha256.question.slice(0, 16))}…</code><br><code>scenario ${esc(card.sha256.scenario.slice(0, 16))}…</code><br><code>report ${esc(card.sha256.report.slice(0, 16))}…</code></div>`;
}

function signBox(j) {
  const box = document.createElement("div");
  if (j.card) { box.innerHTML = signedCard(j.card); return box; }
  box.className = "sign";
  box.innerHTML = `<h4>Sign this answer</h4><p class="note">The model proposed this answer and the simulator scored it. Now a person signs it. Your name, the time and a SHA-256 fingerprint of the question, scenario and report are saved with it on this Mac.</p>` +
    `<form><label class="sr" for="sign-name">Your name</label><input id="sign-name" placeholder="Your name" autocomplete="name"><button class="primary" style="width:auto;margin:0">Sign</button></form><p class="note" id="sign-msg"></p>`;
  box.querySelector("form").onsubmit = async e => {
    e.preventDefault();
    const r = await api("/api/sign", { job: j.id, name: box.querySelector("input").value });
    if (r.signed) { j.card = r.card; box.className = ""; box.innerHTML = signedCard(r.card); }
    else box.querySelector("#sign-msg").textContent = r.error || "Could not sign.";
  };
  return box;
}

// ------------------------------------------------------------------ side by side (docs/FLOOR-UI.md, part 4)
// Today's fab on the left, a candidate on the right, both from seed 0 on one clock and one scrubber, with the
// candidate's verdict cards beneath. Each half keeps its own camera.

const SPLIT = { on: false, building: false, fitting: false, scenes: [], clock: null, active: 0, job: null, name: "" };

function useScene(k) {
  if (!SPLIT.on) return;
  const sc = SPLIT.scenes[k];
  G = sc.G; HALLS_L = sc.HALLS_L; P = sc.P; cur = sc.cur; VP = sc.vp;
  Object.assign(view, sc.view);
  SPLIT.active = k;
}
function keepScene() {
  if (SPLIT.on) Object.assign(SPLIT.scenes[SPLIT.active].view, view);
}
function splitPick(x) {
  if (SPLIT.on) useScene(x < SPLIT.scenes[1].vp.x ? 0 : 1);
}

function layoutSplit() {
  VP = null;
  const pad = floorPad();
  const l = pad.l - 10, r = innerWidth - pad.r + 10, mid = (l + r) / 2;
  SPLIT.scenes[0].vp = { x: l, y: 0, w: mid - l, h: innerHeight };
  SPLIT.scenes[1].vp = { x: mid, y: 0, w: r - mid, h: innerHeight };
  SPLIT.fitting = true;
  for (const k of [0, 1]) { useScene(k); fit(); keepScene(); }
  SPLIT.fitting = false;
  const c = $("split-cards");
  c.style.left = `${(l + r) / 2}px`;
  c.style.width = `${Math.min(640, r - l - 24)}px`;
}

async function sideBySide(j, k) {
  const arms = j.report.arms || [];
  const base = arms.findIndex(a => a.name === "today");
  if (base < 0 || !arms[k]) return;
  stage("Laying both out on the floor…");
  try {
    for (const g of ASK.extra) delete sim.area[g];
    ASK.extra = [];
    for (const i of [base, k]) for (const [g, a] of arms[i].extra_areas) { sim.area[g] = a; ASK.extra.push(g); }
    const runs = [];
    for (const i of [base, k]) {
      const text = await fetch(arms[i].shop_url).then(r => (r.ok ? r.text() : Promise.reject(new Error("the helper has no such setup"))));
      await loadShopText(text);
      const rc = FabAsk.ruleCode(arms[i]);
      runs.push({ name: arms[i].name, rc, run: simulate({ seed: 0, days: 3, rule: rc.code, downGroup: -1, downAt: 0, downHours: 0 }) });
    }
    SPLIT.building = true;
    const scenes = runs.map(r => { setFloor(r.run); return { G, HALLS_L, P, cur, view: { ...view }, name: r.name, rc: r.rc }; });
    SPLIT.building = false;
    SPLIT.scenes = scenes;
    SPLIT.on = true;
    SPLIT.job = j;
    SPLIT.name = arms[k].name;
    ASK.onFloor = arms[k].name;
    document.body.classList.add("split");
    layoutSplit();
    SPLIT.clock = FabUI.pairedClock(scenes[0].P.j.until, scenes[1].P.j.until);
    $("scrub").max = SPLIT.clock.end;
    t = 0; playing = true; $("play").textContent = "❚❚";
    const row = FabAsk.resultRows(j.report).find(r => r.name === arms[k].name);
    $("split-cards").hidden = false;
    $("split-cards").innerHTML = `<div class="split-head"><b>${esc(arms[k].name)}</b> compared with today's fab over ${j.report.seeds.length} paired seeds of the full run` +
      `<button type="button" class="link" id="split-leave">Leave side by side</button></div>` + (row ? verdictCards([row]).replace(/^<p class="note">.*?<\/p>/, "") : "") +
      `<p class="note small">Both halves replay seed 0 for 3 days in your browser.${scenes[1].rc.exact ? "" : " The page's simulator cannot run this candidate's rule, so its half uses today's rule."} The cards come from the helper's full scored run. On the SMT2020 model.</p>`;
    $("split-leave").onclick = () => leaveSplit(true);
    stage("");
  } catch (err) {
    SPLIT.building = false;
    stage("Could not lay them out: " + err.message);
  }
}

function leaveSplit(reload) {
  if (!SPLIT.on) return;
  useScene(1);
  SPLIT.on = false; SPLIT.scenes = []; VP = null;
  document.body.classList.remove("split");
  $("split-cards").hidden = true;
  if (reload) backToToday();
}

function splitFrame(dt) {
  const c = SPLIT.clock;
  if (playing) {
    t = Math.min(c.end, t + dt * speed);
    if (t >= c.end) playing = false, ($("play").textContent = "▶");
  }
  const times = c.at(t);
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawSky();
  for (const k of [0, 1]) {
    useScene(k);
    cur.seek(times[k]);
    let hb = 0;
    for (const q of P.groupTools[P.holdingGroup] || []) if (cur.toolState[q] === 0) hb++;
    cur.holdingBusy = hb;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.beginPath(); ctx.rect(VP.x, VP.y, VP.w, VP.h); ctx.clip();
    draw(false);
    ctx.restore();
    splitLabel(k, times[k]);
  }
  // the seam
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const x = SPLIT.scenes[1].vp.x;
  ctx.fillStyle = "rgba(126, 232, 216, 0.35)"; ctx.fillRect(x - 0.5, 140, 1, innerHeight - 330);
  useScene(1);
  hud();
  if (hover) { useScene(hover.scene || 0); showTip(hover); }
}

function splitLabel(k, tk) {
  const sc = SPLIT.scenes[k], vp = sc.vp;
  let waiting = 0;
  for (let g = 0; g < P.nG; g++) if (g !== P.holdingGroup) waiting += cur.queue[g];
  let protos = 0;
  for (const q of cur.bQ) protos += q;
  for (const tr of cur.active) if (tr[6]) protos++;
  const title = k === 0 ? "Today's fab" : sc.name;
  const line = `${countBelow(P.done, tk).toLocaleString()} lots finished · ${waiting.toLocaleString()} waiting · ${protos} prototype lots in the fab`;
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  ctx.font = "800 17px -apple-system, Inter, sans-serif";
  ctx.fillStyle = k === 0 ? LOOK.title : LOOK.proto;
  ctx.fillText(title, vp.x + vp.w / 2, 140);
  ctx.font = "500 12px ui-monospace, Menlo, monospace";
  ctx.fillStyle = LOOK.sub;
  ctx.fillText(line, vp.x + vp.w / 2, 162);
  ctx.textAlign = "left";
}

main();
