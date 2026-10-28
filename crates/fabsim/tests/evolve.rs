//! Floor and rules evolved together (docs/EVOLVE.md). Written before the code.
//! On the SMT2020 model, with a layout of our own design; not a real fab.

use fabsim::engine::{run, Decision, RunOptions};
use fabsim::evolve::{floor_shop, search, Ants, Floor, Settings, Space, DEPOSITS, RHO, TAU_MAX, TAU_MIN};
use fabsim::gp::{self, Expr, MAX_DEPTH};
use fabsim::money::{money, PriceGrid};
use fabsim::policy::{run_with, Policy as Rule};
use fabsim::pyrandom::PyRandom;
use fabsim::shop::Shop;
use fabsim::window::Window;

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t4\t0.0\t0.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
group\tK\t3\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tK\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
route\trb
step\tG\tlot\t25.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tK\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t20.0\t0.0\t-\tA
release\trb\t5\t10.0\t40.0\t0.0\t-\tB
family\tra\tA
family\trb\tB
";

fn toy() -> Shop {
    Shop::parse(TOY).unwrap()
}

fn opts(seed: u64, until: f64) -> RunOptions {
    RunOptions { seed, until: Some(until), record: true }
}

fn run_tree(shop: &Shop, e: &Expr, o: &RunOptions) -> String {
    let fam = gp::family_numbers(shop);
    let mut pick = |d: &Decision| gp::choose(e, d, &fam);
    run(shop, o, Some(&mut pick)).log_text()
}

// 1. Trees.
#[test]
fn todays_rule_and_fifo_as_trees() {
    let shop = toy();
    let o = opts(3, 4000.0);
    assert_eq!(run_tree(&shop, &Expr::today(), &o), run(&shop, &o, None).log_text());
    assert_eq!(run_tree(&shop, &Expr::fifo(), &o), run_with(&shop, &o, Rule::Fifo).log_text());
    assert_eq!(gp::RULE_FIELDS.len(), 14);
    assert_eq!(gp::RULE_FIELDS.last(), Some(&"family"));
}

#[test]
fn trees_evaluate_as_stated() {
    let mut f = [0.0; 14];
    f[2] = 10.0; // priority
    f[6] = 30.0; // waited_minutes
    let p = || Box::new(Expr::Field(2));
    let w = || Box::new(Expr::Field(6));
    let c = |x: f64| Box::new(Expr::Const(x));
    assert_eq!(Expr::Add(p(), w()).eval(&f), 40.0);
    assert_eq!(Expr::Sub(p(), w()).eval(&f), -20.0);
    assert_eq!(Expr::Mul(p(), c(0.5)).eval(&f), 5.0);
    assert_eq!(Expr::Div(w(), c(0.0)).eval(&f), 1.0, "protected division");
    assert_eq!(Expr::Div(w(), c(1e-10)).eval(&f), 1.0, "protected division near 0");
    assert_eq!(Expr::Div(w(), p()).eval(&f), 3.0);
    assert_eq!(Expr::Min(p(), w()).eval(&f), 10.0);
    assert_eq!(Expr::Max(p(), w()).eval(&f), 30.0);
    assert_eq!(Expr::If(w(), p(), c(1.0), c(2.0)).eval(&f), 1.0);
    assert_eq!(Expr::If(p(), w(), c(1.0), c(2.0)).eval(&f), 2.0);
    assert_eq!(Expr::Add(p(), Box::new(Expr::Mul(w(), c(2.0)))).depth(), 3);
}

#[test]
fn random_trees_crossover_and_mutation_are_seeded_and_shallow() {
    let make = |seed: &str| {
        let mut r = PyRandom::from_str_seed(seed);
        let a: Vec<Expr> = (0..40).map(|_| gp::random_tree(&mut r, 2, 4)).collect();
        let x: Vec<Expr> = (0..40).map(|i| gp::crossover(&a[i], &a[(i + 7) % 40], &mut r)).collect();
        let m: Vec<Expr> = (0..40).map(|i| gp::mutate(&x[i], &mut r)).collect();
        (a, x, m)
    };
    let (a, x, m) = make("t1");
    assert_eq!((a.clone(), x.clone(), m.clone()), make("t1"));
    assert_ne!(a, make("t2").0);
    for e in a.iter().chain(&x).chain(&m) {
        assert!(e.depth() <= MAX_DEPTH, "depth {} > {MAX_DEPTH}: {}", e.depth(), e.to_rust());
    }
    assert!(a.iter().all(|e| (2..=4).contains(&e.depth())));
    assert!(x.iter().zip(&a).any(|(c, p)| c != p), "crossover changes something");
    assert!(m.iter().zip(&x).any(|(c, p)| c != p), "mutation changes something");
}

// 3. Ants.
fn space() -> Space {
    Space::new(vec!["G".into(), "H".into(), "K".into()], vec![0.6, 0.9, 0.4], 4)
}

