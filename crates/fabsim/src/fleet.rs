//! The fleet's types and state (docs/FLEET.md, rungs L3 and L4). The engine moves the vehicles; this holds what they
//! are, what a vehicle controller is asked, and what a run reports. Every fleet number is assumed.

use crate::track::Track;
use std::collections::VecDeque;

/// One idle vehicle a controller may pick: its number, the stop it waits at, and its track metres to the lot.
#[derive(Clone, Debug, PartialEq)]
pub struct IdleVehicle {
    pub vehicle: u32,
    pub stop: usize,
    pub dist: f64,
}

/// What a vehicle controller is asked for each move: the lot, the stop it waits at, the stop it goes to, when it was
/// asked for, now, and the idle vehicles in vehicle order. The answer is an index into `idle`.
#[derive(Clone, Debug, PartialEq)]
pub struct VehicleAsk {
    pub lot: u32,
    pub from: usize,
    pub to: usize,
    pub asked: f64,
    pub now: f64,
    pub idle: Vec<IdleVehicle>,
}

/// A vehicle's stay on one stretch (only with `record`); `t_out` is infinite while it is still there.
#[derive(Clone, Debug, PartialEq)]
pub struct Entry {
    pub vehicle: u32,
    pub edge: usize,
    pub t_in: f64,
    pub t_out: f64,
    pub loaded: bool,
}

/// A hoist at a stop (only with `record`): up to take a lot, or down to leave it.
#[derive(Clone, Debug, PartialEq)]
pub struct HoistRec {
    pub vehicle: u32,
    pub stop: usize,
    pub lot: u32,
    pub up: bool,
    pub t0: f64,
    pub t1: f64,
}

