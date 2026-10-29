//! The machine-paced simulator: lots move along routes of steps, each step done by one tool of
//! a named group. Tools break down, get maintained by calendar or by pieces processed, batch
//! work and change over between setups. Releases can be held by a WIP cap.
//!
//! The rules (reproduced exactly from the reference engine, so the logs match bit for bit):
//! a free tool takes the waiting lot of highest priority, then one needing no setup change,
//! then the earliest arrival. A batch is ready when its pieces reach the maximum less one lot
//! (and the minimum), or when the oldest has waited the batch wait. Work is not interrupted:
//! a down due while a tool works starts when the work ends. Random draws come from streams
//! named by seed and lot or tool, so a change to one lot leaves the others' draws alone.
//!
//! A chooser can replace the dispatch rule: whenever a free tool could start work, it gets a
//! [`Decision`] (only the past and present) and returns the index of a candidate. An index out
//! of range falls back to the engine's own rule, `Decision::default`.

use std::cmp::Ordering;
use std::collections::{BTreeMap, BinaryHeap, HashMap, VecDeque};
use std::fmt::Write as _;

use crate::pyrandom::PyRandom;
use crate::fleet::{Entry, FleetState, HoistRec, Job, Mode, Pos};
pub use crate::fleet::{FleetOut, IdleVehicle, VehicleAsk};
use crate::shop::{Oht, Per, Place, Shop};

pub const STATES: [&str; 4] = ["productive", "standby", "scheduled down", "unscheduled down"];
const PRODUCTIVE: u8 = 0;
const STANDBY: u8 = 1;
const SCHEDULED: u8 = 2;
const UNSCHEDULED: u8 = 3;

#[derive(Clone, Debug)]
pub struct RunOptions {
    pub seed: u64,
    /// stop after this many minutes (events after it are not run); None runs until no events
    pub until: Option<f64>,
    /// keep every lot's steps and every tool state change
    pub record: bool,
}

/// What a free tool sees when it could start work.
#[derive(Clone, Debug)]
pub struct Decision {
    pub t: f64,
    pub tool_group: String,
    pub tool: String,
    pub tool_setup: Option<String>,
    pub group_tools: GroupTools,
    pub totals: Totals,
    pub candidates: Vec<Candidate>,
    /// the index the engine's own rule picks
    pub default: usize,
}

impl Decision {
    pub const FIELDS: [&'static str; 8] =
        ["t", "tool_group", "tool", "tool_setup", "group_tools", "totals", "candidates", "default"];
}

/// The tools of the deciding tool's group, by what they are doing.
#[derive(Clone, Copy, Debug, Default)]
pub struct GroupTools {
    pub working: u32,
    pub idle: u32,
    pub down: u32,
    /// of the down tools, those on a defect hold (docs/RL-DEFECTS.md)
    pub held: u32,
}

/// Running totals so far: lots finished, lots waiting, and lot-minutes spent waiting.
#[derive(Clone, Copy, Debug, Default)]
pub struct Totals {
    pub finished: i64,
    pub waiting: i64,
    pub wait_lot_minutes: f64,
}

/// One thing the tool could start: a lot, or a batch of lots.
#[derive(Clone, Debug)]
pub struct Candidate {
    /// "lot" or "batch"
    pub kind: &'static str,
    pub lots: Vec<String>,
    pub priority: f64,
    pub size_wafers: i64,
    pub route: String,
    pub step: usize,
    pub steps_left: usize,
    pub waited_minutes: f64,
    pub setup_change: bool,
    /// nominal processing minutes of this step (no load, unload or draw)
    pub proc_minutes: f64,
    /// nominal processing minutes from this step to the end of the route
    pub work_left_minutes: f64,
    pub release: f64,
    /// minutes left before a queue-time limit is breached, if one runs to this step
    pub cqt_slack_minutes: Option<f64>,
    /// the lot's family ("" when the shop names none; docs/TWO-FAMILIES.md)
    pub family: String,
}

impl Candidate {
    pub const FIELDS: [&'static str; 14] = [
        "kind",
        "lots",
        "priority",
        "size_wafers",
        "route",
        "step",
        "steps_left",
        "waited_minutes",
        "setup_change",
        "proc_minutes",
        "work_left_minutes",
        "release",
        "cqt_slack_minutes",
        "family",
    ];
}

#[derive(Clone, Debug)]
pub struct StepOut {
    pub step: usize,
    pub tool: String,
    pub arrive: f64,
    pub start: f64,
    pub end: f64,
}

#[derive(Clone, Debug)]
pub struct LotOut {
    pub id: String,
    pub route: String,
    pub priority: f64,
    pub size: i64,
    pub release: f64,
    pub done: Option<f64>,
    /// in progress when the run began
    pub wip: bool,
    pub steps: Vec<StepOut>,
}

#[derive(Clone, Debug)]
pub struct StateRow {
    pub tool: String,
    /// index into `RunResult::tools`
    pub tool_index: u32,
    pub time: f64,
    pub state: &'static str,
    pub why: &'static str,
}

/// One step of one lot, for viewers: every started step, including a released lot's first
/// (which the reference engine's per-lot steps leave out). Indexes into `lots` and `tools`.
#[derive(Clone, Copy, Debug)]
pub struct Trace {
    pub lot: u32,
    pub step: u32,
    pub tool: u32,
    pub arrive: f64,
    pub start: f64,
    pub end: f64,
}

#[derive(Clone, Debug)]
pub struct Breach {
    /// when the late step began (not in the log, which stays as the reference writes it)
    pub t: f64,
    pub lot: String,
    pub from: usize,
    pub to: usize,
    pub limit: f64,
    pub waited: f64,
}

#[derive(Clone, Debug)]
pub struct ToolOut {
    pub name: String,
    pub group: String,
    /// minutes in each of STATES
    pub minutes: [f64; 4],
}

#[derive(Clone, Debug)]
pub struct GroupOut {
    pub name: String,
    pub busy: f64,
    pub wait: f64,
    pub visits: i64,
    pub count: usize,
}

#[derive(Clone, Debug)]
pub struct ReleaseRow {
    pub id: String,
    pub scheduled: f64,
    pub released: Option<f64>,
    pub wip_before: Option<i64>,
}

#[derive(Clone, Debug)]
pub struct Probe {
    pub t: f64,
    pub finished: i64,
    pub wip: i64,
    pub moves: i64,
    pub waiting: i64,
    pub wait_lot_minutes: f64,
    pub wip_lot_minutes: f64,
    /// moves sent between steps so far, and their minutes (counted when sent)
    pub transports: i64,
    pub transport_minutes: f64,
}

#[derive(Clone, Debug)]
pub struct RunResult {
    pub lots: Vec<LotOut>,
    pub states: Vec<StateRow>,
    pub breaches: Vec<Breach>,
    pub tools: Vec<ToolOut>,
    pub groups: Vec<GroupOut>,
    pub release_log: Vec<ReleaseRow>,
    pub probes: Vec<Probe>,
    pub finished: i64,
    pub waiting: i64,
    pub wait_lot_minutes: f64,
    pub moves: i64,
    /// moves sent between steps, and their minutes (counted when sent)
    pub transports: i64,
    pub transport_minutes: f64,
    pub until: f64,
    /// decisions handed to the chooser (or that would have been, without one)
    pub decisions: u64,
    /// every started step, in start order (only with `record`)
    pub trace: Vec<Trace>,
    /// defect findings and the lots they held (docs/RL-DEFECTS.md); empty without a `defects` record
    pub holds: Vec<Hold>,
    /// the fleet's results (docs/FLEET.md); None without a `fleet` record
    pub fleet: Option<FleetOut>,
}

fn hx(x: f64) -> String {
    format!("{:016x}", x.to_bits())
}

impl RunResult {
    /// The canonical log, floats as the hex of their bits (`fabgym-log 1`).
    pub fn log_text(&self) -> String {
        let mut o = String::from("fabgym-log 1\n");
        for s in &self.states {
            let _ = writeln!(
                o,
                "state\t{}\t{}\t{}\t{}",
                s.tool,
                hx(s.time),
                s.state,
                if s.why.is_empty() { "-" } else { s.why }
            );
        }
        for l in &self.lots {
            let done = l.done.map(hx).unwrap_or_else(|| "-".into());
            let _ = writeln!(o, "lot\t{}\t{}\t{}", l.id, hx(l.release), done);
            for s in &l.steps {
                let _ = writeln!(
                    o,
                    "step\t{}\t{}\t{}\t{}\t{}",
                    s.step,
                    s.tool,
                    hx(s.arrive),
                    hx(s.start),
                    hx(s.end)
                );
            }
        }
        for b in &self.breaches {
            let _ = writeln!(o, "breach\t{}\t{}\t{}\t{}", b.lot, b.from, b.to, hx(b.waited));
        }
        for t in &self.tools {
            let _ = writeln!(
                o,
                "tool\t{}\t{}\t{}\t{}\t{}",
                t.name,
                hx(t.minutes[0]),
                hx(t.minutes[1]),
                hx(t.minutes[2]),
                hx(t.minutes[3])
            );
        }
        for g in &self.groups {
            let _ = writeln!(o, "group\t{}\t{}\t{}\t{}", g.name, hx(g.busy), hx(g.wait), g.visits);
        }
        for r in &self.release_log {
            let rel = r.released.map(hx).unwrap_or_else(|| "-".into());
            let wb = r.wip_before.map(|w| w.to_string()).unwrap_or_else(|| "-".into());
            let _ = writeln!(o, "release\t{}\t{}\t{}\t{}", r.id, hx(r.scheduled), rel, wb);
        }
        for p in &self.probes {
            let _ = writeln!(
                o,
                "probe\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                hx(p.t),
                p.finished,
                p.wip,
                p.moves,
                p.waiting,
                hx(p.wait_lot_minutes),
                hx(p.wip_lot_minutes)
            );
        }
        let _ = writeln!(o, "counters\t{}\t{}\t{}", self.finished, self.waiting, hx(self.wait_lot_minutes));
        let _ = writeln!(o, "until\t{}", hx(self.until));
        o
    }
}

// ------------------------------------------------------------------ internals

/// An f64 ordered as Python orders floats (no NaN reaches here).
#[derive(Clone, Copy, Debug, PartialEq)]
struct F(f64);
impl Eq for F {}
impl PartialOrd for F {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for F {
    fn cmp(&self, o: &Self) -> Ordering {
        self.0.partial_cmp(&o.0).expect("NaN in the simulator")
    }
}

enum Ev {
    Arrive(u32),
    Release(u32, i64),
    Unhold,
    Probe,
    Begin(u32, Vec<u32>, f64),
    End(u32, Vec<u32>),
    Down(u32, u8, f64),
    Pm(u32, u32, f64),
    Break(u32),
    Wake(u32),
    Up(u32),
    /// a lot listed with a later start, under its family's cap
    Admit(u32),
    UnholdFam(u32),
    /// a lot's defect hold may be over (docs/RL-DEFECTS.md)
    Unpark(u32),
    /// the fleet (docs/FLEET.md): a vehicle reaches the end of its stretch, tries again, or ends a hoist
    VehEnd(u32),
    VehTry(u32),
    Hoisted(u32),
}

/// A release or a listed lot held by its family's cap: (release, n, log row) or (lot, log row).
enum Held {
    Rel(u32, i64, usize),
    Lot(u32, usize),
}

struct HeapItem {
    t: f64,
    seq: u64,
    ev: Ev,
}
impl PartialEq for HeapItem {
    fn eq(&self, o: &Self) -> bool {
        self.seq == o.seq
    }
}
impl Eq for HeapItem {}
impl PartialOrd for HeapItem {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for HeapItem {
    // reversed: BinaryHeap is a max-heap
    fn cmp(&self, o: &Self) -> Ordering {
        F(o.t).cmp(&F(self.t)).then(o.seq.cmp(&self.seq))
    }
}

struct StepC {
    group: u32,
    per: Per,
    time: f64,
    spread: f64,
    batch: (f64, f64),
    interval: f64,
    batch_wait: Option<f64>,
    setup: u32, // 0: none
    sample: Option<f64>,
    rework: Option<(usize, f64)>,
    cqt: Option<(usize, f64)>,
}

struct Tool {
    name: String,
    group: u32,
    setup: u32,
    busy: bool,
    down: u8, // 0 none, else SCHEDULED or UNSCHEDULED (+1 to keep 0 free)
    pending: VecDeque<(u8, f64)>,
    state: u8,
    since: f64,
    minutes: [f64; 4],
    counts: Vec<f64>,
    /// on a defect hold until (docs/RL-DEFECTS.md)
    hold_until: f64,
    /// with a fleet: finished lots waiting at its ports, and since when every port has been full
    out: u32,
    full_since: f64,
}

struct Lot {
    id: String,
    route: u32,
    size: i64,
    priority: f64,
    release: f64,
    step: usize,
    rng: PyRandom,
    ended: Vec<(usize, f64)>,
    arrived: f64,
    wip: bool,
    done: Option<f64>,
    trail: Option<Vec<StepOut>>,
    entered: bool,
    inwip: bool,
    /// where the lot is, when the shop has a layout
    at: Place,
    /// where the lot is on the track, with a fleet
    node: usize,
    /// index into the family names
    fam: u32,
    /// defects (docs/RL-DEFECTS.md): when the lot last left a queue to start work, until when it is held,
    /// and whether it waits out of its queue now
    last_start: f64,
    held_until: f64,
    parked: bool,
}

type QKey = (F, F, u64);

struct Queue {
    key: u32,
    q: BTreeMap<QKey, u32>,
}

struct Waiting {
    key: (u32, usize),
    lots: Vec<(f64, u32)>,
}

struct Sim<'a, 'c> {
    shop: &'a Shop,
    seed: u64,
    full: bool,
    lo_t: f64,
    hi_t: f64,
    oht: Option<&'a Oht>,
    /// each group's place under the layout (`None`: a stocker)
    place_of: Vec<Option<Place>>,
    transports: i64,
    transport_minutes: f64,
    routes: Vec<Vec<StepC>>,
    rem_lot: Vec<Vec<f64>>,
    rem_piece: Vec<Vec<f64>>,
    setup_names: Vec<String>,
    group_setups: Vec<HashMap<String, f64>>,
    group_tools: Vec<Vec<u32>>,
    heap: BinaryHeap<HeapItem>,
    seq: u64,
    tools: Vec<Tool>,
    queues: Vec<Vec<Queue>>,
    waiting: Vec<Vec<Waiting>>,
    lots: Vec<Lot>,
    states: Vec<StateRow>,
    breaches: Vec<Breach>,
    busy: Vec<f64>,
    wait: Vec<f64>,
    visits: Vec<i64>,
    // running totals
    n: i64,
    last: f64,
    area: f64,
    done: i64,
    wip: i64,
    wlast: f64,
    warea: f64,
    moves: i64,
    now: f64,
    cap: Option<i64>,
    held: VecDeque<(u32, i64, usize)>,
    release_log: Vec<ReleaseRow>,
    probes: Vec<Probe>,
    chooser: Option<&'c mut dyn FnMut(&Decision) -> usize>,
    decisions: u64,
    trace: Vec<Trace>,
    // two families (docs/TWO-FAMILIES.md); with fam_on false nothing below changes a run
    fam_on: bool,
    fam_names: Vec<String>,
    route_fam: Vec<u32>,
    fam_cap: Vec<Option<i64>>,
    fam_wip: Vec<i64>,
    fam_held: Vec<VecDeque<Held>>,
    /// per tool, a bit per family it may process
    elig: Vec<u64>,
    /// per tool, the family whose lots it takes first
    reserved: Vec<Option<u32>>,
    // defects (docs/RL-DEFECTS.md); with `defects` None nothing below changes a run
    defects: Option<crate::shop::Defects>,
    /// per tool, the lots it finished lately: (lot, step, end)
    recent: Vec<VecDeque<(u32, usize, f64)>>,
    holds: Vec<Hold>,
    // the fleet (docs/FLEET.md); with `fl` None nothing below changes a run
    fl: Option<FleetState>,
    ports: u32,
    from_tool: Option<u32>,
    vchooser: Option<&'c mut dyn FnMut(&VehicleAsk) -> usize>,
}

/// A defect finding: the tool that did the step, when, the step, the lot found, and the lots held with it.
#[derive(Clone, Debug)]
pub struct Hold {
    pub tool: u32,
    pub t: f64,
    pub step: u32,
    pub lot: u32,
    pub lots: Vec<u32>,
}

enum Pick {
    Q(usize, QKey),
    B(usize),
}

impl<'a, 'c> Sim<'a, 'c> {
    fn at(&mut self, t: f64, ev: Ev) {
        let seq = self.seq;
        self.seq += 1;
        self.heap.push(HeapItem { t, seq, ev });
    }

