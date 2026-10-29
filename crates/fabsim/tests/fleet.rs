//! The faithful floor, rungs L2 to L4 (docs/FLEET.md): a one-way track, a finite fleet and traffic, opt in by a
//! `fleet` record. Written before the code. On the SMT2020 model with a gigafab-style layout of our own design; every
//! fleet number is assumed.

mod common;

use fabsim::engine::{run, run_vehicles, RunOptions, VehicleAsk};
use fabsim::shop::{Fleet, Shop};
use fabsim::track::Track;
use std::collections::HashMap;

const DAY: f64 = 1440.0;

/// Today's realistic campus with its layout (fabsim layout --real), if it has been built.
fn campus() -> Option<Shop> {
    let p = common::repo().join("data/layout-real/optimised.shop.txt");
    let text = std::fs::read_to_string(&p).ok()?;
    Some(Shop::parse(&text).unwrap())
}

fn fleet(vehicles: usize, ports: usize) -> Fleet {
    Fleet { vehicles, gap: 3.0, hoist: 0.3, ports, cross: 60.0, controller: "nearest".into() }
}

fn with(mut s: Shop, f: Fleet) -> Shop {
    s.fleet = Some(f);
    s
}

fn go(s: &Shop, seed: u64, days: f64, record: bool) -> fabsim::engine::RunResult {
    run(s, &RunOptions { seed, until: Some(days * DAY), record }, None)
}

#[test]
fn the_track_reaches_every_stop_from_every_stop() {
    let Some(s) = campus() else { return };
    let o = s.oht.as_ref().unwrap();
    let t = Track::new(o, 60.0);
    assert!(t.edges().iter().all(|e| e.len > 0.0), "every stretch is longer than zero");
    let stops: Vec<usize> = o.places.iter().filter(|p| p.1.is_some()).map(|p| t.stop_of(&p.0).expect("a stop for every placed group")).collect();
    for &a in &stops {
        for &b in &stops {
            assert!(t.dist(a, b).is_finite(), "stop {a} reaches stop {b}");
        }
    }
}

#[test]
fn no_trip_on_the_track_beats_the_aisles() {
    let Some(s) = campus() else { return };
    let o = s.oht.as_ref().unwrap();
    let t = Track::new(o, 60.0);
    let placed: Vec<(&str, fabsim::shop::Place)> = o.places.iter().filter_map(|(g, p)| p.map(|p| (g.as_str(), p))).collect();
    for (ga, pa) in &placed {
        for (gb, pb) in &placed {
            let track = t.dist(t.stop_of(ga).unwrap(), t.stop_of(gb).unwrap());
            assert!(track + 1e-6 >= o.distance(pa, pb), "{ga} to {gb}: track {track} against aisles {}", o.distance(pa, pb));
        }
    }
}

#[test]
fn the_track_is_one_way() {
    let Some(s) = campus() else { return };
    let o = s.oht.as_ref().unwrap();
    let t = Track::new(o, 60.0);
    let stops: Vec<usize> = o.places.iter().filter(|p| p.1.is_some()).map(|p| t.stop_of(&p.0).unwrap()).collect();
    let back = stops.iter().flat_map(|&a| stops.iter().map(move |&b| (a, b))).any(|(a, b)| t.dist(b, a) > t.dist(a, b) + 20.0);
    assert!(back, "some trips back to a stop just passed go round the loop");
}

#[test]
fn the_fleet_record_reads_and_writes_back() {
    let Some(s) = campus() else { return };
    let text = s.to_text();
    assert!(!text.contains("\nfleet\t"), "a shop without a fleet writes no fleet line");
    let f = with(s, fleet(80, 2));
    let back = Shop::parse(&f.to_text()).unwrap();
    assert_eq!(back.fleet, f.fleet);
    assert_eq!(back.to_text(), f.to_text());
    let mut no_oht = f.clone();
    no_oht.oht = None;
    assert!(Shop::parse(&no_oht.to_text()).is_err(), "a fleet needs a layout");
}

#[test]
fn every_move_asked_for_is_delivered_or_under_way() {
    let Some(s) = campus() else { return };
    let r = go(&with(s, fleet(80, 2)), 0, 2.0, false);
    let f = r.fleet.as_ref().expect("fleet results");
    assert!(f.asked > 1000, "{} moves asked for in two days", f.asked);
    assert_eq!(f.asked, f.delivered + f.open);
    assert_eq!(r.transports, f.delivered, "a move counts when it is delivered");
}

