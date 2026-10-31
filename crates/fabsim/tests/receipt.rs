//! The run referee's receipts (docs/LEAN-CHECK.md, tests R1 to R6). Written before the code. From the SMT2020
//! testbed's rules, with the toy shops for speed; R6 runs on the SMT2020 files when they are present.

mod common;

use fabsim::engine::{run, RunOptions, RunResult};
use fabsim::gym::{episode, episode_recorded};
use fabsim::receipt::{exact, from_exact, tamper, write, Meta, TAMPER_KINDS};
use fabsim::shop::Shop;
use fabsim::window::Window;

fn toy() -> Shop {
    Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap()
}

const UNTIL: f64 = 4.0 * 1440.0;
const W: Window = Window { from: 1440.0, to: UNTIL };

fn meta(seed: u64) -> Meta {
    Meta { shop_sha256: "0".repeat(64), seed, policy: "today".into(), until: UNTIL, from: W.from, to: W.to }
}

fn recorded(shop: &Shop, seed: u64) -> RunResult {
    run(shop, &RunOptions { seed, until: Some(UNTIL), record: true }, None)
}

/// The fields of a line, split on single spaces.
fn fields(l: &str) -> Vec<&str> {
    l.split(' ').collect()
}

fn time(s: &str) -> f64 {
    from_exact(s).unwrap_or_else(|| panic!("not an exact time: {s}"))
}

#[test]
fn r1_every_started_step_and_state_change_in_order() {
    let shop = toy();
    for seed in 0..6u64 {
        let r = recorded(&shop, seed);
        let text = write(&shop, &r, &meta(seed)).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines[0], "fabgym-receipt 1");
        // the jobs' lots, in order, are the run's trace
        let mut jobs: Vec<(u32, u64, u64, u32, u32)> = vec![];
        let mut states: Vec<(u32, u64)> = vec![];
        let (mut last_t, mut last_kind) = (f64::NEG_INFINITY, 'S');
        let mut seen_event = false;
        for l in &lines[1..] {
            let f = fields(l);
            match f[0] {
                "S" | "J" => {
                    seen_event = true;
                    let t = time(f[2]);
                    let kind = f[0].chars().next().unwrap();
                    assert!(t > last_t || (t == last_t && !(last_kind == 'J' && kind == 'S')), "seed {seed}: out of order at {l}");
                    last_t = t;
                    last_kind = kind;
                    if kind == 'S' {
                        states.push((f[1].parse().unwrap(), t.to_bits()));
                    } else {
                        let n: usize = f[4].parse().unwrap();
                        assert_eq!(f.len(), 5 + 3 * n, "seed {seed}: {l}");
                        for k in 0..n {
                            jobs.push((f[1].parse().unwrap(), t.to_bits(), time(f[3]).to_bits(), f[5 + 3 * k].parse().unwrap(), f[6 + 3 * k].parse().unwrap()));
                        }
                    }
                }
                "end" => {}
                _ => assert!(!seen_event, "seed {seed}: header line after an event: {l}"),
            }
        }
        // the receipt's events in time order, each kind in the engine's own order: compare as sorted lists
        let mut want: Vec<(u32, u64, u64, u32, u32)> =
            r.trace.iter().map(|x| (x.tool, x.start.to_bits(), x.end.to_bits(), x.lot, x.step)).collect();
        let mut got = jobs.clone();
        want.sort();
        got.sort();
        assert_eq!(got, want, "seed {seed}: jobs differ from the trace");
        let want_s: Vec<(u32, u64)> = r.states.iter().map(|s| (s.tool_index, s.time.to_bits())).collect();
        assert_eq!(states, want_s, "seed {seed}: state changes differ from the log, or are out of the log's order");
        let end = fields(lines.last().unwrap());
        assert_eq!(end[0], "end");
        assert_eq!(end[2].parse::<usize>().unwrap(), r.states.len());
    }
}

