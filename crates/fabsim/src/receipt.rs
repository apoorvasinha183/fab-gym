//! Receipts for the run referee (docs/LEAN-CHECK.md): a run written out so a separate program in Lean can check, for
//! every job, the testbed's five rules. Times are the engine's `f64` written exactly (`M` or `M/E`, M over 2^E).

use std::collections::HashMap;
use std::io::Write;

use crate::engine::RunResult;
use crate::shop::{Per, Shop};

/// What a receipt says about the run it comes from.
#[derive(Clone, Debug)]
pub struct Meta {
    pub shop_sha256: String,
    pub seed: u64,
    pub policy: String,
    pub until: f64,
    /// the scored window, (from, to], as the score counts breaches
    pub from: f64,
    pub to: f64,
}

/// A nonnegative finite `f64` written exactly: an integer, or an odd integer over a power of two (`M/E`).
pub fn exact(x: f64) -> Option<String> {
    if !x.is_finite() || x < 0.0 {
        return None;
    }
    let bits = x.to_bits();
    let e = ((bits >> 52) & 0x7ff) as i64;
    let f = bits & ((1u64 << 52) - 1);
    let (mut m, mut exp) = if e == 0 { (f as u128, -1074i64) } else { ((f | (1u64 << 52)) as u128, e - 1075) };
    if m == 0 {
        return Some("0".into());
    }
    while m % 2 == 0 && exp < 0 {
        m /= 2;
        exp += 1;
    }
    if exp >= 0 {
        // whole numbers this large never occur as times here; refuse rather than overflow
        if exp > 70 {
            return None;
        }
        Some(format!("{}", m << exp))
    } else {
        Some(format!("{m}/{}", -exp))
    }
}

/// The inverse of `exact`.
pub fn from_exact(s: &str) -> Option<f64> {
    let (m, e) = match s.split_once('/') {
        Some((m, e)) => (m.parse::<u128>().ok()?, e.parse::<u32>().ok()?),
        None => (s.parse::<u128>().ok()?, 0),
    };
    let mut v = m as f64;
    if v as u128 != m {
        return None;
    }
    let mut e = e as i64;
    while e > 0 {
        let k = e.min(1000);
        v *= f64::from_bits(((1023 - k) as u64) << 52);
        e -= k;
    }
    Some(v)
}

fn ex(x: f64) -> Result<String, String> {
    exact(x).ok_or_else(|| format!("a time that cannot be written exactly: {x}"))
}

/// The state code a referee reads: 0 working, 1 idle, 2 setup, 3 scheduled down, 4 unscheduled down.
fn code(state: &str, why: &str) -> Result<u8, String> {
    Ok(match (state, why) {
        ("productive", _) => 0,
        ("standby", _) => 1,
        ("scheduled down", "setup") => 2,
        ("scheduled down", _) => 3,
        ("unscheduled down", _) => 4,
        _ => return Err(format!("unknown state {state}")),
    })
}

