//! A fab file's own dispatch rule (docs/BUILD-CONTROLS.md, part 4, FD1 to FD4). Written before the code. The fixture
//! is Build's Free build file for the teaching fab (`tests/data/teach-free.fab.txt`); on a teaching fab of our own;
//! not a real fab.

use fabsim::engine::{run, RunOptions, RunResult};
use fabsim::policy::{self, Policy};
use fabsim::shop::Shop;

const DAYS: f64 = 2.0;

fn fixture() -> String {
    std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/teach-free.fab.txt")).expect("the Free build fixture")
}

/// The fixture with one more line after its transport line.
fn with_line(text: &str, line: &str) -> String {
    let mut out = vec![];
    for l in text.lines() {
        out.push(l.to_string());
        if l.starts_with("transport\t") {
            out.push(line.to_string());
        }
    }
    out.join("\n") + "\n"
}

fn opts(seed: u64) -> RunOptions {
    RunOptions { seed, until: Some(DAYS * 1440.0), record: true }
}

fn go(text: &str, seed: u64) -> RunResult {
    let shop = Shop::parse(text).unwrap_or_else(|e| panic!("the fab file parses: {e}"));
    run(&shop, &opts(seed), None)
}

/// A run's jobs, exactly.
fn events(r: &RunResult) -> Vec<(u32, u32, u32, u64, u64, u64)> {
    r.trace.iter().map(|x| (x.lot, x.step, x.tool, x.arrive.to_bits(), x.start.to_bits(), x.end.to_bits())).collect()
}

#[test]
fn fd1_no_line_and_today_are_the_run_as_before() {
    let base = fixture();
    for seed in [1u64, 2] {
        let plain = go(&base, seed);
        let today = go(&with_line(&base, "dispatch\ttoday"), seed);
        assert_eq!(events(&plain), events(&today), "seed {seed}: dispatch today changes nothing");
        assert_eq!(plain.finished, today.finished);
    }
}

#[test]
fn fd2_a_rule_in_the_file_is_that_rule_and_unknown_rules_are_refused() {
    let base = fixture();
    let bare = Shop::parse(&base).unwrap();
    for (word, p) in [("fifo", Policy::Fifo), ("spt", Policy::Spt)] {
        for seed in [1u64, 2] {
            let ruled = go(&with_line(&base, &format!("dispatch\t{word}")), seed);
            let handed = policy::run_with(&bare, &opts(seed), p);
            assert_eq!(events(&ruled), events(&handed), "seed {seed}: dispatch {word} is the {word} run");
            assert_eq!(ruled.finished, handed.finished);
        }
        // the record survives writing the shop out
        let shop = Shop::parse(&with_line(&base, &format!("dispatch\t{word}"))).unwrap();
        let again = Shop::parse(&shop.to_text()).unwrap();
        assert_eq!(events(&run(&shop, &opts(1), None)), events(&run(&again, &opts(1), None)), "dispatch {word} written out and read back");
        assert!(shop.to_text().lines().any(|l| l == format!("dispatch\t{word}")), "the written shop has its dispatch line");
    }
    let bad = with_line(&base, "dispatch\tquickest");
    let line = bad.lines().position(|l| l.starts_with("dispatch")).unwrap() + 1;
    let err = Shop::parse(&bad).expect_err("an unknown rule is refused");
    assert!(err.contains(&format!("line {line}")), "the refusal names line {line}: {err}");
    assert!(err.contains("quickest"), "the refusal names the rule: {err}");
}

#[test]
fn fd3_the_receipt_names_the_files_rule_and_lists_its_run() {
    let dir = std::env::temp_dir().join(format!("fd3-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("fifo.fab.txt");
    let text = with_line(&fixture(), "dispatch\tfifo");
    std::fs::write(&path, &text).unwrap();
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_fabsim"))
        .args(["receipt", path.to_str().unwrap(), "--seed", "1", "--until", &(DAYS * 1440.0).to_string()])
        .output()
        .expect("run fabsim receipt");
    std::fs::remove_dir_all(&dir).ok();
    assert!(out.status.success(), "fabsim receipt: {}", String::from_utf8_lossy(&out.stderr));
    let receipt = String::from_utf8(out.stdout).unwrap();
    let run_line = receipt.lines().find(|l| l.starts_with("run ")).expect("a run line");
    assert_eq!(run_line.split(' ').nth(3), Some("fifo"), "the receipt's policy: {run_line}");
    let fifo = policy::run_with(&Shop::parse(&fixture()).unwrap(), &opts(1), Policy::Fifo);
    let finished = receipt.lines().filter(|l| l.starts_with("F ")).count();
    assert_eq!(finished, fifo.lots.iter().filter(|l| l.done.is_some()).count(), "the receipt's finished lots are the FIFO run's");
}

#[test]
fn fd4_quality_holds_with_nothing_sent_back_warn() {
    let held = with_line(&fixture(), "defects\t120\t240\t60");
    let issues = fabsim::checks::check(&Shop::parse(&held).unwrap());
    assert!(issues.iter().any(|i| i.code == "holds_without_rework"), "the checks warn: {:?}", issues.iter().map(|i| i.code).collect::<Vec<_>>());
    // one check step sending lots back (the first lithography check, back to the exposure before it) ends the warning
    let mut n = 0;
    let reworked: Vec<String> = held
        .lines()
        .map(|l| {
            if l.starts_with("step\tLitho_Met_T\t") && n == 0 {
                n += 1;
                let mut f: Vec<&str> = l.split('\t').collect();
                f[11] = "1";
                f[12] = "0.02";
                return f.join("\t");
            }
            l.to_string()
        })
        .collect();
    let ok = fabsim::checks::check(&Shop::parse(&(reworked.join("\n") + "\n")).unwrap());
    assert!(!ok.iter().any(|i| i.code == "holds_without_rework"), "no warning once a check sends lots back");
}
