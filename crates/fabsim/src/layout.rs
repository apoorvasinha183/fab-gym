//! A gigafab-style campus from the SMT2020 testbed (docs/FAB-LAYOUT.md): a layout of our own
//! design, not a real fab. Every number that places a tool is assumed and named in `Config`.
//!
//! Phases sit end to end, west to east, joined by OHT bridges. In each phase one spine runs
//! west to east with bays off both sides; each bay holds one area, tools along both walls.

use std::collections::HashMap;
use std::fmt::Write as _;

use crate::engine::RunResult;
use crate::pyrandom::PyRandom;
use crate::shop::{Oht, Place, Shop};

/// The node new lots come from, in `Problem::flows`.
pub const START: usize = usize::MAX;

/// A kind of tool at its true size (docs/FAB-LOOK.md): the groups whose names start with one of
/// `prefixes`, `w` metres along the wall and `d` metres into the bay.
#[derive(Clone, Debug, PartialEq)]
pub struct Kind {
    pub name: String,
    pub prefixes: Vec<String>,
    pub w: f64,
    pub d: f64,
}

/// One tool in a block packed by kind: (group, bay, wall, y0, w, d).
type Slot = (usize, usize, usize, f64, f64, f64);

#[derive(Clone, Debug)]
pub struct Config {
    /// metres from the spine to a bay's back wall
    pub bay_depth: f64,
    pub bay_aisle: f64,
    /// service chase behind each wall of tools
    pub chase: f64,
    /// a cross aisle this wide at mid-depth on every wall of tools, so a chase has a door into the fab area
    /// half way along (docs/DESIGN-DEV.md); 0 for none
    pub cross: f64,
    pub spine: f64,
    pub bridge: f64,
    /// the most the two sides of a phase may differ in length (the optimiser's plans)
    pub balance: f64,
    /// (area, metres along the wall, metres into the chase)
    pub footprints: Vec<(String, f64, f64)>,
    pub default_footprint: (f64, f64),
    /// areas with no machines, held in stockers on the spine
    pub stocker_areas: Vec<String>,
    /// a group whose name contains the text goes to that phase (first match wins)
    pub phase_rules: Vec<(String, usize)>,
    pub default_phase: usize,
    /// tools by kind at true size; when empty, by area (`footprints`)
    pub kinds: Vec<Kind>,
    /// move each group to the phase that sends it most of its lots (by the name rule's phases)
    pub phase_by_flow: bool,
    /// groups whose name contains one of these texts keep their name rule's phase under `phase_by_flow`
    pub pin: Vec<String>,
    /// the OHT: minutes per move, metres per minute, minutes of jitter
    pub overhead: f64,
    pub speed: f64,
    pub jitter: f64,
    /// the optimiser: moves tried per restart, restarts, seed
    pub iters: usize,
    pub restarts: usize,
    pub seed: u64,
}

impl Config {
    /// The assumed numbers of docs/FAB-LAYOUT.md.
    pub fn gigafab() -> Config {
        let fp = |a: &str, w: f64, d: f64| (a.to_string(), w, d);
        Config {
            bay_depth: 60.0,
            bay_aisle: 3.5,
            chase: 1.5,
            cross: 0.0,
            spine: 8.0,
            bridge: 60.0,
            balance: 40.0,
            footprints: vec![
                fp("Litho", 5.0, 12.0),
                fp("Implant", 5.0, 10.0),
                fp("Planar", 4.0, 7.0),
                fp("Dry_Etch", 3.5, 6.0),
                fp("Dielectric", 3.5, 6.0),
                fp("TF", 3.5, 6.0),
                fp("Wet_Etch", 3.0, 8.0),
                fp("Diffusion", 2.5, 7.0),
                fp("Def_Met", 3.0, 4.0),
                fp("Litho_Met", 3.0, 4.0),
                fp("TF_Met", 3.0, 4.0),
            ],
            default_footprint: (3.5, 6.0),
            stocker_areas: vec!["Delay_32".into()],
            phase_rules: vec![("_BE_".into(), 1)],
            default_phase: 0,
            kinds: vec![],
            phase_by_flow: false,
            pin: vec![],
            overhead: 4.0,
            speed: 150.0,
            jitter: 1.0,
            iters: 200_000,
            restarts: 4,
            seed: 1,
        }
    }

    /// The size book of docs/FAB-LOOK.md (viz/look/sizes.json): tools at true size by kind, and
    /// each group in the phase that sends it most of its lots. All sizes assumed unless the book
    /// cites them.
    pub fn realistic() -> Config {
        let k = |name: &str, prefixes: &[&str], w: f64, d: f64| Kind {
            name: name.into(),
            prefixes: prefixes.iter().map(|p| p.to_string()).collect(),
            w,
            d,
        };
        Config {
            kinds: vec![
                k("metrology", &["LithoMet_", "Litho_REG_", "TF_Met_"], 1.8, 2.8),
                k("track", &["LithoTrack_"], 3.5, 7.0),
                k("scanner", &["Litho_"], 4.5, 11.0),
                k("inspection", &["DefMet_", "DefMEt_"], 2.2, 3.4),
                k("etch", &["DE_"], 3.5, 5.5),
                k("deposition", &["Dielectric_", "TF_"], 3.5, 5.5),
                k("epitaxy", &["EPI_"], 4.0, 6.0),
                k("furnace", &["Diffusion_"], 1.5, 2.0),
                k("implanter", &["Implant_"], 3.6, 8.1),
                k("polisher", &["Planar_"], 3.0, 6.0),
                k("wet_bench", &["WE_"], 2.5, 10.0),
                k("stocker", &["Delay_"], 3.0, 12.0),
            ],
            phase_by_flow: true,
            ..Config::gigafab()
        }
    }

