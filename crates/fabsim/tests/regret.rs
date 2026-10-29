//! Regret options B and D (docs/LONG-RESCORE.md). Written before the code. On the SMT2020 model's rules, with the toy
//! shop for speed.
//!
//! B, the foresight audit: at sampled picks of a policy's own run, every lot the tool could have taken is tried on a
//! copy of the fab with the same luck ahead, today's rule playing on, for a horizon; the best of them is the pick with
//! foresight, and the policy's regret at that pick is the best's gain minus its own.
//! D, rule switching in hindsight: shift by shift, every rule of a library is tried on a copy and the best kept.

mod common;

use fabsim::engine::{Player, RunOptions, Stepper};
use fabsim::policy::Policy;
use fabsim::regret::{audit, switching};
use fabsim::shop::Shop;

fn toy() -> Shop {
    Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap()
}

const FROM: f64 = 1440.0;
const TO: f64 = 3.0 * 1440.0;

fn picks_of(shop: &Shop, p: Policy, seed: u64) -> Vec<u32> {
    let mut s = Stepper::new(shop, &RunOptions { seed, until: Some(TO), record: false }, Some(Player::rule(shop, p, seed).window(FROM, TO)));
    s.advance(TO);
    s.picks().to_vec()
}

#[test]
fn the_audit_tries_every_lot_at_sampled_picks_and_regret_is_never_negative() {
    let shop = toy();
    let picks = picks_of(&shop, Policy::Fifo, 2);
    let a = audit(&shop, 2, FROM, TO, &picks, 12, 240.0);
    assert_eq!(a.samples.len(), 12);
    for s in &a.samples {
        assert!(s.values.len() >= 2, "a real choice");
        assert!(s.chosen < s.values.len());
        let best = s.values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        assert!((s.regret - (best - s.values[s.chosen])).abs() < 1e-9);
        assert!(s.regret >= 0.0);
        assert!(s.t >= FROM && s.t <= TO);
    }
    assert!((a.mean_regret - a.samples.iter().map(|s| s.regret).sum::<f64>() / 12.0).abs() < 1e-9);
    // the same inputs, the same audit
    let b = audit(&shop, 2, FROM, TO, &picks, 12, 240.0);
    assert_eq!(a.samples.iter().map(|s| s.regret).collect::<Vec<_>>(), b.samples.iter().map(|s| s.regret).collect::<Vec<_>>());
}

#[test]
fn switching_keeps_the_best_rule_of_each_shift() {
    let shop = toy();
    let lib = [Policy::Today, Policy::Fifo, Policy::Spt, Policy::CriticalRatio];
    let d = switching(&shop, 3, FROM, TO, 360.0, &lib);
    assert_eq!(d.shifts.len(), 8, "two days of six-hour shifts");
    for sh in &d.shifts {
        let best = sh.gains.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        assert_eq!(sh.gains.len(), lib.len());
        assert!((sh.gains[sh.chosen] - best).abs() < 1e-9, "the kept rule is the shift's best");
    }
    let total: f64 = d.shifts.iter().map(|s| s.gains[s.chosen]).sum();
    assert!((d.value_gain - total).abs() < 1e-6, "the path's gain is its shifts' gains");
    // with today's rule alone, switching is today's run
    let only = switching(&shop, 3, FROM, TO, 360.0, &[Policy::Today]);
    let mut s = Stepper::new(&shop, &RunOptions { seed: 3, until: Some(TO), record: false }, None);
    s.advance(FROM);
    let v0 = s.value();
    s.advance(TO);
    assert!((only.value_gain - (s.value() - v0)).abs() < 1e-6);
}

#[test]
fn the_audit_by_kind_tries_one_lot_of_each_kind_and_never_says_more_than_the_full_audit() {
    // lots of one route, step, size, priority and batch shape are one kind; the policy's own pick stands for its kind
    use fabsim::regret::audit_by_kind;
    let shop = toy();
    let picks = picks_of(&shop, Policy::Fifo, 2);
    let full = audit(&shop, 2, FROM, TO, &picks, 12, 240.0);
    let kind = audit_by_kind(&shop, 2, FROM, TO, &picks, 12, 240.0);
    assert_eq!(kind.samples.len(), full.samples.len());
    for (f, k) in full.samples.iter().zip(&kind.samples) {
        assert_eq!((f.k, f.t), (k.k, k.t), "the same picks are sampled");
        assert_eq!(k.lots, f.values.len(), "the lots there were to choose from");
        assert!(k.values.len() <= f.values.len() && !k.values.is_empty());
        assert!(k.regret >= 0.0 && k.regret <= f.regret + 1e-9, "fewer tries never find more regret");
        if k.values.len() == f.values.len() {
            assert!((k.regret - f.regret).abs() < 1e-9, "every lot its own kind: the full audit");
        }
    }
}
