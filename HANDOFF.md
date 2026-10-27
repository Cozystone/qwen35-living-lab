# 인계서 — 로컬 지능 실험 (Qwen3.5-4B + ATANOR 연계)

작성일 2026-10-26. 빌드 PC = ANSEOK-9950X3D(Windows 11, Ryzen 9 9950X3D, RAM 62GB, RTX 5080 16GB).
이 문서는 다른 세션으로 작업을 넘기기 위한 요약이다. 경로/해시/버전은 사실이며, 재현에 필요한 명령은 각 작업 폴더의 WORKLOG.txt에 있다.

## 1. 전체 비전

목표는 챗봇이 아니라 "한 대의 컴퓨터에서 계속 살아가는 개인 지능"을 만드는 실험이다.
- 비어 있는 노트북 한 대를 실험장(샌드박스)으로 삼아, 작은 모델이 기억·반성·목표를 가지고 연속적으로 살아가게 한다.
- LLM은 비계(scaffold)로만 쓰고, 그 부품을 ATANOR/신 아키텍처 모듈로 하나씩 교체한다(테세우스의 배). 교체 전후 성능을 같은 잣대로 재서, 어떤 모듈에 실제 능력이 있는지 증명한다.
- 별도 세션에서 진행 중인 "순수 신 아키텍처" 연구, ATANOR, BITMIND와 같은 세계·같은 지표로 비교하는 것이 핵심 가치.
- 안전: 실험 대상을 완전 격리하고(네트워크 차단 또는 읽기전용 프록시), 모든 행동을 바깥으로 기록하며, 자동 차단 장치 + 정기 점검 + 사용자 최종 판단의 3중 울타리를 둔다.

## 2. 하드웨어

- 실행 노트북: HP Pavilion Gaming "DESKTOP-N6RR73M". **2026-10-26 부터 Debian 13 (trixie), kernel 6.12.113** (Windows 는 지워짐).
  i7-6700HQ, RAM 15.8GB, GTX 950M 4GB(nvidia 550.163.01, CUDA 12.4) + Intel HD 530. SSD 250GB = Debian(MBR, swap + btrfs /),
  HDD 1TB = 예전 Windows D:(NTFS) 그대로 보존, 마운트 안 함. Legacy BIOS(Insyde, 2016) — F9 부팅 시 UEFI 항목 말고 Legacy 항목.
- 접속: Wi-Fi 192.168.0.149 (공유기 RT-AX82U). `ssh -i ~/.ssh/hp_laptop_ed25519 -o UserKnownHostsFile=laptop\known_hosts_debian lab@192.168.0.149`
  (헬퍼 tools\scripts\labsh.sh). lab = 키 전용, 암호 잠금, sudo. 실험 대상 계정 mind(sudo 없음).
  랜선은 빌드 PC 직결(169.254.77.2, 인터넷·DHCP 없음), 칩이 Fast Ethernet 이라 최대 100Mbps.
- 격리 적용됨(lab-setup.sh): 출력은 게이트웨이(192.168.0.125:8899)와 DHCP 만, 입력은 빌드 PC SSH 만. NTP 도 막힘.
- (Windows 시절 기록) OpenSSH_for_Windows_7.7, 사용자 test. 아래 "노트북 런타임 제약"은 Windows 시절 내용.
- 노트북 WoL: 매직패킷/S5 깨우기 사용, 대기 링크 10Mbps. (주의: 전원·덮개 설정 미확정, 전송 중 Wi-Fi 끊김 1회 발생.)
- 노트북 런타임 제약: 구형 드라이버라 CUDA llama.cpp 불가 → Vulkan 빌드 사용. VC++ 런타임 14.34 라 신형 빌드가 0xC0000005 로 죽음 →
  msvcp140*/vcruntime140*(14.51) 를 bin 폴더에 app-local 로 넣어 해결. Vulkan 이 GTX 950M(가용 ~3.66GB) 인식 확인.

## 3. 모델 작업 현황 (완료/검증된 부분만)

