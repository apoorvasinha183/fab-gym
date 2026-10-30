//! Uncertainty, quantified and qualified.
//!
//! Every number Fab Gym shows about a candidate is a difference against today's rules on the
//! same seeds (common random numbers), with an interval and a stated guarantee. The layers
//! follow docs/PROBLEM.md:
//!
//! 1. Randomness in a run. [`paired`]: the Student t interval of the per-seed differences.
//!    Guarantee: probable, level 1 - alpha; exact when the differences are normal and
//!    asymptotic (central limit theorem) otherwise.
//! 2. Searching too hard. During search, [`Race`] runs candidates on training seeds (100 and
//!    up) and drops one as soon as an anytime-valid confidence sequence ([`ConfSeq`]) shows it
//!    worse than the incumbent or than another candidate; peeking after every seed costs no
//!    validity. The final claim is scored once on the held-out seeds 0 to 9; when several
//!    options are reported together, [`bonferroni_paired`] widens the intervals and [`holm`]
//!    controls the family-wise error of the tests.
//! 3. What the question leaves open. A [`Value`] is said (given in the question) or assumed
//!    (a range the question leaves open). The range is swept and [`crossover`] reports where
//!    the better option changes, which becomes the question worth asking back.
//! 5. The gap to a real fab. Every verdict is about the SMT2020 testbed; the real-fab effect is
//!    always [`REAL_FAB_EFFECT`].
//!
//! No external crates: the t distribution comes from the regularised incomplete beta function
//! (continued fraction, Lentz's method) and a Lanczos log-gamma.

use std::f64::consts::PI;

// ------------------------------------------------------------------ special functions

/// ln Γ(x) for x > 0 (Lanczos, g = 7, nine terms; relative error about 1e-15).
pub fn ln_gamma(x: f64) -> f64 {
    const G: f64 = 7.0;
    const C: [f64; 9] = [
        0.999_999_999_999_809_9,
        676.520_368_121_885_1,
        -1_259.139_216_722_402_8,
        771.323_428_777_653_1,
        -176.615_029_162_140_6,
        12.507_343_278_686_905,
        -0.138_571_095_265_720_12,
        9.984_369_578_019_572e-6,
        1.505_632_735_149_311_6e-7,
    ];
    if x < 0.5 {
        // reflection
        return (PI / (PI * x).sin()).ln() - ln_gamma(1.0 - x);
    }
    let x = x - 1.0;
    let mut a = C[0];
    let t = x + G + 0.5;
    for (i, c) in C.iter().enumerate().skip(1) {
        a += c / (x + i as f64);
    }
    0.5 * (2.0 * PI).ln() + (x + 0.5) * t.ln() - t + a.ln()
}

fn beta_cf(a: f64, b: f64, x: f64) -> f64 {
    const TINY: f64 = 1e-300;
    let (qab, qap, qam) = (a + b, a + 1.0, a - 1.0);
    let mut c = 1.0;
    let mut d = 1.0 - qab * x / qap;
    if d.abs() < TINY {
        d = TINY;
    }
    d = 1.0 / d;
    let mut h = d;
    for m in 1..1000 {
        let m = m as f64;
        let m2 = 2.0 * m;
        let aa = m * (b - m) * x / ((qam + m2) * (a + m2));
        d = 1.0 + aa * d;
        if d.abs() < TINY {
            d = TINY;
        }
        c = 1.0 + aa / c;
        if c.abs() < TINY {
            c = TINY;
        }
        d = 1.0 / d;
        h *= d * c;
        let aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
        d = 1.0 + aa * d;
        if d.abs() < TINY {
            d = TINY;
        }
        c = 1.0 + aa / c;
        if c.abs() < TINY {
            c = TINY;
        }
        d = 1.0 / d;
        let del = d * c;
        h *= del;
        if (del - 1.0).abs() < 1e-16 {
            break;
        }
    }
    h
}

/// The regularised incomplete beta function I_x(a, b), with y = 1 - x passed exactly.
fn inc_beta(a: f64, b: f64, x: f64, y: f64) -> f64 {
    if x <= 0.0 {
        return 0.0;
    }
    if y <= 0.0 {
        return 1.0;
    }
    let ln_front = ln_gamma(a + b) - ln_gamma(a) - ln_gamma(b) + a * x.ln() + b * y.ln();
    let front = ln_front.exp();
    if x < (a + 1.0) / (a + b + 2.0) {
        front * beta_cf(a, b, x) / a
    } else {
        1.0 - front * beta_cf(b, a, y) / b
    }
}

