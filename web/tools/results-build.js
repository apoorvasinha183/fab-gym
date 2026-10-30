// The Results tab's saved entries: each experiment under results/ as its question, the simulator's settings, the
// numbers that came from it and its files. Run by web/build.sh (node web/tools/results-build.js > web/data/results.json).
// From the SMT2020 testbed, a published set of a fab's tool groups, routes and times. No real fab's data is used.
"use strict";
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const NOTE = "Run on a fab built from the SMT2020 testbed, a public research set of a chip fab's machines, routes and times. No real company's data is used.";
const WHO = { ppo: "the trained AI", "e2-best": "the evolved rule", today: "today's rule" };
const FLOORS = { "D1 share": "Shared floor", "D2 wing": "Prototype wing", "D3 copies": "Copies in the halls" };
const POLICIES = { "P0 today": "today's order", "P1 family B first": "prototypes first", "P2 family cap": "prototypes capped at the door",
  "P3 reservation": "a tool kept for prototypes", "P4 qualification": "prototypes on half the tools" };
const MEASURES = { reward: "Score (lots out, minus time spent waiting)", moves: "Deliveries", lots_finished: "Lots finished", wait_lot_hours: "Hours lots spent waiting",
  breaches: "Time limits missed between steps" };

/** A sweep's verdict across breakdown rates in everyday words. */
function plainVerdict(v) {
  return v.replace(/ (on|from) the SMT2020 (model|testbed)/g, "").replace(/same verdict at every rate: (\w+)/, "$1 at every breakdown rate")
    .replace(/at some rates/g, "at some breakdown rates").replace(/no clear effect at any rate/, "too close to call at every breakdown rate").replace(/no clear effect/g, "too close to call");
}

