//! Scores over a window, and a grid of dials on paired seeds (docs/LEAN-LONG.md).

mod common;

use fabsim::dials::Dials;
use fabsim::engine::{run, RunOptions};
use fabsim::shop::Shop;
use fabsim::sweep::{paired_vs, run_grid, Config};
use fabsim::window::{score, with_probes, Window};

fn toy(name: &str) -> Shop {
    Shop::parse(&common::read(&format!("golden/toy/{name}.shop.txt"))).unwrap()
}

#[test]
fn little_on_the_tiny_shop() {
    // two lots of 25 at t = 0, one tool, 10 minutes each: done at 10 and 20
    let w = Window { from: 0.0, to: 30.0 };
    let s = with_probes(&toy("tiny"), &w);
    let r = run(&s, &RunOptions { seed: 0, until: Some(30.0), record: false }, None);
    let sc = score(&r, &w).unwrap();
    assert!((sc.lots_per_day - 2.0 * 1440.0 / 30.0).abs() < 1e-9, "{sc:?}");
    assert!((sc.wafers_per_day - 50.0 * 1440.0 / 30.0).abs() < 1e-9, "{sc:?}");
    assert!((sc.mean_wip - 1.0).abs() < 1e-9, "{sc:?}");
    assert!((sc.cycle_days - 15.0 / 1440.0).abs() < 1e-12, "{sc:?}");
    assert_eq!(sc.hot_lots, 0);
    assert!(sc.hot_cycle_days.is_none());
}

#[test]
fn a_window_needs_its_probes() {
    let w = Window { from: 0.0, to: 30.0 };
    let r = run(&toy("tiny"), &RunOptions { seed: 0, until: Some(30.0), record: false }, None);
    assert!(score(&r, &w).is_err());
    assert!(Window { from: 30.0, to: 30.0 }.check().is_err());
}

#[test]
fn with_probes_keeps_existing_probes_sorted() {
    let s = with_probes(&toy("capped"), &Window { from: 100.0, to: 2000.0 });
    let mut sorted = s.probes.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    sorted.dedup();
    assert_eq!(s.probes, sorted);
    assert!(s.probes.contains(&100.0) && s.probes.contains(&2000.0) && s.probes.contains(&1440.0));
}

#[test]
fn the_grid_does_not_depend_on_threads() {
    let configs = vec![
        Config { label: "base".into(), dials: Dials::default() },
        Config { label: "cap".into(), dials: Dials { cap: Some(6), ..Dials::default() } },
        Config { label: "breakdowns".into(), dials: Dials { breakdowns: 2.0, ..Dials::default() } },
    ];
    let w = Window { from: 600.0, to: 2880.0 };
    let shop = toy("mixed");
    let one = run_grid(&shop, &configs, &[1, 2, 3, 4], 2880.0, &w, 1).unwrap();
    let three = run_grid(&shop, &configs, &[1, 2, 3, 4], 2880.0, &w, 3).unwrap();
    assert_eq!(one.len(), 12);
    let key = |rows: &[fabsim::sweep::Row]| -> Vec<String> {
        rows.iter().map(|r| format!("{} {} {:?}", r.config, r.seed, r.score)).collect()
    };
    assert_eq!(key(&one), key(&three));
    assert_eq!((one[0].config, one[0].seed), (0, 1));
    assert_eq!((one[11].config, one[11].seed), (2, 4));
}

#[test]
fn paired_vs_matches_the_paired_interval() {
    let configs = vec![
        Config { label: "base".into(), dials: Dials::default() },
        Config { label: "breakdowns".into(), dials: Dials { breakdowns: 2.0, ..Dials::default() } },
    ];
    let w = Window { from: 600.0, to: 2880.0 };
    let rows = run_grid(&toy("mixed"), &configs, &[1, 2, 3, 4, 5], 2880.0, &w, 2).unwrap();
    let f = |s: &fabsim::window::WindowScore| s.lots_per_day;
    let iv = paired_vs(&rows, 0, 1, f, 0.05);
    let base: Vec<f64> = rows.iter().filter(|r| r.config == 0).map(|r| f(&r.score)).collect();
    let cand: Vec<f64> = rows.iter().filter(|r| r.config == 1).map(|r| f(&r.score)).collect();
    let want = fabsim::uq::paired(&base, &cand, 0.05);
    assert_eq!((iv.mean, iv.lo, iv.hi, iv.n), (want.mean, want.lo, want.hi, want.n));
}

#[test]
fn smt2020_window_is_sane() {
    let Some(dir) = common::smt2020_dir() else { return };
    let w = Window { from: 1440.0 * 10.0, to: 1440.0 * 20.0 };
    let s = with_probes(&fabsim::smt2020::load(&dir).unwrap(), &w);
    let r = run(&s, &RunOptions { seed: 1000, until: Some(w.to), record: false }, None);
    let sc = score(&r, &w).unwrap();
    assert!(sc.lots_per_day > 30.0 && sc.lots_per_day < 80.0, "{sc:?}");
    assert!((sc.wafers_per_day - 25.0 * sc.lots_per_day).abs() < 1e-6, "{sc:?}");
    assert!(sc.cycle_days > 20.0 && sc.cycle_days < 90.0, "{sc:?}");
    // Little's law holds by construction over the window
    assert!((sc.cycle_days * sc.lots_per_day - sc.mean_wip).abs() < 1e-6 * sc.mean_wip, "{sc:?}");
}
