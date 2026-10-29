//! Dials: what-if knobs applied to a copy of a shop (docs/LEAN-LONG.md).

mod common;

use fabsim::dials::{Dials, Outage};
use fabsim::engine::{run, RunOptions};
use fabsim::shop::Shop;

const SHOP: &str = "fabgym-shop 1
transport\t5.0\t10.0
group\tA\t2\t1.0\t1.0\t-\t900.0\t45.0
group\tB\t1\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t30.0\t3.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t20.0\t0.0\t-\t-\t-\t-\t-\t-\t0\t0.6\t-\t-
release\tr\t25\t10.0\t60.0\t0.0\t-\tN
release\tr\t25\t20.0\t600.0\t30.0\t-\tH
";

fn shop() -> Shop {
    Shop::parse(SHOP).unwrap()
}

#[test]
fn identity_leaves_the_shop_unchanged() {
    let s = shop();
    assert_eq!(Dials::default().apply(&s).unwrap().to_text(), s.to_text());
    let toy = Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap();
    assert_eq!(Dials::default().apply(&toy).unwrap().to_text(), toy.to_text());
}

#[test]
fn breakdowns_divide_time_to_failure_only() {
    let s = Dials { breakdowns: 2.0, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(s.groups[0].breakdown, Some((450.0, 45.0)));
    assert_eq!(s.groups[1].breakdown, None);
    let none = Dials { breakdowns: 0.0, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(none.groups[0].breakdown, None);
}

#[test]
fn repair_multiplies_time_to_repair() {
    let s = Dials { repair: 1.5, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(s.groups[0].breakdown, Some((900.0, 67.5)));
}

#[test]
fn demand_scales_every_release_stream() {
    let s = Dials { demand: 2.0, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(s.releases[0].every, 30.0);
    assert_eq!(s.releases[1].every, 300.0);
}

#[test]
fn hot_scales_only_streams_above_the_lowest_priority() {
    let s = Dials { hot: 3.0, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(s.releases[0].every, 60.0);
    assert_eq!(s.releases[1].every, 200.0);
    let none = Dials { hot: 0.0, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(none.releases.len(), 1);
    assert_eq!(none.releases[0].prefix, "N");
}

#[test]
fn rework_scales_probability_up_to_one() {
    let s = Dials { rework: 1.5, ..Dials::default() }.apply(&shop()).unwrap();
    let r = s.routes[0].steps[1].rework.unwrap();
    assert!((r.1 - 0.9).abs() < 1e-12, "{r:?}");
    let s = Dials { rework: 2.0, ..Dials::default() }.apply(&shop()).unwrap();
    assert_eq!(s.routes[0].steps[1].rework, Some((0, 1.0)));
}

#[test]
fn cap_and_outage() {
    let d = Dials {
        cap: Some(5),
        outage: Some(Outage { group: "B".into(), from: 60.0, hours: 2.0 }),
        ..Dials::default()
    };
    let s = d.apply(&shop()).unwrap();
    assert_eq!(s.cap, Some(5));
    assert_eq!(s.groups[1].down, vec![(60.0, 180.0)]);
    let bad = Dials { outage: Some(Outage { group: "Z".into(), from: 0.0, hours: 1.0 }), ..Dials::default() };
    assert!(bad.apply(&shop()).is_err());
}

#[test]
fn negative_dials_are_refused() {
    for d in [
        Dials { breakdowns: -1.0, ..Dials::default() },
        Dials { repair: 0.0, ..Dials::default() },
        Dials { demand: 0.0, ..Dials::default() },
        Dials { hot: -0.5, ..Dials::default() },
        Dials { rework: -1.0, ..Dials::default() },
        Dials { cap: Some(0), ..Dials::default() },
    ] {
        assert!(d.apply(&shop()).is_err(), "{d:?}");
    }
}

#[test]
fn a_dialled_shop_runs_the_same_on_the_same_seed() {
    let s = Dials { breakdowns: 1.5, demand: 1.2, ..Dials::default() }.apply(&shop()).unwrap();
    let o = RunOptions { seed: 7, until: Some(3000.0), record: true };
    assert_eq!(run(&s, &o, None).log_text(), run(&s, &o, None).log_text());
}

// Defect holds as a dial (docs/RL-DEFECTS.md; the founder, 29 Oct): None leaves the shop's own, 0 switches holds
// off, k > 0 sets k times the assumed central lengths (tool 120 min, lookback 240 min, lots 60 min).
#[test]
fn defect_holds_dial() {
    use fabsim::dials::DEFECTS_CENTRAL;
    use fabsim::shop::Defects;
    assert_eq!(DEFECTS_CENTRAL, (120.0, 240.0, 60.0));
    let s = shop();
    assert_eq!(s.defects, None);
    assert_eq!(Dials { defects: None, ..Dials::default() }.apply(&s).unwrap().to_text(), s.to_text());
    let on = Dials { defects: Some(1.0), ..Dials::default() }.apply(&s).unwrap();
    assert_eq!(on.defects, Some(Defects { hold_tool_minutes: 120.0, lookback_minutes: 240.0, hold_lot_minutes: 60.0 }));
    let twice = Dials { defects: Some(2.0), ..Dials::default() }.apply(&s).unwrap();
    assert_eq!(twice.defects, Some(Defects { hold_tool_minutes: 240.0, lookback_minutes: 480.0, hold_lot_minutes: 120.0 }));
    assert_eq!(Dials { defects: Some(0.0), ..Dials::default() }.apply(&on).unwrap().defects, None);
    assert!(Dials { defects: Some(-1.0), ..Dials::default() }.apply(&s).is_err());
    // the dialled shop runs the same on the same seed
    let r = |sh: &Shop| run(sh, &RunOptions { seed: 3, until: Some(5000.0), record: true }, None).log_text();
    assert_eq!(r(&twice), r(&twice));
}
