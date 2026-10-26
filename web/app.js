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
  const pad = { l: 24, r: innerWidth > 900 ? 330 : 24, t: 140, b: 80 };
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

function drawBelt(points, phase) {
  const s = view.s;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#111417";
  ctx.lineWidth = Math.max(9, 2.6 * s);
  ctx.beginPath();
  points.forEach(([x, y], i) => { const [X, Y] = W(x, y); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); });
  ctx.stroke();
  ctx.strokeStyle = "#3d454f";
  ctx.lineWidth = Math.max(6, 1.9 * s);
  ctx.stroke();
  const u = Math.max(3, s);
  ctx.setLineDash([0.9 * u, 1.1 * u]);
  ctx.lineDashOffset = -phase * u;
  ctx.strokeStyle = "rgba(214, 178, 96, 0.75)";
  ctx.lineWidth = Math.max(2, 0.45 * s);
  ctx.stroke();
  ctx.setLineDash([]);
}

function draw() {
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#1c2127";
  ctx.fillRect(0, 0, innerWidth, innerHeight);
  if (!G || !P) return;
  const s = view.s;
  // floor tiles
  if (s > 3) {
    ctx.strokeStyle = "rgba(255,255,255,0.025)";
    ctx.lineWidth = 1;
    const step = 8;
    const x0 = Math.floor(view.x / step) * step, y0 = Math.floor(view.y / step) * step;
    ctx.beginPath();
    for (let x = x0; x < view.x + innerWidth / s; x += step) { const [X] = W(x, 0); ctx.moveTo(X, 0); ctx.lineTo(X, innerHeight); }
    for (let y = y0; y < view.y + innerHeight / s; y += step) { const [, Y] = W(0, y); ctx.moveTo(0, Y); ctx.lineTo(innerWidth, Y); }
    ctx.stroke();
  }
  // the spine
  const phase = (t * 0.6) % 2;
  drawBelt([[0, G.yTop], [G.L, G.yTop], [G.L, G.yBot], [0, G.yBot], [0, G.yTop]], phase);
  // feeders from each hall's door to the spine
  HALLS_L.forEach((h, i) => {
    const p = G.pos[i];
    const by = p.belt === "top" ? G.yTop : G.yBot;
    drawBelt([[p.door.x, p.door.y], [p.door.x, by]], phase);
  });
  // halls
  const showLabels = s > 2.6;
  HALLS_L.forEach((h, i) => {
    const p = G.pos[i];
    const [X, Y] = W(p.x, p.y);
    rr(X, Y, h.w * s, h.h * s, 1.2 * s);
    ctx.fillStyle = "#252b32";
    ctx.fill();
    ctx.strokeStyle = "#46505b";
    ctx.lineWidth = Math.max(1, 0.35 * s);
    ctx.stroke();
    // door
    const [DX, DY] = W(p.door.x - 2, p.door.y - 0.5);
    ctx.fillStyle = "#c9a34e";
    ctx.fillRect(DX, DY, 4 * s, 1 * s);
    // title
    ctx.fillStyle = "#e3e8ee";
    ctx.textBaseline = "top";
    const toolsN = h.groups.reduce((a, g) => a + P.j.groups[g][1], 0);
    const tsz = Math.max(12, 2.6 * s);
    ctx.font = `650 ${tsz}px -apple-system, Inter, sans-serif`;
    const tw = ctx.measureText(h.name).width;
    ctx.fillText(h.name, X + 1.5 * s, Y + 1.0 * s);
    if (h.w * s > tw + 70) {
      ctx.fillStyle = "#8d98a5";
      ctx.font = `${Math.max(11, 1.5 * s)}px -apple-system, Inter, sans-serif`;
      const label = h.areas[0] === "Delay_32" ? "between steps" : `${toolsN} tools`;
      ctx.fillText(label, X + 1.5 * s + tw + 8, Y + 1.0 * s + (tsz - Math.max(11, 1.5 * s)) * 0.8);
    }
    // cells
    for (const c of h.cells) {
      const cx = p.x + 3 + c.x, cy = p.y + c.y;
      if (c.label) {
        if (showLabels) {
          ctx.fillStyle = "#c9a34e";
          ctx.font = `600 ${1.6 * s}px -apple-system, Inter, sans-serif`;
          const [LX, LY] = W(cx, cy + 0.3);
          ctx.fillText(c.label.toUpperCase(), LX, LY);
        }
        continue;
      }
      drawGroup(c, cx, cy, showLabels);
    }
  });
  // lots in transit
  ctx.lineWidth = Math.max(1, 0.15 * s);
  for (const tr of cur.active) {
    const [x, y] = tripPoint(tr, t);
    const [X, Y] = W(x, y);
    ctx.beginPath();
    ctx.arc(X, Y, Math.max(2.4, 0.8 * s), 0, 2 * Math.PI);
    ctx.fillStyle = tr[4] ? HOT : LOT;
    ctx.fill();
    ctx.strokeStyle = "#14171b";
    ctx.stroke();
  }
}

