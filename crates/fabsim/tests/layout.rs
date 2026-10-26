//! A gigafab-style campus on the SMT2020 model (docs/FAB-LAYOUT.md): flows, the plain plan,
//! packing, distance, the optimiser, and lots moved by the layout's distances in the engine.

mod common;

use fabsim::engine::{run, RunOptions};
use fabsim::layout::{Campus, Config, Problem, START};
use fabsim::shop::{Oht, Place, Shop};

fn toy() -> Shop {
    Shop::parse(&common::read("golden/toy/mixed.shop.txt")).unwrap()
}

fn toy_areas() -> Vec<(String, String)> {
    [("Litho", "Litho"), ("Furnace", "Diffusion"), ("Etch", "Dry_Etch"), ("Metro", "Litho_Met"), ("Single", "Wet_Etch")]
        .iter()
        .map(|(a, b)| (a.to_string(), b.to_string()))
        .collect()
}

fn quick(mut c: Config) -> Config {
    c.iters = 3000;
    c.restarts = 2;
    c
}

/// Four groups, a stocker and one route: A, D (stocker), B, C (sampled 1 in 4), A.
const FLOWS: &str = "fabgym-shop 1
transport\t5.0\t10.0
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t1\t0.0\t0.0\t-\t-\t-
group\tC\t1\t0.0\t0.0\t-\t-\t-
group\tD\t10\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tD\tlot\t60.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tC\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t0.25\t-\t-\t-\t-
step\tA\tlot\t10.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t720.0\t0.0\t100\tR
";

fn flow_areas() -> Vec<(String, String)> {
    [("A", "Litho"), ("B", "Dry_Etch"), ("C", "Litho_Met"), ("D", "Delay_32")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect()
}

// ------------------------------------------------------------------ flows

#[test]
fn flows_merge_the_stocker_and_weigh_sampled_steps() {
    let shop = Shop::parse(FLOWS).unwrap();
    let p = Problem::new(&shop, &flow_areas(), &Config::gigafab()).unwrap();
    let idx = |n: &str| shop.groups.iter().position(|g| g.name == n).unwrap();
    let rate = |a: usize, b: usize| p.flows().iter().filter(|f| f.0 == a && f.1 == b).map(|f| f.2).sum::<f64>();
    // two lots a day (every 720 minutes)
    assert!((rate(START, idx("A")) - 2.0).abs() < 1e-12);
    assert!((rate(idx("A"), idx("B")) - 2.0).abs() < 1e-12, "A to B through the stocker");
    assert!((rate(idx("B"), idx("C")) - 0.5).abs() < 1e-12);
    assert!((rate(idx("B"), idx("A")) - 1.5).abs() < 1e-12, "C skipped");
    assert!((rate(idx("C"), idx("A")) - 0.5).abs() < 1e-12);
    assert!(p.flows().iter().all(|f| f.0 != idx("D") && f.1 != idx("D")), "no flow touches the stocker");
    let total: f64 = p.flows().iter().map(|f| f.2).sum();
    assert!((total - 6.5).abs() < 1e-12, "{total}");
    assert_eq!(p.phase_of(idx("D")), None);
}

#[test]
fn an_unknown_group_is_refused() {
    let shop = Shop::parse(FLOWS).unwrap();
    let mut a = flow_areas();
    a.pop();
    assert!(Problem::new(&shop, &a, &Config::gigafab()).is_err(), "a group with no area must be refused");
}

// ------------------------------------------------------------------ packing

fn check_campus(shop: &Shop, p: &Problem, c: &Campus, cfg: &Config) {
    // every tool of every placed group, once
    for (gi, g) in shop.groups.iter().enumerate() {
        let n = c.tools.iter().filter(|t| t.group == gi).count();
        match p.phase_of(gi) {
            None => {
                assert_eq!(n, 0, "{} is a stocker", g.name);
                assert!(c.places[gi].is_none());
            }
            Some(ph) => {
                assert_eq!(n, g.count, "{}", g.name);
                let pl = c.places[gi].expect("a place");
                assert_eq!(pl.phase, ph);
                assert!(c.tools.iter().filter(|t| t.group == gi).all(|t| t.phase == ph));
            }
        }
    }
    // tools inside their bay, bays one area each, nothing overlaps
    for t in &c.tools {
        let b = &c.bays[t.bay];
        assert_eq!((b.phase, b.side), (t.phase, t.side));
        assert!(t.x0 >= b.x0 - 1e-9 && t.x1 <= b.x1 + 1e-9 && t.y0 >= 0.0 && t.y1 <= cfg.bay_depth + 1e-9, "tool outside its bay");
        assert_eq!(b.area, p.area_of(t.group));
    }
    let ov = |a0: f64, a1: f64, b0: f64, b1: f64| a0 < b1 - 1e-9 && b0 < a1 - 1e-9;
    for (i, a) in c.tools.iter().enumerate() {
        for b in &c.tools[i + 1..] {
            if a.phase == b.phase && a.side == b.side {
                assert!(!(ov(a.x0, a.x1, b.x0, b.x1) && ov(a.y0, a.y1, b.y0, b.y1)), "two tools overlap");
            }
        }
    }
    for (i, a) in c.bays.iter().enumerate() {
        for b in &c.bays[i + 1..] {
            if a.phase == b.phase && a.side == b.side {
                assert!(!ov(a.x0, a.x1, b.x0, b.x1), "two bays overlap");
            }
        }
        assert!(a.x1 <= c.lengths[a.phase] + 1e-9);
    }
}

#[test]
fn the_toy_packs_cleanly() {
    let shop = toy();
    let cfg = quick(Config::gigafab());
    let p = Problem::new(&shop, &toy_areas(), &cfg).unwrap();
    for plan in [p.plain(), p.optimise()] {
        check_campus(&shop, &p, &p.pack(&plan), &cfg);
    }
}

#[test]
fn smt2020_packs_cleanly_front_and_back_end_apart() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let cfg = Config::gigafab();
    let p = Problem::new(&shop, &areas, &cfg).unwrap();
    let c = p.pack(&p.plain());
    check_campus(&shop, &p, &c, &cfg);
    for (gi, g) in shop.groups.iter().enumerate() {
        let area = p.area_of(gi);
        let want = if area == "Delay_32" {
            None
        } else if g.name.contains("_BE_") {
            Some(1)
        } else {
            Some(0)
        };
        assert_eq!(p.phase_of(gi), want, "{} in {area}", g.name);
    }
    assert_eq!(c.lengths.len(), 2);
}

