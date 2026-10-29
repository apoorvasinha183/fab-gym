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

#[derive(Clone, Debug, PartialEq)]
pub struct Sample {
    /// which counted pick of the window, and when
    pub k: u64,
    pub t: f64,
    /// each lot's gain over the horizon, in candidate order; the policy's pick; best minus the policy's
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

/// B: `picks` are the policy's counted picks in the window [from, to] on `seed`; `n` evenly spaced of them are audited.
pub fn audit(shop: &Shop, seed: u64, from: f64, to: f64, picks: &[u32], n: usize, horizon: f64) -> Audit {
    let opts = RunOptions { seed, until: Some(to + horizon), record: false };
    // a first pass finds when each pick comes and how many lots it chose from
    let mut first = Stepper::new(shop, &opts, Some(Player::replay(picks.to_vec()).window(from, to)));
    first.advance(to);
    let seen: Vec<(f64, u32)> = first.player().map(|p| p.seen().to_vec()).unwrap_or_default();
    let len = seen.len().min(picks.len());
    let n = n.min(len);
    let ks: Vec<usize> = (0..n).map(|i| ((i as f64 + 0.5) * len as f64 / n as f64) as usize).collect();
    let mut main = Stepper::new(shop, &opts, Some(Player::replay(picks.to_vec()).window(from, to)));
    let mut samples = vec![];
    for &k in &ks {
        let (t, cands) = seen[k];
        main.advance(t - 1e-6);
        let base = main.value();
        let player = main.player().unwrap().clone();
        let values: Vec<f64> = (0..cands as usize)
            .map(|c| {
                let mut b = main.clone();
                b.set_player(Some(player.branch(&picks[..k], k as u64, c)));
                b.advance(t + horizon);
                b.value() - base
            })
            .collect();
        let chosen = (picks[k] as usize).min(values.len() - 1);
        let best = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        samples.push(Sample { k: k as u64, t, regret: best - values[chosen], values, chosen });
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
