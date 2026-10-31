//! The supervisor, a toy experiment (docs/SUPERVISOR-TOY.md): every so often it looks at the fab as it stands, tries
//! settings (the floor's rule and a cap on lots inside) on copies with fresh luck, and keeps the best until the next
//! look. The floor's minute-by-minute choices stay with the rule. Who proposes the settings is the caller's: all of
//! them (the simulator arm), a model's few, or one fixed. On a teaching fab of our own and the SMT2020 testbed; not a
//! real fab.

use crate::engine::{Player, RunOptions, Stepper};
use crate::overrides::Overrides;
use crate::policy::Policy;
use crate::shop::Shop;

/// A top-level setting: the floor's rule and a cap on lots inside (None: no cap).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Setting {
    pub rule: Policy,
    pub cap: Option<i64>,
}

impl Setting {
    pub const TODAY: Setting = Setting { rule: Policy::Today, cap: None };

    pub fn name(&self) -> String {
        match self.cap {
            Some(c) => format!("{} rule, cap {c}", self.rule.name()),
            None => format!("{} rule, no cap", self.rule.name()),
        }
    }
}

/// The settings to choose from: today's rule, FIFO, shortest first and critical ratio, each with every cap given.
pub fn grid(caps: &[Option<i64>]) -> Vec<Setting> {
    let rules = [Policy::Today, Policy::Fifo, Policy::Spt, Policy::CriticalRatio];
    rules.iter().flat_map(|&rule| caps.iter().map(move |&cap| Setting { rule, cap })).collect()
}

/// When to look and how: warm-up and window in minutes, a look every `every`, each tried setting run `horizon`
/// minutes ahead on `copies` copies.
#[derive(Clone, Copy, Debug)]
pub struct Plan {
    pub warmup: f64,
    pub window: f64,
    pub every: f64,
    pub horizon: f64,
    pub copies: u32,
}

/// What the supervisor sees at a look: only the past and the present.
#[derive(Clone, Debug)]
pub struct LookState {
    pub t: f64,
    pub current: Setting,
    pub lots_inside: i64,
    /// since the last look (the warm-up's end for the first)
    pub lots_finished: i64,
    pub lot_hours_waiting: f64,
    /// (name, tools, tools down, lots waiting, the most worn tool's share of its wear limit)
    pub groups: Vec<(String, i64, i64, i64, f64)>,
}

#[derive(Clone, Debug)]
pub struct Look {
    pub t: f64,
    pub current: Setting,
    /// each setting tried and its mean score on the copies
    pub tried: Vec<(Setting, f64)>,
    pub chosen: Setting,
}

#[derive(Clone, Debug)]
pub struct Outcome {
    pub looks: Vec<Look>,
    pub lots_finished: i64,
    pub wafers_per_day: f64,
    pub cycle_days: f64,
    /// lots finished less 0.01 a lot-hour waiting, over the window
    pub value: f64,
}

fn apply(shop: &Shop, s: &mut Stepper, set: Setting, seed: u64) {
    if let Some(p) = s.player_mut() {
        p.switch(shop, set.rule, seed);
    }
    s.set_cap(set.cap);
}

fn start<'a>(shop: &'a Shop, ov: &Overrides, seed: u64, plan: &Plan) -> Stepper<'a> {
    let opts = RunOptions { seed, until: Some(plan.warmup + plan.window + plan.horizon), record: false };
    let mut s = Stepper::with_overrides(shop, &opts, Some(Player::rule(shop, Policy::Today, seed)), ov);
    s.advance(plan.warmup);
    s
}

fn outcome(s: &Stepper, plan: &Plan, v0: f64, looks: Vec<Look>) -> Outcome {
    let (lots, wafers, cycle) = s.finished_between(plan.warmup, plan.warmup + plan.window);
    Outcome {
        looks,
        lots_finished: lots,
        wafers_per_day: wafers as f64 / (plan.window / 1440.0),
        cycle_days: if lots > 0 { cycle / lots as f64 / 1440.0 } else { 0.0 },
        value: s.value() - v0,
    }
}

/// One setting all window long (the today and best-fixed arms): no looks.
pub fn run_fixed(shop: &Shop, ov: &Overrides, seed: u64, plan: &Plan, set: Setting) -> Outcome {
    let mut s = start(shop, ov, seed, plan);
    let v0 = s.value();
    apply(shop, &mut s, set, seed);
    s.advance(plan.warmup + plan.window);
    outcome(&s, plan, v0, vec![])
}

/// The supervised run: at each look `propose` names the settings to try (the current one is always tried too, first,
/// so a tie keeps it); each runs `horizon` ahead on `copies` copies with fresh luck shared across the settings, and the
/// best mean score is applied until the next look.
pub fn run(shop: &Shop, ov: &Overrides, seed: u64, plan: &Plan, grid: &[Setting], propose: &mut dyn FnMut(&LookState, &[Setting]) -> Vec<Setting>) -> Outcome {
    let mut main = start(shop, ov, seed, plan);
    let v0 = main.value();
    let end = plan.warmup + plan.window;
    let mut current = Setting::TODAY;
    let mut looks = vec![];
    let mut t = plan.warmup;
    let (mut f_last, mut w_last) = main.totals();
    let mut k = 0u64;
    while t < end - 1e-9 {
        let (f, w) = main.totals();
        let state = LookState { t, current, lots_inside: main.lots_inside(), lots_finished: f - f_last, lot_hours_waiting: (w - w_last) / 60.0, groups: main.groups_now() };
        f_last = f;
        w_last = w;
        let mut cands = vec![current];
        for s in propose(&state, grid) {
            if !cands.contains(&s) {
                cands.push(s);
            }
        }
        let mut tried = vec![];
        for &set in &cands {
            let mut total = 0.0;
            for c in 0..plan.copies {
                let mut copy = main.clone();
                copy.fresh_luck(seed.wrapping_mul(1_000_003).wrapping_add(k * 1009 + c as u64 + 17));
                apply(shop, &mut copy, set, seed);
                let before = copy.value();
                copy.advance(t + plan.horizon);
                total += copy.value() - before;
            }
            tried.push((set, total / plan.copies as f64));
        }
        let mut best = 0;
        for (i, x) in tried.iter().enumerate() {
            if x.1 > tried[best].1 {
                best = i;
            }
        }
        let chosen = tried[best].0;
        apply(shop, &mut main, chosen, seed);
        looks.push(Look { t, current, tried, chosen });
        current = chosen;
        let next = (t + plan.every).min(end);
        main.advance(next);
        t = next;
        k += 1;
    }
    outcome(&main, plan, v0, looks)
}
