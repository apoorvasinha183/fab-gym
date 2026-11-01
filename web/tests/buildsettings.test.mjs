// Build: the Floor's settings in Build, part 4 (docs/BUILD-CONTROLS.md). Written before the code. On a teaching fab of
// our own, built from the SMT2020 testbed's shapes; not a real fab. Every hold length is assumed.
//
//     node --test web/tests/buildsettings.test.mjs   (needs a release build for BF5, Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync } from "node:fs";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";
import { rmSync as rmProfile } from "node:fs";
// headless Chrome profiles: made per browser, removed when this file's tests end, so test runs cannot fill the disk
const PROFILES = [];
const profileDir = (prefix) => { const d = mkdtempSync(join(tmpdir(), prefix)); PROFILES.push(d); return d; };
process.on("exit", () => { for (const d of PROFILES) { try { rmProfile(d, { recursive: true, force: true }); } catch { /* already gone */ } } });

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const E = require(join(HERE, "..", "editor-core.js"));
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");

// ---------------------------------------------------------------- in Node, on editor-core.js

const sha = (t) => createHash("sha256").update(t).digest("hex").slice(0, 16);
const fileOf = (x) => E.fabText(x.base, x.state, { vehicles: x.state.vehicles });
const free = () => ({ base: E.TEACHING_SHOP, state: { ...E.template("teaching"), inports: 2 } });
const withFlow = (x, flow) => ({ base: x.base, state: { ...x.state, flow } });
const lines = (t, kind) => t.split("\n").filter((l) => l.startsWith(kind + "\t")).map((l) => l.split("\t"));

// the fab files Build wrote before part 4 (sha256, first 16 hex), taken from editor-core.js at a00c146
const BEFORE = {
  "rush-start": "3e7ce30bc96293db", "rush-fix": "3e7ce30bc96293db", "polisher-start": "881a011036af20b8", "polisher-fix": "3e7ce30bc96293db",
  "breakdown-start": "3e7ce30bc96293db", "breakdown-fix": "3e7ce30bc96293db", "lean-start": "118fa09cfe2868bc", "lean-fix": "0657e0aa21afcea3",
  free: "dc70a3032b9dcd2b",
};

test("BF1 at the first settings the fab file is the one written before part 4", () => {
  for (const c of E.CHALLENGES) for (const v of ["start", "fix"]) {
    let x = c.setup(); if (v === "fix") x = c.fix(x);
    assert.equal(sha(fileOf(x)), BEFORE[`${c.id}-${v}`], `${c.id} ${v}`);
    assert.equal(sha(fileOf(withFlow(x, {}))), BEFORE[`${c.id}-${v}`], `${c.id} ${v}, an empty settings record`);
  }
  assert.equal(sha(fileOf(free())), BEFORE.free, "Free build");
});

test("BF2 each setting writes its lines on the teaching fab", () => {
  const t0 = fileOf(free());
  const steps0 = lines(t0, "step");
  let t = fileOf(withFlow(free(), { rule: "fifo" }));
  assert.deepEqual(lines(t, "dispatch"), [["dispatch", "fifo"]]);
  t = fileOf(withFlow(free(), { rule: "spt" }));
  assert.deepEqual(lines(t, "dispatch"), [["dispatch", "spt"]]);
  // demand x1.5: a lot every 20 minutes
  t = fileOf(withFlow(free(), { demand: 1.5 }));
  let rel = lines(t, "release");
  assert.equal(rel.length, 1);
  assert.equal(+rel[0][4], 20);
  // 1 urgent lot for every 5, at x1.5: a priority 20 release every 100 minutes, its first half a regular gap in
  t = fileOf(withFlow(free(), { demand: 1.5, urgent: "1in5" }));
  rel = lines(t, "release");
  assert.equal(rel.length, 2, "a second release");
  const hot = rel.find((r) => +r[3] > 1);
  assert.ok(hot, "a release of higher priority");
  assert.equal(+hot[3], 20); assert.equal(+hot[4], 100); assert.equal(+hot[5], 10); assert.equal(hot[1], "teach"); assert.equal(+hot[2], 25);
  assert.equal(hot[7], "Hot");
  // rework 5%: each check step sends lots back to the step before
  t = fileOf(withFlow(free(), { rework: "p0.05" }));
  const steps = lines(t, "step");
  assert.equal(steps.length, steps0.length);
  const checks = steps.map((f, i) => [f, i]).filter(([f]) => /_Met_T$/.test(f[1]));
  assert.equal(checks.length, 5, "five check steps");
  for (const [f, i] of checks) { assert.equal(+f[11], i - 1, `step ${i} goes back one`); assert.equal(+f[12], 0.05); }
  for (const [f, i] of steps.map((f, i) => [f, i]).filter(([f]) => !/_Met_T$/.test(f[1]))) assert.equal(f[11], "-", `step ${i} sends nothing back`);
  // quality holds
  assert.deepEqual(lines(fileOf(withFlow(free(), { holds: 1 })), "defects").map((f) => f.slice(1).map(Number)), [[120, 240, 60]]);
  assert.deepEqual(lines(fileOf(withFlow(free(), { holds: 2 })), "defects").map((f) => f.slice(1).map(Number)), [[240, 480, 120]]);
  // all of them at once is still a fab file the other lines of which are unchanged
  t = fileOf(withFlow(free(), { rule: "fifo", demand: 1.25, urgent: "1in10", rework: "p0.02", holds: 1 }));
  assert.deepEqual(lines(t, "group"), lines(t0, "group"));
  assert.deepEqual(lines(t, "node"), lines(t0, "node"));
});

