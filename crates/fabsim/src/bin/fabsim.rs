//! fabsim: run the simulator from the command line.
//!
//!   fabsim bench [DIR] [--days N] [--seeds K]   time runs on the SMT2020 model
//!   fabsim log SHOP SEED [UNTIL]                 print the canonical log of a shop file
//!   fabsim score SCENARIO [DIR] [--seeds A..B] [--threads T]
//!                                                score a scenario (docs/ASK.md); JSON on stdout
//!   fabsim lean-long [DIR] [--threads T] [--out O] [--reference] [--days N --warmup W --seeds K]
//!                                                the pre-registered long-run lean question
//!                                                (docs/LEAN-LONG.md); the overrides are for
//!                                                smoke runs only; --reference reads the
//!                                                files as the reference compile does
//!   fabsim layout [DIR] [--out O] [--data D] [--iters N] [--restarts R] [--seed S] [--chase M] [--cross M]
//!                                                the gigafab-style campus (docs/FAB-LAYOUT.md):
//!                                                plain and optimised plans; layout.json and a
//!                                                summary to O, the shops with layouts to D
//!   fabsim layout-score [DIR] [--data D] [--out O] [--threads T] [--days N --warmup W --seeds K]
//!                                                H2: the two plans (and SMT2020's flat transport)
//!                                                on paired seeds
//!   fabsim layout-trace [DIR] [--data D] [--plan P] [--seed S] [--day N] [--hours H] [--chase M] [--cross M]
//!                                                a recorded window of the run on plan P for the
//!                                                3D views: D/trace-P.json
//!   each layout command takes --real: tools at true size by kind and each group in the phase
//!   that sends it most lots (docs/FAB-LOOK.md); defaults then go to results/layout-real and
//!   data/layout-real

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
    let reference = args.iter().any(|a| a == "--reference");
    let shop = if reference { fabsim::smt2020::load_reference(&dir) } else { fabsim::smt2020::load(&dir) }.expect("SMT2020 loads");
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
    let _ = writeln!(md, "On the SMT2020 model. {} seeds ({}..{}), {days} days, window days {warmup} to {days}. Each cap minus no cap at the same breakdown rate, paired; intervals Bonferroni over {cells} cells (each at level {:.4}), so all cover at once with probability at least 95%. Real-fab effect: cannot say. Files read {}.{}\n",
        seeds.len(), seeds[0], seeds[seeds.len() - 1], alpha,
        if reference { "as the reference compile reads them (first maintenance in days taken as minutes)" } else { "with their units" },
        if preregistered { "" } else { " SMOKE RUN: not the pre-registered design." });
    let mut json = String::from("{\"model\":\"SMT2020\",\"preregistered\":");
    let _ = write!(json, "{preregistered},\"reference_reading\":{reference},\"days\":{days},\"warmup\":{warmup},\"seeds\":{:?},\"alpha_each\":{alpha},\"seconds\":{secs:.1},\"cells\":[", seeds);
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

fn flag<'a>(args: &'a [String], flag: &str, default: &'a str) -> &'a str {
    args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).map(|s| s.as_str()).unwrap_or(default)
}

/// `--real`: the realistic campus (docs/FAB-LOOK.md) and its default folders.
fn layout_kind(args: &[String]) -> (fabsim::layout::Config, &'static str, &'static str) {
    use fabsim::layout::Config;
    if args.iter().any(|a| a == "--real") {
        (Config::realistic(), "results/layout-real", "data/layout-real")
    } else {
        (Config::gigafab(), "results/layout", "data/layout")
    }
}

