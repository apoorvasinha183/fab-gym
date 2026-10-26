//! Python's random.Random, seeded with a string, reproduced bit for bit.

mod common;

use fabsim::pyrandom::{sha512, PyRandom};

fn hex(x: f64) -> String {
    format!("{:016x}", x.to_bits())
}

#[test]
fn sha512_matches_python_hashlib() {
    let text = common::read("golden/pyrandom.txt");
    let mut n = 0;
    for line in text.lines().filter(|l| l.starts_with("sha512\t")) {
        let f: Vec<&str> = line.split('\t').collect();
        let got: String = sha512(f[1].as_bytes()).iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(got, f[2], "sha512 of {:?}", f[1]);
        n += 1;
    }
    assert_eq!(n, 3);
}

#[test]
fn string_seeded_draws_match_python() {
    let text = common::read("golden/pyrandom.txt");
    let mut n = 0;
    for line in text.lines().skip(1).filter(|l| !l.starts_with("sha512\t")) {
        let f: Vec<&str> = line.split('\t').collect();
        let mut g = PyRandom::from_str_seed(f[0]);
        let got = [
            g.random(),
            g.random(),
            g.random(),
            g.uniform(2.5, 7.5),
            g.expovariate(1.0 / 35.28),
            g.random(),
        ];
        let got: Vec<String> = got.iter().map(|x| hex(*x)).collect();
        assert_eq!(got, f[1..].to_vec(), "draws for seed {:?}", f[0]);
        n += 1;
    }
    assert_eq!(n, 5);
}
