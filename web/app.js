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
const STATE_COLORS = [FabUI.PALETTE.working, FabUI.PALETTE.idle, FabUI.PALETTE.maintenance, FabUI.PALETTE.broken, FabUI.PALETTE.setup];
const STATE_NAMES = ["working", "idle", "maintenance", "broken down", "changing setup"];
const LOT = "#efe2c4", HOT = "#e8955a";
const TOOL = 3, PITCH = 4;
let TARGET_ASPECT = 1.8;

// ------------------------------------------------------------------ the simulator

const sim = { e: null, groups: [], tools: [], routes: [], lots: [] };

async function loadSim() {
  // the real building (docs/LIVE-REAL.md): when its data is here, today's fab is the US building with its fleet
  try { BUILDING = await fetch("data/building.json").then(r => (r.ok ? r.json() : null)); } catch { BUILDING = null; }
  sim.baseUrl = BUILDING ? "data/shop-real.txt" : "data/shop.txt";
  const [wasm, shopText, areasText] = await Promise.all([
    fetch("fabweb.wasm").then(r => r.arrayBuffer()),
    fetch(sim.baseUrl).then(r => (r.ok ? r.text() : fetch("data/shop.txt").then(x => x.text()))),
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
  if (e.fg_dials(d.breakdowns, d.repair, d.demand, d.hot, d.rework, d.cap || 0, d.defects || 0) !== 0) throw new Error(readJson().error);
  const t0 = performance.now();
  const rc = e.fg_run(opts.seed, opts.days, opts.rule, opts.downGroup, opts.downAt * 60, opts.downHours);
  const secs = (performance.now() - t0) / 1000;
  if (rc !== 0) throw new Error("the simulator did not run");
  const j = readJson();
  const trace = new Float64Array(e.memory.buffer, e.fg_trace_ptr(), e.fg_trace_len()).slice();
  const states = new Float64Array(e.memory.buffer, e.fg_states_ptr(), e.fg_states_len()).slice();
  const fleetE = e.fg_fleet_entries_len ? new Float32Array(e.memory.buffer, e.fg_fleet_entries_ptr(), e.fg_fleet_entries_len()).slice() : new Float32Array(0);
  const fleetH = e.fg_fleet_hoists_len ? new Float32Array(e.memory.buffer, e.fg_fleet_hoists_ptr(), e.fg_fleet_hoists_len()).slice() : new Float32Array(0);
  // the editor's moods for this run, every 30 minutes, from the same Rust code as `fabsim moods` (docs/FLOOR-LOOK.md)
  const moods = opts.moods !== false && e.fg_moods && e.fg_moods(MOOD_EVERY) === 0 ? readJson() : null;
  return { j, trace, states, secs, fleetE, fleetH, moods };
}
const MOOD_EVERY = 30;
/** A group's mood on the floor now (null before moods are in). */
function moodNow(g) {
  const m = P && P.moods;
  if (!m) return null;
  return FabLook.groupMood(m, Math.max(0, Math.min(m.frames.length - 1, Math.floor(t / MOOD_EVERY))), P.j.groups[g][0]);
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
  const lastStep = new Map(); // lot -> [step, end] of its latest recorded step
  for (let r = 0; r < nRows; r++) {
    const lot = trace[r * 6], tool = trace[r * 6 + 2], arrive = trace[r * 6 + 3], start = trace[r * 6 + 4], end = trace[r * 6 + 5];
    const ls = lastStep.get(lot);
    if (!ls || trace[r * 6 + 1] > ls[0]) lastStep.set(lot, [trace[r * 6 + 1], end]);
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
  // The run records a step only once it starts, so a lot still waiting when the run closes has no row for that wait.
  // It joins its next step's queue when its last step ends (or when it is released, before its first step) and is
  // still there at the close (docs/FLOOR-HEALTH.md).
  j.lots.forEach((l, lot) => {
    if (l[5] !== null) return;
    const steps = j.routes[l[1]][1], ls = lastStep.get(lot);
    const [at, next] = ls ? [ls[1], ls[0] + 1] : l[6] ? [null, 0] : [l[4], 0];
    if (at === null || at >= j.until || next >= steps.length) return;
    qe.push([at, steps[next], 1, lotHot[lot] && !lotB[lot] ? 1 : 0, lotB[lot]]);
  });
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
  // for the health panel (docs/FLOOR-HEALTH.md): step ends, releases (lots in the fab at the start count from -inf),
  // and finished lots in time order with running sums of wafers and of cycle times (lots released during the run)
  // steps on machines and steps in storage (the Delay_32 group's slots are storage, not machines)
  const holdG = j.groups.findIndex(g => sim.area[g[0]] === "Delay_32");
  const mStart = [], mEnd = [], hStart = [], hEnd = [];
  for (let r = 0; r < nRows; r++) {
    const h = toolGroup[trace[r * 6 + 2]] === holdG;
    (h ? hStart : mStart).push(trace[r * 6 + 4]);
    (h ? hEnd : mEnd).push(trace[r * 6 + 5]);
  }
  for (const a of [mStart, mEnd, hStart, hEnd]) a.sort((x, y) => x - y);
  // each machine step's wait (arrival to start), in start order, with running sums: the mean wait per step so far
  const waitRows = [];
  for (let r = 0; r < nRows; r++) if (toolGroup[trace[r * 6 + 2]] !== holdG) waitRows.push([trace[r * 6 + 4], Math.max(0, trace[r * 6 + 4] - trace[r * 6 + 3])]);
  waitRows.sort((x, y) => x[0] - y[0]);
  const waitStart = waitRows.map(w => w[0]), waitSum = [0];
  for (const w of waitRows) waitSum.push(waitSum[waitSum.length - 1] + w[1]);
  const released = j.lots.map(l => (l[6] ? -Infinity : l[4])).sort((a, b) => a - b);
  const fin = j.lots.filter(l => l[5] !== null).sort((a, b) => a[5] - b[5]);
  const finWafers = [0], finCt = [0], finCtN = [0];
  for (const l of fin) {
    finWafers.push(finWafers[finWafers.length - 1] + l[3]);
    finCt.push(finCt[finCt.length - 1] + (l[6] ? 0 : l[5] - l[4]));
    finCtN.push(finCtN[finCtN.length - 1] + (l[6] ? 0 : 1));
  }
  // lots waiting over time, every 20 minutes, for the timeline
  const waitSeries = [];
  let k = 0, w = 0;
  for (let t = 0; t <= j.until; t += 20) {
    while (k < qe.length && qe[k][0] <= t) { w += qe[k][2]; k++; }
    waitSeries.push(w);
  }
  const real = G && G.real ? realPrepare(run, j, trace) : null;
  return { j, trace, states, nT, nG, qe, trips, starts, mStart, mEnd, hStart, hEnd, holdG, waitStart, waitSum, released, done, finWafers, finCt, finCtN, waitSeries, toolGroup, secs: run.secs, real, lotHot, lotB };
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

/** The time the cursor reads: never the run's closing instant, when the run's last events start every lot still
 * waiting, so the queues would read empty (docs/FLOOR-HEALTH.md). */
const seekTime = t => (P && t >= P.j.until ? P.j.until - 0.01 : t);

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
let BUILDING = null; // the real building (docs/LIVE-REAL.md), when its data is here
let HALLS_L = null;
let P = null, cur = null;
let t = 0, playing = true, speed = 60; // fab minutes per second
const MAX = -1; // the Max step: one fab hour each drawn frame (docs/EDITOR-SPEED.md)
const stepOf = dt => (speed === MAX ? 60 : dt * speed);
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
  $("fit").hidden = true; // Fit shows again once the view has moved (docs/SITE-CUTS.md)
  if (!G) return;
  if (SPLIT.on && !SPLIT.fitting) { layoutSplit(); return; }
  const pad = floorPad();
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  updateTilt();
  const M = 3; // the board's margin around the fab, in tiles (smaller: docs/FLOOR-CLEANUP.md, item 5)
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

// The look, in the spirit of factory-builder games and drawn here: concrete floors, yellow-railed belts with
// moving chevrons, machines as sprites with a state panel and a status light, lots as carrier boxes.
const LOOK = {
  sky0: "#16323A", sky1: "#0B1418", sky2: "#070C0F", boardSide: "#071013",
  ground: "#0F1D22", hallFloor: "#12262D", wall: "#2C5560", wallDark: "#0A1418", wallTop: "#7EE8D8",
  rail: FabUI.PALETTE.track, beltTop: "#1F3A42", chevron: "rgba(126, 232, 216, 0.7)", glow: "rgba(126, 232, 216, 0.07)",
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
  if (G.real) { drawReal(s); return; }
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
  const detail = FabUI.zoomDetail(s), showLabels = detail.names;
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
      ctx.fillStyle = FabUI.heatColor(a / 0.75);
      ctx.fillRect(HX, HY, (c.w - 0.6) * s, (c.h - 0.6) * s);
    }
  }
  const yLabel = cy + 1 + c.rows * PITCH;
  if (showLabels) {
    const [LX, LY] = W(cx + 1, yLabel + 0.2);
    ctx.textBaseline = "top";
    uprightText(P.plain[g], LX, LY, `500 ${1.5 * s}px -apple-system, Inter, sans-serif`, LOOK.label);
  }
  // the group's queue: a count chip at middle zoom, the belt with its lots when close (docs/FLOOR-CLEANUP.md)
  const detail = FabUI.zoomDetail(s);
  if (!detail.queues) {
    const n0 = cur.queue[g];
    if (detail.chips && n0 > 0) {
      const [X, Y] = W(cx + 1, yLabel + 2.2);
      ctx.textBaseline = "top";
      uprightText(`${n0} waiting`, X, Y, `600 ${Math.max(12, 1.3 * s)}px -apple-system, Inter, sans-serif`, LOOK.sub);
    }
    return;
  }
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
  // sized when drawn: sized on resize alone, it stayed 0 px wide when the Floor first showed behind Home (docs/FLOOR-REVIEW.md)
  const dpr = window.devicePixelRatio || 1, want = [Math.round(sp.clientWidth * dpr), Math.round(sp.clientHeight * dpr)];
  if (want[0] && (sp.width !== want[0] || sp.height !== want[1])) { sp.width = want[0]; sp.height = want[1]; }
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
  $("flow-ctl").hidden = UI.lens !== "flows" || !!(G && G.real);
  $("journey-ctl").hidden = UI.lens !== "flows" || !(G && G.real);
  if (JOURNEY.on && (UI.lens !== "flows" || !(G && G.real))) journeyStop();
  // the prototype view needs prototype lots in the fab
  let np = 0;
  for (const tr of cur.active) if (tr[6]) np++;
  for (const q of cur.bQ || []) np += q;
  // the prototypes button stands beside Follow only while prototype lots are in the fab (docs/SITE-CUTS.md)
  const pb = $("proto-open"), hide = np === 0 && UI.lens !== "proto";
  if (pb.hidden !== hide) pb.hidden = hide;
  if (UI.lens === "heat") txt = "Each tool group glows with the lots waiting at it. The brighter the glow, the longer the queue.";
  else if (UI.lens === "flows") txt = JOURNEY.on ? journeyNote() : G && G.real ? realFollowNote() : flowNote();
  else if (UI.lens === "proto") {
    let n = 0;
    for (const tr of cur.active) if (tr[6]) n++;
    for (const q of cur.bQ || []) n += q;
    txt = n ? (n === 1 ? "1 prototype lot is in the fab now. It is drawn large and pink, and everything else is dimmed." : `${n} prototype lots are in the fab now. They are drawn large and pink, and everything else is dimmed.`)
      : "Today's fab has no prototype lots. To see some, ask a question about prototypes and press “Show on the floor” on one of the answers.";
  }
  if (SPOT && SPOT.note) txt = SPOT.note; // what the glossary's Show me lit (docs/GLOSSARY-PLUS.md, part 2)
  $("lens-note").classList.toggle("spot-note", !!(SPOT && SPOT.note));
  if (txt !== lensShown) { $("lens-note").textContent = txt; lensShown = txt; }
}

function hud() {
  lensNote();
  const day = Math.floor(t / 1440) + 1;
  const m = Math.floor(t % 1440);
  $("day").textContent = `Day ${day}`;
  $("time").textContent = `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  renderHealth(health());
  renderCurves();
  { const sp = $("spark"); if (sp.clientWidth && sp.width !== Math.round(sp.clientWidth * (window.devicePixelRatio || 1))) drawSpark(); }
  $("scrub").value = t;
  ticker();
}

// ------------------------------------------------------------------ the fab's health (docs/FLOOR-HEALTH.md)

/** The fab at the cursor's time: output, lots in the fab and where they are, tools by state, availability, the longest
 * queue. Read from the run on screen; nothing is estimated. */
// the fab 24 hours earlier, for the comparisons (docs/FLOOR-REVIEW.md); its own cursor, moved forward with the clock
let curAgo = null;
/** Lots waiting (and the longest queue) and tool states by a cursor; the mean wait of machine steps started in the
 * hour up to tq. */
function readingsAt(c, tq) {
  let waiting = 0, longest = { g: -1, lots: 0 };
  for (let g = 0; g < P.nG; g++) {
    if (g === P.holdingGroup) continue;
    waiting += c.queue[g];
    if (c.queue[g] > longest.lots) longest = { g, lots: c.queue[g] };
  }
  const n = [0, 0, 0, 0, 0];
  let machines = 0;
  for (let k = 0; k < P.nT; k++) if (P.toolGroup[k] !== P.holdingGroup) { n[c.toolState[k]]++; machines++; }
  const n0 = countBelow(P.waitStart, tq - 60), n1 = countBelow(P.waitStart, tq);
  const waitHour = n1 > n0 ? (P.waitSum[n1] - P.waitSum[n0]) / (n1 - n0) : null;
  return { waiting, longest, n, machines, available: (machines - n[2] - n[3]) / machines, waitHour };
}

function health() {
  const tq = seekTime(t), nT = P.nT; // nT counts storage slots too
  const finished = countBelow(P.done, t);
  const day = t >= 1440 ? countBelow(P.done, t - 1440) : 0;
  const inFab = countBelow(P.released, tq) - countBelow(P.done, tq);
  const now = readingsAt(cur, tq), { waiting, longest } = now;
  let ago = null;
  if (t >= 1440) {
    if (!curAgo || curAgo.P !== P) { curAgo = makeCursor(P); curAgo.P = P; }
    curAgo.seek(seekTime(t - 1440));
    const y = readingsAt(curAgo, seekTime(t - 1440));
    ago = { waiting: y.waiting, available: y.available, waitHour: y.waitHour };
  }
  const resting = (P.holdingGroup >= 0 ? cur.queue[P.holdingGroup] : 0) + countBelow(P.hStart, tq) - countBelow(P.hEnd, tq);
  const processing = countBelow(P.mStart, tq) - countBelow(P.mEnd, tq);
  const moving = cur.active.length;
  // machines only: the storage group's slots are not tools
  const { n, machines } = now;
  const up = machines - n[2] - n[3];
  const ctN = P.finCtN[finished], nW = countBelow(P.waitStart, tq);
  return {
    t, finished, wafersOut: P.finWafers[finished], last24: finished - day, sinceStart: t < 1440,
    cycleDays: ctN ? P.finCt[finished] / ctN / 1440 : null,
    waitPerStep: nW ? P.waitSum[nW] / nW : null, stepsStarted: nW, waitHour: now.waitHour, ago,
    inFab, waiting, processing, moving, resting,
    tools: { working: n[0], idle: n[1], maintenance: n[2], down: n[3], setup: n[4] }, nT: machines,
    available: up / machines, busy: up ? n[0] / up : 0,
    longest: { g: longest.g, name: longest.g >= 0 ? P.plain[longest.g] : "", lots: longest.lots },
  };
}

// a row of the panel lights what it names (docs/FLOOR-REVIEW.md): { kind: "state", s } or { kind: "waiting" }
let SPOT = null;
// also { kind: "area", a: [areas] } and { kind: "hot" } from the glossary's Show me (docs/GLOSSARY-PLUS.md, part 2)
const areaOfToolK = k => FabLook.areaOf(sim.area[P.j.groups[P.toolGroup[k]][0]]);
function spotTool(k) {
  if (!SPOT || k < 0) return true;
  if (P.toolGroup[k] === P.holdingGroup) return false;
  if (SPOT.kind === "state") return cur.toolState[k] === SPOT.s;
  if (SPOT.kind === "area") return SPOT.a.includes(areaOfToolK(k));
  if (SPOT.kind === "hot") return cur.hotQ[P.toolGroup[k]] > 0;
  return cur.queue[P.toolGroup[k]] > 0;
}
function litNow() {
  if (!SPOT || !P) return null;
  if (SPOT.kind === "state" || SPOT.kind === "area") { const tools = []; for (let k = 0; k < P.nT; k++) if (spotTool(k)) tools.push(k); return { tools }; }
  const by = SPOT.kind === "hot" ? cur.hotQ : cur.queue;
  const groups = []; for (let g = 0; g < P.nG; g++) if (g !== P.holdingGroup && by[g] > 0) groups.push(g); return { groups };
}
function clearSpot() {
  if (!SPOT) return;
  SPOT = null;
  document.querySelectorAll("#health .row.spot").forEach(r => r.classList.remove("on"));
  draw();
}
function spotRow(el) {
  const k = el.dataset.spot;
  if (k === "longest") { const h = health(); if (h.longest.g >= 0) flyToGroup(h.longest.g); return; }
  const want = k === "waiting" ? { kind: "waiting" } : { kind: "state", s: +k.slice(1) };
  SPOT = SPOT && SPOT.kind === want.kind && SPOT.s === want.s ? null : want;
  document.querySelectorAll("#health .row.spot").forEach(r => r.classList.toggle("on", !!SPOT && r === el));
  draw();
}

// fly the map to a group and outline its tools for a few seconds
function flyToGroup(g) {
  if (!G) return;
  const pad = floorPad();
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  updateTilt();
  const [sx, sy] = untilt(pad.l + w / 2, pad.t + h / 2);
  let to = null, boxes = [];
  if (G.real) {
    const B = G.B, R = P.real;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < B.tools.length; i++) {
      const k = R.toolOfBox[i];
      if (k < 0 || P.toolGroup[k] !== g) continue;
      const b = B.tools[i]; boxes.push([b[1], b[2], b[3], b[4]]);
      x0 = Math.min(x0, b[1]); x1 = Math.max(x1, b[2]); y0 = Math.min(y0, b[3]); y1 = Math.max(y1, b[4]);
    }
    if (!boxes.length) return;
    const [cx, cy] = rw((x0 + x1) / 2, (y0 + y1) / 2);
    to = { cx, cy, s: Math.min(40, Math.max(0.5, Math.min(w / (x1 - x0 + 30), h / (y1 - y0 + 30)))) };
  } else {
    for (let i = 0; i < HALLS_L.length && !to; i++) for (const c of HALLS_L[i].cells) if (!c.label && c.gi === g) {
      const p = G.pos[i];
      to = { cx: p.x + 3 + c.x + c.w / 2, cy: p.y + c.y + c.h / 2, s: Math.min(40, Math.max(0.5, Math.min(w / (c.w + 24), h / (c.h + 24)))) };
      break;
    }
    if (!to) return;
  }
  const from = { cx: view.x + sx / view.s, cy: view.y + sy / view.s, s: view.s };
  ST.fly = { from, to, sx, sy, t0: performance.now(), ms: 900 };
  if (boxes.length) ST.flash = { boxes, until: performance.now() + 4500 };
}

/** The map's own region on the screen: [middle x, middle y, width, height]. */
function mapMiddle() {
  const pad = floorPad(), w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  return [pad.l + w / 2, pad.t + h / 2, w, h];
}
function zoomBy(f) {
  const [mx, my] = mapMiddle(), [sx, sy] = untilt(mx, my);
  const cx = view.x + sx / view.s, cy = view.y + sy / view.s;
  view.s = Math.min(60, Math.max(0.3, view.s * f));
  view.x = cx - sx / view.s; view.y = cy - sy / view.s;
  $("fit").hidden = false;
}

let healthShown = "";
function renderHealth(h) {
  const f = x => x.toLocaleString("en-US"), pc = x => `${Math.round(x * 100)}%`;
  const key = JSON.stringify(h);
  if (key === healthShown) return;
  healthShown = key;
  const set = (id, v) => { const e = $(id); if (e.textContent !== v) e.textContent = v; };
  set("h-done", f(h.finished)); set("h-wafers", f(h.wafersOut));
  set("h-24-l", h.sinceStart ? "lots finished since the start" : "lots finished in the last 24 h"); set("h-24", f(h.last24));
  const mins = (m) => (m === null ? "–" : m >= 60 ? `${(m / 60).toFixed(1)} h` : `${Math.round(m)} min`);
  set("h-wh", mins(h.waitHour));
  // against the same time yesterday, in this run (docs/FLOOR-REVIEW.md); none on day 1
  const diff = (id, d, unit, worseUp) => {
    const e = $(id);
    if (d === null) { e.hidden = true; return; }
    const r = Math.round(d), txt = `${r > 0 ? "▲" : r < 0 ? "▼" : "="} ${Math.abs(r).toLocaleString("en-US")}${unit}`;
    e.hidden = false; if (e.textContent !== txt) e.textContent = txt;
    e.className = `dl ${r === 0 ? "" : (r > 0) === worseUp ? "worse" : "better"}`;
  };
  const A = h.ago;
  diff("h-wait-d", A ? h.waiting - A.waiting : null, "", true);
  diff("h-avail-d", A ? (h.available - A.available) * 100 : null, " pts", false);
  diff("h-wh-d", A && h.waitHour !== null && A.waitHour !== null ? h.waitHour - A.waitHour : null, " min", true);
  $("h-ago-note").hidden = !A;
  set("h-wip", f(h.inFab)); set("h-wait", f(h.waiting)); set("h-proc", f(h.processing)); set("h-move", f(h.moving)); set("h-rest", f(h.resting));
  set("h-nt", `· ${f(h.nT)}`);
  const T = h.tools;
  set("h-t0", f(T.working)); set("h-t1", f(T.idle)); set("h-t2", f(T.maintenance)); set("h-t3", f(T.down)); set("h-t4", f(T.setup));
  set("h-avail", pc(h.available)); set("h-busy", pc(h.busy));
  set("h-lq-name", h.longest.lots ? h.longest.name : "no lots waiting"); set("h-lq", f(h.longest.lots));
  const bar = (id, parts, total) => { $(id).innerHTML = parts.map(([v, c]) => (v ? `<i class="${c}" style="flex:${v / total}"></i>` : "")).join(""); };
  bar("h-lotbar", [[h.waiting, "lw"], [h.processing, "lp"], [h.moving, "lm"], [h.resting, "lr"]], Math.max(1, h.inFab));
  bar("h-toolbar", [[T.working, "s0"], [T.idle, "s1"], [T.setup, "s4"], [T.maintenance, "s2"], [T.down, "s3"]], h.nT);
}

// ------------------------------------------------------------------ live curves (docs/CURVES.md)

let LOAD_OPTS = null, curvesShown = -1;
const BASE_CURVES = new Map(); // run number -> today's curves on that run
const CURVE_STEP = 20; // fab minutes between samples

/** The run's curves every 20 fab minutes: lots waiting for a tool, lots finished, the last hour's mean wait for a tool,
 * and the share of machines working; the same readings as the health panel's. */
function curvesOf(P) {
  const xs = [], waiting = [], finished = [], waitHour = [], working = [];
  const machines = P.toolGroup.filter(g => g !== P.holdingGroup).length;
  const q = new Int32Array(P.nG), st = new Uint8Array(P.nT).fill(1);
  let qi = 0, si = 0, busy = 0;
  const S = P.states, Q = P.qe;
  for (let t = 0; t <= P.j.until; t += CURVE_STEP) {
    const tq = seekTime(t);
    while (qi < Q.length && Q[qi][0] <= tq) { q[Q[qi][1]] += Q[qi][2]; qi++; }
    while (si < S.length / 3 && S[si * 3 + 1] <= tq) {
      const k = S[si * 3], v = S[si * 3 + 2];
      if (P.toolGroup[k] !== P.holdingGroup) busy += (v === 0 ? 1 : 0) - (st[k] === 0 ? 1 : 0);
      st[k] = v; si++;
    }
    let w = 0;
    for (let g = 0; g < P.nG; g++) if (g !== P.holdingGroup) w += q[g];
    const n0 = countBelow(P.waitStart, tq - 60), n1 = countBelow(P.waitStart, tq);
    xs.push(t); waiting.push(w); finished.push(countBelow(P.done, t));
    waitHour.push(n1 > n0 ? (P.waitSum[n1] - P.waitSum[n0]) / (n1 - n0) : 0); working.push(busy / machines);
  }
  return { xs, waiting, finished, waitHour, working };
}

function renderCurves() {
  const box = $("curves");
  if (box.hidden || !P || !P.curves) return;
  if (Math.abs(t - curvesShown) < 2 && box.childElementCount) return;
  curvesShown = t;
  const C = P.curves, base = P.isChange ? BASE_CURVES.get(P.seedOf) : null;
  const mins = m => (m >= 60 ? `${(m / 60).toFixed(1)} h` : `${Math.round(m)} min`);
  const charts = [
    ["Lots waiting", "waiting", v => Math.round(v).toLocaleString("en-US")],
    ["Lots finished", "finished", v => Math.round(v).toLocaleString("en-US")],
    ["Wait for a tool, last hour", "waitHour", mins],
    ["Tools working", "working", v => `${Math.round(v * 100)}%`],
  ];
  if (box.childElementCount !== charts.length + 1) box.innerHTML = `<p class="curves-note"></p>` + charts.map(() => `<div class="curve"></div>`).join("");
  box.querySelector(".curves-note").textContent = base ? `Run #${P.seedOf}: your settings against today` : `Run #${P.seedOf}, drawn as the clock runs`;
  const els = box.querySelectorAll(".curve");
  charts.forEach(([name, k, fmt], i) => {
    const series = [{ label: base ? "your settings" : "this run", ys: C[k], cls: base ? "mine" : "" }];
    if (base) series.push({ label: "today", ys: base[k], cls: "today" });
    // the chart spans the run so far (at least half a day), scaled to the values seen up to now
    const span = Math.min(P.j.until, Math.max(t, 720)), n = Math.max(1, Math.floor(t / CURVE_STEP) + 2);
    const top = Math.max(1e-9, ...C[k].slice(0, n), ...(base ? base[k].slice(0, n) : []));
    FabCharts.render(els[i], { name, xs: C.xs, series, until: span, now: t, fmt, top });
  });
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

let tickShown = "", tickHold = false;
function ticker() {
  if (tickHold) return;
  const ev = P.breakdowns;
  const n = countBelow(P.breakdownTimes, t);
  const rows = [];
  for (let i = n - 1; i >= 0 && rows.length < 3; i--) {
    const [tm, k, broke] = ev[i];
    const g = P.toolGroup[k];
    const idx = P.groupTools[g].indexOf(k) + 1;
    rows.push(`<li class="${broke ? "broke" : "fixed"}"><span class="tm" title="${clock(tm)}">${clock(tm).slice(-5)}</span><b>${P.plain[g]}</b>, tool ${idx} ${broke ? "broke down" : "is back up"}</li>`);
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
  if (UI.lens === "flows" && !FLOW.paused) FLOW.secs += dt;
  if (JOURNEY.on && !JOURNEY.paused && JOURNEY.P) { JOURNEY.p = Math.min(JOURNEY.P.total, JOURNEY.p + dt * JOURNEY.rate); journeyCamera(dt); }
  if (playing && P) {
    t = Math.min(P.j.until, t + stepOf(dt));
    if (t >= P.j.until && !P.quick) playing = false, ($("play").textContent = "▶");
  }
  if (P) {
    cur.seek(seekTime(t));
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
  if (G.real) return realGroupAt(mx, my);
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
  const area = FabLook.areaOf(sim.area[P.j.groups[g][0]]);
  tip.classList.toggle("tcard", !!area);
  tip.style.setProperty("--fam", area ? FabLook.FAM[area] : "transparent");
  tip.innerHTML = tipHtml(g);
  tip.hidden = false;
  const p = FabUI.tipPlace(h.mx, h.my, tip.offsetWidth, tip.offsetHeight, innerWidth, innerHeight);
  tip.style.left = p.x + "px";
  tip.style.top = p.y + "px";
}

// a group's hover card (docs/FLOOR-LOOK.md)
function tipHtml(g) {
  const counts = [0, 0, 0, 0, 0];
  for (const k of P.groupTools[g]) counts[cur.toolState[k]]++;
  const G0 = P.j.groups[g];
  const avgWait = G0[4] ? G0[3] / G0[4] : 0;
  const parts = counts.map((n, i) => (n ? `<span style="color:${STATE_COLORS[i]}">●</span> ${n} ${STATE_NAMES[i]}` : "")).filter(Boolean);
  const st = FabStages.byKey(FabStages.stageOfArea(sim.area[G0[0]]));
  const area = FabLook.areaOf(sim.area[G0[0]]), mood = moodNow(g) || "work", M = FabLook.MOOD[mood];
  const art = area ? `<div class="tip-art" style="background:${FabLook.FAM[area]}33"><img src="cast/${area}/${mood}.webp" alt="${FabLook.AREA[area].name}, ${M.fact.toLowerCase()}" width="224" height="224"></div><div class="tip-mood" style="background:${M.color}">${P.moods ? `${M.fact}: ${M.rule}` : P.moodsPending ? "Working out how it's doing…" : "Before a run"}</div>` : "";
  return `<b>${area ? FabLook.label(G0[0], area) : P.plain[g]}</b>${st ? `<span class="m"> · ${st.name}</span>` : ""}${art}${parts.join("<br>")}` +
    `<div class="tip-q"><span>${cur.queue[g]}</span> lots waiting now · <span>${avgWait.toFixed(0)} min</span> mean wait</div>` +
    (area ? `<div class="tip-ex">${FabLook.AREA[area].about}</div>` : "");
}

function setupInput() {
  let drag = null;
  cv.addEventListener("mousedown", e => { splitPick(e.clientX); const [ux, uy] = untilt(e.clientX, e.clientY); drag = { x: ux, y: uy, vx: view.x, vy: view.y, scene: SPLIT.active }; cv.classList.add("drag"); });
  addEventListener("mouseup", () => { drag = null; cv.classList.remove("drag"); });
  addEventListener("mousemove", e => {
    if (drag) {
      $("fit").hidden = false;
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
    $("fit").hidden = false;
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
  // one speed button cycles 1×, 3×, 12×, Max (docs/SITE-CUTS.md, docs/EDITOR-SPEED.md)
  [$("speed")].forEach(b => (b.onclick = () => {
    const SP = [[20, "1×"], [60, "3×"], [240, "12×"], [MAX, "Max"]], i = SP.findIndex(x => x[0] === speed), n = SP[(i + 1) % SP.length];
    speed = n[0];
    b.textContent = n[1];
  }));
  $("scrub").oninput = e => { t = +e.target.value; };
  $("fit").onclick = fit;
  $("curves-open").onclick = () => { const box = $("curves"); box.hidden = !box.hidden; $("curves-open").setAttribute("aria-expanded", String(!box.hidden)); $("curves-open").classList.toggle("on", !box.hidden); curvesShown = -1; renderCurves(); };
  $("new-run").onclick = () => startRun(randomRun(RUN), true); // docs/RANDOM-RUNS.md
  // the map's buttons (docs/FLOOR-REVIEW.md): the same as scroll, F and T
  $("zoom-in").onclick = () => zoomBy(1.25);
  $("zoom-out").onclick = () => zoomBy(0.8);
  $("fit-map").onclick = fit;
  $("tilt-map").onclick = () => { TILT.on = !TILT.on; fit(); };
  // a row of the panel lights what it names; Enter or Space as well as a click
  document.querySelectorAll("#health .row.spot").forEach(r => {
    r.onclick = () => spotRow(r);
    r.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); spotRow(r); } };
  });
  // the legend folds, remembered in this browser
  const keyFold = folded => {
    $("key").classList.toggle("folded", folded);
    $("key-fold").setAttribute("aria-expanded", String(!folded));
    try { localStorage.setItem("fabgym.keyFolded", folded ? "1" : "0"); } catch { /* storage blocked: folding still works */ }
    fit();
  };
  $("key-fold").onclick = () => keyFold(!$("key").classList.contains("folded"));
  try { if (localStorage.getItem("fabgym.keyFolded") === "1") { $("key").classList.add("folded"); $("key-fold").setAttribute("aria-expanded", "false"); } } catch { /* storage blocked */ }
  // Fab status folds the same way, for symmetry (docs/FLOOR-NAMES.md)
  const healthFold = folded => {
    $("health").classList.toggle("folded", folded);
    document.body.classList.toggle("health-folded", folded);
    $("health-fold").setAttribute("aria-expanded", String(!folded));
    try { localStorage.setItem("fabgym.healthFolded", folded ? "1" : "0"); } catch { /* storage blocked: folding still works */ }
    fit();
  };
  $("health-fold").onclick = () => healthFold(!$("health").classList.contains("folded"));
  try { if (localStorage.getItem("fabgym.healthFolded") === "1") { $("health").classList.add("folded"); document.body.classList.add("health-folded"); $("health-fold").setAttribute("aria-expanded", "false"); } } catch { /* storage blocked */ }
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
  for (const k of DIAL_KEYS) $("d-" + k).oninput = showDials;
  $("reset").onclick = () => {
    for (const k of DIAL_KEYS) $("d-" + k).value = k === "cap" ? CAP_NONE : DEFAULT_DIALS[k];
    showDials();
  };
  showDials();
}

// ------------------------------------------------------------------ dials and the comparison

const DEFAULT_DIALS = { breakdowns: 1, repair: 1, demand: 1, hot: 1, rework: 1, cap: 0, defects: 0 };
const DIAL_KEYS = ["breakdowns", "repair", "demand", "hot", "rework", "cap", "defects"];
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
    else if (k === "defects") o.textContent = d.defects ? `×${d.defects}: tool ${120 * d.defects / 60} h, lots ${60 * d.defects / 60} h` : "off";
    else o.textContent = d[k] === 0 && (k === "breakdowns" || k === "hot" || k === "rework") ? "none" : `×${d[k]}`;
    o.classList.toggle("moved", d[k] !== DEFAULT_DIALS[k]);
  }
}

function readOpts() {
  return {
    seed: $("seed").value === "" ? RUN : +$("seed").value, // the run on screen unless another is typed (docs/SIM-SETTINGS.md)
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
  const names = { breakdowns: "breakdowns", repair: "repair time", demand: "demand", hot: "urgent lots", rework: "rework" };
  for (const k of Object.keys(names)) if (o.dials[k] !== 1) parts.push(`${names[k]} ×${o.dials[k]}`);
  if (o.dials.defects) parts.push(`quality holds ×${o.dials.defects}`);
  if (o.dials.cap) parts.push(`a cap of ${o.dials.cap.toLocaleString()} lots inside`);
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
  const dots = d.map(v => `<circle cx="${X(v).toFixed(1)}" cy="11" r="2.6" fill="#CFE3E0" opacity="0.8"/>`).join("");
  const bar = isFinite(st.lo) ? `<rect x="${X(st.lo).toFixed(1)}" y="7" width="${Math.max(1, X(st.hi) - X(st.lo)).toFixed(1)}" height="8" rx="2" fill="#7EE8D8" opacity="0.35"/>
    <line x1="${X(st.mean).toFixed(1)}" x2="${X(st.mean).toFixed(1)}" y1="4" y2="18" stroke="#7EE8D8" stroke-width="2"/>` : "";
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
    : `We ran your change and today's fab on the same ${COMPARE_SEEDS.length} random days (numbers ${COMPARE_SEEDS[0]} to ${COMPARE_SEEDS[COMPARE_SEEDS.length - 1]}), so luck is shared. Each range is where the true difference lies, 95% of the time. Treat this as a first look, to be checked again on fresh days. A real fab may behave differently.`;
}

let compareToken = 0;
async function compare(o) {
  const token = ++compareToken;
  if (isToday(o)) {
    $("cmp-what").textContent = "This is today's fab. Change something above, then run it to compare.";
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
        if (done === 2) { const first = $("cmp-what"); if (first) first.scrollIntoView({ block: "start" }); } // the answer in view (docs/SIM-SETTINGS.md)
      }));
    }
  }
  try {
    await Promise.all(jobs);
    if (token === compareToken) logCompare(o, base, chg);
  } catch (err) { if (token === compareToken) $("cmp-note").textContent = "Could not compare: " + err.message; }
}

