#!/bin/sh
# Protocol long-v1 (docs/LONG-RESCORE.md): every policy, warm-up 130 days under today's rule, window days 130 to 190,
# held-out seeds 0 to 9, defects off and on. Four niced processes, one heavy job. On the SMT2020 model.
cd "$(dirname "$0")/../.." || exit 1
. .venv/bin/activate
B="--policy fifo=builtin:fifo --policy spt=builtin:spt --policy cr=builtin:cr --policy random=builtin:random"
L="--policy ppo=results/rl-defects/ppo/policy.zip --policy e2-1=results/evolve-x4/rules/evolved-1.rs --policy e2-2=results/evolve-x4/rules/evolved-2.rs --policy e2-3=results/evolve-x4/rules/evolved-3.rs"
C="--seeds 0..10 --warmup 130 --window 60 --protocol long-v1"
nice -n 10 python -m agent.rl contest $C $B --out results/long-rescore/rules-defects-off > results/long-rescore/rules-defects-off.log 2>&1 &
nice -n 10 python -m agent.rl contest $C $B --defects 120,240,60 --out results/long-rescore/rules-defects-on > results/long-rescore/rules-defects-on.log 2>&1 &
nice -n 10 python -m agent.rl contest $C $L --out results/long-rescore/learned-defects-off > results/long-rescore/learned-defects-off.log 2>&1 &
nice -n 10 python -m agent.rl contest $C $L --defects 120,240,60 --out results/long-rescore/learned-defects-on > results/long-rescore/learned-defects-on.log 2>&1 &
wait
echo "long-v1 ended $(date)" >> results/long-rescore/done.log
