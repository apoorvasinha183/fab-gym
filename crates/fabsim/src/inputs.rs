//! Uncertainty layer 4 (docs/UQ-INPUTS.md): the shop's input numbers redrawn, as a fab's estimates might be off.
//!
//! For each tool group, four factors, each lognormal with mean 1, exp(σZ − σ²/2): processing time (every step at the
//! group and its per-piece interval), mean time to failure, mean time to repair, and preventive maintenance length
//! (both ends of its range, by time and by wafers). Draw d seeds its own generator from `inputs/<d>`, apart from any
//! run's seed. Everything else stays as given.

use crate::pyrandom::PyRandom;
use crate::shop::Shop;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Factors {
    pub proc: f64,
    pub ttf: f64,
    pub ttr: f64,
    pub pm: f64,
}

fn normal(r: &mut PyRandom) -> f64 {
    // Box-Muller on the generator's own uniforms
    let u1 = 1.0 - r.random();
    let u2 = r.random();
    (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
}

/// Each group's factors for draw `draw` at spread `sigma`, in the shop's group order.
pub fn factors(shop: &Shop, draw: u64, sigma: f64) -> Vec<Factors> {
    let mut r = PyRandom::from_str_seed(&format!("inputs/{draw}"));
    let mut f = || (sigma * normal(&mut r) - sigma * sigma / 2.0).exp();
    shop.groups.iter().map(|_| Factors { proc: f(), ttf: f(), ttr: f(), pm: f() }).collect()
}

/// The shop with draw `draw`'s factors applied. `sigma` = 0 gives the shop back unchanged.
pub fn perturb(shop: &Shop, draw: u64, sigma: f64) -> Shop {
    if sigma == 0.0 {
        return shop.clone();
    }
    let f = factors(shop, draw, sigma);
    let mut s = shop.clone();
    for (g, grp) in s.groups.iter_mut().enumerate() {
        if let Some((ttf, ttr)) = grp.breakdown {
            grp.breakdown = Some((ttf * f[g].ttf, ttr * f[g].ttr));
        }
        for pm in grp.pm.iter_mut().chain(grp.pm_pieces.iter_mut()) {
            pm.lo *= f[g].pm;
            pm.hi *= f[g].pm;
        }
    }
    let index: std::collections::HashMap<String, usize> = s.groups.iter().enumerate().map(|(i, g)| (g.name.clone(), i)).collect();
    for route in s.routes.iter_mut() {
        for st in route.steps.iter_mut() {
            if let Some(&g) = index.get(&st.group) {
                st.time *= f[g].proc;
                if let Some(i) = st.interval.as_mut() {
                    *i *= f[g].proc;
                }
            }
        }
    }
    s
}

/// The redrawn shop with every release rate multiplied by its ceiling over the published ceiling, so it releases the
/// same multiple of its own capacity as the published shop does (docs/UQ-INPUTS.md, the follow-up).
pub fn equal_load(shop: &Shop, draw: u64, sigma: f64) -> Shop {
    if sigma == 0.0 {
        return shop.clone();
    }
    let mut s = perturb(shop, draw, sigma);
    let m = crate::bound::capacity(&s).wafers_per_day / crate::bound::capacity(shop).wafers_per_day;
    for r in s.releases.iter_mut() {
        if r.every > 0.0 {
            r.every /= m;
        }
    }
    s
}