/// P(T > |t|) for Student's t with `df` degrees of freedom (one tail).
fn t_tail(t: f64, df: f64) -> f64 {
    let t2 = t * t;
    let x = df / (df + t2);
    let y = t2 / (df + t2);
    0.5 * inc_beta(df / 2.0, 0.5, x, y)
}

/// The cumulative distribution function of Student's t.
pub fn t_cdf(t: f64, df: f64) -> f64 {
    if t == 0.0 {
        return 0.5;
    }
    let tail = t_tail(t, df);
    if t > 0.0 {
        1.0 - tail
    } else {
        tail
    }
}

/// The p-quantile of Student's t with `df` degrees of freedom (bisection to full precision).
pub fn t_quantile(p: f64, df: f64) -> f64 {
    assert!(p > 0.0 && p < 1.0 && df > 0.0, "t_quantile({p}, {df})");
    if p == 0.5 {
        return 0.0;
    }
    if p < 0.5 {
        return -t_quantile(1.0 - p, df);
    }
    let want = 1.0 - p; // upper tail
    let (mut lo, mut hi) = (0.0f64, 1.0f64);
    while t_tail(hi, df) > want {
        lo = hi;
        hi *= 2.0;
    }
    for _ in 0..200 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if t_tail(mid, df) > want {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    0.5 * (lo + hi)
}

// ------------------------------------------------------------------ layer 1

/// An interval on a difference (candidate minus incumbent), with its guarantee in words.
#[derive(Clone, Debug)]
pub struct Interval {
    pub mean: f64,
    pub lo: f64,
    pub hi: f64,
    pub n: usize,
    pub sd: f64,
    pub alpha: f64,
    pub guarantee: String,
}

impl Interval {
    /// An interval given by its bounds (for sweeps and tests).
    pub fn from_bounds(lo: f64, hi: f64, n: usize, alpha: f64) -> Interval {
        Interval {
            mean: 0.5 * (lo + hi),
            lo,
            hi,
            n,
            sd: f64::NAN,
            alpha,
            guarantee: format!("given bounds at level {:.0}%", (1.0 - alpha) * 100.0),
        }
    }
}

fn mean_sd(d: &[f64]) -> (f64, f64) {
    let n = d.len() as f64;
    let mean = d.iter().sum::<f64>() / n;
    let ss: f64 = d.iter().map(|x| (x - mean) * (x - mean)).sum();
    let sd = if d.len() > 1 { (ss / (n - 1.0)).sqrt() } else { f64::NAN };
    (mean, sd)
}

fn diffs(base: &[f64], cand: &[f64]) -> Vec<f64> {
    assert_eq!(base.len(), cand.len(), "paired runs need the same seeds");
    base.iter().zip(cand).map(|(b, c)| c - b).collect()
}

fn pct(alpha: f64) -> String {
    let p = (1.0 - alpha) * 100.0;
    if (p - p.round()).abs() < 1e-9 {
        format!("{:.0}%", p)
    } else {
        format!("{:.2}%", p)
    }
}

/// Layer 1: the paired t interval of `cand - base` over the same seeds, at level 1 - alpha.
pub fn paired(base: &[f64], cand: &[f64], alpha: f64) -> Interval {
    let d = diffs(base, cand);
    let n = d.len();
    let (mean, sd) = mean_sd(&d);
    let (lo, hi) = if n < 2 {
        (f64::NEG_INFINITY, f64::INFINITY)
    } else {
        let half = t_quantile(1.0 - alpha / 2.0, (n - 1) as f64) * sd / (n as f64).sqrt();
        (mean - half, mean + half)
    };
    Interval {
        mean,
        lo,
        hi,
        n,
        sd,
        alpha,
        guarantee: format!(
            "probable: {} t interval of the paired difference over {n} seeds; exact if the \
             per-seed differences are normal, asymptotic otherwise",
            pct(alpha)
        ),
    }
}

/// The two-sided p-value of the paired t test of no difference.
pub fn paired_p_value(base: &[f64], cand: &[f64]) -> f64 {
    let d = diffs(base, cand);
    let n = d.len();
    let (mean, sd) = mean_sd(&d);
    if n < 2 {
        return 1.0;
    }
    if sd == 0.0 {
        return if mean == 0.0 { 1.0 } else { 0.0 };
    }
    let t = mean / (sd / (n as f64).sqrt());
    (2.0 * t_tail(t, (n - 1) as f64)).min(1.0)
}

/// The smallest true difference that `n` paired seeds detect with the given power, for
/// per-seed differences with standard deviation `sd` (two-sided test at level alpha).
pub fn min_detectable_effect(sd: f64, n: usize, alpha: f64, power: f64) -> f64 {
    let df = (n - 1) as f64;
    (t_quantile(1.0 - alpha / 2.0, df) + t_quantile(power, df)) * sd / (n as f64).sqrt()
}

// ------------------------------------------------------------------ layer 2

/// Layer 2: intervals for several options reported together, each at level alpha / m
/// (Bonferroni), so all m cover at once with probability at least 1 - alpha.
pub fn bonferroni_paired(base: &[f64], cands: &[Vec<f64>], alpha: f64) -> Vec<Interval> {
    let m = cands.len().max(1);
    cands
        .iter()
        .map(|c| {
            let mut iv = paired(base, c, alpha / m as f64);
            iv.guarantee = format!(
                "probable: simultaneous {} over {m} options compared together (Bonferroni, each \
                 a {} t interval of the paired difference over {} seeds; exact if the per-seed \
                 differences are normal, asymptotic otherwise)",
                pct(alpha),
                pct(alpha / m as f64),
                iv.n
            );
            iv
        })
        .collect()
}

/// Holm's step-down procedure: which of the m hypotheses are rejected, with family-wise error
/// at most alpha.
pub fn holm(p: &[f64], alpha: f64) -> Vec<bool> {
    let m = p.len();
    let mut idx: Vec<usize> = (0..m).collect();
    idx.sort_by(|a, b| p[*a].partial_cmp(&p[*b]).unwrap());
    let mut out = vec![false; m];
    for (k, &i) in idx.iter().enumerate() {
        if p[i] <= alpha / (m - k) as f64 {
            out[i] = true;
        } else {
            break;
        }
    }
    out
}

/// An anytime-valid confidence sequence for the mean of independent values in [lo, hi]:
/// with probability at least 1 - alpha, the true mean lies inside `bounds()` at every n at once,
/// so it may be checked after every seed and the search stopped at any time.
///
/// Values in [lo, hi] are sub-Gaussian with sigma = (hi - lo) / 2 (Hoeffding's lemma). With
/// S_n the centred sum and V_n = n sigma^2, the normal mixture of exp(lambda S - lambda^2 V / 2)
/// over lambda ~ N(0, 1 / rho) is a nonnegative supermartingale, and Ville's inequality gives
/// |S_n| < sqrt((V_n + rho) ln((V_n + rho) / (rho alpha^2))) for all n with probability at
/// least 1 - alpha (Robbins 1970; Howard, Ramdas, McAuliffe, Sekhon 2021). `rho = m sigma^2`:
/// the boundary is tightest near n = m seeds.
#[derive(Clone, Debug)]
pub struct ConfSeq {
    lo: f64,
    hi: f64,
    alpha: f64,
    sigma2: f64,
    rho: f64,
    n: usize,
    sum: f64,
}

impl ConfSeq {
    pub fn new(lo: f64, hi: f64, alpha: f64, m: f64) -> ConfSeq {
        assert!(hi > lo && alpha > 0.0 && alpha < 1.0 && m > 0.0);
        let sigma = (hi - lo) / 2.0;
        ConfSeq { lo, hi, alpha, sigma2: sigma * sigma, rho: m * sigma * sigma, n: 0, sum: 0.0 }
    }

    /// Add one value; it must lie in [lo, hi] (values outside are clipped, and the clip is the
    /// caller's stated assumption).
    pub fn push(&mut self, x: f64) {
        self.sum += x.clamp(self.lo, self.hi);
        self.n += 1;
    }

    pub fn n(&self) -> usize {
        self.n
    }

    pub fn mean(&self) -> f64 {
        if self.n == 0 {
            f64::NAN
        } else {
            self.sum / self.n as f64
        }
    }

    /// The current bounds on the mean, within [lo, hi].
    pub fn bounds(&self) -> (f64, f64) {
        if self.n == 0 {
            return (self.lo, self.hi);
        }
        let v = self.n as f64 * self.sigma2;
        let r = ((v + self.rho) * ((v + self.rho) / (self.rho * self.alpha * self.alpha)).ln()).sqrt();
        let m = self.mean();
        let half = r / self.n as f64;
        ((m - half).max(self.lo), (m + half).min(self.hi))
    }
}

/// A race on training seeds: k candidates, each seed giving every live candidate's difference
/// against the incumbent (higher is better). A candidate is dropped once its confidence sequence
/// lies wholly below zero (worse than today's rules) or wholly below another live candidate's.
/// Each sequence runs at level alpha / k, so with probability at least 1 - alpha no sequence is
/// ever wrong and the best candidate is never dropped.
#[derive(Clone, Debug)]
pub struct Race {
    cs: Vec<ConfSeq>,
    alive: Vec<bool>,
}

impl Race {
    pub fn new(k: usize, lo: f64, hi: f64, alpha: f64, m: f64) -> Race {
        Race { cs: (0..k).map(|_| ConfSeq::new(lo, hi, alpha / k as f64, m)).collect(), alive: vec![true; k] }
    }

    /// One seed's differences, one per candidate (dropped candidates' entries are ignored).
    pub fn push(&mut self, d: &[f64]) {
        assert_eq!(d.len(), self.cs.len());
        for (i, x) in d.iter().enumerate() {
            if self.alive[i] {
                self.cs[i].push(*x);
            }
        }
        let b: Vec<(f64, f64)> = self.cs.iter().map(|c| c.bounds()).collect();
        let best_lo = (0..b.len()).filter(|i| self.alive[*i]).map(|i| b[i].0).fold(f64::NEG_INFINITY, f64::max);
        for i in 0..b.len() {
            if self.alive[i] && (b[i].1 < 0.0 || b[i].1 < best_lo) {
                self.alive[i] = false;
            }
        }
    }

    pub fn alive(&self) -> Vec<bool> {
        self.alive.clone()
    }

    pub fn seeds_used(&self) -> Vec<usize> {
        self.cs.iter().map(|c| c.n()).collect()
    }

    pub fn bounds(&self) -> Vec<(f64, f64)> {
        self.cs.iter().map(|c| c.bounds()).collect()
    }
}

// ------------------------------------------------------------------ layer 3

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Basis {
    /// given in the question or the shop
    Said,
    /// left open by the question; a range is swept
    Assumed,
}

/// A value in a scenario, with where it came from.
#[derive(Clone, Debug)]
pub struct Value {
    pub x: Option<f64>,
    pub range: Option<(f64, f64)>,
    pub basis: Basis,
    pub note: String,
}

impl Value {
    pub fn said(x: f64, note: &str) -> Value {
        Value { x: Some(x), range: None, basis: Basis::Said, note: note.into() }
    }

    pub fn assumed(lo: f64, hi: f64, note: &str) -> Value {
        Value { x: None, range: Some((lo, hi)), basis: Basis::Assumed, note: note.into() }
    }
}

/// Where, along a swept value, the better option changes.
#[derive(Clone, Debug)]
pub enum Crossover {
    /// the same clear verdict over the whole range
    None(Verdict),
    /// one clear verdict over part of the range, no clear effect elsewhere
    Partial(Verdict),
    /// no clear verdict anywhere in the range
    Unclear,
    /// the verdict changes once: clear at `last_clear_before`, the other way at
    /// `first_clear_after`, with no clear effect at the points in between
    Between { last_clear_before: f64, first_clear_after: f64, unclear: Vec<f64> },
    /// the verdict changes more than once: each (from, to) pair of clear points
    Several(Vec<(f64, f64)>),
}

/// The crossover of a sweep: points (x, interval of B minus A, higher is better), sorted by x.
pub fn crossover(points: &[(f64, Interval)]) -> Crossover {
    let v: Vec<(f64, Verdict)> = points.iter().map(|(x, iv)| (*x, verdict(iv, true))).collect();
    let clear: Vec<(usize, Verdict)> =
        v.iter().enumerate().filter(|(_, (_, k))| *k != Verdict::CannotSay).map(|(i, (_, k))| (i, *k)).collect();
    if clear.is_empty() {
        return Crossover::Unclear;
    }
    let mut switches = vec![];
    for w in clear.windows(2) {
        if w[0].1 != w[1].1 {
            switches.push((w[0].0, w[1].0));
        }
    }
    match switches.len() {
        0 => {
            if clear.len() == v.len() {
                Crossover::None(clear[0].1)
            } else {
                Crossover::Partial(clear[0].1)
            }
        }
        1 => {
            let (a, b) = switches[0];
            Crossover::Between {
                last_clear_before: v[a].0,
                first_clear_after: v[b].0,
                unclear: v[a + 1..b].iter().map(|(x, _)| *x).collect(),
            }
        }
        _ => Crossover::Several(switches.iter().map(|(a, b)| (v[*a].0, v[*b].0)).collect()),
    }
}

// ------------------------------------------------------------------ qualification (layer 5)

/// A three-valued verdict from the SMT2020 testbed.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    Better,
    Worse,
    CannotSay,
}

