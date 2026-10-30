//! The simulator for the browser, with plain exports and no generated glue.
//!
//! JS writes the shop text into memory from `fg_alloc`, calls `fg_load`, then `fg_run`. Results
//! come back as a JSON summary (`fg_json_*`) and two flat f64 arrays:
//! trace  [lot, step, tool, arrive, start, end] per started step,
//! states [tool, time, state] per tool state change (0 productive, 1 standby, 2 maintenance,
//!        3 breakdown, 4 setup).
//! With a fleet (docs/LIVE-REAL.md), two flat f32 arrays more:
//! fleet entries [vehicle, stretch, in, out (-1 while on it), loaded] per stay on a stretch,
//! fleet hoists  [vehicle, node, lot, up, start, end] per hoist.

use std::cell::RefCell;
use std::fmt::Write as _;

use fabsim::dials::Dials;
use fabsim::engine::{RunOptions, RunResult};
use fabsim::shop::Shop;

#[derive(Default)]
struct State {
    shop: Option<Shop>,
    dials: Dials,
    res: Option<RunResult>,
    /// the shop the last run used (the loaded one with the dials and any outage applied)
    ran: Option<Shop>,
    json: String,
    quick: String,
    trace: Vec<f64>,
    states: Vec<f64>,
    fleet_e: Vec<f32>,
    fleet_h: Vec<f32>,
}

/// The fleet's stays and hoists as flat arrays for the page (empty without a fleet).
pub fn fleet_arrays(res: &RunResult) -> (Vec<f32>, Vec<f32>) {
    let Some(f) = &res.fleet else { return (vec![], vec![]) };
    let e = f.entries.iter().flat_map(|x| [x.vehicle as f32, x.edge as f32, x.t_in as f32, if x.t_out.is_finite() { x.t_out as f32 } else { -1.0 }, x.loaded as u8 as f32]).collect();
    let h = f.hoists.iter().flat_map(|x| [x.vehicle as f32, x.stop as f32, x.lot as f32, x.up as u8 as f32, x.t0 as f32, x.t1 as f32]).collect();
    (e, h)
}

/// A dispatch rule the page offers.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Policy {
    /// today's rule: hot lots first, then no setup change, then oldest
    Today,
    /// first come, first served
    Fifo,
    /// shortest processing first
    Spt,
    /// family B's lots before family A's, today's order within each (docs/ASK-FAMILIES.md)
    BFirst,
}

impl Policy {
    pub fn from_code(c: i32) -> Policy {
        match c {
            1 => Policy::Fifo,
            2 => Policy::Spt,
            3 => Policy::BFirst,
            _ => Policy::Today,
        }
    }
}

/// The base shop with the dials applied, then one group (by index) down from `down_at` minutes
/// for `down_hours` (none when `down_group` < 0 or `down_hours` <= 0).
pub fn prepare(base: &Shop, dials: &Dials, down_group: i32, down_at: f64, down_hours: f64) -> Result<Shop, String> {
    let mut shop = dials.apply(base)?;
    if down_group >= 0 && down_hours > 0.0 {
        let g = shop.groups.get_mut(down_group as usize).ok_or_else(|| format!("no tool group {down_group}"))?;
        g.down.push((down_at, down_at + down_hours * 60.0));
    }
    Ok(shop)
}

pub fn run_policy(shop: &Shop, opts: &RunOptions, policy: Policy) -> RunResult {
    let p = match policy {
        Policy::Fifo => fabsim::policy::Policy::Fifo,
        Policy::Spt => fabsim::policy::Policy::Spt,
        Policy::Today => fabsim::policy::Policy::Today,
        Policy::BFirst => {
            let mut pick = |d: &fabsim::engine::Decision| fabsim::twofam::b_first(d, "B");
            return fabsim::engine::run(shop, opts, Some(&mut pick));
        }
    };
    fabsim::policy::run_with(shop, opts, p)
}

/// The totals of one run, for comparing paired seeds.
#[derive(Clone, Debug, PartialEq)]
pub struct Quick {
    pub moves: i64,
    pub finished: i64,
    pub wafers_out: i64,
    /// lots that broke a queue-time limit
    pub breaches: usize,
    pub wait_lot_hours: f64,
    /// lots waiting at the end
    pub waiting: i64,
}

/// Run `days` days without recording and keep the totals.
pub fn quick(shop: &Shop, seed: u64, days: f64, policy: Policy) -> Quick {
    let r = run_policy(shop, &RunOptions { seed, until: Some(days * 1440.0), record: false }, policy);
    Quick {
        moves: r.moves,
        finished: r.finished,
        wafers_out: r.lots.iter().filter(|l| l.done.is_some()).map(|l| l.size).sum(),
        breaches: r.breaches.len(),
        wait_lot_hours: r.wait_lot_minutes / 60.0,
        waiting: r.waiting,
    }
}

pub fn quick_json(q: &Quick) -> String {
    format!(
        "{{\"moves\":{},\"finished\":{},\"wafers_out\":{},\"breaches\":{},\"wait_lot_hours\":{},\"waiting\":{}}}",
        q.moves, q.finished, q.wafers_out, q.breaches, num(q.wait_lot_hours), q.waiting
    )
}

