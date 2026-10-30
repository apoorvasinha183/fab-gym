//! A fab file's plan from today's track (docs/FAB-FILE.md): the realistic campus's drawn rails written as nodes and
//! links, every tool's port as a stop, the stocker ports, and entry and exit at the campus start. A gigafab-style
//! layout of our own design on the SMT2020 model; the plan coordinates and station boxes are for drawing only.

use crate::shop::{Link, Node, Plan, Shop, Station, Stop};
use crate::track::{NodeAt, Track};

/// The shop's track as a plan. Plan coordinates: x along the campus west to east (phases end to end with their
/// bridges), y from the spine, north negative and south positive. Each station is the box round its group's ports,
/// 1 m wider each way (assumed). No prices: the shop has none.
pub fn plan_from_track(shop: &Shop) -> Result<Plan, String> {
    let o = shop.oht.as_ref().ok_or("the shop has no layout (an oht record), so it has no track")?;
    let t = Track::from_shop(shop);
    let mut off = vec![0.0; o.lengths.len().max(1)];
    for k in 1..o.lengths.len() {
        off[k] = off[k - 1] + o.lengths[k - 1] + o.bridge;
    }
    let pos = |a: &NodeAt| -> (f64, f64) {
        let x = off.get(a.phase).copied().unwrap_or(0.0) + a.x;
        (x, if a.side == 0 { -a.y } else { a.y })
    };
    let id = |i: usize| format!("n{i}");
    let nodes: Vec<Node> = t.nodes().iter().enumerate().map(|(i, a)| {
        let (x, y) = pos(a);
        Node { id: id(i), x, y }
    }).collect();
    let links = t.edges().iter().map(|e| Link { from: id(e.from), to: id(e.to), len: e.len }).collect();
    let mut stops = vec![];
    let mut stations = vec![];
    for g in &shop.groups {
        let ports = t.ports_of(&g.name);
        for (k, n) in ports.iter().enumerate() {
            stops.push(Stop { group: g.name.clone(), tool: k, node: id(*n) });
        }
        if !ports.is_empty() {
            let pts: Vec<(f64, f64)> = ports.iter().map(|n| (nodes[*n].x, nodes[*n].y)).collect();
            let (x0, x1) = pts.iter().fold((f64::MAX, f64::MIN), |a, p| (a.0.min(p.0), a.1.max(p.0)));
            let (y0, y1) = pts.iter().fold((f64::MAX, f64::MIN), |a, p| (a.0.min(p.1), a.1.max(p.1)));
            stations.push(Station { group: g.name.clone(), x: x0 - 1.0, y: y0 - 1.0, w: x1 - x0 + 2.0, h: y1 - y0 + 2.0 });
        }
    }
    let stockers = t.nodes().iter().enumerate().filter(|(_, a)| a.stocker).map(|(i, _)| id(i)).collect();
    let start = id(t.node_of(&o.start));
    // a group the layout holds in a stocker (its place is a stocker) has no tools on the floor
    let stores = o.places.iter().filter(|(_, p)| p.is_none()).map(|(g, _)| g.clone()).collect();
    Ok(Plan { prices: vec![], nodes, links, stations, stops, stockers, entry: vec![start.clone()], exit: vec![start], stores })
}
