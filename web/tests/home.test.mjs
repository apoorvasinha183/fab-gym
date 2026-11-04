// Home after review (docs/HOME-REVIEW.md). Written before the code. The helper has no key here, so nothing is asked of a
// model. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/home.test.mjs   (needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync as rmProfile } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
const PROFILES = [];
const profileDir = (prefix) => { const d = mkdtempSync(join(tmpdir(), prefix)); PROFILES.push(d); return d; };
process.on("exit", () => { for (const d of PROFILES) { try { rmProfile(d, { recursive: true, force: true }); } catch { /* already gone */ } } });

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");
const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function open(path = "index.html#home", w = 1440, h = 1000) {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--no-model", "--port", String(hp), "--runs", mkdtempSync(join(tmpdir(), "fg-runs-"))], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/index.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, `--window-size=${w},${h}`, "--hide-scrollbars", `--user-data-dir=${profileDir("home-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await ev(expr)) return true; } catch { /* busy */ } await sleep(80); } return false; };
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  // every request the page makes to the helper's ask and run routes
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `window.__asked = []; const f0 = window.fetch; window.fetch = (u, o) => { if (/\\/api\\/(ask|run)\\b/.test(String(u))) window.__asked.push(String(u)); return f0(u, o); };` });
  const go = async (p) => { await send("Page.navigate", { url: `http://127.0.0.1:${hp}/${p}` }); await sleep(300); };
  await go(path);
  await until(`!!document.getElementById("open-doors") && document.readyState === "complete"`);
  await sleep(600);
  return { ev, send, until, go, hp, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}
const skip = !ready && "needs Google Chrome and the .venv";
const NAMES = ["Rush hour on the spine", "The gassed polisher", "Breakdown, no spare", "Lean or redundant?"];

test("HO1 no question box at the gate; on the Floor the ask bar offers the suggestions, and picking one asks nothing", { skip }, async () => {
  const p = await open();
  try {
    assert.equal(await p.ev(`[...document.querySelectorAll("#opening input, #opening textarea")].filter(e => e.getClientRects().length).length`), 0, "no question box on Home");
    await p.go("index.html#floor");
    await p.until(`!!document.getElementById("cmd-q") && !document.body.classList.contains("opening-on")`);
    await sleep(800);
    // click into the bar, as a person does
    const at = JSON.parse(await p.ev(`JSON.stringify((() => { const r = document.getElementById("cmd-q").getBoundingClientRect(); return [r.left + 20, r.top + r.height / 2]; })())`));
    for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) await p.send("Input.dispatchMouseEvent", { type, x: at[0], y: at[1], button: "left", clickCount: 1 });
    assert.ok(await p.until(`(() => { const l = document.getElementById("cmd-examples"); return l && !l.hidden && l.querySelectorAll("button").length >= 3; })()`, 6000), "the suggestions show");
    const first = await p.ev(`document.querySelector("#cmd-examples button").textContent.trim()`);
    await p.ev(`document.querySelector("#cmd-examples button").dispatchEvent(new MouseEvent("mousedown", { bubbles: true })), document.querySelector("#cmd-examples button").click(), 1`);
    await sleep(500);
    assert.equal(await p.ev(`document.getElementById("cmd-q").value`), first.replace(/^→\s*/, ""), "the bar holds the suggestion");
    assert.deepEqual(JSON.parse(await p.ev("JSON.stringify(window.__asked)")), [], "nothing asked");
  } finally { p.close(); }
});

test("HO2 four named challenge tiles, each opening its challenge in Build", { skip }, async () => {
  const p = await open();
  try {
    const tiles = JSON.parse(await p.ev(`JSON.stringify([...document.querySelectorAll(".door-play .ch-tile")].map(a => ({ name: a.textContent.replace(/\\s+/g, " ").trim(), href: a.getAttribute("href"), img: !!a.querySelector("img[src]") })))`));
    assert.equal(tiles.length, 4);
    tiles.forEach((t, i) => { assert.ok(t.name.includes(NAMES[i]), `${t.name} names ${NAMES[i]}`); assert.equal(t.href, `editor.html?ch=${i + 1}`); assert.ok(t.img); });
    await p.go("editor.html?ch=3");
    assert.ok(await p.until(`/CHALLENGE 3/i.test((document.getElementById("cheye") || {}).textContent || "")`, 15000), "Build opens challenge 3");
  } finally { p.close(); }
});

