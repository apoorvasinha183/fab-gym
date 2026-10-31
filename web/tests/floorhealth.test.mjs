// The floor's health panel and legend (docs/FLOOR-HEALTH.md). Written before the code. On the SMT2020 testbed; not a
// real fab.
//
//     node --test web/tests/floorhealth.test.mjs   (needs Google Chrome)

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
  const prof = profileDir("health-");
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

test("FH1 the health panel: output, lots in the fab, tools, availability and the longest queue, adding up", { skip }, async () => {
  const p = await floor();
  try {
    await p.at(1500);
    const h = await p.health();
    const tools = h.tools.working + h.tools.idle + h.tools.setup + h.tools.maintenance + h.tools.down;
    assert.equal(tools, 1043, "the five tool counts cover every tool");
    assert.equal(h.waiting + h.processing + h.moving + h.resting, h.inFab, "the lot parts add up to the lots in the fab");
    assert.ok(h.inFab > 500 && h.waiting > 0 && h.processing > 0, JSON.stringify(h));
    assert.ok(h.finished > 0 && h.wafersOut === h.finished * 25, "wafers out are the finished lots' wafers");
    assert.ok(h.available > 0 && h.available <= 1 && h.busy > 0 && h.busy <= 1);
    assert.ok(h.longest.lots > 0 && h.longest.name);
    const panel = await p.text("#health");
    for (const [label, v] of [["finished", h.finished], ["in the fab", h.inFab], ["waiting", h.waiting], ["processed", h.processing],
      ["moving", h.moving], ["storage", h.resting], ["working", h.tools.working], ["idle", h.tools.idle], ["setup", h.tools.setup],
      ["maintenance", h.tools.maintenance], ["broken down", h.tools.down]]) {
      assert.match(panel, new RegExp(label, "i"), `the panel names ${label}`);
      assert.ok(panel.includes(v.toLocaleString("en-US")), `the panel shows ${label}: ${v}`);
    }
    assert.ok(panel.includes(`${Math.round(h.available * 100)}%`), "availability as a share");
    assert.ok(panel.includes(h.longest.name) && panel.includes(String(h.longest.lots)), "the longest queue by name");
    assert.match(panel, /wait for a tool, last hour/i); assert.ok(h.waitHour > 0, "the mean wait for a tool over the last hour");
    assert.match(panel, /broke down|is back up/, "the latest events moved to the panel");
  } finally { p.close(); }
});

test("FH2 the numbers follow the clock", { skip }, async () => {
  const p = await floor();
  try {
    await p.at(1500); const a = await p.health(); const pa = await p.text("#health");
    await p.at(3000); const b = await p.health(); const pb = await p.text("#health");
    assert.ok(b.finished >= a.finished && b.finished > 0);
    assert.notEqual(pa, pb, "the panel changed");
    assert.ok(b.last24 > 0, "lots finished in the last 24 hours");
  } finally { p.close(); }
});

test("FH3 at the very end of the run the lots waiting are those just before closing", { skip }, async () => {
  const p = await floor();
  try {
    const end = await p.ev("FabFloorPage.end()");
    await p.at(end - 1); const before = await p.health();
    await p.at(end); const last = await p.health();
    assert.ok(last.waiting > 0, "lots still wait at the end");
    assert.ok(Math.abs(last.waiting - before.waiting) <= 0.02 * before.waiting, `${last.waiting} at the end against ${before.waiting} a minute before`);
    assert.ok(num(await p.text("#health")) > 0);
  } finally { p.close(); }
});

test("FH4 the legend: three sections, ten badges by what they mean, no gym words on the Floor", { skip }, async () => {
  const p = await floor();
  try {
    const key = await p.text("#key");
    for (const h of ["Tool light", "Group badge", "Lots"]) assert.match(key, new RegExp(h), `section ${h}`);
    const facts = ["Running", "Under 30% busy", "Over 90% busy", "Output full", "Filling a batch", "Changing setup", "Planned maintenance",
      "Just broke down", "Under repair", "On hold"];
    for (const f of facts) assert.ok(key.includes(f), `badge ${f}`);
    assert.match(key, /last 8 hours/, "the rules are given");
    const gym = JSON.parse(await p.ev(`JSON.stringify([...Object.values(FabLook.MOOD).map(m => m.name), ...Object.values(FabLook.AREA).map(a => a.exercise)])`));
    const cards = await p.ev(`(() => { let s = ""; for (let g = 0; g < FabFloorPage.groups(); g++) s += FabFloorPage.cardText(g) + "\\n"; return s; })()`);
    const floorText = [key, await p.text("#health"), cards].join("\n").toLowerCase();
    for (const w of gym) assert.ok(!floorText.includes(w.toLowerCase()), `no "${w}" on the Floor`);
  } finally { p.close(); }
});

for (const [w, h] of [[1440, 1000], [1280, 800]]) {
  test(`FH5 layout at ${w} x ${h}: labels on one line, nothing overlapping, both panels in the window`, { skip }, async () => {
    const p = await floor(w, h);
    try {
      const r = JSON.parse(await p.ev(`JSON.stringify((() => {
        const box = (sel) => { const e = document.querySelector(sel); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return { sel, l: r.left, t: r.top, r: r.right, b: r.bottom }; };
        const wrapped = [...document.querySelectorAll("#key li, #health .row")].filter(li => { const s = getComputedStyle(li); const lh = parseFloat(s.lineHeight) || parseFloat(s.fontSize) * 1.3; return [...li.querySelectorAll(".nm")].some(n => n.getBoundingClientRect().height > lh * 1.6); }).map(li => li.textContent.trim().slice(0, 40));
        return { boxes: ["#key", "#health", ".cmd", "#rail", "footer.bar"].map(box), wrapped, W: innerWidth, H: innerHeight };
      })())`));
      assert.deepEqual(r.wrapped, [], "no label wraps");
      const b = r.boxes.filter(Boolean);
      assert.ok(b.find(x => x.sel === "#key") && b.find(x => x.sel === "#health"), "both panels are shown");
      for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++) {
        const x = b[i], y = b[j], over = x.l < y.r && y.l < x.r && x.t < y.b && y.t < x.b;
        assert.ok(!over, `${x.sel} and ${y.sel} overlap`);
      }
      for (const x of b) assert.ok(x.l >= 0 && x.t >= 0 && x.r <= r.W && x.b <= r.H, `${x.sel} fits in the window`);
    } finally { p.close(); }
  });
}
