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

/// Run a shop under a policy.
pub fn run_with(shop: &Shop, opts: &RunOptions, policy: Policy) -> RunResult {
    match policy {
        Policy::Today => run(shop, opts, None),
        Policy::Fifo => {
            let mut pick = |d: &Decision| argmin(d, |c| (-c.waited_minutes, 0.0));
            run(shop, opts, Some(&mut pick))
        }
        Policy::Spt => {
            let mut pick = |d: &Decision| argmin(d, |c| (c.proc_minutes, -c.waited_minutes));
            run(shop, opts, Some(&mut pick))
        }
        Policy::CriticalRatio => {
            let work: std::collections::HashMap<(String, i64), f64> = shop
                .routes
                .iter()
                .flat_map(|r| [25i64, 1].map(|sz| ((r.name.clone(), sz), route_work(shop, &r.name, sz))))
                .collect();
            let mut pick = |d: &Decision| {
                argmin(d, |c| {
                    let size = c.size_wafers.max(1) / c.lots.len().max(1) as i64;
                    let w = work.get(&(c.route.clone(), size)).copied().unwrap_or_else(|| route_work(shop, &c.route, size));
                    let due = c.release + DUE_FACTOR * w;
                    ((due - d.t) / c.work_left_minutes.max(1.0), -c.waited_minutes)
                })
            };
            run(shop, opts, Some(&mut pick))
        }
        Policy::Random => {
            let mut r = PyRandom::from_str_seed(&format!("{}/random-rule", opts.seed));
            let mut pick = |d: &Decision| ((r.random() * d.candidates.len() as f64) as usize).min(d.candidates.len() - 1);
            run(shop, opts, Some(&mut pick))
        }
    }
}
