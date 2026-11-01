// Build: every machine in reach, every control in view, part 1 (docs/BUILD-CONTROLS.md). Written before the code.
// On a teaching fab of our own, built from the SMT2020 testbed's shapes; not a real fab.
//
//     node --test web/tests/buildcontrols.test.mjs   (needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync as rmProfile } from "node:fs";
// headless Chrome profiles: made per browser, removed when this file's tests end, so test runs cannot fill the disk
const PROFILES = [];
const profileDir = (prefix) => { const d = mkdtempSync(join(tmpdir(), prefix)); PROFILES.push(d); return d; };
process.on("exit", () => { for (const d of PROFILES) { try { rmProfile(d, { recursive: true, force: true }); } catch { /* already gone */ } } });

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");
const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const skip = !ready && "needs Google Chrome and the .venv";
async function openEditor(path = "editor.html?ch=1", w = 1440, h = 1000, stars = null) {
  const hp = 8800 + Math.floor(Math.random() * 600);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, `--window-size=${w},${h}`, "--hide-scrollbars", `--user-data-dir=${profileDir("build-")}`, "about:blank"], { stdio: "ignore" });
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

const J = async (p, e) => JSON.parse(await p.ev(`JSON.stringify(${e})`));
const until = async (p, cond, ms = 8000) => { for (let t = 0; t < ms; t += 100) { if (await p.ev(cond)) return true; await sleep(100); } return false; };
const chTab = async (p, k) => { const r0 = await p.ev("FabEditorPage.runs()"); await p.ev(`document.querySelectorAll("#chtabs button")[${k}].click()`); await until(p, `FabEditorPage.runs() > ${r0}`, 8000); await sleep(300); };
const KINDS = ["Lithography", "Litho metrology", "Dry etch", "Wet etch and clean", "Diffusion", "Dielectric", "Thin film", "Thin film metrology", "Ion implant", "Polishing (CMP)", "Defect inspection"];
// each challenge's levers (docs/BUILD-CONTROLS.md), in order; free build has none
const LEVERS = [
  ["The broken track: when it stops", "Cap on lots inside"],
  ["Polishing (CMP) machines", "Polishing (CMP): when it breaks", "Cap on lots inside"],
  ["Lithography machines", "Lithography: when it breaks"],
  ["Polishing (CMP) machines", "Polishing (CMP): when it breaks", "Cap on lots inside"],
  [],
];
const LEVER_KINDS = [[], ["Polishing (CMP)"], ["Lithography"], ["Polishing (CMP)"], []];
const ROUTE = ["Diffusion", "Lithography", "Litho metrology", "Dry etch", "Wet etch and clean", "Thin film", "Thin film metrology", "Polishing (CMP)", "Defect inspection",
  "Ion implant", "Lithography", "Litho metrology", "Dry etch", "Wet etch and clean", "Dielectric", "Polishing (CMP)", "Defect inspection", "Wet etch and clean"];
const MINUTES = [50, 40, 12, 35, 25, 30, 10, 35, 14, 18, 40, 12, 35, 25, 20, 35, 14, 25];
const machines = (p) => J(p, `[...document.querySelectorAll("#pal [data-kind]")].map(b => { const r = b.getBoundingClientRect(), path = b.querySelector("svg path");
  return { kind: b.dataset.kind, name: (b.getAttribute("aria-label") || "").split(":")[0], label: b.getAttribute("aria-label") || "", d: path ? path.getAttribute("d") : null,
    icon: path ? path.getAttribute("d") === FabLook.ICONS[b.dataset.kind] : false, fam: getComputedStyle(b).getPropertyValue("--fam").trim(), famWant: FabLook.FAM[b.dataset.kind],
    n: (b.querySelector(".n") || {}).textContent || "", img: !!b.querySelector("img"), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height),
    lever: b.classList.contains("lever"), locked: b.disabled || b.classList.contains("locked") }; })`);

