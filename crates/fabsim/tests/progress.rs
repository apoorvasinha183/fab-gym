//! Runs you can watch (docs/RUNS.md, part 1, RN1). Written before the code: the scorer reports as it works, and the
//! report is the same with or without the reports. One test in its own file, since the event sink is shared.
//! From the SMT2020 testbed's shape, on a small test fab; not a real fab.

mod common;

use std::sync::{Arc, Mutex};

use fabsim::layout::Config;
use fabsim::scenario::Scenario;
use fabsim::score::{score, score_with, FamilyContext, Protocol};
use fabsim::shop::Shop;
use serde_json::Value;

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t2\t0.0\t0.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t45.0\t0.0\t-\tA
";

const FAM: &str = "fabgym-scenario 1
question\tPrototype orders double. Their own copies, or first in line?
family\tshare\t2\tsaid
candidate\tcopies\tfloor\tcopies
candidate\tfirst\tpolicy\tbfirst
";

const ONE: &str = "fabgym-scenario 1\nquestion\tq\ncandidate\tfifo\trule\tfifo\n";

fn ctx() -> FamilyContext {
    FamilyContext { from_route: "ra".into(), b_route: "part_E3".into(), areas: None, layout: Config::realistic(), cache: None }
}

fn small() -> Protocol {
    Protocol { warmup_days: 1.0, window_days: 4.0, seeds: vec![0, 1, 2], threads: 2 }
}

/// The events written while `f` runs, parsed.
fn heard<T>(f: impl FnOnce() -> T) -> (T, Vec<Value>) {
    let got = Arc::new(Mutex::new(Vec::<String>::new()));
    let g = got.clone();
    fabsim::progress::set_sink(Some(Box::new(move |line: &str| g.lock().unwrap().push(line.to_string()))));
    let out = f();
    fabsim::progress::set_sink(None);
    let lines = got.lock().unwrap().clone();
    (out, lines.iter().map(|l| serde_json::from_str(l).expect("each event is one JSON object")).collect())
}

fn check(events: &[Value], arms: &[&str], seeds: usize, measure: &str, floors: bool) {
    let kinds: Vec<&str> = events.iter().map(|e| e["e"].as_str().unwrap()).collect();
    assert_eq!(kinds.first(), Some(&"start"), "{kinds:?}");
    assert_eq!(kinds.last(), Some(&"end"), "{kinds:?}");
    let start = &events[0];
    let names: Vec<&str> = start["arms"].as_array().unwrap().iter().map(|a| a.as_str().unwrap()).collect();
    assert_eq!(names, arms);
    assert_eq!(start["runs"].as_u64().unwrap() as usize, arms.len() * seeds);
    assert_eq!(start["measure"].as_str().unwrap(), measure);
    let floor_events: Vec<&Value> = events.iter().filter(|e| e["e"] == "floor").collect();
    if floors {
        assert_eq!(floor_events.len(), arms.len(), "one floor event per setup");
        for (f, a) in floor_events.iter().zip(arms) {
            assert_eq!(f["arm"].as_str().unwrap(), *a);
            assert!(["saved", "new", "none"].contains(&f["how"].as_str().unwrap()));
            assert!(f["groups"].as_u64().unwrap() >= 2);
        }
        // every floor is ready before the first run
        let last_floor = kinds.iter().rposition(|k| *k == "floor").unwrap();
        let first_run = kinds.iter().position(|k| *k == "run").unwrap();
        assert!(last_floor < first_run);
    } else {
        assert!(floor_events.is_empty());
    }
    let runs: Vec<&Value> = events.iter().filter(|e| e["e"] == "run").collect();
    assert_eq!(runs.len(), arms.len() * seeds, "one run event per setup and random run");
    for a in arms {
        let mut s: Vec<u64> = runs.iter().filter(|r| r["arm"] == *a).map(|r| r["seed"].as_u64().unwrap()).collect();
        s.sort();
        assert_eq!(s, (0..seeds as u64).collect::<Vec<_>>(), "{a}: each random run once");
    }
    for r in &runs {
        assert_eq!(r["measure"].as_str().unwrap(), measure);
        assert!(r["value"].as_f64().is_some(), "a run carries its number");
        assert!(r["seconds"].as_f64().unwrap() >= 0.0);
    }
}

#[test]
fn rn1_events_come_in_order_and_change_nothing() {
    // a two-family question: floors, then runs carrying profit, then the end with the leader
    let toy = Shop::parse(TOY).unwrap();
    let s = Scenario::parse(FAM).unwrap();
    let quiet = score_with(&toy, &s, &small(), Some(&ctx())).unwrap().to_json();
    let (loud, ev) = heard(|| score_with(&toy, &s, &small(), Some(&ctx())).unwrap().to_json());
    assert_eq!(quiet, loud, "the report is the same with events on");
    check(&ev, &["today", "copies", "first"], 3, "profit", true);
    let best: Value = serde_json::from_str::<Value>(&loud).unwrap()["best"].clone();
    assert_eq!(ev.last().unwrap()["best"], best, "the end names the report's leader");

    // a one-family question: no floors, runs carrying reward
    let mixed = Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap();
    let one = Scenario::parse(ONE).unwrap();
    let p = Protocol { seeds: vec![0, 1], threads: 2, ..Default::default() };
    let quiet = score(&mixed, &one, &p).unwrap().to_json();
    let (loud, ev) = heard(|| score(&mixed, &one, &p).unwrap().to_json());
    assert_eq!(quiet, loud);
    check(&ev, &["today", "fifo"], 2, "reward", false);
}