    fn bump(&mut self, t: f64, d: i64) {
        self.area += self.n as f64 * (t - self.last);
        self.last = t;
        self.n += d;
    }

    fn wipd(&mut self, t: f64, d: i64) {
        self.warea += self.wip as f64 * (t - self.wlast);
        self.wlast = t;
        self.wip += d;
    }

    fn enter(&mut self, l: u32, t: f64) {
        if !self.lots[l as usize].inwip {
            self.lots[l as usize].inwip = true;
            self.wipd(t, 1);
            if self.fam_on {
                self.fam_wip[self.lots[l as usize].fam as usize] += 1;
            }
        }
    }

    fn leave(&mut self, l: u32, t: f64) {
        self.done += 1;
        if self.lots[l as usize].inwip {
            self.lots[l as usize].inwip = false;
            self.wipd(t, -1);
            if self.fam_on {
                let f = self.lots[l as usize].fam as usize;
                self.fam_wip[f] -= 1;
                if self.fam_cap[f].is_some() && !self.fam_held[f].is_empty() {
                    self.at(t, Ev::UnholdFam(f as u32));
                }
            }
        }
        if self.cap.is_some() && !self.held.is_empty() {
            self.at(t, Ev::Unhold);
        }
    }

    fn step_of(&self, l: u32) -> Option<&StepC> {
        let lot = &self.lots[l as usize];
        self.routes[lot.route as usize].get(lot.step)
    }

    fn set_state(&mut self, ti: u32, t: f64, state: u8, why: &'static str) {
        let tool = &mut self.tools[ti as usize];
        if tool.state == state {
            return;
        }
        tool.minutes[tool.state as usize] += t - tool.since;
        tool.state = state;
        tool.since = t;
        if self.full {
            self.states.push(StateRow {
                tool: tool.name.clone(),
                tool_index: ti,
                time: t,
                state: STATES[state as usize],
                why,
            });
        }
    }

    fn enqueue(&mut self, l: u32, t: f64) {
        self.bump(t, 1);
        let (g, per, setup, bw, key) = {
            let st = self.step_of(l).expect("enqueue past the route's end");
            let lot = &self.lots[l as usize];
            (st.group, st.per, st.setup, st.batch_wait, (lot.route, lot.step))
        };
        self.lots[l as usize].arrived = t;
        if self.lots[l as usize].held_until > t {
            self.lots[l as usize].parked = true;
            let until = self.lots[l as usize].held_until;
            self.at(until, Ev::Unpark(l));
            return;
        }
        self.queue_in(l, g, per, setup, bw, key, t);
        self.dispatch(g, t);
    }

