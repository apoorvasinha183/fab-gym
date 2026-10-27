# agent

The loop that turns a question into dispatch rules written by a model, scores each one in the simulator on
the SMT2020 model of a fab, and ends in a result card a person signs. The spec is `docs/AGENT.md`.

- A rule is one Rust function, `pub fn key(c: &Cand, x: &Ctx) -> f64`. `crates/fabrule` checks it,
  compiles it to WebAssembly and runs it in a wasmtime sandbox with no imports, at most 64 MiB and a fuel
  budget per decision. A fault falls back to today's pick and is counted.
- The model sees only training scores (seeds 100 and up). The finalists are scored once on the held-out
  seeds 0 to 9 after the search, and the card quotes only the scorer's numbers.
- The card stays unsigned until a person signs it. Signing refuses a card whose numbers were changed.

```sh
cargo build --release -p fabrule
python3 -m agent.fabgym_agent run --question "..." --smt2020 data/smt2020/hvlm --out data/agent/run1 \
    --model MODEL --base-url URL          # key read from ~/.config/fab-gym/baseten.key, never printed
python3 -m agent.fabgym_agent sign data/agent/run1/card.json --name "Operations head"
```

A stand-in model (`--stand-in replies.json`, a list of written replies) runs the loop without a key.

Tests: `cargo test -p fabrule` and `python3 -m unittest agent.tests.test_loop`.
