// The glossary for newcomers and experts, part 1: pictures, figures and two depths (docs/GLOSSARY-PLUS.md). Written
// before the code. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/glossaryplus.test.mjs   (GP2 to GP5 need Google Chrome)

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

import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const G = require(join(WEB, "glossary.js"));

const FIGURES = ["Route", "Lot", "Dispatch rule", "Rework", "Defect hold", "Batch", "WIP cap", "Simulator", "Reinforcement learning",
  "E2 (evolutionary search)", "Tool", "Breakdown", "Repair time", "Queue-time limit", "Setup change", "Warm-up", "Window", "Hot lot",
  "Paired seeds", "95% interval", "Verdict", "WIP", "Cycle time"];
const FORMULAS = ["WIP", "Cycle time", "Paired seeds", "95% interval", "Bonferroni", "Net present value", "Payback", "Depreciation", "PPO"];
const REUSED = { "Wafer": "cast/base/12-wafer.webp", "Lithography": "cast/base/01-litho.webp", "Etch": "cast/base/03-dry.webp",
  "Polishing (CMP)": "cast/base/10-cmp.webp", "Checks (metrology)": "cast/base/02-lithomet.webp", "Lot": "cast/lots/fresh.webp",
  "Hot lot": "cast/lots/hot.webp", "Batch": "cast/lots/batch.webp", "Rework": "cast/lots/redo.webp", "Defect hold": "cast/lots/hold.webp",
  "Queue-time limit": "cast/lots/clock.webp", "Move": "cast/lots/ride.webp", "Breakdown": "cast/cmp/hurt.webp",
  "Repair time": "cast/cmp/physio.webp", "Setup change": "cast/cmp/setup.webp" };
const words = (s) => s.trim().split(/\s+/).filter(Boolean).length;

/** A WebP file's width and height from its header (VP8, VP8L or VP8X). */
function webpSize(b) {
  if (b.toString("ascii", 0, 4) !== "RIFF" || b.toString("ascii", 8, 12) !== "WEBP") return null;
  const kind = b.toString("ascii", 12, 16);
  if (kind === "VP8X") return { w: 1 + b.readUIntLE(24, 3), h: 1 + b.readUIntLE(27, 3) };
  if (kind === "VP8L") { const v = b.readUInt32LE(21); return { w: 1 + (v & 0x3fff), h: 1 + ((v >> 14) & 0x3fff) }; }
  if (kind === "VP8 ") return { w: b.readUInt16LE(26) & 0x3fff, h: b.readUInt16LE(28) & 0x3fff };
  return null;
}

test("GP1 every term has a newcomer line of 1 to 20 words ending in a full stop, not its definition", () => {
  for (const t of G.TERMS) {
    assert.equal(typeof t.plain, "string", `${t.term}: a newcomer line`);
    const n = words(t.plain);
    assert.ok(n >= 1 && n <= 20, `${t.term}: ${n} words`);
    assert.ok(/\.$/.test(t.plain.trim()), `${t.term}: ends in a full stop`);
    assert.notEqual(t.plain.trim(), t.meaning.trim(), `${t.term}: different from its definition`);
  }
});