    /// The first kind with a prefix the group's name starts with.
    pub fn kind_of(&self, group: &str) -> Option<&Kind> {
        self.kinds
            .iter()
            .find(|k| k.prefixes.iter().any(|p| group.starts_with(p.as_str())))
    }

    fn footprint(&self, area: &str) -> (f64, f64) {
        self.footprints
            .iter()
            .find(|f| f.0 == area)
            .map(|f| (f.1, f.2))
            .unwrap_or(self.default_footprint)
    }

    fn bay_width(&self, area: &str) -> f64 {
        2.0 * (self.footprint(area).1 + self.chase) + self.bay_aisle
    }

    /// tools along one wall of a bay
    fn per_wall(&self, area: &str) -> usize {
        ((self.bay_depth / self.footprint(area).0).floor() as usize).max(1)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Block {
    pub area: String,
    pub groups: Vec<usize>,
}

/// For each phase, the blocks on the north side (0) and the south side (1), west to east.
#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub phases: Vec<[Vec<Block>; 2]>,
}

/// How far a load port stands in front of its tool (metres): the kit's etch port, as the drawings use it
/// (viz/look/scene.py `port_v`); assumed for every kind.
pub const PORT_V: f64 = 0.225;

#[derive(Clone, Debug, PartialEq)]
pub struct Bay {
    pub phase: usize,
    pub side: usize,
    pub area: String,
    pub x0: f64,
    pub x1: f64,
}

/// One tool's rectangle: x along the spine, y metres deep from it.
#[derive(Clone, Debug, PartialEq)]
pub struct ToolBox {
    pub group: usize,
    pub phase: usize,
    pub side: usize,
    pub bay: usize,
    pub x0: f64,
    pub x1: f64,
    pub y0: f64,
    pub y1: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Campus {
    pub bays: Vec<Bay>,
    pub tools: Vec<ToolBox>,
    /// per group; `None` for a stocker
    pub places: Vec<Option<Place>>,
    pub lengths: Vec<f64>,
    /// per phase, the north and south sides' lengths
    pub sides: Vec<[f64; 2]>,
    pub start: Place,
}

/// One step of a lot in the exported window.
#[derive(Clone, Debug, PartialEq)]
pub struct TraceStep {
    pub arrive: f64,
    pub start: f64,
    pub end: f64,
    /// index into `Campus::tools`; `None` in a stocker
    pub tool: Option<usize>,
    pub group: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct LotTrace {
    pub id: String,
    pub hot: bool,
    /// the step before the window's first: when it ended and on which tool
    pub prev: Option<(f64, Option<usize>)>,
    pub steps: Vec<TraceStep>,
}

pub struct Problem {
    cfg: Config,
    names: Vec<String>,
    counts: Vec<usize>,
    areas: Vec<String>,
    phase: Vec<Option<usize>>,
    nphases: usize,
    flows: Vec<(usize, usize, f64)>,
    /// per group with tool kinds: (along the wall, into the bay); `None` by area
    size: Vec<Option<(f64, f64)>>,
}

impl Problem {
    /// `areas` gives each group's area (as `smt2020::areas` reads it).
    pub fn new(shop: &Shop, areas: &[(String, String)], cfg: &Config) -> Result<Problem, String> {
        let area_of: HashMap<&str, &str> = areas
            .iter()
            .map(|(g, a)| (g.as_str(), a.as_str()))
            .collect();
        let mut out_areas = vec![];
        let mut phase = vec![];
        for g in &shop.groups {
            let a = *area_of
                .get(g.name.as_str())
                .ok_or_else(|| format!("no area for tool group {:?}", g.name))?;
            out_areas.push(a.to_string());
            phase.push(if cfg.stocker_areas.iter().any(|s| s == a) {
                None
            } else {
                Some(
                    cfg.phase_rules
                        .iter()
                        .find(|r| g.name.contains(&r.0))
                        .map(|r| r.1)
                        .unwrap_or(cfg.default_phase),
                )
            });
        }
        let nphases = phase.iter().flatten().max().map(|m| m + 1).unwrap_or(1);
        let gidx: HashMap<&str, usize> = shop
            .groups
            .iter()
            .enumerate()
            .map(|(i, g)| (g.name.as_str(), i))
            .collect();
        let mut acc: HashMap<(usize, usize), f64> = HashMap::new();
        for rel in &shop.releases {
            if rel.every <= 0.0 {
                continue;
            }
            let rate = 1440.0 / rel.every;
            let route = shop
                .route(&rel.route)
                .ok_or_else(|| format!("no route {:?}", rel.route))?;
            // where the lot last was, as a distribution over places
            let mut dist: Vec<(usize, f64)> = vec![(START, 1.0)];
            for st in &route.steps {
                let g = *gidx
                    .get(st.group.as_str())
                    .ok_or_else(|| format!("no tool group {:?}", st.group))?;
                if phase[g].is_none() {
                    continue;
                }
                let p = st.sample.unwrap_or(1.0);
                for &(from, w) in &dist {
                    *acc.entry((from, g)).or_insert(0.0) += rate * w * p;
                }
                if p >= 1.0 {
                    dist = vec![(g, 1.0)];
                } else {
                    for d in &mut dist {
                        d.1 *= 1.0 - p;
                    }
                    match dist.iter_mut().find(|d| d.0 == g) {
                        Some(d) => d.1 += p,
                        None => dist.push((g, p)),
                    }
                }
            }
        }
        let mut flows: Vec<(usize, usize, f64)> =
            acc.into_iter().map(|((a, b), r)| (a, b, r)).collect();
        flows.sort_by(|x, y| (x.0, x.1).cmp(&(y.0, y.1)));
        if cfg.phase_by_flow {
            // each group goes to the phase that sends it most of its lots, counting each sender
            // where it sits now (new lots come from phase 1); ties stay; group by group until no
            // group moves (docs/FAB-LOOK.md)
            for _sweep in 0..100 {
                let mut moved = false;
                for g in 0..phase.len() {
                    let Some(own) = phase[g] else { continue };
                    if cfg.pin.iter().any(|t| shop.groups[g].name.contains(t.as_str())) {
                        continue;
                    }
                    let mut inflow = vec![0.0; nphases];
                    for f in flows.iter().filter(|f| f.1 == g) {
                        let from = if f.0 == START {
                            0
                        } else {
                            phase[f.0].unwrap_or(0)
                        };
                        inflow[from] += f.2;
                    }
                    let mut best = own;
                    for (ph, &w) in inflow.iter().enumerate() {
                        if w > inflow[best] {
                            best = ph;
                        }
                    }
                    if best != own {
                        phase[g] = Some(best);
                        moved = true;
                    }
                }
                if !moved {
                    break;
                }
            }
        }
        let mut size = vec![None; shop.groups.len()];
        if !cfg.kinds.is_empty() {
            for (g, gr) in shop.groups.iter().enumerate() {
                if phase[g].is_some() {
                    let k = cfg
                        .kind_of(&gr.name)
                        .ok_or_else(|| format!("no tool kind for group {:?}", gr.name))?;
                    size[g] = Some((k.w, k.d));
                }
            }
        }
        Ok(Problem {
            cfg: cfg.clone(),
            names: shop.groups.iter().map(|g| g.name.clone()).collect(),
            counts: shop.groups.iter().map(|g| g.count).collect(),
            areas: out_areas,
            phase,
            nphases,
            flows,
            size,
        })
    }

