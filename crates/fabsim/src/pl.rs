//! Money with full business logic: a profit and loss in dollars (docs/MONEY-PL.md). Every price is an assumption of
//! ours, with a low and a high value; none is a quote or a real fab's figure. On the SMT2020 model.

use std::collections::HashMap;
use std::path::Path;

use crate::engine::RunResult;
use crate::money::{money, Money, PriceGrid};
use crate::shop::Shop;
use crate::twofam::{contested, two_family_shop, EngLots};
use crate::uq::{paired, verdict, Interval, Verdict};
use crate::window::Window;

/// A prototype's price holds for this many days from its scheduled arrival (the sweep's grid has only 30).
pub const FREE_DAYS: f64 = 30.0;

/// One assumed price, with its range.
#[derive(Clone, Debug, PartialEq)]
pub struct Item {
    pub key: &'static str,
    pub label: &'static str,
    pub unit: &'static str,
    pub central: f64,
    pub low: f64,
    pub high: f64,
    pub assumed: bool,
}

const fn it(
    key: &'static str,
    label: &'static str,
    unit: &'static str,
    central: f64,
    low: f64,
    high: f64,
) -> Item {
    Item {
        key,
        label,
        unit,
        central,
        low,
        high,
        assumed: true,
    }
}

/// The price sheet of docs/MONEY-PL.md, in its order.
const ITEMS: [Item; 19] = [
    it(
        "a_price",
        "Volume wafer (family A) sale price",
        "$ a wafer",
        8000.0,
        4000.0,
        15000.0,
    ),
    it(
        "b_price",
        "Prototype wafer (family B) price, out within 30 days",
        "$ a wafer",
        60000.0,
        30000.0,
        120000.0,
    ),
    it(
        "b_decay",
        "Prototype price lost per day after 30 days",
        "share of the price a day",
        1.0 / 30.0,
        1.0 / 30.0,
        0.1,
    ),
    it(
        "materials",
        "Materials per wafer out, both families",
        "$ a wafer",
        1800.0,
        900.0,
        3000.0,
    ),
    it(
        "tool_litho",
        "A new lithography tool",
        "$",
        40e6,
        20e6,
        80e6,
    ),
    it(
        "tool_other",
        "A new tool in any other area",
        "$",
        6e6,
        3e6,
        12e6,
    ),
    it(
        "qualify",
        "Qualifying a new tool for production, once",
        "$ a tool",
        0.5e6,
        0.2e6,
        1e6,
    ),
    it(
        "upkeep_rate",
        "Upkeep of an added tool (service, parts, power)",
        "share of its price a year",
        0.10,
        0.06,
        0.15,
    ),
    it(
        "floor_per_tool",
        "Cleanroom floor an added tool needs, with its service space",
        "m²",
        40.0,
        25.0,
        80.0,
    ),
    it(
        "wing_m2",
        "A new wing (building shell and cleanroom fit-out)",
        "$ a m²",
        15000.0,
        8000.0,
        30000.0,
    ),
    it(
        "halls_m2",
        "Fitting out spare space in the existing halls",
        "$ a m²",
        5000.0,
        2500.0,
        10000.0,
    ),
    it(
        "bridge",
        "The overhead track bridge to a wing",
        "$",
        3e6,
        1.5e6,
        6e6,
    ),
    it(
        "base_running",
        "Running today's fab (staff, power, upkeep of its tools, overhead)",
        "$ a day",
        3e6,
        2e6,
        4.5e6,
    ),
    it(
        "base_depreciation",
        "Depreciation of today's fab",
        "$ a day",
        2.5e6,
        1.5e6,
        4e6,
    ),
    it("life_tool", "Life of a tool", "years", 5.0, 5.0, 5.0),
    it(
        "life_building",
        "Life of a building",
        "years",
        20.0,
        20.0,
        20.0,
    ),
    it(
        "life_bridge",
        "Life of the bridge",
        "years",
        10.0,
        10.0,
        10.0,
    ),
    it(
        "horizon_years",
        "Horizon for net present value",
        "years",
        5.0,
        5.0,
        5.0,
    ),
    it(
        "rate",
        "Discount rate for net present value",
        "a year",
        0.10,
        0.08,
        0.12,
    ),
];

