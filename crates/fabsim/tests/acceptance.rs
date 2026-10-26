//! Acceptance tests from the problem statement (docs/PROBLEM.md): numbers 1 to 7, 9, 10, 12.
//! Test 8 (full report), 11 (shocks) and 13 (frontier) belong to the scorer and come with it.

mod common;

use std::collections::{BTreeMap, HashSet};

use fabsim::engine::{run, Decision, RunOptions, RunResult};
use fabsim::shop::Shop;

fn toy(name: &str) -> Shop {
    Shop::parse(&common::read(&format!("golden/toy/{name}.shop.txt"))).unwrap()
}

fn opts(seed: u64, until: Option<f64>) -> RunOptions {
    RunOptions { seed, until, record: true }
}

// 1. Exact incumbent: every decision through the choice point, picking the default, equals a
// run without the choice point.
#[test]
fn t1_exact_incumbent() {
    for (name, seed, until) in [("mixed", 7, Some(4320.0)), ("capped", 3, Some(4320.0))] {
        let shop = toy(name);
        let plain = run(&shop, &opts(seed, until), None).log_text();
        let mut n = 0usize;
        let mut pick = |d: &Decision| {
            n += 1;
            d.default
        };
        let chosen = run(&shop, &opts(seed, until), Some(&mut pick)).log_text();
        assert!(n > 100, "{name}: only {n} decisions");
        common::assert_same_text(&chosen, &plain, name);
    }
    if let Some(dir) = common::smt2020_dir() {
        let shop = fabsim::smt2020::load_reference(&dir).unwrap();
        let o = opts(0, Some(360.0));
        let plain = run(&shop, &o, None).log_text();
        let mut pick = |d: &Decision| d.default;
        let chosen = run(&shop, &o, Some(&mut pick)).log_text();
        common::assert_same_text(&chosen, &plain, "SMT2020 6 h");
    }
}

// 2. Choices matter: two lots wait for one tool; picking the second starts it first.
// (Changed after the first run: in the tiny shop L1 starts before L2 arrives, so the tool is
// held down for the first 5 minutes to make both lots wait for it.)
#[test]
fn t2_choices_matter() {
    let mut shop = toy("tiny");
    shop.groups[0].down.push((0.0, 5.0));
    let base = run(&shop, &opts(0, None), None);
    let start = |r: &RunResult, id: &str| r.lots.iter().find(|l| l.id == id).unwrap().steps[0].start;
    assert_eq!((start(&base, "L1"), start(&base, "L2")), (5.0, 15.0));
    let mut first = true;
    let mut pick = |d: &Decision| {
        if first {
            first = false;
            assert_eq!(d.candidates.len(), 2);
            assert_eq!(d.candidates[d.default].lots, vec!["L1".to_string()]);
            1
        } else {
            d.default
        }
    };
    let swapped = run(&shop, &opts(0, None), Some(&mut pick));
    assert_eq!((start(&swapped, "L1"), start(&swapped, "L2")), (15.0, 5.0));
}

// 2b. A batch candidate starts all its lots together.
#[test]
fn t2_batch_starts_together() {
    let shop = toy("mixed");
    let mut taken: Vec<Vec<String>> = Vec::new();
    let mut pick = |d: &Decision| {
        if let Some(i) = d.candidates.iter().position(|c| c.kind == "batch" && c.lots.len() > 1) {
            taken.push(d.candidates[i].lots.clone());
            i
        } else {
            d.default
        }
    };
    let res = run(&shop, &opts(7, Some(4320.0)), Some(&mut pick));
    assert!(!taken.is_empty(), "no batch of several lots was offered");
    let by_id: BTreeMap<&str, _> = res.lots.iter().map(|l| (l.id.as_str(), l)).collect();
    for batch in &taken {
        // every lot of the batch has a step that starts at the same time on the same tool
        let first = by_id[batch[0].as_str()];
        let found = first.steps.iter().any(|s0| {
            batch.iter().all(|id| {
                by_id[id.as_str()]
                    .steps
                    .iter()
                    .any(|s| s.start == s0.start && s.tool == s0.tool && s.end == s0.end)
            })
        });
        assert!(found, "batch {batch:?} did not start together");
    }
}

// 3. Invalid actions change nothing: the engine falls back to its own rule.
#[test]
fn t3_invalid_actions_change_nothing() {
    let shop = toy("mixed");
    let plain = run(&shop, &opts(7, Some(4320.0)), None).log_text();
    let mut pick = |d: &Decision| d.candidates.len() + 5;
    let bad = run(&shop, &opts(7, Some(4320.0)), Some(&mut pick)).log_text();
    common::assert_same_text(&bad, &plain, "invalid picks");
}

// 4. Determinism: the same seed and actions give the same run; another seed gives another.
#[test]
fn t4_determinism() {
    let shop = toy("mixed");
    let a = run(&shop, &opts(7, Some(4320.0)), None).log_text();
    let b = run(&shop, &opts(7, Some(4320.0)), None).log_text();
    let c = run(&shop, &opts(8, Some(4320.0)), None).log_text();
    assert_eq!(a, b);
    assert_ne!(a, c);
}

