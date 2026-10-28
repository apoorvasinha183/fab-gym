//! Dispatch rules written as one Rust function, compiled to WebAssembly and run in a sandbox inside
//! the simulator, then scored on paired seeds against today's rule and the baselines (docs/AGENT.md).

use std::fmt::Write as _;
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use fabsim::engine::{run, Decision, RunOptions, RunResult};
use fabsim::hash::sha256_hex;
use fabsim::policy::{run_with, Policy};
use fabsim::scenario::Scenario;
use fabsim::score::{Measure, MEASURES};
use fabsim::shop::Shop;
use fabsim::uq::{paired, verdict, Interval, Verdict};
use fabsim::window::{score as window_score, with_probes, Window, WindowScore};
use wasmtime::{
    Config, Engine, ExternType, Instance, Memory, Module, Store, StoreLimits, StoreLimitsBuilder,
    TypedFunc,
};

/// The fields of `Cand`, in the order the harness lays them out.
pub const CAND_FIELDS: [&str; 14] = [
    "is_batch",
    "lots",
    "priority",
    "size_wafers",
    "step",
    "steps_left",
    "waited_minutes",
    "setup_change",
    "proc_minutes",
    "work_left_minutes",
    "age_minutes",
    "cqt_slack_minutes",
    "is_default",
    "family",
];
/// The fields of `Ctx`, in order.
pub const CTX_FIELDS: [&str; 7] = [
    "t",
    "queue",
    "working",
    "idle",
    "down",
    "lots_waiting",
    "lots_finished",
];

/// A rule whose faults exceed this share of its decisions is not eligible.
pub const MAX_FAULT_SHARE: f64 = 0.01;
/// Training seeds start here; the held-out seeds are 0 to 9.
pub const TRAIN_SEEDS_FROM: u64 = 100;
pub const HELD_OUT: std::ops::Range<u64> = 0..10;

/// The most candidates one decision passes to a rule (more is a fault, and today's rule decides).
pub const MAX_CANDIDATES: usize = 4096;
/// The most memory a rule's module may have.
pub const MAX_MEMORY_BYTES: usize = 64 << 20;
/// Fuel for one decision: a fixed part and a part per candidate (about one unit per instruction).
pub const FUEL_BASE: u64 = 100_000;
pub const FUEL_PER_CANDIDATE: u64 = 2_000;
/// How long rustc may take on one rule.
pub const COMPILE_SECONDS: u64 = 120;
/// Changes when the harness changes, so cached modules from an older harness are not reused.
const HARNESS_VERSION: &str = "fabrule-harness-3";

// ------------------------------------------------------------------ the source

/// Comments out, then all whitespace out, so a path cannot hide behind spaces or a comment.
fn squeezed(src: &str) -> String {
    let mut out = String::new();
    let b: Vec<char> = src.chars().collect();
    let mut i = 0;
    while i < b.len() {
        if b[i] == '/' && i + 1 < b.len() && b[i + 1] == '/' {
            while i < b.len() && b[i] != '\n' {
                i += 1;
            }
        } else if b[i] == '/' && i + 1 < b.len() && b[i + 1] == '*' {
            i += 2;
            while i + 1 < b.len() && !(b[i] == '*' && b[i + 1] == '/') {
                i += 1;
            }
            i += 2;
        } else {
            if !b[i].is_whitespace() {
                out.push(b[i]);
            }
            i += 1;
        }
    }
    out
}

fn has_word(src: &str, w: &str) -> bool {
    let bytes = src.as_bytes();
    let mut from = 0;
    while let Some(k) = src[from..].find(w) {
        let a = from + k;
        let z = a + w.len();
        let left = a == 0 || !(bytes[a - 1].is_ascii_alphanumeric() || bytes[a - 1] == b'_');
        let right = z >= bytes.len() || !(bytes[z].is_ascii_alphanumeric() || bytes[z] == b'_');
        if left && right {
            return true;
        }
        from = z;
    }
    false
}

