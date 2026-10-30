//! Money with full business logic: a profit and loss in dollars (docs/MONEY-PL.md). Written before the code.
//! From the SMT2020 testbed, a published set of a fab's tool groups, routes and times. Every price is assumed.

mod common;

use fabsim::engine::{run, RunOptions};
use fabsim::money::{money, PriceGrid};
use fabsim::pl::{b_revenue_day, b_revenue_from_grid, capital, change, npv_factor, run_pl, sweep_pl, Added, Place, RunIn, Sheet};
use fabsim::shop::Shop;
use fabsim::window::Window;

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t2\t0.0\t0.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
route\trb
step\tG\tlot\t25.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t30.0\t0.0\t-\tA
release\trb\t5\t10.0\t60.0\t0.0\t-\tB
family\tra\tA
family\trb\tB
";

fn close(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * (1.0 + a.abs().max(b.abs()))
}

// 1. The price sheet: every item has low <= central <= high and is marked assumed.
#[test]
fn the_price_sheet_is_ordered_and_assumed() {
    let items = Sheet::items();
    for key in [
        "a_price", "b_price", "b_decay", "materials", "tool_litho", "tool_other", "qualify", "upkeep_rate", "floor_per_tool",
        "wing_m2", "halls_m2", "bridge", "base_running", "base_depreciation", "life_tool", "life_building", "life_bridge",
        "horizon_years", "rate",
    ] {
        let it = items.iter().find(|i| i.key == key).unwrap_or_else(|| panic!("no {key}"));
        assert!(it.low <= it.central && it.central <= it.high, "{key}");
        assert!(it.assumed, "{key}");
        assert!(!it.label.is_empty(), "{key}");
    }
    let s = Sheet::central();
    assert_eq!(s.get("a_price"), 8000.0);
    assert_eq!(s.with("a_price", 4000.0).get("a_price"), 4000.0);
    assert_eq!(s.get("a_price"), 8000.0, "with() leaves the original alone");
}

// 2. A run's profit and loss adds up.
#[test]
fn a_runs_profit_and_loss_adds_up() {
    let s = Sheet::central();
    let cap = capital(&Added { tools: vec![("Dry_Etch".into(), 2)], place: Place::Halls }, &s);
    let r = RunIn { a_wafers_day: 900.0, b_wafers_day: 30.0, b_revenue_day: 1.2e6 };
    let p = run_pl(&r, &cap, &s);
    assert!(close(p.revenue, 900.0 * 8000.0 + 1.2e6, 1e-12));
    assert!(close(p.materials, 930.0 * 1800.0, 1e-12));
    assert!(close(p.profit, p.revenue - p.materials - p.running - p.depreciation, 1e-12));
    assert!(close(p.cash, p.profit + p.depreciation, 1e-12));
    assert!(close(p.running, s.get("base_running") + cap.upkeep_day, 1e-12));
    assert!(close(p.depreciation, s.get("base_depreciation") + cap.depreciation_day, 1e-12));
}

// 3. Capital by strategy.
#[test]
fn capital_by_strategy() {
    let s = Sheet::central();
    let none = capital(&Added { tools: vec![], place: Place::None }, &s);
    assert_eq!((none.total, none.depreciation_day, none.upkeep_day), (0.0, 0.0, 0.0));
    let tools = vec![("Litho".to_string(), 1), ("Dry_Etch".to_string(), 1), ("Wet_Etch".to_string(), 1)];
    let wing = capital(&Added { tools: tools.clone(), place: Place::Wing }, &s);
    let area = 3.0 * s.get("floor_per_tool");
    assert!(close(wing.tools, s.get("tool_litho") + 2.0 * s.get("tool_other"), 1e-12));
    assert!(close(wing.qualify, 3.0 * s.get("qualify"), 1e-12));
    assert!(close(wing.floor, area * s.get("wing_m2"), 1e-12));
    assert!(close(wing.bridge, s.get("bridge"), 1e-12));
    assert!(close(wing.total, wing.tools + wing.qualify + wing.floor + wing.bridge, 1e-12));
    let halls = capital(&Added { tools: tools.clone(), place: Place::Halls }, &s);
    assert!(close(halls.floor, area * s.get("halls_m2"), 1e-12));
    assert_eq!(halls.bridge, 0.0);
    assert!(close(halls.tools, wing.tools, 1e-12));
    // doubling the tools doubles every part but the bridge
    let double: Vec<(String, usize)> = tools.iter().map(|(a, n)| (a.clone(), 2 * n)).collect();
    let wing2 = capital(&Added { tools: double, place: Place::Wing }, &s);
    assert!(close(wing2.tools, 2.0 * wing.tools, 1e-12));
    assert!(close(wing2.qualify, 2.0 * wing.qualify, 1e-12));
    assert!(close(wing2.floor, 2.0 * wing.floor, 1e-12));
    assert!(close(wing2.bridge, wing.bridge, 1e-12));
}

