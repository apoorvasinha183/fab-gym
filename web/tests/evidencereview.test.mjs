// Evidence after review (docs/EVIDENCE-REVIEW.md). Written before the code. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/evidencereview.test.mjs   (needs Google Chrome)

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
  const prof = profileDir("evid-");
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


import { createRequire } from "node:module";
const U = createRequire(import.meta.url)(join(WEB, "ui.js"));

// Evidence open, at a laptop browser's size
async function evidence(w = 1440, h = 760) {
  const server = await serve();
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await b.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/index.html#evidence` });
  for (let i = 0; i < 300; i++) { await b.sleep(100); if (await b.ev(`document.body && document.body.classList.contains("evidence-on") && document.querySelectorAll("#find-list .find").length >= 4 && document.querySelectorAll("#res-list details").length > 0`)) break; }
  await b.sleep(600);
  const J = async (e) => JSON.parse(await b.ev(`JSON.stringify(${e})`));
  return { ...b, J, close: () => { b.close(); server.close(); } };
}

test("EV1 the findings' bars cross a $0 line, in proportion to their values", { skip }, async () => {
  const p = await evidence();
  try {
    const rows = await p.J(`[...document.querySelectorAll("#find-list .bar-row")].map(r => { const t = r.querySelector(".bt"), i = r.querySelector(".bt i"), tr = t.getBoundingClientRect(), ir = i.getBoundingClientRect(); return { text: r.querySelector("b").textContent, zero: tr.left + tr.width * (+t.dataset.zero) / 100, l: ir.left, r: ir.right, w: ir.width }; })`);
    assert.ok(rows.length >= 3, "the bars");
    const val = (s) => (s.startsWith("−") ? -1 : 1) * parseFloat(s.replace(/[^0-9.]/g, "")) * (/M/.test(s) ? 1000 : 1);
    for (const r of rows) {
      const v = val(r.text);
      if (v > 0) assert.ok(r.l >= r.zero - 1, `${r.text} starts at the $0 line`); else assert.ok(r.r <= r.zero + 1, `${r.text} ends at the $0 line, to its left`);
    }
    const big = rows.reduce((a, r) => (Math.abs(val(r.text)) > Math.abs(val(a.text)) ? r : a));
    for (const r of rows) if (Math.abs(val(r.text)) > 20) assert.ok(Math.abs(r.w / big.w - Math.abs(val(r.text)) / Math.abs(val(big.text))) < 0.03, `${r.text} in proportion`);
  } finally { p.close(); }
});

test("EV2 badges use the filters' words, and each filter counts its runs", { skip }, async () => {
  const p = await evidence();
  try {
    const words = new Set(["study", "search", "training", "contest", "your change", "your question"]);
    const badges = await p.J(`[...document.querySelectorAll("#res-list .kind")].map(k => k.textContent.trim().toLowerCase())`);
    for (const b of badges) assert.ok(words.has(b), `badge "${b}" is a filter's word`);
    assert.ok(!/sweep/i.test(await p.ev(`document.getElementById("results").innerText`)), "no sweep");
    const filters = await p.J(`[...document.querySelectorAll("#res-kind button")].map(b => ({ k: b.dataset.k, t: b.textContent.trim() }))`);
    for (const f of filters) {
      const m = f.t.match(/\((\d+)\)$/);
      assert.ok(m, `"${f.t}" shows a count`);
      await p.ev(`document.querySelector('#res-kind button[data-k="${f.k}"]').click(), 1`); await p.sleep(150);
      assert.equal(await p.ev(`document.querySelectorAll("#res-list details").length`), +m[1], `${f.t}`);
    }
  } finally { p.close(); }
});

test("EV3 money in k and M, and no blank second line in the notebook", { skip }, async () => {
  assert.equal(U.usd3(8000), "$8k"); assert.equal(U.usd3(7527, true), "+$7.53k"); assert.equal(U.usd3(950), "$950");
  const p = await evidence();
  try {
    const cells = await p.J(`[...document.querySelectorAll("#numbers td.cg")].map(c => ({ b: c.querySelector("b").textContent, s: (c.querySelector("span") || {}).textContent || "" }))`);
    assert.ok(cells.length >= 10, "the grid's cells");
    for (const c of cells) { assert.ok(!/\$\d{1,3},\d{3}/.test(c.b), `${c.b} is in k or M`); assert.ok(c.s.trim().length > 0, `${c.b} has a second line`); }
  } finally { p.close(); }
});

