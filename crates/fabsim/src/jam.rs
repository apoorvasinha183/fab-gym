//! The track cannot jam below a count of cars (docs/DOUBLE-CHECK.md, part 2), with no simulator.
//!
//! In the engine's fleet a car blocks others only while moving: a stretch holds `floor(length / gap)` cars, at least
//! one (`FleetState::new`), a stop or junction one car while it passes or hoists, and an idle car parks off the track.
//! A car waits for the next piece along its way; when the stretch it wants is full it takes any other way out with
//! room that still leads to its target (`FleetState::way`). So a car stuck at a stop has every way out that leads to its
//! target full, and a car stuck at the front of a stretch waits for the stop at its end, held by a stuck car.
//!
//! Following stuck cars to what they wait on must come round again, so a jam holds a loop of full pieces; that loop
//! lies in one connected part of the track (a part where every stop reaches every other). From any stop of that part
//! the stuck car's target can be reached (it was reachable from the stuck stop, which every stop of the part reaches),
//! so every stretch inside the part leads to it: all of them are full, and so are their stops. A jam therefore fills a
//! whole connected part: it needs at least as many cars as the part's stops plus its stretches' cars. Fewer cars than
//! the smallest such part holds can never jam (exact, for the model above; a broken stretch is a wait for its repair,
//! and a car waiting out the gap behind another moves on once it passes, so neither is a jam).
//!
//! The explorer checks the argument by trying every placement of cars on small tracks.

use crate::track::Track;
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

/// A small track for the explorer and the loop search: nodes hold one car, links (from, to, cars) hold that many.
#[derive(Clone, Debug)]
pub struct Small {
    pub nodes: usize,
    pub links: Vec<(usize, usize, usize)>,
}

/// The smallest loop of a fab's track: its stops in order (each to the next by a stretch, the last back to the first),
/// their names, and the cars it holds.
#[derive(Clone, Debug, PartialEq)]
pub struct Loop {
    pub nodes: Vec<usize>,
    pub names: Vec<String>,
    pub cars: usize,
}

/// The cars a stretch holds, as the engine sizes it.
pub fn stretch_cars(len: f64, gap: f64) -> usize {
    ((len / gap).floor() as usize).max(1)
}

/// The loop that holds the fewest cars (a stretch's cars plus one for the stop at its end), and that number; None when
/// the track has no loop. Ties go to the fewest stops, then the lowest first stop.
pub fn smallest_loop_of(g: &Small) -> Option<(Vec<usize>, usize)> {
    let n = g.nodes;
    let mut out: Vec<Vec<(usize, usize)>> = vec![vec![]; n];
    let mut into: Vec<Vec<(usize, usize)>> = vec![vec![]; n];
    for &(a, b, c) in &g.links {
        out[a].push((b, c + 1));
        into[b].push((a, c + 1));
    }
    let mut best: Option<(usize, usize, Vec<usize>)> = None;
    for s in 0..n {
        if into[s].is_empty() {
            continue;
        }
        // shortest ways from s, by cars
        let mut dist = vec![usize::MAX; n];
        let mut prev = vec![usize::MAX; n];
        dist[s] = 0;
        let mut heap = BinaryHeap::new();
        heap.push(Reverse((0usize, s)));
        // a way already as long as the best loop cannot lead to a better one
        let limit = best.as_ref().map(|b| b.0).unwrap_or(usize::MAX);
        while let Some(Reverse((d, u))) = heap.pop() {
            if d >= limit {
                break;
            }
            if d > dist[u] {
                continue;
            }
            for &(v, w) in &out[u] {
                if d + w < dist[v] {
                    dist[v] = d + w;
                    prev[v] = u;
                    heap.push(Reverse((d + w, v)));
                }
            }
        }
        for &(u, w) in &into[s] {
            if dist[u] == usize::MAX {
                continue;
            }
            let cars = dist[u] + w;
            let mut path = vec![u];
            let mut x = u;
            while x != s {
                x = prev[x];
                path.push(x);
            }
            path.reverse();
            if u == s {
                path = vec![s];
            }
            let better = match &best {
                None => true,
                Some((c, k, _)) => (cars, path.len()) < (*c, *k),
            };
            if better {
                best = Some((cars, path.len(), path));
            }
        }
    }
    best.map(|(c, _, p)| (p, c))
}

