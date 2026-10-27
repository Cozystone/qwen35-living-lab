#!/usr/bin/env bash
# Track A M1 본 실행(protocol_A1.json): 세계 v1, KO, {LIFE,FRESH} x {absent,d1}, 시드 1~11 + 결정성 게이트(시드 1 재실행).
set -u
cd /d/Qwen3.5-4B-Heretic
PY=/c/ProgramData/miniconda3/python.exe
OUT=runs/A/m1
mkdir -p $OUT
for t in absent d1; do for c in LIFE FRESH; do
  for s in $(seq 1 11) 1r; do
    seed=${s%r}
    PYTHONIOENCODING=utf-8 $PY life/trackA/run_a.py --root $OUT/$c-$t-s$s --world v1 --cond $c --teacher $t --seed $seed > $OUT/$c-$t-s$s.log 2>&1 || echo "FAIL $c-$t-s$s"
  done
  echo "== $c-$t done"
done; done
$PY life/trackA/freeze.py check
echo "== m1 finished"
