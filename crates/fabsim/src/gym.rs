//! One episode, one dispatch decision at a time (docs/RL-DEFECTS.md). `fabsim env` asks a process over JSON lines;
//! `fabrule env` asks a written rule. Both go through `episode`, so every contestant is scored by this code.

use crate::engine::{run, Decision, RunOptions};
use crate::shop::Shop;
use crate::window::{score, with_probes, Window, WindowScore};

/// candidates shown per decision
pub const K: usize = 8;

pub struct Episode {
    pub score: WindowScore,
    /// decisions asked (in the window, with two or more candidates)
    pub asked: u64,
    /// answers that were not a candidate, taken as the engine's pick
    pub fallbacks: u64,
    /// the window's reward less the rewards already paid at each question
    pub last_reward: f64,
    /// the pick played at each decision asked, in order (docs/LONG-RESCORE.md): replayed, they give the same run
    pub picks: Vec<u32>,
}

/// Write an episode's picks, one a line, for the foresight audit (`fabsim regret audit`).
pub fn write_picks(e: &Episode, path: &std::path::Path) -> std::io::Result<()> {
    let mut s = String::with_capacity(e.picks.len() * 3);
    for p in &e.picks {
        s.push_str(&p.to_string());
        s.push('\n');
    }
    std::fs::write(path, s)
}

/// The order a decision's candidates are shown in: the engine's pick first, then the rest as listed, at most K.
pub fn order(d: &Decision) -> Vec<usize> {
    let mut o = vec![d.default];
    o.extend((0..d.candidates.len()).filter(|&i| i != d.default));
    o.truncate(K);
    o
}

/// Family names numbered from 1 in the order the shop's `family` records first name them; "" is 0.
pub fn families(shop: &Shop) -> Vec<String> {
    let mut f: Vec<String> = vec![];
    for (_, x) in &shop.families {
        if !x.is_empty() && !f.contains(x) {
            f.push(x.clone());
        }
    }
    f
}

/// Run one episode. Today's rule decides the warm-up and every decision with one candidate; for the rest,
/// `ask(decision, shown order, reward since the last question)` returns a candidate's index in the decision, or
/// None for the engine's pick (counted as a fallback, as is an index out of range).
pub fn episode(shop: &Shop, seed: u64, w: Window, ask: &mut dyn FnMut(&Decision, &[usize], f64) -> Option<usize>) -> Episode {
    let shop = with_probes(shop, &w);
    let (mut asked, mut fallbacks) = (0u64, 0u64);
    let mut picks: Vec<u32> = vec![];
    let mut prev: Option<f64> = None;
    let mut paid = 0.0f64;
    let r = {
        let mut chooser = |d: &Decision| -> usize {
            if d.t < w.from || d.t > w.to || d.candidates.len() < 2 {
                return d.default;
            }
            asked += 1;
            let value = d.totals.finished as f64 - 0.01 * d.totals.wait_lot_minutes / 60.0;
            let reward = prev.map(|p| value - p).unwrap_or(0.0);
            prev = Some(value);
            paid += reward;
            let ord = order(d);
            let i = match ask(d, &ord, reward) {
                Some(i) if i < d.candidates.len() => i,
                _ => {
                    fallbacks += 1;
                    d.default
                }
            };
            picks.push(i as u32);
            i
        };
        run(&shop, &RunOptions { seed, until: Some(w.to), record: false }, Some(&mut chooser))
    };
    let sc = score(&r, &w).expect("the window scores");
    Episode { last_reward: sc.reward - paid, score: sc, asked, fallbacks, picks }
}

fn num(x: f64) -> String {
    if x.is_finite() {
        format!("{x}")
    } else {
        "null".into()
    }
}

