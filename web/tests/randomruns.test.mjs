// Random runs to watch (docs/RANDOM-RUNS.md). Written before the code. On a teaching fab of our own and the SMT2020
// testbed; not a real fab.
//
//     node --test web/tests/randomruns.test.mjs   (needs Google Chrome; RR4 and RR5 the .venv too)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, mkdtempSync, statSync, rmSync as rmProfile } from "node:fs";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { dirname, join, extname } from "node:path";
import { tmpdir } from "node:os";
const PROFILES = [];
const profileDir = (prefix) => { const d = mkdtempSync(join(tmpdir(), prefix)); PROFILES.push(d); return d; };
process.on("exit", () => { for (const d of PROFILES) { try { rmProfile(d, { recursive: true, force: true }); } catch { /* already gone */ } } });

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const skip = !existsSync(CHROME) && "Google Chrome not found";
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
  const prof = profileDir("runs-");
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${prof}`, "about:blank"], { stdio: "ignore" });
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



const PY = join(WEB, "..", ".venv", "bin", "python");
const ROOT = join(WEB, "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ready = !skip && existsSync(PY);

// the Floor at an address, its full run in
async function floorAt(server, b, path) {
  await b.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${path}` });
  for (let i = 0; i < 600; i++) { await b.sleep(100); if (await b.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
  await b.ev(`(() => { if (document.getElementById("play").textContent.includes("❚")) document.getElementById("play").click(); return 1; })()`);
  const read = async () => JSON.parse(await b.ev(`JSON.stringify({ run: FabFloorPage.runNumber(), moves: FabFloorPage.moves(), label: document.getElementById("run-no").textContent, url: location.search })`));
  return read();
}
const finishedAt = async (b, t) => { await b.ev(`(() => { const s = document.getElementById("scrub"); s.value = ${t}; s.dispatchEvent(new Event("input", { bubbles: true })); return 1; })()`); await b.sleep(250); return b.ev("FabFloorPage.health().finished"); };

test("RR1 the Floor picks a random run, shows it and puts it in the address", { skip }, async () => {
  const server = await serve(); const b = await chrome();
  try {
    await b.send("Page.enable");
    const seen = [];
    for (let i = 0; i < 3; i++) {
      const r = await floorAt(server, b, "index.html#floor");
      assert.ok(Number.isInteger(r.run) && r.run >= 1 && r.run <= 9999, `a run from 1 to 9,999 (${r.run})`);
      assert.match(r.label, new RegExp(`Run #${r.run}\\b`));
      assert.equal(r.url, `?run=${r.run}`);
      seen.push(r.run);
    }
    assert.ok(new Set(seen).size >= 2, `three visits, at least two runs (${seen})`);
  } finally { b.close(); server.close(); }
});

test("RR2 a run in the address replays it, and run 0 is the old run", { skip }, async () => {
  const server = await serve(); const b = await chrome();
  try {
    await b.send("Page.enable");
    const a = await floorAt(server, b, "index.html?run=4721#floor"); const fa = await finishedAt(b, 2000);
    const c = await floorAt(server, b, "index.html?run=4721#floor"); const fc = await finishedAt(b, 2000);
    assert.equal(a.run, 4721); assert.equal(c.run, 4721);
    assert.equal(a.moves, c.moves, "the same moves"); assert.equal(fa, fc, "the same lots finished on day 2");
    const z = await floorAt(server, b, "index.html?run=0#floor");
    assert.equal(z.run, 0); assert.equal(z.moves, 70131, "run 0: the old run's moves");
  } finally { b.close(); server.close(); }
});

test("RR3 New run on the Floor plays another run", { skip }, async () => {
  const server = await serve(); const b = await chrome();
  try {
    await b.send("Page.enable");
    const a = await floorAt(server, b, "index.html?run=4721#floor");
    await b.ev(`document.getElementById("new-run").click(), 1`);
    let r = null;
    for (let i = 0; i < 300; i++) { await b.sleep(100); r = JSON.parse(await b.ev(`JSON.stringify({ run: FabFloorPage.runNumber(), moves: FabFloorPage.moves(), full: document.body.dataset.floor, label: document.getElementById("run-no").textContent, url: location.search })`)); if (r.run !== 4721 && r.moves) break; }
    assert.notEqual(r.run, 4721);
    assert.match(r.label, new RegExp(`Run #${r.run}\\b`)); assert.equal(r.url, `?run=${r.run}`);
    assert.notEqual(r.moves, a.moves, "a different run arrived");
  } finally { b.close(); server.close(); }
});

// ---------------------------------------------------------------- Build, with a helper of its own
async function openEditor() {
  const DIR = ROOT;
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--no-model", "--runs", mkdtempSync(join(tmpdir(), "test-runs-")), "--port", String(hp)], { cwd: DIR, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("runs-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  const key = async (k, code) => { await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code }); };
  await send("Page.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `window.__runs = []; const f0 = window.fetch; window.fetch = (u, o) => { try { if (String(u).includes("/api/fab/run")) window.__runs.push(JSON.parse(o.body).seed); } catch (e) {} return f0(u, o); };` });
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}

const wafersCard = (p) => p.ev(`document.querySelector("#score .sc .n").textContent.replace(/[^0-9]/g, "")`);

test("RR4 Build watches run #1 first; New run changes the run watched, and the score stays run #1's", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    assert.equal(await p.ev("FabEditorPage.watching()"), 1, "run #1 at first");
    const w1 = await wafersCard(p);
    assert.ok(+w1 > 0);
    const n = await p.ev("FabEditorPage.runs()");
    await p.ev(`document.getElementById("new-run").click(), 1`);
    for (let i = 0; i < 300; i++) { await sleep(100); if ((await p.ev("FabEditorPage.runs()")) > n) break; }
    await sleep(300);
    const watched = await p.ev("FabEditorPage.watching()");
    assert.ok(watched >= 2 && watched <= 9999, `another run watched (${watched})`);
    assert.equal(await wafersCard(p), w1, "the score cards keep run #1's wafers a day");
    const line = await p.ev(`document.getElementById("watching").textContent`);
    assert.match(line, new RegExp(`run #${watched}\\b`)); assert.match(line, /wafers a day/); assert.match(line, /run #1/);
  } finally { p.close(); }
});

test("RR5 an edit after New run runs the run watched and run #1, and nothing else", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const n = await p.ev("FabEditorPage.runs()");
    await p.ev(`document.getElementById("new-run").click(), 1`);
    for (let i = 0; i < 300; i++) { await sleep(100); if ((await p.ev("FabEditorPage.runs()")) > n) break; }
    const watched = await p.ev("FabEditorPage.watching()");
    await p.ev("window.__runs = [], 1");
    const n2 = await p.ev("FabEditorPage.runs()");
    const r = await p.ev(`(async () => { const g = FabEditorPage.blocks().find(b => b.kind === "group"); return JSON.stringify(await FabEditorTools.call("set_machines", { group: g.group, count: g.count + 1 })); })()`);
    assert.match(r, /"ok":true/, r);
    for (let i = 0; i < 300; i++) { await sleep(100); if ((await p.ev("FabEditorPage.runs()")) > n2) break; }
    await sleep(300);
    const seeds = JSON.parse(await p.ev("JSON.stringify(window.__runs)"));
    assert.deepEqual([...new Set(seeds)].sort((a, b) => a - b), [1, watched].sort((a, b) => a - b), `asked for runs ${seeds}`);
    assert.equal(await p.ev("FabEditorPage.watching()"), watched, "still watching the same run");
  } finally { p.close(); }
});
