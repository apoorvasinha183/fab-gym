//! The scorer: today's fab against each candidate on paired held-out seeds (docs/ASK.md).

use std::fmt::Write as _;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use std::path::PathBuf;

use crate::engine::{run, Decision, RunOptions, RunResult};
use crate::layout::Config;
use crate::money::{money, PriceGrid};
use crate::policy::{run_with, Policy};
use crate::scenario::{CandidateSpec, Change, FloorKind, Scenario};
use crate::twofam::{apply_policy, b_cap, b_first, contested, copy_groups, lay_out_copies, policy_groups, two_family_shop, EngLots, Policy as FamPolicy};
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

impl Protocol {
    /// docs/ASK-FAMILIES.md: 120 days of warm-up, a 120-day window, seeds 0 to 9.
    pub fn families() -> Protocol {
        Protocol { warmup_days: 120.0, window_days: 120.0, seeds: (0..10).collect(), threads: 4 }
    }
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
    /// a two-family candidate's money in dollars (docs/MONEY-PL.md); None for other questions
    pub pl: Option<CandPl>,
}

/// What a candidate buys and what it is worth, at the central assumed prices.
#[derive(Clone, Debug)]
pub struct CandPl {
    pub capital: f64,
    /// net present value over the horizon: mean, lo, hi (capital is the same on every seed)
    pub npv: (f64, f64, f64),
    /// payback in days at the cash interval's ends: (soonest, latest); None is never
    pub payback: (Option<f64>, Option<f64>),
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
    /// a two-family question (docs/ASK-FAMILIES.md)
    pub families: bool,
    /// today and each candidate as run, for a two-family question (empty otherwise)
    pub arms: Vec<ArmOut>,
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
    let names: Vec<&str> = std::iter::once("today").chain(sc.candidates.iter().map(|c| c.name.as_str())).collect();
    let today = sc.arm(None, swept);
    arms.push((with_probes(&today.0.apply(shop)?, &w), today.1));
    for c in &sc.candidates {
        let (d, pol) = sc.arm(Some(c), swept);
        arms.push((with_probes(&d.apply(shop)?, &w), pol));
    }
    let jobs: Vec<(usize, u64)> = (0..arms.len()).flat_map(|a| p.seeds.iter().map(move |&s| (a, s))).collect();
    let scores = par_map(jobs, p.threads, |&(a, seed)| {
        let t0 = std::time::Instant::now();
        let r = run_with(&arms[a].0, &RunOptions { seed, until: Some(w.to), record: false }, arms[a].1);
        let s = window_score(&r, &w);
        if let Ok(ws) = &s {
            crate::progress::emit(|| {
                serde_json::json!({"e": "run", "arm": names[a], "seed": seed, "measure": "reward", "value": finite(ws.reward),
                    "moves": finite(ws.moves), "seconds": t0.elapsed().as_secs_f64(), "point": swept})
            });
        }
        s
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
    CandResult { name: c.name.clone(), rule, measures, pl: None }
}

/// A number for an event; NaN and infinities go as null (docs/RUNS.md).
fn finite(x: f64) -> Option<f64> {
    x.is_finite().then_some(x)
}

/// The start of a scoring: the setups, the random runs, the days, how many runs in all and the number each run reports.
fn start_event(sc: &Scenario, p: &Protocol, measure: &str) {
    crate::progress::emit(|| {
        let arms: Vec<&str> = std::iter::once("today").chain(sc.candidates.iter().map(|c| c.name.as_str())).collect();
        let points = 1 + sc.sweep.as_ref().map(|s| s.points().len()).unwrap_or(0);
        serde_json::json!({"e": "start", "runs": arms.len() * p.seeds.len() * points, "arms": arms, "seeds": p.seeds,
            "warmup_days": p.warmup_days, "window_days": p.window_days, "measure": measure, "threads": p.threads})
    });
}

pub fn score(shop: &Shop, sc: &Scenario, p: &Protocol) -> Result<Report, String> {
    if sc.family.is_some() {
        return Err("a two-family question needs its family context (score_with)".into());
    }
    sc.check(shop)?;
    if p.seeds.len() < 2 {
        return Err("at least two seeds".into());
    }
    let m = sc.candidates.len().max(1) as f64;
    let alpha = 0.05 / m;
    start_event(sc, p, "reward");
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
    crate::progress::emit(|| serde_json::json!({"e": "end", "best": best}));
    Ok(Report { families: false, arms: vec![], scenario: sc.clone(), protocol: p.clone(), alpha_each: alpha, candidates, best, sweep })
}

// ------------------------------------------------------------------ two families (docs/ASK-FAMILIES.md)

/// What a two-family question is built on.
#[derive(Clone, Debug)]
pub struct FamilyContext {
    /// family A's route that family B copies, and family B's route name
    pub from_route: String,
    pub b_route: String,
    /// each group's area; without them floors get their copies but no layout
    pub areas: Option<Vec<(String, String)>>,
    pub layout: Config,
    /// laid-out shops kept here by hash
    pub cache: Option<PathBuf>,
}

/// One arm of a two-family question, ready to run.
#[derive(Clone, Debug)]
pub struct ArmShop {
    pub shop: Shop,
    pub rule: Policy,
    pub bfirst: bool,
    pub tools_added: usize,
    pub metres_added: f64,
    /// (copy, area) for copies: the original's area in the halls, "P3 wing" in a wing
    pub extra_areas: Vec<(String, String)>,
    /// what the arm buys: tools by the area of the group they copy, and where they stand (docs/MONEY-PL.md)
    pub added: crate::pl::Added,
}

#[derive(Clone, Debug)]
pub struct ArmOut {
    pub name: String,
    pub rule: Policy,
    pub bfirst: bool,
    pub extra_areas: Vec<(String, String)>,
    pub shop_text: String,
}

fn laid_out(two: &Shop, ctx: &FamilyContext, picks: &[(String, usize)], wing: bool) -> Result<(Shop, usize, f64, &'static str), String> {
    let Some(areas) = &ctx.areas else {
        let s = copy_groups(two, picks, "B")?;
        return Ok((s, picks.iter().map(|p| p.1).sum(), 0.0, "none"));
    };
    let key = crate::hash::sha256_hex(
        format!("{}|{picks:?}|{wing}|{}|{}|{}", two.to_text(), ctx.layout.iters, ctx.layout.restarts, ctx.layout.seed).as_bytes(),
    );
    if let Some(dir) = &ctx.cache {
        if let (Ok(t), Ok(info)) = (std::fs::read_to_string(dir.join(format!("{key}.shop.txt"))), std::fs::read_to_string(dir.join(format!("{key}.info")))) {
            let mut it = info.split_whitespace();
            if let (Some(a), Some(b)) = (it.next().and_then(|x| x.parse().ok()), it.next().and_then(|x| x.parse().ok())) {
                return Ok((Shop::parse(&t)?, a, b, "saved"));
            }
        }
    }
    let (s, info) = lay_out_copies(two, areas, &ctx.layout, picks, wing, "B")?;
    if let Some(dir) = &ctx.cache {
        let _ = std::fs::create_dir_all(dir);
        let _ = std::fs::write(dir.join(format!("{key}.shop.txt")), s.to_text());
        let _ = std::fs::write(dir.join(format!("{key}.info")), format!("{} {}", info.tools_added, info.metres_added));
    }
    Ok((s, info.tools_added, info.metres_added, "new"))
}

/// Today (no candidate) or a candidate of a two-family question as a shop: family B at the share (or the swept
/// share), the floor laid out, the policy applied, then the shocks and the candidate's other changes.
pub fn family_arm(
    base: &Shop,
    sc: &Scenario,
    cand: Option<&CandidateSpec>,
    swept: Option<f64>,
    p: &Protocol,
    ctx: &FamilyContext,
) -> Result<ArmShop, String> {
    let fam = sc.family.as_ref().ok_or("not a two-family question")?;
    let family_swept = sc.sweep.as_ref().is_some_and(|s| s.shock == "family");
    let share = if family_swept { swept.unwrap_or(fam.share) } else { fam.share };
    let e = EngLots { scale: share, ..EngLots::published(&ctx.b_route, (p.warmup_days + p.window_days) * 1440.0, 1) };
    let two = two_family_shop(base, &ctx.from_route, &e)?;
    let changes: &[Change] = cand.map(|c| c.changes.as_slice()).unwrap_or(&[]);
    let floor = changes.iter().find_map(|c| if let Change::Floor(f) = c { Some(*f) } else { None }).unwrap_or(FloorKind::Share);
    let pol = changes.iter().find_map(|c| if let Change::FamilyPolicy(p) = c { Some(*p) } else { None }).unwrap_or(FamPolicy::Today);
    let picks: Vec<(String, usize)> =
        if floor == FloorKind::Share { vec![] } else { contested(&two, "B", 3).into_iter().map(|g| (g, 1)).collect() };
    let wing = floor == FloorKind::Wing;
    let t0 = std::time::Instant::now();
    let (laid, tools_added, metres_added, how) = laid_out(&two, ctx, &picks, wing)?;
    crate::progress::emit(|| {
        serde_json::json!({"e": "floor", "arm": cand.map(|c| c.name.as_str()).unwrap_or("today"), "how": how,
            "groups": laid.groups.len(), "copies": picks.len(), "wing": wing, "seconds": t0.elapsed().as_secs_f64(), "point": swept})
    });
    let extra_areas = match &ctx.areas {
        None => vec![],
        Some(areas) => picks
            .iter()
            .map(|(g, _)| {
                let a = if wing { "P3 wing".to_string() } else { areas.iter().find(|x| x.0 == *g).map(|x| x.1.clone()).unwrap_or_default() };
                (format!("{g}@B"), a)
            })
            .collect(),
    };
    let groups = policy_groups(&laid, "B", 3);
    let raw = crate::measure::raw_processing_days(base, 20, 0).get(&ctx.from_route).copied().ok_or("no raw processing time for the route")?;
    let with_pol = apply_policy(&laid, pol, "B", &groups, b_cap(&e, raw));
    let (dials, rule) = sc.arm(cand, if family_swept { None } else { swept });
    let shop = dials.apply(&with_pol)?;
    // what it buys: the copies (in a wing or the halls) and any spare tools (in the halls)
    let area_of = |g: &str| ctx.areas.as_ref().and_then(|a| a.iter().find(|x| x.0 == g).map(|x| x.1.clone())).unwrap_or_default();
    let mut tools: Vec<(String, usize)> = picks.iter().map(|(g, n)| (area_of(g), *n)).collect();
    tools.extend(dials.spare.iter().map(|(g, n)| (area_of(g), *n)));
    let place = if picks.is_empty() && dials.spare.is_empty() {
        crate::pl::Place::None
    } else if wing {
        crate::pl::Place::Wing
    } else {
        crate::pl::Place::Halls
    };
    let added = crate::pl::Added { tools, place };
    Ok(ArmShop { shop, rule, bfirst: pol == FamPolicy::BFirst, tools_added, metres_added, extra_areas, added })
}

/// One run of an arm: the window's scores, and money, family A's wafers, family B's lots and cycle time.
#[derive(Clone, Debug)]
struct FamRun {
    w: WindowScore,
    money: f64,
    profit: f64,
    cash: f64,
    a_wafers: f64,
    b_lots: f64,
    b_cycle: f64,
}

fn run_arm(a: &ArmShop, seed: u64, w: &Window) -> RunResult {
    let o = RunOptions { seed, until: Some(w.to), record: false };
    if a.bfirst {
        let mut pick = |d: &Decision| b_first(d, "B");
        run(&a.shop, &o, Some(&mut pick))
    } else {
        run_with(&a.shop, &o, a.rule)
    }
}

const FAM_MEASURES: [(&str, bool, fn(&FamRun) -> f64); 6] = [
    ("profit", true, |r| r.profit),
    ("cash", true, |r| r.cash),
    ("money", true, |r| r.money),
    ("a_wafers", true, |r| r.a_wafers),
    ("b_lots", true, |r| r.b_lots),
    ("b_cycle_days", false, |r| r.b_cycle),
];

fn fam_cand(name: &str, rule: Policy, base: &[FamRun], cand: &[FamRun], alpha: f64, capital: f64) -> CandResult {
    let mut measures = vec![];
    let mut push = |key: &'static str, higher: bool, b: Vec<f64>, x: Vec<f64>| {
        let interval = paired(&b, &x, alpha);
        let v = if interval.lo.is_nan() || interval.hi.is_nan() { Verdict::CannotSay } else { verdict(&interval, higher) };
        measures.push(Measure { key, higher_is_better: higher, base: b, cand: x, interval, verdict: v });
    };
    for &(k, h, f) in FAM_MEASURES.iter() {
        push(k, h, base.iter().map(f).collect(), cand.iter().map(f).collect());
    }
    for &(k, h, f) in MEASURES.iter() {
        push(k, h, base.iter().map(|r| f(&r.w)).collect(), cand.iter().map(|r| f(&r.w)).collect());
    }
    let cash = &measures.iter().find(|m| m.key == "cash").expect("cash is measured").interval;
    let f = crate::pl::npv_factor(&crate::pl::Sheet::central());
    let at = |d: f64| if d > 0.0 { Some(capital / d) } else { None };
    let pl = CandPl { capital, npv: (-capital + cash.mean * f, -capital + cash.lo * f, -capital + cash.hi * f), payback: (at(cash.hi), at(cash.lo)) };
    CandResult { name: name.to_string(), rule, measures, pl: Some(pl) }
}

fn fam_point(base: &Shop, sc: &Scenario, p: &Protocol, ctx: &FamilyContext, swept: Option<f64>, alpha: f64) -> Result<(Vec<CandResult>, Vec<(String, ArmShop)>), String> {
    let w = Window { from: p.warmup_days * 1440.0, to: (p.warmup_days + p.window_days) * 1440.0 };
    let mut arms: Vec<(String, ArmShop)> = vec![("today".into(), family_arm(base, sc, None, swept, p, ctx)?)];
    for c in &sc.candidates {
        arms.push((c.name.clone(), family_arm(base, sc, Some(c), swept, p, ctx)?));
    }
    let probed: Vec<ArmShop> = arms.iter().map(|(_, a)| ArmShop { shop: with_probes(&a.shop, &w), ..a.clone() }).collect();
    let central = PriceGrid::preregistered("B").remove(0);
    let jobs: Vec<(usize, u64)> = (0..probed.len()).flat_map(|a| p.seeds.iter().map(move |&s| (a, s))).collect();
    let runs = par_map(jobs, p.threads, |&(a, seed)| -> Result<FamRun, String> {
        let t0 = std::time::Instant::now();
        let arm = &probed[a];
        let r = run_arm(arm, seed, &w);
        let m = money(&arm.shop, &r, &w, &central, arm.tools_added, arm.metres_added);
        let days = (w.to - w.from) / 1440.0;
        let a_w: f64 = r
            .lots
            .iter()
            .filter(|l| arm.shop.family_of(&l.route) != "B" && l.done.is_some_and(|d| d > w.from && d <= w.to))
            .map(|l| l.size as f64)
            .sum();
        let sheet = crate::pl::Sheet::central();
        let cap = crate::pl::capital(&arm.added, &sheet);
        let b_revenue_day = crate::pl::b_revenue_day(&arm.shop, &r, &w, &sheet);
        let pl = crate::pl::run_pl(&crate::pl::RunIn { a_wafers_day: a_w / days, b_wafers_day: m.b_wafers as f64 / days, b_revenue_day }, &cap, &sheet);
        let ws = window_score(&r, &w)?;
        crate::progress::emit(|| {
            serde_json::json!({"e": "run", "arm": arms[a].0, "seed": seed, "measure": "profit", "value": finite(pl.profit),
                "a_wafers": finite(a_w / days), "moves": finite(ws.moves), "seconds": t0.elapsed().as_secs_f64(), "point": swept})
        });
        Ok(FamRun {
            w: ws,
            money: m.per_day,
            profit: pl.profit,
            cash: pl.cash,
            a_wafers: a_w / days,
            b_lots: m.b_lots as f64,
            b_cycle: m.b_cycle_days.unwrap_or(f64::NAN),
        })
    });
    let runs: Vec<FamRun> = runs.into_iter().collect::<Result<_, _>>()?;
    let n = p.seeds.len();
    let of = |a: usize| &runs[a * n..(a + 1) * n];
    let sheet = crate::pl::Sheet::central();
    let cands = sc
        .candidates
        .iter()
        .enumerate()
        .map(|(i, c)| fam_cand(&c.name, arms[i + 1].1.rule, of(0), of(i + 1), alpha, crate::pl::capital(&arms[i + 1].1.added, &sheet).total))
        .collect();
    Ok((cands, arms))
}

/// Score a scenario; a two-family question needs its context (docs/ASK-FAMILIES.md).
pub fn score_with(shop: &Shop, sc: &Scenario, p: &Protocol, fam: Option<&FamilyContext>) -> Result<Report, String> {
    if sc.family.is_none() {
        return score(shop, sc, p);
    }
    let ctx = fam.ok_or("a two-family question needs its family context")?;
    sc.check(shop)?;
    if p.seeds.len() < 2 {
        return Err("at least two seeds".into());
    }
    let alpha = 0.05 / sc.candidates.len().max(1) as f64;
    start_event(sc, p, "profit");
    let (candidates, arms) = fam_point(shop, sc, p, ctx, None, alpha)?;
    let best = candidates
        .iter()
        .filter(|c| c.measure("profit").verdict == Verdict::Better)
        .max_by(|a, b| a.measure("profit").interval.lo.total_cmp(&b.measure("profit").interval.lo))
        .map(|c| c.name.clone());
    let sweep = match &sc.sweep {
        None => None,
        Some(sw) => {
            let points = sw.points();
            let by_point = points.iter().map(|&x| fam_point(shop, sc, p, ctx, Some(x), alpha).map(|r| r.0)).collect::<Result<Vec<_>, _>>()?;
            let crossovers = sc
                .candidates
                .iter()
                .enumerate()
                .map(|(i, c)| {
                    let pts: Vec<(f64, Interval)> = points.iter().zip(&by_point).map(|(x, r)| (*x, r[i].measure("profit").interval.clone())).collect();
                    (c.name.clone(), crossover(&pts))
                })
                .collect();
            Some(SweepResult { shock: sw.shock.clone(), field: sw.field.clone(), points, by_point, crossovers })
        }
    };
    let arms = arms
        .into_iter()
        .map(|(name, a)| ArmOut { name, rule: a.rule, bfirst: a.bfirst, extra_areas: a.extra_areas, shop_text: a.shop.to_text() })
        .collect();
    crate::progress::emit(|| serde_json::json!({"e": "end", "best": best}));
    Ok(Report { families: true, arms, scenario: sc.clone(), protocol: p.clone(), alpha_each: alpha, candidates, best, sweep })
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
        o.push('}');
        if let Some(p) = &c.pl {
            let opt = |x: Option<f64>| x.map(num).unwrap_or_else(|| "null".into());
            let _ = write!(
                o,
                ",\"pl\":{{\"capital\":{},\"npv\":{{\"mean\":{},\"lo\":{},\"hi\":{}}},\"payback_days\":{{\"soonest\":{},\"latest\":{}}}}}",
                num(p.capital),
                num(p.npv.0),
                num(p.npv.1),
                num(p.npv.2),
                opt(p.payback.0),
                opt(p.payback.1)
            );
        }
        o.push('}');
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
        let _ = write!(o, "\"families\":{},", self.families);
        if let Some(f) = &sc.family {
            let _ = write!(o, "\"family\":{{\"share\":{},\"said\":{}}},", num(f.share), f.said);
        }
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
                let _ = write!(o, "{{\"candidate\":{},\"on\":{},\"text\":{}}}", js(n), js(if self.families { "money" } else { "reward" }), js(&crossover_text(c)));
            }
            o.push_str("]}");
        }
        if self.families {
            o.push_str(",\"arms\":[");
            for (i, a) in self.arms.iter().enumerate() {
                if i > 0 {
                    o.push(',');
                }
                let ex: Vec<String> = a.extra_areas.iter().map(|(g, ar)| format!("[{},{}]", js(g), js(ar))).collect();
                let _ = write!(o, "{{\"name\":{},\"rule\":{},\"bfirst\":{},\"extra_areas\":[{}],\"shop\":{}}}", js(&a.name), js(a.rule.name()), a.bfirst, ex.join(","), js(&a.shop_text));
            }
            o.push(']');
        }
        let _ = write!(o, ",\"real_fab\":{}}}", js(REAL_FAB_EFFECT));
        o
    }
}
