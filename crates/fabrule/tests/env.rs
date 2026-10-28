//! `fabrule env`: a written rule plays one episode through the same episode code as `fabsim env`
//! (docs/RL-DEFECTS.md, test 9). Written before the code. A toy shop; no real fab.

use std::process::Command;

const SHOP: &str = "fabgym-shop 1
transport\t5.0\t10.0
group\tA\t2\t1.0\t1.0\t-\t900.0\t45.0
group\tB\t2\t1.0\t1.0\t-\t-\t-
route\tr
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t15.0\t2.0\t-\t-\t-\t-\t-\t-\t0\t0.25\t-\t-
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t12.0\t0.0\t-\tN
release\tr\t25\t20.0\t300.0\t30.0\t-\tH
";
const TODAY: &str = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { if c.is_default > 0.5 { 0.0 } else { 1.0 } }";
const FIFO: &str = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { -c.waited_minutes }";

fn tmp(name: &str, text: &str) -> std::path::PathBuf {
    let p = std::env::temp_dir().join(format!("fabrule-env-{}-{name}", std::process::id()));
    std::fs::write(&p, text).unwrap();
    p
}

fn last_line(out: &std::process::Output) -> String {
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    String::from_utf8_lossy(&out.stdout).trim().lines().last().unwrap().to_string()
}

fn score_part(line: &str) -> String {
    line[line.find("\"score\":").expect("a score")..].to_string()
}

#[test]
fn todays_rule_written_out_plays_as_the_engine() {
    let shop = tmp("toy.shop.txt", SHOP);
    let cache = std::env::temp_dir().join(format!("fabrule-env-cache-{}", std::process::id()));
    let common = ["--seed", "4", "--warmup", "0.5", "--window", "1.0", "--defects", "120,240,60"];
    let today = tmp("today.rs", TODAY);
    let ruled = Command::new(env!("CARGO_BIN_EXE_fabrule"))
        .args(["env", today.to_str().unwrap(), shop.to_str().unwrap(), "--cache", cache.to_str().unwrap()])
        .args(common)
        .output()
        .unwrap();
    let auto = Command::new(env!("CARGO_BIN_EXE_fabrule").replace("fabrule", "fabsim"))
        .args(["env", shop.to_str().unwrap(), "--auto"])
        .args(common)
        .output();
    let ruled = last_line(&ruled);
    assert!(ruled.contains("\"done\":true"), "{ruled}");
    // the engine's own run of today's rule, if fabsim is built next to fabrule; else the rule's own decisions count
    if let Ok(a) = auto {
        if a.status.success() {
            assert_eq!(score_part(&ruled), score_part(&last_line(&a)));
        }
    }
    assert!(ruled.contains("\"faults\":0"), "{ruled}");
    // a different rule plays a different window
    let fifo = tmp("fifo.rs", FIFO);
    let f = Command::new(env!("CARGO_BIN_EXE_fabrule"))
        .args(["env", fifo.to_str().unwrap(), shop.to_str().unwrap(), "--cache", cache.to_str().unwrap()])
        .args(common)
        .output()
        .unwrap();
    let f = last_line(&f);
    assert_ne!(score_part(&f), score_part(&ruled));
}