// ------------------------------------------------------------------ tabs and the 300-day runs

// the old tab names go to the dock's tabs (docs/FLOOR-CLEANUP.md)
function showTab(which, open = true) {
  if (open) openDock({ ask: "ask", change: "change", long: "numbers" }[which] || which);
}

function signed(x, d = 1) {
  const a = Math.abs(x).toFixed(d);
  if (+a === 0) return a;
  return (x < 0 ? "−" : "+") + a;
}

async function loadLong() {
  let L;
  try { L = await fetch("data/lean-long.json").then(r => (r.ok ? r.json() : null)); } catch { L = null; }
  if (!L) { $("long-sec").hidden = true; return; }
  const cell = (metric, k, cap) => L.cells.find(c => c.metric === metric && c.k === k && c.cap === cap);
  const ks = [...new Set(L.cells.map(c => c.k))];
  const caps = [...new Set(L.cells.map(c => c.cap))];
  const verdict = c => (/better/.test(c.verdict) ? "better" : /worse/.test(c.verdict) ? "worse" : "unclear");
  $("long-lead").textContent = `How many wafers come out each day when we cap the number of lots inside the fab, compared with no cap. We measured days ${L.warmup} to ${L.days} of each run, on the same ${L.seeds.length} random histories for every cell.`;
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
      lines.push(`In today's fab, a cap of <b>${cap.toLocaleString()} lots</b> costs no wafers (${signed(calm.mean)} a day, range ${signed(calm.lo)} to ${signed(calm.hi)}), and each wafer gets through ${Math.abs(ctc.mean).toFixed(0)} days sooner. When machines break ${worst.k} times as often, the same cap costs <b>${Math.abs(worst.mean).toFixed(0)} wafers a day</b> (range ${Math.abs(worst.hi).toFixed(0)} to ${Math.abs(worst.lo).toFixed(0)}).`);
    }
  }
  const gains = caps.filter(cap => verdict(cell("wafers_per_day", ks[0], cap)) === "better");
  if (gains.length) lines.push(`Caps of ${gains[0].toLocaleString()} to ${gains[gains.length - 1].toLocaleString()} lots get more wafers out in this simulation. We have not found out why yet.`);
  $("long-finding").innerHTML = lines.join("<br><br>");
  $("long-note").textContent = `Each cell shows the change in wafers a day with the cap, and below it the change in how many days a wafer takes. Green is better, red is worse and grey is too close to call. The ranges hold for all ${L.cells.length / 3} cells together, 95% of the time. We ran these ahead of time (${Math.round(L.seconds)} s), because a wafer needs more than the page's 14-day limit to cross the fab. A real fab may behave differently.`;
}

