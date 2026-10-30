//! Uncertainty layer 4 (docs/UQ-INPUTS.md): the published input numbers redrawn. Written before the code.
//! On the SMT2020 model's rules, with a hand-made shop for speed.

use fabsim::inputs::{factors, perturb, Factors};
use fabsim::shop::Shop;

const SHOP: &str = "fabgym-shop 1
transport\t5.0\t10.0
group\tA\t2\t1.0\t1.0\t-\t900.0\t100.0
group\tB\t1\t0.5\t0.5\t-\t-\t-
route\tr
step\tA\tlot\t50.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t20.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tA\tlot\t30.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t12.0\t0.0\t-\tN
";

fn shop() -> Shop {
    let mut s = Shop::parse(SHOP).unwrap();
    // a maintenance calendar on A, to see its length scaled and its interval kept
    s.groups[0].pm.push(fabsim::shop::Pm { every: 10_000.0, lo: 120.0, hi: 180.0, first: None });
    s
}

#[test]
fn no_doubt_is_the_published_shop() {
    let s = shop();
    assert_eq!(perturb(&s, 3, 0.0), s);
}

#[test]
fn a_draw_is_repeatable_and_draws_differ() {
    let s = shop();
    assert_eq!(perturb(&s, 4, 0.2), perturb(&s, 4, 0.2));
    assert_ne!(perturb(&s, 4, 0.2), perturb(&s, 5, 0.2));
}

#[test]
fn only_the_four_kinds_of_number_change_and_by_the_groups_factor() {
    let s = shop();
    let p = perturb(&s, 7, 0.2);
    let f: Vec<Factors> = factors(&s, 7, 0.2);
    assert_eq!(f.len(), s.groups.len());
    for (g, (a, b)) in s.groups.iter().zip(&p.groups).enumerate() {
        assert_eq!((a.name.as_str(), a.count, a.load, a.unload), (b.name.as_str(), b.count, b.load, b.unload));
        assert_eq!(a.setups, b.setups);
        match (a.breakdown, b.breakdown) {
            (Some((ttf, ttr)), Some((ttf2, ttr2))) => {
                assert!((ttf2 - ttf * f[g].ttf).abs() < 1e-9 && (ttr2 - ttr * f[g].ttr).abs() < 1e-9);
            }
            (None, None) => {}
            _ => panic!("a breakdown appeared or vanished"),
        }
        for (x, y) in a.pm.iter().zip(&b.pm) {
            assert_eq!(x.every, y.every, "maintenance comes as often");
            assert!((y.lo - x.lo * f[g].pm).abs() < 1e-9 && (y.hi - x.hi * f[g].pm).abs() < 1e-9);
        }
    }
    for (ra, rb) in s.routes.iter().zip(&p.routes) {
        assert_eq!(ra.steps.len(), rb.steps.len());
        for (x, y) in ra.steps.iter().zip(&rb.steps) {
            let g = s.groups.iter().position(|gr| gr.name == x.group).unwrap();
            assert!((y.time - x.time * f[g].proc).abs() < 1e-9, "every step at a group scales by its factor");
            assert_eq!((x.per, x.batch, x.setup.clone(), x.sample, x.rework, x.cqt), (y.per, y.batch, y.setup.clone(), y.sample, y.rework, y.cqt));
        }
    }
    assert_eq!(s.releases, p.releases);
}

#[test]
fn factors_average_one_and_spread_by_sigma() {
    let s = shop();
    let n = 4000;
    let logs: Vec<f64> = (0..n).map(|d| factors(&s, d, 0.2)[0].proc.ln()).collect();
    let mean_f = logs.iter().map(|l| l.exp()).sum::<f64>() / n as f64;
    let m = logs.iter().sum::<f64>() / n as f64;
    let sd = (logs.iter().map(|l| (l - m) * (l - m)).sum::<f64>() / (n - 1) as f64).sqrt();
    assert!((mean_f - 1.0).abs() < 0.015, "mean factor {mean_f}");
    assert!((sd - 0.2).abs() < 0.01, "log spread {sd}");
    assert!(logs.iter().all(|l| l.is_finite()));
}

#[test]
fn equal_load_keeps_the_published_release_to_ceiling_ratio() {
    use fabsim::bound::capacity;
    use fabsim::inputs::equal_load;
    let s = shop();
    let c0 = capacity(&s);
    let ratio0 = c0.released_per_day / c0.wafers_per_day;
    for d in 1..6 {
        let e = equal_load(&s, d, 0.2);
        let c = capacity(&e);
        assert!((c.released_per_day / c.wafers_per_day - ratio0).abs() < 1e-9, "draw {d}");
        // the same factors as the plain redraw; only releases differ
        let p = perturb(&s, d, 0.2);
        assert_eq!(e.groups, p.groups);
        assert_eq!(e.routes, p.routes);
    }
    assert_eq!(equal_load(&s, 3, 0.0), s);
}
