// Simulation settings (docs/SIM-SETTINGS.md). Written before the code. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/simsettings.test.mjs   (needs Google Chrome)

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
  const prof = profileDir("sett-");
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
const openSettings = async (p) => { await p.ev(`document.getElementById("change-open").click(), 1`); await p.sleep(500); };
const runIt = async (p) => {
  await p.ev(`(() => { const r = document.querySelector("#pane-change input[type=range]"); r.value = "2"; r.dispatchEvent(new Event("input", { bubbles: true })); r.dispatchEvent(new Event("change", { bubbles: true })); document.getElementById("run").click(); return 1; })()`);
  for (let i = 0; i < 200; i++) { await p.sleep(200); if (await p.ev(`document.querySelectorAll("#cmp-rows > *").length > 0`)) break; }
  await p.sleep(1200);
};

test("SS1 the name says what it is", { skip }, async () => {
  const p = await floorAt("index.html?run=12#floor");
  try {
    assert.match(await p.ev(`document.getElementById("change-open").textContent`), /Simulation settings/);
    await openSettings(p);
    assert.match(await p.ev(`document.getElementById("dock-title").textContent`), /Simulation settings/);
    assert.match(await p.ev(`document.getElementById("pane-change").innerText`), /Change a setting, then run it against today on the same 10 random days/);
    assert.ok(!/Try a change/.test(await p.ev(`document.body.innerText`)), "no Try a change shows");
  } finally { p.close(); }
});

test("SS2 the run on screen is the run it changes", { skip }, async () => {
  const p = await floorAt("index.html?run=4721#floor");
  try {
    await openSettings(p);
    assert.equal(await p.ev(`document.getElementById("seed").value`), "4721");
    await runIt(p);
    assert.match(await p.ev(`document.getElementById("runnote").textContent`), /run #4721\b/);
  } finally { p.close(); }
});

test("SS3 the answer comes into view", { skip }, async () => {
  const p = await floorAt("index.html?run=12#floor");
  try {
    await openSettings(p);
    await runIt(p);
    const r = JSON.parse(await p.ev(`JSON.stringify((() => { const a = document.querySelector("#cmp-rows > *").getBoundingClientRect(), d = document.getElementById("dock-body").getBoundingClientRect(); return { a: [a.top, a.bottom], d: [d.top, d.bottom], H: innerHeight }; })())`));
    assert.ok(r.a[0] >= r.d[0] - 1 && r.a[0] < r.d[1] - 20 && r.a[0] < r.H, `the first row is in view (${r.a} in ${r.d})`);
  } finally { p.close(); }
});