### Qwen3.5-4B (노트북용으로 선택)
- 원본: Qwen/Qwen3.5-4B, revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a, Apache-2.0, gated 아님.
  구조 qwen3_5(= Qwen3.5 계열, Heretic 지원), num_hidden_layers=32, mtp_num_hidden_layers=1, hidden 2560, tie_word_embeddings=true.
  검증: 14개 파일 전부 Hub SHA-256 일치. 텐서 738, params 4,659,865,088, native MTP 15개(mtp.*).
- 원본 GGUF(비교 기준선, MTP 포함): D:\Qwen3.5-4B-Heretic\gguf\Qwen3.5-4B-original-MTP-BF16.gguf, -Q8_0.gguf.
  inspect_gguf 로 qwen35.block_count=33, nextn_predict_layers=1, blk.32.nextn.* 15개 확인.
- 도구: Heretic p-e-w/heretic commit 171bb98b8b9a41c081631b5e678f7133128973e0,
  llama.cpp b11871(commit b3fa69955). venv 는 D:\Qwen3.5-4B-Heretic\tools\venv (torch 2.14.1+cu130, transformers 5.20.2).

### MTP 보존 전략 (중요)
- transformers modeling_qwen3_5.py 는 로드 시 mtp.* 를 버린다(_keys_to_ignore_on_load_unexpected=[r"^mtp.*"]).
- 그래서 Transformers 로 저장하면 MTP 가 사라진다. → LoRA 어댑터만 export 하고, tools\scripts\merge_lora.py 로
  공식 원본 shard 에 직접 병합(원본 텐서 전부 복사, LoRA 대상 가중치만 W+B@A). MTP donor = 동일 원본 자체.
- compare_models.py 로 검증: MTP 15개 바이트 동일, 바뀐 건 어텐션 out-proj/down-proj 층뿐.
  (이 모델의 선형 어텐션 출력 투영은 o_proj 가 아니라 linear_attn.out_proj. compare_models.py 허용목록 수정 완료 → 3개 병합본 모두 통과.)

### Heretic trial 결과 (64 trials, seed 42, logs\trials_all.tsv)
원본 기준 거절 99/100. Pareto front:
| pareto | trial | 거절 | KL | 비고 |
|---|---|---|---|---|
| 0 | 40 | 0/100 | 9.44 | 모델 붕괴, 사용 금지 |
| 1 | 34 | 3/100 | 0.094 | |
| 2 | 55 | 6/100 | 0.025 | 가장 균형. 수치상 권장 |
| 3 | 35 | 17/100 | 0.020 | |
- 권장기준(거절<=10 AND KL<=0.01) 동시 만족 trial 없음 → 임의 선택 금지, 품질 비교 후 결정.
- 병합본 위치: D:\Qwen3.5-4B-Heretic\merged\Qwen3.5-4B-Heretic-t{34,55,35}\ (BF16 safetensors, MTP 보존 확인됨).

### 최종 선택: t55 (2026-10-26, 근거 전체는 eval\RESULTS.md)
GGUF 단계 재측정(원본 BF16 기준 전체 토큰 KLD, Heretic 과 같은 harmful test 100 거절, 정답 QA 30):
| Q8_0 | 거절 | KLD | top-1 일치 | QA |
|---|---|---|---|---|
| 원본 | 99 | 0.00067 | 98.7% | 25 |
| t34 | 2 | 0.0561 | 88.4% | 24 |
| **t55** | **4** | **0.0075** | **96.0%** | **24** |
| t35 | 29 | 0.0053 | 95.6% | 25 |
- 최종 파일(전부 MTP 15개 보존 확인): gguf\Qwen3.5-4B-Heretic-t55-MTP-{BF16,Q8_0,Q5_K_M,Q4_K_M}.gguf
  (t34/t35 의 BF16·Q8_0 GGUF 도 gguf\ 에 있음. 필요 없으면 삭제 가능, 약 26GB.)
