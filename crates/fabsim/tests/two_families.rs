//! Two wafer families in one fab (docs/TWO-FAMILIES.md). Written before the code.
//! From the SMT2020 testbed, with a gigafab-style layout of our own design; not a real fab.

mod common;

use std::collections::HashMap;

use fabsim::engine::{run, Decision, RunOptions, RunResult};
use fabsim::layout::Config;
use fabsim::money::{money, Money};
use fabsim::shop::Shop;
use fabsim::twofam::{contested, copy_groups, engineering_lots, lay_out, two_family_shop, EngLots, Strategy};
use fabsim::window::Window;

const BASE: &str = "fabgym-shop 1
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
";

const FAMS: &str = "family\tra\tA\nfamily\trb\tB\n";

fn toy(extra: &str) -> Shop {
    Shop::parse(&format!("{BASE}{extra}")).unwrap()
}

fn go(shop: &Shop, seed: u64, until: f64) -> RunResult {
    run(shop, &RunOptions { seed, until: Some(until), record: true }, None)
}

fn fam_of_lot(r: &RunResult, l: u32) -> &'static str {
    if r.lots[l as usize].route == "rb" {
        "B"
    } else {
        "A"
    }
}

// 1. Switches off: families named and nothing else changes nothing; the new records round-trip.
#[test]
fn switches_off_same_log_and_round_trip() {
    let plain = go(&toy(""), 3, 3000.0).log_text();
    let named = go(&toy(FAMS), 3, 3000.0).log_text();
    common::assert_same_text(&named, &plain, "families only label lots");
    let full = toy(&format!("{FAMS}famcap\tB\t2\nqual\tG\tB\t1\nreserve\tG\tB\t1\n"));
    let again = Shop::parse(&full.to_text()).unwrap();
    assert_eq!(again, full);
    for rec in ["family\tra\tA", "family\trb\tB", "famcap\tB\t2", "qual\tG\tB\t1", "reserve\tG\tB\t1"] {
        assert!(full.to_text().contains(rec), "{rec}");
    }
    assert_eq!(full.family_of("rb"), "B");
    assert_eq!(full.family_of("nope"), "");
}

// 2. A family cap holds, for releases and for lots listed with a later start; the other family is not delayed.
#[test]
fn family_cap_holds() {
    let mut extra = format!("{FAMS}famcap\tB\t2\n");
    for i in 0..6 {
        extra.push_str(&format!("lot\tbx{i}\trb\t3\t20.0\t100.0\t0\n"));
    }
    let shop = toy(&extra);
    let r = go(&shop, 5, 6000.0);
    let b: Vec<(f64, f64)> = r
        .lots
        .iter()
        .filter(|l| l.route == "rb" && !l.wip)
        .map(|l| (l.release, l.done.unwrap_or(f64::INFINITY)))
        .collect();
    assert!(b.len() > 6);
    for &(t, _) in &b {
        let inside = b.iter().filter(|&&(s, e)| s <= t && t < e).count();
        assert!(inside <= 2, "{inside} family-B lots in the fab at {t}");
    }
    for row in r.release_log.iter().filter(|x| x.id.starts_with("A.")) {
        assert_eq!(row.released, Some(row.scheduled), "{}", row.id);
    }
    assert!(r.release_log.iter().any(|x| x.id.starts_with("B.") && x.released != Some(x.scheduled)));
}

// 3. Qualification: only qualified tools start the family's lots.
#[test]
fn qualification_holds() {
    let r = go(&toy(&format!("{FAMS}qual\tG\tB\t1\n")), 7, 6000.0);
    let mut seen = 0;
    for t in &r.trace {
        let tool = &r.tools[t.tool as usize];
        if tool.group == "G" && fam_of_lot(&r, t.lot) == "B" {
            assert_eq!(tool.name, "G#1");
            seen += 1;
        }
    }
    assert!(seen > 10);
}

// 4. Reservation: a reserved tool takes no other family's lot while one of its family waits.
#[test]
fn reservation_holds() {
    let r = go(&toy(&format!("{FAMS}qual\tG\tB\t2\nreserve\tG\tB\t1\n")), 11, 6000.0);
    let waits: Vec<(f64, f64)> = r
        .trace
        .iter()
        .filter(|t| r.tools[t.tool as usize].group == "G" && fam_of_lot(&r, t.lot) == "B")
        .map(|t| (t.arrive, t.start))
        .collect();
    let mut a_on_reserved = 0;
    for t in &r.trace {
        let tool = &r.tools[t.tool as usize];
        if tool.name == "G#1" && fam_of_lot(&r, t.lot) == "A" {
            a_on_reserved += 1;
            let s = t.start;
            assert!(!waits.iter().any(|&(a, st)| a < s && st > s), "an A lot started on the reserved tool at {s} while a B lot waited");
        }
    }
    assert!(a_on_reserved > 0, "the reserved tool still serves A when no B waits");
}

