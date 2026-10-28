//! Ask the fab, with two families (docs/ASK-FAMILIES.md, parts 1 and 2). Written before the code.
//! On the SMT2020 model, with a layout of our own design; not a real fab.

mod common;

use fabsim::layout::Config;
use fabsim::scenario::{Change, FloorKind, Scenario};
use fabsim::score::{family_arm, score, score_with, FamilyContext, Protocol};
use fabsim::shop::Shop;
use fabsim::twofam::{b_cap, EngLots, Policy as FamPolicy};

const OLD: &str = "fabgym-scenario 1
question\tEtch is down tomorrow morning, what do we do?
shock\toutage\tEtch\t30\t8\tassumed
candidate\tfifo\trule\tfifo
candidate\tcapped\tcap\t6
sweep\toutage\thours\t2\t14\t4
";

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t2\t0.0\t0.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t45.0\t0.0\t-\tA
";

fn toy() -> Shop {
    Shop::parse(TOY).unwrap()
}

fn ctx() -> FamilyContext {
    FamilyContext { from_route: "ra".into(), b_route: "part_E3".into(), areas: None, layout: Config::realistic(), cache: None }
}

fn small(threads: usize) -> Protocol {
    Protocol { warmup_days: 1.0, window_days: 6.0, seeds: vec![0, 1, 2], threads }
}

const FAM: &str = "fabgym-scenario 1
question\tPrototype orders double. Their own copies, or first in line?
family\tshare\t2\tsaid
shock\tbreakdowns\t1.5\tassumed
candidate\tcopies\tfloor\tcopies
candidate\tfirst\tpolicy\tbfirst
candidate\treserved\tpolicy\treserve
candidate\tcapped-copies\tfloor\tcopies
candidate\tcapped-copies\tpolicy\tcap
";

// ------------------------------------------------------------------ the text

#[test]
fn old_scenarios_are_unchanged() {
    let s = Scenario::parse(OLD).unwrap();
    assert!(s.family.is_none());
    assert_eq!(s.to_text(), OLD);
    // a scenario without families still scores with plain `score`
    let mixed = Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap();
    let plain = Scenario::parse("fabgym-scenario 1\nquestion\tq\ncandidate\tfifo\trule\tfifo\n").unwrap();
    let r = score(&mixed, &plain, &Protocol { seeds: vec![0, 1], threads: 1, ..Default::default() }).unwrap();
    assert!(!r.families);
    assert!(r.arms.is_empty(), "no arm shops for a one-family question");
}

#[test]
fn family_records_round_trip() {
    let s = Scenario::parse(FAM).unwrap();
    let f = s.family.as_ref().unwrap();
    assert_eq!((f.share, f.said), (2.0, true));
    assert_eq!(s.candidates.len(), 4);
    assert_eq!(s.candidates[0].changes, vec![Change::Floor(FloorKind::Copies)]);
    assert_eq!(s.candidates[1].changes, vec![Change::FamilyPolicy(FamPolicy::BFirst)]);
    assert_eq!(s.candidates[3].changes, vec![Change::Floor(FloorKind::Copies), Change::FamilyPolicy(FamPolicy::Cap)]);
    assert_eq!(Scenario::parse(&s.to_text()).unwrap(), s);
    assert!(s.to_text().contains("family\tshare\t2\tsaid\n"));
    for (k, p) in [("today", FamPolicy::Today), ("bfirst", FamPolicy::BFirst), ("cap", FamPolicy::Cap), ("reserve", FamPolicy::Reserve), ("qualify", FamPolicy::Qualify)] {
        assert_eq!(p.key(), k);
        assert_eq!(FamPolicy::from_key(k), Some(p));
    }
    // an assumed share may be swept
    let sw = "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tassumed\ncandidate\tw\tfloor\twing\nsweep\tfamily\tvalue\t1\t4\t3\n";
    assert_eq!(Scenario::parse(sw).unwrap().sweep.unwrap().points(), vec![1.0, 2.5, 4.0]);
}

#[test]
fn family_refusals() {
    let bad = [
        // floor or policy without family
        "fabgym-scenario 1\nquestion\tq\ncandidate\tc\tfloor\twing\n",
        "fabgym-scenario 1\nquestion\tq\ncandidate\tc\tpolicy\tbfirst\n",
        // share out of range
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t0.1\tsaid\n",
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t20\tsaid\n",
        // a said share swept
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tsaid\nsweep\tfamily\tvalue\t1\t4\t3\n",
        // unknown floor, unknown policy, family B first with another rule, two families
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tsaid\ncandidate\tc\tfloor\tbasement\n",
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tsaid\ncandidate\tc\tpolicy\tlottery\n",
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tsaid\ncandidate\tc\tpolicy\tbfirst\ncandidate\tc\trule\tfifo\n",
        "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tsaid\nfamily\tshare\t3\tsaid\n",
    ];
    for b in bad {
        assert!(Scenario::parse(b).is_err(), "accepted: {b:?}");
    }
    // a two-family scenario needs the family context
    assert!(score(&toy(), &Scenario::parse(FAM).unwrap(), &small(1)).is_err());
}

// ------------------------------------------------------------------ the arms

