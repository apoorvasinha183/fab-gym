// Floor: panels in the bottom corners (docs/FLOOR-CORNERS.md). Written before the code. On a teaching fab of our own and
// the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/floorcorners.test.mjs   (needs Google Chrome)

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

const box = (sel) => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e || !e.getClientRects().length || getComputedStyle(e).visibility === "hidden") return null; const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; })()`;
const PARTS = { brand: "header.brand", ask: "#cmd", settings: "#change-open", legend: "#key", status: "#health", bar: "footer.bar", maptools: "#maptools", hint: "#hint" };
const overlaps = (x, y) => x.l < y.r - 0.5 && y.l < x.r - 0.5 && x.t < y.b - 0.5 && y.t < x.b - 0.5;
async function layout(p) {
  return JSON.parse(await p.ev(`JSON.stringify({ w: innerWidth, h: innerHeight, ${Object.entries(PARTS).map(([k, s]) => `${k}: ${box(s)}`).join(", ")},
    tabs: [...document.querySelectorAll("header.brand .topnav a")].map(a => { const r = a.getBoundingClientRect(); return { name: a.textContent, l: r.left, t: r.top, r: r.right, b: r.bottom }; }),
    topbar: (() => { const r = document.getElementById("topbar").getBoundingClientRect(); return { b: r.bottom }; })() })`));
}
const fold = (p, open) => p.ev(`(() => { for (const [id, b] of [["key", "key-fold"], ["health", "health-fold"]]) { const folded = document.getElementById(id).classList.contains("folded"); if (folded === ${open}) document.getElementById(b).click(); } return 1; })()`);

for (const [w, h] of [[1280, 720], [1440, 900], [1920, 1080]]) {
  test(`FC1 FC2 FC3 at ${w} x ${h}: panels in the bottom corners, nothing overlapping, the tabs clear of the ask bar`, { skip }, async () => {
    const p = await floor(w, h);
    try {
      for (const open of [true, false]) {
        await fold(p, open); await p.sleep(400);
        const L = await layout(p), tag = `${w}x${h} ${open ? "open" : "folded"}`;
        assert.ok(L.legend && L.status, `${tag}: both panels show`);
        assert.ok(L.legend.l <= 24 && L.h - L.legend.b <= 24, `${tag}: the Legend in the bottom-left corner (${JSON.stringify(L.legend)})`);
        assert.ok(L.w - L.status.r <= 24 && L.h - L.status.b <= 24, `${tag}: Fab status in the bottom-right corner (${JSON.stringify(L.status)})`);
        const keys = Object.keys(PARTS).filter((k) => L[k]);
        for (let i = 0; i < keys.length; i++) for (let j = i + 1; j < keys.length; j++)
          assert.ok(!overlaps(L[keys[i]], L[keys[j]]), `${tag}: ${keys[i]} and ${keys[j]} overlap (${JSON.stringify(L[keys[i]])} ${JSON.stringify(L[keys[j]])})`);
        for (const k of ["legend", "status"]) assert.ok(L[k].t >= L.topbar.b + 4, `${tag}: ${k} stays below the top bar`);
        assert.ok(L.tabs.some((t) => t.name === "Runs"), `${tag}: a Runs tab`);
        for (const t of L.tabs) for (const k of ["ask", "settings"]) assert.ok(!overlaps(t, L[k]), `${tag}: the ${t.name} tab clear of ${k}`);
      }
    } finally { p.close(); }
  });
}
