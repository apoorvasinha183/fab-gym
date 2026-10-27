//! fabrule score RULE.rs (--shop FILE | --smt2020 DIR) [--scenario FILE] (--train A..B | --held-out)
//!               [--threads N] [--cache DIR]
//!
//! Prints one JSON object: the report (docs/AGENT.md), or {"ok": false, "stage": ..., "error": ...}.

use std::path::PathBuf;
use std::process::ExitCode;

use fabrule::{compile, score_rule, Seeds};
use fabsim::scenario::Scenario;
use fabsim::shop::Shop;

fn quote(s: &str) -> String {
    let mut o = String::from("\"");
    for ch in s.chars() {
        match ch {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

fn fail(stage: &str, error: &str) -> ExitCode {
    println!(
        "{{\"ok\": false, \"stage\": {}, \"error\": {}}}",
        quote(stage),
        quote(error)
    );
    ExitCode::from(2)
}

fn usage() -> ExitCode {
    eprintln!("usage: fabrule score RULE.rs (--shop FILE | --smt2020 DIR) [--scenario FILE] (--train A..B | --held-out) [--threads N] [--cache DIR]");
    ExitCode::from(64)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(|s| s.as_str()) != Some("score") || args.len() < 2 {
        return usage();
    }
    let rule = PathBuf::from(&args[1]);
    let (mut shop_file, mut smt, mut scenario, mut train, mut held_out) =
        (None, None, None, None, false);
    let mut threads = 4usize;
    let mut cache = PathBuf::from("target/fabrule-cache");
    let mut i = 2;
    while i < args.len() {
        let val = args.get(i + 1).cloned();
        match (args[i].as_str(), val) {
            ("--shop", Some(v)) => shop_file = Some(PathBuf::from(v)),
            ("--smt2020", Some(v)) => smt = Some(PathBuf::from(v)),
            ("--scenario", Some(v)) => scenario = Some(PathBuf::from(v)),
            ("--train", Some(v)) => train = Some(v),
            ("--threads", Some(v)) => threads = v.parse().unwrap_or(4).clamp(1, 4),
            ("--cache", Some(v)) => cache = PathBuf::from(v),
            ("--held-out", _) => {
                held_out = true;
                i += 1;
                continue;
            }
            _ => return usage(),
        }
        i += 2;
    }
    let seeds = match (train, held_out) {
        (Some(_), true) | (None, false) => {
            return fail("args", "give exactly one of --train A..B and --held-out")
        }
        (None, true) => Seeds::HeldOut,
        (Some(r), false) => {
            let parts: Vec<&str> = r.split("..").collect();
            match (
                parts.len(),
                parts.first().and_then(|a| a.parse::<u64>().ok()),
                parts.get(1).and_then(|b| b.parse::<u64>().ok()),
            ) {
                (2, Some(a), Some(b)) if a < b => Seeds::Train((a..b).collect()),
                _ => return fail("args", "--train takes A..B, for example 100..110"),
            }
        }
    };
    let shop = match (shop_file, smt) {
        (Some(f), None) => match std::fs::read_to_string(&f)
            .map_err(|e| e.to_string())
            .and_then(|t| Shop::parse(&t))
        {
            Ok(s) => s,
            Err(e) => return fail("shop", &format!("{}: {e}", f.display())),
        },
        (None, Some(d)) => match fabsim::smt2020::load(&d) {
            Ok(s) => s,
            Err(e) => return fail("shop", &format!("{}: {e}", d.display())),
        },
        _ => return fail("args", "give exactly one of --shop and --smt2020"),
    };
    let scenario = match scenario {
        None => None,
        Some(f) => match std::fs::read_to_string(&f)
            .map_err(|e| e.to_string())
            .and_then(|t| Scenario::parse(&t))
        {
            Ok(s) => Some(s),
            Err(e) => return fail("scenario", &format!("{}: {e}", f.display())),
        },
    };
    let src = match std::fs::read_to_string(&rule) {
        Ok(s) => s,
        Err(e) => return fail("args", &format!("{}: {e}", rule.display())),
    };
    if let Err(e) = fabrule::check_source(&src) {
        return fail("check", &e);
    }
    let wasm = match compile(&src, &cache) {
        Ok(w) => w,
        Err(e) => return fail("compile", &e),
    };
    match score_rule(&shop, scenario.as_ref(), &wasm, &seeds, threads) {
        Ok(r) => {
            println!("{}", r.to_json());
            ExitCode::SUCCESS
        }
        Err(e) => fail(
            if e.starts_with("refused") {
                "load"
            } else {
                "score"
            },
            &e,
        ),
    }
}
