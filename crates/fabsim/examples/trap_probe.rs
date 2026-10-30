//! Probe (not a test): what the two trap nodes on today's campus are.
use fabsim::layout::{Config, Problem};
use fabsim::track::Track;
fn main() {
    let dir = std::path::PathBuf::from("data/smt2020/hvlm");
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let mut cfg = Config::realistic(); cfg.iters = 3000; cfg.restarts = 1;
    let p = Problem::new(&base, &areas, &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let mut s = base; s.oht = Some(p.oht(&c)); s.ports = p.ports(&c); s.bayrails = p.bayrails(&c);
    let t = Track::from_shop(&s);
    for n in [35usize, 110] {
        let a = &t.nodes()[n];
        let ins: Vec<usize> = t.edges().iter().filter(|e| e.to == n).map(|e| e.from).collect();
        let outs: Vec<usize> = t.out_of(n).iter().map(|&e| t.edges()[e].to).collect();
        println!("n{n}: phase {} side {} x {:.2} y {:.2} bay {} stocker {} tool {:?} group {:?}  in {:?} out {:?}", a.phase, a.side, a.x, a.y, a.bay as i64, a.stocker, a.tool, a.group, ins, outs);
    }
    println!("start node n{}; start place {:?}", t.node_of(&s.oht.as_ref().unwrap().start), s.oht.as_ref().unwrap().start);
    let ends: Vec<usize> = (0..t.nodes().len()).filter(|&n| t.out_of(n).is_empty()).collect();
    println!("nodes with no way out: {ends:?}");
}