/// Write a run's receipt. The run must have been made with `record` on.
pub fn write_to(out: &mut dyn Write, shop: &Shop, r: &RunResult, m: &Meta) -> Result<(), String> {
    let io = |e: std::io::Error| e.to_string();
    if r.order.len() != r.states.len() + r.trace.len() {
        return Err("the run was not recorded (run it with record on)".into());
    }
    let policy: String = m.policy.chars().map(|c| if c.is_whitespace() { '_' } else { c }).collect();
    // version 2 lists the finished lots after the events (docs/LEAN-FINISH.md)
    writeln!(out, "fabgym-receipt 2").map_err(io)?;
    writeln!(out, "run {} {} {} {} {} {}", m.shop_sha256, m.seed, policy, ex(m.until)?, ex(m.from)?, ex(m.to)?).map_err(io)?;
    let gidx: HashMap<&str, usize> = shop.groups.iter().enumerate().map(|(i, g)| (g.name.as_str(), i)).collect();
    let group = |name: &str| gidx.get(name).copied().ok_or_else(|| format!("unknown group {name}"));
    for (i, g) in shop.groups.iter().enumerate() {
        writeln!(out, "group {i} {}", g.name.replace(' ', "_")).map_err(io)?;
    }
    for (i, t) in r.tools.iter().enumerate() {
        writeln!(out, "tool {i} {}", group(&t.group)?).map_err(io)?;
    }
    let ridx: HashMap<&str, usize> = shop.routes.iter().enumerate().map(|(i, x)| (x.name.as_str(), i)).collect();
    for (ri, route) in shop.routes.iter().enumerate() {
        writeln!(out, "route {ri} {}", route.steps.len()).map_err(io)?;
        for (k, st) in route.steps.iter().enumerate() {
            let batch = if st.per == Per::Batch { ex(st.batch.unwrap_or((1.0, 1e9)).1)? } else { "-".into() };
            let rework = st.rework.map(|x| x.0.to_string()).unwrap_or_else(|| "-".into());
            let (cto, cl) = match st.cqt {
                Some((to, l)) => (to.to_string(), ex(l)?),
                None => ("-".into(), "-".into()),
            };
            writeln!(out, "step {ri} {k} {} {batch} {} {rework} {cto} {cl}", group(&st.group)?, u8::from(st.sample.is_some())).map_err(io)?;
        }
    }
    let listed: HashMap<&str, usize> = shop.lots.iter().map(|l| (l.id.as_str(), l.step)).collect();
    for (i, l) in r.lots.iter().enumerate() {
        let ri = ridx.get(l.route.as_str()).ok_or_else(|| format!("unknown route {}", l.route))?;
        let first = listed.get(l.id.as_str()).copied().unwrap_or(0);
        writeln!(out, "lot {i} {ri} {} {first}", l.size).map_err(io)?;
    }
    // the events, in the log's own order
    let (mut si, mut ti, mut jobs) = (0usize, 0usize, 0usize);
    let mut k = 0;
    while k < r.order.len() {
        if !r.order[k] {
            let s = &r.states[si];
            writeln!(out, "S {} {} {}", s.tool_index, ex(s.time)?, code(s.state, s.why)?).map_err(io)?;
            si += 1;
            k += 1;
            continue;
        }
        // one job: the started steps logged together on one tool with one start and end
        let first = &r.trace[ti];
        let mut n = 0;
        while k + n < r.order.len() && r.order[k + n] {
            let x = &r.trace[ti + n];
            if x.tool != first.tool || x.start.to_bits() != first.start.to_bits() || x.end.to_bits() != first.end.to_bits() {
                break;
            }
            n += 1;
        }
        write!(out, "J {} {} {} {n}", first.tool, ex(first.start)?, ex(first.end)?).map_err(io)?;
        for x in &r.trace[ti..ti + n] {
            write!(out, " {} {} {}", x.lot, x.step, ex(x.arrive)?).map_err(io)?;
        }
        writeln!(out).map_err(io)?;
        ti += n;
        k += n;
        jobs += 1;
    }
    // every finished lot, with its exact finish time (rule 6: it did every step of its route)
    let (mut finished, mut fin_window) = (0usize, 0usize);
    for (i, l) in r.lots.iter().enumerate() {
        if let Some(d) = l.done {
            writeln!(out, "F {i} {}", ex(d)?).map_err(io)?;
            finished += 1;
            if d > m.from && d <= m.to {
                fin_window += 1;
            }
        }
    }
    let window = r.breaches.iter().filter(|b| b.t > m.from && b.t <= m.to).count();
    writeln!(out, "end {jobs} {} {} {window} {finished} {fin_window}", r.states.len(), r.breaches.len()).map_err(io)?;
    Ok(())
}

/// Write a run's receipt to a string.
pub fn write(shop: &Shop, r: &RunResult, m: &Meta) -> Result<String, String> {
    let mut v: Vec<u8> = vec![];
    write_to(&mut v, shop, r, m)?;
    String::from_utf8(v).map_err(|e| e.to_string())
}

/// The ways `tamper` can break a receipt, one per rule.
pub const TAMPER_KINDS: [&str; 5] = ["overlap", "skip", "overfill", "into-down", "breach"];

/// The ways `tamper` can fake a finished lot, all against rule 6 (docs/LEAN-FINISH.md).
pub const FINISH_TAMPER_KINDS: [&str; 3] = ["early", "unfinished", "count"];