/// Refuse a source that reaches outside the function (docs/AGENT.md).
pub fn check_source(src: &str) -> Result<(), String> {
    if src.len() > 20_000 {
        return Err("the rule is longer than 20,000 characters".into());
    }
    let sq = squeezed(src);
    for (needle, why) in [
        ("#[", "attributes are not allowed"),
        ("#!", "attributes are not allowed"),
        (
            "include",
            "include!, include_str! and include_bytes! read files",
        ),
        ("env!", "env! and option_env! read the environment"),
        ("asm!", "inline assembly is not allowed"),
        ("staticmut", "static mut is not allowed"),
        ("::fs", "files are not reachable"),
        ("::net", "the network is not reachable"),
        ("::process", "processes are not reachable"),
        ("::env", "the environment is not reachable"),
        ("::thread", "threads are not available"),
        ("::time", "the clock is not available"),
        ("::io", "input and output are not available"),
        ("::os", "the operating system is not reachable"),
        ("::arch", "machine instructions are not allowed"),
        ("::alloc", "the allocator is not reachable"),
        ("::ptr", "raw pointers are not allowed"),
        ("::mem", "std::mem is not allowed"),
    ] {
        if sq.contains(needle) {
            return Err(format!("refused: {why} (found `{needle}`)"));
        }
    }
    for (word, why) in [
        ("unsafe", "unsafe code is not allowed"),
        ("extern", "extern blocks and crates are not allowed"),
        (
            "use",
            "write full paths instead of `use` (for example std::f64::consts::PI)",
        ),
        ("mod", "modules are not allowed"),
        ("static", "statics are not allowed"),
        ("crate", "`crate` paths are not allowed"),
        ("super", "`super` paths are not allowed"),
        ("self", "`self` paths are not allowed"),
        ("macro_rules", "macro definitions are not allowed"),
    ] {
        if has_word(src, word) {
            return Err(format!("refused: {why} (found `{word}`)"));
        }
    }
    let defines_key = src.split("fn").skip(1).any(|rest| {
        let r = rest.trim_start();
        r.starts_with("key") && r[3..].trim_start().starts_with('(')
    });
    if !defines_key || !has_word(src, "pub") {
        return Err("the rule must define `pub fn key(c: &Cand, x: &Ctx) -> f64`".into());
    }
    Ok(())
}

/// The fixed harness around the model's function. The function sits on line 2 of the file.
fn harness(src: &str) -> String {
    let cand: String = CAND_FIELDS
        .iter()
        .map(|f| format!("    pub {f}: f64,\n"))
        .collect();
    let ctx: String = CTX_FIELDS
        .iter()
        .map(|f| format!("    pub {f}: f64,\n"))
        .collect();
    let nc = CAND_FIELDS.len();
    let nx = CTX_FIELDS.len();
    format!(
        "mod rule {{ #[allow(unused_imports)] use super::{{Cand, Ctx}};\n{src}\n}}\n\
#[repr(C)]\n#[derive(Clone, Copy)]\npub struct Cand {{\n{cand}}}\n\
#[repr(C)]\n#[derive(Clone, Copy)]\npub struct Ctx {{\n{ctx}}}\n\
static mut CTX: [f64; {nx}] = [0.0; {nx}];\n\
static mut CANDS: [f64; {max}] = [0.0; {max}];\n\
#[no_mangle]\n#[allow(unused_unsafe)]\npub extern \"C\" fn ctx_ptr() -> i32 {{ unsafe {{ core::ptr::addr_of_mut!(CTX) as i32 }} }}\n\
#[no_mangle]\n#[allow(unused_unsafe)]\npub extern \"C\" fn cands_ptr() -> i32 {{ unsafe {{ core::ptr::addr_of_mut!(CANDS) as i32 }} }}\n\
fn sane(k: f64) -> f64 {{ if k.is_nan() {{ f64::INFINITY }} else {{ k }} }}\n\
#[no_mangle]\npub extern \"C\" fn choose(n: i32, default: i32) -> i32 {{\n\
    let x: Ctx = unsafe {{ *(core::ptr::addr_of!(CTX) as *const Ctx) }};\n\
    let cs: &[Cand] = unsafe {{ core::slice::from_raw_parts(core::ptr::addr_of!(CANDS) as *const Cand, n as usize) }};\n\
    let mut best = default as usize;\n\
    let mut bk = sane(rule::key(&cs[best], &x));\n\
    for (i, c) in cs.iter().enumerate() {{\n\
        let k = sane(rule::key(c, &x));\n\
        if k < bk {{ best = i; bk = k; }}\n\
    }}\n\
    best as i32\n\
}}\n",
        max = MAX_CANDIDATES * nc
    )
}

