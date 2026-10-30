//! The track is what you drew (docs/FAB-RAILS.md): with plan links, vehicles drive on the plan's own nodes and links.
//! Written before the code. From the SMT2020 testbed; layouts here are of our own design.

mod common;

use fabsim::engine::{run, run_with, RunOptions};
use fabsim::overrides::Overrides;
use fabsim::shop::{Fleet, Shop};
use fabsim::track::Track;

/// Today's campus with its ports and drawn rails, a fleet, and (when `plan`) its export with spots.
fn campus(plan: bool) -> Option<Shop> {
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
    s.fleet = Some(Fleet { vehicles: 160, gap: 3.0, hoist: 1.0, ports: 2, cross: 60.0, controller: "nearest".into() });
    if plan {
        s.plan = Some(fabsim::fab::plan_from_track(&s).unwrap());
        // through the text, as a file would be
        s = Shop::parse(&s.to_text()).unwrap();
    }
    Some(s)
}

#[test]
fn the_campus_file_builds_the_drawn_track() {
    let (Some(a), Some(b)) = (campus(false), campus(true)) else { return };
    assert!(b.plan.as_ref().unwrap().spots.len() == b.plan.as_ref().unwrap().nodes.len(), "a spot for every node");
    let (ta, tb) = (Track::from_shop(&a), Track::from_shop(&b));
    assert_eq!(ta.nodes(), tb.nodes());
    assert_eq!(ta.edges(), tb.edges());
    for g in &a.groups {
        assert_eq!(ta.ports_of(&g.name), tb.ports_of(&g.name), "{}", g.name);
        assert_eq!(ta.stop_of(&g.name), tb.stop_of(&g.name), "{}", g.name);
    }
    let n = ta.nodes().len();
    for x in (0..n).step_by(7) {
        for y in 0..n {
            assert_eq!(ta.dist(x, y), tb.dist(x, y));
            assert_eq!(ta.next(x, y), tb.next(x, y));
        }
    }
}

#[test]
fn the_campus_file_gives_todays_run() {
    let (Some(a), Some(b)) = (campus(false), campus(true)) else { return };
    let o = RunOptions { seed: 0, until: Some(720.0), record: true };
    let (ra, rb) = (run(&a, &o, None), run(&b, &o, None));
    assert_eq!(ra.log_text(), rb.log_text());
    assert_eq!(ra.fleet.as_ref().unwrap().entries, rb.fleet.as_ref().unwrap().entries);
}

#[test]
fn the_files_track_is_the_one_driven() {
    let Some(mut b) = campus(true) else { return };
    let o = RunOptions { seed: 0, until: Some(720.0), record: true };
    let before = run(&b, &o, None);
    let p = b.plan.as_mut().unwrap();
    let in_bay: std::collections::HashSet<String> = p.spots.iter().filter(|s| s.bay != usize::MAX).map(|s| s.node.clone()).collect();
    let l = p.links.iter_mut().find(|l| in_bay.contains(&l.from) && in_bay.contains(&l.to)).expect("a stretch inside a bay");
    l.len += 50.0;
    let after = run(&b, &o, None);
    assert_ne!(before.fleet.as_ref().unwrap().entries, after.fleet.as_ref().unwrap().entries, "a longer stretch changes the run");
}

/// Two tools on a loop, with a bypass round the stretch between them; no `oht`.
const OWN: &str = "fabgym-shop 1
transport\t0.0\t0.0
fleet\t6\t3.0\t1.0\t2\t60.0\tnearest
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t1\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t5.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t5.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t1.0\t15.0\t0.0\t-\tL
node\te\t0.0\t0.0
node\ta\t10.0\t0.0
node\tm\t20.0\t0.0
node\tb\t30.0\t0.0
node\tx\t40.0\t0.0
node\tu\t40.0\t10.0
node\tv\t0.0\t10.0
node\tp\t20.0\t6.0
link\te\ta\t10.0
link\ta\tm\t10.0
link\tm\tb\t10.0
link\tb\tx\t10.0
link\tx\tu\t10.0
link\tu\tv\t40.0
link\tv\te\t10.0
link\ta\tp\t11.7
link\tp\tb\t11.7
stop\tA\t0\ta
stop\tB\t0\tb
entry\te
exit\tx
";

