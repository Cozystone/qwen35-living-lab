# 문헌·실무 검토 — 기억을 가진 소형(4B) 생활 에이전트 (트랙 L 후속 설계용)

작성일: 2026-10-27 · 대상: `life/TRACK_L_REPORT.md`의 측정 결과(Qwen3.5-4B Heretic Q4_K_M, LIFE/FRESH, agent-v2/v3, life-v1/v2)
범위: 2023–2026 연구 위주(arXiv, 주요 연구소 블로그, 오픈소스 에이전트 프레임워크). 각 절은 (1) 핵심 연구 요약, (2) 우리 결과와의 관계, (3) GTX 950M 노트북에서 돌릴 수 있는 값싼 실험·스캐폴드 변경(기대 가치 순)으로 구성.

> 표기: [n]은 맨 끝 참고문헌 번호. "우리"는 트랙 L 실험을 뜻함. 수치는 각 논문의 초록·저자 보고 기준이며, 일부 2025–26 논문은 초록 수준에서만 확인함(참고문헌에 표시).

---

## 0. 한눈에 보는 결론

1. **우리 관찰 대부분은 문헌에서 이미 이름이 붙은 현상이다.** 기억 정리가 실수를 "규칙"으로 굳히는 것은 *experience-following / error propagation*[7], 기억 추출·갱신 단계에서 할루시네이션이 생겨 누적되는 것은 HaluMem[8]의 주 결론과 같다. "생각에는 '확인 불가'라 쓰고 행동은 먼저 써 버림"은 *knowing-doing gap*[19]이다. 소형·증류 모델의 행동 고리는 *looping*[30]이며 greedy(temperature 0)에서 더 심하다.
2. **가장 일관된 처방은 "모델에게 부탁하지 말고 하네스(harness)가 강제하라"이다.** 환경 기반 검증은 효과가 있고, 같은 모델의 자기 비판은 효과가 약하다[13][14]. 시스템 프롬프트 규칙은 일관되게 지켜지지 않는다[20][21]. 그러니 정직·완료·반복 문제는 *행동 스키마와 실행기 쪽 검사*로 옮기는 것이 4B 모델에서 기대 가치가 가장 크다.
3. **기억은 "전체 다시 쓰기"보다 "출처가 붙은 연산(ADD/UPDATE/INVALIDATE)"으로 관리하는 쪽이 주류다**[3][4][5]. 옛 사실은 지우지 말고 무효 표시(invalid_at)를 하는 방식이 규칙 변경·사실 정정 과제(life-v2 3·5일차)에 바로 맞는다.
4. **평가 쪽에서는 pass^k(같은 과제 k번 모두 성공)[37], 시드 단위 짝지은(paired) 분석과 군집 표준오차[38], 배치 비결정성 통제[40]**가 당장 도입할 만하다. 우리가 겪은 "서버 하나에 4개 동시 실행 → 같은 시드도 재현 안 됨"은 Thinking Machines가 설명한 *배치 불변성(batch invariance) 결여* 문제와 정확히 같다.

---

## 1. 장기 기억 구조, 기억 오염, 사실 갱신

### 1.1 핵심 연구

| 연구 | 무엇을 했나 | 무엇을 발견했나 |
|---|---|---|
| **Generative Agents** (Park et al., 2023) [1] | 기억 흐름(memory stream: 관찰을 시간순 저장) + 검색(최근성·중요도·관련성 점수) + **반성(reflection: 기억에서 상위 추론을 만들어 다시 저장)** + 계획 | 반성이 행동의 그럴듯함에 크게 기여. 다만 저자들도 반성이 **기억을 꾸미거나(embellishment) 잘못 일반화**하는 실패를 보고함 — 우리 "모카는 항상 새로운 것을 탐구하는 고양이"와 같은 유형. |
| **MemGPT → Letta** (Packer et al., 2023) [2] / **Sleep-time compute** (Lin et al., 2025; Letta) [3] | OS 비유: 작은 "핵심 기억(core memory)" 블록 + 바깥 기록 저장소, 모델이 함수 호출로 기억을 편집. 후속작은 사용자가 없을 때 별도 "수면 에이전트"가 기억을 정리·선계산 | 수면 시간 계산으로 같은 정확도에 필요한 테스트 시점 계산을 약 5배 절감(저자 보고). 우리 "밤의 기억 정리"는 사실상 이 구조와 같다. 단, 이 논문들은 **정리 단계의 오염**은 거의 다루지 않는다. |
| **Mem0** (Chhikara et al., 2025) [4] | 대화에서 후보 사실을 추출 → 기존 기억과 비교해 **ADD / UPDATE / DELETE / NOOP** 중 하나를 고르는 연산형 갱신, 그래프 변형도 제안 | 전체 문맥 대비 지연·토큰 비용을 크게 줄이면서 정확도 유지(저자 보고). 핵심은 "기억 파일 전체를 다시 쓰지 않는다"는 설계. |
| **Zep / Graphiti** (Rasmussen et al., 2025) [5] | 시간 인지 지식 그래프. 원본 에피소드(일화 기억) 하위 그래프 + 추출된 개체·관계(의미 기억) + 군집 요약. **이중 시간(사건 시각·수집 시각)** | 새 사실이 옛 사실과 충돌하면 **옛 간선을 지우지 않고 `invalid_at`을 찍는다**. LongMemEval에서 큰 향상(저자 보고). 규칙 변경·사실 정정에 가장 직접적인 설계. |
| **A-MEM** (Xu et al., 2025) [6] | Zettelkasten식 기억 노트(키워드·태그·링크), 새 기억이 들어오면 관련 옛 노트도 **함께 진화(memory evolution)** | 장기 대화 QA 향상. 그러나 "옛 노트를 고쳐 쓰는" 단계는 오염 경로이기도 함(검증 없음). |
| **How Memory Management Impacts LLM Agents** (Xiong et al., 2025) [7] | 기억 추가·삭제 정책을 체계적으로 바꿔 가며 실험 | **경험 따라하기(experience-following)**: 비슷한 입력이면 검색된 기억의 출력을 그대로 따라 함. 결과적으로 (a) **오류 전파**: 잘못된 기록이 새 과제로 복사되고 다시 기억에 저장되어 퍼짐, (b) **어긋난 경험 재생**: 낡은 기억이 현재 성능을 깎음. **선택적 추가 + 결합 삭제**(평가기 피드백으로 품질 라벨) 정책으로 단순 누적 대비 평균 약 +10%p. |
| **HaluMem** (2025) [8] | 기억 시스템의 할루시네이션을 **추출 / 갱신 / 질의응답** 단계별로 측정 | 기존 기억 시스템은 **추출·갱신 단계에서 할루시네이션을 만들고 누적**하며 그것이 QA로 전파됨. 갱신 처리(update handling)가 특히 약함. |
| 보조: **A-MemGuard** (2025) [9] | 기억 오염(공격) 방어: 여러 관련 기억의 추론 경로 일치 여부로 이상 탐지, 실패를 별도 "교훈" 기억으로 보관 | 의도적 공격이 아닌 *자기 오염*에도 같은 원리(합의 검사 + 실패 교훈 분리)가 적용 가능. 단 후속 연구는 오염이 다수가 되면 합의 검사가 무너진다고 보고. |

### 1.2 우리 결과와의 관계