/// The prices in force: the sheet at its central values, or with some items moved.
#[derive(Clone, Debug, PartialEq)]
pub struct Sheet {
    values: Vec<(&'static str, f64)>,
}

impl Sheet {
    pub fn items() -> Vec<Item> {
        ITEMS.to_vec()
    }
    pub fn central() -> Sheet {
        Sheet {
            values: ITEMS.iter().map(|i| (i.key, i.central)).collect(),
        }
    }
    pub fn get(&self, key: &str) -> f64 {
        self.values
            .iter()
            .find(|v| v.0 == key)
            .unwrap_or_else(|| panic!("no price {key:?}"))
            .1
    }
    /// A copy with one item set to `value`.
    pub fn with(&self, key: &str, value: f64) -> Sheet {
        let mut s = self.clone();
        let v = s
            .values
            .iter_mut()
            .find(|v| v.0 == key)
            .unwrap_or_else(|| panic!("no price {key:?}"));
        v.1 = value;
        s
    }
}

/// Where a change's added tools stand.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Place {
    /// nothing built (the tools, if any, take no new floor)
    None,
    /// a new wing: a building and the bridge to it
    Wing,
    /// spare space in the existing halls, fitted out
    Halls,
}

/// What a change adds: tools by the area of the group they copy, and where they stand.
#[derive(Clone, Debug, PartialEq)]
pub struct Added {
    pub tools: Vec<(String, usize)>,
    pub place: Place,
}

/// Capital a change spends once, and what it costs a day after.
#[derive(Clone, Debug, PartialEq)]
pub struct Capital {
    pub tools: f64,
    pub qualify: f64,
    pub floor: f64,
    pub bridge: f64,
    pub total: f64,
    pub depreciation_day: f64,
    pub upkeep_day: f64,
}

pub fn tool_price(area: &str, s: &Sheet) -> f64 {
    if area == "Litho" {
        s.get("tool_litho")
    } else {
        s.get("tool_other")
    }
}

pub fn capital(a: &Added, s: &Sheet) -> Capital {
    let n: usize = a.tools.iter().map(|t| t.1).sum();
    let tools: f64 = a
        .tools
        .iter()
        .map(|(area, k)| *k as f64 * tool_price(area, s))
        .sum();
    let qualify = n as f64 * s.get("qualify");
    let area = n as f64 * s.get("floor_per_tool");
    let floor = match a.place {
        Place::None => 0.0,
        Place::Wing => area * s.get("wing_m2"),
        Place::Halls => area * s.get("halls_m2"),
    };
    let bridge = if a.place == Place::Wing && n > 0 {
        s.get("bridge")
    } else {
        0.0
    };
    let depreciation_day = (tools + qualify) / (s.get("life_tool") * 365.0)
        + floor / (s.get("life_building") * 365.0)
        + bridge / (s.get("life_bridge") * 365.0);
    Capital {
        tools,
        qualify,
        floor,
        bridge,
        total: tools + qualify + floor + bridge,
        depreciation_day,
        upkeep_day: tools * s.get("upkeep_rate") / 365.0,
    }
}

/// What a run gives, per day of the window.
#[derive(Clone, Debug, PartialEq)]
pub struct RunIn {
    pub a_wafers_day: f64,
    pub b_wafers_day: f64,
    /// family B's revenue in dollars a day (each lot paid by its cycle time)
    pub b_revenue_day: f64,
}

/// A run's profit and loss, per day.
#[derive(Clone, Debug, PartialEq)]
pub struct Pl {
    pub revenue: f64,
    pub materials: f64,
    pub running: f64,
    /// operating cash: revenue less materials and running costs
    pub cash: f64,
    pub depreciation: f64,
    /// operating profit: cash less depreciation
    pub profit: f64,
}

pub fn run_pl(r: &RunIn, cap: &Capital, s: &Sheet) -> Pl {
    let revenue = r.a_wafers_day * s.get("a_price") + r.b_revenue_day;
    let materials = (r.a_wafers_day + r.b_wafers_day) * s.get("materials");
    let running = s.get("base_running") + cap.upkeep_day;
    let cash = revenue - materials - running;
    let depreciation = s.get("base_depreciation") + cap.depreciation_day;
    Pl {
        revenue,
        materials,
        running,
        cash,
        depreciation,
        profit: cash - depreciation,
    }
}

