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
use crate::shop::{Per, Shop};

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
}

impl Candidate {
    pub const FIELDS: [&'static str; 13] = [
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
    pub time: f64,
    pub state: &'static str,
    pub why: &'static str,
}

#[derive(Clone, Debug)]
pub struct Breach {
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
    pub until: f64,
    /// decisions handed to the chooser (or that would have been, without one)
    pub decisions: u64,
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
}

enum Pick {
    Q(usize),
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
        }
    }

    fn leave(&mut self, l: u32, t: f64) {
        self.done += 1;
        if self.lots[l as usize].inwip {
            self.lots[l as usize].inwip = false;
            self.wipd(t, -1);
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
            self.states.push(StateRow { tool: tool.name.clone(), time: t, state: STATES[state as usize], why });
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
        if per == Per::Batch {
            let ws = &mut self.waiting[g as usize];
            match ws.iter_mut().find(|w| w.key == key) {
                Some(w) => w.lots.push((t, l)),
                None => ws.push(Waiting { key, lots: vec![(t, l)] }),
            }
            let wait = bw.or(self.shop.groups[g as usize].batch_wait);
            if let Some(w) = wait {
                self.at(t + w, Ev::Wake(g));
            }
        } else {
            let seq = self.seq;
            self.seq += 1;
            let k = (F(-self.lots[l as usize].priority), F(t), seq);
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

    fn pick(&self, g: u32, ti: u32) -> Option<Pick> {
        let tool_setup = self.tools[ti as usize].setup;
        let mut best: Option<((F, u8, F), Pick)> = None;
        for (qi, q) in self.queues[g as usize].iter().enumerate() {
            let Some((k, _)) = q.q.first_key_value() else { continue };
            let change = if q.key == 0 || q.key == tool_setup { 0 } else { 1 };
            let cand = (k.0, change, k.1);
            if best.as_ref().is_none_or(|b| cand < b.0) {
                best = Some((cand, Pick::Q(qi)));
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
        }
    }

    /// Every candidate the free tool could take, with handles, and the rule's default index.
    fn decision(&self, g: u32, ti: u32, t: f64) -> Option<(Decision, Vec<(bool, usize, Option<QKey>)>)> {
        let mut cands = vec![];
        let mut handles = vec![];
        for (qi, q) in self.queues[g as usize].iter().enumerate() {
            for (k, &l) in q.q.iter() {
                let a = self.lots[l as usize].arrived;
                cands.push(self.candidate("lot", &[l], ti, t, a));
                handles.push((true, qi, Some(*k)));
            }
        }
        for (wi, oldest) in self.ready_batches(g) {
            let taken = self.batch_take(g, wi);
            cands.push(self.candidate("batch", &taken, ti, t, oldest));
            handles.push((false, wi, None));
        }
        if cands.is_empty() {
            return None;
        }
        let default = match self.pick(g, ti).unwrap() {
            Pick::Q(qi) => handles.iter().position(|h| h.0 && h.1 == qi).unwrap(),
            Pick::B(wi) => handles.iter().position(|h| !h.0 && h.1 == wi).unwrap(),
        };
        let mut gt = GroupTools::default();
        for &x in &self.group_tools[g as usize] {
            let tl = &self.tools[x as usize];
            if tl.down != 0 {
                gt.down += 1;
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
                if tool.busy || tool.down != 0 {
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
                Pick::Q(qi) => {
                    let (_, l) = self.queues[g as usize][qi].q.pop_first().unwrap();
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
            let waited = t - self.lots[l as usize].arrived;
            self.wait[g as usize] += waited;
            self.visits[g as usize] += 1;
            let step = self.lots[l as usize].step;
            for (from, to, limit, since) in self.cqts(l) {
                if to == step {
                    let gap = begin - since;
                    if gap > limit {
                        self.breaches.push(Breach {
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
        for &l in &batch {
            let (rework, step) = {
                let st = self.step_of(l).unwrap();
                (st.rework, self.lots[l as usize].step)
            };
            let lot = &mut self.lots[l as usize];
            match lot.ended.iter_mut().find(|e| e.0 == step) {
                Some(e) => e.1 = t,
                None => lot.ended.push((step, t)),
            }
            match rework {
                Some((to, p)) if lot.rng.random() < p => lot.step = to,
                _ => lot.step += 1,
            }
            self.move_on(l, t);
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
        let delay = if self.hi_t > 0.0 { self.lots[l as usize].rng.uniform(self.lo_t, self.hi_t) } else { 0.0 };
        self.at(t + delay, Ev::Arrive(l));
    }

    fn go_down(&mut self, ti: u32, t: f64, kind: u8, minutes: f64) {
        self.tools[ti as usize].down = kind;
        self.set_state(ti, t, kind, "");
        self.at(t + minutes, Ev::Up(ti));
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
        });
        (self.lots.len() - 1) as u32
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

/// Run a shop. With a chooser, every time a free tool could start work it is handed a
/// decision and returns the index of the candidate to start.
pub fn run(shop: &Shop, opts: &RunOptions, chooser: Option<&mut dyn FnMut(&Decision) -> usize>) -> RunResult {
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
            });
        }
        group_tools.push(ids);
    }
    let ng = shop.groups.len();
    let mut sim = Sim {
        shop,
        seed: opts.seed,
        full: opts.record,
        lo_t: shop.transport.0,
        hi_t: shop.transport.1,
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
        sim.at(d.start.max(0.0), Ev::Arrive(l));
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
            Ev::Arrive(l) => {
                if sim.full && sim.lots[l as usize].trail.is_none() {
                    sim.lots[l as usize].trail = Some(vec![]);
                }
                sim.enter(l, t);
                let first = !sim.lots[l as usize].entered;
                sim.lots[l as usize].entered = true;
                let st0 = sim.step_of(l).map(|s| s.sample);
                let p0 = match st0 {
                    Some(s) if first => s,
                    _ => None,
                };
                if let Some(p) = p0 {
                    if sim.lots[l as usize].rng.random() >= p {
                        sim.lots[l as usize].step += 1;
                        sim.move_on(l, t);
                        continue;
                    }
                }
                if st0.is_none() {
                    sim.lots[l as usize].done = Some(t);
                    sim.leave(l, t);
                    continue;
                }
                sim.enqueue(l, t);
            }
            Ev::Release(k, n) => {
                let rel = &shop.releases[k as usize];
                if let Some(c) = rel.count {
                    if n >= c {
                        continue;
                    }
                }
                let id = sim.rid(k, n);
                if sim.cap.is_some() && (!sim.held.is_empty() || sim.wip >= sim.cap.unwrap()) {
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
        probes: std::mem::take(&mut sim.probes),
        finished: sim.done,
        waiting: sim.n,
        wait_lot_minutes: sim.area + sim.n as f64 * (end - sim.last),
        moves: sim.moves,
        until: end,
        decisions: sim.decisions,
    }
}
