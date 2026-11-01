// The glossary, part 2: live numbers from the run on screen, and Show me (docs/GLOSSARY-PLUS.md). Written before the
// code. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/glossarylive.test.mjs   (needs Google Chrome)

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
  const prof = profileDir("glp-");
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


const F = (b, e) => b.ev(`(() => { const F = window.FabFloorPage; return ${e}; })()`);
const fmt = (n) => Number(n).toLocaleString("en-US");
async function paused(b) {
  // the floor plays on its own; pause it so a number can be read against the Floor's at one moment
  const t0 = await F(b, "F.time()"); await b.sleep(300);
  if ((await F(b, "F.time()")) !== t0) await b.ev(`document.getElementById("play").click(), 1`);
  await b.sleep(300);
}
async function article(b, term) {
  await b.ev(`(() => { const s = document.getElementById("gl-search"); if (s) { s.value = ""; s.dispatchEvent(new Event("input")); } const el = document.querySelector('#gl-index [data-term="${term}"]'); el.click(); return 1; })()`);
  await b.sleep(250);
  return b.ev(`(() => { const l = document.getElementById("gl-live"); return l && !l.hidden ? l.innerText : null; })()`);
}
const litArea = async (b, area) => F(b, `(() => { const out = []; for (let k = 0; k < F.tools(); k++) if (!F.isStorage(F.toolGroup(k)) && F.areaOfTool(k) === "${area}") out.push(k); return out; })()`);

test("GL1 Breakdown, Setup change, WIP and Lithography each say what the run on screen is doing", { skip }, async () => {
  const b = await floorAt("index.html?term=Breakdown");
  try {
    await paused(b);
    const h = await F(b, "F.health()");
    let line = await article(b, "Breakdown");
    assert.ok(line && line.includes(fmt(h.tools.down)), `Breakdown: ${line} (down ${h.tools.down})`);
    line = await article(b, "Setup change");
    assert.ok(line && line.includes(fmt(h.tools.setup)), `Setup change: ${line} (setup ${h.tools.setup})`);
    line = await article(b, "WIP");
    assert.ok(line && line.includes(fmt(h.inFab)), `WIP: ${line} (in the fab ${h.inFab})`);
    const litho = await litArea(b, "litho");
    const working = (await F(b, `[${litho.join(",")}].filter(k => F.toolState(k) === 0).length`));
    line = await article(b, "Lithography");
    assert.ok(line && line.includes(fmt(litho.length)) && line.includes(fmt(working)), `Lithography: ${line} (${working} of ${litho.length})`);
  } finally { b.close(); }
});

test("GL2 Show me lights what the line counts: broken machines, an area's machines, groups where urgent lots wait", { skip }, async () => {
  const b = await floorAt("index.html?term=Breakdown");
  try {
    await paused(b);
    await article(b, "Breakdown");
    await b.ev(`document.querySelector("#gl-live [data-show]").click(), 1`); await b.sleep(250);
    assert.equal(await b.ev(`document.getElementById("dock").hidden`), true, "the glossary closes");
    let lit = await F(b, "F.lit()");
    const down = await F(b, `(() => { const out = []; for (let k = 0; k < F.tools(); k++) if (!F.isStorage(F.toolGroup(k)) && F.toolState(k) === 3) out.push(k); return out; })()`);
    assert.deepEqual(lit.tools, down, "exactly the machines broken down now");
    await b.ev(`document.getElementById("glossary-open") ? document.getElementById("glossary-open").click() : 0, 1`);
    await b.ev(`window.FabFloorPage.openGlossary("Lithography"), 1`); await b.sleep(250);
    await b.ev(`document.querySelector("#gl-live [data-show]").click(), 1`); await b.sleep(250);
    lit = await F(b, "F.lit()");
    assert.deepEqual(lit.tools, await litArea(b, "litho"), "that area's machines and no other");
    await b.ev(`window.FabFloorPage.openGlossary("Hot lot"), 1`); await b.sleep(250);
    await b.ev(`document.querySelector("#gl-live [data-show]").click(), 1`); await b.sleep(250);
    lit = await F(b, "F.lit()");
    assert.deepEqual(lit.groups, await F(b, "F.hotWaiting()"), "the groups where urgent lots wait");
  } finally { b.close(); }
});

test("GL3 a word the run cannot count has no Right now line", { skip }, async () => {
  const b = await floorAt("index.html?term=Bonferroni");
  try {
    await paused(b);
    assert.equal(await article(b, "Bonferroni"), null);
  } finally { b.close(); }
});

test("GL4 the number follows the clock", { skip }, async () => {
  const b = await floorAt("index.html?term=WIP");
  try {
    await paused(b);
    await article(b, "WIP");
    await b.ev(`document.getElementById("play").click(), 1`); await b.sleep(1500);
    await b.ev(`document.getElementById("play").click(), 1`); await b.sleep(1300);
    const h = await F(b, "F.health()");
    const line = await b.ev(`document.getElementById("gl-live").innerText`);
    assert.ok(line.includes(fmt(h.inFab)), `after playing on: ${line} (in the fab ${h.inFab})`);
  } finally { b.close(); }
});

test("GL5 Esc turns the light off", { skip }, async () => {
  const b = await floorAt("index.html?term=Breakdown");
  try {
    await paused(b);
    await article(b, "Breakdown");
    await b.ev(`document.querySelector("#gl-live [data-show]").click(), 1`); await b.sleep(250);
    assert.ok(await F(b, "F.lit()"), "lit");
    await b.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
    await b.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
    await b.sleep(200);
    assert.equal(await F(b, "F.lit()"), null, "off");
  } finally { b.close(); }
});
