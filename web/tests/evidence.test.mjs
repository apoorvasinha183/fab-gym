// Evidence in plain words (docs/EVIDENCE-PLAIN.md): four findings first, from the same data as the tables, then the lab
// notebook. Written before the code. From the SMT2020 testbed; not a real fab. Every price is assumed.
//
//     node --test web/tests/evidence.test.mjs   (from the repo root; EV7 to EV9 need Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
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
const WEB = join(HERE, "..");
const ROOT = join(WEB, "..");
const require = createRequire(import.meta.url);
const U = require(join(WEB, "ui.js"));
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");
const json = (p) => JSON.parse(readFileSync(join(WEB, p), "utf8"));

function data() {
  const sweep = json("data/two-families.json");
  return { sweep: U.withPl(sweep, sweep.pl), long: json("data/lean-long.json"), results: json("data/results.json"), lean: json("data/lean-check.json") };
}
const Ev = () => require(join(WEB, "evidence.js"));

test("EV1 the Lean summary agrees with the verdicts file", () => {
  const rows = readFileSync(join(ROOT, "results/lean-check/verdicts.tsv"), "utf8").trim().split("\n").slice(1).map((l) => l.split("\t"));
  const lean = json("data/lean-check.json");
  assert.equal(lean.runs, rows.length);
  assert.equal(lean.passed, rows.filter((r) => r[4].startsWith("yes")).length);
  assert.equal(lean.runs, 120); assert.equal(lean.passed, 120);
  const jobs = rows.reduce((a, r) => a + Number((/jobs=(\d+)/.exec(r[4]) || [0, 0])[1]), 0);
  assert.equal(lean.jobs, jobs);
});

test("EV2 four findings in order, each complete", () => {
  const f = Ev().findings(data());
  assert.deepEqual(f.map((x) => x.id), ["prototypes", "cap", "ai", "checked"]);
  for (const x of f) {
    for (const k of ["title", "what", "means", "sure"]) assert.ok(typeof x[k] === "string" && x[k].length > 8, `${x.id}.${k}`);
    assert.ok(["Sure", "Too close to call", "Exact: a check, not an estimate"].some((w) => x.sure.startsWith(w)), `${x.id}: ${x.sure}`);
  }
});

test("EV3 the prototype finding uses the profit grid's numbers and says where it stops paying", () => {
  const d = data(), f = Ev().findings(d).find((x) => x.id === "prototypes");
  const cell = (share) => U.capitalGrid(d.sweep, share, "day").floors.find((q) => q.floor === "D1 share").cells.find((c) => c.policy === "P2 family cap");
  assert.equal(Math.round(f.levels.find((l) => l.share === 4).value), Math.round(cell(4).value));
  assert.equal(f.levels.find((l) => l.share === 8).verdict, "worse");
  assert.equal(cell(8).verdict, "worse");
  assert.match(f.title + " " + f.means, /eight times/i);
});

test("EV4 the cap finding: 1,800 lots, too close to call, about a month sooner, about 45 wafers lost when breakdowns double", () => {
  const f = Ev().findings(data()).find((x) => x.id === "cap");
  assert.equal(f.cap, 1800);
  assert.match(f.what + f.means + f.title, /1,800/);
  assert.equal(f.normal.verdict, "too close to call");
  assert.ok(Math.abs(f.normal.daysSooner - 30) < 1.5, `${f.normal.daysSooner} days sooner`);
  assert.ok(Math.abs(f.breaks.wafersLost - 45) < 1.5, `${f.breaks.wafersLost} wafers lost`);
});

test("EV5 the AI finding from the contest with quality holds ×1", () => {
  const f = Ev().findings(data()).find((x) => x.id === "ai");
  assert.ok(Math.abs(f.lower - 151.6) < 0.1, `${f.lower}`);
  assert.ok(f.sure.startsWith("Sure"));
});

test("EV6 plain words in every finding", () => {
  const bad = /Bonferroni|paired|\bseeds?\b|family [AB]|\bD[123]\b|\bP[0-4]\b|polic|×|interval/i;
  for (const x of Ev().findings(data())) for (const k of ["title", "what", "means", "sure"]) assert.ok(!bad.test(x[k]), `${x.id}.${k}: ${x[k]}`);
});

// ---------------------------------------------------------------- headless Chrome, a quick helper of its own

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function open(path) {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp), "--quick"], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/index.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,900", "--hide-scrollbars", `--user-data-dir=${profileDir("evid-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  await send("Page.enable");
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/${path}` });
  const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await ev(expr)) return true; } catch { /* busy */ } await sleep(100); } return false; };
  return { ev, until, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}

test("EV7 Evidence opens on What we found, four cards, the first on the first screen", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#evidence");
  try {
    assert.ok(await p.until("document.querySelectorAll('#findings .find').length === 4", 20000), "four finding cards");
    const o = JSON.parse(await p.ev(`JSON.stringify({ h: (document.querySelector("#findings h2") || {}).textContent, shown: !document.getElementById("findings").closest("[hidden]"), top: document.querySelector("#findings .find").getBoundingClientRect().top, inner: innerHeight })`));
    assert.match(o.h || "", /What we found/);
    assert.ok(o.shown, "the findings show");
    assert.ok(o.top < o.inner, `the first card starts at ${o.top}`);
  } finally { p.close(); }
});

test("EV8 the lab notebook heading sits after the findings and before the profit table", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#evidence");
  try {
    assert.ok(await p.until("!!document.querySelector('#num-capital table')", 20000), "the table drew");
    const o = JSON.parse(await p.ev(`JSON.stringify((() => { const nb = [...document.querySelectorAll("h2,h3")].find((h) => /Lab notebook/.test(h.textContent));
      if (!nb) return null; const f = document.getElementById("findings"), t = document.querySelector("#num-capital table");
      return { afterFindings: !!(f.compareDocumentPosition(nb) & Node.DOCUMENT_POSITION_FOLLOWING), beforeTable: !!(nb.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING), shown: !nb.closest("[hidden]") }; })())`));
    assert.ok(o, "a Lab notebook heading");
    assert.ok(o.afterFindings && o.beforeTable && o.shown, JSON.stringify(o));
  } finally { p.close(); }
});

test("EV9 the notebook says days and never pays back", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open("index.html#evidence");
  try {
    assert.ok(await p.until("!!document.querySelector('#num-capital table') && document.getElementById('num-base').textContent.length > 10", 20000));
    assert.match(await p.ev(`document.getElementById("num-base").textContent`), /Prototype cycle time[^.]*days|days[^.]*Prototype cycle time|\d days/i);
    const red = await p.ev(`[...document.querySelectorAll("#num-capital td.cg.worse span")].map((s) => s.textContent)`);
    assert.ok(red.length && red.every((t) => t === "" || /never pays back|pays back|days|months/.test(t)), `red cells: ${red.slice(0, 4)}`);
    assert.ok(red.some((t) => /never pays back/.test(t)), "at least one says never pays back");
  } finally { p.close(); }
});