impl Verdict {
    pub fn label(self) -> &'static str {
        match self {
            Verdict::Better => "better from the SMT2020 testbed",
            Verdict::Worse => "worse from the SMT2020 testbed",
            Verdict::CannotSay => "no clear effect from the SMT2020 testbed",
        }
    }
}

/// Better if the interval of the difference lies wholly on the good side of zero, worse if
/// wholly on the bad side, otherwise no clear effect.
pub fn verdict(iv: &Interval, higher_is_better: bool) -> Verdict {
    let (good, bad) = if higher_is_better { (Verdict::Better, Verdict::Worse) } else { (Verdict::Worse, Verdict::Better) };
    if iv.lo > 0.0 {
        good
    } else if iv.hi < 0.0 {
        bad
    } else {
        Verdict::CannotSay
    }
}

/// What every card says about a real fab: the simulator builds its fab from a published testbed; it is not a real fab.
pub const REAL_FAB_EFFECT: &str = "Real-fab effect: cannot say";

/// Layer 4 (docs/UQ-INPUTS.md): paired runs nested in draws of the inputs. `base[p][s]` and `cand[p][s]` are draw p's
/// runs on seed s.
#[derive(Clone, Debug)]
pub struct Nested {
    /// the mean of the draws' mean differences, with a t interval over the draws
    pub interval: Interval,
    /// the variance of the draws' mean differences (luck and input doubt together)
    pub between_var: f64,
    /// the luck alone in a draw's mean: the mean within-draw variance over the seeds per draw
    pub within_var_of_mean: f64,
    /// the share of draws whose mean difference has the overall mean's sign
    pub share_same_sign: f64,
    /// the share of draws whose own paired interval (level 1 - alpha) excludes zero on the overall mean's side
    pub share_clear: f64,
}