fn layout(args: &[String]) {
    use fabsim::layout::Problem;
    use std::fmt::Write as _;
    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let (mut cfg, out0, data0) = layout_kind(args);
    let out = PathBuf::from(flag(args, "--out", out0));
    let data = PathBuf::from(flag(args, "--data", data0));
    cfg.iters = arg(args, "--iters", cfg.iters as u64) as usize;
    cfg.restarts = arg(args, "--restarts", cfg.restarts as u64) as usize;
    cfg.seed = arg(args, "--seed", cfg.seed);
    // a wider service chase (docs/PERMIT.md, D10): metres, assumed 1.5
    cfg.chase = flag(args, "--chase", "").parse().unwrap_or(cfg.chase);
    // a cross aisle at mid-depth on every wall (docs/DESIGN-DEV.md): metres, none by default
    cfg.cross = flag(args, "--cross", "").parse().unwrap_or(cfg.cross);
    let shop = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let areas = fabsim::smt2020::areas(&dir).expect("areas");
    let p = Problem::new(&shop, &areas, &cfg).expect("a layout problem");
    let t0 = Instant::now();
    let plain = p.pack(&p.plain());
    let best = p.pack(&p.optimise());
    let secs = t0.elapsed().as_secs_f64();
    std::fs::create_dir_all(&out).unwrap();
    std::fs::create_dir_all(&data).unwrap();
    std::fs::write(out.join("layout.json"), p.to_json(&[("plain", &plain), ("optimised", &best)])).unwrap();
    for (name, c) in [("plain", &plain), ("optimised", &best)] {
        let mut s = shop.clone();
        s.oht = Some(p.oht(c));
        std::fs::write(data.join(format!("{name}.shop.txt")), s.to_text()).unwrap();
    }
    let lots: f64 = p.flows().iter().map(|f| f.2).sum();
    let mut md = String::new();
    let _ = writeln!(md, "A gigafab-style layout of our own design on the SMT2020 model (docs/FAB-LAYOUT.md); every placement number is assumed. Not a real fab.\n");
    if cfg.phase_by_flow || !cfg.kinds.is_empty() {
        let _ = writeln!(md, "Realistic campus (docs/FAB-LOOK.md): tools at true size by kind from the size book, each tool group in the phase that sends it most of its lots.\n");
    }
    let _ = writeln!(md, "Optimiser: simulated annealing, {} moves x {} restarts, seed {}, {secs:.1} s. A heuristic; the metres are exact for the stated flows.\n", cfg.iters, cfg.restarts, cfg.seed);
    let _ = writeln!(md, "Moves a day at the release rates: {lots:.1}; crossing the bridge: {:.1} a day.\n", p.crossings());
    let _ = writeln!(md, "| plan | OHT metres a day | metres a move | P1 length (north / south) | P2 length (north / south) |\n|---|---|---|---|---|");
    for (name, c) in [("plain", &plain), ("optimised", &best)] {
        let m = p.cost(c);
        let _ = writeln!(md, "| {name} | {m:.0} | {:.1} | {:.0} ({:.0} / {:.0}) | {:.0} ({:.0} / {:.0}) |", m / lots,
            c.lengths[0], c.sides[0][0], c.sides[0][1], c.lengths[1], c.sides[1][0], c.sides[1][1]);
    }
    let (a, b) = (p.cost(&plain), p.cost(&best));
    let _ = writeln!(md, "\nThe optimised plan carries {:.1}% fewer metres a day.", 100.0 * (a - b) / a);
    std::fs::write(out.join("summary.md"), &md).unwrap();
    println!("{md}");
}

