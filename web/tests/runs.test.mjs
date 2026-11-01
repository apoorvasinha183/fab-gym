// Runs you can watch and find again (docs/RUNS.md, part 1: RN5 to RN8; part 2: RN11 to RN13). Written before the code. A helper in smoke mode
// keeps its runs in a folder of its own; nothing is spent. On a teaching fab of our own and the SMT2020 testbed; not a
// real fab.
//
//     node --test web/tests/runs.test.mjs   (needs Google Chrome, the .venv and a release build)

import { test, after } from "node:test";
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
  const prof = profileDir("runs-");
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



const PY = join(WEB, "..", ".venv", "bin", "python");
const ROOT = join(WEB, "..");
const ready = !skip && existsSync(PY) && existsSync(join(ROOT, "target", "release", "fabsim"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const RUNS = mkdtempSync(join(tmpdir(), "runs-dir-")); PROFILES.push(RUNS);
const ONE = "fabgym-scenario 1\nquestion\tIs first in, first out better today?\ncandidate\tfifo\trule\tfifo\n";
const TWO = "fabgym-scenario 1\nquestion\tPrototypes doubled: first in line?\nfamily\tshare\t2\tsaid\ncandidate\tb-first\tpolicy\tbfirst\n";
// four changes on one core: long enough to watch the card while it works
const FOUR = "fabgym-scenario 1\nquestion\tPrototypes doubled: which rule for them?\nfamily\tshare\t2\tsaid\n" +
  "candidate\tb-first\tpolicy\tbfirst\ncandidate\tcapped\tpolicy\tcap\ncandidate\treserved\tpolicy\treserve\ncandidate\thalf\tpolicy\tqualify\n";

// one helper for the file, in smoke mode, keeping its runs in a folder of its own
let HP = 0, HELPER = null;
after(() => { if (HELPER) HELPER.kill(); }); // stopped when the file's tests end
async function helperUp() {
  if (HELPER) return HP;
  HP = 8800 + Math.floor(Math.random() * 400);
  HELPER = spawn(PY, ["-m", "agent.helper", "--port", String(HP), "--quick", "--threads", "1", "--runs", RUNS], { cwd: ROOT, stdio: "ignore" });
  HELPER.unref(); // the shared helper must not keep the test file from ending
  process.on("exit", () => HELPER.kill());
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${HP}/runs.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  return HP;
}
const api = async (path, body) => (await fetch(`http://127.0.0.1:${HP}${path}`, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {})).json();
async function finished(id) { assert.ok(id, "the helper took the run"); for (let i = 0; i < 1200; i++) { const j = await api(`/api/job/${id}`); if (j.stage === "done" || j.stage === "failed") return j; await sleep(250); } throw new Error("the run did not finish"); }

async function page(path, w = 1440, h = 900) {
  await helperUp();
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await b.send("Page.navigate", { url: `http://127.0.0.1:${HP}/${path}` });
  await b.sleep(1200);
  return b;
}
const cardState = `JSON.stringify((() => { const c = document.getElementById("run-card"); if (!c || c.hidden) return null;
  return { id: (c.querySelector(".runid") || {}).textContent, done: +c.dataset.done, total: +c.dataset.total, stage: c.dataset.stage,
    filled: c.querySelectorAll(".grid .cell.filled").length, cells: c.querySelectorAll(".grid .cell").length,
    log: c.querySelectorAll(".log > div").length, ivals: c.querySelectorAll("svg.forest g.ival").length,
    leader: (c.querySelector(".leader") || {}).textContent || "", text: c.innerText }; })())`;

test("RN5 every page has a Runs tab; the list shows the runs; a run's address opens its card in plain words", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  await helperUp();
  // one run at a time: the helper refuses a second while one works
  const one = (await api("/api/run", { scenario: ONE })).job;
  assert.equal(one, "Q-0001");
  await finished(one);
  const two = (await api("/api/run", { scenario: TWO })).job;
  await finished(two);
  for (const path of ["index.html#floor", "editor.html?ch=1", "runs.html"]) {
    const p = await page(path);
    try { assert.ok(await p.ev(`!!document.querySelector('nav.topnav a[href$="runs.html"]')`), `${path}: a Runs tab`); } finally { p.close(); }
  }
  const p = await page("runs.html");
  try {
    for (let i = 0; i < 40 && !(await p.ev(`document.querySelectorAll("#runs-list [data-run]").length >= 2`)); i++) await p.sleep(250);
    const rows = JSON.parse(await p.ev(`JSON.stringify([...document.querySelectorAll("#runs-list [data-run]")].map(r => [r.dataset.run, r.innerText]))`));
    assert.deepEqual(rows.map((r) => r[0]), [two, one], "newest first");
    assert.ok(rows[0][1].includes("Prototypes doubled: first in line?"));
    await p.ev(`location.hash = "#run=${two}", 1`); await p.sleep(1200);
    const c = JSON.parse(await p.ev(cardState));
    assert.equal(c.id, two);
    assert.ok(c.text.includes("Prototypes doubled: first in line?"));
    assert.ok(/You said/.test(c.text) && /2 times the usual/.test(c.text), "what you said, in words");
    assert.ok(/prototype lots first/i.test(c.text), "the setup by its plain name");
    assert.ok(!/b-first|bfirst/.test(c.text), "no engine codes");
    assert.equal(await p.ev(`[...document.querySelectorAll("#run-card *")].filter(e => e.children.length === 0 && e.textContent.trim() === "said").length`), 0, "no bare 'said'");
  } finally { p.close(); }
});

test("RN6 while a run works, the log grows and the grid fills with it; at the end the card shows the report's verdict", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  const p = await page("runs.html");
  const id = (await api("/api/run", { scenario: FOUR })).job;
  assert.ok(id, "the helper took the run");
  await p.ev(`location.hash = "#run=${id}", 1`);
  try {
    let last = null, sawRunning = false, logs = [];
    for (let i = 0; i < 2400; i++) {
      const c = JSON.parse(await p.ev(cardState));
      if (c) {
        assert.equal(c.filled, c.done, `filled squares equal the runs done (${c.filled} against ${c.done})`);
        logs.push(c.log);
        if (c.stage !== "done" && c.stage !== "failed") sawRunning = true;
        last = c;
        if (c.stage === "done") break;
      }
      await p.sleep(100);
    }
    assert.ok(last && last.stage === "done", "the card shows the end");
    assert.ok(sawRunning, "the card was open while the run worked");
    for (let i = 1; i < logs.length; i++) assert.ok(logs[i] >= logs[i - 1], "the log only grows");
    assert.equal(last.filled, last.total);
    assert.equal(last.cells, last.total, "a square for each setup on each random run");
    const j = await finished(id);
    assert.equal(last.total, j.runs_total);
    assert.equal(last.ivals, j.report.candidates.length, "an interval for each change");
    const verdict = j.report.candidates[0].measures.profit.verdict;
    assert.ok(last.text.includes(verdict), `the report's verdict (${verdict}) shows`);
    assert.ok(j.report.best ? last.leader.includes("first") || last.leader.length > 0 : /no change beat today/i.test(last.leader), "the leader, or that none beat today");
  } finally { p.close(); }
});

