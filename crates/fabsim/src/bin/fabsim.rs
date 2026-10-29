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
//!   fabsim evolve [DIR] [--share S] [--threads T] [--sweep D] [--out O] (smoke: --population --generations --iters ...)
//!                                                floor and rules evolved together (docs/EVOLVE.md)
//!   fabsim two-families [DIR] [--threads T] [--out O] [--days N --warmup W --seeds K --iters I]
//!                                                the pre-registered two-family sweep
//!                                                (docs/TWO-FAMILIES-SWEEP.md); overrides are for
//!                                                smoke runs only
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

fn argf(args: &[String], flag: &str, default: f64) -> f64 {
    args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).map(|v| v.parse().unwrap()).unwrap_or(default)
}

fn evolve_cmd(args: &[String]) {
    use fabsim::engine::{run, Decision, RunOptions};
    use fabsim::evolve::{picks, search, Floor, Settings, Space};
    use fabsim::gp::{self, Expr};
    use fabsim::layout::Config as LayoutConfig;
    use fabsim::money::{money, PriceGrid};
    use fabsim::shop::Shop;
    use fabsim::twofam::{apply_policy, b_cap, b_first, contested, lay_out, lay_out_copies, loads, policy_groups, two_family_shop, EngLots, LayoutInfo, Policy, Strategy};
    use fabsim::uq::{paired, verdict, Verdict};
    use fabsim::window::Window;
    use std::collections::HashMap;
    use std::fmt::Write as _;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};

    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let threads = arg(args, "--threads", 4) as usize;
    let share = argf(args, "--share", 4.0);
    let seed = arg(args, "--seed", 1);
    let pop = arg(args, "--population", 16) as usize;
    let gens = arg(args, "--generations", 12) as usize;
    let sdays = argf(args, "--search-days", 240.0);
    let days = argf(args, "--days", 300.0);
    let warmup = argf(args, "--warmup", 120.0);
    let nheld = arg(args, "--seeds", 10);
    let iters = arg(args, "--iters", 20000) as usize;
    let full_iters = arg(args, "--full-iters", 0) as usize;
    let get = |f: &str| args.iter().position(|a| a == f).and_then(|i| args.get(i + 1)).cloned();
    let out = PathBuf::from(get("--out").unwrap_or_else(|| format!("results/evolve-x{share}")));
    let sweep = get("--sweep").map(PathBuf::from);
    let preregistered = pop == 16 && gens == 12 && sdays == 240.0 && days == 300.0 && warmup == 120.0 && nheld == 10 && iters == 20000 && full_iters == 0;
    let t0 = Instant::now();

    let base = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let areas = fabsim::smt2020::areas(&dir).expect("areas load");
    let raw = fabsim::measure::raw_processing_days(&base, 20, 0)["part_3"];
    let e = EngLots { scale: share, ..EngLots::published("part_E3", days * 1440.0, 1) };
    let shop = two_family_shop(&base, "part_3", &e).expect("two families");
    let all = loads(&shop, None);
    let groups = contested(&shop, "B", 12);
    let space = Space::new(groups.clone(), groups.iter().map(|g| all[g]).collect(), 8);
    let avg_lots = e.lots_per_day() * raw;
    let central = PriceGrid::preregistered("B").remove(0);
    let mut cfg_search = LayoutConfig::realistic();
    cfg_search.iters = iters;
    cfg_search.restarts = 1;
    let mut cfg_full = LayoutConfig::realistic();
    if full_iters > 0 {
        cfg_full.iters = full_iters;
        cfg_full.restarts = 1;
    }
    eprintln!("evolve x{share}: candidates {groups:?}; cap base {avg_lots:.1} lots; population {pop}, generations {gens}, {threads} threads");

    type Laid = Arc<(Shop, LayoutInfo)>;
    let cache: Mutex<HashMap<(Vec<usize>, bool), Laid>> = Mutex::new(HashMap::new());
    let lay = |f: &Floor| -> Laid {
        let any = f.tools.iter().any(|&t| t > 0);
        let key = (f.tools.clone(), f.wing && any);
        if let Some(x) = cache.lock().unwrap().get(&key) {
            return x.clone();
        }
        let x = Arc::new(lay_out_copies(&shop, &areas, &cfg_search, &picks(&space, f), key.1, "B").expect("layout"));
        cache.lock().unwrap().insert(key, x.clone());
        x
    };
    let ws = Window { from: warmup * 1440.0, to: sdays * 1440.0 };
    let with_cap = |s: &Shop, f: &Floor| {
        let mut s = s.clone();
        if let Some(m) = space.caps[f.cap] {
            s.famcaps.push(("B".to_string(), (m * avg_lots).ceil() as i64));
        }
        s
    };
    let eval = |f: &Floor, rule: &Expr, sd: u64| -> f64 {
        let laid = lay(f);
        let s = with_cap(&laid.0, f);
        let fam = gp::family_numbers(&s);
        let mut pick = |d: &Decision| gp::choose(rule, d, &fam);
        let r = run(&s, &RunOptions { seed: sd, until: Some(ws.to), record: false }, Some(&mut pick));
        money(&s, &r, &ws, &central, laid.1.tools_added, laid.1.metres_added).per_day
    };
    let set = Settings { population: pop, generations: gens, seed, threads, ..Settings::default() };
    let hist = search(&eval, &space, &set);
    eprintln!("search done in {:.0} s, {} floors laid out", t0.elapsed().as_secs_f64(), cache.lock().unwrap().len());
    std::fs::create_dir_all(out.join("rules")).unwrap();
    let mut tsv = String::from("generation\tindividual\tfitness\tcopies\twing\tcap\trule\n");
    for (g, gen) in hist.generations.iter().enumerate() {
        for (i, ind) in gen.iter().enumerate() {
            let cp: Vec<String> = picks(&space, &ind.floor).iter().map(|(g, t)| format!("{g}x{t}")).collect();
            let cap = space.caps[ind.floor.cap].map(|m| m.to_string()).unwrap_or("none".into());
            let _ = writeln!(tsv, "{g}\t{i}\t{}\t{}\t{}\t{cap}\t{}", ind.fitness, cp.join(","), ind.floor.wing, ind.rule.to_rust().replace('\n', " "));
        }
    }
    std::fs::write(out.join("history.tsv"), tsv).unwrap();

    // the claim: the three best distinct individuals, laid out in full, on the held-out seeds
    let mut every: Vec<&fabsim::evolve::Individual> = hist.generations.iter().flatten().collect();
    every.sort_by(|a, b| b.fitness.total_cmp(&a.fitness));
    let mut top: Vec<&fabsim::evolve::Individual> = vec![];
    for ind in every {
        if !top.iter().any(|t| t.floor == ind.floor && t.rule == ind.rule) {
            top.push(ind);
        }
        if top.len() == 3 {
            break;
        }
    }
    enum Chooser { Today, BFirst, Tree(Expr) }
    struct Arm { label: String, shop: Shop, chooser: Chooser, tools: usize, metres: f64 }
    let mut arms: Vec<Arm> = vec![];
    let (y, yi) = lay_out(&shop, &areas, &cfg_full, &Strategy::Share, "B").expect("yardstick");
    arms.push(Arm { label: "yardstick: D1 share, P0 today".into(), shop: y, chooser: Chooser::Today, tools: yi.tools_added, metres: yi.metres_added });
    // the sweep's best cell at this share, rebuilt
    if let Some(dir) = &sweep {
        let text = std::fs::read_to_string(dir.join("runs.tsv")).expect("the sweep's runs.tsv");
        let mut sums: HashMap<(String, String), (f64, usize)> = HashMap::new();
        for line in text.lines().skip(1) {
            let f: Vec<&str> = line.split('\t').collect();
            if f[0].parse::<f64>().unwrap() == share {
                let m: f64 = f[8].parse().unwrap();
                let e = sums.entry((f[1].to_string(), f[2].to_string())).or_insert((0.0, 0));
                e.0 += m;
                e.1 += 1;
            }
        }
        let best = sums.iter().max_by(|a, b| (a.1 .0 / a.1 .1 as f64).total_cmp(&(b.1 .0 / b.1 .1 as f64))).map(|(k, _)| k.clone()).expect("the sweep has this share");
        let strat = match best.0.as_str() {
            "D1 share" => Strategy::Share,
            "D2 wing" => Strategy::Wing { groups: 3, tools: 1 },
            _ => Strategy::Copies { groups: 3, tools: 1 },
        };
        let p = Policy::ALL.into_iter().find(|p| p.label() == best.1).expect("a policy label");
        let (s, info) = lay_out(&shop, &areas, &cfg_full, &strat, "B").expect("sweep layout");
        let g = policy_groups(&s, "B", 3);
        let s = apply_policy(&s, p, "B", &g, b_cap(&e, raw));
        arms.push(Arm { label: format!("sweep's best: {} {}", best.0, best.1), shop: s, chooser: if p == Policy::BFirst { Chooser::BFirst } else { Chooser::Today }, tools: info.tools_added, metres: info.metres_added });
    }
    let nref = arms.len();
    for (k, ind) in top.iter().enumerate() {
        let (s, info) = lay_out_copies(&shop, &areas, &cfg_full, &picks(&space, &ind.floor), ind.floor.wing && ind.floor.tools.iter().any(|&t| t > 0), "B").expect("layout");
        let s = with_cap(&s, &ind.floor);
        std::fs::write(out.join("rules").join(format!("evolved-{}.rs", k + 1)), ind.rule.to_rust() + "\n").unwrap();
        arms.push(Arm { label: format!("evolved #{}", k + 1), shop: s, chooser: Chooser::Tree(ind.rule.clone()), tools: info.tools_added, metres: info.metres_added });
    }
    let wh = Window { from: warmup * 1440.0, to: days * 1440.0 };
    let seeds: Vec<u64> = (2000..2000 + nheld).collect();
    let jobs: Vec<(usize, u64)> = (0..arms.len()).flat_map(|a| seeds.iter().map(move |&s| (a, s))).collect();
    let next = AtomicUsize::new(0);
    let res: Mutex<Vec<(f64, f64, f64)>> = Mutex::new(vec![(0.0, 0.0, 0.0); jobs.len()]);
    std::thread::scope(|sc| {
        for _ in 0..threads.max(1) {
            sc.spawn(|| loop {
                let j = next.fetch_add(1, Ordering::SeqCst);
                let Some(&(a, sd)) = jobs.get(j) else { break };
                let arm = &arms[a];
                let o = RunOptions { seed: sd, until: Some(wh.to), record: false };
                let r = match &arm.chooser {
                    Chooser::Today => run(&arm.shop, &o, None),
                    Chooser::BFirst => {
                        let mut p = |d: &Decision| b_first(d, "B");
                        run(&arm.shop, &o, Some(&mut p))
                    }
                    Chooser::Tree(t) => {
                        let fam = gp::family_numbers(&arm.shop);
                        let mut p = |d: &Decision| gp::choose(t, d, &fam);
                        run(&arm.shop, &o, Some(&mut p))
                    }
                };
                let m = money(&arm.shop, &r, &wh, &central, arm.tools, arm.metres);
                let ndays = (wh.to - wh.from) / 1440.0;
                let a_w: f64 = r.lots.iter().filter(|l| arm.shop.family_of(&l.route) != "B" && l.done.is_some_and(|d| d > wh.from && d <= wh.to)).map(|l| l.size as f64).sum::<f64>() / ndays;
                res.lock().unwrap()[j] = (m.per_day, a_w, m.b_cycle_days.unwrap_or(f64::NAN));
            });
        }
    });
    let res = res.into_inner().unwrap();
    let col = |a: usize, k: usize| -> Vec<f64> { (0..seeds.len()).map(|i| { let r = res[a * seeds.len() + i]; [r.0, r.1, r.2][k] }).collect() };
    let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
    let ncomp = (nref * top.len()).max(1) as f64;
    let alpha = 0.05 / ncomp;
    let word = |v: Verdict| match v { Verdict::Better => "better", Verdict::Worse => "worse", Verdict::CannotSay => "no clear effect" };
    let mut md = String::new();
    let _ = writeln!(md, "On the SMT2020 model, with a layout of our own design; not a real fab. Family B at x{share}. Search: population {pop}, {gens} generations, training seeds 3000..3002, {sdays} days scored from day {warmup}; layouts at {iters} optimiser moves. Claim: the three best distinct individuals laid out at the full setting, {} held-out seeds ({}..{}), {days} days, window days {warmup} to {days}; paired, Bonferroni over {ncomp} comparisons (each at level {alpha:.4}). Money a day at the central prices, in wafers of family-A margin; every price assumed. Run on {} {}. Real-fab effect: cannot say.{}\n",
        seeds.len(), seeds[0], seeds[seeds.len() - 1], std::env::consts::OS, std::env::consts::ARCH, if preregistered { "" } else { " SMOKE RUN: not the pre-registered design." });
    let _ = writeln!(md, "| arm | money a day | family A wafers a day | family B cycle days | copies | cap | wing |\n|---|---|---|---|---|---|---|");
    for (a, arm) in arms.iter().enumerate() {
        let (cp, cap, wing) = if a >= nref {
            let ind = top[a - nref];
            (picks(&space, &ind.floor).iter().map(|(g, t)| format!("{g}×{t}")).collect::<Vec<_>>().join(", "), space.caps[ind.floor.cap].map(|m| format!("{m}× load")).unwrap_or("none".into()), ind.floor.wing.to_string())
        } else {
            (String::from("as the cell"), String::from("as the cell"), String::from("-"))
        };
        let _ = writeln!(md, "| {} | {:.2} | {:.2} | {:.2} | {cp} | {cap} | {wing} |", arm.label, mean(&col(a, 0)), mean(&col(a, 1)), mean(&col(a, 2)));
    }
    let _ = writeln!(md, "\n### Each evolved individual minus each reference (money a day)\n");
    for k in 0..top.len() {
        for r in 0..nref {
            let iv = paired(&col(r, 0), &col(nref + k, 0), alpha);
            let _ = writeln!(md, "- evolved #{} minus {}: {:+.2} ({:+.2} to {:+.2}), {}", k + 1, arms[r].label, iv.mean, iv.lo, iv.hi, word(verdict(&iv, true)));
        }
    }
    let _ = writeln!(md, "\n### The evolved rules\n");
    for (k, ind) in top.iter().enumerate() {
        let _ = writeln!(md, "evolved #{} (training money {:.2} a day):\n\n```rust\n{}\n```\n", k + 1, ind.fitness, ind.rule.to_rust());
    }
    let best_by_gen: Vec<String> = hist.generations.iter().map(|g| format!("{:.1}", g.iter().map(|i| i.fitness).fold(f64::NEG_INFINITY, f64::max))).collect();
    let _ = writeln!(md, "Best training money by generation: {}", best_by_gen.join(", "));
    std::fs::write(out.join("claim.md"), md).unwrap();
    eprintln!("done in {:.0} s; wrote {}", t0.elapsed().as_secs_f64(), out.display());
}

