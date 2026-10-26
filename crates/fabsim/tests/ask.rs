//! Ask the fab: the scenario text, the new dials, the policies and the scorer (docs/ASK.md).

mod common;

use fabsim::dials::Dials;
use fabsim::engine::{run, RunOptions};
use fabsim::policy::{run_with, Policy};
use fabsim::scenario::Scenario;
use fabsim::score::{score, Protocol};
use fabsim::shop::Shop;

fn toy() -> Shop {
    Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap()
}

const SCEN: &str = "fabgym-scenario 1
question\tEtch is down tomorrow morning, what do we do?
shock\toutage\tEtch\t30\t8\tassumed
candidate\tfifo\trule\tfifo
candidate\tcapped\tcap\t6
candidate\tspare-etch\tspare\tEtch\t1
candidate\tspare-etch\trule\tspt
sweep\toutage\thours\t2\t14\t4
";

// ------------------------------------------------------------------ the scenario text

#[test]
fn scenario_round_trip() {
    let s = Scenario::parse(SCEN).unwrap();
    assert_eq!(s.question, "Etch is down tomorrow morning, what do we do?");
    assert_eq!(s.shocks.len(), 1);
    assert!(!s.shocks[0].said);
    assert_eq!(s.candidates.iter().map(|c| c.name.as_str()).collect::<Vec<_>>(), vec!["fifo", "capped", "spare-etch"]);
    assert_eq!(s.candidates[2].changes.len(), 2);
    assert_eq!(s.sweep.as_ref().unwrap().points().len(), 4);
    assert_eq!(Scenario::parse(&s.to_text()).unwrap(), s);
}

#[test]
fn scenario_refusals() {
    let bad = [
        // unknown record, unknown shock, unknown rule, a said value swept, two sweeps, bad numbers
        "fabgym-scenario 1\nquestion\tq\nwhat\tx\n",
        "fabgym-scenario 1\nquestion\tq\nshock\tearthquake\t2\tsaid\n",
        "fabgym-scenario 1\nquestion\tq\ncandidate\ta\trule\tmagic\n",
        "fabgym-scenario 1\nquestion\tq\nshock\tbreakdowns\t2\tsaid\nsweep\tbreakdowns\tvalue\t1\t3\t3\n",
        "fabgym-scenario 1\nquestion\tq\nshock\tbreakdowns\t2\tassumed\nshock\tdemand\t1.2\tassumed\nsweep\tbreakdowns\tvalue\t1\t3\t3\nsweep\tdemand\tvalue\t1\t2\t3\n",
        "fabgym-scenario 1\nquestion\tq\ncandidate\ta\tcap\tmany\n",
        "fabgym-scenario 2\nquestion\tq\n",
        "fabgym-scenario 1\n",
    ];
    for b in bad {
        assert!(Scenario::parse(b).is_err(), "accepted: {b:?}");
    }
    let mut seven = String::from("fabgym-scenario 1\nquestion\tq\n");
    for i in 0..7 {
        seven.push_str(&format!("candidate\tc{i}\tcap\t{}\n", 5 + i));
    }
    assert!(Scenario::parse(&seven).is_err(), "seven candidates accepted");
}

#[test]
fn scenario_checks_against_the_shop() {
    let s = Scenario::parse("fabgym-scenario 1\nquestion\tq\nshock\toutage\tNoSuch\t1\t2\tsaid\n").unwrap();
    assert!(s.check(&toy()).is_err());
    let s = Scenario::parse("fabgym-scenario 1\nquestion\tq\ncandidate\ta\tspare\tNoSuch\t1\n").unwrap();
    assert!(s.check(&toy()).is_err());
    assert!(Scenario::parse(SCEN).unwrap().check(&toy()).is_ok());
}

// ------------------------------------------------------------------ the new dials

#[test]
fn spare_tools_join_the_group() {
    let d = Dials { spare: vec![("Etch".into(), 2)], ..Dials::default() };
    let s = d.apply(&toy()).unwrap();
    assert_eq!(s.groups.iter().find(|g| g.name == "Etch").unwrap().count, 4);
    assert!(Dials { spare: vec![("NoSuch".into(), 1)], ..Dials::default() }.apply(&toy()).is_err());
}

#[test]
fn hot_lots_are_spread_and_repeatable() {
    let base = toy();
    let d = Dials { make_hot: 2, ..Dials::default() };
    let a = d.apply(&base).unwrap();
    assert_eq!(a, d.apply(&base).unwrap());
    let hot: Vec<&str> = a.lots.iter().filter(|l| l.priority >= 20.0).map(|l| l.id.as_str()).collect();
    let was_hot = base.lots.iter().filter(|l| l.priority >= 20.0).count();
    assert_eq!(hot.len(), was_hot + 2, "{hot:?}");
    assert!(Dials { make_hot: base.lots.len() + 1, ..Dials::default() }.apply(&base).is_err());
}