test("BF3 on a fab with its own urgent lots and rework, the settings scale them", () => {
  // the teaching fab given an urgent release and one rework step, as the SMT2020 testbed has both
  const own = E.TEACHING_SHOP.replace("release\tteach\t25\t1.0\t30.0\t0.0\t-\tLot", "release\tteach\t25\t1.0\t30.0\t0.0\t-\tLot\nrelease\tteach\t25\t10.0\t300.0\t5.0\t-\tHot")
    .replace(/^(step\tLitho_Met_T\t.*)$/m, (l) => { const f = l.split("\t"); f[11] = "1"; f[12] = "0.3"; return f.join("\t"); });
  const x = { base: own, state: { ...E.template("teaching") } };
  const hotOf = (t) => lines(t, "release").filter((r) => +r[3] > 1);
  assert.equal(+hotOf(fileOf(withFlow(x, { urgent: "x2" })))[0][4], 150, "x2 halves the gap");
  assert.equal(+hotOf(fileOf(withFlow(x, { urgent: "x0.5" })))[0][4], 600, "x0.5 doubles it");
  assert.equal(hotOf(fileOf(withFlow(x, { urgent: "none" }))).length, 0, "None removes the urgent releases");
  assert.equal(lines(fileOf(withFlow(x, { urgent: "none" })), "release").length, 1, "and keeps the regular one");
  const rw = (t) => lines(t, "step").filter((f) => f[11] !== "-").map((f) => +f[12]);
  assert.deepEqual(rw(fileOf(withFlow(x, { rework: "x2" }))), [0.6]);
  assert.deepEqual(rw(fileOf(withFlow(x, { rework: "x4" }))), [1], "at most 1");
  assert.deepEqual(rw(fileOf(withFlow(x, { rework: "none" }))), []);
  assert.equal(E.flowOptions(own).urgent.some(([v]) => v === "x2"), true, "a fab with urgent lots is offered multiples");
  assert.equal(E.flowOptions(E.TEACHING_SHOP).urgent.some(([v]) => v === "1in5"), true, "the teaching fab is offered 1 for every 5");
  assert.equal(E.flowOptions(own).rework.some(([v]) => v === "x2"), true);
  assert.equal(E.flowOptions(E.TEACHING_SHOP).rework.some(([v]) => v === "p0.05"), true);
});

// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper() {
  const port = 8800 + Math.floor(Math.random() * 600);
  const p = spawn(PY, ["-m", "agent.helper", "--port", String(port), "--runs", profileDir("bf-runs-")], { cwd: ROOT, stdio: "ignore" });
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
    `--user-data-dir=${profileDir("bf-")}`, "about:blank"], { stdio: "ignore" });
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

async function openEditor() {
  const h = await helper();
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Page.navigate", { url: `http://127.0.0.1:${h.port}/editor.html` });
  for (let i = 0; i < 200; i++) {
    await sleep(50);
    if (await b.ev("!!(window.FabEditorPage && window.FabEditorPage.runs && window.FabEditorPage.runs() >= 1)")) break;
  }
  const close = () => { b.close(); h.close(); };
  return { b, close };
}

const page = (b, expr) => b.ev(`(() => { const F = window.FabEditorPage; return ${expr}; })()`);