function rerun() {
  const opts = readOpts();
  $("runnote").textContent = "Simulating…";
  setTimeout(() => {
    let run;
    try { run = simulate(opts); } catch (err) { $("runnote").textContent = "Could not run: " + err.message; return; }
    LOAD_OPTS = opts;
    load(run);
    LOAD_OPTS = null;
    const moves = run.j.moves.toLocaleString();
    $("runnote").textContent = `Ran ${opts.days} day${opts.days > 1 ? "s" : ""} (run #${opts.seed}): ${moves} deliveries and ${run.j.decisions.toLocaleString()} choices of what to run next, in ${run.secs.toFixed(2)} s here in your browser.`;
    compare(opts);
  }, 20);
}

function load(run) {
  const hallOfGroup = HALLS_L.hallOfGroup;
  P = prepare(run, HALLS_L, hallOfGroup);
  P.moods = run.moods || null;
  P.groupTools = Array.from({ length: P.nG }, () => []);
  P.toolGroup.forEach((g, k) => P.groupTools[g].push(k));
  P.plain = P.j.groups.map(g => plainGroup(g[0], sim.area[g[0]]));
  P.holdingGroup = P.j.groups.findIndex(g => sim.area[g[0]] === "Delay_32");
  P.breakdowns = breakdownEvents(P);
  P.breakdownTimes = P.breakdowns.map(e => e[0]);
  // the curves (docs/CURVES.md): today's are kept by run number, so a changed run can be drawn over them
  P.isChange = !!(LOAD_OPTS && !isToday(LOAD_OPTS));
  P.seedOf = LOAD_OPTS ? LOAD_OPTS.seed : RUN;
  P.curves = curvesOf(P);
  if (!P.isChange && !P.quick) BASE_CURVES.set(P.seedOf, P.curves);
  curvesShown = -1;
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

// the whole journey, sand to chip, as one strip above the loop (docs/STAGES.md; the founder, 29 Oct)
const JOURNEY_ACTS = { before: "Before the fab", fab: "In the fab · simulated", after: "After the fab" };
function journeyDraw() {
  const el = $("stages-journey");
  let html = "";
  for (const act of ["before", "fab", "after"]) {
    html += `<div class="j-act ${act}"><div class="j-head">${JOURNEY_ACTS[act]}</div><div class="j-cards">` +
      FabStages.JOURNEY.filter(j => j.act === act).map(j => `<button type="button" role="listitem" class="j-card${j.key === ST.jkey ? " on" : ""}" data-j="${j.key}">` +
        `${FabStages.journeyPicture(j.key)}<span>${esc(j.name)}</span></button>`).join("") + `</div></div>`;
  }
  el.innerHTML = html;
  el.querySelectorAll(".j-card").forEach(b => (b.onclick = () => journeySelect(b.dataset.j)));
  journeySelect(ST.jkey || "sand", false);
}
function journeySelect(key, jump = true) {
  ST.jkey = key;
  const j = FabStages.JOURNEY.find(x => x.key === key);
  document.querySelectorAll("#stages-journey .j-card").forEach(b => b.classList.toggle("on", b.dataset.j === key));
  $("journey-detail").innerHTML = `<div class="j-pic">${FabStages.journeyPicture(key)}</div><div class="j-text">` +
    `<div class="j-tag ${j.inModel ? "in" : "out"}">${j.inModel ? "In the simulator · SMT2020 testbed" : "Outside the simulator · general knowledge"}</div>` +
    `<h3>${esc(j.name)}</h3><p>${esc(j.what)}</p><ul>${j.facts.map(f => `<li>${esc(f)}</li>`).join("")}</ul>` +
    (key === "loop" ? `<button type="button" class="link" id="j-to-loop">See the loop below ↓</button>` : "") + `</div>`;
  if (key === "loop") {
    $("j-to-loop").onclick = () => $("loop-title").scrollIntoView({ behavior: "smooth", block: "start" });
    if (jump) $("loop-title").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function stagesDraw() {
  journeyDraw();
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
  if (G.real) { realFlyTo(HALLS_L[i].areas || []); return; }
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
  if (G.real) { realFlash(f, now); return; }
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
  if (pageOfHash() !== "home") document.body.classList.remove("opening-on");
  markPage(pageOfHash());
  chromeSetup();
  stagesSetup();
  $("areakey").innerHTML = FabLook.MAT_KEY.map(([name, col, as]) => {
    const names = as.map(a => FabLook.AREA[a].name);
    return `<li><span class="mat" style="background:${col}"></span><span class="nm">${name}</span>${names.length > 1 || names[0] !== name ? `<span class="rule">${names.join(", ")}</span>` : ""}</li>`;
  }).join("");
  $("moodkey").innerHTML = FabLook.TOOL_MOODS.map(m => { const M = FabLook.MOOD[m]; return `<li><span class="badge" style="background:${M.color}">${FabLook.svg(M.badge, "#15191C")}</span><span class="nm">${M.fact}</span><span class="rule">${M.rule}</span></li>`; }).join("");
  requestAnimationFrame(frame);
  try {
    await loadSim();
  } catch (err) {
    $("runnote").textContent = "Could not load the simulator: " + err.message;
    return;
  }
  // the first hours first (docs/FLOOR-SPEED.md): the same run's first 6 hours draw and play at once, while a worker
  // runs the full 3 days; the simulator is exact, so those hours are the start of the full run
  startRun(runFromAddress(), false);
  // a run from the Runs page (docs/RUNS.md, part 2): ?q=Q-0002&arm=3&run=4 plays that setup's random run as scored
  { const a = new URLSearchParams(location.search), q = a.get("q"), k = a.get("arm");
    if (q && /^[A-Z]-\d{4,}$/.test(q) && k !== null && /^\d{1,3}$/.test(k)) watchRun(q, +k, RUN); }
  await loadLong();
  fit();
  askSetup();
  applyHash();
}

// the run on the Floor (docs/RANDOM-RUNS.md): a random history numbered 1 to 9,999, in the address so it replays;
// run 0 is the one the Floor used to play
let RUN = 0;
let WATCH = null; // a question's run being watched (docs/RUNS.md, part 2)
function runFromAddress() {
  const v = new URLSearchParams(location.search).get("run");
  if (v !== null && /^\d{1,5}$/.test(v)) return +v;
  return randomRun(-1);
}
function randomRun(not) {
  let n = not;
  while (n === not) { const a = new Uint32Array(1); crypto.getRandomValues(a); n = 1 + (a[0] % 9999); }
  return n;
}
/** Play run n: its first hours at once, the full three days from the worker behind them. */
function startRun(n, keepView) {
  RUN = n;
  if (WATCH) { WATCH = null; $("watchbar").hidden = true; }
  const q = new URLSearchParams(location.search); q.set("run", String(n));
  history.replaceState(null, "", `${location.pathname}?${q}${location.hash}`);
  $("run-no").textContent = `Run #${n}`;
  $("seed").value = String(n); // the settings panel changes the run on screen (docs/SIM-SETTINGS.md)
  const opts = { seed: n, days: 3, rule: 0, downGroup: -1, downAt: 0, downHours: 0 };
  const first = simulate({ ...opts, days: QUICK_DAYS, moods: false });
  setFloor(first);
  P.quick = true;
  P.moodsPending = true;
  if (!keepView) fit();
  document.body.dataset.floor = "drawn";
  delete document.body.dataset.moods;
  $("runnote").textContent = "Playing the first hours while the full 3 days run in the background…";
  fullRun(opts);
}

const QUICK_DAYS = 0.25;
const BOOT = { full: null };

// the full run from the worker (web/floorworker.js), swapped in where the first hours are playing
let fullWorker = null, fullSeq = 0;
function fullRun(opts) {
  // a new run makes the one still running in the background stale: stop it and ignore anything it sends
  const seq = ++fullSeq;
  if (fullWorker) { fullWorker.terminate(); fullWorker = null; }
  BOOT.full = null;
  const done = run => {
    if (seq !== fullSeq) return;
    BOOT.full = run;
    if (P && P.quick) swapIn(run);
    keepFloorRun(run, opts);
  };
  if (typeof Worker === "undefined") { done(simulate(opts)); document.body.dataset.moods = "in"; return; }
  const w = new Worker("floorworker.js");
  fullWorker = w;
  w.onmessage = ({ data }) => {
    if (seq !== fullSeq) return;
    if (data.type === "run") {
      done({ j: data.j, trace: data.trace, states: data.states, fleetE: data.fleetE, fleetH: data.fleetH, F: data.F,
        vehicles: data.vehicles, secs: data.secs, moods: null });
    } else if (data.type === "moods") {
      if (BOOT.full) BOOT.full.moods = data.moods;
      if (P && BOOT.full && P.j === BOOT.full.j) { P.moods = data.moods; P.moodsPending = false; document.body.dataset.moods = "in"; }
      w.terminate();
    } else {
      $("runnote").textContent = "Could not run the full 3 days: " + data.error;
      w.terminate();
    }
  };
  w.postMessage({ shopUrl: sim.baseUrl, dials: DEFAULT_DIALS, opts: { ...opts, every: MOOD_EVERY } });
}

function swapIn(run) {
  const keep = t, was = playing;
  setFloor(run);
  P.moodsPending = !run.moods;
  t = Math.min(keep, P.j.until);
  cur.reset();
  cur.seek(seekTime(t));
  playing = was;
  $("play").textContent = playing ? "❚❚" : "▶";
  document.body.dataset.floor = "full";
  $("runnote").textContent = `Ran 3 days of the fab (${run.j.moves.toLocaleString()} deliveries) in ${run.secs.toFixed(2)} s, right here in your browser.`;
}

// for page tests (docs/FLOOR-SPEED.md): read only
window.FabFloorPage = {
  time: () => t,
  end: () => (P ? P.j.until : 0),
  moves: () => (P && !P.quick ? P.j.moves : null),
  // docs/RUNS.md, part 2: a question's run on the Floor, its jobs and finished lots
  watching: () => (WATCH ? { ...WATCH } : null),
  // docs/GLOSSARY-PLUS.md, part 2
  tools: () => (P ? P.nT : 0),
  toolGroup: k => P.toolGroup[k],
  openGlossary: term => openGlossary(term),
  hotWaiting: () => { const out = []; for (let g = 0; g < P.nG; g++) if (g !== P.holdingGroup && cur.hotQ[g] > 0) out.push(g); return out; },
  jobs: () => (P && !P.quick ? P.trace.length / 6 : null),
  finished: () => (P && !P.quick ? P.j.finished : null),
  groups: () => (P ? P.nG : 0),
  mood: g => moodNow(g),
  health: () => (P ? health() : null),
  runNumber: () => RUN,
  // docs/FLOOR-REVIEW.md
  lit: () => litNow(),
  toolState: k => cur.toolState[k],
  queueNow: g => cur.queue[g],
  isStorage: g => g === P.holdingGroup,
  longestGroup: () => health().longest.g,
  stateLights: () => ({ working: STATE_COLORS[0], maintenance: STATE_COLORS[2], down: STATE_COLORS[3], setup: STATE_COLORS[4] }),
  toolTop: k => toolPanel(k),
  areaOfTool: k => FabLook.areaOf(sim.area[P.j.groups[P.toolGroup[k]][0]]),
  view: () => ({ ...view }),
  tilted: () => TILT.on,
  badgesDrawn: () => BADGES.slice(),
  mapMiddle: () => mapMiddle(),
  groupName: g => P.plain[g],
  screenOfGroup: g => {
    if (G.real) { const m = P.real.mid[g]; return m && m[2] ? S(...rw(m[0] / m[2], m[1] / m[2])) : null; }
    for (let i = 0; i < HALLS_L.length; i++) for (const c of HALLS_L[i].cells) if (!c.label && c.gi === g) { const p = G.pos[i]; return S(p.x + 3 + c.x + c.w / 2, p.y + c.y + c.h / 2); }
    return null;
  },
  cardText: g => {
    const box = document.createElement("div");
    box.innerHTML = tipHtml(g);
    return box.textContent;
  },
};

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
  if (BUILDING && run.fleetE && run.fleetE.length && FabBuilding.fits(BUILDING, groups.map(g => [g.name, g.count]))) G = realGeometry(BUILDING);
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
  $("ask-run").onclick = () => runText($("ask-text").value);
  let st;
  try { st = await api("/api/status"); } catch { st = null; }
  if (!st || st.error) {
    $("ask-model").innerHTML = "The ask box needs the helper running on this Mac. In the fab-gym folder, run <code>python3 -m agent.helper</code>, then open <b>http://127.0.0.1:8766</b>.";
    $("ask-run").disabled = true;
    return;
  }
  ASK.helper = true;
  $("ask-model").textContent = st.model_connected
    ? "Meta's Muse Spark model turns your question into an experiment. The simulator runs it on the full fab and shows you what changed."
    : "Until a model is connected, answers come from worked examples. You can also write an experiment yourself under Advanced.";
  $("ask-examples").innerHTML = st.examples.map((e, i) => `<button type="button" data-i="${i}">${esc(e.question)}</button>`).join("");
  $("ask-examples").querySelectorAll("button").forEach(b => (b.onclick = () => askFrom(st.examples[+b.dataset.i].question)));
  if (!$("ask-text").value) $("ask-text").value = "fabgym-scenario 1\nquestion\tPrototype orders double. Their own wing?\nfamily\tshare\t2\tsaid\ncandidate\town-wing\tfloor\twing\n";
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
  // the run's number, with a link to its card on the Runs page (docs/RUNS.md)
  const link = $("ask-run").querySelector("a");
  link.href = `runs.html#run=${id}`;
  link.textContent = `Run ${id} · watch it on the Runs page →`;
  $("ask-run").hidden = false;
  ASK.timer = setInterval(async () => {
    const j = await api(`/api/job/${id}?since=1000000`);
    if (j.error && !j.stage) { clearInterval(ASK.timer); stage(j.error); return; }
    ASK.job = j;
    if (j.scenario) showScenario(j);
    if (j.stage === "done") { clearInterval(ASK.timer); stage(`Done in ${Math.round(j.seconds)} s.`); showResult(j); }
    else if (j.stage === "failed") { clearInterval(ASK.timer); stage(j.error); }
    else if (j.runs_total) stage(`Run ${j.runs_done} of ${j.runs_total}${j.minutes_left != null ? ` · about ${j.minutes_left < 1 ? "under a minute" : Math.round(j.minutes_left) + " min"} left` : ""}`);
    else stage(`${j.stage[0].toUpperCase()}${j.stage.slice(1)}… ${Math.round(j.elapsed)} s`);
  }, 1000);
}

function showScenario(j) {
  const s = FabAsk.scenarioLines(j.scenario);
  // plain words (docs/RUNS.md): where the setup came from, what you said, and each change by what it does
  const src = j.answer_source === "example" ? "Your question matched one of our hand-written examples, so no model ran. The setup:"
    : j.answer_source === "model" ? "Muse Spark turned your question into this setup, and the simulator checked it:" : "Your hand-written setup:";
  const low = t => t.charAt(0).toLowerCase() + t.slice(1);
  $("ask-scenario").hidden = false;
  $("ask-scenario").innerHTML = `<p class="note">${src}</p>
    <ul class="given">${s.given.map(g => `<li><span class="tag ${g.said ? "said" : "assumed"}">${g.said ? "You said" : "Assumed"}</span>${esc(low(g.text))}</li>`).join("") || "<li>Today's fab as it is.</li>"}</ul>
    <p class="note">Compared with today's fab:</p>
    <ul class="cands">${s.candidates.map(c => `<li>${esc(c.changes.join(", and ").replace(/^./, x => x.toUpperCase()))}</li>`).join("")}</ul>`;
  $("ask-text").value = j.scenario;
}

// a cell's value: dollars for operating profit and cash, else the plain number
function cellNum(c, x) { return x === null || x === undefined ? "—" : c.key === "profit" || c.key === "cash" ? FabUI.usd3(x, true) : fmt(x); }
function cellText(c) {
  if (c.mean === null) return "—";
  return cellNum(c, c.mean);
}
// what a candidate buys and what it is worth (docs/MONEY-PL.md)
function plLine(p) {
  if (!p) return "";
  const pay = p.capital ? paybackText(p.payback_days) : "no capital needed";
  return `<p class="note small pl-line">Capital ${p.capital ? FabUI.usd3(p.capital) : "none"} · pays back ${pay} · value over 5 years ${FabUI.usd3(p.npv.mean, true)} (${FabUI.usd3(p.npv.lo, true)} to ${FabUI.usd3(p.npv.hi, true)}) · prices assumed</p>`;
}

// a candidate named by what it changes (docs/FLOOR-CLEANUP.md): the scenario's own lines, in the page's words
function candLabel(j, name) {
  if (name === "today") return "Today's fab";
  const ch = (j.scenario || "").split("\n").map(l => l.split("\t")).filter(f => f[0] === "candidate" && f[1] === name).map(f => [f[2], f.slice(3).join(" ")]);
  return ch.length ? FabUI.candidateName(ch) : name;
}

function showResult(j) {
  logAsk(j);
  const r = j.report;
  const rows = FabAsk.resultRows(r);
  const arms = r.arms || [];
  const armBtn = name => {
    const i = arms.findIndex(a => a.name === name);
    return i < 0 ? "" : (name === "today" ? "" : `<button type="button" class="show sbs" data-arm="${i}">Side by side</button>`) +
      ` <button type="button" class="show link" data-arm="${i}">On the floor</button>`;
  };
  const head = r.families
    ? `<p class="note">Each row compares a candidate with today's fab on the same seeds and gives a 95% interval. Today's values: ${rows[0] ? rows[0].cells.map(c => `${c.label.toLowerCase()} ${c.today === null ? "—" : c.key === "profit" ? FabUI.usd3(c.today, false) : Math.round(c.today * 10) / 10}`).join(", ") : ""}.</p>`
    : `<p class="note">Each row compares a candidate with today's fab on the same seeds and gives a 95% interval.</p>`;
  $("ask-result").innerHTML = `<p class="what">${esc(r.best ? FabAsk.summaryLine(r).replace(r.best, candLabel(j, r.best)) : FabAsk.summaryLine(r))}</p>${head}` +
    (arms.length ? `<div class="arm"><div class="top"><b>today</b>${armBtn("today")}</div></div>` : "") +
    rows.map(row => `<div class="arm"><div class="top"><b>${esc(candLabel(j, row.name))}${row.best ? '<span class="best">best</span>' : ""}</b>${armBtn(row.name)}</div>
      <table>${row.cells.map(c => `<tr><td>${esc(c.label)}</td><td class="v">${cellText(c)}</td><td class="v">${c.lo === null || c.mean === null ? "" : `${cellNum(c, c.lo)} to ${cellNum(c, c.hi)}`}</td><td class="p"><span class="pill ${c.verdict === "no clear effect" ? "unclear" : c.verdict}">${c.verdict}</span></td></tr>`).join("")}</table>${plLine(row.pl)}</div>`).join("") +
    `<p class="note small">${!r.families ? "" : rows.some(x => x.pl) ? "Operating profit is in dollars at the central assumed prices (see How money is counted in the numbers). " : "Money a day is counted in volume-wafer margins, and every price is assumed. "}The intervals hold together at 95% across all the candidates (Bonferroni). Simulated from the SMT2020 testbed, a published set of a fab's tool groups, routes and times. What these changes would do in a real fab is unknown.</p>`;
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
    $("rule").value = String(rc.show);
    const run = simulate({ seed: RUN, days: 3, rule: rc.code, downGroup: -1, downAt: 0, downHours: 0 });
    setFloor(run);
    fit();
    ASK.onFloor = arm.name;
    $("runnote").innerHTML = `On the floor: <b>${esc(arm.name)}</b>, run #${RUN}, first 3 days.${rc.exact ? "" : " The page's simulator cannot run this candidate's rule, so it uses today's rule."} Prototype lots are pink. <button type="button" class="link" id="back-today">Back to today's fab</button>`;
    $("back-today").onclick = backToToday;
  } catch (err) {
    $("runnote").textContent = "Could not show it: " + err.message;
  }
}

// a question's run on the Floor (docs/RUNS.md, part 2): that setup's file, that random run, from its start
async function watchRun(q, k, seed) {
  fullSeq++; if (fullWorker) { fullWorker.terminate(); fullWorker = null; } // the base run in the background is not wanted
  $("runnote").textContent = `Loading ${q} onto the floor…`;
  try {
    const j = await fetch(`/api/job/${q}`).then(r => (r.ok ? r.json() : Promise.reject(new Error("the helper has no such run"))));
    const rep = j.report, arm = rep && rep.arms && rep.arms[k];
    if (!arm) throw new Error(rep ? "that run kept no such setup" : "that run has not finished");
    const text = await fetch(arm.shop_url).then(r => (r.ok ? r.text() : Promise.reject(new Error("the helper has no such setup"))));
    for (const g of ASK.extra) delete sim.area[g];
    ASK.extra = [];
    for (const [g, a] of arm.extra_areas || []) { sim.area[g] = a; ASK.extra.push(g); }
    await loadShopText(text);
    const total = rep.warmup_days + rep.window_days, days = total <= 14 ? total : 3;
    const rc = FabAsk.ruleCode(arm);
    $("rule").value = String(rc.show);
    RUN = seed; $("run-no").textContent = `Run #${seed}`; $("seed").value = String(seed);
    const run = simulate({ seed, days, rule: rc.code, downGroup: -1, downAt: 0, downHours: 0 });
    setFloor(run);
    fit();
    WATCH = { q, k, seed, days, total, name: arm.name };
    ASK.onFloor = arm.name;
    // in view: which run this is, and the way back (the run's own number on its card is the random run's)
    $("run-no").textContent = `${q} · run ${seed + 1}`;
    $("watchbar").innerHTML = `Watching <b>${esc(q)}</b> · ${esc(arm.name)} · random run ${seed + 1} · ${days === total ? `all ${total} days` : `first ${days} of ${total} days`}, as scored · <a href="runs.html#run=${esc(q)}">the run</a> · <button type="button" class="link" id="watch-off">today's fab</button>`;
    $("watchbar").hidden = false;
    $("watch-off").onclick = () => { WATCH = null; $("watchbar").hidden = true; backToToday(); };
    $("runnote").innerHTML = `On the floor: <b>${esc(q)}</b>, setup <b>${esc(arm.name)}</b>, its random run ${seed + 1}: ` +
      `${days === total ? `all ${total} days it ran` : `the first ${days} of its ${total} days`}, as scored (the same engine on the same setup and random run). ` +
      `<a href="runs.html#run=${esc(q)}">Back to the run</a> · <button type="button" class="link" id="back-today">Back to today's fab</button>`;
    $("back-today").onclick = () => { WATCH = null; $("watchbar").hidden = true; backToToday(); };
  } catch (err) {
    $("runnote").textContent = `Could not show ${q}: ${err.message}`;
  }
}

async function backToToday() {
  for (const g of ASK.extra) delete sim.area[g];
  ASK.extra = [];
  const text = await fetch(sim.baseUrl || "data/shop.txt").then(r => r.text());
  await loadShopText(text);
  $("rule").value = "0";
  const run = simulate({ seed: RUN, days: 3, rule: 0, downGroup: -1, downAt: 0, downHours: 0 });
  setFloor(run);
  fit();
  $("runnote").textContent = `Today's fab: ran 3 days (${run.j.moves.toLocaleString()} deliveries) in ${run.secs.toFixed(2)} s, right here in your browser.`;
}


// ------------------------------------------------------------------ the redesigned chrome (docs/FLOOR-UI.md)
// The opening, the command bar (⌘K), lens chips, drawers for the tools, the numbers view and signing.

const UI = { lens: "day", sweep: null, metric: "profit", share: 4 };

let VP = null; // the part of the window a scene is drawn in; null for all of it
function floorPad() {
  if (VP) return { l: VP.x + 6, r: innerWidth - VP.x - VP.w + 6, t: 170, b: 175 };
  const wide = innerWidth > 900;
  const dock = $("dock");
  const healthOpen = !$("health").classList.contains("folded"); // Fab status folds like the legend (docs/FLOOR-NAMES.md)
  const r = !wide ? 24 : !dock.hidden ? dock.offsetWidth + 40 : healthOpen ? $("health").offsetWidth + 32 : 24; // the health panel (docs/FLOOR-HEALTH.md)
  const keyOpen = !document.body.classList.contains("dock-wide") && !$("key").classList.contains("folded");
  return { l: wide && keyOpen ? 330 : 24, r: r + (wide && dock.hidden ? 52 : 0), t: 116, b: 96 }; // room for the map's buttons
}

// ------------------------------------------------------------------ the dock: Ask, Change, Numbers, Results, Glossary
const DOCK = { tab: null };
const DOCK_TITLE = { ask: "Your question", change: "Simulation settings", glossary: "What the words mean", evidence: "Evidence", numbers: "Evidence", results: "Evidence" };
const DOCK_WIDE = new Set(["numbers", "results", "glossary", "evidence"]);
function openDock(tab) {
  closeOpening();
  DOCK.tab = tab;
  const dock = $("dock");
  dock.hidden = false;
  dock.classList.toggle("wide", DOCK_WIDE.has(tab));
  document.body.classList.add("dock-open");
  document.body.classList.toggle("dock-wide", DOCK_WIDE.has(tab));
  for (const [t, id] of [["ask", "pane-ask"], ["change", "pane-change"], ["findings", "findings"], ["numbers", "numbers"], ["results", "results"], ["glossary", "glossary"]])
    $(id).hidden = !(t === tab || (tab === "evidence" && (t === "findings" || t === "numbers" || t === "results")));
  $("dock-title").textContent = DOCK_TITLE[tab] || "";
  document.body.classList.toggle("evidence-on", tab === "evidence");
  document.querySelectorAll("[data-tab]").forEach(b => { const on = b.dataset.tab === tab; b.classList.toggle("on", on); if (b.getAttribute("role") === "tab") b.setAttribute("aria-selected", on); });
  fit();
}
function closeDock() {
  $("dock").hidden = true;
  DOCK.tab = null;
  document.body.classList.remove("dock-open", "dock-wide", "evidence-on");
  document.querySelectorAll("[data-tab]").forEach(b => b.classList.remove("on"));
  fit();
}
// Evidence (docs/SITE-CUTS.md): the long studies and the results on a page of their own
async function openEvidence() {
  openDock("evidence");
  drawFindings();
  await openNumbers(true);
  await openResults(true);
}
// What we found (docs/EVIDENCE-PLAIN.md): four findings in plain words, from the same data as the notebook's tables
let FINDINGS = null;
async function drawFindings() {
  if (!FINDINGS) {
    try {
      const get = p => fetch(p).then(r => (r.ok ? r.json() : Promise.reject(new Error(p))));
      const [sweep, long, results, lean] = await Promise.all([get("data/two-families.json"), get("data/lean-long.json"), get("data/results.json"), get("data/lean-check.json")]);
      FINDINGS = FabEvidence.findings({ sweep: sweep.pl ? FabUI.withPl(sweep, sweep.pl) : sweep, long, results, lean }, FabUI);
    } catch { $("find-list").innerHTML = '<p class="note">The findings could not be loaded.</p>'; return; }
  }
  const pic = f => {
    if (f.id === "prototypes") {
      // bars grow from a $0 line, gains right and losses left, in proportion (docs/EVIDENCE-REVIEW.md)
      const pos = Math.max(0, ...f.levels.map(l => l.value)), neg = Math.max(0, ...f.levels.map(l => -l.value)), span = pos + neg || 1;
      const zero = (neg / span) * 100;
      return `<div class="fpic bars">${f.levels.map(l => { const w = (Math.abs(l.value) / span) * 100, left = l.value >= 0 ? zero : zero - w;
        return `<div class="bar-row"><span class="bl">${({ 1: "Today's orders", 2: "Twice as many", 4: "Four times", 8: "Eight times" })[l.share]}</span><span class="bt" data-zero="${zero.toFixed(3)}"><em class="zero" style="left:${zero}%"></em><i class="${l.verdict === "better" ? "good" : l.verdict === "worse" ? "bad" : "flat"}" style="left:${left}%;width:${Math.max(0.5, w)}%"></i></span><b>${FabEvidence.usd(l.value)}</b></div>`; }).join("")}<p class="cap">Profit a day from holding prototypes at the door, against today's fab</p></div>`;
    }
    if (f.id === "cap") return `<div class="fpic duo"><div><b>${Math.round(f.normal.daysSooner)} days</b><span>sooner for each wafer, normal fab</span></div><div class="bad"><b>−${Math.round(f.breaks.wafersLost)} wafers</b><span>a day when machines break twice as often</span></div></div>`;
    if (f.id === "ai") return `<div class="fpic duo"><div><b>The fab's rule</b><span>wins on ten new days</span></div><div class="bad"><b>−${Math.round(f.lower)} points</b><span>the trained AI's score against it</span></div></div>`;
    return `<div class="fpic big"><b>${f.passed} / ${f.runs}</b><span>scored runs passed the proof-checked referee</span></div>`;
  };
  $("find-list").innerHTML = FINDINGS.map((f, i) => `<article class="find" id="find-${f.id}"><div class="fnum">${i + 1}</div><div class="fbody"><h3>${esc(f.title)}</h3>${pic(f)}` +
    `<dl><dt>What we did</dt><dd>${esc(f.what)}</dd><dt>What it means</dt><dd>${esc(f.means)}</dd><dt>How sure</dt><dd class="sure">${esc(f.sure)}</dd></dl>` +
    `<button type="button" class="link find-proof" data-jump="${PROOF[f.id] ? PROOF[f.id][0] : "results"}" data-kind="${PROOF[f.id] ? PROOF[f.id][1] : ""}">${PROOF[f.id] ? PROOF[f.id][2] : "See the runs behind it"} →</button></div></article>`).join("");
  $("find-list").querySelectorAll(".find-proof").forEach(b => (b.onclick = () => evJump(b.dataset.jump, b.dataset.kind)));
}
// where each finding's proof lives (docs/EVIDENCE-REVIEW.md): [section, a kind of run to show, the link's words]
const PROOF = {
  prototypes: ["numbers", "", "See the table behind it"],
  cap: ["long-sec", "", "See the cap's table"],
  ai: ["results", "contest", "See the contests"],
};
/** Bring a part of Evidence to the top, under the contents bar; with a kind, show only those runs. */
function evJump(id, kind) {
  if (kind) { const b = document.querySelector(`#res-kind button[data-k="${kind}"]`); if (b) b.click(); }
  const t = $(id);
  if (t) t.scrollIntoView({ block: "start" });
}

function goTab(tab) {
  if (tab === "numbers" || tab === "results" || tab === "evidence") { location.hash = "#evidence"; return; }
  else if (tab === "glossary") openGlossary();
  else openDock(tab);
}

// pages by the address's hash (docs/FRONT-DOOR.md): #home the landing, #floor the floor, #ask the floor with the ask
// panel; the top bar marks the one you are on
function pageOfHash() { return ({ "#floor": "floor", "#ask": "ask", "#evidence": "evidence" })[location.hash] || "home"; }
function applyHash() {
  const page = pageOfHash();
  if (page === "home") { closeDock(); document.body.classList.add("opening-on"); resize(); }
  else {
    closeOpening();
    if (page === "ask") openDock("ask");
    else if (page === "evidence") openEvidence();
    else if (DOCK.tab === "ask" || DOCK.tab === "evidence") closeDock();
  }
  markPage(page);
}
function markPage(page) { document.querySelectorAll(".topnav a").forEach(a => (a.dataset.page === page ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"))); }
addEventListener("hashchange", applyHash);

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
  openDock("ask");
  if (location.hash !== "#ask") { history.replaceState(null, "", "#ask"); markPage("ask"); }
  if (ASK.helper) ask(q);
  else stage("To ask a question, start the helper on this Mac. In the fab-gym folder, run python3 -m agent.helper.");
}

async function chromeSetup() {
  let st = null, bundled = [];
  try { st = await api("/api/status"); if (st.error) st = null; } catch { st = null; }
  try { bundled = await fetch("data/examples.json").then(r => r.json()); } catch { bundled = []; }
  const o = FabUI.openingState(st, bundled);
  // the suggestions sit under the Floor's ask bar, shown when you click into it; one fills the bar, Enter asks
  // (docs/HOME-GATE.md: asking left Home's gate)
  const list = $("cmd-examples");
  list.innerHTML = o.examples.map((q, i) => `<button type="button" data-i="${i}">${esc(q)}</button>`).join("");
  list.querySelectorAll("button").forEach(b => {
    b.onmousedown = e => e.preventDefault(); // keep the bar focused
    b.onclick = () => { $("cmd-q").value = o.examples[+b.dataset.i]; list.hidden = true; $("cmd-q").focus(); };
  });
  const offer = () => { if (!$("cmd-q").value) list.hidden = false; };
  $("cmd-q").addEventListener("focus", offer);
  $("cmd-q").addEventListener("mousedown", offer); // a click into a bar that already has focus
  $("cmd-q").addEventListener("input", () => { list.hidden = !!$("cmd-q").value; });
  $("cmd-q").addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== $("cmd-q")) list.hidden = true; }, 120));

  $("cmd").onsubmit = e => { e.preventDefault(); askFrom($("cmd-q").value); $("cmd-q").value = ""; $("cmd-q").blur(); };
  addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      // on Home, ⌘K opens the Floor with its ask bar ready
      if (document.body.classList.contains("opening-on")) { location.hash = "#floor"; setTimeout(() => $("cmd-q").focus(), 150); }
      else $("cmd-q").focus();
    } else if (e.key === "Escape") {
      if (SPOT && SPOT.note) { clearSpot(); return; }
      if (document.activeElement === $("cmd-q")) { $("cmd-examples").hidden = true; $("cmd-q").blur(); }
      else if (!$("dock").hidden) (DOCK.tab === "evidence" ? (location.hash = "#floor") : closeDock());
    }
  });
  // the rail and the dock's tabs; a rail button on the open tab closes the dock
  document.querySelectorAll("[data-tab]").forEach(b => (b.onclick = () => {
    if (b.closest("#topbar, .help-row") && DOCK.tab === b.dataset.tab && !$("dock").hidden) closeDock();
    else goTab(b.dataset.tab);
  }));
  $("dock-close").onclick = () => (DOCK.tab === "evidence" ? (location.hash = "#floor") : closeDock());
  document.querySelectorAll(".ev-toc button").forEach(b => (b.onclick = () => evJump(b.dataset.jump)));
  // Flows: pause, restart, product
  $("flow-play").onclick = () => { FLOW.paused = !FLOW.paused; $("flow-play").textContent = FLOW.paused ? "Play" : "Pause"; };
  $("flow-restart").onclick = () => { FLOW.secs = 0; FLOW.paused = false; $("flow-play").textContent = "Pause"; };
  document.querySelectorAll("#flow-route button").forEach(b => (b.onclick = () => {
    FLOW.want = b.dataset.r; FLOW.secs = 0;
    document.querySelectorAll("#flow-route button").forEach(x => x.classList.toggle("on", x === b));
  }));
  // the log holds still while you read it
  $("key").addEventListener("mouseenter", () => (tickHold = true));
  $("key").addEventListener("mouseleave", () => (tickHold = false));
  // the controls hint shows once, then fades
  let seen = false;
  try { seen = localStorage.getItem("fabgym-hint-seen") === "1"; } catch { seen = false; }
  if (seen) $("hint").hidden = true;
  else setTimeout(() => { $("hint").classList.add("fade"); try { localStorage.setItem("fabgym-hint-seen", "1"); } catch { /* private window */ } }, 9000);
  // rest: start paused when the viewer asks for less motion, and pause while the page is hidden
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) { playing = false; $("play").textContent = "▶"; }
  let wasPlaying = null;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { wasPlaying = playing; playing = false; }
    else if (wasPlaying !== null) { playing = wasPlaying; wasPlaying = null; }
  });
  // outage hours only mean something once a group is chosen
  const outage = () => { const on = +$("down-group").value >= 0; $("down-at").disabled = !on; $("down-hours").disabled = !on; };
  $("down-group").addEventListener("change", outage);
  outage();
  glossarySetup();
  journeySetup();
  $("lens-note").addEventListener("click", () => { if (SPOT && SPOT.note) clearSpot(); }); // the glossary's Show me, turned off
  // a link from Build's controls opens the glossary at its term (docs/BUILD-CONTROLS.md, part 5)
  const glTerm = new URLSearchParams(location.search).get("term");
  if (glTerm && FabGlossary.TERMS.some(x => x.term === glTerm)) { if (location.hash !== "#floor") history.replaceState(null, "", `${location.pathname}${location.search}#floor`); markPage && markPage("floor"); openGlossary(glTerm); }
  // one button to follow a lot, and one for prototypes while there are some (docs/SITE-CUTS.md); Live is the floor
  $("follow-open").onclick = () => {
    if (UI.lens === "flows") { if (JOURNEY.on) journeyStop(); setView("day"); return; }
    setView("flows");
    if (G && G.real && !JOURNEY.on) journeyStart();
  };
  $("proto-open").onclick = () => setView(UI.lens === "proto" ? "day" : "proto");
  document.querySelectorAll("#num-metric button").forEach(b => (b.onclick = () => { UI.metric = b.dataset.m; drawNumbers(); }));
  document.querySelectorAll("#num-share button").forEach(b => (b.onclick = () => { UI.share = +b.dataset.s; drawNumbers(); }));
}

