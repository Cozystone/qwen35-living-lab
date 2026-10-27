#!/usr/bin/env bash
# agent-v5 비교(reports/V5_PREREG.md): 모델 하나에 대해 v5 를 새로 돌리고, v4(크기 연구 실행)에는 시드를 더해 횟수를 맞춘다.
# 사용: PORT=8098 life/v5_study.sh <label> <gguf>   (label 은 크기 연구와 같은 이름: 4b-orig, 9b-orig)
set -u
cd /d/Qwen3.5-4B-Heretic
label=$1; gguf=$2
export PORT
WORLD=v1 AGENT=v5 SUFFIX=-v5 N=15 life/size_study.sh "$label=$gguf"
WORLD=v1 AGENT=v4 S0=8 SKIP_T0=1 N=15 life/size_study.sh "$label=$gguf"
WORLD=v2 DAYS=1-7 AGENT=v5 SUFFIX=-v5 N=7 life/size_study.sh "$label=$gguf"
WORLD=v2 DAYS=1-7 AGENT=v4 S0=4 SKIP_T0=1 N=7 life/size_study.sh "$label=$gguf"
echo "== v5 study $label finished"
