//! The replay and the score (docs/EDITOR-REPLAY.md). Written before the code. On small fabs of our own; not a real fab.

use fabsim::engine::{run, RunOptions, RunResult};
use fabsim::moods::{replay, score, Moods, Settings};
use fabsim::shop::Shop;

const OWN: &str = "fabgym-shop 1
transport\t0.0\t0.0
fleet\t3\t3.0\t1.0\t2\t60.0\tnearest
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t1\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t4.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t4.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t1.0\t6.0\t0.0\t-\tL
release\tr\t25\t20.0\t60.0\t0.0\t-\tH
price\tA\t2000000.0\t100.0
price\tB\t500000.0\t50.0
node\te\t0.0\t0.0
node\ta\t10.0\t0.0
node\tm\t20.0\t0.0
node\tb\t120.0\t0.0
node\tx\t130.0\t0.0
node\tu\t130.0\t10.0
node\tv\t0.0\t10.0
link\te\ta\t10.0
link\ta\tm\t10.0
link\tm\tb\t100.0
link\tb\tx\t10.0
link\tx\tu\t10.0
link\tu\tv\t130.0
link\tv\te\t10.0
stop\tA\t0\ta
stop\tB\t0\tb
entry\te
exit\tx
";

fn own() -> Shop {
    Shop::parse(OWN).unwrap()
}

fn go(s: &Shop, days: f64) -> RunResult {
    run(s, &RunOptions { seed: 5, until: Some(days * 1440.0), record: true }, None)
}

#[test]
fn wafers_out_and_cycle_time_by_littles_law() {
    let s = own();
    let r = go(&s, 1.0);
    let sc = score(&s, &r, &Settings::default(), 60.0);
    let wafers: i64 = r.lots.iter().filter(|l| l.done.is_some_and(|d| d <= r.until)).map(|l| l.size).sum();
    assert!((sc.wafers_per_day - wafers as f64 / 1.0).abs() < 1e-9, "{} vs {wafers}", sc.wafers_per_day);
    assert!(sc.wafers_per_day > 0.0);
    // the average wafers in the fab, sampled each frame, over wafers out a day
    let m = Moods::new(&s, &r, &Settings::default());
    let frames: Vec<f64> = (0..=24).map(|k| k as f64 * 60.0).collect();
    let wip: f64 = frames.iter().map(|&t| m.at(t).lots.iter().filter(|l| l.mood != "grad").count() as f64 * 25.0).sum::<f64>() / frames.len() as f64;
    assert!((sc.cycle_days - wip / sc.wafers_per_day).abs() < 1e-9, "{} vs {}", sc.cycle_days, wip / sc.wafers_per_day);
}

#[test]
fn the_worst_queue_is_the_largest_group_queue_in_any_frame() {
    let s = own();
    let r = go(&s, 1.0);
    let set = Settings::default();
    let sc = score(&s, &r, &set, 60.0);
    let m = Moods::new(&s, &r, &set);
    let mut worst = (String::new(), 0usize);
    for k in 0..=24 {
        for g in &s.groups {
            let q = m.group_queue(&g.name, k as f64 * 60.0);
            if q > worst.1 {
                worst = (g.name.clone(), q);
            }
        }
    }
    assert_eq!((sc.worst_group.clone(), sc.worst_queue), worst);
}

#[test]
fn a_free_running_fab_has_no_jams_and_spend_is_prices_times_counts() {
    let s = own();
    let r = go(&s, 0.5);
    let sc = score(&s, &r, &Settings::default(), 60.0);
    assert_eq!(sc.jams, 0, "three vehicles on a long loop do not jam");
    assert_eq!(sc.spend_usd, Some(2_500_000.0));
    let mut bare = s.clone();
    bare.plan.as_mut().unwrap().prices.clear();
    assert_eq!(score(&bare, &go(&bare, 0.5), &Settings::default(), 60.0).spend_usd, None);
}

#[test]
fn a_replay_window_is_exact() {
    let s = own();
    let r = go(&s, 1.0);
    let (from, to) = (600.0, 630.0);
    let w = replay(&s, &r, from, to);
    assert!(!w.is_empty());
    for st in &w {
        assert!(st.t_out >= from && st.t_in <= to, "{st:?} overlaps the window");
    }
    let mut by_vehicle: std::collections::BTreeMap<u32, Vec<&fabsim::moods::Stay>> = Default::default();
    for st in &w {
        by_vehicle.entry(st.vehicle).or_default().push(st);
    }
    for v in by_vehicle.values() {
        for p in v.windows(2) {
            assert!(p[1].t_in >= p[0].t_out - 1e-9, "no overlap: {:?} {:?}", p[0], p[1]);
            assert_eq!(p[1].from, p[0].to, "each stay starts where the last ended");
        }
    }
    assert!(w.iter().any(|st| st.loaded));
}

#[test]
fn hot_lots_ride_hot() {
    let s = own();
    let r = go(&s, 1.0);
    let w = replay(&s, &r, 0.0, 1440.0);
    assert!(w.iter().any(|st| st.hot), "an H lot rides somewhere");
    assert!(w.iter().all(|st| !st.hot || st.loaded));
}

#[test]
fn the_commands_answer() {
    let d = std::env::temp_dir().join(format!("fabgym-replay-{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("own.fab.txt");
    std::fs::write(&f, OWN).unwrap();
    let bin = env!("CARGO_BIN_EXE_fabsim");
    let out = std::process::Command::new(bin).args(["replay", f.to_str().unwrap(), "5", "--from", "600", "--to", "615"]).output().unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let v: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(!v["stays"].as_array().unwrap().is_empty());
    let out = std::process::Command::new(bin).args(["moods", f.to_str().unwrap(), "5", "--until", "720", "--every", "60"]).output().unwrap();
    let v: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(v["score"]["wafers_per_day"].as_f64().unwrap() > 0.0);
    assert_eq!(v["group_names"].as_array().unwrap().len(), 2);
    assert_eq!(v["frames"][3]["queues"].as_array().unwrap().len(), 2);
    let _ = std::fs::remove_dir_all(&d);
}
