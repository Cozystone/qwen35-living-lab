#!/usr/bin/env bash
# 빌드 PC 에서 GGUF 하나를 llama-server 로 띄우고 eval_server.py 를 돌린다.
# 사용: [EXTRA_ARGS="--spec-type draft-mtp ..."] eval_gguf.sh <gguf> <label> [port]   결과: eval/<label>.json, eval/<label>_quality.json, 서버 로그: logs/eval_<label>_server.log
set -u
cd /d/Qwen3.5-4B-Heretic
GGUF=$1; LABEL=$2; PORT=${3:-8091}
tools/llama-bin/llama-server.exe -m "$GGUF" --port $PORT --host 127.0.0.1 -c 4096 --no-webui ${EXTRA_ARGS:-} \
  > logs/eval_${LABEL}_server.log 2>&1 &
SRV=$!
for i in $(seq 1 120); do
  curl -s -m 2 http://127.0.0.1:$PORT/health | grep -q '"ok"' && break
  kill -0 $SRV 2>/dev/null || { echo "server died"; tail -20 logs/eval_${LABEL}_server.log; exit 1; }
  sleep 1
done
PY=tools/venv/Scripts/python.exe
$PY tools/scripts/eval_server.py http://127.0.0.1:$PORT "$LABEL" eval/$LABEL.json; RC=$?
$PY tools/scripts/eval_quality.py http://127.0.0.1:$PORT "$LABEL" eval/${LABEL}_quality.json || RC=1
kill $SRV; wait $SRV 2>/dev/null
exit $RC