/// Σ over the horizon's days d of (1 + r)^(−d/365).
pub fn npv_factor(s: &Sheet) -> f64 {
    let days = (s.get("horizon_years") * 365.0).round();
    let r = s.get("rate");
    if r == 0.0 {
        return days;
    }
    let q = (1.0 + r).powf(-1.0 / 365.0);
    q * (1.0 - q.powf(days)) / (1.0 - q)
}

/// A change against today.
#[derive(Clone, Debug, PartialEq)]
pub struct Change {
    pub d_profit_day: f64,
    pub d_cash_day: f64,
    pub capital: f64,
    /// days until the change in cash repays the capital; None: never
    pub payback_days: Option<f64>,
    pub npv: f64,
}

pub fn change(base: &Pl, cand: &Pl, cap: &Capital, s: &Sheet) -> Change {
    let d_cash_day = cand.cash - base.cash;
    Change {
        d_profit_day: cand.profit - base.profit,
        d_cash_day,
        capital: cap.total,
        payback_days: if d_cash_day > 0.0 {
            Some(cap.total / d_cash_day)
        } else {
            None
        },
        npv: -cap.total + d_cash_day * npv_factor(s),
    }
}

fn b_money(s: &Sheet) -> Money {
    Money {
        margin: vec![],
        family_b: "B".into(),
        price0: s.get("b_price"),
        free_days: FREE_DAYS,
        decay: s.get("b_decay"),
        tool_day: 0.0,
        metre_day: 0.0,
    }
}

/// Family B's revenue in dollars a day, from the run's own lots.
pub fn b_revenue_day(shop: &Shop, r: &RunResult, w: &Window, s: &Sheet) -> f64 {
    money(shop, r, w, &b_money(s), 0, 0.0).b_per_day
}

/// Family B's revenue in dollars a day, from a saved row of money a day at the preregistered grid's points: money
/// with tools and metres free, less family A's wafers a day (A's margin is 1 there), scaled to the dollar price.
pub fn b_revenue_from_grid(row: &[f64], a_wafers_day: f64, s: &Sheet) -> f64 {
    let grid = PriceGrid::preregistered("B");
    let d = s.get("b_decay");
    let i = grid
        .iter()
        .position(|m| {
            m.tool_day == 0.0
                && m.metre_day == 0.0
                && (m.decay - d).abs() < 1e-12
                && m.free_days == FREE_DAYS
        })
        .unwrap_or_else(|| panic!("the saved grid has no decay {d}"));
    (row[i] - a_wafers_day) / grid[i].price0 * s.get("b_price")
}

// ------------------------------------------------------------------ the saved two-family sweep

/// One saved run, ready to price.
#[derive(Clone, Debug)]
pub struct SavedRun {
    pub share: f64,
    pub strategy: String,
    pub policy: String,
    pub seed: u64,
    pub a_wafers_day: f64,
    pub b_wafers_day: f64,
    pub money_row: Vec<f64>,
}

/// The saved sweep and what each strategy adds at each share.
#[derive(Clone, Debug)]
pub struct SweepInputs {
    pub runs: Vec<SavedRun>,
    pub added: Vec<(f64, String, Added)>,
    pub alpha_each: f64,
}

fn summary_num(text: &str, key: &str) -> Result<f64, String> {
    let k = format!("\"{key}\":");
    let i = text
        .find(&k)
        .ok_or_else(|| format!("summary.json has no {key}"))?
        + k.len();
    let rest = &text[i..];
    let end = rest
        .find(|c: char| c == ',' || c == '}')
        .unwrap_or(rest.len());
    rest[..end]
        .trim()
        .parse()
        .map_err(|_| format!("summary.json: bad {key}"))
}

