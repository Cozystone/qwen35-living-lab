#!/usr/bin/env bash
# 노트북 배포 설정(t55 Q4_K_M, -fitt 256, MTP n=1, ctx 8192)으로 eval_grounding.py 를 돌린다. 결과 eval/lap-t55-Q4_K_M_grounding.json
set -u
cd /d/Qwen3.5-4B-Heretic
DIR='D:\LLM\Qwen3.5-4B-Heretic'
ssh -i "$HOME/.ssh/hp_laptop_ed25519" -o BatchMode=yes -o ExitOnForwardFailure=yes -L 8095:127.0.0.1:8080 test@192.168.0.149 \
  "$DIR\bin-vulkan\llama-server.exe -m $DIR\models\Qwen3.5-4B-Heretic-t55-MTP-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -c 8192 --no-webui -fitt 256 --spec-type draft-mtp --spec-draft-n-max 1" \
  > logs/lap_grounding_server.log 2>&1 &
T=$!
for i in $(seq 1 180); do curl -s -m 2 http://127.0.0.1:8095/health | grep -q ok && break; sleep 1; done
time PYTHONIOENCODING=utf-8 tools/venv/Scripts/python.exe tools/scripts/eval_grounding.py http://127.0.0.1:8095 lap-t55-Q4_K_M eval/lap-t55-Q4_K_M_grounding.json
kill $T
tools/scripts/lap.sh <<'X' >/dev/null
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
X