/// What a run with a fleet reports (minutes and metres).
#[derive(Clone, Debug, PartialEq, Default)]
pub struct FleetOut {
    pub vehicles: usize,
    pub asked: i64,
    pub delivered: i64,
    pub open: i64,
    pub picks: u64,
    pub refused: u64,
    /// from a lot's request to the vehicle reaching it
    pub wait_sum: f64,
    pub wait_n: u64,
    pub wait_max: f64,
    /// from request to the lot set down at its next stop
    pub deliver_sum: f64,
    pub deliver_least: f64,
    pub loaded_m: f64,
    pub empty_m: f64,
    pub busy_min: f64,
    /// minutes vehicles took beyond free flow at the layout's speed, on their way to a pickup or a drop
    pub held_min: f64,
    /// tool-minutes with every port full
    pub blocked_min: f64,
    /// times a vehicle found its way full and went on by another stretch, as a control system routes round a jam
    pub detours: u64,
    pub entries: Vec<Entry>,
    pub hoists: Vec<HoistRec>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Pos {
    Parked(usize),
    Node(usize),
    Edge(usize),
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Mode {
    Idle,
    ToPick,
    HoistUp,
    Loaded,
    HoistDown,
}

#[derive(Clone, Debug)]
pub(crate) struct Job {
    pub lot: u32,
    pub from: usize,
    pub to: usize,
    pub asked: f64,
    pub tool: Option<u32>,
}

pub(crate) struct Veh {
    pub pos: Pos,
    pub mode: Mode,
    pub job: Option<Job>,
    pub target: usize,
    pub at_end: bool,
    pub busy_since: f64,
    /// when the current leg began and its free-flow minutes
    pub leg_start: f64,
    pub leg_free: f64,
    /// index of the open entry, when recording
    pub entry: usize,
    pub hoist: usize,
}

pub(crate) struct FleetState {
    pub track: Track,
    pub speed: f64,
    pub headway: f64,
    pub hoist: f64,
    pub nearest: bool,
    pub cap: Vec<usize>,
    pub edge_q: Vec<VecDeque<u32>>,
    pub last_in: Vec<f64>,
    pub last_end: Vec<f64>,
    pub edge_wait: Vec<Vec<u32>>,
    pub node_held: Vec<Option<u32>>,
    pub node_wait: Vec<Vec<u32>>,
    pub veh: Vec<Veh>,
    pub pending: VecDeque<Job>,
    /// each group's stop (`None`: a stocker)
    pub stop_of_group: Vec<Option<usize>>,
    /// each group's tools' ports (empty when the shop lists none), and deliveries on their way to each node
    pub group_ports: Vec<Vec<usize>>,
    pub port_load: Vec<u32>,
    pub out: FleetOut,
}

impl FleetState {
    #[allow(clippy::too_many_arguments)]
    pub fn new(track: Track, speed: f64, gap: f64, hoist: f64, vehicles: usize, nearest: bool, stop_of_group: Vec<Option<usize>>, group_ports: Vec<Vec<usize>>) -> FleetState {
        let ne = track.edges().len();
        let nn = track.nodes().len();
        let cap = track.edges().iter().map(|e| ((e.len / gap).floor() as usize).max(1)).collect();
        // vehicles start parked at the stops in node order, round and round
        let mut stops: Vec<usize> = (0..nn).filter(|&n| track.nodes()[n].group.is_some() || track.nodes()[n].tool.is_some()).collect();
        stops.sort();
        let veh = (0..vehicles)
            .map(|k| {
                let n = stops[k % stops.len().max(1)];
                Veh { pos: Pos::Parked(n), mode: Mode::Idle, job: None, target: n, at_end: false, busy_since: 0.0, leg_start: 0.0, leg_free: 0.0, entry: usize::MAX, hoist: usize::MAX }
            })
            .collect();
        FleetState {
            track,
            speed,
            headway: gap / speed,
            hoist,
            nearest,
            cap,
            edge_q: vec![VecDeque::new(); ne],
            last_in: vec![f64::NEG_INFINITY; ne],
            last_end: vec![f64::NEG_INFINITY; ne],
            edge_wait: vec![vec![]; ne],
            node_held: vec![None; nn],
            node_wait: vec![vec![]; nn],
            veh,
            pending: VecDeque::new(),
            stop_of_group,
            group_ports,
            port_load: vec![0; nn],
            out: FleetOut { vehicles, deliver_least: f64::INFINITY, ..FleetOut::default() },
        }
    }

    /// The idle vehicles for a lot waiting at `from`, in vehicle order.
    pub fn idle_for(&self, from: usize) -> Vec<IdleVehicle> {
        self.veh
            .iter()
            .enumerate()
            .filter(|(_, v)| v.mode == Mode::Idle)
            .map(|(k, v)| {
                let stop = match v.pos {
                    Pos::Parked(n) | Pos::Node(n) => n,
                    Pos::Edge(e) => self.track.edges()[e].to,
                };
                IdleVehicle { vehicle: k as u32, stop, dist: self.track.dist(stop, from) }
            })
            .collect()
    }

    /// The built-in pick: the nearest idle vehicle (ties to the lower number), or the first.
    pub fn default_pick(&self, idle: &[IdleVehicle]) -> usize {
        if !self.nearest {
            return 0;
        }
        let mut best = 0;
        for (i, v) in idle.iter().enumerate() {
            if v.dist < idle[best].dist {
                best = i;
            }
        }
        best
    }

    /// The stretch to take from node n toward `target`: the shortest way when it has room; when that is full, another
    /// stretch out of n with room, the one with the shortest way on (a detour). `None` when nothing can be entered now.
    pub fn way(&self, n: usize, target: usize, t: f64) -> (usize, Option<usize>) {
        let e2 = self.track.next(n, target).expect("the track reaches every stop");
        if self.can_enter(e2, t) {
            return (e2, Some(e2));
        }
        if self.edge_q[e2].len() < self.cap[e2] {
            return (e2, None); // only the gap to the vehicle ahead: wait for it
        }
        let mut best: Option<(f64, usize)> = None;
        for &e3 in self.track.out_of(n) {
            if e3 != e2 && self.can_enter(e3, t) {
                let d = self.track.edges()[e3].len + self.track.dist(self.track.edges()[e3].to, target);
                if d.is_finite() && best.is_none_or(|b| d < b.0) {
                    best = Some((d, e3));
                }
            }
        }
        (e2, best.map(|b| b.1))
    }

    pub fn can_enter(&self, e: usize, t: f64) -> bool {
        self.edge_q[e].len() < self.cap[e] && t + 1e-12 >= self.last_in[e] + self.headway
    }
}
