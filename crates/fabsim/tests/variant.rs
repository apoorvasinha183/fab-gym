//! The decision as a fab (docs/NARRATIVE.md, deliverable 2): a signed answer, copies of the busiest groups for
//! prototypes in the halls, becomes a variant of today's realistic campus. Today's optimised plan is kept block for
//! block and each copy sits right after its original, so the plans, the BIM and the bill of materials differ only
//! around the copies. Written before the code. A gigafab-style layout of our own design on the SMT2020 model.

mod common;

use fabsim::layout::{Config, Problem};
use fabsim::twofam::{contested, copy_groups, two_family_shop, EngLots};
use fabsim::variant::{variant_layout, Variant};

fn quick() -> Config {
    let mut c = Config::realistic();
    c.iters = 3000;
    c.restarts = 1;
    c
}

fn build() -> Option<(Variant, Problem, fabsim::layout::Plan)> {
    let dir = common::smt2020_dir()?;
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let today = Problem::new(&base, &areas, &quick()).unwrap();
    let plan = today.optimise();
    let v = variant_layout(&base, &areas, &quick(), 2.0, 3).unwrap();
    Some((v, today, plan))
}

#[test]
fn todays_plan_is_kept_and_each_copy_follows_its_original() {
    let Some((v, today, plan)) = build() else { return };
    assert_eq!(v.copies.len(), 3, "one copy for each of the three groups prototypes load most");
    assert_eq!(v.plan.phases.len(), plan.phases.len());
    for (ph, sides) in plan.phases.iter().enumerate() {
        for side in 0..2 {
            let a = &sides[side];
            let b = &v.plan.phases[ph][side];
            assert_eq!(a.len(), b.len(), "phase {ph} side {side}: the same blocks");
            for (ba, bb) in a.iter().zip(b) {
                assert_eq!(ba.area, bb.area);
                let names_a: Vec<String> = ba.groups.iter().map(|&g| today.name(g).to_string()).collect();
                let names_b: Vec<String> = bb.groups.iter().map(|&g| v.problem.name(g).to_string()).collect();
                // remove the copies and today's block is left, in order
                let kept: Vec<String> = names_b.iter().filter(|n| !n.ends_with("@B")).cloned().collect();
                assert_eq!(kept, names_a, "phase {ph} side {side} area {}: today's groups in today's order", ba.area);
                for (i, n) in names_b.iter().enumerate() {
                    if let Some(orig) = n.strip_suffix("@B") {
                        assert!(i > 0 && names_b[i - 1] == orig, "{n} sits right after {orig}");
                    }
                }
            }
        }
    }
}

#[test]
fn the_variant_shop_is_todays_two_family_shop_plus_the_copies() {
    let Some((v, _, _)) = build() else { return };
    let dir = common::smt2020_dir().unwrap();
    let base = fabsim::smt2020::load(&dir).unwrap();
    let e = EngLots { scale: 2.0, ..EngLots::published("part_E3", 300.0 * 1440.0, 1) };
    let two = two_family_shop(&base, "part_3", &e).unwrap();
    let picks: Vec<(String, usize)> = contested(&two, "B", 3).into_iter().map(|g| (g, 1)).collect();
    let want = copy_groups(&two, &picks, "B").unwrap();
    let mut got = v.shop.clone();
    got.oht = None;
    assert_eq!(got.to_text(), want.to_text(), "nothing but the copies changes");
    assert!(v.shop.oht.is_some(), "the variant shop carries its layout");
    for c in &v.copies {
        assert!(v.shop.groups.iter().any(|g| g.name == c.copy && g.count == 1), "{} has one tool", c.copy);
        assert!(!c.area.is_empty(), "{}: its original's area", c.copy);
    }
}

#[test]
fn the_variant_is_the_same_on_every_run() {
    let Some((a, _, _)) = build() else { return };
    let Some((b, _, _)) = build() else { return };
    assert_eq!(a.plan, b.plan);
    assert_eq!(a.shop.to_text(), b.shop.to_text());
}