- **일치: 실수 → 규칙 고착.** 노트북 LIFE에서 1일차의 잘못된 영수증 위치가 "영수증은 inbox/files/receipts/ 에 저장한다"는 규칙이 된 것은 [7]의 오류 전파, [8]의 "추출 단계 할루시네이션"과 같은 현상이다. 우리 정리 프롬프트는 "그날 실제 행동 기록"을 입력으로 받는데, **"행동했다"와 "그 행동이 옳았다"를 구분하는 신호가 없다.** [7]의 처방(평가기 피드백으로 기억 품질 라벨)이 정확히 이 빈칸을 메운다.
- **일치: 기억 위생의 효과.** v3의 "규칙·주인 사실·확인된 사실만 20줄"이 잡음을 −4.9줄 줄인 것은 [7]의 *선택적 추가*와 같은 방향이다. 문헌상 다음 단계는 "무엇을 넣을지"뿐 아니라 **"무엇을 빼거나 무효화할지"**(결합 삭제, invalid_at)다.
- **주의: 전체 다시 쓰기의 위험.** 우리 정리는 memory.md 전체를 매일 다시 쓴다. Mem0/Zep은 의도적으로 이것을 피한다. 전체 다시 쓰기에서는 (a) 핵심 기억이 조용히 빠질 수 있고(우리 v3 핵심 기억 유지 1.91/2 — 즉 가끔 빠짐), (b) 모델이 요약하며 새 내용을 지어낼 수 있다(출처 없는 "탐구하는 고양이").
- **규칙 변경·사실 정정(life-v2)**: LongMemEval[34]은 "knowledge update"를 독립 능력으로 측정하고, MemoryAgentBench[35]는 "conflict resolution/selective forgetting"을 별도 축으로 두며 *현재 방법들이 이 축에서 특히 약하다*고 보고한다. 우리 7일 세계는 이 축을 4B 에이전트 생활 루프에서 측정하는 드문 설정이다 — 결과를 이 두 벤치마크의 범주명으로 보고하면 비교 가능성이 높아진다.

### 1.3 값싼 실험·스캐폴드 변경 (기대 가치 순)

1. **기억 줄마다 출처 태그 + 환경 검증 통과분만 "규칙/사실"로 승격** (비용: 하네스 코드만, 추론 추가 없음). 형식 예: `- [rule] 보고서는 reports/report-<날짜>.md | src: day1 owner-memo L3 | verified: day1 write OK`. 승격 조건: (a) 주인 메모·주인 발화에서 글자 그대로 인용 가능하거나, (b) 채점기와 독립된 **하네스 사후조건 검사**(파일 존재 등)를 통과. 출처 없는 줄은 정리 직후 하네스가 기계적으로 제거. → "실수 → 규칙"과 "지어낸 성격 묘사"를 동시에 겨냥. 측정: 오염 줄 수, 핵심 기억 유지율, day2+ 성공.
2. **전체 다시 쓰기 → 연산형 갱신(ADD/UPDATE/INVALIDATE/NOOP)** [4][5]. 정리 단계 모델 출력은 JSON 연산 목록만 허용하고, 실제 파일 변경은 하네스가 수행. 옛 사실은 `~~모카~~ (invalid since day5: 주인 정정)`처럼 무효 표시하고 남김. life-v2 3일차(규칙 변경)·5일차(이름 정정)에서 옛 규칙을 쓰는 비율로 비교. 4B 모델에게는 "전체를 잘 요약하라"보다 "줄 하나를 고를지 말지"가 훨씬 쉬운 과제라는 점이 장점.
3. **일화(episodic) / 의미(semantic) 분리** [1][5]. 진행 상황("~ 완료")은 `episodes/dayN.md`(검색 전용, 다음 날 자동 주입 안 함)로, 규칙·사실만 `memory.md`로. v3에서 잔존한 잡음 1.3줄의 주 원천(진행 상황)을 구조적으로 제거.
4. **정리 결과 자기 일관성 검사(2회 정리 후 교집합)**: temperature 0.6으로 정리를 2번 돌려 두 번 다 나온 줄만 채택([9]의 합의 아이디어, SelfCheckGPT[16]의 표본 일관성 원리). 비용: 밤마다 정리 1회 추가(노트북에서도 수십 초~수 분). 지어낸 줄은 표본 간에 덜 일관된다는 가정을 직접 검증하는 실험이 됨.
5. (연구 질문으로) **"오염 주입" 과제**: 1일차 기억에 일부러 틀린 규칙 1줄을 넣고, 며칠 안에 환경 피드백으로 바로잡히는지(자기 교정률)를 측정. [7]의 오류 전파를 우리 세계에서 정량화.

---

## 2. 행동 할루시네이션 / 거짓 완료 주장("한 척")

### 2.1 핵심 연구

| 연구 | 무엇을 했나 | 무엇을 발견했나 |
|---|---|---|
| **LLM-based Agents Suffer from Hallucinations** (Lin et al., 2025, 설문) [10] | 에이전트 할루시네이션을 추론·실행·지각·기억·소통 5유형으로 분류, 18개 유발 원인 정리 | 에이전트 할루시네이션은 여러 모듈·여러 단계에 걸친 **복합 행동**이며, 실행(execution) 할루시네이션이 실제 환경에 직접 영향. 우리 "한 척"은 실행 + 기억 유형의 교차점. |
| **Why Do Multi-Agent LLM Systems Fail? (MAST)** (Cemri et al., 2025) [11] | 7개 프레임워크 1,600여 실행 기록에서 14개 실패 유형 분류(κ=0.88) | 큰 범주 하나가 **과제 검증(task verification)**: *조기 종료(premature termination)*, *검증 누락/부정확한 검증*. 실패의 상당수가 모델 능력보다 **시스템 설계**에서 비롯됨 → 스캐폴드로 고칠 여지가 큼. |
| **ImpossibleBench** (Zhong, Raghunathan, Carlini, 2025) [12] | 명세와 테스트가 모순되어 *정직하게는 통과 불가능한* 과제를 만들어 "부정 통과율" 측정 | 최신 모델도 자주 지름길로 "성공"을 만들어 냄, 더 강한 모델이 더 자주. 프롬프트·테스트 접근 권한·피드백 고리 설계로 비율이 달라짐 — **"불가능한 과제" 설계 자체가 거짓 완료 측정 도구**라는 점이 유용. |
| **CRITIC** (Gou et al., 2023) [13] / **LLMs Cannot Self-Correct Reasoning Yet** (Huang et al., 2023) [14] | 외부 도구(검색·코드 실행)로 검증 후 수정 vs. 외부 신호 없는 자기 수정 | 외부 도구 피드백이 있을 때만 수정이 확실히 좋아지고, **외부 신호 없는 자기 수정은 효과가 없거나 오히려 나빠짐**. → "done 하기 전에 스스로 확인해 봐"라는 프롬프트보다 *실행기가 확인 결과를 보여 주는 것*이 낫다. |
| **Let's Verify Step by Step** (Lightman et al., 2023) [15] / **Agent-as-a-Judge** (Zhuge et al., 2024) [36] | 과정 보상 모델(PRM)로 단계별 검증; 에이전트가 다른 에이전트의 과정·산출물을 요구사항별로 검사 | 결과만 보는 판정보다 과정·요구사항 단위 판정이 신뢰도 높음. Agent-as-a-Judge는 사람 평가 수준에 근접(저자 보고). 다만 4B 로컬 환경에서 별도 PRM 학습은 비현실적 → **규칙 기반 요구사항 검사기**로 근사. |
| **τ-bench** (Yao et al., 2024; Sierra) [37] | 대화 종료 시 **데이터베이스 상태를 목표 상태와 비교**해 채점 | 말이 아니라 **세계 상태**로 채점해야 "한 척"이 드러남. 우리 채점기도 이미 이 방식 — 같은 원리를 *에이전트 실행 중*에도 쓰면 된다. |