    /// put a lot that has arrived (at `lots[l].arrived`) into its group's queue or batch list
    #[allow(clippy::too_many_arguments)]
    fn queue_in(&mut self, l: u32, g: u32, per: Per, setup: u32, bw: Option<f64>, key: (u32, usize), t: f64) {
        let arrived = self.lots[l as usize].arrived;
        if per == Per::Batch {
            let ws = &mut self.waiting[g as usize];
            match ws.iter_mut().find(|w| w.key == key) {
                // in arrival order (a lot back from a hold keeps its place)
                Some(w) => {
                    let at = w.lots.iter().position(|(a, _)| *a > arrived).unwrap_or(w.lots.len());
                    w.lots.insert(at, (arrived, l));
                }
                None => ws.push(Waiting { key, lots: vec![(arrived, l)] }),
            }
            let wait = bw.or(self.shop.groups[g as usize].batch_wait);
            if let Some(w) = wait {
                self.at((arrived + w).max(t), Ev::Wake(g));
            }
        } else {
            let seq = self.seq;
            self.seq += 1;
            let k = (F(-self.lots[l as usize].priority), F(arrived), seq);
            let qs = &mut self.queues[g as usize];
            match qs.iter_mut().find(|q| q.key == setup) {
                Some(q) => {
                    q.q.insert(k, l);
                }
                None => {
                    let mut q = BTreeMap::new();
                    q.insert(k, l);
                    qs.push(Queue { key: setup, q });
                }
            }
        }
    }

    /// hold lot l until `until`: out of its queue now if it waits in one, else when it arrives
    fn hold_lot(&mut self, l: u32, until: f64) {
        let lot = &mut self.lots[l as usize];
        if until <= lot.held_until {
            return;
        }
        lot.held_until = until;
        if lot.parked {
            self.at(until, Ev::Unpark(l));
            return;
        }
        let Some(st) = self.step_of(l) else { return };
        let g = st.group as usize;
        let mut found = false;
        for q in &mut self.queues[g] {
            if let Some(k) = q.q.iter().find(|(_, &x)| x == l).map(|(k, _)| *k) {
                q.q.remove(&k);
                found = true;
                break;
            }
        }
        if !found {
            for w in &mut self.waiting[g] {
                if let Some(i) = w.lots.iter().position(|(_, x)| *x == l) {
                    w.lots.remove(i);
                    found = true;
                    break;
                }
            }
        }
        if found {
            self.lots[l as usize].parked = true;
            self.at(until, Ev::Unpark(l));
        }
    }

    fn unpark(&mut self, l: u32, t: f64) {
        let lot = &self.lots[l as usize];
        if !lot.parked || lot.held_until > t {
            return;
        }
        self.lots[l as usize].parked = false;
        let (g, per, setup, bw, key) = {
            let st = self.step_of(l).expect("a parked lot has a step");
            let lot = &self.lots[l as usize];
            (st.group, st.per, st.setup, st.batch_wait, (lot.route, lot.step))
        };
        self.queue_in(l, g, per, setup, bw, key, t);
        self.dispatch(g, t);
    }

    /// Ready batches of group g: (index into waiting, oldest arrival).
    fn ready_batches(&self, g: u32) -> Vec<(usize, f64)> {
        let mut out = vec![];
        for (wi, w) in self.waiting[g as usize].iter().enumerate() {
            if w.lots.is_empty() {
                continue;
            }
            let st = &self.routes[w.key.0 as usize][w.key.1];
            let (lo, hi) = st.batch;
            let pieces: i64 = w.lots.iter().map(|(_, x)| self.lots[*x as usize].size).sum();
            let size = self.lots[w.lots[0].1 as usize].size;
            let oldest = w.lots[0].0;
            let p = pieces as f64;
            let mut ready = p >= lo && p >= hi - size as f64;
            let waited = st.batch_wait.or(self.shop.groups[g as usize].batch_wait);
            if !ready {
                if let Some(wt) = waited {
                    if self.now - oldest >= wt && p >= lo {
                        ready = true;
                    }
                }
            }
            if ready {
                out.push((wi, oldest));
            }
        }
        out
    }

    /// May tool ti process lot l (its family qualified)?
    fn ok(&self, ti: u32, l: u32) -> bool {
        !self.fam_on || (self.elig[ti as usize] >> self.lots[l as usize].fam) & 1 == 1
    }

    /// The family a waiting batch's lots belong to (one route, so one family).
    fn batch_fam(&self, g: u32, wi: usize) -> u32 {
        self.route_fam[self.waiting[g as usize][wi].key.0 as usize]
    }

    fn pick(&self, g: u32, ti: u32) -> Option<Pick> {
        if self.fam_on {
            if let Some(rf) = self.reserved[ti as usize] {
                if let Some(p) = self.pick_among(g, ti, Some(rf)) {
                    return Some(p);
                }
            }
            return self.pick_among(g, ti, None);
        }
        let tool_setup = self.tools[ti as usize].setup;
        let mut best: Option<((F, u8, F), Pick)> = None;
        for (qi, q) in self.queues[g as usize].iter().enumerate() {
            let Some((k, _)) = q.q.first_key_value() else { continue };
            let change = if q.key == 0 || q.key == tool_setup { 0 } else { 1 };
            let cand = (k.0, change, k.1);
            if best.as_ref().is_none_or(|b| cand < b.0) {
                best = Some((cand, Pick::Q(qi, *k)));
            }
        }
        for (wi, oldest) in self.ready_batches(g) {
            let w = &self.waiting[g as usize][wi];
            let pr = w
                .lots
                .iter()
                .map(|(_, x)| -self.lots[*x as usize].priority)
                .fold(f64::INFINITY, |a, b| if b < a { b } else { a });
            let cand = (F(pr), 0, F(oldest));
            if best.as_ref().is_none_or(|b| cand < b.0) {
                best = Some((cand, Pick::B(wi)));
            }
        }
        best.map(|b| b.1)
    }

    /// Today's rule over the lots tool ti may process, and only family `only` when given.
    fn pick_among(&self, g: u32, ti: u32, only: Option<u32>) -> Option<Pick> {
        let tool_setup = self.tools[ti as usize].setup;
        let mut best: Option<((F, u8, F), Pick)> = None;
        for (qi, q) in self.queues[g as usize].iter().enumerate() {
            let first = q.q.iter().find(|(_, &l)| self.ok(ti, l) && only.is_none_or(|f| self.lots[l as usize].fam == f));
            let Some((k, _)) = first else { continue };
            let change = if q.key == 0 || q.key == tool_setup { 0 } else { 1 };
            let cand = (k.0, change, k.1);
            if best.as_ref().is_none_or(|b| cand < b.0) {
                best = Some((cand, Pick::Q(qi, *k)));
            }
        }
        for (wi, oldest) in self.ready_batches(g) {
            let f = self.batch_fam(g, wi);
            if (self.elig[ti as usize] >> f) & 1 == 0 || only.is_some_and(|o| o != f) {
                continue;
            }
            let w = &self.waiting[g as usize][wi];
            let pr = w
                .lots
                .iter()
                .map(|(_, x)| -self.lots[*x as usize].priority)
                .fold(f64::INFINITY, |a, b| if b < a { b } else { a });
            let cand = (F(pr), 0, F(oldest));
            if best.as_ref().is_none_or(|b| cand < b.0) {
                best = Some((cand, Pick::B(wi)));
            }
        }
        best.map(|b| b.1)
    }

    fn batch_take(&self, g: u32, wi: usize) -> Vec<u32> {
        let w = &self.waiting[g as usize][wi];
        let hi = self.routes[w.key.0 as usize][w.key.1].batch.1;
        let mut order: Vec<(f64, u32)> = w.lots.clone();
        order.sort_by(|a, b| {
            F(-self.lots[a.1 as usize].priority)
                .cmp(&F(-self.lots[b.1 as usize].priority))
                .then(F(a.0).cmp(&F(b.0)))
        });
        let mut taken = vec![];
        let mut pieces = 0i64;
        for (_, l) in order {
            let s = self.lots[l as usize].size;
            if (pieces + s) as f64 > hi {
                break;
            }
            taken.push(l);
            pieces += s;
        }
        taken
    }

    fn cqts(&self, l: u32) -> Vec<(usize, usize, f64, f64)> {
        let lot = &self.lots[l as usize];
        let steps = &self.routes[lot.route as usize];
        let mut out = vec![];
        for &(i, t_end) in &lot.ended {
            if let Some((to, limit)) = steps[i].cqt {
                out.push((i, to, limit, t_end));
            }
        }
        out
    }

    fn cqt_slack(&self, l: u32, t: f64) -> Option<f64> {
        let step = self.lots[l as usize].step;
        let mut best: Option<f64> = None;
        for (_, to, limit, since) in self.cqts(l) {
            if to == step {
                let s = limit - (t - since);
                if best.is_none_or(|b| s < b) {
                    best = Some(s);
                }
            }
        }
        best
    }

