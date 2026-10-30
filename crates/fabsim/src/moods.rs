//! Moods from a run (docs/RUN-MOODS.md): each machine's and each lot's mood at a moment, read off a recorded run, and
//! each rail stretch's jam. The names are the cast's (web/cast/cast.json).

use crate::engine::RunResult;
use crate::shop::Shop;
use std::collections::HashMap;

pub const TOOL_MOODS: [&str; 10] = ["work", "sleep", "tired", "full", "batch", "setup", "pm", "hurt", "physio", "hold"];
pub const LOT_MOODS: [&str; 12] = ["fresh", "line", "impatient", "hot", "clock", "missed", "bench", "ride", "batch", "redo", "hold", "grad"];

/// The thresholds (docs/RUN-MOODS.md; the window and the two shares decided by quiz 31 Oct, the rest assumed).
#[derive(Clone, Debug)]
pub struct Settings {
    pub window: f64,
    pub doze_below: f64,
    pub gassed_above: f64,
    pub hurt_minutes: f64,
    pub impatient_after: f64,
    pub fresh_within: f64,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { window: 480.0, doze_below: 0.30, gassed_above: 0.90, hurt_minutes: 15.0, impatient_after: 480.0, fresh_within: 60.0 }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ToolMood {
    pub tool: String,
    pub group: String,
    pub mood: &'static str,
}

#[derive(Clone, Debug, PartialEq)]
pub struct LotMood {
    pub lot: String,
    pub mood: &'static str,
    pub hot: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RailJam {
    pub stretch: String,
    /// average minutes beyond free flow, over the window
    pub jam: f64,
}

#[derive(Clone, Debug, PartialEq, Default)]
pub struct Snapshot {
    pub t: f64,
    pub tools: Vec<ToolMood>,
    pub lots: Vec<LotMood>,
    pub rails: Vec<RailJam>,
}

/// A run indexed for reading moods at many moments.
pub struct Moods<'a> {
    shop: &'a Shop,
    run: &'a RunResult,
    set: Settings,
    /// per tool: (time, state, why), in time order
    rows: Vec<Vec<(f64, &'static str, &'static str)>>,
    /// per group: (arrive, start) of every started step
    waits: HashMap<String, Vec<(f64, f64)>>,
    batch_groups: std::collections::HashSet<String>,
    /// per tool: (end, lot) of every step it did
    done_at: Vec<Vec<(f64, u32)>>,
    /// per lot: hoists (up, t0, t1)
    hoists: HashMap<u32, Vec<(bool, f64, f64)>>,
    /// per lot id: hold times
    holds: HashMap<u32, Vec<f64>>,
    /// per lot: (step, arrive, start, end) from the trace, in start order
    steps: Vec<Vec<(usize, f64, f64, f64)>>,
    ports: usize,
    /// per stretch: name, free-flow minutes, and (t_in, t_out) of every stay
    rails: Vec<(String, f64, Vec<(f64, f64)>)>,
}

impl<'a> Moods<'a> {
    pub fn new(shop: &'a Shop, run: &'a RunResult, set: &Settings) -> Moods<'a> {
        let nt = run.tools.len();
        let mut rows = vec![vec![]; nt];
        for s in &run.states {
            rows[s.tool_index as usize].push((s.time, s.state, s.why));
        }
        let mut steps = vec![vec![]; run.lots.len()];
        let mut waits: HashMap<String, Vec<(f64, f64)>> = HashMap::new();
        let mut done_at = vec![vec![]; nt];
        for tr in &run.trace {
            let g = &run.tools[tr.tool as usize].group;
            waits.entry(g.clone()).or_default().push((tr.arrive, tr.start));
            done_at[tr.tool as usize].push((tr.end, tr.lot));
            if let Some(v) = steps.get_mut(tr.lot as usize) {
                v.push((tr.step as usize, tr.arrive, tr.start, tr.end));
            }
        }
        let batch_groups = shop.routes.iter().flat_map(|r| r.steps.iter()).filter(|s| s.batch.is_some_and(|b| b.0 > 1.0)).map(|s| s.group.clone()).collect();
        let mut hoists: HashMap<u32, Vec<(bool, f64, f64)>> = HashMap::new();
        let mut rails = vec![];
        if let Some(f) = &run.fleet {
            for h in &f.hoists {
                hoists.entry(h.lot).or_default().push((h.up, h.t0, h.t1));
            }
            let floor = crate::engine::native_floor(shop);
            let s = floor.as_ref().unwrap_or(shop);
            if s.oht.is_some() {
                let track = crate::track::Track::from_shop(s);
                let speed = s.oht.as_ref().unwrap().speed;
                rails = track.edges().iter().map(|e| (format!("{}>{}", track.name(e.from), track.name(e.to)), e.len / speed, vec![])).collect();
                for en in &f.entries {
                    rails[en.edge].2.push((en.t_in, en.t_out));
                }
            }
        }
        for v in &mut steps {
            v.sort_by(|a: &(usize, f64, f64, f64), b| a.2.total_cmp(&b.2));
        }
        let mut holds: HashMap<u32, Vec<f64>> = HashMap::new();
        for h in &run.holds {
            for &l in &h.lots {
                holds.entry(l).or_default().push(h.t);
            }
        }
        let ports = shop.fleet.as_ref().map(|f| f.ports).unwrap_or(0);
        Moods { shop, run, set: set.clone(), rows, waits, batch_groups, done_at, hoists, holds, steps, ports, rails }
    }