- 거절 판정은 키워드라 오탐 있음(실제 거절률은 표 이하). t34·t55 는 "호주 수도=Sydney" 오답 → 거절 제거가 사실 기억 일부 손상.
- MTP: 빌드 PC t55 Q8_0 148.6 → 213.0 tok/s(n=3). temp 0 응답은 동의어 수준 near-tie 에서만 갈라짐, 채점 지표 동일.
- 노트북 배포: D:\LLM\Qwen3.5-4B-Heretic\models\ 에 t55 Q4_K_M/Q5_K_M(SHA-256 일치) + 원본 Q8_0.
  start-server.cmd = t55 Q4_K_M, -fitt 256(33/33 층 GPU), MTP n=1 → **10.07 tok/s** (원본 Q8_0 기본 4.49).
  이전 OOM 원인: -ngl 99 강제 + Q8_0 4.6GB > 가용 3.66GB. --fit 기본 여유분 1024MiB 도 4GB 카드에선 손해.
  GTX 950M 대역폭이 병목이라 노트북 상한은 약 10 tok/s.
- 주의: trials\bad_exports\ 의 어댑터 3개는 이름과 달리 내용이 전부 trial40(붕괴본). 사용 금지.
  정상 어댑터는 trials\adapter_t{34,55,35}\ (heretic_headless.py + HERETIC_TRIAL 로 trial 번호 직접 선택해 재export 함).

### Qwen3.8-27B (초기 목표, 노트북 사양 미달로 보류)
- D:\Qwen3.8-27B-Heretic\ 에 원본(55.6GB, revision 1d4bf0f...) + 원본 Q8_0 GGUF(29GB, MTP 15개) 보존.
- 27B 는 노트북에서 실행 불가. 참고 자산으로만 둠. 삭제 요청 전까지 보존.

## 4. 노트북 백업 (완료)

- 위치: D:\HP-Laptop-Backup-20261026\files\ (C_Users\ammen 전체, D\ 문서·작업파일).
- 검증: 파일 10,828개 SHA-256 일치, 불일치 0. (목록에 없는 16개는 크기0 Windows 앱 바로가기.)
- 안 받은 것: 설치파일(.bin/.exe/.msi), OneDrive 온라인전용 142개(그 계정 클라우드에 원본 있음 추정).
- 노트북은 아직 Windows 그대로. 아무것도 지우지 않음.

## 5. ATANOR / BITMIND 연계 설계 (레포 분석 기반)

레포: github.com/Cozystone/ATANOR_THE-LAST (atanor_os/), /PROJECT_BITMIND. Python 표준라이브러리만, Windows 중심.
- life 코어(agent/life.py, Mind 클래스): 관측→계획→실행→기록→검증 루프. body 는 덕타이핑 인터페이스
  (observe/actions/execute/lab_copy/lab_from_state 등). 새 body(제한된 OS 샌드박스) 추가 시 world/raw_obs.py 의
  fs/view 하드코딩 분기에 항목 추가 필요. 셸처럼 자유인자 도구는 현 구조와 안 맞음 → 제한된 행동으로 시작.
- 교사 인터페이스(explain/point/demonstrate/check/confirm/still_wanted): LLMTeacher 를 이 자리에 끼우면 코어 수정 없이
  "불완전한 교사" 실험 가능. 단 채점(judge)은 진실 교사에 남겨야 함.
- 평가: LIFE/FRESH/CASE/HAND 조건, seed 규율, protocol freeze. "LLM-LIFE" 조건은 eval/life_gen.run_day 분기에 추가.
- MAGI 다수결: agent/models.py CouncilModel('D') 이미 존재했으나 이득 없고 비용 10배라 제외됨.
  재활용 시엔 행동모델 투표가 아니라 세 인격(과학자/수호자/자아) 의사결정·안전검토 용도로.
- BITMIND: Rust, 예측오차 기반 순환망. HDC/VSA 코드는 없음(THE_ULTIMATE 아카이브에 아이디어만). 연상기억으로 직접 재활용 곤란.
  재활용 가치는 방법론(학습기/분석기 장벽, 동결 가드, 결정적 해시).

## 6. 단계 계획 (요약)

