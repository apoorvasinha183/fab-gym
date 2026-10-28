//! Money a day for two wafer families (docs/TWO-FAMILIES.md). Every price is assumed, tagged and
//! swept; on the SMT2020 model, not a real fab.

use std::collections::HashMap;

use crate::engine::RunResult;
use crate::shop::Shop;
use crate::window::Window;

/// The assumed prices.
#[derive(Clone, Debug, PartialEq)]
pub struct Money {
    /// margin per wafer out, by family (a family not listed earns none)
    pub margin: Vec<(String, f64)>,
    /// the family paid by cycle time
    pub family_b: String,
    /// family B's price per wafer when out within `free_days`
    pub price0: f64,
    pub free_days: f64,
    /// the share of `price0` lost per day past `free_days` (the price never goes below 0)
    pub decay: f64,
    /// cost of one added tool per day
    pub tool_day: f64,
    /// cost of one added metre per day
    pub metre_day: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MoneyScore {
    /// earned less the added costs, per day of the window
    pub per_day: f64,
    /// margin earned per day, all families
    pub margin_per_day: f64,
    /// family B's price earned per day
    pub b_per_day: f64,
    pub cost_per_day: f64,
    pub b_lots: usize,
    pub b_wafers: i64,
    /// family B's mean cycle time in days, from scheduled arrival (so holding counts)
    pub b_cycle_days: Option<f64>,
}

/// Money a day over the window: lots finishing inside it, margin per wafer by family, family B
/// paid by its cycle time, less the added tools and metres.
pub fn money(shop: &Shop, r: &RunResult, w: &Window, m: &Money, tools_added: usize, metres_added: f64) -> MoneyScore {
    let days = (w.to - w.from) / 1440.0;
    let margin: HashMap<&str, f64> = m.margin.iter().map(|(f, x)| (f.as_str(), *x)).collect();
    let sched: HashMap<&str, f64> = r.release_log.iter().map(|x| (x.id.as_str(), x.scheduled)).collect();
    let (mut a, mut b, mut b_lots, mut b_wafers, mut ct_sum) = (0.0, 0.0, 0usize, 0i64, 0.0);
    for l in &r.lots {
        let Some(d) = l.done else { continue };
        if !(d > w.from && d <= w.to) {
            continue;
        }
        let fam = shop.family_of(&l.route);
        a += l.size as f64 * margin.get(fam).copied().unwrap_or(0.0);
        if fam == m.family_b {
            let start = *sched.get(l.id.as_str()).unwrap_or(&l.release);
            let ct = (d - start) / 1440.0;
            let price = m.price0 * (1.0 - m.decay * (ct - m.free_days).max(0.0)).max(0.0);
            b += l.size as f64 * price;
            b_lots += 1;
            b_wafers += l.size;
            ct_sum += ct;
        }
    }
    let cost = tools_added as f64 * m.tool_day + metres_added * m.metre_day;
    MoneyScore {
        per_day: (a + b) / days - cost,
        margin_per_day: a / days,
        b_per_day: b / days,
        cost_per_day: cost,
        b_lots,
        b_wafers,
        b_cycle_days: if b_lots > 0 { Some(ct_sum / b_lots as f64) } else { None },
    }
}