fn layout_score(args: &[String]) {
    use fabsim::uq::{paired, verdict, Verdict};
    use fabsim::window::{score, with_probes, Window};
    use std::fmt::Write as _;
    use std::sync::Mutex;
    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let (_, out0, data0) = layout_kind(args);
    let data = PathBuf::from(flag(args, "--data", data0));
    let out = PathBuf::from(flag(args, "--out", out0));
    let threads = arg(args, "--threads", 4) as usize;
    let days = arg(args, "--days", 150) as f64;
    let warmup = arg(args, "--warmup", 60) as f64;
    let nseeds = arg(args, "--seeds", 10);
    let preregistered = days == 150.0 && warmup == 60.0 && nseeds == 10;
    let seeds: Vec<u64> = (3000..3000 + nseeds).collect();
    let w = Window { from: warmup * 1440.0, to: days * 1440.0 };
    let read = |n: &str| Shop::parse(&std::fs::read_to_string(data.join(format!("{n}.shop.txt"))).expect("run fabsim layout first")).unwrap();
    let flat = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let arms: Vec<(&str, Shop)> = vec![("plain", read("plain")), ("optimised", read("optimised")), ("smt2020-flat", flat)];
    let arms: Vec<(&str, Shop)> = arms.into_iter().map(|(n, s)| (n, with_probes(&s, &w))).collect();
    let jobs: Vec<(usize, u64)> = (0..arms.len()).flat_map(|a| seeds.iter().map(move |&s| (a, s))).collect();
    eprintln!("{} runs of {days} days (window {warmup}-{days}), {threads} threads", jobs.len());
    let t0 = Instant::now();
    let res: Mutex<Vec<Option<[f64; 5]>>> = Mutex::new(vec![None; jobs.len()]);
    let next = std::sync::atomic::AtomicUsize::new(0);
    std::thread::scope(|sc| {
        for _ in 0..threads.max(1) {
            sc.spawn(|| loop {
                let i = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                if i >= jobs.len() {
                    break;
                }
                let (a, seed) = jobs[i];
                let r = run(&arms[a].1, &RunOptions { seed, until: Some(w.to), record: false }, None);
                let s = score(&r, &w).unwrap();
                let pa = r.probes.iter().find(|p| p.t == w.from).unwrap();
                let pb = r.probes.iter().find(|p| p.t == w.to).unwrap();
                let tpm = (pb.transport_minutes - pa.transport_minutes) / (pb.transports - pa.transports) as f64;
                let row = [tpm, s.cycle_days, s.wafers_per_day, s.mean_wip, s.hot_cycle_days.unwrap_or(f64::NAN)];
                eprintln!("  {} seed {seed}: {:?}", arms[a].0, row);
                res.lock().unwrap()[i] = Some(row);
            });
        }
    });
    let secs = t0.elapsed().as_secs_f64();
    let res: Vec<[f64; 5]> = res.into_inner().unwrap().into_iter().map(|x| x.unwrap()).collect();
    let n = seeds.len();
    let col = |a: usize, k: usize| -> Vec<f64> { (0..n).map(|i| res[a * n + i][k]).collect() };
    let names = [("transport minutes a move", false), ("cycle time, days", false), ("wafers out a day", true), ("mean WIP, lots", false), ("hot-lot cycle time, days", false)];
    let alpha = 0.05 / names.len() as f64;
    let mut md = String::new();
    let _ = writeln!(md, "On the SMT2020 model, a gigafab-style layout of our own design. Seeds {}..{} paired, {days} days, window days {warmup} to {days}, {secs:.0} s. Optimised minus plain, paired t intervals at level {alpha:.3} each (Bonferroni over {} measures, so all cover at once with probability at least 95%). SMT2020's flat transport is for reference only. Real-fab effect: cannot say.{}\n",
        seeds[0], seeds[n - 1], names.len(), if preregistered { "" } else { " SMOKE RUN: not the pre-registered design." });
    let _ = writeln!(md, "| measure | plain | optimised | optimised minus plain (95%) | verdict | SMT2020 flat |\n|---|---|---|---|---|---|");
    let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
    let mut json = format!("{{\"model\":\"SMT2020\",\"preregistered\":{preregistered},\"days\":{days},\"warmup\":{warmup},\"seeds\":{seeds:?},\"alpha_each\":{alpha},\"measures\":[");
    for (k, (name, higher)) in names.iter().enumerate() {
        let (a, b, f) = (col(0, k), col(1, k), col(2, k));
        let iv = paired(&a, &b, alpha);
        let v = if iv.lo.is_nan() { Verdict::CannotSay } else { verdict(&iv, *higher) };
        let word = match v { Verdict::Better => "better", Verdict::Worse => "worse", Verdict::CannotSay => "no clear effect" };
        let _ = writeln!(md, "| {name} | {:.3} | {:.3} | {:+.3} ({:+.3} to {:+.3}) | {word} | {:.3} |", mean(&a), mean(&b), iv.mean, iv.lo, iv.hi, mean(&f));
        let _ = write!(json, "{}{{\"name\":\"{name}\",\"plain\":{a:?},\"optimised\":{b:?},\"flat\":{f:?},\"mean\":{},\"lo\":{},\"hi\":{},\"verdict\":\"{word}\"}}", if k > 0 { "," } else { "" }, iv.mean, iv.lo, iv.hi);
    }
    json.push_str("]}");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("score.md"), &md).unwrap();
    std::fs::write(out.join("score.json"), json.replace("NaN", "null")).unwrap();
    println!("{md}");
}

