#!/bin/sh
# The held-out contest (docs/RL-DEFECTS.md): today's rule, PPO and E2's best rule on seeds 0 to 9, defects on, then off.
# One heavy job, niced; one process. On the SMT2020 model.
cd "$(dirname "$0")/../.." || exit 1
. .venv/bin/activate
for d in on off; do
  if [ $d = on ]; then D="--defects 120,240,60"; else D=""; fi
  nice -n 10 python -m agent.rl contest --seeds 0..10 $D --out results/rl-defects/contest-defects-$d \
    --policy ppo=results/rl-defects/ppo/policy.zip --policy e2-best=results/evolve-x4/rules/evolved-1.rs \
    > results/rl-defects/contest-defects-$d.log 2>&1
  echo "defects $d ended $(date) with code $?" >> results/rl-defects/contest.log
done