/// Read `runs.tsv` and `summary.json` in `dir`, and find what D2 and D3 add at each share from the SMT2020 files.
pub fn sweep_inputs(dir: &Path, smt: &Path) -> Result<SweepInputs, String> {
    let summary = std::fs::read_to_string(dir.join("summary.json"))
        .map_err(|e| format!("summary.json: {e}"))?;
    let days = summary_num(&summary, "days")?;
    let warmup = summary_num(&summary, "warmup")?;
    let alpha_each = summary_num(&summary, "alpha_each")?;
    let window = days - warmup;
    let tsv =
        std::fs::read_to_string(dir.join("runs.tsv")).map_err(|e| format!("runs.tsv: {e}"))?;
    let mut lines = tsv.lines();
    let head: Vec<&str> = lines
        .next()
        .ok_or("runs.tsv is empty")?
        .split('\t')
        .collect();
    let col = |name: &str| {
        head.iter()
            .position(|h| *h == name)
            .ok_or_else(|| format!("runs.tsv has no {name}"))
    };
    let (c_share, c_strat, c_pol, c_seed, c_a, c_bw) = (
        col("share")?,
        col("strategy")?,
        col("policy")?,
        col("seed")?,
        col("a_wafers_per_day")?,
        col("b_wafers")?,
    );
    let money_cols: Vec<usize> = (0..)
        .map_while(|i| head.iter().position(|h| *h == format!("money_{i}")))
        .collect();
    let num = |s: &str| {
        s.parse::<f64>()
            .map_err(|_| format!("runs.tsv: bad number {s:?}"))
    };
    let mut runs = vec![];
    for line in lines.filter(|l| !l.is_empty()) {
        let f: Vec<&str> = line.split('\t').collect();
        runs.push(SavedRun {
            share: num(f[c_share])?,
            strategy: f[c_strat].to_string(),
            policy: f[c_pol].to_string(),
            seed: num(f[c_seed])? as u64,
            a_wafers_day: num(f[c_a])?,
            b_wafers_day: num(f[c_bw])? / window,
            money_row: money_cols
                .iter()
                .map(|&c| num(f[c]))
                .collect::<Result<_, _>>()?,
        });
    }
    // what the strategies add: one tool for each of the three groups family B loads most (docs/TWO-FAMILIES-SWEEP.md)
    let base = crate::smt2020::load(smt)?;
    let area_of: HashMap<String, String> = crate::smt2020::areas(smt)?.into_iter().collect();
    let mut shares: Vec<f64> = runs.iter().map(|r| r.share).collect();
    shares.sort_by(f64::total_cmp);
    shares.dedup();
    let mut added = vec![];
    for &share in &shares {
        let e = EngLots {
            scale: share,
            ..EngLots::published("part_E3", days * 1440.0, 1)
        };
        let shop = two_family_shop(&base, "part_3", &e)?;
        let tools: Vec<(String, usize)> = contested(&shop, "B", 3)
            .into_iter()
            .map(|g| (area_of.get(&g).cloned().unwrap_or_default(), 1))
            .collect();
        added.push((
            share,
            "D1 share".to_string(),
            Added {
                tools: vec![],
                place: Place::None,
            },
        ));
        added.push((
            share,
            "D2 wing".to_string(),
            Added {
                tools: tools.clone(),
                place: Place::Wing,
            },
        ));
        added.push((
            share,
            "D3 copies".to_string(),
            Added {
                tools,
                place: Place::Halls,
            },
        ));
    }
    Ok(SweepInputs {
        runs,
        added,
        alpha_each,
    })
}

/// One priced run.
#[derive(Clone, Debug)]
pub struct RunRow {
    pub share: f64,
    pub strategy: String,
    pub policy: String,
    pub seed: u64,
    pub pl: Pl,
}

/// One cell against the shared floor with today's order at the same share, over the same seeds.
#[derive(Clone, Debug)]
pub struct CellPl {
    pub share: f64,
    pub strategy: String,
    pub policy: String,
    pub capital: f64,
    pub d_profit: Interval,
    pub d_cash: Interval,
    /// net present value: mean, lo, hi (capital is the same on every seed)
    pub npv: (f64, f64, f64),
    /// payback in days at the interval's ends of the change in cash: (soonest, latest); None is never
    pub payback: (Option<f64>, Option<f64>),
    pub verdict: String,
}

/// Today's fab at one share, its profit and loss averaged over the seeds.
#[derive(Clone, Debug)]
pub struct TodayPl {
    pub share: f64,
    pub revenue: f64,
    pub materials: f64,
    pub running: f64,
    pub cash: f64,
    pub depreciation: f64,
    pub profit: f64,
}

#[derive(Clone, Debug)]
pub struct SweepPl {
    pub runs: Vec<RunRow>,
    pub cells: Vec<CellPl>,
    pub today: Vec<TodayPl>,
    pub alpha_each: f64,
}

fn word(v: Verdict) -> String {
    match v {
        Verdict::Better => "better",
        Verdict::Worse => "worse",
        Verdict::CannotSay => "no clear effect",
    }
    .to_string()
}

