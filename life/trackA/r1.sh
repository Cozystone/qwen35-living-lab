#!/usr/bin/env bash
# 트랙 A R1 본 실행(reports/R1_PREREG.md, life/trackA/protocol_R1.json). 9B v5 실험이 끝난 뒤 4B 로 돈다(메모리).
set -u
cd /d/Qwen3.5-4B-Heretic
until grep -q "v5 study 9b-orig finished\|SERVER DOWN" logs/v5_study_9b.log; do sleep 60; done
PORT=8098 WORLD=v1 AGENT=v4a SUFFIX=-r1 N=15 life/size_study.sh 4b-orig=gguf/Qwen3.5-4B-original-MTP-Q4_K_M-rq.gguf
tail -n 5 runs/size-v1-4b-orig-r1.summary.log | grep -q "SERVER DOWN" && { echo "== SERVER DOWN"; exit 3; }
echo "== r1 4b finished"
PORT=8099 WORLD=v1 AGENT=v4a SUFFIX=-r1 N=7 life/size_study.sh 9b-orig=/c/Users/anseo/qwen35_gguf/Qwen3.5-9B-original-MTP-Q4_K_M-rq.gguf
echo "== r1 9b finished"