// 5. Rules see the family, and it matters.
#[test]
fn rules_see_the_family() {
    // a burst of both families at time 0, so they wait together and the choice is real
    let mut extra = FAMS.to_string();
    for i in 0..8 {
        extra.push_str(&format!("lot\tax{i}\tra\t25\t10.0\t0.0\t0\nlot\tbx{i}\trb\t5\t10.0\t0.0\t0\n"));
    }
    let shop = toy(&extra);
    let opts = RunOptions { seed: 13, until: Some(8000.0), record: false };
    let mut fams = HashMap::new();
    let mut mixed = 0;
    let prefer = |want: &'static str| {
        move |d: &Decision| d.candidates.iter().position(|c| c.family == want).unwrap_or(d.default)
    };
    let mut pb = prefer("B");
    let rb = run(&shop, &opts, Some(&mut pb));
    let mut pa = prefer("A");
    let ra = run(&shop, &opts, Some(&mut pa));
    let mut look = |d: &Decision| {
        for c in &d.candidates {
            *fams.entry(c.family.clone()).or_insert(0) += 1;
        }
        if d.candidates.iter().any(|c| c.family == "A") && d.candidates.iter().any(|c| c.family == "B") {
            mixed += 1;
        }
        d.default
    };
    run(&shop, &opts, Some(&mut look));
    assert!(fams.contains_key("A") && fams.contains_key("B"));
    assert!(mixed > 5, "only {mixed} decisions offered both families");
    let mean_b = |r: &RunResult| {
        let v: Vec<f64> = r.lots.iter().filter(|l| l.route == "rb").filter_map(|l| l.done.map(|d| d - l.release)).collect();
        v.iter().sum::<f64>() / v.len() as f64
    };
    assert!(mean_b(&rb) < mean_b(&ra), "B first {} against A first {}", mean_b(&rb), mean_b(&ra));
}

#[test]
fn candidates_carry_the_family_field() {
    assert_eq!(fabsim::engine::Candidate::FIELDS.last(), Some(&"family"));
}

// 6. Engineering lots, from the published facts.
#[test]
fn engineering_lots_follow_the_published_pattern() {
    let e = EngLots::published("part_E3", 60.0 * 1440.0, 7);
    let lots = engineering_lots(&e);
    let mut by: Vec<(f64, Vec<&fabsim::shop::LotSpec>)> = vec![];
    for l in &lots {
        match by.iter_mut().find(|x| x.0 == l.start) {
            Some(x) => x.1.push(l),
            None => by.push((l.start, vec![l])),
        }
    }
    by.sort_by(|a, b| a.0.total_cmp(&b.0));
    assert_eq!(by[0].0, 480.0);
    for w in by.windows(2) {
        assert_eq!(w[1].1.len(), 20);
    }
    for (i, w) in by.windows(2).enumerate() {
        let gap = (w[1].0 - w[0].0) / 1440.0;
        assert_eq!(gap, if i % 2 == 0 { 2.0 } else { 5.0 }, "gap {i}");
    }
    assert!(lots.iter().all(|l| (1..=10).contains(&l.size) && l.step == 0 && l.route == "part_E3"));
    assert_eq!(lots.iter().filter(|l| l.priority == 20.0).count() * 5, lots.len());
    assert!(lots.iter().all(|l| l.priority == 10.0 || l.priority == 20.0));
    assert_eq!(engineering_lots(&e), lots);
    let other = engineering_lots(&EngLots { seed: 8, ..e.clone() });
    assert_ne!(other.iter().map(|l| l.size).collect::<Vec<_>>(), lots.iter().map(|l| l.size).collect::<Vec<_>>());
    let twice = engineering_lots(&EngLots { scale: 2.0, ..e });
    assert_eq!(twice.len(), 2 * lots.len());
}

// 7. Copies serve only their family.
#[test]
fn copies_serve_only_their_family() {
    let shop = copy_groups(&toy(FAMS), &[("G".to_string(), 1)], "B").unwrap();
    let copy = shop.groups.iter().find(|g| g.name == "G@B").expect("the copy");
    assert_eq!(copy.count, 1);
    assert!(shop.route("rb").unwrap().steps.iter().any(|s| s.group == "G@B"));
    assert!(shop.route("ra").unwrap().steps.iter().all(|s| s.group != "G@B"));
    let r = go(&shop, 17, 6000.0);
    let mut b_on_copy = 0;
    for t in &r.trace {
        let g = &r.tools[t.tool as usize].group;
        match fam_of_lot(&r, t.lot) {
            "A" => assert_ne!(g, "G@B"),
            _ => {
                assert_ne!(g, "G");
                if g == "G@B" {
                    b_on_copy += 1;
                }
            }
        }
    }
    assert!(b_on_copy > 10);
}

