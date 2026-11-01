//! Every lot finishes its route (docs/DOUBLE-CHECK.md, part 1), worked out with no simulator.
//!
//! After step k a lot goes to step k+1, or, when the step has rework (to, p), back to `to` with chance p; a step that
//! samples is done with its chance and skipped otherwise (the engine's `move_on` and job end). So a route is a chain of
//! chances over "the lot comes to step k". A released lot does its first step for certain (the engine's release puts
//! it in the step's queue with no sampling draw), then moves on from it as from any step. The expected visits solve
//! c = b + c P, b where the lot goes after that first job; here in floating point, with the largest residual of the
//! equations reported. A step's minutes are the engine's for a lot alone: per
//! piece the time for each wafer (or the time plus the interval for each wafer after the first), else the time, plus the
//! group's load and unload; the mean of the spread draw is the time. Setups are left out.

use crate::checks::{Issue, Severity};
use crate::shop::{Per, Route, Shop};

#[derive(Clone, Debug, PartialEq)]
pub struct RouteChain {
    pub route: String,
    /// expected times each step is done by one lot
    pub visits: Vec<f64>,
    /// expected steps a lot does, rework and sampling counted
    pub expected_steps: f64,
    /// expected minutes of processing a lot gets (its raw processing time with rework and sampling)
    pub expected_minutes: f64,
    /// minutes of processing once through, every step done once (no rework, no sampling)
    pub once_minutes: f64,
    /// the lot size the minutes are for
    pub size: i64,
    /// the largest |c - e0 - c P| over the steps
    pub residual: f64,
}

/// The chance a step is done when a lot comes to it, and its rework (to, chance).
fn chances(r: &Route, k: usize) -> (f64, Option<(usize, f64)>) {
    let st = &r.steps[k];
    (st.sample.unwrap_or(1.0), st.rework)
}

/// Where a lot that comes to step k may go next, with chances; `n` is done.
fn moves(r: &Route, k: usize) -> Vec<(usize, f64)> {
    let (s, rw) = chances(r, k);
    let mut out = vec![(k + 1, 1.0 - s)];
    match rw {
        Some((to, p)) => {
            out.push((k + 1, s * (1.0 - p)));
            out.push((to, s * p));
        }
        None => out.push((k + 1, s)),
    }
    out.retain(|&(_, q)| q > 0.0);
    out
}

fn size_of(shop: &Shop, route: &str) -> i64 {
    shop.releases.iter().find(|x| x.route == route).map(|x| x.size).or_else(|| shop.lots.iter().find(|x| x.route == route).map(|x| x.size)).unwrap_or(25)
}

fn minutes(shop: &Shop, r: &Route, k: usize, size: i64) -> f64 {
    let st = &r.steps[k];
    let extra = shop.groups.iter().find(|g| g.name == st.group).map(|g| g.load + g.unload).unwrap_or(0.0);
    let x = st.time;
    (if st.per == Per::Piece {
        match st.interval {
            Some(iv) if iv != 0.0 => x + (size - 1) as f64 * iv,
            _ => x * size as f64,
        }
    } else {
        x
    }) + extra
}

/// Solve A x = b by Gaussian elimination with partial pivoting; None when A is singular.
fn solve(mut a: Vec<Vec<f64>>, mut b: Vec<f64>) -> Option<Vec<f64>> {
    let n = b.len();
    for col in 0..n {
        let piv = (col..n).max_by(|&i, &j| a[i][col].abs().total_cmp(&a[j][col].abs()))?;
        if a[piv][col].abs() < 1e-300 {
            return None;
        }
        a.swap(col, piv);
        b.swap(col, piv);
        for row in col + 1..n {
            let f = a[row][col] / a[col][col];
            if f != 0.0 {
                for c in col..n {
                    a[row][c] -= f * a[col][c];
                }
                b[row] -= f * b[col];
            }
        }
    }
    let mut x = vec![0.0; n];
    for row in (0..n).rev() {
        let s: f64 = (row + 1..n).map(|c| a[row][c] * x[c]).sum();
        x[row] = (b[row] - s) / a[row][row];
    }
    Some(x)
}

