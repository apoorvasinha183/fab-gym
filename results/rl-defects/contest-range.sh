#!/bin/sh
# The held-out contest at half and twice the assumed defect hold lengths (docs/RL-DEFECTS.md, Changes, 29 Oct).
# One heavy job, niced; one process. On the SMT2020 model.
cd "$(dirname "$0")/../.." || exit 1
. .venv/bin/activate
for pair in "x0.5 60,120,30" "x2 240,480,120"; do
  set -- $pair
  nice -n 10 python -m agent.rl contest --seeds 0..10 --defects "$2" --out "results/rl-defects/contest-defects-$1" \
    --policy ppo=results/rl-defects/ppo/policy.zip --policy e2-best=results/evolve-x4/rules/evolved-1.rs \
    > "results/rl-defects/contest-defects-$1.log" 2>&1
  echo "defects $1 ended $(date) with code $?" >> results/rl-defects/contest.log
done