// 5. Conservation: no lot lost or doubled, steps in order, a tool never runs two jobs at once
// except one batch.
#[test]
fn t5_conservation() {
    let shop = toy("mixed");
    let res = run(&shop, &opts(7, Some(4320.0)), None);
    let ids: HashSet<&str> = res.lots.iter().map(|l| l.id.as_str()).collect();
    assert_eq!(ids.len(), res.lots.len(), "a lot id appears twice");
    let released = res.release_log.iter().filter(|r| r.released.is_some()).count();
    assert_eq!(res.lots.len(), shop.lots.len() + released);
    let mut by_tool: BTreeMap<&str, Vec<(f64, f64)>> = BTreeMap::new();
    for lot in &res.lots {
        let mut last_end = f64::NEG_INFINITY;
        for s in &lot.steps {
            assert!(s.arrive <= s.start && s.start <= s.end, "{} step {}", lot.id, s.step);
            assert!(s.start >= last_end, "{} overlaps its own steps", lot.id);
            last_end = s.end;
            by_tool.entry(s.tool.as_str()).or_default().push((s.start, s.end));
        }
    }
    for (tool, mut iv) in by_tool {
        iv.sort_by(|a, b| a.partial_cmp(b).unwrap());
        iv.dedup(); // the lots of one batch share one interval
        for w in iv.windows(2) {
            assert!(w[1].0 >= w[0].1, "{tool} runs two jobs at once: {:?} and {:?}", w[0], w[1]);
        }
    }
}

// 6. No leakage: the decision and candidate field sets are exactly those of the problem statement.
#[test]
fn t6_no_leakage() {
    assert_eq!(
        Decision::FIELDS,
        ["t", "tool_group", "tool", "tool_setup", "group_tools", "totals", "candidates", "default"]
    );
    assert_eq!(
        fabsim::engine::Candidate::FIELDS,
        [
            "kind",
            "lots",
            "priority",
            "size_wafers",
            "route",
            "step",
            "steps_left",
            "waited_minutes",
            "setup_change",
            "proc_minutes",
            "work_left_minutes",
            "release",
            "cqt_slack_minutes"
        ]
    );
    // and every decision handed out lies in the past or present
    let shop = toy("mixed");
    let mut pick = |d: &Decision| {
        for c in &d.candidates {
            assert!(c.waited_minutes >= 0.0 && c.release <= d.t);
        }
        d.default
    };
    run(&shop, &opts(7, Some(4320.0)), Some(&mut pick));
}

// 7. Faithful world: raw processing time per product within 1% of the published reference
// (Tassel et al., arXiv 2302.07162: 24.75 and 14.54 days).
#[test]
fn t7_faithful_world() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load_reference(&dir).unwrap();
    let days = fabsim::measure::raw_processing_days(&shop, 20, 0);
    for (part, want) in [("part_3", 24.75), ("part_4", 14.54)] {
        let got = days[part];
        assert!((got - want).abs() / want < 0.01, "{part}: {got:.3} days against {want}");
    }
}

// 9. Probes change nothing.
#[test]
fn t9_probes_change_nothing() {
    let mut with = toy("capped");
    let without = {
        let mut s = with.clone();
        s.probes.clear();
        s
    };
    with.probes = vec![0.0, 100.0, 777.5, 1440.0, 2000.0, 4000.0];
    let strip = |t: String| t.lines().filter(|l| !l.starts_with("probe\t")).collect::<Vec<_>>().join("\n");
    let a = strip(run(&with, &opts(3, Some(4320.0)), None).log_text());
    let b = strip(run(&without, &opts(3, Some(4320.0)), None).log_text());
    common::assert_same_text(&a, &b, "probes");
}

// 10. The cap holds: no release while at the cap; releases go in oldest first, never before
// their scheduled time, and none is lost.
#[test]
fn t10_cap_holds() {
    let shop = toy("capped");
    let cap = shop.cap.unwrap();
    let res = run(&shop, &opts(3, Some(4320.0)), None);
    let mut last_released = f64::NEG_INFINITY;
    let mut waiting_seen = false;
    for r in &res.release_log {
        match r.released {
            Some(t) => {
                assert!(t >= r.scheduled);
                assert!(r.wip_before.unwrap() < cap, "released at the cap");
                if r.released != Some(r.scheduled) {
                    assert!(t >= last_released, "held releases out of order");
                    waiting_seen = true;
                }
                last_released = last_released.max(t);
            }
            None => {} // still held at the end of the run: not lost, listed
        }
    }
    assert!(waiting_seen, "the cap never held a release in this test");
}

// 12. Little's law, exactly: the probed WIP area equals the sum of each lot's time in the fab.
#[test]
fn t12_littles_law() {
    let mut shop = toy("capped");
    shop.lots.clear(); // released lots only: each one's time in the fab is release to done
    let t_end = 4320.0;
    shop.probes = vec![t_end];
    let res = run(&shop, &opts(3, Some(t_end + 1.0)), None);
    let probe = res.probes.iter().find(|p| p.t == t_end).unwrap();
    let mut area = 0.0;
    for r in &res.release_log {
        let Some(t0) = r.released else { continue };
        if t0 > t_end {
            continue;
        }
        let lot = res.lots.iter().find(|l| l.id == r.id).unwrap();
        let t1 = lot.done.unwrap_or(t_end).min(t_end);
        area += t1 - t0;
    }
    let rel = (probe.wip_lot_minutes - area).abs() / area;
    assert!(rel < 1e-9, "WIP area {} against lot sum {}", probe.wip_lot_minutes, area);
}
