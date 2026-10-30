//! Moods from a run (docs/RUN-MOODS.md). Written before the code. On the SMT2020 model and small shops of our own.

mod common;

use fabsim::engine::{run, run_with, RunOptions, RunResult};
use fabsim::moods::{snapshot, Settings, Snapshot};
use fabsim::overrides::Overrides;
use fabsim::shop::Shop;

fn one_tool(every: f64, minutes: f64, extra: &str) -> Shop {
    Shop::parse(&format!(
        "fabgym-shop 1\ntransport\t0.0\t0.0\ngroup\tA\t1\t0.0\t0.0\t-\t-\t-\nroute\tr\nstep\tA\tlot\t{minutes:?}\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\nrelease\tr\t25\t1.0\t{every:?}\t0.0\t-\tL\n{extra}"
    ))
    .unwrap()
}

fn go(s: &Shop, days: f64) -> RunResult {
    run(s, &RunOptions { seed: 3, until: Some(days * 1440.0), record: true }, None)
}

fn tool<'a>(snap: &'a Snapshot, name: &str) -> &'a str {
    snap.tools.iter().find(|t| t.tool == name).unwrap_or_else(|| panic!("no tool {name}")).mood
}

fn lot<'a>(snap: &'a Snapshot, id: &str) -> Option<&'a fabsim::moods::LotMood> {
    snap.lots.iter().find(|l| l.lot == id)
}

// ---- 1. downs ----

#[test]
fn down_states_map_to_their_moods() {
    let Some(dir) = common::smt2020_dir() else { return };
    let mut s = fabsim::smt2020::load_reference(&dir).unwrap();
    s.defects = Some(fabsim::shop::Defects { hold_tool_minutes: 60.0, lookback_minutes: 120.0, hold_lot_minutes: 60.0 });
    let r = go(&s, 3.0);
    let set = Settings::default();
    // each state row with the time its tool next changed state
    let rows = &r.states;
    let until = |i: usize| rows[i + 1..].iter().find(|x| x.tool_index == rows[i].tool_index).map(|x| x.time).unwrap_or(f64::INFINITY);
    let mut seen = std::collections::HashSet::new();
    for i in 0..rows.len() {
        let (a, b) = (rows[i].time, until(i));
        let (st, why) = (rows[i].state, rows[i].why);
        let want: Vec<(f64, &str)> = match (st, why) {
            ("unscheduled down", "hold") if b - a > 2.0 => vec![(a + 1.0, "hold")],
            ("unscheduled down", "") if b - a > 20.0 => vec![(a + 1.0, "hurt"), (a + 16.0, "physio")],
            ("scheduled down", "setup") if b - a > 0.2 => vec![(a + (b - a) / 2.0, "setup")],
            ("scheduled down", "") if b - a > 2.0 => vec![(a + 1.0, "pm")],
            _ => vec![],
        };
        for (t, mood) in want {
            if seen.contains(mood) {
                continue;
            }
            let snap = snapshot(&s, &r, t, &set);
            assert_eq!(tool(&snap, &rows[i].tool), mood, "{} at {t} ({st}, {why:?})", rows[i].tool);
            seen.insert(mood);
        }
    }
    for m in ["hurt", "physio", "setup", "pm", "hold"] {
        assert!(seen.contains(m), "the run shows {m} somewhere");
    }
}

// ---- 2 and 3. dozing, gassed, waiting for the class ----

#[test]
fn little_work_dozes_and_too_much_is_gassed() {
    let set = Settings::default();
    let light = one_tool(600.0, 5.0, "");
    assert_eq!(tool(&snapshot(&light, &go(&light, 2.0), 2000.0, &set), "A#1"), "sleep");
    let heavy = one_tool(4.0, 5.0, "");
    assert_eq!(tool(&snapshot(&heavy, &go(&heavy, 2.0), 1000.0, &set), "A#1"), "tired");
}

#[test]
fn a_batch_tool_with_too_few_lots_waits_for_the_class() {
    let s = Shop::parse("fabgym-shop 1\ntransport\t0.0\t0.0\ngroup\tB\t1\t0.0\t0.0\t-\t-\t-\nroute\tr\nstep\tB\tbatch\t30.0\t0.0\t4.0\t4.0\t-\t-\t-\t-\t-\t-\t-\t-\nrelease\tr\t25\t1.0\t600.0\t0.0\t-\tL\n").unwrap();
    assert_eq!(tool(&snapshot(&s, &go(&s, 2.0), 700.0, &Settings::default()), "B#1"), "batch");
}

// ---- 4 and 5. hands full, and the lots ----

/// Two tools on a loop with one vehicle and one port; A is fast, so its finished lots wait for the vehicle.
const OWN: &str = "fabgym-shop 1
transport\t0.0\t0.0
fleet\t1\t3.0\t1.0\t1\t60.0\tnearest
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t1\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t1.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t1.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t1.0\t2.0\t0.0\t-\tL
release\tr\t25\t20.0\t240.0\t0.0\t-\tH
node\te\t0.0\t0.0
node\ta\t10.0\t0.0
node\tm\t20.0\t0.0
node\tb\t200.0\t0.0
node\tx\t210.0\t0.0
node\tu\t210.0\t10.0
node\tv\t0.0\t10.0
link\te\ta\t10.0
link\ta\tm\t10.0
link\tm\tb\t180.0
link\tb\tx\t10.0
link\tx\tu\t10.0
link\tu\tv\t210.0
link\tv\te\t10.0
stop\tA\t0\ta
stop\tB\t0\tb
entry\te
exit\tx
";

