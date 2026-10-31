//! The supervisor, a toy experiment (docs/SUPERVISOR-TOY.md): copies with fresh luck, a cap set mid-run, overrides on a
//! stepper, and the supervisor's looks. Written before the code. On the toy shops; not a real fab.

mod common;

use fabsim::engine::{run_with, Player, RunOptions, Stepper};
use fabsim::overrides::Overrides;
use fabsim::policy::Policy;
use fabsim::shop::Shop;
use fabsim::supervise::{self, Plan, Setting};

fn toy() -> Shop {
    Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap()
}

const DAY: f64 = 1440.0;

#[test]
fn sv1_a_copy_advanced_alongside_ends_the_same() {
    let shop = toy();
    let opts = RunOptions { seed: 4, until: Some(4.0 * DAY), record: true };
    let mut s = Stepper::new(&shop, &opts, Some(Player::rule(&shop, Policy::Today, 4)));
    s.advance(DAY);
    let mut c = s.clone();
    s.advance(4.0 * DAY);
    c.advance(4.0 * DAY);
    assert_eq!(s.finish().log_text(), c.finish().log_text());
}

#[test]
fn sv2_fresh_luck_moves_pending_breakdowns_and_leaves_the_original() {
    let shop = toy();
    let opts = RunOptions { seed: 1, until: Some(5.0 * DAY), record: true };
    let mut s = Stepper::new(&shop, &opts, Some(Player::rule(&shop, Policy::Today, 1)));
    s.advance(DAY);
    let before = s.next_breakdowns();
    assert!(!before.is_empty(), "the toy has random breakdowns pending");
    let mut a = s.clone();
    a.fresh_luck(77);
    assert_ne!(a.next_breakdowns(), before, "fresh luck redraws the pending breakdowns");
    assert_eq!(s.next_breakdowns(), before, "the original is untouched");
    let mut b = s.clone();
    b.fresh_luck(77);
    a.advance(5.0 * DAY);
    b.advance(5.0 * DAY);
    s.advance(5.0 * DAY);
    let (la, lb, ls) = (a.finish().log_text(), b.finish().log_text(), s.finish().log_text());
    assert_eq!(la, lb, "the same fresh seed, the same copy");
    assert_ne!(la, ls, "fresh luck changes what happens next");
}

#[test]
fn sv3_a_cap_set_mid_run_holds_new_releases() {
    let shop = toy();
    let opts = RunOptions { seed: 2, until: Some(6.0 * DAY), record: false };
    let mut s = Stepper::new(&shop, &opts, Some(Player::rule(&shop, Policy::Today, 2)));
    s.advance(2.0 * DAY);
    let at = s.lots_inside();
    let cap = 3;
    s.set_cap(Some(cap));
    let mut most_after = 0;
    let mut t = 2.0 * DAY;
    while t < 3.0 * DAY {
        t += 30.0;
        s.advance(t);
        most_after = most_after.max(s.lots_inside());
    }
    assert!(most_after <= at.max(cap), "lots inside reached {most_after}, the cap {cap}, {at} at the change");
    s.set_cap(None);
    s.advance(6.0 * DAY);
}

#[test]
fn sv4_a_stepper_with_overrides_is_the_ordinary_run_with_them() {
    let shop = toy();
    let ov = Overrides::parse(r#"{"fabgym-overrides": 1, "groups": {"Etch": {"breakdowns": {"kind": "by_wafers", "every": 400, "minutes": [30, 60]}}}}"#, &shop).unwrap();
    let opts = RunOptions { seed: 6, until: Some(4.0 * DAY), record: true };
    let mut s = Stepper::with_overrides(&shop, &opts, None, &ov);
    s.advance(4.0 * DAY);
    assert_eq!(s.finish().log_text(), run_with(&shop, &opts, None, &ov).log_text());
}

fn plan() -> Plan {
    Plan { warmup: DAY, window: 2.0 * DAY, every: DAY, horizon: 2.0 * DAY, copies: 2 }
}

#[test]
fn sv5_the_simulator_arm_is_repeatable_and_records_every_look() {
    let shop = toy();
    let ov = Overrides::default();
    let grid = supervise::grid(&[None, Some(4), Some(8)]);
    let all = |_: &supervise::LookState, g: &[Setting]| g.to_vec();
    let a = supervise::run(&shop, &ov, 3, &plan(), &grid, &mut |s, g| all(s, g));
    let b = supervise::run(&shop, &ov, 3, &plan(), &grid, &mut |s, g| all(s, g));
    assert_eq!(a.looks.len(), 2);
    assert_eq!(a.looks.iter().map(|l| l.chosen).collect::<Vec<_>>(), b.looks.iter().map(|l| l.chosen).collect::<Vec<_>>());
    for l in &a.looks {
        assert_eq!(l.tried.len(), grid.len(), "every setting tried");
        let best = l.tried.iter().map(|x| x.1).fold(f64::MIN, f64::max);
        assert_eq!(l.tried.iter().find(|x| x.0 == l.chosen).unwrap().1, best, "the best is chosen");
    }
    assert_eq!(a.lots_finished, b.lots_finished);
    assert!(a.wafers_per_day > 0.0 && a.cycle_days > 0.0);
}

#[test]
fn sv6_with_a_proposer_only_its_settings_and_the_current_one_are_tried() {
    let shop = toy();
    let ov = Overrides::default();
    let grid = supervise::grid(&[None, Some(4), Some(8)]);
    let picks = [Setting { rule: Policy::Fifo, cap: Some(4) }, Setting { rule: Policy::Spt, cap: None }];
    let out = supervise::run(&shop, &ov, 5, &plan(), &grid, &mut |_, _| picks.to_vec());
    for l in &out.looks {
        let tried: Vec<Setting> = l.tried.iter().map(|x| x.0).collect();
        assert!(tried.iter().all(|s| picks.contains(s) || *s == l.current), "tried {tried:?}");
        assert!(tried.contains(&l.current), "the current setting is always tried");
        assert!(tried.contains(&l.chosen));
    }
}

#[test]
fn sv7_the_lines_a_look_reports_are_real_and_never_more_than_the_lots_inside() {
    let shop = toy();
    let opts = RunOptions { seed: 2, until: Some(4.0 * DAY), record: false };
    let mut s = Stepper::new(&shop, &opts, Some(Player::rule(&shop, Policy::Today, 2)));
    let mut seen = 0;
    for h in 1..=48 {
        s.advance(h as f64 * 120.0);
        let waiting: i64 = s.groups_now().iter().map(|g| g.3).sum();
        assert!(waiting <= s.lots_inside(), "{waiting} waiting but {} inside", s.lots_inside());
        seen += waiting;
    }
    assert!(seen > 0, "lines are seen at some look");
}