function n(x, d = 0) { return x === null || x === undefined || !isFinite(x) ? "—" : Number(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }
function sg(x, d = 0) { return x === null || x === undefined || !isFinite(x) ? "—" : (x > 0 ? "+" : x < 0 ? "−" : "") + n(Math.abs(x), d); }
function usd(x, sign = true) {
  if (x === null || x === undefined || !isFinite(x)) return "—";
  const s = x < 0 ? "−" : sign && x > 0 ? "+" : "", a = Math.abs(x);
  return `${s}$${a >= 1e6 ? `${+(a / 1e6).toFixed(2)}M` : a >= 1e4 ? `${Math.round(a / 1e3)}k` : Math.round(a).toLocaleString("en-US")}`;
}
function days(x) { return x === null || x === undefined ? "never" : x < 1 ? "at once" : x < 60 ? `${Math.round(x)} days` : `${(x / 30.4).toFixed(0)} months`; }
function seedsText(s) { return s.length ? `${s[0]} to ${s[s.length - 1]} (${s.length})` : "—"; }

// when a result was saved: its last commit, else the file's time
function when(root, rel) {
  try {
    const t = execFileSync("git", ["log", "-1", "--format=%cI", "--", rel], { cwd: root, encoding: "utf8" }).trim();
    if (t) return t;
  } catch (e) { /* not in git */ }
  return fs.statSync(path.join(root, rel)).mtime.toISOString();
}
const read = (root, rel) => fs.readFileSync(path.join(root, rel), "utf8");
const json = (root, rel) => JSON.parse(read(root, rel));
const exists = (root, rel) => fs.existsSync(path.join(root, rel));

function twoFamilies(root) {
  const s = json(root, "results/two-families/summary.json");
  const pl = exists(root, "results/two-families/pl.json") ? json(root, "results/two-families/pl.json") : null;
  const price = (k) => { const it = pl && pl.sheet.find((x) => x.key === k); return it ? it.central : null; };
  const settings = [
    ["Starting point", "The SMT2020 high-volume testbed, plus prototype lots (family B) rebuilt from SMT2020's engineering lots"],
    ["Run length", `${s.days} simulated days; the first ${s.warmup} are warm-up, days ${s.warmup} to ${s.days} are scored`],
    ["Seeds", seedsText(s.seeds)],
    ["Prototype orders", "×1, ×2, ×4, ×8 the published 20 lots a release"],
    ["Floors", Object.values(FLOORS).join(", ")],
    ["Policies", Object.values(POLICIES).join(", ")],
    ["Compared with", "the shared floor with today's order, at the same share and on the same seeds"],
    ["Intervals", `paired t, Bonferroni over 56 cells (each at level ${n(s.alpha_each, 5)})`],
  ];
  if (pl) settings.push(["Prices (assumed)", `volume wafer ${usd(price("a_price"), false)}, prototype wafer ${usd(price("b_price"), false)}, materials ${usd(price("materials"), false)} a wafer, a tool ${usd(price("tool_other"), false)} (lithography ${usd(price("tool_litho"), false)})`]);
  settings.push(["Compute", `${n(s.seconds)} s on 4 threads`], ["Command", "fabsim two-families --threads 4, then fabsim pl"]);
  const rows = pl ? pl.cells.map((c) => [`×${c.share}`, FLOORS[c.strategy], POLICIES[c.policy], usd(c.profit.mean), `${usd(c.profit.lo)} to ${usd(c.profit.hi)}`,
    c.capital ? usd(c.capital, false) : "none", c.capital ? days(c.payback_days.soonest) : "—", c.verdict])
    : s.cells.map((c) => [`×${c.share}`, FLOORS[c.strategy], POLICIES[c.policy], sg(c.money.mean, 1), `${sg(c.money.lo, 1)} to ${sg(c.money.hi, 1)}`, "—", "—", c.money.verdict]);
  const best = pl ? [1, 2, 4, 8].map((sh) => { const c = pl.cells.filter((x) => x.share === sh).sort((a, b) => b.profit.mean - a.profit.mean)[0]; return c ? `×${sh}: ${FLOORS[c.strategy].toLowerCase()} with ${POLICIES[c.policy]} (${usd(c.profit.mean)} a day, ${c.verdict})` : ""; }).join("; ") : "";
  const files = ["results/two-families/summary.json", "results/two-families/runs.tsv", "docs/TWO-FAMILIES-SWEEP.md"]
    .concat(pl ? ["results/two-families/pl.json", "results/two-families/pl-runs.tsv", "docs/MONEY-PL.md"] : []);
  return {
    id: "two-families", kind: "sweep", when: when(root, pl ? "results/two-families/pl.json" : "results/two-families/summary.json"),
    title: "Prototypes and the main product: which layout and rule pay best as prototype orders grow",
    question: "As prototype orders grow, which floor layout and which rule for prototypes make the most money, and when does the answer change?",
    settings, headline: best ? `The most profitable change at each level of prototype orders: ${best}.` : "Open the table for each change.",
    numbers: { columns: ["Prototype orders", "Floor", "Policy", pl ? "Change in operating profit a day" : "Change in money a day", "95% interval", "Capital", "Pays back in", "Verdict"], rows },
    files, note: `${NOTE} Every price is assumed.`,
  };
}

function evolve(root) {
  const claim = read(root, "results/evolve-x4/claim.md");
  const m = (re) => { const x = claim.match(re); return x ? x[1] : "—"; };
  const lines = claim.split("\n").filter((l) => l.startsWith("|"));
  const head = lines[0].split("|").slice(1, -1).map((x) => x.trim());
  const rows = [];
  for (const l of lines.slice(2)) {
    const f = l.split("|").slice(1, -1).map((x) => x.trim());
    if (f.length !== head.length) break;
    rows.push(f);
  }
  const gens = read(root, "results/evolve-x4/history.tsv").trim().split("\n").length - 1;
  return {
    id: "evolve-x4", kind: "search", when: when(root, "results/evolve-x4/claim.md"),
    title: "The evolved rule: a search that grows a layout and a rule together, at four times the prototype orders",
    question: "Can a search that breeds layouts and rules beat the rules people wrote by hand?",
    settings: [
      ["Prototype orders", "×4"], ["Population", m(/population (\d+)/)], ["Generations", m(/(\d+) generations/)],
      ["Training seeds", m(/training seeds ([\d.]+)/)], ["Held-out seeds", m(/held-out seeds \(([\d.]+)\)/)],
      ["Scored", m(/(\d+ days, window days [\d ]+to \d+)/)], ["Individuals tried", String(gens)],
      ["Money", "money a day at the central prices, in wafers of family-A margin (the units before dollars)"],
      ["Command", "fabsim evolve"],
    ],
    headline: "All three evolved pairs lost to today's setup and to putting prototypes first. Their rules ended up ignoring the lots, so today's rule made every choice.",
    numbers: { columns: head, rows }, files: ["results/evolve-x4/claim.md", "results/evolve-x4/history.tsv", "docs/EVOLVE.md"],
    note: `${NOTE} Every price is assumed.`,
  };
}

function lean(root) {
  const s = json(root, "results/lean-long-units/summary.json");
  const rows = s.cells.map((c) => [c.metric.replace(/_/g, " "), `×${c.k}`, n(c.cap), n(c.base_mean, 1), n(c.cap_mean, 1), sg(c.mean, 1), `${sg(c.lo, 1)} to ${sg(c.hi, 1)}`, c.verdict.replace(/ (on|from) the SMT2020 (model|testbed)/, "")]);
  return {
    id: "lean-long-units", kind: "sweep", when: when(root, "results/lean-long-units/summary.json"),
    title: "Does a cap on lots inside still pay when machines break more often?",
    question: "Does capping the lots inside the fab cost wafers, and does the answer change when machines break more often?",
    settings: [["Run length", `${s.days} days; warm-up ${s.warmup}`], ["Seeds", seedsText(s.seeds)], ["Caps", [...new Set(s.cells.map((c) => c.cap))].join(", ") + " lots"],
      ["Breakdown rates", [...new Set(s.cells.map((c) => `×${c.k}`))].join(", ")], ["Intervals", `paired t, Bonferroni (each at level ${n(s.alpha_each, 4)})`],
      ["Compute", `${n(s.seconds)} s`], ["Command", "fabsim lean-long"]],
    headline: s.flips.map((f) => `A cap of ${n(f.cap)} lots: ${plainVerdict(f.crossover)}`).join(". ") + ".",
    numbers: { columns: ["Measure", "Breakdowns", "Cap", "No cap", "With cap", "Change", "95% interval", "Verdict"], rows },
    files: ["results/lean-long-units/summary.json", "results/lean-long-units/runs.tsv", "results/lean-long-units/summary.md"], note: NOTE,
  };
}

function rlTrain(root) {
  const t = json(root, "results/rl-defects/ppo/train.json");
  const rows = [];
  for (let i = 0; i < 4; i++) {
    const rel = `results/rl-defects/ppo/monitor-${i}.monitor.csv`;
    if (!exists(root, rel)) continue;
    const r = read(root, rel).trim().split("\n").slice(2).map((l) => Number(l.split(",")[0]));
    const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
    rows.push([`worker ${i + 1}`, String(r.length), n(mean(r.slice(0, 5)), 1), n(mean(r.slice(-5)), 1)]);
  }
  return {
    id: "rl-train", kind: "training", when: when(root, "results/rl-defects/ppo/train.json"),
    title: "The trained AI: learning which lot to run next, with quality holds",
    question: "Can an AI that practises one choice at a time beat today's rule when quality checks stop machines and lots?",
    settings: [["Training seeds", seedsText(t.seeds)], ["Defect holds (assumed)", `tool ${t.defects[0]} min, lookback ${t.defects[1]} min, lots ${t.defects[2]} min`],
      ["Episode", `${t.warmup_days} day warm-up under today's rule, then ${t.window_days} days of decisions`], ["Decisions trained", n(t.timesteps)],
      ["Workers", String(t.workers)], ["Steps per update", n(t.n_steps)], ["Libraries", Object.entries(t.versions).map(([k, v]) => `${k} ${v}`).join(", ")],
      ["Compute", `${n(t.seconds)} s on the Linux server`], ["Command", "python -m agent.rl train --seeds 100..200 --defects 120,240,60 --timesteps 3000000 --workers 4"]],
    headline: (() => {
      const f = rows.map((r) => Number(r[2].replace(/,/g, ""))), l = rows.map((r) => Number(r[3].replace(/,/g, "")));
      const m = (xs) => xs.reduce((p, q) => p + q, 0) / xs.length;
      return `Its average score went from ${n(m(f), 1)} in its first 5 practice runs to ${n(m(l), 1)} in its last 5. The contest on new days shows how it really plays.`;
    })(),
    numbers: { columns: ["Worker", "Episodes", "Mean reward, first 5 episodes", "Mean reward, last 5 episodes"], rows },
    files: ["results/rl-defects/ppo/train.json", "results/rl-defects/ppo/policy.zip", "docs/RL-DEFECTS.md"],
    note: `${NOTE} Defect holds and their lengths are assumed; how often they happen follows SMT2020's published rework rates.`,
  };
}

function rlContest(root, which) {
  const rel = `results/rl-defects/contest-defects-${which}/card.json`;
  const c = json(root, rel);
  const rows = [];
  for (const a of c.against_today) for (const [k, m] of Object.entries(a.measures))
    rows.push([WHO[a.name] || a.name, MEASURES[k] || k, n(c.today[k], 1), sg(m.mean, 1), `${sg(m.lo, 1)} to ${sg(m.hi, 1)}`, m.verdict]);
  const ppo = c.against_today.find((a) => a.name === "ppo");
  return {
    id: `rl-contest-defects-${which}`, kind: "contest", when: when(root, rel),
    title: `Contest on new days, quality holds ${{ on: "×1", off: "off" }[which] || which.replace("x", "×")}: today's rule, the trained AI and the evolved rule`,
    question: "On days none of them practised on, does the trained AI or the evolved rule beat today's rule?",
    settings: [["Seeds", seedsText(c.seeds)], ["Defect holds", c.defects ? `tool ${c.defects[0]} min, lookback ${c.defects[1]} min, lots ${c.defects[2]} min (assumed)` : "off"],
      ["Episode", `${c.warmup_days} day warm-up, ${c.window_days} days scored`], ["Contestants", ["today"].concat(c.against_today.map((a) => a.name)).join(", ")],
      ["Intervals", `paired t, Bonferroni over ${c.against_today.length} (each at level ${n(c.alpha_each, 3)})`],
      ["How often the AI chose differently", ppo ? `${n(100 * ppo.picked_other_share)}% of its choices differ from today's rule` : "—"],
      ["Command", `results/rl-defects/contest.sh`]],
    headline: ppo ? (() => {
      const r = ppo.measures.reward, lower = r.mean < 0, a = Math.abs(r.lo), b = Math.abs(r.hi);
      const how = r.verdict === "better" ? "did better than" : r.verdict === "worse" ? "did worse than" : "was too close to call against";
      const range = r.lo < 0 && r.hi > 0 ? `range ${sg(r.lo, 1)} to ${sg(r.hi, 1)}` : `range ${n(Math.min(a, b), 1)} to ${n(Math.max(a, b), 1)}`;
      return `The trained AI ${how} today's rule: its score was ${n(Math.abs(r.mean), 1)} ${lower ? "lower" : "higher"} (${range}).`;
    })() : "",
    numbers: { columns: ["Contestant", "Measure", "Today's rule", "Change", "95% interval", "Verdict"], rows },
    files: [rel, `results/rl-defects/contest-defects-${which}/runs.tsv`, "docs/RL-DEFECTS.md"],
    note: `${NOTE}${c.defects ? " Defect holds and their lengths are assumed." : ""}`,
  };
}

function buildResults(root) {
  const out = [];
  const add = (f) => { try { out.push(f()); } catch (e) { if (e.code !== "ENOENT") throw e; } };
  add(() => twoFamilies(root));
  add(() => evolve(root));
  add(() => lean(root));
  add(() => rlTrain(root));
  add(() => rlContest(root, "on"));
  add(() => rlContest(root, "off"));
  add(() => rlContest(root, "x0.5"));
  add(() => rlContest(root, "x2"));
  return out.sort((a, b) => (a.when < b.when ? 1 : a.when > b.when ? -1 : 0));
}

module.exports = { buildResults };
if (require.main === module) process.stdout.write(JSON.stringify(buildResults(path.resolve(__dirname, "..", ".."))));
