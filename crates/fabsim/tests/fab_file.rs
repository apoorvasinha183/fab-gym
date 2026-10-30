//! One file for any fab (docs/FAB-FILE.md): today's shop text plus optional plan records. Written before the code.
//! On the SMT2020 model; any layout here is of our own design, not a real fab.

mod common;

use fabsim::engine::{run, RunOptions};
use fabsim::hash::sha256_hex;
use fabsim::shop::{Link, Node, Plan, Price, Shop, Station, Stop};
use fabsim::track::Track;

const TINY: &str = "fabgym-shop 1
transport\t0.0\t0.0
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t2\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t20.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
lot\tL1\tr\t25\t10.0\t0.0\t0
lot\tL2\tr\t25\t10.0\t0.0\t0
";

const TINY_PLAN: &str = "price\tA\t2000000.0\t150.0
price\tB\t500000.0\t40.0
node\tn0\t0.0\t0.0
node\tn1\t10.0\t0.0
node\tn2\t10.0\t5.0
node\tn3\t0.0\t5.0
link\tn0\tn1\t10.0
link\tn1\tn2\t5.0
link\tn2\tn3\t10.0
link\tn3\tn0\t5.0
link\tn1\tn3\t11.5
station\tA\t2.0\t-3.0\t4.0\t2.0
station\tB\t12.0\t1.0\t2.0\t3.0
stop\tA\t0\tn1
stop\tB\t0\tn2
stop\tB\t1\tn2
stocker\tn3
entry\tn0
exit\tn3
";

fn tiny_fab() -> String {
    format!("{TINY}{TINY_PLAN}")
}

#[test]
fn a_shop_with_no_plan_has_none_and_writes_as_before() {
    for name in ["tiny", "mixed", "capped"] {
        let text = common::read(&format!("golden/toy/{name}.shop.txt"));
        let shop = Shop::parse(&text).unwrap();
        assert!(shop.plan.is_none(), "{name} has no plan records");
        common::assert_same_text(&shop.to_text(), &text, name);
    }
}

#[test]
fn a_hand_written_fab_reads_and_writes_back_unchanged() {
    let text = tiny_fab();
    let shop = Shop::parse(&text).expect("the tiny fab parses");
    common::assert_same_text(&shop.to_text(), &text, "tiny fab");
    let p = shop.plan.as_ref().expect("a plan");
    assert_eq!(p.prices[0], Price { group: "A".into(), buy: 2_000_000.0, day: 150.0 });
    assert_eq!(p.nodes.len(), 4);
    assert_eq!(p.nodes[2], Node { id: "n2".into(), x: 10.0, y: 5.0 });
    assert_eq!(p.links.len(), 5);
    assert_eq!(p.links[4], Link { from: "n1".into(), to: "n3".into(), len: 11.5 });
    assert_eq!(p.stations[1], Station { group: "B".into(), x: 12.0, y: 1.0, w: 2.0, h: 3.0 });
    assert_eq!(p.stops[2], Stop { group: "B".into(), tool: 1, node: "n2".into() });
    assert_eq!(p.stockers, vec!["n3".to_string()]);
    assert_eq!(p.entry, vec!["n0".to_string()]);
    assert_eq!(p.exit, vec!["n3".to_string()]);
}

#[test]
fn records_may_come_in_any_order_and_are_written_in_the_set_order() {
    let mut lines: Vec<&str> = TINY_PLAN.lines().collect();
    lines.reverse();
    let shuffled = format!("{TINY}{}\n", lines.join("\n"));
    let shop = Shop::parse(&shuffled).expect("plan records in any order");
    let again = Shop::parse(&tiny_fab()).unwrap();
    assert_eq!(shop.plan.as_ref().unwrap().nodes.len(), 4);
    // within a kind the order read is kept, so only kinds are regrouped
    assert_eq!(shop.to_text().lines().filter(|l| l.starts_with("node")).count(), 4);
    assert_eq!(again.to_text(), tiny_fab());
}

#[test]
fn a_plan_does_not_change_a_toy_run() {
    let opts = RunOptions { seed: 7, until: None, record: true };
    let plain = run(&Shop::parse(TINY).unwrap(), &opts, None).log_text();
    let with_plan = run(&Shop::parse(&tiny_fab()).unwrap(), &opts, None).log_text();
    assert!(!plain.is_empty());
    common::assert_same_text(&with_plan, &plain, "tiny with and without a plan");
}

