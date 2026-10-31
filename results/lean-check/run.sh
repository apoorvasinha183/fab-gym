#!/bin/sh
# Every replayable scored run of protocol long-v1 (docs/LEAN-CHECK.md, docs/LONG-RESCORE.md) through the referee,
# one at a time: defects off replayed from each scored run's own picks; defects on played again by the same episode
# code. Nothing is stored: each receipt streams to the mini. On the SMT2020 testbed.
cd "$(dirname "$0")/../.." || exit 1
OUT=results/lean-check/verdicts.tsv
[ -f "$OUT" ] || printf 'policy\tdefects\tseed\tseconds\tverdict\n' > "$OUT"
done_already() { grep -q "^$1	$2	$3	" "$OUT"; }
one() { # policy defects seed args...
  p=$1 d=$2 s=$3; shift 3
  done_already "$p" "$d" "$s" && return
  t0=$(date +%s)
  v=$(nice -n 10 target/release/fabsim receipt data/smt2020/hvlm --seed "$s" --warmup 130 --window 60 "$@" | lean/run.sh check -- cat | tail -1)
  printf '%s\t%s\t%s\t%s\t%s\n' "$p" "$d" "$s" "$(( $(date +%s) - t0 ))" "$v" >> "$OUT"
}
for p in today fifo spt cr random ppo; do
  for s in 0 1 2 3 4 5 6 7 8 9; do
    one "$p" off "$s" --picks "results/long-rescore/regret-b/picks/$p-$s.picks"
  done
done
for p in today fifo spt cr random; do
  for s in 0 1 2 3 4 5 6 7 8 9; do
    one "$p" on "$s" --auto "$p" --defects 120,240,60
  done
done
echo "lean-check ended $(date)" >> results/lean-check/done.log