/// The Student t quantile, for the page's intervals.
#[no_mangle]
pub extern "C" fn fg_t(p: f64, df: f64) -> f64 {
    fabsim::uq::t_quantile(p, df)
}

/// Set the dials for later runs; 0 on success, else the error is in the JSON buffer.
/// `cap` <= 0 means no cap of the page's own (the shop's own cap stays). `defects` is the defect holds dial: 0 off,
/// k > 0 k times the assumed central hold lengths (docs/RL-DEFECTS.md).
#[no_mangle]
pub extern "C" fn fg_dials(breakdowns: f64, repair: f64, demand: f64, hot: f64, rework: f64, cap: f64, defects: f64) -> i32 {
    ST.with(|st| {
        let mut st = st.borrow_mut();
        let d = Dials { breakdowns, repair, demand, hot, rework, cap: if cap > 0.0 { Some(cap as i64) } else { None }, defects: Some(defects), ..Dials::default() };
        match st.shop.as_ref().map(|s| d.apply(s)) {
            Some(Err(e)) => {
                st.json = format!("{{\"error\":{}}}", js(&e));
                1
            }
            _ => {
                st.dials = d;
                0
            }
        }
    })
}

/// A quick run with the current dials; the totals go to the quick buffer. 0 on success.
#[no_mangle]
pub extern "C" fn fg_quick(seed: f64, days: f64, policy: i32, down_group: i32, down_at: f64, down_hours: f64) -> i32 {
    ST.with(|st| {
        let mut st = st.borrow_mut();
        let Some(base) = st.shop.as_ref() else { return 1 };
        match prepare(base, &st.dials, down_group, down_at, down_hours) {
            Ok(shop) => {
                st.quick = quick_json(&quick(&shop, seed as u64, days, Policy::from_code(policy)));
                0
            }
            Err(e) => {
                st.quick = format!("{{\"error\":{}}}", js(&e));
                1
            }
        }
    })
}

#[no_mangle]
pub extern "C" fn fg_quick_ptr() -> *const u8 {
    ST.with(|st| st.borrow().quick.as_ptr())
}
#[no_mangle]
pub extern "C" fn fg_quick_len() -> usize {
    ST.with(|st| st.borrow().quick.len())
}

thread_local! {
    static ST: RefCell<State> = RefCell::new(State::default());
}