    /// Lots per day from one group to another (`START` for new lots), sorted.
    pub fn flows(&self) -> &[(usize, usize, f64)] {
        &self.flows
    }

    pub fn phase_of(&self, g: usize) -> Option<usize> {
        self.phase[g]
    }

    /// The number of tool groups.
    pub fn len(&self) -> usize {
        self.names.len()
    }

    pub fn is_empty(&self) -> bool {
        self.names.is_empty()
    }

    pub fn name(&self, g: usize) -> &str {
        &self.names[g]
    }

    pub fn area_of(&self, g: usize) -> &str {
        &self.areas[g]
    }

    fn phase_or_start(&self, g: usize) -> usize {
        if g == START {
            0
        } else {
            self.phase[g].unwrap_or(0)
        }
    }

    /// Lots per day crossing between phases.
    pub fn crossings(&self) -> f64 {
        self.flows
            .iter()
            .filter(|f| self.phase_or_start(f.0) != self.phase_or_start(f.1))
            .map(|f| f.2)
            .sum()
    }

    /// Areas in name order, each on whichever side is shorter so far; groups in name order.
    pub fn plain(&self) -> Plan {
        let mut phases: Vec<[Vec<Block>; 2]> =
            (0..self.nphases).map(|_| [vec![], vec![]]).collect();
        for (ph, sides) in phases.iter_mut().enumerate() {
            let mut areas: Vec<&str> = (0..self.names.len())
                .filter(|&g| self.phase[g] == Some(ph))
                .map(|g| self.areas[g].as_str())
                .collect();
            areas.sort();
            areas.dedup();
            let mut len = [0.0, 0.0];
            for a in areas {
                let mut groups: Vec<usize> = (0..self.names.len())
                    .filter(|&g| self.phase[g] == Some(ph) && self.areas[g] == a)
                    .collect();
                groups.sort_by(|x, y| self.names[*x].cmp(&self.names[*y]));
                let side = if len[1] < len[0] { 1 } else { 0 };
                let b = Block {
                    area: a.to_string(),
                    groups,
                };
                len[side] += self.block_length(&b);
                sides[side].push(b);
            }
        }
        Plan { phases }
    }