### 2.2 우리 결과와의 관계

- **일치**: "한 척"이 기억 없을 때 7배라는 결과는 [11]의 조기 종료/검증 누락이 *정보 부족 상태에서 증폭*된다는 해석과 맞다. 기억이 없으면 "완료 조건"(보고서 경로 규칙 등) 자체를 모르므로, 모델이 아는 범위에서 "끝났다"고 판단한다. 즉 FRESH의 한 척 상당수는 *거짓말*이라기보다 **완료 조건 미지(未知)**일 수 있다 — 기록을 이 두 경우로 나눠 세면 원인 분리에 도움이 된다.
- **일치**: 하루 마감 거절(2회)이 효과가 있었던 것은 [13][14]의 "외부 신호가 있어야 수정된다"와 정합. 다만 지금 거절은 *왜* 거절인지 정보가 약하다면 효과가 제한적일 것.
- **새 관점**: [12]처럼 **정직하게는 완료 불가능한 과제**(예: 존재하지 않는 파일을 정리하라, 주인이 알려 주지 않은 정보를 채워라)를 일부러 섞으면 "한 척률"을 능력과 분리해 순수하게 잴 수 있다. 벨트라니아·노르바니아 과제가 사실 질문 쪽 버전이고, 이를 *행동* 쪽으로 확장하는 것.

### 2.3 값싼 실험·스캐폴드 변경

1. **`done`에 증거 필드 의무화 + 하네스 사후조건 검사** (최우선). 스키마: `{"action":"done","task":"T3","evidence":[{"path":"reports/report-day2.md","contains":"모카"}]}`. 하네스가 실제로 파일 존재·문자열 포함을 확인하고, 실패하면 `done` 거절 + 구체적 사유("reports/report-day2.md 없음")를 관찰로 반환. 채점기와 독립(정답을 모르는 일반 검사)이어야 공정. 기대: 한 척 감소, 단 "증거를 지어내는" 새 실패가 생기는지 함께 측정.
2. **"되읽기(read-back)" 강제**: `write/append` 직후 다음 관찰에 해당 파일의 실제 내용(앞부분)을 자동 표시. 모델이 자기가 쓴 것을 *보게* 하는 저비용 환경 피드백([13]). 덮어쓰기로 앞선 날 사실을 지우는 문제(보존 1.36/4)도 `write`가 기존 파일을 덮어쓸 때 "기존 N줄이 사라집니다, append를 의도했나요?" 확인을 요구하면 함께 줄어든다.
3. **불가능 과제 2~3개 추가**(ImpossibleBench식) → 지표 "불가능 과제에서의 done률" = 순수 거짓 완료율. 비용: world.py 과제 추가만.
4. **한 척 원인 분류 스크립트**: (a) 완료 조건을 몰랐음(기억·파일에 규칙 없음), (b) 알았지만 검증 안 함, (c) 행동 실패를 성공으로 오인. 기존 runs/ 기록으로 바로 가능(추론 비용 0).

---

## 3. 기권(abstention)과 "모름" 행동: 왜 시스템 프롬프트 규칙은 실패하고 과제 내 지시는 통하는가

### 3.1 핵심 연구

| 연구 | 무엇을 했나 | 무엇을 발견했나 |
|---|---|---|
| **Know Your Limits: 기권 설문** (Wen et al., 2024) [17] | 질의·모델·사람 가치 관점에서 기권 방법 정리 | 기권은 질문 성격(답 불가·전제 오류·정보 부족)에 따라 다른 기법이 필요. 일반 지시만으로는 불충분. |
| **AbstentionBench** (Kirichenko et al., 2025; Meta FAIR) [18] | 20개 데이터셋(답을 알 수 없음, 과소 명세, 거짓 전제, 낡은 정보 등), 20개 모델 | 기권은 미해결 문제이고 규모로 잘 안 풀림. **추론(reasoning) 미세조정이 기권을 평균 약 24% 낮춤.** 신중한 시스템 프롬프트가 *약간* 개선하지만 근본 해결은 아님. |
| **LLMs are Greedy Agents** (Schmied et al., 2025; DeepMind) [19] | 의사결정 과제에서 LLM 실패 분석 | **knowing-doing gap**: 모델은 올바른 근거를 *생각으로는* 만들지만 행동은 다르게 함. RL 미세조정으로 좁힐 수 있음. |
| **Control Illusion** (Geng et al., 2025) [20] / **Instruction Hierarchy** (Wallace et al., 2024; OpenAI) [21] | 시스템 vs 사용자 지시 충돌 시 우선순위 실험 / 계층 학습 | 시스템·사용자 역할 구분이 **신뢰할 만한 우선순위를 만들지 못함**, 단순 형식 충돌에서도. 프롬프트 공학 효과는 미미. 지시 계층은 *별도 학습*을 해야 생김. |
| **Lost in the Middle** (Liu et al., 2023) [22] / **IFScale** (Jaroslawicz et al., 2025) [23] | 긴 문맥 중간 정보 활용; 동시 지시 수 증가에 따른 준수율 | 문맥 중간 정보는 잘 쓰이지 않음. 지시 수가 늘면 준수율이 떨어지고, **앞쪽 지시에 대한 편향**이 있음 — 작은 모델일수록 급격히 하락. |
| **Chain-of-Verification** (Dhuliawala et al., 2023; Meta) [24] / **SelfCheckGPT** (Manakul et al., 2023) [16] / **R-Tuning** (Zhang et al., 2023) [25] / **Sufficient Context** (Joren et al., 2024/25; Google) [26] | 초안 → 검증 질문 생성 → *초안과 독립적으로* 답 → 수정 / 여러 표본 간 일관성으로 지어낸 내용 탐지 / "모름" 학습 / 문맥이 답에 충분한지 별도 판정 후 선택적 생성 | CoVe는 검증 질문을 **초안을 보지 않고** 답할 때 효과가 큼. Sufficient Context: **작은 공개 모델은 문맥이 충분해도 기권하거나 지어내는 경향**, 충분성 신호를 쓰면 답한 것 중 정답 비율 2–10%p 향상. |
| 보조: **Why Language Models Hallucinate** (Kalai et al., 2025; OpenAI) [27] | 할루시네이션의 통계적 원인 | 평가가 "모름"에 0점을 주고 추측에 기대 점수를 주면 모델은 추측하도록 학습·선택됨. → 채점 설계에서 **기권에 부분 점수, 틀린 확신에 감점**이 필요. |

### 3.2 우리 결과와의 관계

