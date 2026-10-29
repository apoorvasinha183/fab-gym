//! A run that can be paused, copied and continued (docs/LONG-RESCORE.md, regret options B and D). Written before the
//! code. On the SMT2020 model's rules, with the toy shops for speed.

mod common;

use fabsim::engine::{run, Player, RunOptions, Stepper};
use fabsim::policy::{run_with, Policy};
use fabsim::shop::Shop;

fn toy() -> Shop {
    Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap()
}

const UNTIL: f64 = 4.0 * 1440.0;

#[test]
fn a_run_in_steps_is_the_same_run() {
    let shop = toy();
    for seed in [0u64, 5] {
        let opts = RunOptions { seed, until: Some(UNTIL), record: true };
        let mut s = Stepper::new(&shop, &opts, None);
        let mut t = 0.0;
        while t < UNTIL {
            t += 97.0;
            s.advance(t.min(UNTIL));
        }
        assert_eq!(s.finish().log_text(), run(&shop, &opts, None).log_text(), "seed {seed}");
    }
}

#[test]
fn a_copy_goes_on_as_the_original() {
    let shop = toy();
    let opts = RunOptions { seed: 3, until: Some(UNTIL), record: true };
    let mut s = Stepper::new(&shop, &opts, None);
    s.advance(1.5 * 1440.0);
    let mut c = s.clone();
    s.advance(UNTIL);
    c.advance(UNTIL);
    assert_eq!(s.finish().log_text(), c.finish().log_text());
}

#[test]
fn a_built_in_rule_plays_as_run_with() {
    let shop = toy();
    for p in [Policy::Fifo, Policy::Spt, Policy::CriticalRatio, Policy::Random] {
        let opts = RunOptions { seed: 2, until: Some(UNTIL), record: true };
        let mut s = Stepper::new(&shop, &opts, Some(Player::rule(&shop, p, 2)));
        s.advance(UNTIL);
        assert_eq!(s.finish().log_text(), run_with(&shop, &opts, p).log_text(), "{}", p.name());
    }
}

#[test]
fn recorded_picks_replay_the_run_and_a_forced_pick_changes_it() {
    let shop = toy();
    let opts = RunOptions { seed: 4, until: Some(UNTIL), record: true };
    // FIFO in a window, today's rule outside it: the picks it makes in the window are recorded
    let mut a = Stepper::new(&shop, &opts, Some(Player::rule(&shop, Policy::Fifo, 4).window(1440.0, 3.0 * 1440.0)));
    a.advance(UNTIL);
    let picks = a.picks().to_vec();
    assert!(picks.len() > 20, "{} picks recorded", picks.len());
    let log_a = a.finish().log_text();
    // replayed without FIFO, the same run
    let mut b = Stepper::new(&shop, &opts, Some(Player::replay(picks.clone()).window(1440.0, 3.0 * 1440.0)));
    b.advance(UNTIL);
    assert_eq!(b.finish().log_text(), log_a);
    // a pick forced to what was picked anyway changes nothing; forced to another lot, the run differs
    let k = picks.len() / 2;
    let mut same = Stepper::new(&shop, &opts, Some(Player::replay(picks.clone()).force(k as u64, picks[k] as usize).window(1440.0, 3.0 * 1440.0)));
    same.advance(UNTIL);
    assert_eq!(same.finish().log_text(), log_a);
    let mut other = Stepper::new(&shop, &opts, Some(Player::replay(picks.clone()).force(k as u64, if picks[k] == 0 { 1 } else { 0 }).window(1440.0, 3.0 * 1440.0)));
    other.advance(UNTIL);
    assert_ne!(other.finish().log_text(), log_a, "the forced pick moved the run");
}

#[test]
fn the_value_so_far_is_the_rewards_measure() {
    let shop = toy();
    let opts = RunOptions { seed: 1, until: Some(UNTIL), record: false };
    let mut s = Stepper::new(&shop, &opts, None);
    s.advance(2.0 * 1440.0);
    let (finished, wait_lot_minutes) = s.totals();
    assert!(finished > 0 && wait_lot_minutes > 0.0);
    assert!((s.value() - (finished as f64 - 0.01 * wait_lot_minutes / 60.0)).abs() < 1e-9);
}
