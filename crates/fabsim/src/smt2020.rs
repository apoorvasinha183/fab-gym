//! The SMT2020 high-volume testbed (Kopp, Hassoun, Kalir, Mönch, 2020) read into a shop.
//!
//! The files are tab-separated with a header row. A row with fewer fields than the header has
//! the rest empty. Times are put in minutes. Choices the files leave open are made as the
//! reference compile makes them (see NOTICE.md and docs/PROBLEM.md):
//!
//! - with one tool in a group, a maintenance calendar's first occurrence (FOA) is taken as given,
//!   read as minutes (the reference reads it without its units; kept for the exact match);
//!   with several tools each tool's first is drawn over one period;
//! - setups named on a route step apply from no setup (`>NAME`); `setup.txt` adds changes
//!   between named setups to the groups (or areas) it names;
//! - breakdowns attach to every group of the area they name.

use std::collections::HashMap;
use std::path::Path;

use crate::shop::{Group, LotSpec, Per, Pm, Release, Route, Shop, Step};

type Row = HashMap<String, String>;

fn rows(dir: &Path, name: &str) -> Result<Vec<Row>, String> {
    let text = std::fs::read_to_string(dir.join(name)).map_err(|e| format!("{name}: {e}"))?;
    let mut lines = text.lines();
    let head: Vec<String> = lines.next().ok_or(format!("{name}: empty"))?.split('\t').map(String::from).collect();
    let mut out = vec![];
    for line in lines {
        if line.is_empty() {
            continue;
        }
        let f: Vec<&str> = line.split('\t').collect();
        let mut r = Row::new();
        for (i, h) in head.iter().enumerate() {
            r.insert(h.clone(), f.get(i).copied().unwrap_or("").to_string());
        }
        out.push(r);
    }
    Ok(out)
}

fn g<'a>(r: &'a Row, k: &str) -> &'a str {
    r.get(k).map(|s| s.as_str()).unwrap_or("")
}

fn unit(u: &str) -> Result<f64, String> {
    match u {
        "min" | "" => Ok(1.0),
        "hr" => Ok(60.0),
        "day" => Ok(1440.0),
        _ => Err(format!("unknown unit {u:?}")),
    }
}

fn unit_or(u: &str, default: &str) -> Result<f64, String> {
    unit(if u.is_empty() { default } else { u })
}

fn f(s: &str) -> Result<f64, String> {
    s.trim().parse::<f64>().map_err(|e| format!("bad number {s:?}: {e}"))
}

fn fo(s: &str) -> Result<Option<f64>, String> {
    if s.is_empty() {
        Ok(None)
    } else {
        f(s).map(Some)
    }
}

fn i(s: &str) -> Result<i64, String> {
    s.trim().parse::<i64>().map_err(|e| format!("bad integer {s:?}: {e}"))
}

fn step(r: &Row) -> Result<Step, String> {
    let u = unit_or(g(r, "PTUNITS"), "min")?;
    let per = match g(r, "PTPER") {
        "per_piece" => Per::Piece,
        "per_lot" => Per::Lot,
        "per_batch" => Per::Batch,
        x => return Err(format!("unknown PTPER {x:?}")),
    };
    let mut st = Step {
        group: g(r, "STNFAM").into(),
        per,
        time: f(g(r, "PTIME"))? * u,
        spread: fo(g(r, "PTIME2"))?.filter(|x| *x != 0.0).unwrap_or(0.0) * u,
        batch: None,
        interval: None,
        batch_wait: None,
        setup: None,
        sample: None,
        rework: None,
        cqt: None,
    };
    if per == Per::Batch {
        let lo = if g(r, "BATCHMN").is_empty() { 0.0 } else { f(g(r, "BATCHMN"))? };
        let hi = if g(r, "BATCHMX").is_empty() { 1e9 } else { f(g(r, "BATCHMX"))? };
        st.batch = Some((lo, hi));
    }
    if !g(r, "PartInterval").is_empty() {
        st.interval = Some(f(g(r, "PartInterval"))? * unit_or(g(r, "PartIntUnits"), "min")?);
    }
    if !g(r, "BatchInterval").is_empty() {
        st.batch_wait = Some(f(g(r, "BatchInterval"))? * unit_or(g(r, "BatchIntUnits"), "min")?);
    }
    if !g(r, "SETUP").is_empty() {
        st.setup = Some(g(r, "SETUP").into());
    }
    if let Some(p) = fo(g(r, "StepPercent"))? {
        if p < 100.0 {
            st.sample = Some(p / 100.0);
        }
    }
    if !g(r, "RWKSTEP").is_empty() && fo(g(r, "REWORK"))?.is_some_and(|x| x != 0.0) {
        st.rework = Some(((i(g(r, "RWKSTEP"))? - 1) as usize, f(g(r, "REWORK"))? / 100.0));
    }
    if !g(r, "STEP_CQT").is_empty() && fo(g(r, "CQT"))?.is_some_and(|x| x != 0.0) {
        st.cqt = Some((
            (i(g(r, "STEP_CQT"))? - 1) as usize,
            f(g(r, "CQT"))? * unit_or(g(r, "CQTUNITS"), "hr")?,
        ));
    }
    Ok(st)
}