function drawGroup(c, cx, cy, showLabels) {
  const s = view.s;
  const g = c.gi;
  const G0 = P.j.groups[g];
  const toolIds = P.groupTools[g];
  if (c.holding) {
    const [X, Y] = W(cx, cy + 2);
    rr(X, Y, c.w * s, 6 * s, 0.8 * s);
    ctx.fillStyle = "#2c333b";
    ctx.fill();
    ctx.fillStyle = "#e3e8ee";
    ctx.font = `600 ${Math.max(10, 2.2 * s)}px -apple-system, Inter, sans-serif`;
    ctx.fillText(`${cur.holdingBusy} lots`, X + 1.2 * s, Y + 1.4 * s);
    return;
  }
  // machines
  for (let k = 0; k < toolIds.length; k++) {
    const col = k % c.cols, row = Math.floor(k / c.cols);
    const [X, Y] = W(cx + 1 + col * PITCH, cy + 1 + row * PITCH);
    const st = cur.toolState[toolIds[k]];
    if (st === 1) {
      // idle: an outline
      rr(X + 0.25 * s, Y + 0.25 * s, (TOOL - 0.5) * s, (TOOL - 0.5) * s, 0.45 * s);
      ctx.strokeStyle = STATE_COLORS[1];
      ctx.lineWidth = Math.max(1, 0.4 * s);
      ctx.stroke();
      continue;
    }
    rr(X, Y, TOOL * s, TOOL * s, 0.5 * s);
    ctx.fillStyle = STATE_COLORS[st];
    ctx.fill();
    if (st === 3) {
      // broken down: a cross
      ctx.strokeStyle = "#1c2127";
      ctx.lineWidth = Math.max(1, 0.45 * s);
      ctx.beginPath();
      ctx.moveTo(X + 0.8 * s, Y + 0.8 * s); ctx.lineTo(X + 2.2 * s, Y + 2.2 * s);
      ctx.moveTo(X + 2.2 * s, Y + 0.8 * s); ctx.lineTo(X + 0.8 * s, Y + 2.2 * s);
      ctx.stroke();
    } else if (s > 3) {
      ctx.fillStyle = "rgba(0,0,0,0.16)";
      ctx.fillRect(X + 0.8 * s, Y + 0.8 * s, 1.4 * s, 1.4 * s);
    }
  }
  const yLabel = cy + 1 + c.rows * PITCH;
  if (showLabels) {
    const [LX, LY] = W(cx + 1, yLabel + 0.2);
    ctx.fillStyle = "#aab4bf";
    ctx.font = `${1.5 * s}px -apple-system, Inter, sans-serif`;
    ctx.fillText(P.plain[g], LX, LY);
  }
  // queue belt with its waiting lots
  const qy = yLabel + 3;
  const [BX, BY] = W(cx + 1, qy);
  const bw = c.w - 2;
  ctx.fillStyle = "#2c3138";
  ctx.fillRect(BX, BY - 0.9 * s, bw * s, 1.8 * s);
  const n = cur.queue[g], hot = cur.hotQ[g];
  const fits = Math.max(0, Math.floor((bw - 0.5) / 1.6));
  const shown = Math.min(n, n > fits ? fits - 2 : fits);
  for (let k = 0; k < shown; k++) {
    const [X, Y] = W(cx + 1.8 + k * 1.6, qy);
    ctx.beginPath();
    ctx.arc(X, Y, 0.62 * s, 0, 2 * Math.PI);
    ctx.fillStyle = k < hot ? HOT : LOT;
    ctx.fill();
  }
  if (n > shown && s > 1.2) {
    ctx.fillStyle = "#efe2c4";
    ctx.font = `600 ${1.4 * s}px -apple-system, Inter, sans-serif`;
    ctx.textBaseline = "middle";
    const [X, Y] = W(cx + 1.8 + shown * 1.6 - 0.4, qy);
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
}

let lastFrame = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;
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
    `<span class="m">mean wait over the run:</span> ${avgWait.toFixed(0)} min`;
  tip.hidden = false;
  tip.style.left = Math.min(innerWidth - 230, h.mx + 14) + "px";
  tip.style.top = Math.min(innerHeight - 140, h.my + 14) + "px";
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
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.key === " ") { e.preventDefault(); $("play").click(); }
    if (e.key === "f" || e.key === "F") fit();
  });
  addEventListener("resize", () => { resize(); });
  $("run").onclick = rerun;
}

