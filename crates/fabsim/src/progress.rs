//! What the scorer is doing, as it does it (docs/RUNS.md): one JSON object a line, sent to a sink when one is set.
//! `fabsim score --events` sets a sink that writes each line to standard error after `event `; with no sink nothing
//! is built, so a run without events costs nothing extra. The report never depends on the sink.

use std::sync::{Mutex, OnceLock};

pub type Sink = Box<dyn Fn(&str) + Send + Sync>;

fn slot() -> &'static Mutex<Option<Sink>> {
    static S: OnceLock<Mutex<Option<Sink>>> = OnceLock::new();
    S.get_or_init(|| Mutex::new(None))
}

/// Set (or with None, clear) where events go.
pub fn set_sink(s: Option<Sink>) {
    *slot().lock().unwrap() = s;
}

/// Whether anyone is listening; callers skip building an event when not.
pub fn on() -> bool {
    slot().lock().unwrap().is_some()
}

/// Send one event, built only when a sink is set.
pub fn emit(build: impl FnOnce() -> serde_json::Value) {
    let g = slot().lock().unwrap();
    if let Some(f) = g.as_ref() {
        f(&build().to_string());
    }
}