/// rustc's messages with the harness's file and line numbers turned into the rule's own.
fn rule_lines(msg: &str) -> String {
    let mut out = String::new();
    for line in msg.lines() {
        let mut l = line.to_string();
        if let Some(i) = l.find("lib.rs:") {
            let rest = &l[i + 7..];
            let digits: String = rest.chars().take_while(|c| c.is_ascii_digit()).collect();
            if let Ok(n) = digits.parse::<i64>() {
                l = format!("{}rule:{}{}", &l[..i], n - 1, &rest[digits.len()..]);
            }
        } else if let Some(bar) = l.find(" |") {
            // the excerpt's gutter: "2 | ..." is the rule's line 1
            let head = &l[..bar];
            let digits = head.trim_start();
            if !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit()) {
                if let Ok(n) = digits.parse::<i64>() {
                    l = format!("{:>w$}{}", n - 1, &l[bar..], w = head.len());
                }
            }
        }
        out.push_str(&l);
        out.push('\n');
    }
    if out.len() > 4000 {
        let mut cut = 4000;
        while !out.is_char_boundary(cut) {
            cut -= 1;
        }
        out.truncate(cut);
        out.push_str("\n[cut]");
    }
    out
}

/// Check, wrap and compile a rule to WebAssembly, cached under `cache` by the source's hash.
pub fn compile(src: &str, cache: &Path) -> Result<Vec<u8>, String> {
    check_source(src)?;
    let id = sha256_hex(format!("{HARNESS_VERSION}\n{src}").as_bytes());
    let dir = cache.join(&id[..24]);
    let wasm = dir.join("rule.wasm");
    if let Ok(b) = std::fs::read(&wasm) {
        return Ok(b);
    }
    std::fs::create_dir_all(&dir).map_err(|e| format!("cache {}: {e}", dir.display()))?;
    std::fs::write(dir.join("lib.rs"), harness(src)).map_err(|e| format!("write the rule: {e}"))?;
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    let mut cmd = Command::new(rustc);
    cmd.current_dir(&dir)
        .env_clear()
        .args([
            "--edition",
            "2021",
            "--crate-type",
            "cdylib",
            "--crate-name",
            "rule",
            "--target",
            "wasm32-unknown-unknown",
        ])
        .args([
            "-C",
            "opt-level=2",
            "-C",
            "panic=abort",
            "-C",
            "debuginfo=0",
            "-C",
            "strip=symbols",
        ])
        .args(["-o", "rule.wasm.part", "lib.rs"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    for k in [
        "PATH",
        "HOME",
        "RUSTUP_HOME",
        "CARGO_HOME",
        "RUSTUP_TOOLCHAIN",
        "TMPDIR",
    ] {
        if let Ok(v) = std::env::var(k) {
            cmd.env(k, v);
        }
    }
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("rustc did not start: {e}"))?;
    let t0 = Instant::now();
    let status = loop {
        if let Some(s) = child.try_wait().map_err(|e| e.to_string())? {
            break s;
        }
        if t0.elapsed() > Duration::from_secs(COMPILE_SECONDS) {
            let _ = child.kill();
            return Err(format!("rustc took more than {COMPILE_SECONDS} s"));
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let mut err = String::new();
    if let Some(mut e) = child.stderr.take() {
        use std::io::Read;
        let _ = e.read_to_string(&mut err);
    }
    if !status.success() {
        return Err(rule_lines(&err));
    }
    std::fs::rename(dir.join("rule.wasm.part"), &wasm).map_err(|e| e.to_string())?;
    std::fs::read(&wasm).map_err(|e| e.to_string())
}

// ------------------------------------------------------------------ the sandbox

fn engine() -> Engine {
    let mut c = Config::new();
    c.consume_fuel(true);
    Engine::new(&c).expect("a wasmtime engine")
}

/// A checked module, shared between runs (each run gets its own store).
#[derive(Clone)]
pub struct Checked {
    engine: Engine,
    module: Module,
}

impl Checked {
    /// Load a module: it must import nothing and ask for at most 64 MiB.
    pub fn new(wasm: &[u8]) -> Result<Checked, String> {
        let engine = engine();
        let module =
            Module::new(&engine, wasm).map_err(|e| format!("not a WebAssembly module: {e}"))?;
        if let Some(i) = module.imports().next() {
            return Err(format!(
                "refused: the module imports {}::{}; a rule may import nothing",
                i.module(),
                i.name()
            ));
        }
        for e in module.exports() {
            if let ExternType::Memory(m) = e.ty() {
                if m.minimum() as usize * 65_536 > MAX_MEMORY_BYTES {
                    return Err(format!(
                        "refused: the module asks for {} MiB of memory; at most 64",
                        m.minimum() * 64 / 1024
                    ));
                }
            }
        }
        for name in ["memory", "ctx_ptr", "cands_ptr", "choose"] {
            if module.get_export(name).is_none() {
                return Err(format!("refused: the module does not export `{name}`"));
            }
        }
        Ok(Checked { engine, module })
    }

    fn instance(&self) -> Result<Rule, String> {
        let limits = StoreLimitsBuilder::new()
            .memory_size(MAX_MEMORY_BYTES)
            .instances(1)
            .tables(4)
            .memories(1)
            .build();
        let mut store = Store::new(&self.engine, limits);
        store.limiter(|l| l);
        store.set_fuel(FUEL_BASE).map_err(|e| e.to_string())?;
        let inst = Instance::new(&mut store, &self.module, &[])
            .map_err(|e| format!("refused: memory or start: {e}"))?;
        let memory = inst
            .get_memory(&mut store, "memory")
            .ok_or("refused: no memory export")?;
        let get = |store: &mut Store<StoreLimits>, n: &str| {
            inst.get_typed_func::<(), i32>(&mut *store, n)
                .map_err(|e| e.to_string())
        };
        let ctx_ptr = get(&mut store, "ctx_ptr")?;
        let cands_ptr = get(&mut store, "cands_ptr")?;
        let choose = inst
            .get_typed_func::<(i32, i32), i32>(&mut store, "choose")
            .map_err(|e| e.to_string())?;
        store.set_fuel(FUEL_BASE).map_err(|e| e.to_string())?;
        let ctx_at = ctx_ptr.call(&mut store, ()).map_err(|e| e.to_string())? as usize;
        let cands_at = cands_ptr.call(&mut store, ()).map_err(|e| e.to_string())? as usize;
        Ok(Rule {
            store,
            memory,
            choose,
            ctx_at,
            cands_at,
            families: Default::default(),
        })
    }
}

/// A loaded rule, ready to decide.
pub struct Rule {
    store: Store<StoreLimits>,
    memory: Memory,
    choose: TypedFunc<(i32, i32), i32>,
    ctx_at: usize,
    cands_at: usize,
    /// family name to the number a rule sees (docs/TWO-FAMILIES.md); "" is 0
    families: std::collections::HashMap<String, f64>,
}

/// One run under a rule.
pub struct RuleRun {
    pub result: RunResult,
    pub decisions: u64,
    pub faults: u64,
}

fn put(buf: &mut [u8], at: usize, vals: &[f64]) -> bool {
    let end = at + vals.len() * 8;
    if end > buf.len() {
        return false;
    }
    for (i, v) in vals.iter().enumerate() {
        buf[at + i * 8..at + i * 8 + 8].copy_from_slice(&v.to_le_bytes());
    }
    true
}

impl Rule {
    /// Load a module: it must import nothing and ask for at most 64 MiB.
    pub fn load(wasm: &[u8]) -> Result<Rule, String> {
        Checked::new(wasm)?.instance()
    }

    /// The rule's pick for one decision, or None for a fault (out of fuel, a trap, an index out of range,
    /// too many candidates).
    /// The rule's pick for one decision (the candidate with the smallest key), or None on a fault.
    pub fn decide(&mut self, d: &Decision) -> Option<usize> {
        let n = d.candidates.len();
        if n == 0 || n > MAX_CANDIDATES {
            return None;
        }
        let ctx = [
            d.t,
            n as f64,
            d.group_tools.working as f64,
            d.group_tools.idle as f64,
            d.group_tools.down as f64,
            d.totals.waiting as f64,
            d.totals.finished as f64,
        ];
        let mut rows = Vec::with_capacity(n * CAND_FIELDS.len());
        for (i, c) in d.candidates.iter().enumerate() {
            rows.extend_from_slice(&[
                if c.kind == "batch" { 1.0 } else { 0.0 },
                c.lots.len() as f64,
                c.priority,
                c.size_wafers as f64,
                c.step as f64,
                c.steps_left as f64,
                c.waited_minutes,
                if c.setup_change { 1.0 } else { 0.0 },
                c.proc_minutes,
                c.work_left_minutes,
                d.t - c.release,
                c.cqt_slack_minutes.unwrap_or(1e9),
                if i == d.default { 1.0 } else { 0.0 },
                self.families.get(&c.family).copied().unwrap_or(0.0),
            ]);
        }
        let buf = self.memory.data_mut(&mut self.store);
        if !put(buf, self.ctx_at, &ctx) || !put(buf, self.cands_at, &rows) {
            return None;
        }
        self.store
            .set_fuel(FUEL_BASE + FUEL_PER_CANDIDATE * n as u64)
            .ok()?;
        match self
            .choose
            .call(&mut self.store, (n as i32, d.default as i32))
        {
            Ok(k) if k >= 0 && (k as usize) < n => Some(k as usize),
            _ => None,
        }
    }

    /// Number the shop's families as a rule sees them; `run` does this itself.
    pub fn prepare(&mut self, shop: &Shop) {
        // families numbered from 1 in the order the shop's `family` records first name them
        self.families.clear();
        for (_, f) in &shop.families {
            if !f.is_empty() && !self.families.contains_key(f) {
                let n = self.families.len() as f64 + 1.0;
                self.families.insert(f.clone(), n);
            }
        }
    }

    pub fn run(&mut self, shop: &Shop, opts: &RunOptions) -> RuleRun {
        let (mut decisions, mut faults) = (0u64, 0u64);
        self.prepare(shop);
        let result = {
            let mut pick = |d: &Decision| {
                decisions += 1;
                match self.decide(d) {
                    Some(k) => k,
                    None => {
                        faults += 1;
                        d.default
                    }
                }
            };
            run(shop, opts, Some(&mut pick))
        };
        RuleRun {
            result,
            decisions,
            faults,
        }
    }
}

// ------------------------------------------------------------------ scoring

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
    pub scores: Vec<WindowScore>,
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
    pub vs_today: Vec<Measure>,
    /// the rule minus each baseline (fifo, spt, cr) on reward
    pub vs_baselines: Vec<(String, Interval)>,
}

fn num(x: f64) -> String {
    if x.is_finite() {
        let s = format!("{x}");
        if s.contains('.') || s.contains('e') {
            s
        } else {
            format!("{s}.0")
        }
    } else {
        "null".into()
    }
}

fn interval_json(iv: &Interval) -> String {
    format!(
        "{{\"mean\": {}, \"lo\": {}, \"hi\": {}, \"n\": {}, \"sd\": {}, \"alpha\": {}}}",
        num(iv.mean),
        num(iv.lo),
        num(iv.hi),
        iv.n,
        num(iv.sd),
        num(iv.alpha)
    )
}

fn list(v: &[f64]) -> String {
    format!(
        "[{}]",
        v.iter().map(|x| num(*x)).collect::<Vec<_>>().join(", ")
    )
}

fn verdict_word(v: Verdict) -> &'static str {
    match v {
        Verdict::Better => "better",
        Verdict::Worse => "worse",
        Verdict::CannotSay => "no clear effect",
    }
}

impl RuleReport {
    pub fn to_json(&self) -> String {
        let mut s = String::from("{\"ok\": true, \"model\": \"the SMT2020 model\", ");
        let _ = write!(
            s,
            "\"seeds\": [{}], ",
            self.seeds
                .iter()
                .map(|x| x.to_string())
                .collect::<Vec<_>>()
                .join(", ")
        );
        let _ = write!(
            s,
            "\"held_out\": {}, \"decisions\": {}, \"faults\": {}, \"eligible\": {}, ",
            self.held_out, self.decisions, self.faults, self.eligible
        );
        let arms: Vec<String> = self
            .arms
            .iter()
            .map(|a| {
                let fields: Vec<String> = MEASURES
                    .iter()
                    .map(|&(k, _, f)| {
                        format!(
                            "\"{k}\": {}",
                            list(&a.scores.iter().map(f).collect::<Vec<_>>())
                        )
                    })
                    .collect();
                format!("{{\"name\": \"{}\", {}}}", a.name, fields.join(", "))
            })
            .collect();
        let _ = write!(s, "\"arms\": [{}], ", arms.join(", "));
        let vt: Vec<String> = self
            .vs_today
            .iter()
            .map(|m| {
                format!(
                    "{{\"key\": \"{}\", \"higher_is_better\": {}, \"interval\": {}, \"verdict\": \"{}\", \"said\": \"{}\"}}",
                    m.key,
                    m.higher_is_better,
                    interval_json(&m.interval),
                    verdict_word(m.verdict),
                    m.verdict.label()
                )
            })
            .collect();
        let _ = write!(s, "\"vs_today\": [{}], ", vt.join(", "));
        let vb: Vec<String> = self
            .vs_baselines
            .iter()
            .map(|(n, iv)| format!("{{\"name\": \"{n}\", \"key\": \"reward\", \"interval\": {}, \"verdict\": \"{}\"}}", interval_json(iv), verdict_word(verdict(iv, true))))
            .collect();
        let _ = write!(s, "\"vs_baselines\": [{}]}}", vb.join(", "));
        s
    }
}

fn par_map<T: Sync, R: Send>(items: &[T], threads: usize, f: impl Fn(&T) -> R + Sync) -> Vec<R> {
    let out: Mutex<Vec<Option<R>>> = Mutex::new((0..items.len()).map(|_| None).collect());
    let next = AtomicUsize::new(0);
    std::thread::scope(|sc| {
        for _ in 0..threads.max(1).min(items.len().max(1)) {
            sc.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= items.len() {
                    break;
                }
                let r = f(&items[i]);
                out.lock().unwrap()[i] = Some(r);
            });
        }
    });
    out.into_inner()
        .unwrap()
        .into_iter()
        .map(|x| x.expect("every job ran"))
        .collect()
}

