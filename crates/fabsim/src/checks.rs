//! The checks a layout must pass before it runs (docs/FAB-CHECKS.md): errors when it cannot run, warnings when
//! something is off. Reaching means following one-way links in their direction.

use crate::shop::Shop;
use std::collections::{HashMap, HashSet};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
}

impl Severity {
    pub fn name(self) -> &'static str {
        match self {
            Severity::Error => "error",
            Severity::Warning => "warning",
        }
    }
}

/// One finding: what is wrong, in one sentence with the fix, and what it is about (groups, tools as `GROUP#k`, node
/// ids, or links `FROM>TO`).
#[derive(Clone, Debug, PartialEq)]
pub struct Issue {
    pub severity: Severity,
    pub code: &'static str,
    pub message: String,
    pub at: Vec<String>,
}

fn err(code: &'static str, message: String, at: Vec<String>) -> Issue {
    Issue { severity: Severity::Error, code, message, at }
}

fn warn(code: &'static str, message: String, at: Vec<String>) -> Issue {
    Issue { severity: Severity::Warning, code, message, at }
}

/// Every node reachable from `from` along `adj`.
fn reach(from: &[usize], adj: &[Vec<usize>]) -> Vec<bool> {
    let mut seen = vec![false; adj.len()];
    let mut stack: Vec<usize> = vec![];
    for &s in from {
        if !seen[s] {
            seen[s] = true;
            stack.push(s);
        }
    }
    while let Some(u) = stack.pop() {
        for &v in &adj[u] {
            if !seen[v] {
                seen[v] = true;
                stack.push(v);
            }
        }
    }
    seen
}

/// The checks, errors first. A shop that read without error has every name in its plan defined.
pub fn check(shop: &Shop) -> Vec<Issue> {
    let mut issues = check_layout(shop);
    // storage made real (docs/BUILD-CONTROLS.md, part 3): a port limit needs storage for the lots beyond it
    if shop.inports.is_some_and(|n| n > 0) && shop.plan.as_ref().is_some_and(|p| p.stockers.is_empty()) {
        let n = shop.inports.unwrap_or(0);
        issues.push(warn("no_storage", format!("Machines take {n} lot{} each at their ports, but there is no storage, so the extra lots wait in an unlimited line. Place storage beside the track.", if n == 1 { "" } else { "s" }), vec![]));
    }
    issues
}