test("HO3 Start is the play door's one solid button, and says what is inside", { skip }, async () => {
  const p = await open();
  try {
    const solid = JSON.parse(await p.ev(`JSON.stringify([...document.querySelectorAll(".door-play .btn-solid")].map(b => ({ t: b.textContent.trim(), href: b.getAttribute("href") })))`));
    assert.equal(solid.length, 1); assert.match(solid[0].t, /Take problem 1/); assert.equal(solid[0].href, "editor.html?ch=1");
    assert.match(await p.ev(`document.querySelector(".door-play").textContent`), /4 problems · a free build · up to 3 stars each/);
  } finally { p.close(); }
});

test("HO4 two doors, Play and Watch, side by side and in view; Watch it live opens the Floor", { skip }, async () => {
  const p = await open();
  try {
    const doors = JSON.parse(await p.ev(`JSON.stringify([...document.querySelectorAll("#open-doors > .door")].map(d => d.querySelector(".door-k").textContent.trim()))`));
    assert.deepEqual(doors, ["My in-tray", "Walk the floor with me"]);
    const d = JSON.parse(await p.ev(`JSON.stringify((() => { const e = document.querySelector(".door-floor"); const b = e.querySelector(".btn-solid"); return { img: !!e.querySelector("img[src*='ceo']"), href: b && b.getAttribute("href") }; })())`));
    assert.ok(d.img, "the CEO's picture"); assert.equal(d.href, "#floor");
    const r = JSON.parse(await p.ev(`JSON.stringify((() => { const o = document.getElementById("opening"); const box = s => { const r = document.querySelector(s).getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }; return { scroll: o.scrollHeight - o.clientHeight, play: box(".door-play"), floor: box(".door-floor"), H: innerHeight }; })())`));
    const over = (x, y) => x.l < y.r && y.l < x.r && x.t < y.b && y.t < x.b;
    assert.ok(!over(r.play, r.floor), "no overlap");
    assert.ok(Math.abs(r.play.t - r.floor.t) < 4 && r.floor.l > r.play.l, "side by side");
    assert.ok(r.scroll <= 2 && r.floor.b <= r.H && r.play.b <= r.H, `in view (scroll ${r.scroll})`);
    await p.ev(`document.querySelector(".door-floor .btn-solid").click(), 1`);
    assert.ok(await p.until(`location.hash === "#floor" && !document.body.classList.contains("opening-on")`, 8000), "the Floor opens");
  } finally { p.close(); }
});

test("HO6 ⌘K on Home opens the Floor with the ask bar ready; Escape closes the suggestions", { skip }, async () => {
  const p = await open();
  try {
    await p.send("Input.dispatchKeyEvent", { type: "keyDown", key: "k", code: "KeyK", modifiers: 4 });
    await p.send("Input.dispatchKeyEvent", { type: "keyUp", key: "k", code: "KeyK", modifiers: 4 });
    assert.ok(await p.until(`location.hash === "#floor" && document.activeElement === document.getElementById("cmd-q")`, 8000), "the Floor, the ask bar focused");
    assert.ok(await p.until(`!document.getElementById("cmd-examples").hidden`, 4000), "suggestions shown");
    await p.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
    await p.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
    assert.ok(await p.until(`document.getElementById("cmd-examples").hidden`, 3000), "Escape closes them");
  } finally { p.close(); }
});

test("HO5 the line under the headline says what each Meta model does", { skip }, async () => {
  const p = await open();
  try {
    const sub = await p.ev(`document.querySelector(".open-sub").textContent`);
    assert.match(sub, /Muse Spark sets up the what-ifs you ask/); assert.match(sub, /Muse Wonder plays the challenges against you/);
  } finally { p.close(); }
});
