# 노트북 Debian 재설치 계획 (0단계 실험장) — 2026-10-26 실행 완료 (경과: WORKLOG.txt [10])

작성 2026-10-26. 하드웨어 사실은 laptop/hw_inventory_20261026.txt (Windows 에서 읽기만 함).
**재설치는 SSD 의 Windows 를 지운다. 되돌릴 수 없으므로 아래 "착수 조건"을 모두 만족한 뒤에만 진행.**

## 착수 조건
1. 백업 검증 완료(완료: D:\HP-Laptop-Backup-20261026, 10,828개 SHA-256 일치).
2. OneDrive 온라인 전용 142개(0.43GB): **사용자 결정으로 백업 안 함**(2026-10-26, "그냥 날려버려"). 클라우드 쪽은 건드리지 않음.
   (laptop/onedrive_online_only_20261026.txt)
3. 설치 USB 부팅은 물리 작업 → 사용자가 노트북 앞에서 USB 꽂고 F9(HP 부팅 메뉴) 선택.
4. 1TB HDD(D:, 931GB, 자료 있음)를 지울지 보존할지 사용자 결정. 기본안: **HDD 는 건드리지 않고** SSD 만 설치.

## 하드웨어 → 설치 선택
| 항목 | 사실 | 결정 |
|---|---|---|
| 펌웨어 | Legacy BIOS(Insyde F.78, 2016), Secure Boot 없음, BitLocker 꺼짐 | MBR + GRUB(BIOS) 설치. UEFI 전환 불필요 |
| SSD | Samsung 850 EVO M.2 250GB(SATA, MBR) | 전체를 Debian: / 를 Btrfs(서브볼륨 @, @home, @snapshots, @log) + swap 16GB |
| HDD | WD 1TB(SATA, MBR, NTFS D:) | 기본은 보존(읽기전용 마운트도 안 함). 실험 데이터는 SSD |
| Wi-Fi | Intel AC 3165 (8086:3165) | firmware-iwlwifi(non-free-firmware, Debian 공식 설치 이미지에 포함) |
| 유선 | **Realtek RTL8136 = Fast Ethernet, 최대 100Mbps** (10ec:8136) | r8169 드라이버. 케이블 바꿔도 기가비트 불가. 현재 10Mbps 링크 |
| GPU | GTX 950M (10de:139a, Maxwell) + Intel HD 530 (Optimus) | Debian non-free nvidia-driver(Maxwell 지원 계열). Linux 는 Windows 472 드라이버 제약이 없어 **CUDA llama.cpp 가능성** → 설치 후 Vulkan/CUDA 둘 다 실측 |
| CPU/RAM | i7-6700HQ / 15.8GB | - |

배포판: Debian stable(13 "trixie"), netinst 대신 오프라인 DVD-1 또는 펌웨어 포함 이미지(격리 전제). preseed 로 무인 설치 가능.

## 격리 (설치 직후, 실험 대상 실행 전)
- nftables 기본 정책: 입력 drop(빌드 PC IP 의 SSH 만 허용), **출력 drop**.
- 웹 읽기는 빌드 PC 의 읽기전용 프록시 한 곳만 허용: GET/HEAD 만, 도메인 허용목록 = ko.wikipedia.org, en.wikipedia.org
  (tools/scripts/grounded.py 가 쓰는 유일한 외부 자원). POST/업로드 차단 → 정보 유출 경로 최소화.
- 실험 대상은 전용 사용자(sudo 없음) + systemd 서비스(자원 제한: CPUQuota, MemoryMax, TasksMax).

## 감시 (3중 울타리)
1. 자동 차단: watchdog(규칙 위반 시 서비스 정지) + 출력 nftables 카운터 tripwire + AIDE 파일 무결성.
2. 정기 점검: 빌드 PC 가 SSH 로 journald/auditd/행동 로그를 pull(대상은 쓰기 권한 없음). 대시보드.
3. 사용자 최종 판단: 권한 단계 상향(파일/셸/웹읽기 → 화면/입력 → 자기코드수정)은 사용자 승인으로만.
- snapper 타임라인 스냅샷(Btrfs) → 언제든 이전 상태로 롤백.

## 준비물 (완료, laptop/debian/)
- `debian-13.7.0-amd64-netinst.iso` (792MB). SHA256SUMS 일치 + Debian CD 서명 키(DF9B 9C49 EAA9 2984 3258 9D76 DA87 E80D 6294 BE9B) 서명 검증 Good.
- `preseed.cfg`: 무인 설치. **모델명에 "850 EVO" 가 들어간 디스크만** 설치 대상(못 찾으면 멈춤) → HDD 보호.
  MBR + Btrfs 루트 + swap 16GB, GRUB 을 SSD 에. root 잠금, 관리자 `lab` 은 암호 잠금 + 빌드 PC 키로만 SSH.
  Wi-Fi 암호는 파일에 넣지 않음(무선 설치 시 설치기가 물음. 유선이면 자동).
- `lab-setup.sh`: 첫 부팅 후 실행. 영구 저널, snapper, 실험 대상 `mind`(sudo 없음)+mind.slice 자원 제한, auditd, AIDE, nftables 격리.
- `serve_install.sh`: 설치 중 빌드 PC 에서 이 폴더를 HTTP(8000)로 제공.
- 검증(Docker debian:trixie): `debconf-set-selections -c preseed.cfg` OK, `bash -n lab-setup.sh` OK,
  설치 패키지 25개 전부 trixie 에 존재, nftables 규칙 `nft -c` OK. (실제 설치는 아직 안 함.)

## 실행 절차 (사용자 승인 후)
1. 착수 조건 1~4 확인.
2. USB(1GB 이상, 내용 지워짐)에 ISO 기록: Rufus 의 "DD 이미지 모드" 또는 balenaEtcher.
3. 빌드 PC: `bash laptop/debian/serve_install.sh` (빌드 PC IP 가 192.168.0.125 인지 먼저 확인. 바뀌었으면 preseed URL 2곳·lab-setup.sh 수정).
4. 노트북: 랜선 연결 → USB 꽂고 전원 → F9 → USB 선택 → Advanced options → Automated install
   → `http://192.168.0.125:8000/preseed.cfg` 입력. 이후 자동 진행, 재부팅.
5. 빌드 PC: 공유기에서 노트북 새 IP 확인(가능하면 DHCP 고정 할당) →
   `ssh -i ~/.ssh/hp_laptop_ed25519 lab@<IP> sudo /root/lab-setup.sh`
6. 빌드 PC: `tools/venv/Scripts/python.exe tools/scripts/readonly_gateway.py --bind 192.168.0.125 --allow <노트북IP> --log logs/gateway.jsonl`

## 설치 후 첫 검증
- llama.cpp Vulkan/CUDA 빌드로 t55 Q4_K_M 재측정(Windows 기준선 10.07 tok/s 와 비교).
- eval_quality.py / eval_grounding.py 를 프록시 경유로 다시 돌려 Windows 결과와 같은지 확인.