#[test]
fn vehicles_never_pass_one_another() {
    let Some(s) = campus() else { return };
    let sh = with(s, fleet(60, 2));
    let o = sh.oht.as_ref().unwrap();
    let t = Track::new(o, 60.0);
    let r = go(&sh, 1, 1.0, true);
    let f = r.fleet.as_ref().unwrap();
    assert!(!f.entries.is_empty());
    let headway = 3.0 / o.speed;
    let mut by_edge: HashMap<usize, Vec<(f64, f64)>> = HashMap::new();
    for e in &f.entries {
        by_edge.entry(e.edge).or_default().push((e.t_in, e.t_out));
    }
    for (edge, v) in &by_edge {
        let cap = ((t.edges()[*edge].len / 3.0).floor() as usize).max(1);
        // entries are kept in the order vehicles entered
        for w in v.windows(2) {
            assert!(w[1].0 + 1e-9 >= w[0].0 + headway, "edge {edge}: entered {} after {}", w[1].0, w[0].0);
            if w[0].1.is_finite() && w[1].1.is_finite() {
                assert!(w[1].1 + 1e-9 >= w[0].1, "edge {edge}: left out of order");
            }
        }
        let mut ev: Vec<(f64, i32)> = v.iter().flat_map(|&(a, b)| [(a, 1), (if b.is_finite() { b } else { f64::INFINITY }, -1)]).collect();
        ev.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
        let mut n = 0;
        for (_, d) in ev {
            n += d;
            assert!(n as usize <= cap, "edge {edge} holds {cap}, had {n}");
        }
    }
}

#[test]
fn a_stop_holds_one_hoist_at_a_time() {
    let Some(s) = campus() else { return };
    let r = go(&with(s, fleet(60, 2)), 1, 1.0, true);
    let f = r.fleet.as_ref().unwrap();
    let mut by_stop: HashMap<usize, Vec<(f64, f64)>> = HashMap::new();
    for h in &f.hoists {
        by_stop.entry(h.stop).or_default().push((h.t0, h.t1));
    }
    for (stop, mut v) in by_stop {
        v.sort_by(|a, b| a.0.total_cmp(&b.0));
        for w in v.windows(2) {
            assert!(w[1].0 + 1e-9 >= w[0].1, "stop {stop}: hoists overlap");
        }
    }
}

#[test]
fn fewer_vehicles_wait_longer() {
    let Some(s) = campus() else { return };
    let mean = |n: usize| -> f64 {
        let sh = with(s.clone(), fleet(n, 2));
        let (mut sum, mut cnt) = (0.0, 0u64);
        for seed in 0..3 {
            let f = go(&sh, seed, 2.0, false).fleet.unwrap();
            sum += f.wait_sum;
            cnt += f.wait_n;
        }
        sum / cnt as f64
    };
    let (few, many) = (mean(30), mean(150));
    assert!(few > many, "30 vehicles wait {few} min on average, 150 wait {many}");
}

#[test]
fn full_ports_block_tools() {
    let Some(s) = campus() else { return };
    let tight = go(&with(s.clone(), fleet(20, 1)), 0, 2.0, false).fleet.unwrap().blocked_min;
    let loose = go(&with(s, fleet(200, 4)), 0, 2.0, false).fleet.unwrap().blocked_min;
    assert!(tight > 0.0, "one port and 20 vehicles block some tool");
    assert!(loose < tight, "four ports and 200 vehicles block less: {loose} against {tight}");
}

#[test]
fn the_same_seed_gives_the_same_run() {
    let Some(s) = campus() else { return };
    let sh = with(s, fleet(60, 2));
    let a = go(&sh, 5, 1.0, false);
    let b = go(&sh, 5, 1.0, false);
    assert_eq!(a.fleet, b.fleet);
    assert_eq!(a.log_text(), b.log_text());
}