test("GP2 every term has a WebP picture of at most 60 KB and 384 px, reused from the cast where the spec says", () => {
  for (const t of G.TERMS) {
    assert.equal(typeof t.picture, "string", `${t.term}: a picture`);
    assert.ok(/^(glossary|cast)\//.test(t.picture), `${t.term}: in web/glossary or web/cast (${t.picture})`);
    if (REUSED[t.term]) assert.equal(t.picture, REUSED[t.term], `${t.term}: reuses the cast's picture`);
    else assert.ok(t.picture.startsWith("glossary/"), `${t.term}: a new picture in web/glossary`);
    const p = join(WEB, t.picture);
    assert.ok(existsSync(p), `${t.term}: ${t.picture} exists`);
    const b = readFileSync(p), s = webpSize(b);
    assert.ok(s, `${t.term}: WebP`);
    assert.ok(b.length <= 60 * 1024, `${t.term}: ${b.length} bytes`);
    assert.ok(s.w <= 384, `${t.term}: ${s.w} px wide`);
  }
});

test("GP6 pictures.json names a prompt for every new picture and the cast file for every reused one", () => {
  const J = JSON.parse(readFileSync(join(WEB, "glossary", "pictures.json"), "utf8"));
  for (const t of G.TERMS) {
    const e = J.terms[t.term];
    assert.ok(e, `${t.term}: listed`);
    if (REUSED[t.term]) assert.equal(e.reused, REUSED[t.term], `${t.term}: names the cast file`);
    else { assert.ok(typeof e.prompt === "string" && e.prompt.length > 40, `${t.term}: a prompt`); assert.equal(e.file, t.picture, `${t.term}: its file`); }
  }
  assert.ok(Array.isArray(J.references) && J.references.length >= 1, "the references are named");
});

test("GP3 the figures' terms draw an SVG figure with a caption, labels inside, no boxes overlapping (data)", () => {
  const F = require(join(WEB, "glossary-figs.js"));
  for (const name of FIGURES) {
    const t = G.TERMS.find((x) => x.term === name);
    assert.ok(t && t.figure, `${name}: names a figure`);
    const f = F.FIGS[t.figure];
    assert.ok(f, `${name}: figure ${t.figure} exists`);
    assert.ok(typeof f.caption === "string" && f.caption.length > 10, `${name}: a caption`);
    assert.ok(/^<svg[\s\S]*<\/svg>$/.test(F.draw(t.figure).trim()), `${name}: draws as SVG`);
  }
});

test("GP3 GP4 GP5 in the page: pictures, figures that fit, the expert fold, and the lead in view at 1,440 x 760", { skip }, async () => {
  const p = await floorAt("index.html?run=12#floor", 1440, 760);
  try {
    const out = JSON.parse(await p.ev(`(async () => {
      const res = [];
      for (const t of FabGlossary.TERMS) {
        openGlossary(t.term);
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        const a = document.getElementById("gl-article"), img = a.querySelector("img.gl-pic"), plain = a.querySelector(".gl-plain"), h = a.querySelector("h3");
        const inView = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth; };
        const fig = a.querySelector("figure.gl-fig"), svg = fig && fig.querySelector("svg");
        let labelsOut = 0, overlaps = 0, labelsOverBox = 0;
        if (svg) {
          const vb = svg.viewBox.baseVal;
          for (const tx of svg.querySelectorAll("text")) { const b = tx.getBBox(); if (b.x < vb.x - 0.5 || b.y < vb.y - 0.5 || b.x + b.width > vb.x + vb.width + 0.5 || b.y + b.height > vb.y + vb.height + 0.5) labelsOut++; }
          const boxes = [...svg.querySelectorAll("g.node")].map(g => { const r = g.querySelector("rect,ellipse,circle,polygon"); return { g, b: r.getBBox() }; });
          for (const { g, b } of boxes) for (const tx of g.querySelectorAll("text")) { const t2 = tx.getBBox(); if (t2.x < b.x - 0.5 || t2.x + t2.width > b.x + b.width + 0.5) labelsOverBox++; }
          for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) { const A = boxes[i].b, B = boxes[j].b;
            if (A.x < B.x + B.width - 0.5 && B.x < A.x + A.width - 0.5 && A.y < B.y + B.height - 0.5 && B.y < A.y + A.height - 0.5) overlaps++; }
        }
        const ex = a.querySelector("details.gl-expert");
        const above = ex ? [...a.children].slice(0, [...a.children].indexOf(ex)) : [...a.children];
        res.push({ term: t.term, img: !!img && img.complete && img.naturalWidth > 0, alt: img ? img.alt : "", src: img ? img.getAttribute("src") : "",
          plain: plain ? plain.textContent.trim() : "", leadInView: inView(img) && inView(h) && inView(plain),
          fig: !!svg, caption: fig && fig.querySelector("figcaption") ? fig.querySelector("figcaption").textContent.trim() : "", labelsOut, overlaps, labelsOverBox,
          expert: !!ex, expertOpen: ex ? ex.open : null, def: ex ? !!ex.querySelector(".gl-def") : false, src2: ex ? !!ex.querySelector(".gl-src") : false,
          formula: ex ? !!ex.querySelector(".gl-formula") : false, srcAbove: above.some(el => el.querySelector && (el.matches(".gl-src") || el.querySelector(".gl-src"))) });
      }
      return JSON.stringify(res);
    })()`));
    assert.equal(out.length, G.TERMS.length);
    for (const r of out) {
      const t = G.TERMS.find((x) => x.term === r.term);
      assert.ok(r.img, `${r.term}: the picture loads`);
      assert.equal(r.src, t.picture, `${r.term}: its own picture`);
      assert.equal(r.alt, t.plain, `${r.term}: the newcomer line is the alt text`);
      assert.equal(r.plain, t.plain, `${r.term}: the newcomer line shows`);
      assert.ok(r.leadInView, `${r.term}: picture, term and newcomer line in view`);
      assert.equal(r.fig, FIGURES.includes(r.term), `${r.term}: a figure where the spec says`);
      if (r.fig) {
        assert.ok(r.caption.length > 10, `${r.term}: a caption`);
        assert.equal(r.labelsOut, 0, `${r.term}: labels inside the figure`);
        assert.equal(r.labelsOverBox, 0, `${r.term}: labels inside their boxes`);
        assert.equal(r.overlaps, 0, `${r.term}: no boxes overlap`);
      }
      assert.ok(r.expert && r.expertOpen === false, `${r.term}: a closed expert fold`);
      assert.ok(r.def && r.src2, `${r.term}: the fold holds the definition and where it comes from`);
      assert.equal(r.formula, FORMULAS.includes(r.term), `${r.term}: a formula where the spec says`);
      assert.ok(!r.srcAbove, `${r.term}: no source label above the fold`);
    }
  } finally { p.close(); }
});
