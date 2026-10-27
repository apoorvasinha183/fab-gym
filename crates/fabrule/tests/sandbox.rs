//! Rules written as Rust functions, run in the sandbox inside the simulator (docs/AGENT.md).
//! Written before the code.

use std::path::PathBuf;
use std::time::Instant;

use fabrule::{check_source, compile, score_rule, Rule, Seeds, MAX_FAULT_SHARE};
use fabsim::engine::RunOptions;
use fabsim::policy::{run_with, Policy};
use fabsim::shop::Shop;

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

fn toy() -> Shop {
    Shop::parse(&std::fs::read_to_string(repo().join("golden/toy/mixed.shop.txt")).unwrap()).unwrap()
}

fn cache() -> PathBuf {
    repo().join("target/fabrule-cache")
}

fn load(src: &str) -> Rule {
    Rule::load(&compile(src, &cache()).unwrap_or_else(|e| panic!("compile: {e}"))).unwrap()
}

fn opts() -> RunOptions {
    RunOptions { seed: 4, until: Some(2880.0), record: true }
}

const FIFO: &str = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { -c.waited_minutes }";
const TODAY: &str = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { if c.is_default > 0.5 { 0.0 } else { 1.0 } }";
const ENDLESS: &str = "pub fn key(c: &Cand, x: &Ctx) -> f64 {
    let mut i = 0u64;
    while x.t >= 0.0 { i = i.wrapping_add(1); std::hint::black_box(i); }
    c.step
}";

// ------------------------------------------------------------------ a rule is the simulator's own choice

#[test]
fn first_in_first_out_written_as_a_rule_is_first_in_first_out() {
    let mut r = load(FIFO);
    let run = r.run(&toy(), &opts());
    assert_eq!(run.result.log_text(), run_with(&toy(), &opts(), Policy::Fifo).log_text());
    assert!(run.decisions > 0);
    assert_eq!(run.faults, 0);
}

#[test]
fn todays_rule_written_as_a_rule_is_todays_rule() {
    let mut r = load(TODAY);
    assert_eq!(r.run(&toy(), &opts()).result.log_text(), run_with(&toy(), &opts(), Policy::Today).log_text());
}

#[test]
fn a_nan_key_counts_as_the_largest_and_is_no_fault() {
    let mut r = load("pub fn key(c: &Cand, _x: &Ctx) -> f64 { if c.is_default > 0.5 { 0.0 } else { f64::NAN } }");
    let run = r.run(&toy(), &opts());
    assert_eq!(run.result.log_text(), run_with(&toy(), &opts(), Policy::Today).log_text());
    assert_eq!(run.faults, 0);
}

#[test]
fn every_field_reaches_the_rule() {
    // a rule that reads every field compiles, and the standard library's maths is there
    let src = "pub fn key(c: &Cand, x: &Ctx) -> f64 {
        c.is_batch + c.lots + c.priority + c.size_wafers + c.step + c.steps_left + c.waited_minutes
        + c.setup_change + c.proc_minutes + c.work_left_minutes + c.age_minutes + c.cqt_slack_minutes.min(1e6)
        + c.is_default + x.t + x.queue + x.working + x.idle + x.down + x.lots_waiting + x.lots_finished
        + c.waited_minutes.sqrt().ln_1p()
    }";
    let run = load(src).run(&toy(), &opts());
    assert!(run.decisions > 0);
    assert_eq!(run.faults, 0);
}

// ------------------------------------------------------------------ what is refused