test("BC1 every machine in the palette as its map icon, with its count; even rows; the levers' kinds marked, none locked", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1", 1440, 900);
  try {
    for (let k = 0; k < 5; k++) {
      if (k) await chTab(p, k);
      await sleep(400);
      const ms = await machines(p), blocks = await J(p, "FabEditorPage.blocks()");
      assert.deepEqual(ms.map((m) => m.name), KINDS, `tab ${k}: the 11 kinds in order`);
      for (const m of ms) {
        const on = blocks.filter((b) => b.kind === "group" && b.area === m.kind).reduce((a, b) => a + b.count, 0);
        assert.ok(m.icon, `tab ${k} ${m.name}: the map's icon`);
        assert.equal(m.fam.toLowerCase(), m.famWant.toLowerCase(), `tab ${k} ${m.name}: the area's colour`);
        assert.equal(m.img, false, `tab ${k} ${m.name}: no cartoon in the key`);
        assert.equal(m.n.trim(), String(on), `tab ${k} ${m.name}: its count as the badge`);
        assert.match(m.label, new RegExp(`${on} on the floor`), `tab ${k} ${m.name}: its count in its label`);
        assert.match(m.label, /\$\d+(\.\d)?M/, `tab ${k} ${m.name}: its price in its label`);
        assert.equal(m.locked, false, `tab ${k} ${m.name}: nothing is locked`);
        assert.equal(m.lever, LEVER_KINDS[k].includes(m.name), `tab ${k} ${m.name}: marked as a lever only if a lever names it`);
      }
      assert.equal(new Set(ms.map((m) => `${m.w}x${m.h}`)).size, 1, `tab ${k}: every key one size`);
      assert.ok(Math.abs(ms[0].w - ms[0].h) <= 2, `tab ${k}: square keys`);
      assert.ok(new Set(ms.map((m) => m.x)).size >= 3, `tab ${k}: three or more to a row`);
      const rows = new Set(ms.map((m) => m.y));
      for (const y of rows) assert.ok(ms.filter((m) => m.y === y).length >= 1, "rows");
    }
  } finally { p.close(); }
});

test("BC8 pointing at a machine key shows its cartoon card; leaving hides it", { skip }, async () => {
  const p = await openEditor("editor.html?ch=2", 1440, 900);
  try {
    const r = await J(p, `(() => { const b = document.querySelector('#pal [data-kind="cmp"]').getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; })()`);
    await p.mouse("mouseMoved", r.x, r.y); await sleep(300);
    const card = await J(p, `(() => { const c = document.getElementById("palcard"); if (!c || c.hidden) return null; const im = c.querySelector("img"); return { img: im ? im.getAttribute("src") : "", ok: !!(im && im.complete && im.naturalWidth), text: c.innerText }; })()`);
    assert.ok(card, "the card shows");
    assert.match(card.img, /^cast\/base\/\d\d-cmp\.webp$/, "the kind's cartoon");
    assert.ok(card.ok, "the cartoon loads");
    const on = (await J(p, "FabEditorPage.blocks()")).filter((b) => b.kind === "group" && b.area === "cmp").reduce((a, b) => a + b.count, 0);
    assert.match(card.text, /Polishing \(CMP\)/);
    assert.match(card.text, new RegExp(`${on} on the floor`));
    assert.match(card.text, /\$5M/);
    await p.mouse("mouseMoved", 700, 450); await sleep(300);
    assert.equal(await p.ev(`document.getElementById("palcard").hidden`), true, "leaving hides it");
  } finally { p.close(); }
});

