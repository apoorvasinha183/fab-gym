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
  const HIGHER = { money: true, profit: true, a_wafers: true, b_cycle: false };
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
        text: !has ? "no prototype lot out" : metric === "profit" ? `${usd(m.mean, true)} (${usd(m.lo, true)} to ${usd(m.hi, true)})`
          : `${signed(m.mean)} (${signed(m.lo)} to ${signed(m.hi)})`,
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

  // ---------------------------------------------------------------- the Flows view: one wafer's journey
  // A route's trips between halls, in route order. Steps in the same hall make no trip; a group with no hall is skipped.
  function journey(steps, hallOfGroup) {
    const out = [];
    let prev = null;
    steps.forEach((g, k) => {
      const h = hallOfGroup[g];
      if (h === undefined) return;
      if (prev !== null && h !== prev) out.push({ a: prev, b: h, step: k });
      prev = h;
    });
    return out;
  }
  // How many of N trips are drawn after `secs` of a replay lasting T seconds: slow at first so the first trips can be
  // followed by eye, then faster until all N are drawn.
  function journeyDone(N, secs, T) {
    const u = Math.max(0, Math.min(1, secs / T));
    return u >= 1 ? N : N * u * u;
  }
  // How much of each of `bins` equal stretches of a clockwise ring of length `ring` the trips [from, to] cover.
  // A trip to its own starting point goes all the way round.
  function ringUse(trips, ring, bins) {
    const use = new Array(bins).fill(0), w = ring / bins;
    const add = (lo, hi) => {
      for (let i = Math.floor(lo / w); i < bins && i * w < hi; i++) {
        const a = Math.max(lo, i * w), b = Math.min(hi, (i + 1) * w);
        if (b > a) use[i] += (b - a) / w;
      }
    };
    for (const [s0, s1] of trips) {
      const a = ((s0 % ring) + ring) % ring, b = ((s1 % ring) + ring) % ring;
      if (b > a) add(a, b);
      else { add(a, ring); add(0, b); }
    }
    return use;
  }

  // ---------------------------------------------------------------- money in dollars (docs/MONEY-PL.md)
  // Dollars, short: $1.23M, $540k, $8,000; `sign` adds + to gains.
  function usd(x, sign = false) {
    if (x === null || x === undefined || !isFinite(x)) return "—";
    const s = x < 0 ? "−" : sign && x > 0 ? "+" : "", a = Math.abs(x);
    const t = a >= 1e6 ? `${+(a / 1e6).toFixed(a >= 1e8 ? 0 : 2)}M` : a >= 1e4 && sign ? `${Math.round(a / 1e3)}k` : Math.round(a).toLocaleString("en-US");
    return `${s}$${t}`;
  }
  // The sweep's cells with the saved runs priced in dollars: each cell gains `profit` (the change in operating profit
  // a day against the shared floor with today's order) and `pl` (capital, cash, net present value, payback).
  function withPl(summary, pl) {
    const out = { ...summary, plToday: {}, plNote: pl.note };
    for (const t of pl.today) out.plToday[String(t.share)] = t;
    out.cells = summary.cells.map((c) => {
      const p = pl.cells.find((x) => x.share === c.share && x.strategy === c.strategy && x.policy === c.policy);
      return p ? { ...c, profit: { ...p.profit, verdict: p.verdict }, pl: { capital: p.capital, cash: p.cash, npv: p.npv, payback_days: p.payback_days } } : c;
    });
    return out;
  }
  // The price sheet as the page shows it.
  function sheetValue(v, unit) {
    if (unit.startsWith("$")) {
      const rest = unit.slice(1).trim();
      const m = v >= 1e6 ? `$${+(v / 1e6).toFixed(2)}M` : `$${Math.round(v).toLocaleString("en-US")}`;
      return rest ? `${m} ${rest}` : m;
    }
    if (unit.startsWith("share of the price")) return `${+(v * 100).toFixed(1)}% of the price a day`;
    if (unit.startsWith("share of")) return `${+(v * 100).toFixed(1)}% ${unit.replace("share of ", "of ")}`;
    if (unit === "a year") return `${+(v * 100).toFixed(1)}% a year`;
    return `${+v.toFixed(2)} ${unit}`;
  }
  // "$4,000 a wafer" and "$15,000 a wafer" become "$4,000 to $15,000 a wafer"
  function rangeText(lo, hi) {
    const a = lo.split(" "), b = hi.split(" ");
    let k = 0;
    while (k < a.length - 1 && k < b.length - 1 && a[a.length - 1 - k] === b[b.length - 1 - k]) k++;
    return k ? `${a.slice(0, a.length - k).join(" ")} to ${hi}` : `${lo} to ${hi}`;
  }
  function priceSheetRows(pl) {
    return pl.sheet.map((it) => ({
      key: it.key, label: it.label,
      central: sheetValue(it.central, it.unit),
      range: it.low === it.high ? "" : rangeText(sheetValue(it.low, it.unit), sheetValue(it.high, it.unit)),
      note: it.assumed ? "assumed" : "",
    }));
  }

  // ---------------------------------------------------------------- the Results tab: a run in the page as an entry
  let runCount = 0;
  function runEntry(o) {
    runCount++;
    return {
      id: `page-${Date.now()}-${runCount}`, kind: o.kind, when: new Date().toISOString(), title: o.title, question: o.question || "",
      settings: o.settings, headline: o.headline || "", numbers: { columns: o.columns, rows: o.rows }, files: [],
      note: "On the SMT2020 model, a published research model of a wafer fab. No real fab's data is used. Run in this page; not saved to disk.",
    };
  }

  // What each change buys, as a floor × policy grid at one share: profit over the chosen period (a day, a month or a
  // year), the verdict, payback and five-year value, with today's fab (the shared floor, today's order) as the base.
  const PERIOD = { day: [1, "a day"], month: [365 / 12, "a month"], year: [365, "a year"] };
  function capitalGrid(d, share, period) {
    const [k, unit] = PERIOD[period] || PERIOD.day;
    let best = null;
    const floors = STRATEGIES.map((st) => {
      let capital = 0;
      const cells = POLICIES.map((po) => {
        if (st === "D1 share" && po === "P0 today") return { policy: po, base: true };
        const c = d.cells.find((x) => x.share === share && x.strategy === st && x.policy === po);
        if (!c || !c.profit || !c.pl) return { policy: po, missing: true };
        capital = c.pl.capital;
        const cell = {
          policy: po, value: c.profit.mean * k, lo: c.profit.lo * k, hi: c.profit.hi * k, verdict: c.profit.verdict,
          capital: c.pl.capital, payback: c.pl.payback_days, npv: c.pl.npv, best: false,
        };
        if (cell.verdict === "better" && (!best || cell.value > best.value)) best = cell;
        return cell;
      });
      return { floor: st, capital, cells };
    });
    if (best) best.best = true;
    return { share, period, unit, policies: POLICIES.slice(), floors };
  }

  const api = { iso, isoInverse, hallAt, niceTicks, tickLabel, verdictOf, sweepRows, sweepLines, baselineFromRuns, pairedClock, openingState, journey, journeyDone, ringUse, usd, withPl, priceSheetRows, runEntry, capitalGrid, STRATEGIES, POLICIES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabUI = api;
})(typeof window !== "undefined" ? window : globalThis);
