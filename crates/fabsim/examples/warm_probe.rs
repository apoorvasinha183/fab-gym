//! Why our cycle times differ from the published run (docs/DOUBLE-CHECK.md, part 4): run the files as they are until
//! about 3,635 lots are inside (or 240 days), then measure the next 6 months under today's rule, 10 runs.
//!   cargo run --release -p fabsim --example warm_probe
use fabsim::engine::{run, RunOptions};
fn main() {
    let shop = fabsim::smt2020::load(std::path::Path::new("data/smt2020/hvlm")).unwrap();
    let total = 420.0;
    let rows: Vec<_> = std::thread::scope(|sc| {
        let hs: Vec<_> = (0..4u64).map(|w| { let shop = &shop; sc.spawn(move || {
            (0..10u64).filter(|s| s % 4 == w).map(|seed| {
                let r = run(shop, &RunOptions { seed, until: Some(total * 1440.0), record: false }, None);
                // lots inside at day d: entered by d, not done by d
                let inside = |d: f64| r.lots.iter().filter(|l| l.release <= d * 1440.0 && l.done.is_none_or(|x| x > d * 1440.0)).count();
                let mut start = 0.0;
                while start < 240.0 && inside(start) < 3635 { start += 1.0; }
                let ct = |p: &str| { let v: Vec<f64> = r.lots.iter().filter(|l| !l.wip && l.id.starts_with(p) && l.release >= start * 1440.0 && l.done.is_some_and(|x| x <= (start + 180.0) * 1440.0)).map(|l| (l.done.unwrap() - l.release) / 1440.0).collect(); v.iter().sum::<f64>() / v.len() as f64 };
                (start, inside(0.0), inside(start), ct("Lot_3."), ct("Lot_4."), ct("HotLot_3."), ct("HotLot_4."), ct("SuperHotLot_3."))
            }).collect::<Vec<_>>() }) }).collect();
        hs.into_iter().flat_map(|h| h.join().unwrap()).collect()
    });
    for r in &rows { println!("warm-up {:3.0} days ({} -> {} lots inside): regular 3 {:6.2}  regular 4 {:6.2}  hot 3 {:6.2}  hot 4 {:6.2}  super-hot 3 {:6.2}", r.0, r.1, r.2, r.3, r.4, r.5, r.6, r.7); }
    let n = rows.len() as f64;
    println!("mean: regular 3 {:.2}, regular 4 {:.2}, hot 3 {:.2}, hot 4 {:.2}, super-hot 3 {:.2}", rows.iter().map(|r| r.3).sum::<f64>() / n, rows.iter().map(|r| r.4).sum::<f64>() / n, rows.iter().map(|r| r.5).sum::<f64>() / n, rows.iter().map(|r| r.6).sum::<f64>() / n, rows.iter().map(|r| r.7).sum::<f64>() / n);
}
