// The Floor after review (docs/FLOOR-REVIEW.md). Written before the code. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/floorreview.test.mjs   (needs Google Chrome)

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
const num = (s) => Number(String(s).replace(/[^0-9.]/g, ""));


// OKLab distance x100, normal and under the three colour blindnesses (Machado 2009, full severity)
const CVD = { normal: null,
  protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
  tritan: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]] };
function oklab(h, m) {
  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  let [r, g, b] = [1, 3, 5].map((i) => lin(parseInt(h.slice(i, i + 2), 16) / 255));
  if (m) [r, g, b] = m.map((row) => Math.min(1, Math.max(0, row[0] * r + row[1] * g + row[2] * b)));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), mm = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b), s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * mm - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * mm + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * mm - 0.808675766 * s];
}
const dE = (a, b, m) => { const p = oklab(a, CVD[m]), q = oklab(b, CVD[m]); return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]); };
const boxOf = (p, sel) => p.ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return JSON.stringify({ l: r.left, t: r.top, r: r.right, b: r.bottom }); })()`).then((s) => (s ? JSON.parse(s) : null));
const overlaps = (x, y) => x.l < y.r && y.l < x.r && x.t < y.b && y.t < x.b;
const click = (p, sel) => p.ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; e.click(); return true; })()`);

test("FR1 one strip for actions: Try a change by the ask bar, Glossary by How a chip is made, Follow one lot in the panel", { skip }, async () => {
  const p = await floor();
  try {
    const ask = await boxOf(p, "#cmd"), tryc = await boxOf(p, "#change-open");
    assert.ok(ask && tryc, "the ask bar and Try a change are shown");
    assert.ok(Math.abs((ask.t + ask.b) / 2 - (tryc.t + tryc.b) / 2) < 8 && tryc.l >= ask.r, "Try a change sits on the ask bar's row, after it");
    const how = await boxOf(p, "#stages-open"), glo = await boxOf(p, "#glossary-open");
    assert.ok(how && glo && Math.abs(how.t - glo.t) < 8, "Glossary sits beside How a chip is made");
    assert.match(await p.text("#glossary-open"), /Glossary/);
    assert.equal(await p.ev(`!!document.querySelector("#health #follow-open")`), true, "Follow one lot is in the panel");
    assert.equal(await p.ev(`!!document.getElementById("rail")`), false, "no rail is left");
    for (const s of ["#key", "#health", ".brand", "footer.bar"]) { const b = await boxOf(p, s); if (b) assert.ok(!overlaps(b, tryc) && !overlaps(b, ask), `the strip clears ${s}`); }
    await click(p, "#change-open"); await p.sleep(400);
    assert.equal(await p.ev(`!document.getElementById("dock").hidden && /change/i.test(document.getElementById("dock").textContent)`), true, "Try a change opens its panel");
    await click(p, "#glossary-open"); await p.sleep(400);
    assert.equal(await p.ev(`!document.getElementById("dock").hidden && /What the words mean/.test(document.getElementById("dock").textContent)`), true, "Glossary opens the glossary");
  } finally { p.close(); }
});

test("FR1b on Home the Floor's strip, map buttons and panels stay hidden", { skip }, async () => {
  const server = await serve(); const b = await chrome();
  try {
    await b.send("Page.enable");
    await b.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/index.html#home` });
    for (let i = 0; i < 300; i++) { await b.sleep(100); if (await b.ev(`document.body && document.body.classList.contains("opening-on") && !!window.FabFloorPage`)) break; }
    await b.sleep(800);
    const shown = JSON.parse(await b.ev(`JSON.stringify(["#topbar", "#change-open", "#maptools", "#health", "#key"].filter(s => { const e = document.querySelector(s); return e && e.getClientRects().length && getComputedStyle(e).visibility !== "hidden"; }))`));
    assert.deepEqual(shown, [], "nothing of the Floor's on Home");
  } finally { b.close(); server.close(); }
});