#[test]
fn the_vehicle_controller_is_asked_and_obeyed() {
    let Some(s) = campus() else { return };
    let sh = with(s, fleet(60, 2));
    let opts = RunOptions { seed: 2, until: Some(DAY), record: false };
    let mut asked = 0u64;
    let mut last = |a: &VehicleAsk| -> usize {
        asked += 1;
        assert!(!a.idle.is_empty());
        a.idle.len() - 1
    };
    let r = run_vehicles(&sh, &opts, None, Some(&mut last));
    let f = r.fleet.unwrap();
    assert_eq!(f.picks, asked);
    assert_eq!(f.refused, 0);
    let near = run(&sh, &opts, None).fleet.unwrap();
    assert_ne!(f.empty_m, near.empty_m, "a different controller drives differently");
    let mut bad = |_: &VehicleAsk| -> usize { usize::MAX };
    let r = run_vehicles(&sh, &opts, None, Some(&mut bad)).fleet.unwrap();
    assert_eq!(r.refused, r.picks, "every pick that is not an idle vehicle is refused");
    assert_eq!(r.empty_m, near.empty_m, "refused picks fall back to nearest");
}

#[test]
fn a_delivery_takes_at_least_the_two_hoists() {
    let Some(s) = campus() else { return };
    let f = go(&with(s, fleet(80, 2)), 0, 1.0, false).fleet.unwrap();
    assert!(f.deliver_least + 1e-9 >= 2.0 * 0.3, "shortest delivery {}", f.deliver_least);
}

// ---- every tool its own port (docs/FLEET.md, changes after the first probe) ----

/// The realistic campus laid out here (a quick optimiser), with one port per tool.
fn campus_with_ports() -> Option<Shop> {
    use fabsim::layout::{Config, Problem};
    let dir = common::smt2020_dir()?;
    let base = fabsim::smt2020::load(&dir).unwrap();
    let areas = fabsim::smt2020::areas(&dir).unwrap();
    let mut cfg = Config::realistic();
    cfg.iters = 3000;
    cfg.restarts = 1;
    let p = Problem::new(&base, &areas, &cfg).unwrap();
    let c = p.pack(&p.optimise());
    let mut s = base;
    s.oht = Some(p.oht(&c));
    s.ports = p.ports(&c);
    Some(s)
}

#[test]
fn every_tool_has_a_port_on_the_track() {
    let Some(s) = campus_with_ports() else { return };
    let t = Track::with_ports(s.oht.as_ref().unwrap(), &s.ports, 60.0);
    for g in &s.groups {
        let n = s.ports.iter().filter(|p| p.0 == g.name).count();
        let placed = s.oht.as_ref().unwrap().places.iter().any(|p| p.0 == g.name && p.1.is_some());
        assert_eq!(n, if placed { g.count } else { 0 }, "{}: one port per tool", g.name);
        assert_eq!(t.ports_of(&g.name).len(), n);
    }
    let all: Vec<usize> = s.groups.iter().flat_map(|g| t.ports_of(&g.name).to_vec()).collect();
    let o = s.oht.as_ref().unwrap();
    for (i, &a) in all.iter().enumerate().step_by(7) {
        for &b in all.iter().skip(i % 5).step_by(11) {
            let d = t.dist(a, b);
            assert!(d.is_finite());
            assert!(d + 1e-6 >= o.distance(&t.place(a), &t.place(b)), "no trip between ports beats the aisles");
        }
    }
}

#[test]
fn the_port_record_reads_and_writes_back() {
    let Some(s) = campus_with_ports() else { return };
    let back = Shop::parse(&s.to_text()).unwrap();
    assert_eq!(back.ports, s.ports);
    let mut none = s.clone();
    none.ports.clear();
    assert!(!none.to_text().contains("\nport\t"));
}

#[test]
fn lots_are_hoisted_at_tool_ports_and_stocker_spurs_only() {
    let Some(s) = campus_with_ports() else { return };
    let sh = with(s, fleet(250, 2));
    let t = Track::with_ports(sh.oht.as_ref().unwrap(), &sh.ports, 60.0);
    let r = go(&sh, 0, 1.0, true);
    let f = r.fleet.unwrap();
    let mut stops = std::collections::BTreeSet::new();
    for h in &f.hoists {
        let n = &t.nodes()[h.stop];
        assert!(n.tool.is_some() || n.spur, "a hoist at node {} on the open rail", h.stop);
        stops.insert(h.stop);
    }
    assert!(stops.len() > 300, "hoists spread over the tools' ports: {} stops used", stops.len());
}