function setView(v) {
  UI.lens = v;
  FLOW.secs = 0;
  $("follow-open").textContent = v === "flows" ? "Back to the floor" : "Follow one lot";
  $("proto-open").textContent = v === "proto" ? "Back to the floor" : "Show prototypes";
  $("follow-open").classList.toggle("on", v === "flows");
  $("proto-open").classList.toggle("on", v === "proto");
}

// ------------------------------------------------------------------ the real building (docs/LIVE-REAL.md)
// When the run is today's US building with its fleet, the floor is that building in metres, north up, in the same
// 2.5D look: the halls with their walls, the bays, every tool raised at its place in the colour of its state, the
// drawn rails, which are the simulator's track, the stockers, and every vehicle as the simulator moved it, carrying
// its lot. Zoomed in, a tool working on a lot shows its 25 wafers done one by one over the step.

function realGeometry(B) {
  const xs = B.fabs.flatMap(f => [f[0], f[1]]), ys = B.fabs.flatMap(f => [f[2], f[3]]);
  const X0 = Math.min(...xs), X1 = Math.max(...xs), Y0 = Math.min(...ys), Y1 = Math.max(...ys);
  return { real: true, B, X0, Y1, L: X1 - X0, bottom: Y1 - Y0 };
}
// metres on the plan to the floor's world (north up on the screen)
function rw(x, y) { return [x - G.X0, G.Y1 - y]; }

