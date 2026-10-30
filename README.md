<p align="center"><img src="docs/img/fabgym-hero.jpg" width="820" alt="Cartoon of a cleanroom boot camp: a wafer in a red headband yells &quot;You call that planar?&quot; at a sweating CMP robot holding a spirit level."></p>

> ***"Your phone's brain spent most of its childhood waiting in line."***  
> <sub>— a wafer, looking back</sub>

# Fab Gym

A simulated wafer fab you can ask questions, and a fair way to check the answers. On the **SMT2020 model**, a published research model of a fab: 1,043 machines, 105 groups, routes of 583 and 343 steps. No real fab's data.

## A puzzle to start

A polishing machine just finished a job. Five lots are waiting for it.

- one is a rush order;
- one has waited nine hours;
- one would need the machine set up differently first;
- one is a single step from done;
- one has a timer running: if it doesn't reach its next step within two hours, it may be scrapped.

Which one goes next?

Sit with it for a second. There is no obviously right answer, and that is the whole problem. Now scale it up: a thousand machines, thousands of lots, and every choice changes who is waiting where for the next one. Mathematicians call this a dynamic, stochastic job shop. Finding the best schedule is NP-hard even before anything breaks, and in a fab things break all the time.

So fabs use rules of thumb, and nobody can say how good a rule is until weeks after it has run. Fab Gym tests the rule first.

## Three ideas that do most of the work

**1. Little's law.** In any system that has settled, the work inside equals the output rate times the time each piece spends inside. On seed 0 of the SMT2020 model, today's rule holds about 3,014 lots of 25 wafers and gets 1,246 wafers a day out:

> 3,014 × 25 ÷ 1,246 ≈ 60.5 days

which is exactly the cycle time we measure. Let more work in, and at the same output everything takes longer.

**2. The slowest machine group sets the speed limit.** Add up the minutes each wafer needs on each group and divide into the minutes the group has. The polishers come out tightest: at most about 1,302 wafers a day, on average. Today's rule gets 1,263. Yes, this is why the robot in the picture is sweating.

**3. Same luck, fair fight.** To compare two rules, run them on the same random draws, so a breakdown that hits one hits the other. Differences then come from the rules and the luck cancels out.

## Why a short test lies

We first scored everything over three days. Every rule started out looking fine, because a full fab coasts on the work the old rule set up. Over sixty settled days the picture changes completely: FIFO, shortest-job-first and a learned PPO policy fall to 595 to 668 wafers a day, against 1,263.

## What does "best" even mean?

Every other policy we tried lost to today's rule on all ten held-out seeds (our evolved rules tied it, by copying it). We tried four ways to estimate the best possible, and each taught us something:

- **the ceiling**: today's rule is about 39 wafers a day below it;
- **the best rule in hindsight**: today's rule, on every seed;
- **foresight at sampled decisions**: rewards grabbing short jobs now, which loses later;
- **the best rule each shift**: does worse than never switching, by about 2,200 reward points.

The moral: judge a decision over days, from the fab as it stands.

## How sure are we?

An interval only covers the doubt you feed it. Ours first covered the luck inside a run. Then we redrew every machine group's numbers about 20% off, as a real fab's estimates might be, and that doubt turned out to be 98 to 100% of the uncertainty. One rule's apparent win vanished under a pre-registered check: it was draining an overloaded fab. We keep that in the docs (`docs/UQ-INPUTS.md`).

## The machine that answers questions

1. You ask in plain words.
2. Meta's Muse Spark Open turns the question into a scenario that must pass a schema, every value marked *said* or *assumed*.
3. It proposes rules (small Rust functions), caps on work in the fab, spare tools or release plans.
4. Each rule is compiled to WebAssembly and run in a sandbox; the model reads its scores on training seeds and rewrites it.
5. Finalists are scored once on held-out seeds against today's rule, with paired intervals.
6. A card quotes only the scorer's numbers, and a person signs.

<details>
<summary>The engine room</summary>

A discrete-event simulator in Rust that reproduces the reference engine's event log bit for bit, about 0.03 s per simulated day on one laptop core; overhead vehicles on the building's drawn rails; a WebAssembly sandbox with no imports, 64 MiB and a fuel limit per decision; and a design for running beside a real fab's MES and dispatcher (`docs/SYSTEM-DESIGN.md`).
</details>

## Try it

```sh
# the SMT2020 files go in data/smt2020/hvlm (see data/smt2020/README.md)
cargo build --release                      # the simulator and its tools
web/build.sh                               # the browser simulator and the floor page's data
python3 -m agent.helper --port 8766        # the floor page with its ask box, on 127.0.0.1
```

Without a model key the ask box answers the recorded example questions and scores scenarios you write. Every number it shows comes from the simulator.

## Map of the repo

| Where | What lives there |
| --- | --- |
| `crates/fabsim/` | The simulator: the fab, the overhead vehicles, the scorer, regret and uncertainty |
| `crates/fabrule/` | The sandbox that compiles a written rule to WebAssembly and runs it |
| `crates/fabweb/` | The same simulator built for the browser |
| `agent/` | The ask loop, the learned policy and the contests |
| `web/` | The floor page |
| `viz/` | The building: plans, the BIM model, Blender and Godot scenes |
| `docs/` | Every design, written before its code, with its results below the line |
| `results/` | Every run behind every number |
| `golden/` | Event logs the simulator must reproduce exactly |

## What is new in this hackathon

**Everything in this repository was built during the hackathon, starting after the 12:00 PM ET kickoff on 26 October 2026.** The git history is the record.

Built before the hackathon, and kept outside this repository:

- A Python reference engine for the SMT2020 model, written earlier in Chetnova's private repository. The Rust simulator here is written new and is checked against event logs recorded from that engine (the golden files in `golden/`). None of its code is copied here.
- Earlier results on the SMT2020 model (a learned dispatch rule, a WIP-cap study). They are quoted only where labelled "pre-existing".

## Credits

The SMT2020 testbed: Kopp, Hassoun, Kalir and Mönch, *SMT2020: A Semiconductor Manufacturing Testbed*, IEEE Transactions on Semiconductor Manufacturing, 2020. See `NOTICE.md`. Our entry to the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon), Startups track. By Chetnova.