test("RN7 asking on the Floor shows the run's number with a link to its card", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  const p = await page("index.html#floor");
  try {
    for (let i = 0; i < 300 && !(await p.ev(`document.body.dataset.floor === "full"`)); i++) await p.sleep(100);
    const ex = (await api("/api/status")).examples.map((e) => e.question).find((q) => /dispatch rule/i.test(q));
    await p.ev(`(() => { document.getElementById("cmd-q").value = ${JSON.stringify(ex)}; document.getElementById("cmd").requestSubmit(); return 1; })()`);
    let link = null;
    for (let i = 0; i < 100 && !link; i++) { await p.sleep(200); link = await p.ev(`(() => { const a = document.querySelector('#pane-ask a[href^="runs.html#run=Q-"]'); return a ? a.getAttribute("href") + "|" + a.textContent : null; })()`); }
    assert.ok(link, "a link to the run's card");
    const [href, text] = link.split("|");
    assert.match(href, /^runs\.html#run=Q-\d{4}$/);
    assert.ok(text.includes(href.split("=")[1]), "the link names the run's number");
  } finally { p.close(); }
});

test("RN8 the Muse Spark line shows only when a model answered", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  await helperUp();
  for (let i = 0; i < 1200 && (await api("/api/status")).busy; i++) await sleep(250); // the run before this one ends first
  const ex = (await api("/api/status")).examples.map((e) => e.question).find((q) => /dispatch rule/i.test(q));
  const id = (await api("/api/ask", { question: ex })).job;
  await finished(id);
  // a copy of that run, marked as answered by the model, stands in for a model's run without spending anything
  const { cpSync, readFileSync: rf, writeFileSync } = await import("node:fs");
  cpSync(join(RUNS, id), join(RUNS, "Q-0099"), { recursive: true });
  const meta = JSON.parse(rf(join(RUNS, "Q-0099", "run.json"), "utf8"));
  writeFileSync(join(RUNS, "Q-0099", "run.json"), JSON.stringify({ ...meta, id: "Q-0099", answer_source: "model", model: "muse-spark-1.3-contributor" }));
  const p = await page(`runs.html#run=${id}`);
  try {
    await p.sleep(800);
    let c = JSON.parse(await p.ev(cardState));
    assert.ok(/no model ran/i.test(c.text), "an example's card says no model ran");
    assert.ok(!/Muse Spark/.test(c.text), "and does not mention Muse Spark");
    await p.ev(`location.hash = "#run=Q-0099", 1`); await p.sleep(1200);
    c = JSON.parse(await p.ev(cardState));
    assert.ok(/Muse Spark/.test(c.text), "a model's card names Muse Spark");
  } finally { p.close(); }
});

