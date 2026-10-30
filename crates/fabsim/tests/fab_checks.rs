//! The checks a layout must pass (docs/FAB-CHECKS.md). Written before the code. From the SMT2020 testbed; the layouts
//! here are of our own design.

mod common;

use fabsim::checks::{check, Issue, Severity};
use fabsim::shop::Shop;

const TINY: &str = "fabgym-shop 1
transport\t0.0\t0.0
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t2\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t20.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
lot\tL1\tr\t25\t10.0\t0.0\t0
lot\tL2\tr\t25\t10.0\t0.0\t0
";

const PLAN: &str = "price\tA\t2000000.0\t150.0
price\tB\t500000.0\t40.0
node\tn0\t0.0\t0.0
node\tn1\t10.0\t0.0
node\tn2\t10.0\t5.0
node\tn3\t0.0\t5.0
link\tn0\tn1\t10.0
link\tn1\tn2\t5.0
link\tn2\tn3\t10.0
link\tn3\tn0\t5.0
link\tn1\tn3\t11.5
station\tA\t2.0\t-3.0\t4.0\t2.0
station\tB\t12.0\t1.0\t2.0\t3.0
stop\tA\t0\tn1
stop\tB\t0\tn2
stop\tB\t1\tn2
stocker\tn3
entry\tn0
exit\tn3
";

/// The tiny fab with some plan lines removed and others added.
fn fab(remove: &[&str], add: &[&str]) -> Shop {
    let mut lines: Vec<String> = PLAN.lines().filter(|l| !remove.contains(l)).map(String::from).collect();
    lines.extend(add.iter().map(|s| s.to_string()));
    let text = format!("{TINY}{}\n", lines.join("\n"));
    Shop::parse(&text).unwrap_or_else(|e| panic!("the changed fab reads: {e}"))
}

fn codes(issues: &[Issue]) -> Vec<&'static str> {
    issues.iter().map(|i| i.code).collect()
}

/// The issue with this code, which must name `about`.
fn has(issues: &[Issue], code: &str, about: &str) {
    let found = issues.iter().find(|i| i.code == code).unwrap_or_else(|| panic!("no {code} in {:?}", codes(issues)));
    assert!(found.at.iter().any(|a| a == about), "{code} names {about}: {:?}", found.at);
    assert!(!found.message.is_empty());
}

fn errors(issues: &[Issue]) -> usize {
    issues.iter().filter(|i| i.severity == Severity::Error).count()
}

#[test]
fn the_tiny_fab_passes_with_nothing_to_say() {
    let issues = check(&fab(&[], &[]));
    assert!(issues.is_empty(), "{issues:?}");
}

#[test]
fn errors_come_first() {
    let issues = check(&fab(&["entry\tn0", "price\tB\t500000.0\t40.0"], &[]));
    let first_warning = issues.iter().position(|i| i.severity == Severity::Warning).unwrap();
    assert!(issues[..first_warning].iter().all(|i| i.severity == Severity::Error));
    assert!(issues[first_warning..].iter().all(|i| i.severity == Severity::Warning));
}

// ---- errors ----

#[test]
fn a_shop_with_no_plan_cannot_run() {
    let issues = check(&Shop::parse(TINY).unwrap());
    assert_eq!(codes(&issues), vec!["no_plan"]);
}

#[test]
fn no_entry_and_no_exit() {
    assert!(codes(&check(&fab(&["entry\tn0"], &[]))).contains(&"no_entry"));
    assert!(codes(&check(&fab(&["exit\tn3"], &[]))).contains(&"no_exit"));
}

#[test]
fn a_tool_without_a_stop() {
    has(&check(&fab(&["stop\tB\t1\tn2"], &[])), "missing_stops", "B#2");
}

#[test]
fn a_stop_nobody_can_reach() {
    let issues = check(&fab(&["stop\tA\t0\tn1"], &["node\tn9\t20.0\t20.0", "link\tn9\tn3\t30.0", "stop\tA\t0\tn9"]));
    has(&issues, "unreachable", "A#1");
    assert!(errors(&issues) > 0);
}

#[test]
fn a_stop_with_no_way_out() {
    let issues = check(&fab(&["stop\tB\t1\tn2"], &["node\tn8\t10.0\t9.0", "link\tn2\tn8\t4.0", "stop\tB\t1\tn8"]));
    has(&issues, "no_way_out", "B#2");
}

#[test]
fn a_route_whose_next_tool_cannot_be_reached() {
    // B is reached from the entry by its own way, but never from A
    let issues = check(&fab(&["link\tn1\tn2\t5.0", "link\tn3\tn0\t5.0"], &["link\tn0\tn2\t11.5"]));
    has(&issues, "route_gap", "A");
    has(&issues, "route_gap", "B");
    assert!(!codes(&issues).contains(&"unreachable"), "{issues:?}");
    assert!(!codes(&issues).contains(&"trap"), "the exit may be a dead end: {issues:?}");
}