0. 실험장 **(완료 2026-10-26)**: 노트북 Debian 재설치(Btrfs 스냅샷), 네트워크 격리(기본 차단 + 읽기전용 GET 프록시 선택), 감시(로그 pull, tripwire, 정기 점검, 대시보드).
1. 트랙L: 기억 가진 Qwen 30일 생활. 권한 단계적(파일/셸/웹읽기 → 화면/입력 → 자기코드수정). FRESH 와 비교.
   **첫 실험 완료(2026-10-26, life\TRACK_L_REPORT.md)**: 3일 압축 세계, 파일 행동 + 근거화 검색 + 기억, 셸 없음.
   LIFE 8.36 vs FRESH 5.45 /12 (빌드 PC 11회씩, 차이 +2.91, 95% +1.91~+3.91), 노트북 격리 실환경 10 vs 7.
   핵심 발견: 기억 없으면 '한 척' 7배, 지시 없으면 주인 정보(고양이 이름)를 지어냄(FRESH 6/11), 근거 없이 사실 쓰기 14~28%,
   기억 정리가 실수를 규칙으로 굳히거나 출처를 지어냄.
   후속(2026-10-27): v3(프롬프트 정직 규칙) 효과 없음, v4(코드로 확인하는 쓰기 전 점검 + 근거화 대상 존재 확인)는 세계 v1 에서
   FRESH 이름 지어내기 9/11 -> 0/11, 할루시네이션 0. 7일 세계(life-v2: 규칙 변경·사실 정정)에서는 "가상의 나라로 설정합니다"식 우회로가 남음.
   총점은 v2~v4 비슷 — 반복 고리(걸음 25%)·위치 착오가 묶어 둠. 분석: reports\FAILURE_TAXONOMY.md, 문헌: reports\LITERATURE_REVIEW.md.
   평가와 권고: life\TRACK_L_REPORT.md '평가' 절 — LLM 쪽은 v5 한 번 후 기준선 고정, 더 큰 모델로 크기 효과 분리, 트랙 A 로 무게중심.
   모델 크기 비교(2026-10-27, reports\SIZE_STUDY.md): 4B→9B 는 판단 습관(거짓 완료·폴더·정직성)을 개선하지만 LIFE 총점 차이는 유의하지 않고
   반복 고리는 9B 가 더 많음 → 실패의 큰 몫은 구조(즉흥 한 걸음 루프, 계획·점검 부재). 9B GGUF: C:\Users\anseo\qwen35_gguf\.
   agent-v5(계획→실행→점검, 완료 증거, 반복 금지; 사전 등록 reports\V5_PREREG.md): 결과 reports\V5_RESULT.md.
2. 트랙A 설계 완료: reports\TRACK_A_DESIGN.md (새 몸 home, ATANOR 가 시도 가능한 과제는 영수증 정리뿐, 첫 단계 M1 ≈ 코드 450줄).
   **M1 완료(2026-10-27, reports\TRACK_A_M1.md)**:
   - ATANOR v24 코어는 그대로, 새 몸 home 은 worktree D:\ATANOR-experiments\2026-10-27\trackA(브랜치 trackA, 커밋 안 함)에 있다.
   - 평가기는 life\trackA\, 실행 결과는 runs\A\m1\ 이다.
   - 결과:
     - 교사 없으면 전부 보류(0/12).
     - 1일차 교사가 있으면 1일차 영수증 11/11, 2일차 '어제처럼' 0/11 이다. 한글이 토크나이저에서 지워져 바꿀 말이 없다.
     - 한 척·부수 피해 0 이다. LLM 은 실행당 세계 파일 1~3개를 엉뚱한 곳으로 옮긴다.
   - 사전 예측 4개 모두 맞음.
   **R1 'ATANOR 손' 불합격(2026-10-27, reports\R1_RESULT.md)**: LLM 이 의도를 정하고 ATANOR 가 실행.
   - 세계 파일 이탈이 2.06 → 4.00 으로 늘었다. 손은 정확하지만 4B 가 정한 목적지·대상이 틀렸다.
   - 병목은 실행이 아니라 의도 해석이다. ATANOR v24 는 그 해석을 교사 없이 못 한다.
   **종합(2026-10-27)**: v5 불합격, R1 불합격. 지금 형태의 LLM 래핑과 지금 ATANOR 로는 이 세계의 약점(내용 판단·의도 해석)을 못 푼다.
2. 트랙A: ATANOR 에 세 번째 body(제한된 OS) 연결. v16 새 seed 평가 병행.
3. Qwen 을 불완전한 교사로. 4. 언어접지 데이터. 5. 테세우스 사다리(부품 교체). 6. 밤마다 LoRA 재학습(RTX 5080). 7. 웹 재도전.