// 4. Depreciation and upkeep of what a change adds.
#[test]
fn depreciation_and_upkeep() {
    let s = Sheet::central();
    let c = capital(&Added { tools: vec![("Litho".into(), 1), ("Implant".into(), 2)], place: Place::Wing }, &s);
    let tools = s.get("tool_litho") + 2.0 * s.get("tool_other");
    let want_dep = (tools + c.qualify) / (s.get("life_tool") * 365.0) + c.floor / (s.get("life_building") * 365.0)
        + c.bridge / (s.get("life_bridge") * 365.0);
    assert!(close(c.depreciation_day, want_dep, 1e-12), "{} against {want_dep}", c.depreciation_day);
    assert!(close(c.upkeep_day, tools * s.get("upkeep_rate") / 365.0, 1e-12));
}

// 5. Payback and net present value.
#[test]
fn payback_and_net_present_value() {
    let s = Sheet::central();
    let cap = capital(&Added { tools: vec![("Dry_Etch".into(), 3)], place: Place::Halls }, &s);
    let base = run_pl(&RunIn { a_wafers_day: 900.0, b_wafers_day: 20.0, b_revenue_day: 0.5e6 }, &capital(&Added { tools: vec![], place: Place::None }, &s), &s);
    let up = run_pl(&RunIn { a_wafers_day: 960.0, b_wafers_day: 20.0, b_revenue_day: 0.5e6 }, &cap, &s);
    let c = change(&base, &up, &cap, &s);
    assert!(close(c.d_cash_day, up.cash - base.cash, 1e-12));
    assert!(close(c.d_profit_day, up.profit - base.profit, 1e-12));
    assert!(c.d_cash_day > 0.0);
    assert!(close(c.payback_days.unwrap(), cap.total / c.d_cash_day, 1e-12));
    let r: f64 = s.get("rate");
    let days = (s.get("horizon_years") * 365.0) as usize;
    let sum: f64 = (1..=days).map(|d| (1.0 + r).powf(-(d as f64) / 365.0)).sum();
    assert!((npv_factor(&s) - sum).abs() < 1e-6);
    assert!((c.npv - (-cap.total + c.d_cash_day * sum)).abs() < 1.0);
    assert!(npv_factor(&s.with("rate", 0.12)) < npv_factor(&s.with("rate", 0.08)));
    // a change that loses cash never pays back
    let down = run_pl(&RunIn { a_wafers_day: 880.0, b_wafers_day: 20.0, b_revenue_day: 0.5e6 }, &cap, &s);
    let c2 = change(&base, &down, &cap, &s);
    assert!(c2.d_cash_day <= 0.0);
    assert_eq!(c2.payback_days, None);
    assert!(c2.npv < -cap.total + 1.0);
}

// 6. Family B's revenue from the saved price grid equals the revenue from the run's own lots.
#[test]
fn b_revenue_from_the_grid_matches_the_lots() {
    let shop = Shop::parse(TOY).unwrap();
    let r = run(&shop, &RunOptions { seed: 19, until: Some(20000.0), record: true }, None);
    let w = Window { from: 2000.0, to: 20000.0 };
    let days = (w.to - w.from) / 1440.0;
    let a_wafers_day: f64 = r.lots.iter().filter(|l| l.route == "ra" && l.done.is_some_and(|d| d > w.from && d <= w.to)).map(|l| l.size as f64).sum::<f64>() / days;
    let grid = PriceGrid::preregistered("B");
    let row: Vec<f64> = grid.iter().map(|m| money(&shop, &r, &w, m, 0, 0.0).per_day).collect();
    for s in [Sheet::central(), Sheet::central().with("b_price", 30000.0), Sheet::central().with("b_decay", 0.1)] {
        let lots = b_revenue_day(&shop, &r, &w, &s);
        let grid_b = b_revenue_from_grid(&row, a_wafers_day, &s);
        assert!(lots > 0.0);
        assert!((lots - grid_b).abs() < 1e-6 * (1.0 + lots), "{lots} against {grid_b}");
    }
}

// 7. The saved two-family sweep in dollars, with no rerun.
#[test]
fn the_saved_sweep_in_dollars() {
    let Some(smt) = common::smt2020_dir() else { return };
    let dir = common::repo().join("results/two-families");
    let p = sweep_pl(&dir, &smt, &Sheet::central()).unwrap();
    let runs = std::fs::read_to_string(dir.join("runs.tsv")).unwrap();
    assert_eq!(p.runs.len(), runs.lines().count() - 1);
    assert!((p.alpha_each - 0.05 / 56.0).abs() < 1e-12);
    for share in [1.0, 2.0, 4.0, 8.0] {
        let cells: Vec<_> = p.cells.iter().filter(|c| c.share == share).collect();
        assert_eq!(cells.len(), 14, "x{share}: every cell but the shared floor with today's order");
        for c in &cells {
            assert!(!(c.strategy == "D1 share" && c.policy == "P0 today"));
            assert!(c.d_profit.lo <= c.d_profit.mean && c.d_profit.mean <= c.d_profit.hi);
            assert!(["better", "worse", "no clear effect"].contains(&c.verdict.as_str()));
            if c.strategy == "D1 share" {
                assert_eq!(c.capital, 0.0, "{} {}", c.strategy, c.policy);
            } else {
                assert!(c.capital > 0.0, "{} {}", c.strategy, c.policy);
            }
        }
        let today = p.today.iter().find(|t| t.share == share).expect("today's fab at each share");
        assert!(today.profit.is_finite() && today.revenue > 0.0);
    }
}
