//! The browser simulator with the fleet (docs/LIVE-REAL.md). Written before the code. On the SMT2020 model with a
//! gigafab-style layout of our own design.

use fabsim::engine::RunOptions;
use fabsim::shop::{Fleet, Shop};
use std::path::Path;

fn real() -> Option<Shop> {
    let p = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../data/layout-real-dd/optimised.shop.txt");
    let mut s = Shop::parse(&std::fs::read_to_string(p).ok()?).unwrap();
    s.fleet = Some(Fleet { vehicles: 160, gap: 3.0, hoist: 1.0, ports: 2, cross: 60.0, controller: "nearest".into() });
    Some(s)
}

#[test]
fn a_run_of_the_real_building_gives_the_fleet_as_flat_arrays() {
    let Some(s) = real() else { return };
    let r = fabweb::run_policy(&s, &RunOptions { seed: 0, until: Some(720.0), record: true }, fabweb::Policy::Today);
    let (entries, hoists) = fabweb::fleet_arrays(&r);
    assert!(!entries.is_empty() && entries.len() % 5 == 0, "[vehicle, stretch, in, out, loaded] records");
    assert!(!hoists.is_empty() && hoists.len() % 6 == 0, "[vehicle, node, lot, up, start, end] records");
    let t = fabsim::track::Track::from_shop(&s);
    for h in hoists.chunks(6) {
        assert!((h[1] as usize) < t.nodes().len());
        assert!(h[4] <= h[5]);
    }
    for e in entries.chunks(5) {
        assert!((e[1] as usize) < t.edges().len());
        assert!(e[3] < 0.0 || e[3] >= e[2], "out is -1 while still on the stretch");
    }
}

#[test]
fn a_shop_without_a_fleet_gives_none() {
    let Some(mut s) = real() else { return };
    s.fleet = None;
    let r = fabweb::run_policy(&s, &RunOptions { seed: 0, until: Some(120.0), record: true }, fabweb::Policy::Today);
    let (entries, hoists) = fabweb::fleet_arrays(&r);
    assert!(entries.is_empty() && hoists.is_empty());
}
