#!/usr/bin/env bash
# Debian 실험 노트북(lab@)에서 llama-server 를 띄우고 SSH 터널로 bench_speed.py 를 돌린다. (Windows 판: lap_bench.sh)
# 사용: [BACKEND=vulkan|cuda] lab_bench.sh <model_file> <label> [추가 서버 인자...]
#   예: BACKEND=cuda lab_bench.sh Qwen3.5-4B-Heretic-t55-MTP-Q4_K_M.gguf deb-t55-Q4_K_M-cuda-mtp1 --spec-type draft-mtp --spec-draft-n-max 1
# 결과: eval/<label>.json, logs/<label>_server.log
set -u
cd /d/Qwen3.5-4B-Heretic
MODEL=$1; LABEL=$2; shift 2
LAB="${LAB:-192.168.0.149}"
BIN="~/llm/src/build-${BACKEND:-vulkan}/bin/llama-server"
SSH=(ssh -i "$HOME/.ssh/hp_laptop_ed25519" -o BatchMode=yes -o ConnectTimeout=20 -o ExitOnForwardFailure=yes
     -o UserKnownHostsFile=/d/Qwen3.5-4B-Heretic/laptop/known_hosts_debian)

# 서버는 이 SSH 세션의 자식으로 실행된다(세션이 끝나면 함께 종료).
"${SSH[@]}" -L 8096:127.0.0.1:8080 "lab@$LAB" \
  "exec $BIN -m ~/llm/models/$MODEL --host 127.0.0.1 --port 8080 -c 4096 --no-webui $*" \
  > logs/${LABEL}_server.log 2>&1 &
TUN=$!
for i in $(seq 1 180); do
  curl -s -m 2 http://127.0.0.1:8096/health | grep -q '"ok"' && break
  kill -0 $TUN 2>/dev/null || { echo "server/tunnel died"; tail -20 logs/${LABEL}_server.log; exit 1; }
  sleep 1
done
tools/venv/Scripts/python.exe tools/scripts/bench_speed.py http://127.0.0.1:8096 "$LABEL" eval/$LABEL.json
RC=$?
kill $TUN 2>/dev/null; wait $TUN 2>/dev/null
"${SSH[@]}" "lab@$LAB" 'pkill -x llama-server; true' 2>/dev/null
exit $RC