    fn candidate(&self, kind: &'static str, lots: &[u32], ti: u32, t: f64, oldest: f64) -> Candidate {
        let l0 = lots[0];
        let lot = &self.lots[l0 as usize];
        let st = self.step_of(l0).unwrap();
        let pieces: i64 = lots.iter().map(|x| self.lots[*x as usize].size).sum();
        let proc = st.time * if st.per == Per::Piece { pieces as f64 } else { 1.0 };
        let mut prio = f64::NEG_INFINITY;
        for x in lots {
            let p = self.lots[*x as usize].priority;
            if p > prio {
                prio = p;
            }
        }
        let mut slack: Option<f64> = None;
        for x in lots {
            if let Some(v) = self.cqt_slack(*x, t) {
                if slack.is_none_or(|b| v < b) {
                    slack = Some(v);
                }
            }
        }
        let r = lot.route as usize;
        Candidate {
            kind,
            lots: lots.iter().map(|x| self.lots[*x as usize].id.clone()).collect(),
            priority: prio,
            size_wafers: pieces,
            route: self.shop.routes[r].name.clone(),
            step: lot.step,
            steps_left: self.routes[r].len() - lot.step,
            waited_minutes: t - oldest,
            setup_change: kind == "lot" && st.setup != 0 && st.setup != self.tools[ti as usize].setup,
            proc_minutes: proc,
            work_left_minutes: self.rem_lot[r][lot.step] + lot.size as f64 * self.rem_piece[r][lot.step],
            release: lot.release,
            cqt_slack_minutes: slack,
            family: self.fam_names[lot.fam as usize].clone(),
        }
    }

    /// Every candidate the free tool could take, with handles, and the rule's default index.
    fn decision(&self, g: u32, ti: u32, t: f64) -> Option<(Decision, Vec<(bool, usize, Option<QKey>)>)> {
        let mut cands = vec![];
        let mut handles = vec![];
        // with families on: only lots the tool may process, and only its reserved family's while any wait
        let only: Option<u32> = if self.fam_on {
            self.reserved[ti as usize].filter(|&rf| {
                self.queues[g as usize].iter().any(|q| q.q.values().any(|&l| self.ok(ti, l) && self.lots[l as usize].fam == rf))
                    || self.ready_batches(g).iter().any(|&(wi, _)| self.batch_fam(g, wi) == rf)
            })
        } else {
            None
        };
        for (qi, q) in self.queues[g as usize].iter().enumerate() {
            for (k, &l) in q.q.iter() {
                if self.fam_on && (!self.ok(ti, l) || only.is_some_and(|f| self.lots[l as usize].fam != f)) {
                    continue;
                }
                let a = self.lots[l as usize].arrived;
                cands.push(self.candidate("lot", &[l], ti, t, a));
                handles.push((true, qi, Some(*k)));
            }
        }
        for (wi, oldest) in self.ready_batches(g) {
            if self.fam_on {
                let f = self.batch_fam(g, wi);
                if (self.elig[ti as usize] >> f) & 1 == 0 || only.is_some_and(|o| o != f) {
                    continue;
                }
            }
            let taken = self.batch_take(g, wi);
            cands.push(self.candidate("batch", &taken, ti, t, oldest));
            handles.push((false, wi, None));
        }
        if cands.is_empty() {
            return None;
        }
        let default = match self.pick(g, ti).unwrap() {
            Pick::Q(qi, k) => handles.iter().position(|h| h.0 && h.1 == qi && h.2 == Some(k)).unwrap(),
            Pick::B(wi) => handles.iter().position(|h| !h.0 && h.1 == wi).unwrap(),
        };
        let mut gt = GroupTools::default();
        for &x in &self.group_tools[g as usize] {
            let tl = &self.tools[x as usize];
            if tl.down != 0 {
                gt.down += 1;
                if tl.hold_until > t {
                    gt.held += 1;
                }
            } else if tl.busy {
                gt.working += 1;
            } else {
                gt.idle += 1;
            }
        }
        let tool = &self.tools[ti as usize];
        Some((
            Decision {
                t,
                tool_group: self.shop.groups[g as usize].name.clone(),
                tool: tool.name.clone(),
                tool_setup: if tool.setup == 0 { None } else { Some(self.setup_names[tool.setup as usize].clone()) },
                group_tools: gt,
                totals: Totals {
                    finished: self.done,
                    waiting: self.n,
                    wait_lot_minutes: self.area + self.n as f64 * (t - self.last),
                },
                candidates: cands,
                default,
            },
            handles,
        ))
    }

    fn dispatch(&mut self, g: u32, t: f64) {
        self.now = t;
        let ntools = self.group_tools[g as usize].len();
        for k in 0..ntools {
            let ti = self.group_tools[g as usize][k];
            {
                let tool = &self.tools[ti as usize];
                if tool.busy || tool.down != 0 || (self.ports > 0 && tool.out >= self.ports) {
                    continue;
                }
            }
            if let Some((kind, minutes)) = self.tools[ti as usize].pending.pop_front() {
                self.go_down(ti, t, kind, minutes);
                continue;
            }
            let choice;
            if self.chooser.is_some() {
                let Some((dec, handles)) = self.decision(g, ti, t) else { continue };
                self.decisions += 1;
                let mut k = (self.chooser.as_mut().unwrap())(&dec);
                if k >= handles.len() {
                    k = dec.default;
                }
                let h = handles[k];
                if h.0 {
                    let l = self.queues[g as usize][h.1].q.remove(&h.2.unwrap()).unwrap();
                    self.start_work(ti, t, vec![l]);
                    continue;
                }
                choice = Pick::B(h.1);
            } else {
                match self.pick(g, ti) {
                    None => continue,
                    Some(p) => choice = p,
                }
                self.decisions += 1;
            }
            match choice {
                Pick::Q(qi, k) => {
                    let l = self.queues[g as usize][qi].q.remove(&k).unwrap();
                    self.start_work(ti, t, vec![l]);
                }
                Pick::B(wi) => {
                    let key = self.waiting[g as usize][wi].key;
                    let hi = self.routes[key.0 as usize][key.1].batch.1;
                    let mut w = std::mem::take(&mut self.waiting[g as usize][wi].lots);
                    {
                        let lots = &self.lots;
                        w.sort_by(|a, b| {
                            F(-lots[a.1 as usize].priority)
                                .cmp(&F(-lots[b.1 as usize].priority))
                                .then(F(a.0).cmp(&F(b.0)))
                        });
                    }
                    let mut taken = vec![];
                    let mut pieces = 0i64;
                    let mut n = 0;
                    while n < w.len() && ((pieces + self.lots[w[n].1 as usize].size) as f64) <= hi {
                        taken.push(w[n].1);
                        pieces += self.lots[w[n].1 as usize].size;
                        n += 1;
                    }
                    w.drain(..n);
                    self.waiting[g as usize][wi].lots = w;
                    self.start_work(ti, t, taken);
                }
            }
        }
    }

    fn setup_cost(&self, ti: u32, want: u32) -> f64 {
        let tool = &self.tools[ti as usize];
        if want == 0 || tool.setup == want {
            return 0.0;
        }
        let s = &self.group_setups[tool.group as usize];
        let wname = &self.setup_names[want as usize];
        let cur = if tool.setup == 0 { "" } else { self.setup_names[tool.setup as usize].as_str() };
        s.get(&format!("{cur}>{wname}"))
            .or_else(|| s.get(&format!(">{wname}")))
            .copied()
            .unwrap_or(0.0)
    }

    fn start_work(&mut self, ti: u32, t: f64, batch: Vec<u32>) {
        self.bump(t, -(batch.len() as i64));
        self.moves += batch.len() as i64;
        let l0 = batch[0];
        let (g, want, per, time, spread, interval) = {
            let st = self.step_of(l0).unwrap();
            (st.group, st.setup, st.per, st.time, st.spread, st.interval)
        };
        let s_min = self.setup_cost(ti, want);
        self.tools[ti as usize].busy = true;
        if s_min > 0.0 {
            self.set_state(ti, t, SCHEDULED, "setup");
        }
        if want != 0 {
            self.tools[ti as usize].setup = want;
        }
        let pieces: i64 = batch.iter().map(|x| self.lots[*x as usize].size).sum();
        // processing time: one draw from the first lot's stream
        let x = if spread != 0.0 {
            self.lots[l0 as usize].rng.uniform(time - spread, time + spread)
        } else {
            time
        };
        let grp = &self.shop.groups[g as usize];
        let extra = grp.load + grp.unload;
        let dur = if per == Per::Piece {
            (if interval != 0.0 { x + (pieces - 1) as f64 * interval } else { x * pieces as f64 }) + extra
        } else {
            x + extra
        };
        let begin = t + s_min;
        self.at(begin, Ev::Begin(ti, batch.clone(), dur));
        for &l in &batch {
            self.lots[l as usize].last_start = t;
            let waited = t - self.lots[l as usize].arrived;
            self.wait[g as usize] += waited;
            self.visits[g as usize] += 1;
            let step = self.lots[l as usize].step;
            for (from, to, limit, since) in self.cqts(l) {
                if to == step {
                    let gap = begin - since;
                    if gap > limit {
                        self.breaches.push(Breach {
                            t: begin,
                            lot: self.lots[l as usize].id.clone(),
                            from,
                            to,
                            limit,
                            waited: gap,
                        });
                    }
                }
            }
        }
    }

