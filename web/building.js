// The Live view on the real building (docs/LIVE-REAL.md): which drawn box each of the engine's tools is, whether a
// shop fits the drawn building, where each vehicle is and which lot it carries at a moment (from the browser
// simulator's flat fleet arrays), and how many of a lot's wafers a step has done. In the page this defines
// window.FabBuilding; under Node, module.exports. From the SMT2020 testbed, a gigafab-style layout of our own design.
(function (root) {
  "use strict";

  const SPEED = 150; // metres a minute, the layout's
  const HELD = 0.02; // minutes past free flow before a vehicle counts as held up

  /** For each engine tool (its group index into `groupNames`), the index of its drawn box: the k-th tool of a group
   * is the group's k-th box in the building's order. -1 when the building draws none. */
  function toolBoxes(building, groupNames, toolGroups) {
    const boxes = new Map();
    building.tools.forEach((b, i) => { if (!boxes.has(b[0])) boxes.set(b[0], []); boxes.get(b[0]).push(i); });
    const seen = new Map();
    const out = new Int32Array(toolGroups.length);
    toolGroups.forEach((g, k) => {
      const name = groupNames[g], n = seen.get(name) || 0;
      seen.set(name, n + 1);
      const list = boxes.get(name);
      out[k] = list && n < list.length ? list[n] : -1;
    });
    return out;
  }

  /** A shop (pairs of group name and tool count) fits the building when every group the building draws has the same
   * count, and every other group is one the building holds without drawing. */
  function fits(building, groups) {
    const count = new Map();
    for (const b of building.tools) count.set(b[0], (count.get(b[0]) || 0) + 1);
    const hold = new Set(building.holding || []);
    let drawn = 0;
    for (const [name, n] of groups) {
      if (count.has(name)) { if (count.get(name) !== n) return false; drawn++; }
      else if (!hold.has(name)) return false;
    }
    return drawn === count.size;
  }

  /** Index the flat arrays once: stays by entry time, hoists by start, and each vehicle's carries (up to down). */
  function prepFleet(entries, hoists, vehicles, until) {
    const nE = entries.length / 5, nH = hoists.length / 6;
    const eIdx = Uint32Array.from({ length: nE }, (_, i) => i).sort((a, b) => entries[a * 5 + 2] - entries[b * 5 + 2]);
    const hIdx = Uint32Array.from({ length: nH }, (_, i) => i).sort((a, b) => hoists[a * 6 + 4] - hoists[b * 6 + 4]);
    let maxStay = 1, maxHoist = 1;
    for (let i = 0; i < nE; i++) { const o = entries[i * 5 + 3]; maxStay = Math.max(maxStay, (o < 0 ? until : o) - entries[i * 5 + 2]); }
    for (let i = 0; i < nH; i++) maxHoist = Math.max(maxHoist, hoists[i * 6 + 5] - hoists[i * 6 + 4]);
    const carries = Array.from({ length: vehicles }, () => []);
    const open = new Map();
    for (const i of hIdx) {
      const v = hoists[i * 6], lot = hoists[i * 6 + 2], up = hoists[i * 6 + 3], t0 = hoists[i * 6 + 4], t1 = hoists[i * 6 + 5];
      if (up) open.set(v, [t0, lot]);
      else if (open.has(v)) { const [s, l] = open.get(v); carries[v].push([s, t1, l]); open.delete(v); }
    }
    for (const [v, [s, l]] of open) carries[v].push([s, Infinity, l]);
    return { entries, hoists, eIdx, hIdx, maxStay, maxHoist, carries, vehicles, until };
  }

  function lowerBy(idx, arr, w, k, t) {
    let lo = 0, hi = idx.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (arr[idx[m] * w + k] < t) lo = m + 1; else hi = m; }
    return lo;
  }

  function carried(F, v, t) {
    const c = F.carries[v];
    if (!c) return -1;
    let lo = 0, hi = c.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (c[m][0] <= t) lo = m + 1; else hi = m; }
    const k = lo - 1;
    return k >= 0 && c[k][1] >= t ? c[k][2] : -1;
  }

  /** Every vehicle on the track at minute t: where (in the track's metres), what it is doing, the lot it carries
   * (-1 when none), and the counts. */
  function vehicles(F, nodes, edges, t) {
    const list = [], seen = new Set();
    const counts = { empty: 0, loaded: 0, hoist: 0, held: 0, idle: 0 };
    const H = F.hoists, E = F.entries;
    for (let i = lowerBy(F.hIdx, H, 6, 4, t - F.maxHoist); i < F.hIdx.length; i++) {
      const h = F.hIdx[i] * 6;
      if (H[h + 4] > t) break;
      if (H[h + 5] < t || seen.has(H[h])) continue;
      const n = nodes[H[h + 1]];
      seen.add(H[h]);
      list.push({ id: H[h], x: n[0], y: n[1], state: "hoist", up: !!H[h + 3], lot: H[h + 2] });
      counts.hoist++;
    }
    for (let i = lowerBy(F.eIdx, E, 5, 2, t - F.maxStay); i < F.eIdx.length; i++) {
      const e = F.eIdx[i] * 5;
      const tin = E[e + 2];
      if (tin > t) break;
      const out = E[e + 3] < 0 ? F.until : E[e + 3];
      if (out <= t || seen.has(E[e])) continue;
      const ed = edges[E[e + 1]], a = nodes[ed[0]], b = nodes[ed[1]];
      const free = ed[2] / SPEED, k = Math.min(1, (t - tin) / free);
      const loaded = E[e + 4] > 0;
      const state = t - tin > free + HELD ? "held" : loaded ? "loaded" : "empty";
      seen.add(E[e]);
      list.push({ id: E[e], x: a[0] + (b[0] - a[0]) * k, y: a[1] + (b[1] - a[1]) * k, state, loaded, lot: loaded ? carried(F, E[e], t) : -1 });
      counts[state]++;
    }
    counts.idle = Math.max(0, F.vehicles - seen.size);
    return { list, counts };
  }

  /** Wafers of a lot of n done in a step from start to end at t, one at a time at an even pace (drawn; the step's
   * start and end are the run's). */
  function wafersDone(start, end, t, n = 25) {
    if (t >= end) return n;
    if (t <= start) return 0;
    return Math.floor((n * (t - start)) / (end - start));
  }

  const api = { toolBoxes, fits, prepFleet, vehicles, wafersDone, SPEED };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabBuilding = api;
})(typeof window !== "undefined" ? window : globalThis);
