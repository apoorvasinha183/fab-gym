//! A maintenance calendar's first occurrence (FOA) is read with its units by default. The
//! reference compile reads it as minutes; `load_reference` keeps that for the exact-match tests.

mod common;

use fabsim::smt2020::{load, load_reference};

fn firsts(shop: &fabsim::shop::Shop, group: &str) -> (Vec<Option<f64>>, Vec<Option<f64>>) {
    let g = shop.groups.iter().find(|g| g.name == group).unwrap_or_else(|| panic!("no group {group}"));
    (g.pm.iter().map(|p| p.first).collect(), g.pm_pieces.iter().map(|p| p.first).collect())
}

#[test]
fn days_are_read_as_days() {
    let Some(dir) = common::smt2020_dir() else { return };
    let s = load(&dir).unwrap();
    assert_eq!(firsts(&s, "DefMet_BE_42").0, vec![Some(27.0 * 1440.0), Some(81.9 * 1440.0)]);
    assert_eq!(firsts(&s, "DefMet_FE_106").0, vec![Some(27.3 * 1440.0), Some(82.8 * 1440.0)]);
}

#[test]
fn the_reference_reading_is_kept() {
    let Some(dir) = common::smt2020_dir() else { return };
    let s = load_reference(&dir).unwrap();
    assert_eq!(firsts(&s, "DefMet_BE_42").0, vec![Some(27.0), Some(81.9)]);
    assert_eq!(firsts(&s, "DefMet_FE_106").0, vec![Some(27.3), Some(82.8)]);
}

#[test]
fn wafer_counts_are_unchanged() {
    let Some(dir) = common::smt2020_dir() else { return };
    for s in [load(&dir).unwrap(), load_reference(&dir).unwrap()] {
        assert_eq!(firsts(&s, "EPI_38").1, vec![Some(4250.0), Some(18700.0), Some(56100.0)]);
        assert_eq!(firsts(&s, "WE_BE_7").1, vec![Some(4350.0), Some(19140.0), Some(57420.0)]);
    }
}

#[test]
fn nothing_else_differs() {
    let Some(dir) = common::smt2020_dir() else { return };
    let fixed = load(&dir).unwrap();
    let mut reference = load_reference(&dir).unwrap();
    for g in &mut reference.groups {
        if g.name == "DefMet_BE_42" || g.name == "DefMet_FE_106" {
            for p in &mut g.pm {
                p.first = p.first.map(|x| x * 1440.0);
            }
        }
    }
    assert_eq!(fixed, reference);
}
