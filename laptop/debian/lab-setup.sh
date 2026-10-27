#!/bin/bash
# 실험장 첫 설정(Debian 설치 직후, 실험 대상 실행 전). 계획: ../DEBIAN_PLAN.md
# 실행: 빌드 PC 에서  ssh -i ~/.ssh/hp_laptop_ed25519 lab@<노트북IP> sudo /root/lab-setup.sh
# 하는 일: 영구 저널, snapper 스냅샷, 실험 대상 계정(mind, sudo 없음)+자원 제한, auditd 실행 기록,
#          AIDE 기준선, nftables 격리(입력: 빌드 PC SSH 만 / 출력: 읽기전용 게이트웨이 + DHCP 만).
# nftables 는 마지막에 적용한다. 적용 후에는 apt 도 막힌다(풀려면 맨 아래 "일시 해제" 참고).
set -euo pipefail

BUILD_PC="${BUILD_PC:-192.168.0.125}"       # SSH 를 허용할 관리 PC
GATEWAY="${GATEWAY:-192.168.0.125}"         # readonly_gateway.py 가 도는 곳
GATEWAY_PORT="${GATEWAY_PORT:-8899}"

echo "[1] 영구 저널"
mkdir -p /var/log/journal
sed -i 's/^#\?Storage=.*/Storage=persistent/' /etc/systemd/journald.conf
systemctl restart systemd-journald

echo "[2] snapper (Btrfs 루트 스냅샷, 시간별 + 설치 직후 기준점)"
if ! snapper list-configs | grep -q '^root'; then
  snapper -c root create-config /
fi
snapper -c root set-config TIMELINE_CREATE=yes TIMELINE_LIMIT_HOURLY=24 TIMELINE_LIMIT_DAILY=14 TIMELINE_LIMIT_WEEKLY=8
systemctl enable --now snapper-timeline.timer snapper-cleanup.timer
snapper -c root create -d "lab-setup: before isolation"

echo "[3] 실험 대상 계정 mind (sudo 없음) + 자원 제한 slice"
id mind >/dev/null 2>&1 || useradd -m -s /bin/bash mind
cat > /etc/systemd/system/mind.slice <<'EOF'
[Unit]
Description=Experiment subject (mind) resource limits
[Slice]
CPUQuota=600%
MemoryMax=12G
TasksMax=512
EOF
systemctl daemon-reload

echo "[4] auditd: mind 의 모든 실행(execve)과 주요 설정 파일 변경 기록"
MIND_UID=$(id -u mind)
cat > /etc/audit/rules.d/lab.rules <<EOF
-a always,exit -F arch=b64 -S execve -F uid=${MIND_UID} -k mind_exec
-w /etc/nftables.conf -p wa -k fw_change
-w /etc/sudoers -p wa -k priv_change
-w /etc/sudoers.d -p wa -k priv_change
-w /etc/ssh/sshd_config.d -p wa -k ssh_change
EOF
augenrules --load
systemctl enable --now auditd

echo "[5] AIDE 기준선(파일 무결성). 수 분 걸림"
aideinit -y -f >/var/log/aideinit.log 2>&1 || echo "  aideinit 경고: /var/log/aideinit.log 확인"

echo "[6] nftables 격리"
cat > /etc/nftables.conf <<EOF
#!/usr/sbin/nft -f
flush ruleset
table inet lab {
  chain input {
    type filter hook input priority 0; policy drop;
    iif lo accept
    ct state established,related accept
    ip saddr ${BUILD_PC} tcp dport 22 accept
    udp sport 67 udp dport 68 accept
    counter comment "dropped_in"
  }
  chain output {
    type filter hook output priority 0; policy drop;
    oif lo accept
    ct state established,related accept
    ip daddr ${GATEWAY} tcp dport ${GATEWAY_PORT} accept
    udp sport 68 udp dport 67 accept
    counter comment "dropped_out_tripwire"
  }
  chain forward {
    type filter hook forward priority 0; policy drop;
  }
}
EOF
nft -c -f /etc/nftables.conf
systemctl enable nftables
systemctl restart nftables
snapper -c root create -d "lab-setup: isolation applied"

echo "완료. 확인: sudo nft list ruleset / sudo nft list chain inet lab output (dropped_out_tripwire 카운터)"
# 일시 해제(apt 설치 등, 사용자 승인 하에만):  sudo nft flush ruleset ; 작업 후 sudo systemctl restart nftables
