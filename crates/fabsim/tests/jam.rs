//! The track cannot jam below a count of cars (docs/DOUBLE-CHECK.md, part 2). Written before the code. Cars block each
//! other only while moving: a stretch holds floor(length / gap) cars (at least one), a stop or junction one while it
//! passes, and idle cars park off the track. Cars that wait on each other for ever need a loop whose every piece is
//! full, so fewer cars than the smallest loop holds can never jam. On a teaching fab of our own; not a real fab.

use fabsim::checks::{check, Severity};
use fabsim::jam::{explore, smallest_loop, smallest_loop_of, Small};
use fabsim::shop::Shop;
use fabsim::track::Track;

fn teach() -> Shop {
    Shop::parse(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/teach-free.fab.txt")).unwrap()).unwrap()
}

/// A loop's cars: each stretch's cars plus one for the stop at its end.
fn ring(n: usize, caps: &[usize]) -> Small {
    Small { nodes: n, links: (0..n).map(|i| (i, (i + 1) % n, caps[i % caps.len()])).collect() }
}

#[test]
fn dc4_the_smallest_loop_and_its_number() {
    // a figure eight through node 0: 0>1>2>0 with stretches of 1 car, 0>3>4>0 with stretches of 2
    let g = Small { nodes: 5, links: vec![(0, 1, 1), (1, 2, 1), (2, 0, 1), (0, 3, 2), (3, 4, 2), (4, 0, 2)] };
    let (nodes, cars) = smallest_loop_of(&g).expect("a loop");
    assert_eq!(cars, 6, "three stretches of one car and three stops");
    let mut sorted = nodes.clone();
    sorted.sort();
    assert_eq!(sorted, vec![0, 1, 2]);
    assert!(smallest_loop_of(&Small { nodes: 3, links: vec![(0, 1, 1), (1, 2, 1)] }).is_none(), "a line has no loop");

    // the teaching fab's own track: the loop found is a loop of its stretches, and its number adds up
    let shop = teach();
    let gap = shop.fleet.as_ref().unwrap().gap;
    let tr = Track::from_shop(&shop);
    let l = smallest_loop(&tr, gap).expect("the teaching fab's track has a loop");
    assert!(l.nodes.len() >= 2);
    let mut want = 0;
    for i in 0..l.nodes.len() {
        let (a, b) = (l.nodes[i], l.nodes[(i + 1) % l.nodes.len()]);
        let e = tr.edges().iter().find(|e| e.from == a && e.to == b).unwrap_or_else(|| panic!("no stretch {a}>{b}"));
        want += ((e.len / gap).floor() as usize).max(1) + 1;
    }
    assert_eq!(l.cars, want, "the loop's number is its stretches' cars plus its stops");
    assert_eq!(l.names.len(), l.nodes.len(), "each stop on it is named");
}

#[test]
fn dc5_no_jam_below_the_number_on_any_small_track_and_one_at_it_on_a_ring() {
    let tracks = vec![
        ("a ring of three", ring(3, &[1])),
        ("a ring of four with a long stretch", ring(4, &[1, 2])),
        ("a figure eight", Small { nodes: 5, links: vec![(0, 1, 1), (1, 2, 1), (2, 0, 1), (0, 3, 1), (3, 4, 2), (4, 0, 1)] }),
        ("a loop with a shortcut", Small { nodes: 4, links: vec![(0, 1, 1), (1, 2, 2), (2, 3, 1), (3, 0, 1), (1, 3, 1)] }),
        ("two loops joined both ways", Small { nodes: 5, links: vec![(0, 1, 1), (1, 0, 1), (1, 2, 1), (2, 3, 1), (3, 4, 1), (4, 2, 1), (2, 1, 1)] }),
    ];
    for (name, g) in &tracks {
        let (_, m) = smallest_loop_of(g).unwrap();
        for cars in 1..m {
            let x = explore(g, cars);
            assert!(x.states > 0, "{name}, {cars} cars: states were tried");
            assert_eq!(x.jams, 0, "{name}: {cars} cars, below the smallest loop's {m}, never jam ({} placements tried)", x.states);
        }
    }
    for (name, g) in &tracks[..2] {
        let (_, m) = smallest_loop_of(g).unwrap();
        let x = explore(g, m);
        assert!(x.jams > 0 && x.jam_reachable, "{name}: {m} cars fill the ring and can jam");
    }
}

#[test]
fn dc6_the_warning_comes_exactly_at_the_number() {
    let mut shop = teach();
    let gap = shop.fleet.as_ref().unwrap().gap;
    let m = smallest_loop(&Track::from_shop(&shop), gap).unwrap().cars;
    let jams = |shop: &Shop| check(shop).into_iter().filter(|i| i.code == "may_jam").collect::<Vec<_>>();
    shop.fleet.as_mut().unwrap().vehicles = m - 1;
    assert!(jams(&shop).is_empty(), "{} cars, one fewer than the loop holds", m - 1);
    shop.fleet.as_mut().unwrap().vehicles = m;
    let w = jams(&shop);
    assert_eq!(w.len(), 1, "{m} cars");
    assert_eq!(w[0].severity, Severity::Warning);
    assert!(w[0].message.contains(&m.to_string()), "the message names the number: {}", w[0].message);
    assert!(!w[0].at.is_empty(), "it names the loop's stops");
}
