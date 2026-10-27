#!/usr/bin/env bash
# v5 비교의 9B 부분 재개(2026-10-27). 빌드 PC 가상 메모리 부족으로 9B 서버가 죽어서, 4B 가 끝난 뒤 9B 를 혼자 돌린다.
# 서버가 죽으면(batch.sh 가 SERVER DOWN) 거기서 멈춘다.
set -u
cd /d/Qwen3.5-4B-Heretic
until grep -q "v5 study 4b-orig finished" logs/v5_study_4b.log; do sleep 60; done
export PORT=8099
G=/c/Users/anseo/qwen35_gguf/Qwen3.5-9B-original-MTP-Q4_K_M-rq.gguf
step() {  # step <exp> <env...>
  local exp=$1; shift
  env "$@" life/size_study.sh "9b-orig=$G"
  if tail -n 5 runs/$exp.summary.log | grep -q "SERVER DOWN"; then echo "== SERVER DOWN in $exp"; exit 3; fi
}
step size-v1-9b-orig-v5 WORLD=v1 AGENT=v5 SUFFIX=-v5 CONDS=LIFE S0=3 SKIP_T0=1 N=15
step size-v1-9b-orig-v5 WORLD=v1 AGENT=v5 SUFFIX=-v5 CONDS=FRESH N=15
step size-v1-9b-orig WORLD=v1 AGENT=v4 S0=8 SKIP_T0=1 N=15
step size-v2-9b-orig-v5 WORLD=v2 DAYS=1-7 AGENT=v5 SUFFIX=-v5 N=7
step size-v2-9b-orig WORLD=v2 DAYS=1-7 AGENT=v4 S0=4 SKIP_T0=1 N=7
echo "== v5 study 9b-orig finished"