/// A number for JSON: `null` when it is not finite (JSON has no NaN).
fn jnum(x: f64) -> String {
    if x.is_finite() { format!("{x}") } else { "null".into() }
}

/// The saved two-family sweep as a profit and loss in dollars (docs/MONEY-PL.md): every run and every cell at the
/// central prices, and for the best cell at each share its verdict at each price's low and high. No rerun.
fn pl_cmd(args: &[String]) {
    use fabsim::pl::{price_sweep, sweep_inputs, Sheet};
    use std::fmt::Write as _;
    let dir = PathBuf::from(args.get(0).map(|s| s.as_str()).unwrap_or("results/two-families"));
    let smt = PathBuf::from(args.get(1).map(|s| s.as_str()).unwrap_or("data/smt2020/hvlm"));
    let inp = sweep_inputs(&dir, &smt).unwrap_or_else(|e| panic!("{e}"));
    let central = Sheet::central();
    let p = price_sweep(&inp, &central);
    let iv = |i: &fabsim::uq::Interval| format!("{{\"mean\":{},\"lo\":{},\"hi\":{}}}", jnum(i.mean), jnum(i.lo), jnum(i.hi));
    let opt = |x: Option<f64>| x.map(jnum).unwrap_or_else(|| "null".into());
    let mut o = String::from("{\"model\":\"SMT2020\",\"note\":\"On the SMT2020 model, a published research model of a wafer fab. Every price is assumed. No real fab's prices or data are used.\",");
    let _ = write!(o, "\"alpha_each\":{},\"npv_factor\":{},\"sheet\":[", jnum(p.alpha_each), jnum(fabsim::pl::npv_factor(&central)));
    let items = Sheet::items();
    for (k, it) in items.iter().enumerate() {
        let _ = write!(o, "{}{{\"key\":\"{}\",\"label\":\"{}\",\"unit\":\"{}\",\"central\":{},\"low\":{},\"high\":{},\"assumed\":{}}}",
            if k > 0 { "," } else { "" }, it.key, it.label, it.unit, jnum(it.central), jnum(it.low), jnum(it.high), it.assumed);
    }
    o.push_str("],\"today\":[");
    for (k, t) in p.today.iter().enumerate() {
        let _ = write!(o, "{}{{\"share\":{},\"revenue\":{},\"materials\":{},\"running\":{},\"cash\":{},\"depreciation\":{},\"profit\":{}}}",
            if k > 0 { "," } else { "" }, t.share, jnum(t.revenue), jnum(t.materials), jnum(t.running), jnum(t.cash), jnum(t.depreciation), jnum(t.profit));
    }
    o.push_str("],\"cells\":[");
    for (k, c) in p.cells.iter().enumerate() {
        let _ = write!(o, "{}{{\"share\":{},\"strategy\":\"{}\",\"policy\":\"{}\",\"capital\":{},\"profit\":{},\"cash\":{},\"npv\":{{\"mean\":{},\"lo\":{},\"hi\":{}}},\"payback_days\":{{\"soonest\":{},\"latest\":{}}},\"verdict\":\"{}\"}}",
            if k > 0 { "," } else { "" }, c.share, c.strategy, c.policy, jnum(c.capital), iv(&c.d_profit), iv(&c.d_cash),
            jnum(c.npv.0), jnum(c.npv.1), jnum(c.npv.2), opt(c.payback.0), opt(c.payback.1), c.verdict);
    }
    // the best cell at each share (highest mean change in operating profit), checked at each price's low and high
    o.push_str("],\"checks\":[");
    let mut first = true;
    for t in &p.today {
        let Some(best) = p.cells.iter().filter(|c| c.share == t.share).max_by(|a, b| a.d_profit.mean.total_cmp(&b.d_profit.mean)) else { continue };
        let _ = write!(o, "{}{{\"share\":{},\"strategy\":\"{}\",\"policy\":\"{}\",\"verdict\":\"{}\",\"items\":[", if first { "" } else { "," }, t.share, best.strategy, best.policy, best.verdict);
        first = false;
        let mut f2 = true;
        for it in items.iter().filter(|i| i.low != i.high) {
            let at = |v: f64| {
                let q = price_sweep(&inp, &central.with(it.key, v));
                let c = q.cells.into_iter().find(|c| c.share == best.share && c.strategy == best.strategy && c.policy == best.policy).unwrap();
                (c.verdict, c.d_profit.mean)
            };
            let (lv, lm) = at(it.low);
            let (hv, hm) = at(it.high);
            let _ = write!(o, "{}{{\"key\":\"{}\",\"low\":{{\"verdict\":\"{lv}\",\"mean\":{}}},\"high\":{{\"verdict\":\"{hv}\",\"mean\":{}}}}}", if f2 { "" } else { "," }, it.key, jnum(lm), jnum(hm));
            f2 = false;
        }
        o.push_str("]}");
    }
    o.push_str("]}\n");
    let out = dir.join("pl.json");
    std::fs::write(&out, o).unwrap();
    let mut tsv = String::from("share\tstrategy\tpolicy\tseed\trevenue\tmaterials\trunning\tcash\tdepreciation\tprofit\n");
    for r in &p.runs {
        let _ = writeln!(tsv, "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}", r.share, r.strategy, r.policy, r.seed, r.pl.revenue, r.pl.materials, r.pl.running, r.pl.cash, r.pl.depreciation, r.pl.profit);
    }
    std::fs::write(dir.join("pl-runs.tsv"), tsv).unwrap();
    println!("wrote {} and pl-runs.tsv", out.display());
}