#[test]
fn smt2020_with_a_plan_keeps_its_golden_shop_and_log() {
    let Some(dir) = common::smt2020_dir() else { return };
    let mut shop = fabsim::smt2020::load_reference(&dir).unwrap();
    let g = shop.groups[0].name.clone();
    shop.plan = Some(Plan {
        prices: vec![Price { group: g.clone(), buy: 1_000_000.0, day: 100.0 }],
        nodes: vec![Node { id: "a".into(), x: 0.0, y: 0.0 }, Node { id: "b".into(), x: 30.0, y: 0.0 }],
        links: vec![Link { from: "a".into(), to: "b".into(), len: 30.0 }, Link { from: "b".into(), to: "a".into(), len: 30.0 }],
        stations: vec![Station { group: g.clone(), x: 1.0, y: 1.0, w: 3.0, h: 2.0 }],
        stops: vec![Stop { group: g, tool: 0, node: "b".into() }],
        stockers: vec![],
        entry: vec!["a".into()],
        exit: vec!["a".into()],
        stores: vec![],
    });
    let back = Shop::parse(&shop.to_text()).expect("SMT2020 with a plan reads back");
    assert_eq!(back, shop);
    let mut bare = back.clone();
    bare.plan = None;
    let text = bare.to_text();
    let (hash, lines) = common::recorded_hash("shop");
    assert_eq!(text.lines().count(), lines);
    assert_eq!(sha256_hex(text.as_bytes()), hash, "the shop part is the reference compile");
    let log = run(&back, &RunOptions { seed: 0, until: Some(1440.0), record: true }, None).log_text();
    let (hash, lines) = common::recorded_hash("smt2020.seed0.1d.log.txt");
    assert_eq!(log.lines().count(), lines);
    assert_eq!(sha256_hex(log.as_bytes()), hash, "a plan does not change the golden run");
}

fn refused(extra: &str, says: &str) {
    let text = format!("{}{extra}\n", tiny_fab());
    let line = text.lines().count();
    let err = Shop::parse(&text).expect_err(&format!("refused: {extra:?}"));
    assert!(err.contains(&format!("line {line}")), "{err:?} names line {line}");
    assert!(err.contains(says), "{err:?} says {says:?}");
}

#[test]
fn a_link_to_an_unknown_node_is_refused() {
    refused("link\tn0\tn9\t3.0", "n9");
}

#[test]
fn a_stop_for_an_unknown_group_is_refused() {
    refused("stop\tC\t0\tn0", "C");
}

#[test]
fn a_stop_past_the_groups_tools_is_refused() {
    refused("stop\tA\t1\tn0", "tool 1");
}

#[test]
fn a_node_defined_twice_is_refused() {
    refused("node\tn0\t1.0\t1.0", "n0");
}

#[test]
fn a_negative_price_is_refused() {
    refused("price\tA\t-5.0\t1.0", "price");
}

#[test]
fn a_negative_length_is_refused() {
    refused("link\tn0\tn2\t-1.0", "length");
}

#[test]
fn an_exit_at_an_unknown_node_is_refused() {
    refused("exit\tn7", "n7");
}

/// The realistic campus with its ports and each bay's two rails, laid out here (a quick optimiser).
fn campus_drawn() -> Option<Shop> {
    use fabsim::layout::{Config, Problem};
    let dir = common::smt2020_dir()?;
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let mut cfg = Config::realistic();
    cfg.iters = 3000;
    cfg.restarts = 1;
    let p = Problem::new(&base, &areas, &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let mut s = base;
    s.oht = Some(p.oht(&c));
    s.ports = p.ports(&c);
    s.bayrails = p.bayrails(&c);
    Some(s)
}

#[test]
fn the_campus_exports_to_a_plan_that_holds_its_rails() {
    let Some(s) = campus_drawn() else { return };
    let t = Track::from_shop(&s);
    let p = fabsim::fab::plan_from_track(&s).expect("the campus exports");
    assert_eq!(p.nodes.len(), t.nodes().len(), "one node per track node");
    assert_eq!(p.links.len(), t.edges().len(), "one link per stretch");
    let want: f64 = t.edges().iter().map(|e| e.len).sum();
    let got: f64 = p.links.iter().map(|l| l.len).sum();
    assert!((want - got).abs() < 1e-6, "same total metres: {want} vs {got}");
    assert_eq!(p.stops.len(), s.ports.len(), "a stop for every tool's port");
    let stockers = t.nodes().iter().filter(|n| n.stocker).count();
    assert!(stockers > 0);
    assert_eq!(p.stockers.len(), stockers, "a node for every stocker port");
    assert_eq!(p.entry.len(), 1);
    assert_eq!(p.exit.len(), 1);
    let ids: std::collections::HashSet<&str> = p.nodes.iter().map(|n| n.id.as_str()).collect();
    for l in &p.links {
        assert!(ids.contains(l.from.as_str()) && ids.contains(l.to.as_str()));
    }
    for st in &p.stops {
        assert!(ids.contains(st.node.as_str()));
    }
    let mut fab = s.clone();
    fab.plan = Some(p);
    let back = Shop::parse(&fab.to_text()).expect("the exported fab reads back");
    assert_eq!(back, fab);
}

#[test]
fn the_export_command_writes_a_file_that_reads_back() {
    let Some(s) = campus_drawn() else { return };
    let d = std::env::temp_dir().join(format!("fabgym-fab-{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("campus.shop.txt");
    std::fs::write(&f, s.to_text()).unwrap();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_fabsim")).arg("fab-export").arg(&f).output().unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let fab = Shop::parse(&String::from_utf8(out.stdout).unwrap()).expect("the export reads back");
    assert_eq!(fab.plan.as_ref().unwrap().nodes.len(), Track::from_shop(&s).nodes().len());
    let _ = std::fs::remove_dir_all(&d);
}
