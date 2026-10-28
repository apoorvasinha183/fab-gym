//! Floor and rules evolved together (docs/EVOLVE.md): an ant colony builds floors (which groups get copies for
//! family B, how many tools, where, and family B's cap) and genetic programming breeds dispatch rules. On the
//! SMT2020 model, with a layout of our own design; not a real fab.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use crate::gp::{self, Expr};
use crate::pyrandom::PyRandom;
use crate::shop::Shop;
use crate::twofam::copy_groups;

/// Pheromone kept after each generation's evaporation is 1 − RHO.
pub const RHO: f64 = 0.2;
pub const TAU_MIN: f64 = 0.05;
pub const TAU_MAX: f64 = 5.0;
/// What the best four individuals deposit on their choices, best first.
pub const DEPOSITS: [f64; 4] = [0.4, 0.3, 0.2, 0.1];

/// What the ants choose from.
#[derive(Clone, Debug, PartialEq)]
pub struct Space {
    /// candidate groups for copies, with the load that is their heuristic
    pub groups: Vec<String>,
    pub loads: Vec<f64>,
    /// most copy tools in all
    pub max_tools: usize,
    /// most tools in one copy (3: the pheromone table has 0 to 3)
    pub per_group: usize,
    /// family B's cap as a multiple of its average load in lots; None for no cap
    pub caps: Vec<Option<f64>>,
}

impl Space {
    pub fn new(groups: Vec<String>, loads: Vec<f64>, max_tools: usize) -> Space {
        Space { groups, loads, max_tools, per_group: 3, caps: vec![None, Some(0.75), Some(1.0), Some(1.5), Some(2.0)] }
    }
}

/// One floor: tools copied per candidate group, in a wing or in the halls, and the cap's index in `Space::caps`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Floor {
    pub tools: Vec<usize>,
    pub wing: bool,
    pub cap: usize,
}

/// The colony's pheromone (MAX-MIN ant system).
#[derive(Clone, Debug, PartialEq)]
pub struct Ants {
    pub tau_tools: Vec<[f64; 4]>,
    /// [halls, wing]
    pub tau_place: [f64; 2],
    pub tau_cap: Vec<f64>,
}

fn roulette(rng: &mut PyRandom, w: &[f64]) -> usize {
    let total: f64 = w.iter().sum();
    let mut x = rng.random() * total;
    for (i, &v) in w.iter().enumerate() {
        if x < v {
            return i;
        }
        x -= v;
    }
    w.len() - 1
}

impl Ants {
    pub fn new(s: &Space) -> Ants {
        Ants { tau_tools: vec![[1.0; 4]; s.groups.len()], tau_place: [1.0; 2], tau_cap: vec![1.0; s.caps.len()] }
    }

    /// One floor: groups in a random order, each choice by pheromone times heuristic (the group's load for a copy,
    /// 1 for none); a choice that would pass the tool limit becomes 0.
    pub fn build(&self, s: &Space, rng: &mut PyRandom) -> Floor {
        let n = s.groups.len();
        let mut order: Vec<usize> = (0..n).collect();
        for i in 0..n.saturating_sub(1) {
            let j = i + ((rng.random() * (n - i) as f64) as usize).min(n - i - 1);
            order.swap(i, j);
        }
        let mut tools = vec![0; n];
        let mut total = 0;
        for g in order {
            let w: Vec<f64> =
                (0..=s.per_group).map(|t| self.tau_tools[g][t] * if t == 0 { 1.0 } else { s.loads[g] }).collect();
            let mut t = roulette(rng, &w);
            if total + t > s.max_tools {
                t = 0;
            }
            tools[g] = t;
            total += t;
        }
        let wing = roulette(rng, &self.tau_place) == 1;
        let cap = roulette(rng, &self.tau_cap);
        Floor { tools, wing, cap }
    }

    /// Evaporate everything by RHO, then the ranked floors (best first, at most four) deposit on their choices;
    /// pheromone kept within [TAU_MIN, TAU_MAX].
    pub fn update(&mut self, ranked: &[Floor]) {
        let mut d_tools = vec![[0.0; 4]; self.tau_tools.len()];
        let mut d_place = [0.0; 2];
        let mut d_cap = vec![0.0; self.tau_cap.len()];
        for (f, &dep) in ranked.iter().zip(DEPOSITS.iter()) {
            for (g, &t) in f.tools.iter().enumerate() {
                d_tools[g][t] += dep;
            }
            d_place[f.wing as usize] += dep;
            d_cap[f.cap] += dep;
        }
        let upd = |tau: &mut f64, d: f64| *tau = ((1.0 - RHO) * *tau + d).clamp(TAU_MIN, TAU_MAX);
        for (row, d) in self.tau_tools.iter_mut().zip(&d_tools) {
            for (tau, &x) in row.iter_mut().zip(d) {
                upd(tau, x);
            }
        }
        for (tau, &x) in self.tau_place.iter_mut().zip(&d_place) {
            upd(tau, x);
        }
        for (tau, &x) in self.tau_cap.iter_mut().zip(&d_cap) {
            upd(tau, x);
        }
    }
}

/// The copies a floor names, as (group, tools).
pub fn picks(s: &Space, f: &Floor) -> Vec<(String, usize)> {
    s.groups.iter().zip(&f.tools).filter(|(_, &t)| t > 0).map(|(g, &t)| (g.clone(), t)).collect()
}

