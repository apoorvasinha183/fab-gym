//! The scorer: today's fab against each candidate on paired held-out seeds (docs/ASK.md).

use std::fmt::Write as _;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use crate::engine::RunOptions;
use crate::policy::{run_with, Policy};
use crate::scenario::{CandidateSpec, Scenario};
use crate::shop::Shop;
use crate::uq::{crossover, paired, verdict, Crossover, Interval, Verdict, REAL_FAB_EFFECT};
use crate::window::{score as window_score, with_probes, Window, WindowScore};

#[derive(Clone, Debug)]
pub struct Protocol {
    pub warmup_days: f64,
    pub window_days: f64,
    pub seeds: Vec<u64>,
    pub threads: usize,
}

impl Default for Protocol {
    /// docs/PROBLEM.md: 24 hours of warm-up, a 3-day window, held-out seeds 0 to 9.
    fn default() -> Protocol {
        Protocol { warmup_days: 1.0, window_days: 3.0, seeds: (0..10).collect(), threads: 4 }
    }
}

/// (key, higher is better, the value)
pub const MEASURES: [(&str, bool, fn(&WindowScore) -> f64); 7] = [
    ("reward", true, |s| s.reward),
    ("moves", true, |s| s.moves),
    ("lots_finished", true, |s| s.lots_finished),
    ("wait_lot_hours", false, |s| s.wait_lot_hours),
    ("wait_per_move_minutes", false, |s| s.wait_per_move_minutes),
    ("breaches", false, |s| s.breaches),
    ("mean_wip", false, |s| s.mean_wip),
];

#[derive(Clone, Debug)]
pub struct Measure {
    pub key: &'static str,
    pub higher_is_better: bool,
    /// per seed, in the protocol's seed order
    pub base: Vec<f64>,
    pub cand: Vec<f64>,
    /// candidate minus today
    pub interval: Interval,
    pub verdict: Verdict,
}

#[derive(Clone, Debug)]
pub struct CandResult {
    pub name: String,
    pub rule: Policy,
    pub measures: Vec<Measure>,
}

impl CandResult {
    pub fn measure(&self, key: &str) -> &Measure {
        self.measures.iter().find(|m| m.key == key).expect("a known measure")
    }
}

#[derive(Clone, Debug)]
pub struct SweepResult {
    pub shock: String,
    pub field: String,
    pub points: Vec<f64>,
    pub by_point: Vec<Vec<CandResult>>,
    /// each candidate against today on reward, over the swept value
    pub crossovers: Vec<(String, Crossover)>,
}

#[derive(Clone, Debug)]
pub struct Report {
    pub scenario: Scenario,
    pub protocol: Protocol,
    pub alpha_each: f64,
    pub candidates: Vec<CandResult>,
    /// the candidate better than today on reward with the highest lower bound
    pub best: Option<String>,
    pub sweep: Option<SweepResult>,
}

fn par_map<T: Send, R: Send>(items: Vec<T>, threads: usize, f: impl Fn(&T) -> R + Sync) -> Vec<R>
where
    T: Sync,
{
    let out: Mutex<Vec<Option<R>>> = Mutex::new((0..items.len()).map(|_| None).collect());
    let next = AtomicUsize::new(0);
    std::thread::scope(|sc| {
        for _ in 0..threads.max(1).min(items.len().max(1)) {
            sc.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= items.len() {
                    break;
                }
                let r = f(&items[i]);
                out.lock().unwrap()[i] = Some(r);
            });
        }
    });
    out.into_inner().unwrap().into_iter().map(|x| x.expect("every job ran")).collect()
}