    /// With tool kinds: a block's bay width, its bays, and each tool as (group, bay, wall, y0,
    /// w, d). Wall 0 fills from the spine outward, wall 1 from the bay's end back; a bay is as
    /// wide as its block's deepest tool on both walls plus the aisle.
    fn pack_block(&self, b: &Block) -> (f64, usize, Vec<Slot>) {
        let cfg = &self.cfg;
        let deepest = b
            .groups
            .iter()
            .filter_map(|&g| self.size[g])
            .map(|s| s.1)
            .fold(0.0, f64::max);
        let bw = 2.0 * (deepest + cfg.chase) + cfg.bay_aisle;
        let mut out = vec![];
        let (mut bay, mut wall, mut used) = (0usize, 0usize, 0.0f64);
        for &g in &b.groups {
            let (w, d) = self.size[g].expect("a tool kind");
            for _ in 0..self.counts[g] {
                loop {
                    if used > 0.0 && used + w > cfg.bay_depth + 1e-9 {
                        if wall == 0 {
                            wall = 1;
                        } else {
                            wall = 0;
                            bay += 1;
                        }
                        used = 0.0;
                        continue;
                    }
                    // the cross aisle: no tool across it, the wall carries on beyond it
                    let g0 = (cfg.bay_depth - cfg.cross) / 2.0;
                    if cfg.cross > 0.0 && used < g0 + cfg.cross - 1e-9 && used + w > g0 + 1e-9 {
                        used = g0 + cfg.cross;
                        continue;
                    }
                    break;
                }
                let y0 = if wall == 0 {
                    used
                } else {
                    cfg.bay_depth - used - w
                };
                out.push((g, bay, wall, y0, w, d));
                used += w;
            }
        }
        let n = if out.is_empty() { 0 } else { bay + 1 };
        (bw, n, out)
    }

    fn block_length(&self, b: &Block) -> f64 {
        if !self.cfg.kinds.is_empty() {
            let (bw, n, _) = self.pack_block(b);
            return n as f64 * bw;
        }
        let tools: usize = b.groups.iter().map(|&g| self.counts[g]).sum();
        let per_bay = 2 * self.cfg.per_wall(&b.area);
        tools.div_ceil(per_bay) as f64 * self.cfg.bay_width(&b.area)
    }

    /// Lay a plan out. With `boxes` false only the places and lengths are worked out.
    fn lay(&self, plan: &Plan, boxes: bool) -> Campus {
        let cfg = &self.cfg;
        let mut c = Campus {
            bays: vec![],
            tools: vec![],
            places: vec![None; self.names.len()],
            lengths: vec![],
            sides: vec![],
            start: Place {
                phase: 0,
                side: 0,
                bay: usize::MAX,
                x: 0.0,
                y: 0.0,
            },
        };
        // per group: sums of x and y, and tools per bay
        let mut sx = vec![0.0; self.names.len()];
        let mut sy = vec![0.0; self.names.len()];
        let mut by_bay: Vec<Vec<(usize, usize)>> = vec![vec![]; self.names.len()];
        let mut nbays = 0usize;
        for (ph, sides) in plan.phases.iter().enumerate() {
            let mut lens = [0.0, 0.0];
            for (side, blocks) in sides.iter().enumerate() {
                let mut x = 0.0;
                for b in blocks {
                    if !cfg.kinds.is_empty() {
                        let (bw, n, tools) = self.pack_block(b);
                        let first_bay = nbays;
                        for &(g, bay, wall, y0, w, d) in &tools {
                            let bx0 = x + bay as f64 * bw;
                            sx[g] += bx0 + bw / 2.0;
                            sy[g] += y0 + w / 2.0;
                            let id = first_bay + bay;
                            match by_bay[g].iter_mut().find(|e| e.0 == id) {
                                Some(e) => e.1 += 1,
                                None => by_bay[g].push((id, 1)),
                            }
                            if boxes {
                                // fronts on the aisle line, under the hoist rail; the chase
                                // behind the deepest tool, more floor behind shallower ones
                                let tx0 = if wall == 0 {
                                    bx0 + bw / 2.0 - cfg.bay_aisle / 2.0 - d
                                } else {
                                    bx0 + bw / 2.0 + cfg.bay_aisle / 2.0
                                };
                                c.tools.push(ToolBox {
                                    group: g,
                                    phase: ph,
                                    side,
                                    bay: id,
                                    x0: tx0,
                                    x1: tx0 + d,
                                    y0,
                                    y1: y0 + w,
                                });
                            }
                        }
                        if boxes {
                            for i in 0..n {
                                c.bays.push(Bay {
                                    phase: ph,
                                    side,
                                    area: b.area.clone(),
                                    x0: x + i as f64 * bw,
                                    x1: x + (i + 1) as f64 * bw,
                                });
                            }
                        }
                        nbays += n;
                        x += n as f64 * bw;
                        continue;
                    }
                    let (w, d) = cfg.footprint(&b.area);
                    let m = cfg.per_wall(&b.area);
                    let bw = cfg.bay_width(&b.area);
                    let mut k = 0usize;
                    let first_bay = nbays;
                    let mut last_bay = None;
                    for &g in &b.groups {
                        for _ in 0..self.counts[g] {
                            let (bay, j) = (k / (2 * m), k % (2 * m));
                            let bx0 = x + bay as f64 * bw;
                            let (wall, slot) = if j < m { (0, j) } else { (1, 2 * m - 1 - j) };
                            let y0 = slot as f64 * w;
                            sx[g] += bx0 + bw / 2.0;
                            sy[g] += y0 + w / 2.0;
                            let id = first_bay + bay;
                            match by_bay[g].iter_mut().find(|e| e.0 == id) {
                                Some(e) => e.1 += 1,
                                None => by_bay[g].push((id, 1)),
                            }
                            if boxes {
                                let tx0 = if wall == 0 {
                                    bx0 + cfg.chase
                                } else {
                                    bx0 + cfg.chase + d + cfg.bay_aisle
                                };
                                c.tools.push(ToolBox {
                                    group: g,
                                    phase: ph,
                                    side,
                                    bay: id,
                                    x0: tx0,
                                    x1: tx0 + d,
                                    y0,
                                    y1: y0 + w,
                                });
                            }
                            last_bay = Some(bay);
                            k += 1;
                        }
                    }
                    let n = last_bay.map(|b| b + 1).unwrap_or(0);
                    if boxes {
                        for i in 0..n {
                            c.bays.push(Bay {
                                phase: ph,
                                side,
                                area: b.area.clone(),
                                x0: x + i as f64 * bw,
                                x1: x + (i + 1) as f64 * bw,
                            });
                        }
                    }
                    nbays += n;
                    x += n as f64 * bw;
                }
                lens[side] = x;
            }
            c.lengths.push(lens[0].max(lens[1]));
            c.sides.push(lens);
            for (side, blocks) in sides.iter().enumerate() {
                for b in blocks {
                    for &g in &b.groups {
                        let n = self.counts[g] as f64;
                        if n == 0.0 {
                            continue;
                        }
                        let bay = by_bay[g]
                            .iter()
                            .max_by(|a, b| a.1.cmp(&b.1).then(b.0.cmp(&a.0)))
                            .map(|e| e.0)
                            .unwrap_or(usize::MAX);
                        c.places[g] = Some(Place {
                            phase: ph,
                            side,
                            bay,
                            x: sx[g] / n,
                            y: sy[g] / n,
                        });
                    }
                }
            }
        }
        c
    }

