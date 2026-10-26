//! Shared helpers for the acceptance tests.
#![allow(dead_code)]

use std::path::{Path, PathBuf};

pub fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

pub fn read(rel: &str) -> String {
    let p = repo().join(rel);
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("read {}: {e}", p.display()))
}

/// The SMT2020 high-volume files, if present (they are not committed).
pub fn smt2020_dir() -> Option<PathBuf> {
    let p = std::env::var("FABGYM_SMT2020")
        .map(PathBuf::from)
        .unwrap_or_else(|_| repo().join("data/smt2020/hvlm"));
    if p.join("route_3.txt").exists() {
        Some(p)
    } else {
        eprintln!("SMT2020 files not found at {}; skipping", p.display());
        None
    }
}

/// The recorded SHA-256 and line count for a golden name in golden/smt2020.sha256.
pub fn recorded_hash(name: &str) -> (String, usize) {
    for line in read("golden/smt2020.sha256").lines() {
        let f: Vec<&str> = line.split('\t').collect();
        if f[0] == name {
            return (f[1].to_string(), f[2].parse().unwrap());
        }
    }
    panic!("no recorded hash for {name}");
}

/// Compare two texts line by line and report the first difference.
pub fn assert_same_text(got: &str, want: &str, what: &str) {
    if got == want {
        return;
    }
    let (g, w): (Vec<&str>, Vec<&str>) = (got.lines().collect(), want.lines().collect());
    for i in 0..g.len().max(w.len()) {
        let (a, b) = (g.get(i).copied(), w.get(i).copied());
        if a != b {
            panic!(
                "{what}: first difference at line {}\n  got:  {:?}\n  want: {:?}\n  ({} lines got, {} want)",
                i + 1,
                a,
                b,
                g.len(),
                w.len()
            );
        }
    }
    panic!("{what}: texts differ only in line endings");
}
