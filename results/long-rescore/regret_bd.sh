#!/bin/sh
# Regret B and D, and wafers out day by day, on long-v1 (docs/LONG-RESCORE.md). One heavy job, niced, at most 4
# workers. On the SMT2020 model, a published research model of a fab.
#   Runs: each policy (today, FIFO, SPT, critical ratio, random, PPO) on seeds 0 to 9, defects off, days 130 to 190:
#         its picks and its done line with wafers out each day. Four at a time.
#   B:    on seeds 0 to 2, 60 evenly spaced picks audited over a day's horizon, at most 64 lots tried at each (every
#         kind and the policy's own pick first). The audit's copies use 4 threads.
#   D:    the best of today, FIFO, SPT, critical ratio and random kept each 12-hour shift; seeds 0 to 9, defects off
#         and on.
cd "$(dirname "$0")/../.." || exit 1
. .venv/bin/activate
F=./target/release/fabsim
O=results/long-rescore/regret-b
mkdir -p $O/picks $O/runs results/long-rescore/regret-d
W="--warmup 130 --window 60"
log() { echo "$(date '+%d %H:%M:%S') $*" >> results/long-rescore/regret-bd.log; }
log "start"
for s in 0 1 2 3 4 5 6 7 8 9; do for p in today fifo spt cr random ppo; do
  [ -s $O/runs/$p-$s.json ] || echo "$p $s"
done; done | xargs -P 4 -n 2 sh -c 'nice -n 10 python results/long-rescore/play_one.py "$0" "$1" results/long-rescore/regret-b || echo "failed $0 $1" >> results/long-rescore/regret-bd.log'
log "runs done"
for s in 0 1 2; do
  for p in today fifo spt cr random ppo; do
    [ -s $O/$p-$s.json ] || nice -n 10 $F regret audit data/smt2020/hvlm --seed $s $W --picks $O/picks/$p-$s.picks --samples 60 --horizon 1440 --max 64 --out $O/$p-$s.json >> results/long-rescore/regret-bd.log
  done
done
log "B done"
for d in off on; do
  D=""; [ $d = on ] && D="--defects 120,240,60"
  for s in 0 1 2 3 4 5 6 7 8 9; do
    [ -s results/long-rescore/regret-d/$d-$s.json ] || nice -n 10 $F regret switch data/smt2020/hvlm --seed $s $W $D --shift 720 --out results/long-rescore/regret-d/$d-$s.json >> results/long-rescore/regret-bd.log
  done
done
log "D done"
