//! Two wafer families in one fab (docs/TWO-FAMILIES.md), from the SMT2020 testbed with a layout of
//! our own design; not a real fab.
//!
//! Family B is SMT2020's engineering lots, rebuilt from their published facts on product 3's
//! route. Copies of tool groups serve family B only; three layout strategies place them.

use std::collections::{BTreeSet, HashMap};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use crate::engine::{run, Decision, RunOptions};
use crate::layout::{Config, Problem};
use crate::money::{money, Money, MoneyScore};
use crate::window::Window;
use crate::pyrandom::PyRandom;
use crate::shop::{LotSpec, Per, Release, Shop};

/// Family B's lots, from the published facts: `per_release` lots a release (times `scale`), the
/// first release at `first` minutes, gaps cycling through `gaps` (minutes), sizes uniform in
/// `sizes`, and one lot in `hot_every` at `hot_priority` (the rest at `priority`).
#[derive(Clone, Debug, PartialEq)]
pub struct EngLots {
    pub route: String,
    /// releases start before this many minutes
    pub horizon: f64,
    pub seed: u64,
    pub scale: f64,
    pub per_release: usize,
    pub first: f64,
    pub gaps: Vec<f64>,
    pub sizes: (i64, i64),
    pub hot_every: usize,
    pub priority: f64,
    pub hot_priority: f64,
}

impl EngLots {
    /// SMT2020's engineering lots: 20 lots a release, from 08:00 on day 0, gaps of 2 and 5 days in
    /// turn, 1 to 10 wafers, one in five at priority 20 and the rest at 10.
    pub fn published(route: &str, horizon: f64, seed: u64) -> EngLots {
        EngLots {
            route: route.to_string(),
            horizon,
            seed,
            scale: 1.0,
            per_release: 20,
            first: 480.0,
            gaps: vec![2.0 * 1440.0, 5.0 * 1440.0],
            sizes: (1, 10),
            hot_every: 5,
            priority: 10.0,
            hot_priority: 20.0,
        }
    }
}

/// Family B's lots for the horizon, the same for the same config.
pub fn engineering_lots(e: &EngLots) -> Vec<LotSpec> {
    let mut rng = PyRandom::from_str_seed(&format!("fabgym-englots-{}", e.seed));
    let n = (e.per_release as f64 * e.scale).round().max(0.0) as usize;
    let hot = if e.hot_every == 0 { 0 } else { (n as f64 / e.hot_every as f64).round() as usize };
    let span = (e.sizes.1 - e.sizes.0 + 1) as f64;
    let mut out = vec![];
    let (mut t, mut k) = (e.first, 0usize);
    while t < e.horizon {
        // which lots of this release are hot: the first `hot` of a shuffled order
        let mut order: Vec<usize> = (0..n).collect();
        for i in 0..order.len().saturating_sub(1) {
            let j = i + (rng.random() * (order.len() - i) as f64) as usize;
            let last = order.len() - 1;
            order.swap(i, j.min(last));
        }
        let is_hot: BTreeSet<usize> = order.into_iter().take(hot).collect();
        for i in 0..n {
            let size = e.sizes.0 + ((rng.random() * span) as i64).min(span as i64 - 1);
            out.push(LotSpec {
                id: format!("{}.{}.{}", e.route, k + 1, i + 1),
                route: e.route.clone(),
                size,
                priority: if is_hot.contains(&i) { e.hot_priority } else { e.priority },
                start: t,
                step: 0,
            });
        }
        if e.gaps.is_empty() {
            break;
        }
        t += e.gaps[k % e.gaps.len()];
        k += 1;
    }
    out
}

