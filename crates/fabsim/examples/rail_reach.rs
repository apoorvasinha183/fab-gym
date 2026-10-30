//! Probe (not a test): from the start of a stretch, how many nodes stay reachable with the stretch broken.
use fabsim::layout::{Config, Problem};
use fabsim::track::Track;
fn reach(t: &Track, from: usize, skip: usize) -> usize {
    let mut seen = vec![false; t.nodes().len()]; let mut st = vec![from]; seen[from] = true; let mut n = 0;
    while let Some(u) = st.pop() { n += 1; for &e in t.out_of(u) { if e == skip { continue; } let v = t.edges()[e].to; if !seen[v] { seen[v] = true; st.push(v); } } }
    n
}
fn main() {
    let dir = std::path::PathBuf::from("data/smt2020/hvlm");
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let mut cfg = Config::realistic(); cfg.iters = 3000; cfg.restarts = 1;
    let p = Problem::new(&base, &areas, &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let mut s = base; s.oht = Some(p.oht(&c)); s.ports = p.ports(&c); s.bayrails = p.bayrails(&c);
    let t = Track::from_shop(&s);
    let all = t.nodes().len();
    let e = t.edges().iter().position(|x| x.from == 17 && x.to == 18).unwrap();
    println!("n17>n18: from n17, {} of {all} nodes reachable intact, {} with it broken; other way out goes to n{}",
        reach(&t, 17, usize::MAX), reach(&t, 17, e), t.out_of(17).iter().map(|&x| t.edges()[x].to).find(|&v| v != 18).unwrap());
    let mut cut = 0; let mut bypass = 0;
    for (i, x) in t.edges().iter().enumerate() { if t.out_of(x.from).len() >= 2 { if reach(&t, x.from, i) == all { bypass += 1 } else { cut += 1 } } }
    println!("stretches leaving a split: {bypass} can be gone round with every node still reachable, {cut} cut something off");
}
