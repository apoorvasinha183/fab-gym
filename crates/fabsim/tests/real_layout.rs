//! The realistic campus (docs/FAB-LOOK.md): tools at true size by kind, and each tool group in
//! the phase that sends it most of its lots. A gigafab-style layout of our own design on the
//! SMT2020 model. Today's `Config::gigafab()` stays as it was.

mod common;

use fabsim::layout::{Campus, Config, Problem, START};
use fabsim::shop::Shop;

fn quick(mut c: Config) -> Config {
    c.iters = 3000;
    c.restarts = 2;
    c
}

fn smt() -> Option<(Shop, Vec<(String, String)>)> {
    let dir = common::smt2020_dir()?;
    Some((fabsim::smt2020::load(&dir).unwrap(), fabsim::smt2020::areas(&dir).unwrap()))
}

/// The phase a group's name gives it: back end by name goes to phase 1.
fn name_phase(name: &str) -> usize {
    usize::from(name.contains("_BE_"))
}

#[test]
fn todays_config_is_unchanged() {
    let c = Config::gigafab();
    assert!(c.kinds.is_empty(), "the gigafab config has no tool kinds");
    assert!(!c.phase_by_flow, "the gigafab config places groups by name");
}

#[test]
fn the_realistic_config_names_its_kinds() {
    let c = Config::realistic();
    assert!(c.phase_by_flow);
    let want = [
        ("LithoMet_BE_18", "metrology"),
        ("Litho_REG_FE_64", "metrology"),
        ("TF_Met_FE_45", "metrology"),
        ("LithoTrack_FE_95", "track"),
        ("Litho_BE_110", "scanner"),
        ("DefMet_FE_43", "inspection"),
        ("DefMEt_FE_118", "inspection"),
        ("DE_FE_86", "etch"),
        ("Dielectric_BE_27", "deposition"),
        ("TF_BE_40", "deposition"),
        ("EPI_36", "epitaxy"),
        ("Diffusion_FE_44", "furnace"),
        ("Implant_128", "implanter"),
        ("Planar_FE_79", "polisher"),
        ("WE_BE_9", "wet_bench"),
        ("Delay_32", "stocker"),
    ];
    for (g, k) in want {
        assert_eq!(c.kind_of(g).map(|k| k.name.as_str()), Some(k), "{g}");
    }
    // the size book's footprints (viz/look/sizes.json): W along the wall, D into the bay
    let fp = |k: &str| {
        let k = c.kinds.iter().find(|x| x.name == k).unwrap();
        (k.w, k.d)
    };
    assert_eq!(fp("scanner"), (4.5, 11.0));
    assert_eq!(fp("track"), (3.5, 7.0));
    assert_eq!(fp("furnace"), (1.5, 2.0));
    assert_eq!(fp("implanter"), (3.6, 8.1));
    assert_eq!(fp("wet_bench"), (2.5, 10.0));
}

#[test]
fn every_smt2020_group_has_a_kind() {
    let Some((shop, _)) = smt() else { return };
    let c = Config::realistic();
    for g in &shop.groups {
        assert!(c.kind_of(&g.name).is_some(), "{} has no kind", g.name);
    }
}

#[test]
fn groups_go_where_their_lots_come_from() {
    // a fixed point: every group sits in the phase that sends it most of its lots, given where
    // every other group sits (docs/FAB-LOOK.md, "Changes")
    let Some((shop, areas)) = smt() else { return };
    let p = Problem::new(&shop, &areas, &Config::realistic()).unwrap();
    let idx = |n: &str| shop.groups.iter().position(|g| g.name == n).unwrap();
    assert_eq!(p.phase_of(idx("LithoTrack_FE_95")), Some(1), "78% of its lots are back-end");
    assert_eq!(p.phase_of(idx("Litho_BE_110")), Some(1), "the scanners it feeds stay in phase 2");
    assert_eq!(p.phase_of(idx("Delay_32")), None);
    for (gi, g) in shop.groups.iter().enumerate() {
        let Some(ph) = p.phase_of(gi) else { continue };
        let mut inflow = [0.0f64; 2];
        for f in p.flows().iter().filter(|f| f.1 == gi) {
            let from = if f.0 == START { 0 } else { p.phase_of(f.0).unwrap() };
            inflow[from] += f.2;
        }
        assert!(inflow[ph] >= inflow[1 - ph], "{}: lots in from phase 1 {:.1}, phase 2 {:.1}", g.name, inflow[0], inflow[1]);
    }
    let by_name = Problem::new(&shop, &areas, &Config::gigafab()).unwrap();
    assert!(p.crossings() < by_name.crossings(), "fewer lots cross the bridge: {} against {}", p.crossings(), by_name.crossings());
    let moved: Vec<&str> = shop.groups.iter().enumerate().filter(|(i, g)| p.phase_of(*i).is_some() && p.phase_of(*i) != Some(name_phase(&g.name))).map(|(_, g)| g.name.as_str()).collect();
    assert!(moved.len() <= 10, "only a few groups move: {moved:?}");
}