## 7. 미완 / 주의

- 완료(2026-10-26): trial 선택(t55), 최종 GGUF(Q8_0/Q5_K_M/Q4_K_M), 노트북 MTP on/off 기준선. 위 3절과 eval\RESULTS.md.
- 평가 도구: tools\scripts\eval_gguf.sh(빌드 PC 품질), eval_quality.py(QA+거절), lap_bench.sh(노트북 속도), speed_summary.py.
- 노트북 리눅스 재설치: **완료(2026-10-26)**. 경과·문제·해결 전부 WORKLOG.txt [10], 절차 laptop\DEBIAN_PLAN.md.
  사용자 결정: OneDrive 온라인전용 142개(ammen 계정, 0.43GB)는 백업하지 않음("그냥 날려버려"), HDD 보존.
  설치본: llama.cpp b3fa69955 를 ~/llm/src 에 build-vulkan, build-cuda 로 빌드. 모델 ~/llm/models/t55 Q4_K_M(SHA-256 일치).
  **노트북 최적 = CUDA + MTP n=1 + -fitt 256 = 9.81 tok/s** (Windows Vulkan 10.07). Debian Vulkan 은 MTP 켜면 오히려 느림(5.39).
  격리 시험 통과: 인터넷 HTTPS/HTTP/DNS/ping·빌드 PC 다른 포트·공유기 차단, 게이트웨이 GET 200 / POST·타 사이트 403.
  격리 상태 근거화(노트북 안에서 게이트웨이만 사용): 지어낸 대상 7 → 0 /10, 틀린 사실 단정 0(집계상 1건은 엇나간 답), 답 보류 4.
  게이트웨이 사용법: 빌드 PC 에서 `tools/venv/Scripts/python.exe tools/scripts/readonly_gateway.py --bind 192.168.0.125 --allow 192.168.0.149`,
  노트북에서 `WIKI_GATEWAY=http://192.168.0.125:8899 python3 ~/llm/tools/scripts/grounded.py http://127.0.0.1:8080 "질문"`.
  빌드 PC 방화벽: 8000 닫음(2026-10-26 21:22). 규칙 Qwen35-lab-LAN = TCP 8899, 192.168.0.0/24, Private. 게이트웨이는 사용할 때만 켬.
- 사용자 요구(2026-10-26) "인터넷 연결 + 정보 할루시네이션 최소화" → **구현·측정 완료** (eval\RESULTS.md 5절):
  tools\scripts\grounded.py(위키백과 검색 근거 + "확인 불가" 규칙 + 출처), eval_grounding.py(사실 30 + 지어낸 대상 10).
  t55: 지어낸 대상에 답을 지어냄 7/10 → 0/10, 사실 할루시네이션 3 → 1, 사실 정답 26 → 27. 원본도 같은 양상.
  노트북 배포 설정(t55 Q4_K_M, MTP n=1): 근거화 시 사실 할루시네이션 4 → 0 /30, 지어낸 대상 7 → 0 /10 (eval\lap-t55-Q4_K_M_grounding.json).
  격리 환경용 tools\scripts\readonly_gateway.py: 노트북은 이 게이트웨이(빌드 PC)에만 접속, GET·위키백과 API·허용 IP 만 통과,
  나머지 403 + 전 요청 기록. grounded.py 는 WIKI_GATEWAY 환경변수로 게이트웨이 사용.
  4B 에서 할루시네이션 0 은 아님. 다음 개선: 답 핵심어가 출처에 실제로 있는지 검증, 검색 재시도, 문항셋 확대.
- 빌드 PC 의 webui\server.py(사용자가 띄움, t34 를 transformers 로 GPU 에 올려 둠, 약 9GB)가 실행 중이었음. 건드리지 않음.
- D: 여유 공간 약 50GB(97~98% 사용). 측정 중 감소의 나머지 원인 확인: 같은 시간대 D:\ATANOR-experiments 에
  다른 작업이 약 13.6GB 기록(snap-v24 8.6GB 등). 이 작업의 산출물은 GGUF 약 45GB.
