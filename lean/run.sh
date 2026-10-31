#!/bin/sh
# The run referee (docs/LEAN-CHECK.md). Lean runs on the Mac mini: the referee is its own Lake project in
# ~/fab-gym-lean (toolchain v4.35.0-rc3, no dependencies, nothing downloaded); the proofs are checked with the
# shared ~/lean-check's Mathlib, read only. Receipts stream over ssh into the referee; nothing is stored on the mini.
#
#   lean/run.sh build                 copy the project to the mini and build the referee
#   lean/run.sh test                  L1 to L4: the hand-made receipts, then the toy runs and their tampered copies
#   lean/run.sh prove                 L5: check the proofs; no sorry, only the standard axioms
#   lean/run.sh check -- CMD ARGS     stream the receipt CMD writes on stdout into the referee; prints its verdict
#
# Run from the repository root.
set -eu
HOST=${FABGYM_LEAN_HOST:-sdas@souravs-mac-mini}
REMOTE=fab-gym-lean
BIN="\$HOME/$REMOTE/.lake/build/bin/referee"
FABSIM=${FABSIM:-target/release/fabsim}

build() {
  ssh -o BatchMode=yes "$HOST" "mkdir -p ~/$REMOTE/FabCheck ~/$REMOTE/tests"
  scp -q lean/lakefile.toml lean/lean-toolchain lean/Main.lean "$HOST:$REMOTE/"
  scp -q lean/FabCheck/*.lean "$HOST:$REMOTE/FabCheck/"
  scp -q lean/tests/*.receipt lean/tests/expected.txt "$HOST:$REMOTE/tests/"
  ssh -o BatchMode=yes "$HOST" "cd ~/$REMOTE && export PATH=\$HOME/.elan/bin:\$PATH && nice -n 10 lake build referee FabCheck.Core 2>&1 | tail -3"
}

# one verdict line from the referee for a receipt on stdin
referee() {
  gzip -1 | ssh -o BatchMode=yes "$HOST" "gunzip | $BIN -"
}

# compare a verdict with what was expected: "yes", or "no RULE" (the referee's line starts with that)
expect() {
  name=$1 want=$2 got=$3
  case "$got" in
    "$want"|"$want "*) echo "pass $name: $got"; return 0 ;;
    *) echo "FAIL $name: want '$want', got '$got'"; return 1 ;;
  esac
}

test_all() {
  build
  fails=0
  while read -r name want; do
    got=$(referee < "lean/tests/$name.receipt" | tail -1)
    expect "$name" "$want" "$got" || fails=$((fails + 1))
  done < lean/tests/expected.txt
  # L4: the toy runs' receipts pass, and each tampered copy is rejected with its rule named
  for shop in mixed capped tiny; do
    for seed in 0 1 2; do
      tmp=$(mktemp)
      "$FABSIM" receipt "golden/toy/$shop.shop.txt" --seed "$seed" --until 5760 --window-from 1440 > "$tmp"
      got=$(referee < "$tmp" | tail -1)
      expect "toy-$shop-$seed" yes "$got" || fails=$((fails + 1))
      for kind in overlap:one-job skip:route overfill:batch into-down:down breach:breach; do
        k=${kind%%:*} rule=${kind#*:}
        if "$FABSIM" receipt-tamper "$k" < "$tmp" > "$tmp.bad" 2>/dev/null; then
          got=$(referee < "$tmp.bad" | tail -1)
          expect "toy-$shop-$seed-$k" "no $rule" "$got" || fails=$((fails + 1))
        else
          echo "skip toy-$shop-$seed-$k: nothing of that kind to break in this run"
        fi
      done
      rm -f "$tmp" "$tmp.bad"
    done
  done
  echo "failures: $fails"
  [ "$fails" -eq 0 ]
}

prove() {
  build
  ssh -o BatchMode=yes "$HOST" "cd ~/lean-check && export PATH=\$HOME/.elan/bin:\$PATH &&
    lake env sh -c 'LEAN_PATH=\$HOME/$REMOTE/.lake/build/lib/lean:\$LEAN_PATH nice -n 10 lean \$HOME/$REMOTE/FabCheck/Proofs.lean'" > /tmp/fabgym-proofs.txt 2>&1 || {
    cat /tmp/fabgym-proofs.txt; echo "the proofs do not check"; exit 1; }
  cat /tmp/fabgym-proofs.txt
  if grep -qi "sorry" /tmp/fabgym-proofs.txt; then echo "FAIL: a sorry remains"; exit 1; fi
  extra=$(grep "depends on axioms" /tmp/fabgym-proofs.txt | sed 's/.*\[//; s/\].*//' | tr ',' '\n' | tr -d ' ' |
    grep -vx 'propext\|Classical.choice\|Quot.sound' || true)
  if [ -n "$extra" ]; then echo "FAIL: axioms beyond the standard three: $extra"; exit 1; fi
  grep -q "depends on axioms" /tmp/fabgym-proofs.txt || { echo "FAIL: no axioms line printed"; exit 1; }
  echo "proofs check: no sorry, standard axioms only"
}

case "${1:-}" in
  build) build ;;
  test) test_all ;;
  prove) prove ;;
  check) shift; [ "${1:-}" = "--" ] && shift; "$@" | referee ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
