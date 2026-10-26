//! Uncertainty: quantified (intervals with stated guarantees) and qualified (verdicts, the
//! crossover worth asking about, and what the model cannot say). Layers 1, 2, 3 and 5 of the
//! problem statement.
//!
//! Reference quantiles were computed with mpmath at 50 digits (regularised incomplete beta).

use fabsim::pyrandom::PyRandom;
use fabsim::uq::{
    bonferroni_paired, crossover, holm, min_detectable_effect, paired, paired_p_value, t_cdf,
    t_quantile, verdict, Basis, ConfSeq, Crossover, Race, Value, Verdict, REAL_FAB_EFFECT,
};

fn close(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * b.abs().max(1.0)
}

fn normal(r: &mut PyRandom) -> f64 {
    // Box-Muller
    let u1 = 1.0 - r.random();
    let u2 = r.random();
    (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
}

// ------------------------------------------------------------------ the t distribution

#[test]
fn t_quantiles_match_mpmath() {
    for (p, df, want) in [
        (0.975, 1.0, 12.706204736174693314),
        (0.975, 2.0, 4.3026527297494617894),
        (0.975, 4.0, 2.7764451051977934898),
        (0.975, 9.0, 2.2621571627982049992),
        (0.975, 29.0, 2.0452296421327038745),
        (0.995, 9.0, 3.2498355415921257205),
        (0.95, 4.0, 2.1318467863266495285),
        (0.9875, 9.0, 2.685010846816457475),
        (1.0 - 1.0 / 120.0, 9.0, 2.9333240883739881054),
        (0.8, 9.0, 0.88340385968553470914),
        (0.975, 1000.0, 1.9623390808264081039),
    ] {
        let got = t_quantile(p, df);
        assert!(close(got, want, 1e-10), "t({p}, {df}) = {got}, want {want}");
        // symmetric
        assert!(close(t_quantile(1.0 - p, df), -want, 1e-9));
    }
    assert!(close(t_cdf(1.5, 7.0), 0.91135075650501498342, 1e-12));
    assert!(close(t_cdf(0.0, 7.0), 0.5, 1e-15));
}

// ------------------------------------------------------------------ layer 1: paired seeds

#[test]
fn paired_interval_is_the_t_interval_of_differences() {
    let base = [10.0, 11.0, 12.0, 13.0, 14.0];
    let cand = [11.0, 13.0, 15.0, 17.0, 19.0]; // differences 1..5
    let iv = paired(&base, &cand, 0.05);
    let half = 2.7764451051977934898 * (2.5f64).sqrt() / (5.0f64).sqrt();
    assert_eq!(iv.n, 5);
    assert!(close(iv.mean, 3.0, 1e-15));
    assert!(close(iv.lo, 3.0 - half, 1e-10) && close(iv.hi, 3.0 + half, 1e-10));
    assert!(iv.guarantee.contains("95%"), "{}", iv.guarantee);
}

#[test]
fn paired_interval_covers_about_95_percent() {
    // differences ~ normal(0.3, 1), 10 seeds, 4000 repetitions: coverage within 3 standard errors
    let mut r = PyRandom::from_str_seed("uq/coverage");
    let reps = 4000;
    let mut covered = 0;
    for _ in 0..reps {
        let base: Vec<f64> = (0..10).map(|_| normal(&mut r) * 3.0).collect();
        let cand: Vec<f64> = base.iter().map(|b| b + 0.3 + normal(&mut r)).collect();
        let iv = paired(&base, &cand, 0.05);
        if iv.lo <= 0.3 && 0.3 <= iv.hi {
            covered += 1;
        }
    }
    let share = covered as f64 / reps as f64;
    let se = (0.95f64 * 0.05 / reps as f64).sqrt();
    assert!((share - 0.95).abs() < 3.0 * se, "coverage {share}");
}

#[test]
fn pairing_beats_independent_noise() {
    // a common random shock per seed cancels in the paired difference
    let base = [100.0, 250.0, 80.0, 300.0, 150.0, 220.0, 90.0, 310.0, 130.0, 200.0];
    let cand: Vec<f64> = base.iter().enumerate().map(|(i, b)| b - 5.0 + (i % 3) as f64).collect();
    let iv = paired(&base, &cand, 0.05);
    assert!(iv.hi < 0.0, "a clear 4-minute gain hidden: {iv:?}");
}

// ------------------------------------------------------------------ layer 2: selection

#[test]
fn holm_step_down() {
    // sorted: 0.005 <= 0.05/4, 0.01 <= 0.05/3, 0.03 > 0.05/2: stop
    assert_eq!(holm(&[0.01, 0.04, 0.03, 0.005], 0.05), vec![true, false, false, true]);
    assert_eq!(holm(&[0.2, 0.3], 0.05), vec![false, false]);
    assert_eq!(holm(&[0.001, 0.002], 0.05), vec![true, true]);
}

#[test]
fn p_value_agrees_with_the_interval() {
    let base = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
    let cand = [5.4, 6.1, 7.9, 8.2, 9.8, 10.3];
    let iv = paired(&base, &cand, 0.05);
    let p = paired_p_value(&base, &cand);
    assert_eq!(iv.lo > 0.0, p < 0.05, "interval {iv:?}, p {p}");
}

#[test]
fn comparing_together_widens_intervals() {
    let base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
    let a: Vec<f64> = base.iter().enumerate().map(|(i, x)| x + 0.5 + 0.1 * (i % 4) as f64).collect();
    let one = paired(&base, &a, 0.05);
    let three = bonferroni_paired(&base, &[a.clone(), a.clone(), a.clone()], 0.05);
    assert_eq!(three.len(), 3);
    assert!(three[0].hi - three[0].lo > one.hi - one.lo);
    // the per-comparison level is 1 - 0.05/3, with t quantile 2.9333 at 9 degrees of freedom
    let ratio = (three[0].hi - three[0].lo) / (one.hi - one.lo);
    assert!(close(ratio, 2.9333240883739881054 / 2.2621571627982049992, 1e-9), "{ratio}");
    assert!(three[0].guarantee.contains("together"), "{}", three[0].guarantee);
}

#[test]
fn confidence_sequence_is_anytime_valid() {
    // differences uniform in [-1, 1] around mean 0.1; across 300 runs of 400 seeds each, the
    // sequence must exclude the true mean at ANY time in at most 5% of runs
    let mut r = PyRandom::from_str_seed("uq/cs");
    let runs = 300;
    let mut ever_wrong = 0;
    for _ in 0..runs {
        let mut cs = ConfSeq::new(-1.0, 1.0, 0.05, 50.0);
        let mut wrong = false;
        for _ in 0..400 {
            let d = (0.1 + r.uniform(-0.9, 0.9)).clamp(-1.0, 1.0);
            cs.push(d);
            let (lo, hi) = cs.bounds();
            if !(lo <= 0.1 && 0.1 <= hi) {
                wrong = true;
            }
        }
        if wrong {
            ever_wrong += 1;
        }
    }
    assert!((ever_wrong as f64) / (runs as f64) <= 0.05, "{ever_wrong} of {runs} runs went wrong");
}

#[test]
fn confidence_sequence_shrinks_and_costs_more_than_a_fixed_interval() {
    let mut cs = ConfSeq::new(-1.0, 1.0, 0.05, 50.0);
    let mut widths = vec![];
    let mut r = PyRandom::from_str_seed("uq/shrink");
    let mut xs = vec![];
    for n in 1..=1000 {
        let d = r.uniform(-1.0, 1.0);
        xs.push(d);
        cs.push(d);
        if n == 100 || n == 1000 {
            let (lo, hi) = cs.bounds();
            widths.push(hi - lo);
        }
    }
    assert!(widths[1] < widths[0] / 2.0, "{widths:?}");
    // never narrower than the Hoeffding fixed-n interval at the same n and level
    // width = 2 * (b - a) * sqrt(ln(2 / alpha) / (2 n)), with b - a = 2
    let hoeffding = 2.0 * 2.0 * ((2.0f64 / 0.05).ln() / (2.0 * 1000.0)).sqrt();
    assert!(widths[1] >= hoeffding * 0.999, "{} vs {hoeffding}", widths[1]);
    assert_eq!(cs.n(), 1000);
}

#[test]
fn race_drops_losers_and_keeps_the_best() {
    // three candidates against the incumbent: mean differences -0.4, 0.0, +0.4, in [-2, 2];
    // over 100 races the best is never dropped more often than alpha, and the worst is dropped
    let mut r = PyRandom::from_str_seed("uq/race");
    let mut best_dropped = 0;
    let mut worst_dropped = 0;
    for _ in 0..100 {
        let mut race = Race::new(3, -2.0, 2.0, 0.05, 20.0);
        for _ in 0..600 {
            let diffs: Vec<f64> = [-0.4, 0.0, 0.4]
                .iter()
                .map(|m| (m + r.uniform(-1.0, 1.0)).clamp(-2.0, 2.0))
                .collect();
            race.push(&diffs);
        }
        let alive = race.alive();
        if !alive[2] {
            best_dropped += 1;
        }
        if !alive[0] {
            worst_dropped += 1;
        }
    }
    assert!(best_dropped <= 5, "best dropped {best_dropped} times");
    assert!(worst_dropped >= 90, "worst dropped only {worst_dropped} times");
}

#[test]
fn race_never_revives() {
    let mut race = Race::new(2, -1.0, 1.0, 0.05, 10.0);
    for _ in 0..2000 {
        race.push(&[-1.0, 0.0]);
    }
    assert!(!race.alive()[0]);
    for _ in 0..2000 {
        race.push(&[1.0, 0.0]);
    }
    assert!(!race.alive()[0], "a dropped candidate came back");
    assert!(race.seeds_used()[0] < 2000);
}

// ------------------------------------------------------------------ layer 3: open questions

#[test]
fn values_carry_their_basis() {
    let said = Value::said(4.0, "the shift report: tool down 4 hours");
    let assumed = Value::assumed(1.0, 12.0, "outage length not given; swept 1 to 12 hours");
    assert_eq!(said.basis, Basis::Said);
    assert_eq!(assumed.basis, Basis::Assumed);
    assert_eq!(assumed.range, Some((1.0, 12.0)));
    assert!(said.range.is_none());
}

#[test]
fn crossover_is_found_and_hedged() {
    use fabsim::uq::Interval;
    let iv = |lo: f64, hi: f64| Interval::from_bounds(lo, hi, 10, 0.05);
    // B minus A, higher is better for B: B loses at short outages and wins at long ones
    let pts = vec![
        (1.0, iv(-3.0, -1.0)),
        (2.0, iv(-2.0, -0.5)),
        (4.0, iv(-1.0, 1.5)),
        (6.0, iv(0.5, 2.0)),
        (8.0, iv(1.0, 3.0)),
    ];
    match crossover(&pts) {
        Crossover::Between { last_clear_before, first_clear_after, unclear } => {
            assert_eq!((last_clear_before, first_clear_after), (2.0, 6.0));
            assert_eq!(unclear, vec![4.0]);
        }
        other => panic!("{other:?}"),
    }
    let all_better = vec![(1.0, iv(0.5, 1.0)), (2.0, iv(0.2, 2.0))];
    assert!(matches!(crossover(&all_better), Crossover::None(Verdict::Better)));
    let unclear = vec![(1.0, iv(-0.5, 1.0)), (2.0, iv(-0.2, 2.0))];
    assert!(matches!(crossover(&unclear), Crossover::Unclear));
}

// ------------------------------------------------------------------ layer 5: qualification

#[test]
fn verdicts_are_three_valued() {
    use fabsim::uq::Interval;
    assert_eq!(verdict(&Interval::from_bounds(0.5, 1.5, 10, 0.05), true), Verdict::Better);
    assert_eq!(verdict(&Interval::from_bounds(0.5, 1.5, 10, 0.05), false), Verdict::Worse);
    assert_eq!(verdict(&Interval::from_bounds(-0.5, 1.5, 10, 0.05), true), Verdict::CannotSay);
    assert_eq!(Verdict::CannotSay.label(), "no clear effect on the SMT2020 model");
    assert_eq!(REAL_FAB_EFFECT, "Real-fab effect: cannot say");
}

#[test]
fn minimum_detectable_effect() {
    // (t_{0.975,9} + t_{0.8,9}) * sd / sqrt(n)
    let want = (2.2621571627982049992 + 0.88340385968553470914) * 2.0 / (10.0f64).sqrt();
    assert!(close(min_detectable_effect(2.0, 10, 0.05, 0.8), want, 1e-9));
}
