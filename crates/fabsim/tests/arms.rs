//! Every setup keeps its fab file (docs/RUNS.md, part 2, RN9). Written before the code: a one-family question's report
//! carries each setup's file as it was scored, its rule as a `dispatch` record, so the Floor can play the very run.
//! From the SMT2020 testbed's shape, on a small test fab; not a real fab.

use fabsim::engine::{run, RunOptions, RunResult};
use fabsim::policy;
use fabsim::scenario::Scenario;
use fabsim::score::{score, Protocol};
use fabsim::shop::Shop;
use fabsim::window::{with_probes, Window};

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t2\t600.0\t60.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t45.0\t0.0\t-\tA
release\tra\t25\t20.0\t180.0\t0.0\t-\tH
";

const ONE: &str = "fabgym-scenario 1
question\tDemand up a fifth: which rule, or a cap?
shock\tdemand\t1.2\tsaid
candidate\tfifo\trule\tfifo
candidate\tcapped\tcap\t4
candidate\tquickest\trule\tspt
";

fn events(r: &RunResult) -> Vec<(u32, u32, u32, u64, u64, u64)> {
    r.trace.iter().map(|x| (x.lot, x.step, x.tool, x.arrive.to_bits(), x.start.to_bits(), x.end.to_bits())).collect()
}

#[test]
fn rn9_each_setup_keeps_its_file_and_the_file_is_the_run() {
    let shop = Shop::parse(TOY).unwrap();
    let sc = Scenario::parse(ONE).unwrap();
    let p = Protocol { warmup_days: 1.0, window_days: 3.0, seeds: vec![0, 1, 2], threads: 2 };
    let report = score(&shop, &sc, &p).unwrap();
    let names: Vec<&str> = report.arms.iter().map(|a| a.name.as_str()).collect();
    assert_eq!(names, ["today", "fifo", "capped", "quickest"], "today first, then the candidates");
    assert!(report.to_json().contains("\"arms\":["), "the report carries the files");
    for a in &report.arms {
        let has = |rule: &str| a.shop_text.lines().any(|l| l == format!("dispatch\t{rule}"));
        match a.name.as_str() {
            "fifo" => assert!(has("fifo"), "fifo's file names its rule"),
            "quickest" => assert!(has("spt"), "the quickest-first file names its rule"),
            _ => assert!(!a.shop_text.lines().any(|l| l.starts_with("dispatch\t")), "{}: no rule of its own", a.name),
        }
    }
    let w = Window { from: p.warmup_days * 1440.0, to: (p.warmup_days + p.window_days) * 1440.0 };
    for (i, a) in report.arms.iter().enumerate() {
        let cand = if i == 0 { None } else { Some(&sc.candidates[i - 1]) };
        let (d, pol) = sc.arm(cand, None);
        let scored = with_probes(&d.apply(&shop).unwrap(), &w);
        let file = Shop::parse(&a.shop_text).unwrap_or_else(|e| panic!("{}'s file parses: {e}", a.name));
        for seed in [0u64, 1] {
            let o = RunOptions { seed, until: Some(w.to), record: true };
            let want = policy::run_with(&scored, &o, pol);
            let got = run(&file, &o, None);
            assert_eq!(events(&got), events(&want), "{} on random run {seed}: the file is the run as scored", a.name);
            assert_eq!(got.finished, want.finished);
        }
    }
}
