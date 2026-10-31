// The floor in under a second (docs/FLOOR-SPEED.md): the first hours first, the full run off the page's thread,
// moods when they are ready. Written before the code. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/speed.test.mjs          (from the repo root; S2 and S3 need Google Chrome)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, mkdtempSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { dirname, join, extname } from "node:path";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HOURS = 6;

// ---------------------------------------------------------------- the simulator in Node

async function simulator() {
  const { instance } = await WebAssembly.instantiate(readFileSync(join(WEB, "fabweb.wasm")), {});
  const e = instance.exports;
  const text = readFileSync(join(WEB, "data", existsSync(join(WEB, "data", "shop-real.txt")) ? "shop-real.txt" : "shop.txt"));
  const p = e.fg_alloc(text.length);
  new Uint8Array(e.memory.buffer, p, text.length).set(text);
  assert.equal(e.fg_load(p, text.length), 0, "the fab file loads");
  return e;
}

function run(e, days) {
  assert.equal(e.fg_run(0, days, 0, -1, 0, 0), 0, `a run of ${days} days`);
  const trace = new Float64Array(e.memory.buffer, e.fg_trace_ptr(), e.fg_trace_len()).slice();
  const states = new Float64Array(e.memory.buffer, e.fg_states_ptr(), e.fg_states_len()).slice();
  return { trace, states };
}

test("S1 the first hours of a run are the start of the full run, event for event", async () => {
  const e = await simulator();
  const short = run(e, HOURS / 24);
  const full = run(e, 3);
  const cut = HOURS * 60;
  // trace rows: lot, step, tool, arrive, start, end (6 numbers); keep those that start by the cut
  const rows = (tr) => {
    const out = [];
    for (let i = 0; i < tr.length; i += 6) if (tr[i + 4] <= cut) out.push(Array.from(tr.subarray(i, i + 6)).join(","));
    return out;
  };
  const shortRows = rows(short.trace), fullRows = rows(full.trace);
  assert.ok(shortRows.length > 1000, `the first ${HOURS} hours hold real work (${shortRows.length} steps)`);
  assert.deepEqual(shortRows, fullRows, "the steps started in the first hours are the same, in the same order");
  // state changes: tool, time, state (3 numbers)
  const changes = (st) => {
    const out = [];
    for (let i = 0; i < st.length; i += 3) if (st[i + 1] <= cut) out.push(`${st[i]},${st[i + 1]},${st[i + 2]}`);
    return out;
  };
  assert.deepEqual(changes(short.states), changes(full.states), "the machines' state changes in the first hours are the same");
});

// ---------------------------------------------------------------- the page in headless Chrome

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".wasm": "application/wasm", ".txt": "text/plain", ".tsv": "text/plain", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml" };

function serve() {
  const server = createServer((req, res) => {
    const path = join(WEB, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!path.startsWith(WEB) || !existsSync(path) || !statSync(path).isFile()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": TYPES[extname(path)] || "application/octet-stream", "Cache-Control": "no-store" });
    res.end(readFileSync(path));
  });
  return new Promise((r) => server.listen(0, "127.0.0.1", () => r(server)));
}

async function chrome() {
  const port = 9400 + Math.floor(Math.random() * 400);
  const prof = mkdtempSync(join(tmpdir(), "speed-"));
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, "--window-size=1440,900", "--hide-scrollbars", `--user-data-dir=${prof}`, "about:blank"], { stdio: "ignore" });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) {
    try { const l = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up yet */ }
    if (!ws) await sleep(200);
  }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  return { send, ev, sleep, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); } };
}

// watch from navigation: when machines are drawn, when the clock first moves, when the full run is in, and every
// long task on the page's thread
const WATCH = `window.__speed = { t0: performance.timeOrigin, long: [] };
try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__speed.long.push([Math.round(e.startTime), Math.round(e.duration)]); }).observe({ type: "longtask", buffered: true }); } catch (e) {}`;

