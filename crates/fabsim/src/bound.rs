//! Regret option C (docs/LONG-RESCORE.md): the capacity ceiling. No schedule gets more wafers out a day than the
//! busiest tool group can pass at the released product mix, nor more than is released. Exact arithmetic over the
//! model's numbers; a ceiling, never reached, since setups, rework, waiting for batches and the order of work only
//! lower what a real schedule gets.
//!
//! - Each step's tool minutes per wafer: per piece, its time (with the interval for the next pieces) plus the load
//!   and unload spread over the lot; per lot, the lot's time over its wafers; per batch, the batch's time over the
//!   largest batch. A sampled step counts by its share.
//! - The expected ceiling takes each tool's expected time down: breakdowns at mean repair over mean time between
//!   failures plus repair, maintenance by calendar at its mean length over its period, and maintenance by wafers as
//!   more minutes per wafer. The strict ceiling takes no time down at all.

use crate::shop::{Per, Shop};
use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq)]
pub struct GroupCap {
    pub name: String,
    /// tool minutes each wafer out needs at this group, at the released mix (maintenance by wafers included)
    pub minutes_per_wafer: f64,
    /// tool minutes a day the group has, after its expected time down
    pub available_minutes_per_day: f64,
    /// wafers out a day this group alone allows
    pub wafers_per_day: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Capacity {
    pub wafers_per_day: f64,
    pub strict_wafers_per_day: f64,
    pub released_per_day: f64,
    /// the group that sets the ceiling, or "released"
    pub bottleneck: String,
    pub groups: Vec<GroupCap>,
}

/// Tool minutes a wafer of a lot of `n` wafers takes at one step (before maintenance by wafers).
fn step_minutes(per: Per, time: f64, interval: Option<f64>, batch_max: Option<f64>, load: f64, unload: f64, n: f64) -> f64 {
    let handling = load + unload;
    match per {
        Per::Piece => match interval {
            Some(i) if i != 0.0 => (time + (n - 1.0) * i + handling) / n,
            _ => time + handling / n,
        },
        Per::Lot => (time + handling) / n,
        Per::Batch => (time + handling) / batch_max.unwrap_or(n).max(1.0),
    }
}

pub fn capacity(shop: &Shop) -> Capacity {
    // wafers released a day by route, and each route's lot size
    let mut released: HashMap<&str, (f64, f64, f64)> = HashMap::new(); // route -> (wafers a day, lots a day, wafers)
    for r in &shop.releases {
        if r.every > 0.0 {
            let e = released.entry(r.route.as_str()).or_insert((0.0, 0.0, 0.0));
            e.0 += r.size as f64 * 1440.0 / r.every;
            e.1 += 1440.0 / r.every;
            e.2 += r.size as f64 * 1440.0 / r.every;
        }
    }
    let total: f64 = released.values().map(|v| v.0).sum();
    let gi: HashMap<&str, usize> = shop.groups.iter().enumerate().map(|(i, g)| (g.name.as_str(), i)).collect();
    // per output wafer at the released mix: tool minutes at each group, and wafers processed there
    let mut work = vec![0.0; shop.groups.len()];
    let mut visits = vec![0.0; shop.groups.len()];
    for route in &shop.routes {
        let Some(&(wafers, lots, _)) = released.get(route.name.as_str()) else { continue };
        if wafers <= 0.0 || total <= 0.0 {
            continue;
        }
        let share = wafers / total;
        let n = wafers / lots;
        for s in &route.steps {
            let Some(&g) = gi.get(s.group.as_str()) else { continue };
            let grp = &shop.groups[g];
            let p = s.sample.unwrap_or(1.0);
            work[g] += share * p * step_minutes(s.per, s.time, s.interval, s.batch.map(|b| b.1), grp.load, grp.unload, n);
            visits[g] += share * p;
        }
    }
    let mut groups = vec![];
    let (mut best, mut strict) = (f64::INFINITY, f64::INFINITY);
    let mut bottleneck = "released".to_string();
    for (g, grp) in shop.groups.iter().enumerate() {
        if work[g] <= 0.0 || grp.count == 0 {
            continue;
        }
        let mut down = 0.0;
        if let Some((mttf, mttr)) = grp.breakdown {
            down += mttr / (mttf + mttr);
        }
        for pm in &grp.pm {
            if pm.every > 0.0 {
                down += (pm.lo + pm.hi) / 2.0 / pm.every;
            }
        }
        let per_wafer_pm: f64 = grp.pm_pieces.iter().filter(|pm| pm.every > 0.0).map(|pm| (pm.lo + pm.hi) / 2.0 / pm.every).sum();
        let minutes_per_wafer = work[g] + per_wafer_pm * visits[g];
        let available = grp.count as f64 * 1440.0 * (1.0 - down).max(0.0);
        let wpd = available / minutes_per_wafer;
        let strict_g = grp.count as f64 * 1440.0 / work[g];
        if wpd < best {
            best = wpd;
            bottleneck = grp.name.clone();
        }
        strict = strict.min(strict_g);
        groups.push(GroupCap { name: grp.name.clone(), minutes_per_wafer, available_minutes_per_day: available, wafers_per_day: wpd });
    }
    if total <= best {
        best = total;
        bottleneck = "released".into();
    }
    Capacity { wafers_per_day: best, strict_wafers_per_day: strict.min(total), released_per_day: total, bottleneck, groups }
}
