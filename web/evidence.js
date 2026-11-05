// Evidence in plain words (docs/EVIDENCE-PLAIN.md): four findings, each a sentence, what we did, what it means and how
// sure we are, computed from the same data files the tables use. Pure: window.FabEvidence in the page, module.exports
// under Node. From the SMT2020 testbed, a published research set of a fab's machines, routes and times; not a real fab.
// Every price is assumed.
(function (root) {
  const LEVEL = { 1: "today's prototype orders", 2: "twice today's", 4: "four times today's", 8: "eight times today's" };
  const num = (s) => Number(String(s).replace(/−/g, "-").replace(/[^0-9.+-]/g, ""));
  const usd = (x) => { const s = x < 0 ? "−" : "+", a = Math.abs(x); return `${s}$${a >= 1e6 ? (a / 1e6).toFixed(2) + "M" : Math.round(a / 1e3) + "k"}`; };
  const sureOf = (verdict) => (verdict === "better" || verdict === "worse" ? "Sure" : "Too close to call");

  function prototypes(sweep, U) {
    const levels = [1, 2, 4, 8].map((share) => {
      const g = U.capitalGrid(sweep, share, "day");
      const c = g.floors.find((f) => f.floor === "D1 share").cells.find((x) => x.policy === "P2 family cap");
      const best = g.floors.flatMap((f) => f.cells.map((x) => ({ floor: f.floor, ...x }))).find((x) => x.best);
      return { share, label: LEVEL[share], value: c.value, lo: c.lo, hi: c.hi, verdict: c.verdict, best };
    });
    const four = levels.find((l) => l.share === 4), eight = levels.find((l) => l.share === 8);
    const paysUpTo = levels.filter((l) => l.verdict === "better").map((l) => l.share);
    return {
      id: "prototypes",
      title: "Holding rush prototypes at the door until there is room earns more, and costs nothing to build, up to four times today's prototype orders.",
      what: "A fab mostly makes one chip in bulk, and a few customers send rush prototype orders that jump the queue. We tried four ways of choosing the next job and three floor plans, at one, two, four and eight times today's prototype orders, and priced every day's output.",
      means: `At four times today's prototype orders, holding them at the door adds about ${usd(four.value)} a day of operating profit with nothing to buy. At eight times it loses about ${usd(eight.value).slice(1)} a day on today's floor; there, copies of the busiest machines in spare hall space, with prototypes still held at the door, pay instead.`,
      sure: `${sureOf(four.verdict)}: at four times the gain is between ${usd(four.lo)} and ${usd(four.hi)} a day. Prices are made up for this testbed, so the size matters less than the direction.`,
      levels, paysUpTo,
    };
  }

  function cap(long) {
    const cell = (metric, k) => long.cells.find((c) => c.metric === metric && c.k === k && c.cap === 1800);
    const w1 = cell("wafers_per_day", 1), d1 = cell("cycle_days", 1), w2 = cell("wafers_per_day", 2);
    const verdict = (c) => (/better/.test(c.verdict) ? "better" : /worse/.test(c.verdict) ? "worse" : "too close to call");
    const normal = { verdict: verdict(w1), wafers: w1.mean, daysSooner: -d1.mean };
    const breaks = { verdict: verdict(w2), wafersLost: -w2.mean, lo: -w2.hi, hi: -w2.lo };
    return {
      id: "cap",
      title: "Capping how much work is inside the fab gets each wafer out about a month sooner, but costs output when machines break often.",
      what: "We let no more than 1,800 lots into the fab at once and compared it with no cap, over six simulated months, with machines breaking as usual, one and a half times and twice as often.",
      means: `In a normal fab the cap gets each wafer out about ${Math.round(normal.daysSooner)} days sooner, with no change in output we can measure. When machines break twice as often, the same cap costs about ${Math.round(breaks.wafersLost)} wafers a day: a fab that runs lean has less slack when things go wrong.`,
      sure: `Sure about the time saved and the loss when breakdowns double (${Math.round(breaks.lo)} to ${Math.round(breaks.hi)} wafers a day). Too close to call on output in a normal fab. Caps a little higher got more wafers out, and we have not found out why yet.`,
      cap: 1800, normal, breaks,
    };
  }

  function ai(results) {
    const card = results.find((e) => e.id === "rl-contest-defects-on");
    const row = card.numbers.rows.find((r) => r[0] === "the trained AI" && /^Score/.test(r[1]));
    const [lo, hi] = row[4].split(" to ").map(num);
    const lower = -num(row[3]);
    return {
      id: "ai",
      title: "Our trained AI does not beat the fab's own rule for picking the next job yet.",
      what: "We trained an AI to choose which batch of wafers each machine runs next, then played it against the fab's own rule on ten days it had never practised on.",
      means: "It finished a few more batches but kept wafers waiting far longer, so its overall score was lower. Beating a well-tuned rule is hard, and that open problem is what this gym is for.",
      sure: `Sure: its score was about ${Math.round(lower)} points lower (between ${Math.round(-hi)} and ${Math.round(-lo)}).`,
      lower,
    };
  }

  function checked(lean) {
    return {
      id: "checked",
      title: `Every scored run was checked by a separate program: ${lean.passed} of ${lean.runs} passed.`,
      what: `A referee whose rules are proved correct in Lean re-read every run behind our scores: every final scored run of the long study on the full fab: six ways of picking the next lot, each on ten different random histories, with quality holds off and on, 190 simulated days each. ${Math.round(lean.jobs / 1e6)} million machine jobs in all.`,
      means: "In every run no machine did two jobs at once, every batch followed its route, no machine was overloaded, nothing ran on a broken machine, and the missed time limits were counted right. The scores rest on runs that follow the fab's rules.",
      sure: "Exact: a check, not an estimate. It shows these runs follow the rules. It does not prove the simulator's own code correct (that rests on a bit-for-bit match with a separate reference engine and on laws the runs obey), nor that it matches a real fab.",
      runs: lean.runs, passed: lean.passed,
    };
  }

  /** The four findings, in the order the page shows them. `data` holds sweep (priced), long, results and lean. */
  function findings(data, U) {
    U = U || (typeof module !== "undefined" && module.exports ? require("./ui.js") : root.FabUI);
    return [prototypes(data.sweep, U), cap(data.long), ai(data.results), checked(data.lean)];
  }

  const api = { findings, usd };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabEvidence = api;
})(typeof window !== "undefined" ? window : globalThis);