/// Each route's chain: expected visits, steps and minutes for a lot released at step 0.
pub fn analyse(shop: &Shop) -> Vec<RouteChain> {
    shop.routes.iter().map(|r| chain(shop, r)).collect()
}

fn chain(shop: &Shop, r: &Route) -> RouteChain {
    let n = r.steps.len();
    let size = size_of(shop, &r.name);
    // c_j - sum_k c_k P[k][j] = [j == 0], as rows of (I - P^T)
    let mut a = vec![vec![0.0; n]; n];
    for (j, row) in a.iter_mut().enumerate() {
        row[j] = 1.0;
    }
    let ok = issues_of(r).is_empty();
    for k in 0..n {
        for (j, q) in moves(r, k) {
            if j < n && ok {
                a[j][k] -= q;
            }
        }
    }
    // after the first job, done for certain: on to step 1, or back by its rework
    let mut b = vec![0.0; n];
    if n > 0 {
        let r0 = r.steps[0].rework;
        let p = r0.map(|x| x.1).unwrap_or(0.0);
        if n > 1 {
            b[1] += 1.0 - p;
        }
        if let Some((to, p)) = r0 {
            if to < n {
                b[to] += p;
            }
        }
    }
    let first = if n > 0 { 1.0 } else { 0.0 };
    let c = if ok { solve(a, b.clone()) } else { None };
    let Some(c) = c else {
        return RouteChain { route: r.name.clone(), visits: vec![f64::INFINITY; n], expected_steps: f64::INFINITY, expected_minutes: f64::INFINITY, once_minutes: (0..n).map(|k| minutes(shop, r, k, size)).sum(), size, residual: f64::INFINITY };
    };
    // the residual of the equations as written, from the chances themselves
    let mut back = vec![0.0; n];
    for (k, ck) in c.iter().enumerate() {
        for (j, q) in moves(r, k) {
            if j < n {
                back[j] += ck * q;
            }
        }
    }
    let residual = (0..n).map(|j| (c[j] - b[j] - back[j]).abs()).fold(0.0, f64::max);
    let visits: Vec<f64> = (0..n).map(|k| chances(r, k).0 * c[k] + if k == 0 { first } else { 0.0 }).collect();
    RouteChain {
        route: r.name.clone(),
        expected_steps: visits.iter().sum(),
        expected_minutes: (0..n).map(|k| visits[k] * minutes(shop, r, k, size)).sum(),
        once_minutes: (0..n).map(|k| minutes(shop, r, k, size)).sum(),
        visits,
        size,
        residual,
    }
}

fn issue(code: &'static str, message: String, at: Vec<String>) -> Issue {
    Issue { severity: Severity::Error, code, message, at }
}

fn issues_of(r: &Route) -> Vec<Issue> {
    let n = r.steps.len();
    let mut out = vec![];
    let at = |k: usize| vec![format!("{}#{}", r.name, k)];
    for (k, st) in r.steps.iter().enumerate() {
        let bad = |p: f64| !(0.0..=1.0).contains(&p);
        if st.sample.is_some_and(bad) || st.rework.is_some_and(|(_, p)| bad(p)) {
            out.push(issue("bad_chance", format!("Step {k} of {} has a chance outside 0 to 1: a sampling or rework chance is a share of lots.", r.name), at(k)));
        }
        if st.rework.is_some_and(|(to, _)| to >= n) {
            out.push(issue("rework_target", format!("Step {k} of {} sends lots back to step {}, which the route does not have: it has steps 0 to {}.", r.name, st.rework.unwrap().0, n.saturating_sub(1)), at(k)));
        }
    }
    if !out.is_empty() {
        return out;
    }
    // from every step the end must be reachable along moves with a chance above zero (a lot in progress may be anywhere)
    let mut can_end = vec![false; n + 1];
    can_end[n] = true;
    let mut back: Vec<Vec<usize>> = vec![vec![]; n + 1];
    for k in 0..n {
        for (j, _) in moves(r, k) {
            back[j].push(k);
        }
    }
    let mut stack = vec![n];
    while let Some(u) = stack.pop() {
        for &k in &back[u] {
            if !can_end[k] {
                can_end[k] = true;
                stack.push(k);
            }
        }
    }
    let stuck: Vec<usize> = (0..n).filter(|&k| !can_end[k]).collect();
    if !stuck.is_empty() {
        out.push(issue(
            "rework_certain",
            format!("A lot at step {} of {} is sent back every time and never finishes: make the rework chance less than 1.", stuck[0], r.name),
            stuck.iter().map(|&k| format!("{}#{}", r.name, k)).collect(),
        ));
    }
    out
}

