//! Defects in the fab: holds on top of rework (docs/RL-DEFECTS.md, tests 1 to 4). Written before the code.
//! On the SMT2020 model's rules, with a toy shop; no real fab.

mod common;

use fabsim::engine::{run, RunOptions, RunResult};
use fabsim::shop::Shop;

// step 1 (group B) sends a lot back to step 0 a quarter of the time: each such rework is a finding
const BASE: &str = "fabgym-shop 1
transport\t5.0\t10.0
group\tA\t2\t1.0\t1.0\t-\t-\t-
group\tB\t2\t1.0\t1.0\t-\t-\t-
route\tr
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t15.0\t2.0\t-\t-\t-\t-\t-\t-\t0\t0.25\t-\t-
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t12.0\t0.0\t-\tN
";
const DEFECTS: &str = "defects\t120\t240\t60\n";
const HORIZON: f64 = 4.0 * 1440.0;

fn go(text: &str, seed: u64) -> (Shop, RunResult) {
    let shop = Shop::parse(text).unwrap();
    let r = run(&shop, &RunOptions { seed, until: Some(HORIZON), record: true }, None);
    (shop, r)
}

/// every rework in a run: (lot, the step it finished, the tool, when), from the trace
fn reworks(r: &RunResult) -> Vec<(u32, u32, u32, f64)> {
    let mut by_lot: std::collections::BTreeMap<u32, Vec<_>> = Default::default();
    for t in &r.trace {
        by_lot.entry(t.lot).or_default().push(*t);
    }
    let mut out = vec![];
    for (lot, steps) in by_lot {
        for w in steps.windows(2) {
            if w[1].step <= w[0].step {
                out.push((lot, w[0].step, w[0].tool, w[0].end));
            }
        }
    }
    out
}

#[test]
fn without_the_record_nothing_changes() {
    let s = Shop::parse(BASE).unwrap();
    assert!(s.defects.is_none());
    let with = Shop::parse(&format!("{BASE}{DEFECTS}")).unwrap();
    let d = with.defects.expect("the record is read");
    assert_eq!((d.hold_tool_minutes, d.lookback_minutes, d.hold_lot_minutes), (120.0, 240.0, 60.0));
    // the record round-trips, and a shop without it writes none
    assert_eq!(Shop::parse(&with.to_text()).unwrap().defects, with.defects);
    assert!(!s.to_text().contains("defects"));
    // without the record a run has no holds at all
    let (_, r) = go(BASE, 3);
    assert!(r.holds.is_empty());
    assert!(!r.states.iter().any(|s| s.why == "hold"));
}

#[test]
fn a_finding_holds_its_tool() {
    let mut seen = 0;
    for seed in 0..4 {
        let (_, r) = go(&format!("{BASE}{DEFECTS}"), seed);
        let rw = reworks(&r);
        assert!(!rw.is_empty(), "seed {seed}: the toy shop should rework some lots");
        // one hold per tool and moment a rework was found
        let mut want: Vec<(u32, u64)> = rw.iter().map(|&(_, _, tool, end)| (tool, end.to_bits())).collect();
        want.sort();
        want.dedup();
        let mut got: Vec<(u32, u64)> = r.holds.iter().map(|h| (h.tool, h.t.to_bits())).collect();
        got.sort();
        assert_eq!(got, want, "seed {seed}");
        for h in &r.holds {
            let row = r.states.iter().find(|s| s.tool_index == h.tool && s.time >= h.t && s.why == "hold")
                .unwrap_or_else(|| panic!("seed {seed}: no hold row for tool {} at {}", h.tool, h.t));
            assert_eq!(row.state, "unscheduled down");
            // nothing starts on the held tool for hold_tool_minutes from when the hold began
            for t in r.trace.iter().filter(|t| t.tool == h.tool) {
                assert!(!(t.start >= row.time && t.start < row.time + 120.0), "seed {seed}: work started on a held tool");
            }
            seen += 1;
        }
    }
    assert!(seen > 0);
}

#[test]
fn a_finding_holds_the_lots_its_tool_touched() {
    for seed in 0..4 {
        let (_, r) = go(&format!("{BASE}{DEFECTS}"), seed);
        for h in &r.holds {
            // lots that finished the same step on the same tool in the lookback and had not started another step
            let mut want: Vec<u32> = r
                .trace
                .iter()
                .filter(|t| t.tool == h.tool && t.step == h.step && t.end >= h.t - 240.0 && t.end < h.t && t.lot != h.lot)
                .filter(|t| !r.trace.iter().any(|n| n.lot == t.lot && n.start > t.end && n.start <= h.t))
                .map(|t| t.lot)
                .collect();
            want.sort();
            want.dedup();
            let mut got = h.lots.clone();
            got.sort();
            assert_eq!(got, want, "seed {seed}, hold at {}", h.t);
            // a held lot starts nothing until hold_lot_minutes after the finding
            for &l in &h.lots {
                assert!(!r.trace.iter().any(|n| n.lot == l && n.start > h.t && n.start < h.t + 60.0), "seed {seed}: lot {l} started while held");
            }
        }
    }
}

#[test]
fn holds_move_no_random_draw() {
    // a lot's path (its steps, reworks included) comes from its own stream, so defects leave it alone:
    // for every lot, one run's path is a prefix of the other's
    for seed in 0..4 {
        let (_, off) = go(BASE, seed);
        let (_, on) = go(&format!("{BASE}{DEFECTS}"), seed);
        let path = |r: &RunResult, id: &str| -> Vec<u32> {
            let k = r.lots.iter().position(|l| l.id == id);
            k.map(|k| r.trace.iter().filter(|t| t.lot as usize == k).map(|t| t.step).collect()).unwrap_or_default()
        };
        let mut compared = 0;
        for l in &off.lots {
            let (a, b) = (path(&off, &l.id), path(&on, &l.id));
            let n = a.len().min(b.len());
            assert_eq!(a[..n], b[..n], "seed {seed}, lot {}", l.id);
            compared += n;
        }
        assert!(compared > 100);
    }
}
