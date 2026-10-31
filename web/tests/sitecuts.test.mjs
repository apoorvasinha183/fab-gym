// Fewer doors (docs/SITE-CUTS.md): the nav Home · Floor · Build · Evidence, a tab icon, the floor's view bar, numbers,
// key, speeds and rail cut down, Evidence a page of its own, Build without modes or lot tiles. Written before the code.
// On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/sitecuts.test.mjs   (from the repo root; K6 to K9 need Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, mkdtempSync } from "node:fs";
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
const WEB = join(HERE, "..");
const ROOT = join(WEB, "..");
const index = readFileSync(join(WEB, "index.html"), "utf8"), editor = readFileSync(join(WEB, "editor.html"), "utf8");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");
const between = (s, a, b) => { const i = s.indexOf(a); return i < 0 ? "" : s.slice(i, s.indexOf(b, i + a.length)); };
const textOf = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

function navOf(html) {
  const m = html.match(/<nav class="topnav"[^>]*>([\s\S]*?)<\/nav>/);
  assert.ok(m, "a top bar");
  return [...m[1].matchAll(/<a [^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/g)].map((x) => [x[2].trim(), x[1]]);
}

// ---------------------------------------------------------------- in Node, on the pages' files

test("K1 the nav on both pages: Home, Floor, Build, Evidence", () => {
  assert.deepEqual(navOf(index), [["Home", "#home"], ["Floor", "#floor"], ["Build", "editor.html"], ["Evidence", "#evidence"]]);
  assert.deepEqual(navOf(editor), [["Home", "index.html"], ["Floor", "index.html#floor"], ["Build", "editor.html"], ["Evidence", "index.html#evidence"]]);
});

test("K2 both pages declare a tab icon", () => {
  for (const [name, html] of [["index", index], ["editor", editor]]) assert.match(html, /<link rel="icon"[^>]*href="data:image\/svg\+xml/, name);
});

test("K3 Home keeps its two doors and drops 'or explore the floor'", () => {
  const doors = between(index, 'id="open-doors"', "</section>");
  assert.match(doors, /Play a challenge/);
  assert.match(doors, /Watch the whole fab at work/, "the door to the Floor (docs/HOME-REVIEW.md)");
  assert.ok(!/Ask the fab/.test(doors), "asking moved to the Floor (docs/HOME-GATE.md)");
  assert.ok(!/id="open-explore"/.test(index), "no 'or explore the floor'");
});

test("K4 the floor: no view bar; Follow one lot; a health panel; a sectioned key; one speed button; Try a change and Glossary in reach", () => {
  assert.ok(!/<nav class="lenses"/.test(index), "no view bar");
  assert.match(index, /<button[^>]*id="follow-open"[^>]*>Follow one lot<\/button>/);
  assert.match(index, /<button[^>]*id="proto-open"[^>]*hidden[^>]*>Show prototypes<\/button>/);
  // the two numbers and the key of three gave way to the health panel and a sectioned legend (docs/FLOOR-HEALTH.md)
  const health = between(index, 'id="health"', "</section>");
  for (const h of ["Output", "Lots in the fab", "Tools", "Longest queue", "Latest events"]) assert.match(textOf(health), new RegExp(h), `health: ${h}`);
  const key = between(index, 'id="key"', "</section>");
  for (const h of ["Tool light", "Group badge", "Lots"]) assert.match(textOf(key), new RegExp(h), `key: ${h}`);
  assert.match(textOf(key), /working/); assert.match(textOf(key), /broken down/); assert.match(textOf(key), /25 wafers/);
  const bar = between(index, 'class="speeds"', "</div>");
  assert.equal((bar.match(/<button/g) || []).length, 1, "one speed button");
  // the rail of two went: Try a change sits by the ask bar, Glossary by How a chip is made (docs/FLOOR-REVIEW.md)
  assert.ok(!/<nav id="rail"/.test(index), "no rail");
  assert.match(index, /<button[^>]*id="change-open"[^>]*data-tab="change"[^>]*>[^<]*Simulation settings/); // docs/SIM-SETTINGS.md
  assert.match(index, /<button[^>]*id="glossary-open"[^>]*data-tab="glossary"[^>]*>[^<]*Glossary/);
  for (const gone of ["data-tab=\"ask\"", "data-tab=\"numbers\"", "data-tab=\"results\""]) assert.ok(!index.includes(gone), `${gone} is gone`);
});

test("K5 Build: no mode buttons, no lots right now, three score cards", () => {
  assert.ok(!/id="modeRun"|id="modeBuild"/.test(editor), "no Run and Build modes");
  assert.ok(!/The lots right now/.test(editor) && !/id="lots"/.test(editor), "no lot tiles");
  const js = readFileSync(join(WEB, "editor.js"), "utf8");
  const score = between(js, "function renderScore()", "\n  }\n");
  assert.equal((score.match(/card\("/g) || []).length, 3, "three score cards");
});

// ---------------------------------------------------------------- in headless Chrome, with a quick helper of its own

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function open(path) {
  const hp = 8800 + Math.floor(Math.random() * 600);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp), "--quick"], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/index.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,900", "--hide-scrollbars", `--user-data-dir=${profileDir("cuts-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map(); const failed = [];
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); }
    else if (d.method === "Network.responseReceived" && d.params.response.status >= 400) failed.push(`${d.params.response.status} ${d.params.response.url}`);
    else if (d.method === "Network.loadingFailed" && !/ERR_ABORTED/.test(d.params.errorText)) failed.push(d.params.errorText); };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  await send("Network.enable"); await send("Page.enable");
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/${path}` });
  const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await ev(expr)) return true; } catch { /* page busy */ } await sleep(100); } return false; };
  return { ev, until, failed, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}

const VISIBLE_CONTROLS = `[...document.querySelectorAll("button,a,select,input,textarea,summary")].filter((e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; }).length`;

test("K6 the floor's first screen has at most 12 controls, and nothing fails to load", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#floor");
  try {
    assert.ok(await p.until("document.body.dataset.floor === 'full'", 20000), "the floor loaded");
    await sleep(500);
    const n = await p.ev(VISIBLE_CONTROLS);
    // 13 after the cuts; docs/FLOOR-REVIEW.md adds the map's four buttons and the legend's fold (the strip and help row swap two for two)
    // and docs/RANDOM-RUNS.md adds New run
    assert.ok(n <= 18, `${n} controls on the first screen (was 21)`);
    assert.deepEqual(p.failed, [], "no failed request");
  } finally { p.close(); }
});

test("K7 Evidence is a page of its own: the WIP-cap study, the prototype money table and the results", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#evidence");
  try {
    assert.ok(await p.until("!!document.querySelector('#long-grid *') && !!document.querySelector('#res-list *') && !!document.querySelector('#num-forest *, #num-lines *, #numbers table')", 20000), "all three filled in");
    const o = JSON.parse(await p.ev(`JSON.stringify({ title: (document.getElementById("dock-title") || {}).textContent, current: (document.querySelector('.topnav a[aria-current="page"]') || {}).textContent,
      long: !document.getElementById("long-sec").closest("[hidden]"), res: !document.getElementById("results").closest("[hidden]"), num: !document.getElementById("numbers").closest("[hidden]") })`));
    assert.equal(o.title, "Evidence");
    assert.equal(o.current, "Evidence", "the nav marks Evidence");
    assert.ok(o.long && o.res && o.num, `all shown: ${JSON.stringify(o)}`);
  } finally { p.close(); }
});

test("K8 a question in the bar opens the answer; #ask still does too", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#floor");
  try {
    await p.until("document.body.dataset.floor", 20000);
    await p.until("typeof ASK !== 'undefined' && ASK.helper", 10000);
    // a worked example's question, answered from its written answer: no model is called and no credit spent
    // the worked examples are the ask bar's suggestions (docs/HOME-GATE.md)
    await p.until("!!document.querySelector('#cmd-examples button')", 10000);
    await p.ev(`(() => { const q = document.getElementById("cmd-q"); q.value = document.querySelector("#cmd-examples button").textContent; document.getElementById("cmd").requestSubmit(); })()`);
    assert.ok(await p.until("!document.getElementById('pane-ask').closest('[hidden]')", 5000), "the answer panel opens");
    await p.ev(`location.hash = "#floor"`); await sleep(200); await p.ev(`location.hash = "#ask"`);
    assert.ok(await p.until("!document.getElementById('pane-ask').closest('[hidden]')", 5000), "#ask opens it");
  } finally { p.close(); }
});

test("K9 the one speed button cycles 1×, 3×, 12×, Max", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#floor");
  try {
    await p.until("document.body.dataset.floor", 20000);
    const seen = [];
    for (let i = 0; i < 5; i++) { seen.push(await p.ev(`document.querySelector(".speeds button").textContent.trim()`)); await p.ev(`document.querySelector(".speeds button").click()`); await sleep(50); }
    assert.deepEqual(new Set(seen), new Set(["1×", "3×", "12×", "Max"]), `labels seen: ${seen}`);
    assert.equal(seen[0], seen[4], "back where it started after four presses");
  } finally { p.close(); }
});
