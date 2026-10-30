//! Regret option C (docs/LONG-RESCORE.md, the Speed and Regret page): the capacity ceiling. No schedule can get more
//! wafers out a day than the busiest tool group can pass at the released product mix, nor more than is released.
//! Written before the code. From the SMT2020 testbed's rules.

mod common;

use fabsim::bound::capacity;
use fabsim::shop::Shop;

fn toy(group: &str) -> Shop {
    Shop::parse(&format!(
        "fabgym-shop 1
transport\t5.0\t10.0
{group}
route\tr
step\tA\tlot\t50.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t12.0\t0.0\t-\tN
"
    ))
    .unwrap()
}

#[test]
fn one_group_no_downtime_is_its_tools_over_its_work_per_wafer() {
    let c = capacity(&toy("group\tA\t2\t1.0\t1.0\t-\t-\t-"));
    // 2 tools x 1,440 min a day, over (50 + 1 + 1) min a lot of 25 wafers
    let want = 2.0 * 1440.0 / (52.0 / 25.0);
    assert!((c.wafers_per_day - want).abs() < 1e-9, "{} against {want}", c.wafers_per_day);
    assert!((c.released_per_day - 25.0 * 1440.0 / 12.0).abs() < 1e-9);
    assert_eq!(c.bottleneck, "A");
    assert!((c.strict_wafers_per_day - want).abs() < 1e-9, "no downtime: the strict and expected ceilings agree");
}

#[test]
fn breakdowns_take_their_expected_share() {
    let c = capacity(&toy("group\tA\t2\t1.0\t1.0\t-\t900.0\t100.0"));
    let want = 0.9 * 2.0 * 1440.0 / (52.0 / 25.0);
    assert!((c.wafers_per_day - want).abs() < 1e-9);
    assert!(c.strict_wafers_per_day > c.wafers_per_day, "the strict ceiling ignores downtime");
}

#[test]
fn the_ceiling_is_capped_by_what_is_released() {
    let c = capacity(&toy("group\tA\t200\t1.0\t1.0\t-\t-\t-"));
    assert!((c.wafers_per_day - c.released_per_day).abs() < 1e-9);
    assert_eq!(c.bottleneck, "released");
}

#[test]
fn smt2020s_ceiling_lies_above_what_todays_rule_gets_out() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let c = capacity(&shop);
    // today's rule gets about 1,246 wafers a day out over days 130 to 190 on seed 0 (docs/LONG-RESCORE.md)
    assert!(c.wafers_per_day > 1246.0 && c.wafers_per_day <= c.released_per_day + 1e-9, "{c:?}");
    assert!(c.groups.iter().any(|g| g.name == c.bottleneck) || c.bottleneck == "released");
    assert!(c.groups.iter().all(|g| g.wafers_per_day >= c.wafers_per_day - 1e-9), "the ceiling is the lowest of them");
}
