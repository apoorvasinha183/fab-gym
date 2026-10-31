// Floor: Legend and Fab status (docs/FLOOR-NAMES.md). Written before the code. On a teaching fab of our own and the
// SMT2020 testbed; not a real fab.
//
//     node --test web/tests/floornames.test.mjs   (needs Google Chrome)

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
  const prof = profileDir("review-");
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


// the Floor with its full run and moods in, paused, at a given size
async function floor(w = 1440, h = 1000) {
  const server = await serve();
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await b.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/index.html#floor` });
  for (let i = 0; i < 600; i++) { await b.sleep(100); if (await b.ev(`document.body && document.body.dataset.floor === "full" && document.body.dataset.moods === "in"`)) break; }
  await b.ev(`(() => { if (document.getElementById("play").textContent.includes("❚")) document.getElementById("play").click(); return 1; })()`);
  const at = async (t) => { await b.ev(`(() => { const s = document.getElementById("scrub"); s.value = ${t}; s.dispatchEvent(new Event("input", { bubbles: true })); return 1; })()`); await b.sleep(250); };
  const health = async () => JSON.parse(await b.ev("JSON.stringify(FabFloorPage.health())"));
  const text = async (sel) => b.ev(`(document.querySelector(${JSON.stringify(sel)}) || {}).textContent || ""`);
  return { ...b, at, health, text, close: () => { b.close(); server.close(); } };
}
const click = (p, sel) => p.ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; e.click(); return true; })()`);

const reload = async (p) => { await p.send("Page.reload"); for (let i = 0; i < 300; i++) { await p.sleep(100); if (await p.ev(`document.body && document.body.dataset.floor === "full"`)) break; } };

test("FN1 the panels are called Legend and Fab status, and the old titles are gone", { skip }, async () => {
  const p = await floor();
  try {
    assert.equal(await p.ev(`document.querySelector("#key .hp-title").textContent.replace(/[▾\s]+$/, "").trim()`), "Legend");
    assert.equal(await p.ev(`document.querySelector("#health .hp-title").textContent.replace(/[▾\s]+$/, "").trim()`), "Fab status");
    const text = await p.ev(`document.documentElement.outerHTML`);
    assert.ok(!/What the marks mean/i.test(text), "no 'What the marks mean'");
    assert.ok(!/The fab now/i.test(text), "no 'The fab now'");
  } finally { p.close(); }
});

test("FN2 Fab status folds, the map takes the room, and the browser remembers", { skip }, async () => {
  const p = await floor();
  try {
    const before = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.mapMiddle())"));
    assert.equal(await click(p, "#health-fold"), true, "a fold button");
    await p.sleep(300);
    assert.equal(await p.ev(`document.getElementById("health").classList.contains("folded")`), true);
    assert.equal(await p.ev(`document.getElementById("health-fold").getAttribute("aria-expanded")`), "false");
    assert.equal(await p.ev(`[...document.querySelectorAll("#health > :not(.hp-title)")].filter(e => e.getClientRects().length).length`), 0, "only the title shows");
    const after = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.mapMiddle())"));
    assert.ok(after[2] >= before[2], "the map is no narrower");
    await reload(p);
    assert.equal(await p.ev(`document.getElementById("health").classList.contains("folded")`), true, "still folded after a reload");
    await click(p, "#health-fold"); await p.sleep(200);
    assert.equal(await p.ev(`document.getElementById("health").classList.contains("folded")`), false, "open again");
    await reload(p);
    assert.equal(await p.ev(`document.getElementById("health").classList.contains("folded")`), false, "open after a reload");
  } finally { p.close(); }
});
