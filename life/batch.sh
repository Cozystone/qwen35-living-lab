#!/usr/bin/env bash
# 빌드 PC 반복 실험: 조건별 온도 0 1회 + 온도 0.6 시드 N개. 각 실행은 빈 root 에서 시작해 세계의 모든 날을 돈다.
# 사용: [S0=1] [SKIP_T0=1] [EXTRA="--agent v3 --world v2"] [CONDS="LIFE FRESH"] [DAYS=1-3] life/batch.sh <exp_name> <llm_url> [N]
# S0: 시드 시작 번호(기존 실험에 시드를 더할 때), SKIP_T0: 온도 0 실행을 건너뜀(기존 것을 지우지 않음).
# 위키백과 캐시는 runs/<exp>/web_cache.json 을 실험 안에서 공유한다
# (같은 조건을 동시에 두 배치로 돌리면 캐시 쓰기가 겹칠 수 있으니 조건마다 따로 실행할 때는 CACHE 를 다르게 준다).
set -u
cd /d/Qwen3.5-4B-Heretic
EXP=$1; LLM=$2; N=${3:-10}
PY=tools/venv/Scripts/python.exe
mkdir -p runs/$EXP
CACHE=${CACHE:-runs/$EXP/web_cache.json}
for cond in ${CONDS:-LIFE FRESH}; do
  if [ -z "${SKIP_T0:-}" ]; then
    root=runs/$EXP/$cond-t0
    rm -rf $root
    PYTHONIOENCODING=utf-8 $PY life/run.py --root $root --cond $cond --days ${DAYS:-1-3} --llm $LLM --stop-file runs/STOP \
      --web-cache $CACHE ${EXTRA:-} > $root.log 2>&1
    rc=$?; grep -a "score=" $root.log | sed "s|^|$cond-t0 |"
    if [ $rc -eq 3 ]; then echo "SERVER DOWN $cond-t0"; rm -rf $root; exit 3; fi
  fi
  for s in $(seq ${S0:-1} $N); do
    root=runs/$EXP/$cond-s$s
    rm -rf $root
    PYTHONIOENCODING=utf-8 $PY life/run.py --root $root --cond $cond --days ${DAYS:-1-3} --llm $LLM --stop-file runs/STOP \
      --web-cache $CACHE ${EXTRA:-} --temperature 0.6 --seed $s > $root.log 2>&1
    rc=$?; grep -a "score=" $root.log | sed "s|^|$cond-s$s |"
    if [ $rc -eq 3 ]; then echo "SERVER DOWN $cond-s$s"; rm -rf $root; exit 3; fi
  done
done
