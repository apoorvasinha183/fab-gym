use fabsim::shop::Shop;

const VALID: &str = "fabgym-shop 1\ntransport\t0\t0\ngroup\tA\t1\t0\t0\t-\t-\t-\nroute\tr\nstep\tA\tlot\t10\t0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\nrelease\tr\t25\t10\t12\t0\t-\tN\n";

#[test]
fn nonfinite_inputs_are_refused_before_the_event_queue() {
    for number in ["NaN", "inf", "-inf"] {
        let text = VALID.replace("transport\t0\t0", &format!("transport\t{number}\t0"));
        assert!(Shop::parse(&text).is_err(), "accepted {number}");
    }
}

#[test]
fn a_repeating_event_must_advance_time() {
    for interval in ["0", "-1"] {
        let text = VALID.replace("\t12\t0\t-\tN", &format!("\t{interval}\t0\t-\tN"));
        assert!(Shop::parse(&text).is_err(), "accepted release interval {interval}");
        let text = VALID.replace("route\tr", &format!("pm\t{interval}\t1\t1\t0\nroute\tr"));
        assert!(Shop::parse(&text).is_err(), "accepted maintenance interval {interval}");
    }
}

#[test]
fn missing_or_ambiguous_engine_references_are_refused() {
    for text in [
        VALID.replace("step\tA", "step\tmissing"),
        VALID.replace("release\tr", "release\tmissing"),
        format!("{VALID}lot\tL\tr\t25\t10\t0\t99\n"),
        format!("{VALID}group\tA\t1\t0\t0\t-\t-\t-\n"),
        format!("{VALID}route\tr\n"),
    ] {
        assert!(Shop::parse(&text).is_err(), "accepted invalid references: {text}");
    }
    assert!(Shop::parse(VALID).is_ok());
}

#[test]
fn names_with_quotes_and_backslashes_survive_the_gym_protocol() {
    use fabsim::engine::{run, RunOptions};
    let name = "tool\"\\one";
    let text = VALID.replace("\tA\t", &format!("\t{name}\t")).replace("\t12\t0\t-\tN", "\t2\t0\t-\tN");
    let shop = Shop::parse(&text).unwrap();
    let mut asked = 0;
    let mut chooser = |d: &fabsim::engine::Decision| {
        let json = fabsim::gym::observation_json(d, &fabsim::gym::order(d), 0.0, &[]);
        let parsed: serde_json::Value = serde_json::from_str(&json).expect("every observation is JSON");
        assert_eq!(parsed["group"], name);
        asked += 1;
        d.default
    };
    run(&shop, &RunOptions { seed: 0, until: Some(100.0), record: false }, Some(&mut chooser));
    assert!(asked > 0);
}