    pub fn pack(&self, plan: &Plan) -> Campus {
        self.lay(plan, true)
    }

    /// The x of a bay's two rails, over wall 0's and wall 1's load ports, as the drawings put them (viz/look/scene.py:
    /// the aisle's edge plus how far a port stands in front of its tool).
    fn rails_x(&self, b: &Bay) -> [f64; 2] {
        let cx = (b.x0 + b.x1) / 2.0;
        let d = self.cfg.bay_aisle / 2.0 + PORT_V;
        [cx - d, cx + d]
    }

    /// Each tool's load port (docs/FLEET.md): under the rail of its wall, at the middle of the tool along the bay,
    /// grouped by tool group in the order the campus placed them.
    pub fn ports(&self, c: &Campus) -> Vec<(String, Place)> {
        let mut out = vec![];
        for g in 0..self.names.len() {
            for tb in c.tools.iter().filter(|t| t.group == g) {
                let b = &c.bays[tb.bay];
                let wall = if (tb.x0 + tb.x1) / 2.0 < (b.x0 + b.x1) / 2.0 { 0 } else { 1 };
                out.push((self.names[g].clone(), Place { phase: tb.phase, side: tb.side, bay: tb.bay, x: self.rails_x(b)[wall], y: (tb.y0 + tb.y1) / 2.0 }));
            }
        }
        out
    }

    /// Each bay's two rails and the depth where they join (docs/FLEET.md).
    pub fn bayrails(&self, c: &Campus) -> Vec<crate::shop::BayRail> {
        c.bays
            .iter()
            .enumerate()
            .map(|(i, b)| crate::shop::BayRail { bay: i, phase: b.phase, side: b.side, x: self.rails_x(b), far: self.cfg.bay_depth })
            .collect()
    }

    /// The OHT record for a campus, with the config's hoist numbers.
    pub fn oht(&self, c: &Campus) -> Oht {
        Oht {
            overhead: self.cfg.overhead,
            speed: self.cfg.speed,
            jitter: self.cfg.jitter,
            bridge: self.cfg.bridge,
            spine: self.cfg.spine,
            lengths: c.lengths.clone(),
            start: c.start,
            places: self
                .names
                .iter()
                .cloned()
                .zip(c.places.iter().copied())
                .collect(),
        }
    }

    fn metres(&self, c: &Campus, o: &Oht) -> f64 {
        let at = |g: usize| {
            if g == START {
                Some(c.start)
            } else {
                c.places[g]
            }
        };
        self.flows
            .iter()
            .map(|&(a, b, r)| match (at(a), at(b)) {
                (Some(p), Some(q)) => r * o.distance(&p, &q),
                _ => 0.0,
            })
            .sum()
    }

    /// OHT metres per day carried under a campus (exact for the stated flows).
    pub fn cost(&self, c: &Campus) -> f64 {
        self.metres(c, &self.oht(c))
    }

