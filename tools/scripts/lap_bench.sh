#!/usr/bin/env bash
# 노트북(Vulkan)에서 llama-server 를 띄우고 SSH 터널로 bench_speed.py 를 돌린다.
# 사용: lap_bench.sh <laptop_model_file> <label> [추가 서버 인자...]
#   예: lap_bench.sh Qwen3.5-4B-Heretic-t55-MTP-Q4_K_M.gguf lap-t55-Q4_K_M-mtp2 --spec-type draft-mtp --spec-draft-n-max 2
# BIN=bin-cpu 로 CPU 빌드 사용. -ngl 은 지정하지 않는다(llama.cpp --fit 이 가용 VRAM 에 맞춰 자동 결정). 결과: eval/<label>.json, logs/<label>_server.log
set -u
cd /d/Qwen3.5-4B-Heretic
MODEL=$1; LABEL=$2; shift 2
LAPTOP="${LAPTOP:-192.168.0.149}"
DIR='D:\LLM\Qwen3.5-4B-Heretic'
SSH=(ssh -i "$HOME/.ssh/hp_laptop_ed25519" -o BatchMode=yes -o ConnectTimeout=10 -o ExitOnForwardFailure=yes)

# 서버는 이 SSH 세션의 자식으로 실행된다(세션이 끝나면 함께 종료).
"${SSH[@]}" -L 8092:127.0.0.1:8080 "test@$LAPTOP" \
  "$DIR\\${BIN:-bin-vulkan}\\llama-server.exe -m $DIR\\models\\$MODEL --host 127.0.0.1 --port 8080 -c 4096 --no-webui $*" \
  > logs/${LABEL}_server.log 2>&1 &
TUN=$!
for i in $(seq 1 180); do
  curl -s -m 2 http://127.0.0.1:8092/health | grep -q '"ok"' && break
  kill -0 $TUN 2>/dev/null || { echo "server/tunnel died"; tail -20 logs/${LABEL}_server.log; exit 1; }
  sleep 1
done
grep -E "offloaded|fit|Vulkan0 model buffer" logs/${LABEL}_server.log | head -5
tools/venv/Scripts/python.exe tools/scripts/bench_speed.py http://127.0.0.1:8092 "$LABEL" eval/$LABEL.json
RC=$?
kill $TUN 2>/dev/null; wait $TUN 2>/dev/null
tools/scripts/lap.sh <<'EOF' >/dev/null
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
EOF
exit $RC