    /// Lots that have arrived at a group and not started, at `t`.
    pub fn group_queue(&self, group: &str, t: f64) -> usize {
        self.queue(group, t)
    }

    fn queue(&self, group: &str, t: f64) -> usize {
        self.waits.get(group).map(|v| v.iter().filter(|w| w.0 <= t && w.1 > t).count()).unwrap_or(0)
    }

    fn busy_share(&self, ti: usize, t: f64) -> f64 {
        let t0 = (t - self.set.window).max(0.0);
        if t <= t0 {
            return 0.0;
        }
        let rows = &self.rows[ti];
        let mut busy = 0.0;
        for (k, r) in rows.iter().enumerate() {
            let a = r.0;
            let b = rows.get(k + 1).map(|x| x.0).unwrap_or(f64::INFINITY);
            if r.1 == "productive" {
                busy += (b.min(t) - a.max(t0)).max(0.0);
            }
        }
        busy / (t - t0)
    }

    fn picked_up_after(&self, lot: u32, end: f64) -> f64 {
        self.hoists.get(&lot).and_then(|v| v.iter().filter(|h| h.0 && h.1 >= end).map(|h| h.1).fold(None, |m: Option<f64>, x| Some(m.map_or(x, |m| m.min(x))))).unwrap_or(f64::INFINITY)
    }