fn check_layout(shop: &Shop) -> Vec<Issue> {
    let Some(p) = &shop.plan else {
        return vec![err("no_plan", "The file has no floor plan: add nodes, links, a stop for every tool, an entry and an exit.".into(), vec![])];
    };
    let idx: HashMap<&str, usize> = p.nodes.iter().enumerate().map(|(i, n)| (n.id.as_str(), i)).collect();
    let n = p.nodes.len();
    let mut out = vec![vec![]; n];
    let mut back = vec![vec![]; n];
    for l in &p.links {
        let (a, b) = (idx[l.from.as_str()], idx[l.to.as_str()]);
        out[a].push(b);
        back[b].push(a);
    }
    let entries: Vec<usize> = p.entry.iter().map(|e| idx[e.as_str()]).collect();
    let exits: Vec<usize> = p.exit.iter().map(|e| idx[e.as_str()]).collect();
    let stocker_nodes: Vec<usize> = p.stockers.iter().map(|s| idx[s.as_str()]).collect();
    let mut issues = vec![];
    if entries.is_empty() {
        issues.push(err("no_entry", "No entry: add an `entry` record naming the node where new lots come onto the rail.".into(), vec![]));
    }
    if exits.is_empty() {
        issues.push(err("no_exit", "No exit: add an `exit` record naming the node where finished lots leave.".into(), vec![]));
    }
    let fwd = reach(&entries, &out);
    let bwd = reach(&exits, &back);

    // every tool needs its own stop, unless its group is held in a stocker
    let stores: HashSet<&str> = p.stores.iter().map(|s| s.as_str()).collect();
    let mut stops: HashMap<&str, Vec<(usize, usize)>> = HashMap::new();
    for s in &p.stops {
        stops.entry(s.group.as_str()).or_default().push((s.tool, idx[s.node.as_str()]));
    }
    for g in &shop.groups {
        if stores.contains(g.name.as_str()) {
            continue;
        }
        let have: HashSet<usize> = stops.get(g.name.as_str()).map(|v| v.iter().map(|x| x.0).collect()).unwrap_or_default();
        let missing: Vec<String> = (0..g.count).filter(|k| !have.contains(k)).map(|k| format!("{}#{}", g.name, k + 1)).collect();
        if !missing.is_empty() {
            let mut at = vec![g.name.clone()];
            let msg = format!("{} has {} tool(s) but {} without a stop ({}): add a `stop` for each, or a `store` if its lots wait in a stocker.",
                g.name, g.count, missing.len(), if missing.len() > 3 { format!("{} and {} more", missing[..3].join(", "), missing.len() - 3) } else { missing.join(", ") });
            at.extend(missing);
            issues.push(err("missing_stops", msg, at));
        }
    }
    for s in &p.stops {
        let v = idx[s.node.as_str()];
        let tool = format!("{}#{}", s.group, s.tool + 1);
        if !entries.is_empty() && !fwd[v] {
            issues.push(err("unreachable", format!("No rail from the entry reaches {tool}'s stop at {}: link it to the track.", s.node), vec![tool.clone(), s.node.clone()]));
        }
        if !exits.is_empty() && !bwd[v] {
            issues.push(err("no_way_out", format!("From {tool}'s stop at {} no rail reaches an exit: add a link onward.", s.node), vec![tool, s.node.clone()]));
        }
    }

    // each step of each route must reach the next by rail; a stored group is reached through any stocker
    let nodes_of = |g: &str| -> Vec<usize> {
        if stores.contains(g) {
            stocker_nodes.clone()
        } else {
            stops.get(g).map(|v| v.iter().map(|x| x.1).collect()).unwrap_or_default()
        }
    };
    let mut from_group: HashMap<String, Vec<bool>> = HashMap::new();
    let mut seen_pairs: HashSet<(String, String)> = HashSet::new();
    for r in &shop.routes {
        let mut seq: Vec<&str> = vec![];
        for st in &r.steps {
            if seq.last() != Some(&st.group.as_str()) {
                seq.push(st.group.as_str());
            }
        }
        if let (Some(first), false) = (seq.first(), entries.is_empty()) {
            let to = nodes_of(first);
            if !to.is_empty() && !to.iter().any(|&v| fwd[v]) && seen_pairs.insert(("entry".into(), first.to_string())) {
                issues.push(err("route_gap", format!("Route {} starts at {first}, which no rail from the entry reaches.", r.name), vec!["entry".into(), first.to_string()]));
            }
        }
        for w in seq.windows(2) {
            let (a, b) = (w[0], w[1]);
            let (fa, tb) = (nodes_of(a), nodes_of(b));
            if fa.is_empty() || tb.is_empty() || !seen_pairs.insert((a.to_string(), b.to_string())) {
                continue;
            }
            let r_a = from_group.entry(a.to_string()).or_insert_with(|| reach(&fa, &out));
            if !tb.iter().any(|&v| r_a[v]) {
                issues.push(err("route_gap", format!("Route {} goes from {a} to {b}, but no rail leads from {a}'s stops to {b}'s: add a link between them.", r.name), vec![a.to_string(), b.to_string()]));
            }
        }
        if let (Some(last), false) = (seq.last(), exits.is_empty()) {
            let fl = nodes_of(last);
            if !fl.is_empty() && !fl.iter().any(|&v| bwd[v]) && seen_pairs.insert((last.to_string(), "exit".into())) {
                issues.push(err("route_gap", format!("Route {} ends at {last}, from which no rail reaches an exit.", r.name), vec![last.to_string(), "exit".into()]));
            }
        }
    }

    // a node a vehicle can reach but never leave toward an exit
    if !entries.is_empty() && !exits.is_empty() {
        let traps: Vec<String> = (0..n).filter(|&v| fwd[v] && !bwd[v]).map(|v| p.nodes[v].id.clone()).collect();
        if !traps.is_empty() {
            let shown = if traps.len() > 5 { format!("{} and {} more", traps[..5].join(", "), traps.len() - 5) } else { traps.join(", ") };
            issues.push(err("trap", format!("{} node(s) can be reached but lead to no exit ({shown}): a vehicle that goes in never comes back out. Add a link onward.", traps.len()), traps));
        }
    }

    // warnings
    for (s, &v) in p.stockers.iter().zip(&stocker_nodes) {
        if (!entries.is_empty() && !fwd[v]) || (!exits.is_empty() && !bwd[v]) {
            issues.push(warn("stocker_unreachable", format!("The stocker at {s} is off the track's way from the entry to the exit, so no vehicle can use it."), vec![s.clone()]));
        }
    }
    if !p.prices.is_empty() {
        let priced: HashSet<&str> = p.prices.iter().map(|r| r.group.as_str()).collect();
        for g in &shop.groups {
            if !priced.contains(g.name.as_str()) && !stores.contains(g.name.as_str()) {
                issues.push(warn("no_price", format!("{} has no price, so the budget leaves it out: add a `price` record.", g.name), vec![g.name.clone()]));
            }
        }
    }
    for (i, a) in p.stations.iter().enumerate() {
        for b in &p.stations[i + 1..] {
            if a.group != b.group && a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h {
                issues.push(warn("overlap", format!("The stations of {} and {} overlap on the plan: move one.", a.group, b.group), vec![a.group.clone(), b.group.clone()]));
            }
        }
    }
    for l in &p.links {
        let (a, b) = (&p.nodes[idx[l.from.as_str()]], &p.nodes[idx[l.to.as_str()]]);
        let straight = ((a.x - b.x).powi(2) + (a.y - b.y).powi(2)).sqrt();
        if l.len + 1e-9 < straight {
            issues.push(warn("too_short", format!("The link {}>{} is {} m long but its ends are {:.2} m apart: no rail is shorter than the straight line.", l.from, l.to, l.len, straight), vec![format!("{}>{}", l.from, l.to)]));
        }
    }
    issues.sort_by_key(|i| i.severity == Severity::Warning);
    issues
}