#[test]
fn a_trap() {
    has(&check(&fab(&[], &["node\tn7\t20.0\t0.0", "link\tn1\tn7\t10.0"])), "trap", "n7");
}

// ---- warnings ----

#[test]
fn an_unreachable_stocker() {
    let issues = check(&fab(&["stocker\tn3"], &["node\tn9\t30.0\t30.0", "stocker\tn9"]));
    has(&issues, "stocker_unreachable", "n9");
    assert_eq!(errors(&issues), 0, "{issues:?}");
}

#[test]
fn a_group_with_no_price() {
    let issues = check(&fab(&["price\tB\t500000.0\t40.0"], &[]));
    has(&issues, "no_price", "B");
    assert_eq!(errors(&issues), 0);
}

#[test]
fn overlapping_stations() {
    let issues = check(&fab(&["station\tB\t12.0\t1.0\t2.0\t3.0"], &["station\tB\t3.0\t-2.0\t2.0\t2.0"]));
    has(&issues, "overlap", "A");
    has(&issues, "overlap", "B");
}

#[test]
fn a_link_shorter_than_the_straight_line() {
    has(&check(&fab(&["link\tn1\tn3\t11.5"], &["link\tn1\tn3\t5.0"])), "too_short", "n1>n3");
}

// ---- today's campus, and the command ----

fn campus_fab() -> Option<Shop> {
    use fabsim::layout::{Config, Problem};
    let dir = common::smt2020_dir()?;
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let mut cfg = Config::realistic();
    cfg.iters = 3000;
    cfg.restarts = 1;
    let p = Problem::new(&base, &areas, &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let mut s = base;
    s.oht = Some(p.oht(&c));
    s.ports = p.ports(&c);
    s.bayrails = p.bayrails(&c);
    s.plan = Some(fabsim::fab::plan_from_track(&s).unwrap());
    Some(s)
}

#[test]
fn todays_campus_passes_but_for_the_two_spine_ends() {
    // the drawn spine rails stop at the campus's far ends without a U-turn (docs/FAB-CHECKS.md, Changes): the only
    // errors are those two dead ends, and the runs never use them
    let Some(s) = campus_fab() else { return };
    let issues = check(&s);
    let errs: Vec<&Issue> = issues.iter().filter(|i| i.severity == Severity::Error).collect();
    assert!(errs.iter().all(|i| i.code == "trap"), "{:?}", errs.iter().take(5).collect::<Vec<_>>());
    let t = fabsim::track::Track::from_shop(&s);
    let o = s.oht.as_ref().unwrap();
    let traps: Vec<&String> = errs.iter().flat_map(|i| i.at.iter()).collect();
    assert_eq!(traps.len(), 2, "{traps:?}");
    for id in traps {
        let n: usize = id.strip_prefix('n').unwrap().parse().unwrap();
        let a = &t.nodes()[n];
        assert!(t.out_of(n).is_empty(), "{id} has no way out");
        assert_eq!(a.bay, usize::MAX, "{id} is on a spine rail");
        assert!(a.x.abs() < 1e-9 || (a.x - o.lengths[a.phase]).abs() < 1e-6, "{id} is at a spine rail's end: x {}", a.x);
    }
}

#[test]
fn the_check_command_prints_json_and_exits_by_errors() {
    let d = std::env::temp_dir().join(format!("fabgym-check-{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let good = d.join("good.fab.txt");
    let bad = d.join("bad.fab.txt");
    std::fs::write(&good, fab(&[], &[]).to_text()).unwrap();
    std::fs::write(&bad, fab(&["exit\tn3"], &[]).to_text()).unwrap();
    let run = |f: &std::path::Path| std::process::Command::new(env!("CARGO_BIN_EXE_fabsim")).arg("fab-check").arg(f).arg("--json").output().unwrap();
    let ok = run(&good);
    assert_eq!(ok.status.code(), Some(0));
    let v: serde_json::Value = serde_json::from_slice(&ok.stdout).unwrap();
    assert_eq!(v.as_array().unwrap().len(), 0);
    let no = run(&bad);
    assert_eq!(no.status.code(), Some(2));
    let v: serde_json::Value = serde_json::from_slice(&no.stdout).unwrap();
    assert!(v.as_array().unwrap().iter().any(|i| i["code"] == "no_exit" && i["severity"] == "error"));
    let _ = std::fs::remove_dir_all(&d);
}
