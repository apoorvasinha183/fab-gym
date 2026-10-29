//! Regret options B and D (docs/LONG-RESCORE.md), on runs that can be copied (`engine::Stepper`). The value is the
//! reward's measure: lots finished minus 0.01 per lot-hour waiting, gained over a stretch of time.
//!
//! - B, the foresight audit: at sampled picks of a policy's own run (its recorded picks replayed), each lot the tool
//!   could have taken is tried on a copy with the same luck ahead and today's rule playing on for `horizon` minutes.
//!   The best is the pick with foresight; regret at that pick is the best's gain minus the policy's. Greedy and as
//!   long as the horizon: a lower estimate of what a better plan could gain.
//! - D, rule switching in hindsight: shift by shift, each rule of a library plays the shift on a copy, and the best
//!   copy is kept. The kept path is a target an agent that retunes each shift could reach; greedy shift by shift.

use crate::engine::{Player, RunOptions, Stepper};
use crate::policy::Policy;
use crate::shop::Shop;

/// A copy of a run, sent to a worker thread. The run's two callback slots (`Hook`) are not thread-safe, but a copy's
/// are always empty (`Hook`'s `Clone` gives `None`), and nothing else in it is tied to a thread.
struct Copied<'a>(Stepper<'a>);
// SAFETY: see above; the only parts that are not `Send` are the hooks, which a clone leaves empty.
unsafe impl Send for Copied<'_> {}

/// At most this many copies run at once (one heavy job, at most 4 workers).
pub const WORKERS: usize = 4;