    fn finish(&mut self, ti: u32, t: f64, batch: Vec<u32>) {
        self.tools[ti as usize].busy = false;
        let g = self.tools[ti as usize].group;
        let done: i64 = batch.iter().map(|x| self.lots[*x as usize].size).sum();
        let npp = self.shop.groups[g as usize].pm_pieces.len();
        for k in 0..npp {
            let pm = &self.shop.groups[g as usize].pm_pieces[k];
            let tool = &mut self.tools[ti as usize];
            tool.counts[k] += done as f64;
            if tool.counts[k] >= pm.every {
                tool.counts[k] = 0.0;
                let mut r = PyRandom::from_str_seed(&format!("{}/pmc/{}/{}/{}", self.seed, tool.name, k, t as i64));
                let m = r.uniform(pm.lo, pm.hi);
                tool.pending.push_back((SCHEDULED, m));
            }
        }
        self.set_state(ti, t, STANDBY, "");
        let mut finding: Option<(u32, usize)> = None;
        let mut finished: Vec<(u32, usize)> = vec![];
        for &l in &batch {
            let (rework, step) = {
                let st = self.step_of(l).unwrap();
                (st.rework, self.lots[l as usize].step)
            };
            let has_cqt = self.routes[self.lots[l as usize].route as usize][step].cqt.is_some();
            let lot = &mut self.lots[l as usize];
            // only steps that start a queue-time limit are ever read back, so only they are kept
            // (in first-ended order, as the reference keeps every step)
            if has_cqt {
                match lot.ended.iter_mut().find(|e| e.0 == step) {
                    Some(e) => e.1 = t,
                    None => lot.ended.push((step, t)),
                }
            }
            match rework {
                Some((to, p)) if lot.rng.random() < p => {
                    lot.step = to;
                    if finding.is_none() {
                        finding = Some((l, step));
                    }
                }
                _ => lot.step += 1,
            }
            finished.push((l, step));
            self.from_tool = Some(ti);
            self.move_on(l, t);
            self.from_tool = None;
        }
        if let Some(d) = self.defects {
            if let Some((found, step)) = finding {
                self.find(ti, t, found, step, d);
            }
            let recent = &mut self.recent[ti as usize];
            for x in finished {
                recent.push_back((x.0, x.1, t));
            }
            while recent.front().is_some_and(|e| e.2 < t - d.lookback_minutes) {
                recent.pop_front();
            }
            if finding.is_some() {
                self.go_down_why(ti, t, UNSCHEDULED, d.hold_tool_minutes, "hold");
                self.dispatch(self.tools[ti as usize].group, t);
                return;
            }
        }
        if let Some((kind, m)) = self.tools[ti as usize].pending.pop_front() {
            self.go_down(ti, t, kind, m);
        }
        self.dispatch(g, t);
    }

    fn move_on(&mut self, l: u32, t: f64) {
        loop {
            let sample = match self.step_of(l) {
                None => {
                    self.lots[l as usize].done = Some(t);
                    self.leave(l, t);
                    return;
                }
                Some(st) => st.sample,
            };
            if let Some(p) = sample {
                if self.lots[l as usize].rng.random() >= p {
                    self.lots[l as usize].step += 1;
                    continue;
                }
            }
            break;
        }
        if self.fl.is_some() {
            self.fleet_ask(l, t);
            return;
        }
        let delay = match self.oht {
            None => {
                if self.hi_t > 0.0 {
                    self.lots[l as usize].rng.uniform(self.lo_t, self.hi_t)
                } else {
                    0.0
                }
            }
            Some(o) => {
                let from = self.lots[l as usize].at;
                let g = self.routes[self.lots[l as usize].route as usize][self.lots[l as usize].step].group as usize;
                // a stocker holds the lot at the spine end of the bay it came from
                let to = self.place_of[g].unwrap_or(Place { bay: usize::MAX, y: 0.0, ..from });
                let base = o.minutes(o.distance(&from, &to));
                self.lots[l as usize].at = to;
                self.lots[l as usize].rng.uniform(base - o.jitter, base + o.jitter).max(0.0)
            }
        };
        self.transports += 1;
        self.transport_minutes += delay;
        self.at(t + delay, Ev::Arrive(l));
    }

    fn go_down(&mut self, ti: u32, t: f64, kind: u8, minutes: f64) {
        self.go_down_why(ti, t, kind, minutes, "");
    }

    fn go_down_why(&mut self, ti: u32, t: f64, kind: u8, minutes: f64, why: &'static str) {
        if why == "hold" {
            self.tools[ti as usize].hold_until = t + minutes;
        }
        self.tools[ti as usize].down = kind;
        self.set_state(ti, t, kind, why);
        self.at(t + minutes, Ev::Up(ti));
    }

    /// a finding against tool ti (docs/RL-DEFECTS.md): hold the lots it finished at this step in the
    /// lookback that have not started another step since
    fn find(&mut self, ti: u32, t: f64, found: u32, step: usize, d: crate::shop::Defects) {
        let mut lots: Vec<u32> = vec![];
        for &(l, s, end) in &self.recent[ti as usize] {
            let lot = &self.lots[l as usize];
            if s == step && l != found && end >= t - d.lookback_minutes && end < t && lot.last_start <= end && lot.done.is_none() && !lots.contains(&l) {
                lots.push(l);
            }
        }
        for &l in &lots {
            self.hold_lot(l, t + d.hold_lot_minutes);
        }
        self.holds.push(Hold { tool: ti, t, step: step as u32, lot: found, lots });
    }

    fn down_due(&mut self, ti: u32, t: f64, kind: u8, minutes: f64) {
        let tool = &mut self.tools[ti as usize];
        if tool.busy || tool.down != 0 {
            tool.pending.push_back((kind, minutes));
        } else {
            self.go_down(ti, t, kind, minutes);
        }
    }

    fn rid(&self, k: u32, n: i64) -> String {
        format!("{}.{}", self.shop.releases[k as usize].prefix, n)
    }

    fn new_lot(&mut self, id: String, route: &str, size: i64, priority: f64, start: f64, step: usize, wip: bool) -> u32 {
        let r = self.shop.routes.iter().position(|x| x.name == route).unwrap_or_else(|| panic!("unknown route {route}"));
        let rng = PyRandom::from_str_seed(&format!("{}/lot/{}", self.seed, id));
        let at = match self.oht {
            None => Place { phase: 0, side: 0, bay: 0, x: 0.0, y: 0.0 },
            Some(o) => self.routes[r].get(step).and_then(|st| self.place_of[st.group as usize]).unwrap_or(o.start),
        };
        // with a fleet: at one of its first group's ports (spread over the tools by lot number), else a stocker spur
        let n_lot = self.lots.len();
        let node = match &self.fl {
            None => 0,
            Some(f) => match self.routes[r].get(step).map(|st| st.group as usize) {
                Some(g) if !f.group_ports[g].is_empty() => f.group_ports[g][n_lot % f.group_ports[g].len()],
                Some(g) if self.place_of[g].is_none() => f.track.node_of(&Place { bay: usize::MAX, y: 0.0, ..at }),
                _ => f.track.node_of(&at),
            },
        };
        self.lots.push(Lot {
            id,
            route: r as u32,
            size,
            priority,
            release: start,
            step,
            rng,
            ended: vec![],
            arrived: 0.0,
            wip,
            done: None,
            trail: None,
            entered: false,
            inwip: false,
            at,
            node,
            fam: self.route_fam[r],
            last_start: f64::NEG_INFINITY,
            held_until: f64::NEG_INFINITY,
            parked: false,
        });
        (self.lots.len() - 1) as u32
    }

    /// A lot reaching the fab (or its next step after a listed start): the reference engine's arrival.
    fn arrive(&mut self, l: u32, t: f64) {
        if self.full && self.lots[l as usize].trail.is_none() {
            self.lots[l as usize].trail = Some(vec![]);
        }
        self.enter(l, t);
        let first = !self.lots[l as usize].entered;
        self.lots[l as usize].entered = true;
        let st0 = self.step_of(l).map(|s| s.sample);
        let p0 = match st0 {
            Some(s) if first => s,
            _ => None,
        };
        if let Some(p) = p0 {
            if self.lots[l as usize].rng.random() >= p {
                self.lots[l as usize].step += 1;
                self.move_on(l, t);
                return;
            }
        }
        if st0.is_none() {
            self.lots[l as usize].done = Some(t);
            self.leave(l, t);
            return;
        }
        self.enqueue(l, t);
    }

    /// Is there room for one more lot of family f under its cap?
    fn fam_room(&self, f: usize) -> bool {
        match self.fam_cap[f] {
            None => true,
            Some(c) => self.fam_held[f].is_empty() && self.fam_wip[f] < c,
        }
    }

    fn release(&mut self, k: u32, n: i64, t: f64) {
        let shop = self.shop;
        let rel = &shop.releases[k as usize];
        let id = self.rid(k, n);
        let l = self.new_lot(id, &rel.route, rel.size, rel.priority, t, 0, false);
        self.enter(l, t);
        self.enqueue(l, t);
    }
}

// ---------------------------------------------------------------------------- the fleet (docs/FLEET.md)

impl<'a, 'c> Sim<'a, 'c> {
    /// A lot's move becomes a request: it waits at its stop until a vehicle comes.
    fn fleet_ask(&mut self, l: u32, t: f64) {
        let g = self.routes[self.lots[l as usize].route as usize][self.lots[l as usize].step].group as usize;
        let from_place = self.lots[l as usize].at;
        // a stocker holds the lot at the spine end of the bay it came from, as without a fleet
        let to_place = self.place_of[g].unwrap_or(Place { bay: usize::MAX, y: 0.0, ..from_place });
        self.lots[l as usize].at = to_place;
        let tool = self.from_tool;
        let fl = self.fl.as_ref().unwrap();
        // from the port of the tool that finished it, when tools have ports; else where the lot stands
        let from = match tool {
            Some(ti) => {
                let tl = &self.tools[ti as usize];
                let k = self.group_tools[tl.group as usize].iter().position(|&x| x == ti).unwrap();
                fl.group_ports[tl.group as usize].get(k).copied().unwrap_or(self.lots[l as usize].node)
            }
            None => self.lots[l as usize].node,
        };
        // to the port of the group's tool with the fewest deliveries on their way (ties to the first tool)
        let to = match fl.group_ports[g].iter().min_by_key(|&&n| fl.port_load[n]) {
            Some(&n) => n,
            None => fl.stop_of_group[g].unwrap_or_else(|| fl.track.node_of(&to_place)),
        };
        if let Some(ti) = tool {
            self.tool_out(ti, true, t);
        }
        let fl = self.fl.as_mut().unwrap();
        fl.port_load[to] += 1;
        fl.out.asked += 1;
        fl.pending.push_back(Job { lot: l, from, to, asked: t, tool });
        self.fleet_assign(t);
    }

