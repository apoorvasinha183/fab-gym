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
                other => return Err(format!("line {}: unknown record {other:?}", no + 2)),
            }
        }
        if let Some(o) = &s.oht {
            o.check()?;
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
        o
    }
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
