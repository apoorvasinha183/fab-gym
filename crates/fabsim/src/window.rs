//! Scores over a window of a run: wafers out, cycle time by Little's law, hot-lot cycle time.

use crate::engine::RunResult;
use crate::shop::Shop;

/// A window of fab time, in minutes: (from, to].
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Window {
    pub from: f64,
    pub to: f64,
}

impl Window {
    pub fn check(&self) -> Result<(), String> {
        if self.from >= 0.0 && self.to > self.from && self.to.is_finite() {
            Ok(())
        } else {
            Err(format!("a window needs 0 <= from < to, got ({}, {})", self.from, self.to))
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct WindowScore {
    pub lots_per_day: f64,
    pub wafers_per_day: f64,
    /// lots in the fab, averaged over the window
    pub mean_wip: f64,
    /// lot-minutes in the fab over lots finished, in days (Little's law)
    pub cycle_days: f64,
    /// lots released during the run above the lowest priority, finished in the window
    pub hot_lots: usize,
    pub hot_cycle_days: Option<f64>,
    /// steps started in the window
    pub moves: f64,
    pub lots_finished: f64,
    pub wait_lot_hours: f64,
    pub wait_per_move_minutes: f64,
    /// lots that broke a queue-time limit in the window
    pub breaches: f64,
    /// lots finished minus 0.01 per lot-hour waiting (docs/PROBLEM.md)
    pub reward: f64,
}

/// A copy of the shop with probes at the window's ends (kept sorted, without repeats).
pub fn with_probes(shop: &Shop, w: &Window) -> Shop {
    let mut s = shop.clone();
    s.probes.push(w.from);
    s.probes.push(w.to);
    s.probes.sort_by(|a, b| a.partial_cmp(b).unwrap());
    s.probes.dedup();
    s
}

/// Score a run over a window. The run needs probes at both ends (`with_probes`).
pub fn score(r: &RunResult, w: &Window) -> Result<WindowScore, String> {
    w.check()?;
    let at = |t: f64| r.probes.iter().find(|p| p.t == t).ok_or_else(|| format!("no probe at {t}; use window::with_probes"));
    let (a, b) = (at(w.from)?, at(w.to)?);
    let days = (w.to - w.from) / 1440.0;
    let done: Vec<_> = r.lots.iter().filter(|l| matches!(l.done, Some(d) if d > w.from && d <= w.to)).collect();
    let lots = done.len() as f64;
    let wafers: f64 = done.iter().map(|l| l.size as f64).sum();
    let lot_minutes = b.wip_lot_minutes - a.wip_lot_minutes;
    let lowest = r.lots.iter().map(|l| l.priority).fold(f64::INFINITY, f64::min);
    let hot: Vec<f64> = done.iter().filter(|l| !l.wip && l.priority > lowest).map(|l| (l.done.unwrap() - l.release) / 1440.0).collect();
    let moves = (b.moves - a.moves) as f64;
    let wait_lot_hours = (b.wait_lot_minutes - a.wait_lot_minutes) / 60.0;
    let breaches = r.breaches.iter().filter(|x| x.t > w.from && x.t <= w.to).count() as f64;
    Ok(WindowScore {
        moves,
        lots_finished: lots,
        wait_lot_hours,
        wait_per_move_minutes: if moves > 0.0 { wait_lot_hours * 60.0 / moves } else { f64::NAN },
        breaches,
        reward: lots - 0.01 * wait_lot_hours,
        lots_per_day: lots / days,
        wafers_per_day: wafers / days,
        mean_wip: lot_minutes / (w.to - w.from),
        cycle_days: if lots > 0.0 { lot_minutes / lots / 1440.0 } else { f64::NAN },
        hot_lots: hot.len(),
        hot_cycle_days: if hot.is_empty() { None } else { Some(hot.iter().sum::<f64>() / hot.len() as f64) },
    })
}
