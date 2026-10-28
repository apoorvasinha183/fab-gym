//! Dispatch rules as expression trees for genetic programming (docs/EVOLVE.md). A tree computes a key from a
//! candidate's 14 numbers; the smallest key starts, ties keep today's pick, and a key that is not a number counts as
//! the largest: the rule sandbox's own convention, so a tree printed with `to_rust` runs the same there.

use std::collections::HashMap;

use crate::engine::Decision;
use crate::pyrandom::PyRandom;
use crate::shop::Shop;

/// The candidate's numbers, in the sandbox's order (`fabrule::CAND_FIELDS`).
pub const RULE_FIELDS: [&str; 14] = [
    "is_batch",
    "lots",
    "priority",
    "size_wafers",
    "step",
    "steps_left",
    "waited_minutes",
    "setup_change",
    "proc_minutes",
    "work_left_minutes",
    "age_minutes",
    "cqt_slack_minutes",
    "is_default",
    "family",
];

pub const MAX_DEPTH: usize = 5;

const IS_DEFAULT: usize = 12;
const WAITED: usize = 6;
/// Constants a random tree may use.
const CONSTS: [f64; 9] = [-1.0, 0.5, 1.0, 2.0, 5.0, 10.0, 60.0, 1440.0, 1e6];

#[derive(Clone, Debug, PartialEq)]
pub enum Expr {
    Field(usize),
    Const(f64),
    Add(Box<Expr>, Box<Expr>),
    Sub(Box<Expr>, Box<Expr>),
    Mul(Box<Expr>, Box<Expr>),
    /// protected: 1 when the divisor is within 1e-9 of 0
    Div(Box<Expr>, Box<Expr>),
    Min(Box<Expr>, Box<Expr>),
    Max(Box<Expr>, Box<Expr>),
    /// if a > b then c else d
    If(Box<Expr>, Box<Expr>, Box<Expr>, Box<Expr>),
}

impl Expr {
    /// Today's rule: today's pick gets 0, every other candidate 1.
    pub fn today() -> Expr {
        Expr::Sub(Box::new(Expr::Const(1.0)), Box::new(Expr::Field(IS_DEFAULT)))
    }

    /// First in, first out: the longest wait first.
    pub fn fifo() -> Expr {
        Expr::Sub(Box::new(Expr::Const(0.0)), Box::new(Expr::Field(WAITED)))
    }

    pub fn eval(&self, f: &[f64; 14]) -> f64 {
        use Expr::*;
        match self {
            Field(i) => f[*i],
            Const(x) => *x,
            Add(a, b) => a.eval(f) + b.eval(f),
            Sub(a, b) => a.eval(f) - b.eval(f),
            Mul(a, b) => a.eval(f) * b.eval(f),
            Div(a, b) => {
                let d = b.eval(f);
                if d.abs() < 1e-9 {
                    1.0
                } else {
                    a.eval(f) / d
                }
            }
            Min(a, b) => a.eval(f).min(b.eval(f)),
            Max(a, b) => a.eval(f).max(b.eval(f)),
            If(a, b, c, d) => {
                if a.eval(f) > b.eval(f) {
                    c.eval(f)
                } else {
                    d.eval(f)
                }
            }
        }
    }

    /// A leaf has depth 1.
    pub fn depth(&self) -> usize {
        self.kids().iter().map(|k| k.depth()).max().unwrap_or(0) + 1
    }

    fn kids(&self) -> Vec<&Expr> {
        use Expr::*;
        match self {
            Field(_) | Const(_) => vec![],
            Add(a, b) | Sub(a, b) | Mul(a, b) | Div(a, b) | Min(a, b) | Max(a, b) => vec![a, b],
            If(a, b, c, d) => vec![a, b, c, d],
        }
    }

    fn kids_mut(&mut self) -> Vec<&mut Expr> {
        use Expr::*;
        match self {
            Field(_) | Const(_) => vec![],
            Add(a, b) | Sub(a, b) | Mul(a, b) | Div(a, b) | Min(a, b) | Max(a, b) => vec![a, b],
            If(a, b, c, d) => vec![a, b, c, d],
        }
    }

    fn size(&self) -> usize {
        1 + self.kids().iter().map(|k| k.size()).sum::<usize>()
    }

    /// The n-th node in preorder.
    fn node(&self, n: usize) -> &Expr {
        fn go<'a>(e: &'a Expr, n: &mut usize) -> Option<&'a Expr> {
            if *n == 0 {
                return Some(e);
            }
            *n -= 1;
            for k in e.kids() {
                if let Some(x) = go(k, n) {
                    return Some(x);
                }
            }
            None
        }
        let mut k = n;
        go(self, &mut k).expect("node in range")
    }

    fn replace(&self, n: usize, with: &Expr) -> Expr {
        fn go(e: &mut Expr, n: &mut usize, with: &Expr) -> bool {
            if *n == 0 {
                *e = with.clone();
                return true;
            }
            *n -= 1;
            for k in e.kids_mut() {
                if go(k, n, with) {
                    return true;
                }
            }
            false
        }
        let mut out = self.clone();
        let mut k = n;
        go(&mut out, &mut k, with);
        out
    }

    fn rust(&self) -> String {
        use Expr::*;
        match self {
            Field(i) => format!("c.{}", RULE_FIELDS[*i]),
            Const(x) if *x < 0.0 => format!("({x:?})"),
            Const(x) => format!("{x:?}"),
            Add(a, b) => format!("({} + {})", a.rust(), b.rust()),
            Sub(a, b) => format!("({} - {})", a.rust(), b.rust()),
            Mul(a, b) => format!("({} * {})", a.rust(), b.rust()),
            Div(a, b) => format!("({{ let d: f64 = {}; if d.abs() < 1e-9 {{ 1.0 }} else {{ {} / d }} }})", b.rust(), a.rust()),
            Min(a, b) => format!("({}).min({})", a.rust(), b.rust()),
            Max(a, b) => format!("({}).max({})", a.rust(), b.rust()),
            If(a, b, c, d) => format!("(if {} > {} {{ {} }} else {{ {} }})", a.rust(), b.rust(), c.rust(), d.rust()),
        }
    }

    /// The tree as a sandbox rule.
    pub fn to_rust(&self) -> String {
        format!("pub fn key(c: &Cand, _x: &Ctx) -> f64 {{\n    {}\n}}", self.rust())
    }
}