/// Score today and every candidate at one value of the swept shock (or the shock's own).
fn score_point(shop: &Shop, sc: &Scenario, p: &Protocol, swept: Option<f64>, alpha: f64) -> Result<Vec<CandResult>, String> {
    let w = Window { from: p.warmup_days * 1440.0, to: (p.warmup_days + p.window_days) * 1440.0 };
    let mut arms: Vec<(Shop, Policy)> = vec![];
    let today = sc.arm(None, swept);
    arms.push((with_probes(&today.0.apply(shop)?, &w), today.1));
    for c in &sc.candidates {
        let (d, pol) = sc.arm(Some(c), swept);
        arms.push((with_probes(&d.apply(shop)?, &w), pol));
    }
    let jobs: Vec<(usize, u64)> = (0..arms.len()).flat_map(|a| p.seeds.iter().map(move |&s| (a, s))).collect();
    let scores = par_map(jobs, p.threads, |&(a, seed)| {
        let r = run_with(&arms[a].0, &RunOptions { seed, until: Some(w.to), record: false }, arms[a].1);
        window_score(&r, &w)
    });
    let scores: Vec<WindowScore> = scores.into_iter().collect::<Result<_, _>>()?;
    let n = p.seeds.len();
    let arm_scores = |a: usize| &scores[a * n..(a + 1) * n];
    let base = arm_scores(0);
    Ok(sc
        .candidates
        .iter()
        .enumerate()
        .map(|(i, c)| cand_result(c, sc.arm(Some(c), swept).1, base, arm_scores(i + 1), alpha))
        .collect())
}

fn cand_result(c: &CandidateSpec, rule: Policy, base: &[WindowScore], cand: &[WindowScore], alpha: f64) -> CandResult {
    let measures = MEASURES
        .iter()
        .map(|&(key, higher, f)| {
            let b: Vec<f64> = base.iter().map(f).collect();
            let x: Vec<f64> = cand.iter().map(f).collect();
            let interval = paired(&b, &x, alpha);
            let v = if interval.lo.is_nan() || interval.hi.is_nan() { Verdict::CannotSay } else { verdict(&interval, higher) };
            Measure { key, higher_is_better: higher, base: b, cand: x, interval, verdict: v }
        })
        .collect();
    CandResult { name: c.name.clone(), rule, measures }
}

pub fn score(shop: &Shop, sc: &Scenario, p: &Protocol) -> Result<Report, String> {
    sc.check(shop)?;
    if p.seeds.len() < 2 {
        return Err("at least two seeds".into());
    }
    let m = sc.candidates.len().max(1) as f64;
    let alpha = 0.05 / m;
    let candidates = score_point(shop, sc, p, None, alpha)?;
    let best = candidates
        .iter()
        .filter(|c| c.measure("reward").verdict == Verdict::Better)
        .max_by(|a, b| a.measure("reward").interval.lo.partial_cmp(&b.measure("reward").interval.lo).unwrap())
        .map(|c| c.name.clone());
    let sweep = match &sc.sweep {
        None => None,
        Some(sw) => {
            let points = sw.points();
            let by_point = points.iter().map(|&x| score_point(shop, sc, p, Some(x), alpha)).collect::<Result<Vec<_>, _>>()?;
            let crossovers = sc
                .candidates
                .iter()
                .enumerate()
                .map(|(i, c)| {
                    let pts: Vec<(f64, Interval)> = points.iter().zip(&by_point).map(|(x, r)| (*x, r[i].measure("reward").interval.clone())).collect();
                    (c.name.clone(), crossover(&pts))
                })
                .collect();
            Some(SweepResult { shock: sw.shock.clone(), field: sw.field.clone(), points, by_point, crossovers })
        }
    };
    Ok(Report { scenario: sc.clone(), protocol: p.clone(), alpha_each: alpha, candidates, best, sweep })
}

// ------------------------------------------------------------------ JSON

fn js(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            c if (c as u32) < 0x20 => {
                let _ = write!(o, "\\u{:04x}", c as u32);
            }
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

fn num(x: f64) -> String {
    if x.is_finite() { format!("{x}") } else { "null".into() }
}

fn nums(v: &[f64]) -> String {
    format!("[{}]", v.iter().map(|x| num(*x)).collect::<Vec<_>>().join(","))
}

fn verdict_word(v: Verdict) -> &'static str {
    match v {
        Verdict::Better => "better",
        Verdict::Worse => "worse",
        Verdict::CannotSay => "no clear effect",
    }
}

