//! Every lot finishes its route (docs/DOUBLE-CHECK.md, part 1). Written before the code. A route is a chain of chances:
//! after a step a lot goes on, or back for rework by a draw; a sampled step is done by a draw and skipped otherwise. So
//! each route can be worked out exactly with no simulator, and the simulator must agree. From the SMT2020 testbed and
//! a teaching fab of our own; not a real fab.

mod common;

use fabsim::checks::{check, Severity};
use fabsim::engine::{run, RunOptions};
use fabsim::routes::{analyse, issues};
use fabsim::shop::Shop;
use fabsim::uq::t_quantile;

fn toy(steps: &str) -> Shop {
    Shop::parse(&format!(
        "fabgym-shop 1
transport\t1.0\t2.0
group\tA\t1\t1.0\t1.0\t-\t-\t-
route\tr
{steps}release\tr\t25\t10.0\t60.0\t0.0\t-\tL
"
    ))
    .unwrap()
}

// step GROUP PER TIME SPREAD BATCHLO BATCHHI INTERVAL BATCHWAIT SETUP SAMPLE REWORKTO REWORKP CQTTO CQTMIN
fn step(per: &str, time: f64, interval: &str, sample: &str, rework: (&str, &str)) -> String {
    format!("step\tA\t{per}\t{time}\t0.0\t-\t-\t{interval}\t-\t-\t{sample}\t{}\t{}\t-\t-\n", rework.0, rework.1)
}

#[test]
fn dc1_a_toy_route_matches_the_hand_worked_answer() {
    // step 1 sends a lot back to step 0 one time in five; step 2 is done half the time
    let shop = toy(&[
        step("lot", 30.0, "-", "-", ("-", "-")),
        step("piece", 2.0, "-", "-", ("0", "0.2")),
        step("piece", 2.0, "0.5", "0.5", ("-", "-")),
    ]
    .concat());
    let c = &analyse(&shop)[0];
    assert_eq!(c.route, "r");
    // steps 0 and 1 are done 1 / (1 - 0.2) = 1.25 times each, step 2 half the time
    let want = [1.25, 1.25, 0.5];
    for (k, w) in want.iter().enumerate() {
        assert!((c.visits[k] - w).abs() < 1e-12, "step {k}: {} against {w}", c.visits[k]);
    }
    assert!((c.expected_steps - 3.0).abs() < 1e-12, "{}", c.expected_steps);
    // a lot of 25 alone, load and unload 1 + 1 minutes a job: 32, then 2 x 25 + 2 = 52, then 2 + 24 x 0.5 + 2 = 16
    let minutes = 1.25 * 32.0 + 1.25 * 52.0 + 0.5 * 16.0;
    assert!((c.expected_minutes - minutes).abs() < 1e-9, "{} against {minutes}", c.expected_minutes);
    // once through, every step done once, rework and sampling aside
    assert!((c.once_minutes - (32.0 + 52.0 + 16.0)).abs() < 1e-9, "{}", c.once_minutes);
    assert!(c.residual < 1e-12, "the equations hold to rounding: {}", c.residual);
    assert!(issues(&shop).is_empty());
}

#[test]
fn dc2_every_route_of_our_fabs_passes_and_broken_ones_are_refused() {
    let mut shops = vec![
        ("the Floor's fab", Shop::parse(&common::read("web/data/shop.txt")).unwrap()),
        ("the teaching fab", Shop::parse(&common::read("crates/fabsim/tests/data/teach-free.fab.txt")).unwrap()),
    ];
    if let Some(dir) = common::smt2020_dir() {
        shops.push(("the high-volume testbed", fabsim::smt2020::load(&dir).unwrap()));
    }
    for (name, shop) in &shops {
        assert!(issues(shop).is_empty(), "{name}: {:?}", issues(shop));
        let chains = analyse(shop);
        assert_eq!(chains.len(), shop.routes.len(), "{name}: one chain a route");
        for c in &chains {
            let r = shop.routes.iter().find(|r| r.name == c.route).unwrap();
            assert_eq!(c.visits.len(), r.steps.len());
            assert!(c.expected_steps.is_finite() && c.expected_steps > 0.0, "{name} {}: {}", c.route, c.expected_steps);
            assert!(c.residual < 1e-9, "{name} {}: residual {}", c.route, c.residual);
            assert!(c.once_minutes > 0.0 && c.expected_minutes.is_finite(), "{name} {}: minutes", c.route);
        }
    }
    let bad = |steps: &str, code: &str| {
        let shop = toy(steps);
        let got = issues(&shop);
        assert!(got.iter().any(|i| i.code == code && i.severity == Severity::Error), "{code}: {got:?}");
        assert!(check(&shop).iter().any(|i| i.code == code), "{code} joins the layout checks");
    };
    bad(&[step("lot", 1.0, "-", "-", ("-", "-")), step("lot", 1.0, "-", "-", ("5", "0.1"))].concat(), "rework_target");
    bad(&[step("lot", 1.0, "-", "-", ("-", "-")), step("lot", 1.0, "-", "-", ("0", "1.0"))].concat(), "rework_certain");
    bad(&[step("lot", 1.0, "-", "1.5", ("-", "-")), step("lot", 1.0, "-", "-", ("-", "-"))].concat(), "bad_chance");
}

#[test]
fn dc3_the_simulator_agrees_on_steps_per_lot() {
    let Some(dir) = common::smt2020_dir() else { return };
    let mut shop = fabsim::smt2020::load(&dir).unwrap();
    // releases keep coming, at a quarter of the usual rate, so a lot waiting at a batch step always gets partners;
    // only lots released in the first week are counted, and every one of them must finish, so none is left out for
    // being slow (a slow lot is often one sent back for rework)
    shop.lots.clear();
    for r in &mut shop.releases {
        r.every *= 4.0;
    }
    let chains = analyse(&shop);
    let mut steps: std::collections::HashMap<String, Vec<f64>> = Default::default();
    for seed in 0..10u64 {
        let res = run(&shop, &RunOptions { seed, until: Some(55.0 * 1440.0), record: true }, None);
        let early: Vec<_> = res.lots.iter().filter(|l| !l.wip && l.release < 7.0 * 1440.0).collect();
        assert!(early.len() >= 80, "run {seed}: {} lots released in the first week", early.len());
        assert!(early.iter().all(|l| l.done.is_some()), "run {seed}: every lot released in the first week finished");
        // jobs from the trace: a lot's own record leaves out a released lot's first job, as the reference log does
        let mut jobs = vec![0usize; res.lots.len()];
        for x in &res.trace {
            jobs[x.lot as usize] += 1;
        }
        for (i, l) in res.lots.iter().enumerate() {
            if !l.wip && l.release < 7.0 * 1440.0 {
                steps.entry(l.route.clone()).or_default().push(jobs[i] as f64);
            }
        }
    }
    for c in &chains {
        let d = &steps[&c.route];
        let n = d.len() as f64;
        let mean = d.iter().sum::<f64>() / n;
        let sd = (d.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n - 1.0)).sqrt();
        let h = t_quantile(0.975, n - 1.0) * sd / n.sqrt();
        assert!(
            (mean - c.expected_steps).abs() <= h,
            "{}: the simulator's {mean:.3} steps a lot (95%: {:.3} to {:.3}) against the exact {:.3}",
            c.route,
            mean - h,
            mean + h,
            c.expected_steps
        );
    }
}
