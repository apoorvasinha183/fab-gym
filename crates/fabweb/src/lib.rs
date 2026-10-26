//! The simulator for the browser, with plain exports and no generated glue.
//!
//! JS writes the shop text into memory from `fg_alloc`, calls `fg_load`, then `fg_run`. Results
//! come back as a JSON summary (`fg_json_*`) and two flat f64 arrays:
//! trace  [lot, step, tool, arrive, start, end] per started step,
//! states [tool, time, state] per tool state change (0 productive, 1 standby, 2 maintenance,
//!        3 breakdown, 4 setup).

use std::cell::RefCell;
use std::fmt::Write as _;

use fabsim::engine::{run, Decision, RunOptions, RunResult};
use fabsim::shop::Shop;

#[derive(Default)]
struct State {
    shop: Option<Shop>,
    res: Option<RunResult>,
    json: String,
    trace: Vec<f64>,
    states: Vec<f64>,
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
/// `policy`: 0 today's rule, 1 first come first served, 2 shortest processing first.
/// `down_group` >= 0 takes that whole tool group down from `down_at` for `down_hours`.
#[no_mangle]
pub extern "C" fn fg_run(seed: f64, days: f64, policy: i32, down_group: i32, down_at: f64, down_hours: f64) -> i32 {
    ST.with(|st| {
        let mut st = st.borrow_mut();
        let Some(base) = st.shop.as_ref() else { return 1 };
        let mut shop = base.clone();
        if down_group >= 0 && (down_group as usize) < shop.groups.len() && down_hours > 0.0 {
            shop.groups[down_group as usize].down.push((down_at, down_at + down_hours * 60.0));
        }
        let opts = RunOptions { seed: seed as u64, until: Some(days * 1440.0), record: true };
        let res = match policy {
            1 => {
                let mut pick = |d: &Decision| argmin(d, |c| (-c.waited_minutes, 0.0));
                run(&shop, &opts, Some(&mut pick))
            }
            2 => {
                let mut pick = |d: &Decision| argmin(d, |c| (c.proc_minutes, -c.waited_minutes));
                run(&shop, &opts, Some(&mut pick))
            }
            _ => run(&shop, &opts, None),
        };
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
        st.json = summary(&shop, &res);
        st.res = Some(res);
        0
    })
}

fn argmin(d: &Decision, key: impl Fn(&fabsim::engine::Candidate) -> (f64, f64)) -> usize {
    let mut best = d.default;
    let mut bk = key(&d.candidates[best]);
    for (i, c) in d.candidates.iter().enumerate() {
        let k = key(c);
        if k < bk {
            best = i;
            bk = k;
        }
    }
    best
}

fn summary(shop: &Shop, res: &RunResult) -> String {
    let mut o = String::from("{");
    let _ = write!(o, "\"until\":{},\"finished\":{},\"moves\":{},\"decisions\":{},", num(res.until), res.finished, res.moves, res.decisions);
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
