#!/bin/sh
# After the 110 runs: PPO with defects on, 10 seeds, played again with picks, then through the referee (one at a time).
cd "$(dirname "$0")/../.." || exit 1
while ! grep -q "lean-check ended" results/lean-check/done.log 2>/dev/null; do sleep 60; done
OUT=results/lean-check/verdicts.tsv
for s in 0 1 2 3 4 5 6 7 8 9; do
  grep -q "^ppo	on	$s	" "$OUT" && continue
  t0=$(date +%s)
  if nice -n 10 .venv/bin/python results/lean-check/ppo_on.py "$s" >> results/lean-check/ppo_on.log 2>&1; then
    v=$(nice -n 10 target/release/fabsim receipt data/smt2020/hvlm --seed "$s" --warmup 130 --window 60 --defects 120,240,60 \
        --picks "results/lean-check/picks/ppo-on-$s.picks" | lean/run.sh check -- cat | tail -1)
  else
    v="not checked: the replay differs from the scored run (see ppo_on.log)"
  fi
  printf 'ppo\ton\t%s\t%s\t%s\n' "$s" "$(( $(date +%s) - t0 ))" "$v" >> "$OUT"
done
echo "ppo-on ended $(date)" >> results/lean-check/done.log
