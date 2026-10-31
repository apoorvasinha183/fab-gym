//! Storage made real (docs/BUILD-CONTROLS.md, part 3, ST1 to ST4). Written before the code. The fixture is Build's own
//! Free build file for the teaching fab (`tests/data/teach-free.fab.txt`, written by `fabText`); on a teaching fab of
//! our own; not a real fab.

use fabsim::engine::{run, RunOptions, RunResult};
use fabsim::shop::Shop;

const DAYS: f64 = 2.0;

fn fixture() -> String {
    std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/teach-free.fab.txt")).expect("the Free build fixture")
}

/// The fixture with an `inports N` line after its transport line.
fn with_ports(text: &str, n: u32) -> String {
    let mut out = vec![];
    for l in text.lines() {
        out.push(l.to_string());
        if l.starts_with("transport\t") {
            out.push(format!("inports\t{n}"));
        }
    }
    out.join("\n") + "\n"
}

fn no_storage(text: &str) -> String {
    text.lines().filter(|l| !l.starts_with("stocker\t")).collect::<Vec<_>>().join("\n") + "\n"
}

fn go(text: &str, seed: u64) -> RunResult {
    let shop = Shop::parse(text).unwrap_or_else(|e| panic!("the fab file parses: {e}"));
    run(&shop, &RunOptions { seed, until: Some(DAYS * 1440.0), record: true }, None)
}

/// A run's jobs, exactly.
fn events(r: &RunResult) -> Vec<(u32, u32, u32, u64, u64, u64)> {
    r.trace.iter().map(|x| (x.lot, x.step, x.tool, x.arrive.to_bits(), x.start.to_bits(), x.end.to_bits())).collect()
}

#[test]
fn st1_without_a_limit_nothing_changes() {
    let base = fixture();
    for seed in [1u64, 2] {
        let plain = go(&base, seed);
        assert!(plain.storage.is_none(), "no storage report without a limit");
        let roomy = go(&with_ports(&base, 1000), seed);
        assert_eq!(events(&plain), events(&roomy), "seed {seed}: a limit no line reaches changes nothing");
        assert_eq!(plain.finished, roomy.finished);
        let st = roomy.storage.as_ref().expect("a report when a limit is set");
        assert_eq!(st.to_storage, 0, "nothing goes to storage");
    }
}

#[test]
fn st2_ports_hold_at_most_their_limit_and_storage_takes_the_rest() {
    let text = with_ports(&fixture(), 1);
    let shop = Shop::parse(&text).unwrap();
    let mut used = 0;
    for seed in [1u64, 2, 3] {
        let r = go(&text, seed);
        let st = r.storage.as_ref().expect("a storage report");
        for (gi, g) in shop.groups.iter().enumerate() {
            let tools = r.tools.iter().filter(|t| t.group == g.name).count() as u32;
            if tools == 0 {
                continue;
            }
            assert!(st.peak_ports[gi] <= tools, "seed {seed} {}: {} lots at or headed to {} ports", g.name, st.peak_ports[gi], tools);
        }
        assert_eq!(st.to_storage, st.from_storage + st.still_stored as i64, "seed {seed}: every stored lot came back or is still there");
        used += st.to_storage;
    }
    assert!(used > 0, "with one port a machine, storage is used");
}

#[test]
fn st3_a_limit_with_no_storage_changes_nothing_and_the_checks_warn() {
    let bare = no_storage(&fixture());
    let limited = with_ports(&bare, 1);
    for seed in [1u64, 2] {
        assert_eq!(events(&go(&bare, seed)), events(&go(&limited, seed)), "seed {seed}: no storage, no change");
    }
    let issues = fabsim::checks::check(&Shop::parse(&limited).unwrap());
    assert!(issues.iter().any(|i| i.code == "no_storage"), "the checks warn: {:?}", issues.iter().map(|i| i.code).collect::<Vec<_>>());
    let ok = fabsim::checks::check(&Shop::parse(&with_ports(&fixture(), 1)).unwrap());
    assert!(!ok.iter().any(|i| i.code == "no_storage"), "no warning with storage on the floor");
}

#[test]
fn st4_with_storage_in_use_every_lot_still_follows_its_route() {
    let text = with_ports(&fixture(), 1);
    let shop = Shop::parse(&text).unwrap();
    let r = go(&text, 2);
    assert!(r.storage.as_ref().unwrap().to_storage > 0);
    // each lot's jobs: steps in order (the teaching route samples nothing and has no rework), each on its step's group
    let route = &shop.routes[0];
    let mut last: std::collections::HashMap<u32, (u32, f64)> = Default::default();
    let mut jobs: Vec<_> = r.trace.iter().collect();
    jobs.sort_by(|a, b| a.start.total_cmp(&b.start).then(a.lot.cmp(&b.lot)));
    for x in jobs {
        let want = last.get(&x.lot).map(|(s, _)| s + 1).unwrap_or(0);
        assert_eq!(x.step, want, "lot {} skipped or repeated a step", x.lot);
        if let Some((_, end)) = last.get(&x.lot) {
            assert!(x.arrive >= *end, "lot {} arrived before its last step ended", x.lot);
        }
        assert_eq!(r.tools[x.tool as usize].group, route.steps[x.step as usize].group, "lot {} on the wrong group", x.lot);
        last.insert(x.lot, (x.step, x.end));
    }
    // finished lots did every step
    for (i, l) in r.lots.iter().enumerate() {
        if l.done.is_some() {
            assert_eq!(last.get(&(i as u32)).map(|(s, _)| *s as usize), Some(route.steps.len() - 1), "lot {i} finished without its last step");
        }
    }
    let receipt = fabsim::receipt::write(&shop, &r, &fabsim::receipt::Meta { shop_sha256: "0".repeat(64), seed: 2, policy: "today".into(), until: DAYS * 1440.0, from: 0.0, to: DAYS * 1440.0 }).unwrap();
    let f = receipt.lines().filter(|l| l.starts_with("F ")).count();
    assert_eq!(f, r.lots.iter().filter(|l| l.done.is_some()).count(), "the receipt lists the finished lots");
}