    pub fn tool_mood(&self, ti: usize, t: f64) -> &'static str {
        let rows = &self.rows[ti];
        let cur = rows.iter().rev().find(|r| r.0 <= t);
        let (since, state, why) = cur.copied().unwrap_or((0.0, "standby", ""));
        match (state, why) {
            ("unscheduled down", "hold") => return "hold",
            ("unscheduled down", _) => return if t - since < self.set.hurt_minutes { "hurt" } else { "physio" },
            ("scheduled down", "setup") => return "setup",
            ("scheduled down", _) => return "pm",
            _ => {}
        }
        if self.ports > 0 {
            let waiting = self.done_at[ti].iter().filter(|(end, lot)| *end <= t && self.picked_up_after(*lot, *end) > t).count();
            if waiting >= self.ports {
                return "full";
            }
        }
        let group = &self.run.tools[ti].group;
        let q = self.queue(group, t);
        if state == "standby" && q > 0 && self.batch_groups.contains(group) {
            return "batch";
        }
        let share = self.busy_share(ti, t);
        if share < self.set.doze_below && q == 0 {
            return "sleep";
        }
        if share > self.set.gassed_above && q > self.queue(group, t - self.set.window) {
            return "tired";
        }
        "work"
    }

    pub fn lot_mood(&self, li: usize, t: f64) -> Option<&'static str> {
        let l = &self.run.lots[li];
        if l.release > t && !l.wip {
            return None;
        }
        if l.done.is_some_and(|d| d <= t) {
            return Some("grad");
        }
        let st = &self.steps[li];
        if st.iter().any(|s| s.2 <= t && t < s.3) {
            return Some("bench");
        }
        if let Some(v) = self.hoists.get(&(li as u32)) {
            for (k, h) in v.iter().enumerate() {
                if h.0 && h.1 <= t {
                    let down = v[k + 1..].iter().find(|d| !d.0).map(|d| d.2).unwrap_or(f64::INFINITY);
                    if t < down {
                        return Some("ride");
                    }
                }
            }
        }
        // waiting for its next step
        let finished: Vec<&(usize, f64, f64, f64)> = st.iter().filter(|s| s.3 <= t).collect();
        let last = finished.iter().max_by(|a, b| a.3.total_cmp(&b.3));
        let next = st.iter().filter(|s| s.2 > t).min_by(|a, b| a.2.total_cmp(&b.2));
        let since = last.map(|s| s.3).unwrap_or(l.release);
        if self.holds.get(&(li as u32)).is_some_and(|v| v.iter().any(|&h| h <= t && h >= since)) {
            return Some("hold");
        }
        if let Some(route) = self.shop.route(&l.route) {
            let mut inside = false;
            for s in &finished {
                if let Some((to, limit)) = route.steps.get(s.0).and_then(|x| x.cqt) {
                    let reached = st.iter().any(|x| x.0 == to && x.2 > s.3 && x.2 <= t);
                    if !reached {
                        if t - s.3 > limit {
                            return Some("missed");
                        }
                        inside = true;
                    }
                }
            }
            if inside {
                return Some("clock");
            }
            if let (Some(n), Some(p)) = (next, last) {
                if n.0 <= p.0 {
                    return Some("redo");
                }
            }
            let next_idx = next.map(|n| n.0).or(last.map(|p| p.0 + 1)).unwrap_or(0);
            if route.steps.get(next_idx).is_some_and(|x| x.batch.is_some_and(|b| b.0 > 1.0)) {
                return Some("batch");
            }
        }
        if t - since > self.set.impatient_after {
            return Some("impatient");
        }
        if finished.is_empty() && t - l.release < self.set.fresh_within {
            return Some("fresh");
        }
        Some("line")
    }

    pub fn at(&self, t: f64) -> Snapshot {
        let tools = (0..self.run.tools.len())
            .map(|ti| ToolMood { tool: self.run.tools[ti].name.clone(), group: self.run.tools[ti].group.clone(), mood: self.tool_mood(ti, t) })
            .collect();
        let lots = (0..self.run.lots.len())
            .filter_map(|li| {
                self.lot_mood(li, t).map(|m| LotMood { lot: self.run.lots[li].id.clone(), mood: m, hot: self.run.lots[li].priority >= crate::dials::HOT_PRIORITY })
            })
            .collect();
        let t0 = t - self.set.window;
        let rails = self
            .rails
            .iter()
            .map(|(name, free, stays)| {
                let done: Vec<f64> = stays.iter().filter(|s| s.0 >= t0 && s.1 <= t).map(|s| (s.1 - s.0 - free).max(0.0)).collect();
                RailJam { stretch: name.clone(), jam: if done.is_empty() { 0.0 } else { done.iter().sum::<f64>() / done.len() as f64 } }
            })
            .collect();
        Snapshot { t, tools, lots, rails }
    }
}