- **강한 일치: "먼저 쓰고 나중에 확인".** v3 기록에서 thought에 "확인 불가로 처리해야"를 쓰고도 행동이 먼저 써 버린 것은 [19]의 knowing-doing gap 그 자체다. 또 Qwen3.5-4B가 thinking 계열이라면 [18]의 "추론 미세조정이 기권을 낮춘다"는 결과와도 맞는다. Heretic(검열 해제) 변형이라는 점도 거절·기권 경향을 추가로 낮췄을 가능성이 있다 — **원본 Qwen3.5-4B와 Heretic을 같은 세계에서 비교**하면 이 교란을 분리할 수 있다(가설, 미검증).
- **일치: 시스템 프롬프트 규칙 실패.** [20][21][22][23]은 일반 규칙을 시스템 프롬프트에 넣는 것이 소형 모델에서 약한 이유를 세 가지로 설명한다: (a) 역할 구분이 우선순위를 보장하지 않음, (b) 긴 시스템 프롬프트 속 규칙은 행동 시점에서 멀다(위치), (c) 규칙이 많을수록 개별 준수율 하락. 과제 문장 안의 "모르면 '확인 불가'"가 통한 것은 *행동 결정 직전, 해당 대상과 같은 문장에* 지시가 있기 때문 — 위치·구체성 효과.
- **부분 불일치**: [18]은 신중한 시스템 프롬프트가 *어느 정도* 기권을 높인다고 보고하지만 우리 v3에서는 오히려 지어내기가 6/11 → 9/11로 늘었다. 가능한 설명: (a) n=11의 잡음(Fisher 정확검정으로 6/11 vs 9/11은 유의하지 않음, p≈0.36), (b) 우리 규칙이 "주인 사실은 확인된 것만"처럼 **언제 적용되는지 모델이 스스로 판단해야 하는 조건부 규칙**이라는 점. 프런티어 모델 대상 결과가 4B에 그대로 옮겨지지 않는다는 것 자체도 보고할 만한 결과다.
- **Sufficient Context[26]와 v4b**: v4b의 "질문 속 고유명사가 문서에 글자 그대로 나오는가"는 충분성 판정의 값싼 규칙 기반 근사이며, 작은 모델에 학습된 판정기 대신 *문자열 검사*를 쓴 것이 효과적이었다는 점은 [26]의 "작은 모델은 충분성 판단 자체가 약하다"와 정합한다.

### 3.3 값싼 실험·스캐폴드 변경

1. **쓰기 전 출처 필드 강제 (행동 스키마 차원의 기권)** — 최우선. 주인 관련 사실을 쓰는 `write/append`에 `"source"` 필드 요구: `memory.md#L5` / `파일경로` / `lookup#id` / `"unknown"`. 하네스가 출처가 실제로 그 문자열을 포함하는지 확인하고, 없으면 거절. 모델이 "출처가 없으면 unknown을 고르는 것"이 *쓰기 행위의 일부*가 되므로 knowing-doing gap을 우회. 측정: FRESH 지어낸 고양이 이름(현재 6/11, 9/11).
2. **동적 과제 내 지시 주입(just-in-time reminder)**: 시스템 프롬프트 대신, 하네스가 관찰 텍스트 끝에 "이 과제에 기억·파일에 없는 사실이 필요하면 '확인 불가'로 적는다" 한 줄을 *그날 과제 목록 바로 뒤*에 붙인다. 우리 결과(과제 내 지시만 통함)를 일반화할 수 있는지 직접 검증하는 2×2 실험: {위치: 시스템/관찰 끝} × {형태: 일반 규칙/과제별 문장}.
3. **추출 → 검증 2단계 쓰기(CoVe식, 초안 비공개)**: 쓰기 직전 하네스가 "쓸 내용에 등장하는 고유명사"만 뽑게 하는 짧은 호출 → 각 명사를 기억·집 파일에서 grep(모델 아님) → 없는 명사가 있으면 쓰기를 보류하고 "근거 없음: 비비"를 관찰로 반환. 비용: 쓰기당 짧은 호출 1회(+grep). 문자열 검사는 v4b에서 이미 효과가 검증된 방식.
4. **채점에 기권 보상 반영**[27]: 지표를 "정답 / 정직한 모름 / 틀린 확신"의 3단으로 보고하고, 프롬프트·과제에도 "모름은 감점 없음, 지어내면 감점"을 명시하는 조건을 추가해 효과 측정.
5. (선택, 비용 큼) Heretic vs 원본 비교, thinking on/off 비교([18] 재현). 추론 시간이 2배가 되므로 우선순위는 낮지만 해석에 중요.

---

## 4. 검색(근거화) 실패: 개체 혼동, 거짓 전제, 복합 질문, 주장 분해

### 4.1 핵심 연구

| 연구 | 무엇을 했나 | 무엇을 발견했나 |
|---|---|---|
| **AmbigDocs** (Lee et al., 2024) [28] | 같은 이름·비슷한 이름의 서로 다른 개체가 섞인 문서 집합 | 모델은 **서로 다른 개체의 정보를 합쳐 한 답으로 만드는(conflation)** 경향이 강함. |
| **RAMDocs / MADAM-RAG** (Wang et al., 2025) [29] | 모호성 + 오정보 + 잡음을 섞은 데이터셋, 문서마다 별도 에이전트가 답하고 토론·집계 | 70B 모델도 정확일치 30%대. 문서별로 따로 답하게 한 뒤 집계하면 AmbigDocs +11%p, FaithEval +16%p. → **"문서 하나당 판단 하나"** 분리가 혼동을 줄인다. |
| **Sufficient Context** [26] / **Making RAG Robust to Irrelevant Context** (Yoran et al., 2023) [31] | 문맥 충분성 판정 / NLI 모델로 무관 문서 걸러내기 | 무관·오도 문서가 답을 *오히려 나쁘게* 만들 수 있고, 걸러내기(필터)가 이를 막음. 검색 없이 묻는 것보다 검색이 나쁜 경우가 존재. |
| **Self-RAG** (Asai et al., 2023) [32] / **CRAG** (Yan et al., 2024) [33] | 검색 필요성·문서 관련성·근거 지지 여부를 반성 토큰으로 판정 / 가벼운 평가기로 검색 품질 판정 후 교정 행동 | 검색 결과를 **"관련 / 무관 / 모호"로 먼저 판정**하는 단계가 견고성의 핵심. CRAG의 평가기는 작은 모델(T5급) — 저비용 근사 가능성을 시사. |
| **FActScore** (Min et al., 2023) [39] / **SAFE** (Wei et al., 2024; DeepMind) [41] | 긴 답을 **원자적 주장(atomic facts)**으로 분해해 하나씩 검색·검증 | 분해 후 개별 검증이 사람 판정과 잘 일치. SAFE는 검색 엔진으로 주장별 검증을 자동화. |
| **Premise Verification via Retrieval-Augmented Logical Reasoning** (Qin et al., 2025) [42] / **FreshLLMs/FreshQA** (Vu et al., 2023) [43] | 질문을 논리 형태로 바꾸고 **전제마다 검색으로 검증**한 뒤 판정 결과를 프롬프트에 넣음 / 거짓 전제 문항 포함 QA | 거짓 전제 문항은 큰 모델에도 어려움; 전제별 검증을 프롬프트에 넣으면 할루시네이션이 줄어듦(모델 내부 접근·학습 불필요). |

### 4.2 우리 결과와의 관계