    fn objective(&self, plan: &Plan, weight: f64) -> f64 {
        let c = self.lay(plan, false);
        let excess: f64 = c
            .sides
            .iter()
            .map(|s| ((s[0] - s[1]).abs() - self.cfg.balance).max(0.0))
            .sum();
        self.metres(&c, &self.oht(&c)) + weight * excess
    }

    /// Simulated annealing from the plain plan: block order and sides, group order inside blocks.
    /// A heuristic; the best plan over the restarts is kept. Same config, same plan.
    pub fn optimise(&self) -> Plan {
        let plain = self.plain();
        let base = self.cost(&self.pack(&plain)).max(1.0);
        // a metre of imbalance past the allowance costs 1% of the plain plan's metres
        let weight = 0.01 * base;
        let mut best = plain.clone();
        let mut best_f = self.objective(&plain, weight);
        for r in 0..self.cfg.restarts.max(1) {
            let mut rng = PyRandom::from_str_seed(&format!("{}/layout/{}", self.cfg.seed, r));
            let mut cur = plain.clone();
            let mut f = self.objective(&cur, weight);
            let t0 = 0.02 * f;
            let t1 = 1e-5 * f;
            let n = self.cfg.iters.max(1);
            for i in 0..n {
                let temp = t0 * (t1 / t0).powf(i as f64 / n as f64);
                let Some(next) = self.neighbour(&cur, &mut rng) else {
                    break;
                };
                let g = self.objective(&next, weight);
                if g <= f || rng.random() < ((f - g) / temp).exp() {
                    cur = next;
                    f = g;
                    if f < best_f - 1e-9 {
                        best_f = f;
                        best = cur.clone();
                    }
                }
            }
        }
        best
    }

    fn neighbour(&self, plan: &Plan, rng: &mut PyRandom) -> Option<Plan> {
        let pick = |rng: &mut PyRandom, n: usize| {
            ((rng.random() * n as f64) as usize).min(n.saturating_sub(1))
        };
        let phases: Vec<usize> = (0..plan.phases.len())
            .filter(|&p| plan.phases[p][0].len() + plan.phases[p][1].len() > 0)
            .collect();
        if phases.is_empty() {
            return None;
        }
        let mut p = plan.clone();
        let ph = phases[pick(rng, phases.len())];
        let sides = &mut p.phases[ph];
        let nblocks = sides[0].len() + sides[1].len();
        let locate = |sides: &[Vec<Block>; 2], k: usize| {
            if k < sides[0].len() {
                (0, k)
            } else {
                (1, k - sides[0].len())
            }
        };
        match pick(rng, 4) {
            0 => {
                // move a block to any place on either side
                let (s, i) = locate(sides, pick(rng, nblocks));
                let b = sides[s].remove(i);
                let to = pick(rng, 2);
                let j = pick(rng, sides[to].len() + 1);
                sides[to].insert(j, b);
            }
            1 => {
                // swap two blocks
                let (s1, i1) = locate(sides, pick(rng, nblocks));
                let (s2, i2) = locate(sides, pick(rng, nblocks));
                if (s1, i1) == (s2, i2) {
                    return Some(p);
                }
                let a = sides[s1][i1].clone();
                let b = std::mem::replace(&mut sides[s2][i2], a);
                sides[s1][i1] = b;
            }
            k => {
                // swap or move groups inside one block
                let (s, i) = locate(sides, pick(rng, nblocks));
                let gs = &mut sides[s][i].groups;
                if gs.len() < 2 {
                    return Some(p);
                }
                let a = pick(rng, gs.len());
                let b = pick(rng, gs.len());
                if k == 2 {
                    gs.swap(a, b);
                } else {
                    let g = gs.remove(a);
                    gs.insert(b.min(gs.len()), g);
                }
            }
        }
        Some(p)
    }

    /// Where each phase starts along the world's x axis (metres east).
    pub fn offsets(&self, c: &Campus) -> Vec<f64> {
        let mut x = 0.0;
        c.lengths
            .iter()
            .map(|l| {
                let o = x;
                x += l + self.cfg.bridge;
                o
            })
            .collect()
    }

    /// World metres (east, north) of a point given by phase, side, x along the spine and depth.
    pub fn world(&self, c: &Campus, phase: usize, side: usize, x: f64, y: f64) -> (f64, f64) {
        let d = self.cfg.spine / 2.0 + y;
        (self.offsets(c)[phase] + x, if side == 0 { d } else { -d })
    }

