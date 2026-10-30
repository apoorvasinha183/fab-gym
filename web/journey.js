// Following one lot from start to finish on the real building (docs/LIVE-REAL.md). The journey (`fabsim follow`)
// holds the lot's steps [step, group, tool, arrive, start, end], its rail stays [stretch, in, out, loaded] and its
// hoists [node, up, start, end]. It plays as waits, work and moves, each at its own pace in seconds, so a 56-day
// journey can be watched: long queue waits pass quickly, work and moves slowly. In the page this defines
// window.FabJourney; under Node, module.exports. From the SMT2020 testbed, a gigafab-style layout of our own design.
(function (root) {
  "use strict";

  const SPEED = 150; // metres a minute, the layout's

  /** The journey as segments with playback times: a wait (when the lot queued), its work, then the move on. */
  function plan(J, pace) {
    const segs = [];
    let p = 0;
    const add = (kind, step, t0, t1, d) => { if (d > 0 && t1 >= t0) { segs.push({ kind, step, t0, t1, p0: p, p1: p + d }); p += d; } };
    J.steps.forEach((s, i) => {
      const [, , , arrive, start, end] = s;
      if (start > arrive) add("wait", i, arrive, start, pace.wait);
      add("work", i, start, end, pace.work);
      const next = J.steps[i + 1];
      if (next && next[3] > end) add("move", i, end, next[3], pace.move);
    });
    return { segs, total: p };
  }

  /** Where the playback is at second p: the segment's kind, the step's index and the fab minute. */
  function at(P, p) {
    const S = P.segs;
    if (!S.length) return null;
    const q = Math.max(0, Math.min(p, P.total));
    let lo = 0, hi = S.length - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (S[m].p0 <= q) lo = m; else hi = m - 1; }
    const s = S[lo];
    const f = s.p1 > s.p0 ? Math.min(1, (q - s.p0) / (s.p1 - s.p0)) : 1;
    return { kind: s.kind, step: s.step, t: s.t0 + f * (s.t1 - s.t0), seg: lo, f };
  }

  /** The playback second at which step i begins. */
  function startOf(P, i) {
    const s = P.segs.find(x => x.step === i);
    return s ? s.p0 : 0;
  }

  /** Where the lot is on the rails at fab minute t: hoisting at a node, riding a stretch, or null when off the rails. */
  function where(J, nodes, edges, t) {
    for (const h of J.hoists) {
      if (h[2] <= t && t <= h[3]) { const n = nodes[h[0]]; return { state: "hoist", up: !!h[1], x: n[0], y: n[1] }; }
    }
    for (const e of J.entries) {
      const out = e[2] === null ? Infinity : e[2];
      if (e[1] <= t && t < out) {
        const ed = edges[e[0]], a = nodes[ed[0]], b = nodes[ed[1]];
        const k = Math.min(1, (t - e[1]) / (ed[2] / SPEED));
        return { state: "rail", loaded: !!e[3], x: a[0] + (b[0] - a[0]) * k, y: a[1] + (b[1] - a[1]) * k };
      }
    }
    return null;
  }

  /** The node where the lot was last set down at or before t (it waits there for its tool), or -1. */
  function lastDrop(J, t) {
    let n = -1;
    for (const h of J.hoists) if (!h[1] && h[3] <= t) n = h[0];
    return n;
  }

  const api = { plan, at, startOf, where, lastDrop };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabJourney = api;
})(typeof window !== "undefined" ? window : globalThis);