/// Families numbered from 1 in the order the shop's `family` records first name them; "" is 0.
pub fn family_numbers(shop: &Shop) -> HashMap<String, f64> {
    let mut m = HashMap::new();
    for (_, f) in &shop.families {
        if !f.is_empty() && !m.contains_key(f) {
            let n = m.len() as f64 + 1.0;
            m.insert(f.clone(), n);
        }
    }
    m
}

/// A candidate's 14 numbers, exactly as the sandbox lays them out.
pub fn fields(d: &Decision, i: usize, fam: &HashMap<String, f64>) -> [f64; 14] {
    let c = &d.candidates[i];
    [
        if c.kind == "batch" { 1.0 } else { 0.0 },
        c.lots.len() as f64,
        c.priority,
        c.size_wafers as f64,
        c.step as f64,
        c.steps_left as f64,
        c.waited_minutes,
        if c.setup_change { 1.0 } else { 0.0 },
        c.proc_minutes,
        c.work_left_minutes,
        d.t - c.release,
        c.cqt_slack_minutes.unwrap_or(1e9),
        if i == d.default { 1.0 } else { 0.0 },
        fam.get(&c.family).copied().unwrap_or(0.0),
    ]
}

/// The candidate the tree picks, by the sandbox's convention.
pub fn choose(e: &Expr, d: &Decision, fam: &HashMap<String, f64>) -> usize {
    let sane = |k: f64| if k.is_nan() { f64::INFINITY } else { k };
    let mut best = d.default;
    let mut bk = sane(e.eval(&fields(d, best, fam)));
    for i in 0..d.candidates.len() {
        let k = sane(e.eval(&fields(d, i, fam)));
        if k < bk {
            best = i;
            bk = k;
        }
    }
    best
}

fn pick(rng: &mut PyRandom, n: usize) -> usize {
    ((rng.random() * n as f64) as usize).min(n - 1)
}

fn leaf(rng: &mut PyRandom) -> Expr {
    if rng.random() < 0.7 {
        Expr::Field(pick(rng, RULE_FIELDS.len()))
    } else {
        Expr::Const(CONSTS[pick(rng, CONSTS.len())])
    }
}

fn grow(rng: &mut PyRandom, depth: usize) -> Expr {
    if depth <= 1 {
        return leaf(rng);
    }
    // the first child reaches the full depth, the others any depth below it
    let sub = |rng: &mut PyRandom, first: bool| {
        let d = if first { depth - 1 } else { 1 + pick(rng, depth - 1) };
        Box::new(grow(rng, d))
    };
    match pick(rng, 7) {
        0 => Expr::Add(sub(rng, true), sub(rng, false)),
        1 => Expr::Sub(sub(rng, true), sub(rng, false)),
        2 => Expr::Mul(sub(rng, true), sub(rng, false)),
        3 => Expr::Div(sub(rng, true), sub(rng, false)),
        4 => Expr::Min(sub(rng, true), sub(rng, false)),
        5 => Expr::Max(sub(rng, true), sub(rng, false)),
        _ => Expr::If(sub(rng, true), sub(rng, false), sub(rng, false), sub(rng, false)),
    }
}

/// A random tree whose depth is drawn evenly from `lo` to `hi`.
pub fn random_tree(rng: &mut PyRandom, lo: usize, hi: usize) -> Expr {
    let d = lo + pick(rng, hi - lo + 1);
    grow(rng, d)
}

/// Subtree crossover: a random node of `a` replaced by a random node of `b`, retried up to 10 times while the
/// result would be deeper than the limit (then `a` unchanged).
pub fn crossover(a: &Expr, b: &Expr, rng: &mut PyRandom) -> Expr {
    for _ in 0..10 {
        let at = pick(rng, a.size());
        let from = b.node(pick(rng, b.size())).clone();
        let out = a.replace(at, &from);
        if out.depth() <= MAX_DEPTH {
            return out;
        }
    }
    a.clone()
}

/// Subtree mutation: a random node replaced by a random tree of depth 1 to 3, within the limit (10 tries).
pub fn mutate(a: &Expr, rng: &mut PyRandom) -> Expr {
    for _ in 0..10 {
        let at = pick(rng, a.size());
        let new = random_tree(rng, 1, 3);
        let out = a.replace(at, &new);
        if out.depth() <= MAX_DEPTH {
            return out;
        }
    }
    a.clone()
}