    /// The run's steps that touch the window [from, to], per lot, for the 3D views. The run
    /// must have been recorded (`RunOptions::record`) on a shop laid out as `c`.
    pub fn trace(&self, c: &Campus, r: &RunResult, from: f64, to: f64) -> Vec<LotTrace> {
        let gidx: HashMap<&str, usize> = self.names.iter().enumerate().map(|(i, n)| (n.as_str(), i)).collect();
        let mut boxes: Vec<Vec<usize>> = vec![vec![]; self.names.len()];
        for (i, t) in c.tools.iter().enumerate() {
            boxes[t.group].push(i);
        }
        let mut seen = vec![0usize; self.names.len()];
        let tool_of: Vec<(usize, Option<usize>)> = r
            .tools
            .iter()
            .map(|t| {
                let g = gidx[t.group.as_str()];
                let k = seen[g];
                seen[g] += 1;
                (g, boxes[g].get(k).copied())
            })
            .collect();
        let lowest = r.lots.iter().map(|l| l.priority).fold(f64::INFINITY, f64::min);
        let mut per_lot: Vec<Vec<usize>> = vec![vec![]; r.lots.len()];
        for (i, t) in r.trace.iter().enumerate() {
            per_lot[t.lot as usize].push(i);
        }
        let mut out = vec![];
        for (li, idx) in per_lot.iter().enumerate() {
            let mut steps = vec![];
            let mut prev = None;
            for &i in idx {
                let t = &r.trace[i];
                let (g, tool) = tool_of[t.tool as usize];
                if t.end >= from && t.arrive <= to {
                    steps.push(TraceStep { arrive: t.arrive, start: t.start, end: t.end, tool, group: g });
                } else if t.end < from {
                    prev = Some((t.end, tool));
                }
            }
            if !steps.is_empty() {
                steps.sort_by(|a, b| a.start.partial_cmp(&b.start).unwrap());
                let l = &r.lots[li];
                out.push(LotTrace { id: l.id.clone(), hot: l.priority > lowest, prev, steps });
            }
        }
        out
    }

    /// `trace` as JSON, with each tool's state through the window (0 working, 1 idle,
    /// 2 maintenance, 3 broken down) and the world offsets.
    pub fn trace_json(&self, c: &Campus, r: &RunResult, from: f64, to: f64) -> String {
        let n = |x: f64| format!("{}", (x * 100.0).round() / 100.0);
        let lots = self.trace(c, r, from, to);
        let gidx: HashMap<&str, usize> = self.names.iter().enumerate().map(|(i, n)| (n.as_str(), i)).collect();
        let mut boxes: Vec<Vec<usize>> = vec![vec![]; self.names.len()];
        for (i, t) in c.tools.iter().enumerate() {
            boxes[t.group].push(i);
        }
        let mut seen = vec![0usize; self.names.len()];
        let tool_of: Vec<Option<usize>> = r
            .tools
            .iter()
            .map(|t| {
                let g = gidx[t.group.as_str()];
                seen[g] += 1;
                boxes[g].get(seen[g] - 1).copied()
            })
            .collect();
        let code = |s: &str| match s {
            "productive" => 0,
            "standby" => 1,
            "scheduled down" => 2,
            _ => 3,
        };
        let mut at_from: HashMap<usize, u8> = HashMap::new();
        let mut changes = vec![];
        for st in &r.states {
            let Some(b) = tool_of[st.tool_index as usize] else { continue };
            if st.time <= from {
                at_from.insert(b, code(st.state));
            } else if st.time <= to {
                changes.push((st.time, b, code(st.state)));
            }
        }
        let mut o = String::from("{\"model\":\"SMT2020\",");
        o.push_str("\"what\":\"a simulated run from the SMT2020 testbed, on a gigafab-style layout of our own design; not a real fab\",");
        let _ = write!(
            o,
            "\"from\":{},\"to\":{},\"spine\":{},\"bridge\":{},\"offsets\":[{}],\"lengths\":[{}],\"states\":[",
            n(from),
            n(to),
            n(self.cfg.spine),
            n(self.cfg.bridge),
            self.offsets(c).iter().map(|x| n(*x)).collect::<Vec<_>>().join(","),
            c.lengths.iter().map(|x| n(*x)).collect::<Vec<_>>().join(",")
        );
        let mut first = true;
        let mut start: Vec<(usize, u8)> = at_from.into_iter().collect();
        start.sort();
        for (b, k) in start {
            let _ = write!(o, "{}[{},{},{}]", if first { "" } else { "," }, n(from), b, k);
            first = false;
        }
        for (t, b, k) in changes {
            let _ = write!(o, "{}[{},{},{}]", if first { "" } else { "," }, n(t), b, k);
            first = false;
        }
        o.push_str("],\"lots\":[");
        let tool = |t: Option<usize>| t.map(|x| x as i64).unwrap_or(-1);
        for (i, l) in lots.iter().enumerate() {
            let _ = write!(o, "{}{{\"id\":\"{}\",\"hot\":{},\"prev\":", if i > 0 { "," } else { "" }, l.id, l.hot);
            match l.prev {
                None => o.push_str("null"),
                Some((t, b)) => {
                    let _ = write!(o, "[{},{}]", n(t), tool(b));
                }
            }
            o.push_str(",\"steps\":[");
            for (k, st) in l.steps.iter().enumerate() {
                let _ = write!(o, "{}[{},{},{},{},{}]", if k > 0 { "," } else { "" }, n(st.arrive), n(st.start), n(st.end), tool(st.tool), st.group);
            }
            o.push_str("]}");
        }
        o.push_str("]}");
        o
    }

