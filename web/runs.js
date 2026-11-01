// Runs you can watch and find again (docs/RUNS.md, part 1). The list of every numbered run from the helper, and a run's
// card at runs.html#run=Q-0004: what was asked and where its setup came from, the stage rail, the log as the simulator
// writes it, a square for each setup on each random run, and each change's 95% interval as runs come in.
// On a teaching fab of our own and the SMT2020 testbed; not a real fab.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const api = async (path) => { const r = await fetch(path, { cache: "no-store" }); return r.json(); };
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
  const mmss = (t) => { t = Math.max(0, Math.round(t)); return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`; };
  const dur = (s) => (s == null ? "" : s < 90 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);
  const usdK = (v) => (v == null ? "—" : `${v < 0 ? "−" : "+"}$${Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toFixed(2) + "M" : Math.round(Math.abs(v) / 1000) + "k"}`);
  const num = (v) => (v == null ? "—" : `${v < 0 ? "−" : "+"}${Math.abs(v) >= 100 ? Math.round(Math.abs(v)).toLocaleString("en-US") : Math.abs(v).toFixed(1)}`);

  // ---------------------------------------------------------------- statistics: the paired t interval, as the engine does
  function lgamma(x) { // Lanczos
    const g = 7, c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
    if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - lgamma(1 - x);
    x -= 1; let a = c[0]; const t = x + g + 0.5;
    for (let i = 1; i < g + 2; i++) a += c[i] / (x + i);
    return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
  }
  function betacf(a, b, x) {
    let qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - (qab * x) / qap;
    d = 1 / (Math.abs(d) < 1e-30 ? 1e-30 : d); let h = d;
    for (let m = 1; m <= 200; m++) {
      const m2 = 2 * m; let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
      d = 1 + aa * d; d = 1 / (Math.abs(d) < 1e-30 ? 1e-30 : d); c = 1 + aa / c; c = Math.abs(c) < 1e-30 ? 1e-30 : c; h *= d * c;
      aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
      d = 1 + aa * d; d = 1 / (Math.abs(d) < 1e-30 ? 1e-30 : d); c = 1 + aa / c; c = Math.abs(c) < 1e-30 ? 1e-30 : c;
      const del = d * c; h *= del; if (Math.abs(del - 1) < 3e-14) break;
    }
    return h;
  }
  function ibeta(a, b, x) {
    if (x <= 0) return 0; if (x >= 1) return 1;
    const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
    return x < (a + 1) / (a + b + 2) ? (bt * betacf(a, b, x)) / a : 1 - (bt * betacf(b, a, 1 - x)) / b;
  }
  const tcdf = (t, n) => { const x = n / (n + t * t), p = 0.5 * ibeta(n / 2, 0.5, x); return t >= 0 ? 1 - p : p; };
  function tq(p, n) { let lo = 0, hi = 1e4; for (let i = 0; i < 200; i++) { const m = (lo + hi) / 2; if (tcdf(m, n) < p) lo = m; else hi = m; } return (lo + hi) / 2; }
  /** Paired differences' mean and the t interval at level 1 - alpha (alpha already split over the changes). */
  function paired(d, alpha) {
    const n = d.length, m = d.reduce((a, b) => a + b, 0) / n;
    const sd = Math.sqrt(d.reduce((a, b) => a + (b - m) * (b - m), 0) / (n - 1)), h = tq(1 - alpha / 2, n - 1) * sd / Math.sqrt(n);
    return { mean: m, lo: m - h, hi: m + h };
  }

  // ---------------------------------------------------------------- the list
  const STATUS = (r) => r.status === "running" ? `running · ${r.runs_done} of ${r.runs_total || "?"}` : r.status === "done" ? "done" : r.status;
  async function showList() {
    $("runs-view").hidden = false; $("run-card").hidden = true; stopPoll();
    let rows = [];
    try { rows = (await api("/api/runs")).runs || []; } catch { /* no helper: the empty note says so */ }
    const tb = $("runs-list").querySelector("tbody");
    tb.innerHTML = rows.map((r) => `<tr data-run="${esc(r.id)}" data-kind="${esc(r.kind || "question")}"><td class="id"><a href="#run=${esc(r.id)}">${esc(r.id)}</a></td>` +
      `<td class="kind">${esc(KINDS[r.kind] || "Question")}</td><td>${esc(r.title || r.question || "A hand-written setup")}</td><td class="note">${esc(when(r.started))}</td>` +
      `<td><span class="pill ${esc(r.status)}">${esc(STATUS(r))}</span>${r.seconds ? ` <span class="note">${esc(dur(r.seconds))}</span>` : ""}</td></tr>`).join("");
    $("runs-empty").hidden = rows.length > 0;
    filterList();
    tb.querySelectorAll("tr[data-run]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("a")) location.hash = `#run=${tr.dataset.run}`; }));
    if (rows.some((r) => r.status === "running")) POLL.list = setTimeout(() => { if (!location.hash) showList(); }, 2000);
  }
  // every kind of run in one list, with chips to show one (docs/RUNS.md, part 3)
  const KINDS = { question: "Question", settings: "Simulation settings", build: "Build", floor: "Floor" };
  let KIND_SHOWN = "";
  function filterList() {
    document.querySelectorAll("#runs-chips [data-kind]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kind === KIND_SHOWN)));
    document.querySelectorAll("#runs-list tbody tr").forEach((tr) => (tr.hidden = !!KIND_SHOWN && tr.dataset.kind !== KIND_SHOWN));
  }
  document.querySelectorAll("#runs-chips [data-kind]").forEach((b) => (b.onclick = () => { KIND_SHOWN = b.dataset.kind; filterList(); }));
  const when = (s) => { if (!s) return ""; const d = new Date(s.replace(/(\+\d{2})(\d{2})$/, "$1:$2")); return isNaN(d) ? s : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); };

  // ---------------------------------------------------------------- a run's card
  const POLL = { timer: null, list: null };
  function stopPoll() { clearTimeout(POLL.timer); clearTimeout(POLL.list); POLL.timer = POLL.list = null; }
  let RUN = null; // { id, job, events, start, arms, names, seeds, measure }

  async function showRun(id) {
    $("runs-view").hidden = true; $("run-card").hidden = false; stopPoll();
    RUN = { id, job: null, events: [], start: null, arms: [], names: {}, seeds: [], measure: "profit" };
    $("run-card").querySelector(".runid").textContent = id;
    $("rc-addr").textContent = `runs.html#run=${id}`;
    await poll();
  }

  async function poll() {
    const r = RUN;
    let j;
    try { j = await api(`/api/job/${encodeURIComponent(r.id)}?since=${r.events.length}`); } catch { j = { error: "The helper is not answering." }; }
    if (r !== RUN) return; // another run was opened meanwhile
    if (j.error && !j.stage) { $("rc-question").textContent = j.error; $("rc-status").textContent = "not found"; return; }
    r.job = j;
    if (j.since === r.events.length) r.events.push(...(j.events || []));
    else if (j.since === 0) r.events = j.events || [];
    const st = r.events.find((e) => e.e === "start");
    if (st && !r.start) { r.start = st; r.arms = st.arms; r.seeds = st.seeds; r.measure = st.measure; }
    draw();
    if (j.stage !== "done" && j.stage !== "failed") POLL.timer = setTimeout(poll, 1000);
  }

  function setupNames(j) {
    const sc = j.scenario ? FabAsk.scenarioLines(j.scenario) : { given: [], candidates: [] };
    const names = { today: "Today's fab" };
    for (const c of sc.candidates) names[c.name] = cap(c.changes.join(", and "));
    return { sc, names };
  }

  function draw() {
    const kept = RUN.job && RUN.job.kind && RUN.job.kind !== "question";
    $("rc-kept").hidden = !kept; $("rc-live").hidden = !!kept; $("rc-forest-panel").hidden = !!kept;
    $("rc-two").hidden = !!kept && RUN.job.kind !== "settings";
    if (kept) return drawKept(RUN.job);
    const r = RUN, j = r.job, { sc, names } = setupNames(j);
    r.names = names;
    const card = $("run-card");
    const runs = r.events.filter((e) => e.e === "run" && (e.point === null || e.point === undefined));
    const total = r.start ? r.start.runs : j.runs_total || 0;
    card.dataset.done = String(r.events.filter((e) => e.e === "run").length);
    card.dataset.total = String(total);
    card.dataset.stage = j.stage;
    // status and facts
    const status = j.stage === "done" ? "done" : j.stage === "failed" ? "failed" : "running";
    $("rc-status").className = `pill ${status}`;
    $("rc-status").textContent = status === "running" ? `running · ${mmss(j.elapsed || 0)}` : status === "done" ? `done in ${dur(j.seconds)}` : "stopped";
    $("rc-question").textContent = j.question || (sc.question || "A hand-written setup");
    const src = j.answer_source === "model" ? `Meta's Muse Spark (${esc(j.model || "the model")}) turned your question into this setup, and the simulator checked it before running.`
      : j.answer_source === "example" ? "Your question matched one of our hand-written examples, so this setup was written by hand. No model ran."
      : "Written by hand in the ask panel. No model ran.";
    const given = sc.given.map((g) => `<li>${g.said ? "You said: " : "Assumed: "}${esc(g.text.charAt(0).toLowerCase() + g.text.slice(1))}</li>`).join("");
    const p = r.start;
    $("rc-facts").innerHTML = `<dt>Setup from</dt><dd>${src}</dd>` +
      `<dt>Given</dt><dd>${given ? `<ul>${given}</ul>` : "Today's fab as it is."}</dd>` +
      `<dt>Compared</dt><dd><ul>${["today", ...sc.candidates.map((c) => c.name)].map((n) => `<li>${esc(names[n] || n)}</li>`).join("")}</ul></dd>` +
      (p ? `<dt>Random runs</dt><dd>${p.seeds.length}, the same ones for every setup, so luck cancels out</dd>` +
        `<dt>Each run</dt><dd>${p.warmup_days + p.window_days} simulated days: ${p.warmup_days} to fill up, then ${p.window_days} scored</dd>` +
        `<dt>In all</dt><dd>${p.runs} runs on ${p.threads} cores</dd>` : "") +
      `<dt>Fab</dt><dd>Built from the SMT2020 testbed; prices assumed</dd>`;
    drawRail(j, runs.length);
    drawProgress(j, total);
    drawLog();
    drawGrid(runs);
    drawForest(runs, j);
    drawFloors(j);
  }

  const STAGES = [["Read the question", "what is asked"], ["Check the setup", "what can run"], ["Lay out floors", "where tools stand"],
    ["Simulate", "every setup, every random run"], ["Compare", "against today"], ["Sign", "a person signs"]];
  function drawRail(j, done) {
    const floors = RUN.events.some((e) => e.e === "floor");
    let now = j.stage === "queued" || j.stage === "asking the model" ? 0 : j.stage === "checking the scenario" ? 1
      : j.stage === "laying out and simulating" ? (done > 0 || (RUN.start && !floors && RUN.events.length > 1) ? 3 : 2) : j.stage === "done" ? 5 : 3;
    const failed = j.stage === "failed";
    $("rc-rail").innerHTML = STAGES.map(([b, t], i) => {
      const cls = failed && i === now ? "bad" : i < now ? "done" : i === now ? "now" : "";
      const sub = i === 2 && !floors && RUN.start && RUN.events.length > 1 ? "the floor as it is" : t;
      return `<div class="st ${cls}"><b>${b}</b>${sub}</div>`;
    }).join("");
  }
  function drawProgress(j, total) {
    const done = RUN.events.filter((e) => e.e === "run").length, el = $("rc-progress");
    el.className = `progress ${j.stage === "done" ? "done" : ""}`;
    if (j.stage === "done") el.textContent = `All ${total} runs done in ${dur(j.seconds)}.`;
    else if (j.stage === "failed") el.textContent = j.error || "The run stopped.";
    else if (!total) el.textContent = `${cap(j.stage || "starting")}… ${mmss(j.elapsed || 0)}`;
    else el.textContent = `Run ${done} of ${total}` + (j.minutes_left != null ? ` · about ${j.minutes_left < 1 ? "under a minute" : Math.round(j.minutes_left) + " min"} left` : done < 2 ? " · the estimate comes after two runs" : "");
  }
  function logLine(e, k) {
    const nm = (a) => (RUN.names[a] || a).toLowerCase();
    if (e.e === "start") return [`Started: ${e.arms.length} setups × ${e.seeds.length} random runs, ${e.warmup_days + e.window_days} days each`, ""];
    if (e.e === "floor") return e.how === "none" ? [`Floor ready: ${nm(e.arm)} (${e.groups} groups)`, ""]
      : [`Floor laid out: ${nm(e.arm)} (${e.copies ? `${e.copies} groups copied, ` : ""}${e.groups} groups placed), ${e.how === "saved" ? "from the saved layouts" : `new, ${dur(e.seconds)}`}`, "ok"];
    if (e.e === "run") {
      const today = RUN.events.find((x) => x.e === "run" && x.arm === "today" && x.seed === e.seed && x.point === e.point);
      const v = RUN.measure === "profit" ? `profit ${usdK(e.value).replace("+", "")} a day` : `reward ${Math.round(e.value).toLocaleString("en-US")}`;
      const vs = e.arm !== "today" && today && e.value != null && today.value != null ? `, ${RUN.measure === "profit" ? usdK(e.value - today.value) : num(e.value - today.value)} against today` : "";
      return [`Run ${k} of ${RUN.start ? RUN.start.runs : "?"} done: ${nm(e.arm)}, random run ${e.seed + 1}: ${v}${vs}`, vs ? (e.value - today.value >= 0 ? "ok" : "warn") : ""];
    }
    if (e.e === "end") return [e.best ? `All runs done. Leader: ${nm(e.best)}.` : "All runs done. No change beat today.", "ok"];
    return [JSON.stringify(e), ""];
  }
  function drawLog() {
    let k = 0;
    const lines = RUN.events.map((e) => { if (e.e === "run") k++; const [m, c] = logLine(e, k); return `<div><span class="t">${mmss(e.t || 0)}</span><span class="${c}">${esc(m)}</span></div>`; });
    const el = $("rc-log"), atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
    if (!lines.length) lines.push(`<div><span class="t">${mmss(RUN.job.elapsed || 0)}</span><span>${esc(cap(RUN.job.stage || "starting"))}…</span></div>`);
    el.innerHTML = lines.join("");
    if (atEnd) el.scrollTop = el.scrollHeight;
  }
  function drawGrid(runs) {
    const arms = RUN.arms.length ? RUN.arms : ["today"], seeds = RUN.seeds.length ? RUN.seeds : [];
    const g = $("rc-grid");
    g.style.gridTemplateColumns = `minmax(110px, max-content) repeat(${Math.max(1, seeds.length)}, minmax(18px, 1fr))`;
    const val = (a, s) => runs.find((e) => e.arm === a && e.seed === s);
    let html = `<span></span>` + seeds.map((s) => `<span class="h">${s + 1}</span>`).join("");
    for (const a of arms) {
      html += `<span class="nm">${esc(RUN.names[a] || a)}</span>`;
      for (const s of seeds) {
        const e = val(a, s), t = val("today", s);
        let cls = "cell";
        if (e) cls += " filled" + (a === "today" ? "" : t && e.value != null && t.value != null ? (e.value >= t.value ? " up" : " down") : "");
        const tip = `${esc(RUN.names[a] || a)}, random run ${s + 1}${e && e.value != null ? `: ${RUN.measure} ${Math.round(e.value).toLocaleString("en-US")}` : ""}`;
        // once the run is done, each square opens that setup's random run on the Floor (docs/RUNS.md, part 2)
        const k = armIndex(a);
        html += k >= 0 ? `<a class="${cls}" href="${floorLink(k, s)}" title="${tip}. Open it on the Floor"></a>` : `<span class="${cls}" title="${tip}"></span>`;
      }
    }
    g.innerHTML = html;
  }
  // ---------- part 3 (docs/RUNS.md): the cards of Simulation settings, Build and Floor runs
  const table = (cols, rows, id) => `<table${id ? ` id="${id}"` : ""}><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const facts = (pairs) => pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  let LAYOUT = { id: null, svg: "" };
  function drawKept(j) {
    const rec = j.record || {}, kind = j.kind, card = $("run-card");
    card.dataset.stage = j.stage; card.dataset.done = String(j.runs_done || 0); card.dataset.total = String(j.runs_total || 0);
    $("rc-status").className = "pill done"; $("rc-status").textContent = "done";
    $("rc-question").textContent = j.title || KINDS[kind];
    $("rc-floors-panel").hidden = true;
    if (kind === "settings") {
      $("rc-facts").innerHTML = facts(rec.settings || []);
      const s = rec.summary || { columns: [], rows: [] };
      $("rc-kept").innerHTML = `<h3>Against today on the same random runs</h3>${table(s.columns, s.rows, "rc-measures")}` +
        `<p class="note">Paired over ${(rec.seeds || []).length} random runs in the browser, each a 95% interval of the change minus today. The squares below are each random run's wafers out against today.</p>` +
        (rec.link ? `<a class="open" href="${esc(rec.link)}">Open the Floor on this run →</a>` : "");
      const st = RUN.events.find((e) => e.e === "start");
      if (st) { RUN.start = st; RUN.arms = st.arms; RUN.seeds = st.seeds; RUN.measure = "wafers out"; }
      RUN.names = { today: "Today's fab", change: (j.title || "").replace(/^Simulation settings: /, "") || "The change" };
      drawGrid(RUN.events.filter((e) => e.e === "run"));
      return;
    }
    if (kind === "floor") {
      $("rc-facts").innerHTML = facts([["Fab", "Today's fab, built from the SMT2020 testbed"], ["Where", "the simulator in the browser"]]);
      const s = rec.summary || { columns: [], rows: [] };
      $("rc-kept").innerHTML = table(s.columns, s.rows) + (rec.link ? `<a class="open" href="${esc(rec.link)}">Open it on the Floor →</a>` : "");
      return;
    }
    // a Build run: its layout drawn from its own fab file, its score, and the way back into Build
    const sc = rec.score || {};
    $("rc-facts").innerHTML = facts([["From", rec.challenge ? rec.title : `${rec.title || "Free build"} (${rec.template === "smt2020" ? "the full fab" : "the small fab"})`],
      ["Random run", `#${rec.seed}`], ["Days", String(rec.days)]]);
    const nums = [["Wafers out a day", sc.wafers_per_day != null ? Math.round(sc.wafers_per_day).toLocaleString("en-US") : "—"],
      ["Days a wafer takes", sc.cycle_days != null ? sc.cycle_days.toFixed(2) : "—"], ["Jams", sc.jams != null ? String(sc.jams) : "—"]];
    $("rc-kept").innerHTML = `<div class="layout" id="rc-layout">${LAYOUT.id === j.id ? LAYOUT.svg : "<p class=\"note\">Drawing the layout…</p>"}</div>${table(["Measure", "Value"], nums)}` +
      `<a class="open" href="editor.html?run=${esc(j.id)}">Open in Build →</a>`;
    if (LAYOUT.id !== j.id && rec.fab_url) fetch(rec.fab_url).then((r) => r.text()).then((txt) => { LAYOUT = { id: j.id, svg: layoutSvg(txt) }; if (RUN && RUN.id === j.id) $("rc-layout").innerHTML = LAYOUT.svg; });
  }
  /** A Build layout from its fab file: the track's links, each machine group's station and each storage, from above. */
  function layoutSvg(txt) {
    const L = txt.split("\n").map((l) => l.split("\t")), node = {};
    for (const f of L) if (f[0] === "node") node[f[1]] = [+f[2], +f[3]];
    const pts = [...Object.values(node), ...L.filter((f) => f[0] === "station").flatMap((f) => [[+f[2], +f[3]], [+f[2] + +f[4], +f[3] + +f[5]]])];
    if (!pts.length) return "<p class=\"note\">This layout has no plan to draw.</p>";
    const x0 = Math.min(...pts.map((p) => p[0])) - 4, y0 = Math.min(...pts.map((p) => p[1])) - 4, x1 = Math.max(...pts.map((p) => p[0])) + 4, y1 = Math.max(...pts.map((p) => p[1])) + 4;
    let s = `<svg viewBox="${x0} ${y0} ${x1 - x0} ${y1 - y0}" role="img" aria-label="The layout from above">`;
    for (const f of L) if (f[0] === "link" && node[f[1]] && node[f[2]]) s += `<line data-link x1="${node[f[1]][0]}" y1="${node[f[1]][1]}" x2="${node[f[2]][0]}" y2="${node[f[2]][1]}" stroke="#2F6470" stroke-width="1.4" stroke-linecap="round"/>`;
    for (const f of L) if (f[0] === "station") {
      const a = (window.FabLook && FabLook.AREA_OF) ? FabLook.areaOf(f[1].replace(/_T$/, "")) || FabLook.areaOf(f[1].split("_")[0]) : null;
      s += `<rect data-block="${esc(f[1])}" x="${+f[2] + 0.4}" y="${+f[3] + 0.4}" width="${+f[4] - 0.8}" height="${+f[5] - 0.8}" rx="0.8" fill="${(a && FabLook.FAM[a]) || "#8FB3AE"}"><title>${esc(f[1])}</title></rect>`;
    }
    for (const f of L) if (f[0] === "stocker" && node[f[1]]) s += `<rect data-block="storage" x="${node[f[1]][0] - 2}" y="${node[f[1]][1] - 2}" width="4" height="4" rx="0.6" fill="#8A6A2C"><title>Storage</title></rect>`;
    return s + "</svg>";
  }

  // ---------- part 2 (docs/RUNS.md): each setup's floor, and links that open any run on the Floor
  const doneArms = () => (RUN.job && RUN.job.stage === "done" && RUN.job.report && RUN.job.report.arms ? RUN.job.report.arms : null);
  const armIndex = (name) => { const arms = doneArms(); return arms ? arms.findIndex((x) => x.name === name) : -1; };
  const floorLink = (k, s) => `index.html?q=${encodeURIComponent(RUN.id)}&arm=${k}&run=${s}#floor`;
  let AREA_OF_GROUP = null;
  fetch("data/areas.tsv").then((r) => (r.ok ? r.text() : "")).then((t) => {
    AREA_OF_GROUP = {};
    for (const l of t.split("\n")) { const [g, a] = l.split("\t"); if (g) AREA_OF_GROUP[g] = a; }
    if (RUN && RUN.job) drawFloors(RUN.job);
  }).catch(() => { AREA_OF_GROUP = {}; });
  /** A setup's floor from above: each phase's spine, each group on its side at its place along the spine and depth. */
  function floorSvg(plan, extra) {
    const L = plan.phases.length ? plan.phases : [Math.max(...plan.groups.map((g) => g.x)) + 10], BR = 60, D = 62, SP = 8;
    const off = L.map((_, i) => L.slice(0, i).reduce((a, b) => a + b, 0) + i * BR), W = off[L.length - 1] + L[L.length - 1], H = 2 * D + SP;
    const copies = new Set(plan.copies), moved = new Set(plan.moved);
    let s = `<svg viewBox="-4 -4 ${W + 8} ${H + 8}" role="img" aria-label="The floor from above: ${plan.groups.length} groups">`;
    L.forEach((len, i) => { s += `<rect x="${off[i]}" y="0" width="${len}" height="${H}" rx="3" fill="#10232A"/><rect x="${off[i]}" y="${D}" width="${len}" height="${SP}" fill="#2F6470"/>`; });
    for (let i = 0; i + 1 < L.length; i++) s += `<rect x="${off[i] + L[i]}" y="${D}" width="${BR}" height="${SP}" fill="#285059"/>`;
    for (const g of plan.groups) {
      const base = g.g.replace(/@B$/, ""), area = (extra[g.g]) || (AREA_OF_GROUP || {})[base] || "", key = window.FabLook ? FabLook.areaOf(area) : null;
      const col = copies.has(g.g) ? "#FF8AD8" : (key && FabLook.FAM[key]) || "#8FB3AE";
      const sz = Math.min(12, 4 + Math.sqrt(g.tools) * 1.6), x = off[g.phase] + g.x - sz / 2, y = (g.side === 0 ? D - g.y : D + SP + g.y) - sz / 2;
      s += `<rect data-g="${esc(g.g)}" class="${copies.has(g.g) ? "copy" : ""}${moved.has(g.g) ? " moved" : ""}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${sz.toFixed(1)}" height="${sz.toFixed(1)}" rx="1.5" fill="${col}"><title>${esc(g.g)}${area ? ` (${esc(area)})` : ""}: ${g.tools} tool${g.tools === 1 ? "" : "s"}${copies.has(g.g) ? ", a copy for prototypes" : moved.has(g.g) ? ", stands elsewhere than today" : ""}</title></rect>`;
    }
    return s + "</svg>";
  }
  function drawFloors(j) {
    const arms = doneArms(), box = $("rc-floors"), panel = $("rc-floors-panel");
    if (!arms || !arms.length) { panel.hidden = true; return; }
    panel.hidden = false;
    const first = RUN.seeds.length ? RUN.seeds[0] : (j.report.seeds || [0])[0];
    const watch = (k) => `<a class="watch" href="${floorLink(k, first)}">Watch random run ${first + 1} on the Floor →</a>`;
    const planned = arms.some((a) => a.plan);
    $("rc-floors-note").textContent = planned
      ? "Drawn from above from each setup's own fab file: halls along their spines, each group on its side, coloured by area. Copies for prototypes are pink; groups standing elsewhere than in today's floor are ringed. Every square in the grid opens that run on the Floor."
      : "Every setup here uses today's floor; the changes are in the rules. Every square in the grid opens that run on the Floor.";
    box.innerHTML = arms.map((a, k) => {
      const nm = RUN.names[a.name] || a.name, extra = Object.fromEntries(a.extra_areas || []);
      if (!a.plan) return `<div class="floor"><h4>${esc(nm)}</h4>${watch(k)}</div>`;
      const c = a.plan.copies.length, m = a.plan.moved.length;
      const line = a.name === "today" ? "Today's floor." : !c && !m ? "The same floor as today." : [c && `${c} cop${c === 1 ? "y" : "ies"} for prototypes`, m && `${m} group${m === 1 ? "" : "s"} standing elsewhere than today`].filter(Boolean).join("; ") + ".";
      return `<div class="floor"><h4>${esc(nm)}</h4>${floorSvg(a.plan, extra)}<p>${esc(line)}</p>${watch(k)}</div>`;
    }).join("");
  }

  function drawForest(runs, j) {
    const svg = $("rc-forest"), cands = RUN.arms.filter((a) => a !== "today"), m = RUN.measure;
    $("rc-forest-title").textContent = m === "profit" ? "Profit a day against today, 95% intervals" : "Reward against today, 95% intervals";
    const alpha = 0.05 / Math.max(1, cands.length);
    const final = j.stage === "done" && j.report ? j.report : null;
    const rows = cands.map((a) => {
      if (final) {
        const c = final.candidates.find((x) => x.name === a), mm = c && c.measures[m];
        return mm ? { a, n: mm.today.length, mean: mm.mean, lo: mm.lo, hi: mm.hi, verdict: mm.verdict } : { a, n: 0 };
      }
      const d = RUN.seeds.map((s) => { const t = runs.find((e) => e.arm === "today" && e.seed === s), x = runs.find((e) => e.arm === a && e.seed === s);
        return t && x && t.value != null && x.value != null ? x.value - t.value : null; }).filter((v) => v !== null);
      return d.length >= 2 ? { a, n: d.length, ...paired(d, alpha) } : { a, n: d.length };
    });
    const shown = rows.filter((r) => r.lo != null && isFinite(r.lo));
    const lo = Math.min(0, ...shown.map((r) => r.lo)), hi = Math.max(0, ...shown.map((r) => r.hi)), pad = (hi - lo) * 0.08 || 1;
    const X0 = 200, X1 = 470, x = (v) => X0 + ((v - (lo - pad)) / (hi + pad - (lo - pad))) * (X1 - X0), H = 34 + rows.length * 44;
    svg.setAttribute("viewBox", `0 0 560 ${H}`);
    let s = shown.length ? `<line x1="${x(0)}" y1="16" x2="${x(0)}" y2="${H - 6}" stroke="#5D7F84" stroke-dasharray="3 3"/><text x="${x(0)}" y="11" fill="#7FA6A2" font-size="11" text-anchor="middle">same as today</text>` : "";
    rows.forEach((r, i) => {
      const y = 38 + i * 44, nm = RUN.names[r.a] || r.a;
      s += `<text x="4" y="${y + 4}" fill="#CFE3E0" font-size="13">${esc(nm.length > 30 ? nm.slice(0, 29) + "…" : nm)}<title>${esc(nm)}</title></text>` +
        `<text x="4" y="${y + 19}" fill="#7FA6A2" font-size="11">${r.n} of ${RUN.seeds.length} random runs</text>`;
      if (r.lo == null || !isFinite(r.lo)) { s += `<text x="${X0}" y="${y + 4}" fill="#7FA6A2" font-size="11.5">waiting for two random runs</text>`; return; }
      const v = r.verdict || (r.n === RUN.seeds.length ? (r.lo > 0 ? "better" : r.hi < 0 ? "worse" : "no clear effect") : null);
      const col = r.lo > 0 ? "#4FE3A3" : r.hi < 0 ? "#FF8A7A" : "#CFE3E0", f = m === "profit" ? usdK : num;
      s += `<g class="ival"><line x1="${x(r.lo)}" y1="${y}" x2="${x(r.hi)}" y2="${y}" stroke="${col}" stroke-width="2.4"/>` +
        `<line x1="${x(r.lo)}" y1="${y - 6}" x2="${x(r.lo)}" y2="${y + 6}" stroke="${col}" stroke-width="2"/><line x1="${x(r.hi)}" y1="${y - 6}" x2="${x(r.hi)}" y2="${y + 6}" stroke="${col}" stroke-width="2"/>` +
        `<circle cx="${x(r.mean)}" cy="${y}" r="5" fill="${col}"/></g>` +
        `<text x="${X1 + 10}" y="${y - 2}" fill="${col}" font-size="11.5">${f(r.mean)}</text>` +
        `<text x="${X1 + 10}" y="${y + 13}" fill="${col}" font-size="11">${v ? esc(v) : "so far"}</text>`;
    });
    svg.innerHTML = s;
    $("rc-forest-note").textContent = final ? `Final: paired t intervals over ${RUN.seeds.length} random runs, each at 1 − 0.05/${cands.length} so all hold together at 95%.`
      : `So far: recomputed as runs finish, from the random runs both today and the change have done. Final only when all are in.`;
    const best = final ? final.best : null, el = $("rc-leader");
    if (!final) el.textContent = "";
    else if (best) { const b = rows.find((r) => r.a === best); el.innerHTML = `Leader: <b>${esc(RUN.names[best] || best)}</b>${b ? `, ${esc((m === "profit" ? usdK : num)(b.mean))} ${m === "profit" ? "a day" : ""} against today (95%: ${esc((m === "profit" ? usdK : num)(b.lo))} to ${esc((m === "profit" ? usdK : num)(b.hi))})` : ""}. Not signed yet: a person signs it in the ask panel on the Floor.`; }
    else el.textContent = "No change beat today: none is better on the whole interval.";
  }

  // ---------------------------------------------------------------- routing on the address
  function route() {
    const m = /^#run=([A-Z]-\d{4,})$/.exec(location.hash);
    if (m) showRun(m[1]); else showList();
  }
  addEventListener("hashchange", route);
  route();
  window.FabRunsPage = { paired, tq, run: () => RUN };
})();
