//! A grid of dials run on the same seeds (paired), over up to a few threads.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use crate::dials::Dials;
use crate::engine::{run, RunOptions};
use crate::shop::Shop;
use crate::uq::{paired, Interval};
use crate::window::{score, with_probes, Window, WindowScore};

#[derive(Clone, Debug)]
pub struct Config {
    pub label: String,
    pub dials: Dials,
}

#[derive(Clone, Debug)]
pub struct Row {
    /// index into the configs
    pub config: usize,
    pub seed: u64,
    pub score: WindowScore,
}

/// Run every config on every seed until `until` minutes, scored over the window. Rows come back
/// ordered by config, then seed, whatever the thread count.
pub fn run_grid(shop: &Shop, configs: &[Config], seeds: &[u64], until: f64, w: &Window, threads: usize) -> Result<Vec<Row>, String> {
    w.check()?;
    if w.to > until {
        return Err(format!("the window ends at {} after the run's end {until}", w.to));
    }
    let shops: Vec<Shop> = configs.iter().map(|c| c.dials.apply(shop).map(|s| with_probes(&s, w))).collect::<Result<_, _>>()?;
    let jobs: Vec<(usize, u64)> = (0..configs.len()).flat_map(|c| seeds.iter().map(move |&s| (c, s))).collect();
    let out: Mutex<Vec<Option<Result<WindowScore, String>>>> = Mutex::new(vec![None; jobs.len()]);
    let next = AtomicUsize::new(0);
    std::thread::scope(|sc| {
        for _ in 0..threads.max(1).min(jobs.len().max(1)) {
            sc.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= jobs.len() {
                    break;
                }
                let (c, seed) = jobs[i];
                let r = run(&shops[c], &RunOptions { seed, until: Some(until), record: false }, None);
                let s = score(&r, w);
                out.lock().unwrap()[i] = Some(s);
            });
        }
    });
    let out = out.into_inner().unwrap();
    jobs.iter()
        .zip(out)
        .map(|(&(config, seed), s)| Ok(Row { config, seed, score: s.expect("every job ran")? }))
        .collect()
}

/// The paired interval of `other - base` on one score, over the seeds both share, in seed order.
pub fn paired_vs(rows: &[Row], base: usize, other: usize, f: impl Fn(&WindowScore) -> f64, alpha: f64) -> Interval {
    let pick = |c: usize| {
        let mut v: Vec<(u64, f64)> = rows.iter().filter(|r| r.config == c).map(|r| (r.seed, f(&r.score))).collect();
        v.sort_by_key(|x| x.0);
        v
    };
    let (b, o) = (pick(base), pick(other));
    let seeds: Vec<u64> = b.iter().map(|x| x.0).filter(|s| o.iter().any(|y| y.0 == *s)).collect();
    let get = |v: &[(u64, f64)]| -> Vec<f64> { seeds.iter().map(|s| v.iter().find(|x| x.0 == *s).unwrap().1).collect() };
    paired(&get(&b), &get(&o), alpha)
}
