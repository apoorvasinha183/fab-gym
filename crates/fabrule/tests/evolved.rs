//! An evolved rule printed as a sandbox rule runs the same as the tree (docs/EVOLVE.md). Written before the code.

use std::path::PathBuf;

use fabrule::{compile, Rule, CAND_FIELDS};
use fabsim::engine::{run, Decision, RunOptions};
use fabsim::gp;
use fabsim::pyrandom::PyRandom;
use fabsim::shop::Shop;

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

#[test]
fn the_fields_are_the_sandbox_fields() {
    assert_eq!(gp::RULE_FIELDS, CAND_FIELDS);
}

#[test]
fn printed_trees_run_as_the_trees_do() {
    let base = std::fs::read_to_string(repo().join("golden/toy/mixed.shop.txt")).unwrap();
    let shop = Shop::parse(&base).unwrap();
    let mut text = base.clone();
    if !text.ends_with('\n') {
        text.push('\n');
    }
    let routes: Vec<String> = shop.routes.iter().map(|r| r.name.clone()).collect();
    text.push_str(&format!("family\t{}\tA\n", routes[0]));
    for r in &routes[1..] {
        text.push_str(&format!("family\t{r}\tB\n"));
    }
    let two = Shop::parse(&text).unwrap();
    let o = RunOptions { seed: 4, until: Some(2880.0), record: true };
    let fam = gp::family_numbers(&two);
    let mut rng = PyRandom::from_str_seed("printed");
    let cache = repo().join("target/fabrule-cache");
    for _ in 0..4 {
        let e = gp::random_tree(&mut rng, 3, 5);
        let mut pick = |d: &Decision| gp::choose(&e, d, &fam);
        let tree_log = run(&two, &o, Some(&mut pick)).log_text();
        let src = e.to_rust();
        let mut rule = Rule::load(&compile(&src, &cache).unwrap_or_else(|err| panic!("{src}\n{err}"))).unwrap();
        let ran = rule.run(&two, &o);
        assert_eq!(ran.faults, 0, "{src}");
        assert!(ran.result.log_text() == tree_log, "the sandbox and the tree differ for\n{src}");
    }
}
