// Live curves (docs/CURVES.md). Written before the code. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/curves.test.mjs   (needs Google Chrome; CU5 the .venv too)

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
  const prof = profileDir("curv-");
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


async function floorAt(path, w = 1440, h = 760) {
  const server = await serve();
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await b.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${path}` });
  for (let i = 0; i < 300; i++) { await b.sleep(100); if (await b.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
  await b.sleep(400);
  return { ...b, close: () => { b.close(); server.close(); } };
}
const PY = join(WEB, "..", ".venv", "bin", "python");
const ROOT = join(WEB, "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ready = !skip && existsSync(PY);
async function openEditor(path = "editor.html?ch=1", w = 1440, h = 1000, stars = null) {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--runs", mkdtempSync(join(tmpdir(), "test-runs-")), "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, `--window-size=${w},${h}`, "--hide-scrollbars", `--user-data-dir=${profileDir("curv-")}`, "about:blank"], { stdio: "ignore" });
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
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  if (stars) await send("Page.addScriptToEvaluateOnNewDocument", { source: `try { localStorage.setItem("fabgym.stars", ${JSON.stringify(JSON.stringify(stars))}); } catch (e) {}` });
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/${path}` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}


// every chart in the open drawer: its name, latest value, how many lines, where its first line ends and where now is
const CHARTS = `JSON.stringify([...document.querySelectorAll("#curves .curve")].map(c => { const s = c.querySelector("svg"), ls = [...s.querySelectorAll("polyline.series")];
  const end = ls.length ? +ls[0].getAttribute("points").trim().split(/\\s+/).pop().split(",")[0] : null, now = s.querySelector("line.now");
  return { name: c.dataset.name, last: +c.dataset.last, lines: ls.length, end, now: now ? +now.getAttribute("x1") : null, key: (c.querySelector(".key") || {}).textContent || "" }; }))`;
const scrub = (p, t) => p.ev(`(() => { const s = document.getElementById("scrub"); s.value = ${t}; s.dispatchEvent(new Event("input", { bubbles: true })); return 1; })()`);
const pause = (p) => p.ev(`(() => { if (document.getElementById("play").textContent.includes("❚")) document.getElementById("play").click(); return 1; })()`);

test("CU1 the Floor's Curves button opens four charts and closes them", { skip }, async () => {
  const p = await floorAt("index.html?run=12#floor");
  try {
    assert.equal(await p.ev(`document.getElementById("curves").hidden`), true, "closed at first");
    await p.ev(`document.getElementById("curves-open").click(), 1`); await p.sleep(300);
    const c = JSON.parse(await p.ev(CHARTS));
    assert.deepEqual(c.map(x => x.name), ["Lots waiting", "Lots finished", "Wait for a tool, last hour", "Tools working"]);
    await p.ev(`document.getElementById("curves-open").click(), 1`); await p.sleep(200);
    assert.equal(await p.ev(`document.getElementById("curves").hidden`), true, "closed again");
  } finally { p.close(); }
});

test("CU2 and CU3 the lines end at now, and their latest values agree with the health panel", { skip }, async () => {
  const p = await floorAt("index.html?run=12#floor");
  try {
    await pause(p); await p.ev(`document.getElementById("curves-open").click(), 1`);
    await scrub(p, 2000); await p.sleep(500);
    const c = JSON.parse(await p.ev(CHARTS)), h = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.health())"));
    for (const x of c) assert.ok(Math.abs(x.end - x.now) <= 2, `${x.name}: the line ends at now (${x.end} against ${x.now})`);
    const by = Object.fromEntries(c.map(x => [x.name, x.last]));
    assert.equal(by["Lots waiting"], h.waiting);
    assert.equal(by["Lots finished"], h.finished);
    assert.ok(Math.abs(by["Tools working"] - h.tools.working / h.nT) < 1e-9, `${by["Tools working"]} against ${h.tools.working}/${h.nT}`);
    assert.ok(Math.abs(by["Wait for a tool, last hour"] - (h.waitHour || 0)) < 1e-6);
  } finally { p.close(); }
});

test("CU4 after a Simulation settings run, your settings are drawn over today", { skip }, async () => {
  const p = await floorAt("index.html?run=12#floor");
  try {
    await p.ev(`document.getElementById("change-open").click(), 1`); await p.sleep(500);
    await p.ev(`(() => { const r = document.querySelector("#pane-change input[type=range]"); r.value = "2"; r.dispatchEvent(new Event("input", { bubbles: true })); r.dispatchEvent(new Event("change", { bubbles: true })); document.getElementById("run").click(); return 1; })()`);
    for (let i = 0; i < 100; i++) { await p.sleep(200); if (await p.ev(`/run #12/.test(document.getElementById("runnote").textContent)`)) break; }
    await p.ev(`document.getElementById("dock-close").click(), 1`);
    await p.ev(`document.getElementById("curves-open").click(), 1`);
    let c = [];
    for (let i = 0; i < 50; i++) { await p.sleep(200); c = JSON.parse(await p.ev(CHARTS)); if (c.length && c.every(x => x.lines === 2)) break; }
    assert.equal(c.length, 4, "four charts");
    for (const x of c) { assert.equal(x.lines, 2, `${x.name} draws two lines`); assert.match(x.key, /today/); assert.match(x.key, /your settings/); }
  } finally { p.close(); }
});

test("CU5 in Build, Curves opens three charts that end at now, and the page still fits", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor("editor.html?ch=1", 1440, 760);
  try {
    await p.ev(`document.getElementById("curves-open").click(), 1`);
    await sleep(800);
    const c = JSON.parse(await p.ev(CHARTS));
    assert.deepEqual(c.map(x => x.name), ["Lots waiting", "Lots finished", "Tools busy"]);
    for (const x of c) assert.ok(Math.abs(x.end - x.now) <= 2, `${x.name}: ends at now (${x.end} against ${x.now})`);
    assert.ok((await p.ev(`document.documentElement.scrollHeight - innerHeight`)) <= 1, "no scroll");
  } finally { p.close(); }
});