function realPrepare(run, j, trace) {
  const B = G.B;
  const names = j.groups.map(g => g[0]);
  const boxOf = FabBuilding.toolBoxes(B, names, j.tools);
  const toolOfBox = new Int32Array(B.tools.length).fill(-1);
  boxOf.forEach((b, k) => { if (b >= 0) toolOfBox[b] = k; });
  // the full run's fleet comes prepared from the worker (docs/FLOOR-SPEED.md); a run made here is prepared here
  let nv = run.vehicles || 0, F = run.F || null;
  if (!F) {
    for (let i = 0; i < run.fleetE.length; i += 5) nv = Math.max(nv, run.fleetE[i] + 1);
    for (let i = 0; i < run.fleetH.length; i += 6) nv = Math.max(nv, run.fleetH[i] + 1);
    F = FabBuilding.prepFleet(run.fleetE, run.fleetH, nv, j.until);
  }
  // each tool's steps in start order, for the wafers drawn at a tool
  const steps = Array.from({ length: j.tools.length }, () => []);
  for (let r = 0; r < trace.length / 6; r++) steps[trace[r * 6 + 2]].push([trace[r * 6 + 4], trace[r * 6 + 5], trace[r * 6]]);
  for (const a of steps) a.sort((x, y) => x[0] - y[0]);
  // each group's middle, for its label and its queue
  const mid = j.groups.map(() => [0, 0, 0]);
  B.tools.forEach((b, i) => { const k = toolOfBox[i]; if (k < 0) return; const g = j.tools[k], m = mid[g]; m[0] += (b[1] + b[2]) / 2; m[1] += (b[3] + b[4]) / 2; m[2]++; });
  // the lot to follow in Flows: the one the fleet carries most in the run
  const moves = new Map();
  for (const c of F.carries) for (const x of c) moves.set(x[2], (moves.get(x[2]) || 0) + 1);
  let follow = -1, most = 0;
  for (const [lot, n] of moves) if (n > most || (n === most && lot < follow)) { follow = lot; most = n; }
  return { boxOf, toolOfBox, F, steps, mid, follow, vehicles: nv };
}

function stepAt(list, tt) {
  let lo = 0, hi = list.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (list[m][0] <= tt) lo = m + 1; else hi = m; }
  const k = lo - 1;
  return k >= 0 && list[k][1] > tt ? list[k] : null;
}

const REAL_LOOK = { rail: "rgba(126, 232, 216, 0.55)", spine: "rgba(126, 232, 216, 0.85)", bay: "rgba(126, 232, 216, 0.10)",
  bridge: "#10232A", stocker: "#8a6a2c", stockerTop: "#d9a12b", side: "#0C1A1F", wafer: "#F4E7C6", waferOff: "rgba(244, 231, 198, 0.22)" };

// a raised box: its footprint in metres, h metres tall; front faces darker, the top in `top`, an optional inset panel
function block(x0, x1, y0, y1, h, top, panel, edge) {
  const [ax, ay] = rw(x0, y1), [bx, by] = rw(x1, y0);
  const C = [S(ax, ay), S(bx, ay), S(bx, by), S(ax, by)];
  const hz = TILT.on ? h * view.s * 0.55 : 0;
  screenSpace();
  for (let i = 0; i < 4; i++) {
    const [px, py] = C[i], [qx, qy] = C[(i + 1) % 4];
    if (-(qx - px) <= 0 || !hz) continue;
    ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(qx, qy); ctx.lineTo(qx, qy - hz); ctx.lineTo(px, py - hz); ctx.closePath();
    ctx.fillStyle = REAL_LOOK.side; ctx.fill();
  }
  ctx.beginPath(); C.forEach(([x, y], i) => (i ? ctx.lineTo(x, y - hz) : ctx.moveTo(x, y - hz))); ctx.closePath();
  ctx.fillStyle = top; ctx.fill();
  if (edge) { ctx.strokeStyle = edge; ctx.lineWidth = 1; ctx.stroke(); }
  if (panel) {
    const cx = (C[0][0] + C[2][0]) / 2, cy = (C[0][1] + C[2][1]) / 2 - hz;
    ctx.beginPath(); C.forEach(([x, y], i) => { const X = cx + (x - cx) * 0.55, Y = cy + (y - hz - cy) * 0.55; i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }); ctx.closePath();
    ctx.fillStyle = panel; ctx.fill();
  }
  floorSpace();
  return hz;
}

function drawReal(s) {
  BADGES = []; // filled by groupBadges when the zoom shows labels
  const B = G.B, R = P.real;
  if (!R) return;
  const detail = FabUI.zoomDetail(s);
  const wallH = Math.max(5, 2.2 * s * TILT.k);
  const halls = B.fabs.filter(f => f[5] === "fab");
  if (TILT.on) for (const f of halls) { const [x, y] = rw(f[0], f[3]); hallWalls(x, y, f[1] - f[0], f[3] - f[2], wallH, false); }
  for (const f of B.fabs) {
    const [X, Y] = W(...rw(f[0], f[3]));
    const w = (f[1] - f[0]) * s, h = (f[3] - f[2]) * s;
    ctx.fillStyle = "rgba(0,0,0,0.35)"; ctx.fillRect(X + 0.6 * s, Y + 0.8 * s, w, h);
    ctx.fillStyle = f[5] === "fab" ? pattern("hall") : REAL_LOOK.bridge; ctx.fillRect(X, Y, w, h);
    ctx.strokeStyle = LOOK.wall; ctx.lineWidth = Math.max(1.5, 0.3 * s); ctx.strokeRect(X, Y, w, h);
  }
  ctx.strokeStyle = REAL_LOOK.bay; ctx.lineWidth = 1;
  for (const b of B.bays) { const [X, Y] = W(...rw(b[0], b[3])); ctx.strokeRect(X, Y, (b[1] - b[0]) * s, (b[3] - b[2]) * s); }
  // the rails: the spine pair brighter, the bays' rails over their walls of tools
  const N = B.track.nodes, E = B.track.edges;
  for (const e of E) {
    const a = N[e[0]], b = N[e[1]];
    const spine = Math.abs(a[1] - b[1]) < 1e-6 && Math.abs(a[1]) < 3;
    ctx.strokeStyle = spine ? REAL_LOOK.spine : REAL_LOOK.rail;
    ctx.lineWidth = Math.max(spine ? 1.4 : 0.8, (spine ? 0.35 : 0.2) * s);
    const [ax, ay] = W(...rw(a[0], a[1])), [bx, by] = W(...rw(b[0], b[1]));
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
  }
  // tools, back to front, each the colour of its state; stockers as gold blocks
  const dimTools = UI.lens === "proto" || UI.lens === "flows";
  const order = B.tools.map((b, i) => [S(...rw((b[1] + b[2]) / 2, (b[3] + b[4]) / 2))[1], i]).sort((x, y) => x[0] - y[0]);
  if (dimTools) ctx.globalAlpha = 0.35;
  const followTool = UI.lens === "flows" && R.follow >= 0 ? realToolOfLot(R, R.follow) : -1;
  const jr = JOURNEY.on ? journeyNow() : null;
  if (jr) ctx.globalAlpha = 1;
  const lights = [];
  for (const [, i] of order) {
    const b = B.tools[i], k = R.toolOfBox[i];
    const st = k >= 0 ? cur.toolState[k] : 1;
    let top = LOOK.body, panel = st === 1 ? null : STATE_COLORS[st];
    if (jr) {
      // following one lot: the fab in grey, the tools it has used faintly lit, the one it is at in pink
      const here = k === jr.tool, been = jr.visited.has(k);
      block(b[1], b[2], b[3], b[4], b[7], here ? LOOK.proto : been ? "#3d5a5e" : "#283236", here && jr.kind === "work" ? "#c25aa6" : null, null);
      continue;
    }
    // the editor's look: a dark body, the area's colour as the top panel, and a light for the tool's state
    const area = k >= 0 ? FabLook.areaOf(sim.area[P.j.groups[P.toolGroup[k]][0]]) : null;
    top = "#33434B"; panel = toolPanel(k);
    const off = !spotTool(k);
    if (UI.lens === "heat" && k >= 0) { const q = cur.queue[P.toolGroup[k]]; panel = q > 0 ? FabUI.heatColor(Math.min(1, q / 30)) : "#3A4A52"; }
    if (k === followTool) { ctx.globalAlpha = 1; top = LOOK.proto; }
    if (st === 1 && !dimTools && UI.lens !== "heat") ctx.globalAlpha = 0.55;
    if (off) ctx.globalAlpha = 0.12;
    const hz = block(b[1], b[2], b[3], b[4], b[7], top, panel, "rgba(8,16,20,.9)");
    ctx.globalAlpha = dimTools ? 0.35 : 1;
    if (k >= 0 && st !== 1 && s >= 3 && !off) lights.push([b, hz, STATE_COLORS[st]]);
  }
  ctx.globalAlpha = 1;
  // state lights: a small disc on the top's corner of every tool that is not idle
  if (lights.length) {
    screenSpace();
    const r = Math.max(1.6, Math.min(4, 0.28 * s));
    for (const [b, hz, col] of lights) {
      const [X, Y] = S(...rw(b[1] + 0.22 * (b[2] - b[1]), b[3] + 0.78 * (b[4] - b[3])));
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(X, Y - hz, r, 0, 7); ctx.fill();
      if (r > 2.2) { ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1; ctx.stroke(); }
    }
    floorSpace();
  }
  for (const st of B.stockers) { block(st[0], st[1], st[2], st[3], 4, "#33434B", "#8FB3AE", "rgba(8,16,20,.9)"); }
  if (jr) { followDraw(jr, s); drawFlash(); return; }
  // wafers at a tool: the lot's 25 as a 5 by 5 grid on the working tool's panel, filled one by one over the step
  if (s >= 8) {
    screenSpace();
    for (let i = 0; i < B.tools.length; i++) {
      const k = R.toolOfBox[i];
      if (k < 0 || cur.toolState[k] !== 0) continue;
      const stp = stepAt(R.steps[k], t);
      if (!stp) continue;
      const b = B.tools[i], done = FabBuilding.wafersDone(stp[0], stp[1], t, 25);
      const hz = TILT.on ? b[7] * view.s * 0.55 : 0;
      const r = Math.min(5, Math.max(0.9, 0.055 * Math.min(b[2] - b[1], b[4] - b[3]) * s));
      for (let w = 0; w < 25; w++) {
        const u = 0.25 + 0.5 * ((w % 5) + 0.5) / 5, v = 0.25 + 0.5 * (Math.floor(w / 5) + 0.5) / 5;
        const [X, Y] = S(...rw(b[1] + u * (b[2] - b[1]), b[3] + v * (b[4] - b[3])));
        ctx.beginPath(); ctx.arc(X, Y - hz, r, 0, 2 * Math.PI);
        ctx.fillStyle = w < done ? REAL_LOOK.wafer : "rgba(10, 20, 24, 0.55)"; ctx.fill();
      }
    }
    floorSpace();
  }
  if (TILT.on) for (const f of halls) { const [x, y] = rw(f[0], f[3]); hallWalls(x, y, f[1] - f[0], f[3] - f[2], wallH, true); }
  // labels and queues
  if (detail.names) for (const l of B.labels) { const [X, Y] = W(...rw(l[1], l[2])); ctx.textBaseline = "middle"; plateText(l[0], X, Y, Math.min(22, Math.max(11, 1.6 * s)), 700, LOOK.section); }
  if (detail.names) groupBadges(R, s, detail);
  // the fleet: each vehicle where the simulator had it, carrying its lot
  const now = FabBuilding.vehicles(R.F, N, E, t);
  R.now = now.counts;
  const sz = Math.max(4, 1.1 * s);
  for (const v of now.list) {
    const [X, Y] = W(...rw(v.x, v.y));
    const followed = UI.lens === "flows" && v.lot === R.follow && v.lot >= 0;
    if (UI.lens === "flows" && !followed) ctx.globalAlpha = 0.25;
    if (v.lot >= 0) drawLot(X, Y, followed ? sz * 1.8 : sz, P.lotHot[v.lot], P.lotB[v.lot]);
    else { const [x, y] = T(X, Y); screenSpace(); ctx.fillStyle = "#8FB3AE"; ctx.fillRect(x - sz * 0.35, y - sz * 0.35, sz * 0.7, sz * 0.7); floorSpace(); }
    if (v.state === "hoist" || v.state === "held") {
      const [x, y] = T(X, Y);
      screenSpace();
      ctx.strokeStyle = v.state === "hoist" ? "#6fe3ff" : "#ff6b6b"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(x, y - sz * 0.4, sz * 0.95, 0, 2 * Math.PI); ctx.stroke();
      floorSpace();
    }
    ctx.globalAlpha = 1;
  }
  drawFlash();
}

