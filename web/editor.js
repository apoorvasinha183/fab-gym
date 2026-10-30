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
  const INFRA = { stocker: ["Stocker", "Holds lots between steps when a tool's ports are full."], entry: ["Wafer start", "New lots enter the fab here."], exit: ["Ship point", "Finished lots leave here."] };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const money = (d) => (Math.abs(d) >= 1e6 ? `$${(d / 1e6).toFixed(d % 1e6 ? 1 : 0)}M` : `$${Math.round(d).toLocaleString()}`);

  // ---------- state
  let chIdx = 0; // 0..3 a challenge, 4 free build
  let setupNow = null, base = E.TEACHING_SHOP, s = null, spend0 = 0, areaOfGroup = {};
  let run = null, prev = null, stale = false, running = false;
  let mode = "run", playing = !matchMedia("(prefers-reduced-motion: reduce)").matches, speed = 60;
  let clock = 0, win = null, nextWin = null, fetching = false;
  let tool = "select", sel = null, hover = null, drag = null, flash = null, checks = null, checkTimer = null;
  const met = new Set();
  try { for (const id of JSON.parse(localStorage.getItem("fabgym.met") || "[]")) met.add(id); } catch (e) { /* no storage */ }
  const ch = () => (chIdx < E.CHALLENGES.length ? E.CHALLENGES[chIdx] : null);
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

  // ---------- the 2.5D floor
  const ISO = { r: -0.36, q: 0.5, pad: 0.03 };
  const cv = $("map"), ctx = cv.getContext("2d");
  let F = null;
  function fit(cw) {
    const co = Math.cos(ISO.r), sn = Math.sin(ISO.r);
    const pts = [[0, 0], [s.W, 0], [0, s.H], [s.W, s.H]].map(([x, y]) => [x * co - y * sn, (x * sn + y * co) * ISO.q]);
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const pad = cw * ISO.pad, sc = (cw - 2 * pad) / (Math.max(...xs) - Math.min(...xs));
    const lift = sc * 1.6, depth = sc * 0.7;
    return { s: sc, co, sn, ox: pad - Math.min(...xs) * sc, oy: pad + lift - Math.min(...ys) * sc, ch: (Math.max(...ys) - Math.min(...ys)) * sc + 2 * pad + lift + depth, depth };
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
    F = fit(cw);
    cv.width = Math.round(cw * dpr); cv.height = Math.round(F.ch * dpr); cv.style.height = F.ch + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const g = ctx.createRadialGradient(cw / 2, F.ch * 0.45, 10, cw / 2, F.ch * 0.45, cw * 0.7);
    g.addColorStop(0, "#16323A"); g.addColorStop(0.6, "#0B1418"); g.addColorStop(1, "#070C0F");
    ctx.fillStyle = g; ctx.fillRect(0, 0, cw, F.ch);
    const slab = [P(0, 0), P(s.W, 0), P(s.W, s.H), P(0, s.H)];
    ctx.save(); ctx.translate(0, F.depth); poly(slab); ctx.fillStyle = "#071013"; ctx.fill(); ctx.restore();
    poly(slab); ctx.fillStyle = "#0F1D22"; ctx.fill(); ctx.strokeStyle = "rgba(126,232,216,.5)"; ctx.lineWidth = 1.2; ctx.stroke();
    ctx.strokeStyle = "rgba(126,232,216,0.05)"; ctx.beginPath();
    for (let x = 0; x <= s.W; x += 5) { const a = P(x, 0), b = P(x, s.H); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
    for (let y = 0; y <= s.H; y += 5) { const a = P(0, y), b = P(s.W, y); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
    ctx.stroke();
    const fi = frameIdx(), fr = showRun() ? run.frames[fi] : null;
    const jam = {};
    if (fr) run.stretches.forEach((n, i) => (jam[n] = fr.rails[i]));
    const bad = new Set((checks && checks.issues ? checks.issues : []).filter((i) => i.severity === "error").flatMap((i) => i.at));
    // rail
    const breaks = [];
    for (const k of Object.keys(s.rail)) {
      const [x, y] = k.split(",").map(Number), v = s.rail[k];
      v.o.forEach((on, d) => {
        if (!on) return;
        const live = !!s.rail[E.key(x + D[d][0], y + D[d][1])];
        const a = P(x + 0.5, y + 0.5, 0.06), b = P(x + 0.5 + D[d][0] * (live ? 1 : 0.45), y + 0.5 + D[d][1] * (live ? 1 : 0.45), 0.06);
        const j = jam[`c${x}_${y}>c${x + D[d][0]}_${y + D[d][1]}`] || 0;
        ctx.strokeStyle = bad.has(`c${x}_${y}`) ? "#FF6B57" : j > 1 ? "#FF6B57" : j > 0.2 ? "#F2B33D" : v.spine ? "#2F6470" : "#285059";
        ctx.lineWidth = Math.max(2, F.s * 0.3); ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
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
    const vs = showRun() && win ? vehicles(clock) : [];
    for (const v of vs) items.push({ v, d: P(v.x + 0.5, v.y + 0.5)[1] });
    items.sort((a, b) => a.d - b.d);
    const labels = [];
    for (const it of items) {
      if (it.v) { drawVehicle(it.v); continue; }
      const b = it.b, col = b.kind === "group" ? FAM[b.area] || "#8FB3AE" : b.kind === "stocker" ? "#8FB3AE" : "#7EE8D8";
      const tall = b.kind === "group" ? (b.area === "litho" ? 1.05 : b.area === "diff" ? 1.15 : 0.75) : b.kind === "stocker" ? 0.9 : 0.35;
      const i = 0.14;
      const bs = [P(b.x + i, b.y + i), P(b.x + b.w - i, b.y + i), P(b.x + b.w - i, b.y + b.h - i), P(b.x + i, b.y + b.h - i)];
      const tp = bs.map((p) => [p[0], p[1] - tall * F.s]);
      prism(bs, tp, "#26343B", "#33434B");
      const cx = tp.reduce((a, p) => a + p[0], 0) / 4, cy = tp.reduce((a, p) => a + p[1], 0) / 4;
      const inner = tp.map((p) => [cx + (p[0] - cx) * 0.72, cy + (p[1] - cy) * 0.72]);
      poly(inner); ctx.fillStyle = col; ctx.globalAlpha = 0.92; ctx.fill(); ctx.globalAlpha = 1;
      if (b.area === "litho") { ctx.save(); ctx.shadowColor = col; ctx.shadowBlur = 14; poly(inner); ctx.fill(); ctx.restore(); }
      const ic = b.kind === "group" ? b.area : b.kind;
      if (IC[ic]) icon(ic, cx, cy, Math.max(10, F.s * 0.95), "#0B1418", 2);
      let q = 0;
      if (b.kind === "group" && fr) { const gi = run.group_names.indexOf(b.group); q = gi >= 0 ? fr.queues[gi] : 0; }
      if (b.kind === "group") labels.push([`${SHORT[b.area] || b.group} ×${b.count}`, cx, bs.reduce((a, p) => (p[1] > a[1] ? p : a), bs[0])[1] + 3, q]);
      if (b.kind === "group" && fr) {
        const mood = E.blockMood(run, fi, b.group);
        if (mood) {
          const tr = tp.reduce((a, p) => (p[0] - p[1] > a[0] - a[1] ? p : a), tp[0]), r = Math.max(5, F.s * 0.36);
          ctx.fillStyle = MOOD[mood][1]; ctx.beginPath(); ctx.arc(tr[0], tr[1], r, 0, 7); ctx.fill(); ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.5; ctx.stroke();
          icon(MOOD[mood][2], tr[0], tr[1], r * 1.35, "#15191C", 2.2);
        }
      }
      if (b.kind === "group" && (b.fail || b.rec)) { const bl = tp.reduce((a, p) => (p[0] < a[0] ? p : a), tp[0]); ctx.fillStyle = "#FF4D4F"; ctx.beginPath(); ctx.arc(bl[0], bl[1], Math.max(4, F.s * 0.28), 0, 7); ctx.fill(); icon("bolt", bl[0], bl[1], Math.max(7, F.s * 0.4), "#1B1E22", 2); }
      if (b.kind === "group" && (bad.has(b.group) || [...bad].some((a) => typeof a === "string" && a.startsWith(b.group + "#")))) { ctx.save(); ctx.setLineDash([5, 4]); ctx.strokeStyle = "#FF6B57"; ctx.lineWidth = 2; poly(tp); ctx.stroke(); ctx.restore(); }
      if (sel && sel.id === b.id) { ctx.strokeStyle = "#7EE8D8"; ctx.lineWidth = 2.2; poly(tp); ctx.stroke(); }
    }
    // labels last, on a dark pill, so blocks in front never cut them
    ctx.font = `600 ${Math.max(9, Math.round(F.s * 0.36))}px "Chakra Petch",sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const [t, x, y, q] of labels) {
      const w = ctx.measureText(t).width + 8, h = Math.max(13, F.s * 0.5);
      ctx.fillStyle = "rgba(7,16,19,.8)"; ctx.beginPath(); ctx.roundRect(x - w / 2, y, w, h, 4); ctx.fill();
      ctx.fillStyle = "#CFE3E0"; ctx.fillText(t, x, y + h / 2 + 0.5);
      if (q) pods(x, y + h + 2, q, h);
    }
    // a stretch set to break: a red bolt over it
    for (const c of breaks) { ctx.fillStyle = "#FF4D4F"; ctx.beginPath(); ctx.arc(c[0], c[1] - F.s * 0.35, Math.max(6, F.s * 0.38), 0, 7); ctx.fill(); ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1.5; ctx.stroke(); icon("bolt", c[0], c[1] - F.s * 0.35, Math.max(9, F.s * 0.52), "#1B1E22", 2); }
    if (flash) { const p = P(flash[0] + 0.5, flash[1] + 0.5); ctx.strokeStyle = "#FF6B57"; ctx.lineWidth = 3; ctx.beginPath(); ctx.ellipse(p[0], p[1], F.s * 1.8, F.s * 0.9, 0, 0, 7); ctx.stroke(); }
    if (hover && mode === "build" && ["group", "stocker", "entry", "exit"].includes(placeKind())) {
      const [w, h] = placeKind() === "entry" || placeKind() === "exit" ? [1, 2] : [2, 2];
      poly([P(hover[0], hover[1]), P(hover[0] + w, hover[1]), P(hover[0] + w, hover[1] + h), P(hover[0], hover[1] + h)]);
      ctx.fillStyle = free(hover[0], hover[1], w, h) ? "rgba(126,232,216,.3)" : "rgba(255,107,87,.35)"; ctx.fill();
    }
    if (stale) {
      ctx.font = '600 14px "Chakra Petch",sans-serif'; ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = "#F2B33D";
      ctx.fillText(running ? "Running the simulator on your layout…" : "Edited. Run again to see it move.", 12, 10);
    }
  }

  /** Lots waiting at a group: a row of pods under its label, the eighth and on as a count. */
  function pods(x, y, n, h) {
    const k = Math.min(n, 8), pw = Math.max(6, h * 0.55), ph = Math.max(5, h * 0.45), gap = 2;
    const more = n > k ? `+${n - k}` : "";
    ctx.font = `700 ${Math.max(9, Math.round(h * 0.7))}px "IBM Plex Mono",monospace`;
    const tw = more ? ctx.measureText(more).width + 4 : 0, W = k * (pw + gap) - gap + tw + 8;
    ctx.fillStyle = "rgba(7,16,19,.8)"; ctx.beginPath(); ctx.roundRect(x - W / 2, y, W, ph + 6, 4); ctx.fill();
    let px = x - W / 2 + 4;
    for (let i = 0; i < k; i++, px += pw + gap) {
      ctx.fillStyle = n >= 8 ? "#FFB020" : "#F4E7C6"; ctx.fillRect(px, y + 3, pw, ph);
      ctx.strokeStyle = "#0B1418"; ctx.lineWidth = 1; ctx.strokeRect(px, y + 3, pw, ph);
    }
    if (more) { ctx.fillStyle = "#FFB020"; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(more, px + 2, y + 3 + ph / 2 + 0.5); ctx.textAlign = "center"; }
    ctx.font = `600 ${Math.max(9, Math.round(F.s * 0.36))}px "Chakra Petch",sans-serif`;
  }

  function drawVehicle(v) {
    const z = 0.38, i = 0.2, x = v.x, y = v.y;
    const bs = [P(x + i, y + i, 0.1), P(x + 1 - i, y + i, 0.1), P(x + 1 - i, y + 1 - i, 0.1), P(x + i, y + 1 - i, 0.1)];
    const tp = bs.map((p) => [p[0], p[1] - z * F.s]);
    ctx.save();
    if (v.loaded) { ctx.shadowColor = v.hot ? "#FF8A4C" : "#F2B33D"; ctx.shadowBlur = 10; }
    prism(bs, tp, v.hot ? "#B4532A" : v.loaded ? "#9C7A22" : "#4A5961", v.hot ? "#FF8A4C" : v.loaded ? "#F2B33D" : "#8A9AA2");
    ctx.restore();
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
  async function fetchWindow(from) {
    const r = await post("/api/fab/replay", { fab: fab(), seed: 1, start: from, minutes: WINDOW, overrides: E.overridesFor(s) });
    if (r.error) return null;
    return { from: r.from, to: r.to, by: index(r.stays) };
  }
  async function jumpTo(t) {
    clock = t; win = null; nextWin = null; fetching = true; tickUi(); draw();
    const w = await fetchWindow(t);
    fetching = false;
    if (w && Math.abs(w.from - clock) < 1e-6) { win = w; draw(); }
  }
  function advance(dt) {
    if (!win || fetching) return;
    const end = days() * 1440;
    clock += (dt * speed) / 60;
    if (!nextWin && !fetching && clock > win.from + 0.6 * WINDOW && win.to < end) {
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
  async function runNow() {
    running = true; stale = true; $("again").disabled = true; $("again").textContent = "Running…"; $("goaltext").textContent = "Running the simulator…"; draw();
    const r = await post("/api/fab/run", { fab: fab(), seed: 1, days: days(), every: 60, overrides: E.overridesFor(s) });
    running = false; $("again").disabled = false; $("again").textContent = "Run again with my changes";
    if (r.checks) { checks = r.checks; renderChecks(); }
    if (r.error) { if (!r.checks || r.checks.ok) { checks = { error: r.error }; renderChecks(); } $("goaltext").textContent = r.error; draw(); return; }
    if (run) prev = { ...run.score, spend: run.spendTop };
    run = r.moods; run.every = 60; run.spendTop = E.spend(s) - spend0;
    stale = false;
    const c = ch();
    if (c && E.meets(run.score, c.target, run.spendTop)) { met.add(c.id); try { localStorage.setItem("fabgym.met", JSON.stringify([...met])); } catch (e) { /* no storage */ } }
    $("slider").max = run.frames.length - 1;
    renderTabs(); renderScore(); setMode("run");
    await jumpTo(startTime());
  }

  function renderScore() {
    const c = ch(), sc = run ? run.score : null, p = prev;
    const card = (k, n, unit, cur, was, better, bad) => {
      let dl = '<span class="dl">first run</span>';
      if (p && was != null && cur != null) {
        const d = cur - was;
        dl = Math.abs(d) < 1e-9 ? '<span class="dl">same as last run</span>' : `<span class="dl ${better(d) ? "good" : "bad"}">${d > 0 ? "+" : ""}${Number.isInteger(d) ? d.toLocaleString() : d.toFixed(2)} vs last run</span>`;
      }
      return `<div class="sc${bad ? " bad" : ""}${stale ? " stale" : ""}"><span class="k">${k}</span><span class="n">${n}${unit ? ` <small>${unit}</small>` : ""}</span>${dl}</div>`;
    };
    if (!sc) { $("score").innerHTML = ""; return; }
    const top = run.spendTop;
    $("score").innerHTML =
      card("Wafers out a day", Math.round(sc.wafers_per_day).toLocaleString(), "", sc.wafers_per_day, p && p.wafers_per_day, (d) => d > 0, c && sc.wafers_per_day < c.target.wafers) +
      card("Cycle time", sc.cycle_days.toFixed(2), "days", sc.cycle_days, p && p.cycle_days, (d) => d < 0) +
      card("Worst queue", sc.worst_queue, `lots · ${esc(groupLabel(sc.worst_group))}`, sc.worst_queue, p && p.worst_queue, (d) => d < 0) +
      card("Jammed stretches", sc.jams, "", sc.jams, p && p.jams, (d) => d < 0, c && c.target.jams != null && sc.jams > c.target.jams) +
      card("Spend on top", money(top), c && c.target.budget ? `of ${money(c.target.budget)} allowed` : c && c.target.budget === 0 ? "nothing to spend" : "", top, p && p.spend, (d) => d < 0, c && c.target.budget != null && top > c.target.budget);
    if (c) {
      const w = sc.wafers_per_day, full = c.target.wafers * 1.2, ok = E.meets(sc, c.target, top);
      $("goalfill").style.width = Math.min(100, (w / full) * 100) + "%";
      $("goaltick").style.left = (c.target.wafers / full) * 100 + "%";
      $("goalbar").classList.toggle("met", ok);
      $("goaltext").innerHTML = ok ? `<b>Challenge met.</b> ${Math.round(w).toLocaleString()} wafers a day${c.target.budget ? `, ${money(top)} spent of ${money(c.target.budget)}` : ""}.` : `<b>${Math.round(w).toLocaleString()}</b> of ${c.target.wafers.toLocaleString()} wafers a day${c.target.budget != null && top > c.target.budget ? `, over budget by ${money(top - c.target.budget)}` : ""}`;
    } else {
      $("goalfill").style.width = "0"; $("goalbar").classList.remove("met");
      $("goaltext").innerHTML = `<b>${Math.round(sc.wafers_per_day).toLocaleString()}</b> wafers a day on your layout`;
    }
  }
  const groupLabel = (g) => { const b = s.blocks.find((z) => z.group === g); return b && AREA[b.area] ? AREA[b.area][0] : g || "none"; };

  // ---------- challenges
  function renderTabs() {
    const names = [...E.CHALLENGES.map((c, i) => `${i + 1} · ${c.title}`), "Free build"];
    $("chtabs").innerHTML = names.map((n, i) => `<button class="tab" data-ch="${i}" aria-pressed="${i === chIdx}">${esc(n)}${i < E.CHALLENGES.length && met.has(E.CHALLENGES[i].id) ? '<span class="met" aria-label="met">✓</span>' : ""}</button>`).join("");
    $("chtabs").querySelectorAll("[data-ch]").forEach((b) => (b.onclick = () => load(+b.dataset.ch)));
  }
  async function load(i, fixed) {
    chIdx = i; sel = null; run = null; prev = null; win = null; checks = null;
    const c = ch();
    if (c) { setupNow = c.setup(); if (fixed) setupNow = c.fix(setupNow); }
    else {
      const name = $("template").value;
      if (name === "smt2020") {
        const d = await (await fetch("/api/fab/base?name=smt2020")).json();
        if (d.error) { $("goaltext").textContent = d.error; return; }
        setupNow = { state: E.template("smt2020", d), base: d.shop, overrides: null };
        for (const l of d.areas.split("\n")) { const [g, a] = l.split("\t"); if (g) areaOfGroup[g] = E.AREA_OF[a]; }
      } else setupNow = { state: E.template("teaching"), base: E.TEACHING_SHOP, overrides: null };
    }
    s = setupNow.state; base = setupNow.base;
    for (const l of base.split("\n")) if (l.startsWith("group\t")) { const g = l.split("\t")[1]; if (!areaOfGroup[g]) areaOfGroup[g] = E.AREA_OF[g.replace(/_T$/, "")]; }
    spend0 = E.spend(c ? c.setup().state : s);
    $("cheye").textContent = c ? `Challenge ${i + 1} · ${c.title}` : "Free build";
    $("chproblem").textContent = c ? c.problem : "Lay out your own fab: place tool groups, lay rail, then run it.";
    $("chgoal").textContent = c ? c.goal : "No target here. The score shows how your layout does.";
    $("showfix").hidden = !c;
    $("tmpl").hidden = !!c;
    renderTabs(); buildPalette(); inspector(); renderChecks(); renderScore(); draw();
    await runNow();
  }

  // ---------- modes and the clock
  function setMode(m) {
    mode = m;
    $("modeRun").setAttribute("aria-pressed", String(m === "run")); $("modeBuild").setAttribute("aria-pressed", String(m === "build"));
    $("editor").classList.toggle("running", m === "run");
    $("again").hidden = !(m === "build" || stale);
    if (m === "build") playing = false;
    else { playing = !matchMedia("(prefers-reduced-motion: reduce)").matches || playing; tool = "select"; syncPal(); }
    playBtn(); draw();
  }
  function playBtn() { $("play").textContent = playing ? "❚❚" : "▶"; $("play").setAttribute("aria-label", playing ? "Pause" : "Play"); }
  const hhmmss = (t) => { const d = Math.floor(t / 1440) + 1, m = t % 1440; return `Day ${d} · ${String(Math.floor(m / 60)).padStart(2, "0")}:${String(Math.floor(m % 60)).padStart(2, "0")}:${String(Math.floor((m * 60) % 60)).padStart(2, "0")}`; };
  let lastHour = -1;
  function tickUi() {
    $("clock").textContent = hhmmss(clock);
    if (!run) return;
    const fi = frameIdx();
    if (fi === lastHour) return;
    lastHour = fi;
    $("slider").value = fi; $("slabel").textContent = hhmmss(run.frames[fi].t).replace(/:00$/, "");
    const lots = run.frames[fi].lots;
    $("lots").innerHTML = Object.keys(LOT).map((m) => `<div class="${lots[m] ? "" : "zero"}"><img src="cast/lots/${m}.webp" alt=""><b>${lots[m] || 0}</b>${LOT[m]}</div>`).join("");
  }

  // ---------- palette and editing
  function placeKind() { return tool in AREA ? "group" : tool; }
  function nextGroup(area) {
    const placed = new Set(s.blocks.filter((b) => b.kind === "group").map((b) => b.group));
    return Object.keys(areaOfGroup).find((g) => areaOfGroup[g] === area && !placed.has(g) && !(s.stores || []).includes(g) && base.includes(`group\t${g}\t`));
  }
  function buildPalette() {
    const pb = (t, n, k, col, dis) => `<button data-t="${t}" aria-pressed="${tool === t}"${dis ? " disabled" : ""} title="${esc(n)}${dis ? ": every group of this area is placed; add tools with + in Selected" : ""}">${svg(t, col)}<span>${esc(n)}</span>${k ? `<kbd>${k}</kbd>` : ""}</button>`;
    let h = "<h4>Tools</h4>" + pb("select", "Select", "V") + pb("rail", "Rail", "B") + pb("erase", "Erase", "E");
    h += "<h4>Process areas</h4>";
    for (const a of E.AREAS) h += pb(a, AREA[a][0], "", FAM[a], !nextGroup(a));
    h += "<h4>Logistics</h4>" + pb("entry", INFRA.entry[0]) + pb("exit", INFRA.exit[0]) + pb("stocker", INFRA.stocker[0]);
    $("pal").innerHTML = h;
    $("pal").querySelectorAll("button").forEach((b) => (b.onclick = () => { tool = b.dataset.t; if (tool !== "select" && mode === "run") setMode("build"); syncPal(); }));
  }
  function syncPal() { $("pal").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.t === tool))); }

  const blockAt = (x, y, skip) => s.blocks.find((b) => b !== skip && x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h);
  function free(x, y, w, h, skip) {
    if (x < 0 || y < 0 || x + w > s.W || y + h > s.H) return false;
    for (let i = 0; i < w; i++) for (let j = 0; j < h; j++) if (s.rail[E.key(x + i, y + j)] || blockAt(x + i, y + j, skip)) return false;
    return true;
  }
  function edited() {
    if (!stale) { stale = true; renderScore(); }
    if (mode !== "build") setMode("build");
    $("again").hidden = false;
    clearTimeout(checkTimer);
    checkTimer = setTimeout(async () => { checks = await post("/api/fab/check", { fab: fab() }); renderChecks(); draw(); }, 350);
    draw();
  }
  const tallOf = (b) => (b.kind === "group" ? (b.area === "litho" ? 1.05 : b.area === "diff" ? 1.15 : 0.75) : b.kind === "stocker" ? 0.9 : 0.35);
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
    const [x, y] = cellOf(e);
    if (x < 0 || y < 0 || x >= s.W || y >= s.H) return;
    const k = E.key(x, y), b = blockAt(x, y);
    if (tool === "select") {
      sel = b ? { id: b.id } : s.rail[k] ? { rail: k } : null;
      if (b && mode === "build") { drag = { move: b, dx: x - b.x, dy: y - b.y }; cv.setPointerCapture(e.pointerId); }
      inspector(); draw(); return;
    }
    if (tool === "erase") { if (b) s.blocks = s.blocks.filter((z) => z !== b); else if (s.rail[k]) delete s.rail[k]; else return; sel = null; buildPalette(); inspector(); edited(); drag = { erase: true }; cv.setPointerCapture(e.pointerId); return; }
    if (tool === "rail") { if (b) return; if (!s.rail[k]) s.rail[k] = { o: [0, 0, 0, 0] }; drag = { last: k }; sel = { rail: k }; cv.setPointerCapture(e.pointerId); inspector(); edited(); return; }
    const kind = placeKind(), [w, h] = kind === "entry" || kind === "exit" ? [1, 2] : [2, 2];
    if (!free(x, y, w, h)) return;
    const id = Math.max(0, ...s.blocks.map((z) => z.id)) + 1;
    if (kind === "group") {
      const g = nextGroup(tool);
      if (!g) return;
      s.blocks.push({ id, kind: "group", group: g, area: tool, count: 1, x, y, w, h });
      buildPalette();
      if (!nextGroup(tool)) { tool = "select"; syncPal(); }
    } else s.blocks.push({ id, kind, x, y, w, h });
    sel = { id }; inspector(); edited();
  });
  cv.addEventListener("pointermove", (e) => {
    const [x, y] = cellOf(e), inb = x >= 0 && y >= 0 && x < s.W && y < s.H;
    hover = inb ? [x, y] : null;
    if (drag && inb) {
      const k = E.key(x, y);
      if (drag.move) {
        const b = drag.move, nx = x - drag.dx, ny = y - drag.dy;
        if ((nx !== b.x || ny !== b.y) && free(nx, ny, b.w, b.h, b)) { b.x = nx; b.y = ny; edited(); }
      } else if (drag.erase) {
        const b = blockAt(x, y);
        if (b) { s.blocks = s.blocks.filter((z) => z !== b); buildPalette(); } else if (s.rail[k]) delete s.rail[k]; else return;
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
  cv.addEventListener("pointerup", () => { drag = null; inspector(); });
  cv.addEventListener("pointerleave", () => { hover = null; $("hover").hidden = true; if (!playing) draw(); });

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
        <div class="kv"><span>Lots waiting</span><span>${n ? n.queue : "–"}</span><span>Group</span><span>${esc(b.group)}</span><span>Price a tool</span><span>${money(E.PRICE[b.area] || 0)}</span></div>
        <div class="ex">${esc(AREA[b.area][1])}. ${esc(AREA[b.area][2])}</div></div>`;
    } else if (!b && showRun() && win) {
      const v = vehicles(clock).find((w) => Math.abs(w.x - x) < 0.8 && Math.abs(w.y - y) < 0.8);
      if (v) {
        const m = v.hot ? "hot" : v.loaded ? "ride" : null;
        key = `v${v.vehicle}|${m}`;
        html = () => m
          ? `<div class="tcard" style="--fam:${v.hot ? "#FF8A4C" : "#F2B33D"}"><div class="hd"><span class="nm">Vehicle ${v.vehicle + 1}</span><span class="fm">${v.hot ? "hot lot" : "carrying"}</span></div><div class="art" style="background:#E3EAF0"><img src="cast/lots/${m}.webp" alt="A wafer lot riding the rail" width="224" height="224"></div><div class="st" style="background:${v.hot ? "#FF8A4C" : "#5FA8FF"}">${v.hot ? "Hot lot, riding the rail" : "Riding the rail"}</div><div class="ex">Where the simulator had this vehicle at ${hhmmss(clock)}.</div></div>`
          : `<div class="tcard" style="--fam:#8A9AA2"><div class="hd"><span class="nm">Vehicle ${v.vehicle + 1}</span><span class="fm">empty</span></div><div class="ex">Running empty to its next pickup, where the simulator had it at ${hhmmss(clock)}.</div></div>`;
      }
    }
    if (!html) return (hov.hidden = true);
    if (hov.dataset.k !== key) { hov.innerHTML = html(); hov.dataset.k = key; }
    const r = $("mapbox").getBoundingClientRect();
    let lx = e.clientX - r.left + 16, ly = e.clientY - r.top + 12;
    if (lx + 230 > r.width) lx = e.clientX - r.left - 236;
    hov.hidden = false;
    const hh = hov.offsetHeight || 320;
    if (ly + hh > r.height) ly = Math.max(4, r.height - hh - 4);
    hov.style.left = Math.max(4, lx) + "px"; hov.style.top = ly + "px";
  }

  // ---------- the selection widget
  const FAILS = [["", "As the model has it"], ["none", "Never breaks"], ["random", "Random breakdowns"], ["by_wafers", "Every N wafers"]];
  const RECS = [["", "Repair in place"], ["swap_to_spare", "Swap to a spare"], ["repair_and_hold_lots", "Repair and hold its last lots"]];
  const num = (id, v, lab, unit) => `<label class="sub">${lab} <input type="number" min="1" step="1" id="${id}" value="${v}"> ${unit}</label>`;
  function inspector() {
    const ins = $("insp");
    if (sel && sel.id) {
      const b = s.blocks.find((z) => z.id === sel.id);
      if (!b) { sel = null; return inspector(); }
      if (b.kind === "group") {
        const f = b.fail || {}, r = b.rec || {};
        let h = `<div class="ttl">${svg(b.area, FAM[b.area])}<span>${esc(AREA[b.area][0])}</span></div><p class="note">${esc(b.group)} · ${esc(AREA[b.area][2])} ${money(E.PRICE[b.area])} a tool (assumed).</p>`;
        h += `<div class="row"><span>Tools in this group</span><span class="count"><button class="btn" id="dn" aria-label="One fewer">−</button><b>${b.count}</b><button class="btn" id="up" aria-label="One more">+</button></span></div>`;
        h += `<div class="row"><label for="fsel">Breakdowns</label><select id="fsel">${FAILS.map(([k, n]) => `<option value="${k}" ${(f.kind || "") === k ? "selected" : ""}>${n}</option>`).join("")}</select></div>`;
        if (f.kind === "random") h += `<div class="row">${num("fa", f.mttf_minutes / 60, "every", "h")}${num("fb", f.mttr_minutes / 60, "repair", "h")}</div>`;
        if (f.kind === "by_wafers") h += `<div class="row">${num("fa", f.every, "every", "wafers")}${num("fb", (f.minutes || [60])[0], "repair", "min")}</div>`;
        h += `<div class="row"><label for="rsel">Recovery</label><select id="rsel">${RECS.map(([k, n]) => `<option value="${k}" ${(r.kind || "") === k ? "selected" : ""}>${n}</option>`).join("")}</select></div>`;
        if (r.kind === "swap_to_spare") h += `<div class="row">${num("ra", r.spares, "spares", `(${money(r.spares * E.PRICE[b.area])})`)}${num("rb", r.swap_minutes, "swap", "min")}</div>`;
        h += `<div class="row"><button class="btn" id="del">Remove</button></div>`;
        ins.innerHTML = h;
        $("up").onclick = () => { b.count++; inspector(); edited(); };
        $("dn").onclick = () => { b.count = Math.max(1, b.count - 1); inspector(); edited(); };
        $("fsel").onchange = (e) => {
          const k = e.target.value;
          b.fail = k === "" ? undefined : k === "none" ? { kind: "none" } : k === "random" ? { kind: "random", mttf_minutes: 480, mttr_minutes: 120 } : { kind: "by_wafers", every: 500, minutes: [60, 120] };
          inspector(); edited();
        };
        $("rsel").onchange = (e) => {
          const k = e.target.value;
          b.rec = k === "" ? undefined : k === "swap_to_spare" ? { kind: "swap_to_spare", spares: 1, swap_minutes: 20 } : { kind: "repair_and_hold_lots", lookback_minutes: 60, hold_minutes: 120 };
          inspector(); edited();
        };
        const bind = (id, fn) => { const el = $(id); if (el) el.onchange = () => { const v = Number(el.value); if (v > 0) { fn(v); edited(); } inspector(); }; };
        bind("fa", (v) => (f.kind === "random" ? (b.fail.mttf_minutes = v * 60) : (b.fail.every = v)));
        bind("fb", (v) => (f.kind === "random" ? (b.fail.mttr_minutes = v * 60) : (b.fail.minutes = [v, v])));
        bind("ra", (v) => (b.rec.spares = Math.round(v)));
        bind("rb", (v) => (b.rec.swap_minutes = v));
      } else {
        ins.innerHTML = `<div class="ttl">${svg(b.kind)}<span>${INFRA[b.kind][0]}</span></div><p class="note">${INFRA[b.kind][1]}</p><div class="row"><button class="btn" id="del">Remove</button></div>`;
      }
      $("del").onclick = () => { s.blocks = s.blocks.filter((z) => z !== b); sel = null; buildPalette(); inspector(); edited(); };
    } else if (sel && sel.rail && s.rail[sel.rail]) {
      const v = s.rail[sel.rail], split = v.o.reduce((a, c) => a + c) > 1, f = v.fail || {};
      let h = `<div class="ttl">${svg(split ? "split" : "rail")}<span>Rail piece (${sel.rail.replace(",", ", ")})</span></div><p class="note">One-way. Turn on more than one way out to make a split.</p>`;
      h += `<div class="row"><span>Ways out</span><span class="dirs4">${DN.map((d, i) => `<button class="btn" data-d="${i}" aria-pressed="${!!v.o[i]}" aria-label="${DLONG[i]}">${d}</button>`).join("")}</span></div>`;
      h += `<div class="row"><label for="rf">Breakdowns</label><select id="rf"><option value="">Never</option><option value="random" ${f.kind === "random" ? "selected" : ""}>Random stoppages</option></select></div>`;
      if (f.kind === "random") {
        h += `<div class="row">${num("ra", f.mttf_minutes, "every", "min")}${num("rb", f.mttr_minutes, "repair", "min")}</div>`;
        h += `<div class="row"><label for="rr">When it stops</label><select id="rr"><option value="wait" ${(v.rec || {}).kind !== "route_around" ? "selected" : ""}>Vehicles wait for the repair</option><option value="route_around" ${(v.rec || {}).kind === "route_around" ? "selected" : ""}>Vehicles go round it</option></select></div>`;
      }
      ins.innerHTML = h;
      ins.querySelectorAll("[data-d]").forEach((bt) => (bt.onclick = () => { const d = +bt.dataset.d; v.o[d] = v.o[d] ? 0 : 1; inspector(); edited(); }));
      $("rf").onchange = (e) => { if (e.target.value) { v.fail = { kind: "random", mttf_minutes: 240, mttr_minutes: 60 }; v.rec = { kind: "wait" }; } else { delete v.fail; delete v.rec; } inspector(); edited(); };
      if ($("rr")) $("rr").onchange = (e) => { v.rec = { kind: e.target.value }; edited(); };
      const bind = (id, fn) => { const el = $(id); if (el) el.onchange = () => { const n = Number(el.value); if (n > 0) { fn(n); edited(); } inspector(); }; };
      bind("ra", (n) => (v.fail.mttf_minutes = n));
      bind("rb", (n) => (v.fail.mttr_minutes = n));
    } else {
      let h = `<div class="ttl">${svg("fab")}<span>The whole fab</span></div><p class="note">Click a machine or a rail piece to change it. These apply to the whole fab.</p>`;
      h += `<div class="row"><span>Vehicles</span><span class="count"><button class="btn" id="vdn" aria-label="One fewer vehicle">−</button><b>${s.vehicles}</b><button class="btn" id="vup" aria-label="One more vehicle">+</button></span></div>`;
      h += `<div class="row"><label for="cap">Work-in-fab cap</label><span class="sub"><input type="number" min="0" step="1" id="cap" value="${s.cap || 0}"> lots (0 = none)</span></div>`;
      ins.innerHTML = h;
      $("vup").onclick = () => { s.vehicles++; inspector(); edited(); };
      $("vdn").onclick = () => { s.vehicles = Math.max(1, s.vehicles - 1); inspector(); edited(); };
      $("cap").onchange = (e) => { const n = Math.max(0, Math.round(Number(e.target.value) || 0)); if (n) s.cap = n; else delete s.cap; inspector(); edited(); };
    }
  }

  // ---------- checks
  function renderChecks() {
    const ul = $("issues");
    if (!checks) { ul.innerHTML = '<li><span class="chip warning">…</span><span>Checking the layout.</span></li>'; $("verdict").innerHTML = ""; return; }
    if (checks.error) { ul.innerHTML = `<li><span class="chip error">refused</span><span>${esc(checks.error)}</span></li>`; $("verdict").innerHTML = '<span class="chip error">refused</span>'; return; }
    const errs = checks.issues.filter((i) => i.severity === "error").length;
    $("verdict").innerHTML = errs ? `<span class="chip error">${errs} to fix</span>` : '<span class="chip ok">ready to run</span>';
    ul.innerHTML = checks.issues.length
      ? checks.issues.map((i, n) => `<li data-n="${n}"><span class="chip ${i.severity}">${i.severity === "error" ? "fix" : "note"}</span><span>${esc(i.message)}</span></li>`).join("")
      : '<li><span class="chip ok">ok</span><span>Every tool has a stop, every stop is on the way from the wafer start to the ship point, and every route can be followed.</span></li>';
    ul.querySelectorAll("li[data-n]").forEach((li) => (li.onclick = () => {
      const i = checks.issues[+li.dataset.n];
      const at = i.at.map((a) => E.cellOfNode(a)).find(Boolean) || (() => { const b = s.blocks.find((z) => i.at.includes(z.group) || i.at.some((a) => z.group && a.startsWith(z.group + "#"))); return b ? [b.x, b.y] : null; })();
      if (at) { flash = at; draw(); setTimeout(() => { flash = null; draw(); }, 1400); }
    }));
  }

  // ---------- controls
  $("modeRun").onclick = () => { if (stale && !running) runNow(); else { setMode("run"); playing = true; playBtn(); } };
  $("modeBuild").onclick = () => setMode("build");
  $("play").onclick = () => { if (stale) return runNow(); playing = !playing; if (playing && mode === "build") setMode("run"); playBtn(); };
  $("speed").onchange = (e) => { speed = +e.target.value; };
  $("again").onclick = () => runNow();
  $("showfix").onclick = () => load(chIdx, true);
  $("template").onchange = () => load(E.CHALLENGES.length);
  $("slider").oninput = () => { if (!run) return; const t = run.frames[+$("slider").value].t; lastHour = -1; jumpTo(Math.min(t, days() * 1440 - WINDOW)); };
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("select,input,textarea")) return;
    const k = e.key.toLowerCase(), m = { v: "select", b: "rail", e: "erase" };
    if (m[k]) { tool = m[k]; if (tool !== "select" && mode === "run") setMode("build"); syncPal(); }
    if (k === " ") { e.preventDefault(); $("play").click(); }
    if (k === "r" && sel && sel.rail && s.rail[sel.rail]) { const v = s.rail[sel.rail]; v.o = [v.o[3], v.o[0], v.o[1], v.o[2]]; inspector(); edited(); }
    if ((k === "delete" || k === "backspace") && sel && sel.id) { s.blocks = s.blocks.filter((b) => b.id !== sel.id); sel = null; buildPalette(); inspector(); edited(); }
    if (k === "escape") { sel = null; inspector(); draw(); }
  });

  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.1, (ts - (last || ts)) / 1000);
    last = ts;
    if (playing && mode === "run" && !stale && !document.hidden && win) { advance(dt); tickUi(); draw(); }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(draw, 80); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => s && draw());
  // for page tests: where a floor cell's centre is on screen, and the map's state (read only)
  window.FabEditorPage = {
    screenOf(x, y, z) { const r = cv.getBoundingClientRect(), p = P(x + 0.5, y + 0.5, z || 0); return [r.left + p[0], r.top + p[1]]; },
    blocks: () => s.blocks.map((b) => ({ ...b })),
    breaks: () => Object.keys(s.rail).filter((k) => s.rail[k].fail),
  };
  load(0);
})();