fn layout_trace(args: &[String]) {
    use fabsim::layout::Problem;
    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let (mut cfg, _, data0) = layout_kind(args);
    // the same chase the layout was built with (docs/DESIGN-DEV.md, DD2)
    cfg.chase = flag(args, "--chase", "").parse().unwrap_or(cfg.chase);
    cfg.cross = flag(args, "--cross", "").parse().unwrap_or(cfg.cross);
    let data = PathBuf::from(flag(args, "--data", data0));
    let plan = flag(args, "--plan", "optimised");
    let seed = arg(args, "--seed", 3000);
    let from = arg(args, "--day", 30) as f64 * 1440.0;
    let to = from + arg(args, "--hours", 6) as f64 * 60.0;
    let shop = Shop::parse(&std::fs::read_to_string(data.join(format!("{plan}.shop.txt"))).expect("run fabsim layout first")).unwrap();
    // the campus is rebuilt from the same deterministic optimiser, and checked against the shop's places
    let flat = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let areas = fabsim::smt2020::areas(&dir).expect("areas");
    let p = Problem::new(&flat, &areas, &cfg).unwrap();
    let c = if plan == "plain" { p.pack(&p.plain()) } else { p.pack(&p.optimise()) };
    assert_eq!(Some(p.oht(&c)), shop.oht, "the shop's layout is not this build's {plan} plan; rerun fabsim layout");
    // run past the window so lots that arrive in it and start later are recorded
    let r = run(&shop, &RunOptions { seed, until: Some(to + 5.0 * 1440.0), record: true }, None);
    let out = data.join(format!("trace-{plan}.json"));
    std::fs::write(&out, p.trace_json(&c, &r, from, to)).unwrap();
    println!("wrote {}", out.display());
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
        Some("layout") => layout(&args[1..]),
        Some("layout-score") => layout_score(&args[1..]),
        Some("layout-trace") => layout_trace(&args[1..]),
        Some("score") => {
            let text = std::fs::read_to_string(&args[1]).expect("read the scenario");
            let dir = args.get(2).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
            let mut p = fabsim::score::Protocol { threads: arg(&args, "--threads", 4) as usize, ..Default::default() };
            if let Some(r) = args.iter().position(|a| a == "--seeds").and_then(|i| args.get(i + 1)) {
                let (a, b) = r.split_once("..").expect("--seeds A..B");
                p.seeds = (a.parse::<u64>().unwrap()..b.parse::<u64>().unwrap()).collect();
            }
            let shop = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
            match fabsim::scenario::Scenario::parse(&text).and_then(|sc| fabsim::score::score(&shop, &sc, &p)) {
                Ok(r) => println!("{}", r.to_json()),
                Err(e) => {
                    eprintln!("refused: {e}");
                    std::process::exit(2);
                }
            }
        }
        _ => eprintln!("usage: fabsim bench [DIR] [--days N] [--seeds K] | fabsim log SHOP SEED [UNTIL]"),
    }
}
