//! Measures on a shop.

use std::collections::BTreeMap;

use crate::engine::{run, RunOptions};
use crate::shop::{LotSpec, Per, Shop};

/// Raw processing time per product, in days: one lot at a time in an empty fab, with no other
/// lots, maintenance, breakdowns, setups or transport, each batch of the lot alone, loading and
/// unloading counted; the mean over `lots` lots (seeds `seed`, `seed + 1`, ...).
pub fn raw_processing_days(shop: &Shop, lots: usize, seed: u64) -> BTreeMap<String, f64> {
    let mut base = shop.clone();
    base.lots.clear();
    base.releases.clear();
    base.probes.clear();
    base.cap = None;
    base.transport = (0.0, 0.0);
    for g in &mut base.groups {
        g.pm.clear();
        g.pm_pieces.clear();
        g.breakdown = None;
        g.setups.clear();
    }
    for r in &mut base.routes {
        for st in &mut r.steps {
            if st.per == Per::Batch {
                st.batch = Some((0.0, 25.0));
            }
        }
    }
    let mut out = BTreeMap::new();
    for r in &shop.routes {
        let mut sum = 0.0;
        for i in 0..lots {
            let id = format!("{}.{i}", r.name);
            let mut one = base.clone();
            one.lots = vec![LotSpec { id: id.clone(), route: r.name.clone(), size: 25, priority: 10.0, start: 0.0, step: 0 }];
            let res = run(&one, &RunOptions { seed: seed + i as u64, until: None, record: false }, None);
            let done = res.lots[0].done.expect("the lot finishes in an empty fab");
            sum += done / 1440.0;
        }
        out.insert(r.name.clone(), sum / lots as f64);
    }
    out
}