test("BC9 the map's card over the lowest machine is whole: inside the window and every box that hides overflow", { skip }, async () => {
  for (const [w, h] of [[1440, 900], [1280, 720]]) {
    const p = await openEditor("editor.html?ch=1", w, h);
    try {
      await sleep(400);
      const pt = await J(p, `(() => { const g = FabEditorPage.blocks().filter(b => b.kind === "group"); let best = null;
        for (const b of g) { const s = FabEditorPage.screenOf(b.x + (b.w - 1) / 2, b.y + (b.h - 1) / 2); if (!best || s[1] > best[1]) best = s; } return best; })()`);
      await p.mouse("mouseMoved", pt[0] - 3, pt[1] - 3); await sleep(150);
      await p.mouse("mouseMoved", pt[0], pt[1]); await sleep(400);
      const o = await J(p, `(() => { const c = document.getElementById("hover"); if (!c || c.hidden) return null; const r = c.getBoundingClientRect(); const cut = [];
        for (let e = c.parentElement; e && e !== document.documentElement; e = e.parentElement) { const s = getComputedStyle(e); if (/hidden|clip|auto|scroll/.test(s.overflow + s.overflowX + s.overflowY)) { const q = e.getBoundingClientRect(); if (r.top < q.top - 1 || r.bottom > q.bottom + 1 || r.left < q.left - 1 || r.right > q.right + 1) cut.push(e.id || e.className); } }
        return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, h: r.height, cut }; })()`);
      assert.ok(o, `${w} x ${h}: the card shows`);
      assert.ok(o.h > 100, `${w} x ${h}: a whole card`);
      assert.ok(o.top >= 0 && o.left >= 0 && o.bottom <= h && o.right <= w, `${w} x ${h}: inside the window (${JSON.stringify(o)})`);
      assert.deepEqual(o.cut, [], `${w} x ${h}: no box cuts it`);
    } finally { p.close(); }
  }
});

test("BC2 BC3 a machine in the palette opens its controls; the panel's three tabs; All controls changes the fab as + does", { skip }, async () => {
  const p = await openEditor("editor.html?ch=2", 1440, 900);
  try {
    await sleep(400);
    await p.ev(`document.querySelector('#pal [data-kind="cmp"]').click(), 1`); await sleep(300);
    assert.equal(await p.ev(`document.querySelector('#ctl-tabs [data-tab="sel"]').getAttribute("aria-selected")`), "true", "the Selected tab opens");
    assert.match(await p.ev(`document.getElementById("insp").innerText`), /Polishing \(CMP\)/, "on the polishing group");
    const tabs = await J(p, `[...document.querySelectorAll("#ctl-tabs [data-tab]")].map(b => b.textContent.trim())`);
    assert.deepEqual(tabs, ["Selected", "Whole fab", "All controls"]);
    await p.ev(`document.querySelector('#ctl-tabs [data-tab="fab"]').click(), 1`); await sleep(200);
    // only the open tab's panel shows
    const shown = (id) => p.ev(`document.getElementById("${id}").getClientRects().length > 0`);
    assert.deepEqual([await shown("insp"), await shown("ctl-fab"), await shown("ctl-all")], [false, true, false], "Whole fab alone shows");
    const fab = await p.ev(`document.getElementById("ctl-fab").innerText`);
    assert.match(fab, /Cars on the track/); assert.match(fab, /Cap on lots inside/);
    await p.ev(`document.querySelector('#ctl-tabs [data-tab="all"]').click(), 1`); await sleep(200);
    assert.deepEqual([await shown("insp"), await shown("ctl-fab"), await shown("ctl-all")], [false, false, true], "All controls alone shows");
    const groups = await J(p, `FabEditorPage.blocks().filter(b => b.kind === "group").map(b => b.group)`);
    const rows = await J(p, `[...document.querySelectorAll("#ctl-all tr[data-group]")].map(r => r.dataset.group)`);
    assert.deepEqual(rows.slice().sort(), groups.slice().sort(), "a row per machine group");
    const before = await J(p, `FabEditorPage.blocks().find(b => b.group === "Litho_T").count`);
    await p.ev(`document.querySelector('#ctl-all tr[data-group="Litho_T"] [data-up]').click(), 1`); await sleep(400);
    assert.equal(await J(p, `FabEditorPage.blocks().find(b => b.group === "Litho_T").count`), before + 1, "one more machine");
    assert.match(await p.ev("FabEditorPage.fab()"), new RegExp(`group\\tLitho_T\\t${before + 1}\\t`), "the next fab file has it");
    await p.ev(`document.querySelector('#pal [data-kind="litho"]').click(), 1`); await sleep(300);
    assert.match(await p.ev(`document.querySelector("#insp .count b").textContent`), new RegExp(`^${before + 1}$`), "Selected shows the same count");
  } finally { p.close(); }
});

