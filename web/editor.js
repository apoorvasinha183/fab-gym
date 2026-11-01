// Editor take two (docs/EDITOR-TAKE-TWO.md): the page opens on a challenge already run and plays an exact replay of
// the simulator's vehicles, with every machine's mood and queue from the same run. Build pauses it; Run again scores
// the new layout on the same seed. The pure parts are in editor-core.js. On a teaching fab of our own and the SMT2020
// model; never a real fab.
(function () {
  "use strict";
  const E = window.FabEditor;
  const $ = (id) => document.getElementById(id);
  const D = [[1, 0], [0, 1], [-1, 0], [0, -1]];
  const DN = ["E", "S", "W", "N"], DLONG = ["east", "south", "west", "north"];
  const WINDOW = 30; // fab minutes in one replay window

  // ---------- the cast, from the shared look (web/look.js)
  const L = window.FabLook;
  const FAM = FabLook.FAM, LOT = FabLook.LOTS, IC = FabLook.ICONS, svg = FabLook.svg;
  const AREA = {}, SHORT = {}, MOOD = {};
  for (const a in L.AREA) { AREA[a] = [L.AREA[a].name, L.AREA[a].exercise, L.AREA[a].about]; SHORT[a] = L.AREA[a].short; }
  for (const m in L.MOOD) MOOD[m] = [L.MOOD[m].name, L.MOOD[m].color, L.MOOD[m].badge];
  const INFRA = { stocker: ["Storage", "Holds lots whose next machine's ports are full; a car brings them back when a port frees."], entry: ["Wafers in", "New lots enter the fab here."], exit: ["Wafers out", "Finished lots leave the fab here."] };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const money = (d) => (Math.abs(d) >= 1e6 ? `$${(d / 1e6).toFixed(d % 1e6 ? 1 : 0)}M` : `$${Math.round(d).toLocaleString()}`);

  // ---------- state
  let chIdx = 0; // 0..3 a challenge, 4 free build
  // the run watched (docs/RANDOM-RUNS.md): run #1 is the challenge's own, which always gives the score and the stars
  let watch = 1;
  let setupNow = null, base = E.TEACHING_SHOP, s = null, spend0 = 0, areaOfGroup = {}, start = null;
  let run = null, prev = null, stale = false, running = false;
  let mode = "run", playing = !matchMedia("(prefers-reduced-motion: reduce)").matches, speed = 20; // fab minutes a real second, the floor's steps (docs/EDITOR-SPEED.md)
  const MAX = -1; // the Max step: one fab hour each drawn frame, no cars
  let lastCars = 0;
  // the editor as a game (docs/EDITOR-GAME.md)
  let aiPlaying = false, pendingEdits = false; // Race the AI (docs/RACE-AI.md)
  let cursorCell = null, jamMap = false, showLast = false, prevRun = null, flashes = [], lastEditAt = null, lastBadges = [], lastDrawFi = 0, lastLabels = [];
  let clock = 0, win = null, nextWin = null, fetching = false;
  let tool = "select", sel = null, hover = null, drag = null, flash = null, checks = null, checkTimer = null;
  // the editor's basics (docs/EDITOR-BASICS.md): the view, undo, the ghost, runs made by themselves
  let V = null, FIT = null, ghostAt = null, panDrag = null, spaceHeld = false, spacePanned = false, lastSnap = null, rerunTimer = null, runSeq = 0, runsDone = 0;
  const hist = E.History(200);
  // the foreman keys (docs/EDITOR-MOVES.md): recent pieces for the hotbar, a turned piece in hand, the box, the clipboard
  let recent = [], handTurned = false, boxSel = null, boxDrag = null, clip = null, pasting = false, pastePlan = null;
  let routeFrom = null, routePlan = null, healGaps = null; // part 8
  const PIECES = new Set(["stocker", "entry", "exit", ...E.AREAS]);
  /** Take a tool in hand, as the palette, a hotbar key or Q does; a piece goes to the front of the recent list. */
  function take(t) {
    if (!allowed(t)) { $("status").textContent = "This challenge needs only the tools in the palette."; return false; }
    // a machine in hand places one where it is clicked, in its group, or the group itself if not yet placed (docs/BUILD-CONTROLS.md)
    tool = t; handTurned = false; pasting = false;
    if (PIECES.has(t)) { recent = [t, ...recent.filter((x) => x !== t)].slice(0, 6); buildPalette(); }
    if (tool !== "select" && mode === "run") setMode("build");
    syncPal(); draw();
    return true;
  }
  /** The footprint of the piece in hand: wafers in and out may be turned with R. */
  function handDims(kind) {
    const [w, h] = E.footprint(kind);
    return handTurned && (kind === "entry" || kind === "exit") ? [h, w] : [w, h];
  }
  /** Unplaced groups of each kind, for a paste. */
  /** The machine groups this fab's base file has (a blueprint may come from another fab, part 8). */
  const knownGroups = () => new Set(base.split("\n").filter((l) => l.startsWith("group\t")).map((l) => l.split("\t")[1]));
  function unplaced() {
    const placed = new Set(s.blocks.filter((b) => b.kind === "group").map((b) => b.group)), out = {};
    for (const g of Object.keys(areaOfGroup)) {
      const a = areaOfGroup[g];
      if (placed.has(g) || (s.stores || []).includes(g) || !base.includes(`group\t${g}\t`)) continue;
      (out[a] = out[a] || []).push(g);
    }
    return out;
  }
  /** The floor cell under a pointer, ignoring pieces drawn in front (for the box and a paste). */
  function floorCell(e) {
    const r = cv.getBoundingClientRect(), [fx, fy] = unP(e.clientX - r.left, e.clientY - r.top);
    return [Math.floor(fx), Math.floor(fy)];
  }
  const met = new Set();
  try { for (const id of JSON.parse(localStorage.getItem("fabgym.met") || "[]")) met.add(id); } catch (e) { /* no storage */ }
  // best stars per challenge, kept in this browser (docs/EDITOR-ROOM.md)
  let best = {};
  try { best = JSON.parse(localStorage.getItem("fabgym.stars") || "{}") || {}; } catch (e) { best = {}; }
  const ch = () => (chIdx < E.CHALLENGES.length ? E.CHALLENGES[chIdx] : null);
  // a challenge run with a port limit, or with any of the Floor's settings changed, is an experiment: its targets are
  // tuned with unlimited ports and today's settings, so it earns no stars (docs/BUILD-CONTROLS.md, parts 3 and 4)
  const flowSet = () => !!(s && s.flow && Object.keys(s.flow).length);
  const experiment = () => !!(ch() && s && (s.inports || flowSet()));
  const starsFor = (sc, c, top) => (experiment() ? 0 : E.stars(sc, c.target, top));
  const meetsFor = (sc, c, top) => !experiment() && E.meets(sc, c.target, top);
  const days = () => (ch() ? ch().days : 2);
  const fab = () => E.fabText(base, s, { vehicles: s.vehicles });

  async function post(path, body) {
    try {
      const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) {
      return { error: "The helper did not answer. Start it with: python3 -m agent.helper" };
    }
  }

  // the helper does one job at a time and answers "busy" meanwhile: checks, runs and the first window of a jump wait
  // their turn (docs/EDITOR-SPEED.md)
  async function postWait(path, body) {
    for (let i = 0; ; i++) {
      const r = await post(path, body);
      if (!r.busy || i >= 50) return r;
      await new Promise((ok) => setTimeout(ok, 60));
    }
  }
  let busyUntil = 0; // a prefetch told "busy" steps back for a moment

  // ---------- the 2.5D floor
  // straight down (docs/EDITOR-TOPDOWN.md): x across, y down, square tiles
  const ISO = { r: 0, q: 1, pad: 0.03 };
  const cv = $("map"), ctx = cv.getContext("2d");
  let F = null, room = null;
  function fit(cw) {
    const co = Math.cos(ISO.r), sn = Math.sin(ISO.r);
    const M = 1.5; // a tile and a half of paper all round (docs/EDITOR-ROOM.md)
    const pts = [[-M, -M], [s.W + M, -M], [-M, s.H + M], [s.W + M, s.H + M]].map(([x, y]) => [x * co - y * sn, (x * sn + y * co) * ISO.q]);
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const wx = Math.max(...xs) - Math.min(...xs), wy = Math.max(...ys) - Math.min(...ys), pad = cw * ISO.pad;
    // the smaller of the column's width and the window's height below the map, never under 360 px (docs/EDITOR-TOPDOWN.md)
    // kept until the room changes by 8 px or more, so small reflows above the map do not make it breathe
    // everything the page holds below the map (the playback bar, the status line, the page's own padding) stays in the
    // window (docs/BUILD-REVIEW.md)
    // measured from the map's own column and the page's fixed padding, never from the side column, so the answer does
    // not depend on the map's own height (an earlier version fed back on itself)
    const cr = cv.getBoundingClientRect(), col = cv.closest(".mapcol"), ed = $("editor"), cs = getComputedStyle(ed);
    const colBelow = col ? col.getBoundingClientRect().bottom - cr.bottom : 0;
    const edPad = parseFloat(cs.paddingBottom) + parseFloat(cs.borderBottomWidth);
    const after = Math.max(0, document.documentElement.scrollHeight - (ed.getBoundingClientRect().bottom + window.scrollY));
    const below = colBelow + edPad + after;
    // fit the window when that leaves the map 330 px or more; in a shorter window keep the old 430 px and let the page
    // scroll (D8: the floor stays usable)
    const avail = window.innerHeight - (cr.top + window.scrollY) - below, r = avail >= 300 ? avail : 430; // at least 300 px of map before the page may scroll (docs/BUILD-CONTROLS.md)
    if (room == null || Math.abs(r - room) >= 8) room = r;
    const sc = Math.min((cw - 2 * pad) / wx, (room - 2 * pad) / wy);
    const lift = 0, depth = 0;
    return { s: sc, co, sn, ox: (cw - wx * sc) / 2 - Math.min(...xs) * sc, oy: pad + lift - Math.min(...ys) * sc, ch: wy * sc + 2 * pad + lift + depth, depth };
  }
  const P = (x, y, z) => [F.ox + (x * F.co - y * F.sn) * F.s, F.oy + (x * F.sn + y * F.co) * ISO.q * F.s - (z || 0) * F.s];
  const unP = (sx, sy) => { const X = (sx - F.ox) / F.s, Y = (sy - F.oy) / (ISO.q * F.s); return [X * F.co + Y * F.sn, -X * F.sn + Y * F.co]; };
  function poly(pts) { ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath(); }
  const icon = (name, cx, cy, size, col, lw) => L.icon(ctx, name, cx, cy, size, col, lw);
  function prism(bs, tp, side, top) {
    const faces = [0, 1, 2, 3].map((q) => ({ p: [bs[q], bs[(q + 1) % 4], tp[(q + 1) % 4], tp[q]], d: (bs[q][1] + bs[(q + 1) % 4][1]) / 2 })).sort((a, c) => a.d - c.d);
    faces.forEach((f, k) => { poly(f.p); ctx.fillStyle = k >= 2 ? side : "#141D22"; ctx.fill(); ctx.strokeStyle = "rgba(8,16,20,.9)"; ctx.lineWidth = 1; ctx.stroke(); });
    poly(tp); ctx.fillStyle = top; ctx.fill(); ctx.strokeStyle = "rgba(255,255,255,.16)"; ctx.lineWidth = 1; ctx.stroke();
  }

  const frameIdx = () => (run ? Math.max(0, Math.min(run.frames.length - 1, Math.floor(clock / run.every))) : 0);
  const showRun = () => run && !stale;

  function draw() {
    const dpr = window.devicePixelRatio || 1, cw = cv.parentElement.clientWidth || 800;
    FIT = fit(cw);
    F = V ? { ...FIT, s: V.s, ox: V.ox, oy: V.oy } : FIT;
    cv.width = Math.round(cw * dpr); cv.height = Math.round(F.ch * dpr); cv.style.height = F.ch + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const g = ctx.createRadialGradient(cw / 2, F.ch * 0.45, 10, cw / 2, F.ch * 0.45, cw * 0.7);
    g.addColorStop(0, "#16323A"); g.addColorStop(0.6, "#0B1418"); g.addColorStop(1, "#070C0F");
    ctx.fillStyle = g; ctx.fillRect(0, 0, cw, F.ch);
    const slab = [P(0, 0), P(s.W, 0), P(s.W, s.H), P(0, s.H)];
    poly(slab); ctx.fillStyle = "#11242A"; ctx.fill();
    // paper to draw on, all over the map (docs/EDITOR-GAME.md, docs/EDITOR-ROOM.md): a fine line per tile, a stronger one every five
    const [ux0, uy0] = unP(0, 0), [ux1, uy1] = unP(cw, F.ch), gx0 = Math.floor(Math.min(ux0, ux1)), gx1 = Math.ceil(Math.max(ux0, ux1)), gy0 = Math.floor(Math.min(uy0, uy1)), gy1 = Math.ceil(Math.max(uy0, uy1));
    for (const [step, a] of [[1, 0.07], [5, 0.16]]) {
      ctx.strokeStyle = `rgba(126,232,216,${a})`; ctx.lineWidth = 1; ctx.beginPath();
      for (let x = Math.ceil(gx0 / step) * step; x <= gx1; x += step) { const p0 = P(x, gy0), p1 = P(x, gy1); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(p1[0], p1[1]); }
      for (let y = Math.ceil(gy0 / step) * step; y <= gy1; y += step) { const p0 = P(gx0, y), p1 = P(gx1, y); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(p1[0], p1[1]); }
      ctx.stroke();
    }
    poly(slab); ctx.save(); ctx.setLineDash([6, 5]); ctx.strokeStyle = "rgba(126,232,216,.35)"; ctx.lineWidth = 1.2; ctx.stroke(); ctx.restore();
    const fi = frameIdx(), fr = showRun() ? run.frames[fi] : null;
    const jam = {}, jamWas = {};
    if (fr) run.stretches.forEach((n, i) => (jam[n] = fr.rails[i]));
    const pf = prevRun && prevRun.frames[Math.min(fi, prevRun.frames.length - 1)];
    if (pf) prevRun.stretches.forEach((n, i) => (jamWas[n] = pf.rails[i]));
    lastDrawFi = fi;
    const nowMs = performance.now();
    flashes = flashes.filter((f) => f.until > nowMs);
    const flashing = new Set(flashes.flatMap((f) => f.stretches));
    const bad = new Set((checks && checks.issues ? checks.issues : []).filter((i) => i.severity === "error").flatMap((i) => i.at));
    // rail
    const breaks = [];
    for (const k of Object.keys(s.rail)) {
      const [x, y] = k.split(",").map(Number), v = s.rail[k];
      v.o.forEach((on, d) => {
        if (!on) return;
        const live = !!s.rail[E.key(x + D[d][0], y + D[d][1])];
        const a = P(x + 0.5, y + 0.5, 0.06), b = P(x + 0.5 + D[d][0] * (live ? 1 : 0.45), y + 0.5 + D[d][1] * (live ? 1 : 0.45), 0.06);
        const sn = `c${x}_${y}>c${x + D[d][0]}_${y + D[d][1]}`, j = jam[sn] || 0, js = E.jamStyle(j);
        const calm = v.spine ? "#2F6470" : "#285059";
        ctx.save();
        ctx.strokeStyle = bad.has(`c${x}_${y}`) ? "#FF6B57" : js.kind === "red" ? "#FF6B57" : js.kind === "amber" ? "#F2B33D" : calm;
        if (js.kind !== "calm") { ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = js.kind === "red" ? 10 : 5; }
        if (jamMap && js.kind === "calm") ctx.globalAlpha = 0.35;
        ctx.lineWidth = Math.max(2, F.s * 0.3) * js.width; ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        ctx.restore();
        if (flashing.has(sn)) { ctx.save(); ctx.strokeStyle = "rgba(126,232,216,.85)"; ctx.shadowColor = "#7EE8D8"; ctx.shadowBlur = 14; ctx.lineWidth = Math.max(3, F.s * 0.5); ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); ctx.restore(); }
        if (showLast && (jamWas[sn] || 0) > 0.2) { ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = (jamWas[sn] || 0) > 1 ? "rgba(199,146,255,.95)" : "rgba(199,146,255,.6)"; ctx.lineWidth = Math.max(2, F.s * 0.22); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); ctx.restore(); }
        if ((x + y) % 2 === 0 || v.o.reduce((p, q) => p + q) > 1) {
          const m = P(x + 0.5 + D[d][0] * 0.5, y + 0.5 + D[d][1] * 0.5, 0.06), ang = Math.atan2(b[1] - a[1], b[0] - a[0]), r = Math.max(2, F.s * 0.13);
          ctx.save(); ctx.translate(m[0], m[1]); ctx.rotate(ang); ctx.strokeStyle = "rgba(126,232,216,.75)"; ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.moveTo(-r * 0.6, -r); ctx.lineTo(r * 0.6, 0); ctx.lineTo(-r * 0.6, r); ctx.stroke(); ctx.restore();
        }
      });
      if (v.fail) breaks.push(P(x + 0.5, y + 0.5, 0.06));
      if (sel && sel.rail === k) { poly([P(x, y), P(x + 1, y), P(x + 1, y + 1), P(x, y + 1)]); ctx.strokeStyle = "#7EE8D8"; ctx.lineWidth = 2; ctx.stroke(); }
    }
    // raised things back to front: blocks and vehicles
    const items = s.blocks.map((b) => ({ b, d: P(b.x + b.w / 2, b.y + b.h / 2)[1] }));
    const vs = showRun() && win && speed !== MAX ? vehicles(clock) : [];
    lastCars = vs.length;
    for (const v of vs) items.push({ v, d: P(v.x + 0.5, v.y + 0.5)[1] });
    items.sort((a, b) => a.d - b.d);
    lastBadges = []; lastLabels = [];

    for (const it of items) {
      if (it.v) { drawVehicle(it.v); continue; }
      // a flat tile (docs/EDITOR-TOPDOWN.md): the area's colour, a darker rim, a lit top edge, the icon engraved
      const b = it.b, col = b.kind === "group" ? FAM[b.area] || "#8FB3AE" : b.kind === "stocker" ? "#8A6A2C" : "#2F6F68";
      const i = 0.08, [ax, ay] = P(b.x + i, b.y + i), [bx, by] = P(b.x + b.w - i, b.y + b.h - i), w = bx - ax, h = by - ay;
      const en = E.engrave(col);
      let q = 0, tr = null;
      if (b.kind === "group" && fr) { const gi = run.group_names.indexOf(b.group); q = gi >= 0 ? fr.queues[gi] : 0; tr = E.trouble(E.blockMood(run, fi, b.group), q); }
      ctx.save();
      if (jamMap && !(tr && tr.kind === "broken")) ctx.globalAlpha = 0.28;
      ctx.beginPath(); ctx.roundRect(ax, ay, w, h, Math.min(w, h) * 0.12); ctx.fillStyle = col; ctx.fill();
      ctx.lineWidth = Math.max(1.5, F.s * 0.07); ctx.strokeStyle = en.cut; ctx.globalAlpha = 0.6; ctx.stroke(); ctx.globalAlpha = 1;
      ctx.fillStyle = "rgba(255,255,255,.2)"; ctx.beginPath(); ctx.roundRect(ax + 3, ay + 3, w - 6, Math.max(2, h * 0.05), 2); ctx.fill();
      const pl = E.pile(q), rows = Math.ceil((pl.shown + (pl.more ? 1 : 0)) / 6);
      // a named tile (docs/BUILD-REVIEW.md) keeps its name along the top, so its icon sits a little lower and smaller
      const named = Math.max(w, h) >= 40 && w >= 40;
      const ic = b.kind === "group" ? b.area : b.kind, cx = ax + w / 2, cy = ay + h / 2 - (rows ? h * 0.06 * rows : 0) + (named ? h * 0.08 : 0), sz = Math.min(w, h) * (rows > 1 ? 0.36 : named ? 0.42 : 0.5);
      if (IC[ic]) { icon(ic, cx, cy + Math.max(1, F.s * 0.04), sz, en.light, 2.2); icon(ic, cx, cy, sz, en.cut, 2.2); }
      // the tile's name, once the tile can hold it (docs/BUILD-REVIEW.md)
      if (Math.max(w, h) >= 40) {
        const name = b.kind === "group" ? SHORT[b.area] || b.group : INFRA[b.kind] ? INFRA[b.kind][0] : b.kind;
        const long = Math.max(w, h), fs = Math.max(10, Math.min(13, long * 0.15));
        ctx.font = `700 ${fs}px "Chakra Petch",sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = en.cut;
        // a tall, narrow tile (wafers in and out) takes its name sideways
        if (w < 40 && h > w) { ctx.save(); ctx.translate(ax + Math.max(4, w * 0.12), ay + h / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(name, 0, 0, h - 8); ctx.restore(); }
        else {
          // left-aligned along the top, short of the trouble badge in the top-right corner
          const room = w - 10 - (tr ? 2 * Math.max(5, F.s * 0.3) + 4 : 0);
          ctx.textAlign = "left"; ctx.fillText(name, ax + 5, ay + Math.max(5, h * 0.06), Math.max(16, room));
        }
        lastLabels.push(name);
      }
      ctx.restore();
      if (q) podsIn(ax, ay, w, h, q);
      // badges only for trouble (docs/EDITOR-GAME.md); the mood's own icon inside
      if (tr) {
        const mood = E.blockMood(run, fi, b.group), r = Math.max(5, F.s * 0.3), mx = ax + w - r - 2, my = ay + r + 2;
        ctx.fillStyle = tr.color; ctx.beginPath(); ctx.arc(mx, my, r, 0, 7); ctx.fill(); ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.5; ctx.stroke();
        if (tr.kind === "line") icon("queue" in IC ? "queue" : "stocker", mx, my, r * 1.25, "#15191C", 2);
        else if (mood && MOOD[mood]) icon(MOOD[mood][2], mx, my, r * 1.35, "#15191C", 2.2);
        lastBadges.push({ group: b.group, kind: tr.kind });
      }
      if (b.kind === "group" && (b.fail || b.rec)) { const r = Math.max(4, F.s * 0.26), fx = ax + r + 2, fy = ay + h - r - 2; ctx.fillStyle = "#FF4D4F"; ctx.beginPath(); ctx.arc(fx, fy, r, 0, 7); ctx.fill(); icon("bolt", fx, fy, r * 1.4, "#1B1E22", 2); }
      if (b.kind === "group" && (bad.has(b.group) || [...bad].some((a) => typeof a === "string" && a.startsWith(b.group + "#")))) { ctx.save(); ctx.setLineDash([5, 4]); ctx.strokeStyle = "#FF6B57"; ctx.lineWidth = 2; ctx.beginPath(); ctx.roundRect(ax - 2, ay - 2, w + 4, h + 4, 6); ctx.stroke(); ctx.restore(); }
      if (sel && sel.id === b.id) { ctx.strokeStyle = "#7EE8D8"; ctx.lineWidth = 2.4; ctx.beginPath(); ctx.roundRect(ax - 2, ay - 2, w + 4, h + 4, 6); ctx.stroke(); }
    }
    // a stretch set to break: a red bolt over it
    for (const c of breaks) { ctx.fillStyle = "#FF4D4F"; ctx.beginPath(); ctx.arc(c[0], c[1], Math.max(6, F.s * 0.38), 0, 7); ctx.fill(); ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.5; ctx.stroke(); icon("bolt", c[0], c[1], Math.max(9, F.s * 0.52), "#1B1E22", 2); }
    if (flash) { const p = P(flash[0] + 0.5, flash[1] + 0.5); ctx.strokeStyle = "#FF6B57"; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(p[0], p[1], F.s * 1.4, 0, 7); ctx.stroke(); }
    // the challenge's spot: a pulsing ring (docs/EDITOR-GAME.md)
    const sp = spotNow();
    if (sp) {
      const ph = (nowMs % 1600) / 1600, c = P(sp.x + sp.w / 2, sp.y + sp.h / 2), r0 = F.s * (Math.max(sp.w, sp.h) / 2 + 0.35);
      ctx.save(); ctx.strokeStyle = "#F2B33D"; ctx.lineWidth = 2.5;
      ctx.globalAlpha = 0.9; ctx.beginPath(); ctx.arc(c[0], c[1], r0, 0, 7); ctx.stroke();
      if (!matchMedia("(prefers-reduced-motion: reduce)").matches) { ctx.globalAlpha = 0.8 * (1 - ph); ctx.beginPath(); ctx.arc(c[0], c[1], r0 * (1 + 0.6 * ph), 0, 7); ctx.stroke(); }
      ctx.restore();
    }
    // the cell under the pointer, lit in the tool's colour
    if (cursorCell && !ghostAt && !panDrag && !boxDrag) {
      const ob = blockAt(cursorCell[0], cursorCell[1]), [hx, hy] = ob ? [ob.x, ob.y] : cursorCell, hw = ob ? ob.w : 1, hh = ob ? ob.h : 1, tc = tool === "rail" ? "126,232,216" : tool === "erase" ? "255,107,87" : tool in AREA ? "242,179,61" : "227,236,238";
      poly([P(hx, hy), P(hx + hw, hy), P(hx + hw, hy + hh), P(hx, hy + hh)]);
      ctx.fillStyle = `rgba(${tc},.16)`; ctx.fill(); ctx.strokeStyle = `rgba(${tc},.85)`; ctx.lineWidth = 1.5; ctx.stroke();
    }
    const outline = (x0, y0, w, h, col, dash) => {
      poly([P(x0, y0), P(x0 + w, y0), P(x0 + w, y0 + h), P(x0, y0 + h)]);
      ctx.setLineDash(dash || []); ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.stroke(); ctx.setLineDash([]);
    };
    if (boxSel) {
      for (const id of boxSel.blocks) { const b = s.blocks.find((z) => z.id === id); if (b) outline(b.x, b.y, b.w, b.h, "#F2B33D"); }
      for (const r of boxSel.rails) { const [x, y] = r.split(",").map(Number); outline(x, y, 1, 1, "#F2B33D"); }
    }
    if (boxDrag) {
      const [ax, ay] = boxDrag.a, [bx, by] = boxDrag.b;
      // right: wholly inside, a solid line; left: whatever it touches, dashed (part 7)
      outline(Math.min(ax, bx), Math.min(ay, by), Math.abs(bx - ax) + 1, Math.abs(by - ay) + 1, boxDrag.mode === "sub" ? "rgba(255,107,87,.9)" : "rgba(242,179,61,.9)", bx < ax ? [6, 4] : []);
    }
    if (ghostAt && ghostAt.kind === "paste" && pastePlan) {
      const col = pastePlan.ok ? "rgba(126,232,216,.28)" : "rgba(255,107,87,.32)";
      for (const b of pastePlan.blocks) { poly([P(b.x, b.y), P(b.x + b.w, b.y), P(b.x + b.w, b.y + b.h), P(b.x, b.y + b.h)]); ctx.fillStyle = col; ctx.fill(); }
      for (const r of Object.keys(pastePlan.rails)) { const [x, y] = r.split(",").map(Number); poly([P(x, y), P(x + 1, y), P(x + 1, y + 1), P(x, y + 1)]); ctx.fillStyle = col; ctx.fill(); }
    } else if (ghostAt) {
      const g = ghostAt, q = [P(g.x, g.y), P(g.x + g.w, g.y), P(g.x + g.w, g.y + g.h), P(g.x, g.y + g.h)];
      poly(q); ctx.fillStyle = g.ok ? "rgba(126,232,216,.28)" : "rgba(255,107,87,.32)"; ctx.fill();
      ctx.setLineDash([5, 4]); ctx.strokeStyle = g.ok ? "rgba(126,232,216,.9)" : "rgba(255,107,87,.95)"; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
    }
    if (tool === "route" && routeFrom) {
      const [fx, fy] = routeFrom.split(",").map(Number);
      outline(fx, fy, 1, 1, "#7EE8D8");
      if (routePlan && routePlan.ok) for (const c of routePlan.path) { const [cx, cy] = c.split(",").map(Number); poly([P(cx, cy), P(cx + 1, cy), P(cx + 1, cy + 1), P(cx, cy + 1)]); ctx.fillStyle = "rgba(126,232,216,.28)"; ctx.fill(); }
    }
    drawGears();
    if (stale || running) {
      ctx.font = '600 13px "Chakra Petch",sans-serif'; ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = "#F2B33D";
      ctx.fillText(running ? "Updating the run with your changes…" : "Your changes run as soon as the checks pass.", 12, 10);
    }
  }

  /** A vehicle seen from above: a flat token on its track piece, lit when it carries a lot. */
  function drawVehicle(v) {
    const [cx, cy] = P(v.x + 0.5, v.y + 0.5), r = Math.max(3, F.s * 0.3);
    ctx.save();
    if (v.loaded) { ctx.shadowColor = v.hot ? "#FF8A4C" : "#F2B33D"; ctx.shadowBlur = 8; }
    ctx.beginPath(); ctx.roundRect(cx - r, cy - r, 2 * r, 2 * r, r * 0.35);
    ctx.fillStyle = v.hot ? "#FF8A4C" : v.loaded ? "#F2B33D" : "#8A9AA2"; ctx.fill();
    ctx.restore();
    ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.2; ctx.stroke();
  }

  /** Lots waiting at a group, inside its tile's lower edge: up to eight pods, a ninth in amber when there are more. */
  function podsIn(ax, ay, w, h, q) {
    // the line piles up from the tile's lower edge: rows of six, up to three, a red pod for more (docs/EDITOR-GAME.md)
    const pl = E.pile(q), n = pl.shown + (pl.more ? 1 : 0), pw = Math.max(3, w * 0.11), gap = Math.max(1.5, w * 0.03);
    const rowW = 6 * (pw + gap) - gap, x0 = ax + (w - rowW) / 2, y0 = ay + h - pw - Math.max(3, h * 0.07);
    for (let j = 0; j < n; j++) {
      const px = x0 + (j % 6) * (pw + gap), py = y0 - Math.floor(j / 6) * (pw + gap);
      ctx.fillStyle = pl.more && j === n - 1 ? "#FF4D4F" : q >= 4 ? "#F2B33D" : "#F4E7C6"; ctx.fillRect(px, py, pw, pw);
      ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1; ctx.strokeRect(px, py, pw, pw);
    }
  }

  // ---------- the replay
  function index(stays) {
    const by = new Map();
    for (const st of stays) { if (!by.has(st[0])) by.set(st[0], []); by.get(st[0]).push(st); }
    for (const l of by.values()) l.sort((a, b) => a[3] - b[3]);
    return by;
  }
  function vehicles(t) {
    const out = [];
    for (const [id, l] of win.by) {
      let lo = 0, hi = l.length - 1, k = -1;
      while (lo <= hi) { const m = (lo + hi) >> 1; if (l[m][3] <= t) { k = m; lo = m + 1; } else hi = m - 1; }
      const st = l[Math.max(0, k)];
      const at = k >= 0 ? E.vehicleAt([st], t)[0] : null;
      if (at) { out.push(at); continue; }
      const c = E.cellOfNode(k < 0 ? st[1] : st[2]); // before its first stay, or parked after one
      if (c) out.push({ vehicle: id, x: c[0], y: c[1], loaded: st[5], hot: st[6] });
    }
    return out;
  }
  // a window holds about 4 real seconds of play, at least WINDOW fab minutes (docs/EDITOR-SPEED.md)
  const span = () => Math.max(WINDOW, speed * 4);
  async function fetchWindow(from, wait) {
    const body = { fab: fab(), seed: watch, start: from, minutes: span(), overrides: E.overridesFor(s) };
    const r = wait ? await postWait("/api/fab/replay", body) : await post("/api/fab/replay", body);
    if (r.busy) busyUntil = performance.now() + 120;
    if (r.error) return null;
    return { from: r.from, to: r.to, by: index(r.stays) };
  }
  async function jumpTo(t) {
    clock = t; win = null; nextWin = null; fetching = true; tickUi(); draw();
    const w = await fetchWindow(t, true);
    fetching = false;
    if (w && Math.abs(w.from - clock) < 1e-6) { win = w; draw(); }
  }
  function advance(dt) {
    const end = days() * 1440;
    if (speed === MAX) { clock += 60; if (clock > end - WINDOW) clock = startTime(); return; }
    if (!win || fetching) return;
    clock += dt * speed;
    // fetch the next window when 2 real seconds are left, or past 60% of this one
    if (!nextWin && !fetching && !running && performance.now() > busyUntil && win.to < end && ((win.to - clock) / speed < 2 || clock > win.from + 0.6 * (win.to - win.from))) {
      fetching = true;
      fetchWindow(win.to).then((w) => { fetching = false; nextWin = w; });
    }
    if (clock >= win.to) {
      if (win.to >= end) return jumpTo(startTime());
      if (nextWin) { win = nextWin; nextWin = null; } else clock = win.to - 1e-6;
    }
  }

  /** Where to start watching: the hour with the most lots waiting (or a jammed stretch), after the first six hours. */
  function startTime() {
    let best = 0, bi = Math.min(6, run.frames.length - 1);
    run.frames.forEach((f, i) => {
      if (f.t < 360 || f.t > days() * 1440 - WINDOW) return;
      const v = f.queues.reduce((a, b) => a + b, 0) + 8 * f.rails.filter((r) => r > 1).length;
      if (v > best) { best = v; bi = i; }
    });
    return run.frames[bi].t;
  }

  // ---------- runs and the score
  async function runNow(keepClock) {
    const seq = ++runSeq;
    running = true; pendingEdits = false; $("again").disabled = true; $("again").textContent = "Running…"; if (!keepClock) { stale = true; $("goaltext").textContent = "Running the simulator…"; } draw();
    const c0 = ch();
    // each scored run is kept as a B run with its layout (docs/RUNS.md, part 3)
    const record = { title: c0 ? `Challenge ${chIdx + 1}: ${c0.title}` : "Free build", state: snap(), template: c0 ? "teaching" : $("template").value, challenge: c0 ? c0.id : null };
    const req = { fab: fab(), days: days(), every: 60, overrides: E.overridesFor(s), record };
    const r = await postWait("/api/fab/run", { ...req, seed: watch });
    if (seq !== runSeq) return;
    // watching another run: run #1 is run too, and gives the score, so stars stay fair (docs/RANDOM-RUNS.md)
    const r1 = watch !== 1 && !r.error ? await postWait("/api/fab/run", { ...req, seed: 1 }) : null;
    if (seq !== runSeq) return;
    running = false; $("again").disabled = false; $("again").textContent = "Run again with my changes";
    if (r.checks) { checks = r.checks; renderChecks(); }
    if (r.error) { if (!r.checks || r.checks.ok) { checks = { error: r.error }; renderChecks(); } $("goaltext").textContent = r.error; draw(); return; }
    if (run) prev = { ...run.score, spend: run.spendTop };
    prevRun = keepClock ? run : null;
    run = r.moods; run.every = 60; run.spendTop = E.spend(s) - spend0;
    run.watchScore = run.score;
    if (r1 && r1.moods) run.score = r1.moods.score;
    $("watching").hidden = watch === 1;
    if (watch !== 1) $("watching").textContent = `Watching run #${watch}: ${Math.round(run.watchScore.wafers_per_day).toLocaleString()} wafers a day, ${run.watchScore.cycle_days.toFixed(2)} days a wafer takes. Stars count run #1, the challenge's own${r1 && r1.moods ? "" : " (it did not run, so this score is the run watched)"}.`;
    $("run-no").textContent = `Run #${watch}`;
    if (prevRun) afterChange(prevRun, run);
    stale = false;
    const c = ch();
    if (c && meetsFor(run.score, c, run.spendTop)) { met.add(c.id); try { localStorage.setItem("fabgym.met", JSON.stringify([...met])); } catch (e) { /* no storage */ } }
    if (c && !aiPlaying) {
      const st = starsFor(run.score, c, run.spendTop);
      if (st > (best[c.id] || 0)) {
        const first = !best[c.id];
        best[c.id] = st;
        try { localStorage.setItem("fabgym.stars", JSON.stringify(best)); } catch (e) { /* no storage */ }
        celebrate(st, c, first);
      }
    }
    $("slider").max = run.frames.length - 1;
    runsDone++;
    // a rerun after an edit keeps the tool in hand; only a fresh run goes back to watching (docs/EDITOR-SPEED.md)
    renderTabs(); renderScore(); lastHour = -1;
    if (keepClock) { $("again").hidden = true; draw(); } else setMode("run");
    await jumpTo(keepClock && clock > 0 ? Math.min(clock, days() * 1440 - WINDOW) : startTime());
  }

  // ---------- Race the AI (docs/RACE-AI.md): the AI's moves are the editor's own, each one an undoable edit
  const DIRS = { E: 0, S: 1, W: 2, N: 3 };
  const int = (v) => Number.isInteger(v);
  function lookNow() {
    const c = ch(), sc = run && !stale ? run.score : null;
    return {
      challenge: c ? { title: c.title, problem: c.problem, goal: c.goal, target_wafers_a_day: c.target.wafers, budget: c.target.budget ?? null } : { title: "Free build" },
      floor: { width: s.W, height: s.H, note: "x is the column from 0 at the left, y the row from 0 at the top" },
      tools_you_may_use: c && c.tools ? c.tools : "all",
      pieces: s.blocks.map((b) => ({ kind: b.kind, group: b.group, area: b.area, name: b.kind === "group" ? AREA[b.area][0] : INFRA[b.kind][0], x: b.x, y: b.y, w: b.w, h: b.h,
        machines: b.count, breaks: b.fail ? b.fail.kind : "as in the data", when_it_breaks: b.rec ? b.rec.kind : "fix it where it stands" })),
      areas_you_can_still_place: E.AREAS.filter((a) => nextGroup(a)),
      track: Object.entries(s.rail).map(([k, v]) => ({ at: k, out: DN.filter((_, i) => v.o[i]).join(""), ...(v.fail ? { breaks: true, when_it_breaks: (v.rec || {}).kind || "wait" } : {}) })),
      cars: s.vehicles, cap_on_lots: s.cap || 0,
      checks: checks && checks.issues ? checks.issues.map((i) => `${i.severity}: ${i.message || i.text || ""}`) : [],
      advice: $("advice").textContent,
      last_run: sc ? { wafers_a_day: Math.round(sc.wafers_per_day), days_a_wafer_takes: +sc.cycle_days.toFixed(2), extra_spend: run.spendTop } : null,
      stars: sc && c ? starsFor(sc, c, run.spendTop) : null,
    };
  }
  async function afterRun() {
    for (let i = 0; i < 300 && (pendingEdits || running); i++) await new Promise((r) => setTimeout(r, 100));
    const c = ch(), sc = run && !stale ? run.score : null;
    if (!checks || !checks.ok) return { ran: false, checks: checks && checks.issues ? checks.issues.map((i) => `${i.severity}: ${i.message || i.text || ""}`) : [], note: "The checks did not pass, so nothing ran." };
    return { ran: true, wafers_a_day: sc ? Math.round(sc.wafers_per_day) : null, days_a_wafer_takes: sc ? +sc.cycle_days.toFixed(2) : null, extra_spend: run ? run.spendTop : null,
      target: c ? c.target.wafers : null, stars: sc && c ? starsFor(sc, c, run.spendTop) : null, advice: $("advice").textContent };
  }
  const refuse = (error) => ({ ok: false, error });
  const done = (note) => { buildPalette(); inspector(); edited(); draw(); return { ok: true, note }; };
  const TOOLS = {
    look: () => lookNow(),
    lay_track({ path }) {
      if (!allowed("rail")) return refuse("This challenge does not use track.");
      if (!Array.isArray(path) || !path.length || !path.every((c) => Array.isArray(c) && c.length === 2 && int(c[0]) && int(c[1]))) return refuse("path must be a list of [x, y] cells.");
      for (let i = 1; i < path.length; i++) if (Math.abs(path[i][0] - path[i - 1][0]) + Math.abs(path[i][1] - path[i - 1][1]) !== 1) return refuse(`step ${i} is not next to the cell before it.`);
      let cells = path.map((c) => [...c]);
      for (const [x, y] of cells) if (blockAt(x, y)) return refuse(`(${x}, ${y}) is covered by a piece.`);
      for (let i = 0; i < cells.length; i++) { const d = growFor(cells[i][0], cells[i][1], 1, 1); if (!d) return refuse("That is as far as the floor goes."); if (d[0] || d[1]) cells = cells.map((c) => [c[0] + d[0], c[1] + d[1]]); }
      for (let i = 0; i < cells.length; i++) {
        const k = E.key(cells[i][0], cells[i][1]);
        if (!s.rail[k]) s.rail[k] = { o: [0, 0, 0, 0] };
        if (i) { const p = cells[i - 1], dir = D.findIndex((v) => v[0] === cells[i][0] - p[0] && v[1] === cells[i][1] - p[1]); s.rail[E.key(p[0], p[1])].o[dir] = 1; }
      }
      return done(`Laid ${cells.length} track piece${cells.length > 1 ? "s" : ""}.`);
    },
    set_track_direction({ x, y, dir, on }) {
      const v = s.rail[E.key(x, y)];
      if (!v) return refuse(`There is no track at (${x}, ${y}).`);
      if (!(dir in DIRS)) return refuse("dir is N, E, S or W.");
      v.o[DIRS[dir]] = on ? 1 : 0;
      return done(`(${x}, ${y}) ${on ? "now runs" : "no longer runs"} ${DLONG[DIRS[dir]]}.`);
    },
    erase({ x, y }) {
      if (!allowed("erase")) return refuse("This challenge does not use Erase.");
      const b = blockAt(x, y);
      if (b) { s.blocks = s.blocks.filter((z) => z !== b); return done("Removed the piece."); }
      if (s.rail[E.key(x, y)]) { delete s.rail[E.key(x, y)]; return done("Removed the track piece."); }
      return refuse(`Nothing at (${x}, ${y}).`);
    },
    place({ piece, x, y }) {
      if (!(piece in AREA) && !["stocker", "entry", "exit"].includes(piece)) return refuse("piece is an area name or stocker, entry or exit.");
      if (!allowed(piece)) return refuse("This challenge does not use that piece.");
      if (!int(x) || !int(y)) return refuse("x and y are whole numbers.");
      const kind = piece in AREA ? "group" : piece, [w, h] = E.footprint(kind);
      if (kind === "group" && !nextGroup(piece)) return refuse("Every group of that area is placed. Use set_machines.");
      const f = E.isFree(s, x, y, w, h, undefined, true);
      if (!f.ok) return refuse(f.why);
      const d = growFor(x, y, w, h); if (!d) return refuse("That is as far as the floor goes.");
      const id = Math.max(0, ...s.blocks.map((z) => z.id)) + 1, px = x + d[0], py = y + d[1];
      if (kind === "group") s.blocks.push({ id, kind: "group", group: nextGroup(piece), area: piece, count: 1, x: px, y: py, w, h });
      else s.blocks.push({ id, kind, x: px, y: py, w, h });
      return done(`Placed ${kind === "group" ? AREA[piece][0].toLowerCase() : INFRA[kind][0].toLowerCase()} at (${px}, ${py}).`);
    },
    set_machines({ group, count }) {
      const b = s.blocks.find((z) => z.group === group);
      if (!b) return refuse(`No machine group called ${group}.`);
      if (!int(count) || count < 1) return refuse("count is a whole number, 1 or more.");
      // the group's total across its places (docs/BUILD-CONTROLS.md, part 2): the first place takes the difference
      const others = s.blocks.filter((z) => z.group === group && z !== b).reduce((a, z) => a + z.count, 0);
      if (count - others < 1) return refuse(`${group} stands in several places; ${others + 1} is the fewest it can have.`);
      b.count = count - others;
      return done(`${AREA[b.area][0]} now has ${count} machine${count > 1 ? "s" : ""}.`);
    },
    set_when_it_breaks({ group, x, y, kind, spares }) {
      if (group != null) {
        const b = s.blocks.find((z) => z.group === group);
        if (!b) return refuse(`No machine group called ${group}.`);
        if (!["", "as set", "swap_to_spare", "repair_and_hold_lots"].includes(kind)) return refuse("For a group, kind is as set, swap_to_spare or repair_and_hold_lots.");
        b.rec = kind === "swap_to_spare" ? { kind, spares: int(spares) && spares > 0 ? spares : 1, swap_minutes: 20 } : kind === "repair_and_hold_lots" ? { kind, lookback_minutes: 60, hold_minutes: 120 } : undefined;
        return done(`${AREA[b.area][0]}: ${kind || "as set"} when it breaks.`);
      }
      const v = s.rail[E.key(x, y)];
      if (!v) return refuse(`There is no track at (${x}, ${y}).`);
      if (!v.fail) return refuse(`The track at (${x}, ${y}) never breaks.`);
      if (!["wait", "route_around"].includes(kind)) return refuse("For track, kind is wait or route_around.");
      v.rec = { kind };
      return done(kind === "route_around" ? `Cars now route round (${x}, ${y}) when it breaks.` : `Cars wait at (${x}, ${y}) for the repair.`);
    },
    set_cars({ count }) { if (!int(count) || count < 1) return refuse("count is a whole number, 1 or more."); s.vehicles = count; return done(`${count} cars on the track.`); },
    set_cap({ lots }) { if (!int(lots) || lots < 0) return refuse("lots is a whole number, 0 or more."); if (lots) s.cap = lots; else delete s.cap; return done(lots ? `At most ${lots} lots inside.` : "No cap on lots."); },
    run: () => afterRun(),
  };
  window.FabEditorTools = {
    names: Object.keys(TOOLS),
    async call(name, args) {
      if (!Object.prototype.hasOwnProperty.call(TOOLS, name)) return refuse(`unknown tool ${name}`);
      try { return await TOOLS[name](args || {}); } catch (e) { return refuse(`the tool failed: ${e.message}`); }
    },
    setPlaying(on) { aiPlaying = !!on; },
    challenge: () => { const c = ch(); return c ? { title: c.title, problem: c.problem, goal: c.goal, target: c.target } : null; },
  };

  // ---------- sketch to fab (docs/SKETCH.md): Muse Spark reads a drawing; the editor's own moves build it
  let sketchBefore = null, sketchSeq = 0;
  function pictureOf(file) {
    return new Promise((ok, bad) => {
      const fr = new FileReader();
      fr.onerror = () => bad(new Error("the picture could not be read"));
      fr.onload = () => {
        const im = new Image();
        im.onerror = () => bad(new Error("that file is not a picture"));
        im.onload = () => {
          const k = Math.min(1, 1024 / Math.max(im.width, im.height)), w = Math.round(im.width * k), h = Math.round(im.height * k);
          const c = document.createElement("canvas"); c.width = w; c.height = h;
          const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.drawImage(im, 0, 0, w, h);
          ok({ url: c.toDataURL("image/jpeg", 0.9), w, h });
        };
        im.src = fr.result;
      };
      fr.readAsDataURL(file);
    });
  }
  async function fromSketch(file) {
    const box = $("sketch-body");
    $("sketch-panel").hidden = false; $("sketch-keep").hidden = true; $("sketch-discard").hidden = true;
    box.innerHTML = '<p class="sk-note" style="color:var(--muted)">Reading your sketch…</p>';
    let pic;
    try { pic = await pictureOf(file); } catch (e) { box.innerHTML = `<p class="sk-note">${esc(e.message)}</p>`; return; }
    const seq = ++sketchSeq;
    const r = await post("/api/sketch", { image: pic.url, width: pic.w, height: pic.h });
    if (seq !== sketchSeq) return; // discarded while it was being read
    if (r.error) { box.innerHTML = `<p class="sk-note">${esc(r.error)}</p>`; return; }
    const free = E.CHALLENGES.length;
    if (chIdx !== free) await load(free);
    sketchBefore = snap();
    s.blocks = []; s.rail = {}; s.W = r.floor[0]; s.H = r.floor[1]; V = null; room = null;
    const placed = [], left = [];
    for (const p of r.pieces) {
      const res = await TOOLS.place({ piece: p.piece, x: p.x, y: p.y });
      if (res.ok) placed.push(r.names[p.piece] || p.piece); else left.push(`${r.names[p.piece] || p.piece}: ${res.error}`);
    }
    let pieces = 0;
    for (const path of r.paths) { const res = await TOOLS.lay_track({ path }); if (res.ok) pieces += path.length; else left.push(`a line: ${res.error}`); }
    buildPalette(); inspector(); draw();
    const notes = [...r.notes, ...left];
    const still = E.AREAS.filter((a) => nextGroup(a)).map((a) => AREA[a][0]);
    if (still.length) notes.push(`A wafer's route also visits ${still.length === 1 ? still[0] : still.slice(0, -1).join(", ") + " and " + still[still.length - 1]}. Place ${still.length === 1 ? "it" : "them"} from Machines to finish the fab.`);
    box.innerHTML = `<p class="ai-cost">${r.model === "stand-in" ? "stand-in (a recorded reading)" : esc(r.model)} · $${(r.cost_usd || 0).toFixed(3)} · read ${r.read.boxes} boxes and ${r.read.lines} lines</p>` +
      `<p class="ai-status">Built ${placed.length} piece${placed.length === 1 ? "" : "s"} and ${pieces} track piece${pieces === 1 ? "" : "s"} on a ${s.W} × ${s.H} floor.</p>` +
      `<ul class="sk-list">${placed.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` +
      notes.map((n) => `<p class="sk-note">${esc(n)}</p>`).join("") +
      '<p class="note">The checks below say what is still missing. Keep it to go on drawing, or Discard to go back.</p>';
    $("sketch-keep").hidden = false; $("sketch-discard").hidden = false;
  }
  // another random run to watch; the score stays run #1's (docs/RANDOM-RUNS.md)
  $("new-run").onclick = () => {
    let n = watch;
    while (n === watch || n === 1) { const a = new Uint32Array(1); crypto.getRandomValues(a); n = 2 + (a[0] % 9998); }
    watch = n; $("run-no").textContent = `Run #${watch}`;
    if (checks && checks.ok === false) return; // the checks refuse the layout: it runs when they pass
    runNow(false);
  };
  document.querySelectorAll("#ctl-tabs [data-tab]").forEach((bt) => (bt.onclick = () => ctlTab(bt.dataset.tab)));
  renderProcess();
  $("curves-open").onclick = () => { const box = $("curves"); box.hidden = !box.hidden; $("curves-open").setAttribute("aria-expanded", String(!box.hidden)); curvesShown = -1; renderCurves(); };
  $("sketch-go").onclick = () => $("sketch-file").click();
  $("sketch-file").onchange = (e) => { const f = e.target.files && e.target.files[0]; e.target.value = ""; if (f) fromSketch(f); };
  $("sketch-keep").onclick = () => { $("sketch-panel").hidden = true; sketchBefore = null; };
  $("sketch-discard").onclick = () => { sketchSeq++; if (sketchBefore) { restore(sketchBefore); V = null; room = null; draw(); } sketchBefore = null; $("sketch-panel").hidden = true; };

  // ---------- the moment a challenge is met (docs/EDITOR-ROOM.md)
  function celebrate(st, c, first) {
    const w = Math.round(run.score.wafers_per_day), t = c.target.wafers;
    $("win-h").textContent = first ? "Challenge met!" : "New best!";
    $("win-stars").innerHTML = [1, 2, 3].map((i) => `<span class="star${i <= st ? " on" : ""}" aria-hidden="true">★</span>`).join("") + `<span class="sr">${st} of 3 stars</span>`;
    $("win-line").textContent = `${w.toLocaleString()} wafers a day against a target of ${t.toLocaleString()}${c.target.budget ? `, ${money(run.spendTop)} spent of ${money(c.target.budget)}` : ""}.`;
    $("win-next").textContent = st >= 3 ? "Three stars: the best there is." : st === 2 ? `Three stars at ${Math.ceil(t * 1.05).toLocaleString()} wafers a day.` : `Two stars at ${Math.ceil(t * 1.02).toLocaleString()}, three at ${Math.ceil(t * 1.05).toLocaleString()}.`;
    const next = chIdx + 1;
    $("win-go").textContent = next < E.CHALLENGES.length ? "Next challenge →" : "Try Free build →";
    $("win-go").onclick = () => { $("win").hidden = true; load(next); };
    $("win-stay").onclick = () => { $("win").hidden = true; };
    // three stars: Muse Image can make a poster of the map (docs/POSTER.md)
    $("poster-go").hidden = st < 3; $("poster-go").disabled = false; $("poster-go").textContent = "Make a poster";
    $("poster-img").hidden = true; $("poster-dl").hidden = true; $("poster-note").textContent = "";
    $("poster-go").onclick = async () => {
      $("poster-go").disabled = true; $("poster-go").textContent = "Making your poster…";
      const r = await post("/api/poster", { image: cv.toDataURL("image/png"), title: c.title, wafers: w, stars: st });
      if (r.error) { $("poster-note").textContent = r.error; $("poster-go").disabled = false; $("poster-go").textContent = "Try again"; return; }
      $("poster-img").src = r.image; $("poster-img").hidden = false;
      $("poster-dl").href = r.image; $("poster-dl").download = `fab-gym-poster.${r.format || "png"}`; $("poster-dl").hidden = false; $("poster-go").hidden = true;
      $("poster-note").textContent = `${r.model === "stand-in" ? "stand-in (a recorded picture)" : r.model} · $${(r.cost_usd || 0).toFixed(2)} · saved on this Mac: ${r.saved}`;
    };
    $("win").hidden = false;
    confetti();
  }
  function confetti() {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const c = $("confetti"), box = $("mapbox"), dpr = window.devicePixelRatio || 1, W = box.clientWidth, H = box.clientHeight;
    c.width = W * dpr; c.height = H * dpr; c.style.width = W + "px"; c.style.height = H + "px";
    const g = c.getContext("2d"), cols = ["#F2B33D", "#7EE8D8", "#4FE3A3", "#FF8A5B", "#C9A3FF"], t0 = performance.now();
    const bits = Array.from({ length: 140 }, () => ({ x: W / 2 + (Math.random() - 0.5) * 80, y: H * 0.35, vx: (Math.random() - 0.5) * 9, vy: -Math.random() * 9 - 3, r: Math.random() * 6.28, col: cols[(Math.random() * cols.length) | 0] }));
    const step = (now) => {
      const k = (now - t0) / 1800;
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      if (k >= 1) return;
      for (const b of bits) { b.x += b.vx; b.y += b.vy; b.vy += 0.28; b.r += 0.2; g.save(); g.translate(b.x, b.y); g.rotate(b.r); g.globalAlpha = 1 - k; g.fillStyle = b.col; g.fillRect(-4, -2, 8, 4); g.restore(); }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // ---------- see your change work (docs/EDITOR-GAME.md)
  function afterChange(was, now) {
    const fi = frameIdx(), a = was.frames[Math.min(fi, was.frames.length - 1)], b = now.frames[Math.min(fi, now.frames.length - 1)];
    const before = {}; was.stretches.forEach((n, i) => (before[n] = a.rails[i]));
    const cleared = now.stretches.filter((n, i) => (before[n] || 0) > 1 && b.rails[i] <= 0.2);
    if (cleared.length) flashes.push({ stretches: cleared, until: performance.now() + 1500 });
    const text = E.floatText(was.score.wafers_per_day, now.score.wafers_per_day);
    if (!text) return;
    const box = $("mapbox").getBoundingClientRect(), c = cv.getBoundingClientRect();
    const at = lastEditAt ? P(lastEditAt[0] + 0.5, lastEditAt[1] + 0.5) : [c.width / 2, c.height / 2];
    const el = document.createElement("div");
    el.className = "float " + (text.startsWith("+") ? "up" : text.startsWith("same") ? "same" : "down");
    el.textContent = text;
    el.style.left = `${at[0] + c.left - box.left}px`; el.style.top = `${at[1] + c.top - box.top}px`;
    $("floats").appendChild(el);
    setTimeout(() => el.remove(), 2200);
  }
  /** The challenge's spot on the floor: its broken track piece or its machine. */
  function spotNow() {
    const c = ch();
    if (!c || !c.spot) return null;
    if (c.spot.rail) { const k = Object.keys(s.rail).find((z) => s.rail[z].fail); if (!k) return null; const [x, y] = k.split(",").map(Number); return { rail: k, x, y, w: 1, h: 1 }; }
    const b = s.blocks.find((z) => z.group === c.spot.group);
    return b ? { group: b.group, x: b.x, y: b.y, w: b.w, h: b.h } : null;
  }
  function renderAdvice() {
    if (!run) { $("advice").textContent = ""; return; }
    const fi = frameIdx(), f = run.frames[fi], c = ch();
    const jamOf = {}; run.stretches.forEach((n, i) => (jamOf[n] = f.rails[i]));
    const failing = Object.keys(s.rail).filter((k) => s.rail[k].fail).map((k) => "c" + k.replace(",", "_"));
    const brokenJam = failing.some((cell) => Object.keys(jamOf).some((n) => (n.startsWith(cell + ">") || n.endsWith(">" + cell)) && jamOf[n] > 0.2));
    let worst = null;
    run.group_names.forEach((g, i) => { const b = s.blocks.find((z) => z.group === g); if (b && b.area && (!worst || f.queues[i] > worst.queue)) worst = { name: AREA[b.area][0], queue: f.queues[i] }; });
    const met = !!(c && meetsFor(run.score, c, run.spendTop));
    const stars = c && met ? starsFor(run.score, c, run.spendTop) : 0;
    $("advice").textContent = E.advise({ brokenJam, worst, met, stars, tip: c && c.tip });
    $("advice").title = $("advice").textContent; // the whole line on hover, when the row cuts it short
  }

  function renderScore() {
    const c = ch(), sc = run ? run.score : null, p = prev;
    // the checks refuse the layout on the floor, so these numbers are the last layout's (docs/SKETCH.md)
    const blocked = stale && !running && checks && !checks.ok;
    const card = (k, n, unit, cur, was, better, bad) => {
      let dl = '<span class="dl">first run</span>';
      if (blocked) dl = '<span class="dl">before your changes</span>';
      else if (p && was != null && cur != null) {
        const d = cur - was;
        dl = Math.abs(d) < 1e-9 ? '<span class="dl">same as last run</span>' : `<span class="dl ${better(d) ? "good" : "bad"}">${d > 0 ? "+" : ""}${Number.isInteger(d) ? d.toLocaleString() : d.toFixed(2)} vs last run</span>`;
      }
      return `<div class="sc${bad ? " bad" : ""}${stale ? " stale" : ""}"><span class="k">${k}</span><span class="n">${n}${unit ? ` <small>${unit}</small>` : ""}</span>${dl}</div>`;
    };
    // before the first run the three cards wait in place, so their arrival does not move the map
    if (!sc) { $("score").innerHTML = ["Wafers out a day", "Days a wafer takes", "Extra spend"].map((k) => `<div class="sc stale"><span class="k">${k}</span><span class="n">…</span><span class="dl">running</span></div>`).join(""); return; }
    const top = run.spendTop;
    $("score").innerHTML =
      card("Wafers out a day", Math.round(sc.wafers_per_day).toLocaleString(), "", sc.wafers_per_day, p && p.wafers_per_day, (d) => d > 0, c && sc.wafers_per_day < c.target.wafers) +
      card("Days a wafer takes", sc.cycle_days.toFixed(2), "days", sc.cycle_days, p && p.cycle_days, (d) => d < 0) +
      card("Extra spend", money(top), c && c.target.budget ? `of ${money(c.target.budget)} allowed` : c && c.target.budget === 0 ? "no budget here" : "", top, p && p.spend, (d) => d < 0, c && c.target.budget != null && top > c.target.budget);
    if (c) {
      const w = sc.wafers_per_day, full = c.target.wafers * 1.2, ok = meetsFor(sc, c, top);
      $("goalfill").style.width = Math.min(100, (w / full) * 100) + "%";
      $("goaltick").style.left = (c.target.wafers / full) * 100 + "%";
      // only the next star is marked (docs/EDITOR-ROOM.md); none after three
      const got = starsFor(sc, c, top);
      [1, 1.02, 1.05].forEach((m, i) => { const el = $("goalbar").querySelectorAll(".starmark")[i]; if (el) { el.hidden = i !== got; el.style.left = `calc(${(c.target.wafers * m / full) * 100}% - 6px)`; el.title = `${i + 1} star${i ? "s" : ""} at ${Math.ceil(c.target.wafers * m)} wafers a day`; } });
      $("goalbar").classList.toggle("met", ok && !blocked);
      $("goaltext").title = "";
      $("goaltext").innerHTML = blocked ? `<b>${Math.round(w).toLocaleString()}</b> wafers a day before your changes. Fix the checks to run the new layout.` : ok ? `<b>Challenge met.</b> ${Math.round(w).toLocaleString()} wafers a day${c.target.budget ? `, ${money(top)} spent of ${money(c.target.budget)}` : ""}.` : `<b>${Math.round(w).toLocaleString()}</b> of ${c.target.wafers.toLocaleString()} wafers a day${c.target.budget != null && top > c.target.budget ? `, over budget by ${money(top - c.target.budget)}` : ""}`;
      if (experiment() && !blocked) {
        // kept short: the banner's column is narrow, and a long line pushes the map off the page (docs/BUILD-CONTROLS.md)
        const parts = [s.inports ? `${s.inports} port${s.inports > 1 ? "s" : ""} a machine` : "", ...E.flowWords(s.flow, base).split(", ")].filter(Boolean);
        const what = parts.length > 2 ? `${parts.slice(0, 2).join(", ")} and ${parts.length - 2} more` : parts.join(", ");
        $("goaltext").innerHTML = `<b>An experiment</b> with ${esc(what)}: ${Math.round(w).toLocaleString()} wafers a day, no stars.`;
        $("goaltext").title = "This challenge is tuned with unlimited load ports and today's settings, so a run with other settings earns no stars.";
      }
    } else {
      $("goalfill").style.width = "0"; $("goalbar").classList.remove("met");
      $("goaltext").innerHTML = blocked ? `<b>${Math.round(sc.wafers_per_day).toLocaleString()}</b> wafers a day before your changes. Fix the checks to run the new layout.` : `<b>${Math.round(sc.wafers_per_day).toLocaleString()}</b> wafers a day on your layout`;
    }
  }
  const groupLabel = (g) => { const b = s.blocks.find((z) => z.group === g); return b && AREA[b.area] ? AREA[b.area][0] : g || "none"; };

  // ---------- challenges
  function renderTabs() {
    const names = [...E.CHALLENGES.map((c, i) => `${i + 1} · ${c.title}`), "Free build"];
    const starsOf = (i) => { const n = i < E.CHALLENGES.length ? best[E.CHALLENGES[i].id] || 0 : 0; return n ? `<span class="met tabstars" aria-label="best: ${n} of 3 stars"><small>best</small><b>${"★".repeat(n)}</b><i>${"☆".repeat(3 - n)}</i></span>` : ""; };
    $("chtabs").innerHTML = names.map((n, i) => `<button class="tab" data-ch="${i}" aria-pressed="${i === chIdx}">${esc(n)}${starsOf(i)}</button>`).join("");
    $("chtabs").querySelectorAll("[data-ch]").forEach((b) => (b.onclick = () => load(+b.dataset.ch)));
  }
  async function load(i, fixed, saved) {
    chIdx = i; sel = null; run = null; prev = null; win = null; checks = null; prevRun = null; flashes = []; lastEditAt = null;
    watch = 1; $("run-no").textContent = "Run #1"; $("watching").hidden = true; // a challenge starts on its own run
    const c = ch();
    if (c) { setupNow = c.setup(); if (fixed) setupNow = c.fix(setupNow); }
    else {
      const name = $("template").value;
      if (name === "smt2020") {
        const d = await (await fetch("/api/fab/base?name=smt2020")).json();
        if (d.error) { $("goaltext").textContent = d.error; return; }
        setupNow = { state: E.template("smt2020", d), base: d.shop, overrides: null };
        for (const l of d.areas.split("\n")) { const [g, a] = l.split("\t"); if (g) areaOfGroup[g] = E.AREA_OF[a]; }
      } else setupNow = { state: { ...E.template("teaching"), inports: 2 }, base: E.TEACHING_SHOP, overrides: null }; // real storage (part 3)
      // a kept Build run opened again (docs/RUNS.md, part 3): its own layout, as Free build
      if (saved && saved.state) setupNow.state = JSON.parse(JSON.stringify(saved.state));
    }
    s = setupNow.state; base = setupNow.base;
    for (const l of base.split("\n")) if (l.startsWith("group\t")) { const g = l.split("\t")[1]; if (!areaOfGroup[g]) areaOfGroup[g] = E.AREA_OF[g.replace(/_T$/, "")]; }
    spend0 = E.spend(c ? c.setup().state : s);
    start = c ? c.setup().state : JSON.parse(JSON.stringify(s)); // what Your changes counts from (part 5)
    renderChanges();
    $("cheye").textContent = c ? `Challenge ${i + 1} · ${c.title}` : "Free build";
    $("chproblem").textContent = c ? c.problem : "Lay out your own fab. Place machines, lay track, then run it.";
    $("chgoal").textContent = c ? c.goal : "There is no target here. The scores show how your layout does.";
    $("showfix").hidden = !c;
    $("tmpl").hidden = !!c;
    hist.clear(); lastSnap = snap(); V = null; syncUndo();
    renderTabs(); renderLevers(); buildPalette(); ctlTab("sel"); inspector(); renderChecks(); renderScore();
    room = null; draw(); // the levers change the banner's height, so the map measures its room again
    await runNow();
  }

  // ---------- modes and the clock
  function setMode(m) {
    mode = m;

    $("editor").classList.toggle("running", m === "run");
    $("again").hidden = !stale || !(checks && checks.ok); // only when the run on screen is out of date and can run again (docs/EDITOR-GAME.md)
    if (m === "run") { playing = !matchMedia("(prefers-reduced-motion: reduce)").matches || playing; tool = "select"; syncPal(); }
    playBtn(); draw();
  }
  function playBtn() { $("play").textContent = playing ? "❚❚" : "▶"; $("play").setAttribute("aria-label", playing ? "Pause" : "Play"); }
  const hhmmss = (t) => { const d = Math.floor(t / 1440) + 1, m = t % 1440; return `Day ${d} · ${String(Math.floor(m / 60)).padStart(2, "0")}:${String(Math.floor(m % 60)).padStart(2, "0")}:${String(Math.floor((m * 60) % 60)).padStart(2, "0")}`; };
  let lastHour = -1;
  // live curves (docs/CURVES.md): from the run's hourly frames
  let curvesShown = -1;
  function renderCurves() {
    const box = $("curves");
    if (box.hidden || !run || !run.frames) return;
    if (Math.abs(clock - curvesShown) < 2 && box.childElementCount) return;
    curvesShown = clock;
    const busy = ["work", "tired", "full"].map((m) => run.tool_moods.indexOf(m)); // moods that count as a tool busy
    const xs = run.frames.map((f) => f.t);
    const waiting = run.frames.map((f) => f.queues.reduce((a, b) => a + b, 0));
    const finished = run.frames.map((f) => (f.lots && f.lots.grad) || 0);
    const working = run.frames.map((f) => (f.tools.length ? f.tools.filter((m) => busy.includes(m)).length / f.tools.length : 0));
    const charts = [["Lots waiting", waiting, (v) => Math.round(v)], ["Lots finished", finished, (v) => Math.round(v)], ["Tools busy", working, (v) => `${Math.round(v * 100)}%`]];
    if (box.childElementCount !== charts.length) box.innerHTML = charts.map(() => '<div class="curve"></div>').join("");
    const els = box.querySelectorAll(".curve"), until = days() * 1440;
    charts.forEach(([name, ys, fmt], i) => FabCharts.render(els[i], { name, xs, series: [{ label: "this run", ys }], until, now: clock, fmt }));
  }

  function tickUi() {
    $("clock").textContent = hhmmss(clock);
    renderCurves();
    if (!run) return;
    const fi = frameIdx();
    if (fi === lastHour) return;
    lastHour = fi;
    $("slider").value = fi;
    renderAdvice();
    const lots = run.frames[fi].lots;
    void lots;
  }

  // ---------- palette and editing
  function placeKind() { return tool in AREA ? "group" : tool; }
  function nextGroup(area) {
    const placed = new Set(s.blocks.filter((b) => b.kind === "group").map((b) => b.group));
    return Object.keys(areaOfGroup).find((g) => areaOfGroup[g] === area && !placed.has(g) && !(s.stores || []).includes(g) && base.includes(`group\t${g}\t`));
  }
  function buildPalette() {
    // a grid of keys, only this challenge's tools, nothing greyed (docs/EDITOR-GAME.md)
    const pb = (t, n, k, col) => (allowed(t) ? `<button data-t="${t}" aria-pressed="${tool === t}" title="${esc(n)}${k ? ` (key ${k})` : ""}">${svg(t, col)}<span>${esc(n)}</span>${k ? `<kbd>${k}</kbd>` : ""}</button>` : "");
    const sec = (name, keys) => (keys ? `<h4>${name}</h4><div class="keys">${keys}</div>` : "");
    let h = sec("Tools", pb("select", "Select", "V") + pb("rail", "Track", "B") + pb("route", "Route", "T") + pb("erase", "Erase", "E"));
    // every machine as its map tile, in even rows; its cartoon on hover (docs/BUILD-CONTROLS.md, parts 1 and 6)
    const lever = new Set(leversOf(ch()).map((l) => l.kind).filter(Boolean));
    h += `<h4>Machines</h4><div class="keys mks">` + E.AREAS.map((a) => {
      const n = onFloor(a);
      return `<button class="mk${lever.has(a) ? " lever" : ""}" data-kind="${a}" style="--fam:${FAM[a]}" aria-label="${esc(AREA[a][0])}: ${n} on the floor, ${money(E.PRICE[a])} a machine${lever.has(a) ? ", one of this challenge's levers" : ""}">` +
        `${svg(a, E.engrave(FAM[a]).cut)}<span class="n">${n}</span></button>`;
    }).join("") + `</div>`;
    // blueprints (part 8): kept in this browser, each with a small drawing of its pieces
    const bps = blueprints();
    if (bps.length) h += `<h4>Blueprints</h4><div class="bps">` + bps.map((bp, i) => `<span class="bp"><button data-bp="${i}" title="Take it in hand">${bpThumb(bp.clip)}<span>${esc(bp.name)}</span></button><button class="bpx" data-bpdel="${i}" aria-label="Forget ${esc(bp.name)}">×</button></span>`).join("") + `</div>`;
    const fresh = E.AREAS.filter((a) => nextGroup(a)).map((a) => pb(a, AREA[a][0], "", FAM[a])).join("");
    if (fresh) h += sec("New groups", fresh);
    h += sec("Moving wafers", pb("entry", INFRA.entry[0]) + pb("exit", INFRA.exit[0]) + pb("stocker", INFRA.stocker[0]));
    $("pal").innerHTML = h;
    $("pal").querySelectorAll("button[data-t]").forEach((b) => (b.onclick = () => take(b.dataset.t)));
    $("pal").querySelectorAll("[data-bp]").forEach((bt) => (bt.onclick = () => {
      const bp = blueprints()[+bt.dataset.bp]; if (!bp) return;
      clip = bp.clip; tool = "select"; syncPal(); pasting = true; ghostAt = null;
      $("status").textContent = `"${bp.name}" in hand: click where it should go. Esc drops it.`; draw();
    }));
    $("pal").querySelectorAll("[data-bpdel]").forEach((bt) => (bt.onclick = () => { const l = blueprints(); l.splice(+bt.dataset.bpdel, 1); saveBlueprints(l); buildPalette(); }));
    $("pal").querySelectorAll("button[data-kind]").forEach((bt) => (bt.onclick = () => {
      const a = bt.dataset.kind, b = s.blocks.find((z) => z.kind === "group" && z.area === a);
      take(a); // in hand: a click places one machine, Shift-drag fills (part 2)
      if (b) { sel = { id: b.id }; ctlTab("sel"); inspector(); }
      $("status").textContent = `${AREA[a][0]} in hand: click to place one, Shift-drag to fill, Esc to put it down.`;
      draw();
    }));
    // the hotbar's numbers (docs/EDITOR-MOVES.md): 4 to 9 on the six recent pieces
    E.hotbar(recent).forEach((t, i) => {
      const btn = $("pal").querySelector(`[data-t="${t}"]`);
      if (!btn || i < 3) return;
      let kb = btn.querySelector("kbd");
      if (!kb) { kb = document.createElement("kbd"); btn.appendChild(kb); }
      kb.textContent = String(i + 1);
      btn.title = `${btn.title.replace(/ \(key \w+\)$/, "")} (key ${i + 1})`;
    });
  }
  // blueprints in this browser's storage (a convenience for this viewer; part 8)
  function blueprints() { try { return JSON.parse(localStorage.getItem("fabgym.blueprints") || "[]") || []; } catch (e) { return []; } }
  function saveBlueprints(l) { try { localStorage.setItem("fabgym.blueprints", JSON.stringify(l)); } catch (e) { $("status").textContent = "This browser would not keep the blueprint."; } }
  function bpThumb(c) {
    const W = Math.max(1, c.w), H = Math.max(1, c.h);
    return `<svg viewBox="0 0 ${W} ${H}" width="34" height="34" aria-hidden="true">` + c.rails.map((r) => `<rect x="${r.dx + 0.3}" y="${r.dy + 0.3}" width=".4" height=".4" fill="#7EE8D8"/>`).join("") +
      c.blocks.map((b) => `<rect x="${b.dx + 0.08}" y="${b.dy + 0.08}" width="${b.w - 0.16}" height="${b.h - 0.16}" rx=".2" fill="${b.kind === "group" ? FAM[b.area] || "#8FB3AE" : b.kind === "stocker" ? "#8A6A2C" : "#2F6F68"}"/>`).join("") + `</svg>`;
  }
  const onFloor = (a) => s.blocks.filter((b) => b.kind === "group" && b.area === a).reduce((x, b) => x + b.count, 0);
  /** The cartoon card beside the palette, for the machine key pointed at or focused (part 6). */
  function palCard(bt) {
    const c = $("palcard");
    if (!bt) { c.hidden = true; return; }
    const a = bt.dataset.kind, i = E.AREAS.indexOf(a), n = onFloor(a);
    c.innerHTML = `<div class="tcard" style="--fam:${FAM[a]}"><div class="hd"><span class="nm">${esc(AREA[a][0])}</span><span class="fm">${n} on the floor</span></div>` +
      `<div class="art" style="background:${FAM[a]}33"><img src="cast/base/${String(i + 1).padStart(2, "0")}-${a}.webp" alt="" width="224" height="224"></div>` +
      `<div class="kv"><span>Price of one</span><span>${money(E.PRICE[a])}</span></div><div class="ex">${esc(AREA[a][2])}${bt.classList.contains("lever") ? " One of this challenge's levers." : ""} Click to take one in hand.</div></div>`;
    c.hidden = false;
    const r = bt.getBoundingClientRect(), hh = c.offsetHeight;
    c.style.left = `${Math.round($("pal").getBoundingClientRect().right + 10)}px`; // beside the palette, clear of its keys
    c.style.top = `${Math.round(Math.max(8, Math.min(r.top - 8, innerHeight - hh - 8)))}px`;
  }
  function syncPal() { $("pal").querySelectorAll("button[data-t]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.t === tool))); renderHint(); }
  // machines are never locked: the budget is what limits them (docs/BUILD-CONTROLS.md)
  const allowed = (t) => { const c = ch(); return !c || !c.tools || c.tools.includes(t) || t in AREA || (t === "route" && c.tools.includes("rail")); };
  function renderHint() {
    const h = $("hint"); if (!h) return;
    h.textContent = pasting ? "Click where the copy should go. Esc puts it down."
      : tool === "rail" ? "Drag across the floor to lay track. Cars run the way you drag."
      : tool === "route" ? (routeFrom ? "Click where the track should go: the shortest free way is laid, one way." : "Click where the track should start: on track or on empty floor.")
      : tool === "erase" ? "Click or drag over track and machines to remove them."
      : tool in AREA ? `Click to place one ${AREA[tool][0].toLowerCase()} machine; click one of them for one more there. Shift-drag fills. Esc puts it down.`
      : ["entry", "exit", "stocker"].includes(tool) ? "Click an empty spot to place it. R turns it."
      : "Click a machine or track to change it. Drag to select, Space-drag to move the view. J shows the jams.";
  }

  /** Whether a w × h spot at (x, y) touches the track, so a machine there gets a stop. */
  const beside = (x, y, w, h) => E.beside(s, { x, y, w, h }).length > 0;
  const blockAt = (x, y, skip) => s.blocks.find((b) => b !== skip && x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h);
  function free(x, y, w, h, skip) {
    if (x < 0 || y < 0 || x + w > s.W || y + h > s.H) return false;
    for (let i = 0; i < w; i++) for (let j = 0; j < h; j++) if (s.rail[E.key(x + i, y + j)] || blockAt(x + i, y + j, skip)) return false;
    return true;
  }
  function edited() {
    if ($("heal")) $("heal").hidden = true; // an offer to reconnect lasts until the next edit
    { const b = sel && sel.id && s.blocks.find((z) => z.id === sel.id); lastEditAt = b ? [b.x + (b.w - 1) / 2, b.y + (b.h - 1) / 2] : hover ? [...hover] : null; }
    // one undo step per gesture: the state before the gesture is kept once, at its first change
    if (!(drag && drag.recorded)) { hist.push(lastSnap); if (drag) drag.recorded = true; }
    lastSnap = snap();
    syncUndo();
    changed();
  }
  // after any change (an edit, an undo, a redo): check, then run again by itself, keeping the clock
  function changed() {
    renderChanges();
    pendingEdits = true; // reruns are automatic; "Run again" shows only when the run is out of date
    clearTimeout(checkTimer);
    checkTimer = setTimeout(async () => {
      if (drag) return changed(); // never mid-drag: wait for the release
      checks = await postWait("/api/fab/check", { fab: fab() });
      renderChecks(); draw();
      // a layout the checks refuse cannot run, so the last run no longer matches the floor: stop drawing it
      if (checks && checks.ok) runNow(true); else { pendingEdits = false; stale = true; $("again").hidden = true; renderScore(); draw(); }
    }, 250);
    draw();
  }
  const snap = () => JSON.parse(JSON.stringify(s));
  // ---------- selections (docs/BUILD-CONTROLS.md, part 7)
  const selNow = () => (boxSel ? { blocks: boxSel.blocks.slice(), rails: boxSel.rails.slice() } : { blocks: [], rails: [] });
  /** The selection while a box is dragged: new, added to the selection it started from, or taken away from it. */
  function boxNow() {
    const { a, b, mode, base } = boxDrag, got = E.inBox(s, a[0], a[1], b[0], b[1], b[0] < a[0]);
    if (mode === "new") return got;
    if (mode === "add") return { blocks: [...new Set([...base.blocks, ...got.blocks])], rails: [...new Set([...base.rails, ...got.rails])] };
    return { blocks: base.blocks.filter((id) => !got.blocks.includes(id)), rails: base.rails.filter((k) => !got.rails.includes(k)) };
  }
  /** Shift-click (or Alt-click) on (x, y): the piece there added to, or taken from, the selection. */
  function toggled(base, x, y, mode) {
    const b = blockAt(x, y), k = E.key(x, y), out = { blocks: base.blocks.slice(), rails: base.rails.slice() };
    const flip = (arr, v) => { const i = arr.indexOf(v); if (i >= 0) arr.splice(i, 1); else if (mode !== "sub") arr.push(v); };
    if (b) flip(out.blocks, b.id); else if (s.rail[k]) flip(out.rails, k);
    return out;
  }
  function selStatus() {
    $("status").textContent = boxSel ? `${boxSel.blocks.length} piece${boxSel.blocks.length === 1 ? "" : "s"} and ${boxSel.rails.length} track piece${boxSel.rails.length === 1 ? "" : "s"} selected. Drag to move, R to turn, Delete to remove.` : "";
  }
  /** A route's floor, which may have grown: the view keeps still where everything moved over (as growFor does). */
  function applyRoute(r) {
    useState(r.state);
    if (r.shift && (r.shift[0] || r.shift[1])) { const v = viewNow(); V = { s: v.s, ox: v.ox - r.shift[0] * v.s, oy: v.oy - r.shift[1] * v.s }; boxSel = null; }
  }
  /** Swap in a new floor (a move, turn or delete of a selection); the caller records the edit. */
  function useState(st) { s = st; if (setupNow) setupNow.state = s; }
  /** Act on the selection with a turn, mirror or move result: apply it, or say why not. */
  function actSel(r) {
    if (!r.ok) { $("status").textContent = r.why; return false; }
    useState(r.state); boxSel = r.sel; buildPalette(); inspector(); edited(); selStatus(); return true;
  }
  function deleteSelection(only) {
    if (!boxSel) return;
    const gaps = only === "all" || only === "track" || !only ? E.cutGaps(s, boxSel.rails) : null;
    useState(E.deleteSel(s, boxSel, only || "all"));
    boxSel = null; sel = null; buildPalette(); inspector(); edited();
    if (gaps) offerHeal(gaps);
  }
  /** After a cut of track that a run passed through: offer to reconnect around it (never done by itself). */
  function offerHeal(gaps) {
    if (!gaps.preds.length || !gaps.succs.length) return;
    healGaps = gaps; $("heal").hidden = false;
  }
  function restore(st) {
    if (!st) return;
    s = st; if (setupNow) setupNow.state = s; sel = null; drag = null; boxSel = null;
    lastSnap = snap();
    buildPalette(); inspector(); syncUndo(); changed();
  }
  function undo() { restore(hist.undo(s)); }
  function redo() { restore(hist.redo(s)); }
  function syncUndo() { $("undo").disabled = !hist.canUndo(); $("redo").disabled = !hist.canRedo(); }
  /** The view as drawn: the user's, or the fitted one. */
  const viewNow = () => (V ? { ...V } : FIT ? { s: FIT.s, ox: FIT.ox, oy: FIT.oy } : null);
  /** Grows the floor to take a piece at (x, y), holding the view still; returns how far everything moved, or null. */
  function growFor(x, y, w, h) {
    if (x >= 0 && y >= 0 && x + w <= s.W && y + h <= s.H) return [0, 0];
    const v = viewNow(), d = E.grow(s, x, y, w, h);
    if (!d) { $("status").textContent = "That is as far as the floor goes."; return null; }
    V = { s: v.s, ox: v.ox - d[0] * v.s, oy: v.oy - d[1] * v.s };
    if (d[0] || d[1]) {
      const mv = (k) => { const [a, b] = k.split(",").map(Number); return E.key(a + d[0], b + d[1]); };
      if (drag && drag.last) drag.last = mv(drag.last);
      if (sel && sel.rail) sel = { rail: mv(sel.rail) };
      for (const c of [hover, cursorCell, lastEditAt]) if (c) { c[0] += d[0]; c[1] += d[1]; }
      boxSel = null;
    }
    return d;
  }
  function zoom(factor, px, py) {
    if (!FIT) return;
    V = E.zoomAt(viewNow(), factor, px, py, FIT.s * 0.25, FIT.s * 4);
    draw();
  }
  function pan(dx, dy) { if (FIT) { V = E.panBy(viewNow(), dx, dy); draw(); } }
  const tallOf = () => 0; // nothing stands up when seen from above (docs/EDITOR-TOPDOWN.md)
  function hull(pts) {
    pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]), lo = [], up = [];
    for (const p of pts) { while (lo.length > 1 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
    for (const p of pts.reverse()) { while (up.length > 1 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }
  const inside = (pt, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) c = !c; } return c; };
  /** The cell under the pointer: a raised block's drawn box first (front to back), else the floor. */
  function cellOf(e) {
    const r = cv.getBoundingClientRect(), pt = [e.clientX - r.left, e.clientY - r.top];
    if (F && !drag) {
      const front = s.blocks.map((b) => ({ b, d: P(b.x + b.w / 2, b.y + b.h / 2)[1] })).sort((a, c) => c.d - a.d);
      for (const { b } of front) {
        const bs = [[b.x, b.y], [b.x + b.w, b.y], [b.x + b.w, b.y + b.h], [b.x, b.y + b.h]].map(([x, y]) => P(x, y));
        if (inside(pt, hull(bs.concat(bs.map((p) => [p[0], p[1] - tallOf(b) * F.s]))))) return [b.x, b.y];
      }
    }
    const [x, y] = unP(pt[0], pt[1]);
    return [Math.floor(x), Math.floor(y)];
  }
  cv.addEventListener("pointerdown", (e) => {
    if (gearsShown() && e.button === 0) {
      const g = lastGears.find((z) => Math.hypot(e.clientX - z.x, e.clientY - z.y) <= z.r + 2);
      if (g) { sel = g.kind === "group" ? { id: g.id } : { rail: g.rail }; ctlTab("sel"); inspector(); draw(); return; }
    }
    if (pasting && clip && e.button === 0) {
      const [ax, ay] = floorCell(e), plan = E.pasteAt(s, clip, ax, ay, unplaced(), knownGroups());
      if (!plan.ok) { $("status").textContent = plan.why; return; }
      let id = Math.max(0, ...s.blocks.map((z) => z.id));
      for (const b of plan.blocks) {
        // a new place for a group already on the floor takes the group's breakdown settings (part 2)
        const was = b.kind === "group" && s.blocks.find((z) => z.kind === "group" && z.group === b.group);
        s.blocks.push({ ...b, id: ++id, ...(was && was.fail ? { fail: JSON.parse(JSON.stringify(was.fail)) } : {}), ...(was && was.rec ? { rec: JSON.parse(JSON.stringify(was.rec)) } : {}) });
      }
      Object.assign(s.rail, plan.rails);
      buildPalette(); edited();
      if (plan.skipped.length) $("status").textContent = plan.skipped.join(" ");
      return;
    }
    let [x, y] = cellOf(e);
    const empty = !(x >= 0 && y >= 0 && x < s.W && y < s.H) || (!blockAt(x, y) && !s.rail[E.key(x, y)]);
    // selecting (docs/BUILD-CONTROLS.md, part 7): Shift-drag adds a box, Alt-drag takes one away, a plain drag on empty
    // floor draws a new one; Shift-click toggles a piece on release
    if (tool === "select" && e.button === 0 && !spaceHeld && (e.shiftKey || e.altKey || empty)) {
      const c = floorCell(e), mode = e.altKey ? "sub" : e.shiftKey ? "add" : "new";
      boxDrag = { a: c, b: c, mode, base: mode === "new" ? { blocks: [], rails: [] } : selNow(), moved: false };
      if (mode === "new") { boxSel = null; sel = null; inspector(); }
      cv.setPointerCapture(e.pointerId); e.preventDefault(); draw(); return;
    }
    // a selected piece drags the whole selection
    if (tool === "select" && e.button === 0 && boxSel && !spaceHeld) {
      const b0 = blockAt(x, y), k0 = E.key(x, y);
      if ((b0 && boxSel.blocks.includes(b0.id)) || (!b0 && boxSel.rails.includes(k0))) {
        drag = { moveSel: true, at: [x, y] }; cv.setPointerCapture(e.pointerId); e.preventDefault(); return;
      }
    }
    if (e.button === 1 || e.button === 2 || spaceHeld) {
      panDrag = { x: e.clientX, y: e.clientY, v: viewNow() };
      if (spaceHeld) spacePanned = true;
      cv.setPointerCapture(e.pointerId); cv.classList.add("panning");
      e.preventDefault(); draw(); return;
    }
    if ((x < 0 || y < 0 || x >= s.W || y >= s.H) && (tool === "rail" || PIECES.has(tool) || tool in AREA)) {
      // the floor grows to take what you draw (docs/EDITOR-ROOM.md)
      const [gw, gh] = tool === "rail" ? [1, 1] : handDims(placeKind());
      if (tool !== "rail" && !E.isFree(s, x, y, gw, gh, undefined, true).ok) return;
      const d = growFor(x, y, gw, gh);
      if (!d) return;
      x += d[0]; y += d[1];
    }
    // Route (part 8): the first click sets the start, the second lays the shortest way to it; either may be past the
    // floor's edge, which grows to take the way
    if (tool === "route") {
      const k0 = E.key(x, y);
      if (!routeFrom) {
        if (blockAt(x, y)) { $("status").textContent = "A route starts on track or on empty floor."; return; }
        routeFrom = k0; $("status").textContent = "Point where the track should go, then click. Esc starts again."; draw(); return;
      }
      const r = E.route(s, routeFrom, k0);
      if (!r.ok) { $("status").textContent = r.why; return; }
      applyRoute(r); routeFrom = null; routePlan = null; sel = { rail: r.path[r.path.length - 1] }; inspector(); edited();
      $("status").textContent = `Laid ${r.path.length} track pieces${r.shift[0] || r.shift[1] || r.state.W !== s.W ? "; the floor grew to take them" : ""}.`; return;
    }
    if (x < 0 || y < 0 || x >= s.W || y >= s.H) return;
    const k = E.key(x, y), b = blockAt(x, y);
    if (tool === "select") {
      boxSel = null; // a click on one piece selects just that piece
      sel = b ? { id: b.id } : s.rail[k] ? { rail: k } : null;
      if (b && mode === "build") { drag = { move: b, dx: x - b.x, dy: y - b.y }; cv.setPointerCapture(e.pointerId); }
      inspector(); draw(); return;
    }
    if (tool === "erase") {
      const before = snap(), cut = [];
      if (b) s.blocks = s.blocks.filter((z) => z !== b); else if (s.rail[k]) { delete s.rail[k]; cut.push(k); } else return;
      sel = null; buildPalette(); inspector(); edited(); drag = { erase: true, recorded: true, before, cut }; cv.setPointerCapture(e.pointerId); return;
    }
    if (tool === "rail") { if (b) return; if (!s.rail[k]) s.rail[k] = { o: [0, 0, 0, 0] }; drag = { last: k }; sel = { rail: k }; cv.setPointerCapture(e.pointerId); inspector(); edited(); return; }
    const kind = placeKind(), [w, h] = handDims(kind);
    if (kind === "group" && b && b.kind === "group" && b.area === tool) { b.count++; sel = { id: b.id }; buildPalette(); refreshCtl(); edited(); return; }
    // a piece pointed at free floor off the track snaps beside it, within 3 tiles; Alt places it where pointed (part 8)
    if (!e.altKey && ["group", "stocker", "entry", "exit"].includes(kind) && free(x, y, w, h) && !E.beside(s, { x, y, w, h }).length) {
      const sp = E.snapBeside(s, x, y, w, h);
      if (sp) [x, y] = sp;
    }
    if (!free(x, y, w, h)) return;
    if (kind === "group") {
      const nb = placeMachine(tool, x, y);
      if (!nb) return;
      if (e.shiftKey) { drag = { fill: tool }; cv.setPointerCapture(e.pointerId); } // Shift-drag fills; the fill is one undo step
      sel = { id: nb.id }; buildPalette(); refreshCtl(); edited(); return;
    }
    const id = Math.max(0, ...s.blocks.map((z) => z.id)) + 1;
    s.blocks.push({ id, kind, x, y, w, h });
    sel = { id }; inspector(); edited();
  });
  cv.addEventListener("pointermove", (e) => {
    if (panDrag) { V = E.panBy(panDrag.v, e.clientX - panDrag.x, e.clientY - panDrag.y); draw(); return; }
    if (boxDrag) {
      boxDrag.b = floorCell(e);
      if (boxDrag.b[0] !== boxDrag.a[0] || boxDrag.b[1] !== boxDrag.a[1]) boxDrag.moved = true;
      if (boxDrag.moved) boxSel = boxNow();
      draw(); return;
    }
    if (drag && drag.moveSel) {
      const [mx, my] = cellOf(e), dx = mx - drag.at[0], dy = my - drag.at[1];
      if (dx || dy) {
        const m = E.moveSel(s, boxSel, dx, dy);
        if (m.ok) { useState(m.state); boxSel = m.sel; drag.at = [mx, my]; edited(); }
        else $("status").textContent = m.why;
      }
      return;
    }
    let [x, y] = cellOf(e), inb = x >= 0 && y >= 0 && x < s.W && y < s.H;
    if (!inb && drag && drag.last) { const d = growFor(x, y, 1, 1); if (d) { x += d[0]; y += d[1]; inb = true; } }
    hover = inb ? [x, y] : null;
    cursorCell = floorCell(e);
    const pk = placeKind();
    if (pasting && clip) {
      const [ax, ay] = floorCell(e);
      pastePlan = E.pasteAt(s, clip, ax, ay, unplaced(), knownGroups());
      ghostAt = { kind: "paste", x: ax, y: ay, w: clip.w, h: clip.h, ok: pastePlan.ok, why: pastePlan.why };
      $("status").textContent = pastePlan.ok ? `Click to paste${pastePlan.skipped.length ? ". " + pastePlan.skipped.join(" ") : ""}` : pastePlan.why;
    } else if (tool === "route" && routeFrom) {
      routePlan = E.route(s, routeFrom, E.key(x, y));
      $("status").textContent = routePlan.ok ? `${routePlan.path.length} track pieces: click to lay them.` : routePlan.why;
      ghostAt = null;
    } else if (["group", "stocker", "entry", "exit"].includes(pk)) {
      const [gw, gh] = handDims(pk), f = E.isFree(s, x, y, gw, gh, undefined, true);
      ghostAt = { kind: pk, x, y, w: gw, h: gh, ok: f.ok, why: f.why };
      // the spot it will snap to (part 8)
      if (f.ok && !e.altKey && inb && !E.beside(s, { x, y, w: gw, h: gh }).length) { const sp = E.snapBeside(s, x, y, gw, gh); if (sp) ghostAt = { ...ghostAt, x: sp[0], y: sp[1], snapped: true }; }
      // every group of this kind placed: a click adds one more machine to a group already on the floor (placeMachine), in
      // a new spot; only a kind with no group in this fab at all refuses
      if (ghostAt.ok && pk === "group" && !nextGroup(tool)) {
        const join = (s.blocks.find((z) => z.kind === "group" && z.area === tool) || {}).group;
        ghostAt = join ? { ...ghostAt, joins: join } : { ...ghostAt, ok: false, why: `This fab has no ${AREA[tool][0].toLowerCase()} group.` };
      }
    } else ghostAt = null;
    if (drag && inb) {
      const k = E.key(x, y);
      if (drag.fill) {
        const [w, h] = handDims("group");
        if (free(x, y, w, h)) { const nb = placeMachine(drag.fill, x, y); if (nb) { buildPalette(); edited(); } }
      } else if (drag.move) {
        const b = drag.move, nx = x - drag.dx, ny = y - drag.dy;
        if ((nx !== b.x || ny !== b.y) && free(nx, ny, b.w, b.h, b)) { b.x = nx; b.y = ny; edited(); }
      } else if (drag.erase) {
        const b = blockAt(x, y);
        if (b) { s.blocks = s.blocks.filter((z) => z !== b); buildPalette(); } else if (s.rail[k]) { delete s.rail[k]; if (drag.cut) drag.cut.push(k); } else return;
        edited();
      } else if (k !== drag.last && !blockAt(x, y)) {
        const [lx, ly] = drag.last.split(",").map(Number), dx = x - lx, dy = y - ly;
        if (Math.abs(dx) + Math.abs(dy) === 1) {
          s.rail[drag.last].o[D.findIndex((v) => v[0] === dx && v[1] === dy)] = 1;
          if (!s.rail[k]) s.rail[k] = { o: [0, 0, 0, 0] };
          drag.last = k; sel = { rail: k }; edited();
        }
      }
    }
    hoverCard(e, x, y, inb);
    status(x, y, inb);
    if (!drag && !playing) draw();
  });
  cv.addEventListener("pointerup", () => {
    if (panDrag) { panDrag = null; cv.classList.remove("panning"); return; }
    if (boxDrag) {
      const bd = boxDrag;
      boxDrag = null;
      if (!bd.moved && bd.mode !== "new") boxSel = toggled(bd.base, bd.a[0], bd.a[1], bd.mode);
      if (boxSel && !boxSel.blocks.length && !boxSel.rails.length) boxSel = null;
      inspector();
      $("status").textContent = boxSel ? `${boxSel.blocks.length} piece${boxSel.blocks.length === 1 ? "" : "s"} and ${boxSel.rails.length} track piece${boxSel.rails.length === 1 ? "" : "s"} selected. ⌘C copies, Delete removes.` : "";
      draw(); return;
    }
    const was = drag;
    drag = null; inspector();
    if (was && was.erase && was.cut && was.cut.length) offerHeal(E.cutGaps(was.before, was.cut));
  });
  cv.addEventListener("contextmenu", (e) => e.preventDefault()); // the right button pans
  // double-click: every block of a machine's group, or all the track joined to a piece (part 7)
  cv.addEventListener("dblclick", (e) => {
    if (tool !== "select") return;
    const [x, y] = cellOf(e), b = blockAt(x, y), k = E.key(x, y);
    if (b && b.kind === "group") boxSel = { blocks: s.blocks.filter((z) => z.kind === "group" && z.group === b.group).map((z) => z.id), rails: [] };
    else if (!b && s.rail[k]) boxSel = { blocks: [], rails: E.connectedRail(s, k) };
    else return;
    sel = null; ctlTab("sel"); inspector(); selStatus(); draw();
  });
  cv.addEventListener("pointerleave", () => { hover = null; cursorCell = null; ghostAt = null; $("hover").hidden = true; if (!playing) draw(); });
  // scroll or pinch zooms about the pointer
  cv.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = cv.getBoundingClientRect();
    zoom(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  $("undo").onclick = undo;
  $("redo").onclick = redo;

  function groupNow(b) {
    if (!showRun()) return null;
    const fi = frameIdx(), gi = run.group_names.indexOf(b.group);
    const tools = run.groups.reduce((n, g) => n + (g === b.group ? 1 : 0), 0);
    return { mood: E.blockMood(run, fi, b.group), queue: gi >= 0 ? run.frames[fi].queues[gi] : 0, tools };
  }
  function status(x, y, inb) {
    if (!inb) return ($("status").textContent = "");
    const b = blockAt(x, y), k = E.key(x, y);
    if (b && b.kind === "group") { const n = groupNow(b); $("status").textContent = `(${x}, ${y})  ${b.group}: ${b.count} tool${b.count > 1 ? "s" : ""}, ${AREA[b.area][0]}${n ? `, ${n.queue} lot${n.queue === 1 ? "" : "s"} waiting, ${MOOD[n.mood || "work"][0].toLowerCase()}` : ""}`; }
    else if (b) $("status").textContent = `(${x}, ${y})  ${INFRA[b.kind][0].toLowerCase()}`;
    else if (s.rail[k]) { const o = s.rail[k].o.map((z, i) => (z ? DLONG[i] : null)).filter(Boolean); $("status").textContent = `(${x}, ${y})  rail, out ${o.join(" and ") || "nowhere"}${o.length > 1 ? " (a split)" : ""}${s.rail[k].fail ? ", breaks now and then" : ""}`; }
    else if (ghostAt && ghostAt.ok && ghostAt.joins) $("status").textContent = `(${x}, ${y})  floor, click to add one more machine to ${ghostAt.joins} here; its machines in both spots count as one group`;
    else $("status").textContent = `(${x}, ${y})  floor${mode === "build" && tool !== "select" && tool !== "erase" ? ", click to place" : ""}`;
  }

  function hoverCard(e, x, y, inb) {
    const hov = $("hover");
    if (!inb || drag) return (hov.hidden = true);
    const b = blockAt(x, y);
    let key = null, html = null;
    if (b && b.kind === "group") {
      const n = groupNow(b), mood = (n && n.mood) || "work", col = FAM[b.area];
      key = `${b.id}|${mood}|${n ? n.queue : "-"}|${b.count}`;
      html = () => `<div class="tcard" style="--fam:${col}"><div class="hd"><span class="nm">${esc(AREA[b.area][0])}</span><span class="fm">${b.count} tool${b.count > 1 ? "s" : ""}</span></div>
        <div class="art" style="background:${col}33"><img src="cast/${b.area}/${mood}.webp" alt="${esc(AREA[b.area][0])}, ${MOOD[mood][0].toLowerCase()}" width="224" height="224"></div>
        <div class="st" style="background:${MOOD[mood][1]}">${n ? MOOD[mood][0] : "Before a run"}</div>
        <div class="kv"><span>Lots waiting</span><span>${n ? n.queue : "–"}</span><span>Group</span><span>${esc(b.group)}</span><span>Price of one</span><span>${money(E.PRICE[b.area] || 0)}</span></div>
        <div class="ex">${esc(AREA[b.area][1])}. ${esc(AREA[b.area][2])}</div></div>`;
    } else if (!b && showRun() && win && speed !== MAX) {
      const v = vehicles(clock).find((w) => Math.abs(w.x - x) < 0.8 && Math.abs(w.y - y) < 0.8);
      if (v) {
        const m = v.hot ? "hot" : v.loaded ? "ride" : null;
        key = `v${v.vehicle}|${m}`;
        html = () => m
          ? `<div class="tcard" style="--fam:${v.hot ? "#FF8A4C" : "#F2B33D"}"><div class="hd"><span class="nm">Vehicle ${v.vehicle + 1}</span><span class="fm">${v.hot ? "urgent lot" : "carrying a lot"}</span></div><div class="art" style="background:#E3EAF0"><img src="cast/lots/${m}.webp" alt="A lot of wafers riding the track" width="224" height="224"></div><div class="st" style="background:${v.hot ? "#FF8A4C" : "#5FA8FF"}">${v.hot ? "Urgent lot, on its way" : "On its way"}</div><div class="ex">This is where the simulator had the car at ${hhmmss(clock)}.</div></div>`
          : `<div class="tcard" style="--fam:#8A9AA2"><div class="hd"><span class="nm">Vehicle ${v.vehicle + 1}</span><span class="fm">empty</span></div><div class="ex">Driving empty to its next pickup, as the simulator had it at ${hhmmss(clock)}.</div></div>`;
      }
    }
    if (!html) return (hov.hidden = true);
    if (hov.dataset.k !== key) { hov.innerHTML = html(); hov.dataset.k = key; }
    // drawn over the page and kept inside the window, so nothing around the map cuts it (docs/BUILD-CONTROLS.md, part 6)
    hov.hidden = false;
    const hw = hov.offsetWidth || 230, hh = hov.offsetHeight || 320;
    let lx = e.clientX + 16, ly = e.clientY + 12;
    if (lx + hw > innerWidth - 8) lx = e.clientX - hw - 16;
    if (ly + hh > innerHeight - 8) ly = Math.max(8, innerHeight - hh - 8);
    hov.style.left = Math.max(8, lx) + "px"; hov.style.top = ly + "px";
  }

  // ---------- the controls panel (docs/BUILD-CONTROLS.md): Selected, Whole fab, All controls; every control says what it does
  const FAILS = [["", "As in the data"], ["none", "Never"], ["random", "At random"], ["by_wafers", "After so many wafers"]];
  const RECS = [["", "Fix it where it stands"], ["swap_to_spare", "Swap in a spare"], ["repair_and_hold_lots", "Fix it and hold its last lots for checks"]];
  const WHY = {
    count: "More machines share the line; each costs its price.",
    fail: "How often a machine breaks down, and how long a fix takes.",
    rec: "Fix it in place, swap in a spare (costs a machine), or fix it and hold its last lots for checks.",
    dirs: "Cars leave this piece only these ways; two ways make a junction.",
    rfail: "Whether this piece of track stops now and then.",
    rrec: "Cars wait for the repair, or go around it where there is another way.",
    cars: "More cars carry more lots at once, and can jam the track.",
    cap: "New lots wait at the door while this many are inside; 0 means no cap. Too low starves the fab.",
    ports: "How many lots each machine takes at its ports; the rest wait in storage until a port frees. Unlimited needs no storage.",
    rule: "Which waiting lot a free machine takes next. Today's rule takes urgent lots first, then lots that need no re-setup, then the oldest.",
    demand: "How often new lots come in. More lots can mean more wafers out; past what the machines and cars can carry, lines grow and output can fall.",
    urgent: "Urgent lots go to the front of every line: they finish sooner, and the lots behind them wait longer.",
    rework: "A check that finds a fault sends the lot back to redo the step before, so machines repeat work. The SMT2020 testbed's lithography checks send back 0.7% to 1.8% of lots.",
    holds: "When a check sends a lot back, its measuring machine stops and the lots it measured just before wait (lengths assumed, as on the Floor). Needs some rework.",
  };
  const num = (id, v, lab, unit) => `<label class="sub">${lab} <input type="number" min="1" step="1" id="${id}" value="${v}"> ${unit}</label>`;
  const why = (k) => `<span class="why">${WHY[k]}</span>`;
  // each control's glossary entry (docs/BUILD-CONTROLS.md, part 5)
  const TERM = { count: "Tool group", fail: "Breakdown", rec: "Repair time", dirs: "Track (overhead track)", rfail: "Breakdown", rrec: "Track (overhead track)",
    cars: "Car (vehicle)", cap: "WIP cap", ports: "Load port", rule: "Dispatch rule", demand: "Demand (release rate)", urgent: "Hot lot", rework: "Rework", holds: "Defect hold" };
  const glq = (k) => (TERM[k] ? `<button type="button" class="gl-q" data-term="${esc(TERM[k])}" aria-label="What is ${esc(TERM[k])}?" title="What is ${esc(TERM[k])}?">?</button>` : "");
  const row = (k, inner) => `<div class="row ctlrow" data-ctl="${k}">${inner.replace(/(<\/label>|<\/span>)/, `$1${glq(k)}`)}${why(k)}</div>`;
  let ctlTabNow = "sel";
  function ctlTab(name) {
    ctlTabNow = name;
    document.querySelectorAll("#ctl-tabs [data-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
    $("insp").hidden = name !== "sel"; $("ctl-fab").hidden = name !== "fab"; $("ctl-all").hidden = name !== "all";
    if (name === "fab") wholeFab($("ctl-fab"));
    if (name === "all") allControls();
    markMoved();
  }
  // the changes a control makes, shared by Selected and All controls
  // a group's breakdown settings are the group's, wherever its machines stand (docs/BUILD-CONTROLS.md, part 2)
  function syncGroup(b) {
    for (const z of s.blocks) if (z !== b && z.kind === "group" && z.group === b.group) {
      z.fail = b.fail ? JSON.parse(JSON.stringify(b.fail)) : undefined;
      z.rec = b.rec ? JSON.parse(JSON.stringify(b.rec)) : undefined;
    }
  }
  const setFail = (b, k) => { b.fail = k === "" ? undefined : k === "none" ? { kind: "none" } : k === "random" ? { kind: "random", mttf_minutes: 480, mttr_minutes: 120 } : { kind: "by_wafers", every: 500, minutes: [60, 120] }; syncGroup(b); };
  const setRec = (b, k) => { b.rec = k === "" ? undefined : k === "swap_to_spare" ? { kind: "swap_to_spare", spares: 1, swap_minutes: 20 } : { kind: "repair_and_hold_lots", lookback_minutes: 60, hold_minutes: 120 }; syncGroup(b); };
  /** One machine of a kind at (x, y): its group's first placing, or a new place for a group already on the floor. */
  function placeMachine(area, x, y) {
    const [w, h] = handDims("group"), id = Math.max(0, ...s.blocks.map((z) => z.id)) + 1;
    const g = nextGroup(area) || (s.blocks.find((z) => z.kind === "group" && z.area === area) || {}).group;
    if (!g) return null;
    const like = s.blocks.find((z) => z.kind === "group" && z.group === g);
    const nb = { id, kind: "group", group: g, area, count: 1, x, y, w, h };
    if (like) { if (like.fail) nb.fail = JSON.parse(JSON.stringify(like.fail)); if (like.rec) nb.rec = JSON.parse(JSON.stringify(like.rec)); }
    s.blocks.push(nb);
    return nb;
  }
  const failSel = (id, f) => `<select id="${id}">${FAILS.map(([k, n]) => `<option value="${k}" ${(f.kind || "") === k ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  const recSel = (id, r) => `<select id="${id}">${RECS.map(([k, n]) => `<option value="${k}" ${(r.kind || "") === k ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  function wholeFab(el) {
    el.innerHTML = `<div class="ttl">${svg("fab")}<span>The whole fab</span></div>` +
      row("cars", `<span>Cars on the track</span><span class="count"><button class="btn" data-cars="-1" aria-label="One fewer car">−</button><b>${s.vehicles}</b><button class="btn" data-cars="1" aria-label="One more car">+</button></span>`) +
      row("cap", `<label for="${el.id}-cap">Cap on lots inside</label><span class="sub"><input type="number" min="0" step="1" id="${el.id}-cap" value="${s.cap || 0}"> lots</span>`) +
      row("ports", `<label for="${el.id}-ports">Load ports per machine</label><select id="${el.id}-ports">${[["", "Unlimited"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"]].map(([v, n]) => `<option value="${v}" ${String(s.inports || "") === v ? "selected" : ""}>${n}</option>`).join("")}</select>`);
    el.querySelectorAll("[data-cars]").forEach((bt) => (bt.onclick = () => { s.vehicles = Math.max(1, s.vehicles + Number(bt.dataset.cars)); refreshCtl(); edited(); }));
    $(`${el.id}-ports`).onchange = (e) => { const n = Number(e.target.value); if (n) s.inports = n; else delete s.inports; refreshCtl(); renderScore(); edited(); };
    $(`${el.id}-cap`).onchange = (e) => { const n = Math.max(0, Math.round(Number(e.target.value) || 0)); if (n) s.cap = n; else delete s.cap; refreshCtl(); edited(); };
    // the Floor's settings (docs/BUILD-CONTROLS.md, part 4)
    const o = E.flowOptions(base), f = s.flow || {}, NAMES = FLOWNAMES;
    el.insertAdjacentHTML("beforeend", `<div class="ttl sub-ttl"><span>How the fab runs</span></div>` + Object.keys(NAMES).map((k) =>
      row(k, `<label for="${el.id}-${k}">${NAMES[k]}</label><select id="${el.id}-${k}">${o[k].map(([v, n]) => `<option value="${v}" ${String(f[k] == null ? "" : f[k]) === v ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`)).join(""));
    // the teaching fab's machines need no re-setup and a step takes the same time on every machine of its kind, so the
    // three rules pick the same lots until urgent lots come in (measured on runs #1 to #3)
    if (!E.flowKind(base).hot && !f.urgent) $(`${el.id}-rule`).closest(".ctlrow").insertAdjacentHTML("beforeend", `<span class="why">Here all three pick the same lots until there are urgent lots: no machine needs a re-setup, and a step takes the same time on every machine of its kind.</span>`);
    for (const k of Object.keys(NAMES)) $(`${el.id}-${k}`).onchange = (e) => {
      const v = e.target.value, flow = { ...(s.flow || {}) };
      if (v === "") delete flow[k]; else flow[k] = k === "demand" || k === "holds" ? Number(v) : v;
      if (Object.keys(flow).length) s.flow = flow; else delete s.flow;
      refreshCtl(); renderScore(); edited();
    };
  }
  function allControls() {
    const el = $("ctl-all"), groups = s.blocks.filter((b) => b.kind === "group"), broken = Object.keys(s.rail).filter((k) => s.rail[k].fail);
    let h = `<table class="allctl"><tbody>` + groups.map((b) => `<tr class="ctlrow" data-group="${esc(b.group)}" data-ctl="count:${esc(b.group)}"><td><b>${esc(AREA[b.area][0])}</b> <small>${esc(b.group)}</small>` +
      `${glq("count")}<span class="why">${WHY.count} ${money(E.PRICE[b.area] || 0)} a machine.</span></td><td><span class="count"><button class="btn" data-dn aria-label="One fewer">−</button><b>${b.count}</b><button class="btn" data-up aria-label="One more">+</button></span>` +
      `${failSel(`af-${b.id}`, b.fail || {})}${recSel(`ar-${b.id}`, b.rec || {})}</td></tr>`).join("");
    h += broken.map((k) => `<tr class="ctlrow" data-rail="${k}" data-ctl="rrec:${k}"><td><b>Track piece</b> <small>${k.replace(",", ", ")}</small>${glq("rrec")}${why("rrec")}</td><td><select data-rr><option value="wait" ${(s.rail[k].rec || {}).kind !== "route_around" ? "selected" : ""}>Cars wait for the repair</option><option value="route_around" ${(s.rail[k].rec || {}).kind === "route_around" ? "selected" : ""}>Cars go around it</option></select></td></tr>`).join("");
    el.innerHTML = h + `</tbody></table>`;
    el.querySelectorAll("tr[data-group]").forEach((tr) => {
      const b = s.blocks.find((z) => z.kind === "group" && z.group === tr.dataset.group);
      tr.querySelector("[data-up]").onclick = () => { b.count++; refreshCtl(); buildPalette(); edited(); };
      tr.querySelector("[data-dn]").onclick = () => { b.count = Math.max(1, b.count - 1); refreshCtl(); buildPalette(); edited(); };
      tr.querySelector(`#af-${b.id}`).onchange = (e) => { setFail(b, e.target.value); refreshCtl(); edited(); };
      tr.querySelector(`#ar-${b.id}`).onchange = (e) => { setRec(b, e.target.value); refreshCtl(); edited(); };
    });
    el.querySelectorAll("tr[data-rail] [data-rr]").forEach((sl) => (sl.onchange = (e) => { s.rail[sl.closest("tr").dataset.rail].rec = { kind: e.target.value }; edited(); }));
  }
  /** Redraw what the controls show after a change, keeping the open tab. */
  function refreshCtl() { inspector(); if (ctlTabNow !== "sel") ctlTab(ctlTabNow); markMoved(); }
  function inspector() { inspectorDraw(); markMoved(); }
  function inspectorDraw() {
    const ins = $("insp");
    if (boxSel && (boxSel.blocks.length || boxSel.rails.length)) { bulkPanel(ins); return; }
    if (sel && sel.id) {
      const b = s.blocks.find((z) => z.id === sel.id);
      if (!b) { sel = null; return inspector(); }
      if (b.kind === "group") {
        const f = b.fail || {}, r = b.rec || {};
        let h = `<div class="ttl">${svg(b.area, FAM[b.area])}<span>${esc(AREA[b.area][0])}</span></div><p class="note">${esc(b.group)} · ${esc(AREA[b.area][2])} ${money(E.PRICE[b.area])} a machine (assumed).</p>`;
        const places = s.blocks.filter((z) => z.kind === "group" && z.group === b.group), all = places.reduce((a, z) => a + z.count, 0);
        h += row("count", `<span>${places.length > 1 ? "Machines here" : "Machines in this group"}</span><span class="count"><button class="btn" id="dn" aria-label="One fewer">−</button><b>${b.count}</b><button class="btn" id="up" aria-label="One more">+</button></span>`);
        if (places.length > 1) h += `<p class="note">${all} in the group in all, in ${places.length} places.</p>`;
        h += row("fail", `<label for="fsel">Breakdowns</label>${failSel("fsel", f)}`);
        if (f.kind === "random") h += `<div class="row">${num("fa", f.mttf_minutes / 60, "about every", "h")}${num("fb", f.mttr_minutes / 60, "fix takes", "h")}</div>`;
        if (f.kind === "by_wafers") h += `<div class="row">${num("fa", f.every, "after", "wafers")}${num("fb", (f.minutes || [60])[0], "fix takes", "min")}</div>`;
        h += row("rec", `<label for="rsel">When it breaks</label>${recSel("rsel", r)}`);
        // the same breakdowns for every group, or every group of this kind (part 8)
        const kinds = new Set(s.blocks.filter((z) => z.kind === "group" && z.area === b.area).map((z) => z.group)).size;
        h += `<div class="row same-btns"><button class="btn" data-same="all">Same for every machine group</button>${kinds > 1 ? `<button class="btn" data-same="kind">Same for every ${esc(AREA[b.area][0])} group</button>` : ""}</div>`;
        if (r.kind === "swap_to_spare") h += `<div class="row">${num("ra", r.spares, "spares", `(${money(r.spares * E.PRICE[b.area])})`)}${num("rb", r.swap_minutes, "swap takes", "min")}</div>`;
        h += `<div class="row"><button class="btn" id="del">Remove</button></div>`;
        ins.innerHTML = h;
        ins.querySelectorAll("[data-same]").forEach((bt) => (bt.onclick = () => { useState(E.sameForKind(s, b.group, bt.dataset.same)); refreshCtl(); edited(); $("status").textContent = "Breakdowns copied."; }));
        $("up").onclick = () => { b.count++; refreshCtl(); buildPalette(); edited(); };
        $("dn").onclick = () => { b.count = Math.max(1, b.count - 1); refreshCtl(); buildPalette(); edited(); };
        $("fsel").onchange = (e) => { setFail(b, e.target.value); refreshCtl(); edited(); };
        $("rsel").onchange = (e) => { setRec(b, e.target.value); refreshCtl(); edited(); };
        const bind = (id, fn) => { const el = $(id); if (el) el.onchange = () => { const v = Number(el.value); if (v > 0) { fn(v); edited(); } refreshCtl(); }; };
        bind("fa", (v) => { f.kind === "random" ? (b.fail.mttf_minutes = v * 60) : (b.fail.every = v); syncGroup(b); });
        bind("fb", (v) => { f.kind === "random" ? (b.fail.mttr_minutes = v * 60) : (b.fail.minutes = [v, v]); syncGroup(b); });
        bind("ra", (v) => { b.rec.spares = Math.round(v); syncGroup(b); });
        bind("rb", (v) => { b.rec.swap_minutes = v; syncGroup(b); });
      } else {
        const idle = b.kind === "stocker" && !s.inports ? ` With unlimited load ports (this fab's setting, under Whole fab), nothing waits here.` : b.kind === "stocker" ? ` Machines here take ${s.inports} lot${s.inports > 1 ? "s" : ""} each at their ports.` : "";
        ins.innerHTML = `<div class="ttl">${svg(b.kind)}<span>${INFRA[b.kind][0]}</span></div><p class="note">${INFRA[b.kind][1]}${idle}</p><div class="row"><button class="btn" id="del">Remove</button></div>`;
      }
      $("del").onclick = () => { s.blocks = s.blocks.filter((z) => z !== b); sel = null; buildPalette(); refreshCtl(); edited(); };
    } else if (sel && sel.rail && s.rail[sel.rail]) {
      const v = s.rail[sel.rail], split = v.o.reduce((a, c) => a + c) > 1, f = v.fail || {};
      let h = `<div class="ttl">${svg(split ? "split" : "rail")}<span>Track piece (${sel.rail.replace(",", ", ")})</span></div><p class="note">Track runs one way. Turn on a second direction to make a junction.</p>`;
      h += row("dirs", `<span>Directions out</span><span class="dirs4">${DN.map((d, i) => `<button class="btn" data-d="${i}" aria-pressed="${!!v.o[i]}" aria-label="${DLONG[i]}">${d}</button>`).join("")}</span>`);
      h += row("rfail", `<label for="rf">Breakdowns</label><select id="rf"><option value="">Never</option><option value="random" ${f.kind === "random" ? "selected" : ""}>Now and then</option></select>`);
      if (f.kind === "random") {
        h += `<div class="row">${num("ra", f.mttf_minutes, "about every", "min")}${num("rb", f.mttr_minutes, "for", "min")}</div>`;
        h += row("rrec", `<label for="rr">When it stops</label><select id="rr"><option value="wait" ${(v.rec || {}).kind !== "route_around" ? "selected" : ""}>Cars wait for the repair</option><option value="route_around" ${(v.rec || {}).kind === "route_around" ? "selected" : ""}>Cars go around it</option></select>`);
      }
      ins.innerHTML = h;
      ins.querySelectorAll("[data-d]").forEach((bt) => (bt.onclick = () => { const d = +bt.dataset.d; v.o[d] = v.o[d] ? 0 : 1; refreshCtl(); edited(); }));
      $("rf").onchange = (e) => { if (e.target.value) { v.fail = { kind: "random", mttf_minutes: 240, mttr_minutes: 60 }; v.rec = { kind: "wait" }; } else { delete v.fail; delete v.rec; } refreshCtl(); edited(); };
      if ($("rr")) $("rr").onchange = (e) => { v.rec = { kind: e.target.value }; edited(); };
      const bind = (id, fn) => { const el = $(id); if (el) el.onchange = () => { const n = Number(el.value); if (n > 0) { fn(n); edited(); } refreshCtl(); }; };
      bind("ra", (n) => (v.fail.mttf_minutes = n));
      bind("rb", (n) => (v.fail.mttr_minutes = n));
    } else {
      // nothing selected: the whole fab's controls, as before, and a pointer to the other tabs
      wholeFab(ins);
      ins.insertAdjacentHTML("afterbegin", `<p class="note">Click a machine or a piece of track to change it, or pick a machine in the palette. All controls lists everything at once.</p>`);
    }
  }

  // ---------- a selection's panel: what is in it, controls for all of it, and its delete buttons (part 7)
  function bulkPanel(ins) {
    const bs = s.blocks.filter((b) => boxSel.blocks.includes(b.id)), gs = bs.filter((b) => b.kind === "group"), infra = bs.filter((b) => b.kind !== "group");
    const groups = [...new Set(gs.map((b) => b.group))], rails = boxSel.rails.filter((k) => s.rail[k]), pl = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
    const one = (list, f) => { const v = list.map((x) => JSON.stringify(f(x) || {})); return v.every((x) => x === v[0]) ? JSON.parse(v[0] || "{}") : {}; };
    let h = `<div class="ttl"><span>Selection</span></div><p class="note">${[gs.length && `${pl(groups.length, "machine group")} (${pl(gs.reduce((a, b) => a + b.count, 0), "machine")})`,
      infra.length && `${infra.length} storage and door piece${infra.length === 1 ? "" : "s"}`, rails.length && pl(rails.length, "track piece")].filter(Boolean).join(", ")}.</p>`;
    if (gs.length) {
      h += row("fail", `<label for="bulk-fail">Breakdowns, for all ${groups.length}</label>${failSel("bulk-fail", one(gs, (b) => b.fail))}`);
      h += row("rec", `<label for="bulk-rec">When they break</label>${recSel("bulk-rec", one(gs, (b) => b.rec))}`);
    }
    if (rails.length) {
      const any = rails.some((k) => s.rail[k].fail);
      h += row("rfail", `<label for="bulk-rfail">Track breakdowns</label><select id="bulk-rfail"><option value="">Never</option><option value="random" ${any ? "selected" : ""}>Now and then</option></select>`);
    }
    h += `<div class="row bulk-btns"><button class="btn" data-act="save">Save as a blueprint</button></div><div class="row bp-new" id="bp-new" hidden><input id="bp-name" placeholder="Name it" aria-label="Blueprint name" maxlength="40"><button class="btn" id="bp-save">Save</button></div>`;
    h += `<div class="row bulk-btns"><button class="btn" data-act="turn" title="R">Turn</button><button class="btn" data-act="mirror" title="Shift-R">Mirror</button><button class="btn" data-act="dup" title="⌘D">Duplicate</button></div>`;
    h += `<div class="row bulk-btns"><span class="note">Delete:</span><button class="btn" data-del="all" title="Delete">All of it</button>${rails.length ? `<button class="btn" data-del="track">Only the track</button>` : ""}${gs.length ? `<button class="btn" data-del="machines">Only the machines</button>` : ""}${infra.length ? `<button class="btn" data-del="infra">Only storage and doors</button>` : ""}</div>`;
    ins.innerHTML = h;
    const byGroup = () => groups.map((g) => s.blocks.find((z) => z.kind === "group" && z.group === g)).filter(Boolean);
    if ($("bulk-fail")) $("bulk-fail").onchange = (e) => { for (const b of byGroup()) setFail(b, e.target.value); refreshCtl(); edited(); };
    if ($("bulk-rec")) $("bulk-rec").onchange = (e) => { for (const b of byGroup()) setRec(b, e.target.value); refreshCtl(); edited(); };
    if ($("bulk-rfail")) $("bulk-rfail").onchange = (e) => {
      for (const k of rails) { const v = s.rail[k]; if (e.target.value) { v.fail = { kind: "random", mttf_minutes: 240, mttr_minutes: 60 }; v.rec = { kind: "wait" }; } else { delete v.fail; delete v.rec; } }
      refreshCtl(); edited();
    };
    ins.querySelectorAll("[data-del]").forEach((bt) => (bt.onclick = () => deleteSelection(bt.dataset.del)));
    $("bp-save").onclick = () => {
      const c = E.copySel(s, boxSel), name = $("bp-name").value.trim() || `Blueprint ${blueprints().length + 1}`;
      if (!c) return;
      saveBlueprints([{ name, clip: c }, ...blueprints()].slice(0, 12));
      buildPalette(); $("bp-new").hidden = true; $("status").textContent = `Saved "${name}" in the palette.`;
    };
    ins.querySelectorAll("[data-act]").forEach((bt) => (bt.onclick = () => {
      if (bt.dataset.act === "save") { $("bp-new").hidden = false; $("bp-name").focus(); return; }
      if (bt.dataset.act === "dup") { clip = E.copySel(s, boxSel); if (clip) { pasting = true; ghostAt = null; $("status").textContent = "A copy in hand: click where it should go. Esc drops it."; draw(); } return; }
      actSel(E.turnSel(s, boxSel, bt.dataset.act === "mirror"));
    }));
  }

  // ---------- gears, find a control, your changes and the glossary (docs/BUILD-CONTROLS.md, part 5)
  const FLOWNAMES = { rule: "Dispatch rule", demand: "Demand", urgent: "Urgent lots", rework: "Rework", holds: "Quality holds" };
  const FABNAMES = { cars: "Cars on the track", cap: "Cap on lots inside", ports: "Load ports per machine", ...FLOWNAMES };
  const GROUPNAMES = { count: "Machines", fail: "Breakdowns", rec: "When it breaks" };
  const RAILNAMES = { dirs: "Directions out", rfail: "Breakdowns", rrec: "When it stops" };
  const clone = (v) => (v == null ? v : JSON.parse(JSON.stringify(v)));
  const same = (a, b) => JSON.stringify(a == null ? null : a) === JSON.stringify(b == null ? null : b);

  // gears: hold G, or the Controls button
  let gearsBtn = false, gHeld = false, lastGears = [];
  const gearsShown = () => gearsBtn || gHeld;
  function drawGears() {
    lastGears = [];
    if (!gearsShown() || !s) return;
    const r = cv.getBoundingClientRect(), c = ch(), litGroup = c && c.spot && c.spot.group, litRail = !!(c && c.spot && c.spot.rail);
    const rad = Math.max(9, Math.min(13, F.s * 0.32));
    const one = (px, py, n, lit, g) => {
      ctx.save();
      ctx.fillStyle = lit ? "#F2B33D" : "#0F1D22"; ctx.strokeStyle = lit ? "#FFE3A3" : "#7EE8D8"; ctx.lineWidth = 1.6;
      ctx.beginPath(); // a gear: eight teeth round a disc
      for (let i = 0; i < 16; i++) { const a = (i / 16) * Math.PI * 2, rr = i % 2 ? rad : rad * 1.22; ctx.lineTo(px + Math.cos(a) * rr, py + Math.sin(a) * rr); }
      ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.font = `700 ${Math.round(rad * 1.05)}px "Chakra Petch",sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = lit ? "#14191D" : "#E8F2F0"; ctx.fillText(String(n), px, py + 0.5);
      ctx.restore();
      lastGears.push({ ...g, n, lit, x: r.left + px, y: r.top + py, r: rad * 1.22 });
    };
    for (const b of s.blocks) if (b.kind === "group") { const [px, py] = P(b.x + b.w - 0.32, b.y + 0.32); one(px, py, Object.keys(GROUPNAMES).length, b.group === litGroup, { kind: "group", id: b.id }); }
    for (const k of Object.keys(s.rail)) if (s.rail[k].fail) { const [x, y] = k.split(",").map(Number), [px, py] = P(x + 0.5, y + 0.5, 0.06); one(px, py, Object.keys(RAILNAMES).length, litRail, { kind: "rail", rail: k }); }
  }

  // your changes, from the challenge's start (or Free build's)
  const groupTotals = (st) => { const m = {}; for (const b of st.blocks) if (b.kind === "group") (m[b.group] = m[b.group] || { n: 0, b }).n += b.count; return m; };
  const failWords = (f) => (!f ? "as the fab has them" : f.kind === "none" ? "never" : f.kind === "random" ? `about every ${Math.round(f.mttf_minutes / 60)} h, fixed in ${Math.round(f.mttr_minutes / 60)} h` : `after every ${f.every} wafers`);
  const recWords = (r) => (!r || r.kind === "repair_in_place" ? "fix it in place" : r.kind === "swap_to_spare" ? `swap in a spare (${r.spares} kept)` : "fix it and hold its last lots");
  const spares = (r) => (r && r.kind === "swap_to_spare" ? r.spares || 0 : 0);
  function setGroup(g, key, v) { for (const b of s.blocks) if (b.kind === "group" && b.group === g) { if (v == null) delete b[key]; else b[key] = clone(v); } }
  function undoCount(g) {
    const was = start.blocks.filter((b) => b.kind === "group" && b.group === g), cur = s.blocks.filter((b) => b.kind === "group" && b.group === g);
    const fail = cur[0] && cur[0].fail, rec = cur[0] && cur[0].rec;
    s.blocks = s.blocks.filter((b) => !(b.kind === "group" && b.group === g && !was.some((z) => z.id === b.id)));
    for (const z of was) { let b = s.blocks.find((y) => y.id === z.id); if (!b) { b = clone(z); s.blocks.push(b); } b.count = z.count; }
    if (cur.length) { setGroup(g, "fail", fail); setGroup(g, "rec", rec); }
  }
  function changesOf() {
    if (!start || !s) return [];
    const out = [], t0 = groupTotals(start), t1 = groupTotals(s);
    for (const g of new Set([...Object.keys(t0), ...Object.keys(t1)])) {
      const a = (t0[g] || t1[g]).b.area, nm = AREA[a] ? AREA[a][0] : g, price = E.PRICE[a] || 0;
      const d = (t1[g] ? t1[g].n : 0) - (t0[g] ? t0[g].n : 0);
      if (d) out.push({ key: `count:${g}`, group: g, ctl: "count", text: `${d > 0 ? "+" : "−"}${Math.abs(d)} ${nm} machine${Math.abs(d) > 1 ? "s" : ""}`, cost: d * price, undo: () => undoCount(g) });
      if (!t0[g] || !t1[g]) continue;
      const f0 = t0[g].b.fail, f1 = t1[g].b.fail, r0 = t0[g].b.rec, r1 = t1[g].b.rec;
      if (!same(f0, f1)) out.push({ key: `fail:${g}`, group: g, ctl: "fail", text: `${nm}: breakdowns ${failWords(f1)}`, cost: 0, undo: () => setGroup(g, "fail", f0) });
      if (!same(r0, r1)) out.push({ key: `rec:${g}`, group: g, ctl: "rec", text: `${nm}: when it breaks, ${recWords(r1)}`, cost: (spares(r1) - spares(r0)) * price, undo: () => setGroup(g, "rec", r0) });
    }
    const k0 = Object.keys(start.rail), k1 = Object.keys(s.rail);
    const added = k1.filter((k) => !start.rail[k]), gone = k0.filter((k) => !s.rail[k]), turned = k1.filter((k) => start.rail[k] && !same(start.rail[k].o, s.rail[k].o));
    const pc = (n) => `${n} piece${n > 1 ? "s" : ""}`;
    if (added.length || gone.length || turned.length) out.push({ key: "track", ctl: "dirs", rails: [...added, ...turned],
      text: `Track: ${[added.length && `${pc(added.length)} added`, gone.length && `${pc(gone.length)} taken away`, turned.length && `${pc(turned.length)} with new directions`].filter(Boolean).join(", ")}`, cost: 0,
      undo: () => { for (const k of added) delete s.rail[k]; for (const k of gone) s.rail[k] = clone(start.rail[k]); for (const k of turned) if (s.rail[k]) s.rail[k].o = [...start.rail[k].o]; } });
    for (const k of k1) {
      const a = start.rail[k] || {}, b = s.rail[k];
      if (same(a.fail, b.fail) && (!b.fail || same(a.rec, b.rec))) continue;
      out.push({ key: `rail:${k}`, rail: k, text: `Track piece ${k.replace(",", ", ")}: ${b.fail ? `stops now and then, ${(b.rec || {}).kind === "route_around" ? "cars go around it" : "cars wait for the repair"}` : "never stops"}`, cost: 0,
        undo: () => { const v = s.rail[k]; if (!v) return; for (const f of ["fail", "rec"]) { if (a[f] == null) delete v[f]; else v[f] = clone(a[f]); } } });
    }
    for (const kind of ["stocker", "entry", "exit"]) {
      const b0 = start.blocks.filter((b) => b.kind === kind), b1 = s.blocks.filter((b) => b.kind === kind);
      const add = b1.filter((b) => !b0.some((z) => z.id === b.id)), rem = b0.filter((b) => !b1.some((z) => z.id === b.id));
      if (add.length || rem.length) out.push({ key: `blocks:${kind}`, text: `${INFRA[kind][0]}: ${[add.length && `${add.length} added`, rem.length && `${rem.length} taken away`].filter(Boolean).join(", ")}`, cost: 0,
        undo: () => { const ids = new Set(add.map((b) => b.id)); s.blocks = s.blocks.filter((b) => !ids.has(b.id)); for (const b of rem) s.blocks.push(clone(b)); } });
    }
    if ((s.vehicles || 12) !== (start.vehicles || 12)) out.push({ key: "cars", text: `Cars on the track: ${s.vehicles}`, cost: 0, undo: () => { s.vehicles = start.vehicles || 12; } });
    if ((s.cap || 0) !== (start.cap || 0)) out.push({ key: "cap", text: `Cap on lots inside: ${s.cap ? `${s.cap.toLocaleString()} lots` : "none"}`, cost: 0, undo: () => { if (start.cap) s.cap = start.cap; else delete s.cap; } });
    if ((s.inports || 0) !== (start.inports || 0)) out.push({ key: "ports", text: `Load ports per machine: ${s.inports || "unlimited"}`, cost: 0, undo: () => { if (start.inports) s.inports = start.inports; else delete s.inports; } });
    const o = E.flowOptions(base), f0 = start.flow || {}, f1 = s.flow || {}, str = (v) => (v == null ? "" : String(v));
    for (const k of Object.keys(FLOWNAMES)) {
      if (str(f0[k]) === str(f1[k])) continue;
      const lab = (o[k].find(([v]) => v === str(f1[k])) || [null, str(f1[k])])[1];
      out.push({ key: k, text: `${FLOWNAMES[k]}: ${lab}`, cost: 0, undo: () => { const fl = { ...(s.flow || {}) }; if (f0[k] == null) delete fl[k]; else fl[k] = f0[k]; if (Object.keys(fl).length) s.flow = fl; else delete s.flow; } });
    }
    return out;
  }
  const costWords = (c) => (c > 0 ? money(c) : c < 0 ? `saves ${money(-c)}` : "");
  function renderChanges() {
    const box = $("changes");
    if (!box || !s) return;
    const list = changesOf(), total = list.reduce((a, x) => a + x.cost, 0);
    box.querySelector("summary").innerHTML = list.length ? `Your changes: <b>${list.length}</b>${total ? ` · ${esc(costWords(total))}` : ""}` : "Your changes: none yet";
    box.querySelector("ul").innerHTML = list.map((x, i) => `<li data-chg="${esc(x.key)}"><span>${esc(x.text)}${x.cost ? `, ${esc(costWords(x.cost))}` : ""}</span><button type="button" class="btn" data-undo="${i}" aria-label="Undo: ${esc(x.text)}">Undo</button></li>`).join("");
    box.querySelectorAll("[data-undo]").forEach((bt) => (bt.onclick = () => { list[+bt.dataset.undo].undo(); buildPalette(); refreshCtl(); edited(); }));
    markMoved();
  }
  /** A dot on every control that differs from the start. */
  function markMoved() {
    if (!s || !start) return;
    const list = changesOf(), keys = new Set(list.map((x) => x.key));
    const groupMoved = (g, c) => keys.has(`${c}:${g}`);
    const fabRows = (panel) => panel.querySelectorAll(".ctlrow").forEach((r) => r.classList.toggle("moved", keys.has(r.dataset.ctl)));
    fabRows($("ctl-fab"));
    $("ctl-all").querySelectorAll(".ctlrow").forEach((r) => {
      const [c, id] = (r.dataset.ctl || "").split(/:(.*)/s);
      r.classList.toggle("moved", c === "count" ? ["count", "fail", "rec"].some((x) => groupMoved(id, x)) : keys.has(`rail:${id}`));
    });
    const b = sel && sel.id && s.blocks.find((z) => z.id === sel.id);
    if (b && b.kind === "group") $("insp").querySelectorAll(".ctlrow").forEach((r) => r.classList.toggle("moved", groupMoved(b.group, r.dataset.ctl)));
    else if (sel && sel.rail) {
      const tr = list.find((x) => x.key === "track");
      $("insp").querySelectorAll(".ctlrow").forEach((r) => r.classList.toggle("moved", r.dataset.ctl === "dirs" ? !!(tr && tr.rails.includes(sel.rail)) : keys.has(`rail:${sel.rail}`)));
    } else fabRows($("insp"));
  }

  // find a control
  function findIndex() {
    const out = [];
    const words = (k) => { const t = window.FabGlossary && FabGlossary.TERMS.find((x) => x.term === TERM[k]); return [WHY[k], TERM[k], ...((t && t.aliases) || [])].join(" "); };
    for (const k of Object.keys(FABNAMES)) out.push({ label: FABNAMES[k], where: "Whole fab", words: words(k), go: () => { sel = null; ctlTab("fab"); return k; } });
    const seen = new Set();
    for (const b of s.blocks) {
      if (b.kind !== "group" || seen.has(b.group)) continue;
      seen.add(b.group);
      for (const k of Object.keys(GROUPNAMES)) out.push({ label: `${AREA[b.area][0]}: ${GROUPNAMES[k]}`, where: b.group, words: `${SHORT[b.area]} ${AREA[b.area][2]} ${words(k)}`,
        go: () => { const z = s.blocks.find((y) => y.kind === "group" && y.group === b.group); if (!z) return null; sel = { id: z.id }; ctlTab("sel"); inspector(); return k; } });
    }
    for (const k of Object.keys(s.rail)) if (s.rail[k].fail) for (const c of Object.keys(RAILNAMES))
      out.push({ label: `Track piece ${k.replace(",", ", ")}: ${RAILNAMES[c]}`, where: "Track", words: words(c), go: () => { if (!s.rail[k]) return null; sel = { rail: k }; ctlTab("sel"); inspector(); return c; } });
    return out;
  }
  let found = [];
  function findNow() {
    const q = $("ctl-find").value.trim().toLowerCase(), ul = $("ctl-found");
    if (!q) { found = []; ul.hidden = true; ul.innerHTML = ""; return; }
    const toks = q.split(/\s+/);
    found = findIndex().map((x) => ({ ...x, hay: `${x.label} ${x.where} ${x.words}`.toLowerCase() })).filter((x) => toks.every((t) => x.hay.includes(t)))
      .sort((a, b) => Number(!a.label.toLowerCase().includes(q)) - Number(!b.label.toLowerCase().includes(q))).slice(0, 8);
    ul.hidden = false;
    ul.innerHTML = found.length ? found.map((x, i) => `<li><button type="button" data-find="${i}">${esc(x.label)} <small>${esc(x.where)}</small></button></li>`).join("") : `<li class="none">No control matches “${esc(q)}”.</li>`;
  }
  function goFound(i) { const x = found[i]; if (!x) return; const k = x.go(); if (k) { draw(); light(k); } }

  // the glossary card
  function glCard(term, from) {
    const t = window.FabGlossary && FabGlossary.TERMS.find((x) => x.term === term), c = $("glcard");
    if (!t || !c) return;
    const fig = t.figure && window.FabGlossaryFigs && FabGlossaryFigs.FIGS[t.figure];
    c.innerHTML = `<button type="button" class="btn gl-x" aria-label="Close">✕</button><div class="gl-lead"><img src="${esc(t.picture)}" alt="" width="72" height="72"><div><h4>${esc(t.term)}</h4><p class="gl-plain">${esc(t.plain || t.meaning)}</p></div></div>` +
      (fig ? `<figure class="gl-fig">${FabGlossaryFigs.draw(t.figure)}<figcaption>${esc(fig.caption)}</figcaption></figure>` : "") +
      `<p class="note">${esc(t.here)}</p><a href="index.html?term=${encodeURIComponent(t.term)}" target="_blank" rel="noopener">The full entry on the Floor →</a>`;
    c.hidden = false;
    const r = from.getBoundingClientRect(), w = c.offsetWidth, h = c.offsetHeight;
    c.style.left = `${Math.max(8, Math.min(r.right - w, innerWidth - w - 8))}px`;
    c.style.top = `${Math.max(8, Math.min(r.bottom + 6, innerHeight - h - 8))}px`;
    c.querySelector(".gl-x").onclick = () => (c.hidden = true);
  }
  document.addEventListener("click", (e) => {
    const q = e.target.closest(".gl-q");
    if (q) { e.preventDefault(); glCard(q.dataset.term, q); return; }
    const c = $("glcard");
    if (c && !c.hidden && !e.target.closest("#glcard")) c.hidden = true;
  });

  // ---------- your levers (docs/BUILD-CONTROLS.md): what the challenge lets you change, each opening its control
  function leversOf(c) {
    if (!c) return [];
    const out = [];
    if (c.spot && c.spot.rail) out.push({ label: "The broken track: when it stops", go: () => {
      const k = Object.keys(s.rail).find((x) => s.rail[x].fail); if (!k) return null; sel = { rail: k }; ctlTab("sel"); inspector(); return "rrec"; } });
    if (c.spot && c.spot.group) {
      const g = c.spot.group, a = areaOfGroup[g] || (s.blocks.find((b) => b.group === g) || {}).area, nm = AREA[a][0];
      const pick = () => { const b = s.blocks.find((z) => z.kind === "group" && z.group === g); if (!b) return false; sel = { id: b.id }; ctlTab("sel"); inspector(); return true; };
      out.push({ label: `${nm} machines (${money(E.PRICE[a])} each)`, kind: a, go: () => (pick() ? "count" : null) });
      out.push({ label: `${nm}: when it breaks`, kind: a, go: () => (pick() ? "rec" : null) });
    }
    if (c.tip) out.push({ label: "Cap on lots inside", go: () => { ctlTab("fab"); return "cap"; } });
    return out;
  }
  let litTimer = null;
  function light(key) {
    document.querySelectorAll(".ctlrow.lit").forEach((e) => e.classList.remove("lit"));
    const panel = ctlTabNow === "sel" ? $("insp") : ctlTabNow === "fab" ? $("ctl-fab") : $("ctl-all");
    const el = panel.querySelector(`.ctlrow[data-ctl="${key}"]`);
    if (!el) return;
    el.classList.add("lit");
    el.scrollIntoView({ block: "nearest" });
    clearTimeout(litTimer); litTimer = setTimeout(() => el.classList.remove("lit"), 4000);
  }
  function renderLevers() {
    const lv = leversOf(ch()), box = $("levers");
    box.hidden = !lv.length;
    box.innerHTML = lv.length ? `<span class="lv-h">Your levers:</span>` + lv.map((l, i) => `<button class="btn lever" data-lv="${i}">${esc(l.label)}</button>`).join("") : "";
    box.querySelectorAll("[data-lv]").forEach((bt) => (bt.onclick = () => { const k = lv[+bt.dataset.lv].go(); if (k) { draw(); light(k); } }));
  }

  // ---------- the process (docs/BUILD-CONTROLS.md): the teaching fab's one product, step by step
  function renderProcess() {
    const steps = E.TEACHING_SHOP.split("\n").filter((l) => l.startsWith("step\t")).map((l) => { const f = l.split("\t"); return [E.AREA_OF[f[1].replace(/_T$/, "")] || areaOfGroup[f[1]], Number(f[3])]; });
    $("process").innerHTML = steps.map(([a, m], i) => `<li><img src="cast/base/${String(E.AREAS.indexOf(a) + 1).padStart(2, "0")}-${a}.webp" alt="" width="28" height="28"><span class="nm">${esc(AREA[a][0])}</span><span class="mn">${m} min</span></li>`).join("");
  }

  // ---------- checks
  // one-click fixes for what the checks find (docs/BUILD-CONTROLS.md, part 8); run() changes the floor, or says why not
  function fixFor(i) {
    const nodeKey = (n) => { const c = E.cellOfNode(n); return c ? E.key(c[0], c[1]) : null; };
    const viaRoute = (from, to) => { const r = E.route(s, from, to); if (!r.ok) return r.why; applyRoute(r); return ""; };
    if (i.code === "missing_stops") return { label: "Move it beside the track", run: () => {
      const bs = s.blocks.filter((b) => b.kind === "group" && b.group === i.at[0] && !E.beside(s, b).length);
      for (const b of bs) {
        const rest = { ...s, blocks: s.blocks.filter((z) => z !== b) }, sp = E.snapBeside(rest, b.x, b.y, b.w, b.h, Math.max(s.W, s.H));
        if (!sp) return "There is no free spot beside the track for it.";
        b.x = sp[0]; b.y = sp[1];
      }
      return "";
    } };
    if (i.code === "unreachable") { const n = nodeKey(i.at[1]); return n && { label: "Connect it", run: () => viaRoute(E.reach(s).fromEntry, n) }; }
    if (i.code === "no_way_out") { const n = nodeKey(i.at[1]); return n && { label: "Connect it onward", run: () => viaRoute(n, E.reach(s).toExit) }; }
    if (i.code === "trap") return { label: "Connect it onward", run: () => {
      const traps = i.at.map(nodeKey).filter(Boolean), sinks = traps.filter((t2) => { const [x, y] = t2.split(",").map(Number); return !s.rail[t2].o.some((on, d) => on && s.rail[E.key(x + D[d][0], y + D[d][1])]); });
      return viaRoute(sinks.length ? sinks : traps, E.reach(s).toExit);
    } };
    if (i.code === "no_storage") return { label: "Place storage", run: () => {
      const sp = E.snapBeside(s, Math.floor(s.W / 2) - 1, Math.floor(s.H / 2) - 1, 2, 2, Math.max(s.W, s.H));
      if (!sp) return "There is no free spot beside the track for storage.";
      s.blocks.push({ id: Math.max(0, ...s.blocks.map((b) => b.id)) + 1, kind: "stocker", x: sp[0], y: sp[1], w: 2, h: 2 });
      return "";
    } };
    if (i.code === "holds_without_rework") return { label: "Set rework", run: () => {
      const fl = { ...(s.flow || {}) };
      if (E.flowKind(base).rework) delete fl.rework; else fl.rework = "p0.01";
      s.flow = fl; return "";
    } };
    return null;
  }
  function renderChecks() {
    const ul = $("issues");
    if (!checks) { ul.innerHTML = '<li><span class="chip warning">…</span><span>Checking the layout.</span></li>'; $("verdict").innerHTML = ""; return; }
    if (checks.error) { ul.innerHTML = `<li><span class="chip error">refused</span><span>${esc(checks.error)}</span></li>`; $("verdict").innerHTML = '<span class="chip error">refused</span>'; return; }
    const errs = checks.issues.filter((i) => i.severity === "error").length;
    $("verdict").innerHTML = errs ? `<span class="chip error">${errs} to fix</span>` : '<span class="chip ok">complete</span>';
    ul.innerHTML = checks.issues.length
      ? checks.issues.map((i, n) => `<li data-n="${n}"><span class="chip ${i.severity}">${i.severity === "error" ? "fix" : "note"}</span><span>${esc(i.message)}${fixFor(i) ? ` <button type="button" class="btn fixbtn" data-fix="${n}">${esc(fixFor(i).label)}</button>` : ""}</span></li>`).join("")
      : '<li><span class="chip ok">ok</span><span>Complete and connected: every machine is on the track, and wafers can get from the way in to every machine and out again.</span></li>';
    ul.querySelectorAll("[data-fix]").forEach((bt) => (bt.onclick = (e) => {
      e.stopPropagation();
      const f = fixFor(checks.issues[+bt.dataset.fix]);
      if (!f) return;
      const why = f.run();
      if (why) { $("status").textContent = why; return; }
      buildPalette(); refreshCtl(); edited();
    }));
    ul.querySelectorAll("li[data-n]").forEach((li) => (li.onclick = () => {
      const i = checks.issues[+li.dataset.n];
      const at = i.at.map((a) => E.cellOfNode(a)).find(Boolean) || (() => { const b = s.blocks.find((z) => i.at.includes(z.group) || i.at.some((a) => z.group && a.startsWith(z.group + "#"))); return b ? [b.x, b.y] : null; })();
      if (at) { flash = at; draw(); setTimeout(() => { flash = null; draw(); }, 1400); }
    }));
  }

  // ---------- controls
  $("play").onclick = () => { if (stale) return runNow(); playing = !playing; if (playing && mode === "build") setMode("run"); playBtn(); };
  function setJamMap(on) { jamMap = on; $("jammap").setAttribute("aria-pressed", String(on)); draw(); }
  $("jammap").onclick = () => setJamMap(!jamMap);
  // one speed button, the floor's steps: 1×, 3×, 12× are 20, 60, 240 fab minutes a real second; Max one fab hour a frame
  $("speed").onclick = () => {
    const SP = [[20, "1×"], [60, "3×"], [240, "12×"], [MAX, "Max"]], i = SP.findIndex((x) => x[0] === speed), n = SP[(i + 1) % SP.length];
    const wasMax = speed === MAX;
    speed = n[0]; $("speed").textContent = n[1];
    if (wasMax && run) jumpTo(Math.min(clock, days() * 1440 - WINDOW)); // the cars' window is stale after Max
  };
  $("again").onclick = () => runNow();
  document.body.appendChild($("hover")); // out of the map's box, which would cut it (part 6)
  $("pal").addEventListener("pointerover", (e) => { const bt = e.target.closest("[data-kind]"); if (bt) palCard(bt); });
  $("pal").addEventListener("pointerout", (e) => { const bt = e.target.closest("[data-kind]"); if (bt && !bt.contains(e.relatedTarget)) palCard(null); });
  $("pal").addEventListener("focusin", (e) => { const bt = e.target.closest("[data-kind]"); if (bt) palCard(bt); });
  $("pal").addEventListener("focusout", () => palCard(null));
  $("heal").onclick = () => {
    if (!healGaps) return;
    const h = E.heal(s, healGaps);
    if (!h.ok) { $("status").textContent = h.why; return; }
    useState(h.state); healGaps = null; buildPalette(); inspector(); edited();
    $("status").textContent = `Reconnected around the cut with ${h.paths.reduce((a, p) => a + p.length - 2, 0)} new track pieces.`;
  };
  $("gears").onclick = () => { gearsBtn = !gearsBtn; $("gears").setAttribute("aria-pressed", String(gearsBtn)); draw(); };
  $("ctl-find").addEventListener("input", findNow);
  $("ctl-find").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); goFound(0); }
    if (e.key === "Escape") { $("ctl-find").value = ""; findNow(); $("ctl-find").blur(); }
  });
  $("ctl-found").addEventListener("click", (e) => { const bt = e.target.closest("[data-find]"); if (bt) goFound(+bt.dataset.find); });
  $("showfix").onclick = () => load(chIdx, true);
  $("template").onchange = () => load(E.CHALLENGES.length);
  $("slider").oninput = () => { if (!run) return; const t = run.frames[+$("slider").value].t; lastHour = -1; jumpTo(Math.min(t, days() * 1440 - WINDOW)); };
  document.addEventListener("keyup", (e) => {
    if (e.key.toLowerCase() === "h" && showLast) { showLast = false; $("lastrun").hidden = true; draw(); }
    if (e.key.toLowerCase() === "g" && gHeld) { gHeld = false; draw(); }
    if (e.key === " " && spaceHeld) { spaceHeld = false; if (!spacePanned) $("play").click(); spacePanned = false; }
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("select,input,textarea")) return;
    const k = e.key.toLowerCase(), m = { v: "select", b: "rail", e: "erase", t: "route" };
    if (e.metaKey || e.ctrlKey) {
      if (k === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
      else if (k === "y") { e.preventDefault(); redo(); }
      else if (k === "a") { e.preventDefault(); boxSel = { blocks: s.blocks.map((b) => b.id), rails: Object.keys(s.rail) }; sel = null; ctlTab("sel"); inspector(); selStatus(); draw(); }
      else if (k === "d" && boxSel) { e.preventDefault(); clip = E.copySel(s, boxSel); if (clip) { tool = "select"; syncPal(); pasting = true; ghostAt = null; $("status").textContent = "A copy in hand: click where it should go. Esc drops it."; draw(); } }
      else if (k === "c" && boxSel) { e.preventDefault(); clip = E.copySel(s, boxSel); $("status").textContent = clip ? "Copied. ⌘V takes it in hand." : ""; }
      else if (k === "v" && clip) { e.preventDefault(); tool = "select"; syncPal(); pasting = true; ghostAt = null; $("status").textContent = "Point where the copy should go and click. Esc drops it."; draw(); }
      return;
    }
    if (/^[1-9]$/.test(k)) { take(E.hotbar(recent)[+k - 1]); return; }
    if (k === "q") {
      if (hover) { const t = E.pickAt(s, hover[0], hover[1]); if (!take(t) && t !== "select") take("select"); }
      return;
    }
    if (k === "r" && boxSel && !pasting) { actSel(E.turnSel(s, boxSel, e.shiftKey)); return; }
    const nudge = { arrowup: [0, -1], arrowdown: [0, 1], arrowleft: [-1, 0], arrowright: [1, 0] }[k];
    if (nudge && boxSel) { e.preventDefault(); actSel(E.moveSel(s, boxSel, nudge[0], nudge[1])); return; }
    if (k === "r" && ["entry", "exit"].includes(placeKind())) {
      handTurned = !handTurned;
      if (ghostAt && ghostAt.kind === placeKind()) { const [gw, gh] = handDims(ghostAt.kind), f = E.isFree(s, ghostAt.x, ghostAt.y, gw, gh); ghostAt = { ...ghostAt, w: gw, h: gh, ok: f.ok, why: f.why }; }
      draw(); return;
    }
    if (k === "r" && sel && sel.id) {
      const b = s.blocks.find((z) => z.id === sel.id);
      if (b) {
        const t = E.turn(b.kind, b.w, b.h);
        if (!t.changed) $("status").textContent = "A square piece looks and works the same turned: it serves the track on every side.";
        else { const f = E.isFree(s, b.x, b.y, t.w, t.h, b.id); if (f.ok) { b.w = t.w; b.h = t.h; inspector(); edited(); } else $("status").textContent = `It cannot turn here: ${f.why.toLowerCase()}`; }
      }
      return;
    }
    if ((k === "delete" || k === "backspace") && boxSel) { deleteSelection("all"); return; }
    if (k === "escape") { pasting = false; boxSel = null; ghostAt = null; routeFrom = null; routePlan = null; $("win").hidden = true; }
    if (k === " ") { e.preventDefault(); if (!e.repeat) { spaceHeld = true; spacePanned = false; } return; }
    if (k === "j") { setJamMap(!jamMap); return; }
    if (k === "g") { if (!e.repeat) { gHeld = true; draw(); } return; }
    if (e.key === "/") { e.preventDefault(); $("ctl-find").focus(); return; }
    if (k === "h") { if (!e.repeat) { showLast = true; $("lastrun").textContent = prevRun ? "Dashed purple: the jams of your last run" : "No earlier run yet"; $("lastrun").hidden = false; draw(); } return; }
    if (k === "f") { V = null; draw(); return; }
    const step = 40, dirs = { w: [0, step], arrowup: [0, step], s: [0, -step], arrowdown: [0, -step], a: [step, 0], arrowleft: [step, 0], d: [-step, 0], arrowright: [-step, 0] };
    if (dirs[k]) { e.preventDefault(); pan(dirs[k][0], dirs[k][1]); return; }
    if (m[k]) take(m[k]);
    if (k === "r" && sel && sel.rail && s.rail[sel.rail]) { const v = s.rail[sel.rail]; v.o = [v.o[3], v.o[0], v.o[1], v.o[2]]; inspector(); edited(); }
    if ((k === "delete" || k === "backspace") && sel && sel.id) { s.blocks = s.blocks.filter((b) => b.id !== sel.id); sel = null; buildPalette(); inspector(); edited(); }
    if (k === "escape") { if (tool !== "select") take("select"); sel = null; inspector(); draw(); }
  });

  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.1, (ts - (last || ts)) / 1000);
    last = ts;
    if (playing && !document.hidden && run && (win || speed === MAX)) { advance(dt); tickUi(); draw(); }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
  let rt;
  window.addEventListener("resize", () => { $("glcard").hidden = true; clearTimeout(rt); rt = setTimeout(() => { V = null; room = null; draw(); }, 80); });
  // the fonts change the banner's height, so the map measures its room again once they are in
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { room = null; if (s) draw(); });
  // for page tests: where a floor cell's centre is on screen, and the map's state (read only)
  window.FabEditorPage = {
    screenOf(x, y, z) { const r = cv.getBoundingClientRect(), p = P(x + 0.5, y + 0.5, z || 0); return [r.left + p[0], r.top + p[1]]; },
    blocks: () => s.blocks.map((b) => ({ ...b })),
    fab: () => fab(),
    // for the placing tests (docs/BUILD-CONTROLS.md, part 2): free machine spots beside the track, a selection, spend, overrides, checks
    freeBeside: (w, h) => { for (let y = 0; y < s.H; y++) for (let x = 0; x < s.W; x++) if (free(x, y, w, h) && E.isFree(s, x, y, w, h).ok && beside(x, y, w, h)) return [x, y]; return null; },
    freeRowBeside: (n) => {
      const [w, h] = handDims("group");
      for (let y = 0; y < s.H; y++) for (let x = 0; x < s.W; x++) {
        for (const [dx, dy] of [[w, 0], [0, h]]) { // along the track either way
          const row = Array.from({ length: n }, (_, i) => [x + i * dx, y + i * dy]);
          if (row.every(([a, c]) => free(a, c, w, h) && beside(a, c, w, h))) return row;
        }
      }
      return null;
    },
    select: (id) => { sel = { id }; ctlTab("sel"); inspector(); draw(); return true; },
    spend: () => E.spend(s),
    overrides: () => E.overridesFor(s),
    checks: () => checks,
    experiment: () => experiment(),
    starsNow: () => (run && run.score && ch() ? starsFor(run.score, ch(), run.spendTop) : null),
    breaks: () => Object.keys(s.rail).filter((k) => s.rail[k].fail),
    // part 5: gears, the selection, a track piece selected
    gears: () => lastGears.map((g) => ({ ...g })),
    // part 7: the floor as it stands (read only), and whether a copy is in hand
    snapshot: () => JSON.parse(JSON.stringify(s)),
    pasting: () => !!pasting,
    selected: () => (sel ? { ...sel } : null),
    selectRail: (k) => { sel = { rail: k }; ctlTab("sel"); inspector(); draw(); return true; },
    // the editor's basics (docs/EDITOR-BASICS.md)
    view: () => viewNow(),
    ghost: () => (ghostAt ? { ...ghostAt } : null),
    rails: () => Object.keys(s.rail).length,
    runs: () => runsDone,
    tileLabels: () => lastLabels.slice(),
    watching: () => watch,
    showsRun: () => !!showRun(),
    clock: () => clock,
    cars: () => lastCars,
    railAt: (x, y) => { const v = s.rail[E.key(x, y)]; return v ? JSON.parse(JSON.stringify(v)) : null; },
    cursor: () => (cursorCell ? [...cursorCell] : null),
    badges: () => lastBadges.map((b) => ({ ...b })),
    groupsNow: () => (run ? s.blocks.filter((b) => b.kind === "group").map((b) => { const gi = run.group_names.indexOf(b.group), q = gi >= 0 ? run.frames[lastDrawFi].queues[gi] : 0, mood = E.blockMood(run, lastDrawFi, b.group); return { group: b.group, mood, queue: q, trouble: E.trouble(mood, q) }; }) : []),
    jamMap: () => jamMap,
    spot: () => { const p = spotNow(); return p ? (p.rail ? { rail: p.rail } : { group: p.group }) : null; },
    showingLast: () => showLast,
    canUndo: () => hist.canUndo(),
    canRedo: () => hist.canRedo(),
    // the foreman keys (docs/EDITOR-MOVES.md)
    tool: () => tool,
    size: () => [s.W, s.H],
    railKeys: () => Object.keys(s.rail),
    selection: () => (boxSel ? { blocks: boxSel.blocks.slice(), rails: boxSel.rails.slice() } : { blocks: [], rails: [] }),
    hotbar: () => E.hotbar(recent),
    clipboard: () => (clip ? JSON.parse(JSON.stringify(clip)) : null),
    // the first spot that is free and can be pointed at: every cell's middle picks that cell, not a block drawn in front
    firstFree(w, h) {
      const r = cv.getBoundingClientRect();
      const picks = (x, y) => { const p = P(x + 0.5, y + 0.5); const c = cellOf({ clientX: r.left + p[0], clientY: r.top + p[1] }); return c[0] === x && c[1] === y; };
      for (let y = 0; y < s.H; y++) {
        for (let x = 0; x < s.W; x++) {
          if (!E.isFree(s, x, y, w, h).ok) continue;
          let ok = true;
          for (let i = 0; i < w && ok; i++) for (let j = 0; j < h && ok; j++) ok = picks(x + i, y + j);
          if (ok) return [x, y];
        }
      }
      return null;
    },
  };
  // a challenge from the address: editor.html?ch=N, N from 1 (docs/HOME-REVIEW.md)
  {
    const a = new URLSearchParams(location.search), q = Number(a.get("ch")), rid = a.get("run");
    if (rid && /^B-\d{4,}$/.test(rid)) {
      // a kept Build run (docs/RUNS.md, part 3): its layout opens as Free build
      fetch(`/api/job/${rid}`).then((r) => (r.ok ? r.json() : null)).then((j) => {
        const rec = j && j.record;
        if (!rec || !rec.state) { load(0); return; }
        $("template").value = rec.template === "smt2020" ? "smt2020" : "teaching";
        load(E.CHALLENGES.length, false, rec).then(() => { $("status").textContent = `Opened ${rid}: ${rec.title || "a Build run"}, as Free build.`; });
      }).catch(() => load(0));
    } else load(Number.isInteger(q) && q >= 1 && q <= E.CHALLENGES.length ? q - 1 : 0);
  }
})();