/// Moods at one moment (indexes the run each call; for many moments use `Moods`).
pub fn snapshot(shop: &Shop, run: &RunResult, t: f64, set: &Settings) -> Snapshot {
    Moods::new(shop, run, set).at(t)
}

/// The five scores of a run (docs/EDITOR-REPLAY.md).
#[derive(Clone, Debug, PartialEq)]
pub struct Score {
    pub wafers_per_day: f64,
    /// by Little's law: the average wafers in the fab over the frames, over wafers out a day; infinite with none out
    pub cycle_days: f64,
    pub worst_group: String,
    pub worst_queue: usize,
    pub jams: usize,
    pub spend_usd: Option<f64>,
}

/// The run's score, its frames every `every` minutes from 0 to the run's end.
pub fn score(shop: &Shop, run: &RunResult, set: &Settings, every: f64) -> Score {
    let m = Moods::new(shop, run, set);
    let days = run.until / 1440.0;
    let out: i64 = run.lots.iter().filter(|l| l.done.is_some_and(|d| d <= run.until)).map(|l| l.size).sum();
    let wafers_per_day = if days > 0.0 { out as f64 / days } else { 0.0 };
    let mut frames = vec![];
    let mut t = 0.0;
    while t <= run.until + 1e-9 {
        frames.push(t);
        t += every;
    }
    let mut wip = 0.0;
    let (mut worst_group, mut worst_queue) = (String::new(), 0usize);
    for &t in &frames {
        wip += (0..run.lots.len()).filter(|&li| m.lot_mood(li, t).is_some_and(|x| x != "grad")).map(|li| run.lots[li].size as f64).sum::<f64>();
        for g in &shop.groups {
            let q = m.queue(&g.name, t);
            if q > worst_queue {
                worst_group = g.name.clone();
                worst_queue = q;
            }
        }
    }
    wip /= frames.len().max(1) as f64;
    let cycle_days = if wafers_per_day > 0.0 { wip / wafers_per_day } else { f64::INFINITY };
    let jams = m
        .rails
        .iter()
        .filter(|(_, free, stays)| {
            let done: Vec<f64> = stays.iter().filter(|s| s.1.is_finite()).map(|s| (s.1 - s.0 - free).max(0.0)).collect();
            !done.is_empty() && done.iter().sum::<f64>() / done.len() as f64 > 1.0
        })
        .count();
    let spend_usd = shop.plan.as_ref().filter(|p| !p.prices.is_empty()).map(|p| {
        p.prices.iter().map(|r| shop.group(&r.group).map(|g| g.count as f64 * r.buy).unwrap_or(0.0)).sum()
    });
    Score { wafers_per_day, cycle_days, worst_group, worst_queue, jams, spend_usd }
}

/// One stay of a vehicle on a rail stretch (docs/EDITOR-REPLAY.md).
#[derive(Clone, Debug, PartialEq)]
pub struct Stay {
    pub vehicle: u32,
    pub edge: usize,
    pub from: String,
    pub to: String,
    pub t_in: f64,
    /// infinite while the vehicle is still on the stretch at the run's end
    pub t_out: f64,
    pub loaded: bool,
    pub hot: bool,
}

