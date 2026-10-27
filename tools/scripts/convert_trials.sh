#!/usr/bin/env bash
# 병합본(t34/t55/t35)을 BF16 GGUF -> Q8_0 GGUF 로 변환한다. 로그: logs/convert_tNN_*.log
set -u
cd /d/Qwen3.5-4B-Heretic
PY=tools/venv/Scripts/python.exe
for t in "$@"; do
  name=Qwen3.5-4B-Heretic-t$t
  $PY tools/llama.cpp/convert_hf_to_gguf.py merged/$name --outtype bf16 --outfile gguf/$name-MTP-BF16.gguf \
    > logs/convert_t${t}_bf16.log 2>&1 || { echo "t$t bf16 FAIL"; continue; }
  tools/llama-bin/llama-quantize.exe gguf/$name-MTP-BF16.gguf gguf/$name-MTP-Q8_0.gguf Q8_0 \
    > logs/quantize_t${t}_q8.log 2>&1 || { echo "t$t q8 FAIL"; continue; }
  echo "t$t done"
done
