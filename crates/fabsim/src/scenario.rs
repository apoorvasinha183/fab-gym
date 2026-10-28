//! A question turned into shocks and candidates: the `fabgym-scenario 1` text (docs/ASK.md).

use std::fmt::Write as _;

use crate::dials::{Dials, Outage};
use crate::policy::Policy;
use crate::shop::Shop;
use crate::twofam::Policy as FamPolicy;

/// A floor for family B (docs/TWO-FAMILIES-SWEEP.md): no copies, copies in a P3 wing, or copies in the halls.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FloorKind {
    Share,
    Wing,
    Copies,
}

impl FloorKind {
    pub fn key(self) -> &'static str {
        match self {
            FloorKind::Share => "share",
            FloorKind::Wing => "wing",
            FloorKind::Copies => "copies",
        }
    }

    pub fn from_key(k: &str) -> Option<FloorKind> {
        [FloorKind::Share, FloorKind::Wing, FloorKind::Copies].into_iter().find(|f| f.key() == k)
    }
}

/// Family B's share: times the published engineering lots (docs/ASK-FAMILIES.md).
#[derive(Clone, Debug, PartialEq)]
pub struct FamilySpec {
    pub share: f64,
    pub said: bool,
}

pub const SHARE_RANGE: (f64, f64) = (0.25, 16.0);

/// At most this many candidates in one scenario.
pub const MAX_CANDIDATES: usize = 6;

#[derive(Clone, Debug, PartialEq)]
pub enum ShockKind {
    Breakdowns(f64),
    Repair(f64),
    Demand(f64),
    /// a whole group down from an hour of the run for some hours
    Outage { group: String, from_hours: f64, hours: f64 },
    /// lots in progress made hot
    Hot(usize),
}