fn cands_json(cs: &[CandResult]) -> String {
    let mut o = String::from("[");
    for (i, c) in cs.iter().enumerate() {
        if i > 0 {
            o.push(',');
        }
        let _ = write!(o, "{{\"name\":{},\"rule\":{},\"measures\":{{", js(&c.name), js(c.rule.name()));
        for (k, m) in c.measures.iter().enumerate() {
            if k > 0 {
                o.push(',');
            }
            let _ = write!(
                o,
                "{}:{{\"higher_is_better\":{},\"today\":{},\"candidate\":{},\"mean\":{},\"lo\":{},\"hi\":{},\"verdict\":{}}}",
                js(m.key),
                m.higher_is_better,
                nums(&m.base),
                nums(&m.cand),
                num(m.interval.mean),
                num(m.interval.lo),
                num(m.interval.hi),
                js(verdict_word(m.verdict))
            );
        }
        o.push_str("}}");
    }
    o.push(']');
    o
}

fn crossover_text(c: &Crossover) -> String {
    match c {
        Crossover::None(v) => format!("same verdict over the whole range: {}", v.label()),
        Crossover::Partial(v) => format!("{} over part of the range, no clear effect elsewhere", v.label()),
        Crossover::Unclear => "no clear effect anywhere in the range".into(),
        Crossover::Between { last_clear_before, first_clear_after, unclear } => {
            format!("changes between {last_clear_before} and {first_clear_after} (no clear effect at {unclear:?})")
        }
        Crossover::Several(v) => format!("changes more than once: {v:?}"),
    }
}

impl Report {
    pub fn to_json(&self) -> String {
        let sc = &self.scenario;
        let p = &self.protocol;
        let mut o = String::from("{\"model\":\"SMT2020\",");
        let _ = write!(o, "\"question\":{},\"shocks\":[", js(&sc.question));
        for (i, sh) in sc.shocks.iter().enumerate() {
            if i > 0 {
                o.push(',');
            }
            let _ = write!(o, "{{\"kind\":{},\"value\":{},\"said\":{}}}", js(sh.kind.name()), js(&format!("{:?}", sh.kind)), sh.said);
        }
        let _ = write!(
            o,
            "],\"warmup_days\":{},\"window_days\":{},\"seeds\":{:?},\"alpha_each\":{},\"guarantee\":{},\"candidates\":{},\"best\":{}",
            num(p.warmup_days),
            num(p.window_days),
            p.seeds,
            num(self.alpha_each),
            js(&format!(
                "paired t intervals at level {:.4} each (Bonferroni over {} candidates), so all hold at once with probability at least 95%; exact if the per-seed differences are normal, asymptotic otherwise",
                self.alpha_each,
                sc.candidates.len().max(1)
            )),
            cands_json(&self.candidates),
            self.best.as_deref().map(js).unwrap_or_else(|| "null".into())
        );
        if let Some(sw) = &self.sweep {
            let _ = write!(o, ",\"sweep\":{{\"shock\":{},\"field\":{},\"points\":{},\"by_point\":[", js(&sw.shock), js(&sw.field), nums(&sw.points));
            for (i, r) in sw.by_point.iter().enumerate() {
                if i > 0 {
                    o.push(',');
                }
                o.push_str(&cands_json(r));
            }
            o.push_str("],\"crossovers\":[");
            for (i, (n, c)) in sw.crossovers.iter().enumerate() {
                if i > 0 {
                    o.push(',');
                }
                let _ = write!(o, "{{\"candidate\":{},\"on\":\"reward\",\"text\":{}}}", js(n), js(&crossover_text(c)));
            }
            o.push_str("]}");
        }
        let _ = write!(o, ",\"real_fab\":{}}}", js(REAL_FAB_EFFECT));
        o
    }
}