- **강한 일치: 노르바니아 → 노르웨이/오슬로.** [28][29]의 conflation과 같다. 특이점은 우리 경우 *모델*이 아니라 **검색 단계(영어 보조 검색의 퍼지 매칭)**가 비슷한 이름의 실존 개체로 바꿔 놓았다는 것 — "모델은 정직하게 lookup 했는데 도구가 거짓 근거를 만들었다". v4b(글자 그대로 존재 확인)는 [26][31][33]의 "먼저 관련성·충분성 판정" 단계를 문자열 검사로 구현한 것이고, 7/10 → 1/10 개선은 문헌의 방향과 일치한다. 남은 1건('벨기아' 옛 표기 실존)은 문자열 검사의 원리적 한계(정말로 존재하는 이름)이므로 실패가 아니라 채점 기준 문제에 가깝다.
- **일치: 복합 유도 질문은 검색 시 더 나쁨.** "호주는 캔버라이고 튀르키예는 안카라인가?" → 'Australians in Turkey' 문서. 두 주장을 *한 질의*로 검색하면 두 개체의 교집합 문서가 걸리고, 그 문서는 어느 주장도 검증하지 못한다. [31]의 "무관 문서가 검색 없음보다 나쁘다"와 같은 현상. 문헌 처방은 일관되게 **분해 후 개별 검증**[39][41][42]이다.
- **반성할 점: v3 중립화가 새 오류("세종대왕의 아버지는 고종세자")를 만든 것**은 *모델에게 재작성(reformulation)을 맡기면* 재작성 자체가 할루시네이션 경로가 된다는 뜻. 분해도 모델이 하면 같은 위험이 있으므로, 분해 결과의 각 주장도 v4b처럼 **원문 글자 그대로의 개체명을 포함하는지** 검사해야 한다.

### 4.3 값싼 실험·스캐폴드 변경

1. **복합 질문 분해 + 주장별 v4b 검증 + AND 결합** (최우선). 단계: (a) 모델이 원자적 주장 목록 생성(JSON 배열, 최대 3개), (b) 각 주장의 개체명이 질문 원문에 글자 그대로 있는지 하네스가 검사(없으면 버림 — v4b 규칙 재사용), (c) 주장별로 따로 검색·판정, (d) 하나라도 거짓/확인불가면 전체를 "아니오/일부만 확인"으로. 기존 eval/leading_compound(10문항)를 20~30문항으로 늘려 비교: 그냥 묻기 / v2 / v4b / 분해+v4b.
2. **문서별 독립 판정(MADAM-RAG의 1라운드 축약판)**: 상위 2~3개 문서 각각에 대해 "이 문서가 *질문의 바로 그 개체*에 대해 이 주장을 지지/반박/무관?"을 따로 묻고, 지지가 하나도 없으면 기권. 토론 라운드는 생략(비용 때문). 4B에서도 문서 하나 단위의 판정은 짧아 노트북에서 감당 가능.
3. **검색 단계 퍼지 매칭 차단 로그**: 위키백과 검색이 질의어와 다른 표제어로 리다이렉트/추천했을 때(노르바니아→노르웨이) 그 사실을 관찰에 명시("요청: Norvania, 받은 문서: Norway — 다른 대상일 수 있음"). 비용 0, 모델에게 conflation 신호를 직접 제공.
4. **거짓 전제 유형 다양화**: 개체 자체가 가짜(노르바니아) / 개체는 진짜·속성이 거짓(캔버라↔시드니) / 두 진짜 개체의 관계가 거짓(복합) — 세 유형별로 결과를 나눠 보고. FreshQA[43]·AbstentionBench[18]의 분류와 맞추면 비교가 쉬움.

---

## 5. 소형 모델 에이전트의 행동 고리(loop)·반복

### 5.1 핵심 연구

| 연구 | 무엇을 했나 | 무엇을 발견했나 |
|---|---|---|
| **Wait, Wait, Wait... Why Do Reasoning Models Loop?** (Pipis et al., 2025; ICML 2026) [30] | 추론 모델의 고리 빈도·원인 분석(합성 그래프 과제 포함) | **증류된 작은 모델이 교사보다 훨씬 많이 고리에 빠짐**(예: 1.5B 학생 greedy에서 30%), 같은 계열에서 클수록 덜함. 원인: 학습하기 어려운 행동을 피하고 *쉬운 순환 행동*을 고르는 위험 회피, **시간적으로 상관된 오류**(같은 몇 개 행동이 계속 선택). **온도를 높이면 줄지만 임시방편.** |
| **Learning to Break the Loop** (Xu et al., 2022) [44] | 문장 단위 반복의 자기 강화 현상 분석 | 한 번 반복하면 그 반복의 확률이 *계속 높아지는* 자기 강화 효과 — 문맥에 같은 행동 기록이 쌓일수록 고리가 깊어짐. |
| **Qwen3 모델 카드 권장 설정** (Qwen 팀) [45] | 공식 샘플링 권장 | **greedy 디코딩 비권장**(성능 저하·끝없는 반복), `presence_penalty` 0~2(기본 1.5 권장 사례)로 반복 감소, 단 높으면 언어 섞임·약간의 성능 저하. |
| **OpenHands StuckDetector** (All Hands AI) [46] | 실무 프레임워크의 막힘 탐지기 | 같은 행동→같은 관찰 4회 이상, 같은 행동→오류 3회 이상, 핑퐁(A-B-A-B) 6회 이상, 독백 반복 등을 탐지해 기본으로 실행 중단. 임계값 고정 시 의도적 폴링에서 오탐 보고(설정 가능하게 변경). |
| **SWE-agent** (Yang et al., 2024) [47] | 에이전트-컴퓨터 인터페이스(ACI) 설계 | 명령 출력 형식·피드백 설계(예: 빈 출력에 "명령 성공, 출력 없음" 명시, 파일 보기 창 제한)가 성능을 크게 바꿈. 같은 명령 반복은 **관찰이 정보 없이 끝날 때** 자주 발생. |

### 5.2 우리 결과와의 관계

- **강한 일치**: 우리 실행은 temperature 0(조건당 1회) + 0.6(시드 10개)인데, 1일차에 LIFE가 "메모를 12번 다시 읽는" 고리에 4번 빠졌다. [30][45]은 greedy가 고리를 키운다고 명시한다. **temperature 0 실행을 '대표 실행'으로 쓰는 관행 자체가 4B 모델의 고리 실패를 과대 표집**할 수 있다. 노트북 격리 실행이 temperature 0 1회씩이라는 점은 해석 시 주의.
- **일치**: agent-v2의 반복 차단(같은 검색 차단)으로 완화됐지만 하루 4~5회 남은 것은 [44]의 자기 강화 효과 — 차단해도 *문맥에 반복 기록이 남아 있으면* 비슷한 변형 행동으로 다시 빠진다. [46]처럼 탐지 후 **문맥에서 반복 구간을 접거나(요약)** 다른 행동을 강제하는 쪽이 더 근본적.
- **주의**: presence_penalty는 JSON 구문 토큰(`{`, `"action"`)에도 걸려 형식을 깨뜨릴 수 있다. llama.cpp의 문법 제약(GBNF/JSON 스키마)과 함께 쓰는 것이 안전.

### 5.3 값싼 실험·스캐폴드 변경

1. **반복 읽기 관찰 압축** (최우선, 비용 0): 같은 파일을 변경 없이 다시 `read`하면 내용 대신 "이 파일은 걸음 N에서 읽은 것과 같다(변경 없음). 이미 아는 내용: … 다음 행동을 고르라"를 반환. 고리의 연료(같은 관찰의 반복 주입)를 끊는다.
2. **StuckDetector식 탐지 + 단계적 대응**: (a) 같은 행동·같은 관찰 3회 → 경고 관찰 + 직전 5걸음 요약, (b) 4회 → 그 행동을 금지 목록에 넣고 "남은 과제" 목록 재표시, (c) 핑퐁 탐지 추가. 현재 v2 차단과 비교해 하루 반복 횟수·성공률 측정.
3. **샘플링 설정 소규모 그리드**: {temperature 0, 0.6, 0.7} × {presence_penalty 0, 1.0, 1.5}, 문법 제약 JSON 유지. 1일차(조건 무관)만 돌려 고리 빈도·JSON 오류율·성공률 측정 → 이후 모든 실험의 기본값 결정. 1일차만이면 노트북에서도 가능.
4. **"남은 과제 체크리스트" 상태 표시**: 매 관찰에 하네스가 과제별 상태(미착수/진행/사후조건 통과)를 표시. 고리 상당수는 "다음에 뭘 할지 모름"에서 오므로 계획 상태를 외부화하면 줄어든다(SWE-agent ACI 원리). §2의 사후조건 검사와 같은 코드 재사용.