// ------------------------------------------------------------------ distance

#[test]
fn distance_is_a_walk_along_the_aisles() {
    let o = Oht {
        overhead: 4.0,
        speed: 150.0,
        jitter: 1.0,
        bridge: 60.0,
        spine: 8.0,
        lengths: vec![300.0, 200.0],
        start: Place { phase: 0, side: 0, bay: usize::MAX, x: 0.0, y: 0.0 },
        places: vec![],
    };
    let pl = |phase, side, bay, x, y| Place { phase, side, bay, x, y };
    let a = pl(0, 0, 3, 100.0, 20.0);
    let same_bay = pl(0, 0, 3, 104.0, 50.0);
    let other_bay = pl(0, 0, 5, 160.0, 10.0);
    let other_side = pl(0, 1, 9, 160.0, 10.0);
    let far = pl(1, 1, 2, 30.0, 15.0);
    assert_eq!(o.distance(&a, &a), 0.0);
    assert_eq!(o.distance(&a, &same_bay), 4.0 + 30.0);
    assert_eq!(o.distance(&a, &other_bay), 20.0 + 60.0 + 10.0);
    assert_eq!(o.distance(&a, &other_side), 20.0 + 60.0 + 8.0 + 10.0);
    assert_eq!(o.distance(&a, &far), 20.0 + 200.0 + 60.0 + 30.0 + 15.0);
    for (x, y) in [(a, far), (other_side, a), (same_bay, far)] {
        assert_eq!(o.distance(&x, &y), o.distance(&y, &x));
    }
    assert_eq!(o.minutes(150.0), 5.0);
}

// ------------------------------------------------------------------ the optimiser

