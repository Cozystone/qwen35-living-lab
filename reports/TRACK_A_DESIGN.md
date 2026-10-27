# 트랙 A 설계 — ATANOR 코어를 LLM 에이전트와 같은 집에 살게 하기 (2026-10-27, 구현 전)

목적: ATANOR life 코어(`atanor_os/agent/life.py`, v24 동결)를 트랙 L의 LLM 에이전트(`life/agent.py`)가 사는 **같은 집·같은 날·같은 채점기**에 넣는다. 그래서 두 시스템과 그 사이의 혼합체(테세우스 사다리)를 하나의 표로 비교한다.

이 문서는 설계일 뿐이다. 두 저장소의 어떤 파일도 바꾸지 않았다. 아래의 "확인함" 표시는 이번에 읽기 전용 파이썬으로 직접 확인한 사실이다. 나머지는 코드를 읽고 내린 추론이거나 예측이다.

---

## 0. 요약

- **결론부터.** ATANOR는 지금 있는 파일 몸(`fs`) 그대로는 LLM 세계의 핵심 파일 과제(영수증 정리)조차 풀 수 없다. 이유는 관측이다. 영수증 `a.txt`와 메모 `b.txt`는 원자 집합이 **완전히 같다**(확인함, 0.3절). 내용을 보는 원자가 없기 때문이다. 그래서 새 몸 `home`이 필요하다. `home`은 fs와 같은 도구를 쓰고, 관측 속성 두 개(내용 첫 낱말 `head`, 부모 폴더 이름 `loc`)를 더한다.
- **풀 수 있는 과제.** 세계 v1에서 ATANOR가 원리상 시도할 수 있는 채점 항목은 **12개 중 2개**(1·2일차 영수증)다. v2에서는 18개 중 2개다. 나머지는 자유 글쓰기, 사실 조회, 한국어 메모 읽기가 필요하다. 그래서 총점만 보면 비교가 무의미해진다. **시도 가능 부분집합 점수**를 1차 지표로 둔다.
- **LLM이 약한 곳이 바로 그 2개다.** 기존 LLM 실행의 영수증 성공은 exp1 LIFE 1일차 2/11, 2일차 0/11, FRESH 0/11·0/11이었다(확인함, 0.4절). 비교할 가치가 가장 큰 곳이다.
- **첫 마일스톤(M1).** 세계 v1 3일 동안 ATANOR를 돌린다. 조건은 {LIFE, FRESH} × {주인 부재, 1일차만 진실 교사} 4가지이고, 한국어 원문을 그대로 넣는다. 채점은 `world.judge` 그대로 한다. LLM 쪽은 **새로 돌리지 않는다.** 기존 exp1·exp2v3 결과와 비교한다. 코드는 약 450줄, 테스트는 약 150줄이다.

---

## 0.x 근거로 확인한 사실

**0.1 ATANOR 몸 인터페이스(덕타이핑, `life.py`와 `concepts.py`에서 실제로 부르는 것).**
- `BODY`(문자열): `raw_obs`의 분기 키다. 기본값은 `'fs'`다(`life.py:677`).
- `CAPABILITY`: 도구에서 권한으로 가는 맵이다. Mind는 **몸이 알리는 권한을 전부 허가**한다(`life.py:678`). 그래서 금지할 도구는 아예 몸에 두지 않아야 한다.
- `existing()`, `universe(paths)`, `observe(paths)`: 반환 형식은 `{id: {'kind', ...사람 속성}}`이다. `kind ∈ {file, dir, absent}`와 `'absent'`라는 값을 코어가 직접 쓴다.
- `kind(id)`, `attrs(id)`, `tools()`(도구→인자 수), `actions(universe)`(구문상 가능한 모든 호출), `execute(tool, args, caps)`. `execute`는 `{'ok','blocked','error','ms'}`를 돌려주고, 전제조건 실패는 예외가 아니라 `ok=False`다.
- `lab_copy(root, objs, seen)`: 실험실 사본이다. 내용까지 복사한다.
- `lab_from_state(root, state)`: 관측 상태로부터 재구성한다. 내용은 자리표시자다. 재검증(`_reverify`)에 쓰인다.
- `drift`: 세계 변화 집합. 선택 사항이다.
- `raw_obs.py`: `IDENTITY`, `KIND_ATTRS`, `raw_attrs`, `related`, `neighbours`, `to_human`, `recompute_derived`. 지금은 `fs`, `view`, `board`가 하드코딩되어 있다. `else`로 떨어지면 view로 처리되므로, 새 몸은 **반드시 분기를 추가**해야 한다.
- 코어가 관여하는 경로 관계는 `o`, `D`, `D/name(o)`뿐이다(`_pattern`, `_goal`). 목적지 아래의 이름은 원래 이름의 마지막 조각이다.

**0.2 교사 인터페이스(`teach/life_teacher.py`의 `Teacher`).**
- `explain(word)` → 다른 말로 바꾼 설명, `''`(뜻 없음), `None`(모름).
- `point(command)` → `{'objects', 'dest'}`.
- `demonstrate(cmd, o, D)` → 한 대상에 대한 단계. Mind가 실험실에서 직접 실행한다.
- `demonstrate_goal(goal)`, `check(proposal)`, `confirm(command)`, `still_wanted(command)`.
- 모든 호출은 `help` Counter로 센다. `life_gen`의 도움 점수 가중치는 explain/point/check/recall 1, demonstrate 2, demonstrate_goal 3이다. `confirm`은 따로 센다.
- `Teacher.judge`/`_steps`는 대상이 집 꼭대기에 있다고 가정한다(`f'{d}/{p}'`). 그래서 `inbox/files/a.txt`처럼 깊은 경로에는 그대로 쓸 수 없다. 새 교사 클래스가 필요하다.

**0.3 fs 몸으로 본 v1 1일차 집(확인함, 임시 폴더에서 `world.setup_day` 후 `Workspace.observe`).**
```
inbox/files/a.txt (영수증)  U: a0=1 a1=0 a2=txt   S: a0=1 a1=1 a2=-
inbox/files/b.txt (메모)    U: a0=1 a1=0 a2=txt   S: a0=1 a1=1 a2=-     ← a.txt와 원자 집합 동일
```
- 해시(`a3`)는 정체성 속성이라 같은지 다른지만 의미가 있다. 원자에서도 빠진다.
- 그래서 "영수증만"은 어떤 학습으로도 구별할 수 없다.
- 대상이 셋일 때 `actions` 수는 140이다.