fn frames(s: &Shop, r: &RunResult, every: f64) -> Vec<Snapshot> {
    let set = Settings::default();
    (1..((r.until / every) as usize)).map(|k| snapshot(s, r, k as f64 * every, &set)).collect()
}

#[test]
fn a_fast_tool_with_one_slow_vehicle_has_its_hands_full() {
    let s = Shop::parse(OWN).unwrap();
    let r = go(&s, 1.0);
    assert!(frames(&s, &r, 10.0).iter().any(|f| tool(f, "A#1") == "full"));
}

#[test]
fn lots_finish_work_wait_and_ride() {
    let set = Settings::default();
    let light = one_tool(600.0, 5.0, "");
    let r = go(&light, 2.0);
    let l1 = r.lots.iter().find(|l| l.release == 600.0).expect("the lot released at 600");
    let st = &l1.steps[0];
    assert_eq!(lot(&snapshot(&light, &r, (st.start + st.end) / 2.0, &set), &l1.id).unwrap().mood, "bench");
    assert_eq!(lot(&snapshot(&light, &r, st.end + 50.0, &set), &l1.id).unwrap().mood, "grad");
    assert!(lot(&snapshot(&light, &r, 599.0, &set), &l1.id).is_none(), "not released yet");

    let heavy = one_tool(4.0, 5.0, "");
    let r = go(&heavy, 4.0);
    let at = |t: f64| snapshot(&heavy, &r, t, &set);
    let waiting_since = |t: f64, from: f64, to: f64| {
        r.lots.iter().find(|l| l.release >= from && l.release <= to && l.steps.first().is_none_or(|s| s.start > t)).expect("a lot waiting").id.clone()
    };
    let t = 4000.0;
    let fresh = waiting_since(t, t - 30.0, t - 1.0);
    assert_eq!(lot(&at(t), &fresh).unwrap().mood, "fresh");
    let line = waiting_since(t, t - 300.0, t - 100.0);
    assert_eq!(lot(&at(t), &line).unwrap().mood, "line");
    let old = waiting_since(t, 0.0, t - 600.0);
    assert_eq!(lot(&at(t), &old).unwrap().mood, "impatient");

    let own = Shop::parse(OWN).unwrap();
    let r = go(&own, 1.0);
    let fs = frames(&own, &r, 1.0);
    assert!(fs.iter().any(|f| f.lots.iter().any(|l| l.mood == "ride")), "some lot rides the rail");
    assert!(fs.iter().any(|f| f.lots.iter().any(|l| l.hot && l.lot.starts_with('H'))), "the H lots are hot");
    assert!(fs.iter().all(|f| f.lots.iter().all(|l| l.hot == l.lot.starts_with('H'))));
}

// ---- 6. queue-time limits ----

#[test]
fn a_breach_shows_missed_and_a_running_limit_shows_on_the_clock() {
    let Some(dir) = common::smt2020_dir() else { return };
    let s = fabsim::smt2020::load_reference(&dir).unwrap();
    let r = go(&s, 3.0);
    let set = Settings::default();
    let b = r.breaches.first().expect("a breach in three days");
    assert_eq!(lot(&snapshot(&s, &r, b.t - 0.01, &set), &b.lot).unwrap().mood, "missed");
    // a lot that finished a step with a limit and started the next well inside it
    let mut found = false;
    'outer: for l in &r.lots {
        let route = s.route(&l.route).unwrap();
        for w in l.steps.windows(2) {
            if let Some((_, limit)) = route.steps[w[0].step].cqt {
                if w[1].start - w[0].end > 2.0 && w[1].start - w[0].end < limit && w[1].step == w[0].step + 1 {
                    let t = w[0].end + 1.0;
                    assert_eq!(lot(&snapshot(&s, &r, t, &set), &l.id).unwrap().mood, "clock", "{} at {t}", l.id);
                    found = true;
                    break 'outer;
                }
            }
        }
    }
    assert!(found, "some lot waits inside a limit");
}

// ---- 7. jam ----

#[test]
fn a_stretch_behind_a_broken_one_jams() {
    let s = Shop::parse(OWN).unwrap();
    let jam = |r: &RunResult| -> f64 { frames(&s, r, 30.0).iter().map(|f| f.rails.iter().find(|x| x.stretch == "a>m").unwrap().jam).sum() };
    let o = RunOptions { seed: 3, until: Some(1440.0), record: true };
    let base = run(&s, &o, None);
    let ov = Overrides::parse(r#"{"fabgym-overrides": 1, "rails": {"m>b": {"breakdowns": {"kind": "random", "mttf_minutes": 60, "mttr_minutes": 60}, "recovery": {"kind": "wait"}}}}"#, &s).unwrap();
    let broken = run_with(&s, &o, None, &ov);
    assert!(jam(&broken) > jam(&base), "{} vs {}", jam(&broken), jam(&base));
}

// ---- 8. the command ----

#[test]
fn the_moods_command_writes_a_frame_every_so_often() {
    let d = std::env::temp_dir().join(format!("fabgym-moods-{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("light.shop.txt");
    std::fs::write(&f, one_tool(600.0, 5.0, "").to_text()).unwrap();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_fabsim"))
        .args(["moods", f.to_str().unwrap(), "1", "--until", "1440", "--every", "60"])
        .output()
        .unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let v: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(v["frames"].as_array().unwrap().len(), 25);
    assert_eq!(v["tools"].as_array().unwrap().len(), 1);
    assert!(v["frames"].as_array().unwrap().iter().all(|fr| fr["tools"].as_array().unwrap().len() == 1));
    assert_eq!(v["tool_moods"].as_array().unwrap().len(), 10);
    assert_eq!(v["lot_moods"].as_array().unwrap().len(), 12);
    let _ = std::fs::remove_dir_all(&d);
}
