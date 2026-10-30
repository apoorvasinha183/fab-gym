//! Failure and recovery per tool and per rail piece (docs/OVERRIDES.md): a JSON overrides file beside the fab file;
//! with none, every run is today's. Written before the code. On the SMT2020 model; numbers here are test settings.

mod common;

use fabsim::engine::{run, run_with, RunOptions, RunResult};
use fabsim::hash::sha256_hex;
use fabsim::overrides::Overrides;
use fabsim::shop::{Fleet, Shop};
use fabsim::track::Track;

const DAY: f64 = 1440.0;
const UNSCHEDULED: usize = 3;

const TINY: &str = "fabgym-shop 1
transport\t0.0\t0.0
group\tA\t1\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
lot\tL1\tr\t25\t10.0\t0.0\t0
lot\tL2\tr\t25\t10.0\t0.0\t0
";

fn tiny() -> Shop {
    Shop::parse(TINY).unwrap()
}

fn smt() -> Option<Shop> {
    Some(fabsim::smt2020::load_reference(&common::smt2020_dir()?).unwrap())
}

fn go(shop: &Shop, ov: &Overrides, seed: u64, days: f64) -> RunResult {
    run_with(shop, &RunOptions { seed, until: Some(days * DAY), record: true }, None, ov)
}

/// When each tool's breakdowns (or maintenance, or a rail's breakdowns) fell due, from a recorded run.
fn dues(r: &RunResult, what: &str, tool: &str) -> Vec<f64> {
    r.due.iter().filter(|d| d.what == what && d.tool == tool).map(|d| d.t).collect()
}

fn unscheduled(r: &RunResult, group: &str) -> f64 {
    r.tools.iter().filter(|t| t.group == group).map(|t| t.minutes[UNSCHEDULED]).sum()
}

/// A group with random breakdowns and at least two tools.
fn breaking_group(s: &Shop) -> String {
    s.groups.iter().find(|g| g.breakdown.is_some_and(|b| b.0 > 0.0) && g.count >= 2).expect("a group with breakdowns").name.clone()
}

fn ov(shop: &Shop, json: &str) -> Overrides {
    Overrides::parse(json, shop).unwrap_or_else(|e| panic!("{json} should read: {e}"))
}

// ---- 1. no overrides is today ----

#[test]
fn no_overrides_and_an_empty_file_leave_the_toy_logs_unchanged() {
    for name in ["tiny", "mixed", "capped"] {
        let shop = Shop::parse(&common::read(&format!("golden/toy/{name}.shop.txt"))).unwrap();
        let want = common::read(&format!("golden/toy/{name}.log.txt"));
        let meta = common::read(&format!("golden/toy/{name}.run.json"));
        let seed: u64 = meta.split("\"seed\": ").nth(1).unwrap().split([',', '}']).next().unwrap().trim().parse().unwrap();
        let until_s = meta.split("\"until\": ").nth(1).unwrap().split([',', '}']).next().unwrap().trim();
        let until = if until_s == "null" { None } else { Some(until_s.parse().unwrap()) };
        let opts = RunOptions { seed, until, record: true };
        for o in [Overrides::default(), ov(&shop, r#"{"fabgym-overrides": 1}"#)] {
            common::assert_same_text(&run_with(&shop, &opts, None, &o).log_text(), &want, name);
        }
    }
}

#[test]
fn an_empty_file_leaves_the_smt2020_golden_logs_unchanged() {
    let Some(shop) = smt() else { return };
    let empty = ov(&shop, r#"{"fabgym-overrides": 1, "groups": {}, "tools": {}}"#);
    for seed in 0..3 {
        let log = run_with(&shop, &RunOptions { seed, until: Some(DAY), record: true }, None, &empty).log_text();
        let (hash, lines) = common::recorded_hash(&format!("smt2020.seed{seed}.1d.log.txt"));
        assert_eq!(log.lines().count(), lines, "seed {seed}");
        assert_eq!(sha256_hex(log.as_bytes()), hash, "seed {seed}");
    }
}

// ---- 2. refused, naming the path ----

fn refused(shop: &Shop, json: &str, path: &str) {
    let e = Overrides::parse(json, shop).expect_err(json);
    assert!(e.contains(path), "{e:?} names {path:?}");
}

#[test]
fn bad_files_are_refused_naming_the_path() {
    let s = tiny();
    refused(&s, r#"{"groups": {}}"#, "fabgym-overrides");
    refused(&s, r#"{"fabgym-overrides": 1, "groups": {"Nope": {}}}"#, "groups.Nope");
    refused(&s, r#"{"fabgym-overrides": 1, "tools": {"A#9": {}}}"#, "tools.A#9");
    refused(&s, r#"{"fabgym-overrides": 1, "groups": {"A": {"breakdowns": {"kind": "sometimes"}}}}"#, "groups.A.breakdowns.kind");
    refused(&s, r#"{"fabgym-overrides": 1, "groups": {"A": {"breakdowns": {"kind": "random", "mttf_minutes": -5, "mttr_minutes": 3}}}}"#,
            "groups.A.breakdowns.mttf");
    refused(&s, r#"{"fabgym-overrides": 1, "groups": {"A": {"breakdowns": {"kind": "random", "mttf_minutes": 50}}}}"#,
            "groups.A.breakdowns.mttr");
    refused(&s, r#"{"fabgym-overrides": 1, "groups": {"A": {"maintenance": {"kind": "calendar", "every_minutes": 100, "minutes": [9, 3]}}}}"#,
            "groups.A.maintenance.minutes");
    refused(&s, r#"{"fabgym-overrides": 1, "groups": {"A": {"recovery": {"kind": "swap_to_spare", "spares": -1, "swap_minutes": 5}}}}"#,
            "groups.A.recovery.spares");
    refused(&s, r#"{"fabgym-overrides": 1, "rails": {"n0>n1": {"breakdowns": {"kind": "none"}}}}"#, "rails");
    refused(&s, r#"not json"#, "JSON");
}

#[test]
fn hours_and_minutes_mean_the_same() {
    let Some(shop) = smt() else { return };
    let g = breaking_group(&shop);
    let a = ov(&shop, &format!(r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "random", "mttf_hours": 10, "mttr_hours": 1}}}}}}}}"#));
    let b = ov(&shop, &format!(r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "random", "mttf_minutes": 600, "mttr_minutes": 60}}}}}}}}"#));
    assert_eq!(go(&shop, &a, 0, 2.0).log_text(), go(&shop, &b, 0, 2.0).log_text());
}