**0.4 ATANOR 토크나이저는 `[a-z0-9]+`다(`life.py:37`).** 한국어 과제 문장을 넣으면 이렇게 된다(확인함).
- `receipts`(1일차) → `['inbox','files','receipts']`
- `receipts`(2일차, "어제처럼 정리해줘") → `['inbox','files']`
- `report`(2일차) → `['2026','10','28']`

한글은 모두 사라진다. 경로 조각만 남는다.

**0.5 기존 LLM 결과의 영수증 판정(확인함, `runs/*/results.json`).**

| 실험 | LIFE 1일차 | LIFE 2일차 | FRESH 1일차 | FRESH 2일차 |
|---|---|---|---|---|
| exp1 (v1, agent-v2, 11회) | 2/11 | 0/11 | 0/11 | 0/11 |
| exp2v3 (v1, v3, 11회) | 1/11 | 0/11 | 1/11 | 0/11 |
| exp4v4w1 (v1, v4, 5회) | 0/5 | 0/5 | 0/5 | 0/5 |
| exp3w2 (v2, v3, 6회) | 1/6 | 0/6 | 0/6 | 0/6 |
| exp5v4w2 (v2, v4, 2~3회) | 2/2 | 1/2 | 2/3 | 1/3 |

- 실패한 집을 보면 유형은 셋이다. 목적지를 틀렸고(`inbox/receipts/`), 메모까지 옮겼고(`receipts/b.txt`), 2일차 파일은 아예 건드리지 않았다.
- `ask_user` 호출은 exp1 기준 LIFE 4회, FRESH 17회였다. 모두 "주인 부재"라는 답을 받았다.

---

## 1. 행동 대응표: LLM Body ↔ ATANOR 몸

### 1.1 행동별 대응

| LLM 행동 (`life/agent.py`) | ATANOR 쪽 | 대응 | 메모 |
|---|---|---|---|
| `list(path)` | `observe(existing())` | **관측으로 흡수** | ATANOR는 매 걸음 집 전체를 공짜로 본다. LLM은 60줄 트리와 `list` 200개가 상한이다. 지각 예산이 다르다는 점을 결과 표에 적는다. |
| `read(path)` | (없음) → `head` 속성 | **적응** | ATANOR는 글을 읽지 않는다. 새 몸은 파일마다 내용 첫 낱말 하나(`head`)만 이름 없는 원자 `a4`로 준다. 4000자 읽기와 비교하면 아주 작은 투영이다. |
| `write(path, text)` | (없음) | **대응 불가** | ATANOR는 글을 만들지 못한다. 보고서, 수도, 고양이 이름, 초대장, 카드가 여기에 해당한다. 구조화된 대안은 1.3절에 있다. |
| `append(path, text)` | (없음) | 대응 불가 | 위와 같다. |
| `move(src, dst)` | `move(s, d)` | **직접(의미 차이 있음)** | LLM 쪽은 dst가 폴더이거나 확장자가 없으면 그 안으로 넣고, 상위 폴더를 자동으로 만든다. ATANOR 쪽은 d가 최종 경로여야 하고(`receipts/a.txt`), 부모가 이미 있어야 하며, 덮어쓰지 않는다. ATANOR는 더 원시적인 도구로 같은 끝 상태에 도달해야 한다. |
| `mkdir(path)` | `mkdir(p)` | **직접(의미 차이)** | LLM은 `parents=True, exist_ok=True`다. ATANOR는 이미 있거나 부모가 없으면 실패한다. ATANOR가 학습할 전제조건이다. |
| (LLM에는 없음) | `copy(s, d)` | 비대칭 | LLM은 `read`+`write`로 흉내 낸다. 해시로 판정하므로 내용이 한 글자만 달라도 실패한다. 공용 세계 W-F(3.5절)에서는 LLM에도 `copy`를 준다. 에이전트 판본 표기가 바뀐다. |
| (LLM에는 없음) | `delete`, `convert` | **몸에서 뺀다** | LLM은 삭제할 수 없다. Mind는 몸의 권한을 자동으로 전부 허가한다. 그래서 `home` 몸의 도구는 `{mkdir, move, copy}` 셋으로 둔다. |
| `lookup(question)` | (없음) | 대응 불가 | 근거화 검색이다. 사다리 혼합체에서만 LLM 부품으로 연결한다. |
| `remember(text)` | 자동: `episodes.jsonl`, `lexicon.json`, `patterns.json`, `procedures.json`, `pending.json` | **구조가 다름** | ATANOR의 기억은 경험과 어휘이고, 무엇을 기억할지 고르는 행동이 따로 없다. FRESH는 두 쪽 모두 `mind/`를 지우는 것으로 같게 정의한다(`life_gen.run_day`와 `agent.run_day`가 이미 그렇게 한다). |
| `ask_user(question)` | `explain/point/check/demonstrate/demonstrate_goal/confirm/still_wanted` | **형식이 다름** | ATANOR는 구조화된 질문을 하고, LLM은 자유 질문을 한다. 공정성 규칙은 2.3절에 있다. |
| `done(task, summary)` | `Mind.do(...)['achieved']` | **적응** | ATANOR가 "했다"고 주장하는 것은 `achieved is True`로 정의한다. `confirmed`는 교사가 있을 때만 생긴다. `false_done` = 주장했는데 `world.judge`가 실패. |
| `end_day(diary)` | 브리지가 그날 과제를 다 넘기면 끝 | 브리지 몫 | 마감 거절 규칙은 ATANOR에 적용되지 않는다. 브리지가 모든 과제 줄을 반드시 넘기기 때문이다. |
| 밤의 기억 정리(`consolidate`) | 해당 없음 | — | ATANOR는 줄여 쓰지 않는다. 모든 에피소드를 남기고 규칙을 매번 다시 유도한다. |

### 1.2 ATANOR가 필요로 하는데 지금 세계가 주지 않는 것

1. **실험실 사본(`lab_copy`, `lab_from_state`).**
   - LLM 세계에는 사본 개념이 없다. `HomeWorkspace`가 fs의 구현을 그대로 물려받으면 해결된다.
   - 단 `lab_from_state`의 자리표시자 내용은 `head`를 되살려야 한다. 그래서 `f"{head} placeholder\n"`로 쓴다. 안 그러면 재검증 실험실에서 영수증이 영수증이 아니게 된다.
   - 실험실 경로는 **짧은 경로**여야 한다. 이번 확인에서 스크래치패드의 긴 경로가 Windows MAX_PATH(WinError 206)로 실패했다. 그래서 `runs/A/<조건>/lab`처럼 짧은 위치를 쓴다.
