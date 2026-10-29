//! The track (docs/FLEET.md, rung L2): the overhead rail as a one-way graph built from a shop's layout.
//!
//! Each phase has a spine loop: the north lane (side 0) runs east past the north bays, the south lane (side 1) runs
//! west past the south bays, and a U-turn of the spine's width joins them at each end, with crossovers both ways every
//! `cross` metres. Each bay has a loop: it leaves its lane at the bay's upstream end, passes every stop in order of
//! depth (each tool's load port when the shop lists ports, else one stop per tool group), and rejoins the lane at the
//! downstream end, where a short spur holds the bay's stocker port off the lane. The bridge has one lane each way between one phase's
//! east end and the next phase's west end. Every stretch is measured along the aisles, as `Oht::distance` measures, so
//! no trip on the track is shorter than the aisles. A gigafab-style layout of our own design; the shape is assumed.

use crate::shop::{Oht, Place};
use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap};

/// The shortest stretch the track keeps (metres, assumed), where two stops stand at the same point.
const LEAST: f64 = 0.5;
/// Metres into and out of a bay's stocker spur (assumed).
const SPUR: f64 = 2.0;

#[derive(Clone, Debug, PartialEq)]
pub struct Edge {
    pub from: usize,
    pub to: usize,
    pub len: f64,
}

/// Where a node is, for drawing: the phase, the side, along the spine (x) and into the bay (y).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct NodeAt {
    pub phase: usize,
    pub side: usize,
    pub x: f64,
    pub y: f64,
    /// the bay a stop or spur belongs to (`usize::MAX` on a lane)
    pub bay: usize,
    /// a tool group's stop (index into the layout's places), when the shop lists no ports
    pub group: Option<usize>,
    /// a tool's load port (index into the shop's ports)
    pub tool: Option<usize>,
    /// a bay's stocker spur
    pub spur: bool,
}

pub struct Track {
    nodes: Vec<NodeAt>,
    edges: Vec<Edge>,
    out: Vec<Vec<usize>>,
    stops: HashMap<String, usize>,
    ports: HashMap<String, Vec<usize>>,
    /// stocker spurs per (phase, side): (x, node)
    spurs: HashMap<(usize, usize), Vec<(f64, usize)>>,
    /// lane nodes per (phase, side), sorted by x
    lanes: HashMap<(usize, usize), Vec<(f64, usize)>>,
    /// dist[to][from]: metres from `from` to `to`; next[to][from]: the first edge on that way
    dist: Vec<Vec<f64>>,
    next: Vec<Vec<u32>>,
}

#[derive(PartialEq)]
struct Item(f64, usize);
impl Eq for Item {}
impl PartialOrd for Item {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Item {
    fn cmp(&self, o: &Self) -> Ordering {
        o.0.total_cmp(&self.0).then_with(|| o.1.cmp(&self.1))
    }
}

fn key(x: f64) -> i64 {
    (x * 1000.0).round() as i64
}

impl Track {
    /// The track with one stop per tool group, at the group's place.
    pub fn new(o: &Oht, cross: f64) -> Track {
        Track::with_ports(o, &[], cross)
    }

