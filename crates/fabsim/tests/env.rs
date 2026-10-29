//! `fabsim env`: one dispatch decision at a time, as JSON lines (docs/RL-DEFECTS.md, tests 5 to 7).
//! Written before the code. A toy shop on the SMT2020 model's rules; no real fab.

use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio};

use fabsim::engine::{run, RunOptions};
use fabsim::shop::Shop;
use fabsim::window::{score, with_probes, Window};

const SHOP: &str = "fabgym-shop 1
transport\t5.0\t10.0
group\tA\t2\t1.0\t1.0\t-\t900.0\t45.0
group\tB\t2\t1.0\t1.0\t-\t-\t-
route\tr
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t15.0\t2.0\t-\t-\t-\t-\t-\t-\t0\t0.25\t-\t-
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t12.0\t0.0\t-\tN
release\tr\t25\t20.0\t300.0\t30.0\t-\tH
";
const DEFECTS: &str = "defects\t120\t240\t60\n";
const WARMUP: f64 = 0.5;
const WINDOW: f64 = 1.0;

fn shop_file(text: &str, name: &str) -> std::path::PathBuf {
    let p = std::env::temp_dir().join(format!("fabgym-env-{}-{name}.shop.txt", std::process::id()));
    std::fs::write(&p, text).unwrap();
    p
}

/// a number field of a flat JSON object line (enough for these tests)
fn num(line: &str, key: &str) -> f64 {
    let pat = format!("\"{key}\":");
    let i = line.find(&pat).unwrap_or_else(|| panic!("no {key} in {line}")) + pat.len();
    let rest = line[i..].trim_start();
    let end = rest.find(|c: char| !(c.is_ascii_digit() || "+-.eE".contains(c))).unwrap_or(rest.len());
    rest[..end].parse().unwrap_or_else(|_| panic!("{key} is not a number in {line}"))
}

/// the window's score inside a done line
fn score_of(done: &str) -> &str {
    &done[done.find("\"score\":").expect("a score")..]
}

fn count_cands(line: &str) -> usize {
    let i = line.find("\"cands\":[").expect("cands") + 9;
    let body = &line[i..];
    let mut depth = 0i32;
    let mut n = 0;
    for c in body.chars() {
        match c {
            '{' => {
                if depth == 0 {
                    n += 1;
                }
                depth += 1;
            }
            '}' => depth -= 1,
            ']' if depth == 0 => break,
            _ => {}
        }
    }
    n
}

struct Episode {
    obs: Vec<String>,
    done: String,
}

/// run one episode, answering each observation with `answer(i, line)`
fn episode(text: &str, name: &str, seed: u64, mut answer: impl FnMut(usize, &str) -> String) -> Episode {
    let path = shop_file(text, name);
    let mut child = Command::new(env!("CARGO_BIN_EXE_fabsim"))
        .args(["env", path.to_str().unwrap(), "--seed", &seed.to_string(), "--warmup", &WARMUP.to_string(), "--window", &WINDOW.to_string()])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("fabsim env starts");
    let mut stdin = child.stdin.take().unwrap();
    let out = BufReader::new(child.stdout.take().unwrap());
    let mut obs = vec![];
    let mut done = String::new();
    for line in out.lines() {
        let line = line.unwrap();
        if line.contains("\"done\":true") {
            done = line;
            break;
        }
        let a = answer(obs.len(), &line);
        obs.push(line);
        writeln!(stdin, "{a}").unwrap();
        stdin.flush().unwrap();
    }
    drop(stdin);
    assert!(child.wait().unwrap().success());
    let _ = std::fs::remove_file(path);
    assert!(!done.is_empty(), "the episode ends with a done line");
    Episode { obs, done }
}

fn expected(text: &str, seed: u64) -> fabsim::window::WindowScore {
    let w = Window { from: WARMUP * 1440.0, to: (WARMUP + WINDOW) * 1440.0 };
    let shop = with_probes(&Shop::parse(text).unwrap(), &w);
    let r = run(&shop, &RunOptions { seed, until: Some(w.to), record: false }, None);
    score(&r, &w).unwrap()
}