test("FR2 the play bar's chart is drawn at its size, with a line across it", { skip }, async () => {
  const p = await floor();
  try {
    const r = JSON.parse(await p.ev(`JSON.stringify((() => { const c = document.getElementById("spark"), dpr = devicePixelRatio || 1, x = c.getContext("2d");
      const W = c.width, H = c.height; if (!W || !H) return { W, H, want: Math.round(c.clientWidth * dpr), cols: 0 };
      const d = x.getImageData(0, 0, W, H).data; let cols = 0;
      for (let i = 0; i < W; i++) { for (let j = 0; j < H; j++) if (d[(j * W + i) * 4 + 3] > 0) { cols++; break; } }
      return { W, H, want: Math.round(c.clientWidth * dpr), cols }; })())`));
    assert.ok(r.W > 0 && r.W === r.want, `the canvas is its drawn size (${r.W} against ${r.want})`);
    assert.ok(r.cols >= r.W / 2, `a line across at least half (${r.cols} of ${r.W} columns)`);
  } finally { p.close(); }
});

test("FR3 every count in Output says lots or wafers", { skip }, async () => {
  const p = await floor();
  try {
    await p.at(2000);
    const labels = JSON.parse(await p.ev(`JSON.stringify([...[...document.querySelectorAll("#health .hp-sec")].find(s => /Output/.test(s.querySelector("h3").textContent)).querySelectorAll(".row .nm, .hp-big .u")].map(e => e.textContent))`));
    assert.ok(labels.length >= 3);
    for (const l of labels) assert.match(l, /lots|wafers/, `"${l}" names its unit`);
  } finally { p.close(); }
});

test("FR4 an Areas key for all eleven areas, and area colours kept apart from the state lights", { skip }, async () => {
  const p = await floor();
  try {
    const key = await p.text("#key");
    assert.match(key, /Areas/);
    const names = JSON.parse(await p.ev(`JSON.stringify(Object.values(FabLook.AREA).map(a => a.name))`));
    assert.equal(names.length, 11);
    for (const n of names) assert.ok(key.includes(n), `the key names ${n}`);
    const mats = JSON.parse(await p.ev(`JSON.stringify(FabLook.MAT)`)), states = JSON.parse(await p.ev(`JSON.stringify(FabFloorPage.stateLights())`));
    assert.deepEqual(Object.keys(mats).sort(), Object.keys(JSON.parse(await p.ev(`JSON.stringify(FabLook.AREA)`))).sort(), "a mat for every area");
    for (const [a, ac] of Object.entries(mats)) for (const [s, sc] of Object.entries(states)) for (const m of Object.keys(CVD))
      assert.ok(dE(ac, sc, m) >= 12, `${a} ${ac} and ${s} ${sc} are ${dE(ac, sc, m).toFixed(1)} apart (${m})`);
    const distinct = [...new Set(Object.values(mats))];
    for (let i = 0; i < distinct.length; i++) for (let j = i + 1; j < distinct.length; j++)
      assert.ok(dE(distinct[i], distinct[j], "normal") >= 7, `${distinct[i]} and ${distinct[j]} are ${dE(distinct[i], distinct[j], "normal").toFixed(1)} apart`);
    assert.equal(await p.ev(`FabFloorPage.toolTop(0) === FabLook.MAT[FabFloorPage.areaOfTool(0)]`), true, "the map draws tools in their mat");
  } finally { p.close(); }
});

test("FR5 the panel points: a state lights its machines, waiting lights its groups, the longest queue is flown to", { skip }, async () => {
  const p = await floor();
  try {
    await p.at(2000);
    await click(p, '#health [data-spot="s3"]'); await p.sleep(200);
    const lit = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.lit())"));
    const down = (await p.health()).tools.down;
    assert.equal(lit.tools.length, down, "as many lit as are broken down");
    assert.equal(await p.ev(`FabFloorPage.lit().tools.every(k => FabFloorPage.toolState(k) === 3)`), true, "each lit tool is broken down");
    await click(p, '#health [data-spot="s3"]'); await p.sleep(200);
    assert.equal(await p.ev("FabFloorPage.lit()"), null, "a second click clears it");
    await click(p, '#health [data-spot="waiting"]'); await p.sleep(200);
    const groups = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.lit().groups)"));
    const want = JSON.parse(await p.ev(`JSON.stringify([...Array(FabFloorPage.groups()).keys()].filter(g => FabFloorPage.queueNow(g) > 0 && !FabFloorPage.isStorage(g)))`));
    assert.deepEqual(groups.sort((a, b) => a - b), want, "the groups with lots waiting");
    await click(p, '#health [data-spot="waiting"]');
    const g = await p.ev(`FabFloorPage.longestGroup()`);
    await click(p, '#health [data-spot="longest"]'); await p.sleep(1800);
    const at = JSON.parse(await p.ev(`JSON.stringify(FabFloorPage.screenOfGroup(${g}))`)), mid = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.mapMiddle())"));
    assert.ok(Math.abs(at[0] - mid[0]) < 0.12 * mid[2] && Math.abs(at[1] - mid[1]) < 0.12 * mid[3], `the longest queue's group is in the middle (${at} against ${mid})`);
  } finally { p.close(); }
});