async function coldLoad(b, url) {
  await b.send("Page.enable");
  await b.send("Page.addScriptToEvaluateOnNewDocument", { source: WATCH });
  await b.send("Page.navigate", { url });
  const seen = { drawn: null, moving: null, full: null, moods: null };
  let firstTime = null;
  for (let i = 0; i < 400; i++) {
    await b.sleep(25);
    const s = await b.ev(`JSON.stringify({ now: Math.round(performance.now()), floor: document.body && document.body.dataset.floor, moods: document.body && document.body.dataset.moods, time: (document.getElementById("time") || {}).textContent })`);
    if (!s) continue;
    const o = JSON.parse(s);
    if (o.floor === "drawn" || o.floor === "full") seen.drawn ??= o.now;
    if (seen.drawn !== null && o.time) { firstTime ??= o.time; if (o.time !== firstTime) seen.moving ??= o.now; }
    if (o.floor === "full") seen.full ??= o.now;
    if (o.moods === "in") seen.moods ??= o.now;
    if (seen.full !== null && seen.moving !== null && seen.moods !== null) break;
  }
  return seen;
}

const haveChrome = existsSync(CHROME);

test("S2 from a cold link the floor draws in a second, moves, and takes the full run in without a long freeze", { skip: !haveChrome && "Google Chrome not found" }, async () => {
  const server = await serve();
  const b = await chrome();
  try {
    const seen = await coldLoad(b, `http://127.0.0.1:${server.address().port}/index.html#floor`);
    assert.ok(seen.drawn !== null && seen.drawn <= 1000, `machines drawn within 1,000 ms (at ${seen.drawn} ms)`);
    assert.ok(seen.moving !== null && seen.moving <= 1500, `the clock moving within 1,500 ms (at ${seen.moving} ms)`);
    assert.ok(seen.full !== null && seen.full <= 6000, `the full run in within 6,000 ms (at ${seen.full} ms)`);
    const moves = await b.ev("window.FabFloorPage && window.FabFloorPage.moves()");
    assert.equal(moves, 70131, "seed 0, 3 days: the same 70,131 moves as before");
    const long = JSON.parse(await b.ev("JSON.stringify(window.__speed.long)"));
    const freezes = long.filter(([start, dur]) => start >= seen.drawn && start <= seen.full && dur > 250);
    assert.deepEqual(freezes, [], "no task on the page's thread over 250 ms between the first draw and the full run");
  } finally {
    b.close();
    server.close();
  }
});

test("S3 moods arrive when they are ready, and the hover card says so until then", { skip: !haveChrome && "Google Chrome not found" }, async () => {
  const server = await serve();
  const b = await chrome();
  try {
    await b.send("Page.enable");
    await b.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/index.html#floor` });
    // before the moods are in: no mood, and the card's words say it is being worked out
    let before = null;
    for (let i = 0; i < 200 && before === null; i++) {
      await b.sleep(20);
      before = await b.ev(`(() => { const d = document.body && document.body.dataset; if (!d || d.floor !== "drawn" || d.moods === "in" || !window.FabFloorPage) return null;
        return JSON.stringify({ mood: window.FabFloorPage.mood(0), card: window.FabFloorPage.cardText(0) }); })()`);
    }
    assert.ok(before, "the floor was drawn before the moods were in");
    const b0 = JSON.parse(before);
    assert.equal(b0.mood, null, "no mood before the moods are in");
    assert.match(b0.card, /Working out how it.s doing/, "the card says the mood is being worked out");
    // once in: every group has a mood
    for (let i = 0; i < 300; i++) { await b.sleep(25); if ((await b.ev("document.body.dataset.moods")) === "in") break; }
    const all = await b.ev(`(() => { const n = window.FabFloorPage.groups(); for (let g = 0; g < n; g++) if (!window.FabFloorPage.mood(g)) return "group " + g + " has no mood"; return "ok"; })()`);
    assert.equal(all, "ok");
  } finally {
    b.close();
    server.close();
  }
});