    /// The track with a stop at every tool's load port, when `ports` lists them (else one stop per group).
    pub fn with_ports(o: &Oht, ports: &[(String, Place)], cross: f64) -> Track {
        let mut t = Track {
            nodes: vec![],
            edges: vec![],
            out: vec![],
            stops: HashMap::new(),
            ports: HashMap::new(),
            spurs: HashMap::new(),
            lanes: HashMap::new(),
            dist: vec![],
            next: vec![],
        };
        let nph = o.lengths.len();
        // the bays and their stops: (index, place); the index is a port's when ports are listed, else a place's
        let mut bays: HashMap<(usize, usize, usize), Vec<(usize, Place)>> = HashMap::new();
        if ports.is_empty() {
            for (i, (_, p)) in o.places.iter().enumerate() {
                if let Some(p) = p {
                    bays.entry((p.phase, p.side, p.bay)).or_default().push((i, *p));
                }
            }
        } else {
            for (i, (_, p)) in ports.iter().enumerate() {
                bays.entry((p.phase, p.side, p.bay)).or_default().push((i, *p));
            }
        }
        let mut bay_keys: Vec<(usize, usize, usize)> = bays.keys().copied().collect();
        bay_keys.sort();
        // each bay's two ends on its lane, upstream (in) and downstream (out)
        let mut ends: HashMap<(usize, usize, usize), (f64, f64)> = HashMap::new();
        let mut lane_x: HashMap<(usize, usize), Vec<f64>> = HashMap::new();
        for ph in 0..nph {
            for side in 0..2 {
                let len = o.lengths[ph];
                let mut xs = vec![0.0, len];
                if cross > 0.0 {
                    let mut x = cross;
                    while x < len - 1e-9 {
                        xs.push(x);
                        x += cross;
                    }
                }
                if o.start.phase == ph && o.start.side == side {
                    xs.push(o.start.x.clamp(0.0, len));
                }
                lane_x.insert((ph, side), xs);
            }
        }
        for k in &bay_keys {
            let g = &bays[k];
            let len = o.lengths[k.0];
            let lo = g.iter().map(|p| p.1.x).fold(f64::INFINITY, f64::min);
            let hi = g.iter().map(|p| p.1.x).fold(f64::NEG_INFINITY, f64::max);
            let (lo, hi) = if hi - lo < 2.0 {
                let m = (lo + hi) / 2.0;
                ((m - 1.0).max(0.0), (m + 1.0).min(len))
            } else {
                (lo, hi)
            };
            // the north lane runs east, the south lane west
            let (i, o2) = if k.1 == 0 { (lo, hi) } else { (hi, lo) };
            ends.insert(*k, (i, o2));
            let xs = lane_x.get_mut(&(k.0, k.1)).unwrap();
            xs.push(i);
            xs.push(o2);
        }
        // lane nodes and the lane's stretches
        let mut lane_keys: Vec<(usize, usize)> = lane_x.keys().copied().collect();
        lane_keys.sort();
        for lk in &lane_keys {
            let mut xs = lane_x[lk].clone();
            xs.sort_by(|a, b| a.total_cmp(b));
            xs.dedup_by(|a, b| key(*a) == key(*b));
            let ids: Vec<(f64, usize)> = xs.iter().map(|&x| (x, t.node(NodeAt { phase: lk.0, side: lk.1, x, y: 0.0, bay: usize::MAX, group: None, tool: None, spur: false }))).collect();
            for w in ids.windows(2) {
                let (a, b) = if lk.1 == 0 { (w[0], w[1]) } else { (w[1], w[0]) };
                t.edge(a.1, b.1, (b.0 - a.0).abs());
            }
            t.lanes.insert(*lk, ids);
        }
        for ph in 0..nph {
            let len = o.lengths[ph];
            let (n0, n1) = (t.lane(ph, 0, len), t.lane(ph, 1, len));
            t.edge(n0, n1, o.spine.max(LEAST));
            let (w1, w0) = (t.lane(ph, 1, 0.0), t.lane(ph, 0, 0.0));
            t.edge(w1, w0, o.spine.max(LEAST));
            if cross > 0.0 {
                let mut x = cross;
                while x < len - 1e-9 {
                    let (a, b) = (t.lane(ph, 0, x), t.lane(ph, 1, x));
                    t.edge(a, b, o.spine.max(LEAST));
                    t.edge(b, a, o.spine.max(LEAST));
                    x += cross;
                }
            }
            if ph + 1 < nph {
                let (e0, w0n) = (t.lane(ph, 0, len), t.lane(ph + 1, 0, 0.0));
                t.edge(e0, w0n, o.bridge.max(LEAST));
                let (w1n, e1) = (t.lane(ph + 1, 1, 0.0), t.lane(ph, 1, len));
                t.edge(w1n, e1, o.bridge.max(LEAST));
            }
        }
        // the bay loops
        for k in &bay_keys {
            let mut g = bays[k].clone();
            g.sort_by(|a, b| a.1.y.total_cmp(&b.1.y).then(a.1.x.total_cmp(&b.1.x)).then(a.0.cmp(&b.0)));
            let (xi, xo) = ends[k];
            let jin = t.lane(k.0, k.1, xi);
            let jout = t.lane(k.0, k.1, xo);
            let (mut prev, mut px, mut py) = (jin, xi, 0.0);
            for (i, p) in &g {
                let (group, tool) = if ports.is_empty() { (Some(*i), None) } else { (None, Some(*i)) };
                let n = t.node(NodeAt { phase: k.0, side: k.1, x: p.x, y: p.y, bay: k.2, group, tool, spur: false });
                if ports.is_empty() {
                    t.stops.insert(o.places[*i].0.clone(), n);
                }
                t.edge(prev, n, ((p.x - px).abs() + (p.y - py).abs()).max(LEAST));
                prev = n;
                px = p.x;
                py = p.y;
            }
            t.edge(prev, jout, ((xo - px).abs() + py).max(LEAST));
            // the bay's stocker port, on a spur off the lane at the bay's downstream end
            let sp = t.node(NodeAt { phase: k.0, side: k.1, x: xo, y: 0.0, bay: k.2, group: None, tool: None, spur: true });
            t.edge(jout, sp, SPUR);
            t.edge(sp, jout, SPUR);
            t.spurs.entry((k.0, k.1)).or_default().push((xo, sp));
        }
        // ports by group, in the shop's order (a group's tools in order)
        if !ports.is_empty() {
            let mut node_of_port = vec![usize::MAX; ports.len()];
            for (n, a) in t.nodes.iter().enumerate() {
                if let Some(j) = a.tool {
                    node_of_port[j] = n;
                }
            }
            for (j, (g, _)) in ports.iter().enumerate() {
                t.ports.entry(g.clone()).or_default().push(node_of_port[j]);
            }
            for (g, v) in &t.ports {
                t.stops.insert(g.clone(), v[0]);
            }
        }
        t.out = vec![vec![]; t.nodes.len()];
        for (i, e) in t.edges.iter().enumerate() {
            t.out[e.from].push(i);
        }
        t.routes();
        t
    }