const until = async (b, cond, ms = 15000) => { for (let t = 0; t < ms; t += 100) { if (await b.ev(cond)) return true; await sleep(100); } return false; };
const toTab = async (b, k) => { const r0 = await page(b, "F.runs()"); await b.ev(`document.querySelectorAll("#chtabs button")[${k}].click(), 1`); await until(b, `FabEditorPage.runs() > ${r0}`); await sleep(300); };
const openFab = async (b) => { await b.ev(`document.querySelector('#ctl-tabs [data-tab="fab"]').click(), 1`); await sleep(150); };
const choose = async (b, k, v) => {
  await openFab(b);
  await b.ev(`(() => { const s = document.getElementById("ctl-fab-${k}"); s.value = ${JSON.stringify(v)}; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(200);
};
const FIVE = ["rule", "demand", "urgent", "rework", "holds"];

test("BF4 Whole fab shows the five settings, each saying what it does, and each changes the fab file", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    await openFab(b);
    for (const k of FIVE) {
      const r = await b.ev(`(() => { const s = document.getElementById("ctl-fab-${k}"); const row = s && s.closest(".ctlrow"); return row ? { why: (row.querySelector(".why") || {}).textContent || "", shown: !!row.offsetParent, opts: [...s.options].map(o => o.value) } : null; })()`);
      assert.ok(r, `a ${k} control`);
      assert.ok(r.shown, `${k} shows`);
      assert.ok(r.why.trim().length > 20, `${k} says what it does: ${r.why}`);
      assert.ok(r.opts.length >= 3, `${k} has choices`);
    }
    const before = await page(b, "F.fab()");
    const picks = { rule: "fifo", demand: "1.5", urgent: "1in5", rework: "p0.05", holds: "1" };
    for (const k of FIVE) {
      const t0 = await page(b, "F.fab()");
      await choose(b, k, picks[k]);
      assert.notEqual(await page(b, "F.fab()"), t0, `${k} changes the fab file`);
    }
    const t = await page(b, "F.fab()");
    assert.match(t, /^dispatch\tfifo$/m);
    assert.match(t, /^defects\t120(\.0)?\t240(\.0)?\t60(\.0)?$/m);
    for (const k of FIVE) await choose(b, k, await b.ev(`document.getElementById("ctl-fab-${k}").options[0].value`));
    assert.equal(await page(b, "F.fab()"), before, "the first choices give the file back");
  } finally { close(); }
});

test("BF5 a fab file with all five set passes the checks and runs; holds with no rework warn", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const h = await helper();
  try {
    const post = async (path, body) => { for (;;) { const r = await (await fetch(`http://127.0.0.1:${h.port}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json(); if (!r.busy) return r; await sleep(100); } };
    const all = fileOf(withFlow(free(), { rule: "fifo", demand: 1.25, urgent: "1in5", rework: "p0.02", holds: 1 }));
    const c = await post("/api/fab/check", { fab: all });
    assert.equal(c.ok, true, JSON.stringify(c));
    const r = await post("/api/fab/run", { fab: all, seed: 1, days: 2, every: 60 });
    assert.ok(r.moods && r.moods.score && r.moods.score.wafers_per_day > 0, JSON.stringify(r).slice(0, 300));
    const held = fileOf(withFlow(free(), { holds: 1 }));
    const w = await post("/api/fab/check", { fab: held });
    assert.ok((w.issues || []).some((i) => i.code === "holds_without_rework"), JSON.stringify(w));
  } finally { h.close(); }
});

test("BF6 in a challenge the five start at today's settings; changing one is an experiment with no stars", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 1);
    await openFab(b);
    for (const k of FIVE) assert.equal(await b.ev(`document.getElementById("ctl-fab-${k}").selectedIndex`), 0, `${k} starts at today's`);
    assert.equal(await page(b, "F.experiment()"), false);
    const r0 = await page(b, "F.runs()");
    await choose(b, "demand", "1.25");
    await until(b, `FabEditorPage.runs() > ${r0}`, 20000);
    assert.equal(await page(b, "F.experiment()"), true, "the run is an experiment");
    assert.equal(await page(b, "F.starsNow()"), 0, "no stars");
    assert.match(await b.ev(`document.querySelector(".banner").innerText`), /experiment/i);
    assert.match(await b.ev(`document.querySelector(".banner").innerText`), /demand/i, "the banner names what changed");
  } finally { close(); }
});

test("BF7 the page does not scroll with Whole fab open", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    for (const [w, hh] of [[1440, 900], [1440, 760], [1280, 720]]) {
      await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: hh, deviceScaleFactor: 1, mobile: false });
      await sleep(400);
      await openFab(b);
      await sleep(300);
      const over = await b.ev(`Math.max(document.documentElement.scrollHeight - innerHeight, document.documentElement.scrollWidth - innerWidth)`);
      assert.ok(over <= 0, `${w} x ${hh}: the page scrolls ${over} px`);
    }
  } finally { close(); }
});
