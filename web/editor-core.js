// The map editor's pure parts (docs/EDITOR.md): templates, the map as a fab file, and a block's mood from a run.
// In the page this defines window.FabEditor; under Node, module.exports. A fab built from the SMT2020 testbed
// (a published set of a fab's tool groups, routes and times), or a teaching fab of our own; not a real fab.
(function (root) {
  "use strict";

  const TILE_M = 3; // metres a tile (decided by quiz 31 Oct)
  // the cast's areas (web/cast/cast.json), in the order the templates lay them out
  const AREAS = ["litho", "lithomet", "dry", "wet", "diff", "diel", "tf", "tfmet", "imp", "cmp", "defmet"];
  const AREA_OF = { Litho: "litho", Litho_Met: "lithomet", Dry_Etch: "dry", Wet_Etch: "wet", Diffusion: "diff", Dielectric: "diel", TF: "tf", TF_Met: "tfmet", Implant: "imp", Planar: "cmp", Def_Met: "defmet" };
  // a tie between moods goes to the more serious
  const SERIOUS = ["hurt", "physio", "hold", "full", "tired", "batch", "setup", "pm", "sleep", "work"];
  const D = [[1, 0], [0, 1], [-1, 0], [0, -1]];

  // The teaching fab: one small group per cast area and an 18-step route, a lot every 30 minutes (all assumed).
  const T_GROUPS = [["Litho_T", 3], ["Litho_Met_T", 1], ["Dry_Etch_T", 3], ["Wet_Etch_T", 3], ["Diffusion_T", 2], ["Dielectric_T", 1], ["TF_T", 2], ["TF_Met_T", 1], ["Implant_T", 1], ["Planar_T", 2], ["Def_Met_T", 1]];
  const T_ROUTE = ["Diffusion_T", "Litho_T", "Litho_Met_T", "Dry_Etch_T", "Wet_Etch_T", "TF_T", "TF_Met_T", "Planar_T", "Def_Met_T", "Implant_T", "Litho_T", "Litho_Met_T", "Dry_Etch_T", "Wet_Etch_T", "Dielectric_T", "Planar_T", "Def_Met_T", "Wet_Etch_T"];
  const T_MINUTES = { Litho_T: 40, Litho_Met_T: 12, Dry_Etch_T: 35, Wet_Etch_T: 25, Diffusion_T: 50, Dielectric_T: 20, TF_T: 30, TF_Met_T: 10, Implant_T: 18, Planar_T: 35, Def_Met_T: 14 };
  const step = (g) => `step\t${g}\tlot\t${T_MINUTES[g].toFixed(1)}\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-`;
  const TEACHING_SHOP = ["fabgym-shop 1", "transport\t0.0\t0.0", ...T_GROUPS.map(([g, n]) => `group\t${g}\t${n}\t0.0\t0.0\t-\t-\t-`), "route\tteach", ...T_ROUTE.map(step), "release\tteach\t25\t1.0\t30.0\t0.0\t-\tLot", ""].join("\n");

  const key = (x, y) => `${x},${y}`;
  const nodeId = (x, y) => `c${x}_${y}`;
  function cellOfNode(id) {
    const m = /^c(\d+)_(\d+)$/.exec(id);
    return m ? [Number(m[1]), Number(m[2])] : null;
  }

  /** A fab laid out in bays by area along a two-lane spine with U-turns at both ends. `groups`: [{name, area, count}];
   * `depth`: rows of blocks above and below the spine (even). Each bay holds two columns of 2x2 blocks round its
   * one-way loop, its last slot a stocker. */
  function bays(groups, depth, stores) {
    const perCol = depth / 2, perBay = 2 * perCol - 1;
    const nb = Math.max(1, Math.ceil(groups.length / perBay));
    const north = Math.ceil(nb / 2);
    const ys = 2 + depth; // north lane; the south lane is ys + 1
    const yb = ys + 2 + depth; // the south bays' far rail
    const W = 2 + 6 * north + 3, H = yb + 1;
    const rail = {};
    const out = (x, y, d, spine) => {
      const k = key(x, y);
      if (!rail[k]) rail[k] = { o: [0, 0, 0, 0] };
      if (d != null) rail[k].o[d] = 1;
      if (spine) rail[k].spine = true;
    };
    for (let x = 1; x <= W - 3; x++) out(x, ys, 0, true);
    out(W - 2, ys, 1, true);
    for (let x = W - 2; x >= 2; x--) out(x, ys + 1, 2, true);
    out(1, ys + 1, 3, true);
    const blocks = [];
    let gi = 0, id = 1;
    const place = (x, y, bayGroups) => {
      if (bayGroups.length) {
        const g = bayGroups.shift();
        blocks.push({ id: id++, kind: "group", group: g.name, area: g.area, count: g.count, x, y, w: 2, h: 2 });
      }
    };
    for (let b = 0; b < nb; b++) {
      const south = b >= north, a = 2 + 6 * (south ? b - north : b);
      const mine = groups.slice(gi, gi + perBay);
      gi += perBay;
      if (!south) {
        out(a, ys, 3);
        for (let y = ys - 1; y >= 2; y--) out(a, y, 3);
        out(a, 1, 0); out(a + 1, 1, 0); out(a + 2, 1, 0); out(a + 3, 1, 1);
        for (let y = 2; y < ys; y++) out(a + 3, y, 1);
        for (let r = 0; r < perCol; r++) place(a + 1, 2 + 2 * r, mine);
        for (let r = 0; r < perCol - 1; r++) place(a + 4, 2 + 2 * r, mine);
        blocks.push({ id: id++, kind: "stocker", x: a + 4, y: 2 + 2 * (perCol - 1), w: 2, h: 2 });
      } else {
        out(a + 3, ys + 1, 1);
        for (let y = ys + 2; y < yb; y++) out(a + 3, y, 1);
        out(a + 3, yb, 2); out(a + 2, yb, 2); out(a + 1, yb, 2); out(a, yb, 3);
        for (let y = yb - 1; y >= ys + 2; y--) out(a, y, 3);
        for (let r = 0; r < perCol; r++) place(a + 1, ys + 2 + 2 * r, mine);
        for (let r = 0; r < perCol - 1; r++) place(a + 4, ys + 2 + 2 * r, mine);
        blocks.push({ id: id++, kind: "stocker", x: a + 4, y: ys + 2 + 2 * (perCol - 1), w: 2, h: 2 });
      }
    }
    blocks.push({ id: id++, kind: "entry", x: 0, y: ys, w: 1, h: 2 });
    blocks.push({ id: id++, kind: "exit", x: W - 1, y: ys, w: 1, h: 2 });
    return { W, H, blocks, rail, stores: stores || [] };
  }

  /** A template: "teaching", or "smt2020" with {shop, areas} (the floor page's web/data files). */
  function template(name, data) {
    if (name === "teaching") {
      const groups = T_GROUPS.map(([g, n]) => ({ name: g, area: AREA_OF[g.replace(/_T$/, "")], count: n }));
      const s = bays(groups, 4, []);
      s.vehicles = 12;
      return s;
    }
    if (name === "smt2020") {
      const areaOf = {};
      for (const l of data.areas.split("\n")) {
        const [g, a] = l.split("\t");
        if (g) areaOf[g] = a;
      }
      const groups = [], stores = [];
      for (const l of data.shop.split("\n")) {
        if (!l.startsWith("group\t")) continue;
        const f = l.split("\t");
        const area = AREA_OF[areaOf[f[1]]];
        if (!area) stores.push(f[1]);
        else groups.push({ name: f[1], area, count: Number(f[2]) });
      }
      groups.sort((a, b) => AREAS.indexOf(a.area) - AREAS.indexOf(b.area) || (a.name < b.name ? -1 : 1));
      const s = bays(groups, 8, stores);
      s.vehicles = 120;
      return s;
    }
    throw new Error(`no template ${name}`);
  }

  /** Rail cells beside a block (its border ring, corners left out), in a fixed order. */
  function beside(s, b) {
    const cells = [];
    for (let x = b.x; x < b.x + b.w; x++) cells.push([x, b.y - 1], [x, b.y + b.h]);
    for (let y = b.y; y < b.y + b.h; y++) cells.push([b.x - 1, y], [b.x + b.w, y]);
    return cells.filter(([x, y]) => s.rail[key(x, y)]);
  }

  /** The map's plan records (docs/FAB-FILE.md). */
  function toPlan(s) {
    const lines = [];
    const cells = Object.keys(s.rail).map((k) => k.split(",").map(Number)).sort((a, b) => a[1] - b[1] || a[0] - b[0]);
    for (const [x, y] of cells) lines.push(`node\t${nodeId(x, y)}\t${(x * TILE_M).toFixed(1)}\t${(y * TILE_M).toFixed(1)}`);
    for (const [x, y] of cells) {
      s.rail[key(x, y)].o.forEach((on, d) => {
        const nx = x + D[d][0], ny = y + D[d][1];
        if (on && s.rail[key(nx, ny)]) lines.push(`link\t${nodeId(x, y)}\t${nodeId(nx, ny)}\t${TILE_M.toFixed(1)}`);
      });
    }
    const groups = s.blocks.filter((b) => b.kind === "group");
    for (const b of groups) lines.push(`station\t${b.group}\t${(b.x * TILE_M).toFixed(1)}\t${(b.y * TILE_M).toFixed(1)}\t${(b.w * TILE_M).toFixed(1)}\t${(b.h * TILE_M).toFixed(1)}`);
    for (const b of groups) {
      const c = beside(s, b);
      if (!c.length) continue;
      for (let k = 0; k < b.count; k++) lines.push(`stop\t${b.group}\t${k}\t${nodeId(...c[k % c.length])}`);
    }
    const seen = new Set();
    for (const b of s.blocks.filter((b) => b.kind === "stocker")) {
      const c = beside(s, b)[0];
      if (c && !seen.has(nodeId(...c))) {
        seen.add(nodeId(...c));
        lines.push(`stocker\t${nodeId(...c)}`);
      }
    }
    for (const kind of ["entry", "exit"]) {
      for (const b of s.blocks.filter((b) => b.kind === kind)) {
        const c = beside(s, b)[0];
        if (c) lines.push(`${kind}\t${nodeId(...c)}`);
      }
    }
    for (const g of s.stores || []) lines.push(`store\t${g}`);
    return lines;
  }

  /** The fab file: the base shop with each placed group's count set, a fleet when the base has none, and the plan. */
  function fabText(base, s, opts) {
    const counts = {};
    for (const b of s.blocks) if (b.kind === "group") counts[b.group] = b.count;
    const vehicles = (opts && opts.vehicles) || s.vehicles || 12;
    const out = [];
    let fleet = base.split("\n").some((l) => l.startsWith("fleet\t"));
    for (const l of base.split("\n")) {
      if (!l) continue;
      if (l.startsWith("group\t")) {
        const f = l.split("\t");
        if (counts[f[1]] != null) f[2] = String(counts[f[1]]);
        out.push(f.join("\t"));
      } else out.push(l);
      if (!fleet && l.startsWith("transport\t")) {
        out.push(`fleet\t${vehicles}\t3.0\t1.0\t2\t60.0\tnearest`);
        fleet = true;
      }
    }
    if (s.cap) out.splice(out.findIndex((l) => l.startsWith("transport\t")) + 1, 0, `cap\t${s.cap}`);
    const prices = (opts && opts.prices === false) ? [] : s.blocks.filter((b) => b.kind === "group" && PRICE[b.area])
      .map((b) => `price\t${b.group}\t${PRICE[b.area].toFixed(1)}\t${(PRICE[b.area] / 2000).toFixed(1)}`);
    return [...out, ...toPlan(s), ...prices, ""].join("\n");
  }

  // Dollars to buy one tool of an area (assumed for the gym; not any vendor's price). Running cost a day is 1/2000.
  const PRICE = { litho: 60e6, lithomet: 8e6, dry: 6e6, wet: 4e6, diff: 5e6, diel: 6e6, tf: 7e6, tfmet: 3e6, imp: 9e6, cmp: 5e6, defmet: 10e6 };

  /** Dollars spent on tools, spares included. */
  function spend(s) {
    let d = 0;
    for (const b of s.blocks) {
      if (b.kind !== "group" || !PRICE[b.area]) continue;
      d += b.count * PRICE[b.area];
      if (b.rec && b.rec.kind === "swap_to_spare") d += (b.rec.spares || 0) * PRICE[b.area];
    }
    return d;
  }

  /** The selection widget's failures and recoveries as an overrides file (docs/OVERRIDES.md); null when none is set. */
  function overridesFor(s) {
    const groups = {}, rails = {};
    for (const b of s.blocks) {
      if (b.kind !== "group" || !(b.fail || b.rec)) continue;
      groups[b.group] = {};
      if (b.fail) groups[b.group].breakdowns = b.fail;
      if (b.rec) groups[b.group].recovery = b.rec;
    }
    for (const k of Object.keys(s.rail)) {
      const v = s.rail[k];
      if (!v.fail) continue;
      const [x, y] = k.split(",").map(Number);
      v.o.forEach((on, d) => {
        const nx = x + D[d][0], ny = y + D[d][1];
        if (on && s.rail[key(nx, ny)]) rails[`${nodeId(x, y)}>${nodeId(nx, ny)}`] = { breakdowns: v.fail, recovery: v.rec || { kind: "wait" } };
      });
    }
    if (!Object.keys(groups).length && !Object.keys(rails).length) return null;
    const ov = { "fabgym-overrides": 1 };
    if (Object.keys(groups).length) ov.groups = groups;
    if (Object.keys(rails).length) ov.rails = rails;
    return ov;
  }

  /** Does a run's score meet a challenge's target, having spent `extra` dollars on top? */
  function meets(score, target, extra) {
    if (!score || !(score.wafers_per_day >= target.wafers)) return false;
    if (target.jams != null && score.jams > target.jams) return false;
    if (target.budget != null && extra > target.budget) return false;
    return true;
  }

  /** Where each vehicle is at `t` in a replay window: stays are [vehicle, from, to, t_in, t_out|null, loaded, hot]. */
  function vehicleAt(stays, t) {
    const out = [];
    for (const [vehicle, from, to, tin, tout, loaded, hot] of stays) {
      if (t < tin || (tout != null && t >= tout)) continue;
      const a = cellOfNode(from), b = cellOfNode(to);
      if (!a || !b) continue;
      const f = tout == null || tout <= tin ? 0 : (t - tin) / (tout - tin);
      out.push({ vehicle, x: a[0] + (b[0] - a[0]) * f, y: a[1] + (b[1] - a[1]) * f, loaded, hot });
    }
    return out;
  }

  // ---------- the challenges (docs/EDITOR-TAKE-TWO.md), calibrated on the simulator on 31 Oct, two days, seed 1
  const teach = () => ({ state: template("teaching"), base: TEACHING_SHOP, overrides: null });
  const groupBlock = (st, g) => st.blocks.find((b) => b.group === g);
  const withOverrides = (x) => ((x.overrides = overridesFor(x.state)), x);
  function laneCell(st, x) {
    const ys = Math.min(...Object.keys(st.rail).filter((k) => st.rail[k].spine).map((k) => Number(k.split(",")[1])));
    return key(x, ys);
  }
  const CHALLENGES = [
    {
      id: "rush", title: "Rush hour on the spine", days: 2,
      problem: "A piece of the main track by the lithography bay keeps breaking down, and every car behind it sits and waits.",
      goal: "Get output up to 670 wafers a day. Hint: the bay's own loop can carry the cars around the break.",
      target: { wafers: 670, budget: 0 },
      setup() { const x = teach(); const v = x.state.rail[laneCell(x.state, 3)]; v.fail = { kind: "random", mttf_minutes: 120, mttr_minutes: 90 }; v.rec = { kind: "wait" }; return withOverrides(x); },
      fix(x) { x.state.rail[laneCell(x.state, 3)].rec = { kind: "route_around" }; return withOverrides(x); },
    },
    {
      id: "polisher", title: "The gassed polisher", days: 2,
      problem: "The whole fab shares one polishing machine. It cannot keep up, and work piles up in front of it.",
      goal: "Get output up to 780 wafers a day. You can afford one more polishing machine.",
      target: { wafers: 780, budget: PRICE.cmp },
      setup() { const x = teach(); groupBlock(x.state, "Planar_T").count = 1; return x; },
      fix(x) { groupBlock(x.state, "Planar_T").count = 2; return x; },
    },
    {
      id: "breakdown", title: "Breakdown, no spare", days: 2,
      problem: "The lithography machines break every few hours, and each repair takes three hours on the spot.",
      goal: "Get output up to 550 wafers a day. You can afford one more lithography machine, or one spare to swap in.",
      target: { wafers: 550, budget: PRICE.litho },
      setup() { const x = teach(); const b = groupBlock(x.state, "Litho_T"); b.fail = { kind: "random", mttf_minutes: 240, mttr_minutes: 180 }; return withOverrides(x); },
      fix(x) { groupBlock(x.state, "Litho_T").rec = { kind: "swap_to_spare", spares: 1, swap_minutes: 20 }; return withOverrides(x); },
    },
    {
      id: "lean", title: "Lean or redundant?", days: 2,
      problem: "On day two the polishing machines are down for ten hours. Do you keep the fab lean, or pay for a backup?",
      goal: "Keep output at 650 wafers a day through the outage. You can afford one more polishing machine.",
      target: { wafers: 650, budget: PRICE.cmp },
      setup() { const x = teach(); x.base = TEACHING_SHOP.replace(/(group\tPlanar_T\t\d+\t[^\n]*)/, "$1\ndown\t1800.0\t2400.0"); return x; },
      fix(x) { groupBlock(x.state, "Planar_T").count = 3; return x; },
    },
  ];

  /** A block's mood at a frame: the most common mood among its group's tools; a tie to the more serious. */
  function blockMood(m, frame, group) {
    const f = m.frames[frame];
    const n = {};
    m.groups.forEach((g, i) => {
      if (g === group) {
        const mood = m.tool_moods[f.tools[i]];
        n[mood] = (n[mood] || 0) + 1;
      }
    });
    const moods = Object.keys(n);
    if (!moods.length) return null;
    moods.sort((a, b) => n[b] - n[a] || SERIOUS.indexOf(a) - SERIOUS.indexOf(b));
    return moods[0];
  }

  // ---------- the editor's basics (docs/EDITOR-BASICS.md)

  /** Undo and redo. Push the state before each step; undo and redo take the state now and give the one to show.
   * At most `limit` steps are kept; every state kept is a copy. */
  function History(limit) {
    const copy = (x) => JSON.parse(JSON.stringify(x));
    let back = [], fwd = [];
    return {
      push(st) { back.push(copy(st)); if (back.length > limit) back.shift(); fwd = []; },
      undo(now) { if (!back.length) return null; fwd.push(copy(now)); return back.pop(); },
      redo(now) { if (!fwd.length) return null; back.push(copy(now)); return fwd.pop(); },
      canUndo: () => back.length > 0,
      canRedo: () => fwd.length > 0,
      clear() { back = []; fwd = []; },
    };
  }

  /** Zoom a view ({s, ox, oy}: screen = o + world × s) by `factor` about the screen point (px, py), keeping s within
   * [lo, hi]; the point under (px, py) stays there. */
  function zoomAt(v, factor, px, py, lo, hi) {
    const sc = Math.max(lo, Math.min(hi, v.s * factor)), f = sc / v.s;
    return { s: sc, ox: px - (px - v.ox) * f, oy: py - (py - v.oy) * f };
  }

  function panBy(v, dx, dy) {
    return { s: v.s, ox: v.ox + dx, oy: v.oy + dy };
  }

  /** Whether a w × h footprint at (x, y) is clear of the floor's edge, track and other blocks (`skipId` may stay). */
  function isFree(st, x, y, w, h, skipId) {
    if (x < 0 || y < 0 || x + w > st.W || y + h > st.H) return { ok: false, why: "Off the edge of the floor." };
    for (let i = 0; i < w; i++) {
      for (let j = 0; j < h; j++) {
        if (st.rail[key(x + i, y + j)]) return { ok: false, why: "Track is in the way." };
        const b = st.blocks.find((z) => z.id !== skipId && x + i >= z.x && x + i < z.x + z.w && y + j >= z.y && y + j < z.y + z.h);
        if (b) return { ok: false, why: b.kind === "group" ? "A machine is in the way." : "Something is in the way." };
      }
    }
    return { ok: true, why: "" };
  }

  /** A block's footprint in tiles: wafers in and out are 1 × 2, the rest 2 × 2. */
  const footprint = (kind) => (kind === "entry" || kind === "exit" ? [1, 2] : [2, 2]);

  /** The ghost of a block about to be placed at (x, y): its footprint and whether it fits. */
  function ghost(st, kind, x, y) {
    const [w, h] = footprint(kind), f = isFree(st, x, y, w, h);
    return { kind, x, y, w, h, ok: f.ok, why: f.why };
  }

  const api = { TILE_M, AREAS, AREA_OF, TEACHING_SHOP, PRICE, CHALLENGES, template, toPlan, fabText, blockMood, cellOfNode, beside, key, spend, overridesFor, meets, vehicleAt,
    History, zoomAt, panBy, isFree, footprint, ghost };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabEditor = api;
})(typeof window !== "undefined" ? window : globalThis);
