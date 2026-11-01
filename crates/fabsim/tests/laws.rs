//! Laws every run obeys (docs/DOUBLE-CHECK.md, part 3). Written before the code. Little's law as an identity of a
//! run's record: the lot-minutes the run counts over a window (which the scorer's cycle time rests on) equal each lot's
//! time inside the window, added up. The utilisation law: a machine group's busy share is the work sent to it over its
//! machines, with the work worked out exactly from part 1's chains. From the SMT2020 testbed; not a real fab.

mod common;

use fabsim::engine::{run, RunOptions};
use fabsim::routes::loads;
use fabsim::uq::t_quantile;
use fabsim::window::{with_probes, Window};

const DAY: f64 = 1440.0;

#[test]
fn dc7_littles_law_holds_on_the_runs_record() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let w = Window { from: 5.0 * DAY, to: 15.0 * DAY };
    let probed = with_probes(&shop, &w);
    for seed in 0..3u64 {
        let res = run(&probed, &RunOptions { seed, until: Some(w.to), record: true }, None);
        let at = |t: f64| res.probes.iter().find(|p| (p.t - t).abs() < 1e-9).unwrap_or_else(|| panic!("a probe at {t}"));
        let (a, b) = (at(w.from), at(w.to));
        // each lot's minutes inside the window, from its own entry and finish
        let inside: f64 = res.lots.iter().map(|l| (l.done.unwrap_or(f64::INFINITY).min(w.to) - l.release.max(w.from)).max(0.0)).sum();
        let area = b.wip_lot_minutes - a.wip_lot_minutes;
        assert!((area - inside).abs() <= 1e-9 * area, "run {seed}: the run counts {area} lot-minutes, the lots add up to {inside}");
        let finished = res.lots.iter().filter(|l| l.done.is_some_and(|d| d > w.from && d <= w.to)).count() as i64;
        assert_eq!(b.finished - a.finished, finished, "run {seed}: lots finished in the window");
        let wip = res.lots.iter().filter(|l| l.release <= w.to && l.done.is_none_or(|d| d > w.to)).count() as i64;
        assert_eq!(b.wip, wip, "run {seed}: lots inside at the window's end");
    }
}

#[test]
fn dc8_busy_shares_follow_the_work_sent() {
    let Some(dir) = common::smt2020_dir() else { return };
    let mut shop = fabsim::smt2020::load(&dir).unwrap();
    // the law holds for a fab that keeps up, in steady state. At the testbed's own release rate the polishers cannot
    // keep up (the releases ask 1,430 wafers a day; the busiest polishing group passes at most 1,302), and the lots in
    // progress at the start are those of that rate. So: an empty start, four fifths of the release rate, and days 60
    // to 90, more than a lot's cycle time after the start
    shop.lots.clear();
    for r in &mut shop.releases {
        r.every *= 1.25;
    }
    let mut ld = loads(&shop);
    // groups with no batch step, where a lot's work is exact; the five busiest
    ld.retain(|g| g.exact);
    ld.sort_by(|a, b| b.share.total_cmp(&a.share));
    ld.truncate(5);
    assert_eq!(ld.len(), 5);
    let (from, to) = (60.0 * DAY, 90.0 * DAY);
    let mut shares: Vec<Vec<f64>> = vec![vec![]; ld.len()];
    for seed in 0..10u64 {
        let res = run(&shop, &RunOptions { seed, until: Some(to), record: true }, None);
        for (i, g) in ld.iter().enumerate() {
            let prefix = format!("{}#", g.name);
            let busy: f64 = res
                .trace
                .iter()
                .filter(|x| res.tools[x.tool as usize].name.starts_with(&prefix))
                .map(|x| (x.end.min(to) - x.start.max(from)).max(0.0))
                .sum();
            shares[i].push(busy / (g.tools as f64 * (to - from)));
        }
    }
    for (i, g) in ld.iter().enumerate() {
        let d = &shares[i];
        let n = d.len() as f64;
        let mean = d.iter().sum::<f64>() / n;
        let sd = (d.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n - 1.0)).sqrt();
        let h = t_quantile(0.975, n - 1.0) * sd / n.sqrt();
        assert!(
            (mean - g.share).abs() <= h,
            "{}: busy {mean:.4} of the time (95%: {:.4} to {:.4}); the work sent to it is {:.4} of its {} machines' time",
            g.name,
            mean - h,
            mean + h,
            g.share,
            g.tools
        );
    }
}