2. **관측 원자.** `fs`에는 내용을 보는 원자도, 위치 이름을 보는 원자도 없다(0.3절). 새 몸 `home`에 아래 두 속성을 더한다.
   - `head` (`a4`)
     - 파일: 내용 첫 줄의 첫 공백 구분 토큰을 NFC로 정규화하고 최대 24자로 자른 것. 디렉터리와 없음은 `'-'`.
     - 이동하거나 복사하면 `D/o`의 `head`가 `o`의 값으로 바뀐다. 이것은 `copy(0,'a4')` 효과로 학습된다.
     - 이 속성은 "이름"이 될 수 있다. 다만 한글 값이라 한국어 문장 토큰과는 만날 수 없다(0.4절).
   - `loc` (`a5`)
     - 부모 id의 마지막 조각이다(꼭대기는 `'-'`). `ext`와 똑같이 **id에서만 계산되고 존재 여부와 무관하다.** 그래서 행동이 바꾸지 않는다. 패턴과 효과에 절대 들어가지 않고 선택(U·S 원자)에만 쓰인다.
     - fs의 `ext`가 바로 이 성질을 가진 선례다(`name_ext`는 없는 경로에도 값을 준다).
     - 2일차 선택 문제를 푼다. `head=영수증`만으로 고르면 이미 정리된 `receipts/a.txt`까지 골라져 `o == D/o`인 모순 목표가 된다. 반면 `loc=files`로는 `inbox/files/*`만 골라진다.
     - 덤으로, 한국어 원문에 남는 토큰 `inbox`·`files`·`receipts`가 `loc` 값이나 목적지 id와 맞물린다.
   - 고려했다가 기각한 안
     - **디렉터리 자신의 이름 속성(`label`)**: `mkdir`이 그 속성을 바꾸는 것으로 보이므로 패턴에 상수 `'receipts'`가 박힌다. 실험실 탐침 `probe`를 만들면 `mkdir`의 효과가 `unknown`이 된다.
     - **깊이(depth)**: 쓸 수는 있다. 하지만 "루트 바로 아래 목적지"라는 세계 우연에 기댄다.
3. **명령 전달.** ATANOR는 명령 문장을 받는다. LLM은 `inbox/tasks.md`를 스스로 읽는다. 둘을 잇는 브리지는 2절에 있다.
4. **진실 명세.** 교사가 `point`/`check`/`demonstrate`에 답하려면 과제마다 (도구, 대상 집합, 목적지)가 필요하다. 세계 v1/v2의 `judge`는 판정만 하고 명세를 내놓지 않는다. 그래서 평가기 쪽에 `TASK_TRUTH`를 만든다. 대상은 `begin` 때 내용으로 계산한다. 예: `inbox/files/` 안에서 첫 줄이 `영수증`인 파일, 도구 move, 목적지 `receipts`.
5. **세계 변화(`drift`).** LLM 세계에는 도구 변화가 없다. 지금은 `drift = frozenset()`이다. W-F(3.5절)에서 양쪽에 같은 변화를 넣을지는 열린 질문으로 둔다(5절).

### 1.3 자유 글쓰기를 구조화된 도구로 바꿀 수 있는가 (지금은 넣지 않음)

- **줄 단위 대상**: 텍스트 파일의 각 줄을 대상으로 만들고 `quote(line, dst)` 도구를 준다고 해 보자.
  - 그러면 `cat`(note.md의 "고양이 이름은 '모카'" 줄을 `pets/cat.txt`로 옮겨 적기)과 `catfix`, `card` 일부가 원리상 도달 가능해진다. 판정기는 `'모카' in text`이므로 줄 하나만 있으면 된다.
  - 하지만 이것은 사실상 새 몸(텍스트 몸)이다. 나중 단계의 가설로 남긴다.
- **보고서(`reports/report-<날짜>.md`)는 구조적으로 불가능하다.**
  - 날짜로 이름을 짓는 것은 코어의 경로 관계 언어(`o`, `D`, `D/name(o)`)로 표현할 수 없다.
  - 규칙 자체가 한국어 메모에 있다.

---

## 2. 과제 전달 브리지와 교사 역할

### 2.1 브리지 (평가기 쪽, `life/trackA/bridge.py`)

```
하루 = world.setup_day(home, day)          # 같은 함수, 같은 파일 (LLM 실행과 동일한 집 상태로 시작)
      FRESH이면 mind/ 삭제(보관)            # 두 쪽 정의 동일
      lines = tasks.md의 "- [id] 문장" 줄      # agent.task_ids와 같은 정규식
      for (tid, 문장) in lines:              # 과제를 거르지 않는다. 시도할 수 없는 과제도 그대로 넘긴다
          teacher.begin(TASK_TRUTH.get((day, tid)))   # 진실이 없으면 point → 대상 없음
          r = Mind(home, mind, lab, user=teacher_or_None, seed=...).do(command(문장), f'd{day}-{tid}')
          행 기록: outcome(success/wrong/held), claim=r['achieved'] is True, help 증감, counts
      주인이 있는 날이면: resume_goals (life_gen과 같은 방식, still_wanted를 센다)
      j = world.judge(home, day); s = world.score(j); s['false_done'] = world.false_done(j, claimed_ids)
      results.json 을 트랙 L과 같은 스키마로 씀  → life/analyze.py 가 그대로 읽는다
```

정직성 규칙은 다섯이다.
- (a) **과제를 미리 거르지 않는다.** 시도할 수 있는지는 ATANOR가 스스로 드러내야 한다(보류 또는 not understood). 시도 가능 여부 표는 보고용으로만 쓰고, 실행 경로에는 넣지 않는다.
- (b) 브리지가 `tasks.md`를 줄 단위로 잘라 주는 일은 **제공된 지각**이다. `life_gen`이 명령을 하나씩 주는 것과 같은 지위다. 보고서에 명시한다.
- (c) Mind는 `world.judge`와 `TASK_TRUTH`를 볼 수 없다. 교사 객체만 진실에 닿는다. `agent/`가 `teach/`·`eval/`를 import하지 않는다는 ATANOR 규칙을 따른다.
- (d) 집(home)은 시스템마다, 조건마다 따로 둔다. 같은 `setup_day`로 만들므로 시작 상태가 같다.
- (e) `inbox/tasks.md`와 `note*.md`도 집 안의 대상이다. ATANOR가 이것을 옮기면 부수 피해(collateral)로 센다(3.2절).

