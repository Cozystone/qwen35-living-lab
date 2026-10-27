#!/usr/bin/env bash
# Debian 실험 노트북(lab@)에서 bash 스크립트를 실행한다. stdin 으로 스크립트를 받는다.
# 사용: tools/scripts/labsh.sh <<'X' ... X      (LAB=<ip> 로 주소 변경)
LAB="${LAB:-192.168.0.149}"
ssh -i "$HOME/.ssh/hp_laptop_ed25519" -o BatchMode=yes -o ConnectTimeout=20 \
  -o UserKnownHostsFile=/d/Qwen3.5-4B-Heretic/laptop/known_hosts_debian "lab@$LAB" 'bash -s' 2>&1 \
  | grep -a -v -E 'post-quantum|store now, decrypt|openssh.com/pq.html'
