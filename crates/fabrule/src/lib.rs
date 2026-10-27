//! Dispatch rules written as one Rust function, compiled to WebAssembly and run in a sandbox inside
//! the simulator, then scored on paired seeds against today's rule and the baselines (docs/AGENT.md).
//!
//! Tests first: the functions below are declared and not yet built.

use std::path::Path;

use fabsim::engine::{RunOptions, RunResult};
use fabsim::scenario::Scenario;
use fabsim::shop::Shop;

/// The fields of `Cand`, in the order the harness lays them out.
pub const CAND_FIELDS: [&str; 13] = [
    "is_batch", "lots", "priority", "size_wafers", "step", "steps_left", "waited_minutes", "setup_change",
    "proc_minutes", "work_left_minutes", "age_minutes", "cqt_slack_minutes", "is_default",
];
/// The fields of `Ctx`, in order.
pub const CTX_FIELDS: [&str; 7] = ["t", "queue", "working", "idle", "down", "lots_waiting", "lots_finished"];

/// A rule whose faults exceed this share of its decisions is not eligible.
pub const MAX_FAULT_SHARE: f64 = 0.01;
/// Training seeds start here; the held-out seeds are 0 to 9.
pub const TRAIN_SEEDS_FROM: u64 = 100;
pub const HELD_OUT: std::ops::Range<u64> = 0..10;

/// Refuse a source that reaches outside the function (docs/AGENT.md).
pub fn check_source(_src: &str) -> Result<(), String> {
    todo!()
}

/// Check, wrap and compile a rule to WebAssembly, cached under `cache` by the source's hash.
pub fn compile(_src: &str, _cache: &Path) -> Result<Vec<u8>, String> {
    todo!()
}

/// A loaded rule.
pub struct Rule {}

/// One run under a rule.
pub struct RuleRun {
    pub result: RunResult,
    pub decisions: u64,
    pub faults: u64,
}

impl Rule {
    /// Load a module: it must import nothing and ask for at most 64 MiB.
    pub fn load(_wasm: &[u8]) -> Result<Rule, String> {
        todo!()
    }

    pub fn run(&mut self, _shop: &Shop, _opts: &RunOptions) -> RuleRun {
        todo!()
    }
}

/// Which seeds a scoring uses.
#[derive(Clone, Debug)]
pub enum Seeds {
    /// training seeds, each 100 or more
    Train(Vec<u64>),
    /// the held-out seeds 0 to 9
    HeldOut,
}

/// One arm's scores, per seed in the report's seed order.
#[derive(Clone, Debug)]
pub struct Arm {
    /// "today", "fifo", "spt", "cr" or "rule"
    pub name: String,
    pub scores: Vec<fabsim::window::WindowScore>,
}

/// The scoring of one rule (docs/AGENT.md).
#[derive(Clone, Debug)]
pub struct RuleReport {
    pub seeds: Vec<u64>,
    pub held_out: bool,
    pub decisions: u64,
    pub faults: u64,
    pub eligible: bool,
    /// today, fifo, spt, cr, rule
    pub arms: Vec<Arm>,
    /// the rule minus today, on each of fabsim::score::MEASURES
    pub vs_today: Vec<fabsim::score::Measure>,
    /// the rule minus each baseline (fifo, spt, cr) on reward
    pub vs_baselines: Vec<(String, fabsim::uq::Interval)>,
}

impl RuleReport {
    pub fn to_json(&self) -> String {
        todo!()
    }
}

/// Score a rule against today and the baselines.
pub fn score_rule(_shop: &Shop, _scenario: Option<&Scenario>, _wasm: &[u8], _seeds: &Seeds, _threads: usize) -> Result<RuleReport, String> {
    todo!()
}
