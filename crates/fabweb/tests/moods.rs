//! The floor's moods (docs/FLOOR-LOOK.md): the browser build gives the same moods as `fabsim moods`, from one function
//! in the library. Written before the code. On small shops of our own and the SMT2020 model; not a real fab.

use fabsim::engine::RunOptions;
use fabsim::moods::{Moods, Settings, TOOL_MOODS};
use fabsim::shop::Shop;

fn small() -> String {
    "fabgym-shop 1\ntransport\t0.0\t0.0\ngroup\tA\t2\t0.0\t0.0\t-\t-\t-\ngroup\tB\t1\t0.0\t0.0\t-\t-\t-\nroute\tr\n\
step\tA\tlot\t40.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\nstep\tB\tlot\t25.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-\n\
release\tr\t25\t1.0\t30.0\t0.0\t-\tL\n"
        .to_string()
}

fn indexes(f: &serde_json::Value) -> Vec<usize> {
    f["tools"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as usize).collect()
}

#[test]
fn the_library_writes_the_moods_at_every_frame() {
    let s = Shop::parse(&small()).unwrap();
    let r = fabweb::run_policy(&s, &RunOptions { seed: 1, until: Some(1440.0), record: true }, fabweb::Policy::Today);
    let j = fabsim::moods::frames_json(&s, &r, 1440.0, 60.0);
    assert_eq!(j["tool_moods"], serde_json::json!(TOOL_MOODS));
    assert_eq!(j["group_names"], serde_json::json!(["A", "B"]));
    let frames = j["frames"].as_array().unwrap();
    assert_eq!(frames.len(), 25, "every 60 minutes from 0 to 1,440");
    let m = Moods::new(&s, &r, &Settings::default());
    for f in frames {
        let t = f["t"].as_f64().unwrap();
        let want: Vec<usize> = m.at(t).tools.iter().map(|x| TOOL_MOODS.iter().position(|y| *y == x.mood).unwrap()).collect();
        assert_eq!(indexes(f), want, "frame at {t}");
        assert_eq!(f["queues"].as_array().unwrap().len(), 2);
    }
    assert!(j["score"]["wafers_per_day"].as_f64().unwrap() > 0.0);
}

#[test]
fn the_browser_export_gives_the_last_runs_moods() {
    let text = small();
    let p = fabweb::fg_alloc(text.len());
    unsafe {
        std::ptr::copy_nonoverlapping(text.as_ptr(), p, text.len());
        assert_eq!(fabweb::fg_load(p, text.len()), 0);
    }
    assert_eq!(fabweb::fg_run(1.0, 1.0, 0, -1, 0.0, 0.0), 0);
    assert_eq!(fabweb::fg_moods(60.0), 0);
    let out = unsafe { std::str::from_utf8(std::slice::from_raw_parts(fabweb::fg_json_ptr(), fabweb::fg_json_len())).unwrap().to_string() };
    let got: serde_json::Value = serde_json::from_str(&out).unwrap();
    // the same run the page made: the loaded shop with the default dials, today's rule
    let s = fabweb::prepare(&Shop::parse(&text).unwrap(), &fabsim::dials::Dials::default(), -1, 0.0, 0.0).unwrap();
    let r = fabweb::run_policy(&s, &RunOptions { seed: 1, until: Some(1440.0), record: true }, fabweb::Policy::Today);
    let want = fabsim::moods::frames_json(&s, &r, 1440.0, 60.0);
    assert_eq!(got["frames"], want["frames"]);
    assert_eq!(got["tools"], want["tools"]);
}

#[test]
fn moods_before_any_run_are_refused() {
    // a fresh thread has no run yet
    std::thread::spawn(|| assert_ne!(fabweb::fg_moods(60.0), 0)).join().unwrap();
}