#[no_mangle]
pub extern "C" fn fg_alloc(n: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(n.max(1));
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

/// # Safety
/// `p` and `n` must come from one `fg_alloc` call.
#[no_mangle]
pub unsafe extern "C" fn fg_free(p: *mut u8, n: usize) {
    drop(Vec::from_raw_parts(p, 0, n.max(1)));
}

/// Read a shop from `n` bytes of text at `p`; 0 on success, else the error is in the JSON buffer.
///
/// # Safety
/// `p` must point to `n` readable bytes.
#[no_mangle]
pub unsafe extern "C" fn fg_load(p: *const u8, n: usize) -> i32 {
    let text = String::from_utf8_lossy(std::slice::from_raw_parts(p, n)).into_owned();
    ST.with(|st| {
        let mut st = st.borrow_mut();
        match Shop::parse(&text) {
            Ok(s) => {
                st.shop = Some(s);
                0
            }
            Err(e) => {
                st.json = format!("{{\"error\":{}}}", js(&e));
                1
            }
        }
    })
}

fn js(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            c if (c as u32) < 0x20 => {
                let _ = write!(o, "\\u{:04x}", c as u32);
            }
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

fn num(x: f64) -> String {
    if x.is_finite() {
        format!("{x}")
    } else {
        "null".into()
    }
}

/// Run the loaded shop for `days` simulated days.
/// `policy`: 0 today's rule, 1 first come first served, 2 shortest processing first, 3 family B first.
/// `down_group` >= 0 takes that whole tool group down from `down_at` for `down_hours`.
#[no_mangle]
pub extern "C" fn fg_run(seed: f64, days: f64, policy: i32, down_group: i32, down_at: f64, down_hours: f64) -> i32 {
    ST.with(|st| {
        let mut st = st.borrow_mut();
        let Some(base) = st.shop.as_ref() else { return 1 };
        let shop = match prepare(base, &st.dials, down_group, down_at, down_hours) {
            Ok(s) => s,
            Err(e) => {
                st.json = format!("{{\"error\":{}}}", js(&e));
                return 1;
            }
        };
        let opts = RunOptions { seed: seed as u64, until: Some(days * 1440.0), record: true };
        let res = run_policy(&shop, &opts, Policy::from_code(policy));
        st.trace = res
            .trace
            .iter()
            .flat_map(|t| [t.lot as f64, t.step as f64, t.tool as f64, t.arrive, t.start, t.end])
            .collect();
        st.states = res
            .states
            .iter()
            .flat_map(|s| {
                let code = match (s.state, s.why) {
                    ("productive", _) => 0.0,
                    ("standby", _) => 1.0,
                    ("scheduled down", "setup") => 4.0,
                    ("scheduled down", _) => 2.0,
                    _ => 3.0,
                };
                [s.tool_index as f64, s.time, code]
            })
            .collect();
        let (fe, fh) = fleet_arrays(&res);
        st.fleet_e = fe;
        st.fleet_h = fh;
        st.json = summary(&shop, &res);
        st.res = Some(res);
        st.ran = Some(shop);
        0
    })
}

/// The editor's moods for the last run (docs/FLOOR-LOOK.md): `fabsim moods`'s frames every `every` minutes, as JSON
/// read through `fg_json_ptr` and `fg_json_len`. 1 with no run yet.
#[no_mangle]
pub extern "C" fn fg_moods(every: f64) -> i32 {
    ST.with(|st| {
        let mut st = st.borrow_mut();
        let (Some(shop), Some(res)) = (st.ran.as_ref(), st.res.as_ref()) else { return 1 };
        if every <= 0.0 {
            return 1;
        }
        let j = fabsim::moods::frames_json(shop, res, res.until, every).to_string();
        st.json = j;
        0
    })
}

pub fn summary(shop: &Shop, res: &RunResult) -> String {
    let mut o = String::from("{");
    let _ = write!(o, "\"until\":{},\"finished\":{},\"moves\":{},\"decisions\":{},\"breaches\":{},", num(res.until), res.finished, res.moves, res.decisions, res.breaches.len());
    o.push_str("\"groups\":[");
    for (i, g) in res.groups.iter().enumerate() {
        if i > 0 {
            o.push(',');
        }
        let _ = write!(o, "[{},{},{},{},{}]", js(&g.name), g.count, num(g.busy), num(g.wait), g.visits);
    }
    o.push_str("],\"tools\":[");
    let gi: std::collections::HashMap<&str, usize> = shop.groups.iter().enumerate().map(|(i, g)| (g.name.as_str(), i)).collect();
    for (i, t) in res.tools.iter().enumerate() {
        if i > 0 {
            o.push(',');
        }
        let _ = write!(o, "{}", gi[t.group.as_str()]);
    }
    o.push_str("],\"routes\":[");
    for (i, r) in shop.routes.iter().enumerate() {
        if i > 0 {
            o.push(',');
        }
        o.push('[');
        o.push_str(&js(&r.name));
        o.push_str(",[");
        for (k, s) in r.steps.iter().enumerate() {
            if k > 0 {
                o.push(',');
            }
            let _ = write!(o, "{}", gi[s.group.as_str()]);
        }
        o.push_str("]]");
    }
    o.push_str("],\"families\":[");
    for (i, r) in shop.routes.iter().enumerate() {
        if i > 0 {
            o.push(',');
        }
        o.push_str(&js(shop.family_of(&r.name)));
    }
    o.push_str("],\"lots\":[");
    let ri: std::collections::HashMap<&str, usize> = shop.routes.iter().enumerate().map(|(i, r)| (r.name.as_str(), i)).collect();
    for (i, l) in res.lots.iter().enumerate() {
        if i > 0 {
            o.push(',');
        }
        let done = l.done.map(num).unwrap_or_else(|| "null".into());
        let _ = write!(o, "[{},{},{},{},{},{},{}]", js(&l.id), ri[l.route.as_str()], num(l.priority), l.size, num(l.release), done, l.wip as u8);
    }
    o.push_str("]}");
    o
}

#[no_mangle]
pub extern "C" fn fg_json_ptr() -> *const u8 {
    ST.with(|st| st.borrow().json.as_ptr())
}
#[no_mangle]
pub extern "C" fn fg_json_len() -> usize {
    ST.with(|st| st.borrow().json.len())
}
#[no_mangle]
pub extern "C" fn fg_trace_ptr() -> *const f64 {
    ST.with(|st| st.borrow().trace.as_ptr())
}
#[no_mangle]
pub extern "C" fn fg_trace_len() -> usize {
    ST.with(|st| st.borrow().trace.len())
}
#[no_mangle]
pub extern "C" fn fg_states_ptr() -> *const f64 {
    ST.with(|st| st.borrow().states.as_ptr())
}
#[no_mangle]
pub extern "C" fn fg_states_len() -> usize {
    ST.with(|st| st.borrow().states.len())
}

#[no_mangle]
pub extern "C" fn fg_fleet_entries_ptr() -> *const f32 {
    ST.with(|st| st.borrow().fleet_e.as_ptr())
}
#[no_mangle]
pub extern "C" fn fg_fleet_entries_len() -> usize {
    ST.with(|st| st.borrow().fleet_e.len())
}
#[no_mangle]
pub extern "C" fn fg_fleet_hoists_ptr() -> *const f32 {
    ST.with(|st| st.borrow().fleet_h.as_ptr())
}
#[no_mangle]
pub extern "C" fn fg_fleet_hoists_len() -> usize {
    ST.with(|st| st.borrow().fleet_h.len())
}
