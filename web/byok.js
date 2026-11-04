// Bring your own key (the founder, 5 Nov 2026). On a copy with no helper, such as the public site, a visitor's own key
// lets Meta's model read a what-if into a shock and one change to try, in the page's own Simulation settings; the
// page's simulator then compares "shock and change" with "shock alone" on its paired days. The key stays in this
// browser (this tab only, unless "remember" is ticked) and is sent only to the provider chosen. On the SMT2020
// testbed; not a real fab.
(function (root) {
  "use strict";
  const PROVIDERS = {
    meta: { label: "Meta Model API", base: "https://api.meta.ai/v1", model: "muse-spark-1.3-contributor", name: "Muse Spark",
            extra: { reasoning_effort: "low" } },
    baseten: { label: "Baseten", base: "https://inference.baseten.co/v1", model: "meta-models/muse-spark-open-1026",
               name: "Muse Spark Open", extra: {} },
  };
  const STORE = "fabgym.byok";
  const KEYS = ["breakdowns", "repair", "demand", "hot", "rework", "cap", "rule", "outage"];
  const RULES = { today: 0, fifo: 1, spt: 2 };

  function load() {
    try { return JSON.parse(sessionStorage.getItem(STORE) || localStorage.getItem(STORE) || "null"); } catch { return null; }
  }
  function save(v, remember) {
    try {
      sessionStorage.setItem(STORE, JSON.stringify(v));
      if (remember) localStorage.setItem(STORE, JSON.stringify(v)); else localStorage.removeItem(STORE);
    } catch { /* storage blocked: the key lasts as long as the page */ }
    mem = v;
  }
  function forget() { try { sessionStorage.removeItem(STORE); localStorage.removeItem(STORE); } catch { /* blocked */ } mem = null; }
  let mem = null;
  const current = () => mem || load();

  function prompt(groups, R) {
    return `You turn a person's question about a wafer fab into an experiment for the simulator in this page. The fab is
the SMT2020 testbed, a published research model of a fab's tool groups, routes and times: not a real fab, no real data.

Answer with one JSON object and nothing else:
{"question": "the question, one line",
 "shock": {"breakdowns": 2},
 "try": {"cap": 2000},
 "said": ["breakdowns"],
 "assumed": {"cap": "a few words on why this value"}}

"shock" is what happens to the fab (it applies to both sides of the comparison); "try" is the one answer to test (it
applies only to the second side). "try" holds only what the question asks to test, at least one key, and nothing
else; "shock" may be empty. Keys, all optional:
- breakdowns: multiplier of breakdown rates, ${R.breakdowns[0]} to ${R.breakdowns[1]}
- repair: multiplier of repair times, ${R.repair[0]} to ${R.repair[1]}
- demand: multiplier of new lots released, ${R.demand[0]} to ${R.demand[1]}
- hot: multiplier of urgent lots, ${R.hot[0]} to ${R.hot[1]}
- rework: multiplier of rework, ${R.rework[0]} to ${R.rework[1]}
- cap: the most lots allowed in the fab, a whole number from ${R.cap[0]} to ${R.cap[1]}
- rule: the dispatch rule, "today", "fifo" (first come, first served) or "spt" (quickest job first)
- outage: a tool group down, {"group": "NAME", "from_hours": 0 to 72, "hours": 1 to 72}
Every value in "shock" or "try" is either said in the question (list its key under "said") or assumed (give it under
"assumed" with a reason). Use only these tool group names: ${groups.join(", ")}.
Write JSON only, with no comments.`;
  }

  function parse(text) {
    const m = String(text || "").match(/\{[\s\S]*\}/);
    if (!m) throw new Error("the reply holds no JSON object");
    return JSON.parse(m[0]);
  }

  function checkPart(part, where, groups, R, out) {
    if (part == null) return;
    if (typeof part !== "object" || Array.isArray(part)) { out.push(`${where} must be an object`); return; }
    for (const [k, v] of Object.entries(part)) {
      if (!KEYS.includes(k)) { out.push(`${where}: unknown key ${JSON.stringify(k)}`); continue; }
      if (k === "rule") { if (!(v in RULES)) out.push(`${where}: rule must be "today", "fifo" or "spt"`); continue; }
      if (k === "outage") {
        if (!v || !groups.includes(v.group)) out.push(`${where}: outage needs a group from the list`);
        else if (!(v.hours >= 1 && v.hours <= 72) || !(v.from_hours >= 0 && v.from_hours <= 72)) out.push(`${where}: outage hours 1 to 72, from hour 0 to 72`);
        continue;
      }
      const [lo, hi] = R[k];
      if (typeof v !== "number" || !(v >= lo && v <= hi)) out.push(`${where}: ${k} from ${lo} to ${hi}`);
      if (k === "cap" && !Number.isInteger(v)) out.push(`${where}: cap is a whole number of lots`);
    }
  }

  function check(a, groups, R) {
    const out = [];
    if (!a || typeof a !== "object") return ["the answer is not a JSON object"];
    checkPart(a.shock || {}, "shock", groups, R, out);
    checkPart(a.try, "try", groups, R, out);
    if (!a.try || !Object.keys(a.try).length) out.push("try must change at least one thing");
    for (const k of Object.keys(a.try || {})) if (a.shock && k in a.shock) out.push(`${k} is in both shock and try`);
    return out;
  }

  async function call(cfg, messages, fetcher) {
    const p = PROVIDERS[cfg.provider];
    const r = await (fetcher || fetch)(p.base + "/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + cfg.key },
      body: JSON.stringify({ model: p.model, messages, max_tokens: 4000, ...p.extra }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(`${p.label} answered ${r.status}${j.error ? ": " + (j.error.message || j.error) : ""}`);
    const c = j.choices && j.choices[0] && j.choices[0].message;
    return { text: (c && c.content) || "", usage: j.usage || null };
  }

  // the model's experiment, checked; refused once, it is shown the reasons and asked again
  async function read(question, groups, R, fetcher) {
    const cfg = current();
    if (!cfg) throw new Error("no key set");
    const msgs = [{ role: "system", content: prompt(groups, R) }, { role: "user", content: question }];
    let reply = await call(cfg, msgs, fetcher), a = null, why = [];
    try { a = parse(reply.text); why = check(a, groups, R); } catch (e) { why = [e.message]; }
    let tries = 1;
    if (why.length) {
      tries = 2;
      msgs.push({ role: "assistant", content: reply.text },
                { role: "user", content: "That was refused: " + why.join("; ") + ". Write it again, fixing every reason, as JSON only." });
      reply = await call(cfg, msgs, fetcher);
      a = parse(reply.text);
      why = check(a, groups, R);
      if (why.length) throw new Error("the model's experiment was refused twice: " + why.join("; "));
    }
    return { answer: a, tries, model: PROVIDERS[cfg.provider].name, provider: PROVIDERS[cfg.provider].label };
  }

  // one side's settings for the page's compare: the page's own options, today's rule and dials, with a part applied
  function apply(base, part, groups) {
    const o = { ...base, dials: { ...base.dials } };
    for (const [k, v] of Object.entries(part || {})) {
      if (k === "rule") o.rule = RULES[v];
      else if (k === "outage") { o.downGroup = groups.indexOf(v.group); o.downAt = v.from_hours; o.downHours = v.hours; }
      else o.dials[k] = v;
    }
    return o;
  }

  function words(part) {
    const n = { breakdowns: "breakdowns", repair: "repair time", demand: "demand", hot: "urgent lots", rework: "rework" };
    return Object.entries(part || {}).map(([k, v]) =>
      k === "cap" ? `a cap of ${v.toLocaleString("en-US")} lots` : k === "rule" ? ["today's rule", "first come, first served", "quickest job first"][RULES[v]]
        : k === "outage" ? `${v.group} down ${v.hours} h from hour ${v.from_hours}` : `${n[k]} ×${v}`).join(", ");
  }

  const api = { PROVIDERS, load: current, save, forget, ready: () => !!current(), prompt, check, read, apply, words, parse };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FabBYOK = api;
})(typeof window !== "undefined" ? window : globalThis);
