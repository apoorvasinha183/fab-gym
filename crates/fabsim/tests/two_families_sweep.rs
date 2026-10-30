//! The two-family sweep's pieces (docs/TWO-FAMILIES-SWEEP.md). Written before the code.
//! From the SMT2020 testbed, with a layout of our own design; not a real fab.

use fabsim::engine::{Candidate, Decision, GroupTools, RunOptions, Totals};
use fabsim::money::{money, PriceGrid};
use fabsim::shop::Shop;
use fabsim::twofam::{apply_policy, b_cap, b_first, copy_groups, policy_groups, run_cells, Cell, EngLots, Policy};
use fabsim::window::Window;

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t4\t0.0\t0.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
group\tK\t3\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tK\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
route\trb
step\tG\tlot\t25.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tK\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t20.0\t0.0\t-\tA
release\trb\t5\t10.0\t40.0\t0.0\t-\tB
family\tra\tA
family\trb\tB
";

fn toy() -> Shop {
    Shop::parse(TOY).unwrap()
}

#[test]
fn policy_groups_leave_out_the_copies() {
    let shop = copy_groups(&toy(), &[("H".to_string(), 1)], "B").unwrap();
    let g = policy_groups(&shop, "B", 3);
    assert_eq!(g.len(), 2, "{g:?}");
    assert!(g.iter().all(|x| !x.ends_with("@B")));
    assert!(!g.contains(&"H".to_string()), "family B no longer visits H");
}

#[test]
fn policies_change_only_what_they_name() {
    let shop = toy();
    let groups = vec!["G".to_string(), "K".to_string()];
    assert_eq!(apply_policy(&shop, Policy::Today, "B", &groups, 50), shop);
    assert_eq!(apply_policy(&shop, Policy::BFirst, "B", &groups, 50), shop);
    let cap = apply_policy(&shop, Policy::Cap, "B", &groups, 50);
    assert_eq!(cap.famcaps, vec![("B".to_string(), 50)]);
    assert_eq!((cap.quals.len(), cap.reserves.len()), (0, 0));
    let res = apply_policy(&shop, Policy::Reserve, "B", &groups, 50);
    assert_eq!(res.quals, vec![("G".into(), "B".into(), 4), ("K".into(), "B".into(), 3)]);
    assert_eq!(res.reserves, vec![("G".into(), "B".into(), 1), ("K".into(), "B".into(), 1)]);
    let q = apply_policy(&shop, Policy::Qualify, "B", &groups, 50);
    assert_eq!(q.quals, vec![("G".into(), "B".into(), 2), ("K".into(), "B".into(), 2)]);
    assert!(q.reserves.is_empty() && q.famcaps.is_empty());
    assert_eq!(Policy::ALL.len(), 5);
    let labels: Vec<&str> = Policy::ALL.iter().map(|p| p.label()).collect();
    assert_eq!(labels, ["P0 today", "P1 family B first", "P2 family cap", "P3 reservation", "P4 qualification"]);
}

fn cand(family: &str, step: usize) -> Candidate {
    Candidate {
        kind: "lot".into(),
        lots: vec![format!("x{step}")],
        priority: 10.0,
        size_wafers: 5,
        route: "r".into(),
        step,
        steps_left: 1,
        waited_minutes: 0.0,
        setup_change: false,
        proc_minutes: 1.0,
        work_left_minutes: 1.0,
        release: 0.0,
        cqt_slack_minutes: None,
        family: family.into(),
    }
}

fn decision(fams: &[&str], default: usize) -> Decision {
    Decision {
        t: 1.0,
        tool_group: "G".into(),
        tool: "G#1".into(),
        tool_setup: None,
        group_tools: GroupTools::default(),
        totals: Totals::default(),
        candidates: fams.iter().enumerate().map(|(i, f)| cand(f, i)).collect(),
        default,
    }
}

#[test]
fn family_b_first_keeps_todays_order_within_a_family() {
    assert_eq!(b_first(&decision(&["A", "B", "B"], 0), "B"), 1);
    assert_eq!(b_first(&decision(&["A", "B", "B"], 2), "B"), 2);
    assert_eq!(b_first(&decision(&["A", "A"], 1), "B"), 1);
}

#[test]
fn the_cap_is_the_stated_formula() {
    let e = EngLots::published("part_E3", 300.0 * 1440.0, 1);
    assert!((e.lots_per_day() - 20.0 / 3.5).abs() < 1e-12);
    assert_eq!(b_cap(&e, 24.68), (1.5_f64 * 20.0 / 3.5 * 24.68).ceil() as i64);
    let twice = EngLots { scale: 2.0, ..e.clone() };
    assert!((twice.lots_per_day() - 40.0 / 3.5).abs() < 1e-12);
}

#[test]
fn the_price_grid_starts_at_the_central_point() {
    let g = PriceGrid::preregistered("B");
    assert_eq!(g.len(), 36);
    let c = &g[0];
    assert_eq!((c.price0, c.free_days, c.tool_day, c.metre_day), (20.0, 30.0, 20.0, 2.0));
    assert!((c.decay - 1.0 / 30.0).abs() < 1e-15);
    assert_eq!(c.margin, vec![("A".to_string(), 1.0)]);
    for i in 0..g.len() {
        for j in 0..i {
            assert_ne!(g[i], g[j]);
        }
    }
}

#[test]
fn cells_run_the_same_on_any_number_of_threads() {
    let shop = toy();
    let groups = policy_groups(&shop, "B", 2);
    let cells: Vec<Cell> = [Policy::Today, Policy::BFirst, Policy::Reserve]
        .iter()
        .map(|&p| Cell {
            label: p.label().to_string(),
            shop: apply_policy(&shop, p, "B", &groups, 40),
            policy: p,
            tools_added: 1,
            metres_added: 3.0,
        })
        .collect();
    let w = Window { from: 1440.0, to: 6.0 * 1440.0 };
    let grid = PriceGrid::preregistered("B");
    let one = run_cells(&cells, &[5, 6], w.to, &w, &grid, "B", 1).unwrap();
    let three = run_cells(&cells, &[5, 6], w.to, &w, &grid, "B", 3).unwrap();
    assert_eq!(one, three);
    assert_eq!(one.len(), 6);
    // the central money equals the money of the run itself
    let r = &one.iter().find(|x| x.cell == 2 && x.seed == 6).unwrap();
    let run = fabsim::engine::run(&cells[2].shop, &RunOptions { seed: 6, until: Some(w.to), record: false }, None);
    assert_eq!(r.money[0], money(&cells[2].shop, &run, &w, &grid[0], 1, 3.0));
    assert_eq!(r.money.len(), 36);
    assert!(r.a_wafers_per_day > 0.0 && r.money[0].b_lots > 0);
    // P1 really chooses: its runs differ from today's
    let today: Vec<_> = one.iter().filter(|x| x.cell == 0).map(|x| x.money[0].b_cycle_days).collect();
    let bfirst: Vec<_> = one.iter().filter(|x| x.cell == 1).map(|x| x.money[0].b_cycle_days).collect();
    assert_ne!(today, bfirst);
}