pub fn nested_paired(base: &[Vec<f64>], cand: &[Vec<f64>], alpha: f64) -> Nested {
    assert_eq!(base.len(), cand.len(), "the same draws on both sides");
    let per: Vec<Interval> = base.iter().zip(cand).map(|(b, c)| paired(b, c, alpha)).collect();
    let means: Vec<f64> = per.iter().map(|i| i.mean).collect();
    let p = means.len();
    let (mean, sd) = mean_sd(&means);
    let (lo, hi) = if p < 2 {
        (f64::NEG_INFINITY, f64::INFINITY)
    } else {
        let half = t_quantile(1.0 - alpha / 2.0, (p - 1) as f64) * sd / (p as f64).sqrt();
        (mean - half, mean + half)
    };
    let within = per.iter().map(|i| if i.n > 1 { i.sd * i.sd / i.n as f64 } else { f64::NAN }).sum::<f64>() / p as f64;
    let up = mean >= 0.0;
    let same = means.iter().filter(|&&m| (m >= 0.0) == up).count() as f64 / p as f64;
    let clear = per.iter().filter(|i| if up { i.lo > 0.0 } else { i.hi < 0.0 }).count() as f64 / p as f64;
    Nested {
        interval: Interval {
            mean,
            lo,
            hi,
            n: p,
            sd,
            alpha,
            guarantee: format!(
                "probable: {} t interval over {p} draws of the inputs, each the mean paired difference over its seeds; \
                 covers the luck and the input doubt as modelled",
                pct(alpha)
            ),
        },
        between_var: sd * sd,
        within_var_of_mean: within,
        share_same_sign: same,
        share_clear: clear,
    }
}