### 2.2 명령 언어: 두 모드

| 모드 | ATANOR에 넣는 문자열 | 장점 | 단점 |
|---|---|---|---|
| **KO (1차)** | `tasks.md`의 한국어 원문 그대로 | **두 시스템의 입력이 완전히 같다.** 해석이 개입하지 않는다. | 토크나이저가 한글을 지운다(0.4절). 남는 것은 경로 조각뿐이다. ATANOR의 언어 학습은 거의 측정되지 않는다. |
| **EN (2차, 진단)** | 실행 전에 동결한 영어 직역(`gloss_v1.json`, sha256을 프로토콜에 기록) | ATANOR 어휘 학습이 실제로 작동하는 조건이다. | 번역자가 개입한다. 번역은 결과를 보기 전에 한 번만 쓰고, life_gen 문법에 맞춰 다듬지 않는다(직역 원칙). 대칭을 위해 LLM도 같은 영어로 한 번 돌린다(LLM-EN 대조군). |

- 직역 예(EN): "Move only the receipts among the files in inbox/files/ into the receipts/ folder. Leave the other files as they are."
- 2일차는 "Organize the new files in inbox/files/ the same way as yesterday."다. `organize`, `yesterday`, `like`/`same way`는 1일차에 없던 말이다. 그래서 EN에서도 2일차는 **기억과 유추가 둘 다 필요한 진짜 시험**이 된다.

### 2.3 교사 역할 — 같은 정보 원칙

LLM 세계의 주인은 "대개 부재"다. LLM은 주인 정보를 **집 안의 메모**로만 얻는다. ATANOR는 처음 보는 명령을 교사 없이는 이해할 수 없다(`_understand`가 패턴이 없으면 시범을 요구한다). 이 비대칭을 숨기지 않고 조건으로 드러낸다.

| 교사 모드 | ATANOR | LLM | 무엇을 묻는가 |
|---|---|---|---|
| **T0 부재** (트랙 L 기본) | `user=None` 매일 | `ask_user` → "부재" (지금 그대로) | 같은 정보만으로 무엇을 하는가. ATANOR는 처음부터 혼자이므로 아마 전부 보류한다(예측, 2.5절). |
| **T1-D1 진실 교사, 메모가 있는 날만** (주 비교 조건) | 1일차(v2는 메모가 있는 1·3·5일차)에만 `TrackATeacher`, 나머지 날은 `None` | 같은 날에만 `ask_user`에 **같은 교사 객체가 글로 답한다**(`OwnerText`). 나머지 날은 부재. | 주인이 메모를 남긴 날만 있다는 세계 이야기와 맞다. LIFE−FRESH 차이가 곧 **기억이 2일차 이후로 넘어가는가**다. |
| **T1-ALL** (상한, 진단) | 매일 교사 | 매일 `OwnerText` | 도움을 무제한으로 주면 도움 수는 어떻게 줄어드는가. ATANOR 90일 생활의 "도움 감소 곡선"에 해당한다. |
| **T2 LLM 교사** (사다리 단) | `LLMTeacher`(Qwen이 집 파일을 읽고 구조화된 답을 함) | — | 불완전한 교사. 채점은 여전히 `world.judge`(진실)가 한다. |

**`OwnerText`(LLM에게 주는 같은 진실).**
- `ask_user(question)`에는 질문 내용과 상관없이 그 과제의 `point` 답을 한국어로 한 번 준다. 예: "그 일에서 말하는 파일은 inbox/files/a.txt, inbox/files/c.txt이고, 목적지는 receipts/ 폴더야."
- 지금 집 상태가 그 과제를 만족하면 "지금 상태가 맞아"를 덧붙인다. 이것은 confirm에 해당한다.
- 진실이 없는 과제(수도, 보고서 등)에는 "그건 메모나 할 일에 적힌 대로 해"라고 답한다. ATANOR 교사가 그 과제에 `point → 대상 없음`을 돌려주는 것과 정보량이 같다.
- 질문 1회 = point 1로 센다. 답에 확인이 붙으면 confirm 1을 따로 센다.
- 구현에는 `agent.Body.execute`의 `ask_user` 분기에 선택적 훅이 필요하다. 트랙 L 에이전트 판본을 `agent-v4o`로 올려 기존 결과와 섞이지 않게 한다.

**ATANOR 진실 교사(`TrackATeacher`, `life_teacher.Teacher`를 재사용하지 않고 새로 씀).**
- `begin(truth)`: `before` = 집 전체 파일의 해시. `truth` = 내용과 위치로 계산한 대상 목록.
- `explain(word)`: 직역 모드에서만 의미가 있다. 동결된 `EXPLAIN_MAP`(낱말 → 쉬운 영어 또는 `''`)을 쓰고, 없으면 `None`.
- `point`, `demonstrate`(`mkdir D` + `move(o, D/name(o))`), `demonstrate_goal`, `check`(`Teacher.check`와 같은 판정, 경로만 `D/name(o)`).
- `confirm`은 `world.task_ok(world.judge(home, day), tid)`와 **같은 함수**다. 확인과 채점이 갈라질 수 없다.
- `still_wanted`도 같은 판정을 쓴다.

### 2.4 시도 가능 과제 표 (보고용, 실행 경로에 넣지 않음)

| 세계 | 과제(채점 항목 수) | LLM | ATANOR(`home` 몸) | 이유 |
|---|---|---|---|---|
| v1 d1 | note (채점 없음) | 가능 | 해당 없음 | 기억 과제의 원천. ATANOR는 한국어 메모를 읽지 못한다. |
| v1 d1 | capitals (3) | 가능 | **불가** | 글쓰기와 사실 조회 |
| v1 d1 | **receipts (1)** | 가능 | **가능** | `head`+`loc`, move/mkdir |
| v1 d1·d2·d3 | report (각 1) | 가능 | 불가 | 날짜로 짓는 이름, 글쓰기, 메모 속 규칙 |
| v1 d2 | cat (1) | 가능 | 불가(1.3절의 줄 대상이 있으면 가능성 있음) | 글쓰기 |
| v1 d2 | **receipts (1)** | 가능 | **가능** | 기억("어제처럼")이 필요하다 |
| v1 d2 | capitals 뉴질랜드 (1) | 가능 | 불가 | |
| v1 d3 | fiction (1), gift (1) | 가능 | 불가 | '확인 불가'를 쓰는 것도 글쓰기다. **ATANOR의 할루시네이션 0은 능력이 아니라 무능이다.** 표에는 "해당 없음"으로 쓴다. |
| v2 | receipts d1·d2 (2/18) | 가능 | 가능 | 나머지 16개(초대장, 규칙 변경 보고서, 고양이, 요약표, 가짜 나라)는 불가 |