/// One observation line (docs/RL-DEFECTS.md).
pub fn observation_json(d: &Decision, ord: &[usize], reward: f64, fams: &[String]) -> String {
    let fam_no = |f: &str| if f.is_empty() { 0 } else { fams.iter().position(|x| x == f).map(|i| i + 1).unwrap_or(0) };
    let cands: Vec<String> = ord
        .iter()
        .map(|&i| {
            let c = &d.candidates[i];
            format!(
                "{{\"is_batch\":{},\"lots\":{},\"priority\":{},\"size_wafers\":{},\"step\":{},\"steps_left\":{},\"waited_minutes\":{},\"setup_change\":{},\"proc_minutes\":{},\"work_left_minutes\":{},\"age_minutes\":{},\"cqt_slack_minutes\":{},\"is_default\":{},\"family\":{}}}",
                u8::from(c.kind == "batch"),
                c.lots.len(),
                num(c.priority),
                c.size_wafers,
                c.step,
                c.steps_left,
                num(c.waited_minutes),
                u8::from(c.setup_change),
                num(c.proc_minutes),
                num(c.work_left_minutes),
                num(d.t - c.release),
                num(c.cqt_slack_minutes.unwrap_or(1e9)),
                u8::from(i == d.default),
                fam_no(&c.family)
            )
        })
        .collect();
    let g = &d.group_tools;
    format!(
        "{{\"t\":{},\"group\":\"{}\",\"tools\":{{\"working\":{},\"idle\":{},\"down\":{}}},\"held_tools\":{},\"totals\":{{\"finished\":{},\"waiting\":{},\"wait_lot_minutes\":{}}},\"cands\":[{}],\"default\":0,\"reward\":{}}}",
        num(d.t),
        d.tool_group,
        g.working,
        g.idle,
        g.down,
        g.held,
        d.totals.finished,
        d.totals.waiting,
        num(d.totals.wait_lot_minutes),
        cands.join(","),
        num(reward)
    )
}

/// The last line of an episode; `extra` is appended inside the object (for example `,"faults":0`).
pub fn done_json(e: &Episode, extra: &str) -> String {
    let s = &e.score;
    format!(
        "{{\"done\":true,\"reward\":{},\"decisions\":{},\"fallbacks\":{}{},\"score\":{{\"reward\":{},\"moves\":{},\"lots_finished\":{},\"wait_lot_hours\":{},\"wait_per_move_minutes\":{},\"breaches\":{},\"mean_wip\":{},\"lots_per_day\":{},\"wafers_per_day\":{},\"cycle_days\":{},\"hot_cycle_days\":{}}}}}",
        num(e.last_reward),
        e.asked,
        e.fallbacks,
        extra,
        num(s.reward),
        num(s.moves),
        num(s.lots_finished),
        num(s.wait_lot_hours),
        num(s.wait_per_move_minutes),
        num(s.breaches),
        num(s.mean_wip),
        num(s.lots_per_day),
        num(s.wafers_per_day),
        num(s.cycle_days),
        num(s.hot_cycle_days.unwrap_or(f64::NAN))
    )
}

/// Read a shop file or the SMT2020 folder, adding defect holds from `--defects H,L,R` when it has none.
pub fn load_shop(src: &std::path::Path, defects: Option<&str>) -> Result<Shop, String> {
    let mut shop = if src.is_dir() {
        crate::smt2020::load(src)?
    } else {
        Shop::parse(&std::fs::read_to_string(src).map_err(|e| format!("{}: {e}", src.display()))?)?
    };
    if let Some(d) = defects {
        let v: Vec<f64> = d.split(',').map(|x| x.trim().parse::<f64>()).collect::<Result<_, _>>().map_err(|_| "--defects H,L,R in minutes")?;
        if v.len() != 3 || v.iter().any(|x| *x < 0.0) {
            return Err("--defects H,L,R in minutes".into());
        }
        if shop.defects.is_none() {
            shop.defects = Some(crate::shop::Defects { hold_tool_minutes: v[0], lookback_minutes: v[1], hold_lot_minutes: v[2] });
        }
    }
    Ok(shop)
}