    fn tool_out(&mut self, ti: u32, up: bool, t: f64) {
        let ports = self.ports;
        let tool = &mut self.tools[ti as usize];
        if up {
            tool.out += 1;
            if tool.out == ports {
                tool.full_since = t;
            }
        } else {
            if tool.out == ports {
                self.fl.as_mut().unwrap().out.blocked_min += t - tool.full_since;
            }
            tool.out -= 1;
        }
    }

    /// Requests are served oldest first, each by one idle vehicle the controller picks.
    fn fleet_assign(&mut self, t: f64) {
        loop {
            let fl = self.fl.as_ref().unwrap();
            let Some(job) = fl.pending.front() else { break };
            let idle = fl.idle_for(job.from);
            if idle.is_empty() {
                break;
            }
            let default = fl.default_pick(&idle);
            let mut refused = false;
            let k = match self.vchooser.as_mut() {
                Some(ch) => {
                    let ask = VehicleAsk { lot: job.lot, from: job.from, to: job.to, asked: job.asked, now: t, idle: idle.clone() };
                    let k = ch(&ask);
                    if k < idle.len() {
                        k
                    } else {
                        refused = true;
                        default
                    }
                }
                None => default,
            };
            let v = idle[k].vehicle;
            let fl = self.fl.as_mut().unwrap();
            fl.out.picks += 1;
            if refused {
                fl.out.refused += 1;
            }
            let job = fl.pending.pop_front().unwrap();
            let start = match fl.veh[v as usize].pos {
                Pos::Parked(n) | Pos::Node(n) => n,
                Pos::Edge(e) => fl.track.edges()[e].to,
            };
            let free = fl.track.dist(start, job.from) / fl.speed;
            let veh = &mut fl.veh[v as usize];
            veh.mode = Mode::ToPick;
            veh.target = job.from;
            veh.job = Some(job);
            veh.busy_since = t;
            veh.leg_start = t;
            veh.leg_free = free;
            self.fleet_go(v, t);
        }
    }

    /// Move a vehicle on as far as the track lets it now; it is woken again when what holds it clears.
    fn fleet_go(&mut self, v: u32, t: f64) {
        let vi = v as usize;
        let fl = self.fl.as_mut().unwrap();
        let mode = fl.veh[vi].mode;
        if matches!(mode, Mode::Idle | Mode::HoistUp | Mode::HoistDown) {
            return;
        }
        let target = fl.veh[vi].target;
        let n = match fl.veh[vi].pos {
            Pos::Parked(n) => {
                if fl.node_held[n].is_some() {
                    if !fl.node_wait[n].contains(&v) {
                        fl.node_wait[n].push(v);
                    }
                    return;
                }
                fl.node_held[n] = Some(v);
                fl.veh[vi].pos = Pos::Node(n);
                n
            }
            Pos::Node(n) => n,
            Pos::Edge(e) => {
                if !fl.veh[vi].at_end || fl.edge_q[e].front() != Some(&v) {
                    return;
                }
                let n = fl.track.edges()[e].to;
                if fl.node_held[n].is_some_and(|h| h != v) {
                    if !fl.node_wait[n].contains(&v) {
                        fl.node_wait[n].push(v);
                    }
                    return;
                }
                if n != target {
                    let (want, go) = fl.way(n, target, t);
                    let Some(e2) = go else {
                        self.fleet_wait(v, n, want, t);
                        return;
                    };
                    if e2 != want {
                        fl.out.detours += 1;
                    }
                    self.fleet_leave(v, e, t);
                    self.fleet_enter(v, e2, t);
                    return;
                }
                self.fleet_leave(v, e, t);
                let fl = self.fl.as_mut().unwrap();
                fl.node_held[n] = Some(v);
                fl.veh[vi].pos = Pos::Node(n);
                n
            }
        };
        if n == target {
            self.fleet_hoist(v, n, t);
            return;
        }
        let fl = self.fl.as_mut().unwrap();
        let (want, go) = fl.way(n, target, t);
        let Some(e2) = go else {
            self.fleet_wait(v, n, want, t);
            return;
        };
        if e2 != want {
            fl.out.detours += 1;
        }
        self.fleet_release(n, t);
        self.fleet_enter(v, e2, t);
    }

    /// Wait at node n: for the gap behind the vehicle ahead on `e`, or, when every way out is full, for any of them
    /// to free.
    fn fleet_wait(&mut self, v: u32, n: usize, e: usize, t: f64) {
        let fl = self.fl.as_mut().unwrap();
        if fl.edge_q[e].len() >= fl.cap[e] {
            let outs: Vec<usize> = fl.track.out_of(n).to_vec();
            for e3 in outs {
                if !fl.edge_wait[e3].contains(&v) {
                    fl.edge_wait[e3].push(v);
                }
            }
            // a way out held only by its gap frees by itself
            let soonest = fl.track.out_of(n).iter().filter(|&&e3| fl.edge_q[e3].len() < fl.cap[e3]).map(|&e3| fl.last_in[e3] + fl.headway).fold(f64::INFINITY, f64::min);
            if soonest.is_finite() {
                self.at(soonest.max(t), Ev::VehTry(v));
            }
        } else {
            let at = fl.last_in[e] + fl.headway;
            self.at(at.max(t), Ev::VehTry(v));
        }
    }

    fn fleet_enter(&mut self, v: u32, e: usize, t: f64) {
        let full = self.full;
        let fl = self.fl.as_mut().unwrap();
        let len = fl.track.edges()[e].len;
        let end = (t + len / fl.speed).max(fl.last_end[e] + fl.headway);
        fl.last_end[e] = end;
        fl.last_in[e] = t;
        fl.edge_q[e].push_back(v);
        let loaded = fl.veh[v as usize].mode == Mode::Loaded;
        if loaded {
            fl.out.loaded_m += len;
        } else {
            fl.out.empty_m += len;
        }
        let veh = &mut fl.veh[v as usize];
        veh.pos = Pos::Edge(e);
        veh.at_end = false;
        if full {
            veh.entry = fl.out.entries.len();
            fl.out.entries.push(Entry { vehicle: v, edge: e, t_in: t, t_out: f64::INFINITY, loaded });
        }
        self.at(end, Ev::VehEnd(v));
    }

    fn fleet_leave(&mut self, v: u32, e: usize, t: f64) {
        let full = self.full;
        let fl = self.fl.as_mut().unwrap();
        let first = fl.edge_q[e].pop_front();
        debug_assert_eq!(first, Some(v), "vehicles leave a stretch in the order they entered");
        if full {
            let i = fl.veh[v as usize].entry;
            fl.out.entries[i].t_out = t;
        }
        let mut wake: Vec<u32> = std::mem::take(&mut fl.edge_wait[e]);
        if let Some(&h) = fl.edge_q[e].front() {
            if fl.veh[h as usize].at_end {
                wake.push(h);
            }
        }
        for w in wake {
            self.at(t, Ev::VehTry(w));
        }
    }

    fn fleet_release(&mut self, n: usize, t: f64) {
        let fl = self.fl.as_mut().unwrap();
        fl.node_held[n] = None;
        let wake: Vec<u32> = std::mem::take(&mut fl.node_wait[n]);
        for w in wake {
            self.at(t, Ev::VehTry(w));
        }
    }

    fn fleet_hoist(&mut self, v: u32, n: usize, t: f64) {
        let full = self.full;
        let fl = self.fl.as_mut().unwrap();
        let vi = v as usize;
        let held = (t - fl.veh[vi].leg_start - fl.veh[vi].leg_free).max(0.0);
        fl.out.held_min += held;
        let up = fl.veh[vi].mode == Mode::ToPick;
        let job = fl.veh[vi].job.clone().unwrap();
        if up {
            let w = t - job.asked;
            fl.out.wait_sum += w;
            fl.out.wait_n += 1;
            fl.out.wait_max = fl.out.wait_max.max(w);
        }
        fl.veh[vi].mode = if up { Mode::HoistUp } else { Mode::HoistDown };
        if full {
            fl.veh[vi].hoist = fl.out.hoists.len();
            fl.out.hoists.push(HoistRec { vehicle: v, stop: n, lot: job.lot, up, t0: t, t1: t + fl.hoist });
        }
        let end = t + fl.hoist;
        self.at(end, Ev::Hoisted(v));
    }