/** Each group at its tools' centre in the editor's look: an icon tile in the area's colour, its label, its mood badge
 * and, zoomed in further, its lots waiting as pods. */
function groupBadges(R, s, detail) {
  BADGES = [];
  screenSpace();
  const size = Math.max(10, Math.min(15, 0.95 * s));
  R.mid.forEach((m, g) => {
    if (!m[2] || g === P.holdingGroup) return;
    const name = P.j.groups[g][0], area = FabLook.areaOf(sim.area[name]);
    if (!area) return;
    const [x0, y0] = S(...rw(m[0] / m[2], m[1] / m[2]));
    const y = y0 - (TILT.on ? 3 * view.s * 0.55 : 0);
    const text = `${FabLook.label(name, area)} ×${P.j.groups[g][1]}`;
    ctx.font = `600 ${size}px "Chakra Petch",sans-serif`;
    const tw = ctx.measureText(text).width + 8, ic = size * 1.35, w = ic + 3 + tw;
    const xl = x0 - w / 2;
    // the icon tile
    ctx.fillStyle = FabLook.MAT[area]; ctx.beginPath(); ctx.roundRect(xl, y - ic / 2, ic, ic, 3); ctx.fill();
    FabLook.icon(ctx, area, xl + ic / 2, y, ic * 0.78, "#E3ECEE", 2);
    // the label
    const h = FabLook.pill(ctx, text, xl + ic + 3 + tw / 2, y - Math.max(13, size * 1.35) / 2, size);
    // the mood badge on the label's end
    // Running is drawn only on the hovered group, so the badges left are the ones that need a look (docs/FLOOR-REVIEW.md)
    const mood = moodNow(g);
    if (mood && (mood !== "work" || (hover && hover.g === g))) { FabLook.badge(ctx, mood, xl + w + size * 0.55, y, size * 0.62); BADGES.push(mood); }
    if (detail.chips && cur.queue[g] > 0) FabLook.pods(ctx, x0, y + h / 2 + 2, cur.queue[g], h);
  });
  floorSpace();
}

let BADGES = [];
/** A tool's top on the Floor: its area's muted mat (docs/FLOOR-REVIEW.md). */
function toolPanel(k) {
  const area = k >= 0 ? FabLook.areaOf(sim.area[P.j.groups[P.toolGroup[k]][0]]) : null;
  return area ? FabLook.MAT[area] : "#5C5C60";
}

function realToolOfLot(R, lot) {
  for (let k = 0; k < R.steps.length; k++) { const st = stepAt(R.steps[k], t); if (st && st[2] === lot) return k; }
  return -1;
}

function realFollowNote() {
  const R = P && P.real;
  if (!R || R.follow < 0) return "No lot rides the fleet in this run.";
  const name = P.j.lots[R.follow] ? P.j.lots[R.follow][0] : `lot ${R.follow}`;
  const k = realToolOfLot(R, R.follow);
  const where = k >= 0 ? `in ${P.plain[P.toolGroup[k]]}, its wafers going through one by one` : "on the rails or waiting for a tool";
  return `Following ${name}, the lot the fleet moves most in this run: drawn large, now ${where}. Everything else is dimmed.`;
}

function realGroupAt(mx, my) {
  const R = P && P.real;
  if (!R) return null;
  const [ux, uy] = untilt(mx, my);
  const wx = ux / view.s + view.x, wy = uy / view.s + view.y;
  const x = wx + G.X0, y = G.Y1 - wy;
  const B = G.B;
  for (let i = 0; i < B.tools.length; i++) {
    const b = B.tools[i];
    if (x >= b[1] && x <= b[2] && y >= b[3] && y <= b[4] && R.toolOfBox[i] >= 0) return { g: P.toolGroup[R.toolOfBox[i]], mx, my };
  }
  return null;
}

function realBox(areas) {
  const bays = G.B.bays.filter(b => areas.includes(b[4]));
  if (!bays.length) return null;
  const x0 = Math.min(...bays.map(b => b[0])), x1 = Math.max(...bays.map(b => b[1])), y0 = Math.min(...bays.map(b => b[2])), y1 = Math.max(...bays.map(b => b[3]));
  return { bays, x0, x1, y0, y1 };
}

function realFlyTo(areas) {
  const bx = realBox(areas);
  if (!bx) return;
  const pad = floorPad();
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  updateTilt();
  const [sx, sy] = untilt(pad.l + w / 2, pad.t + h / 2);
  const [cx, cy] = rw((bx.x0 + bx.x1) / 2, (bx.y0 + bx.y1) / 2);
  const to = { cx, cy, s: Math.min(40, Math.max(0.5, Math.min(w / (bx.x1 - bx.x0 + 20), h / (bx.y1 - bx.y0 + 20)))) };
  const from = { cx: view.x + sx / view.s, cy: view.y + sy / view.s, s: view.s };
  ST.fly = { from, to, sx, sy, t0: performance.now(), ms: 900 };
  ST.flash = { areas, until: performance.now() + 4500 };
}

function realFlash(f, now) {
  const bx = f.boxes ? { bays: f.boxes.map(b => [b[0], b[1], b[2], b[3]]) } : realBox(f.areas || (HALLS_L[f.i] && HALLS_L[f.i].areas) || []);
  if (!bx) return;
  const a = 0.55 + 0.45 * Math.sin(now / 180);
  ctx.save();
  ctx.strokeStyle = `rgba(240,166,60,${a.toFixed(3)})`;
  ctx.lineWidth = Math.max(2, 0.4 * view.s);
  for (const b of bx.bays) { const [X, Y] = W(...rw(b[0], b[3])); ctx.strokeRect(X, Y, (b[1] - b[0]) * view.s, (b[3] - b[2]) * view.s); }
  ctx.restore();
}

// ------------------------------------------------------------------ one lot from start to finish (docs/LIVE-REAL.md)
// In Flows on the real building: the whole fab in grey, one lot followed through every step of its route, released
// to finished, from the native simulator's journey (web/data/journey.json, `fabsim follow`). Waits pass quickly,
// work and moves slowly; the camera stays with the lot; the slider jumps to any step.
const JOURNEY = { data: null, P: null, on: false, paused: false, rate: 4, p: 0, boxOf: null, loading: false };
const JOURNEY_PACE = { wait: 0.8, work: 1.6, move: 2.4 };

async function journeyStart() {
  if (!JOURNEY.data && !JOURNEY.loading) {
    JOURNEY.loading = true;
    try { JOURNEY.data = await fetch("data/journey.json").then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status)))); }
    catch { $("jr-label").textContent = "The journey is not in this copy of the page. Run web/build.sh."; JOURNEY.loading = false; return; }
    JOURNEY.loading = false;
  }
  if (!JOURNEY.data || !G || !G.real) return;
  JOURNEY.P = FabJourney.plan(JOURNEY.data, JOURNEY_PACE);
  // the journey's tools are the engine's, numbered by group in the shop's order, as in today's run
  JOURNEY.boxOf = P.real ? P.real.boxOf : null;
  JOURNEY.on = true; JOURNEY.paused = false; JOURNEY.p = 0;
  const n = JOURNEY.data.steps.length;
  $("jr-step").max = String(n - 1);
  for (const id of ["jr-play", "jr-rate", "jr-step-l"]) $(id).hidden = false;
  $("follow-lot").textContent = "Stop following";
  $("jr-play").textContent = "Pause";
  const lot = journeyNow();
  if (lot) { view.s = Math.max(view.s, 11); journeyCamera(1, true); }
}

function journeyStop() {
  JOURNEY.on = false;
  for (const id of ["jr-play", "jr-rate", "jr-step-l"]) $(id).hidden = true;
  $("follow-lot").textContent = "Follow one lot, start to finish";
  $("jr-label").textContent = "";
}

/** Where the followed lot is now: its step, what it is doing, the tool, its place on the plan, the tools it has used. */
function journeyNow() {
  const J = JOURNEY.data, a = FabJourney.at(JOURNEY.P, JOURNEY.p);
  if (!a) return null;
  const st = J.steps[a.step];
  const visited = new Set();
  for (let i = 0; i < a.step; i++) visited.add(J.steps[i][2]);
  const N = G.B.track.nodes, E = G.B.track.edges;
  let pos = null, how = a.kind;
  if (a.kind === "move") {
    const w = FabJourney.where(J, N, E, a.t);
    if (w) { pos = [w.x, w.y]; how = w.state === "hoist" ? (w.up ? "up" : "down") : "rail"; }
  }
  // a step in a holding group (lots resting between steps; no tool drawn) shows the lot where it was set down
  const resting = a.kind !== "move" && (G.B.holding || []).includes(st[1]);
  const tool = a.kind === "move" || resting ? -1 : st[2];
  if (!pos) {
    const n = a.kind === "wait" || resting ? FabJourney.lastDrop(J, a.t) : -1;
    if (n >= 0) pos = [N[n][0], N[n][1]];
    else if (JOURNEY.boxOf && JOURNEY.boxOf[st[2]] >= 0) { const b = G.B.tools[JOURNEY.boxOf[st[2]]]; pos = [(b[1] + b[2]) / 2, (b[3] + b[4]) / 2]; }
  }
  return { ...a, how, st, tool, pos, visited, resting, boxOf: JOURNEY.boxOf };
}

function journeyCamera(dt, jump = false) {
  const jr = journeyNow();
  if (!jr || !jr.pos || drag_active()) return;
  const pad = floorPad();
  const w = innerWidth - pad.l - pad.r, h = innerHeight - pad.t - pad.b;
  updateTilt();
  const [sx, sy] = untilt(pad.l + w / 2, pad.t + h / 2);
  const [cx, cy] = rw(jr.pos[0], jr.pos[1]);
  const tx = cx - sx / view.s, ty = cy - sy / view.s;
  const k = jump ? 1 : Math.min(1, dt * (jr.kind === "move" ? 9 : 4));
  view.x += (tx - view.x) * k;
  view.y += (ty - view.y) * k;
}
function drag_active() { return document.querySelector("#floor.drag") !== null; }