/// The base shop with family B added: `e.route` copies `from`'s steps, every base route is family
/// A, `e.route` is family B, and family B's lots are listed.
pub fn two_family_shop(base: &Shop, from: &str, e: &EngLots) -> Result<Shop, String> {
    let src = base.route(from).ok_or_else(|| format!("no route {from:?}"))?;
    if base.route(&e.route).is_some() {
        return Err(format!("route {:?} already exists", e.route));
    }
    let mut s = base.clone();
    let mut r = src.clone();
    r.name = e.route.clone();
    s.routes.push(r);
    s.families = base.routes.iter().map(|r| (r.name.clone(), "A".to_string())).collect();
    s.families.push((e.route.clone(), "B".to_string()));
    s.lots.extend(engineering_lots(e));
    Ok(s)
}

/// Each named group gets a copy `G@family` with its own tool count and the same times, setups,
/// maintenance and breakdowns; the family's routes use the copy in place of the group.
pub fn copy_groups(shop: &Shop, groups: &[(String, usize)], family: &str) -> Result<Shop, String> {
    let mut s = shop.clone();
    for (g, n) in groups {
        let orig = shop.group(g).ok_or_else(|| format!("no tool group {g:?}"))?;
        let name = format!("{g}@{family}");
        if shop.group(&name).is_some() {
            return Err(format!("group {name:?} already exists"));
        }
        let mut c = orig.clone();
        c.name = name.clone();
        c.count = *n;
        s.groups.push(c);
        for r in s.routes.iter_mut() {
            if shop.family_of(&r.name) == family {
                for st in r.steps.iter_mut().filter(|st| st.group == *g) {
                    st.group = name.clone();
                }
            }
        }
    }
    Ok(s)
}

/// Lots a day and mean wafers a lot, per route: release streams at their rate, and listed lots
/// arriving after time 0 at step 0 at their count over the span of their arrivals (that span
/// stretched by one mean gap, so k arrival times cover k gaps).
fn route_rates(shop: &Shop) -> HashMap<String, (f64, f64)> {
    let mut acc: HashMap<String, (f64, f64)> = HashMap::new();
    for rel in shop.releases.iter().filter(|r| r.every > 0.0) {
        let e = acc.entry(rel.route.clone()).or_insert((0.0, 0.0));
        let rate = 1440.0 / rel.every;
        e.0 += rate;
        e.1 += rate * rel.size as f64;
    }
    let mut listed: HashMap<&str, Vec<&LotSpec>> = HashMap::new();
    for l in shop.lots.iter().filter(|l| l.step == 0 && l.start >= 0.0) {
        listed.entry(l.route.as_str()).or_default().push(l);
    }
    for (route, lots) in listed {
        let mut starts: Vec<f64> = lots.iter().map(|l| l.start).collect();
        starts.sort_by(f64::total_cmp);
        starts.dedup();
        let k = starts.len() as f64;
        let days = if k >= 2.0 { (starts[starts.len() - 1] - starts[0]) * k / (k - 1.0) / 1440.0 } else { 1.0 };
        let rate = lots.len() as f64 / days;
        let mean = lots.iter().map(|l| l.size as f64).sum::<f64>() / lots.len() as f64;
        let e = acc.entry(route.to_string()).or_insert((0.0, 0.0));
        e.0 += rate;
        e.1 += rate * mean;
    }
    acc.into_iter()
        .map(|(r, (lots, wafers))| (r, (lots, if lots > 0.0 { wafers / lots } else { 0.0 })))
        .collect()
}