    fn fleet_hoisted(&mut self, v: u32, t: f64) {
        let vi = v as usize;
        let fl = self.fl.as_mut().unwrap();
        let Pos::Node(n) = fl.veh[vi].pos else { unreachable!("a hoist happens at a stop") };
        let job = fl.veh[vi].job.clone().unwrap();
        if fl.veh[vi].mode == Mode::HoistUp {
            let free = fl.track.dist(n, job.to) / fl.speed;
            let veh = &mut fl.veh[vi];
            veh.mode = Mode::Loaded;
            veh.target = job.to;
            veh.leg_start = t;
            veh.leg_free = free;
            if let Some(ti) = job.tool {
                self.tool_out(ti, false, t);
                let g = self.tools[ti as usize].group;
                self.dispatch(g, t);
            }
            self.fleet_go(v, t);
            return;
        }
        // set down: the lot joins its next group's queue and the vehicle parks off the track
        let d = t - job.asked;
        fl.out.delivered += 1;
        fl.port_load[job.to] -= 1;
        fl.out.deliver_sum += d;
        fl.out.deliver_least = fl.out.deliver_least.min(d);
        fl.out.busy_min += t - fl.veh[vi].busy_since;
        let veh = &mut fl.veh[vi];
        veh.mode = Mode::Idle;
        veh.job = None;
        veh.pos = Pos::Parked(n);
        self.transports += 1;
        self.transport_minutes += d;
        self.lots[job.lot as usize].node = job.to;
        self.fleet_release(n, t);
        self.arrive(job.lot, t);
        self.fleet_assign(t);
    }
}

/// Run a shop. With a chooser, every time a free tool could start work it is handed a
/// decision and returns the index of the candidate to start.
pub fn run(shop: &Shop, opts: &RunOptions, chooser: Option<&mut dyn FnMut(&Decision) -> usize>) -> RunResult {
    run_vehicles(shop, opts, chooser, None)
}

/// `run` with a vehicle controller (docs/FLEET.md): asked which idle vehicle takes each move, when the shop has a
/// fleet. A pick that is not one of the idle vehicles is refused, counted, and the built-in pick used instead.
pub fn run_vehicles<'c>(
    shop: &Shop,
    opts: &RunOptions,
    chooser: Option<&'c mut dyn FnMut(&Decision) -> usize>,
    vchooser: Option<&'c mut dyn FnMut(&VehicleAsk) -> usize>,
) -> RunResult {
    let horizon = opts.until.unwrap_or(f64::INFINITY);
    // compile the shop into indexes
    let gidx: HashMap<&str, u32> = shop.groups.iter().enumerate().map(|(i, g)| (g.name.as_str(), i as u32)).collect();
    let mut setup_names = vec![String::new()];
    let mut setup_idx: HashMap<String, u32> = HashMap::new();
    let mut routes = vec![];
    let mut rem_lot = vec![];
    let mut rem_piece = vec![];
    for r in &shop.routes {
        let mut steps = vec![];
        for st in &r.steps {
            let setup = match &st.setup {
                Some(s) if !s.is_empty() => *setup_idx.entry(s.clone()).or_insert_with(|| {
                    setup_names.push(s.clone());
                    (setup_names.len() - 1) as u32
                }),
                _ => 0,
            };
            steps.push(StepC {
                group: *gidx.get(st.group.as_str()).unwrap_or_else(|| panic!("unknown group {}", st.group)),
                per: st.per,
                time: st.time,
                spread: st.spread,
                batch: st.batch.unwrap_or((1.0, 1e9)),
                interval: st.interval.unwrap_or(0.0),
                batch_wait: st.batch_wait,
                setup,
                sample: st.sample,
                rework: st.rework,
                cqt: st.cqt,
            });
        }
        let n = steps.len();
        let (mut a, mut b) = (vec![0.0; n + 1], vec![0.0; n + 1]);
        for i in (0..n).rev() {
            a[i] = a[i + 1];
            b[i] = b[i + 1];
            if steps[i].per == Per::Piece {
                b[i] += steps[i].time;
            } else {
                a[i] += steps[i].time;
            }
        }
        routes.push(steps);
        rem_lot.push(a);
        rem_piece.push(b);
    }
    let mut tools = vec![];
    let mut group_tools = vec![];
    for (gi, g) in shop.groups.iter().enumerate() {
        let mut ids = vec![];
        for i in 0..g.count {
            ids.push(tools.len() as u32);
            tools.push(Tool {
                name: format!("{}#{}", g.name, i + 1),
                group: gi as u32,
                setup: 0,
                busy: false,
                down: 0,
                pending: VecDeque::new(),
                state: STANDBY,
                since: 0.0,
                minutes: [0.0; 4],
                counts: vec![0.0; g.pm_pieces.len()],
                hold_until: f64::NEG_INFINITY,
                out: 0,
                full_since: 0.0,
            });
        }
        group_tools.push(ids);
    }
    let ng = shop.groups.len();
    let place_of: Vec<Option<Place>> = match &shop.oht {
        None => vec![],
        Some(o) => shop
            .groups
            .iter()
            .map(|g| match o.places.iter().find(|p| p.0 == g.name) {
                Some(p) => p.1,
                None => panic!("the layout has no place for group {}", g.name),
            })
            .collect(),
    };
    // two families (docs/TWO-FAMILIES.md)
    let mut fam_names: Vec<String> = vec![String::new()];
    let route_fam: Vec<u32> = shop
        .routes
        .iter()
        .map(|r| {
            let f = shop.family_of(&r.name).to_string();
            match fam_names.iter().position(|x| *x == f) {
                Some(i) => i as u32,
                None => {
                    fam_names.push(f);
                    (fam_names.len() - 1) as u32
                }
            }
        })
        .collect();
    for f in shop.famcaps.iter().map(|(f, _)| f).chain(shop.quals.iter().map(|(_, f, _)| f)).chain(shop.reserves.iter().map(|(_, f, _)| f)) {
        if !fam_names.contains(f) {
            fam_names.push(f.clone());
        }
    }
    assert!(fam_names.len() <= 64, "at most 64 families");
    let fam_on = shop.has_family_rules();
    let fidx = |f: &str| fam_names.iter().position(|x| x == f).unwrap() as u32;
    let mut elig = vec![u64::MAX; tools.len()];
    let mut reserved: Vec<Option<u32>> = vec![None; tools.len()];
    let ntools_for_defects = tools.len();
    if fam_on {
        for (g, f, n) in &shop.quals {
            let Some(gi) = gidx.get(g.as_str()) else { panic!("qual names unknown group {g}") };
            let bit = 1u64 << fidx(f);
            for (k, &ti) in group_tools[*gi as usize].iter().enumerate() {
                if k >= *n {
                    elig[ti as usize] &= !bit;
                }
            }
        }
        for (g, f, n) in &shop.reserves {
            let Some(gi) = gidx.get(g.as_str()) else { panic!("reserve names unknown group {g}") };
            for (k, &ti) in group_tools[*gi as usize].iter().enumerate() {
                if k < *n {
                    reserved[ti as usize] = Some(fidx(f));
                }
            }
        }
    }
    let nf = fam_names.len();
    let mut fam_cap = vec![None; nf];
    for (f, n) in &shop.famcaps {
        fam_cap[fidx(f) as usize] = Some(*n);
    }
    let mut sim = Sim {
        shop,
        seed: opts.seed,
        full: opts.record,
        lo_t: shop.transport.0,
        hi_t: shop.transport.1,
        oht: shop.oht.as_ref(),
        place_of,
        transports: 0,
        transport_minutes: 0.0,
        routes,
        rem_lot,
        rem_piece,
        setup_names,
        group_setups: shop.groups.iter().map(|g| g.setups.iter().cloned().collect()).collect(),
        group_tools,
        heap: BinaryHeap::new(),
        seq: 0,
        tools,
        queues: (0..ng).map(|_| vec![]).collect(),
        waiting: (0..ng).map(|_| vec![]).collect(),
        lots: vec![],
        states: vec![],
        breaches: vec![],
        busy: vec![0.0; ng],
        wait: vec![0.0; ng],
        visits: vec![0; ng],
        n: 0,
        last: 0.0,
        area: 0.0,
        done: 0,
        wip: 0,
        wlast: 0.0,
        warea: 0.0,
        moves: 0,
        now: 0.0,
        cap: shop.cap,
        held: VecDeque::new(),
        release_log: vec![],
        probes: vec![],
        chooser,
        decisions: 0,
        trace: vec![],
        fam_on,
        fam_names,
        route_fam,
        fam_cap,
        fam_wip: vec![0; nf],
        fam_held: (0..nf).map(|_| VecDeque::new()).collect(),
        elig,
        reserved,
        defects: shop.defects,
        recent: if shop.defects.is_some() { (0..ntools_for_defects).map(|_| VecDeque::new()).collect() } else { vec![] },
        holds: vec![],
        fl: match (&shop.fleet, &shop.oht) {
            (Some(f), Some(o)) => {
                let track = crate::track::Track::with_ports(o, &shop.ports, f.cross);
                let stops = shop.groups.iter().map(|g| track.stop_of(&g.name)).collect();
                let gports = shop.groups.iter().map(|g| track.ports_of(&g.name).to_vec()).collect();
                Some(FleetState::new(track, o.speed, f.gap, f.hoist, f.vehicles, f.controller != "first", stops, gports))
            }
            _ => None,
        },
        ports: shop.fleet.as_ref().filter(|_| shop.oht.is_some()).map(|f| f.ports as u32).unwrap_or(0),
        from_tool: None,
        vchooser,
    };

    // downs: given windows, maintenance calendars, breakdowns
    for (gi, g) in shop.groups.iter().enumerate() {
        for k in 0..sim.group_tools[gi].len() {
            let ti = sim.group_tools[gi][k];
            for &(s, e) in &g.down {
                sim.at(s, Ev::Down(ti, SCHEDULED, e - s));
            }
            let needs_rng = g.pm.iter().any(|p| p.first.is_none())
                || g.pm_pieces.iter().any(|p| p.first.is_none())
                || g.breakdown.is_some_and(|b| b.0 > 0.0);
            let mut r = if needs_rng {
                Some(PyRandom::from_str_seed(&format!("{}/tool/{}", opts.seed, sim.tools[ti as usize].name)))
            } else {
                None
            };
            for (pk, pm) in g.pm.iter().enumerate() {
                let first = match pm.first {
                    Some(f) => f,
                    None => r.as_mut().unwrap().uniform(0.0, pm.every),
                };
                sim.at(first, Ev::Pm(ti, pk as u32, pm.every));
            }
            for (pk, pm) in g.pm_pieces.iter().enumerate() {
                sim.tools[ti as usize].counts[pk] = match pm.first {
                    Some(f) => pm.every - f,
                    None => r.as_mut().unwrap().uniform(0.0, pm.every),
                };
            }
            if let Some((mttf, _)) = g.breakdown {
                if mttf > 0.0 {
                    let x = r.as_mut().unwrap().expovariate(1.0 / mttf);
                    sim.at(x, Ev::Break(ti));
                }
            }
        }
    }
    for d in &shop.lots {
        let wip = d.step > 0 || d.start < 0.0;
        let l = sim.new_lot(d.id.clone(), &d.route, d.size, d.priority, d.start, d.step, wip);
        let f = sim.lots[l as usize].fam as usize;
        if sim.fam_on && !wip && sim.fam_cap[f].is_some() {
            sim.at(d.start, Ev::Admit(l));
        } else {
            sim.at(d.start.max(0.0), Ev::Arrive(l));
        }
    }
    for (k, rel) in shop.releases.iter().enumerate() {
        sim.at(rel.first, Ev::Release(k as u32, 0));
    }
    for &tp in &shop.probes {
        sim.at(tp, Ev::Probe);
    }

    while let Some(HeapItem { t, ev, .. }) = sim.heap.pop() {
        if t > horizon {
            break;
        }
        sim.now = t;
        match ev {
            Ev::Arrive(l) => sim.arrive(l, t),
            Ev::Admit(l) => {
                let f = sim.lots[l as usize].fam as usize;
                let id = sim.lots[l as usize].id.clone();
                if sim.fam_room(f) {
                    sim.release_log.push(ReleaseRow { id, scheduled: t, released: Some(t), wip_before: Some(sim.fam_wip[f]) });
                    sim.lots[l as usize].release = t;
                    sim.arrive(l, t);
                } else {
                    sim.release_log.push(ReleaseRow { id, scheduled: t, released: None, wip_before: None });
                    let row = sim.release_log.len() - 1;
                    sim.fam_held[f].push_back(Held::Lot(l, row));
                }
            }
            Ev::UnholdFam(f) => {
                let f = f as usize;
                let cap = sim.fam_cap[f].unwrap();
                while sim.fam_wip[f] < cap {
                    let Some(h) = sim.fam_held[f].pop_front() else { break };
                    match h {
                        Held::Rel(k, n, row) => {
                            sim.release_log[row].released = Some(t);
                            sim.release_log[row].wip_before = Some(sim.fam_wip[f]);
                            sim.release(k, n, t);
                        }
                        Held::Lot(l, row) => {
                            sim.release_log[row].released = Some(t);
                            sim.release_log[row].wip_before = Some(sim.fam_wip[f]);
                            sim.lots[l as usize].release = t;
                            sim.arrive(l, t);
                        }
                    }
                }
            }
            Ev::Release(k, n) => {
                let rel = &shop.releases[k as usize];
                if let Some(c) = rel.count {
                    if n >= c {
                        continue;
                    }
                }
                let id = sim.rid(k, n);
                let rf = if sim.fam_on {
                    let r = shop.routes.iter().position(|x| x.name == rel.route).unwrap();
                    Some(sim.route_fam[r] as usize).filter(|&f| sim.fam_cap[f].is_some())
                } else {
                    None
                };
                if let Some(f) = rf {
                    if sim.fam_room(f) {
                        sim.release_log.push(ReleaseRow { id, scheduled: t, released: Some(t), wip_before: Some(sim.fam_wip[f]) });
                        sim.release(k, n, t);
                    } else {
                        sim.release_log.push(ReleaseRow { id, scheduled: t, released: None, wip_before: None });
                        let row = sim.release_log.len() - 1;
                        sim.fam_held[f].push_back(Held::Rel(k, n, row));
                    }
                } else if sim.cap.is_some() && (!sim.held.is_empty() || sim.wip >= sim.cap.unwrap()) {
                    sim.release_log.push(ReleaseRow { id, scheduled: t, released: None, wip_before: None });
                    sim.held.push_back((k, n, sim.release_log.len() - 1));
                } else {
                    sim.release_log.push(ReleaseRow { id, scheduled: t, released: Some(t), wip_before: Some(sim.wip) });
                    sim.release(k, n, t);
                }
                sim.at(t + rel.every, Ev::Release(k, n + 1));
            }
            Ev::Unhold => {
                while !sim.held.is_empty() && sim.wip < sim.cap.unwrap() {
                    let (k, n, row) = sim.held.pop_front().unwrap();
                    sim.release_log[row].released = Some(t);
                    sim.release_log[row].wip_before = Some(sim.wip);
                    sim.release(k, n, t);
                }
            }
            Ev::Probe => {
                sim.probes.push(Probe {
                    t,
                    finished: sim.done,
                    wip: sim.wip,
                    moves: sim.moves,
                    waiting: sim.n,
                    wait_lot_minutes: sim.area + sim.n as f64 * (t - sim.last),
                    wip_lot_minutes: sim.warea + sim.wip as f64 * (t - sim.wlast),
                    transports: sim.transports,
                    transport_minutes: sim.transport_minutes,
                });
            }
            Ev::Begin(ti, batch, dur) => {
                sim.set_state(ti, t, PRODUCTIVE, "");
                if sim.full {
                    for &l in &batch {
                        let name = sim.tools[ti as usize].name.clone();
                        let lot = &mut sim.lots[l as usize];
                        let (step, arrive) = (lot.step, lot.arrived);
                        if let Some(tr) = lot.trail.as_mut() {
                            tr.push(StepOut { step, tool: name, arrive, start: t, end: t + dur });
                        }
                        sim.trace.push(Trace { lot: l, step: step as u32, tool: ti, arrive, start: t, end: t + dur });
                    }
                }
                let g = sim.tools[ti as usize].group as usize;
                sim.busy[g] += dur;
                sim.at(t + dur, Ev::End(ti, batch));
            }
            Ev::End(ti, batch) => sim.finish(ti, t, batch),
            Ev::Down(ti, how, minutes) => sim.down_due(ti, t, how, minutes),
            Ev::Pm(ti, k, every) => {
                let g = sim.tools[ti as usize].group as usize;
                let pm = &shop.groups[g].pm[k as usize];
                let mut r = PyRandom::from_str_seed(&format!("{}/pm/{}/{}/{}", opts.seed, sim.tools[ti as usize].name, k, t as i64));
                let m = r.uniform(pm.lo, pm.hi);
                sim.down_due(ti, t, SCHEDULED, m);
                sim.at(t + every, Ev::Pm(ti, k, every));
            }
            Ev::Break(ti) => {
                let g = sim.tools[ti as usize].group as usize;
                let (mttf, mttr) = shop.groups[g].breakdown.unwrap();
                let mut r = PyRandom::from_str_seed(&format!("{}/break/{}/{}", opts.seed, sim.tools[ti as usize].name, t as i64));
                let m = r.expovariate(1.0 / mttr);
                sim.down_due(ti, t, UNSCHEDULED, m);
                let next = r.expovariate(1.0 / mttf);
                sim.at(t + next, Ev::Break(ti));
            }
            Ev::Wake(g) => sim.dispatch(g, t),
            Ev::VehEnd(v) => {
                sim.fl.as_mut().unwrap().veh[v as usize].at_end = true;
                sim.fleet_go(v, t);
            }
            Ev::VehTry(v) => sim.fleet_go(v, t),
            Ev::Hoisted(v) => sim.fleet_hoisted(v, t),
            Ev::Unpark(l) => sim.unpark(l, t),
            Ev::Up(ti) => {
                sim.tools[ti as usize].down = 0;
                sim.set_state(ti, t, STANDBY, "");
                if let Some((kind, m)) = sim.tools[ti as usize].pending.pop_front() {
                    sim.go_down(ti, t, kind, m);
                }
                let g = sim.tools[ti as usize].group;
                sim.dispatch(g, t);
            }
        }
    }

    let end = if horizon.is_infinite() { sim.now } else { horizon };
    for tool in &mut sim.tools {
        let x = end - tool.since;
        tool.minutes[tool.state as usize] += if x > 0.0 { x } else { 0.0 };
    }
    let lots = std::mem::take(&mut sim.lots)
        .into_iter()
        .map(|l| LotOut {
            route: shop.routes[l.route as usize].name.clone(),
            id: l.id,
            priority: l.priority,
            size: l.size,
            release: l.release,
            done: l.done,
            wip: l.wip,
            steps: l.trail.unwrap_or_default(),
        })
        .collect();
    RunResult {
        lots,
        states: std::mem::take(&mut sim.states),
        breaches: std::mem::take(&mut sim.breaches),
        tools: sim
            .tools
            .iter()
            .map(|t| ToolOut { name: t.name.clone(), group: shop.groups[t.group as usize].name.clone(), minutes: t.minutes })
            .collect(),
        groups: shop
            .groups
            .iter()
            .enumerate()
            .map(|(i, g)| GroupOut { name: g.name.clone(), busy: sim.busy[i], wait: sim.wait[i], visits: sim.visits[i], count: g.count })
            .collect(),
        release_log: std::mem::take(&mut sim.release_log),
        holds: std::mem::take(&mut sim.holds),
        probes: std::mem::take(&mut sim.probes),
        finished: sim.done,
        waiting: sim.n,
        wait_lot_minutes: sim.area + sim.n as f64 * (end - sim.last),
        moves: sim.moves,
        transports: sim.transports,
        transport_minutes: sim.transport_minutes,
        until: end,
        decisions: sim.decisions,
        trace: std::mem::take(&mut sim.trace),
        fleet: sim.fl.take().map(|mut f| {
            for tool in &sim.tools {
                if sim.ports > 0 && tool.out >= sim.ports {
                    f.out.blocked_min += end - tool.full_since;
                }
            }
            for v in &f.veh {
                if v.mode != Mode::Idle {
                    f.out.busy_min += end - v.busy_since;
                }
            }
            f.out.open = f.out.asked - f.out.delivered;
            if f.out.deliver_least.is_infinite() {
                f.out.deliver_least = 0.0;
            }
            f.out
        }),
    }
}