/// A receipt read back just enough to break it in one place.
struct Read<'a> {
    lines: Vec<&'a str>,
    tool_group: Vec<usize>,
    /// per route, per step: (group, batch max, sampled)
    steps: Vec<Vec<(usize, Option<f64>, bool)>>,
    lot_route: Vec<usize>,
}

fn read(text: &str) -> Result<Read<'_>, String> {
    let lines: Vec<&str> = text.lines().collect();
    let (mut tool_group, mut steps, mut lot_route) = (vec![], vec![], vec![]);
    for l in &lines {
        let f: Vec<&str> = l.split(' ').collect();
        let num = |i: usize| f.get(i).and_then(|x| x.parse::<usize>().ok()).ok_or_else(|| format!("bad line {l}"));
        match f[0] {
            "tool" => tool_group.push(num(2)?),
            "route" => steps.push(Vec::with_capacity(num(2)?)),
            "step" => {
                let b = if f[4] == "-" { None } else { from_exact(f[4]) };
                steps.last_mut().ok_or("a step before its route")?.push((num(3)?, b, f[5] == "1"));
            }
            "lot" => lot_route.push(num(2)?),
            _ => {}
        }
    }
    Ok(Read { lines, tool_group, steps, lot_route })
}

/// Each lot's last job in a receipt: its step and end.
fn last_jobs(rd: &Read<'_>) -> HashMap<usize, (usize, f64)> {
    let mut last = HashMap::new();
    for l in &rd.lines {
        let f: Vec<&str> = l.split(' ').collect();
        if f[0] != "J" {
            continue;
        }
        let (Some(end), Ok(n)) = (from_exact(f[3]), f[4].parse::<usize>()) else { continue };
        for k in 0..n {
            if let (Ok(lot), Ok(step)) = (f[5 + 3 * k].parse::<usize>(), f[6 + 3 * k].parse::<usize>()) {
                last.insert(lot, (step, end));
            }
        }
    }
    last
}

fn split(l: &str) -> Vec<String> {
    l.split(' ').map(|s| s.to_string()).collect()
}

