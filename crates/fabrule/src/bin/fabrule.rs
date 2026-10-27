//! fabrule score RULE.rs (--shop FILE | --smt2020 DIR) [--scenario FILE] (--train A..B | --held-out)
//!               [--threads N] [--cache DIR]
//!
//! Prints one JSON object: the report (docs/AGENT.md), or {"ok": false, "stage": ..., "error": ...}.
//!
//! fabrule trace RULE.rs [--real] [--data D] [--plan P] [--seed S] [--day N] [--hours H] [--smt2020 DIR]
//!               --out FILE
//!
//! Runs the campus's shop (D/P.shop.txt) under the rule and writes the trace `fabsim layout-trace` writes,
//! with the same defaults (docs/REPLAY.md).

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
    eprintln!("       fabrule trace RULE.rs [--real] [--data D] [--plan P] [--seed S] [--day N] [--hours H] --out FILE");
    ExitCode::from(64)
}

fn flag(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned()
}

fn trace(args: &[String]) -> ExitCode {
    use fabsim::engine::RunOptions;
    use fabsim::layout::{Config, Problem};
    if args.len() < 2 {
        return usage();
    }
    let real = args.iter().any(|a| a == "--real");
    let cfg = if real { Config::realistic() } else { Config::gigafab() };
    let data = PathBuf::from(flag(args, "--data").unwrap_or_else(|| (if real { "data/layout-real" } else { "data/layout" }).into()));
    let dir = PathBuf::from(flag(args, "--smt2020").unwrap_or_else(|| "data/smt2020/hvlm".into()));
    let plan = flag(args, "--plan").unwrap_or_else(|| "optimised".into());
    let num = |name: &str, d: u64| -> Result<u64, String> {
        flag(args, name).map(|v| v.parse::<u64>().map_err(|_| format!("{name} takes a whole number"))).unwrap_or(Ok(d))
    };
    let (seed, day, hours) = match (num("--seed", 3000), num("--day", 30), num("--hours", 6)) {
        (Ok(a), Ok(b), Ok(c)) => (a, b, c),
        (Err(e), _, _) | (_, Err(e), _) | (_, _, Err(e)) => return fail("args", &e),
    };
    let Some(out) = flag(args, "--out").map(PathBuf::from) else { return fail("args", "--out FILE is needed") };
    let cache = PathBuf::from(flag(args, "--cache").unwrap_or_else(|| "target/fabrule-cache".into()));
    let src = match std::fs::read_to_string(&args[1]) {
        Ok(s) => s,
        Err(e) => return fail("args", &format!("{}: {e}", args[1])),
    };
    let wasm = match compile(&src, &cache) {
        Ok(w) => w,
        Err(e) => return fail(if e.starts_with("refused") { "check" } else { "compile" }, &e),
    };
    let mut rule = match fabrule::Rule::load(&wasm) {
        Ok(r) => r,
        Err(e) => return fail("load", &e),
    };
    let shop_file = data.join(format!("{plan}.shop.txt"));
    let shop = match std::fs::read_to_string(&shop_file).map_err(|e| e.to_string()).and_then(|t| Shop::parse(&t)) {
        Ok(s) => s,
        Err(e) => return fail("shop", &format!("{}: {e} (run fabsim layout first)", shop_file.display())),
    };
    // the campus is rebuilt by the same deterministic optimiser fabsim uses, and checked against the shop
    let (flat, areas) = match (fabsim::smt2020::load(&dir), fabsim::smt2020::areas(&dir)) {
        (Ok(f), Ok(a)) => (f, a),
        (Err(e), _) | (_, Err(e)) => return fail("shop", &e),
    };
    let p = match Problem::new(&flat, &areas, &cfg) {
        Ok(p) => p,
        Err(e) => return fail("shop", &e),
    };
    let c = if plan == "plain" { p.pack(&p.plain()) } else { p.pack(&p.optimise()) };
    if Some(p.oht(&c)) != shop.oht {
        return fail("shop", &format!("the shop's layout is not this build's {plan} plan; rerun fabsim layout"));
    }
    let from = day as f64 * 1440.0;
    let to = from + hours as f64 * 60.0;
    let rr = rule.run(&shop, &RunOptions { seed, until: Some(to + 5.0 * 1440.0), record: true });
    if let Err(e) = std::fs::write(&out, p.trace_json(&c, &rr.result, from, to)) {
        return fail("write", &format!("{}: {e}", out.display()));
    }
    println!(
        "{{\"ok\": true, \"out\": {}, \"decisions\": {}, \"faults\": {}}}",
        quote(&out.display().to_string()),
        rr.decisions,
        rr.faults
    );
    ExitCode::SUCCESS
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(|s| s.as_str()) == Some("trace") {
        return trace(&args);
    }
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