**보고 규칙.** 결과 표에 전체 점수(v1 /12, v2 /18)와 **시도 가능 부분집합 점수**(v1 /2, v2 /2, W-F 전체)를 함께 낸다. 할루시네이션·근거 없는 쓰기 지표는 ATANOR에서 `n/a`로 쓰고, 0으로 쓰지 않는다.

### 2.5 사전 예측 (M1 실행 전에 적어 둠)

- T0, KO: ATANOR LIFE·FRESH 모두 0/12다. 모든 과제가 보류이고 `false_done`은 0이다. 패턴이 없으면 혼자서는 시범을 받을 수 없다(`_teach_from_demo`는 `user is None`이면 False).
- T1-D1, KO: 1일차 영수증은 성공할 것이다(point·시범·확인 도움이 몇 번 필요하다). 2일차 영수증은 보류할 것이다. 토큰이 `['inbox','files']`뿐이라 목적지가 없고, 주인도 없다. 그러면 LIFE와 FRESH가 거의 같다. 기억은 있지만 그 기억에 닿을 말이 없다.
- T1-D1, EN: 2일차에 `organize`·`yesterday`라는 처음 듣는 말이 결정 낱말 자리에 오므로 아마 보류한다. 유추로 성공한다면 그것이 가장 흥미로운 결과다.
- 틀린 행동(메모 이동 등): T0·T1 모두 0에 가까울 것이다. 사람이 없을 때 지지 없는 읽기는 실행하지 않는다(`_complete`).

---

## 3. 공통 지표와 프로토콜

### 3.1 같게 고정하는 것

- 세계 모듈(`world.py` = life-v1, `world_v2.py` = life-v2, 이후 W-F), `setup_day`, `DATES`, `judge`, `score`, `false_done`. 세 모듈의 sha256을 프로토콜에 기록한다.
- 날 수, LIFE/FRESH 정의(FRESH = 매일 아침 `mind/`를 보관 폴더로 옮김, 집은 유지).
- 교사 모드와 주인이 있는 날의 일정.
- 집 시작 상태(매 조건 빈 root에서 시작).
- 결과 스키마: `results.json` = `{protocol, agent, cond, sampling, days: {d: {judge, score, stats, wall_sec}}}`. ATANOR는 `agent = "atanor-life-v24/home-1/bridge-1"`이고, `stats`에 `steps`, `done`, `ended`, `stopped` 등 트랙 L 키를 채운다. 그래야 `life/analyze.py`가 수정 없이 읽는다.

### 3.2 지표 (모든 시스템·혼합체에 같은 정의)

| 지표 | 정의 | LLM에서 얻는 곳 | ATANOR에서 얻는 곳 |
|---|---|---|---|
| `total_ok` | `world.score` ok 합 | 있음 | 브리지가 같은 함수로 계산 |
| `attemptable_ok` | 2.4절 부분집합의 ok 합 | `compare.py`가 judge에서 계산 | 같음 |
| `memory_ok` | 세계의 `MEMORY_TASKS` | analyze.py | 같음 |
| `false_done` | 했다고 했는데 판정 실패 | `done` id | `claim`(achieved True) id |
| `held` | 주장도 하지 않고, 관련 변화도 없는 과제 | 브리지 사후 계산(done 없음 + 대상 불변) | Mind outcome `held` |
| `wrong` | 행동했는데 판정 실패 | 행동함(관련 파일 변화) + 실패 | outcome `wrong` |
| `collateral` | **그날 시작 때 있던 파일 중, 진실 명세가 허용하지 않는 변경·삭제·이동의 수.** 자유 글쓰기 과제의 허용 집합은 그 과제가 쓰라고 한 경로다. | 공통 `collateral.py`(날 전후 스냅샷 비교) | 같음 |
| `preserved` (v1 d3) | 이전 날 수도 줄이 남았는가 | judge | judge |
| `help_asks` | 도움을 청한 횟수(답이 없어도 셈) | `ask_user` 수 | 교사 메서드 호출 수. T0에서는 Mind가 묻지 않으므로 0이다. 그 사실 자체를 보고한다. |
| `help_answered` / `help_score` | 실제로 받은 답, 가중치 explain/point/check/recall 1, demonstrate 2, demonstrate_goal 3. confirm은 별도 열. | `OwnerText` 기록 | `teacher.help` |
| `actions_home` | 집에서 한 행동 수(관측 행동 제외) | write/append/move/mkdir(/copy) | `counts['home_actions']` |
| `actions_lab` | 실험실 행동 | 0 | `lab_actions + rehearsal_actions` |
| 비용 | wall 초, LLM 생성 토큰, 예측 호출 | stats `tok_gen`, `sec_llm` | 행별 seconds, (선택) 예측 수 |
| 사실 할루시네이션 / 근거 없는 쓰기 | 트랙 L 정의 | analyze.py | **n/a** |

### 3.3 반복과 불확실성

- **LLM**: 기존과 같다. temperature 0 1회 + 0.6 시드 1~10. 서버 하나에서 동시 실행하지 않는다(exp2v3의 재현성 문제).
- **ATANOR**: 결정적이다. `Mind(seed=...)`가 실험 순서만 바꾼다. 시드 1~11로 11회 돌려 표본 수를 맞춘다. 같은 시드를 다시 돌려 같은 결과가 나오는지를 유효성 게이트로 삼는다.
- **차이 구간**: `analyze.boot_diff`(독립 표본 부트스트랩 95%)를 그대로 쓴다. 시드 짝짓기는 하지 않는다.

### 3.4 동결과 무효 규칙 (ATANOR EXPERIMENT_PROTOCOL을 따름)

- `life/trackA/protocol_A1.json`에 실행 전에 적을 것:
  - 세계 판, 세 모듈의 sha256
  - ATANOR 스냅샷 커밋과 `agent/`, `core/`, `world/`, `teach/` 소스 sha256
  - 브리지·교사·`TASK_TRUTH`·gloss·`EXPLAIN_MAP`의 sha256
  - 조건 목록, 교사 모드, 주인이 있는 날, 시드, 예산