/// One broken copy of a receipt: one record changed in place, so the referee must reject it under the named rule.
pub fn tamper(text: &str, kind: &str) -> Result<String, String> {
    let rd = read(text)?;
    let mut lines: Vec<String> = rd.lines.iter().map(|s| s.to_string()).collect();
    let job = |i: usize| -> Option<(usize, f64, f64, Vec<(usize, usize)>)> {
        let f: Vec<&str> = rd.lines[i].split(' ').collect();
        if f[0] != "J" {
            return None;
        }
        let n: usize = f[4].parse().ok()?;
        let lots = (0..n).map(|k| (f[5 + 3 * k].parse().unwrap(), f[6 + 3 * k].parse().unwrap())).collect();
        Some((f[1].parse().ok()?, from_exact(f[2])?, from_exact(f[3])?, lots))
    };
    match kind {
        // a job moved to another tool of its group that is busy at its start
        "overlap" => {
            let mut busy_until: HashMap<usize, f64> = HashMap::new();
            for i in 0..lines.len() {
                let Some((t, s, e, _)) = job(i) else { continue };
                let g = rd.tool_group[t];
                let other = busy_until.iter().find(|(&o, &end)| o != t && rd.tool_group[o] == g && end > s).map(|(&o, _)| o);
                if let Some(o) = other {
                    let mut f = split(&lines[i]);
                    f[1] = o.to_string();
                    lines[i] = f.join(" ");
                    return Ok(lines.join("\n") + "\n");
                }
                busy_until.insert(t, e);
            }
            Err("no moment with two tools of one group busy".into())
        }
        // a lot's job relabelled one step on, past a step that does not sample
        "skip" => {
            for i in 0..lines.len() {
                let Some((_, _, _, lots)) = job(i) else { continue };
                if lots.len() != 1 {
                    continue;
                }
                let (lot, step) = lots[0];
                let route = &rd.steps[rd.lot_route[lot]];
                if step + 1 < route.len() && !route[step].2 {
                    let mut f = split(&lines[i]);
                    f[6] = (step + 1).to_string();
                    lines[i] = f.join(" ");
                    return Ok(lines.join("\n") + "\n");
                }
            }
            Err("no single-lot job before a step that does not sample".into())
        }
        // a lot in a batch made bigger than the batch's maximum
        "overfill" => {
            for i in 0..lines.len() {
                let Some((_, _, _, lots)) = job(i) else { continue };
                let (lot, step) = lots[0];
                if let Some(max) = rd.steps[rd.lot_route[lot]][step].1 {
                    if max < 1e8 {
                        let j = rd.lines.iter().position(|l| l.starts_with(&format!("lot {lot} "))).ok_or("no lot line")?;
                        let mut f = split(&lines[j]);
                        f[3] = (max.ceil() as i64 + 1).to_string();
                        lines[j] = f.join(" ");
                        return Ok(lines.join("\n") + "\n");
                    }
                }
            }
            Err("no job at a batch step with a maximum".into())
        }
        // the tool's change to working, logged as its job begins, made a scheduled down
        "into-down" => {
            for i in 1..lines.len() {
                let Some((t, s, _, _)) = job(i) else { continue };
                let f = split(&lines[i - 1]);
                if f[0] == "S" && f[1] == t.to_string() && from_exact(&f[2]) == Some(s) && f[3] == "0" {
                    let mut g = f;
                    g[3] = "3".into();
                    lines[i - 1] = g.join(" ");
                    return Ok(lines.join("\n") + "\n");
                }
            }
            Err("no job just after its tool turned to working".into())
        }
        // the claimed total of breaches one higher
        "breach" => {
            let i = lines.len() - 1;
            let mut f = split(&lines[i]);
            if f[0] != "end" {
                return Err("no end line".into());
            }
            f[3] = (f[3].parse::<u64>().map_err(|e| e.to_string())? + 1).to_string();
            lines[i] = f.join(" ");
            Ok(lines.join("\n") + "\n")
        }
        // a finish moved before its lot's last job ends
        "early" => {
            let last = last_jobs(&rd);
            for (i, l) in rd.lines.iter().enumerate() {
                let f: Vec<&str> = l.split(' ').collect();
                if f[0] != "F" {
                    continue;
                }
                let lot: usize = f[1].parse().map_err(|_| format!("bad line {l}"))?;
                if let Some(&(_, end)) = last.get(&lot) {
                    if end > 0.0 {
                        lines[i] = format!("F {lot} {}", exact(end / 2.0).ok_or("an end that cannot be halved exactly")?);
                        return Ok(lines.join("\n") + "\n");
                    }
                }
            }
            Err("no finished lot with a job that ends after time 0".into())
        }
        // a finish claimed for a lot whose last job leaves an unsampled step still to do
        "unfinished" => {
            let last = last_jobs(&rd);
            let done: std::collections::HashSet<usize> =
                rd.lines.iter().filter(|l| l.starts_with("F ")).filter_map(|l| l.split(' ').nth(1)?.parse().ok()).collect();
            let todo = last.iter().filter(|(lot, (k, _))| {
                let route = &rd.steps[rd.lot_route[**lot]];
                !done.contains(*lot) && route[k + 1..].iter().any(|s| !s.2)
            }).map(|(lot, _)| *lot).min();
            let Some(lot) = todo else { return Err("no lot with an unsampled step still to do".into()) };
            let i = rd.lines.iter().position(|l| l.starts_with("F ")).ok_or("no finished lot to relabel")?;
            let f = split(&lines[i]);
            // a finish no earlier than the lot's last job ends, so only the steps it still had to do are wrong
            let end = last[&lot].1;
            let at = if from_exact(&f[2]).is_some_and(|x| x >= end) { f[2].clone() } else { exact(end).ok_or("an end that cannot be written")? };
            lines[i] = format!("F {lot} {at}");
            Ok(lines.join("\n") + "\n")
        }
        // one more finished lot claimed than the receipt lists
        "count" => {
            let i = lines.len() - 1;
            let mut f = split(&lines[i]);
            if f[0] != "end" || f.len() < 7 {
                return Err("no version 2 end line".into());
            }
            f[5] = (f[5].parse::<u64>().map_err(|e| e.to_string())? + 1).to_string();
            lines[i] = f.join(" ");
            Ok(lines.join("\n") + "\n")
        }
        _ => Err(format!("unknown kind {kind}; one of {}, {}", TAMPER_KINDS.join(", "), FINISH_TAMPER_KINDS.join(", "))),
    }
}