    fn node(&mut self, n: NodeAt) -> usize {
        self.nodes.push(n);
        self.nodes.len() - 1
    }

    fn edge(&mut self, from: usize, to: usize, len: f64) {
        if from != to {
            self.edges.push(Edge { from, to, len });
        }
    }

    /// The lane node at x (it exists by construction).
    fn lane(&self, phase: usize, side: usize, x: f64) -> usize {
        let v = &self.lanes[&(phase, side)];
        let k = key(x);
        v.iter().find(|p| key(p.0) == k).map(|p| p.1).unwrap_or_else(|| self.nearest(phase, side, x))
    }

    fn nearest(&self, phase: usize, side: usize, x: f64) -> usize {
        let v = &self.lanes[&(phase, side)];
        v.iter().min_by(|a, b| (a.0 - x).abs().total_cmp(&(b.0 - x).abs())).unwrap().1
    }

    /// Shortest ways to every node, by Dijkstra on the reversed graph from each target.
    fn routes(&mut self) {
        let n = self.nodes.len();
        let mut inn: Vec<Vec<usize>> = vec![vec![]; n];
        for (i, e) in self.edges.iter().enumerate() {
            inn[e.to].push(i);
        }
        self.dist = vec![vec![f64::INFINITY; n]; n];
        self.next = vec![vec![u32::MAX; n]; n];
        for to in 0..n {
            let d = &mut self.dist[to];
            let nx = &mut self.next[to];
            d[to] = 0.0;
            let mut h = BinaryHeap::new();
            h.push(Item(0.0, to));
            while let Some(Item(du, u)) = h.pop() {
                if du > d[u] {
                    continue;
                }
                for &ei in &inn[u] {
                    let e = &self.edges[ei];
                    let dv = du + e.len;
                    // ties go to the lower edge number, so the way is the same on every run
                    if dv < d[e.from] - 1e-12 || ((dv - d[e.from]).abs() <= 1e-12 && (ei as u32) < nx[e.from]) {
                        d[e.from] = dv;
                        nx[e.from] = ei as u32;
                        h.push(Item(dv, e.from));
                    }
                }
            }
        }
    }

    /// The stretches leaving a node.
    pub fn out_of(&self, n: usize) -> &[usize] {
        &self.out[n]
    }

    pub fn edges(&self) -> &[Edge] {
        &self.edges
    }

    pub fn nodes(&self) -> &[NodeAt] {
        &self.nodes
    }

    /// The stop of a tool group by name.
    pub fn stop_of(&self, group: &str) -> Option<usize> {
        self.stops.get(group).copied()
    }

    /// A tool group's load ports in the order of its tools (empty when the shop lists no ports).
    pub fn ports_of(&self, group: &str) -> &[usize] {
        self.ports.get(group).map(|v| v.as_slice()).unwrap_or(&[])
    }

    /// A node as a place, for measuring along the aisles.
    pub fn place(&self, n: usize) -> Place {
        let a = &self.nodes[n];
        Place { phase: a.phase, side: a.side, bay: a.bay, x: a.x, y: a.y }
    }

    /// Where a place is on the track: a stop standing at it; for a stocker (bay `usize::MAX`) the nearest stocker
    /// spur on its lane; else the nearest point of its lane.
    pub fn node_of(&self, p: &Place) -> usize {
        let ph = p.phase.min(self.lanes.keys().map(|k| k.0).max().unwrap_or(0));
        let side = p.side.min(1);
        if p.bay == usize::MAX {
            if let Some(v) = self.spurs.get(&(ph, side)) {
                return v.iter().min_by(|a, b| (a.0 - p.x).abs().total_cmp(&(b.0 - p.x).abs())).unwrap().1;
            }
        } else if let Some(n) = self.nodes.iter().position(|q| (q.group.is_some() || q.tool.is_some()) && q.phase == p.phase && q.side == p.side && key(q.x) == key(p.x) && key(q.y) == key(p.y)) {
            return n;
        }
        self.nearest(ph, side, p.x)
    }

    /// Metres along the track from a to b.
    pub fn dist(&self, a: usize, b: usize) -> f64 {
        self.dist[b][a]
    }

    /// The first edge on the way from `at` to `to` (`None` when there already).
    pub fn next(&self, at: usize, to: usize) -> Option<usize> {
        let e = self.next[to][at];
        (e != u32::MAX).then_some(e as usize)
    }
}