/// Busy share each group would carry at the routes' rates, by the engine's own job times at their middle (an
/// estimate for ranking): per piece the first piece plus the cascade interval for each further one (or every piece
/// in full), per lot one time, per batch the lot's share of a batch of mean size in wafers; load and unload minutes on
/// every job; sampled steps by their share; setups left out.
pub fn loads(shop: &Shop, only_family: Option<&str>) -> HashMap<String, f64> {
    let rates = route_rates(shop);
    let mut load: HashMap<String, f64> = HashMap::new();
    for r in &shop.routes {
        if only_family.is_some_and(|f| shop.family_of(&r.name) != f) {
            continue;
        }
        let Some(&(lots, wafers)) = rates.get(&r.name) else { continue };
        for st in &r.steps {
            let grp = shop.group(&st.group);
            let extra = grp.map(|g| g.load + g.unload).unwrap_or(0.0);
            let per_lot = match st.per {
                Per::Piece => match st.interval {
                    Some(iv) if iv != 0.0 => st.time + (wafers - 1.0).max(0.0) * iv + extra,
                    _ => st.time * wafers + extra,
                },
                Per::Lot => st.time + extra,
                Per::Batch => (st.time + extra) * wafers / st.batch.map(|b| (b.0 + b.1) / 2.0).unwrap_or(wafers).max(1.0),
            };
            let n = grp.map(|g| g.count).unwrap_or(0).max(1) as f64;
            *load.entry(st.group.clone()).or_insert(0.0) += lots * per_lot * st.sample.unwrap_or(1.0) / (n * 1440.0);
        }
    }
    load
}

/// The `n` groups the family visits that carry the most load from both families, most first
/// (ties by name).
pub fn contested(shop: &Shop, family: &str, n: usize) -> Vec<String> {
    let all = loads(shop, None);
    let mine = loads(shop, Some(family));
    let mut v: Vec<(&String, f64)> = mine.keys().map(|g| (g, all[g])).collect();
    v.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(b.0)));
    v.into_iter().take(n).map(|(g, _)| g.clone()).collect()
}

/// A layout strategy for family B (docs/TWO-FAMILIES.md).
#[derive(Clone, Debug, PartialEq)]
pub enum Strategy {
    /// D1: no copies.
    Share,
    /// D2: copies of the `groups` most contested groups, `tools` each, in a third phase on pad P3.
    Wing { groups: usize, tools: usize },
    /// D3: the same copies, placed in the two halls by family B's flow.
    Copies { groups: usize, tools: usize },
}

/// What a strategy adds: tools, and metres of wall their tools take along the bays (by tool kind)
/// plus, for the wing, one more OHT bridge.
#[derive(Clone, Debug, PartialEq)]
pub struct LayoutInfo {
    pub tools_added: usize,
    pub metres_added: f64,
    pub copies: Vec<String>,
}

/// The shop as the layout reads it: listed lots become a release stream at their rate and mean
/// size, so their flows place the groups.
pub fn layout_shop(shop: &Shop) -> Shop {
    let mut s = shop.clone();
    let listed: BTreeSet<String> =
        shop.lots.iter().filter(|l| l.step == 0 && l.start >= 0.0).map(|l| l.route.clone()).collect();
    let rates = route_rates(&Shop { releases: vec![], ..shop.clone() });
    for r in listed {
        let (lots, wafers) = rates[&r];
        if lots > 0.0 {
            s.releases.push(Release {
                route: r.clone(),
                size: wafers.round().max(1.0) as i64,
                priority: 10.0,
                every: 1440.0 / lots,
                first: 0.0,
                count: None,
                prefix: format!("layout-{r}"),
            });
        }
    }
    s.lots.clear();
    s
}

/// Lay a strategy out on the 2D campus (the optimiser's plan, packed), returning the shop with
/// its copies and transport by distance.
pub fn lay_out(
    shop: &Shop,
    areas: &[(String, String)],
    cfg: &Config,
    strategy: &Strategy,
    family: &str,
) -> Result<(Shop, LayoutInfo), String> {
    let (picks, wing): (Vec<(String, usize)>, bool) = match strategy {
        Strategy::Share => (vec![], false),
        Strategy::Wing { groups, tools } => (contested(shop, family, *groups).into_iter().map(|g| (g, *tools)).collect(), true),
        Strategy::Copies { groups, tools } => {
            (contested(shop, family, *groups).into_iter().map(|g| (g, *tools)).collect(), false)
        }
    };
    lay_out_copies(shop, areas, cfg, &picks, wing, family)
}

