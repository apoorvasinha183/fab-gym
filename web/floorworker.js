// The floor's full run off the page's thread (docs/FLOOR-SPEED.md). This worker's own copy of the simulator runs the
// 3 days, prepares the fleet for playback (the slow part of preparing a run) and works out the moods, and hands the
// arrays to the page without copying them. On the SMT2020 testbed; not a real fab.
"use strict";
importScripts("building.js");

onmessage = async ({ data: job }) => {
  try {
    const [wasm, shopText] = await Promise.all([
      fetch("fabweb.wasm").then(r => r.arrayBuffer()),
      fetch(job.shopUrl).then(r => r.text()),
    ]);
    const { instance } = await WebAssembly.instantiate(wasm, {});
    const e = instance.exports;
    const json = () => JSON.parse(new TextDecoder().decode(new Uint8Array(e.memory.buffer, e.fg_json_ptr(), e.fg_json_len())));
    const bytes = new TextEncoder().encode(shopText);
    const p = e.fg_alloc(bytes.length);
    new Uint8Array(e.memory.buffer, p, bytes.length).set(bytes);
    if (e.fg_load(p, bytes.length) !== 0) throw new Error(json().error);
    const d = job.dials;
    if (e.fg_dials(d.breakdowns, d.repair, d.demand, d.hot, d.rework, d.cap || 0, d.defects || 0) !== 0) throw new Error(json().error);
    const o = job.opts;
    const t0 = performance.now();
    if (e.fg_run(o.seed, o.days, o.rule, o.downGroup, o.downAt * 60, o.downHours) !== 0) throw new Error("the simulator did not run");
    const secs = (performance.now() - t0) / 1000;
    const j = json();
    const trace = new Float64Array(e.memory.buffer, e.fg_trace_ptr(), e.fg_trace_len()).slice();
    const states = new Float64Array(e.memory.buffer, e.fg_states_ptr(), e.fg_states_len()).slice();
    const fleetE = e.fg_fleet_entries_len ? new Float32Array(e.memory.buffer, e.fg_fleet_entries_ptr(), e.fg_fleet_entries_len()).slice() : new Float32Array(0);
    const fleetH = e.fg_fleet_hoists_len ? new Float32Array(e.memory.buffer, e.fg_fleet_hoists_ptr(), e.fg_fleet_hoists_len()).slice() : new Float32Array(0);
    // the fleet, indexed for playback here rather than on the page (FabBuilding.prepFleet, as the page would)
    let F = null, vehicles = 0;
    if (fleetE.length) {
      for (let i = 0; i < fleetE.length; i += 5) vehicles = Math.max(vehicles, fleetE[i] + 1);
      for (let i = 0; i < fleetH.length; i += 6) vehicles = Math.max(vehicles, fleetH[i] + 1);
      F = FabBuilding.prepFleet(fleetE, fleetH, vehicles, j.until);
    }
    const moved = [trace.buffer, states.buffer, fleetE.buffer, fleetH.buffer];
    if (F) moved.push(F.eIdx.buffer, F.hIdx.buffer);
    postMessage({ type: "run", j, trace, states, fleetE, fleetH, F, vehicles, secs }, moved);
    // the moods last: the floor is already playing the full run while they are worked out
    if (e.fg_moods && e.fg_moods(o.every) === 0) postMessage({ type: "moods", moods: json() });
    else postMessage({ type: "moods", moods: null });
  } catch (err) {
    postMessage({ type: "error", error: String((err && err.message) || err) });
  }
};