impl ShockKind {
    pub fn name(&self) -> &'static str {
        match self {
            ShockKind::Breakdowns(_) => "breakdowns",
            ShockKind::Repair(_) => "repair",
            ShockKind::Demand(_) => "demand",
            ShockKind::Outage { .. } => "outage",
            ShockKind::Hot(_) => "hot",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Shock {
    pub kind: ShockKind,
    /// said in the question (true) or assumed (false)
    pub said: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Change {
    Rule(Policy),
    Cap(i64),
    Spare(String, usize),
    Demand(f64),
    Floor(FloorKind),
    FamilyPolicy(FamPolicy),
}

#[derive(Clone, Debug, PartialEq)]
pub struct CandidateSpec {
    pub name: String,
    pub changes: Vec<Change>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Sweep {
    /// the shock swept, by name
    pub shock: String,
    /// which of its values: "value" for a multiplier, "hours" or "from" for an outage, "lots" for hot
    pub field: String,
    pub low: f64,
    pub high: f64,
    pub n: usize,
}

impl Sweep {
    pub fn points(&self) -> Vec<f64> {
        (0..self.n).map(|i| self.low + (self.high - self.low) * i as f64 / (self.n - 1) as f64).collect()
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Scenario {
    pub question: String,
    /// a two-family question when present
    pub family: Option<FamilySpec>,
    pub shocks: Vec<Shock>,
    pub candidates: Vec<CandidateSpec>,
    pub sweep: Option<Sweep>,
}

fn num(s: &str, what: &str) -> Result<f64, String> {
    let x: f64 = s.trim().parse().map_err(|_| format!("{what}: not a number: {s:?}"))?;
    if x.is_finite() { Ok(x) } else { Err(format!("{what}: not a finite number: {s:?}")) }
}

fn count(s: &str, what: &str) -> Result<usize, String> {
    s.trim().parse().map_err(|_| format!("{what}: not a whole number: {s:?}"))
}

fn tag(s: &str) -> Result<bool, String> {
    match s {
        "said" => Ok(true),
        "assumed" => Ok(false),
        _ => Err(format!("a shock is said or assumed, not {s:?}")),
    }
}

impl Scenario {
    pub fn parse(text: &str) -> Result<Scenario, String> {
        let mut lines = text.lines();
        if lines.next().map(str::trim_end) != Some("fabgym-scenario 1") {
            return Err("not a fabgym-scenario 1 file".into());
        }
        let mut s = Scenario { question: String::new(), family: None, shocks: vec![], candidates: vec![], sweep: None };
        for (no, line) in lines.enumerate() {
            let line = line.trim_end_matches('\r');
            if line.trim().is_empty() {
                continue;
            }
            let f: Vec<&str> = line.split('\t').collect();
            let at = |e: String| format!("line {}: {e}", no + 2);
            let need = |n: usize| if f.len() == n { Ok(()) } else { Err(at(format!("{} wants {} fields, got {}", f[0], n, f.len()))) };
            match f[0] {
                "question" => {
                    need(2)?;
                    s.question = f[1].trim().to_string();
                }
                "family" => {
                    need(4)?;
                    if f[1] != "share" {
                        return Err(at(format!("a family record sets the share, not {:?}", f[1])));
                    }
                    if s.family.is_some() {
                        return Err(at("two family records".into()));
                    }
                    let v = num(f[2], "family share").map_err(at)?;
                    if !(SHARE_RANGE.0..=SHARE_RANGE.1).contains(&v) {
                        return Err(at(format!("family share out of range: {v} (from {} to {})", SHARE_RANGE.0, SHARE_RANGE.1)));
                    }
                    s.family = Some(FamilySpec { share: v, said: tag(f[3]).map_err(at)? });
                }
                "shock" => {
                    if f.len() < 2 {
                        return Err(at("a shock needs a kind".into()));
                    }
                    let kind = match f[1] {
                        "breakdowns" | "repair" | "demand" => {
                            need(4)?;
                            let v = num(f[2], f[1]).map_err(at)?;
                            if v < 0.0 || (f[1] != "breakdowns" && v == 0.0) {
                                return Err(at(format!("{} out of range: {v}", f[1])));
                            }
                            match f[1] {
                                "breakdowns" => ShockKind::Breakdowns(v),
                                "repair" => ShockKind::Repair(v),
                                _ => ShockKind::Demand(v),
                            }
                        }
                        "outage" => {
                            need(6)?;
                            let (from_hours, hours) = (num(f[3], "from hour").map_err(at)?, num(f[4], "hours").map_err(at)?);
                            if from_hours < 0.0 || hours <= 0.0 {
                                return Err(at("an outage needs from >= 0 and hours > 0".into()));
                            }
                            ShockKind::Outage { group: f[2].to_string(), from_hours, hours }
                        }
                        "hot" => {
                            need(4)?;
                            ShockKind::Hot(count(f[2], "hot lots").map_err(at)?)
                        }
                        k => return Err(at(format!("unknown shock {k:?}"))),
                    };
                    if s.shocks.iter().any(|x| x.kind.name() == kind.name()) {
                        return Err(at(format!("two {} shocks", kind.name())));
                    }
                    let said = tag(f[f.len() - 1]).map_err(at)?;
                    s.shocks.push(Shock { kind, said });
                }
                "candidate" => {
                    if f.len() < 4 {
                        return Err(at("a candidate needs a name, a kind and a value".into()));
                    }
                    let change = match f[2] {
                        "rule" => {
                            need(4)?;
                            Change::Rule(Policy::parse(f[3]).ok_or_else(|| at(format!("unknown rule {:?}", f[3])))?)
                        }
                        "cap" => {
                            need(4)?;
                            let c = count(f[3], "cap").map_err(at)?;
                            if c < 1 {
                                return Err(at("a cap is at least 1 lot".into()));
                            }
                            Change::Cap(c as i64)
                        }
                        "spare" => {
                            need(5)?;
                            let n = count(f[4], "spare tools").map_err(at)?;
                            if n < 1 {
                                return Err(at("spare tools: at least 1".into()));
                            }
                            Change::Spare(f[3].to_string(), n)
                        }
                        "demand" => {
                            need(4)?;
                            let v = num(f[3], "demand").map_err(at)?;
                            if v <= 0.0 {
                                return Err(at("demand must be above 0".into()));
                            }
                            Change::Demand(v)
                        }
                        "floor" => {
                            need(4)?;
                            Change::Floor(FloorKind::from_key(f[3]).ok_or_else(|| at(format!("unknown floor {:?}", f[3])))?)
                        }
                        "policy" => {
                            need(4)?;
                            Change::FamilyPolicy(FamPolicy::from_key(f[3]).ok_or_else(|| at(format!("unknown policy {:?}", f[3])))?)
                        }
                        k => return Err(at(format!("unknown candidate kind {k:?}"))),
                    };
                    let name = f[1].trim();
                    if name.is_empty() {
                        return Err(at("a candidate needs a name".into()));
                    }
                    let i = match s.candidates.iter().position(|c| c.name == name) {
                        Some(i) => i,
                        None => {
                            s.candidates.push(CandidateSpec { name: name.to_string(), changes: vec![] });
                            s.candidates.len() - 1
                        }
                    };
                    let c = &mut s.candidates[i];
                    let same = |a: &Change| std::mem::discriminant(a) == std::mem::discriminant(&change);
                    if !matches!(change, Change::Spare(..)) && c.changes.iter().any(same) {
                        return Err(at(format!("candidate {name:?} sets that twice")));
                    }
                    c.changes.push(change);
                }
                "sweep" => {
                    need(6)?;
                    if s.sweep.is_some() {
                        return Err(at("one sweep at most".into()));
                    }
                    let n = count(f[5], "sweep points").map_err(at)?;
                    let (low, high) = (num(f[3], "sweep low").map_err(at)?, num(f[4], "sweep high").map_err(at)?);
                    if !(2..=12).contains(&n) || high <= low {
                        return Err(at("a sweep needs low < high and 2 to 12 points".into()));
                    }
                    s.sweep = Some(Sweep { shock: f[1].to_string(), field: f[2].to_string(), low, high, n });
                }
                k => return Err(at(format!("unknown record {k:?}"))),
            }
        }
        if s.question.is_empty() {
            return Err("a scenario needs its question".into());
        }
        if s.candidates.len() > MAX_CANDIDATES {
            return Err(format!("{} candidates, at most {MAX_CANDIDATES}", s.candidates.len()));
        }
        for c in &s.candidates {
            let fam = c.changes.iter().any(|ch| matches!(ch, Change::Floor(_) | Change::FamilyPolicy(_)));
            if fam && s.family.is_none() {
                return Err(format!("candidate {:?} sets a floor or policy, which needs a family record", c.name));
            }
            let first = c.changes.iter().any(|ch| *ch == Change::FamilyPolicy(FamPolicy::BFirst));
            let other_rule = c.changes.iter().any(|ch| matches!(ch, Change::Rule(p) if *p != Policy::Today));
            if first && other_rule {
                return Err(format!("candidate {:?}: family B first decides the order, so it takes no other rule", c.name));
            }
        }
        if let Some(sw) = s.sweep.as_ref().filter(|sw| sw.shock == "family") {
            let f = s.family.as_ref().ok_or("the sweep names the family share, but there is no family record")?;
            if f.said {
                return Err("the family share was said in the question, so it is not swept".into());
            }
            if sw.field != "value" || sw.low < SHARE_RANGE.0 || sw.high > SHARE_RANGE.1 {
                return Err(format!("a family sweep runs over value within {} to {}", SHARE_RANGE.0, SHARE_RANGE.1));
            }
        } else if let Some(sw) = &s.sweep {
            let sh = s.shocks.iter().find(|x| x.kind.name() == sw.shock).ok_or_else(|| format!("the sweep names no shock {:?}", sw.shock))?;
            if sh.said {
                return Err(format!("the {} shock was said in the question, so it is not swept", sw.shock));
            }
            let ok = match &sh.kind {
                ShockKind::Outage { .. } => sw.field == "hours" || sw.field == "from",
                ShockKind::Hot(_) => sw.field == "lots",
                _ => sw.field == "value",
            };
            if !ok {
                return Err(format!("a {} shock has no field {:?}", sw.shock, sw.field));
            }
        }
        Ok(s)
    }

    pub fn to_text(&self) -> String {
        let mut o = String::from("fabgym-scenario 1\n");
        let _ = writeln!(o, "question\t{}", self.question);
        if let Some(f) = &self.family {
            let _ = writeln!(o, "family\tshare\t{}\t{}", f.share, if f.said { "said" } else { "assumed" });
        }
        for sh in &self.shocks {
            let t = if sh.said { "said" } else { "assumed" };
            let _ = match &sh.kind {
                ShockKind::Breakdowns(v) | ShockKind::Repair(v) | ShockKind::Demand(v) => writeln!(o, "shock\t{}\t{v}\t{t}", sh.kind.name()),
                ShockKind::Outage { group, from_hours, hours } => writeln!(o, "shock\toutage\t{group}\t{from_hours}\t{hours}\t{t}"),
                ShockKind::Hot(n) => writeln!(o, "shock\thot\t{n}\t{t}"),
            };
        }
        for c in &self.candidates {
            for ch in &c.changes {
                let _ = match ch {
                    Change::Rule(p) => writeln!(o, "candidate\t{}\trule\t{}", c.name, p.name()),
                    Change::Cap(n) => writeln!(o, "candidate\t{}\tcap\t{n}", c.name),
                    Change::Spare(g, n) => writeln!(o, "candidate\t{}\tspare\t{g}\t{n}", c.name),
                    Change::Demand(v) => writeln!(o, "candidate\t{}\tdemand\t{v}", c.name),
                    Change::Floor(fl) => writeln!(o, "candidate\t{}\tfloor\t{}", c.name, fl.key()),
                    Change::FamilyPolicy(p) => writeln!(o, "candidate\t{}\tpolicy\t{}", c.name, p.key()),
                };
            }
        }
        if let Some(sw) = &self.sweep {
            let _ = writeln!(o, "sweep\t{}\t{}\t{}\t{}\t{}", sw.shock, sw.field, sw.low, sw.high, sw.n);
        }
        o
    }

    pub fn without_sweep(&self) -> Scenario {
        Scenario { sweep: None, ..self.clone() }
    }

    /// Check names against a shop, and that every arm's dials apply.
    pub fn check(&self, shop: &Shop) -> Result<(), String> {
        let has = |g: &str| shop.groups.iter().any(|x| x.name == g);
        for sh in &self.shocks {
            if let ShockKind::Outage { group, .. } = &sh.kind {
                if !has(group) {
                    return Err(format!("no tool group {group:?} in the shop"));
                }
            }
        }
        for c in &self.candidates {
            for ch in &c.changes {
                if let Change::Spare(g, _) = ch {
                    if !has(g) {
                        return Err(format!("candidate {:?}: no tool group {g:?} in the shop", c.name));
                    }
                }
            }
        }
        self.arm(None, None).0.apply(shop)?;
        for c in &self.candidates {
            self.arm(Some(c), None).0.apply(shop)?;
        }
        Ok(())
    }

    /// The dials and rule of one arm: today (no candidate) or a candidate, under the shocks, with
    /// the swept value in place of the shock's own when given.
    pub fn arm(&self, cand: Option<&CandidateSpec>, swept: Option<f64>) -> (Dials, Policy) {
        let mut d = Dials::default();
        for sh in &self.shocks {
            let sw = self.sweep.as_ref().filter(|s| s.shock == sh.kind.name()).and(swept);
            match &sh.kind {
                ShockKind::Breakdowns(v) => d.breakdowns = sw.unwrap_or(*v),
                ShockKind::Repair(v) => d.repair = sw.unwrap_or(*v),
                ShockKind::Demand(v) => d.demand = sw.unwrap_or(*v),
                ShockKind::Hot(n) => d.make_hot = sw.map(|x| x.round().max(0.0) as usize).unwrap_or(*n),
                ShockKind::Outage { group, from_hours, hours } => {
                    let field = self.sweep.as_ref().map(|s| s.field.as_str()).unwrap_or("");
                    let (f, h) = match sw {
                        Some(x) if field == "from" => (x, *hours),
                        Some(x) => (*from_hours, x),
                        None => (*from_hours, *hours),
                    };
                    d.outage = Some(Outage { group: group.clone(), from: f * 60.0, hours: h });
                }
            }
        }
        let mut policy = Policy::Today;
        if let Some(c) = cand {
            for ch in &c.changes {
                match ch {
                    Change::Rule(p) => policy = *p,
                    Change::Cap(n) => d.cap = Some(*n),
                    Change::Spare(g, n) => d.spare.push((g.clone(), *n)),
                    Change::Demand(v) => d.demand *= v,
                    // floors and family policies are built by the scorer (score::family_arm)
                    Change::Floor(_) | Change::FamilyPolicy(_) => {}
                }
            }
        }
        (d, policy)
    }
}