#[test]
fn sources_that_reach_outside_the_function_are_refused() {
    for bad in [
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { include_str!(\"/etc/passwd\").len() as f64 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { include_bytes!(\"/etc/hosts\").len() as f64 }",
        "include!(\"/tmp/x.rs\");",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { env!(\"HOME\").len() as f64 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { option_env!(\"HOME\").map_or(0.0, |s| s.len() as f64) }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { unsafe { 0.0 } }",
        "extern \"C\" { fn f() -> f64; } pub fn key(c: &Cand, x: &Ctx) -> f64 { 0.0 }",
        "#[no_mangle] pub fn key(c: &Cand, x: &Ctx) -> f64 { 0.0 }",
        "#![allow(unused)] pub fn key(c: &Cand, x: &Ctx) -> f64 { 0.0 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { std::fs::read(\"/etc/hosts\").map_or(0.0, |v| v.len() as f64) }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { let _ = std::net::TcpStream::connect(\"1.1.1.1:80\"); 0.0 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { std::process::exit(0) }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { std::env::args().count() as f64 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { std::thread::yield_now(); 0.0 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { std::time::Instant::now(); 0.0 }",
        "static mut N: f64 = 0.0; pub fn key(c: &Cand, x: &Ctx) -> f64 { 0.0 }",
        "pub fn key(c: &Cand, x: &Ctx) -> f64 { core::arch::asm!(\"nop\"); 0.0 }",
    ] {
        assert!(check_source(bad).is_err(), "not refused: {bad}");
        assert!(compile(bad, &cache()).is_err(), "compiled: {bad}");
    }
    assert!(check_source(FIFO).is_ok());
}

#[test]
fn a_compile_error_comes_back_as_the_compilers_words() {
    let e = compile("pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.nope }", &cache()).unwrap_err();
    assert!(e.contains("nope"), "{e}");
    let e = compile("pub fn rank(c: &Cand, _x: &Ctx) -> f64 { 0.0 }", &cache()).unwrap_err();
    assert!(e.contains("key"), "a source without key: {e}");
}

#[test]
fn a_module_that_imports_anything_is_refused() {
    let wasm = wat_bytes("(module (import \"env\" \"f\" (func)) (func (export \"choose\") (param i32 i32) (result i32) i32.const 0))");
    let e = Rule::load(&wasm).err().expect("refused");
    assert!(e.contains("import"), "{e}");
}

#[test]
fn a_module_asking_for_too_much_memory_is_refused() {
    let wasm = wat_bytes("(module (memory (export \"memory\") 2000) (func (export \"choose\") (param i32 i32) (result i32) i32.const 0))");
    let e = Rule::load(&wasm).err().expect("refused");
    assert!(e.contains("memory"), "{e}");
}

fn wat_bytes(text: &str) -> Vec<u8> {
    // Rule::load reads the WebAssembly text format too (wasmtime's "wat" feature)
    text.as_bytes().to_vec()
}

// ------------------------------------------------------------------ faults fall back to today's pick

#[test]
fn a_rule_that_never_ends_runs_out_of_fuel_and_today_decides() {
    let mut r = load(ENDLESS);
    let t0 = Instant::now();
    let run = r.run(&toy(), &opts());
    assert!(run.decisions > 0);
    assert_eq!(run.faults, run.decisions);
    assert_eq!(run.result.log_text(), run_with(&toy(), &opts(), Policy::Today).log_text());
    assert!(t0.elapsed().as_secs() < 120, "fuel did not stop it soon enough");
}

#[test]
fn a_rule_that_panics_falls_back_and_the_run_completes() {
    let mut r = load("pub fn key(c: &Cand, _x: &Ctx) -> f64 { let v = [0.0f64; 1]; v[c.step as usize + 5] }");
    let run = r.run(&toy(), &opts());
    assert!(run.faults > 0);
    assert_eq!(run.result.log_text(), run_with(&toy(), &opts(), Policy::Today).log_text());
}

// ------------------------------------------------------------------ the compiled modules are kept

#[test]
fn the_same_source_compiles_once() {
    let src = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.proc_minutes - 0.001 * c.waited_minutes }";
    let a = compile(src, &cache()).unwrap();
    let t0 = Instant::now();
    let b = compile(src, &cache()).unwrap();
    assert_eq!(a, b);
    assert!(t0.elapsed().as_millis() < 500, "the second compile was not from the cache");
}

// ------------------------------------------------------------------ scoring

#[test]
fn a_rule_is_scored_against_today_and_every_baseline() {
    let wasm = compile(FIFO, &cache()).unwrap();
    let seeds: Vec<u64> = (100..104).collect();
    let r = score_rule(&toy(), None, &wasm, &Seeds::Train(seeds.clone()), 2).unwrap();
    assert_eq!(r.seeds, seeds);
    assert!(!r.held_out);
    let names: Vec<&str> = r.arms.iter().map(|a| a.name.as_str()).collect();
    assert_eq!(names, ["today", "fifo", "spt", "cr", "rule"]);
    for a in &r.arms {
        assert_eq!(a.scores.len(), seeds.len());
    }
    // the rule is first in first out, so its arm is the fifo arm, seed by seed
    assert_eq!(r.arms[4].scores, r.arms[1].scores);
    let vs_fifo = &r.vs_baselines.iter().find(|(n, _)| n == "fifo").unwrap().1;
    assert_eq!(vs_fifo.mean, 0.0);
    let keys: Vec<&str> = r.vs_today.iter().map(|m| m.key).collect();
    assert_eq!(keys, fabsim::score::MEASURES.iter().map(|m| m.0).collect::<Vec<_>>());
    assert!(r.eligible);
    assert_eq!(r.faults, 0);
    assert!(r.decisions > 0);
    let j = r.to_json();
    for k in ["\"seeds\"", "\"held_out\"", "\"eligible\"", "\"faults\"", "\"decisions\"", "\"vs_today\"", "\"vs_baselines\"", "\"arms\""] {
        assert!(j.contains(k), "{k} missing from the json");
    }
}

#[test]
fn a_faulty_rule_is_not_eligible() {
    let wasm = compile(ENDLESS, &cache()).unwrap();
    let r = score_rule(&toy(), None, &wasm, &Seeds::Train(vec![100, 101]), 2).unwrap();
    assert!(r.faults as f64 > MAX_FAULT_SHARE * r.decisions as f64);
    assert!(!r.eligible);
}

#[test]
fn training_never_touches_the_held_out_seeds() {
    let wasm = compile(FIFO, &cache()).unwrap();
    let e = score_rule(&toy(), None, &wasm, &Seeds::Train(vec![100, 5]), 2).err().expect("refused");
    assert!(e.contains("held-out") || e.contains("100"), "{e}");
    let r = score_rule(&toy(), None, &wasm, &Seeds::HeldOut, 2).unwrap();
    assert_eq!(r.seeds, (0..10).collect::<Vec<u64>>());
    assert!(r.held_out);
}
