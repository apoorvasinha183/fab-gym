//! Probe (not a test): held-up minutes and detours with a broken busiest stretch, going round against waiting.
use fabsim::engine::{run, run_with, RunOptions};
use fabsim::layout::{Config, Problem};
use fabsim::overrides::Overrides;
use fabsim::shop::Fleet;
use fabsim::track::Track;
fn main() {
    let dir = std::path::PathBuf::from("data/smt2020/hvlm");
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let mut cfg = Config::realistic(); cfg.iters = 3000; cfg.restarts = 1;
    let p = Problem::new(&base, &areas, &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let mut s = base; s.oht = Some(p.oht(&c)); s.ports = p.ports(&c); s.bayrails = p.bayrails(&c);
    s.fleet = Some(Fleet { vehicles: 160, gap: 3.0, hoist: 1.0, ports: 2, cross: 60.0, controller: "nearest".into() });
    let o = RunOptions { seed: 0, until: Some(720.0), record: true };
    let b = run(&s, &o, None); let fl = b.fleet.as_ref().unwrap();
    let t = Track::from_shop(&s);
    let mut n = vec![0usize; t.edges().len()]; for e in &fl.entries { n[e.edge] += 1; }
    let e = (0..n.len()).filter(|&i| t.out_of(t.edges()[i].from).len() >= 2).max_by_key(|&i| n[i]).unwrap();
    let id = format!("n{}>n{}", t.edges()[e].from, t.edges()[e].to);
    println!("base: held {:.0} detours {} delivered {}  busiest {id} ({} entries, out-degree of its start {})", fl.held_min, fl.detours, fl.delivered, n[e], t.out_of(t.edges()[e].from).len());
    for rec in ["route_around", "wait"] {
        let ov = Overrides::parse(&format!(r#"{{"fabgym-overrides":1,"rails":{{"{id}":{{"breakdowns":{{"kind":"random","mttf_minutes":90,"mttr_minutes":30}},"recovery":{{"kind":"{rec}"}}}}}}}}"#), &s).unwrap();
        let r = run_with(&s, &o, None, &ov); let f = r.fleet.as_ref().unwrap();
        let down: f64 = r.due.iter().filter(|d| d.what == "rail").map(|d| d.minutes).sum();
        println!("{rec}: held {:.0} detours {} delivered {} asked {} open {}  rail downs {} ({down:.0} min)", f.held_min, f.detours, f.delivered, f.asked, f.open, r.due.iter().filter(|d| d.what == "rail").count());
    }
}
