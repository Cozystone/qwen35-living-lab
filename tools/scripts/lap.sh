#!/usr/bin/env bash
# HP 노트북(DESKTOP-N6RR73M)에서 PowerShell 스크립트를 실행한다. stdin 으로 스크립트를 받는다.
# 사용: tools/scripts/lap.sh <<'EOF' ... EOF
LAPTOP="${LAPTOP:-192.168.0.149}"
ENC=$( { printf '%s\n' '$ProgressPreference="SilentlyContinue"; [Console]::OutputEncoding=[Text.Encoding]::UTF8'; cat; } | iconv -f UTF-8 -t UTF-16LE | base64 -w0)
ssh -i "$HOME/.ssh/hp_laptop_ed25519" -o BatchMode=yes -o ConnectTimeout=10 "test@$LAPTOP" \
  "powershell -NoProfile -NonInteractive -EncodedCommand $ENC" 2>&1 \
  | grep -a -v -E 'post-quantum|store now, decrypt|openssh.com/pq.html|^#< CLIXML|^<Objs'