fn own() -> Shop {
    Shop::parse(OWN).expect("a fab of its own reads, with a fleet and no oht")
}

#[test]
fn a_fab_of_its_own_runs_with_a_fleet() {
    let s = own();
    assert!(s.oht.is_none());
    assert!(fabsim::checks::check(&s).iter().all(|i| i.severity != fabsim::checks::Severity::Error));
    let r = run(&s, &RunOptions { seed: 1, until: Some(2.0 * 1440.0), record: true }, None);
    assert!(r.finished > 100, "lots finish: {}", r.finished);
    let f = r.fleet.as_ref().unwrap();
    // each lot makes one move, from A to B (it starts at A's stop and leaves from B)
    assert!(f.delivered >= r.finished, "moves delivered: {}, lots finished: {}", f.delivered, r.finished);
}

#[test]
fn going_round_a_break_beats_waiting_when_there_is_a_way_round() {
    let s = own();
    let set = |rec: &str| Overrides::parse(&format!(
        r#"{{"fabgym-overrides": 1, "rails": {{"a>m": {{"breakdowns": {{"kind": "random", "mttf_minutes": 60, "mttr_minutes": 30}}, "recovery": {{"kind": "{rec}"}}}}}}}}"#), &s).unwrap();
    let o = RunOptions { seed: 1, until: Some(2.0 * 1440.0), record: true };
    let around = run_with(&s, &o, None, &set("route_around"));
    let wait = run_with(&s, &o, None, &set("wait"));
    assert!(around.due.iter().any(|d| d.what == "rail" && d.tool == "a>m"), "the stretch broke, named by its plan nodes");
    let (fa, fw) = (around.fleet.as_ref().unwrap(), wait.fleet.as_ref().unwrap());
    assert!(fa.held_min < fw.held_min, "going round: {} held minutes, waiting: {}", fa.held_min, fw.held_min);
    assert!(fa.delivered >= fw.delivered);
}

#[test]
fn bad_spots_and_a_fleet_with_no_track_are_refused() {
    let e = Shop::parse(&format!("{OWN}spot\tzz\t0\t0\t0\t0.0\t0.0\t-\t0\n")).expect_err("an unknown node");
    assert!(e.contains("zz") && e.contains("line"), "{e}");
    let bare = "fabgym-shop 1\ntransport\t0.0\t0.0\nfleet\t6\t3.0\t1.0\t2\t60.0\tnearest\ngroup\tA\t1\t0.0\t0.0\t-\t-\t-\n";
    let e = Shop::parse(bare).expect_err("a fleet with no track");
    assert!(e.contains("fleet"), "{e}");
}

#[test]
fn going_round_starts_at_the_split_before_the_break() {
    // the break is one stretch past the split (m>b, after a>m); a vehicle bound for b plans round it at a, the last
    // split before it, through the bypass a>p>b (editor take two, docs/EDITOR-TAKE-TWO.md)
    let s = own();
    let set = |rec: &str| Overrides::parse(&format!(
        r#"{{"fabgym-overrides": 1, "rails": {{"m>b": {{"breakdowns": {{"kind": "random", "mttf_minutes": 60, "mttr_minutes": 30}}, "recovery": {{"kind": "{rec}"}}}}}}}}"#), &s).unwrap();
    let o = RunOptions { seed: 1, until: Some(2.0 * 1440.0), record: true };
    let around = run_with(&s, &o, None, &set("route_around"));
    let wait = run_with(&s, &o, None, &set("wait"));
    let (fa, fw) = (around.fleet.as_ref().unwrap(), wait.fleet.as_ref().unwrap());
    assert!(fa.held_min < fw.held_min, "going round from the split: {} held minutes, waiting: {}", fa.held_min, fw.held_min);
    // the bypass is used while m>b is down
    let t = Track::from_shop(&fabsim::engine::native_floor(&s).unwrap());
    let ap = (0..t.edges().len()).find(|&i| t.name(t.edges()[i].from) == "a" && t.name(t.edges()[i].to) == "p").unwrap();
    assert!(fa.entries.iter().any(|e| e.edge == ap), "some vehicle took a>p");
}
