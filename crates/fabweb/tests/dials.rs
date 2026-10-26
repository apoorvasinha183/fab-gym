//! The browser glue: dials and the outage applied in order, and the quick paired-seed score.

use fabsim::dials::Dials;
use fabsim::engine::{run, RunOptions};
use fabsim::shop::Shop;
use fabweb::{prepare, quick, quick_json, Policy};

fn toy() -> Shop {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../golden/toy/mixed.shop.txt");
    Shop::parse(&std::fs::read_to_string(p).unwrap()).unwrap()
}

#[test]
fn defaults_leave_the_shop_alone() {
    let s = toy();
    assert_eq!(prepare(&s, &Dials::default(), -1, 0.0, 0.0).unwrap(), s);
}

#[test]
fn dials_then_the_outage() {
    let s = toy();
    let d = Dials { breakdowns: 2.0, cap: Some(4), ..Dials::default() };
    let p = prepare(&s, &d, 2, 60.0, 3.0).unwrap();
    let want = d.apply(&s).unwrap();
    assert_eq!(p.groups[0].breakdown, want.groups[0].breakdown);
    assert_eq!(p.cap, Some(4));
    let mut down = s.groups[2].down.clone();
    down.push((60.0, 240.0));
    assert_eq!(p.groups[2].down, down);
    assert!(prepare(&s, &Dials { demand: 0.0, ..Dials::default() }, -1, 0.0, 0.0).is_err());
    assert!(prepare(&s, &Dials::default(), 99, 0.0, 3.0).is_err());
}

#[test]
fn quick_matches_a_full_run_and_repeats() {
    let s = toy();
    let a = quick(&s, 3, 2.0, Policy::Today);
    let b = quick(&s, 3, 2.0, Policy::Today);
    assert_eq!(a, b);
    let full = run(&s, &RunOptions { seed: 3, until: Some(2880.0), record: true }, None);
    assert_eq!(a.moves, full.moves);
    assert_eq!(a.finished, full.finished);
    assert_eq!(a.breaches, full.breaches.len());
    assert!((a.wait_lot_hours - full.wait_lot_minutes / 60.0).abs() < 1e-9);
    let wafers: i64 = full.lots.iter().filter(|l| l.done.is_some()).map(|l| l.size).sum();
    assert_eq!(a.wafers_out, wafers);
}

#[test]
fn quick_json_has_every_score() {
    let j = quick_json(&quick(&toy(), 1, 1.0, Policy::Fifo));
    for k in ["\"moves\":", "\"finished\":", "\"wafers_out\":", "\"breaches\":", "\"wait_lot_hours\":", "\"waiting\":"] {
        assert!(j.contains(k), "{k} missing from {j}");
    }
}

#[test]
fn t_quantile_is_exported() {
    assert!((fabweb::fg_t(0.975, 9.0) - 2.2621571627982049992).abs() < 1e-9);
}
