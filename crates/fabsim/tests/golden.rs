//! The simulator reproduces the reference engine's log exactly on the same shop and seed.

mod common;

use fabsim::engine::{run, RunOptions};
use fabsim::hash::sha256_hex;
use fabsim::shop::Shop;

fn toy(name: &str) -> (Shop, RunOptions) {
    let text = common::read(&format!("golden/toy/{name}.shop.txt"));
    let shop = Shop::parse(&text).expect("toy shop parses");
    let meta = common::read(&format!("golden/toy/{name}.run.json"));
    let seed: u64 = meta.split("\"seed\": ").nth(1).unwrap().split([',', '}']).next().unwrap().trim().parse().unwrap();
    let until_s = meta.split("\"until\": ").nth(1).unwrap().split([',', '}']).next().unwrap().trim();
    let until = if until_s == "null" { None } else { Some(until_s.parse().unwrap()) };
    (shop, RunOptions { seed, until, record: true })
}

#[test]
fn shop_text_round_trips() {
    for name in ["tiny", "mixed", "capped"] {
        let text = common::read(&format!("golden/toy/{name}.shop.txt"));
        let shop = Shop::parse(&text).unwrap();
        common::assert_same_text(&shop.to_text(), &text, name);
    }
}

#[test]
fn toy_logs_match_reference() {
    for name in ["tiny", "mixed", "capped"] {
        let (shop, opts) = toy(name);
        let res = run(&shop, &opts, None);
        let want = common::read(&format!("golden/toy/{name}.log.txt"));
        common::assert_same_text(&res.log_text(), &want, name);
    }
}

#[test]
fn smt2020_shop_matches_reference_compile() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let text = shop.to_text();
    let golden = common::repo().join("data/golden/smt2020.shop.txt");
    if let Ok(want) = std::fs::read_to_string(&golden) {
        common::assert_same_text(&text, &want, "SMT2020 shop");
    }
    let (hash, lines) = common::recorded_hash("shop");
    assert_eq!(text.lines().count(), lines);
    assert_eq!(sha256_hex(text.as_bytes()), hash);
}

fn smt2020_run(seed: u64, days: u32) {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let opts = RunOptions { seed, until: Some(1440.0 * days as f64), record: true };
    let text = run(&shop, &opts, None).log_text();
    let name = format!("smt2020.seed{seed}.{days}d.log.txt");
    if let Ok(want) = std::fs::read_to_string(common::repo().join("data/golden").join(&name)) {
        common::assert_same_text(&text, &want, &name);
    }
    let (hash, lines) = common::recorded_hash(&name);
    assert_eq!(text.lines().count(), lines, "{name} line count");
    assert_eq!(sha256_hex(text.as_bytes()), hash, "{name} hash");
}

#[test]
fn smt2020_seed0_one_day_matches_reference() {
    smt2020_run(0, 1);
}

#[test]
fn smt2020_seed1_one_day_matches_reference() {
    smt2020_run(1, 1);
}

#[test]
fn smt2020_seed2_one_day_matches_reference() {
    smt2020_run(2, 1);
}

#[test]
fn smt2020_seed0_three_days_matches_reference() {
    smt2020_run(0, 3);
}