test("FR6 the map's buttons do what their keys do, and Running badges wait for a hover", { skip }, async () => {
  const p = await floor();
  try {
    const s0 = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.view())")).s;
    await click(p, "#zoom-in"); await p.sleep(150);
    const s1 = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.view())")).s;
    assert.ok(s1 > s0, "zoom in");
    await click(p, "#zoom-out"); await click(p, "#zoom-out"); await p.sleep(150);
    assert.ok(JSON.parse(await p.ev("JSON.stringify(FabFloorPage.view())")).s < s1, "zoom out");
    await click(p, "#fit-map"); await p.sleep(150);
    assert.ok(Math.abs(JSON.parse(await p.ev("JSON.stringify(FabFloorPage.view())")).s - s0) < 1e-6, "fit is the first view");
    const t0 = await p.ev("FabFloorPage.tilted()");
    await click(p, "#tilt-map"); await p.sleep(150);
    assert.equal(await p.ev("FabFloorPage.tilted()"), !t0, "tilt");
    for (const s of ["#key", "#health", "footer.bar", "#cmd"]) { const a = await boxOf(p, "#maptools"), b = await boxOf(p, s); if (a && b) assert.ok(!overlaps(a, b), `the map's buttons clear ${s}`); }
    await p.at(2000);
    for (let i = 0; i < 6; i++) await click(p, "#zoom-in"); // group labels and badges show only zoomed in
    await p.sleep(400);
    const drawn = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.badgesDrawn())"));
    assert.ok(drawn.length > 0, "some badges are drawn");
    assert.ok(!drawn.includes("work"), "no Running badge with nothing hovered");
  } finally { p.close(); }
});

test("FR7 the same hour yesterday, on day 2 and not on day 1", { skip }, async () => {
  const p = await floor();
  try {
    await p.at(2000 - 1440); const y = await p.health();
    await p.at(2000); const h = await p.health();
    assert.ok(h.ago, "a comparison on day 2");
    assert.equal(h.ago.waiting, y.waiting); assert.equal(h.ago.available, y.available); assert.equal(h.ago.waitHour, y.waitHour);
    const panel = await p.text("#health");
    const dw = h.waiting - y.waiting;
    assert.ok(panel.includes(`${dw > 0 ? "▲" : dw < 0 ? "▼" : "="} ${Math.abs(dw).toLocaleString("en-US")}`), `the change in lots waiting (${dw}) shows`);
    assert.match(panel, /yesterday/);
    await p.at(600); const d1 = await p.health();
    assert.equal(d1.ago, null);
    assert.equal(await p.ev(`document.querySelectorAll("#health .dl:not([hidden])").length`), 0, "no comparison on day 1");
  } finally { p.close(); }
});

test("FR8 the legend folds, the map takes the room, and the browser remembers", { skip }, async () => {
  const p = await floor();
  try {
    const before = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.mapMiddle())"));
    await click(p, "#key-fold"); await p.sleep(300);
    assert.equal(await p.ev(`document.getElementById("key").classList.contains("folded")`), true);
    const after = JSON.parse(await p.ev("JSON.stringify(FabFloorPage.mapMiddle())"));
    assert.ok(after[2] > before[2], "the map is wider");
    await p.send("Page.reload"); for (let i = 0; i < 300; i++) { await p.sleep(100); if (await p.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
    assert.equal(await p.ev(`document.getElementById("key").classList.contains("folded")`), true, "still folded after a reload");
    await click(p, "#key-fold"); await p.sleep(200);
    await p.send("Page.reload"); for (let i = 0; i < 300; i++) { await p.sleep(100); if (await p.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
    assert.equal(await p.ev(`document.getElementById("key").classList.contains("folded")`), false, "open again after unfolding");
  } finally { p.close(); }
});
