#!/usr/bin/env bash
# Debian 설치 중 노트북이 preseed.cfg / lab-setup.sh 를 받아 가도록 빌드 PC 에서 이 폴더를 HTTP 로 연다.
# 설치가 끝나면 Ctrl+C 로 닫는다. Windows 방화벽이 8000 포트 수신을 물어보면 "개인 네트워크"만 허용.
# 빌드 PC IP 가 192.168.0.125 가 아니면 preseed.cfg 의 URL 두 곳과 lab-setup.sh 의 BUILD_PC/GATEWAY 를 고칠 것.
cd "$(dirname "$0")"
exec /d/Qwen3.5-4B-Heretic/tools/venv/Scripts/python.exe -m http.server 8000 --bind 0.0.0.0