fn payback_of(cap: f64, lo: f64, hi: f64) -> (Option<f64>, Option<f64>) {
    let at = |d: f64| if d > 0.0 { Some(cap / d) } else { None };
    (at(hi), at(lo))
}

/// Price the saved sweep with one sheet.
pub fn price_sweep(inp: &SweepInputs, s: &Sheet) -> SweepPl {
    let cap_of = |share: f64, strategy: &str| -> Capital {
        let a = inp
            .added
            .iter()
            .find(|a| a.0 == share && a.1 == strategy)
            .map(|a| a.2.clone());
        capital(
            &a.unwrap_or(Added {
                tools: vec![],
                place: Place::None,
            }),
            s,
        )
    };
    let runs: Vec<RunRow> = inp
        .runs
        .iter()
        .map(|r| {
            let cap = cap_of(r.share, &r.strategy);
            let b = b_revenue_from_grid(&r.money_row, r.a_wafers_day, s);
            RunRow {
                share: r.share,
                strategy: r.strategy.clone(),
                policy: r.policy.clone(),
                seed: r.seed,
                pl: run_pl(
                    &RunIn {
                        a_wafers_day: r.a_wafers_day,
                        b_wafers_day: r.b_wafers_day,
                        b_revenue_day: b,
                    },
                    &cap,
                    s,
                ),
            }
        })
        .collect();
    let factor = npv_factor(s);
    let mut cells = vec![];
    let mut today = vec![];
    let mut shares: Vec<f64> = runs.iter().map(|r| r.share).collect();
    shares.sort_by(f64::total_cmp);
    shares.dedup();
    for &share in &shares {
        let of = |st: &str, po: &str| -> Vec<&RunRow> {
            let mut v: Vec<&RunRow> = runs
                .iter()
                .filter(|r| r.share == share && r.strategy == st && r.policy == po)
                .collect();
            v.sort_by_key(|r| r.seed);
            v
        };
        let base = of("D1 share", "P0 today");
        if base.is_empty() {
            continue;
        }
        let n = base.len() as f64;
        let avg = |f: fn(&Pl) -> f64| base.iter().map(|r| f(&r.pl)).sum::<f64>() / n;
        today.push(TodayPl {
            share,
            revenue: avg(|p| p.revenue),
            materials: avg(|p| p.materials),
            running: avg(|p| p.running),
            cash: avg(|p| p.cash),
            depreciation: avg(|p| p.depreciation),
            profit: avg(|p| p.profit),
        });
        let mut keys: Vec<(String, String)> = vec![];
        for r in runs.iter().filter(|r| r.share == share) {
            let k = (r.strategy.clone(), r.policy.clone());
            if !keys.contains(&k) && !(k.0 == "D1 share" && k.1 == "P0 today") {
                keys.push(k);
            }
        }
        for (st, po) in keys {
            let cand = of(&st, &po);
            let cap = cap_of(share, &st);
            let d_profit = paired(
                &base.iter().map(|r| r.pl.profit).collect::<Vec<_>>(),
                &cand.iter().map(|r| r.pl.profit).collect::<Vec<_>>(),
                inp.alpha_each,
            );
            let d_cash = paired(
                &base.iter().map(|r| r.pl.cash).collect::<Vec<_>>(),
                &cand.iter().map(|r| r.pl.cash).collect::<Vec<_>>(),
                inp.alpha_each,
            );
            let npv = (
                -cap.total + d_cash.mean * factor,
                -cap.total + d_cash.lo * factor,
                -cap.total + d_cash.hi * factor,
            );
            let payback = payback_of(cap.total, d_cash.lo, d_cash.hi);
            let v = word(verdict(&d_profit, true));
            cells.push(CellPl {
                share,
                strategy: st,
                policy: po,
                capital: cap.total,
                d_profit,
                d_cash,
                npv,
                payback,
                verdict: v,
            });
        }
    }
    SweepPl {
        runs,
        cells,
        today,
        alpha_each: inp.alpha_each,
    }
}

/// The saved sweep priced with `s` (no rerun).
pub fn sweep_pl(dir: &Path, smt: &Path, s: &Sheet) -> Result<SweepPl, String> {
    Ok(price_sweep(&sweep_inputs(dir, smt)?, s))
}