- **INVALID 조건**
  - 실행 중 소스 sha256이 바뀌었다.
  - HAND/ORACLE 게이트가 실패했다. 평가기 쪽 스크립트 해결사가 시도 가능 과제에서 100%를 못 냈다. 이 해결사는 `life_gen.hand_do`처럼 진실 명세로 바로 실행한다.
  - 실행 인자가 프로토콜과 다르다.
  - ATANOR 테스트 게이트(`pytest -m "not learning and not timing"`)가 실패했다.
- **개발과 평가 분리 (중요).** LLM 세계는 시드가 없는 고정 세계다. 브리지나 몸을 v1에서 다듬으면 평가가 오염된다.
  - 개발은 **변형 세계 `life-v1-dev`**에서만 한다. 파일 이름, 가게, 첫 줄 낱말 위치를 바꾸고, 영수증 첫 줄을 `[영수증]` 또는 `Receipt`로 바꾼 것도 섞는다.
  - v1/v2 본 실행은 판본마다 한 번 돌리고, 결과를 본 뒤에 고치지 않는다. 고치면 새 실험 이름을 쓴다.
- `head` 관측은 "영수증이 첫 낱말"이라는 세계 지식을 알고 고른 설계다. 그래서 그 정의(첫 줄 첫 토큰)를 이 문서에서 미리 고정한다. W-F에서는 판별 낱말이 첫 토큰이 아닌 과제도 넣어 관측 설계의 한계를 따로 잰다.

### 3.5 공용 파일 세계 W-F (`life/world_fs.py`, life-fs-v1, M2)

v1/v2에서는 ATANOR가 2개만 시도할 수 있다. 그래서 두 시스템이 **모든 과제를 시도할 수 있는** 7일 고정 세계를 하나 더 둔다.
- **형식은 트랙 L 세계와 같다**: `DAYS`, `setup_day`, `judge`, `score`, `false_done`, `MEMORY_TASKS`, 한국어 `tasks.md`, 동결된 EN 직역.
- **과제는 파일 정리만 한다**: 내용 종류(영수증, 메모, 계약서)나 확장자나 위치로 고르고, 옮기거나 복사(백업)한다. 목적지는 고정이거나 새 이름이다.
- 3일차에 **규칙 변경**이 있다(영수증 → `ledger/`). 2일차, 4일차, 6일차는 "어제처럼"으로 기억 과제다. 주인 메모는 다음 날 치운다(v2 규칙).
- 대상이 아닌 파일을 일부러 섞어 부수 피해를 측정한다. 이미 정리된 파일과 같은 종류의 새 파일이 오면 `loc` 원자가 필요해진다.
- 양쪽 도구: LLM `list/read/move/mkdir/copy`(+기존 행동), ATANOR `mkdir/move/copy`.
- 세계 변화(예: 5일차부터 `move`가 폴더 목적지를 받지 않음)를 넣을지는 5절의 열린 질문으로 둔다.

### 3.6 테세우스 사다리 — 같은 표에 놓을 단

부품은 일곱 가지다. ① 지각 ② 의도 해석 ③ 계획·실행·검증 ④ 장기 기억 ⑤ 글 생성 ⑥ 사실 조회 ⑦ 교사.

| 단 | ① | ② | ③ | ④ | ⑤⑥ | ⑦ | 구현 |
|---|---|---|---|---|---|---|---|
| R0 LLM (트랙 L agent-v4) | LLM | LLM | LLM | memory.md | LLM | 부재/OwnerText | 있음 |
| R1 ATANOR 손 | LLM | LLM → 구조화 의도 `{change, objects, dest}` | **ATANOR** (Goal + planner + 학습된 세계 모델 + 실험실 리허설 + 검증) | memory.md + ATANOR episodes | LLM | 같음 | LLM 행동에 `organize(task, objects, dest, change)` 추가. 브리지가 Goal을 만들어 Mind의 실행부로 보낸다(아래 위험 참조). |
| R2 ATANOR 마음, LLM 교사 | ATANOR | **ATANOR**(LLM이 explain/point/check/confirm에 답) | ATANOR | ATANOR | 불가 | LLM | `LLMTeacher` |
| R3 R2 + 교사 소멸 | ATANOR | ATANOR | ATANOR | ATANOR | 불가 | LLM은 메모가 있는 날만 | 같은 코드, 일정만 다름 |
| R4 ATANOR 단독 | ATANOR | ATANOR | ATANOR | ATANOR | 불가 | T0 / T1(상한) | M1 |
| 혼합 R5 (목표) | ATANOR | ATANOR(파일)·LLM(글) | ATANOR(파일)·LLM(글) | ATANOR + memory.md | LLM | 부재 | R1과 R2의 합: 과제 종류별 라우팅 |

- 각 단은 3.2절의 같은 지표 열을 채운다. 추가 열은 "누가 답했나"(사람 진실, LLM, 없음)와 "LLM 토큰"이다.
- **주장은 단 사이의 차이로만 한다.** 예: R1−R0 = 실행·검증을 ATANOR로 바꾼 효과. 영수증 부분집합과 collateral에서 본다.

---

## 4. 파일 단위 구현 계획

### 4.1 ATANOR 저장소 (브랜치 `trackA`, 분류 ③ "몸 어댑터", `agent/`·`core/`는 한 줄도 바꾸지 않음)