fn two_families(args: &[String]) {
    use fabsim::layout::Config as LayoutConfig;
    use fabsim::money::PriceGrid;
    use fabsim::twofam::{apply_policy, b_cap, lay_out, policy_groups, run_cells, two_family_shop, Cell, EngLots, Policy, Strategy};
    use fabsim::uq::{crossover, paired, verdict, Crossover, Interval, Verdict};
    use fabsim::window::Window;
    use std::fmt::Write as _;

    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let threads = arg(args, "--threads", 4) as usize;
    let days = arg(args, "--days", 300) as f64;
    let warmup = arg(args, "--warmup", 120) as f64;
    let nseeds = arg(args, "--seeds", 10);
    let iters = arg(args, "--iters", 0) as usize;
    let out = PathBuf::from(args.iter().position(|a| a == "--out").and_then(|i| args.get(i + 1)).map(|s| s.as_str()).unwrap_or("results/two-families"));
    let preregistered = days == 300.0 && warmup == 120.0 && nseeds == 10 && iters == 0;
    let shares = [1.0, 2.0, 4.0, 8.0];
    let strategies = [("D1 share", Strategy::Share), ("D2 wing", Strategy::Wing { groups: 3, tools: 1 }), ("D3 copies", Strategy::Copies { groups: 3, tools: 1 })];
    let seeds: Vec<u64> = (2000..2000 + nseeds).collect();
    let w = Window { from: warmup * 1440.0, to: days * 1440.0 };
    let base = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let areas = fabsim::smt2020::areas(&dir).expect("areas load");
    let raw = fabsim::measure::raw_processing_days(&base, 20, 0)["part_3"];
    let mut cfg = LayoutConfig::realistic();
    if iters > 0 {
        cfg.iters = iters;
        cfg.restarts = 1;
    }
    let grid = PriceGrid::preregistered("B");
    let t0 = Instant::now();
    // cells in (share, strategy, policy) order
    let mut cells: Vec<Cell> = vec![];
    let mut meta: Vec<(f64, &str, Policy, Vec<String>, i64, usize)> = vec![];
    for &scale in &shares {
        let e = EngLots { scale, ..EngLots::published("part_E3", days * 1440.0, 1) };
        let shop = two_family_shop(&base, "part_3", &e).expect("two families");
        let cap = b_cap(&e, raw);
        for (sname, strat) in &strategies {
            let (s, info) = lay_out(&shop, &areas, &cfg, strat, "B").expect("layout");
            let groups = policy_groups(&s, "B", 3);
            eprintln!("x{scale} {sname}: copies {:?}, policy groups {:?}, cap {cap}, {:.0} s", info.copies, groups, t0.elapsed().as_secs_f64());
            for p in Policy::ALL {
                let unqualified: usize = if p == Policy::Qualify { groups.iter().map(|g| s.group(g).unwrap().count / 2).sum() } else { 0 };
                cells.push(Cell { label: format!("x{scale} {sname} {}", p.label()), shop: apply_policy(&s, p, "B", &groups, cap), policy: p, tools_added: info.tools_added, metres_added: info.metres_added });
                meta.push((scale, sname, p, groups.clone(), cap, unqualified));
            }
        }
    }
    eprintln!("{} cells x {} seeds, {days} days (window {warmup}-{days}), {threads} threads", cells.len(), seeds.len());
    let rows = run_cells(&cells, &seeds, w.to, &w, &grid, "B", threads).expect("cells run");
    let secs = t0.elapsed().as_secs_f64();
    eprintln!("done in {secs:.0} s");
    std::fs::create_dir_all(&out).unwrap();
    // every run, every price point
    let mut tsv = String::from("share\tstrategy\tpolicy\tseed\ta_wafers_per_day\tb_lots\tb_wafers\tb_cycle_days");
    for i in 0..grid.len() {
        let _ = write!(tsv, "\tmoney_{i}");
    }
    tsv.push('\n');
    for r in &rows {
        let m = &meta[r.cell];
        let c = &r.money[0];
        let _ = write!(tsv, "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}", m.0, m.1, m.2.label(), r.seed, r.a_wafers_per_day, c.b_lots, c.b_wafers, c.b_cycle_days.unwrap_or(f64::NAN));
        for x in &r.money {
            let _ = write!(tsv, "\t{}", x.per_day);
        }
        tsv.push('\n');
    }
    std::fs::write(out.join("runs.tsv"), tsv).unwrap();
    let mut prices = String::from("index\tprice0\tfree_days\tdecay\ttool_day\tmetre_day\n");
    for (i, m) in grid.iter().enumerate() {
        let _ = writeln!(prices, "{i}\t{}\t{}\t{}\t{}\t{}", m.price0, m.free_days, m.decay, m.tool_day, m.metre_day);
    }
    std::fs::write(out.join("prices.tsv"), prices).unwrap();

    // intervals: every cell against (D1, P0) at the same share, Bonferroni over 56
    let per_share = strategies.len() * Policy::ALL.len();
    let compared = (shares.len() * (per_share - 1)) as f64;
    let alpha = 0.05 / compared;
    let vals = |c: usize, f: &dyn Fn(&fabsim::twofam::CellRun) -> f64| -> Vec<f64> { rows.iter().filter(|r| r.cell == c).map(f).collect() };
    let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
    let fmt_iv = |iv: &Interval| format!("{:+.2} ({:+.2} to {:+.2})", iv.mean, iv.lo, iv.hi);
    let word = |v: Verdict| match v { Verdict::Better => "better", Verdict::Worse => "worse", Verdict::CannotSay => "no clear effect" };
    let metrics: [(&str, &str, bool, &dyn Fn(&fabsim::twofam::CellRun) -> f64); 3] = [
        ("money", "money a day (central prices, wafers of family-A margin)", true, &|r| r.money[0].per_day),
        ("a_wafers", "family A wafers out a day", true, &|r| r.a_wafers_per_day),
        ("b_cycle", "family B cycle time, days from scheduled arrival", false, &|r| r.money[0].b_cycle_days.unwrap_or(f64::NAN)),
    ];
    let mut md = String::new();
    let _ = writeln!(md, "On the SMT2020 model, with a layout of our own design; not a real fab. {} seeds ({}..{}), {days} days, window days {warmup} to {days}; family B's lots drawn with seed 1 (the same lots on every seed). Each cell minus (D1 share, P0 today) at the same share, paired; intervals Bonferroni over {compared} cells (each at level {:.5}), so all cover at once with probability at least 95%. Every price assumed. Real-fab effect: cannot say.{}\n",
        seeds.len(), seeds[0], seeds[seeds.len() - 1], alpha, if preregistered { "" } else { " SMOKE RUN: not the pre-registered design." });
    let mut json = format!("{{\"model\":\"SMT2020\",\"preregistered\":{preregistered},\"days\":{days},\"warmup\":{warmup},\"seeds\":{seeds:?},\"alpha_each\":{alpha},\"seconds\":{secs:.1},\"cells\":[");
    let mut first = true;
    for (mi, (key, title, higher, f)) in metrics.iter().enumerate() {
        let _ = writeln!(md, "### {title}\n");
        let _ = write!(md, "| share | strategy |");
        for p in Policy::ALL {
            let _ = write!(md, " {} |", p.label());
        }
        let _ = writeln!(md, "\n|---|---|{}", "---|".repeat(Policy::ALL.len()));
        for (si, &scale) in shares.iter().enumerate() {
            let b0 = si * per_share;
            let base_v = vals(b0, *f);
            for (ti, (sname, _)) in strategies.iter().enumerate() {
                let _ = write!(md, "| x{scale} | {sname} |");
                for pi in 0..Policy::ALL.len() {
                    let c = b0 + ti * Policy::ALL.len() + pi;
                    if c == b0 {
                        let _ = write!(md, " {:.2} (mean) |", mean(&base_v));
                        continue;
                    }
                    let iv = paired(&base_v, &vals(c, *f), alpha);
                    let v = verdict(&iv, *higher);
                    let _ = write!(md, " {} {} |", fmt_iv(&iv), word(v));
                    if mi == 0 {
                        // one json row per compared cell, with all three scores
                        let ivs: Vec<String> = metrics.iter().map(|(k, _, h, g)| {
                            let iv = paired(&vals(b0, *g), &vals(c, *g), alpha);
                            format!("\"{k}\":{{\"mean\":{},\"lo\":{},\"hi\":{},\"verdict\":\"{}\"}}", jnum(iv.mean), jnum(iv.lo), jnum(iv.hi), word(verdict(&iv, *h)))
                        }).collect();
                        let _ = write!(json, "{}{{\"label\":\"{}\",\"share\":{scale},\"strategy\":\"{sname}\",\"policy\":\"{}\",{}}}", if first { "" } else { "," }, cells[c].label, Policy::ALL[pi].label(), ivs.join(","));
                        first = false;
                    }
                }
                md.push('\n');
            }
        }
        md.push('\n');
        let _ = key;
    }
    json.push_str("]}");
    // the best cell per share by mean money, and each cell's crossover over share
    let _ = writeln!(md, "### Best cell per share (central prices)\n");
    for (si, &scale) in shares.iter().enumerate() {
        let b0 = si * per_share;
        let best = (b0..b0 + per_share).max_by(|&a, &b| mean(&vals(a, metrics[0].3)).total_cmp(&mean(&vals(b, metrics[0].3)))).unwrap();
        let iv = if best == b0 { None } else { Some(paired(&vals(b0, metrics[0].3), &vals(best, metrics[0].3), alpha)) };
        let _ = writeln!(md, "- x{scale}: {} ({:.2} a day){}", cells[best].label, mean(&vals(best, metrics[0].3)),
            iv.map(|iv| format!(", against D1 P0 {} {}", fmt_iv(&iv), word(verdict(&iv, true)))).unwrap_or_default());
    }
    let _ = writeln!(md, "\n### Where each cell's money verdict changes, over share\n");
    for k in 1..per_share {
        let pts: Vec<(f64, Interval)> = shares.iter().enumerate().map(|(si, &x)| (x, paired(&vals(si * per_share, metrics[0].3), &vals(si * per_share + k, metrics[0].3), alpha))).collect();
        let txt = match crossover(&pts) {
            Crossover::None(v) => format!("same verdict at every share: {}", v.label()),
            Crossover::Partial(v) => format!("{} at some shares, no clear effect at the others", v.label()),
            Crossover::Unclear => "no clear effect at any share".into(),
            Crossover::Between { last_clear_before, first_clear_after, unclear } => format!("flips between x{last_clear_before} and x{first_clear_after} (unclear at {unclear:?})"),
            Crossover::Several(v) => format!("flips more than once: {v:?}"),
        };
        let lab = cells[k].label.splitn(2, ' ').nth(1).unwrap_or("");
        let _ = writeln!(md, "- {lab}: {txt}");
    }
    let _ = writeln!(md, "\n### P4: break-even qualification cost per unqualified tool a day (central prices)\n");
    for (si, &scale) in shares.iter().enumerate() {
        for (ti, (sname, _)) in strategies.iter().enumerate() {
            let p0 = si * per_share + ti * Policy::ALL.len();
            let p4 = p0 + 4;
            let lost = mean(&vals(p0, metrics[0].3)) - mean(&vals(p4, metrics[0].3));
            let n = meta[p4].5;
            let _ = writeln!(md, "- x{scale} {sname}: P4 loses {lost:.2} a day against P0 with {n} tools unqualified{}", if n > 0 { format!(": it pays when qualifying one tool costs more than {:.2} a day", lost / n as f64) } else { String::new() });
        }
    }
    std::fs::write(out.join("summary.md"), md).unwrap();
    std::fs::write(out.join("summary.json"), json).unwrap();
    eprintln!("wrote {}", out.display());
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
        s.ports = p.ports(c);
        s.bayrails = p.bayrails(c);
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

/// The decision as a fab (docs/NARRATIVE.md, deliverable 2): today's realistic plan with copies of the groups
/// prototypes load most, each right after its original. Writes the layout, the variant shop and variant.json.
fn variant_cmd(args: &[String]) {
    use fabsim::pl::Sheet;
    use fabsim::variant::variant_layout;
    use std::fmt::Write as _;
    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    // by default the building on record for the US profile: 1.6 m chases with a cross aisle (docs/DESIGN-DEV.md)
    let mut cfg = fabsim::layout::Config::realistic();
    cfg.chase = flag(args, "--chase", "1.6").parse().expect("--chase is metres");
    cfg.cross = flag(args, "--cross", "1.6").parse().expect("--cross is metres");
    let out = PathBuf::from(flag(args, "--out", "results/layout-real-dd-copies"));
    let data = PathBuf::from(flag(args, "--data", "data/layout-real-dd-copies"));
    let n = arg(args, "--copies", 3) as usize;
    let share: f64 = flag(args, "--share", "2").parse().expect("--share is a number");
    let base = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
    let areas = fabsim::smt2020::areas(&dir).expect("areas");
    let v = variant_layout(&base, &areas, &cfg, share, n).expect("the variant");
    let plain = v.problem.pack(&v.problem.plain());
    let campus = v.problem.pack(&v.plan);
    std::fs::create_dir_all(&out).unwrap();
    std::fs::create_dir_all(&data).unwrap();
    // the same names as `fabsim layout`, so the plans, BIM and bill of materials read it unchanged
    std::fs::write(out.join("layout.json"), v.problem.to_json(&[("plain", &plain), ("optimised", &campus)])).unwrap();
    std::fs::write(data.join("optimised.shop.txt"), v.shop.to_text()).unwrap();
    let mut ps = v.shop.clone();
    ps.oht = Some(v.problem.oht(&plain));
    ps.ports = v.problem.ports(&plain);
    ps.bayrails = v.problem.bayrails(&plain);
    std::fs::write(data.join("plain.shop.txt"), ps.to_text()).unwrap();
    let s = Sheet::central();
    let cap = v.capital(&s);
    let (before, after) = v.travel();
    let mut json = format!(
        "{{\"model\":\"SMT2020\",\"note\":\"A gigafab-style layout of our own design on the SMT2020 model; placements and prices assumed.\",\"share\":{share},\"copies\":["
    );
    let mut md = String::new();
    let _ = writeln!(md, "The decision as a fab, on the SMT2020 model: today's realistic plan kept block for block, with one copy of each of the {n} groups prototype orders (x{share}) load most, each right after its original in the halls. Placements and prices assumed.\n");
    let _ = writeln!(md, "| copy | area | tools |\n|---|---|---|");
    for (i, c) in v.copies.iter().enumerate() {
        let _ = write!(json, "{}{{\"copy\":\"{}\",\"original\":\"{}\",\"area\":\"{}\",\"tools\":{}}}", if i > 0 { "," } else { "" }, c.copy, c.original, c.area, c.tools);
        let _ = writeln!(md, "| {} | {} | {} |", c.copy, c.area, c.tools);
    }
    let _ = write!(json, "],\"capital\":{{\"tools\":{},\"qualify\":{},\"floor\":{},\"bridge\":{},\"total\":{},\"depreciation_day\":{},\"upkeep_day\":{}}},", cap.tools, cap.qualify, cap.floor, cap.bridge, cap.total, cap.depreciation_day, cap.upkeep_day);
    let _ = write!(json, "\"travel\":{{\"before\":{before},\"after\":{after},\"unit\":\"hoist metres a day at the two-family flows\"}},\"lengths\":{:?}}}\n", campus.lengths);
    let _ = writeln!(md, "\nCapital (central price sheet): ${:.1}M once (tools ${:.1}M, qualifying ${:.1}M, floor ${:.1}M), ${:.0} a day in depreciation and upkeep.", cap.total / 1e6, cap.tools / 1e6, cap.qualify / 1e6, cap.floor / 1e6, cap.depreciation_day + cap.upkeep_day);
    let _ = writeln!(md, "\nHoist travel at the two-family flows: {:.0} m a day on today's campus, {:.0} m with the copies ({:+.1}%). Exact for the stated flows.", before, after, 100.0 * (after - before) / before);
    std::fs::write(out.join("variant.json"), json).unwrap();
    std::fs::write(out.join("summary.md"), &md).unwrap();
    println!("{md}");
}

/// The fleet in a window (docs/FLEET.md), for the viewers: the layout's shop with a fleet of `--vehicles`, run on
/// `--seed` to the window's end, and the track with every vehicle's stretches and hoists in the window as JSON.
fn fleet_trace(args: &[String]) {
    use fabsim::fleet::FleetTrace;
    use fabsim::shop::Fleet;
    use fabsim::track::Track;
    let data = PathBuf::from(flag(args, "--data", "data/layout-real-dd"));
    let plan = flag(args, "--plan", "optimised");
    let mut shop = Shop::parse(&std::fs::read_to_string(data.join(format!("{plan}.shop.txt"))).expect("run fabsim layout first")).unwrap();
    let vehicles = arg(args, "--vehicles", 160) as usize;
    let f = Fleet { vehicles, gap: 3.0, hoist: 1.0, ports: 2, cross: 60.0, controller: flag(args, "--controller", "nearest").to_string() };
    let cross = f.cross;
    shop.fleet = Some(f);
    let seed = arg(args, "--seed", 3000);
    let from = flag(args, "--day", "1").parse::<f64>().expect("--day is a number") * 1440.0;
    let to = from + arg(args, "--minutes", 60) as f64;
    let r = run(&shop, &RunOptions { seed, until: Some(to), record: true }, None);
    let fo = r.fleet.as_ref().unwrap();
    let o = shop.oht.as_ref().unwrap();
    let _ = cross;
    let t = Track::from_shop(&shop);
    let tr = FleetTrace::new(o, &t, fo, from, to);
    let out = PathBuf::from(flag(args, "--out", "")).to_str().filter(|s| !s.is_empty()).map(PathBuf::from).unwrap_or_else(|| data.join(format!("fleet-{vehicles}.json")));
    std::fs::write(&out, tr.to_json()).unwrap();
    println!(
        "wrote {}: {} nodes, {} stretches, {} stays and {} hoists in the window; whole run: wait {:.2} min, delivery {:.2} min, {} detours",
        out.display(), tr.nodes.len(), tr.edges.len(), tr.entries.len(), tr.hoists.len(),
        fo.wait_sum / fo.wait_n.max(1) as f64, fo.deliver_sum / fo.delivered.max(1) as f64, fo.detours
    );
}

/// The track a fleet runs on (docs/FLEET.md), as segments on the campus plan, for checking against the drawings.
fn track_cmd(args: &[String]) {
    let data = PathBuf::from(flag(args, "--data", "data/layout-real-dd"));
    let plan = flag(args, "--plan", "optimised");
    let shop = Shop::parse(&std::fs::read_to_string(data.join(format!("{plan}.shop.txt"))).expect("run fabsim layout first")).unwrap();
    let t = fabsim::track::Track::from_shop(&shop);
    let segs = t.segments(shop.oht.as_ref().unwrap());
    let body: Vec<String> = segs.iter().map(|s| format!("[{:.3},{:.3},{:.3},{:.3}]", s[0], s[1], s[2], s[3])).collect();
    let out = PathBuf::from(flag(args, "--out", "track.json"));
    std::fs::write(&out, format!("{{\"model\":\"SMT2020\",\"nodes\":{},\"runs\":[{}]}}\n", t.nodes().len(), body.join(","))).unwrap();
    println!("wrote {}: {} nodes, {} stretches", out.display(), t.nodes().len(), segs.len());
}

/// One lot from start to finish (docs/LIVE-REAL.md): the first lot of `--route` released on or after `--day` on the
/// layout's shop with a fleet of `--vehicles`, followed until it leaves the fab; its steps, rail stays and hoists.
fn follow_cmd(args: &[String]) {
    use fabsim::shop::Fleet;
    use std::fmt::Write as _;
    let data = PathBuf::from(flag(args, "--data", "data/layout-real-dd"));
    let mut shop = Shop::parse(&std::fs::read_to_string(data.join("optimised.shop.txt")).expect("run fabsim layout first")).unwrap();
    let vehicles = arg(args, "--vehicles", 160) as usize;
    shop.fleet = Some(Fleet { vehicles, gap: 3.0, hoist: 1.0, ports: 2, cross: 60.0, controller: "nearest".into() });
    let route = flag(args, "--route", "part_3").to_string();
    let day: f64 = flag(args, "--day", "20").parse().expect("--day is a number");
    let rel = shop.releases.iter().find(|r| r.route == route && r.prefix.starts_with("Lot_")).expect("a plain release of that route");
    let n = ((day * 1440.0 - rel.first) / rel.every).ceil().max(0.0) as i64;
    let id = format!("{}.{}", rel.prefix, n);
    let seed = arg(args, "--seed", 3000);
    let days = arg(args, "--days", 150) as f64;
    let t0 = Instant::now();
    let r = fabsim::engine::run_follow(&shop, &RunOptions { seed, until: Some(days * 1440.0), record: false }, &id);
    let li = r.lots.iter().position(|l| l.id == id).expect("the lot was released");
    let lot = &r.lots[li];
    let names: Vec<&str> = shop.groups.iter().map(|g| g.name.as_str()).collect();
    let tool_group: Vec<usize> = shop.groups.iter().enumerate().flat_map(|(gi, g)| std::iter::repeat_n(gi, g.count)).collect();
    let n4 = |x: f64| if x.is_finite() { format!("{x:.3}") } else { "null".into() };
    let mut o = format!(
        "{{\"model\":\"SMT2020\",\"what\":\"One lot followed from release to finish on today's US building with {vehicles} vehicles, seed {seed}; a gigafab-style layout of our own design on the SMT2020 model, not a real fab.\",\"lot\":\"{id}\",\"route\":\"{route}\",\"wafers\":{},\"released\":{},\"done\":{},\"route_steps\":{},\"steps\":[",
        lot.size, n4(lot.release), lot.done.map(n4).unwrap_or("null".into()), shop.routes.iter().find(|x| x.name == route).map(|x| x.steps.len()).unwrap_or(0)
    );
    for (i, t) in r.trace.iter().enumerate() {
        let _ = write!(o, "{}[{},\"{}\",{},{},{},{}]", if i > 0 { "," } else { "" }, t.step, names[tool_group[t.tool as usize]], t.tool, n4(t.arrive), n4(t.start), n4(t.end));
    }
    let f = r.fleet.as_ref().unwrap();
    o.push_str("],\"entries\":[");
    for (i, e) in f.entries.iter().enumerate() {
        let _ = write!(o, "{}[{},{},{},{}]", if i > 0 { "," } else { "" }, e.edge, n4(e.t_in), n4(e.t_out), e.loaded as u8);
    }
    o.push_str("],\"hoists\":[");
    for (i, h) in f.hoists.iter().enumerate() {
        let _ = write!(o, "{}[{},{},{},{}]", if i > 0 { "," } else { "" }, h.stop, h.up as u8, n4(h.t0), n4(h.t1));
    }
    o.push_str("]}\n");
    let out = PathBuf::from(flag(args, "--out", "web/data/journey.json"));
    std::fs::write(&out, o).unwrap();
    println!(
        "wrote {}: {id}, {} steps of {}, released day {:.1}, {} after {:.1} days, {} rail stays and {} hoists ({:.1} s)",
        out.display(), r.trace.len(), route, lot.release / 1440.0,
        if lot.done.is_some() { "finished" } else { "not finished" }, lot.done.map(|d| (d - lot.release) / 1440.0).unwrap_or(f64::NAN),
        f.entries.len(), f.hoists.len(), t0.elapsed().as_secs_f64()
    );
}

/// Regret option C (docs/LONG-RESCORE.md): the capacity ceiling of a shop, its bottleneck and the next groups.
fn bound_cmd(args: &[String]) {
    use std::fmt::Write as _;
    let dir = args.get(0).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
    let shop = if dir.is_dir() { fabsim::smt2020::load(&dir).expect("SMT2020 loads") } else { Shop::parse(&std::fs::read_to_string(&dir).unwrap()).unwrap() };
    let c = fabsim::bound::capacity(&shop);
    let mut g = c.groups.clone();
    g.sort_by(|a, b| a.wafers_per_day.total_cmp(&b.wafers_per_day));
    let mut j = format!(
        "{{\"model\":\"SMT2020\",\"wafers_per_day\":{},\"strict_wafers_per_day\":{},\"released_per_day\":{},\"bottleneck\":\"{}\",\"groups\":[",
        c.wafers_per_day, c.strict_wafers_per_day, c.released_per_day, c.bottleneck
    );
    for (i, x) in g.iter().enumerate() {
        let _ = write!(j, "{}{{\"name\":\"{}\",\"minutes_per_wafer\":{},\"available_minutes_per_day\":{},\"wafers_per_day\":{}}}", if i > 0 { "," } else { "" }, x.name, x.minutes_per_wafer, x.available_minutes_per_day, x.wafers_per_day);
    }
    j.push_str("]}\n");
    if let Some(out) = args.iter().position(|a| a == "--out").and_then(|i| args.get(i + 1)) {
        std::fs::write(out, &j).unwrap();
    }
    println!("ceiling {:.1} wafers a day (strict {:.1}), released {:.1}; bottleneck {}", c.wafers_per_day, c.strict_wafers_per_day, c.released_per_day, c.bottleneck);
    for x in g.iter().take(6) {
        println!("  {:<18} {:>8.1} wafers a day ({:.2} tool-min a wafer, {:.0} tool-min a day)", x.name, x.wafers_per_day, x.minutes_per_wafer, x.available_minutes_per_day);
    }
}

/// Regret B and D (docs/LONG-RESCORE.md) on one seed:
/// `fabsim regret audit SHOP --seed N --warmup D --window D --picks FILE [--defects H,L,R] [--samples 300] [--horizon 1440] [--by-kind | --max M] --out FILE`
/// `fabsim regret switch SHOP --seed N --warmup D --window D [--defects H,L,R] [--shift 720] --out FILE`
fn regret_cmd(args: &[String]) {
    use fabsim::policy::Policy;
    use std::fmt::Write as _;
    let what = args.first().map(|s| s.as_str()).unwrap_or("");
    let src = args.get(1).expect("a shop");
    let defects = args.iter().position(|a| a == "--defects").and_then(|i| args.get(i + 1)).map(|s| s.as_str());
    let shop = fabsim::gym::load_shop(std::path::Path::new(src), defects).expect("the shop loads");
    let seed = arg(args, "--seed", 0);
    let from = argf(args, "--warmup", 130.0) * 1440.0;
    let to = from + argf(args, "--window", 60.0) * 1440.0;
    let out = PathBuf::from(flag(args, "--out", "regret.json"));
    let t0 = Instant::now();
    let mut j = format!("{{\"model\":\"SMT2020\",\"seed\":{seed},\"from\":{from},\"to\":{to},\"defects\":{},", defects.map(|d| format!("\"{d}\"")).unwrap_or("null".into()));
    match what {
        "audit" => {
            let text = std::fs::read_to_string(flag(args, "--picks", "")).expect("--picks FILE");
            let picks: Vec<u32> = text.lines().filter_map(|l| l.trim().parse().ok()).collect();
            let n = arg(args, "--samples", 300) as usize;
            let horizon = argf(args, "--horizon", 1440.0);
            // --by-kind: one lot of each kind tried, the policy's pick standing for its own (never more regret than all)
            let by_kind = args.iter().any(|a| a == "--by-kind");
            // --max M: the kinds and the pick, then lots spread evenly over the rest, at most M tried
            let max = args.iter().position(|a| a == "--max").and_then(|i| args.get(i + 1)).and_then(|v| v.parse::<usize>().ok());
            let a = match (max, by_kind) {
                (Some(m), _) => fabsim::regret::audit_capped(&shop, seed, from, to, &picks, n, horizon, m),
                (None, true) => fabsim::regret::audit_by_kind(&shop, seed, from, to, &picks, n, horizon),
                (None, false) => fabsim::regret::audit(&shop, seed, from, to, &picks, n, horizon),
            };
            let by_kind = by_kind || max.is_some();
            let _ = write!(j, "\"kind\":\"audit\",\"by_kind\":{by_kind},\"max\":{},\"horizon\":{horizon},\"picks\":{},\"mean_regret\":{},\"samples\":[", max.map(|m| m.to_string()).unwrap_or("null".into()), picks.len(), a.mean_regret);
            for (i, x) in a.samples.iter().enumerate() {
                let _ = write!(j, "{}{{\"k\":{},\"t\":{},\"lots\":{},\"tried\":{:?},\"chosen\":{},\"regret\":{},\"values\":{:?}}}", if i > 0 { "," } else { "" }, x.k, x.t, x.lots, x.tried, x.chosen, x.regret, x.values);
            }
            j.push_str("]");
            println!("audit seed {seed}: {} samples, mean regret {:.4} a pick over {horizon} min ({:.0} s)", a.samples.len(), a.mean_regret, t0.elapsed().as_secs_f64());
        }
        "switch" => {
            let lib = [Policy::Today, Policy::Fifo, Policy::Spt, Policy::CriticalRatio, Policy::Random];
            let shift = argf(args, "--shift", 720.0);
            let d = fabsim::regret::switching(&shop, seed, from, to, shift, &lib);
            let _ = write!(j, "\"kind\":\"switch\",\"shift\":{shift},\"library\":{:?},\"value_gain\":{},\"sequence\":{:?},\"shifts\":[",
                lib.iter().map(|p| p.name()).collect::<Vec<_>>(), d.value_gain, d.sequence.iter().map(|p| p.name()).collect::<Vec<_>>());
            for (i, x) in d.shifts.iter().enumerate() {
                let _ = write!(j, "{}{{\"start\":{},\"chosen\":{},\"gains\":{:?}}}", if i > 0 { "," } else { "" }, x.start, x.chosen, x.gains);
            }
            j.push_str("]");
            println!("switch seed {seed}: gain {:.2} over the window ({:.0} s)", d.value_gain, t0.elapsed().as_secs_f64());
        }
        _ => panic!("fabsim regret audit|switch ..."),
    }
    j.push_str("}\n");
    std::fs::write(&out, j).unwrap();
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
    // `--copies N`: the variant (fabsim variant), rebuilt the same way
    let copies = arg(args, "--copies", 0) as usize;
    let (p, c) = if copies > 0 {
        let share: f64 = flag(args, "--share", "2").parse().expect("--share is a number");
        let v = fabsim::variant::variant_layout(&flat, &areas, &cfg, share, copies).unwrap();
        let c = if plan == "plain" { v.problem.pack(&v.problem.plain()) } else { v.problem.pack(&v.plan) };
        (v.problem, c)
    } else {
        let p = Problem::new(&flat, &areas, &cfg).unwrap();
        let c = if plan == "plain" { p.pack(&p.plain()) } else { p.pack(&p.optimise()) };
        (p, c)
    };
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
        Some("two-families") => two_families(&args[1..]),
        Some("pl") => pl_cmd(&args[1..]),
        Some("evolve") => evolve_cmd(&args[1..]),
        Some("env") => env_cmd(&args[1..]),
        Some("layout") => layout(&args[1..]),
        Some("layout-score") => layout_score(&args[1..]),
        Some("layout-trace") => layout_trace(&args[1..]),
        Some("variant") => variant_cmd(&args[1..]),
        Some("fleet-trace") => fleet_trace(&args[1..]),
        Some("track") => track_cmd(&args[1..]),
        Some("follow") => follow_cmd(&args[1..]),
        Some("bound") => bound_cmd(&args[1..]),
        Some("regret") => regret_cmd(&args[1..]),
        Some("score") => {
            let text = std::fs::read_to_string(&args[1]).expect("read the scenario");
            let dir = args.get(2).filter(|a| !a.starts_with("--")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/smt2020/hvlm"));
            let parsed = fabsim::scenario::Scenario::parse(&text);
            let two = parsed.as_ref().map(|s| s.family.is_some()).unwrap_or(false);
            // a two-family question runs months (docs/ASK-FAMILIES.md); the overrides are for smoke runs
            let mut p = if two { fabsim::score::Protocol::families() } else { fabsim::score::Protocol::default() };
            p.threads = arg(&args, "--threads", 4) as usize;
            p.warmup_days = argf(&args, "--warmup", p.warmup_days);
            p.window_days = argf(&args, "--window", p.window_days);
            if let Some(r) = args.iter().position(|a| a == "--seeds").and_then(|i| args.get(i + 1)) {
                let (a, b) = r.split_once("..").expect("--seeds A..B");
                p.seeds = (a.parse::<u64>().unwrap()..b.parse::<u64>().unwrap()).collect();
            }
            let shop = fabsim::smt2020::load(&dir).expect("SMT2020 loads");
            let ctx = if two {
                let mut layout = fabsim::layout::Config::realistic();
                if let Some(i) = args.iter().position(|a| a == "--layout-iters").and_then(|i| args.get(i + 1)) {
                    layout.iters = i.parse().unwrap();
                    layout.restarts = 1;
                }
                let cache = args.iter().position(|a| a == "--layout-cache").and_then(|i| args.get(i + 1)).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("data/ask/layouts"));
                Some(fabsim::score::FamilyContext {
                    from_route: "part_3".into(),
                    b_route: "part_E3".into(),
                    areas: Some(fabsim::smt2020::areas(&dir).expect("areas load")),
                    layout,
                    cache: Some(cache),
                })
            } else {
                None
            };
            match parsed.and_then(|sc| fabsim::score::score_with(&shop, &sc, &p, ctx.as_ref())) {
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

// ------------------------------------------------------------------ fabsim env (docs/RL-DEFECTS.md)
// One episode, one dispatch decision at a time, as JSON lines on standard input and output.

fn env_cmd(args: &[String]) {
    use fabsim::gym::{done_json, episode, families, load_shop, observation_json};
    use fabsim::window::Window;
    use std::io::{BufRead, Write};
    let src = args.first().filter(|a| !a.starts_with("--")).expect("fabsim env SHOP --seed N [--warmup D] [--window D] [--defects H,L,R] [--auto]");
    let defects = args.iter().position(|a| a == "--defects").and_then(|i| args.get(i + 1)).map(|s| s.as_str());
    let shop = load_shop(std::path::Path::new(src), defects).unwrap_or_else(|e| {
        eprintln!("refused: {e}");
        std::process::exit(2)
    });
    let seed = arg(args, "--seed", 0);
    let warmup = argf(args, "--warmup", 1.0);
    let window = argf(args, "--window", 3.0);
    // --auto plays the engine's own pick; --auto NAME a built-in rule (docs/LONG-RESCORE.md), with today's rule in the
    // warm-up as for any player
    let auto_at = args.iter().position(|a| a == "--auto");
    let auto = auto_at.is_some();
    let rule = auto_at.and_then(|i| args.get(i + 1)).filter(|s| !s.starts_with("--")).map(|s| fabsim::policy::Policy::parse(s).unwrap_or_else(|| {
        eprintln!("refused: --auto names today, fifo, spt, cr or random");
        std::process::exit(2)
    }));
    let mut rule_pick = rule.map(|p| fabsim::policy::picker(&shop, p, seed));
    let w = Window { from: warmup * 1440.0, to: (warmup + window) * 1440.0 };
    let fams = families(&shop);
    let stdin = std::io::stdin();
    let mut input = stdin.lock();
    let stdout = std::io::stdout();
    let mut out = std::io::BufWriter::new(stdout.lock());
    let mut line = String::new();
    // seconds inside the rule's own pick (docs/LONG-RESCORE.md, the speed chart)
    let mut pick_time = 0.0f64;
    let mut ask = |d: &fabsim::engine::Decision, ord: &[usize], reward: f64| -> Option<usize> {
        if auto {
            let t0 = std::time::Instant::now();
            let k = match rule_pick.as_mut() {
                Some(p) => p(d),
                None => d.default,
            };
            pick_time += t0.elapsed().as_secs_f64();
            return Some(k);
        }
        let _ = writeln!(out, "{}", observation_json(d, ord, reward, &fams));
        let _ = out.flush();
        line.clear();
        if input.read_line(&mut line).unwrap_or(0) == 0 {
            return None;
        }
        line.find("\"action\"")
            .and_then(|i| line[i + 8..].trim_start().strip_prefix(':'))
            .and_then(|r| {
                let r = r.trim_start();
                let end = r.find(|c: char| !c.is_ascii_digit()).unwrap_or(r.len());
                r[..end].parse::<usize>().ok()
            })
            .and_then(|k| ord.get(k).copied())
    };
    let e = episode(&shop, seed, w, &mut ask);
    drop(ask);
    if let Some(p) = args.iter().position(|a| a == "--picks").and_then(|i| args.get(i + 1)) {
        fabsim::gym::write_picks(&e, std::path::Path::new(p)).expect("write the picks");
    }
    let mut tag = rule.map(|p| format!(",\"policy\":\"{}\"", p.name())).unwrap_or_default();
    if auto {
        tag.push_str(&format!(",\"pick_ns\":{}", 1e9 * pick_time / e.asked.max(1) as f64));
    }
    let _ = writeln!(out, "{}", done_json(&e, &tag));
    let _ = out.flush();
}
