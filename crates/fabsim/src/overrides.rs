//! Failure and recovery per tool and per rail piece (docs/OVERRIDES.md): a JSON file listing only what differs from
//! today. With none, every tool behaves as its group's records say and no rail stretch fails.

use crate::shop::Shop;
use crate::track::Track;
use serde_json::{Map, Value};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Overrides {
    /// by group name, for every tool of the group
    pub groups: BTreeMap<String, ToolSet>,
    /// by tool name (`GROUP#k`, k from 1); wins over its group
    pub tools: BTreeMap<String, ToolSet>,
    /// by the stretch's index on the shop's track
    pub rails: BTreeMap<usize, RailSet>,
}

/// What one tool does; a field left `None` keeps today's setting.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ToolSet {
    pub breakdowns: Option<Breakdowns>,
    pub maintenance: Option<Maintenance>,
    pub recovery: Option<Recovery>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Breakdowns {
    None,
    /// exponential time to failure and repair time, minutes (today's kind)
    Random { mttf: f64, mttr: f64 },
    /// every so many wafers processed, down uniform(lo, hi) minutes
    ByWafers { every: f64, lo: f64, hi: f64 },
}

#[derive(Clone, Debug, PartialEq)]
pub enum Maintenance {
    None,
    Calendar { every: f64, lo: f64, hi: f64 },
    ByWafers { every: f64, lo: f64, hi: f64 },
}

#[derive(Clone, Debug, PartialEq)]
pub enum Recovery {
    /// today's: repaired where it stands
    InPlace,
    /// while the group has a spare, back after `swap` minutes; the broken unit returns to the spares once repaired
    Swap { spares: u32, swap: f64 },
    /// as a breakdown starts, hold the lots the tool finished in the last `lookback` minutes for `hold` minutes
    HoldLots { lookback: f64, hold: f64 },
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct RailSet {
    pub breakdowns: Option<RailBreakdowns>,
    pub recovery: Option<RailRecovery>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum RailBreakdowns {
    None,
    Random { mttf: f64, mttr: f64 },
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum RailRecovery {
    /// vehicles take another open stretch (today's detour rule)
    RouteAround,
    /// vehicles queue at the stretch until it is repaired
    Wait,
}

type R<T> = Result<T, String>;

fn obj<'v>(v: &'v Value, path: &str) -> R<&'v Map<String, Value>> {
    v.as_object().ok_or_else(|| format!("{path}: wants an object"))
}

/// A time given as `NAME_minutes` or `NAME_hours`, in minutes; zero or more.
fn minutes(o: &Map<String, Value>, name: &str, path: &str) -> R<f64> {
    let p = format!("{path}.{name}");
    let v = match (o.get(&format!("{name}_minutes")), o.get(&format!("{name}_hours"))) {
        (Some(m), None) => m.as_f64().ok_or_else(|| format!("{p}_minutes: wants a number"))?,
        (None, Some(h)) => h.as_f64().ok_or_else(|| format!("{p}_hours: wants a number"))? * 60.0,
        (Some(_), Some(_)) => return Err(format!("{p}: give {name}_minutes or {name}_hours, not both")),
        (None, None) => return Err(format!("{p}: wants {name}_minutes or {name}_hours")),
    };
    if !(v >= 0.0) || !v.is_finite() {
        return Err(format!("{p}: wants a time of zero or more"));
    }
    Ok(v)
}

/// A positive time to failure.
fn mttf(o: &Map<String, Value>, path: &str) -> R<f64> {
    let v = minutes(o, "mttf", path)?;
    if v <= 0.0 {
        return Err(format!("{path}.mttf: wants a time above zero"));
    }
    Ok(v)
}

/// `minutes: [lo, hi]` or `hours: [lo, hi]`, 0 <= lo <= hi.
fn range(o: &Map<String, Value>, path: &str) -> R<(f64, f64)> {
    let (key, scale) = if o.contains_key("minutes") { ("minutes", 1.0) } else { ("hours", 60.0) };
    let p = format!("{path}.{key}");
    let a = o.get(key).and_then(|v| v.as_array()).ok_or_else(|| format!("{path}.minutes: wants [lo, hi]"))?;
    let n: Vec<f64> = a.iter().filter_map(|x| x.as_f64()).collect();
    if n.len() != 2 || a.len() != 2 || !(n[0] >= 0.0 && n[0] <= n[1]) || !n[1].is_finite() {
        return Err(format!("{p}: wants [lo, hi] with 0 <= lo <= hi"));
    }
    Ok((n[0] * scale, n[1] * scale))
}

fn every_wafers(o: &Map<String, Value>, path: &str) -> R<f64> {
    let v = o.get("every").and_then(|x| x.as_f64()).ok_or_else(|| format!("{path}.every: wants a number of wafers"))?;
    if !(v > 0.0) || !v.is_finite() {
        return Err(format!("{path}.every: wants a number of wafers above zero"));
    }
    Ok(v)
}

fn kind<'v>(o: &'v Map<String, Value>, path: &str) -> R<&'v str> {
    o.get("kind").and_then(|k| k.as_str()).ok_or_else(|| format!("{path}.kind: wants a kind"))
}