/// Every vehicle's stays on rail stretches that overlap `[from, to]`, by vehicle and time; empty without a fleet.
pub fn replay(shop: &Shop, run: &RunResult, from: f64, to: f64) -> Vec<Stay> {
    let Some(f) = &run.fleet else { return vec![] };
    let floor = crate::engine::native_floor(shop);
    let s = floor.as_ref().unwrap_or(shop);
    if s.oht.is_none() {
        return vec![];
    }
    let track = crate::track::Track::from_shop(s);
    // per vehicle, its hoists in time order: (t0, up, lot)
    let mut hoists: HashMap<u32, Vec<(f64, bool, u32)>> = HashMap::new();
    for h in &f.hoists {
        hoists.entry(h.vehicle).or_default().push((h.t0, h.up, h.lot));
    }
    for v in hoists.values_mut() {
        v.sort_by(|a, b| a.0.total_cmp(&b.0));
    }
    let aboard = |v: u32, t: f64| -> Option<u32> {
        let hs = hoists.get(&v)?;
        let mut lot = None;
        for &(t0, up, l) in hs {
            if t0 > t {
                break;
            }
            lot = if up { Some(l) } else { None };
        }
        lot
    };
    let mut out: Vec<Stay> = f
        .entries
        .iter()
        .filter(|e| e.t_out >= from && e.t_in <= to)
        .map(|e| {
            let ed = &track.edges()[e.edge];
            let hot = e.loaded && aboard(e.vehicle, e.t_in).is_some_and(|l| run.lots.get(l as usize).is_some_and(|x| x.priority >= crate::dials::HOT_PRIORITY));
            Stay { vehicle: e.vehicle, edge: e.edge, from: track.name(ed.from), to: track.name(ed.to), t_in: e.t_in, t_out: e.t_out, loaded: e.loaded, hot }
        })
        .collect();
    out.sort_by(|a, b| a.vehicle.cmp(&b.vehicle).then(a.t_in.total_cmp(&b.t_in)));
    out
}

/// The frames `fabsim moods` writes (docs/RUN-MOODS.md): every tool's mood, each group's queue, lot moods counted, hot
/// lots and rail jams, every `every` minutes from 0 to `until`, with the run's score. Shared by the command line and
/// the browser build, so both pages show the same moods.
pub fn frames_json(shop: &Shop, run: &RunResult, until: f64, every: f64) -> serde_json::Value {
    let set = Settings::default();
    let m = Moods::new(shop, run, &set);
    let ti = |s: &str| TOOL_MOODS.iter().position(|m| *m == s).unwrap();
    let mut frames = vec![];
    let mut stretches = vec![];
    let mut t = 0.0;
    while t <= until + 1e-9 {
        let s = m.at(t);
        let mut counts = serde_json::Map::new();
        for name in LOT_MOODS {
            counts.insert(name.into(), serde_json::json!(s.lots.iter().filter(|l| l.mood == name).count()));
        }
        let hot: Vec<serde_json::Value> = s.lots.iter().filter(|l| l.hot).map(|l| serde_json::json!([l.lot, l.mood])).collect();
        if stretches.is_empty() {
            stretches = s.rails.iter().map(|x| x.stretch.clone()).collect();
        }
        frames.push(serde_json::json!({
            "t": t,
            "queues": shop.groups.iter().map(|g| m.group_queue(&g.name, t)).collect::<Vec<_>>(),
            "tools": s.tools.iter().map(|x| ti(x.mood)).collect::<Vec<_>>(),
            "lots": counts,
            "hot": hot,
            "rails": s.rails.iter().map(|x| (x.jam * 100.0).round() / 100.0).collect::<Vec<_>>(),
        }));
        t += every;
    }
    let sc = score(shop, run, &set, every);
    let fin = |x: f64| if x.is_finite() { serde_json::json!((x * 100.0).round() / 100.0) } else { serde_json::Value::Null };
    serde_json::json!({
        "about": "Moods from a Fab Gym run (docs/RUN-MOODS.md). From the SMT2020 testbed or a layout of its own; not a real fab.",
        "tool_moods": TOOL_MOODS,
        "lot_moods": LOT_MOODS,
        "tools": run.tools.iter().map(|x| x.name.clone()).collect::<Vec<_>>(),
        "groups": run.tools.iter().map(|x| x.group.clone()).collect::<Vec<_>>(),
        "stretches": stretches,
        "group_names": shop.groups.iter().map(|g| g.name.clone()).collect::<Vec<_>>(),
        "score": {"wafers_per_day": fin(sc.wafers_per_day), "cycle_days": fin(sc.cycle_days), "worst_group": sc.worst_group,
            "worst_queue": sc.worst_queue, "jams": sc.jams, "spend_usd": sc.spend_usd},
        "frames": frames,
    })
}