/// Lay out the shop with the named copies (group, tools), in a wing on a further phase or in the halls.
pub fn lay_out_copies(
    shop: &Shop,
    areas: &[(String, String)],
    cfg: &Config,
    picks: &[(String, usize)],
    wing: bool,
    family: &str,
) -> Result<(Shop, LayoutInfo), String> {
    let picks: Vec<(String, usize)> = picks.iter().filter(|p| p.1 > 0).cloned().collect();
    let mut s = copy_groups(shop, &picks, family)?;
    let mut areas = areas.to_vec();
    let mut metres = 0.0;
    let mut copies = vec![];
    for (g, n) in &picks {
        let a = areas.iter().find(|x| x.0 == *g).map(|x| x.1.clone()).ok_or_else(|| format!("no area for {g:?}"))?;
        let name = format!("{g}@{family}");
        let w = cfg.kind_of(&name).map(|k| k.w).unwrap_or(cfg.default_footprint.0);
        metres += w * *n as f64;
        areas.push((name.clone(), a));
        copies.push(name);
    }
    let mut c = cfg.clone();
    if wing && !picks.is_empty() {
        let tag = format!("@{family}");
        let wing_phase = c.phase_rules.iter().map(|r| r.1).chain([c.default_phase]).max().unwrap_or(0) + 1;
        c.phase_rules.insert(0, (tag.clone(), wing_phase));
        c.pin.push(tag);
        metres += cfg.bridge;
    }
    let p = Problem::new(&layout_shop(&s), &areas, &c)?;
    let campus = p.pack(&p.optimise());
    s.oht = Some(p.oht(&campus));
    let tools_added = picks.iter().map(|p| p.1).sum();
    Ok((s, LayoutInfo { tools_added, metres_added: metres, copies }))
}

impl EngLots {
    /// Lots a day on average: the lots of a release over the mean gap.
    pub fn lots_per_day(&self) -> f64 {
        let n = (self.per_release as f64 * self.scale).round().max(0.0);
        if self.gaps.is_empty() {
            return 0.0;
        }
        let gap_days = self.gaps.iter().sum::<f64>() / self.gaps.len() as f64 / 1440.0;
        n / gap_days
    }
}

/// P2's cap (docs/TWO-FAMILIES-SWEEP.md): ⌈1.5 × lots a day × raw processing days⌉.
pub fn b_cap(e: &EngLots, raw_days: f64) -> i64 {
    (1.5 * e.lots_per_day() * raw_days).ceil() as i64
}

/// The operating policies of the sweep (docs/TWO-FAMILIES-SWEEP.md).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Policy {
    Today,
    BFirst,
    Cap,
    Reserve,
    Qualify,
}

impl Policy {
    pub const ALL: [Policy; 5] = [Policy::Today, Policy::BFirst, Policy::Cap, Policy::Reserve, Policy::Qualify];

    /// The word a scenario uses (docs/ASK-FAMILIES.md).
    pub fn key(self) -> &'static str {
        match self {
            Policy::Today => "today",
            Policy::BFirst => "bfirst",
            Policy::Cap => "cap",
            Policy::Reserve => "reserve",
            Policy::Qualify => "qualify",
        }
    }

    pub fn from_key(k: &str) -> Option<Policy> {
        Policy::ALL.into_iter().find(|p| p.key() == k)
    }

    pub fn label(self) -> &'static str {
        match self {
            Policy::Today => "P0 today",
            Policy::BFirst => "P1 family B first",
            Policy::Cap => "P2 family cap",
            Policy::Reserve => "P3 reservation",
            Policy::Qualify => "P4 qualification",
        }
    }
}

/// The `n` groups the family still shares with others, most contested first (its copies left out).
pub fn policy_groups(shop: &Shop, family: &str, n: usize) -> Vec<String> {
    let tag = format!("@{family}");
    contested(shop, family, usize::MAX).into_iter().filter(|g| !g.ends_with(&tag)).take(n).collect()
}