// ---------------------------------------------------------------- part 2 (docs/RUNS.md): each setup's floor, and any run on the Floor

const COPIES = "fabgym-scenario 1\nquestion\tPrototypes doubled: copies in the halls?\nfamily\tshare\t2\tsaid\ncandidate\tcopies\tfloor\tcopies\n";
async function runDone(text) {
  await helperUp();
  for (let i = 0; i < 1200 && (await api("/api/status")).busy; i++) await sleep(250);
  const id = (await api("/api/run", { scenario: text })).job;
  return [id, await finished(id)];
}
const FABSIM = join(ROOT, "target", "release", "fabsim");
/** The engine's receipt of a setup's file on a random run for the days shown: [jobs, finished lots]. */
async function receiptOf(shopUrl, seed, until) {
  const { writeFileSync } = await import("node:fs");
  const { execFileSync } = await import("node:child_process");
  const f = join(RUNS, `arm-${Date.now()}.fab.txt`);
  writeFileSync(f, await (await fetch(`http://127.0.0.1:${HP}${shopUrl}`)).text());
  const end = execFileSync(FABSIM, ["receipt", f, "--seed", String(seed), "--until", String(until)], { maxBuffer: 1 << 30 }).toString().trim().split("\n").pop().split(" ");
  return [+end[1], +end[5]];
}

test("RN11 a two-family run's card draws each setup's floor, a mark for each placed group, the copies marked", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  const [id, j] = await runDone(COPIES);
  const arms = j.report.arms;
  const p = await page(`runs.html#run=${id}`);
  try {
    await p.sleep(800);
    const floors = JSON.parse(await p.ev(`JSON.stringify([...document.querySelectorAll("#rc-floors svg")].map(s => ({ marks: s.querySelectorAll("[data-g]").length, copies: s.querySelectorAll("[data-g].copy").length, moved: s.querySelectorAll("[data-g].moved").length })))`));
    assert.equal(floors.length, arms.length, "a floor for each setup");
    arms.forEach((a, k) => {
      assert.equal(floors[k].marks, a.plan.groups.length, `${a.name}: a mark for each group`);
      assert.equal(floors[k].copies, a.plan.copies.length, `${a.name}: the copies marked`);
      assert.equal(floors[k].moved, a.plan.moved.length, `${a.name}: the moved groups ringed`);
    });
    assert.ok(arms[1].plan.copies.length > 0, "the copies setup has copies");
    assert.match(await p.ev(`document.getElementById("rc-floors").innerText`), new RegExp(`${arms[1].plan.copies.length} cop`), "a line says how many copies");
  } finally { p.close(); }
});

test("RN12 once done, every square of the grid links to the Floor with the run, the setup and the random run", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  const [id, j] = await runDone(COPIES);
  const p = await page(`runs.html#run=${id}`);
  try {
    await p.sleep(800);
    const links = JSON.parse(await p.ev(`JSON.stringify([...document.querySelectorAll("#rc-grid a.cell")].map(a => a.getAttribute("href")))`));
    const seeds = j.report.seeds, arms = j.report.arms;
    assert.equal(links.length, arms.length * seeds.length, "every square is a link");
    for (let k = 0; k < arms.length; k++) for (const s of seeds)
      assert.ok(links.includes(`index.html?q=${id}&arm=${k}&run=${s}#floor`), `${arms[k].name}, random run ${s}`);
  } finally { p.close(); }
});

test("RN13 the Floor opened from a link plays that run as scored, for two families and for one family's own rule", { skip: !ready && "needs Chrome, the .venv and a release build" }, async () => {
  for (const [text, k, seed] of [[COPIES, 1, 1], [ONE, 1, 2]]) {
    const [id, j] = await runDone(text);
    const arm = j.report.arms[k];
    const p = await page(`index.html?q=${id}&arm=${k}&run=${seed}#floor`);
    try {
      let ok = false;
      for (let i = 0; i < 240 && !ok; i++) { await p.sleep(250); ok = await p.ev(`!!(window.FabFloorPage && FabFloorPage.watching && FabFloorPage.watching() && FabFloorPage.jobs() > 0)`); }
      assert.ok(ok, `${id}: the Floor plays the run`);
      const note = await p.ev(`document.getElementById("runnote").innerText`);
      assert.match(note, new RegExp(id), "the note names the run");
      assert.match(note, new RegExp(arm.name), "and the setup");
      assert.equal(await p.ev(`FabFloorPage.runNumber()`), seed, "the random run");
      const until = await p.ev(`FabFloorPage.end()`);
      const [jobs, fin] = await receiptOf(arm.shop_url, seed, until);
      assert.equal(await p.ev(`FabFloorPage.jobs()`), jobs, `${id} ${arm.name}: the Floor's jobs are the engine's`);
      assert.equal(await p.ev(`FabFloorPage.finished()`), fin, `${id} ${arm.name}: and its finished lots`);
    } finally { p.close(); }
  }
});