#[test]
fn the_optimiser_repeats_and_beats_the_plain_plan() {
    let shop = toy();
    let mut cfg = quick(Config::gigafab());
    cfg.phase_rules = vec![("Etch".into(), 1)];
    let p = Problem::new(&shop, &toy_areas(), &cfg).unwrap();
    let (a, b) = (p.optimise(), p.optimise());
    assert_eq!(a, b, "same seed, same plan");
    let plain = p.cost(&p.pack(&p.plain()));
    let best = p.cost(&p.pack(&a));
    assert!(best <= plain + 1e-9, "optimised {best} above plain {plain}");
    // a plan is a permutation: every placed group once
    let mut seen: Vec<usize> = a.phases.iter().flat_map(|ph| ph.iter().flat_map(|side| side.iter().flat_map(|bl| bl.groups.clone()))).collect();
    seen.sort();
    let want: Vec<usize> = (0..shop.groups.len()).filter(|&g| p.phase_of(g).is_some()).collect();
    assert_eq!(seen, want);
    assert!(p.crossings() > 0.0, "Etch sits in phase 2, so lots cross");
}

#[test]
fn smt2020_optimised_below_plain() {
    let Some(dir) = common::smt2020_dir() else { return };
    let shop = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let cfg = quick(Config::gigafab());
    let p = Problem::new(&shop, &areas, &cfg).unwrap();
    let plan = p.optimise();
    let c = p.pack(&plan);
    check_campus(&shop, &p, &c, &cfg);
    assert!(p.cost(&c) < p.cost(&p.pack(&p.plain())));
    for ph in 0..2 {
        let (n, s) = (c.sides[ph][0], c.sides[ph][1]);
        assert!((n - s).abs() <= cfg.balance + 1e-9, "phase {ph}: north {n} south {s}");
    }
}

#[test]
fn the_export_says_what_it_is() {
    let shop = toy();
    let cfg = quick(Config::gigafab());
    let p = Problem::new(&shop, &toy_areas(), &cfg).unwrap();
    let (plain, best) = (p.pack(&p.plain()), p.pack(&p.optimise()));
    let j = p.to_json(&[("plain", &plain), ("optimised", &best)]);
    for k in ["\"model\":\"SMT2020\"", "our own design", "\"assumed\":", "\"plans\":", "\"tools\":", "\"bays\":", "\"places\":", "\"flows\":", "\"metres_per_day\":", "\"optimised\"", "\"plain\""] {
        assert!(j.contains(k), "{k} missing");
    }
    assert!(!j.contains("TSMC"));
}

// ------------------------------------------------------------------ the engine

fn with_oht(shop: &Shop, o: Oht) -> Shop {
    let mut s = shop.clone();
    s.oht = Some(o);
    s
}

fn flat(shop: &Shop, overhead: f64, jitter: f64) -> Oht {
    let p = Place { phase: 0, side: 0, bay: 0, x: 0.0, y: 0.0 };
    Oht {
        overhead,
        speed: 150.0,
        jitter,
        bridge: 60.0,
        spine: 8.0,
        lengths: vec![100.0],
        start: p,
        places: shop.groups.iter().map(|g| (g.name.clone(), Some(p))).collect(),
    }
}

#[test]
fn the_oht_record_round_trips() {
    let shop = toy();
    assert!(!shop.to_text().contains("oht"), "no record without a layout");
    let mut o = flat(&shop, 4.0, 1.0);
    o.places[2].1 = None;
    o.places[1].1 = Some(Place { phase: 0, side: 1, bay: 4, x: 37.25, y: 12.5 });
    let s = with_oht(&shop, o);
    assert_eq!(Shop::parse(&s.to_text()).unwrap(), s);
}

#[test]
fn a_layout_at_one_point_is_smt2020_transport() {
    // toy transport is 5 to 10 minutes: overhead 7.5, jitter 2.5 and zero distance draw the same
    let shop = toy();
    let o = RunOptions { seed: 7, until: Some(4320.0), record: true };
    let a = run(&shop, &o, None);
    let b = run(&with_oht(&shop, flat(&shop, 7.5, 2.5)), &o, None);
    assert_eq!(a.log_text(), b.log_text());
    assert_eq!(a.transports, b.transports);
    assert!(a.transports > 0);
    let mean = a.transport_minutes / a.transports as f64;
    assert!((5.0..=10.0).contains(&mean), "{mean}");
}

