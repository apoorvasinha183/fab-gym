// The ask box's pure parts (docs/ASK-FAMILIES.md, part 5): a scenario in plain words, a report as rows, family B's
// routes, the wing hall and an arm's rule for the page's simulator. In the page this defines window.FabAsk; under
// Node, module.exports. From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; not a real fab.
(function (root) {
  "use strict";

  const AREA_WORDS = {
    Planar: "Polisher group", Litho: "Lithography group", Dry_Etch: "Dry-etch group", Wet_Etch: "Wet-etch group",
    TF: "Thin-film group", Implant: "Implant group", Diffusion: "Furnace group", Dielectric: "Dielectric group",
  };
  const PREFIX_AREA = [["Planar_", "Planar"], ["Litho_", "Litho"], ["DE_", "Dry_Etch"], ["WE_", "Wet_Etch"], ["TF_", "TF"],
    ["Implant_", "Implant"], ["Diffusion_", "Diffusion"], ["Dielectric_", "Dielectric"]];
  const RULES = { today: "today's rule", fifo: "first in, first out", spt: "shortest processing first", cr: "critical ratio", random: "random order" };
  const FLOORS = { share: "the floor as it is", wing: "copies of the busiest groups in a P3 wing", copies: "copies of the busiest groups in the halls" };
  const POLICIES = {
    today: "today's order", bfirst: "prototype lots first", cap: "prototypes held at the door above their usual load",
    reserve: "one tool per busy group kept for prototypes", qualify: "prototypes on half the tools of busy groups",
  };
  const n = x => String(+x);

  function groupWords(g) {
    const hit = PREFIX_AREA.find(([p]) => g.startsWith(p));
    return hit ? `${AREA_WORDS[hit[1]]} ${g}` : `Tool group ${g}`;
  }

  function scenarioLines(text) {
    const out = { question: "", given: [], candidates: [] };
    const byName = new Map();
    for (const line of text.split("\n").slice(1)) {
      const f = line.split("\t");
      if (!f[0]) continue;
      const said = f[f.length - 1] === "said";
      if (f[0] === "question") out.question = f[1];
      else if (f[0] === "family") out.given.push({ text: `Prototype lots at ${n(f[2])} times the usual`, said });
      else if (f[0] === "shock") {
        const k = f[1];
        const t = k === "outage" ? `${groupWords(f[2])} down from hour ${n(f[3])} for ${n(f[4])} hours`
          : k === "breakdowns" ? `Breakdowns ×${n(f[2])}` : k === "repair" ? `Repair times ×${n(f[2])}`
          : k === "demand" ? `Demand ×${n(f[2])}` : k === "hot" ? `${n(f[2])} lots made urgent` : `${k} ${f.slice(2, -1).join(" ")}`;
        out.given.push({ text: t, said });
      } else if (f[0] === "candidate") {
        let c = byName.get(f[1]);
        if (!c) { c = { name: f[1], changes: [] }; byName.set(f[1], c); out.candidates.push(c); }
        const k = f[2], v = f[3];
        c.changes.push(k === "rule" ? RULES[v] || v : k === "floor" ? FLOORS[v] || v : k === "policy" ? POLICIES[v] || v
          : k === "cap" ? `at most ${v} lots in the fab` : k === "spare" ? `${f[4]} more tool${f[4] === "1" ? "" : "s"} in ${v}`
          : k === "demand" ? `demand ×${n(v)}` : `${k} ${v}`);
      }
    }
    return out;
  }

  const CELLS_FAM = [["money", "Money a day"], ["a_wafers", "Volume wafers a day"], ["b_cycle_days", "Prototype cycle, days"]];
  // answers scored in dollars (docs/MONEY-PL.md) carry operating profit; older answers carry only money a day
  const CELLS_USD = [["profit", "Operating profit a day ($)"], ["a_wafers", "Volume wafers a day"], ["b_cycle_days", "Prototype cycle, days"]];
  const inDollars = (report) => report.families && report.candidates.some((c) => c.measures && c.measures.profit);
  const CELLS_ONE = [["reward", "Reward"], ["moves", "Moves"], ["wait_per_move_minutes", "Wait per move, min"]];

  function resultRows(report) {
    const keys = !report.families ? CELLS_ONE : inDollars(report) ? CELLS_USD : CELLS_FAM;
    return report.candidates.map(c => ({
      name: c.name,
      best: report.best === c.name,
      pl: c.pl || null,
      cells: keys.map(([key, label]) => {
        const m = c.measures[key];
        const vals = (m.today || []).filter(x => x !== null);
        return {
          key, label, higher: m.higher_is_better,
          mean: m.mean, lo: m.lo, hi: m.hi,
          verdict: m.mean === null || m.lo === null || m.hi === null ? "no clear effect" : m.verdict,
          today: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null,
        };
      }),
    }));
  }

  function summaryLine(report) {
    const what = !report.families ? "the scorer's reward" : inDollars(report) ? "operating profit a day" : "money a day";
    const head = report.best
      ? `Best on ${what}: ${report.best}. It beats today's fab, with all intervals holding together at 95%.`
      : `No candidate is clearly better on ${what}, so today's fab stands.`;
    return `${head} Simulated from the SMT2020 testbed with ${report.seeds.length} paired seeds. What these changes would do in a real fab is unknown.`;
  }

  function familyB(j) {
    return j.routes.map((_, i) => ((j.families || [])[i] || "") === "B");
  }

  function extraHalls(areas) {
    return areas.includes("P3 wing") ? [["Wing (P3)", ["P3 wing"]]] : [];
  }

  // the page's simulator runs prototypes first, first come first served and quickest first itself; any other rule runs
  // exactly only when the setup's file carries it as a dispatch record (docs/RUNS.md, part 2; the helper says so in
  // rule_in_file). `show` is the rule menu's choice for it.
  function ruleCode(arm) {
    if (arm.bfirst) return { code: 3, exact: true, show: 0 };
    const k = { today: 0, fifo: 1, spt: 2 }[arm.rule];
    return k === undefined ? { code: 0, exact: !!arm.rule_in_file, show: 0 } : { code: k, exact: true, show: k };
  }

  // one place to ask (docs/GLOSSARY-PLUS.md, part 3): a question about what something means goes to the glossary; a
  // what-if, or a choice between setups, goes to the simulator as before
  function wordQuestion(q) {
    const s = String(q || "").trim().toLowerCase();
    if (/\bwhat (if|would|happens if)\b|\bwould\b|\bshould\b|\bwhich\b|^if\b|\bdo we\b/.test(s)) return false;
    return /^(what|what's|whats|why)\b/.test(s) || /^how (do|does|did)\b/.test(s) || /\b(mean|means|meaning|define|explain)\b/.test(s);
  }


  // ---------------------------------------------------------------- one bar for anything (docs/ONE-BAR.md)
  // Plain rules read a question first; only a question none of them reads goes to the model, which picks a tool.

  // the Floor's Simulation settings, with the ranges its sliders allow
  const RANGE = { breakdowns: [0, 3], repair: [0.5, 3], demand: [0.5, 1.5], hot: [0, 5], rework: [0, 5], defects: [0, 2], cap: [1500, 3500] };
  const SETTING = [
    ["breakdowns", /\bbreak ?downs?\b|\bfailures?\b|\bbreak(?:s|ing)?\b/],
    ["repair", /\brepairs?\b|\brepair times?\b|\bfix(?:es|ing)?\b/],
    ["demand", /\bdemand\b|\breleases?\b|\bstarts\b/],
    ["hot", /\burgent\b|\bhot lots?\b/],
    ["rework", /\brework\b/],
    ["defects", /\bquality holds?\b|\bdefects?\b/],
  ];
  const NAMES = { breakdowns: "Breakdowns", repair: "Repair time", demand: "Demand", hot: "Urgent lots", rework: "Rework", defects: "Quality holds" };
  const GROUP = /\b([A-Z][A-Za-z]*_[A-Za-z0-9_]*\d)\b/;

  // a multiple read from words: double, half, x2, 2x, 3 times, 50% worse, 20% fewer; null when none is said
  function multiple(s) {
    let m;
    if (/\b(?:double[sd]?|twice|doubling)\b/.test(s)) return 2;
    if (/\b(?:triple[sd]?|thrice|tripling)\b/.test(s)) return 3;
    if (/\b(?:halve[sd]?|half|halving)\b/.test(s)) return 0.5;
    if ((m = s.match(/(\d+(?:\.\d+)?)\s*(?:x|×|times)(?=\s|$|[^a-z0-9])/))) return +m[1];
    if ((m = s.match(/(?:^|[^a-z0-9])(?:x|×)\s*(\d+(?:\.\d+)?)/))) return +m[1];
    const up = /(\d+(?:\.\d+)?)\s*%\s*(?:worse|more|up|higher|longer|slower|increase|rise|extra)|\b(?:up|more|rise[sn]?|increase[sd]?|grows?|by)\s*(?:by\s*)?(\d+(?:\.\d+)?)\s*%/;
    const down = /(\d+(?:\.\d+)?)\s*%\s*(?:less|fewer|down|lower|better|shorter|faster|drop|decrease)|\b(?:down|drops?|falls?|cut|less|fewer|decrease[sd]?)\s*(?:by\s*)?(\d+(?:\.\d+)?)\s*%/;
    if ((m = s.match(down))) return Math.round((1 - (m[1] || m[2]) / 100) * 1000) / 1000;
    if ((m = s.match(up))) return Math.round((1 + (m[1] || m[2]) / 100) * 1000) / 1000;
    return null;
  }

  /** A change to the Simulation settings read from words, or null: {dials, rule?, outage?, words, over}. */
  function parseChange(q) {
    const raw = String(q || "").trim(), s = raw.toLowerCase();
    const dials = {}, words = [], over = [];
    let rule, outage;
    for (const clause of s.split(/,|;|\band\b|\.\s/)) {
      for (const [k, re] of SETTING) {
        if (!re.test(clause)) continue;
        let v = null;
        if (k === "defects") v = /\b(?:off|no|without)\b/.test(clause) ? 0 : multiple(clause) ?? (/\bon\b/.test(clause) ? 1 : null);
        else if (new RegExp(`\\b(?:no|zero|without)\\s+(?:more\\s+)?(?:\\w+\\s+)?${re.source}`).test(clause) && k !== "repair" && k !== "demand") v = 0;
        else v = multiple(clause);
        if (v === null || dials[k] !== undefined) continue;
        const [lo, hi] = RANGE[k];
        if (v < lo || v > hi) { over.push(k); continue; }
        dials[k] = v;
      }
      let m;
      if (/\b(?:no|remove|lift|drop) (?:the )?(?:wip )?cap\b/.test(clause)) dials.cap = 0;
      else if ((m = clause.match(/\bcap\b[^0-9]*?(\d[\d,]*)/))) {
        const v = +m[1].replace(/,/g, "");
        if (v < RANGE.cap[0] || v > RANGE.cap[1]) over.push("cap"); else dials.cap = v;
      }
    }
    if (/first come,? first served|first in,? first out|\bfifo\b/.test(s)) rule = 1;
    else if (/\bquickest\b|\bshortest (?:job|processing)\b|\bspt\b/.test(s)) rule = 2;
    else if (/\btoday'?s rule\b|\bthe usual rule\b/.test(s)) rule = 0;
    const g = raw.match(GROUP), hrs = s.match(/(\d+(?:\.\d+)?)\s*(?:h|hrs?|hours?)\b/);
    if (g && hrs && /\bdown\b|\bout\b|\boffline\b/.test(s)) {
      const at = s.match(/\b(?:from|at|after)\s*hour\s*(\d+(?:\.\d+)?)/);
      outage = { group: g[1], at: at ? +at[1] : 0, hours: +hrs[1] };
      if (outage.hours < 1 || outage.hours > 72 || outage.at > 72) { over.push("outage"); outage = undefined; }
    }
    if (!Object.keys(dials).length && rule === undefined && !outage && !over.length) return null;
    for (const k of Object.keys(NAMES)) if (dials[k] !== undefined)
      words.push(k === "defects" ? (dials[k] ? `Quality holds on${dials[k] !== 1 ? ` ×${dials[k]}` : ""}` : "Quality holds off")
        : dials[k] === 0 ? `No ${NAMES[k].toLowerCase()}` : `${NAMES[k]} ×${dials[k]}`);
    if (dials.cap !== undefined) words.push(dials.cap ? `A cap of ${dials.cap.toLocaleString("en-US")} lots in the fab` : "No cap on lots");
    if (rule !== undefined) words.push(["Today's rule", "First come, first served", "Quickest job first"][rule]);
    if (outage) words.push(`${outage.group} down for ${outage.hours} h from hour ${outage.at}`);
    const out = { dials, words: words.join(", "), over };
    if (rule !== undefined) out.rule = rule;
    if (outage) out.outage = outage;
    return out;
  }

  // what the run on screen can count, from the question's words; the glossary's terms (docs/GLOSSARY-PLUS.md, part 2)
  const COUNT = [
    ["Hot lot", /\burgent\b|\bhot lots?\b/],
    ["Setup change", /\bsetups?\b|\bchanging setup\b/],
    ["Breakdown", /\bbroken\b|\bbroke\b|\bbreak ?downs?\b|\bdown machines\b|\bmachines? (?:are |is )?down\b/],
    ["Lithography", /\blitho(?:graphy)?\b/],
    ["Etch", /\betch(?:ing|ers?)?\b/],
    ["Polishing (CMP)", /\bpolish(?:ing|ers?)?\b|\bcmp\b/],
    ["Checks (metrology)", /\bmetrology\b|\bchecks\b/],
    ["Tool group", /\blongest (?:line|queue)\b|\bbusiest\b|\bbottleneck\b/],
    ["Cycle time", /\bcycle time\b/],
    ["Wafer", /\bwafers?\b/],
    ["WIP", /\bwaiting\b|\bwait\b|\bwip\b|\bin the fab\b|\bqueued?\b/],
    ["Track (overhead track)", /\bon the move\b|\bmoving\b|\btrack\b/],
    ["Lot", /\blots?\b|\bfinished\b/],
    ["Tool", /\bmachines?\b|\btools?\b/],
  ];
  const SHOWN = new Set(["Hot lot", "Setup change", "Breakdown", "Lithography", "Etch", "Polishing (CMP)", "Checks (metrology)", "Tool group", "WIP", "Lot"]);
  const countOf = s => { const hit = COUNT.find(([, re]) => re.test(s)); return hit ? hit[0] : null; };

  const GO_VERB = /^(?:please\s+)?(?:open|go to|go back to|take me to|bring me to|show me|show|see|fly to|find|jump to)\b/;
  function goTo(raw, s) {
    const verb = GO_VERB.test(s);
    let m;
    if ((m = raw.match(/\b([QSBF]-\d{4})\b/i)) && (verb || s === m[1].toLowerCase())) return { run: m[1].toUpperCase() };
    if (!verb) return null;
    if ((m = s.match(/\bchallenge\s*#?\s*(\d+)\b/))) return { page: "build", ch: +m[1] };
    if (/\bbuild\b|\bthe editor\b/.test(s)) return { page: "build", ch: null };
    if (/\bsimulation settings\b|\bsettings\b|\bthe dials\b/.test(s)) return { tab: "change" };
    if (/\bglossary\b/.test(s)) return { tab: "glossary" };
    if (/\bevidence\b|\bfindings\b/.test(s)) return { tab: "evidence" };
    if (/\b(?:the )?runs\b|\brun list\b/.test(s)) return { page: "runs" };
    if ((m = raw.match(GROUP))) return { group: m[1] };
    if (/^(?:please\s+)?(?:show me|show|see)\b/.test(s)) { const t = countOf(s); if (t && SHOWN.has(t)) return { show: t }; }
    return null;
  }

  const NOW = /\bhow many\b|\bright now\b|\bnow\b|\bcurrently\b|\bat the moment\b|\blongest (?:line|queue)\b|\bbusiest\b|\bbottleneck\b|\bbacked up\b/;
  const WHATIF = /\bwhat (?:if|would|happens)\b|\bwould\b|\bshould\b|\bwhich\b|^if\b|\bdo we\b|\bdoes\b|\bis it worth\b/;
  // a change that is the whole question; a question that also weighs a choice goes to the simulator's question path
  const WEIGHS = /\bdoes\b|\bdo we\b|\bshould\b|\bwhich\b|\bor\b|\bbetter\b|\bworth\b|\bprotects?\b|\bversus\b|\bvs\.?\b/;

  /** One bar's rules (docs/ONE-BAR.md): {kind: "go" | "change" | "now" | "words" | "whatif" | "unsure", ...}. */
  function route(q) {
    const raw = String(q || "").trim(), s = raw.toLowerCase();
    if (!s) return { kind: "unsure" };
    const to = goTo(raw, s);
    if (to) return { kind: "go", to };
    const ch = parseChange(raw);
    if (ch && !WEIGHS.test(s)) return { kind: "change", change: ch };
    if (NOW.test(s)) { const t = countOf(s); if (t) return { kind: "now", term: t }; }
    if (wordQuestion(raw)) return { kind: "words" };
    if (WHATIF.test(s)) return { kind: "whatif" };
    return { kind: "unsure" };
  }

  const api = { scenarioLines, resultRows, summaryLine, familyB, extraHalls, ruleCode, wordQuestion, route, parseChange, RANGE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabAsk = api;
})(typeof window !== "undefined" ? window : globalThis);