function followDraw(jr, s) {
  // the followed tool's wafers, then the lot itself, large and pink
  if (jr.tool >= 0 && jr.boxOf && jr.boxOf[jr.tool] >= 0 && jr.kind === "work") {
    const b = G.B.tools[jr.boxOf[jr.tool]], done = FabBuilding.wafersDone(jr.st[4], jr.st[5], jr.t, JOURNEY.data.wafers || 25);
    const hz = TILT.on ? b[7] * view.s * 0.55 : 0;
    const r = Math.min(6, Math.max(1.2, 0.06 * Math.min(b[2] - b[1], b[4] - b[3]) * s));
    screenSpace();
    for (let w = 0; w < 25; w++) {
      const u = 0.25 + 0.5 * ((w % 5) + 0.5) / 5, v = 0.25 + 0.5 * (Math.floor(w / 5) + 0.5) / 5;
      const [X, Y] = S(...rw(b[1] + u * (b[2] - b[1]), b[3] + v * (b[4] - b[3])));
      ctx.beginPath(); ctx.arc(X, Y - hz, r, 0, 2 * Math.PI);
      ctx.fillStyle = w < done ? REAL_LOOK.wafer : "rgba(10, 20, 24, 0.6)"; ctx.fill();
    }
    floorSpace();
  }
  if (jr.pos && (jr.kind !== "work" || jr.resting)) {
    // the lot as a pod, large and pink, in its own drawing (drawLot dims lots in Flows)
    const [X, Y] = W(...rw(jr.pos[0], jr.pos[1]));
    const [x, y] = T(X, Y), sz = Math.max(10, 1.8 * s), h = sz * 0.75, top = sz * 0.38;
    screenSpace();
    ctx.fillStyle = LOOK.bodyEdge; ctx.fillRect(x - sz / 2 - 1, y - h - top - 1, sz + 2, h + top + 2);
    ctx.fillStyle = LOOK.protoTop; ctx.fillRect(x - sz / 2, y - h, sz, h);
    ctx.fillStyle = LOOK.proto; ctx.fillRect(x - sz / 2, y - h - top, sz, top);
    ctx.strokeStyle = LOOK.proto; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y - h / 2, Math.max(16, 2.4 * s), 0, 2 * Math.PI); ctx.stroke();
    floorSpace();
  }
  const J = JOURNEY.data;
  $("jr-step").value = String(jr.step);
  const day = Math.floor(jr.t / 1440) + 1, m = Math.floor(jr.t % 1440);
  const plainOf = name => P.plain[P.j.groups.findIndex(g => g[0] === name)] || name;
  const next = J.steps[jr.step + 1];
  const doing = jr.resting ? "resting between steps" : jr.kind === "wait" ? `waiting for a tool in ${plainOf(jr.st[1])}` : jr.kind === "work" ? `in ${plainOf(jr.st[1])}, its wafers going through` :
    `${jr.how === "up" ? "hoisted up" : jr.how === "down" ? "set down" : jr.how === "rail" ? "on the rails" : "waiting for a vehicle"} from ${plainOf(jr.st[1])}${next ? ` to ${plainOf(next[1])}` : ""}`;
  $("jr-label").textContent = `Step ${jr.step + 1} of ${J.steps.length} · ${doing} · day ${day} ${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

function journeyNote() {
  const J = JOURNEY.data;
  if (!J) return "";
  const days = J.done !== null ? ((J.done - J.released) / 1440).toFixed(1) : "?";
  return `Following ${J.lot} (${J.wafers} wafers of product 3) through its ${J.steps.length} steps, released day ${Math.floor(J.released / 1440) + 1}, finished ${days} days later. Grey: the rest of the fab. Lit: tools it has used.`;
}

function journeySetup() {
  $("follow-lot").onclick = () => (JOURNEY.on ? journeyStop() : journeyStart());
  $("jr-play").onclick = () => { JOURNEY.paused = !JOURNEY.paused; $("jr-play").textContent = JOURNEY.paused ? "Play" : "Pause"; };
  document.querySelectorAll("#jr-rate button").forEach(b => (b.onclick = () => {
    JOURNEY.rate = +b.dataset.k;
    document.querySelectorAll("#jr-rate button").forEach(x => x.classList.toggle("on", x === b));
  }));
  $("jr-step").oninput = e => { if (JOURNEY.P) { JOURNEY.p = FabJourney.startOf(JOURNEY.P, +e.target.value); journeyCamera(1, true); } };
}

// The Flows view: one wafer's whole route replayed on the track. A lot runs from hall to hall along the spine with
// a glowing tail; every stretch of track brightens each time it passes, so the map fills from nothing. Slow at first,
// faster later (FabUI.journeyDone); after a pause it starts again.
const FLOW = { secs: 0, T: 36, hold: 8, key: null, trips: [], route: "", steps: 0, sOf: [], fin: null, finMax: 1, feedFin: [], feedMax: 1, paused: false, want: "3" };
const FLOW_BINS = 260;

function flowSetup() {
  const routes = HALLS_L.routes || [];
  const key = HALLS_L;
  if (FLOW.key === key && FLOW.keyWant === FLOW.want) return FLOW.trips.length > 0;
  FLOW.key = key;
  FLOW.keyWant = FLOW.want;
  const k = Math.max(0, routes.findIndex(([name]) => new RegExp(`(^|_)${FLOW.want}$`).test(name)));
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
    `From the SMT2020 testbed. The replay starts again in a moment.`;
}

// ------------------------------------------------------------------ the numbers

const FLOOR_WORDS = Object.fromEntries(FabUI.STRATEGIES.map(k => [k, FabUI.floorWord(k)]));
const POLICY_WORDS = Object.fromEntries(FabUI.POLICIES.map(k => [k, FabUI.policyWord(k).replace(/^./, c => c.toLowerCase())]));
const METRIC = {
  profit: { name: "Operating profit a day", unit: "$ a day", higher: true, base: v => FabUI.usd3(v), tick: v => FabUI.usd3(v) },
  a_wafers: { name: "Volume wafers a day", unit: "wafers a day", higher: true, base: v => fmtN(v, 0) },
  b_cycle: { name: "Prototype cycle time", unit: "days", higher: false, base: v => `${fmtN(v, 1)} days` },
};
const LINE_COLORS = ["#7EE8D8", "#FF8AD8", "#FFC857", "#7F9CFF"];
const VERDICT_COLOR = { better: "#4FE3A3", worse: "#FF6262", "no clear effect": "#8FB3AE" };

function fmtN(v, d = 1) { return v === null || v === undefined ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }

async function openNumbers(within) {
  if (!within) openDock("numbers");
  if (!UI.sweep) {
    try {
      UI.sweep = await fetch("data/two-families.json").then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status))));
      if (UI.sweep.pl) UI.sweep = FabUI.withPl(UI.sweep, UI.sweep.pl);
    }
    catch (err) { $("num-lead").textContent = "The sweep's results are not in this build (run web/build.sh)."; return; }
  }
  drawNumbers();
  if (!within) $("dock-close").focus();
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
    lines.push(`<text x="${X(t)}" y="${y + 18}" fill="#A9C4C0" font-size="12" text-anchor="middle">${(m.tick || FabUI.tickLabel)(t)}</text>`);
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
    const mark = r.verdict === "better" ? "✓ " : r.verdict === "worse" ? "✗ " : "· ";
    lines.push(`<text x="${W0 - R + 12}" y="${yy + 4}" fill="#CFE3E0" font-size="12" style="font-variant-numeric: tabular-nums"><tspan fill="${c}">${mark}</tspan>${esc(r.text)}</text>`);
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
  // far points are left off the scale and marked at its edge, so they do not flatten the rest (docs/FLOOR-CLEANUP.md)
  const cr = FabUI.clipRange(lines.flatMap(l => l.points.map(p => p.mean)));
  const inRange = p => p.mean !== null && !cr.off.includes(p.mean);
  const vals = lines.flatMap(l => l.points.flatMap(p => (inRange(p) ? [p.lo, p.hi] : []))).concat([0]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const ticks = FabUI.niceTicks(lo, hi);
  lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
  const Yc = v => Math.max(top, Math.min(H - B, top + (1 - (v - lo) / (hi - lo)) * (H - top - B)));
  const X = i => L + 20 + (i / (shares.length - 1)) * (W0 - L - R - 40);
  const Y = v => top + (1 - (v - lo) / (hi - lo)) * (H - top - B);
  const out = [];
  const si = shares.indexOf(share);
  if (si >= 0) out.push(`<rect x="${X(si) - 18}" y="${top}" width="36" height="${H - top - B}" fill="rgba(126,232,216,0.07)" rx="6"/>`);
  for (const t of ticks) {
    out.push(`<line x1="${L}" x2="${W0 - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="${t === 0 ? "#A9C4C0" : "#1A2E35"}" stroke-width="${t === 0 ? 1.5 : 1}"/>`);
    out.push(`<text x="${L - 8}" y="${Y(t) + 4}" fill="#A9C4C0" font-size="12" text-anchor="end">${(m.tick || FabUI.tickLabel)(t)}</text>`);
  }
  shares.forEach((s, i) => out.push(`<text x="${X(i)}" y="${H - B + 18}" fill="#A9C4C0" font-size="12" text-anchor="middle">×${s}</text>`));
  out.push(`<line x1="${L}" x2="${L}" y1="${top}" y2="${H - B}" stroke="#2C5560"/><line x1="${L}" x2="${W0 - R}" y1="${H - B}" y2="${H - B}" stroke="#2C5560"/>`);
  lines.forEach((l, k) => {
    const c = LINE_COLORS[k % LINE_COLORS.length], dx = (k - 1.5) * 5;
    const pts = l.points.map((p, i) => (p.mean === null ? null : [X(i) + dx, Yc(p.mean), p]));
    const d = pts.filter(Boolean).map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
    out.push(`<path d="${d}" fill="none" stroke="${c}" stroke-width="2"/>`);
    for (const q of pts) if (q) {
      const [x, yv, p] = q;
      if (!inRange(p)) {
        const down = p.mean < lo, ty = down ? H - B - 2 : top + 2;
        out.push(`<path d="M${x - 6},${down ? ty - 9 : ty + 9} L${x + 6},${down ? ty - 9 : ty + 9} L${x},${ty} Z" fill="${c}"/>`);
        out.push(`<text x="${x + 9}" y="${down ? ty - 4 : ty + 12}" fill="${c}" font-size="12">${(m.tick || fmtN)(p.mean)}, off the scale</text>`);
        continue;
      }
      out.push(`<line x1="${x}" x2="${x}" y1="${Yc(p.lo)}" y2="${Yc(p.hi)}" stroke="${c}" stroke-width="2" opacity="0.6"/>`);
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
  $("num-lead").textContent = `The two-family sweep from the SMT2020 testbed. Each change ran for ${d.days} simulated days after ${d.warmup} days of warm-up, on ${d.seeds.length} seeds, ` +
    `and is compared with today's fab on the same seeds. Today's fab means one shared floor and today's dispatch order. ` +
    `Each interval is set at 1 − 0.05/${k}, so all ${k} hold together at 95%. Every price is assumed: see How money is counted below. What these changes would do in a real fab is unknown.`;
  const base = { ...(d.baseline[String(share)] || {}), profit: d.plToday && d.plToday[String(share)] ? d.plToday[String(share)].profit : null };
  $("num-base").innerHTML = Object.entries(METRIC).map(([key, mm]) =>
    `<div class="fact${key === UI.metric ? " on" : ""}"><div class="v">${mm.base(base[key])}</div><div class="l">${mm.name}, today's fab at ×${share}</div></div>`).join("");
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
        text: has ? (qkey === "profit" ? `${FabUI.usd3(c.mean, true)} (${FabUI.usd3(c.lo, true)} to ${FabUI.usd3(c.hi, true)})` : `${FabUI.tickLabel(Math.round(c.mean * 10) / 10)} (${FabUI.tickLabel(Math.round(c.lo * 10) / 10)} to ${FabUI.tickLabel(Math.round(c.hi * 10) / 10)})`) : "no prototype lot out" };
    });
    const q = forestSVG(qrows, m, `Change against today's fab, ${m.unit}`);
    $("num-question").innerHTML = `<figure><figcaption>Your question: ${esc(j.question || "a written scenario")}<span>${esc(m.name)}: each candidate compared with today's fab on ${j.report.seeds.length} paired seeds. The intervals hold together at 95%.</span></figcaption><svg role="img"></svg></figure>`;
    setSVG($("num-question").querySelector("svg"), q, `${m.name} for each candidate in your question`);
  } else $("num-question").innerHTML = "";
  $("num-note").textContent = `Operating profit a day is revenue less materials, running costs and depreciation, in dollars. Capital, payback and the five-year value count what a change buys: tools, their qualification, floor space and, for a wing, a building and a bridge. Every price is assumed. Simulated from the SMT2020 testbed (Kopp, Hassoun, Kalir, Mönch 2020), a published set of a fab's tool groups, routes and times. No real fab's data is used.`;
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
  const U = FabUI.usd3, period = UI.period || "day";
  const g = FabUI.capitalGrid(d, share, period);
  const short = { "P0 today": "Today's order", "P1 family B first": "Prototypes first", "P2 family cap": "Capped at the door",
    "P3 reservation": "A tool kept for prototypes", "P4 qualification": "Half the tools" };
  const pay = c => (!c.capital ? "no capital" : paybackText(c.payback) === "never" ? "never pays back" : paybackText(c.payback)); // never a blank line (docs/EVIDENCE-REVIEW.md)
  const cellHtml = (f, c, ci) => {
    if (c.base) return `<td class="cg-base"><b>today's fab</b><span>the base</span></td>`;
    if (c.missing) return `<td class="cg-na">—</td>`;
    const v = c.verdict === "no clear effect" ? "unclear" : c.verdict;
    return `<td class="cg ${v}${c.best ? " best" : ""}${UI.capPick === `${f.floor}|${c.policy}` ? " picked" : ""}" tabindex="0" data-k="${f.floor}|${c.policy}">` +
      `<b>${U(c.value, true)}</b><span>${esc(pay(c))}</span>${c.best ? '<i class="star" title="best change here">best</i>' : ""}</td>`;
  };
  const head = `<tr><th></th>${g.policies.map(p => `<th>${esc(short[p])}</th>`).join("")}</tr>`;
  const body = g.floors.map(f => `<tr><th class="cg-floor">${esc(FLOOR_WORDS[f.floor])}<span>${f.capital ? `costs ${U(f.capital)}` : "nothing to build"}</span></th>` +
    f.cells.map((c, ci) => cellHtml(f, c, ci)).join("") + `</tr>`).join("");
  // the detail line: the picked cell, else the best one
  const all = g.floors.flatMap(f => f.cells.map(c => ({ f, c }))).filter(x => !x.c.base && !x.c.missing);
  const pick = all.find(x => `${x.f.floor}|${x.c.policy}` === UI.capPick) || all.find(x => x.c.best) || all[0];
  let detail = "";
  if (pick) {
    const { f, c } = pick;
    detail = `<p class="cg-detail"><b>${esc(FLOOR_WORDS[f.floor])}, ${esc(POLICY_WORDS[c.policy])}</b>: ${U(c.value, true)} ${esc(g.unit)} ` +
      `(95%: ${U(c.lo, true)} to ${U(c.hi, true)}), ${esc(c.verdict)}. ` +
      (c.capital ? `Capital ${U(c.capital)}, pays back ${esc(paybackText(c.payback))}. ` : "Nothing to buy. ") +
      `Value over 5 years ${U(c.npv.mean, true)} (${U(c.npv.lo, true)} to ${U(c.npv.hi, true)}).</p>`;
  }
  const ck = (d.pl.checks || []).find(x => x.share === share);
  let check = "";
  if (ck) {
    const name = `${FLOOR_WORDS[ck.strategy].toLowerCase()} with ${POLICY_WORDS[ck.policy]}`;
    const item = k => (d.pl.sheet.find(x => x.key === k) || {}).label || k;
    const moves = ck.items.flatMap(it => [["low", it.low], ["high", it.high]].filter(([, v]) => v.verdict !== ck.verdict).map(([end]) => `the ${item(it.key).replace(/^./, (c) => c.toLowerCase())} is at the ${end} end`));
    check = `<p class="note">The best change here is the ${esc(name)} (${esc(ck.verdict)} on profit). ` +
      (moves.length ? `The answer changes if ${esc(moves.join(", or "))}. Any other single price can move to either end of its range and the answer holds.`
        : "The answer holds when any single price moves to either end of its range.") + "</p>";
  }
  const sheet = FabUI.priceSheetRows(d.pl).map(r => `<tr><td>${esc(r.label)}</td><td class="v">${esc(r.central)}</td><td class="v">${esc(r.range)}</td><td>${r.note}</td></tr>`).join("");
  el.innerHTML = `<div class="cg-head"><h4>What each change buys at ×${share} prototype orders</h4>` +
    `<div class="seg cg-period" role="tablist" aria-label="Profit over">${[["day", "a day"], ["month", "a month"], ["year", "a year"]].map(([k, w]) =>
      `<button type="button" role="tab" aria-selected="${k === period}" class="${k === period ? "on" : ""}" data-p="${k}">Profit ${w}</button>`).join("")}</div></div>` +
    `<table class="capgrid"><thead>${head}</thead><tbody>${body}</tbody></table>` +
    `<p class="note small cg-key"><span class="sw better"></span>better <span class="sw worse"></span>worse <span class="sw unclear"></span>no clear effect · each cell: change in operating profit ${esc(g.unit)} against today's fab, and payback · click a cell for its details</p>` +
    detail + check +
    `<details class="sheet"><summary>How money is counted: the price sheet</summary><table class="captab"><thead><tr><th>Item</th><th>Used</th><th>Range tried</th><th></th></tr></thead><tbody>${sheet}</tbody></table>` +
    `<p class="note small">Today's tools already run the prototype route, so only new tools are qualified. Copies in the halls use spare space there; a wing is a new building. The value over 5 years discounts each day's cash at 10% a year and subtracts the capital.</p></details>`;
  el.querySelectorAll(".cg-period button").forEach(b => (b.onclick = () => { UI.period = b.dataset.p; drawCapital(d, share); }));
  el.querySelectorAll("td.cg").forEach(td => {
    const go = () => { UI.capPick = td.dataset.k; drawCapital(d, share); };
    td.onclick = go;
    td.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
  });
}

// ------------------------------------------------------------------ the Results tab: a log of every run
const RESULTS = { saved: null, page: [], askLogged: new Set() };

// runs kept by the helper beside the questions (docs/RUNS.md, part 3); with no helper (a static copy) nothing is kept
function keepRun(body) {
  fetch("/api/runs/record", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => {});
}
function keepFloorRun(run, opts) {
  if (WATCH || !run || !run.j || new URLSearchParams(location.search).get("q")) return;
  const d = opts.dials || DEFAULT_DIALS, moved = DIAL_KEYS.some(k => d[k] !== DEFAULT_DIALS[k]);
  if (moved || opts.rule || opts.downGroup >= 0) return; // today's fab only; a change on screen is a comparison's
  keepRun({ kind: "floor", key: `floor|${sim.baseUrl}|${opts.seed}|${opts.days}`, title: `Today's fab, run #${opts.seed}`, days: opts.days,
    link: `index.html?run=${opts.seed}#floor`,
    summary: { columns: ["Measure", "Value"], rows: [["Days played", String(opts.days)], ["Lots finished", run.j.finished.toLocaleString("en-US")], ["Moves", run.j.moves.toLocaleString("en-US")]] } });
}

function logCompare(o, base, chg) {
  const seeds = COMPARE_SEEDS.filter(s => base.has(s) && chg.has(s));
  const rows = METRICS.map(m => {
    const d = seeds.map(s => chg.get(s)[m.key] - base.get(s)[m.key]);
    const st = stats(d);
    const v = st.lo > 0 ? (m.higher ? "better" : "worse") : st.hi < 0 ? (m.higher ? "worse" : "better") : "no clear effect";
    const today = seeds.reduce((a, s) => a + base.get(s)[m.key], 0) / seeds.length;
    return [m.name, Math.round(today).toLocaleString("en-US"), fmt(st.mean), `${fmt(st.lo)} to ${fmt(st.hi)}`, v];
  });
  const dials = Object.entries(o.dials || {}).filter(([k, v]) => v !== DEFAULT_DIALS[k]).map(([k, v]) => `${k} ${v === null ? "none" : v}`);
  const settings = [
    ["Change", describe(o)],
    ["Dispatch rule", $("rule").selectedOptions[0] ? $("rule").selectedOptions[0].textContent : String(o.rule)],
    ["Tool group down", o.downGroup >= 0 ? `${$("down-group").selectedOptions[0].textContent} from hour ${o.downAt} for ${o.downHours} h` : "none"],
    ["Dials", dials.length ? dials.join(", ") : "as today"],
    ["Seeds", `${seeds[0]} to ${seeds[seeds.length - 1]} (${seeds.length}), each paired with today's fab on the same seed`],
    ["Days simulated", String(o.days)],
    ["Where", "the simulator in this browser"],
  ];
  const head = rows.find(r => r[4] !== "no clear effect");
  RESULTS.page.unshift(FabUI.runEntry({
    kind: "what-if", title: `Simulation settings: ${describe(o)}`, question: "What does this change do against today's fab on the same seeds?",
    settings, columns: ["Measure", "Today's fab", "Change", "95% interval", "Verdict"], rows,
    headline: head ? `${head[0]}: ${head[2]} (${head[3]}), ${head[4]}.` : "No clear effect on any measure.",
  }));
  if (!$("results").hidden) drawResults();
  // kept by the helper as an S run (docs/RUNS.md, part 3): the change, its settings, every random run's measures
  const pick = q => Object.fromEntries(METRICS.map(m => [m.key, q[m.key]]));
  keepRun({ kind: "settings", title: `Simulation settings: ${describe(o)}`, settings, days: o.days, seeds, arms: ["today", "change"], measure: "wafers_out",
    runs: seeds.flatMap(s => [{ arm: "today", seed: s, values: pick(base.get(s)) }, { arm: "change", seed: s, values: pick(chg.get(s)) }]),
    summary: { columns: ["Measure", "Today's fab", "Change", "95% interval", "Verdict"], rows }, link: `index.html?run=${RUN}#floor` });
}