test("BC4 each challenge's levers open their control and light it", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1", 1440, 900);
  try {
    for (let k = 0; k < 5; k++) {
      if (k) await chTab(p, k);
      await sleep(300);
      const lv = await J(p, `[...document.querySelectorAll("#levers button")].map(b => b.textContent.trim())`);
      assert.equal(lv.length, LEVERS[k].length, `tab ${k}: ${JSON.stringify(lv)}`);
      LEVERS[k].forEach((want, i) => assert.ok(lv[i].startsWith(want), `tab ${k}: lever ${i} is "${want}" (${lv[i]})`));
      for (let i = 0; i < lv.length; i++) {
        await p.ev(`document.querySelectorAll("#levers button")[${i}].click(), 1`); await sleep(250);
        const lit = await J(p, `(() => { const e = document.querySelector(".ctlrow.lit"); if (!e) return null; const r = e.getBoundingClientRect(); return { text: e.innerText, shown: r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight }; })()`);
        assert.ok(lit && lit.shown, `tab ${k} lever ${i}: its control is lit and in view`);
      }
    }
  } finally { p.close(); }
});

test("BC5 every control says what it does", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1", 1440, 900);
  try {
    await sleep(400);
    const check = async (where) => {
      const rows = await J(p, `[...document.querySelectorAll("${where} .ctlrow")].map(r => (r.querySelector(".why") || {}).textContent || "")`);
      assert.ok(rows.length > 0, `${where}: controls`);
      for (const w of rows) assert.ok(w.trim().length > 12, `${where}: a line on what it does ("${w}")`);
    };
    await p.ev(`document.querySelector('#pal [data-kind="litho"]').click(), 1`); await sleep(250);
    await check("#insp");
    await p.ev(`document.querySelector('#ctl-tabs [data-tab="fab"]').click(), 1`); await sleep(200);
    await check("#ctl-fab");
    await p.ev(`document.querySelector('#ctl-tabs [data-tab="all"]').click(), 1`); await sleep(200);
    await check("#ctl-all");
  } finally { p.close(); }
});

test("BC6 About shows the fab's 18 steps in order, and how many a real product takes", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1", 1440, 900);
  try {
    await p.ev(`document.getElementById("about").open = true, 1`); await sleep(200);
    const steps = await J(p, `[...document.querySelectorAll("#process li")].map(li => ({ name: (li.querySelector(".nm") || {}).textContent, min: (li.querySelector(".mn") || {}).textContent }))`);
    assert.deepEqual(steps.map((s) => s.name), ROUTE, "the 18 steps in order");
    assert.deepEqual(steps.map((s) => parseInt(s.min, 10)), MINUTES, "each step's minutes");
    assert.match(await p.ev(`document.getElementById("about").innerText`), /583/, "a real product's 583 steps");
  } finally { p.close(); }
});

for (const [w, h] of [[1440, 900], [1440, 760], [1280, 720]]) {
  test(`BC7 at ${w} x ${h} the page does not scroll`, { skip }, async () => {
    const p = await openEditor("editor.html?ch=2", w, h);
    try {
      await sleep(600);
      const o = await J(p, `({ sh: document.documentElement.scrollHeight, ih: innerHeight, sw: document.documentElement.scrollWidth, iw: innerWidth })`);
      assert.ok(o.sh <= o.ih + 1, `no vertical scroll (${o.sh} against ${o.ih})`);
      assert.ok(o.sw <= o.iw + 1, `no sideways scroll (${o.sw} against ${o.iw})`);
    } finally { p.close(); }
  });
}
