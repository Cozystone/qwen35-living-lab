#!/usr/bin/env bash
# 모델 크기 비교: 모델마다 단일 슬롯 서버(-np 1, 재현 가능)를 띄우고 같은 세계·같은 에이전트·같은 시드로 batch.sh 를 돈다.
# 사용: [PORT=8098] [SUFFIX=-v5] [S0=1 SKIP_T0=1] [WORLD=v1] [DAYS=1-3] [N=7] [AGENT=v4] life/size_study.sh <label=gguf> [<label=gguf> ...]
#   예: life/size_study.sh 4b-orig=gguf/Qwen3.5-4B-original-MTP-Q4_K_M-rq.gguf 9b-orig=/c/.../Qwen3.5-9B-original-MTP-Q4_K_M-rq.gguf
# 결과: runs/size-<WORLD>-<label>/ , 서버 로그 logs/size_<label>_server.log
set -u
cd /d/Qwen3.5-4B-Heretic
PORT=${PORT:-8098}
for spec in "$@"; do
  label=${spec%%=*}; gguf=${spec#*=}
  exp=size-${WORLD:-v1}-$label${SUFFIX:-}
  tools/llama-bin/llama-server.exe -m "$gguf" --port $PORT --host 127.0.0.1 -c 16384 -np 1 --no-webui \
    --spec-type draft-mtp --spec-draft-n-max 3 > logs/size_${label}_server.log 2>&1 &
  srv=$!
  for i in $(seq 1 180); do curl -s -m 2 http://127.0.0.1:$PORT/health | grep -q '"ok"' && break; sleep 1; done
  echo "== $label ($gguf) server pid $srv"
  mkdir -p runs/$exp
  [ -f runs/$exp/cache.json ] || cp runs/exp4v4w1/cache_LIFE.json runs/$exp/cache.json
  CACHE=runs/$exp/cache.json DAYS=${DAYS:-1-3} EXTRA="--agent ${AGENT:-v4} --world ${WORLD:-v1}" \
    life/batch.sh $exp http://127.0.0.1:$PORT ${N:-7} >> runs/$exp.summary.log 2>&1
  kill $srv; wait $srv 2>/dev/null
  powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\" | Where-Object { \$_.CommandLine -like '*--port $PORT*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" 2>/dev/null
  echo "== $label done: $(grep -ac score= runs/$exp.summary.log) day-scores"
done