test("EV4 a contest: one row per measure, a column for each contestant", { skip }, async () => {
  const p = await evidence();
  try {
    await p.ev(`document.querySelector('#res-kind button[data-k="contest"]').click(), 1`); await p.sleep(150);
    const t = await p.J(`(() => { const d = document.querySelector("#res-list details"); d.open = true; const tabs = d.querySelectorAll("table"); const tb = tabs[tabs.length - 1]; return { head: [...tb.querySelectorAll("thead th")].map(x => x.textContent), rows: [...tb.querySelectorAll("tbody tr")].map(r => r.querySelector("td").textContent) }; })()`);
    assert.ok(t.head.some(h => /trained AI/i.test(h)) && t.head.some(h => /evolved rule/i.test(h)), `a column each: ${t.head}`);
    assert.equal(new Set(t.rows).size, t.rows.length, "each measure once");
    assert.equal(t.rows.length, 5);
  } finally { p.close(); }
});

test("EV5 one scroll, no close button, and a contents bar that stays and jumps", { skip }, async () => {
  const p = await evidence();
  try {
    assert.equal(await p.ev(`(() => { const c = document.getElementById("dock-close"); return !c.getClientRects().length; })()`), true, "no close button");
    const inner = await p.J(`[...document.querySelectorAll("#dock-body *")].filter(e => { const s = getComputedStyle(e); return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1; }).map(e => e.id || e.className)`);
    assert.deepEqual(inner, [], "nothing inside scrolls on its own");
    const toc = await p.J(`(() => { const n = document.querySelector(".ev-toc"); return n && { pos: getComputedStyle(n).position, links: [...n.querySelectorAll("button")].map(b => b.textContent.trim()) }; })()`);
    assert.ok(toc, "a contents bar"); assert.equal(toc.pos, "sticky"); assert.deepEqual(toc.links, ["What we found", "Lab notebook", "Runs"]);
    for (const [i, id] of [[2, "results"], [1, "numbers"], [0, "findings"]]) {
      await p.ev(`document.querySelectorAll(".ev-toc button")[${i}].click(), 1`); await p.sleep(700);
      const r = await p.J(`(() => { const t = document.getElementById("${id}").getBoundingClientRect(), n = document.querySelector(".ev-toc").getBoundingClientRect(); return { t: t.top, n: n.bottom, toc: n.top }; })()`);
      assert.ok(Math.abs(r.t - r.n) < 40, `${id} is brought to the top (${Math.round(r.t)} under the bar at ${Math.round(r.n)})`);
    }
  } finally { p.close(); }
});

test("EV6 every finding links to its proof", { skip }, async () => {
  const p = await evidence();
  try {
    const n = await p.ev(`document.querySelectorAll("#find-list .find").length`);
    for (let i = 0; i < n; i++) {
      const t = await p.ev(`(() => { const b = document.querySelectorAll("#find-list .find")[${i}].querySelector(".find-proof"); if (!b) return null; b.click(); return b.dataset.jump; })()`);
      assert.ok(t, `finding ${i + 1} has a link`);
      await p.sleep(700);
      const vis = await p.ev(`(() => { const t = document.getElementById(document.querySelectorAll("#find-list .find")[${i}].querySelector(".find-proof").dataset.jump).getBoundingClientRect(); const d = document.getElementById("dock-body").getBoundingClientRect(); return t.top >= d.top - 2 && t.top < d.bottom - 40; })()`);
      assert.equal(vis, true, `finding ${i + 1}'s proof is in view`);
    }
  } finally { p.close(); }
});

test("EV7 the disclaimer once", { skip }, async () => {
  const p = await evidence();
  try {
    const text = await p.ev(`document.getElementById("dock-body").textContent`);
    assert.equal((text.match(/No real company's data is used/g) || []).length, 1, "said once");
    assert.ok(!/Run on a fab built from the SMT2020 testbed/.test(text), "the runs' notes are gone");
  } finally { p.close(); }
});

test("EV8 the subtitle on Evidence", { skip }, async () => {
  const p = await evidence();
  try {
    const sub = await p.ev(`document.querySelector(".brand .sub").innerText`);
    assert.ok(!/running live/i.test(sub), `subtitle: ${sub}`);
    assert.match(sub, /What the simulator found/);
  } finally { p.close(); }
});