fn breakdowns(v: &Value, path: &str) -> R<Breakdowns> {
    let o = obj(v, path)?;
    match kind(o, path)? {
        "none" => Ok(Breakdowns::None),
        "random" => Ok(Breakdowns::Random { mttf: mttf(o, path)?, mttr: minutes(o, "mttr", path)? }),
        "by_wafers" => {
            let (lo, hi) = range(o, path)?;
            Ok(Breakdowns::ByWafers { every: every_wafers(o, path)?, lo, hi })
        }
        k => Err(format!("{path}.kind: {k:?} is not none, random or by_wafers")),
    }
}

fn maintenance(v: &Value, path: &str) -> R<Maintenance> {
    let o = obj(v, path)?;
    match kind(o, path)? {
        "none" => Ok(Maintenance::None),
        "calendar" => {
            let every = minutes(o, "every", path)?;
            if every <= 0.0 {
                return Err(format!("{path}.every: wants a period above zero"));
            }
            let (lo, hi) = range(o, path)?;
            Ok(Maintenance::Calendar { every, lo, hi })
        }
        "by_wafers" => {
            let (lo, hi) = range(o, path)?;
            Ok(Maintenance::ByWafers { every: every_wafers(o, path)?, lo, hi })
        }
        k => Err(format!("{path}.kind: {k:?} is not none, calendar or by_wafers")),
    }
}

fn recovery(v: &Value, path: &str) -> R<Recovery> {
    let o = obj(v, path)?;
    match kind(o, path)? {
        "repair_in_place" => Ok(Recovery::InPlace),
        "swap_to_spare" => {
            let s = o.get("spares").and_then(|x| x.as_i64()).filter(|n| *n >= 0)
                .ok_or_else(|| format!("{path}.spares: wants a whole number of spares, zero or more"))?;
            Ok(Recovery::Swap { spares: s as u32, swap: minutes(o, "swap", path)? })
        }
        "repair_and_hold_lots" => Ok(Recovery::HoldLots { lookback: minutes(o, "lookback", path)?, hold: minutes(o, "hold", path)? }),
        k => Err(format!("{path}.kind: {k:?} is not repair_in_place, swap_to_spare or repair_and_hold_lots")),
    }
}

fn toolset(v: &Value, path: &str) -> R<ToolSet> {
    let o = obj(v, path)?;
    let mut s = ToolSet::default();
    for (k, x) in o {
        let p = format!("{path}.{k}");
        match k.as_str() {
            "breakdowns" => s.breakdowns = Some(breakdowns(x, &p)?),
            "maintenance" => s.maintenance = Some(maintenance(x, &p)?),
            "recovery" => s.recovery = Some(recovery(x, &p)?),
            _ => return Err(format!("{p}: not breakdowns, maintenance or recovery")),
        }
    }
    Ok(s)
}