#[test]
fn r2_times_are_the_engines_f64_exactly() {
    let shop = toy();
    let r = recorded(&shop, 2);
    for x in r.trace.iter().flat_map(|x| [x.arrive, x.start, x.end]).chain([0.0, 0.5, 1.0 / 3.0, 1e-300, 123456.789]) {
        let s = exact(x).unwrap();
        assert_eq!(from_exact(&s).unwrap().to_bits(), x.to_bits(), "{x} written as {s}");
        if let Some((m, e)) = s.split_once('/') {
            assert!(m.parse::<u128>().unwrap() % 2 == 1, "{s}: an even numerator over a power of two is not in lowest terms");
            assert!(e.parse::<u32>().unwrap() > 0);
        }
    }
    assert!(exact(-1.0).is_none(), "times are never negative");
    assert!(exact(f64::INFINITY).is_none());
}

#[test]
fn r3_claimed_breaches_are_the_engines() {
    let shop = toy();
    let mut any = 0;
    for seed in 0..12u64 {
        let r = recorded(&shop, seed);
        let text = write(&shop, &r, &meta(seed)).unwrap();
        let end = fields(text.lines().last().unwrap());
        let total = r.breaches.len();
        let window = r.breaches.iter().filter(|b| b.t > W.from && b.t <= W.to).count();
        assert_eq!(end[3].parse::<usize>().unwrap(), total, "seed {seed}");
        assert_eq!(end[4].parse::<usize>().unwrap(), window, "seed {seed}");
        any += total;
    }
    assert!(any > 0, "the toy runs should hold at least one breach, or this test checks nothing");
}

#[test]
fn r4_writing_a_receipt_changes_nothing() {
    let shop = toy();
    for seed in [0u64, 3] {
        let mut a = |d: &fabsim::engine::Decision, _o: &[usize], _r: f64| Some(d.candidates.len() - 1);
        let plain = episode(&shop, seed, W, &mut a);
        let mut b = |d: &fabsim::engine::Decision, _o: &[usize], _r: f64| Some(d.candidates.len() - 1);
        let (rec, res) = episode_recorded(&shop, seed, W, &mut b);
        assert_eq!(rec.picks, plain.picks, "seed {seed}");
        assert_eq!(format!("{:?}", rec.score), format!("{:?}", plain.score), "seed {seed}");
        let m = meta(seed);
        assert_eq!(write(&shop, &res, &m).unwrap(), write(&shop, &res, &m).unwrap());
    }
}

#[test]
fn r5_one_broken_copy_per_rule() {
    let shop = toy();
    let r = recorded(&shop, 1);
    let good = write(&shop, &r, &meta(1)).unwrap();
    assert_eq!(TAMPER_KINDS, ["overlap", "skip", "overfill", "into-down", "breach"]);
    for kind in TAMPER_KINDS {
        let bad = tamper(&good, kind).unwrap_or_else(|e| panic!("{kind}: {e}"));
        let (g, b): (Vec<&str>, Vec<&str>) = (good.lines().collect(), bad.lines().collect());
        assert_eq!(g.len(), b.len(), "{kind}: a tampered copy changes one record in place");
        let differ = g.iter().zip(&b).filter(|(x, y)| x != y).count();
        assert_eq!(differ, 1, "{kind}: {differ} records differ");
    }
    assert!(tamper(&good, "nonsense").is_err());
}

#[test]
fn r6_a_replayed_run_gives_the_same_receipt() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let w = Window { from: 1440.0, to: 2.0 * 1440.0 };
    let mut fifo = fabsim::policy::picker(&shop, fabsim::policy::Policy::Fifo, 0);
    let mut ask = |d: &fabsim::engine::Decision, _o: &[usize], _r: f64| Some(fifo(d));
    let (first, res) = episode_recorded(&shop, 0, w, &mut ask);
    let picks = first.picks.clone();
    let mut k = 0usize;
    let mut replay = |_d: &fabsim::engine::Decision, _o: &[usize], _r: f64| {
        k += 1;
        Some(picks[k - 1] as usize)
    };
    let (second, res2) = episode_recorded(&shop, 0, w, &mut replay);
    assert_eq!(second.picks, first.picks);
    let m = Meta { shop_sha256: "0".repeat(64), seed: 0, policy: "fifo".into(), until: w.to, from: w.from, to: w.to };
    assert_eq!(write(&shop, &res, &m).unwrap(), write(&shop, &res2, &m).unwrap());
}
