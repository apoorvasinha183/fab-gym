//! Our numbers beside the published testbed's (docs/DOUBLE-CHECK.md, part 4). Written before the code. Each published
//! figure names its source and page; our raw processing times are the exact chain's (part 1) and lie within 1% of the
//! published theoretical cycle times; the 6-month runs behind the comparison are written by `fabsim published`. From
//! the SMT2020 testbed; not a real fab.

mod common;

use fabsim::routes::analyse;

fn json(rel: &str) -> serde_json::Value {
    serde_json::from_str(&common::read(rel)).unwrap_or_else(|e| panic!("{rel}: {e}"))
}

fn figure(f: &serde_json::Value, key: &str) -> f64 {
    f["figures"].as_array().unwrap().iter().find(|x| x["key"] == key).unwrap_or_else(|| panic!("no figure {key}"))["value"].as_f64().unwrap()
}

#[test]
fn dc9_every_published_figure_names_its_source() {
    let f = json("results/double-check/published-figures.json");
    let sources = f["sources"].as_object().unwrap();
    for x in f["figures"].as_array().unwrap() {
        assert!(sources.contains_key(x["source"].as_str().unwrap()), "{x}: a known source");
        assert!(x["where"].as_str().is_some_and(|w| w.contains("p.")), "{x}: the page it was read on");
        assert!(x["value"].as_f64().is_some_and(f64::is_finite), "{x}: a number");
    }
}

#[test]
fn dc9_our_raw_processing_times_are_the_chains_and_near_the_published() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let f = json("results/double-check/published-figures.json");
    let ours = json("results/double-check/ours.json");
    for c in analyse(&shop) {
        let days = c.expected_minutes / 1440.0;
        let written = ours["raw_days"][&c.route].as_f64().unwrap_or_else(|| panic!("ours.json has {}", c.route));
        assert!((written - days).abs() < 0.005, "{}: ours.json says {written}, the chain {days}", c.route);
        let published = figure(&f, &format!("theoretical_{}", c.route));
        assert!(((days - published) / published).abs() < 0.01, "{}: {days:.2} days against the published {published}", c.route);
    }
    // the runs behind the comparison: today's rule, 6 months, 10 runs, per lot type
    for k in ["Lot_3", "Lot_4", "HotLot_3", "HotLot_4", "SuperHotLot_3"] {
        let t = &ours["cycle_days"][k];
        assert!(t["mean"].as_f64().is_some_and(|m| m > 0.0) && t["runs"].as_u64() == Some(10), "{k}: {t}");
    }
    assert_eq!(ours["days"].as_f64(), Some(180.0));
}
