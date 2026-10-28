// The redesigned floor page's pure parts (docs/FLOOR-UI.md): the tilted view, picking, axis ticks, verdicts, the
// two-family sweep as rows, lines and baselines, one clock for two runs, and the opening. In the page this defines
// window.FabUI; under Node, module.exports. On the SMT2020 model, a published model of a fab; not a real fab.
(function (root) {
  "use strict";

  // ---------------------------------------------------------------- the tilted (2.5D) view
  // A floor point (x, y) in tiles is turned by `rot`, the depth axis squashed by `tilt`, scaled and offset.
  function iso(x, y, v) {
    const c = Math.cos(v.rot), s = Math.sin(v.rot);
    return [v.ox + v.scale * (x * c - y * s), v.oy + v.scale * v.tilt * (x * s + y * c)];
  }
  function isoInverse(sx, sy, v) {
    const c = Math.cos(v.rot), s = Math.sin(v.rot);
    const u = (sx - v.ox) / v.scale, w = (sy - v.oy) / (v.scale * v.tilt);
    return [u * c + w * s, -u * s + w * c];
  }
  function hallAt(halls, sx, sy, v) {
    const [x, y] = isoInverse(sx, sy, v);
    return halls.find((h) => x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) || null;
  }

  // ---------------------------------------------------------------- axes
  function niceTicks(lo, hi) {
    if (!(hi > lo)) return [lo];
    const raw = (hi - lo) / 4, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
    const step = (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * mag;
    const out = [];
    for (let k = Math.ceil(lo / step - 1e-9); k <= Math.floor(hi / step + 1e-9); k++) out.push(Math.round(k * step * 1e9) / 1e9);
    return out;
  }
  function tickLabel(v) {
    const a = Number(Math.abs(v).toFixed(1));
    return (v > 0 ? "+" : v < 0 ? "−" : "") + a.toLocaleString("en-US");
  }
  const signed = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1);

  // ---------------------------------------------------------------- verdicts
  const ok = (x) => typeof x === "number" && isFinite(x);
  function verdictOf(iv, higherIsBetter) {
    if (!iv || !ok(iv.lo) || !ok(iv.hi)) return "no clear effect";
    if (iv.lo > 0) return higherIsBetter ? "better" : "worse";
    if (iv.hi < 0) return higherIsBetter ? "worse" : "better";
    return "no clear effect";
  }

  // ---------------------------------------------------------------- the two-family sweep
  const STRATEGIES = ["D1 share", "D2 wing", "D3 copies"];
  const POLICIES = ["P0 today", "P1 family B first", "P2 family cap", "P3 reservation", "P4 qualification"];
  const HIGHER = { money: true, a_wafers: true, b_cycle: false };
  function sweepRows(summary, share, metric) {
    const rows = [];
    for (const st of STRATEGIES) for (const po of POLICIES) {
      if (st === "D1 share" && po === "P0 today") continue;
      const c = summary.cells.find((x) => x.share === share && x.strategy === st && x.policy === po);
      if (!c) continue;
      const m = c[metric] || {};
      const has = ok(m.mean);
      rows.push({
        strategy: st, policy: po,
        mean: has ? m.mean : null, lo: has ? m.lo : null, hi: has ? m.hi : null,
        verdict: verdictOf(has ? m : null, HIGHER[metric]),
        text: has ? `${signed(m.mean)} (${signed(m.lo)} to ${signed(m.hi)})` : "no prototype lot out",
      });
    }
    return rows;
  }
  function sweepLines(summary, metric) {
    const shares = [...new Set(summary.cells.map((c) => c.share))].sort((a, b) => a - b);
    return POLICIES.slice(1).map((po) => ({
      policy: po,
      points: shares.map((s) => {
        const c = summary.cells.find((x) => x.share === s && x.strategy === "D1 share" && x.policy === po);
        const m = (c && c[metric]) || {};
        return { share: s, mean: ok(m.mean) ? m.mean : null, lo: ok(m.lo) ? m.lo : null, hi: ok(m.hi) ? m.hi : null };
      }),
    }));
  }
  // today's means per share (shared floor, P0), from the sweep's runs file
  function baselineFromRuns(tsv) {
    const lines = tsv.trim().split("\n");
    const head = lines[0].split("\t");
    const ix = (n) => head.indexOf(n);
    const acc = {};
    for (const line of lines.slice(1)) {
      const f = line.split("\t");
      if (f[ix("strategy")] !== "D1 share" || f[ix("policy")] !== "P0 today") continue;
      const s = Number(f[ix("share")]);
      const a = acc[s] || (acc[s] = { money: [], a_wafers: [], b_cycle: [] });
      for (const [k, col] of [["money", "money_0"], ["a_wafers", "a_wafers_per_day"], ["b_cycle", "b_cycle_days"]]) {
        const v = Number(f[ix(col)]);
        if (isFinite(v)) a[k].push(v);
      }
    }
    const mean = (xs) => (xs.length ? xs.reduce((p, q) => p + q, 0) / xs.length : null);
    const out = {};
    for (const s in acc) out[s] = { money: mean(acc[s].money), a_wafers: mean(acc[s].a_wafers), b_cycle: mean(acc[s].b_cycle) };
    return out;
  }

  // ---------------------------------------------------------------- one clock for two runs
  function pairedClock(durA, durB) {
    const end = Math.max(durA, durB);
    return { end, at: (t) => { const u = Math.max(0, Math.min(t, end)); return [Math.min(u, durA), Math.min(u, durB)]; } };
  }

  // ---------------------------------------------------------------- the opening
  function openingState(status, bundled) {
    const examples = status && status.examples ? status.examples.map((e) => e.question) : (bundled || []).map((e) => e.question);
    return { prompt: "Ask the fab a question", explore: "or explore the floor", examples, canAsk: !!status };
  }

  const api = { iso, isoInverse, hallAt, niceTicks, tickLabel, verdictOf, sweepRows, sweepLines, baselineFromRuns, pairedClock, openingState, STRATEGIES, POLICIES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabUI = api;
})(typeof window !== "undefined" ? window : globalThis);