    /// The campus as JSON for the viewers: the assumed numbers, groups, flows and each plan.
    pub fn to_json(&self, plans: &[(&str, &Campus)]) -> String {
        let cfg = &self.cfg;
        let n = |x: f64| {
            if x.is_finite() {
                format!("{}", (x * 1000.0).round() / 1000.0)
            } else {
                "null".into()
            }
        };
        let mut o = String::from("{\"model\":\"SMT2020\",");
        o.push_str("\"what\":\"a gigafab-style layout of our own design from the SMT2020 testbed; not a real fab; every placement number is assumed\",");
        let _ = write!(
            o,
            "\"assumed\":{{\"bay_depth\":{},\"bay_aisle\":{},\"chase\":{},\"spine\":{},\"bridge\":{},\"balance\":{},\"overhead_min\":{},\"speed_m_per_min\":{},\"jitter_min\":{},",
            n(cfg.bay_depth),
            n(cfg.bay_aisle),
            n(cfg.chase),
            n(cfg.spine),
            n(cfg.bridge),
            n(cfg.balance),
            n(cfg.overhead),
            n(cfg.speed),
            n(cfg.jitter)
        );
        if cfg.cross > 0.0 {
            // only when used, so the layouts written before it stay byte for byte the same
            let _ = write!(o, "\"cross\":{},", n(cfg.cross));
        }
        o.push_str("\"footprints\":{");
        let mut areas: Vec<&str> = self.areas.iter().map(|s| s.as_str()).collect();
        areas.sort();
        areas.dedup();
        for (i, a) in areas.iter().enumerate() {
            let (w, d) = cfg.footprint(a);
            let _ = write!(
                o,
                "{}\"{}\":[{},{}]",
                if i > 0 { "," } else { "" },
                a,
                n(w),
                n(d)
            );
        }
        o.push('}');
        if cfg.phase_by_flow || !cfg.kinds.is_empty() {
            let _ = write!(
                o,
                ",\"phase_rule\":\"{}\",\"kinds\":{{",
                if cfg.phase_by_flow {
                    "where its lots come from"
                } else {
                    "by name"
                }
            );
            for (i, k) in cfg.kinds.iter().enumerate() {
                let _ = write!(
                    o,
                    "{}\"{}\":{{\"w\":{},\"d\":{},\"prefixes\":[{}]}}",
                    if i > 0 { "," } else { "" },
                    k.name,
                    n(k.w),
                    n(k.d),
                    k.prefixes
                        .iter()
                        .map(|p| format!("\"{p}\""))
                        .collect::<Vec<_>>()
                        .join(",")
                );
            }
            o.push('}');
        }
        o.push_str("},\"groups\":[");
        for g in 0..self.names.len() {
            let _ = write!(
                o,
                "{}{{\"name\":\"{}\",\"area\":\"{}\",\"phase\":{},\"tools\":{}}}",
                if g > 0 { "," } else { "" },
                self.names[g],
                self.areas[g],
                self.phase[g]
                    .map(|p| p.to_string())
                    .unwrap_or_else(|| "null".into()),
                self.counts[g]
            );
        }
        o.push_str("],\"flows\":[");
        for (i, &(a, b, r)) in self.flows.iter().enumerate() {
            let fa = if a == START {
                "-1".to_string()
            } else {
                a.to_string()
            };
            let _ = write!(o, "{}[{},{},{}]", if i > 0 { "," } else { "" }, fa, b, n(r));
        }
        let _ = write!(
            o,
            "],\"crossings_per_day\":{},\"plans\":{{",
            n(self.crossings())
        );
        for (k, (name, c)) in plans.iter().enumerate() {
            let oht = self.oht(c);
            let _ = write!(
                o,
                "{}\"{}\":{{\"metres_per_day\":{},\"lengths\":[{}],\"sides\":[{}],\"bays\":[",
                if k > 0 { "," } else { "" },
                name,
                n(self.metres(c, &oht)),
                c.lengths
                    .iter()
                    .map(|x| n(*x))
                    .collect::<Vec<_>>()
                    .join(","),
                c.sides
                    .iter()
                    .map(|s| format!("[{},{}]", n(s[0]), n(s[1])))
                    .collect::<Vec<_>>()
                    .join(",")
            );
            for (i, b) in c.bays.iter().enumerate() {
                let _ = write!(
                    o,
                    "{}{{\"phase\":{},\"side\":{},\"area\":\"{}\",\"x0\":{},\"x1\":{}}}",
                    if i > 0 { "," } else { "" },
                    b.phase,
                    b.side,
                    b.area,
                    n(b.x0),
                    n(b.x1)
                );
            }
            o.push_str("],\"tools\":[");
            for (i, t) in c.tools.iter().enumerate() {
                let _ = write!(
                    o,
                    "{}[{},{},{},{},{},{},{},{}]",
                    if i > 0 { "," } else { "" },
                    t.group,
                    t.phase,
                    t.side,
                    t.bay,
                    n(t.x0),
                    n(t.x1),
                    n(t.y0),
                    n(t.y1)
                );
            }
            o.push_str("],\"places\":[");
            for (i, p) in c.places.iter().enumerate() {
                if i > 0 {
                    o.push(',');
                }
                match p {
                    None => o.push_str("null"),
                    Some(p) => {
                        let _ = write!(
                            o,
                            "[{},{},{},{},{}]",
                            p.phase,
                            p.side,
                            if p.bay == usize::MAX {
                                -1
                            } else {
                                p.bay as i64
                            },
                            n(p.x),
                            n(p.y)
                        );
                    }
                }
            }
            o.push_str("]}");
        }
        o.push_str("}}");
        o
    }
}
