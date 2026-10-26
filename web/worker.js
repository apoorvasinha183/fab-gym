// A worker with its own copy of the simulator: runs one seed at a time and returns its totals.
"use strict";

let e = null;
const ready = (async () => {
  const [wasm, shopText] = await Promise.all([
    fetch("fabweb.wasm").then(r => r.arrayBuffer()),
    fetch("data/shop.txt").then(r => r.text()),
  ]);
  const { instance } = await WebAssembly.instantiate(wasm, {});
  e = instance.exports;
  const bytes = new TextEncoder().encode(shopText);
  const p = e.fg_alloc(bytes.length);
  new Uint8Array(e.memory.buffer, p, bytes.length).set(bytes);
  if (e.fg_load(p, bytes.length) !== 0) throw new Error("the shop did not load");
})();

function text(ptr, len) {
  return new TextDecoder().decode(new Uint8Array(e.memory.buffer, ptr, len));
}

onmessage = async ({ data: job }) => {
  try {
    await ready;
    const d = job.dials;
    if (e.fg_dials(d.breakdowns, d.repair, d.demand, d.hot, d.rework, d.cap || 0) !== 0) {
      throw new Error(JSON.parse(text(e.fg_json_ptr(), e.fg_json_len())).error);
    }
    const rc = e.fg_quick(job.seed, job.days, job.rule, job.downGroup, job.downAt * 60, job.downHours);
    const q = JSON.parse(text(e.fg_quick_ptr(), e.fg_quick_len()));
    if (rc !== 0) throw new Error(q.error);
    postMessage({ id: job.id, q });
  } catch (err) {
    postMessage({ id: job.id, error: String(err.message || err) });
  }
};