fn quick(mut c: Config) -> Config {
    c.iters = 3000;
    c.restarts = 1;
    c
}

// 8. The three strategies from the SMT2020 testbed.
#[test]
fn strategies_on_the_smt2020_model() {
    let Some(dir) = common::smt2020_dir() else { return };
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let e = EngLots::published("part_E3", 30.0 * 1440.0, 1);
    let shop = two_family_shop(&base, "part_3", &e).unwrap();
    assert_eq!(shop.family_of("part_3"), "A");
    assert_eq!(shop.family_of("part_4"), "A");
    assert_eq!(shop.family_of("part_E3"), "B");
    assert_eq!(shop.route("part_E3").unwrap().steps, shop.route("part_3").unwrap().steps);
    let top = contested(&shop, "B", 3);
    assert_eq!(top.len(), 3);
    let cfg = quick(Config::realistic());
    let (d1, i1) = lay_out(&shop, &areas, &cfg, &Strategy::Share, "B").unwrap();
    assert_eq!(d1.groups.len(), shop.groups.len());
    assert_eq!((i1.tools_added, i1.metres_added), (0, 0.0));
    let (d2, i2) = lay_out(&shop, &areas, &cfg, &Strategy::Wing { groups: 3, tools: 1 }, "B").unwrap();
    let (d3, i3) = lay_out(&shop, &areas, &cfg, &Strategy::Copies { groups: 3, tools: 1 }, "B").unwrap();
    for (s, info, wing) in [(&d2, &i2, true), (&d3, &i3, false)] {
        let o = s.oht.as_ref().unwrap();
        let copies: Vec<&str> = s.groups.iter().filter(|g| g.name.ends_with("@B")).map(|g| g.name.as_str()).collect();
        assert_eq!(copies.len(), 3);
        assert_eq!(info.tools_added, 3);
        assert!(info.metres_added > 0.0);
        for c in copies {
            let p = o.places.iter().find(|p| p.0 == c).and_then(|p| p.1).expect("a place for the copy");
            if wing {
                assert_eq!(p.phase, 2, "{c}");
            } else {
                assert!(p.phase < 2, "{c}");
            }
        }
        assert_eq!(o.lengths.len(), if wing { 3 } else { 2 });
        assert!(s.groups.iter().all(|g| o.places.iter().any(|p| p.0 == g.name)));
        go(s, 1, 1440.0);
    }
    go(&d1, 1, 1440.0);
}

// 9. Money: the formula on a run, and the same figure twice.
#[test]
fn money_is_the_stated_formula() {
    let shop = toy(FAMS);
    let r = go(&shop, 19, 20000.0);
    let w = Window { from: 2000.0, to: 20000.0 };
    let m = Money {
        margin: vec![("A".into(), 3.0), ("B".into(), 0.0)],
        family_b: "B".into(),
        price0: 100.0,
        free_days: 0.05,
        decay: 2.0,
        tool_day: 7.0,
        metre_day: 0.5,
    };
    let s = money(&shop, &r, &w, &m, 2, 10.0);
    let days = (w.to - w.from) / 1440.0;
    let sched: HashMap<&str, f64> = r.release_log.iter().map(|x| (x.id.as_str(), x.scheduled)).collect();
    let (mut a, mut b) = (0.0, 0.0);
    for l in &r.lots {
        let Some(d) = l.done else { continue };
        if !(d > w.from && d <= w.to) {
            continue;
        }
        if l.route == "ra" {
            a += l.size as f64 * 3.0;
        } else {
            let start = *sched.get(l.id.as_str()).unwrap_or(&l.release);
            let ct = (d - start) / 1440.0;
            let price = 100.0 * (1.0 - 2.0 * (ct - 0.05).max(0.0)).max(0.0);
            b += l.size as f64 * price;
        }
    }
    let want = (a + b) / days - 2.0 * 7.0 - 10.0 * 0.5;
    assert!((s.per_day - want).abs() < 1e-9, "{} against {want}", s.per_day);
    assert!(s.b_lots > 0);
    assert_eq!(money(&shop, &go(&shop, 19, 20000.0), &w, &m, 2, 10.0), s);
}
