// The Rails lens (docs/FLEET.md): the floor seen from above on today's US building, with the rails the drawings
// show, which are the simulator's own track, and the fleet replayed from the simulator's trace (`fabsim
// fleet-trace`). In the page this defines window.FabRails; under Node, module.exports. On the SMT2020 model, a
// published model of a fab, with a gigafab-style layout of our own design; not a real fab.
(function (root) {
  "use strict";

  const SPEED = 150; // metres a minute, the layout's
  const HELD = 0.02; // minutes past free flow before a vehicle counts as held up
  const NOTE = "The rails here are the ones the plans, the BIM and the game draw, and the simulator moves its vehicles on them: " +
    "two one-way spine rails, a rail over each row of tools, a port under every tool. An hour of the fleet from the simulator's trace " +
    "on the SMT2020 model; a gigafab-style layout of our own design, not a real fab.";

  /** Sort what the trace holds once, so a moment can be looked up quickly. */
  function prep(d) {
    for (const f of d.fleets) {
      f.entries.sort((a, b) => a[2] - b[2]);
      f.hoists.sort((a, b) => a[4] - b[4]);
      f.maxStay = f.entries.reduce((m, e) => Math.max(m, (e[3] ?? f.to) - e[2]), 1);
      f.maxHoist = f.hoists.reduce((m, h) => Math.max(m, h[5] - h[4]), 1);
    }
    return d;
  }

  function lower(arr, k, t) {
    let lo = 0, hi = arr.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m][k] < t) lo = m + 1; else hi = m; }
    return lo;
  }

  /** Every vehicle on the track at fab minute t in fleet fi: where it is and what it is doing, and the counts. */
  function at(d, fi, t) {
    const f = d.fleets[fi], N = d.track.nodes, E = d.track.edges;
    const out = [], seen = new Set();
    const counts = { empty: 0, loaded: 0, hoist: 0, held: 0, idle: 0 };
    for (let i = lower(f.hoists, 4, t - f.maxHoist); i < f.hoists.length && f.hoists[i][4] <= t; i++) {
      const h = f.hoists[i];
      if (h[5] < t || seen.has(h[0])) continue;
      const n = N[h[1]];
      seen.add(h[0]);
      out.push({ id: h[0], x: n[0], y: n[1], state: "hoist", up: !!h[3] });
      counts.hoist++;
    }
    for (let i = lower(f.entries, 2, t - f.maxStay); i < f.entries.length && f.entries[i][2] <= t; i++) {
      const en = f.entries[i], leave = en[3] ?? f.to;
      if (leave <= t || seen.has(en[0])) continue;
      const e = E[en[1]], a = N[e[0]], b = N[e[1]];
      const free = e[2] / SPEED, k = Math.min(1, (t - en[2]) / free);
      const state = t - en[2] > free + HELD ? "held" : en[4] ? "loaded" : "empty";
      seen.add(en[0]);
      out.push({ id: en[0], x: a[0] + (b[0] - a[0]) * k, y: a[1] + (b[1] - a[1]) * k, state, loaded: !!en[4] });
      counts[state]++;
    }
    counts.idle = Math.max(0, f.vehicles - seen.size);
    return { vehicles: out, counts };
  }

  /** A view (centre and metres-to-pixels) fitting the buildings in a W by H canvas. */
  function fit(d, W, H) {
    const xs = d.plan.fabs.flatMap(f => [f[0], f[1]]), ys = d.plan.fabs.flatMap(f => [f[2], f[3]]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, s: Math.min(W / (x1 - x0), H / (y1 - y0)) * 0.94 };
  }

  const COLORS = { ground: "#0b1020", fab: "#111a36", fabLine: "#2a3462", bay: "#1c2550", tool: "#1a2246", stocker: "#4a4220", stockerLine: "#ffd75e",
    lane: "#5b78e6", bayRail: "#3a4ea0", port: "#8ea0e8", empty: "#f2f4fb", loaded: "#ff9d42", hoist: "#6fe3ff", held: "#ff6b6b" };

  /** Draw the plan, the rails and the vehicles at t on a 2D context sized W by H (CSS pixels). */
  function draw(ctx, W, H, view, d, fi, t, C = COLORS) {
    const sx = x => (x - view.x) * view.s + W / 2, sy = y => H / 2 - (y - view.y) * view.s;
    const rect = (x0, x1, y0, y1) => [sx(x0), sy(y1), (x1 - x0) * view.s, (y1 - y0) * view.s];
    ctx.fillStyle = C.ground; ctx.fillRect(0, 0, W, H);
    ctx.lineWidth = 1;
    for (const f of d.plan.fabs) { ctx.fillStyle = C.fab; ctx.strokeStyle = C.fabLine; const r = rect(f[0], f[1], f[2], f[3]); ctx.fillRect(...r); ctx.strokeRect(...r); }
    ctx.strokeStyle = C.bay;
    for (const b of d.plan.bays) ctx.strokeRect(...rect(b[0], b[1], b[2], b[3]));
    ctx.fillStyle = C.tool;
    for (const tl of d.plan.tools) ctx.fillRect(...rect(tl[0], tl[1], tl[2], tl[3]));
    ctx.fillStyle = C.stocker; ctx.strokeStyle = C.stockerLine;
    for (const st of d.plan.stockers) { const r = rect(st[0], st[1], st[2], st[3]); ctx.fillRect(...r); ctx.strokeRect(...r); }
    const N = d.track.nodes, E = d.track.edges;
    const isLane = i => N[i][2] === "lane" || N[i][2] === "stocker";
    for (const e of E) {
      const a = N[e[0]], b = N[e[1]];
      const spine = isLane(e[0]) && isLane(e[1]) && Math.abs(a[1] - b[1]) < 1e-6 && Math.abs(a[1]) < 3;
      ctx.strokeStyle = spine ? C.lane : C.bayRail;
      ctx.lineWidth = spine ? Math.max(1.2, view.s * 0.3) : Math.max(0.8, view.s * 0.15);
      ctx.beginPath(); ctx.moveTo(sx(a[0]), sy(a[1])); ctx.lineTo(sx(b[0]), sy(b[1])); ctx.stroke();
    }
    if (view.s > 3) {
      ctx.fillStyle = C.port;
      for (const n of N) if (n[2] === "port") { ctx.beginPath(); ctx.arc(sx(n[0]), sy(n[1]), Math.max(1.2, view.s * 0.16), 0, 7); ctx.fill(); }
    }
    const now = at(d, fi, t);
    const vs = Math.max(2.5, view.s * 0.8);
    for (const v of now.vehicles) {
      const X = sx(v.x), Y = sy(v.y);
      ctx.fillStyle = v.state === "hoist" ? C.hoist : v.loaded || v.state === "loaded" ? C.loaded : C.empty;
      ctx.fillRect(X - vs / 2, Y - vs / 2, vs, vs);
      if (v.state === "hoist") { ctx.strokeStyle = C.hoist; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(X, Y, vs * 1.4, 0, 7); ctx.stroke(); }
      if (v.state === "held") { ctx.strokeStyle = C.held; ctx.lineWidth = Math.max(1, vs * 0.3); ctx.strokeRect(X - vs / 2, Y - vs / 2, vs, vs); }
    }
    return now;
  }

  /** Zoom by factor k about the screen point (mx, my). */
  function zoom(view, W, H, mx, my, k) {
    const wx = view.x + (mx - W / 2) / view.s, wy = view.y - (my - H / 2) / view.s;
    view.s = Math.min(80, Math.max(0.3, view.s * k));
    view.x = wx - (mx - W / 2) / view.s;
    view.y = wy + (my - H / 2) / view.s;
  }

  const api = { prep, at, fit, draw, zoom, COLORS, NOTE, SPEED };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabRails = api;
})(typeof window !== "undefined" ? window : globalThis);
