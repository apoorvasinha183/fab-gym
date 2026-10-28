//! The browser glue for two families (docs/ASK-FAMILIES.md, part 5). Written before the code.

use fabsim::engine::{run, Decision, RunOptions};
use fabsim::shop::Shop;
use fabsim::twofam::b_first;
use fabweb::{run_policy, summary, Policy};

const TOY: &str = "fabgym-shop 1
transport\t1.0\t2.0
group\tG\t2\t0.0\t0.0\t-\t-\t-
group\tH\t1\t0.0\t0.0\t-\t-\t-
route\tra
step\tG\tlot\t30.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
route\trb
step\tG\tlot\t25.0\t5.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tH\tlot\t12.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tra\t25\t10.0\t20.0\t0.0\t-\tA
release\trb\t5\t10.0\t40.0\t0.0\t-\tB
family\tra\tA
family\trb\tB
";

#[test]
fn family_b_first_is_code_3_and_runs_as_the_engine_does() {
    assert_eq!(Policy::from_code(3), Policy::BFirst);
    let s = Shop::parse(TOY).unwrap();
    let o = RunOptions { seed: 4, until: Some(3000.0), record: true };
    let mut pick = |d: &Decision| b_first(d, "B");
    let want = run(&s, &o, Some(&mut pick)).log_text();
    assert_eq!(run_policy(&s, &o, Policy::BFirst).log_text(), want);
    assert_ne!(run_policy(&s, &o, Policy::Today).log_text(), want);
}

#[test]
fn the_summary_names_each_routes_family() {
    let s = Shop::parse(TOY).unwrap();
    let r = run_policy(&s, &RunOptions { seed: 1, until: Some(600.0), record: true }, Policy::Today);
    let j = summary(&s, &r);
    assert!(j.contains("\"families\":[\"A\",\"B\"]"), "{}", &j[..200.min(j.len())]);
    let one = Shop::parse(&TOY.replace("family\tra\tA\nfamily\trb\tB\n", "")).unwrap();
    let j1 = summary(&one, &run_policy(&one, &RunOptions { seed: 1, until: Some(600.0), record: true }, Policy::Today));
    assert!(j1.contains("\"families\":[\"\",\"\"]"));
}