#[test]
fn distance_slows_the_moves() {
    let shop = toy();
    let o = RunOptions { seed: 3, until: Some(4320.0), record: false };
    let near = with_oht(&shop, flat(&shop, 4.0, 0.0));
    let mut far_o = flat(&shop, 4.0, 0.0);
    // every group in its own bay, 300 m apart along the spine, 30 m deep
    for (i, p) in far_o.places.iter_mut().enumerate() {
        p.1 = Some(Place { phase: 0, side: 0, bay: i, x: 300.0 * i as f64, y: 30.0 });
    }
    far_o.lengths = vec![300.0 * shop.groups.len() as f64];
    let far = with_oht(&shop, far_o);
    let (a, b) = (run(&near, &o, None), run(&far, &o, None));
    assert!((a.transport_minutes / a.transports as f64 - 4.0).abs() < 1e-9, "zero distance and no jitter: overhead only");
    let mb = b.transport_minutes / b.transports as f64;
    assert!(mb > 4.0 + 60.0 / 150.0, "{mb}");
    assert_eq!(run(&far, &o, None).log_text(), b.log_text(), "repeats");
}

#[test]
fn probes_carry_transport() {
    let shop = fabsim::window::with_probes(&toy(), &fabsim::window::Window { from: 1440.0, to: 2880.0 });
    let r = run(&with_oht(&shop, flat(&shop, 4.0, 0.0)), &RunOptions { seed: 1, until: Some(2880.0), record: false }, None);
    let (a, b) = (&r.probes[0], &r.probes[1]);
    assert!(b.transports > a.transports);
    assert!(((b.transport_minutes - a.transport_minutes) - 4.0 * (b.transports - a.transports) as f64).abs() < 1e-6);
}

#[test]
fn the_campus_drives_the_engine() {
    let shop = toy();
    let cfg = quick(Config::gigafab());
    let p = Problem::new(&shop, &toy_areas(), &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let s = with_oht(&shop, p.oht(&c));
    assert_eq!(Shop::parse(&s.to_text()).unwrap(), s);
    let r = run(&s, &RunOptions { seed: 2, until: Some(4320.0), record: false }, None);
    assert!(r.transports > 0 && r.transport_minutes > 0.0);
}

// ------------------------------------------------------------------ the export for the 3D views

#[test]
fn world_coordinates_put_phases_end_to_end() {
    let shop = toy();
    let mut cfg = quick(Config::gigafab());
    cfg.phase_rules = vec![("Etch".into(), 1)];
    let p = Problem::new(&shop, &toy_areas(), &cfg).unwrap();
    let c = p.pack(&p.plain());
    let off = p.offsets(&c);
    assert_eq!(off, vec![0.0, c.lengths[0] + cfg.bridge]);
    // north is +y past half the spine, south is -y
    assert_eq!(p.world(&c, 1, 0, 10.0, 5.0), (off[1] + 10.0, cfg.spine / 2.0 + 5.0));
    assert_eq!(p.world(&c, 0, 1, 10.0, 5.0), (10.0, -(cfg.spine / 2.0 + 5.0)));
}

#[test]
fn the_trace_export_follows_the_run() {
    let shop = toy();
    let cfg = quick(Config::gigafab());
    let p = Problem::new(&shop, &toy_areas(), &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let s = with_oht(&shop, p.oht(&c));
    let r = run(&s, &RunOptions { seed: 2, until: Some(3000.0), record: true }, None);
    let (from, to) = (600.0, 1800.0);
    let lots = p.trace(&c, &r, from, to);
    let want = r.trace.iter().filter(|t| t.end >= from && t.arrive <= to).count();
    assert_eq!(lots.iter().map(|l| l.steps.len()).sum::<usize>(), want);
    assert!(want > 0);
    for l in &lots {
        assert!(l.steps.windows(2).all(|w| w[0].start <= w[1].start), "{} out of order", l.id);
        for st in &l.steps {
            assert!(st.arrive <= st.start && st.start <= st.end);
            match st.tool {
                Some(t) => assert_eq!(c.tools[t].group, st.group),
                None => assert_eq!(p.phase_of(st.group), None),
            }
        }
        if let Some((t, _)) = l.prev {
            assert!(t <= l.steps[0].arrive);
        }
    }
    let j = p.trace_json(&c, &r, from, to);
    for k in ["\"from\":600", "\"to\":1800", "\"offsets\":", "\"lots\":", "\"states\":", "on the SMT2020 model"] {
        assert!(j.contains(k), "{k} missing");
    }
}