/// The track's connected parts that hold a loop (strongly connected components with a stretch inside), each as its
/// stops and the cars it holds (its stops plus its inside stretches' cars), fewest cars first.
pub fn parts_of(g: &Small) -> Vec<(Vec<usize>, usize)> {
    let n = g.nodes;
    let mut out: Vec<Vec<usize>> = vec![vec![]; n];
    let mut back: Vec<Vec<usize>> = vec![vec![]; n];
    for &(a, b, _) in &g.links {
        out[a].push(b);
        back[b].push(a);
    }
    // Kosaraju, without recursion: finishing order on the track, then parts on the track reversed
    let mut seen = vec![false; n];
    let mut order = vec![];
    for s0 in 0..n {
        if seen[s0] {
            continue;
        }
        seen[s0] = true;
        let mut stack = vec![(s0, 0usize)];
        while let Some(top) = stack.last_mut() {
            let u = top.0;
            if top.1 < out[u].len() {
                let v = out[u][top.1];
                top.1 += 1;
                if !seen[v] {
                    seen[v] = true;
                    stack.push((v, 0));
                }
            } else {
                order.push(u);
                stack.pop();
            }
        }
    }
    let mut part = vec![usize::MAX; n];
    let mut parts: Vec<Vec<usize>> = vec![];
    for &s0 in order.iter().rev() {
        if part[s0] != usize::MAX {
            continue;
        }
        let k = parts.len();
        let mut members = vec![s0];
        part[s0] = k;
        let mut stack = vec![s0];
        while let Some(u) = stack.pop() {
            for &v in &back[u] {
                if part[v] == usize::MAX {
                    part[v] = k;
                    members.push(v);
                    stack.push(v);
                }
            }
        }
        members.sort();
        parts.push(members);
    }
    let mut cars = vec![0usize; parts.len()];
    let mut inside = vec![false; parts.len()];
    for (k, m) in parts.iter().enumerate() {
        cars[k] = m.len();
    }
    for &(a, b, c) in &g.links {
        if part[a] == part[b] {
            cars[part[a]] += c;
            inside[part[a]] = true;
        }
    }
    let mut res: Vec<(Vec<usize>, usize)> = parts.into_iter().enumerate().filter(|(k, _)| inside[*k]).map(|(k, m)| (m, cars[k])).collect();
    res.sort_by(|a, b| (a.1, a.0.first()).cmp(&(b.1, b.0.first())));
    res
}

/// The fewest cars that can jam the track: the smallest connected part's stops and stretch cars. None with no loop.
pub fn jam_number_of(g: &Small) -> Option<(Vec<usize>, usize)> {
    parts_of(g).into_iter().next()
}

/// The fewest cars that can jam a fab's track, with the gap its fleet keeps: the part's stops (named) and the number.
pub fn jam_number(tr: &Track, gap: f64) -> Option<Loop> {
    let g = Small { nodes: tr.nodes().len(), links: tr.edges().iter().map(|e| (e.from, e.to, stretch_cars(e.len, gap))).collect() };
    jam_number_of(&g).map(|(nodes, cars)| Loop { names: nodes.iter().map(|&n| tr.name(n)).collect(), nodes, cars })
}

/// The smallest loop of a fab's track, with the gap its fleet keeps: a weaker bound than `jam_number` (a jam holds a
/// loop of full pieces, and more).
pub fn smallest_loop(tr: &Track, gap: f64) -> Option<Loop> {
    let g = Small { nodes: tr.nodes().len(), links: tr.edges().iter().map(|e| (e.from, e.to, stretch_cars(e.len, gap))).collect() };
    smallest_loop_of(&g).map(|(nodes, cars)| Loop { names: nodes.iter().map(|&n| tr.name(n)).collect(), nodes, cars })
}

/// What the explorer saw: placements tried, those where no car can move, and whether such a placement follows from
/// one where a car could.
#[derive(Clone, Debug, Default)]
pub struct Explore {
    pub states: usize,
    pub jams: usize,
    pub jam_reachable: bool,
}

/// Try every placement of `cars` cars on a small track, each car always wanting to move on: a car at a stop may take
/// any way out with room (on a track where every stop reaches every other, every way out leads to its target), a car at the front of a stretch may take the stop at its end when it is free. A placement
/// where no car can move is a jam.
pub fn explore(g: &Small, cars: usize) -> Explore {
    // a placement: each node's car (0 or 1), then each link's cars
    let room: Vec<usize> = (0..g.nodes).map(|_| 1).chain(g.links.iter().map(|l| l.2)).collect();
    let mut all: Vec<Vec<usize>> = vec![];
    let mut cur = vec![0; room.len()];
    fn fill(i: usize, left: usize, room: &[usize], cur: &mut Vec<usize>, all: &mut Vec<Vec<usize>>) {
        if i == room.len() {
            if left == 0 {
                all.push(cur.clone());
            }
            return;
        }
        let rest: usize = room[i + 1..].iter().sum();
        for k in 0..=room[i].min(left) {
            if left - k <= rest {
                cur[i] = k;
                fill(i + 1, left - k, room, cur, all);
            }
        }
        cur[i] = 0;
    }
    fill(0, cars, &room, &mut cur, &mut all);
    let n = g.nodes;
    let next = |s: &Vec<usize>| -> Vec<Vec<usize>> {
        let mut out = vec![];
        for (li, &(a, b, c)) in g.links.iter().enumerate() {
            // from a stop into a stretch with room
            if s[a] == 1 && s[n + li] < c {
                let mut t = s.clone();
                t[a] = 0;
                t[n + li] += 1;
                out.push(t);
            }
            // from the front of a stretch onto a free stop
            if s[n + li] > 0 && s[b] == 0 {
                let mut t = s.clone();
                t[n + li] -= 1;
                t[b] = 1;
                out.push(t);
            }
        }
        out
    };
    let mut jam: HashMap<Vec<usize>, bool> = HashMap::new();
    for s in &all {
        jam.insert(s.clone(), next(s).is_empty());
    }
    let jams = jam.values().filter(|&&j| j).count();
    let jam_reachable = all.iter().any(|s| !jam[s] && next(s).iter().any(|t| jam[t]));
    Explore { states: all.len(), jams, jam_reachable }
}