function rerun() {
  const opts = {
    seed: +$("seed").value || 0,
    days: Math.min(14, Math.max(1, +$("days").value || 3)),
    rule: +$("rule").value,
    downGroup: +$("down-group").value,
    downAt: +$("down-at").value || 0,
    downHours: +$("down-hours").value || 0,
  };
  $("runnote").textContent = "Simulating…";
  setTimeout(() => {
    const run = simulate(opts);
    load(run);
    const moves = run.j.moves.toLocaleString();
    $("runnote").textContent = `Simulated ${opts.days} day${opts.days > 1 ? "s" : ""} (${moves} moves, ${run.j.decisions.toLocaleString()} dispatch decisions) in ${run.secs.toFixed(2)} s, here in your browser.`;
  }, 20);
}

function load(run) {
  const hallOfGroup = HALLS_L.hallOfGroup;
  P = prepare(run, HALLS_L, hallOfGroup);
  P.groupTools = Array.from({ length: P.nG }, () => []);
  P.toolGroup.forEach((g, k) => P.groupTools[g].push(k));
  P.plain = P.j.groups.map(g => plainGroup(g[0], sim.area[g[0]]));
  P.holdingGroup = P.j.groups.findIndex(g => sim.area[g[0]] === "Delay_32");
  cur = makeCursor(P);
  t = 0;
  playing = true;
  $("play").textContent = "❚❚";
  $("scrub").max = P.j.until;
  drawSpark();
}

async function main() {
  resize();
  setupInput();
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
  const padR = innerWidth > 900 ? 330 : 24;
  TARGET_ASPECT = Math.max(1.0, Math.min(2.4, (innerWidth - padR - 24) / (innerHeight - 220)));
  G = placeHalls(HALLS_L, flows);
  const sel = $("down-group");
  groups
    .map((g, i) => [plainGroup(g.name, sim.area[g.name]), i])
    .filter(([, i]) => sim.area[groups[i].name] !== "Delay_32")
    .sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
    .forEach(([name, i]) => { const o = document.createElement("option"); o.value = i; o.textContent = name; sel.appendChild(o); });
  load(first);
  fit();
  $("runnote").textContent = `Simulated 3 days (${first.j.moves.toLocaleString()} moves) in ${first.secs.toFixed(2)} s, here in your browser.`;
}

main();
