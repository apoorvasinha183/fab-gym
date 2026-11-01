// One bar for anything, on the Floor (docs/ONE-BAR.md: OB1 to OB6). Written before the code. The helper runs with
// --no-model; a recorded pick stands in for Muse Spark, so nothing is spent. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/onebar.test.mjs   (OB3 to OB6 need Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync } from "node:fs";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
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
const require = createRequire(import.meta.url);
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");

// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper(extra = []) {
  const port = 8800 + Math.floor(Math.random() * 400);
  const p = spawn(PY, ["-m", "agent.helper", "--no-model", "--port", String(port), "--runs", profileDir("ob-runs-"), ...extra], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/editor.html`)).ok) return { port, close: () => p.kill() }; } catch { /* not up yet */ }
    await sleep(100);
  }
  p.kill();
  throw new Error("the helper did not start");
}

async function chrome() {
  const port = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, "--window-size=1440,1000", "--hide-scrollbars",
    `--user-data-dir=${profileDir("ob-")}`, "about:blank"], { stdio: "ignore" });
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
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  // modifiers: 2 Ctrl, 8 Shift
  const key = async (k, code, modifiers = 0) => {
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, modifiers, windowsVirtualKeyCode: k.toUpperCase().charCodeAt(0) });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, modifiers });
  };
  return { send, ev, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); } };
}

const SKIP = !ready && "needs Google Chrome and the .venv";

const A = require(join(HERE, "..", "ask.js"));
const STAND_IN = join(HERE, "fixtures", "onebar");

// ---------------------------------------------------------------- in Node, on ask.js

test("OB1 the rules route questions to their kinds, with what each needs", () => {
  const r = (q) => A.route(q);
  assert.deepEqual(r("open challenge 2"), { kind: "go", to: { page: "build", ch: 2 } });
  assert.deepEqual(r("take me to Build"), { kind: "go", to: { page: "build", ch: null } });
  assert.deepEqual(r("open simulation settings"), { kind: "go", to: { tab: "change" } });
  assert.deepEqual(r("go to the glossary"), { kind: "go", to: { tab: "glossary" } });
  assert.deepEqual(r("open Q-0002"), { kind: "go", to: { run: "Q-0002" } });
  assert.deepEqual(r("show me S-0001"), { kind: "go", to: { run: "S-0001" } });
  assert.deepEqual(r("show me the longest line"), { kind: "go", to: { show: "Tool group" } });
  assert.deepEqual(r("show me the broken machines"), { kind: "go", to: { show: "Breakdown" } });
  assert.deepEqual(r("take me to Planar_FE_79"), { kind: "go", to: { group: "Planar_FE_79" } });
  assert.equal(r("double the breakdowns").kind, "change");
  assert.equal(r("what if breakdowns double?").kind, "change", "a what-if whose change reads is a change");
  assert.deepEqual(r("How many machines are broken right now?"), { kind: "now", term: "Breakdown" });
  assert.deepEqual(r("Why is lithography backed up?"), { kind: "now", term: "Lithography" });
  assert.deepEqual(r("where is the longest line?"), { kind: "now", term: "Tool group" });
  assert.deepEqual(r("how many lots are waiting?"), { kind: "now", term: "WIP" });
  assert.deepEqual(r("What's a WIP cap?"), { kind: "words" });
  assert.deepEqual(r("Why do lots wait so long at the polisher?"), { kind: "words" });
  assert.deepEqual(r("What if we hired more operators?"), { kind: "whatif" });
  for (const q of ["Prototype orders double next quarter. Do we give them their own wing or put them first in line?",
    "Polisher group Planar_FE_79 is down for a shift tomorrow morning. Which dispatch rule should we run?",
    "If breakdowns get 50% worse, does holding prototype lots at the door protect the volume product?"])
    assert.equal(r(q).kind, "whatif", q);
  assert.deepEqual(r("make the fab sing"), { kind: "unsure" });
});

test("OB2 changes are read from words; a value beyond its setting's range is marked", () => {
  const c = (q) => A.parseChange(q);
  assert.deepEqual(c("double the breakdowns").dials, { breakdowns: 2 });
  assert.deepEqual(c("halve the breakdowns").dials, { breakdowns: 0.5 });
  assert.deepEqual(c("breakdowns x2").dials, { breakdowns: 2 });
  assert.deepEqual(c("2x breakdowns").dials, { breakdowns: 2 });
  assert.deepEqual(c("breakdowns 50% worse").dials, { breakdowns: 1.5 });
  assert.deepEqual(c("no breakdowns").dials, { breakdowns: 0 });
  assert.deepEqual(c("repairs take twice as long").dials, { repair: 2 });
  assert.deepEqual(c("demand up 20%").dials, { demand: 1.2 });
  assert.deepEqual(c("20% fewer urgent lots").dials, { hot: 0.8 });
  assert.deepEqual(c("no urgent lots").dials, { hot: 0 });
  assert.deepEqual(c("triple the rework").dials, { rework: 3 });
  assert.deepEqual(c("quality holds on").dials, { defects: 1 });
  assert.deepEqual(c("cap lots at 2400").dials, { cap: 2400 });
  assert.equal(c("use first come, first served").rule, 1);
  assert.equal(c("switch to quickest job first").rule, 2);
  assert.deepEqual(c("take Planar_FE_79 down for 8 hours").outage, { group: "Planar_FE_79", at: 0, hours: 8 });
  assert.deepEqual(c("Planar_FE_79 down for 8 hours from hour 30").outage, { group: "Planar_FE_79", at: 30, hours: 8 });
  assert.match(c("double the breakdowns").words, /breakdowns ×2/i);
  assert.deepEqual(c("demand x3").over, ["demand"], "demand goes to ×1.5 at most");
  assert.equal(c("make the fab sing"), null);
});

// ---------------------------------------------------------------- the Floor, with a helper and no model

async function floorWith(extra) {
  const h = await helper(extra);
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Page.navigate", { url: `http://127.0.0.1:${h.port}/index.html?run=3#floor` });
  for (let i = 0; i < 300; i++) { await sleep(100); if (await b.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
  // paused, so a number can be read against the Floor's at one moment
  const t0 = await b.ev("FabFloorPage.time()"); await sleep(300);
  if ((await b.ev("FabFloorPage.time()")) !== t0) await b.ev(`document.getElementById("play").click(), 1`);
  await sleep(300);
  const ask = async (q) => {
    await b.ev(`(() => { const c = document.getElementById("bar-card"); if (c) c.hidden = true; const i = document.getElementById("cmd-q"); i.value = ${JSON.stringify(q)}; document.getElementById("cmd").requestSubmit(); return 1; })()`);
    for (let i = 0; i < 80; i++) { await sleep(100); if (await b.ev(`!!(document.getElementById("bar-card") && !document.getElementById("bar-card").hidden)`)) break; }
    await sleep(150);
  };
  const card = () => b.ev(`(() => { const c = document.getElementById("bar-card"); return c && !c.hidden ? { text: c.innerText, acts: [...c.querySelectorAll("[data-act]")].map(x => x.dataset.act) } : null; })()`);
  const act = (a) => b.ev(`document.querySelector('#bar-card [data-act="${a}"]').click(), 1`);
  return { b, h, ask, card, act, close: () => { b.close(); h.close(); } };
}

test("OB3 right now: the Floor's own count, and Show me lights it", { skip: SKIP }, async () => {
  const { b, ask, card, act, close } = await floorWith([]);
  try {
    await ask("How many machines are broken right now?");
    const h = await b.ev("FabFloorPage.health()"), c = await card();
    assert.ok(c && c.text.includes(Number(h.tools.down).toLocaleString("en-US")), `${c && c.text} (down ${h.tools.down})`);
    assert.match(c.text, /live floor/i, "where it came from");
    await act("show"); await sleep(250);
    const lit = await b.ev("FabFloorPage.lit()");
    const down = await b.ev(`(() => { const F = FabFloorPage, out = []; for (let k = 0; k < F.tools(); k++) if (!F.isStorage(F.toolGroup(k)) && F.toolState(k) === 3) out.push(k); return out; })()`);
    assert.deepEqual(lit.tools, down);
  } finally { close(); }
});

test("OB4 take me there: a challenge, a panel, a run's card, the longest line", { skip: SKIP }, async () => {
  const { b, h, ask, close } = await floorWith([]);
  try {
    const rec = await (await fetch(`http://127.0.0.1:${h.port}/api/runs/record`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "floor", key: "ob4", title: "Today's fab, run #3", link: "index.html?run=3#floor", summary: { columns: [], rows: [] } }) })).json();
    await ask("show me the longest line");
    assert.equal(await b.ev("FabFloorPage.flownTo()"), (await b.ev("FabFloorPage.health()")).longest.g, "flies to the longest line");
    await ask("open simulation settings");
    assert.equal(await b.ev(`!document.getElementById("pane-change").hidden && !document.getElementById("dock").hidden`), true, "Simulation settings open");
    await ask(`open ${rec.id}`);
    for (let i = 0; i < 50 && !(await b.ev(`location.pathname.endsWith("runs.html")`)); i++) await sleep(100);
    assert.equal(await b.ev("location.pathname.endsWith('runs.html') && location.hash"), `#run=${rec.id}`, "the run's card");
    await b.send("Page.navigate", { url: `http://127.0.0.1:${h.port}/index.html?run=3#floor` });
    for (let i = 0; i < 300; i++) { await sleep(100); if (await b.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
    await ask("open challenge 2");
    for (let i = 0; i < 50 && !(await b.ev(`location.pathname.endsWith("editor.html")`)); i++) await sleep(100);
    assert.equal(await b.ev("location.pathname.endsWith('editor.html') && location.search"), "?ch=2", "Build on challenge 2");
  } finally { close(); }
});

test("OB5 a change is a proposal: nothing changes until Apply, and Cancel leaves it all", { skip: SKIP }, async () => {
  const { b, ask, card, act, close } = await floorWith([]);
  try {
    await ask("double the breakdowns");
    const c = await card();
    assert.match(c.text, /breakdowns ×2/i); assert.ok(c.acts.includes("apply") && c.acts.includes("cancel"), c.acts.join());
    assert.equal(await b.ev(`document.getElementById("d-breakdowns").value`), "1", "nothing changed yet");
    await act("apply"); await sleep(400);
    assert.equal(await b.ev(`document.getElementById("d-breakdowns").value`), "2", "Apply sets it");
    assert.match(await b.ev(`document.getElementById("cmp-what").textContent`), /breakdowns ×2/i, "and compares it with today");
    await ask("cap lots at 2400");
    await act("cancel"); await sleep(200);
    assert.equal(await b.ev(`document.getElementById("d-cap").value`), "3600", "Cancel leaves the cap as it was");
    assert.equal(await b.ev(`document.getElementById("bar-card").hidden`), true);
  } finally { close(); }
});

test("OB6 a what-if that reads as a change is a proposal; an unsure question follows the model's pick, or says what the bar can do", { skip: SKIP }, async () => {
  let s = await floorWith([]);
  try {
    await s.ask("what if breakdowns get 50% worse?");
    assert.match((await s.card()).text, /breakdowns ×1\.5/i);
    await s.ask("how is the fab feeling about its lots");
    const c = await s.card();
    assert.match(c.text, /no model/i); assert.match(c.text, /what's a WIP cap|how many|open challenge|double the breakdowns/i, "examples of what it can do");
  } finally { s.close(); }
  s = await floorWith(["--stand-in", STAND_IN]);
  try {
    await s.ask("how is the fab feeling about its lots");
    const h = await s.b.ev("FabFloorPage.health()"), c = await s.card();
    assert.ok(c.text.includes(Number(h.inFab).toLocaleString("en-US")), `the recorded pick (right now, WIP) is followed: ${c.text}`);
  } finally { s.close(); }
});
