# Uncertainty in Fab Gym

Every claim is a difference against today's rules on the SMT2020 model, run on the same seeds
(common random numbers), with an interval and its guarantee. Code: `crates/fabsim/src/uq.rs`;
tests: `crates/fabsim/tests/uq.rs`.

## Layer 1: randomness in a run

For seeds i = 1..n, d_i = score(candidate, seed i) − score(today, seed i).

    mean ± t(1 − α/2, n − 1) · s / √n,    s² = Σ (d_i − mean)² / (n − 1)

Guarantee: probable at level 1 − α (95% by default); exact if the d_i are normal, asymptotic
otherwise. The t quantile is computed from the regularised incomplete beta function and agrees
with mpmath (50 digits) to 1e-10. Pairing cancels the shocks that both runs share, so a small
effect shows through day-to-day noise. A simulated check over 4,000 repetitions gives coverage
within three standard errors of 95%.

Minimum detectable effect with power 1 − β: (t(1 − α/2, n − 1) + t(1 − β, n − 1)) · s / √n.

## Layer 2: searching too hard

- **Search on training seeds (100 and up).** Each candidate's differences go into a confidence
  sequence that holds at every n at once. With values in [a, b], σ = (b − a)/2 (Hoeffding's
  lemma), V_n = nσ² and ρ = mσ²:

      |mean_n − μ| < √((V_n + ρ) · ln((V_n + ρ) / (ρ α²))) / n    for all n, with probability ≥ 1 − α

  This comes from a normal mixture supermartingale and Ville's inequality (Robbins 1970; Howard,
  Ramdas, McAuliffe and Sekhon 2021). Checking after every seed and stopping at any time cost no
  validity. The race runs each of k sequences at level α/k. It drops a candidate once its
  sequence lies wholly below zero or wholly below another live candidate's. With probability
  ≥ 1 − α the best candidate is never dropped.
- **The claim, on held-out seeds 0 to 9, scored once.** When m options are reported together,
  each interval runs at level α/m (Bonferroni), so all m cover at once with probability
  ≥ 1 − α. Holm's step-down procedure controls the family-wise error of the tests.

## Layer 3: what the question leaves open

Each value in a scenario is **said** (given in the question or the shop) or **assumed** (a range
the question leaves open). An assumed range is swept, and the crossover is reported: the last
point where the verdict is clear one way, the first point where it is clear the other way, and
the points in between with no clear effect. That gap is the question worth asking back ("B wins
if the outage runs past N hours. How long will it be?").

## Layer 5: the gap to a real fab

A verdict is three-valued: better, worse, or no clear effect, always "on the SMT2020 model". Every
card also says "Real-fab effect: cannot say".

Layer 4 (redrawing the SMT2020 model's own breakdown and repair numbers) comes later.