// ---- 3 and 4. breakdowns per group and per tool ----

#[test]
fn a_group_breaking_more_often_is_down_longer_and_other_groups_are_untouched() {
    let Some(shop) = smt() else { return };
    let g = breaking_group(&shop);
    let (mttf, mttr) = shop.group(&g).unwrap().breakdown.unwrap();
    let more = ov(&shop, &format!(
        r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "random", "mttf_minutes": {}, "mttr_minutes": {}}}}}}}}}"#,
        mttf / 4.0, mttr));
    let base = go(&shop, &Overrides::default(), 1, 3.0);
    let worse = go(&shop, &more, 1, 3.0);
    assert!(unscheduled(&worse, &g) > unscheduled(&base, &g), "{g} breaks more often");
    let other = shop.groups.iter().find(|h| h.name != g && h.breakdown.is_some_and(|b| b.0 > 0.0)).unwrap();
    for k in 1..=other.count {
        let t = format!("{}#{k}", other.name);
        assert_eq!(dues(&base, "breakdown", &t), dues(&worse, "breakdown", &t), "{t}'s breakdowns are its own");
    }
}

#[test]
fn a_group_with_no_breakdowns_has_none() {
    let Some(shop) = smt() else { return };
    let g = breaking_group(&shop);
    let none = ov(&shop, &format!(r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "none"}}}}}}}}"#));
    let r = go(&shop, &none, 1, 3.0);
    assert_eq!(unscheduled(&r, &g), 0.0, "no defects record, so no holds either");
    assert!(r.due.iter().all(|d| !(d.what == "breakdown" && d.tool.starts_with(&format!("{g}#")))));
    assert!(go(&shop, &Overrides::default(), 1, 3.0).due.iter().any(|d| d.what == "breakdown" && d.tool.starts_with(&format!("{g}#"))));
}

#[test]
fn one_tool_changes_alone() {
    let Some(shop) = smt() else { return };
    let g = breaking_group(&shop);
    let (mttf, mttr) = shop.group(&g).unwrap().breakdown.unwrap();
    let one = ov(&shop, &format!(
        r#"{{"fabgym-overrides": 1, "tools": {{"{g}#1": {{"breakdowns": {{"kind": "random", "mttf_minutes": {}, "mttr_minutes": {}}}}}}}}}"#,
        mttf / 10.0, mttr));
    let base = go(&shop, &Overrides::default(), 2, 3.0);
    let r = go(&shop, &one, 2, 3.0);
    assert!(dues(&r, "breakdown", &format!("{g}#1")).len() > dues(&base, "breakdown", &format!("{g}#1")).len());
    assert_eq!(dues(&r, "breakdown", &format!("{g}#2")), dues(&base, "breakdown", &format!("{g}#2")), "the sibling is untouched");
}