| 파일 | 내용 | 크기 |
|---|---|---|
| `world/home_world.py` (새 파일) | `HomeWorkspace(Workspace)`: `BODY='home'`, `TOOLS={'mkdir':1,'move':2,'copy':2}`, `CAPABILITY={}`, `attrs()`에 `head`·`loc` 추가(head는 파일 앞 256바이트만 읽음), `tools()`는 drift 없이 위 세 개(선택: drift 훅), `lab_from_state`는 head를 되살리는 자리표시자, `ENV_VERSION='homeworld-1/...'` | ~90줄 |
| `world/raw_obs.py` (분기 추가) | `IDENTITY['home']=('a3',)`, `KIND_ATTRS['home']=('a0','a1')`, `raw_attrs`: a0..a3는 fs와 같고 `a4=head`, `a5=loc`. `related`/`neighbours`/`recompute_derived`: `body in ('fs','home')`. `to_human`: 역변환에 head 추가(loc은 old에서 유지). | +20줄 |
| `tests/test_home_world.py` (새 파일) | ① 영수증·메모의 원자 집합이 다르다(0.3절의 반례) ② move 후 `D/o`의 a4 = o의 a4, 두 대상의 a5는 불변 ③ 없는 경로에도 loc가 계산된다 ④ `lab_copy`가 head를 보존한다 ⑤ `lab_from_state`가 head를 되살린다 ⑥ `raw_attrs`↔`to_human` 왕복 ⑦ delete/convert가 없다(`invalid action`) ⑧ 경로 격리(`..`, 절대경로, 심볼릭 링크) ⑨ `agent/` sha256 불변 확인(누출 테스트에 몸 하나 추가) | ~110줄 |
| 스냅샷 | `runs/_scripts/snap.py`로 `snap-trackA-1`을 만든다. 평가 실행은 스냅샷에서만 한다. | — |

운영 규칙: ATANOR의 몸 인터페이스 확장은 CURRENT_STATE.md 1절이 허용하는 경로다. 그래도 코어 동결 원칙에 맞추려면 **런타임 몽키패치(Qwen 저장소에서 raw_obs를 덮어쓰기)는 금지**한다. 보이지 않는 코어 변경이 되기 때문이다.

### 4.2 Qwen 저장소 `life/trackA/` (평가기 쪽, 표준 라이브러리만, ATANOR를 `sys.path`로 import)

| 파일 | 내용 | 크기 | 단계 |
|---|---|---|---|
| `__init__.py` | | 0 | M1 |
| `truth.py` | `TASK_TRUTH[(protocol, day, tid)] = fn(home) -> {tool, objects, dest}` (v1·v2 영수증: `inbox/files/` 안에서 head가 `영수증`인 파일, move, `receipts`), `ATTEMPTABLE` 표(보고용), `hand_solve(home, truth)`(HAND/ORACLE 게이트) | ~80 | M1 |
| `teacher.py` | `TrackATeacher`(2.3절, confirm = `world.task_ok(world.judge(...))`), `Schedule`(주인이 있는 날), `OwnerText`(LLM용 같은 진실의 글 렌더링) | ~160 | M1 (OwnerText는 M1b) |
| `bridge.py` | `run_day(root, world, day, cond, teacher_mode, lang, seed)`: 2.1절 흐름 그대로. 행 기록은 `days.jsonl`(life_gen과 같은 키), `results.json`은 트랙 L 스키마, 날 끝 스냅샷 | ~200 | M1 |
| `collateral.py` | 날 전후 파일 해시 스냅샷 → 허용 집합 밖의 변경 수. LLM 기존 실행에도 소급 적용한다(`runs/*/home`에 날별 스냅샷이 없으므로 LLM은 마지막 날 기준으로만 계산. 앞으로의 실행에는 날 스냅샷 추가). | ~60 | M1 |
| `run_a.py` | CLI: `--root --world v1|v2|fs --cond LIFE|FRESH --teacher absent|d1|all|llm --lang ko|en --seed --days`. `run.py`와 같은 모양. | ~70 | M1 |
| `compare.py` | 여러 실험 폴더(LLM과 ATANOR)를 읽어 3.2절 표, 시도 가능 부분집합, 부트스트랩 차이를 낸다. `analyze.summarize`를 재사용한다. | ~120 | M1 |
| `protocol_A1.json` | 3.4절 동결 기록 | — | M1 |
| `gloss_v1.json`, `gloss_v2.json`, `explain_map.json` | EN 직역과 교사 설명표(동결, sha256) | — | M1b |
| `llm_teacher.py` | `LLMTeacher`: point/check/explain/demonstrate/confirm을 Qwen JSON 호출로(스키마 강제, 경로 존재 검증, 도구 이름 검증), 호출과 토큰 기록 | ~170 | M3 |
| `organize.py` | R1: LLM의 구조화 의도 → `Goal` → Mind 실행부(`_achieve`) 호출 | ~120 | M4 |
| `life/world_fs.py` | W-F 세계(3.5절) | ~200 | M2 |
| `life/agent.py` 수정(판본 v4o) | `ask_user`의 선택적 owner 훅, W-F용 `copy` 행동(플래그). 기존 v2~v4 동작은 바뀌지 않는다. | +25 | M1b/M2 |
| `life/trackA/test_trackA.py` | 아래 4.3절 | ~150 | M1 |

### 4.3 시험 계획

1. **게이트**: v1·v2에서 `hand_solve`가 영수증 1·2일차를 `world.judge` ok로 만든다. 끝 상태가 judge 조건과 정확히 맞는지 확인한다.
2. **교사 일관성**: 진실 제안으로 `TrackATeacher.check`를 부르면 True, 메모를 끼우면 False. 해결사 실행 뒤 `confirm`은 `world.task_ok`와 같다. 시작 상태에서는 `still_wanted`가 True다.
3. **브리지 스키마**: `run_a` 1일 실행 결과를 `analyze.load`/`summarize`가 예외 없이 읽는다. `days` 키, `score`, `false_done`이 있어야 한다.
4. **FRESH**: 2일차 시작 때 `mind/`가 비어 있고 보관본이 있다. home은 유지된다.
5. **누출**: Mind 쪽에서 `truth`·`world` 모듈이 import되지 않았다(`sys.modules` 검사는 Mind 생성 시점이 아니라 별도 프로세스 실행으로 확인). 실행 전후로 ATANOR 소스 sha256이 같다.
6. **결정성**: 같은 시드 두 번 → `days.jsonl` 동일(시간 필드 제외).
7. **스모크(빠른 실행, 학습 단정 없음)**: T1, KO, v1 1일차 하나. 끝까지 예외 없이 끝나고 행이 4개다(교사에게 묻는 횟수는 단정하지 않는다. `learning` 마커).
8. **경로 길이**: root를 짧게 잡는지 확인한다(Windows MAX_PATH).

### 4.4 마일스톤

