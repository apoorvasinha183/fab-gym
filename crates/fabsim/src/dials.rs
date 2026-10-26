//! What-if dials, applied to a copy of a shop. Every dial at its default leaves the shop as it is.

use crate::shop::Shop;

/// Every tool of one group down for a while.
#[derive(Clone, Debug, PartialEq)]
pub struct Outage {
    pub group: String,
    /// minutes from the start of the run
    pub from: f64,
    pub hours: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Dials {
    /// breakdown rate multiplier: mean time to failure is divided by this (0: no breakdowns)
    pub breakdowns: f64,
    /// mean time to repair multiplier
    pub repair: f64,
    /// release rate multiplier for every stream
    pub demand: f64,
    /// release rate multiplier for streams above the lowest priority (0: none released)
    pub hot: f64,
    /// rework probability multiplier, capped at 1
    pub rework: f64,
    /// a WIP cap in lots; replaces the shop's own cap when given
    pub cap: Option<i64>,
    pub outage: Option<Outage>,
    /// more tools in a group: (group, how many); existing tools keep their random draws
    pub spare: Vec<(String, usize)>,
    /// lots in progress made hot (priority 20), spread evenly over the lots sorted by id
    pub make_hot: usize,
}

/// The priority a lot made hot gets.
pub const HOT_PRIORITY: f64 = 20.0;

impl Default for Dials {
    fn default() -> Dials {
        Dials { breakdowns: 1.0, repair: 1.0, demand: 1.0, hot: 1.0, rework: 1.0, cap: None, outage: None, spare: vec![], make_hot: 0 }
    }
}

impl Dials {
    pub fn apply(&self, shop: &Shop) -> Result<Shop, String> {
        let pos = |x: f64, what: &str| if x > 0.0 && x.is_finite() { Ok(()) } else { Err(format!("{what} must be above 0, got {x}")) };
        let nonneg = |x: f64, what: &str| if x >= 0.0 && x.is_finite() { Ok(()) } else { Err(format!("{what} must be 0 or more, got {x}")) };
        nonneg(self.breakdowns, "breakdowns")?;
        pos(self.repair, "repair")?;
        pos(self.demand, "demand")?;
        nonneg(self.hot, "hot")?;
        nonneg(self.rework, "rework")?;
        if let Some(c) = self.cap {
            if c < 1 {
                return Err(format!("cap must be at least 1 lot, got {c}"));
            }
        }
        let mut s = shop.clone();
        for g in &mut s.groups {
            if let Some((mttf, mttr)) = g.breakdown {
                g.breakdown = if self.breakdowns == 0.0 {
                    None
                } else {
                    Some((if self.breakdowns == 1.0 { mttf } else { mttf / self.breakdowns }, mttr * self.repair))
                };
            }
        }
        let lowest = s.releases.iter().map(|r| r.priority).fold(f64::INFINITY, f64::min);
        if self.hot == 0.0 {
            s.releases.retain(|r| r.priority <= lowest);
        }
        for r in &mut s.releases {
            let mut k = self.demand;
            if r.priority > lowest {
                k *= self.hot;
            }
            if k != 1.0 {
                r.every /= k;
            }
        }
        if self.rework != 1.0 {
            for route in &mut s.routes {
                for st in &mut route.steps {
                    if let Some((to, p)) = st.rework {
                        st.rework = Some((to, (p * self.rework).min(1.0)));
                    }
                }
            }
        }
        if self.cap.is_some() {
            s.cap = self.cap;
        }
        if let Some(o) = &self.outage {
            pos(o.hours, "outage hours")?;
            nonneg(o.from, "outage start")?;
            let g = s.groups.iter_mut().find(|g| g.name == o.group).ok_or_else(|| format!("no tool group {:?}", o.group))?;
            g.down.push((o.from, o.from + o.hours * 60.0));
        }
        for (name, n) in &self.spare {
            if *n == 0 {
                return Err(format!("spare tools for {name:?} must be at least 1"));
            }
            let g = s.groups.iter_mut().find(|g| &g.name == name).ok_or_else(|| format!("no tool group {name:?}"))?;
            g.count += n;
        }
        if self.make_hot > 0 {
            let mut ids: Vec<(String, usize)> =
                s.lots.iter().enumerate().filter(|(_, l)| l.priority < HOT_PRIORITY).map(|(i, l)| (l.id.clone(), i)).collect();
            ids.sort();
            let (m, n) = (ids.len(), self.make_hot);
            if n > m {
                return Err(format!("{n} hot lots asked for, {m} lots in progress are not hot"));
            }
            for i in 0..n {
                let k = ((i as f64 + 0.5) * m as f64 / n as f64) as usize;
                s.lots[ids[k.min(m - 1)].1].priority = HOT_PRIORITY;
            }
        }
        Ok(s)
    }
}