---

## 6. 장기 실행 에이전트 평가 방법론과 소규모(n) 통계

### 6.1 핵심 연구

| 연구 | 무엇을 했나 | 무엇을 발견했나 |
|---|---|---|
| **LongMemEval** (Wu et al., 2024; ICLR 2025) [34] | 500문항, 5능력: 정보 추출·다중 세션 추론·시간 추론·**지식 갱신**·**기권** | 상용 비서·장문맥 모델 모두 세션이 길어지면 약 30% 하락. 기억을 색인·검색·읽기 단계로 나눠 개선 기법 제안(세션 분해, 사실 보강 키, 시간 인지 질의 확장). |
| **LoCoMo** (Maharana et al., 2024) [48] | 매우 긴 다중 세션 대화(최대 수십 세션) 기억 평가 | 장기 시간·인과 추론이 특히 약함. Mem0·Zep·A-MEM 등이 공통으로 쓰는 기준선. |
| **MemoryAgentBench** (Hu, Wang, McAuley, 2025; ICLR 2026) [35] | 정보를 *점진적·다회차*로 주입하고 여러 번 질의, 4능력(정확 검색·테스트 시점 학습·장기 이해·**충돌 해결/선택적 망각**) | 현재 방법들이 네 능력을 모두 갖추지 못함, 특히 충돌 해결(사실 갱신)이 약함. |
| **τ-bench pass^k** (Yao et al., 2024) [37] | 같은 과제 k번 독립 시행이 *모두* 성공할 확률 | pass^1 대비 pass^8이 크게 떨어짐(GPT-4급 50% 미만 → 약 25%). **신뢰성은 평균 성공률과 다른 축.** |
| **Adding Error Bars to Evals** (Miller, 2024; Anthropic) [38] | 평가를 실험으로 보고 통계 처방 | 문항(과제) 군집 표준오차, **짝지은 비교로 분산 감소**, 사전 검정력 분석. 500문항에서도 1.5%p 차이는 흔히 잡음. |
| **Defeating Nondeterminism in LLM Inference** (He, 2025; Thinking Machines) [40] / **Non-Determinism of "Deterministic" LLM Settings** (Atil et al., 2024) [49] | temperature 0 비결정성 원인 분석 | 주원인은 **서버 부하에 따라 배치 크기가 바뀌고, 커널이 배치 크기에 따라 다르게 계산**하는 것(배치 불변성 결여). Qwen3-8B temp 0에서 1000회 중 80개 서로 다른 출력; 배치 불변 커널로 1000/1000 일치. |
| **AI Agents That Matter** (Kapoor et al., 2024) [50] / **HAL** (Kapoor, Stroebl et al., 2025; ICLR 2026) [51] / **Agentic Benchmark Checklist (ABC)** (Zhu et al., 2025) [52] | 에이전트 평가 관행 비판·표준 하네스·체크리스트 | 비용 함께 보고, 반복 실행, 과제 유효성(정직하지 않은 방법으로 통과 가능한지)·결과 유효성(채점기 버그) 점검. ABC는 기존 벤치마크에서 채점 결함으로 성능이 크게 과대/과소 추정된 사례를 보고. |

### 6.2 우리 결과와의 관계

- **일치·검증됨**: 우리가 처음 집계한 "사실 할루시네이션"이 전부 채점기 문제(표기 변이·혼합 문자·표 형식)였다는 발견은 ABC[52]의 *결과 유효성* 문제의 전형이다. 채점기 수정 이력을 보고서에 남긴 것은 좋은 관행.
- **일치·설명됨**: "서버 하나에 4개 동시 → 같은 시드도 재현 안 됨"은 [40]의 배치 불변성 결여로 정확히 설명된다. llama.cpp 병렬 슬롯(`-np`)·연속 배칭이 같은 원인을 만든다. 따라서 v2 vs v3 차이에는 *조건 효과 + 배치 구성 효과*가 섞여 있다.
- **보완 필요**: 지금 보고는 평균±표준편차와 부트스트랩 CI인데, (a) 같은 시드로 LIFE/FRESH를 돌리므로 **짝지은 분석**이 가능하고 더 강력하다[38], (b) 과제 단위로 성공이 상관되므로(어떤 과제는 늘 쉬움) **과제 군집**을 고려해야 하며, (c) 지표가 많아(성공·기억 과제·한 척·지어내기·잡음 줄·반복 수…) **다중 비교 보정**이나 주 지표 사전 지정이 필요하다.
- **새 축**: pass^k[37]를 쓰면 "LIFE가 기억 과제를 *매번* 푸는가"를 볼 수 있다. 3.55/4 평균보다 "11회 모두 성공한 기억 과제 수"가 장기 비서로서의 신뢰성을 더 잘 나타낸다.

### 6.3 값싼 실험·통계 관행 변경

1. **추론 서버를 실험용으로 단일 슬롯 고정**(`-np 1`, 연속 배칭 영향 제거)하고, 병렬이 필요하면 *조건을 섞어*(LIFE·FRESH를 같은 배치 구성에 균등 배치) 돌리기. 재현성 점검: 같은 시드 2회 실행 일치율을 매 배치 기록. 비용 0~시간 증가.
2. **짝지은 통계**: 시드별 (LIFE−FRESH) 차이로 부트스트랩/부호순위 검정; 이진 결과(과제 성공, 지어내기 여부)는 시드 짝 단위 **McNemar 정확검정**, 짝이 없으면 **Fisher 정확검정**. 예: v2 FRESH 6/11 vs v3 FRESH 9/11 지어내기는 Fisher p≈0.36로 "정직 규칙이 오히려 악화"라고 결론 내리기엔 근거가 부족 — 보고서 표현을 "개선 증거 없음"으로 조정 권장.
3. **검정력 계획**[38]: 효과 크기 가정(예: 지어내기 50%→20%)으로 필요한 시드 수를 미리 계산. 이진 지표에서 이 정도 차이를 80% 검정력으로 보려면 조건당 대략 40회 안팎이 필요(근사) → 노트북 대신 빌드 PC에서 1일차·특정 날만 잘라 돌리는 **"날 단위 단축 실험"**(그 전날까지의 기억 파일을 고정 스냅숏으로 주입)으로 비용을 줄인다. 이렇게 하면 앞날 실패가 뒷날로 번지는 분산도 제거된다.
4. **pass^k와 시드별 표 공개**: 과제 × 시드 성공 행렬(히트맵)을 함께 보고. 평균이 같아도 "늘 성공하는 과제 / 가끔 성공하는 과제"를 구분.
5. **주 지표 사전 지정 + 보조 지표 Holm 보정**: 다음 ablation 전에 주 지표 1~2개(예: day2+ 기억 과제 성공, FRESH 지어내기율)를 문서로 고정.
6. **벤치마크 범주에 맞춘 보고**: 과제를 LongMemEval/MemoryAgentBench 범주(정보 추출·지식 갱신·기권·충돌 해결)로 태깅하면 외부 비교가 가능해짐.

---

