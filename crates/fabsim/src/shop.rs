//! A shop: tool groups, routes of steps, lots in progress and lot releases.
//!
//! The text form (`fabgym-shop 1`) is one record per line, fields separated by tabs, `-` for a
//! value that is absent. Floats are written as Python's `repr` writes them (the shortest text
//! that reads back to the same bits), so a shop written by the reference recorder reads and
//! writes back unchanged.

use std::fmt::Write as _;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Per {
    Piece,
    Lot,
    Batch,
}

impl Per {
    pub fn name(self) -> &'static str {
        match self {
            Per::Piece => "piece",
            Per::Lot => "lot",
            Per::Batch => "batch",
        }
    }
    fn parse(s: &str) -> Result<Self, String> {
        match s {
            "piece" => Ok(Per::Piece),
            "lot" => Ok(Per::Lot),
            "batch" => Ok(Per::Batch),
            _ => Err(format!("unknown per {s:?}")),
        }
    }
}

/// Maintenance: every `every` minutes (or pieces), lasting uniform(lo, hi) minutes.
#[derive(Clone, Debug, PartialEq)]
pub struct Pm {
    pub every: f64,
    pub lo: f64,
    pub hi: f64,
    pub first: Option<f64>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Group {
    pub name: String,
    pub count: usize,
    pub load: f64,
    pub unload: f64,
    pub batch_wait: Option<f64>,
    /// (mean time to failure, mean time to repair), minutes
    pub breakdown: Option<(f64, f64)>,
    /// "from>to" (from may be empty) to minutes, in the order given
    pub setups: Vec<(String, f64)>,
    pub pm: Vec<Pm>,
    pub pm_pieces: Vec<Pm>,
    /// windows when every tool of the group is down, [start, end)
    pub down: Vec<(f64, f64)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Step {
    pub group: String,
    pub per: Per,
    pub time: f64,
    pub spread: f64,
    /// (min, max) pieces
    pub batch: Option<(f64, f64)>,
    pub interval: Option<f64>,
    pub batch_wait: Option<f64>,
    pub setup: Option<String>,
    pub sample: Option<f64>,
    /// (step index to go back to, probability)
    pub rework: Option<(usize, f64)>,
    /// (step index the limit runs to, minutes)
    pub cqt: Option<(usize, f64)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Route {
    pub name: String,
    pub steps: Vec<Step>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct LotSpec {
    pub id: String,
    pub route: String,
    pub size: i64,
    pub priority: f64,
    pub start: f64,
    pub step: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Release {
    pub route: String,
    pub size: i64,
    pub priority: f64,
    pub every: f64,
    pub first: f64,
    pub count: Option<i64>,
    pub prefix: String,
}

/// Where a tool group stands on a campus (docs/FAB-LAYOUT.md): phase, side of the spine,
/// bay, metres along the spine and metres deep from it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Place {
    pub phase: usize,
    pub side: usize,
    pub bay: usize,
    pub x: f64,
    pub y: f64,
}

/// Lots moved by the overhead hoist over a layout's distances, instead of the flat transport.
#[derive(Clone, Debug, PartialEq)]
pub struct Oht {
    /// minutes for every move whatever its length (vehicle called, hoist down and up)
    pub overhead: f64,
    /// metres per minute
    pub speed: f64,
    /// a move takes overhead + distance / speed, plus uniform(-jitter, +jitter) minutes
    pub jitter: f64,
    /// metres of bridge between one phase's east end and the next one's west end
    pub bridge: f64,
    /// width of the main aisle, crossed to reach the other side
    pub spine: f64,
    /// each phase's length along its spine, west to east
    pub lengths: Vec<f64>,
    /// where new lots enter
    pub start: Place,
    /// every group's place; `None` for a stocker (a lot sent there waits at the spine end of its bay)
    pub places: Vec<(String, Option<Place>)>,
}

impl Oht {
    /// Metres along the aisles between two places.
    pub fn distance(&self, a: &Place, b: &Place) -> f64 {
        if a.phase == b.phase {
            if a.side == b.side && a.bay == b.bay {
                (a.x - b.x).abs() + (a.y - b.y).abs()
            } else {
                a.y + (a.x - b.x).abs() + b.y + if a.side == b.side { 0.0 } else { self.spine }
            }
        } else {
            let (p, q) = if a.phase < b.phase { (a, b) } else { (b, a) };
            let between: f64 = ((p.phase + 1)..q.phase).map(|k| self.lengths[k] + self.bridge).sum();
            p.y + (self.lengths[p.phase] - p.x) + self.bridge + between + q.x + q.y
        }
    }

    /// Minutes for a move of `metres`, before the jitter.
    pub fn minutes(&self, metres: f64) -> f64 {
        self.overhead + metres / self.speed
    }

    pub fn check(&self) -> Result<(), String> {
        let ok = self.overhead >= 0.0 && self.speed > 0.0 && self.jitter >= 0.0 && self.jitter <= self.overhead;
        if !ok || !self.bridge.is_finite() || self.bridge < 0.0 || self.spine < 0.0 {
            return Err("oht wants overhead >= jitter >= 0, speed > 0, bridge and spine >= 0".into());
        }
        let n = self.lengths.len();
        let bad = |p: &Place| p.phase >= n || p.x < 0.0 || p.y < 0.0 || p.side > 1;
        if bad(&self.start) || self.places.iter().any(|(_, p)| p.as_ref().is_some_and(bad)) {
            return Err("an oht place is outside its phases".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Default)]
pub struct Shop {
    /// moves by a layout instead of `transport`, when given
    pub oht: Option<Oht>,
    pub transport: (f64, f64),
    /// a WIP cap (CONWIP): releases wait while this many lots are in the fab
    pub cap: Option<i64>,
    pub probes: Vec<f64>,
    pub groups: Vec<Group>,
    pub routes: Vec<Route>,
    pub lots: Vec<LotSpec>,
    pub releases: Vec<Release>,
    /// (route, family): lots on the route belong to the family; others to family "" (docs/TWO-FAMILIES.md)
    pub families: Vec<(String, String)>,
    /// (family, lots): at most that many of the family's lots in the fab
    pub famcaps: Vec<(String, i64)>,
    /// (group, family, tools): only the group's first that-many tools may process the family's lots
    pub quals: Vec<(String, String, usize)>,
    /// (group, family, tools): the group's first that-many tools take the family's waiting lots first
    pub reserves: Vec<(String, String, usize)>,
    /// holds on top of rework (docs/RL-DEFECTS.md); None leaves every run as it was
    pub defects: Option<Defects>,
    /// a finite fleet on a one-way track (docs/FLEET.md); needs `oht`; None leaves every run as it was
    pub fleet: Option<Fleet>,
    /// (group, place): each tool's load port on the rail, in the order of the group's tools (docs/FLEET.md);
    /// read only by a fleet
    pub ports: Vec<(String, Place)>,
    /// each bay's two rails, one over each wall's ports (docs/FLEET.md); read only by a fleet
    pub bayrails: Vec<BayRail>,
    /// the floor plan (docs/FAB-FILE.md): prices, rail nodes and links, stations, stops, stockers, entry and exit;
    /// None for a shop with no plan records, which then writes exactly as before
    pub plan: Option<Plan>,
}

/// A fab's floor plan (docs/FAB-FILE.md). Written after every other record, kind by kind in the order of the fields.
#[derive(Clone, Debug, PartialEq, Default)]
pub struct Plan {
    pub prices: Vec<Price>,
    pub nodes: Vec<Node>,
    pub links: Vec<Link>,
    pub stations: Vec<Station>,
    pub stops: Vec<Stop>,
    /// node ids of stocker ports
    pub stockers: Vec<String>,
    /// node ids where new lots come onto the rail
    pub entry: Vec<String>,
    /// node ids where finished lots leave
    pub exit: Vec<String>,
}

/// Dollars to buy one tool of the group, and dollars a day to run it.
#[derive(Clone, Debug, PartialEq)]
pub struct Price {
    pub group: String,
    pub buy: f64,
    pub day: f64,
}

/// A point of the rail on the floor plan, in metres.
#[derive(Clone, Debug, PartialEq)]
pub struct Node {
    pub id: String,
    pub x: f64,
    pub y: f64,
}

/// A one-way stretch of rail and its length in metres.
#[derive(Clone, Debug, PartialEq)]
pub struct Link {
    pub from: String,
    pub to: String,
    pub len: f64,
}

/// Where a group's tools stand on the plan: a rectangle in metres, for drawing.
#[derive(Clone, Debug, PartialEq)]
pub struct Station {
    pub group: String,
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

/// The node where a group's tool number `tool` (from 0) loads and unloads.
#[derive(Clone, Debug, PartialEq)]
pub struct Stop {
    pub group: String,
    pub tool: usize,
    pub node: String,
}

/// A bay's rails (docs/FLEET.md): the bay, its phase and side, the x of the rail over wall 0's and wall 1's ports
/// (along the spine, in its phase), and the depth of the far end where the two join.
#[derive(Clone, Debug, PartialEq)]
pub struct BayRail {
    pub bay: usize,
    pub phase: usize,
    pub side: usize,
    pub x: [f64; 2],
    pub far: f64,
}

/// The fleet (docs/FLEET.md): vehicles on the one-way track, the gap between them (metres), minutes to hoist a lot
/// up or down, finished lots a tool may hold before it stops, metres between crossovers, and the vehicle controller.
#[derive(Clone, Debug, PartialEq)]
pub struct Fleet {
    pub vehicles: usize,
    pub gap: f64,
    pub hoist: f64,
    pub ports: usize,
    pub cross: f64,
    pub controller: String,
}

/// A rework is a finding: the tool that did the step is held, and so are the lots it touched just before.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Defects {
    pub hold_tool_minutes: f64,
    pub lookback_minutes: f64,
    pub hold_lot_minutes: f64,
}

// ------------------------------------------------------------------ Python float text

/// A float as Python's `repr(float)` writes it.
pub fn pyrepr(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".into() } else { "-inf".into() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    let e = format!("{:e}", x.abs()); // shortest round-trip digits, e.g. "4.194e2"
    let (mant, exp) = e.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    let digits: String = mant.chars().filter(|c| *c != '.').collect();
    let decpt = exp + 1;
    let mut out = String::new();
    if x < 0.0 {
        out.push('-');
    }
    if decpt <= -4 || decpt > 16 {
        out.push_str(&digits[..1]);
        if digits.len() > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        let e10 = decpt - 1;
        let _ = write!(out, "e{}{:02}", if e10 < 0 { '-' } else { '+' }, e10.abs());
    } else if decpt <= 0 {
        out.push_str("0.");
        for _ in 0..(-decpt) {
            out.push('0');
        }
        out.push_str(&digits);
    } else if decpt as usize >= digits.len() {
        out.push_str(&digits);
        for _ in 0..(decpt as usize - digits.len()) {
            out.push('0');
        }
        out.push_str(".0");
    } else {
        out.push_str(&digits[..decpt as usize]);
        out.push('.');
        out.push_str(&digits[decpt as usize..]);
    }
    out
}

fn opt(x: Option<f64>) -> String {
    x.map(pyrepr).unwrap_or_else(|| "-".into())
}

fn optn<T: ToString>(x: Option<T>) -> String {
    x.map(|v| v.to_string()).unwrap_or_else(|| "-".into())
}

fn pf(s: &str) -> Result<f64, String> {
    s.trim().parse::<f64>().map_err(|e| format!("bad float {s:?}: {e}"))
}

fn pfo(s: &str) -> Result<Option<f64>, String> {
    if s == "-" {
        Ok(None)
    } else {
        pf(s).map(Some)
    }
}

fn pi<T: std::str::FromStr>(s: &str) -> Result<T, String> {
    s.trim().parse::<T>().map_err(|_| format!("bad integer {s:?}"))
}

fn pio<T: std::str::FromStr>(s: &str) -> Result<Option<T>, String> {
    if s == "-" {
        Ok(None)
    } else {
        pi(s).map(Some)
    }
}

/// A bay number; one too large for this platform's usize (the 64-bit "no bay" marker read by a 32-bit build, such
/// as the page's WebAssembly) reads as `usize::MAX`, the same marker.
pub fn read_bay(s: &str) -> Result<usize, String> {
    let v: u64 = pi(s)?;
    Ok(usize::try_from(v).unwrap_or(usize::MAX))
}

fn read_place(f: &[&str]) -> Result<Place, String> {
    Ok(Place { phase: pi(f[0])?, side: pi(f[1])?, bay: read_bay(f[2])?, x: pf(f[3])?, y: pf(f[4])? })
}

fn write_place(p: &Place) -> String {
    format!("{}\t{}\t{}\t{}\t{}", p.phase, p.side, p.bay, pyrepr(p.x), pyrepr(p.y))
}

impl Shop {
    pub fn group(&self, name: &str) -> Option<&Group> {
        self.groups.iter().find(|g| g.name == name)
    }

    pub fn route(&self, name: &str) -> Option<&Route> {
        self.routes.iter().find(|r| r.name == name)
    }

    /// The family of a route's lots ("" when none is named).
    pub fn family_of(&self, route: &str) -> &str {
        self.families.iter().find(|f| f.0 == route).map(|f| f.1.as_str()).unwrap_or("")
    }

    /// True when any of the two-family switches is on (families only label lots).
    pub fn has_family_rules(&self) -> bool {
        !self.famcaps.is_empty() || !self.quals.is_empty() || !self.reserves.is_empty()
    }

    /// Read the text form.
    pub fn parse(text: &str) -> Result<Shop, String> {
        let mut lines = text.lines();
        if lines.next() != Some("fabgym-shop 1") {
            return Err("not a fabgym-shop 1 file".into());
        }
        let mut s = Shop::default();
        // plan records keep their line numbers so references can be checked after the whole file is read
        let mut plan_lines: Vec<(usize, PlanRef)> = vec![];
        let mut node_ids: std::collections::HashSet<String> = Default::default();
        for (no, line) in lines.enumerate() {
            if line.is_empty() {
                continue;
            }
            let f: Vec<&str> = line.split('\t').collect();
            let need = |n: usize| -> Result<(), String> {
                if f.len() < n {
                    Err(format!("line {}: {} wants {n} fields", no + 2, f[0]))
                } else {
                    Ok(())
                }
            };
            let last_group = |s: &mut Shop| -> Result<usize, String> {
                if s.groups.is_empty() {
                    Err(format!("line {}: {} before any group", no + 2, f[0]))
                } else {
                    Ok(s.groups.len() - 1)
                }
            };
            match f[0] {
                "transport" => {
                    need(3)?;
                    s.transport = (pf(f[1])?, pf(f[2])?);
                }
                "cap" => {
                    need(2)?;
                    s.cap = Some(pi(f[1])?);
                }
                "probe" => {
                    need(2)?;
                    s.probes.push(pf(f[1])?);
                }
                "group" => {
                    need(8)?;
                    let mttf = pfo(f[6])?;
                    let mttr = pfo(f[7])?;
                    s.groups.push(Group {
                        name: f[1].into(),
                        count: pi(f[2])?,
                        load: pf(f[3])?,
                        unload: pf(f[4])?,
                        batch_wait: pfo(f[5])?,
                        breakdown: match (mttf, mttr) {
                            (Some(a), Some(b)) => Some((a, b)),
                            _ => None,
                        },
                        setups: vec![],
                        pm: vec![],
                        pm_pieces: vec![],
                        down: vec![],
                    });
                }
                "setup" => {
                    need(3)?;
                    let g = last_group(&mut s)?;
                    s.groups[g].setups.push((f[1].into(), pf(f[2])?));
                }
                "pm" | "pmp" => {
                    need(5)?;
                    let g = last_group(&mut s)?;
                    let pm = Pm { every: pf(f[1])?, lo: pf(f[2])?, hi: pf(f[3])?, first: pfo(f[4])? };
                    if f[0] == "pm" {
                        s.groups[g].pm.push(pm);
                    } else {
                        s.groups[g].pm_pieces.push(pm);
                    }
                }
                "down" => {
                    need(3)?;
                    let g = last_group(&mut s)?;
                    s.groups[g].down.push((pf(f[1])?, pf(f[2])?));
                }
                "route" => {
                    need(2)?;
                    s.routes.push(Route { name: f[1].into(), steps: vec![] });
                }
                "step" => {
                    need(15)?;
                    let r = s.routes.last_mut().ok_or("step before any route")?;
                    let (blo, bhi) = (pfo(f[5])?, pfo(f[6])?);
                    let (rto, rp) = (pio::<usize>(f[11])?, pfo(f[12])?);
                    let (cto, cl) = (pio::<usize>(f[13])?, pfo(f[14])?);
                    r.steps.push(Step {
                        group: f[1].into(),
                        per: Per::parse(f[2])?,
                        time: pf(f[3])?,
                        spread: pf(f[4])?,
                        batch: blo.zip(bhi),
                        interval: pfo(f[7])?,
                        batch_wait: pfo(f[8])?,
                        setup: if f[9] == "-" { None } else { Some(f[9].into()) },
                        sample: pfo(f[10])?,
                        rework: rto.zip(rp),
                        cqt: cto.zip(cl),
                    });
                }
                "lot" => {
                    need(7)?;
                    s.lots.push(LotSpec {
                        id: f[1].into(),
                        route: f[2].into(),
                        size: pi(f[3])?,
                        priority: pf(f[4])?,
                        start: pf(f[5])?,
                        step: pi(f[6])?,
                    });
                }
                "release" => {
                    need(8)?;
                    s.releases.push(Release {
                        route: f[1].into(),
                        size: pi(f[2])?,
                        priority: pf(f[3])?,
                        every: pf(f[4])?,
                        first: pf(f[5])?,
                        count: pio(f[6])?,
                        prefix: f[7].into(),
                    });
                }
                "family" => {
                    need(3)?;
                    s.families.push((f[1].into(), f[2].into()));
                }
                "defects" => {
                    need(4)?;
                    let d = Defects { hold_tool_minutes: pf(f[1])?, lookback_minutes: pf(f[2])?, hold_lot_minutes: pf(f[3])? };
                    if !(d.hold_tool_minutes >= 0.0 && d.lookback_minutes >= 0.0 && d.hold_lot_minutes >= 0.0) {
                        return Err(format!("line {}: defects wants three minutes, none negative", no + 2));
                    }
                    s.defects = Some(d);
                }
                "famcap" => {
                    need(3)?;
                    s.famcaps.push((f[1].into(), pi(f[2])?));
                }
                "qual" | "reserve" => {
                    need(4)?;
                    let n: usize = f[3].parse().map_err(|_| format!("line {}: {} wants a tool count", no + 2, f[0]))?;
                    let rec = (f[1].to_string(), f[2].to_string(), n);
                    if f[0] == "qual" {
                        s.quals.push(rec);
                    } else {
                        s.reserves.push(rec);
                    }
                }
                "oht" => {
                    need(6)?;
                    s.oht = Some(Oht {
                        overhead: pf(f[1])?,
                        speed: pf(f[2])?,
                        jitter: pf(f[3])?,
                        bridge: pf(f[4])?,
                        spine: pf(f[5])?,
                        lengths: vec![],
                        start: Place { phase: 0, side: 0, bay: 0, x: 0.0, y: 0.0 },
                        places: vec![],
                    });
                }
                "bayrail" => {
                    need(7)?;
                    s.bayrails.push(BayRail { bay: pi(f[1])?, phase: pi(f[2])?, side: pi(f[3])?, x: [pf(f[4])?, pf(f[5])?], far: pf(f[6])? });
                }
                "port" => {
                    need(7)?;
                    s.ports.push((f[1].to_string(), read_place(&f[2..])?));
                }
                "fleet" => {
                    need(7)?;
                    let n = |x: &str| x.parse::<usize>().map_err(|_| format!("line {}: fleet wants whole numbers of vehicles and ports", no + 2));
                    s.fleet = Some(Fleet { vehicles: n(f[1])?, gap: pf(f[2])?, hoist: pf(f[3])?, ports: n(f[4])?, cross: pf(f[5])?, controller: f[6].to_string() });
                }
                "ohtphase" | "ohtstart" | "place" => {
                    let o = s.oht.as_mut().ok_or_else(|| format!("line {}: {} before oht", no + 2, f[0]))?;
                    match f[0] {
                        "ohtphase" => {
                            need(2)?;
                            o.lengths.push(pf(f[1])?);
                        }
                        "ohtstart" => {
                            need(6)?;
                            o.start = read_place(&f[1..])?;
                        }
                        _ => {
                            need(3)?;
                            let p = if f[2] == "stocker" {
                                None
                            } else {
                                need(7)?;
                                Some(read_place(&f[2..])?)
                            };
                            o.places.push((f[1].into(), p));
                        }
                    }
                }
                "price" | "node" | "link" | "station" | "stop" | "stocker" | "entry" | "exit" => {
                    let ln = no + 2;
                    let p = s.plan.get_or_insert_with(Plan::default);
                    match f[0] {
                        "price" => {
                            need(4)?;
                            let (buy, day) = (pf(f[2])?, pf(f[3])?);
                            if !(buy >= 0.0 && day >= 0.0) {
                                return Err(format!("line {ln}: price wants dollars to buy and a day, none negative"));
                            }
                            p.prices.push(Price { group: f[1].into(), buy, day });
                            plan_lines.push((ln, PlanRef::Group(f[1].into(), None)));
                        }
                        "node" => {
                            need(4)?;
                            if !node_ids.insert(f[1].to_string()) {
                                return Err(format!("line {ln}: node {:?} is defined twice", f[1]));
                            }
                            p.nodes.push(Node { id: f[1].into(), x: pf(f[2])?, y: pf(f[3])? });
                        }
                        "link" => {
                            need(4)?;
                            let len = pf(f[3])?;
                            if !(len >= 0.0) {
                                return Err(format!("line {ln}: link wants a length of zero or more metres"));
                            }
                            p.links.push(Link { from: f[1].into(), to: f[2].into(), len });
                            plan_lines.push((ln, PlanRef::Node(f[1].into())));
                            plan_lines.push((ln, PlanRef::Node(f[2].into())));
                        }
                        "station" => {
                            need(6)?;
                            p.stations.push(Station { group: f[1].into(), x: pf(f[2])?, y: pf(f[3])?, w: pf(f[4])?, h: pf(f[5])? });
                            plan_lines.push((ln, PlanRef::Group(f[1].into(), None)));
                        }
                        "stop" => {
                            need(4)?;
                            let tool: usize = pi(f[2])?;
                            p.stops.push(Stop { group: f[1].into(), tool, node: f[3].into() });
                            plan_lines.push((ln, PlanRef::Group(f[1].into(), Some(tool))));
                            plan_lines.push((ln, PlanRef::Node(f[3].into())));
                        }
                        kind => {
                            need(2)?;
                            let list = match kind {
                                "stocker" => &mut p.stockers,
                                "entry" => &mut p.entry,
                                _ => &mut p.exit,
                            };
                            list.push(f[1].into());
                            plan_lines.push((ln, PlanRef::Node(f[1].into())));
                        }
                    }
                }
                other => return Err(format!("line {}: unknown record {other:?}", no + 2)),
            }
        }
        for (ln, r) in &plan_lines {
            match r {
                PlanRef::Node(id) if !node_ids.contains(id) => {
                    return Err(format!("line {ln}: names node {id:?}, which is not defined"));
                }
                PlanRef::Group(g, tool) => match s.group(g) {
                    None => return Err(format!("line {ln}: names group {g:?}, which the shop does not have")),
                    Some(gr) => {
                        if let Some(k) = tool {
                            if *k >= gr.count {
                                return Err(format!("line {ln}: stop for tool {k} of {g}, which has {} tool(s)", gr.count));
                            }
                        }
                    }
                },
                _ => {}
            }
        }
        if let Some(o) = &s.oht {
            o.check()?;
        }
        if (!s.ports.is_empty() || !s.bayrails.is_empty()) && s.oht.is_none() {
            return Err("ports need a layout (an oht record)".into());
        }
        if let Some(f) = &s.fleet {
            if s.oht.is_none() {
                return Err("a fleet needs a layout (an oht record)".into());
            }
            // written so that a NaN fails too
            let ok = f.vehicles > 0 && f.ports > 0 && f.gap > 0.0 && f.hoist >= 0.0 && f.cross >= 0.0 && ["nearest", "first"].contains(&f.controller.as_str());
            if !ok {
                return Err("fleet wants vehicles and ports above zero, gap > 0, hoist and cross >= 0, and a controller nearest or first".into());
            }
        }
        Ok(s)
    }

    /// Write the text form.
    pub fn to_text(&self) -> String {
        let mut o = String::from("fabgym-shop 1\n");
        let _ = writeln!(o, "transport\t{}\t{}", pyrepr(self.transport.0), pyrepr(self.transport.1));
        if let Some(c) = self.cap {
            let _ = writeln!(o, "cap\t{c}");
        }
        for p in &self.probes {
            let _ = writeln!(o, "probe\t{}", pyrepr(*p));
        }
        if let Some(h) = &self.oht {
            let _ = writeln!(
                o,
                "oht\t{}\t{}\t{}\t{}\t{}",
                pyrepr(h.overhead),
                pyrepr(h.speed),
                pyrepr(h.jitter),
                pyrepr(h.bridge),
                pyrepr(h.spine)
            );
            for l in &h.lengths {
                let _ = writeln!(o, "ohtphase\t{}", pyrepr(*l));
            }
            let _ = writeln!(o, "ohtstart\t{}", write_place(&h.start));
            for (g, p) in &h.places {
                match p {
                    None => {
                        let _ = writeln!(o, "place\t{g}\tstocker");
                    }
                    Some(p) => {
                        let _ = writeln!(o, "place\t{g}\t{}", write_place(p));
                    }
                }
            }
        }
        // ports belong to a layout: written only with one
        if self.oht.is_some() {
            for (g, p) in &self.ports {
                let _ = writeln!(o, "port\t{g}\t{}", write_place(p));
            }
            for b in &self.bayrails {
                let _ = writeln!(o, "bayrail\t{}\t{}\t{}\t{}\t{}\t{}", b.bay, b.phase, b.side, pyrepr(b.x[0]), pyrepr(b.x[1]), pyrepr(b.far));
            }
        }
        if let Some(f) = &self.fleet {
            let _ = writeln!(o, "fleet\t{}\t{}\t{}\t{}\t{}\t{}", f.vehicles, pyrepr(f.gap), pyrepr(f.hoist), f.ports, pyrepr(f.cross), f.controller);
        }
        for g in &self.groups {
            let _ = writeln!(
                o,
                "group\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                g.name,
                g.count,
                pyrepr(g.load),
                pyrepr(g.unload),
                opt(g.batch_wait),
                opt(g.breakdown.map(|b| b.0)),
                opt(g.breakdown.map(|b| b.1)),
            );
            for (k, m) in &g.setups {
                let _ = writeln!(o, "setup\t{k}\t{}", pyrepr(*m));
            }
            for (tag, list) in [("pm", &g.pm), ("pmp", &g.pm_pieces)] {
                for pm in list {
                    let _ = writeln!(
                        o,
                        "{tag}\t{}\t{}\t{}\t{}",
                        pyrepr(pm.every),
                        pyrepr(pm.lo),
                        pyrepr(pm.hi),
                        opt(pm.first)
                    );
                }
            }
            for (a, b) in &g.down {
                let _ = writeln!(o, "down\t{}\t{}", pyrepr(*a), pyrepr(*b));
            }
        }
        for r in &self.routes {
            let _ = writeln!(o, "route\t{}", r.name);
            for st in &r.steps {
                let _ = writeln!(
                    o,
                    "step\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                    st.group,
                    st.per.name(),
                    pyrepr(st.time),
                    pyrepr(st.spread),
                    opt(st.batch.map(|b| b.0)),
                    opt(st.batch.map(|b| b.1)),
                    opt(st.interval),
                    opt(st.batch_wait),
                    st.setup.as_deref().unwrap_or("-"),
                    opt(st.sample),
                    optn(st.rework.map(|r| r.0)),
                    opt(st.rework.map(|r| r.1)),
                    optn(st.cqt.map(|c| c.0)),
                    opt(st.cqt.map(|c| c.1)),
                );
            }
        }
        for l in &self.lots {
            let _ = writeln!(
                o,
                "lot\t{}\t{}\t{}\t{}\t{}\t{}",
                l.id,
                l.route,
                l.size,
                pyrepr(l.priority),
                pyrepr(l.start),
                l.step
            );
        }
        for r in &self.releases {
            let _ = writeln!(
                o,
                "release\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                r.route,
                r.size,
                pyrepr(r.priority),
                pyrepr(r.every),
                pyrepr(r.first),
                optn(r.count),
                r.prefix
            );
        }
        for (r, f) in &self.families {
            let _ = writeln!(o, "family\t{r}\t{f}");
        }
        for (f, n) in &self.famcaps {
            let _ = writeln!(o, "famcap\t{f}\t{n}");
        }
        for (g, f, n) in &self.quals {
            let _ = writeln!(o, "qual\t{g}\t{f}\t{n}");
        }
        for (g, f, n) in &self.reserves {
            let _ = writeln!(o, "reserve\t{g}\t{f}\t{n}");
        }
        if let Some(d) = self.defects {
            let _ = writeln!(o, "defects\t{}\t{}\t{}", pyrepr(d.hold_tool_minutes), pyrepr(d.lookback_minutes), pyrepr(d.hold_lot_minutes));
        }
        if let Some(p) = &self.plan {
            for r in &p.prices {
                let _ = writeln!(o, "price\t{}\t{}\t{}", r.group, pyrepr(r.buy), pyrepr(r.day));
            }
            for n in &p.nodes {
                let _ = writeln!(o, "node\t{}\t{}\t{}", n.id, pyrepr(n.x), pyrepr(n.y));
            }
            for l in &p.links {
                let _ = writeln!(o, "link\t{}\t{}\t{}", l.from, l.to, pyrepr(l.len));
            }
            for st in &p.stations {
                let _ = writeln!(o, "station\t{}\t{}\t{}\t{}\t{}", st.group, pyrepr(st.x), pyrepr(st.y), pyrepr(st.w), pyrepr(st.h));
            }
            for st in &p.stops {
                let _ = writeln!(o, "stop\t{}\t{}\t{}", st.group, st.tool, st.node);
            }
            for (tag, list) in [("stocker", &p.stockers), ("entry", &p.entry), ("exit", &p.exit)] {
                for n in list {
                    let _ = writeln!(o, "{tag}\t{n}");
                }
            }
        }
        o
    }
}

/// What a plan record names, checked once the whole file is read.
enum PlanRef {
    Node(String),
    /// a group, and for a stop the tool number
    Group(String, Option<usize>),
}

#[cfg(test)]
mod tests {
    use super::pyrepr;

    #[test]
    fn repr_like_python() {
        for (x, want) in [
            (1.0, "1.0"),
            (0.1, "0.1"),
            (419.40000000000003, "419.40000000000003"),
            (1e16, "1e+16"),
            (1e15, "1000000000000000.0"),
            (1e-4, "0.0001"),
            (1e-5, "1e-05"),
            (1.5e-7, "1.5e-07"),
            (-30.0, "-30.0"),
            (1e9, "1000000000.0"),
            (123456789012345680.0, "1.2345678901234568e+17"),
        ] {
            assert_eq!(pyrepr(x), want);
        }
    }
}