function logAsk(j) {
  if (!j || !j.report || RESULTS.askLogged.has(j.id)) return;
  RESULTS.askLogged.add(j.id);
  const r = j.report, sc = FabAsk.scenarioLines(j.scenario);
  const rows = [];
  for (const row of FabAsk.resultRows(r)) for (const c of row.cells)
    rows.push([candLabel(j, row.name), c.label, cellNum(c, c.today), cellNum(c, c.mean), c.lo === null || c.mean === null ? "—" : `${cellNum(c, c.lo)} to ${cellNum(c, c.hi)}`, c.verdict]);
  const settings = [["Question", j.question || "a written scenario"], ["Answer from", j.answer_source === "model" ? "the model, checked" : j.answer_source === "example" ? "an example answer we wrote by hand" : "a scenario written by hand"]]
    .concat(sc.given.map(g => ["Given", `${g.text}${g.said ? "" : " (assumed)"}`]))
    .concat(sc.candidates.map(c => [`Candidate: ${c.name}`, c.changes.join("; ")]))
    .concat([["Seeds", `${r.seeds.length} paired seeds`], ["Where", "the helper on this Mac, the simulator run natively"]]);
  RESULTS.page.unshift(FabUI.runEntry({
    kind: "question", title: `Question: ${j.question || "a written scenario"}`, question: j.question || "",
    settings, columns: ["Candidate", "Measure", "Today's fab", "Change", "95% interval", "Verdict"], rows, headline: FabAsk.summaryLine(r),
  }));
  if (!$("results").hidden) drawResults();
}

async function openResults(within) {
  if (!within) openDock("results");
  if (!RESULTS.saved) {
    try { RESULTS.saved = await fetch("data/results.json").then(r => (r.ok ? r.json() : Promise.reject(new Error(r.status)))); }
    catch (err) { RESULTS.saved = []; }
  }
  if (!RESULTS.wired) {
    RESULTS.wired = true;
    $("res-q").oninput = drawResults;
    document.querySelectorAll("#res-kind button").forEach(b => (b.onclick = () => { document.querySelectorAll("#res-kind button").forEach(x => x.classList.toggle("on", x === b)); drawResults(); }));
  }
  drawResults();
  if (!within) $("res-q").focus();
  else $("dock-body").scrollTop = 0;
}

/** A contest's numbers with one row per measure and the contestants side by side (docs/EVIDENCE-REVIEW.md). */
function contestTable(nb) {
  const who = [...new Set(nb.rows.map(r => r[0]))], measures = [...new Set(nb.rows.map(r => r[1]))];
  const cell = (r) => { const v = r[5] === "no clear effect" ? "unclear" : r[5]; return `<td class="v">${esc(r[3])} <small>(${esc(r[4])})</small> <span class="pill ${v}">${esc(r[5])}</span></td>`; };
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  return `<div class="res-scroll"><table class="captab contest"><thead><tr><th>Measure</th><th>Today's rule</th>${who.map(w => `<th>${esc(cap(w))}: change</th>`).join("")}</tr></thead><tbody>` +
    measures.map(m => { const rs = who.map(w => nb.rows.find(r => r[0] === w && r[1] === m)); return `<tr><td>${esc(m)}</td><td class="v">${esc(rs[0][2])}</td>${rs.map(r => (r ? cell(r) : "<td>—</td>")).join("")}</tr>`; }).join("") + "</tbody></table></div>";
}

function drawResults() {
  const kindOn = document.querySelector("#res-kind button.on");
  const all = FabUI.filterResults(RESULTS.page.concat(RESULTS.saved || []), $("res-q").value, kindOn ? kindOn.dataset.k : "all");
  // the badge says the filter's word (docs/EVIDENCE-REVIEW.md), and each filter counts its runs
  const KIND = { sweep: "study", search: "search", training: "training", contest: "contest", "what-if": "your change", question: "your question" };
  const pool = RESULTS.page.concat(RESULTS.saved || []);
  document.querySelectorAll("#res-kind button").forEach(b => {
    if (!b.dataset.label) b.dataset.label = b.textContent.trim();
    const n = b.dataset.k === "all" ? pool.length : pool.filter(e => e.kind === b.dataset.k).length;
    b.textContent = `${b.dataset.label} (${n})`;
  });
  const when = iso => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const table = (cols, rows) => `<div class="res-scroll"><table class="captab"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => `<tr>${r.map((x, i) => `<td class="${i >= cols.length - 1 && /better|worse|no clear/.test(x) ? "" : /^[−+\-$\d]/.test(String(x)) ? "v" : ""}">${/^(better|worse|no clear effect)$/.test(x) ? `<span class="pill ${x === "no clear effect" ? "unclear" : x}">${x}</span>` : esc(String(x))}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
  $("res-list").innerHTML = all.length ? all.map((e, i) => `<details class="res"${i === 0 ? " open" : ""}>
    <summary><span class="kind">${esc(KIND[e.kind] || e.kind)}</span><span class="t">${esc(e.title)}</span><span class="w">${esc(when(e.when))}</span><span class="h">${esc(e.headline)}</span></summary>
    <div class="res-body">${e.question ? `<p class="q">${esc(e.question)}</p>` : ""}
      <h4>Settings in the simulator</h4>${table(["Setting", "Value"], e.settings)}
      <h4>Numbers that came out</h4>${e.kind === "contest" && e.numbers.columns[0] === "Contestant" ? contestTable(e.numbers) : table(e.numbers.columns, e.numbers.rows)}
      ${e.id === "two-families" ? `<p><button type="button" class="link" data-open-numbers>Open it in Numbers</button></p>` : ""}
      ${e.files.length ? `<h4>Files</h4><p class="files">${e.files.map(f => `<code>${esc(f)}</code>`).join(" ")}</p>` : ""}
      ${e.note && !/^Run on a fab built from the SMT2020 testbed/.test(e.note) ? `<p class="note small">${esc(e.note)}</p>` : ""}</div></details>`).join("")
    : `<p class="note">${RESULTS.saved && RESULTS.saved.length ? "No result matches." : "No results in this build (run web/build.sh)."}</p>`;
  $("res-list").querySelectorAll("[data-open-numbers]").forEach(b => (b.onclick = () => openNumbers()));
}

// ------------------------------------------------------------------ the Glossary tab: every term in plain English
const GL = { term: null, order: "az" };
const GL_SOURCE = { published: "Published", assumed: "Assumed by us", choice: "Our choice", standard: "Standard method" };

function openGlossary(term) {
  openDock("glossary");
  if (term) GL.term = term;
  if (!GL.term) GL.term = FabGlossary.find("")[0].term;
  drawGlossaryIndex();
  drawGlossaryArticle();
  $("gl-search").focus();
}

function drawGlossaryIndex() {
  const terms = FabGlossary.find($("gl-search").value);
  const item = t => `<button type="button" class="gl-item${t.term === GL.term ? " on" : ""}" data-term="${esc(t.term)}">${esc(t.term)}</button>`;
  let html = "";
  if (GL.order === "topic") {
    const topics = [...new Set(FabGlossary.TERMS.map(t => t.topic))];
    for (const tp of topics) {
      const ts = terms.filter(t => t.topic === tp);
      if (ts.length) html += `<div class="gl-head">${esc(tp)}</div>` + ts.map(item).join("");
    }
  } else {
    let letter = "";
    for (const t of terms) {
      const L = t.term[0].toUpperCase();
      if (L !== letter) { letter = L; html += `<div class="gl-head">${esc(/[A-Z]/.test(L) ? L : "#")}</div>`; }
      html += item(t);
    }
  }
  $("gl-index").innerHTML = html || `<p class="note">No term matches.</p>`;
}

// ------------------------------------------------------------------ the glossary, part 2: right now, and Show me
// Each countable word's reading of the run on screen, the Floor's own count, and what Show me lights
// (docs/GLOSSARY-PLUS.md, part 2). null for a word the run cannot count.
const AREA_TERMS = { "Lithography": ["litho"], "Etch": ["dry", "wet"], "Polishing (CMP)": ["cmp"], "Checks (metrology)": ["lithomet", "tfmet", "defmet"] };
function liveFor(term) {
  if (!P || !P.j || P.quick) return null;
  const h = health(), n = x => Number(x).toLocaleString("en-US"), T = h.tools;
  if (AREA_TERMS[term]) {
    let total = 0, working = 0;
    for (let k = 0; k < P.nT; k++) if (P.toolGroup[k] !== P.holdingGroup && AREA_TERMS[term].includes(areaOfToolK(k))) { total++; if (cur.toolState[k] === 0) working++; }
    return { text: `${n(working)} of ${n(total)} ${term.replace(/ \(.*\)$/, "").toLowerCase()} machines working.`, show: { kind: "area", a: AREA_TERMS[term] }, lit: `the ${term.replace(/ \(.*\)$/, "").toLowerCase()} machines` };
  }
  const hot = (cur.hotQ || []).reduce((a, b) => a + b, 0);
  switch (term) {
    case "Breakdown": case "Repair time":
      return { text: `${n(T.down)} of ${n(h.nT)} machines broken down.`, show: { kind: "state", s: 3 }, lit: "the machines broken down now" };
    case "Setup change": return { text: `${n(T.setup)} machines changing setup.`, show: { kind: "state", s: 4 }, lit: "the machines changing setup now" };
    case "Tool": return { text: `${n(T.working)} working, ${n(T.idle)} idle, ${n(T.maintenance)} in maintenance, ${n(T.down)} broken down and ${n(T.setup)} changing setup, of ${n(h.nT)} machines.` };
    case "WIP": return { text: `${n(h.inFab)} lots in the fab; ${n(h.waiting)} wait for a machine.`, show: { kind: "waiting" }, lit: "the groups where lots wait" };
    case "Lot": return { text: `${n(h.finished)} lots finished so far; ${n(h.inFab)} in the fab, ${n(h.waiting)} waiting.`, show: { kind: "waiting" }, lit: "the groups where lots wait" };
    case "Wafer": return { text: `${n(h.wafersOut)} wafers out so far.` };
    case "Cycle time": return { text: h.cycleDays ? `${h.cycleDays.toFixed(2)} days a wafer, over the ${n(h.finished)} lots finished so far.` : "No lot has finished yet." };
    case "Tool group": return h.longest.g >= 0 ? { text: `The longest line is at ${h.longest.name}: ${n(h.longest.lots)} lots.`, show: { kind: "longest", g: h.longest.g }, lit: `the longest line, at ${h.longest.name}` } : null;
    case "Hot lot": return { text: `${n(hot)} urgent lot${hot === 1 ? "" : "s"} waiting for a machine.`, show: { kind: "hot" }, lit: "the groups where urgent lots wait" };
    case "Track (overhead track)": return { text: `${n(h.moving)} lots on the move.` };
    case "Seed": return { text: `This is run #${RUN}.` };
    case "Simulator": return { text: `This page simulated ${P.j.until / 1440} days of the fab in ${P.secs ? P.secs.toFixed(1) : "?"} s.` };
    default: return null;
  }
}
function liveHtml(term) {
  const l = liveFor(term);
  if (!l) return "";
  return `<div class="gl-live" id="gl-live"><span class="gl-live-h">Right now</span> <span id="gl-live-text">${esc(l.text)}</span>${l.show ? ` <button type="button" class="link" data-show>Show me</button>` : ""}</div>`;
}
function showMe(term) {
  const l = liveFor(term);
  if (!l || !l.show) return;
  closeDock();
  if (l.show.kind === "longest") { flyToGroup(l.show.g); return; }
  SPOT = { ...l.show, note: `Lit: ${l.lit}. Esc or a click here turns it off.` };
  document.querySelectorAll("#health .row.spot").forEach(r => r.classList.remove("on"));
  draw();
}
let glLiveTimer = null;
function keepLiveFresh() {
  clearInterval(glLiveTimer);
  glLiveTimer = setInterval(() => {
    const el = $("gl-live-text");
    if (!el || $("dock").hidden || DOCK.tab !== "glossary") return;
    const l = liveFor(GL.term);
    if (l && el.textContent !== l.text) el.textContent = l.text;
  }, 500);
}

function drawGlossaryArticle() {
  const t = FabGlossary.TERMS.find(x => x.term === GL.term);
  if (!t) { $("gl-article").innerHTML = ""; return; }
  const link = name => `<button type="button" class="gl-see" data-term="${esc(name)}">${esc(name)}</button>`;
  // the newcomer's view first (picture, one plain line, the figure, this fab, an example), the expert's in a fold
  // (docs/GLOSSARY-PLUS.md)
  const fig = t.figure && window.FabGlossaryFigs && FabGlossaryFigs.FIGS[t.figure];
  $("gl-article").innerHTML = `<div class="gl-lead"><img class="gl-pic" src="${esc(t.picture)}" alt="${esc(t.plain || "")}" width="128" height="128" onerror="this.onerror=null;this.classList.add('missing');this.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'">` +
    `<div><div class="gl-topic">${esc(t.topic)}</div><h3>${esc(t.term)}</h3><p class="gl-plain">${esc(t.plain || t.meaning)}</p>` +
    (FabGlossary.shownAliases(t).length ? `<p class="gl-aka">Also: ${FabGlossary.shownAliases(t).map(esc).join(", ")}</p>` : "") + `</div></div>` +
    liveHtml(t.term) +
    (fig ? `<figure class="gl-fig">${FabGlossaryFigs.draw(t.figure)}<figcaption>${esc(fig.caption)}</figcaption></figure>` : "") +
    `<h4>In this fab</h4><p>${esc(t.here)}</p>` +
    `<h4>Example</h4><p>${esc(t.example)}</p>` +
    `<details class="gl-expert"><summary>For experts</summary>` +
    `<h4>Definition</h4><p class="gl-def">${esc(t.meaning)}</p>` +
    (t.formula ? `<h4>Formula</h4><p class="gl-formula">${esc(t.formula)}</p>` : "") +
    `<h4>Where it comes from</h4><p><span class="gl-src ${t.source.kind}">${GL_SOURCE[t.source.kind]}</span> ${esc(t.source.text)}` +
    (t.source.range ? `<br><span class="note">Range tried: ${esc(t.source.range)}</span>` : "") + `</p></details>` +
    `<h4>See also</h4><p class="gl-links">${t.see.map(link).join(" ")}</p>`;
  $("gl-article").scrollTop = 0;
  const sb = $("gl-article").querySelector("#gl-live [data-show]");
  if (sb) sb.onclick = () => showMe(t.term);
  keepLiveFresh();
}

function glossarySetup() {
  $("gl-search").oninput = drawGlossaryIndex;
  $("gl-index").onclick = e => { const b = e.target.closest("[data-term]"); if (b) { GL.term = b.dataset.term; drawGlossaryIndex(); drawGlossaryArticle(); } };
  $("gl-article").onclick = e => { const b = e.target.closest("[data-term]"); if (b) { GL.term = b.dataset.term; drawGlossaryIndex(); drawGlossaryArticle(); } };
  document.querySelectorAll(".gl-order button").forEach(b => (b.onclick = () => {
    GL.order = b.dataset.o;
    document.querySelectorAll(".gl-order button").forEach(x => x.classList.toggle("on", x === b));
    drawGlossaryIndex();
  }));
  // technical words in the page's notes open their article
  document.addEventListener("click", e => { const b = e.target.closest("button.gl"); if (b) { e.preventDefault(); openGlossary(b.dataset.term); } });
  const wrap = el => {
    if (!el || el.dataset.glText === el.textContent) return;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: n => (n.parentElement.closest("button, code, svg, .gl, table, h4") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    const seen = new Set();
    for (const n of nodes) {
      const segs = FabGlossary.linkify(n.nodeValue).map(s => (s.term && seen.has(s.term) ? { text: s.text } : s));
      if (!segs.some(s => s.term)) continue;
      const frag = document.createDocumentFragment();
      for (const s of segs) {
        if (!s.term) { frag.appendChild(document.createTextNode(s.text)); continue; }
        seen.add(s.term);
        const b = document.createElement("button");
        b.type = "button"; b.className = "gl"; b.dataset.term = s.term; b.textContent = s.text; b.title = `What is “${s.term}”?`;
        frag.appendChild(b);
      }
      n.parentNode.replaceChild(frag, n);
    }
    el.dataset.glText = el.textContent;
  };
  for (const id of ["lens-note", "num-lead", "num-note", "cmp-what", "cmp-note", "long-lead", "long-note", "num-capital", "ask-result", "res-list"]) {
    const el = $(id);
    if (!el) continue;
    new MutationObserver(() => wrap(el)).observe(el, { childList: true, characterData: true, subtree: true });
  }
}

// ------------------------------------------------------------------ the evidence: verdict cards and signing

function verdictCards(rows) {
  const best = rows.find(r => r.best) || rows[0];
  if (!best) return "";
  return `<p class="note">${esc(best.name)} compared with today's fab:</p><div class="verdicts">${best.cells.map(c => {
    const v = c.mean === null ? "no clear effect" : c.verdict;
    return `<div class="vcard ${v === "no clear effect" ? "" : v}"><div class="l">${esc(c.label)}</div><div class="v">${c.mean === null ? "—" : c.key === "profit" || c.key === "cash" ? FabUI.usd3(c.mean, true) : FabUI.tickLabel(Math.round(c.mean * 10) / 10)}</div>` +
      `<div class="iv">${c.lo === null || c.mean === null ? "" : c.key === "profit" || c.key === "cash" ? `${FabUI.usd3(c.lo, true)} to ${FabUI.usd3(c.hi, true)}` : `${fmtN(c.lo)} to ${fmtN(c.hi)}`}</div><span class="pill ${v === "no clear effect" ? "unclear" : v}">${v}</span></div>`;
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
      `<p class="note small">Both halves replay seed 0 for 3 days in your browser.${scenes[1].rc.exact ? "" : " The page's simulator cannot run this candidate's rule, so its half uses today's rule."} The cards come from the helper's full scored run. From the SMT2020 testbed.</p>`;
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
    t = Math.min(c.end, t + stepOf(dt));
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
  ctx.fillStyle = k === 0 ? LOOK.title : LOOK.section;
  ctx.fillText(title, vp.x + vp.w / 2, 140);
  ctx.font = "500 12px -apple-system, Inter, sans-serif";
  ctx.fillStyle = LOOK.sub;
  ctx.fillText(line, vp.x + vp.w / 2, 162);
  ctx.textAlign = "left";
}

main();
