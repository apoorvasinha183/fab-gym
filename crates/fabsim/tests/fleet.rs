//! The faithful floor, rungs L2 to L4 (docs/FLEET.md): a one-way track, a finite fleet and traffic, opt in by a
//! `fleet` record. Written before the code. From the SMT2020 testbed with a gigafab-style layout of our own design; every
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
    // the track the engine builds from the shop
    let t = Track::from_shop(&sh);
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

// ---- the track and fleet for the viewers (the 2D page and the game) ----

#[test]
fn the_fleet_trace_holds_the_track_and_the_vehicles_in_its_window() {
    let Some(s) = campus() else { return };
    let sh = with(s, fleet(160, 2));
    let o = sh.oht.as_ref().unwrap();
    let t = Track::from_shop(&sh);
    let r = go(&sh, 3000, 1.0, true);
    let f = r.fleet.as_ref().unwrap();
    let (from, to) = (600.0, 660.0);
    let tr = fabsim::fleet::FleetTrace::new(o, &t, f, from, to);
    assert_eq!(tr.edges.len(), t.edges().len());
    assert_eq!(tr.nodes.len(), t.nodes().len());
    assert_eq!(tr.vehicles, 160);
    assert!(!tr.entries.is_empty() && !tr.hoists.is_empty());
    for e in &tr.entries {
        assert!(e.t_in <= to && e.t_out >= from, "every entry kept overlaps the window");
    }
    for h in &tr.hoists {
        assert!(h.t0 <= to && h.t1 >= from, "every hoist kept overlaps the window");
    }
    let js = tr.to_json();
    assert!(js.starts_with('{') && js.trim_end().ends_with('}'));
    assert_eq!(js.matches('[').count(), js.matches(']').count());
    assert!(js.contains("SMT2020") && js.contains("\"offsets\""));
}

// ---- the drawn rails are the true track (decided by quiz 29 Oct: the two-rail bay loop) ----

/// The realistic campus with its ports and each bay's two rails, laid out here (a quick optimiser).
fn campus_drawn() -> Option<Shop> {
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
    s.bayrails = p.bayrails(&c);
    Some(s)
}

#[test]
fn every_bay_has_a_rail_over_each_wall_and_ports_sit_under_them() {
    let Some(s) = campus_drawn() else { return };
    assert!(!s.bayrails.is_empty());
    for (g, p) in &s.ports {
        let b = s.bayrails.iter().find(|b| b.bay == p.bay).unwrap_or_else(|| panic!("{g}: a bay with rails"));
        assert!((p.x - b.x[0]).abs() < 1e-9 || (p.x - b.x[1]).abs() < 1e-9, "{g}: its port under one of its bay's two rails");
        assert!(p.y > 0.0 && p.y < b.far);
    }
    let back = Shop::parse(&s.to_text()).unwrap();
    assert_eq!(back.bayrails, s.bayrails);
}

#[test]
fn the_drawn_track_reaches_every_port_and_never_beats_the_aisles() {
    let Some(s) = campus_drawn() else { return };
    let t = Track::from_shop(&s);
    let o = s.oht.as_ref().unwrap();
    let all: Vec<usize> = s.groups.iter().flat_map(|g| t.ports_of(&g.name).to_vec()).collect();
    assert_eq!(all.len(), s.ports.len());
    for (i, &a) in all.iter().enumerate().step_by(5) {
        for &b in all.iter().skip(i % 3).step_by(9) {
            let d = t.dist(a, b);
            assert!(d.is_finite(), "port {a} reaches port {b}");
            assert!(d + 1e-6 >= o.distance(&t.place(a), &t.place(b)));
        }
    }
    // a bay loop goes in along one wall's rail and out along the other's
    let n0 = t.nodes()[all[0]];
    let same_bay: Vec<usize> = all.iter().copied().filter(|&n| t.nodes()[n].bay == n0.bay).collect();
    let xs: std::collections::BTreeSet<i64> = same_bay.iter().map(|&n| (t.nodes()[n].x * 1000.0).round() as i64).collect();
    assert!(xs.len() <= 2);
}

#[test]
fn a_fleet_runs_on_the_drawn_track() {
    let Some(s) = campus_drawn() else { return };
    let sh = with(s, fleet(160, 2));
    let t = Track::from_shop(&sh);
    let r = go(&sh, 0, 1.0, true);
    let f = r.fleet.unwrap();
    assert!(f.delivered > 10_000, "{} delivered in a day", f.delivered);
    for h in &f.hoists {
        let n = &t.nodes()[h.stop];
        assert!(n.tool.is_some() || n.stocker, "hoists at tool ports and stockers only");
    }
}

// ---- follow one lot from start to finish (docs/LIVE-REAL.md, the journey) ----

#[test]
fn one_lot_is_followed_through_its_whole_route() {
    let Some(s) = campus() else { return };
    let sh = with(s, fleet(160, 2));
    let rel = sh.releases.iter().find(|r| r.route == "part_3").expect("a release of product 3");
    let id = format!("{}.{}", rel.prefix, 3);
    let r = fabsim::engine::run_follow(&sh, &RunOptions { seed: 3000, until: Some(150.0 * DAY), record: false }, &id);
    let lot = r.lots.iter().position(|l| l.id == id).expect("the lot was released") as u32;
    assert!(r.lots[lot as usize].done.is_some(), "it finished within 150 days");
    assert!(!r.trace.is_empty() && r.trace.iter().all(|t| t.lot == lot), "only the followed lot's steps are kept");
    let steps = sh.routes.iter().find(|x| x.name == "part_3").unwrap().steps.len();
    assert!(r.trace.len() >= steps * 8 / 10 && r.trace.len() <= steps + 50, "{} of the route's {steps} steps (some are sampled)", r.trace.len());
    for w in r.trace.windows(2) {
        assert!(w[1].start >= w[0].end - 1e-9, "one step after another");
        assert!(w[1].arrive >= w[0].end - 1e-9, "it arrives after the last step ends");
    }
    let f = r.fleet.as_ref().unwrap();
    assert!(f.hoists.iter().all(|h| h.lot == lot), "only its hoists are kept");
    let ups = f.hoists.iter().filter(|h| h.up).count();
    assert!(ups >= r.trace.len() / 2, "{ups} pickups for {} steps", r.trace.len());
    assert!(!f.entries.is_empty());
}