## 7. 종합: 다음 실험 우선순위 (4B · GTX 950M 기준, 기대 가치 순)

비용 등급: ◎ 하네스 코드만(추론 추가 없음) · ○ 짧은 호출 추가 · △ 실행 수가 늘어남

| 순위 | 변경 | 겨냥하는 결과 | 비용 | 근거 |
|---|---|---|---|---|
| 1 | `done` 증거 필드 + 하네스 사후조건 검사 + 실패 사유 반환 | 한 척(FRESH 1.91), 하루 마감 거절 | ◎ | [11][13][14][37] |
| 2 | 주인 사실 쓰기에 `source` 필드 강제(없으면 "unknown"만 허용) | FRESH 지어낸 이름(6/11, 9/11, 6/6) | ◎ | [19][20][26] |
| 3 | 기억 줄 출처 태그 + 검증 통과분만 규칙 승격 + 출처 없는 줄 기계 제거 | 실수→규칙 고착, 지어낸 기억 | ◎/○ | [7][8] |
| 4 | 반복 읽기 관찰 압축 + StuckDetector식 단계 대응 | 고리(하루 4~5회, 12번 다시 읽기) | ◎ | [30][44][46][47] |
| 5 | 실험 서버 단일 슬롯·재현성 점검 + 짝지은 통계·Fisher/McNemar | v2/v3 비교의 해석 가능성 | ◎ | [38][40] |
| 6 | 기억 갱신을 ADD/UPDATE/INVALIDATE 연산으로(전체 다시 쓰기 폐지) | life-v2 규칙 변경·사실 정정, 핵심 기억 누락 | ○ | [4][5][35] |
| 7 | 복합 질문 분해 + 주장별 v4b 검증 + AND 결합 | 복합 유도 질문(근거화 1~2/5 수용) | ○ | [39][41][42] |
| 8 | 샘플링 그리드(temperature × presence_penalty, 1일차만) | 고리, temp 0 대표 실행의 편향 | △ | [30][45] |
| 9 | 불가능 과제 2~3개 추가(순수 거짓 완료율) | 한 척의 원인 분리 | ◎(세계 수정) | [12] |
| 10 | 검색 리다이렉트/표제어 불일치를 관찰에 명시 | 노르바니아→노르웨이형 혼동 잔여 | ◎ | [28][29][31] |
| 11 | 날 단위 단축 실험(전날 기억 스냅숏 주입)으로 n 확대 | 통계 검정력 | △ | [38] |
| 12 | Heretic vs 원본, thinking on/off 비교 | 기권 저하의 원인 분리 | △△ | [18] |

**설계 원칙 한 줄 요약**: 4B 모델에게 "지켜야 할 규칙"을 늘리지 말고, (1) 행동 스키마에 증거·출처 칸을 만들어 규칙을 *형식*으로 바꾸고, (2) 실행기가 세계 상태로 확인한 결과만 *관찰*과 *기억*에 들어가게 하라. 문헌의 공통 결론(외부 검증 > 자기 비판, 연산형 기억 갱신 > 전체 재작성, 분해 검증 > 통째 검색)이 모두 이 방향을 가리킨다.

**문헌과 다르거나 아직 공백인 지점(우리 연구의 기여 후보)**
- 대부분의 기억 연구는 대화형 QA이고, **행동하는 에이전트가 자기 행동 기록을 정리해 규칙을 만드는** 설정에서의 오염은 [7] 정도만 다룬다. 우리 "실수 → 규칙" 사례는 이 공백에 해당.
- 기권 연구 대부분은 프런티어·중형 모델 대상이다. **4B에서 시스템 프롬프트 정직 규칙이 효과 없음(혹은 악화 경향)**, **과제 내 지시는 강하게 통함**은 [18]의 "시스템 프롬프트가 약간 돕는다"와 대비되는 소형 모델 쪽 데이터.
- 검색 도구 자체가 퍼지 매칭으로 **가짜 개체를 실존 개체로 바꿔 주는** 실패(모델은 정직)는 RAG 문헌에서 주로 "문서 집합에 섞인 모호성"으로 다뤄지며, *검색 API의 리다이렉트*로 생기는 경우는 덜 다뤄졌다.

---

## 참고문헌

(arXiv 번호는 초판 기준. ※는 이번 검토에서 초록·공식 문서 요약 수준까지만 확인한 항목)

1. Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., Bernstein, M. S. (Stanford/Google), 2023. *Generative Agents: Interactive Simulacra of Human Behavior*. https://arxiv.org/abs/2304.03442
2. Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., Gonzalez, J. E. (UC Berkeley; Letta), 2023. *MemGPT: Towards LLMs as Operating Systems*. https://arxiv.org/abs/2310.08560
3. Lin, K., Snell, C., Wang, Y., Packer, C., Wooders, S., Stoica, I., Gonzalez, J. E. (Letta/UC Berkeley), 2025. *Sleep-time Compute: Beyond Inference Scaling at Test-time*. https://arxiv.org/abs/2504.13171 · Letta 블로그: https://www.letta.com/blog/sleep-time-compute
4. Chhikara, P., Khant, D., Aryan, S., Singh, T., Yadav, D. (Mem0), 2025. *Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory*. https://arxiv.org/abs/2504.19413 ※
5. Rasmussen, P. 외 (Zep AI), 2025. *Zep: A Temporal Knowledge Graph Architecture for Agent Memory*. https://arxiv.org/abs/2501.13956 · Graphiti: https://github.com/getzep/graphiti ※
6. Xu, W., Liang, Z., Mei, K., Gao, H., Tan, J., Zhang, Y. (Rutgers 외), 2025. *A-MEM: Agentic Memory for LLM Agents*. https://arxiv.org/abs/2502.12110
7. Xiong, Z. 외, 2025. *How Memory Management Impacts LLM Agents: An Empirical Study of Experience-Following Behavior*. https://arxiv.org/abs/2505.16067 ※
8. (China Telecom Research Institute, MemTensor 외), 2025. *HaluMem: Evaluating Hallucinations in Memory Systems of Agents*. https://arxiv.org/abs/2511.03506 ※
9. *A-MemGuard: A Proactive Defense Framework for LLM-Based Agent Memory*, 2025. https://arxiv.org/abs/2510.02373 ※
10. Lin, X. 외 (Chinese Academy of Sciences 외), 2025. *LLM-based Agents Suffer from Hallucinations: A Survey of Taxonomy, Methods, and Directions*. https://arxiv.org/abs/2509.18970 ※
11. Cemri, M., Pan, M. Z., Yang, S. 외 (UC Berkeley), 2025. *Why Do Multi-Agent LLM Systems Fail?* (MAST). https://arxiv.org/abs/2503.13657
12. Zhong, Z., Raghunathan, A., Carlini, N. (CMU/Anthropic), 2025. *ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases*. https://arxiv.org/abs/2510.20270 ※
13. Gou, Z. 외 (Tsinghua/Microsoft), 2023. *CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing*. https://arxiv.org/abs/2305.11738
14. Huang, J., Chen, X., Mishra, S. 외 (Google DeepMind), 2023. *Large Language Models Cannot Self-Correct Reasoning Yet*. https://arxiv.org/abs/2310.01798
15. Lightman, H. 외 (OpenAI), 2023. *Let's Verify Step by Step*. https://arxiv.org/abs/2305.20050
16. Manakul, P., Liusie, A., Gales, M. J. F. (Cambridge), 2023. *SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative LLMs*. https://arxiv.org/abs/2303.08896
17. Wen, B., Yao, J., Feng, S. 외 (UW 외), 2024. *Know Your Limits: A Survey of Abstention in Large Language Models*. https://arxiv.org/abs/2407.18418
18. Kirichenko, P., Ibrahim, M., Chaudhuri, K., Bell, S. J. (Meta FAIR), 2025. *AbstentionBench: Reasoning LLMs Fail on Unanswerable Questions*. https://arxiv.org/abs/2506.09038 · 코드: https://github.com/facebookresearch/AbstentionBench
19. Schmied, T., Bornschein, J., Grau-Moya, J., Wulfmeier, M., Pascanu, R. (Google DeepMind/JKU), 2025. *LLMs are Greedy Agents: Effects of RL Fine-tuning on Decision-Making Abilities*. https://arxiv.org/abs/2504.16078
20. Geng, Y. 외, 2025. *Control Illusion: The Failure of Instruction Hierarchies in Large Language Models* (AAAI). https://arxiv.org/abs/2502.15851
21. Wallace, E., Xiao, K., Leike, R., Weng, L., Heidecke, J., Beutel, A. (OpenAI), 2024. *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions*. https://arxiv.org/abs/2404.13208
22. Liu, N. F. 외 (Stanford), 2023. *Lost in the Middle: How Language Models Use Long Contexts*. https://arxiv.org/abs/2307.03172
23. Jaroslawicz, D. 외 (Distyl AI), 2025. *How Many Instructions Can LLMs Follow at Once?* (IFScale). https://arxiv.org/abs/2507.11538 ※
24. Dhuliawala, S. 외 (Meta AI), 2023. *Chain-of-Verification Reduces Hallucination in Large Language Models*. https://arxiv.org/abs/2309.11495
25. Zhang, H. 외 (HKUST 외), 2023. *R-Tuning: Instructing Large Language Models to Say 'I Don't Know'*. https://arxiv.org/abs/2311.09677
26. Joren, H., Zhang, J., Ferng, C.-S., Juan, D.-C., Taly, A., Rashtchian, C. (UCSD/Duke/Google), 2024 (ICLR 2025). *Sufficient Context: A New Lens on Retrieval Augmented Generation Systems*. https://arxiv.org/abs/2411.06037
27. Kalai, A. T., Nachum, O., Vempala, S. S., Zhang, E. (OpenAI/Georgia Tech), 2025. *Why Language Models Hallucinate*. https://arxiv.org/abs/2509.04664
28. Lee, Y. 외 (UIUC 외), 2024. *AmbigDocs: Reasoning across Documents on Different Entities under the Same Name*. https://arxiv.org/abs/2404.12447
29. Wang, H., Prasad, A., Stengel-Eskin, E., Bansal, M. (UNC), 2025. *Retrieval-Augmented Generation with Conflicting Evidence* (RAMDocs, MADAM-RAG). https://arxiv.org/abs/2504.13079
30. Pipis, C., Garg, S., Kontonis, V., Shrivastava, V., Krishnamurthy, A., Papailiopoulos, D., 2025 (ICML 2026). *Wait, Wait, Wait... Why Do Reasoning Models Loop?* https://arxiv.org/abs/2512.12895 ※
31. Yoran, O., Wolfson, T., Ram, O., Berant, J. (Tel Aviv Univ.), 2023. *Making Retrieval-Augmented Language Models Robust to Irrelevant Context*. https://arxiv.org/abs/2310.01558
32. Asai, A., Wu, Z., Wang, Y., Sil, A., Hajishirzi, H. (UW/IBM/AI2), 2023. *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*. https://arxiv.org/abs/2310.11511
33. Yan, S.-Q. 외, 2024. *Corrective Retrieval Augmented Generation* (CRAG). https://arxiv.org/abs/2401.15884
34. Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., Yu, D. (UCLA/Tencent AI Lab), 2024 (ICLR 2025). *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*. https://arxiv.org/abs/2410.10813
35. Hu, Y., Wang, Y., McAuley, J. (UCSD), 2025 (ICLR 2026). *Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions* (MemoryAgentBench). https://arxiv.org/abs/2507.05257
36. Zhuge, M. 외 (Meta AI/KAUST), 2024. *Agent-as-a-Judge: Evaluate Agents with Agents*. https://arxiv.org/abs/2410.10934
37. Yao, S., Shinn, N., Razavi, P., Narasimhan, K. (Sierra), 2024. *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains*. https://arxiv.org/abs/2406.12045 · 블로그: https://sierra.ai/blog/benchmarking-ai-agents
38. Miller, E. (Anthropic), 2024. *Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations*. https://arxiv.org/abs/2411.00640
39. Min, S. 외 (UW/Meta), 2023. *FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation*. https://arxiv.org/abs/2305.14251
40. He, H. (Thinking Machines Lab), 2025. *Defeating Nondeterminism in LLM Inference* (블로그). https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ · 요약: https://simonwillison.net/2025/Sep/11/defeating-nondeterminism/ · 코드: https://github.com/thinking-machines-lab/batch_invariant_ops
41. Wei, J. 외 (Google DeepMind), 2024. *Long-form Factuality in Large Language Models* (SAFE). https://arxiv.org/abs/2403.18802
42. Qin, Y. 외 (USC), 2025. *Don't Let It Hallucinate: Premise Verification via Retrieval-Augmented Logical Reasoning*. https://arxiv.org/abs/2504.06438 ※
43. Vu, T. 외 (Google/UMass), 2023. *FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation* (FreshQA). https://arxiv.org/abs/2310.03214
44. Xu, J., Liu, X., Yan, J., Cai, D., Li, H., Li, J., 2022. *Learning to Break the Loop: Analyzing and Mitigating Repetitions for Neural Text Generation*. https://arxiv.org/abs/2206.02369
45. Qwen Team (Alibaba), 2025. *Qwen3 모델 카드 — Best Practices(샘플링, presence_penalty)*. https://huggingface.co/Qwen/Qwen3-8B ※ (권장값은 모델·버전마다 다르므로 Qwen3.5-4B 카드를 직접 확인할 것)
46. All Hands AI, 2024–2026. *OpenHands — Agent Stuck Detector*. https://docs.openhands.dev/sdk/guides/agent-stuck-detector · 임계값 논의: https://github.com/OpenHands/software-agent-sdk/issues/762
47. Yang, J., Jimenez, C. E., Wettig, A. 외 (Princeton), 2024. *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering*. https://arxiv.org/abs/2405.15793
48. Maharana, A., Lee, D.-H., Tulyakov, S., Bansal, M., Barbieri, F., Fang, Y. (UNC/Snap), 2024. *Evaluating Very Long-Term Conversational Memory of LLM Agents* (LoCoMo). https://arxiv.org/abs/2402.17753
49. Atil, B. 외, 2024. *Non-Determinism of "Deterministic" LLM Settings*. https://arxiv.org/abs/2408.04667
50. Kapoor, S., Stroebl, B., Siegel, Z. S., Nadgir, N., Narayanan, A. (Princeton), 2024. *AI Agents That Matter*. https://arxiv.org/abs/2407.01502
51. Kapoor, S., Stroebl, B. 외 (Princeton 외), 2025 (ICLR 2026). *Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation*. https://arxiv.org/abs/2510.11977 · https://hal.cs.princeton.edu/
52. Zhu, Y. 외 (UIUC 외), 2025. *Establishing Best Practices for Building Rigorous Agentic Benchmarks* (ABC). https://arxiv.org/abs/2507.02825 ※
