//! fabsim: run the simulator from the command line.
//!
//!   fabsim bench [DIR] [--days N] [--seeds K]   time runs on the SMT2020 model
//!   fabsim log SHOP SEED [UNTIL]                 print the canonical log of a shop file
//!   fabsim lean-long [DIR] [--threads T] [--out O] [--days N --warmup W --seeds K]
//!                                                the pre-registered long-run lean question
//!                                                (docs/LEAN-LONG.md); the overrides are for
//!                                                smoke runs only

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

fn lean_long(args: &[String]) {
    use fabsim::dials::Dials;
    use fabsim::sweep::{paired_vs, run_grid, Config};
    use fabsim::uq::{crossover, verdict, Crossover, Interval};
    use fabsim::window::{Window, WindowScore};
    use std::fmt::Write as _;

    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let threads = arg(args, "--threads", 4) as usize;
    let days = arg(args, "--days", 300) as f64;
    let warmup = arg(args, "--warmup", 120) as f64;
    let nseeds = arg(args, "--seeds", 10);
    let out = PathBuf::from(args.iter().position(|a| a == "--out").and_then(|i| args.get(i + 1)).map(|s| s.as_str()).unwrap_or("results/lean-long"));
    let preregistered = days == 300.0 && warmup == 120.0 && nseeds == 10;
    let ks = [1.0, 1.5, 2.0];
    let caps: [Option<i64>; 6] = [None, Some(1800), Some(2100), Some(2400), Some(2700), Some(3000)];
    let seeds: Vec<u64> = (1000..1000 + nseeds).collect();
    let w = Window { from: warmup * 1440.0, to: days * 1440.0 };
    let shop = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let mut configs = vec![];
    for &k in &ks {
        for &cap in &caps {
            let label = format!("k={k} cap={}", cap.map(|c| c.to_string()).unwrap_or("none".into()));
            configs.push(Config { label, dials: Dials { breakdowns: k, cap, ..Dials::default() } });
        }
    }
    eprintln!("{} cells x {} seeds, {days} days (window {warmup}-{days}), {threads} threads", configs.len(), seeds.len());
    let t0 = Instant::now();
    let rows = run_grid(&shop, &configs, &seeds, w.to, &w, threads).expect("grid runs");
    let secs = t0.elapsed().as_secs_f64();
    eprintln!("done in {secs:.0} s");
    std::fs::create_dir_all(&out).unwrap();
    let mut tsv = String::from("k\tcap\tseed\tlots_per_day\twafers_per_day\tmean_wip\tcycle_days\thot_lots\thot_cycle_days\n");
    for r in &rows {
        let c = &configs[r.config].dials;
        let s = &r.score;
        let _ = writeln!(tsv, "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}", c.breakdowns, c.cap.map(|x| x.to_string()).unwrap_or("none".into()), r.seed,
            s.lots_per_day, s.wafers_per_day, s.mean_wip, s.cycle_days, s.hot_lots, s.hot_cycle_days.unwrap_or(f64::NAN));
    }
    std::fs::write(out.join("runs.tsv"), tsv).unwrap();

    let cells = (ks.len() * (caps.len() - 1)) as f64;
    let alpha = 0.05 / cells;
    let mean = |c: usize, f: &dyn Fn(&WindowScore) -> f64| {
        let v: Vec<f64> = rows.iter().filter(|r| r.config == c).map(|r| f(&r.score)).collect();
        v.iter().sum::<f64>() / v.len() as f64
    };
    let metrics: [(&str, &str, bool, &dyn Fn(&WindowScore) -> f64); 3] = [
        ("wafers_per_day", "wafers out a day", true, &|s: &WindowScore| s.wafers_per_day),
        ("cycle_days", "cycle time, days", false, &|s: &WindowScore| s.cycle_days),
        ("hot_cycle_days", "hot-lot cycle time, days", false, &|s: &WindowScore| s.hot_cycle_days.unwrap_or(f64::NAN)),
    ];
    let fmt_iv = |iv: &Interval| format!("{:+.2} ({:+.2} to {:+.2})", iv.mean, iv.lo, iv.hi);
    let mut md = String::new();
    let _ = writeln!(md, "On the SMT2020 model. {} seeds ({}..{}), {days} days, window days {warmup} to {days}. Each cap minus no cap at the same breakdown rate, paired; intervals Bonferroni over {cells} cells (each at level {:.4}), so all cover at once with probability at least 95%. Real-fab effect: cannot say.{}\n",
        seeds.len(), seeds[0], seeds[seeds.len() - 1], alpha, if preregistered { "" } else { " SMOKE RUN: not the pre-registered design." });
    let mut json = String::from("{\"model\":\"SMT2020\",\"preregistered\":");
    let _ = write!(json, "{preregistered},\"days\":{days},\"warmup\":{warmup},\"seeds\":{:?},\"alpha_each\":{alpha},\"seconds\":{secs:.1},\"cells\":[", seeds);
    let mut first = true;
    for (key, name, higher, f) in metrics.iter() {
        let _ = writeln!(md, "### {name}\n\n| breakdowns | no cap (mean) | {} |\n|---|---|{}", caps[1..].iter().map(|c| format!("cap {}", c.unwrap())).collect::<Vec<_>>().join(" | "), "---|".repeat(caps.len() - 1));
        for (ki, &k) in ks.iter().enumerate() {
            let base = ki * caps.len();
            let mut line = format!("| x{k} | {:.2} |", mean(base, *f));
            for ci in 1..caps.len() {
                let iv = paired_vs(&rows, base, base + ci, |s| f(s), alpha);
                let v = verdict(&iv, *higher);
                let _ = write!(line, " {} {} |", fmt_iv(&iv), match v { fabsim::uq::Verdict::Better => "better", fabsim::uq::Verdict::Worse => "worse", _ => "unclear" });
                if !first { json.push(','); }
                first = false;
                let _ = write!(json, "{{\"metric\":\"{key}\",\"k\":{k},\"cap\":{},\"base_mean\":{},\"cap_mean\":{},\"mean\":{},\"lo\":{},\"hi\":{},\"verdict\":\"{}\"}}",
                    caps[ci].unwrap(), mean(base, *f), mean(base + ci, *f), iv.mean, iv.lo, iv.hi, v.label());
            }
            let _ = writeln!(md, "{line}");
        }
        let _ = writeln!(md);
    }
    let _ = writeln!(md, "### Where each cap stops being free (wafers out, over breakdown rate)\n");
    json.push_str("],\"flips\":[");
    for ci in 1..caps.len() {
        let pts: Vec<(f64, Interval)> = ks.iter().enumerate().map(|(ki, &k)| {
            let base = ki * caps.len();
            (k, paired_vs(&rows, base, base + ci, |s| s.wafers_per_day, alpha))
        }).collect();
        let free: Vec<String> = pts.iter().map(|(k, iv)| format!("x{k}: {}", if verdict(iv, true) == fabsim::uq::Verdict::Worse { "costs wafers" } else { "free" })).collect();
        let cx = crossover(&pts);
        let txt = match &cx {
            Crossover::None(v) => format!("same verdict at every rate: {}", v.label()),
            Crossover::Partial(v) => format!("{} at some rates, no clear effect at the others", v.label()),
            Crossover::Unclear => "no clear effect at any rate".into(),
            Crossover::Between { last_clear_before, first_clear_after, unclear } => format!("flips between x{last_clear_before} and x{first_clear_after} (unclear at {unclear:?})"),
            Crossover::Several(v) => format!("flips more than once: {v:?}"),
        };
        let _ = writeln!(md, "- cap {}: {} — {}", caps[ci].unwrap(), free.join(", "), txt);
        if ci > 1 { json.push(','); }
        let _ = write!(json, "{{\"cap\":{},\"free\":[{}],\"crossover\":\"{}\"}}", caps[ci].unwrap(),
            pts.iter().map(|(_, iv)| (verdict(iv, true) != fabsim::uq::Verdict::Worse).to_string()).collect::<Vec<_>>().join(","), txt.replace('"', "'"));
    }
    json.push_str("]}\n");
    std::fs::write(out.join("summary.json"), json).unwrap();
    std::fs::write(out.join("summary.md"), &md).unwrap();
    println!("{md}");
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
        Some("web-data") => {
            // the shop text and each group's area, for the browser page (not committed)
            let out = PathBuf::from(args.get(1).map(|s| s.as_str()).unwrap_or("web/data"));
            let dir = PathBuf::from(args.get(2).map(|s| s.as_str()).unwrap_or("data/smt2020/hvlm"));
            std::fs::create_dir_all(&out).unwrap();
            let shop = fabsim::smt2020::load(&dir).unwrap();
            std::fs::write(out.join("shop.txt"), shop.to_text()).unwrap();
            let areas: String = fabsim::smt2020::areas(&dir).unwrap().iter().map(|(g, a)| format!("{g}\t{a}\n")).collect();
            std::fs::write(out.join("areas.tsv"), areas).unwrap();
            println!("wrote {}", out.display());
        }
        Some("lean-long") => lean_long(&args[1..]),
        _ => eprintln!("usage: fabsim bench [DIR] [--days N] [--seeds K] | fabsim log SHOP SEED [UNTIL]"),
    }
}