#[test]
fn engine_picks_score_as_todays_rule() {
    for (text, name) in [(SHOP.to_string(), "off"), (format!("{SHOP}{DEFECTS}"), "on")] {
        for seed in [0u64, 7] {
            let e = episode(&text, name, seed, |_, _| "{\"action\":0}".into());
            let want = expected(&text, seed);
            assert!(e.obs.len() > 20, "{name}: the toy shop should ask some decisions");
            for (k, v) in [("reward", want.reward), ("moves", want.moves), ("lots_finished", want.lots_finished), ("wait_lot_hours", want.wait_lot_hours), ("breaches", want.breaches)] {
                assert!((num(score_of(&e.done), k) - v).abs() < 1e-9, "{name} seed {seed}: {k} {} vs {v}", num(score_of(&e.done), k));
            }
            assert_eq!(num(&e.done, "fallbacks"), 0.0);
        }
    }
}

#[test]
fn rewards_sum_to_the_windows_reward() {
    let mut flip = 0usize;
    let e = episode(&format!("{SHOP}{DEFECTS}"), "sum", 3, |_, line| {
        // pick the last candidate, to move away from today's rule
        flip += 1;
        format!("{{\"action\":{}}}", count_cands(line) - 1)
    });
    let total: f64 = e.obs.iter().map(|o| num(o, "reward")).sum::<f64>() + num(&e.done, "reward");
    let score_reward = num(score_of(&e.done), "reward");
    assert!((total - score_reward).abs() < 1e-9, "{total} vs {score_reward}");
    assert!(flip > 0);
}

#[test]
fn only_real_choices_in_the_window_are_asked_and_bad_answers_fall_back() {
    let mut bad = 0;
    let e = episode(SHOP, "ask", 5, |i, _| {
        if i % 3 == 0 {
            bad += 1;
            if i % 2 == 0 { "{\"action\":99}".into() } else { "not an action".into() }
        } else {
            "{\"action\":0}".into()
        }
    });
    for o in &e.obs {
        assert!(num(o, "t") >= WARMUP * 1440.0, "asked during the warm-up: {o}");
        assert!(count_cands(o) >= 2 && count_cands(o) <= 8, "{o}");
        assert!(o.contains("\"held_tools\":"), "{o}");
    }
    assert_eq!(num(&e.done, "fallbacks"), bad as f64);
    assert_eq!(num(&e.done, "decisions"), e.obs.len() as f64);
    // a fallback is the engine's pick, so the score is today's
    let want = expected(SHOP, 5);
    assert!((num(score_of(&e.done), "moves") - want.moves).abs() < 1e-9);
}

// ---- every built-in rule through the same episode, and the slow measures (docs/LONG-RESCORE.md) ----

#[test]
fn a_built_in_rule_plays_in_the_window_and_todays_rule_in_the_warm_up() {
    use fabsim::gym::episode;
    use fabsim::policy::{picker, Policy};
    let text = SHOP.to_string();
    let shop = Shop::parse(&text).unwrap();
    let w = Window { from: WARMUP * 1440.0, to: (WARMUP + WINDOW) * 1440.0 };
    for p in [Policy::Fifo, Policy::Spt, Policy::CriticalRatio, Policy::Random] {
        let mut pick = picker(&shop, p, 3);
        let mut ask = |d: &fabsim::engine::Decision, _o: &[usize], _r: f64| Some(pick(d));
        let e = episode(&shop, 3, w, &mut ask);
        assert_eq!(e.fallbacks, 0, "{}", p.name());
        assert!(e.asked > 20, "{}: it decides in the window", p.name());
    }
    // the warm-up is today's rule whatever plays the window: a window of nothing scores as today's
    let mut pick = picker(&shop, Policy::Fifo, 3);
    let mut ask = |d: &fabsim::engine::Decision, _o: &[usize], _r: f64| Some(pick(d));
    let none = Window { from: w.to, to: w.to };
    let a = episode(&shop, 3, none, &mut ask);
    let mut today = |d: &fabsim::engine::Decision, _o: &[usize], _r: f64| Some(d.default);
    let b = episode(&shop, 3, none, &mut today);
    assert_eq!(a.score.moves, b.score.moves);
}

#[test]
fn the_env_runs_a_built_in_rule_and_reports_the_slow_measures() {
    let p = shop_file(SHOP, "auto-fifo");
    let out = Command::new(env!("CARGO_BIN_EXE_fabsim"))
        .args(["env", p.to_str().unwrap(), "--seed", "1", "--warmup", "0.5", "--window", "1", "--auto", "fifo"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let done = String::from_utf8(out.stdout).unwrap();
    let done = done.lines().last().unwrap();
    for k in ["cycle_days", "wafers_per_day", "mean_wip", "hot_cycle_days", "moves", "lots_finished"] {
        assert!(done.contains(&format!("\"{k}\":")), "{k} in {done}");
    }
    assert!(done.contains("\"policy\":\"fifo\""));
}