fn check_true_size(shop: &Shop, p: &Problem, c: &Campus, cfg: &Config) {
    for (gi, g) in shop.groups.iter().enumerate() {
        let n = c.tools.iter().filter(|t| t.group == gi).count();
        match p.phase_of(gi) {
            None => assert_eq!(n, 0, "{} is a stocker", g.name),
            Some(ph) => {
                assert_eq!(n, g.count, "{}", g.name);
                assert_eq!(c.places[gi].expect("a place").phase, ph);
            }
        }
    }
    for t in &c.tools {
        let k = cfg.kind_of(&shop.groups[t.group].name).unwrap();
        // x runs across the bay (depth into it), y along the wall
        assert!(((t.x1 - t.x0) - k.d).abs() < 1e-9 && ((t.y1 - t.y0) - k.w).abs() < 1e-9, "{} drawn at its true size", shop.groups[t.group].name);
        let b = &c.bays[t.bay];
        assert_eq!((b.phase, b.side), (t.phase, t.side));
        assert_eq!(b.area, p.area_of(t.group));
        assert!(t.x0 >= b.x0 + cfg.chase - 1e-9 && t.x1 <= b.x1 - cfg.chase + 1e-9, "tool outside its walls");
        assert!(t.y0 >= -1e-9 && t.y1 <= cfg.bay_depth + 1e-9, "tool beyond the bay's depth");
        // every tool's front lines the aisle, under the hoist rail, with the chase behind it
        let (a0, a1) = ((b.x0 + b.x1 - cfg.bay_aisle) / 2.0, (b.x0 + b.x1 + cfg.bay_aisle) / 2.0);
        assert!((t.x1 - a0).abs() < 1e-9 || (t.x0 - a1).abs() < 1e-9, "{} front off the aisle line", shop.groups[t.group].name);
    }
    // each bay is wide enough for its deepest tool on both walls, with the aisle between
    for (bi, b) in c.bays.iter().enumerate() {
        let deepest = c.tools.iter().filter(|t| t.bay == bi).map(|t| t.x1 - t.x0).fold(0.0, f64::max);
        assert!(b.x1 - b.x0 + 1e-9 >= 2.0 * (deepest + cfg.chase) + cfg.bay_aisle, "bay {bi} too narrow");
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
fn smt2020_packs_at_true_size() {
    let Some((shop, areas)) = smt() else { return };
    let cfg = quick(Config::realistic());
    let p = Problem::new(&shop, &areas, &cfg).unwrap();
    let plain = p.pack(&p.plain());
    check_true_size(&shop, &p, &plain, &cfg);
    let plan = p.optimise();
    assert_eq!(plan, p.optimise(), "same seed, same plan");
    let best = p.pack(&plan);
    check_true_size(&shop, &p, &best, &cfg);
    assert!(p.cost(&best) < p.cost(&plain), "the optimiser beats the plain plan at true size");
    for ph in 0..best.sides.len() {
        let (n, s) = (best.sides[ph][0], best.sides[ph][1]);
        assert!((n - s).abs() <= cfg.balance + 1e-9, "phase {ph}: north {n} south {s}");
    }
}

#[test]
fn the_realistic_export_carries_its_kinds() {
    let Some((shop, areas)) = smt() else { return };
    let cfg = quick(Config::realistic());
    let p = Problem::new(&shop, &areas, &cfg).unwrap();
    let c = p.pack(&p.plain());
    let j = p.to_json(&[("plain", &c)]);
    for k in ["\"kinds\":", "\"scanner\"", "\"phase_rule\":\"where its lots come from\"", "our own design"] {
        assert!(j.contains(k), "{k} missing");
    }
    assert!(!j.contains("TSMC"));
}