// ------------------------------------------------------------------ the policies

#[test]
fn todays_rule_is_the_engine_own() {
    let o = RunOptions { seed: 4, until: Some(2880.0), record: true };
    assert_eq!(run_with(&toy(), &o, Policy::Today).log_text(), run(&toy(), &o, None).log_text());
}

#[test]
fn every_policy_repeats_and_some_differ() {
    let o = RunOptions { seed: 4, until: Some(2880.0), record: true };
    let mut logs = vec![];
    for p in [Policy::Today, Policy::Fifo, Policy::Spt, Policy::CriticalRatio, Policy::Random] {
        let a = run_with(&toy(), &o, p).log_text();
        assert_eq!(a, run_with(&toy(), &o, p).log_text(), "{p:?} does not repeat");
        logs.push(a);
    }
    assert_ne!(logs[0], logs[4], "random matches today's rule");
    assert_ne!(logs[2], logs[3], "critical ratio matches shortest processing");
    assert_eq!(Policy::parse("cr"), Some(Policy::CriticalRatio));
    assert_eq!(Policy::parse("magic"), None);
}

// ------------------------------------------------------------------ the scorer

fn quick() -> Protocol {
    Protocol { warmup_days: 1.0, window_days: 3.0, seeds: (0..6).collect(), threads: 2 }
}

#[test]
fn a_candidate_equal_to_today_shows_no_effect() {
    let s = Scenario::parse("fabgym-scenario 1\nquestion\tq\ncandidate\tsame\trule\ttoday\n").unwrap();
    let r = score(&toy(), &s, &quick()).unwrap();
    assert_eq!(r.candidates.len(), 1);
    for m in &r.candidates[0].measures {
        assert_eq!(m.interval.mean, 0.0, "{}", m.key);
        assert_eq!(m.verdict, fabsim::uq::Verdict::CannotSay, "{}", m.key);
        assert_eq!(m.cand.len(), 6);
    }
    assert!(r.best.is_none());
    assert!((r.alpha_each - 0.05).abs() < 1e-12);
}

#[test]
fn bonferroni_over_candidates_and_the_reward() {
    let s = Scenario::parse(SCEN).unwrap();
    let r = score(&toy(), &s.without_sweep(), &quick()).unwrap();
    assert!((r.alpha_each - 0.05 / 3.0).abs() < 1e-12);
    let keys: Vec<&str> = r.candidates[0].measures.iter().map(|m| m.key).collect();
    for k in ["reward", "moves", "lots_finished", "wait_lot_hours", "wait_per_move_minutes", "breaches", "mean_wip"] {
        assert!(keys.contains(&k), "{k} missing");
    }
    for c in &r.candidates {
        let get = |k: &str| c.measures.iter().find(|m| m.key == k).unwrap();
        let (fin, wait, rew) = (get("lots_finished"), get("wait_lot_hours"), get("reward"));
        for i in 0..fin.cand.len() {
            assert!((rew.cand[i] - (fin.cand[i] - 0.01 * wait.cand[i])).abs() < 1e-9);
        }
    }
}

#[test]
fn the_sweep_scores_every_point() {
    let s = Scenario::parse(SCEN).unwrap();
    let r = score(&toy(), &s, &quick()).unwrap();
    let sw = r.sweep.as_ref().expect("a sweep");
    assert_eq!(sw.points, vec![2.0, 6.0, 10.0, 14.0]);
    assert_eq!(sw.by_point.len(), 4);
    assert_eq!(sw.crossovers.len(), 3);
}

#[test]
fn scores_do_not_depend_on_threads() {
    let s = Scenario::parse(SCEN).unwrap().without_sweep();
    let mut one = quick();
    one.threads = 1;
    let mut four = quick();
    four.threads = 4;
    assert_eq!(score(&toy(), &s, &one).unwrap().to_json(), score(&toy(), &s, &four).unwrap().to_json());
}

#[test]
fn the_report_says_what_it_is() {
    let s = Scenario::parse(SCEN).unwrap().without_sweep();
    let j = score(&toy(), &s, &quick()).unwrap().to_json();
    for k in ["\"question\":", "\"seeds\":", "\"alpha_each\":", "\"candidates\":", "\"best\":", "Real-fab effect: cannot say", "\"said\":false"] {
        assert!(j.contains(k), "{k} missing");
    }
}

#[test]
fn breaches_counted_in_the_window_only() {
    let s = toy();
    let r = run(&s, &RunOptions { seed: 2, until: Some(5760.0), record: false }, None);
    assert!(r.breaches.iter().all(|b| b.t >= 0.0 && b.t <= 5760.0));
}