fn railset(v: &Value, path: &str) -> R<RailSet> {
    let o = obj(v, path)?;
    let mut s = RailSet::default();
    for (k, x) in o {
        let p = format!("{path}.{k}");
        match k.as_str() {
            "breakdowns" => {
                let b = obj(x, &p)?;
                s.breakdowns = Some(match kind(b, &p)? {
                    "none" => RailBreakdowns::None,
                    "random" => RailBreakdowns::Random { mttf: mttf(b, &p)?, mttr: minutes(b, "mttr", &p)? },
                    k => return Err(format!("{p}.kind: {k:?} is not none or random")),
                });
            }
            "recovery" => {
                let b = obj(x, &p)?;
                s.recovery = Some(match kind(b, &p)? {
                    "route_around" => RailRecovery::RouteAround,
                    "wait" => RailRecovery::Wait,
                    k => return Err(format!("{p}.kind: {k:?} is not route_around or wait")),
                });
            }
            _ => return Err(format!("{p}: not breakdowns or recovery")),
        }
    }
    Ok(s)
}

impl Overrides {
    /// Read an overrides file against the shop it is for. Refused, naming the path, for an unknown group, tool or
    /// stretch, an unknown kind, a missing or negative number, lo above hi, and rail settings without a fleet.
    pub fn parse(text: &str, shop: &Shop) -> R<Overrides> {
        let v: Value = serde_json::from_str(text).map_err(|e| format!("not JSON: {e}"))?;
        let top = obj(&v, "the file")?;
        if top.get("fabgym-overrides").and_then(|x| x.as_i64()) != Some(1) {
            return Err("fabgym-overrides: the file starts with \"fabgym-overrides\": 1".into());
        }
        let mut out = Overrides::default();
        for (k, x) in top {
            match k.as_str() {
                "fabgym-overrides" => {}
                "groups" => {
                    for (g, s) in obj(x, "groups")? {
                        let p = format!("groups.{g}");
                        if shop.group(g).is_none() {
                            return Err(format!("{p}: the shop has no such group"));
                        }
                        out.groups.insert(g.clone(), toolset(s, &p)?);
                    }
                }
                "tools" => {
                    for (t, s) in obj(x, "tools")? {
                        let p = format!("tools.{t}");
                        let ok = t.rsplit_once('#').is_some_and(|(g, k)| {
                            shop.group(g).is_some_and(|gr| k.parse::<usize>().is_ok_and(|k| k >= 1 && k <= gr.count))
                        });
                        if !ok {
                            return Err(format!("{p}: the shop has no such tool (tools are named GROUP#k, k from 1)"));
                        }
                        out.tools.insert(t.clone(), toolset(s, &p)?);
                    }
                }
                "rails" => {
                    let rails = obj(x, "rails")?;
                    if rails.is_empty() {
                        continue;
                    }
                    let plan_links = shop.plan.as_ref().is_some_and(|p| !p.links.is_empty());
                    if shop.fleet.is_none() || (shop.oht.is_none() && !plan_links) {
                        return Err("rails: rail settings need a fleet (a fleet record and a track)".into());
                    }
                    let track = Track::from_shop(shop);
                    let by_name: std::collections::HashMap<String, usize> = (0..track.nodes().len()).map(|i| (track.name(i), i)).collect();
                    for (id, s) in rails {
                        let p = format!("rails.{id}");
                        let e = id.split_once('>').and_then(|(a, b)| {
                            let (a, b) = (*by_name.get(a)?, *by_name.get(b)?);
                            track.edges().iter().position(|e| e.from == a && e.to == b)
                        });
                        let e = e.ok_or_else(|| format!("{p}: the track has no such stretch (named FROM>TO by plan node, as fabsim fab-export writes)"))?;
                        out.rails.insert(e, railset(s, &p)?);
                    }
                }
                _ => return Err(format!("{k}: not groups, tools or rails")),
            }
        }
        Ok(out)
    }

    /// One tool's settings: its own, else its group's, field by field.
    pub fn tool(&self, group: &str, tool: &str) -> ToolSet {
        let g = self.groups.get(group);
        let t = self.tools.get(tool);
        let pick = |f: fn(&ToolSet) -> bool| t.filter(|s| f(s)).or(g.filter(|s| f(s)));
        ToolSet {
            breakdowns: pick(|s| s.breakdowns.is_some()).and_then(|s| s.breakdowns.clone()),
            maintenance: pick(|s| s.maintenance.is_some()).and_then(|s| s.maintenance.clone()),
            recovery: pick(|s| s.recovery.is_some()).and_then(|s| s.recovery.clone()),
        }
    }
}