#[test]
fn a_tool_setting_wins_over_its_group() {
    let Some(shop) = smt() else { return };
    let g = breaking_group(&shop);
    let both = ov(&shop, &format!(
        r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "none"}}}}}}, "tools": {{"{g}#2": {{"breakdowns": {{"kind": "random", "mttf_minutes": 300, "mttr_minutes": 30}}}}}}}}"#));
    let r = go(&shop, &both, 0, 3.0);
    assert!(dues(&r, "breakdown", &format!("{g}#1")).is_empty());
    assert!(!dues(&r, "breakdown", &format!("{g}#2")).is_empty());
}

// ---- 5 and 6. maintenance, and breakdowns that come with use ----

#[test]
fn maintenance_can_be_removed_or_set_to_a_calendar() {
    let Some(shop) = smt() else { return };
    let g = shop.groups.iter().find(|g| !g.pm.is_empty()).expect("a group with calendar maintenance").name.clone();
    // the shortest SMT2020 calendar is 7 days with the first drawn within it, so 7 days holds every tool's first
    let base = go(&shop, &Overrides::default(), 0, 7.0);
    assert!(base.due.iter().any(|d| d.what == "maintenance" && d.tool.starts_with(&format!("{g}#"))));
    let none = ov(&shop, &format!(r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"maintenance": {{"kind": "none"}}}}}}}}"#));
    let r = go(&shop, &none, 0, 7.0);
    assert!(!r.due.iter().any(|d| d.what == "maintenance" && d.tool.starts_with(&format!("{g}#"))));
    let cal = ov(&shop, &format!(
        r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"maintenance": {{"kind": "calendar", "every_minutes": 600, "minutes": [30, 30]}}}}}}}}"#));
    let r = go(&shop, &cal, 0, 3.0);
    let t = dues(&r, "maintenance", &format!("{g}#1"));
    assert!(t.len() >= 6, "about every 10 hours over 3 days: {t:?}");
    for w in t.windows(2) {
        assert!((w[1] - w[0] - 600.0).abs() < 1e-9, "{w:?} are 600 minutes apart");
    }
}