/// The shop with the floor's copies and cap (no layout): the cap is ⌈multiple × `avg_lots`⌉.
pub fn floor_shop(shop: &Shop, s: &Space, f: &Floor, avg_lots: f64, family: &str) -> Result<Shop, String> {
    let mut out = copy_groups(shop, &picks(s, f), family)?;
    if let Some(m) = s.caps[f.cap] {
        out.famcaps.push((family.to_string(), (m * avg_lots).ceil() as i64));
    }
    Ok(out)
}

/// The search's settings (docs/EVOLVE.md).
#[derive(Clone, Debug, PartialEq)]
pub struct Settings {
    pub population: usize,
    pub generations: usize,
    pub seeds: Vec<u64>,
    pub seed: u64,
    pub threads: usize,
    pub tournament: usize,
    pub p_cross: f64,
    pub p_mutate: f64,
}

impl Default for Settings {
    fn default() -> Settings {
        Settings {
            population: 16,
            generations: 12,
            seeds: vec![3000, 3001, 3002],
            seed: 1,
            threads: 4,
            tournament: 3,
            p_cross: 0.7,
            p_mutate: 0.2,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Individual {
    pub floor: Floor,
    pub rule: Expr,
    /// mean money a day over the training seeds
    pub fitness: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct History {
    pub generations: Vec<Vec<Individual>>,
}

fn tournament<'a>(gen: &'a [Individual], k: usize, rng: &mut PyRandom) -> &'a Individual {
    let n = gen.len();
    let mut best: Option<&Individual> = None;
    for _ in 0..k.max(1) {
        let c = &gen[((rng.random() * n as f64) as usize).min(n - 1)];
        if best.is_none_or(|b| c.fitness > b.fitness) {
            best = Some(c);
        }
    }
    best.unwrap()
}

/// The joint search. `eval` scores one floor and rule on one seed; it is called from several threads, and the
/// history is the same on any number of them.
pub fn search(eval: &(dyn Fn(&Floor, &Expr, u64) -> f64 + Sync), s: &Space, set: &Settings) -> History {
    let mut rng = PyRandom::from_str_seed(&format!("fabgym-evolve-{}", set.seed));
    let mut ants = Ants::new(s);
    let pop = set.population.max(2);
    let mut rules: Vec<Expr> = vec![Expr::today(), Expr::fifo()];
    while rules.len() < pop {
        rules.push(gp::random_tree(&mut rng, 2, 4));
    }
    rules.truncate(pop);
    let mut kept: Option<Individual> = None;
    let mut history = History { generations: vec![] };
    for _ in 0..set.generations {
        // pair the ants' floors with the rules; the kept individual comes first, whole
        let mut gen: Vec<Option<Individual>> = vec![None; pop];
        let start = if let Some(k) = &kept {
            gen[0] = Some(k.clone());
            1
        } else {
            0
        };
        let mut todo: Vec<(Floor, Expr)> = vec![];
        for i in start..pop {
            todo.push((ants.build(s, &mut rng), rules[i].clone()));
        }
        let jobs: Vec<(usize, u64)> = (0..todo.len()).flat_map(|i| set.seeds.iter().map(move |&sd| (i, sd))).collect();
        let next = AtomicUsize::new(0);
        let scores: Mutex<Vec<f64>> = Mutex::new(vec![0.0; jobs.len()]);
        std::thread::scope(|sc| {
            for _ in 0..set.threads.max(1).min(jobs.len().max(1)) {
                sc.spawn(|| loop {
                    let j = next.fetch_add(1, Ordering::SeqCst);
                    let Some(&(i, sd)) = jobs.get(j) else { break };
                    let v = eval(&todo[i].0, &todo[i].1, sd);
                    scores.lock().unwrap()[j] = v;
                });
            }
        });
        let scores = scores.into_inner().unwrap();
        let ns = set.seeds.len().max(1);
        for (i, (floor, rule)) in todo.into_iter().enumerate() {
            let fitness = scores[i * ns..(i + 1) * ns].iter().sum::<f64>() / ns as f64;
            gen[start + i] = Some(Individual { floor, rule, fitness });
        }
        let gen: Vec<Individual> = gen.into_iter().map(|x| x.unwrap()).collect();
        // rank, feed the ants, keep the best whole
        let mut order: Vec<usize> = (0..gen.len()).collect();
        order.sort_by(|&a, &b| gen[b].fitness.total_cmp(&gen[a].fitness).then(a.cmp(&b)));
        let ranked: Vec<Floor> = order.iter().take(DEPOSITS.len()).map(|&i| gen[i].floor.clone()).collect();
        ants.update(&ranked);
        let best = gen[order[0]].clone();
        // the next rules: the best's first, the rest bred by tournament
        let mut next_rules = vec![best.rule.clone()];
        while next_rules.len() < pop {
            let a = tournament(&gen, set.tournament, &mut rng).rule.clone();
            let mut child = if rng.random() < set.p_cross {
                let b = tournament(&gen, set.tournament, &mut rng).rule.clone();
                gp::crossover(&a, &b, &mut rng)
            } else {
                a
            };
            if rng.random() < set.p_mutate {
                child = gp::mutate(&child, &mut rng);
            }
            next_rules.push(child);
        }
        rules = next_rules;
        kept = Some(best);
        history.generations.push(gen);
    }
    history
}
