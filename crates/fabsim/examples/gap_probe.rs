//! Why our cycle times differ from the published run (docs/DOUBLE-CHECK.md, part 4, "Why the cycle times differ"):
//! 6 months under a rule, starting with ARG1 lots in progress (copies of the files' own lots, placed where those are).
//!   cargo run --release -p fabsim --example gap_probe -- 3635 180 today|mimic|cqt
//! "mimic" is today's rule written as a chooser (a control); "cqt" puts lots under a queue-time limit first.
use fabsim::engine::{run, RunOptions};
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let target: usize = a[0].parse().unwrap(); // lots in progress at the start
    let days: f64 = a.get(1).map(|x| x.parse().unwrap()).unwrap_or(180.0);
    let rule_s = a.get(2).cloned().unwrap_or("today".into());
    let rule: &str = &rule_s;
    let mut shop = fabsim::smt2020::load(std::path::Path::new("data/smt2020/hvlm")).unwrap();
    let base: Vec<_> = shop.lots.clone();
    let mut i = 0;
    while shop.lots.len() < target {
        let mut l = base[(i * 7919) % base.len()].clone();
        l.id = format!("dup.{i}.{}", l.id);
        shop.lots.push(l);
        i += 1;
    }
    let res: Vec<_> = std::thread::scope(|sc| {
        let hs: Vec<_> = (0..4u64).map(|w| { let shop = &shop; sc.spawn(move || {
            (0..10u64).filter(|s| s % 4 == w).map(|seed| {
                let o = RunOptions { seed, until: Some(days * 1440.0), record: false };
                // queue-time lots first (when cqt), then priority, then no setup change, then the longest waiting
                let cqt = rule == "cqt";
                let mut pick = |d: &fabsim::engine::Decision| -> usize {
                    let key = |c: &fabsim::engine::Candidate| (if cqt && c.cqt_slack_minutes.is_some() { 0 } else { 1 }, -c.priority, c.setup_change as i32, -c.waited_minutes);
                    let mut best = d.default;
                    for (i, c) in d.candidates.iter().enumerate() {
                        if key(c).partial_cmp(&key(&d.candidates[best])) == Some(std::cmp::Ordering::Less) { best = i; }
                    }
                    best
                };
                let r = if rule == "today" { run(shop, &o, None) } else { run(shop, &o, Some(&mut pick)) };
                let ct = |p: &str| { let v: Vec<f64> = r.lots.iter().filter(|l| !l.wip && l.id.starts_with(p) && l.done.is_some()).map(|l| (l.done.unwrap() - l.release) / 1440.0).collect(); v.iter().sum::<f64>() / v.len() as f64 };
                let fin = r.lots.iter().filter(|l| l.done.is_some()).count();
                let end = r.lots.iter().filter(|l| l.done.is_none()).count();
                (ct("Lot_3."), ct("Lot_4."), ct("HotLot_3."), ct("HotLot_4."), fin, end)
            }).collect::<Vec<_>>() }) }).collect();
        hs.into_iter().flat_map(|h| h.join().unwrap()).collect()
    });
    let m = |f: &dyn Fn(&(f64, f64, f64, f64, usize, usize)) -> f64| res.iter().map(f).sum::<f64>() / res.len() as f64;
    print!("{rule:6} ");
    println!("start lots {:5}: regular 3 {:6.2}  regular 4 {:6.2}  hot 3 {:6.2}  hot 4 {:6.2}  finished/run {:6.0}  inside at end {:6.0}",
        shop.lots.len(), m(&|x| x.0), m(&|x| x.1), m(&|x| x.2), m(&|x| x.3), m(&|x| x.4 as f64), m(&|x| x.5 as f64));
}
