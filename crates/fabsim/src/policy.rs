//! Dispatch rules: today's rule (the engine's own) and the baselines of docs/PROBLEM.md.

use crate::engine::{run, Candidate, Decision, RunOptions, RunResult};
use crate::pyrandom::PyRandom;
use crate::shop::{Per, Shop};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Policy {
    /// hot lots first, then no setup change, then oldest
    Today,
    /// first come, first served
    Fifo,
    /// shortest processing first
    Spt,
    /// smallest (due - now) / work left first; due at release plus 3 times the route's work
    CriticalRatio,
    /// a seeded random pick
    Random,
}

impl Policy {
    pub fn parse(s: &str) -> Option<Policy> {
        match s {
            "today" => Some(Policy::Today),
            "fifo" => Some(Policy::Fifo),
            "spt" => Some(Policy::Spt),
            "cr" => Some(Policy::CriticalRatio),
            "random" => Some(Policy::Random),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Policy::Today => "today",
            Policy::Fifo => "fifo",
            Policy::Spt => "spt",
            Policy::CriticalRatio => "cr",
            Policy::Random => "random",
        }
    }
}

/// The due-date factor for critical ratio (assumed, docs/PROBLEM.md).
pub const DUE_FACTOR: f64 = 3.0;

/// Nominal processing minutes of a whole route for a lot of `size` pieces (no load, unload,
/// transport or waiting).
pub fn route_work(shop: &Shop, route: &str, size: i64) -> f64 {
    shop.routes
        .iter()
        .find(|r| r.name == route)
        .map(|r| r.steps.iter().map(|s| if s.per == Per::Piece { s.time * size as f64 } else { s.time }).sum())
        .unwrap_or(0.0)
}

/// The index with the smallest key, starting from the engine's own pick (so ties keep it).
pub fn argmin(d: &Decision, key: impl Fn(&Candidate) -> (f64, f64)) -> usize {
    let mut best = d.default;
    let mut bk = key(&d.candidates[best]);
    for (i, c) in d.candidates.iter().enumerate() {
        let k = key(c);
        if k < bk {
            best = i;
            bk = k;
        }
    }
    best
}

/// A built-in rule as a value a run can copy (docs/LONG-RESCORE.md): its policy, the random rule's stream and the
/// critical ratio's route work.
#[derive(Clone)]
pub struct Rule {
    pub policy: Policy,
    rng: PyRandom,
    work: Option<std::sync::Arc<std::collections::HashMap<(String, i64), f64>>>,
}

impl Rule {
    pub fn new(shop: &Shop, policy: Policy, seed: u64) -> Rule {
        let work = (policy == Policy::CriticalRatio).then(|| {
            std::sync::Arc::new(
                shop.routes.iter().flat_map(|r| [25i64, 1].map(|sz| ((r.name.clone(), sz), route_work(shop, &r.name, sz)))).collect(),
            )
        });
        Rule { policy, rng: PyRandom::from_str_seed(&format!("{seed}/random-rule")), work }
    }

    pub fn pick(&mut self, shop: &Shop, d: &Decision) -> usize {
        match self.policy {
            Policy::Today => d.default,
            Policy::Fifo => argmin(d, |c| (-c.waited_minutes, 0.0)),
            Policy::Spt => argmin(d, |c| (c.proc_minutes, -c.waited_minutes)),
            Policy::CriticalRatio => {
                let work = self.work.as_ref().unwrap();
                argmin(d, |c| {
                    let size = c.size_wafers.max(1) / c.lots.len().max(1) as i64;
                    let w = work.get(&(c.route.clone(), size)).copied().unwrap_or_else(|| route_work(shop, &c.route, size));
                    let due = c.release + DUE_FACTOR * w;
                    ((due - d.t) / c.work_left_minutes.max(1.0), -c.waited_minutes)
                })
            }
            Policy::Random => ((self.rng.random() * d.candidates.len() as f64) as usize).min(d.candidates.len() - 1),
        }
    }
}

/// A policy's pick at each decision (docs/LONG-RESCORE.md), for a run or for the window of an episode. `seed` seeds
/// the random rule.
pub fn picker<'a>(shop: &'a Shop, policy: Policy, seed: u64) -> Box<dyn FnMut(&Decision) -> usize + 'a> {
    let mut r = Rule::new(shop, policy, seed);
    Box::new(move |d: &Decision| r.pick(shop, d))
}

/// Run a shop under a policy.
pub fn run_with(shop: &Shop, opts: &RunOptions, policy: Policy) -> RunResult {
    if policy == Policy::Today {
        return run(shop, opts, None);
    }
    let mut p = picker(shop, policy, opts.seed);
    let mut pick = |d: &Decision| p(d);
    run(shop, opts, Some(&mut pick))
}