/// The shop under a policy: P2 caps the family, P3 reserves each group's first tool for it, P4 qualifies it on the
/// first half of each group's tools (rounded up). P0 and P1 change no record (P1 is a choice, `b_first`).
pub fn apply_policy(shop: &Shop, p: Policy, family: &str, groups: &[String], cap: i64) -> Shop {
    let mut s = shop.clone();
    let count = |g: &str| shop.group(g).map(|x| x.count).unwrap_or(0);
    match p {
        Policy::Today | Policy::BFirst => {}
        Policy::Cap => s.famcaps.push((family.to_string(), cap)),
        Policy::Reserve => {
            for g in groups {
                s.quals.push((g.clone(), family.to_string(), count(g)));
                s.reserves.push((g.clone(), family.to_string(), 1));
            }
        }
        Policy::Qualify => {
            for g in groups {
                s.quals.push((g.clone(), family.to_string(), count(g).div_ceil(2)));
            }
        }
    }
    s
}

/// P1: today's pick when it is of the family, else the family's first candidate, else today's pick.
pub fn b_first(d: &Decision, family: &str) -> usize {
    if d.candidates.get(d.default).is_some_and(|c| c.family == family) {
        return d.default;
    }
    d.candidates.iter().position(|c| c.family == family).unwrap_or(d.default)
}

/// One cell of the sweep: a laid-out shop under a policy.
#[derive(Clone, Debug)]
pub struct Cell {
    pub label: String,
    pub shop: Shop,
    pub policy: Policy,
    pub tools_added: usize,
    pub metres_added: f64,
}

/// One run of a cell.
#[derive(Clone, Debug, PartialEq)]
pub struct CellRun {
    pub cell: usize,
    pub seed: u64,
    /// wafers out a day of every family but `family`, in the window
    pub a_wafers_per_day: f64,
    /// money at each point of the price grid, in its order
    pub money: Vec<MoneyScore>,
}

/// Every cell on every seed, at most `threads` at once; the rows in (cell, seed) order whatever the thread count.
pub fn run_cells(
    cells: &[Cell],
    seeds: &[u64],
    until: f64,
    w: &Window,
    grid: &[Money],
    family: &str,
    threads: usize,
) -> Result<Vec<CellRun>, String> {
    w.check()?;
    let jobs: Vec<(usize, u64)> = (0..cells.len()).flat_map(|c| seeds.iter().map(move |&s| (c, s))).collect();
    let next = AtomicUsize::new(0);
    let out: Mutex<Vec<Option<CellRun>>> = Mutex::new(vec![None; jobs.len()]);
    std::thread::scope(|sc| {
        for _ in 0..threads.max(1).min(jobs.len().max(1)) {
            sc.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::SeqCst);
                let Some(&(c, seed)) = jobs.get(i) else { break };
                let cell = &cells[c];
                let opts = RunOptions { seed, until: Some(until), record: false };
                let r = if cell.policy == Policy::BFirst {
                    let mut pick = |d: &Decision| b_first(d, family);
                    run(&cell.shop, &opts, Some(&mut pick))
                } else {
                    run(&cell.shop, &opts, None)
                };
                let days = (w.to - w.from) / 1440.0;
                let a: f64 = r
                    .lots
                    .iter()
                    .filter(|l| cell.shop.family_of(&l.route) != family)
                    .filter(|l| l.done.is_some_and(|d| d > w.from && d <= w.to))
                    .map(|l| l.size as f64)
                    .sum();
                let money = grid.iter().map(|m| money(&cell.shop, &r, w, m, cell.tools_added, cell.metres_added)).collect();
                out.lock().unwrap()[i] = Some(CellRun { cell: c, seed, a_wafers_per_day: a / days, money });
            });
        }
    });
    Ok(out.into_inner().unwrap().into_iter().map(|x| x.expect("every job ran")).collect())
}