#[test]
fn breakdowns_by_wafers_come_every_so_many_wafers() {
    let shop = tiny();
    let o = ov(&shop, r#"{"fabgym-overrides": 1, "groups": {"A": {"breakdowns": {"kind": "by_wafers", "every": 25, "minutes": [5, 5]}}}}"#);
    let r = run_with(&shop, &RunOptions { seed: 3, until: None, record: true }, None, &o);
    assert_eq!(dues(&r, "breakdown", "A#1").len(), 2, "two lots of 25 wafers");
    assert!((r.tools[0].minutes[UNSCHEDULED] - 10.0).abs() < 1e-9, "two downs of five minutes");
}

// ---- 7 and 8. recovery ----

#[test]
fn a_spare_cuts_the_down_time_to_the_swap() {
    let Some(shop) = smt() else { return };
    let g = breaking_group(&shop);
    let set = |rec: &str| ov(&shop, &format!(
        r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "random", "mttf_minutes": 400, "mttr_minutes": 300}}, "recovery": {rec}}}}}}}"#));
    let in_place = go(&shop, &set(r#"{"kind": "repair_in_place"}"#), 0, 3.0);
    let swap = go(&shop, &set(r#"{"kind": "swap_to_spare", "spares": 2, "swap_minutes": 15}"#), 0, 3.0);
    assert!(swap.due.iter().any(|d| d.what == "breakdown" && d.tool.starts_with(&format!("{g}#")) && d.minutes == 15.0));
    assert!(unscheduled(&swap, &g) < unscheduled(&in_place, &g));
}

#[test]
fn a_breakdown_can_hold_the_lots_the_tool_just_finished() {
    let Some(shop) = smt() else { return };
    assert!(shop.defects.is_none(), "so every hold here comes from a breakdown");
    let g = breaking_group(&shop);
    let o = ov(&shop, &format!(
        r#"{{"fabgym-overrides": 1, "groups": {{"{g}": {{"breakdowns": {{"kind": "random", "mttf_minutes": 300, "mttr_minutes": 30}}, "recovery": {{"kind": "repair_and_hold_lots", "lookback_minutes": 240, "hold_minutes": 60}}}}}}}}"#));
    let r = go(&shop, &o, 0, 3.0);
    let ours: Vec<_> = r.holds.iter().filter(|h| r.tools[h.tool as usize].group == g).collect();
    assert!(!ours.is_empty() && ours.iter().any(|h| !h.lots.is_empty()), "lots held after a breakdown");
}

// ---- 9. rail pieces ----

fn campus_fleet() -> Option<Shop> {
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
    Some(s)
}

#[test]
fn an_empty_file_leaves_a_fleet_run_unchanged() {
    let Some(s) = campus_fleet() else { return };
    let a = run(&s, &RunOptions { seed: 0, until: Some(0.5 * DAY), record: true }, None);
    let b = go(&s, &ov(&s, r#"{"fabgym-overrides": 1, "rails": {}}"#), 0, 0.5);
    assert_eq!(a.log_text(), b.log_text());
    assert_eq!(a.fleet.as_ref().unwrap().entries, b.fleet.as_ref().unwrap().entries);
}

#[test]
fn a_broken_stretch_is_not_entered_and_its_recovery_matters() {
    let Some(s) = campus_fleet() else { return };
    let base = run(&s, &RunOptions { seed: 0, until: Some(0.5 * DAY), record: true }, None);
    let t = Track::from_shop(&s);
    let fl = base.fleet.as_ref().unwrap();
    let mut use_count = vec![0usize; t.edges().len()];
    for e in &fl.entries {
        use_count[e.edge] += 1;
    }
    // the busiest stretch leaving a split, so a way round could exist
    let busiest = (0..use_count.len()).filter(|&i| t.out_of(t.edges()[i].from).len() >= 2).max_by_key(|&i| use_count[i]).unwrap();
    let id = format!("n{}>n{}", t.edges()[busiest].from, t.edges()[busiest].to);
    let set = |rec: &str| ov(&s, &format!(
        r#"{{"fabgym-overrides": 1, "rails": {{"{id}": {{"breakdowns": {{"kind": "random", "mttf_minutes": 90, "mttr_minutes": 30}}, "recovery": {{"kind": "{rec}"}}}}}}}}"#));
    let around = go(&s, &set("route_around"), 0, 0.5);
    let downs: Vec<(f64, f64)> = around.due.iter().filter(|d| d.what == "rail" && d.tool == id).map(|d| (d.t, d.t + d.minutes)).collect();
    assert!(!downs.is_empty(), "the stretch broke at least once");
    let fa = around.fleet.as_ref().unwrap();
    for e in fa.entries.iter().filter(|e| e.edge == busiest) {
        assert!(!downs.iter().any(|(a, b)| e.t_in > *a && e.t_in < *b), "entered {id} at {} while it was down", e.t_in);
    }
    assert!(fa.delivered < fl.delivered, "breaking the busiest stretch costs deliveries");
    assert_eq!(fa.delivered + fa.open, fa.asked, "every move arrives or is under way");
    let wait = go(&s, &set("wait"), 0, 0.5);
    assert!(fa.held_min <= wait.fleet.as_ref().unwrap().held_min + 1e-6, "going round is never worse than waiting");
}

#[test]
fn an_unknown_stretch_is_refused() {
    let Some(s) = campus_fleet() else { return };
    refused(&s, r#"{"fabgym-overrides": 1, "rails": {"n0>n999999": {"breakdowns": {"kind": "none"}}}}"#, "rails.n0>n999999");
}

// ---- 10. the command ----

#[test]
fn the_log_command_reads_an_overrides_file() {
    let d = std::env::temp_dir().join(format!("fabgym-ov-{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    std::fs::write(d.join("tiny.shop.txt"), TINY).unwrap();
    std::fs::write(d.join("empty.json"), r#"{"fabgym-overrides": 1}"#).unwrap();
    std::fs::write(d.join("wear.json"), r#"{"fabgym-overrides": 1, "groups": {"A": {"breakdowns": {"kind": "by_wafers", "every": 25, "minutes": [5, 5]}}}}"#).unwrap();
    let log = |extra: &[&str]| {
        let out = std::process::Command::new(env!("CARGO_BIN_EXE_fabsim"))
            .arg("log").arg(d.join("tiny.shop.txt")).arg("3").args(extra).output().unwrap();
        assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
        String::from_utf8(out.stdout).unwrap()
    };
    let plain = log(&[]);
    let empty = log(&["--overrides", d.join("empty.json").to_str().unwrap()]);
    let wear = log(&["--overrides", d.join("wear.json").to_str().unwrap()]);
    assert_eq!(plain, empty);
    assert_ne!(plain, wear);
    let _ = std::fs::remove_dir_all(&d);
}