#[test]
fn ants_build_within_the_limits_and_by_seed() {
    let s = space();
    let ants = Ants::new(&s);
    let build = |seed: &str| {
        let mut r = PyRandom::from_str_seed(seed);
        (0..200).map(|_| ants.build(&s, &mut r)).collect::<Vec<Floor>>()
    };
    let floors = build("a1");
    assert_eq!(floors, build("a1"));
    assert_ne!(floors, build("a2"));
    for f in &floors {
        assert_eq!(f.tools.len(), 3);
        assert!(f.tools.iter().all(|&t| t <= 3));
        assert!(f.tools.iter().sum::<usize>() <= 4, "{f:?}");
        assert!(f.cap < s.caps.len());
    }
    assert!(floors.iter().any(|f| f.wing) && floors.iter().any(|f| !f.wing));
    assert!(floors.iter().any(|f| f.tools.iter().sum::<usize>() > 0));
}

#[test]
fn pheromone_follows_the_stated_rule() {
    let s = space();
    let mut ants = Ants::new(&s);
    let best = Floor { tools: vec![1, 0, 2], wing: true, cap: 2 };
    let second = Floor { tools: vec![1, 3, 0], wing: false, cap: 0 };
    ants.update(&[best.clone(), second.clone()]);
    let after = |deposit: f64| ((1.0 - RHO) * 1.0 + deposit).clamp(TAU_MIN, TAU_MAX);
    assert_eq!(ants.tau_tools[0][1], after(DEPOSITS[0] + DEPOSITS[1]));
    assert_eq!(ants.tau_tools[0][0], after(0.0));
    assert_eq!(ants.tau_tools[1][3], after(DEPOSITS[1]));
    assert_eq!(ants.tau_tools[2][2], after(DEPOSITS[0]));
    assert_eq!(ants.tau_place, [after(DEPOSITS[1]), after(DEPOSITS[0])]);
    assert_eq!(ants.tau_cap[2], after(DEPOSITS[0]));
    assert_eq!(ants.tau_cap[0], after(DEPOSITS[1]));
    assert_eq!(DEPOSITS, [0.4, 0.3, 0.2, 0.1]);
    for _ in 0..200 {
        ants.update(&[best.clone()]);
    }
    // one depositor settles where evaporation equals its deposit: 0.4 / 0.2 = 2; unchosen pheromone falls to the floor
    assert!((ants.tau_tools[0][1] - DEPOSITS[0] / RHO).abs() < 1e-9, "{}", ants.tau_tools[0][1]);
    assert!(ants.tau_tools[0][1] <= TAU_MAX);
    assert_eq!(ants.tau_tools[0][0], TAU_MIN);
}

// 4. Genome to shop.
#[test]
fn a_floor_becomes_its_shop() {
    let shop = toy();
    let s = space();
    let none = Floor { tools: vec![0, 0, 0], wing: false, cap: 0 };
    let plain = floor_shop(&shop, &s, &none, 100.0, "B").unwrap();
    assert_eq!(plain, shop);
    let f = Floor { tools: vec![2, 0, 1], wing: true, cap: 3 };
    let got = floor_shop(&shop, &s, &f, 100.0, "B").unwrap();
    assert_eq!(got.group("G@B").unwrap().count, 2);
    assert!(got.group("H@B").is_none());
    assert_eq!(got.group("K@B").unwrap().count, 1);
    assert_eq!(got.famcaps, vec![("B".to_string(), (s.caps[3].unwrap() * 100.0).ceil() as i64)]);
}

// 5. The loop.
#[test]
fn the_search_is_seeded_and_keeps_its_best() {
    let shop = toy();
    let s = space();
    let w = Window { from: 1440.0, to: 4.0 * 1440.0 };
    let grid = PriceGrid::preregistered("B");
    let eval = |f: &Floor, e: &Expr, seed: u64| -> f64 {
        let sh = floor_shop(&shop, &s, f, 40.0, "B").unwrap();
        let fam = gp::family_numbers(&sh);
        let mut pick = |d: &Decision| gp::choose(e, d, &fam);
        let r = run(&sh, &RunOptions { seed, until: Some(w.to), record: false }, Some(&mut pick));
        let tools: usize = f.tools.iter().sum();
        money(&sh, &r, &w, &grid[0], tools, 0.0).per_day
    };
    let set = |threads| Settings { population: 6, generations: 4, seeds: vec![3000, 3001], seed: 9, threads, ..Settings::default() };
    let h1 = search(&eval, &s, &set(1));
    let h3 = search(&eval, &s, &set(3));
    assert_eq!(h1, h3);
    assert_eq!(h1.generations.len(), 4);
    assert!(h1.generations.iter().all(|g| g.len() == 6));
    let best: Vec<f64> = h1.generations.iter().map(|g| g.iter().map(|i| i.fitness).fold(f64::NEG_INFINITY, f64::max)).collect();
    for w in best.windows(2) {
        assert!(w[1] >= w[0], "best fell: {best:?}");
    }
    // the kept individual opens each later generation unchanged
    for k in 1..h1.generations.len() {
        let prev = &h1.generations[k - 1];
        // ties go to the earlier individual, as the search ranks them
        let m = prev.iter().map(|i| i.fitness).fold(f64::NEG_INFINITY, f64::max);
        let top = prev.iter().find(|i| i.fitness == m).unwrap();
        assert_eq!(&h1.generations[k][0], top);
    }
    let d = Settings::default();
    assert_eq!((d.population, d.generations, d.seeds.clone(), d.tournament), (16, 12, vec![3000, 3001, 3002], 3));
    assert_eq!((d.p_cross, d.p_mutate), (0.7, 0.2));
}
