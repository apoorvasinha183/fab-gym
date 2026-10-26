//! fabsim: run the simulator from the command line.
//!
//!   fabsim bench [DIR] [--days N] [--seeds K]   time runs on the SMT2020 model
//!   fabsim log SHOP SEED [UNTIL]                 print the canonical log of a shop file

use std::path::PathBuf;
use std::time::Instant;

use fabsim::engine::{run, Decision, RunOptions};
use fabsim::shop::Shop;

fn arg(args: &[String], flag: &str, default: u64) -> u64 {
    args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).map(|v| v.parse().unwrap()).unwrap_or(default)
}

fn bench(args: &[String]) {
    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let days = arg(args, "--days", 30);
    let seeds = arg(args, "--seeds", 5);
    let t0 = Instant::now();
    let shop = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    println!("load: {:.3} s ({} groups, {} tools, {} lots in progress)", t0.elapsed().as_secs_f64(),
        shop.groups.len(), shop.groups.iter().map(|g| g.count).sum::<usize>(), shop.lots.len());
    println!("on the SMT2020 model, {days} simulated days, seeds 0..{seeds}, one core");
    for (label, record, chooser) in [("totals only", false, false), ("full record", true, false), ("choice point (default rule)", false, true)] {
        let mut secs = vec![];
        let mut decisions = 0u64;
        let mut moves = 0i64;
        for seed in 0..seeds {
            let opts = RunOptions { seed, until: Some(1440.0 * days as f64), record };
            let t = Instant::now();
            let res = if chooser {
                let mut pick = |d: &Decision| d.default;
                run(&shop, &opts, Some(&mut pick))
            } else {
                run(&shop, &opts, None)
            };
            secs.push(t.elapsed().as_secs_f64());
            decisions += res.decisions;
            moves += res.moves;
        }
        let total: f64 = secs.iter().sum();
        let per_day = total / (seeds * days) as f64;
        println!(
            "{label:>28}: {:.3} s a run, {:.4} s a simulated day, {:.0} decisions/s, {:.0} moves/s",
            total / seeds as f64,
            per_day,
            decisions as f64 / total,
            moves as f64 / total
        );
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(|s| s.as_str()) {
        Some("bench") => bench(&args[1..]),
        Some("log") => {
            let shop = Shop::parse(&std::fs::read_to_string(&args[1]).unwrap()).unwrap();
            let seed = args[2].parse().unwrap();
            let until = args.get(3).map(|u| u.parse().unwrap());
            print!("{}", run(&shop, &RunOptions { seed, until, record: true }, None).log_text());
        }
        _ => eprintln!("usage: fabsim bench [DIR] [--days N] [--seeds K] | fabsim log SHOP SEED [UNTIL]"),
    }
}