#[derive(Clone, Debug, PartialEq)]
pub struct Sample {
    /// which counted pick of the window, and when
    pub k: u64,
    pub t: f64,
    /// how many lots (or batches) there were to choose from, and which of them were tried, in candidate order
    pub lots: usize,
    pub tried: Vec<usize>,
    /// each tried lot's gain over the horizon, in the order of `tried`; the policy's pick among them; best minus it
    pub values: Vec<f64>,
    pub chosen: usize,
    pub regret: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Audit {
    pub samples: Vec<Sample>,
    pub mean_regret: f64,
    pub horizon: f64,
}

/// B: `picks` are the policy's counted picks in the window [from, to] on `seed`; `n` evenly spaced of them are audited,
/// every lot tried.
pub fn audit(shop: &Shop, seed: u64, from: f64, to: f64, picks: &[u32], n: usize, horizon: f64) -> Audit {
    audit_with(shop, seed, from, to, picks, n, horizon, None)
}

/// B by kind: as `audit`, but one lot of each kind is tried (`engine::kinds_of`), the policy's own pick standing for
/// its kind. Fewer tries can only miss a better lot, so its regret is never above the full audit's.
pub fn audit_by_kind(shop: &Shop, seed: u64, from: f64, to: f64, picks: &[u32], n: usize, horizon: f64) -> Audit {
    audit_with(shop, seed, from, to, picks, n, horizon, Some(0))
}

/// B capped: one lot of each kind and the policy's pick, then lots spread evenly over the rest, at most `max` tried in
/// all (or the kinds, if there are more of them). Its regret lies between the audit by kind and the full audit.
#[allow(clippy::too_many_arguments)]
pub fn audit_capped(shop: &Shop, seed: u64, from: f64, to: f64, picks: &[u32], n: usize, horizon: f64, max: usize) -> Audit {
    audit_with(shop, seed, from, to, picks, n, horizon, Some(max))
}

#[allow(clippy::too_many_arguments)]
/// `cap`: None tries every lot; Some(m), one of each kind and the policy's pick, filled evenly up to m.
fn audit_with(shop: &Shop, seed: u64, from: f64, to: f64, picks: &[u32], n: usize, horizon: f64, cap: Option<usize>) -> Audit {
    let by_kind = cap.is_some();
    // the shop as an episode plays it (probes at the window's ends), so recorded picks replay their own run
    let probed = crate::window::with_probes(shop, &crate::window::Window { from, to });
    let shop = &probed;
    let opts = RunOptions { seed, until: Some(to + horizon), record: false };
    let n = n.min(picks.len());
    let ks: Vec<usize> = (0..n).map(|i| ((i as f64 + 0.5) * picks.len() as f64 / n as f64) as usize).collect();
    // a first pass finds when each pick comes and how many lots it chose from (and, by kind, their kinds)
    let mut player = Player::replay(picks.to_vec()).window(from, to);
    if by_kind {
        player = player.keep_kinds(ks.iter().map(|&k| k as u64).collect());
    }
    let mut first = Stepper::new(shop, &opts, Some(player));
    first.advance(to);
    let seen: Vec<(f64, u32)> = first.player().map(|p| p.seen().to_vec()).unwrap_or_default();
    let kinds: std::collections::HashMap<u64, Vec<u32>> = first.player().map(|p| p.kinds().iter().cloned().collect()).unwrap_or_default();
    let ks: Vec<usize> = ks.into_iter().filter(|&k| k < seen.len()).collect();
    let mut main = Stepper::new(shop, &opts, Some(Player::replay(picks.to_vec()).window(from, to)));
    let mut samples = vec![];
    for &k in &ks {
        let (t, cands) = seen[k];
        let lots = cands as usize;
        let chosen_lot = (picks[k] as usize).min(lots - 1);
        // the lots tried: all, or the first of each kind with the policy's pick standing for its own
        let tried: Vec<usize> = match kinds.get(&(k as u64)).filter(|_| by_kind) {
            Some(kd) => {
                let mut first_of: Vec<Option<usize>> = vec![None; kd.iter().map(|&x| x as usize + 1).max().unwrap_or(0)];
                for (i, &x) in kd.iter().enumerate() {
                    first_of[x as usize].get_or_insert(i);
                }
                first_of[kd[chosen_lot] as usize] = Some(chosen_lot);
                let mut v: Vec<usize> = first_of.into_iter().flatten().collect();
                let m = cap.unwrap_or(0);
                if m > v.len() {
                    let mut taken = vec![false; lots];
                    v.iter().for_each(|&i| taken[i] = true);
                    let rest: Vec<usize> = (0..lots).filter(|&i| !taken[i]).collect();
                    let add = (m - v.len()).min(rest.len());
                    v.extend((0..add).map(|j| rest[((j as f64 + 0.5) * rest.len() as f64 / add as f64) as usize]));
                }
                v.sort_unstable();
                v.dedup();
                v
            }
            None => (0..lots).collect(),
        };
        main.advance(t - 1e-6);
        let base = main.value();
        let player = main.player().unwrap().clone();
        // each lot on its own copy; the copies spread over at most WORKERS threads, the values kept in `tried` order
        let per = tried.len().div_ceil(WORKERS).max(1);
        let mut values = vec![0.0; tried.len()];
        std::thread::scope(|sc| {
            let player = &player;
            let tried = &tried;
            for (w, chunk) in values.chunks_mut(per).enumerate() {
                let own = Copied(main.clone());
                sc.spawn(move || {
                    let own = own;
                    for (j, v) in chunk.iter_mut().enumerate() {
                        let mut b = own.0.clone();
                        b.set_player(Some(player.branch(&picks[..k], k as u64, tried[w * per + j])));
                        b.advance(t + horizon);
                        *v = b.value() - base;
                    }
                });
            }
        });
        let chosen = tried.iter().position(|&i| i == chosen_lot).unwrap_or(0);
        let best = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        samples.push(Sample { k: k as u64, t, lots, regret: best - values[chosen], tried, values, chosen });
    }
    let mean_regret = if samples.is_empty() { 0.0 } else { samples.iter().map(|s| s.regret).sum::<f64>() / samples.len() as f64 };
    Audit { samples, mean_regret, horizon }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Shift {
    pub start: f64,
    /// each library rule's gain over the shift, in library order, and the kept one
    pub gains: Vec<f64>,
    pub chosen: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Switching {
    pub shifts: Vec<Shift>,
    pub value_gain: f64,
    pub sequence: Vec<Policy>,
}

/// D: today's rule until `from`, then shift by shift (`shift` minutes) the best of `library` kept, until `to`.
pub fn switching(shop: &Shop, seed: u64, from: f64, to: f64, shift: f64, library: &[Policy]) -> Switching {
    let opts = RunOptions { seed, until: Some(to), record: false };
    let mut main = Stepper::new(shop, &opts, Some(Player::rule(shop, Policy::Today, seed).window(from, to)));
    main.advance(from);
    let v0 = main.value();
    let mut shifts = vec![];
    let mut sequence = vec![];
    let mut start = from;
    while start < to - 1e-9 {
        let end = (start + shift).min(to);
        let v = main.value();
        let mut branches: Vec<Stepper> = library
            .iter()
            .map(|&r| {
                let mut b = main.clone();
                b.player_mut().unwrap().switch(shop, r, seed);
                b.advance(end);
                b
            })
            .collect();
        let gains: Vec<f64> = branches.iter().map(|b| b.value() - v).collect();
        let mut chosen = 0;
        for (i, g) in gains.iter().enumerate() {
            if *g > gains[chosen] {
                chosen = i;
            }
        }
        main = branches.swap_remove(chosen);
        sequence.push(library[chosen]);
        shifts.push(Shift { start, gains, chosen });
        start = end;
    }
    Switching { value_gain: main.value() - v0, shifts, sequence }
}
