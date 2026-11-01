//! The track cannot jam below a count of cars (docs/DOUBLE-CHECK.md, part 2). Written before the code, and revised
//! once while writing it (see the spec's Changes): a car whose stretch is full takes another way out with room, so a jam
//! must fill a whole connected part of the track, not just one loop. Cars block each other only while moving: a stretch
//! holds floor(length / gap) cars (at least one), a stop or junction one while it passes, and idle cars park off the
//! track. On a teaching fab of our own; not a real fab.

use fabsim::checks::{check, Severity};
use fabsim::jam::{explore, jam_number, jam_number_of, smallest_loop_of, Small};
use fabsim::shop::Shop;
use fabsim::track::Track;

fn teach() -> Shop {
    Shop::parse(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/teach-free.fab.txt")).unwrap()).unwrap()
}

fn ring(n: usize, caps: &[usize]) -> Small {
    Small { nodes: n, links: (0..n).map(|i| (i, (i + 1) % n, caps[i % caps.len()])).collect() }
}

#[test]
fn dc4_the_number_is_the_smallest_connected_part() {
    // a figure eight through node 0: 0>1>2>0 with stretches of 1 car, 0>3>4>0 with stretches of 2. Every stop reaches
    // every other, so a jam fills it all: 5 stops and 9 stretch cars
    let g = Small { nodes: 5, links: vec![(0, 1, 1), (1, 2, 1), (2, 0, 1), (0, 3, 2), (3, 4, 2), (4, 0, 2)] };
    assert_eq!(jam_number_of(&g), Some((vec![0, 1, 2, 3, 4], 14)));
    // its smallest loop alone holds 6: a weaker bound, kept for the explanation
    assert_eq!(smallest_loop_of(&g).map(|x| x.1), Some(6));
    // a ring with a siding feeding in: the siding is not part of any loop, so the ring is the part
    let siding = Small { nodes: 4, links: vec![(0, 1, 1), (1, 2, 1), (2, 0, 1), (3, 0, 1)] };
    assert_eq!(jam_number_of(&siding), Some((vec![0, 1, 2], 6)));
    assert!(jam_number_of(&Small { nodes: 3, links: vec![(0, 1, 1), (1, 2, 1)] }).is_none(), "a line has no loop");

    // the teaching fab's own track: the number is the part's stops plus its inside stretches' cars
    let shop = teach();
    let gap = shop.fleet.as_ref().unwrap().gap;
    let tr = Track::from_shop(&shop);
    let l = jam_number(&tr, gap).expect("the teaching fab's track has a loop");
    let inside: std::collections::HashSet<usize> = l.nodes.iter().copied().collect();
    let want = l.nodes.len() + tr.edges().iter().filter(|e| inside.contains(&e.from) && inside.contains(&e.to)).map(|e| ((e.len / gap).floor() as usize).max(1)).sum::<usize>();
    assert_eq!(l.cars, want);
    assert_eq!(l.names.len(), l.nodes.len(), "each stop is named");
}

#[test]
fn dc5_no_jam_below_the_number_on_any_small_track_and_one_at_it() {
    let tracks = vec![
        ("a ring of three", ring(3, &[1])),
        ("a ring of four with a long stretch", ring(4, &[1, 2])),
        ("a figure eight", Small { nodes: 5, links: vec![(0, 1, 1), (1, 2, 1), (2, 0, 1), (0, 3, 1), (3, 4, 2), (4, 0, 1)] }),
        ("a loop with a shortcut", Small { nodes: 4, links: vec![(0, 1, 1), (1, 2, 2), (2, 3, 1), (3, 0, 1), (1, 3, 1)] }),
        ("two loops joined both ways", Small { nodes: 5, links: vec![(0, 1, 1), (1, 0, 1), (1, 2, 1), (2, 3, 1), (3, 4, 1), (4, 2, 1), (2, 1, 1)] }),
        ("a ring with a siding", Small { nodes: 4, links: vec![(0, 1, 1), (1, 2, 1), (2, 0, 1), (3, 0, 1)] }),
    ];
    for (name, g) in &tracks {
        let (_, m) = jam_number_of(g).unwrap();
        for cars in 1..m {
            let x = explore(g, cars);
            assert!(x.states > 0, "{name}, {cars} cars: placements were tried");
            assert_eq!(x.jams, 0, "{name}: {cars} cars, below the number {m}, never jam ({} placements tried)", x.states);
        }
        assert!(explore(g, m).jams > 0, "{name}: {m} cars can fill the part and jam");
    }
    // and a jam can be reached: on the ring with a siding a car comes in and closes the last gap
    let (name, g) = &tracks[5];
    let (_, m) = jam_number_of(g).unwrap();
    assert!(explore(g, m).jam_reachable, "{name}: {m} cars can be led into a jam");
}

#[test]
fn dc6_the_warning_comes_exactly_at_the_number() {
    let mut shop = teach();
    let gap = shop.fleet.as_ref().unwrap().gap;
    let m = jam_number(&Track::from_shop(&shop), gap).unwrap().cars;
    let jams = |shop: &Shop| check(shop).into_iter().filter(|i| i.code == "may_jam").collect::<Vec<_>>();
    assert!(jams(&shop).is_empty(), "the teaching fab's own cars are below its number");
    shop.fleet.as_mut().unwrap().vehicles = m - 1;
    assert!(jams(&shop).is_empty(), "{} cars, one fewer than the part holds", m - 1);
    shop.fleet.as_mut().unwrap().vehicles = m;
    let w = jams(&shop);
    assert_eq!(w.len(), 1, "{m} cars");
    assert_eq!(w[0].severity, Severity::Warning);
    assert!(w[0].message.contains(&m.to_string()), "the message names the number: {}", w[0].message);
    assert!(!w[0].at.is_empty(), "it names the part's stops");
}