- **M1 (첫 비교 수치, 가장 작음)**
  - 4.1절 전부 + `truth`·`teacher`(OwnerText 제외)·`bridge`·`collateral`·`run_a`·`compare`·테스트. 약 450줄 + 테스트 약 260줄이다.
  - 실행: 세계 v1, 3일, `--lang ko`, {LIFE, FRESH} × {absent, d1}, 시드 1~11 (ATANOR라 빠르다. 예산 상한으로도 한 날 몇 분 안).
  - 산출: ATANOR `total_ok`/12, **영수증 부분집합 /2**, false_done, held, wrong, collateral, help. **LLM은 새로 돌리지 않는다.** exp1(agent-v2)·exp2v3·exp4v4w1과 같은 표에 놓는다.
  - 공정성 주의: 기존 LLM 실행은 T0(부재)뿐이다. 그래서 M1에서 **정직하게 맞대는 칸은 T0 대 T0**다. T1-d1 ATANOR는 "도움을 받으면 어디까지"를 보여 주는 참고 칸이다.
- **M1b**: OwnerText를 붙인 LLM T1-d1 실행(agent-v4o, v1, 조건당 11회). 이것으로 T1 대 T1 칸이 채워진다. EN 직역(ATANOR-EN, LLM-EN)도 여기서 돌린다.
- **M2**: W-F 세계, 두 시스템, T0와 T1-d1, LIFE/FRESH. 모든 과제를 시도할 수 있는 세계에서의 첫 정면 비교다.
- **M3**: R2/R3(LLMTeacher). 사람 진실 교사를 LLM으로 바꿨을 때 ATANOR의 성공, 틀림, 도움.
- **M4**: R1(ATANOR 손)과 R5 라우팅.

---

## 5. 위험과 열린 질문

### 위험

1. **관측이 과제를 안다.** `head`와 `loc`은 이 세계의 영수증 과제를 보고 고른 관측이다. 완화책은 셋이다. 정의를 지금 동결한다. 개발은 변형 세계에서만 한다. W-F에 첫 토큰이 아닌 판별 과제를 넣는다. 그래도 "몸 설계자가 문제를 반쯤 풀어 줬다"는 비판은 남는다. 보고서에 명시한다.
2. **언어 통로가 거의 비어 있다.** KO 모드에서 ATANOR는 경로 토큰만 본다. ATANOR의 강점(어휘 학습)은 EN에서만 측정되는데, EN에는 번역자가 개입한다. 두 모드를 따로 보고하고 섞지 않는다.
3. **정보 비대칭.**
   - 진실 교사는 LLM이 한 번도 받지 못한 답을 준다. 그래서 같은 교사를 LLM에도 붙인 칸(M1b) 없이 T1 ATANOR와 T0 LLM을 비교하면 안 된다.
   - 거꾸로, LLM은 한국어 메모에서 주인 사실을 얻는다. ATANOR는 그 통로가 없다. 이것은 능력 차이이고 설정의 불공정은 아니다.
4. **총점의 착시.** v1의 10/12는 글쓰기 과제다. ATANOR의 총점은 구조적으로 2/12가 상한이다. 할루시네이션 0도 무능에서 나온다. 표의 1차 열은 시도 가능 부분집합이다.
5. **도구 의미 차이.** LLM `move`는 폴더 자동 생성과 폴더 안 이동을 해 준다. ATANOR `move`는 원시적이다. 같은 이름 다른 의미라서 행동 수 비교는 참고로만 쓴다.
6. **`loc`의 부작용.** E 원자(`o`와 `D/o`의 loc 같음/다름)가 move 전제조건 규칙에 끼어 엉뚱한 일반화를 만들 수 있다. 대조 유도가 실패 사례로 걸러야 한다. `test_learning`급 확인이 필요하다.
7. **부수 피해의 정의.** 자유 글쓰기 과제의 허용 집합(어떤 파일을 고쳐도 되는가)은 판정기 바깥의 추가 정의다. 사전에 동결하지 않으면 사후 조정이 된다.
8. **R1의 사적 API.** Mind의 `_achieve`나 `_goal` 직접 호출은 v24 내부에 기대는 일이다. 코어는 동결되어 있으므로 동작은 안정적이다. 그래도 공개 인터페이스는 아니다.
9. **재현성.** ATANOR는 결정적이고 LLM은 확률적이다. 표본 성격이 다르다. 부트스트랩은 같은 방식으로 하되 해석은 따로 한다.
10. **Windows 경로 길이.** 실험실과 스냅샷 폴더가 깊어지면 실패한다(확인함). root를 짧게 쓴다.
11. **세계 고정.** v1/v2는 시드가 없다. 같은 세계를 반복해 개발하면 바로 과적합된다. 판본마다 한 번 실행한다.

### 열린 질문

1. 코어로 `life.py` v24(영어 명령 생활)를 쓸 것인가, `grounding.py` 학습기(g30~, 1세대 동결, 교사와 함께 배우는 쪽)를 쓸 것인가?
   - 이 설계는 `Mind.do(command)` API와 생활 평가 틀이 맞는 v24를 M1에 쓴다.
   - grounding 학습기는 사다리의 별도 단(R4')으로 같은 표에 추가하는 편이 낫다고 본다.
2. LLM 세계에도 도구 변화(drift)를 양쪽에 같이 넣을 것인가? ATANOR의 강점(실험실 회복)은 거기서만 드러난다. 다만 LLM 쪽 도구 실패 메시지를 어떻게 줄지(오류 문자열 vs 조용한 실패)가 공정성 문제다.
3. 줄 단위 텍스트 대상(1.3절)으로 `cat`, `catfix`, `card`를 도달 가능하게 할 것인가? 이것은 사실상 새 몸이고, DESK_BODY 설계(4번째 몸)와 겹친다.
4. `OwnerText`의 답 정보량을 ATANOR `point`와 정확히 맞추는 방법. 지금 안은 질문과 무관한 고정 답 1회다. LLM의 자유 질문에 답하지 않는 것이 공정한가, 아니면 LLM의 장점을 깎는 것인가?
5. 도움 가중치(explain 1 … demonstrate_goal 3)를 LLM의 자유 질문에 어떻게 매길 것인가? 지금 안은 질문 1회 = point 1이다.
6. 주인이 있는 날의 일정. v1은 1일차만, v2는 메모가 있는 1·3·5일차. 주인이 다시 오는 날에는 `resume_goals`(still_wanted)도 센다. LLM에는 대응하는 행동이 없다(LLM은 보류한 일을 다음 날 다시 꺼내지 않는다). 이 비대칭을 지표로 둘지 정해야 한다.
7. ATANOR에 `copy`를 줄 것인가? LLM v1/v2에는 copy가 없다. M1에서는 그대로 두되(세계 v1에 copy 과제가 없음), W-F에서는 양쪽에 준다.