/// Route errors for the layout checks: chances outside 0 to 1, rework to a step the route lacks, and steps a lot can
/// never finish from.
pub fn issues(shop: &Shop) -> Vec<Issue> {
    shop.routes.iter().flat_map(issues_of).collect()
}

/// A group's work at the release rates (docs/DOUBLE-CHECK.md, part 3): tool minutes a day, its machines, and the share
/// of their time that work needs. `exact` when no step at the group batches; at a batch step the lots a job takes are
/// not known before the run, so the share counts the largest batch, a floor.
#[derive(Clone, Debug, PartialEq)]
pub struct GroupLoad {
    pub name: String,
    pub tools: usize,
    pub minutes_per_day: f64,
    pub share: f64,
    pub exact: bool,
}

/// Minutes one job at step k takes for `pieces` wafers, as the engine times it (the spread's mean).
fn job_minutes(shop: &Shop, r: &Route, k: usize, pieces: f64) -> f64 {
    let st = &r.steps[k];
    let extra = shop.groups.iter().find(|g| g.name == st.group).map(|g| g.load + g.unload).unwrap_or(0.0);
    (if st.per == Per::Piece {
        match st.interval {
            Some(iv) if iv != 0.0 => st.time + (pieces - 1.0) * iv,
            _ => st.time * pieces,
        }
    } else {
        st.time
    }) + extra
}

/// Each group's work a day from the releases (each release a lot every `every` minutes, its count taken as unending),
/// with each step's expected visits from the route's chain.
pub fn loads(shop: &Shop) -> Vec<GroupLoad> {
    let chains = analyse(shop);
    let mut work = vec![0.0; shop.groups.len()];
    let mut exact = vec![true; shop.groups.len()];
    let gi = |name: &str| shop.groups.iter().position(|g| g.name == name);
    for (r, c) in shop.routes.iter().zip(&chains) {
        if !c.expected_steps.is_finite() {
            continue;
        }
        for rel in shop.releases.iter().filter(|x| x.route == r.name && x.every > 0.0) {
            let per_day = 1440.0 / rel.every;
            let size = rel.size as f64;
            for (k, st) in r.steps.iter().enumerate() {
                let Some(g) = gi(&st.group) else { continue };
                let per_lot = match st.batch {
                    Some((_, hi)) if hi > 0.0 => {
                        exact[g] = false;
                        let pieces = hi.max(size);
                        job_minutes(shop, r, k, pieces) * size / pieces
                    }
                    _ => job_minutes(shop, r, k, size),
                };
                work[g] += per_day * c.visits[k] * per_lot;
            }
        }
    }
    shop.groups
        .iter()
        .enumerate()
        .map(|(g, x)| GroupLoad { name: x.name.clone(), tools: x.count, minutes_per_day: work[g], share: if x.count > 0 { work[g] / (x.count as f64 * 1440.0) } else { f64::INFINITY }, exact: exact[g] })
        .collect()
}