fn set(v: &mut Vec<(String, f64)>, k: String, x: f64) {
    match v.iter_mut().find(|(a, _)| *a == k) {
        Some(e) => e.1 = x,
        None => v.push((k, x)),
    }
}

/// Read the testbed's files from `dir` into a shop: groups, both routes, the lots in progress
/// (`WIP.txt`) and the lot starts (`order.txt`).
pub fn load(dir: &Path) -> Result<Shop, String> {
    let tools = rows(dir, "tool.txt.1l")?;
    let parts = rows(dir, "part.txt")?;
    let mut routes: Vec<(String, Vec<Row>)> = vec![];
    for p in &parts {
        let mut rs = rows(dir, g(p, "ROUTEFILE"))?;
        let mut keyed = vec![];
        for r in rs.drain(..) {
            keyed.push((i(g(&r, "STEP"))?, r));
        }
        keyed.sort_by_key(|(k, _)| *k);
        for (n, (k, _)) in keyed.iter().enumerate() {
            if *k != n as i64 + 1 {
                return Err(format!("{}: steps not numbered 1..n", g(p, "PART")));
            }
        }
        routes.push((g(p, "PART").into(), keyed.into_iter().map(|(_, r)| r).collect()));
    }
    let pmcal: HashMap<String, Row> =
        rows(dir, "pmcal.txt")?.into_iter().map(|r| (g(&r, "PMCALNAME").to_string(), r)).collect();
    let downcal: HashMap<String, Row> =
        rows(dir, "downcal.txt")?.into_iter().map(|r| (g(&r, "DOWNCALNAME").to_string(), r)).collect();
    let attach = rows(dir, "attach.txt")?;
    let setups = rows(dir, "setup.txt")?;
    let orders = rows(dir, "order.txt")?;
    let wip = rows(dir, "WIP.txt")?;
    let mv = rows(dir, "fromto.txt")?.into_iter().next().ok_or("fromto.txt: no rows")?;

    let mut groups: Vec<Group> = vec![];
    let mut area: Vec<String> = vec![];
    let mut idx: HashMap<String, usize> = HashMap::new();
    for r in &tools {
        let name = g(r, "STNFAM").to_string();
        let ltime = if g(r, "LTIME").is_empty() { 0.0 } else { f(g(r, "LTIME"))? };
        let utime = if g(r, "ULTIME").is_empty() { 0.0 } else { f(g(r, "ULTIME"))? };
        let grp = Group {
            name: name.clone(),
            count: f(g(r, "STNQTY"))? as usize,
            load: ltime * unit_or(g(r, "LTUNITS"), "min")?,
            unload: utime * unit_or(g(r, "ULTUNITS"), "min")?,
            batch_wait: None,
            breakdown: None,
            setups: vec![],
            pm: vec![],
            pm_pieces: vec![],
            down: vec![],
        };
        if let Some(&k) = idx.get(&name) {
            groups[k] = grp;
            area[k] = g(r, "STNGRP").into();
        } else {
            idx.insert(name, groups.len());
            groups.push(grp);
            area.push(g(r, "STNGRP").into());
        }
    }
    for (_, rs) in &routes {
        for r in rs {
            if !g(r, "SETUP").is_empty() && !g(r, "STIME").is_empty() {
                let k = *idx.get(g(r, "STNFAM")).ok_or("route names an unknown group")?;
                let m = f(g(r, "STIME"))? * unit_or(g(r, "STUNITS"), "min")?;
                set(&mut groups[k].setups, format!(">{}", g(r, "SETUP")), m);
            }
        }
    }
    for r in &setups {
        let fam = g(r, "IGNORE");
        let m = f(g(r, "STIME"))? * unit_or(g(r, "STUNITS"), "min")?;
        for k in 0..groups.len() {
            if groups[k].name == fam || area[k] == fam {
                set(&mut groups[k].setups, format!("{}>{}", g(r, "CURSETUP"), g(r, "NEWSETUP")), m);
            }
        }
    }
    for a in &attach {
        if g(a, "CALTYPE") == "pm" && g(a, "RESTYPE") == "stnfam" && idx.contains_key(g(a, "RESNAME")) {
            let c = pmcal.get(g(a, "CALNAME")).ok_or("attach names an unknown pm calendar")?;
            let mid = f(g(c, "MTTR"))?;
            let half = if g(c, "MTTR2").is_empty() { 0.0 } else { f(g(c, "MTTR2"))? };
            let u = unit(g(c, "MTTRUNITS"))?;
            let k = idx[g(a, "RESNAME")];
            let first = if groups[k].count == 1 && !g(a, "FOA").is_empty() {
                Some(f(g(a, "FOA"))?)
            } else {
                None
            };
            let lo = (mid - half) * u;
            let hi = (mid + half) * u;
            if g(c, "PMCALTYPE") == "mtbpm_by_pieces" {
                groups[k].pm_pieces.push(Pm { every: f(g(c, "MTBPM"))?, lo, hi, first });
            } else {
                let every = f(g(c, "MTBPM"))? * unit(g(c, "MTBPMUNITS"))?;
                groups[k].pm.push(Pm { every, lo, hi, first });
            }
        } else if g(a, "CALTYPE") == "down" && g(a, "RESTYPE") == "stngrp" {
            let c = downcal.get(g(a, "CALNAME")).ok_or("attach names an unknown down calendar")?;
            let mttf = f(g(c, "MTTF"))? * unit(g(c, "MTTFUNITS"))?;
            let mttr = f(g(c, "MTTR"))? * unit(g(c, "MTTRUNITS"))?;
            for k in 0..groups.len() {
                if area[k] == g(a, "RESNAME") {
                    groups[k].breakdown = Some((mttf, mttr));
                }
            }
        }
    }
    // a breakdown with no failures is no breakdown
    for grp in &mut groups {
        if grp.breakdown.is_some_and(|b| b.0 <= 0.0) {
            grp.breakdown = None;
        }
    }

    let mut out_routes = vec![];
    for (part, rs) in &routes {
        let steps = rs.iter().map(step).collect::<Result<Vec<_>, _>>()?;
        out_routes.push(Route { name: part.clone(), steps });
    }
    let mut lots = vec![];
    for (n, w) in wip.iter().enumerate() {
        lots.push(LotSpec {
            id: format!("wip.{n}.{}", g(w, "LOT")),
            route: g(w, "PART").into(),
            size: i(g(w, "PIECES"))?,
            priority: f(g(w, "PRIOR"))?,
            start: 0.0,
            step: (i(g(w, "CURSTEP"))? - 1) as usize,
        });
    }
    let mut releases = vec![];
    for o in &orders {
        releases.push(Release {
            route: g(o, "PART").into(),
            size: i(g(o, "PIECES"))?,
            priority: f(g(o, "PRIOR"))?,
            every: f(g(o, "REPEAT"))? * unit(g(o, "RUNITS"))?,
            first: 0.0,
            count: Some(i(g(o, "RPT#"))?),
            prefix: g(o, "LOT").into(),
        });
    }
    let mid = f(g(&mv, "DTIME"))?;
    let half = f(g(&mv, "DTIME2"))?;
    Ok(Shop {
        transport: (mid - half, mid + half),
        cap: None,
        probes: vec![],
        groups,
        routes: out_routes,
        lots,
        releases,
    })
}

/// Each tool group's area (STNGRP in tool.txt.1l), in file order, for viewers.
pub fn areas(dir: &Path) -> Result<Vec<(String, String)>, String> {
    Ok(rows(dir, "tool.txt.1l")?.iter().map(|r| (g(r, "STNFAM").to_string(), g(r, "STNGRP").to_string())).collect())
}