#[test]
fn arms_build_the_expected_shops() {
    let s = Scenario::parse(FAM).unwrap();
    let base = toy();
    let p = small(1);
    let c = ctx();
    let raw = fabsim::measure::raw_processing_days(&base, 20, 0)["ra"];
    let e = EngLots { scale: 2.0, ..EngLots::published("part_E3", (p.warmup_days + p.window_days) * 1440.0, 1) };
    let today = family_arm(&base, &s, None, None, &p, &c).unwrap();
    assert_eq!(today.shop.family_of("part_E3"), "B");
    assert_eq!(today.shop.family_of("ra"), "A");
    assert_eq!(today.shop.lots.iter().filter(|l| l.route == "part_E3").count(), fabsim::twofam::engineering_lots(&e).len());
    assert!(today.shop.groups.iter().all(|g| !g.name.ends_with("@B")));
    assert!(!today.bfirst && today.tools_added == 0);
    let copies = family_arm(&base, &s, Some(&s.candidates[0]), None, &p, &c).unwrap();
    assert_eq!(copies.shop.groups.iter().filter(|g| g.name.ends_with("@B")).count(), 2, "both toy groups copied");
    assert_eq!(copies.tools_added, 2);
    assert_eq!(copies.extra_areas.len(), 0, "no areas without a layout");
    let first = family_arm(&base, &s, Some(&s.candidates[1]), None, &p, &c).unwrap();
    assert!(first.bfirst);
    let reserved = family_arm(&base, &s, Some(&s.candidates[2]), None, &p, &c).unwrap();
    assert_eq!(reserved.shop.reserves.len(), 2);
    assert!(reserved.shop.quals.iter().all(|q| q.2 == base.group(&q.0).unwrap().count));
    let capped = family_arm(&base, &s, Some(&s.candidates[3]), None, &p, &c).unwrap();
    assert_eq!(capped.shop.famcaps, vec![("B".to_string(), b_cap(&e, raw))]);
    assert_eq!(capped.shop.groups.iter().filter(|g| g.name.ends_with("@B")).count(), 2);
    // the breakdown shock applies to every arm (the toy has no breakdowns, so the shops are otherwise the same)
    let txt = Shop::parse(&copies.shop.to_text()).unwrap();
    assert_eq!(txt, copies.shop);
}

#[test]
fn a_wing_on_the_smt2020_model_has_its_own_hall() {
    let Some(dir) = common::smt2020_dir() else { return };
    let base = fabsim::smt2020::load(&dir).unwrap();
    let mut layout = Config::realistic();
    layout.iters = 3000;
    layout.restarts = 1;
    let c = FamilyContext { from_route: "part_3".into(), b_route: "part_E3".into(), areas: Some(fabsim::smt2020::areas(&dir).unwrap()), layout, cache: None };
    let s = Scenario::parse("fabgym-scenario 1\nquestion\tq\nfamily\tshare\t4\tsaid\ncandidate\twing\tfloor\twing\n").unwrap();
    let p = Protocol::families();
    assert_eq!((p.warmup_days, p.window_days, p.seeds.len()), (120.0, 120.0, 10));
    let w = family_arm(&base, &s, Some(&s.candidates[0]), None, &p, &c).unwrap();
    assert_eq!(w.shop.oht.as_ref().unwrap().lengths.len(), 3);
    assert_eq!(w.extra_areas.len(), 3);
    assert!(w.extra_areas.iter().all(|(g, a)| g.ends_with("@B") && a == "P3 wing"));
    let t = family_arm(&base, &s, None, None, &p, &c).unwrap();
    assert_eq!(t.shop.oht.as_ref().unwrap().lengths.len(), 2);
}

// ------------------------------------------------------------------ the scorer

#[test]
fn two_families_score_deterministically_with_money_and_shops() {
    let s = Scenario::parse(FAM).unwrap();
    let one = score_with(&toy(), &s, &small(1), Some(&ctx())).unwrap();
    let three = score_with(&toy(), &s, &small(3), Some(&ctx())).unwrap();
    assert_eq!(one.to_json(), three.to_json());
    assert!(one.families);
    assert_eq!(one.arms.len(), 5, "today and four candidates");
    assert_eq!(one.arms[0].name, "today");
    for a in &one.arms {
        assert_eq!(Shop::parse(&a.shop_text).unwrap().family_of("part_E3"), "B");
    }
    for c in &one.candidates {
        for k in ["money", "a_wafers", "b_lots", "b_cycle_days", "moves"] {
            let m = c.measure(k);
            assert_eq!(m.base.len(), 3);
        }
        assert!(c.measure("money").higher_is_better && !c.measure("b_cycle_days").higher_is_better);
    }
    let j = one.to_json();
    for k in ["\"families\":true", "\"arms\":[", "\"shop\":\"fabgym-shop 1", "\"money\":", "Real-fab effect"] {
        assert!(j.contains(k), "{k} missing");
    }
    // the best is the better-than-today candidate with the highest money lower bound, if any
    let better: Vec<_> = one.candidates.iter().filter(|c| c.measure("money").verdict == fabsim::uq::Verdict::Better).collect();
    match &one.best {
        None => assert!(better.is_empty()),
        Some(b) => {
            let top = better.iter().max_by(|x, y| x.measure("money").interval.lo.total_cmp(&y.measure("money").interval.lo)).unwrap();
            assert_eq!(&top.name, b);
        }
    }
}

// Found in the browser: the hoist's start marks "no bay" with the largest 64-bit number, which a 32-bit build (the
// page's WebAssembly) cannot read as a usize. A bay too large for the platform reads as "no bay".
#[test]
fn the_no_bay_marker_reads_on_any_width() {
    assert_eq!(fabsim::shop::read_bay("18446744073709551615"), Ok(usize::MAX));
    assert_eq!(fabsim::shop::read_bay("4294967295"), Ok(usize::try_from(4294967295u64).unwrap_or(usize::MAX)));
    assert_eq!(fabsim::shop::read_bay("7"), Ok(7));
    assert!(fabsim::shop::read_bay("seven").is_err());
    assert!(fabsim::shop::read_bay("-1").is_err());
}
