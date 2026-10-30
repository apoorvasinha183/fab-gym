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

  function ruleCode(arm) {
    if (arm.bfirst) return { code: 3, exact: true };
    const k = { today: 0, fifo: 1, spt: 2 }[arm.rule];
    return k === undefined ? { code: 0, exact: false } : { code: k, exact: true };
  }

  const api = { scenarioLines, resultRows, summaryLine, familyB, extraHalls, ruleCode };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabAsk = api;
})(typeof window !== "undefined" ? window : globalThis);