/// Score a rule against today and the baselines.
pub fn score_rule(
    shop: &Shop,
    scenario: Option<&Scenario>,
    wasm: &[u8],
    seeds: &Seeds,
    threads: usize,
) -> Result<RuleReport, String> {
    let (seeds, held_out) = match seeds {
        Seeds::Train(v) => {
            if let Some(s) = v.iter().find(|&&s| s < TRAIN_SEEDS_FROM) {
                return Err(format!("refused: seed {s} is below {TRAIN_SEEDS_FROM}; seeds 0 to 9 are held out for the final scoring"));
            }
            (v.clone(), false)
        }
        Seeds::HeldOut => (HELD_OUT.collect::<Vec<u64>>(), true),
    };
    if seeds.len() < 2 {
        return Err("refused: at least two seeds are needed for an interval".into());
    }
    let checked = Checked::new(wasm)?;
    let p = fabsim::score::Protocol::default();
    let w = Window {
        from: p.warmup_days * 1440.0,
        to: (p.warmup_days + p.window_days) * 1440.0,
    };
    let base = match scenario {
        Some(sc) => {
            sc.check(shop)?;
            sc.arm(None, None).0.apply(shop)?
        }
        None => shop.clone(),
    };
    let shop = with_probes(&base, &w);
    const ARMS: [&str; 5] = ["today", "fifo", "spt", "cr", "rule"];
    let jobs: Vec<(usize, u64)> = (0..ARMS.len())
        .flat_map(|a| seeds.iter().map(move |&s| (a, s)))
        .collect();
    let results = par_map(
        &jobs,
        threads,
        |&(a, seed)| -> Result<(WindowScore, u64, u64), String> {
            let o = RunOptions {
                seed,
                until: Some(w.to),
                record: false,
            };
            let (r, dec, fau) = if ARMS[a] == "rule" {
                let mut rule = checked.instance()?;
                let rr = rule.run(&shop, &o);
                (rr.result, rr.decisions, rr.faults)
            } else {
                let pol = Policy::parse(ARMS[a]).expect("a baseline");
                (run_with(&shop, &o, pol), 0, 0)
            };
            Ok((window_score(&r, &w)?, dec, fau))
        },
    );
    let results: Vec<(WindowScore, u64, u64)> = results.into_iter().collect::<Result<_, _>>()?;
    let n = seeds.len();
    let arms: Vec<Arm> = ARMS
        .iter()
        .enumerate()
        .map(|(a, name)| Arm {
            name: name.to_string(),
            scores: results[a * n..(a + 1) * n]
                .iter()
                .map(|r| r.0.clone())
                .collect(),
        })
        .collect();
    let decisions: u64 = results[4 * n..].iter().map(|r| r.1).sum();
    let faults: u64 = results[4 * n..].iter().map(|r| r.2).sum();
    let alpha = 0.05;
    let rule = &arms[4].scores;
    let vs_today = MEASURES
        .iter()
        .map(|&(key, higher, f)| {
            let b: Vec<f64> = arms[0].scores.iter().map(f).collect();
            let x: Vec<f64> = rule.iter().map(f).collect();
            let interval = paired(&b, &x, alpha);
            let v = if interval.lo.is_nan() || interval.hi.is_nan() {
                Verdict::CannotSay
            } else {
                verdict(&interval, higher)
            };
            Measure {
                key,
                higher_is_better: higher,
                base: b,
                cand: x,
                interval,
                verdict: v,
            }
        })
        .collect();
    let reward = |s: &WindowScore| s.reward;
    let vs_baselines = (1..4)
        .map(|a| {
            let b: Vec<f64> = arms[a].scores.iter().map(reward).collect();
            let x: Vec<f64> = rule.iter().map(reward).collect();
            (ARMS[a].to_string(), paired(&b, &x, alpha))
        })
        .collect();
    let eligible = decisions > 0 && (faults as f64) <= MAX_FAULT_SHARE * decisions as f64;
    Ok(RuleReport {
        seeds,
        held_out,
        decisions,
        faults,
        eligible,
        arms,
        vs_today,
        vs_baselines,
    })
}
