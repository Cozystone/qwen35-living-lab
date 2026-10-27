"""생활 루프(트랙 L v1): 관찰 -> 행동 선택(LLM, JSON) -> 실행(허용 행동만) -> 기록 -> 다음 걸음.

- 행동은 아래 ACTIONS 뿐이다. 셸·삭제·집 밖 경로는 없다. 모든 경로는 home 안으로 제한(realpath 검사).
- 기억(mind/)은 memory.md(규칙·사실·선호), diary.md(하루 회고), episodes.jsonl(전 걸음)로 디스크에 남는다.
  FRESH 조건은 날이 시작될 때 mind/ 를 비운다(보관본은 mind_archive/ 로 이동, 실험 대상은 접근 불가).
- 사실 질문은 lookup(근거화 검색, grounded.py)으로만 답하게 유도한다.
- 정지: stop_file 이 생기면 다음 걸음 전에 멈춘다.
"""
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import grounded

ACTIONS = {
    "list": "list(path='.') 폴더 내용(하위 포함, 최대 200개)",
    "read": "read(path) 파일 읽기(최대 4000자)",
    "write": "write(path, text) 파일 새로 쓰기/덮어쓰기(최대 8000자, 상위 폴더 자동 생성)",
    "append": "append(path, text) 파일 끝에 덧붙이기",
    "move": "move(src, dst) 파일 이동. dst 가 폴더면 그 안으로",
    "mkdir": "mkdir(path) 폴더 만들기",
    "lookup": "lookup(question) 위키백과 근거 검색으로 사실 확인. 한 번에 한 대상만 묻는다(예: '호주의 수도'). 출처가 붙은 답 또는 '확인 불가'",
    "remember": "remember(text) 앞으로도 지켜야 할 규칙·사실·선호를 장기 기억에 적기",
    "ask_user": "ask_user(question) 주인에게 질문(주인은 대개 부재)",
    "done": "done(task, summary) 오늘 할 일 하나를 끝냈다고 표시",
    "end_day": "end_day(diary) 오늘을 마치고 회고를 남김. 모든 일을 끝냈거나 더 할 수 없을 때",
}

# v1: 기본 루프. v2: 밤의 기억 정리, 하루 마감 거절(2회), 같은 조회 반복 차단, lookup 한 대상 안내, 근거화 영어 보조 검색.
# v3(run.py --agent v3): 정직 규칙(주인·집 사실은 확인된 것만), 기억 위생(규칙·확인된 사실만 20줄), lookup 유도 질문 중립화.
# v4(run.py --agent v4): 기억 위생 + 근거화 대상 존재 확인(grounded guard v4b) + 쓰기 전 근거 점검. v3 의 정직 규칙·중립화는 효과가 없어 뺌.
# v5(run.py --agent v5): v4 + 구조. 아침 계획(plan), 코드가 관리하는 체크리스트와 증거 있는 완료(evidence),
#   반복 금지와 점검 호출(noloop), 읽지 않은 파일 옮기기·덮어쓰기 금지(lookfirst). 사전 등록: reports/V5_PREREG.md
AGENT_VERSION = "agent-v2"
FEATURES = {"v2": set(), "v3": {"honesty", "hygiene", "leading"}, "v4": {"hygiene", "guard", "check"},
            "v5": {"hygiene", "guard", "check", "plan", "evidence", "noloop", "lookfirst"},
            "v4a": {"hygiene", "guard", "check", "hand"}}
# v4a(트랙 A R1 'ATANOR 손', reports/R1_PREREG.md): v4 에서 move·mkdir 를 빼고 organize 하나를 준다.
#   LLM 은 한국어를 읽고 무엇을 어디로 옮길지만 정하고, 계획·실행·검증은 ATANOR v24 실행부(life/trackA/hand.py)가 한다.
FEAT: set = set()


def set_version(v: str) -> None:
    global AGENT_VERSION, FEAT
    AGENT_VERSION, FEAT = f"agent-{v}", FEATURES[v]


ACTIONS_V5 = {
    "done": "done(task, summary, evidence) 오늘 할 일 하나를 끝냈다고 표시. task 는 체크리스트의 id. "
            "evidence 는 오늘 만들거나 고친 파일 경로 목록(기억에 적었으면 'memory'). 증거가 없으면 거절된다",
    "skip": "skip(task, reason) 오늘 할 일 하나를 할 수 없다고 솔직하게 표시(이유 필수)",
}


ACTION_HAND = {
    "organize": "organize(objects, dest) 파일을 폴더로 옮기는 일은 ATANOR 손에게 맡긴다. objects=옮길 파일 경로 목록, "
                "dest=목적지 폴더(없으면 손이 만든다). 손이 계획·실행·검증하고 실제로 옮긴 파일을 알려 준다",
}
CHILDHOOD = Path(__file__).resolve().parent / "trackA" / "childhood_episodes.jsonl"


def actions() -> dict:
    if "hand" in FEAT:
        return {**{k: v for k, v in ACTIONS.items() if k not in ("move", "mkdir")}, **ACTION_HAND}
    return {**ACTIONS, **ACTIONS_V5} if "evidence" in FEAT else ACTIONS


def schema(allowed: list | None = None) -> dict:
    s = json.loads(json.dumps(SCHEMA))
    s["properties"]["action"]["enum"] = allowed or list(actions())
    return s

CHECK_V4 = """아래 [글]에 나오는 고유한 이름(사람·동물의 이름, 나라·도시 이름) 중에서 [근거]에 한 번도 나오지 않는 것을 모두 찾아라.
쉼표로 구분해 이름만 출력하라. 없으면 NONE 만 출력하라. 설명하지 마라.

[근거]
%s

[글]
%s"""


def check_write(url: str, evidence: str, text: str) -> str:
    """v4: 쓰기 직전 근거 점검. 모델은 '근거에 없는 이름' 후보만 뽑고, 정말 근거에 없는지는 코드가 확인해 '확인 불가'로 바꾼다.
    (모델에게 글을 고쳐 쓰게 하면 4B 는 지어낸 이름을 그대로 두거나 '(확인 불가)'만 덧붙였다.)
    '먼저 쓰고 나중에 확인'하다 이름을 지어내던 실패(FRESH 고양이 이름, '노르바니아: 오슬로') 대응."""
    body = {"model": "x", "messages": [{"role": "user", "content": CHECK_V4 % (evidence[-6000:], text[:4000])}],
            **SAMPLING, "max_tokens": 80, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(r.read())["choices"][0]["message"]["content"].strip()
    if not out or out.upper().startswith("NONE"):
        return text
    ev = evidence.lower()
    for name in {n.strip().strip("'\"*.()[]") for n in re.split(r"[,\n]", out)}:
        # 짧은 조각이나 근거에 실제로 있는 이름은 건드리지 않는다(모델이 잘못 뽑은 후보를 코드가 걸러냄).
        if len(name) >= 2 and name.lower() not in ev and name in text:
            text = text.replace(name, "확인 불가")
    return text


HONESTY_V3 = ("\n- 주인과 집에 관한 사실(이름, 규칙, 날짜 등)은 장기 기억이나 집의 파일에서 확인된 것만 쓴다. "
              "어디에도 없으면 지어내지 말고 '확인 불가'로 적는다. 과제에 그런 지시가 없어도 항상 그렇다.")

# 샘플링(run.py 가 --temperature/--seed 로 바꾼다). 기본은 결정적(temperature 0).
SAMPLING = {"temperature": 0}

SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string", "maxLength": 200},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "args": {"type": "object"},
    },
    "required": ["thought", "action", "args"],
}

SYSTEM = """너는 이 컴퓨터의 집(작업 폴더)에서 계속 살아가는 비서다. 매일 주인이 inbox/tasks.md 에 할 일을 남긴다.
한 번에 행동 하나만 JSON 으로 고른다: {"thought": "...", "action": "...", "args": {...}}
가능한 행동:
%s
규칙:
- 사실(지명, 수도, 인물 등)은 기억으로 단정하지 말고 lookup 으로 확인한다. 확인이 안 되면 '확인 불가'로 적는다.
- 주인이 알려 준 규칙·사실·선호는 remember 로 장기 기억에 적는다. 다음 날의 너는 오늘 일을 장기 기억으로만 안다.
- 집의 현재 파일 목록은 매 걸음 보여 준다. 같은 행동을 같은 인자로 되풀이하지 않는다.
- 일을 실제로 끝낸 뒤에만 done(task=<할 일 id>) 을 한다. 하지 않은 일을 했다고 하지 않는다.
- 기존 파일에 내용을 더할 때는 append 를 쓴다. write 는 파일 전체를 덮어쓴다.
- 오늘 할 일을 모두 끝내면 end_day 로 회고를 남긴다.
- thought 는 한 문장으로 짧게. 지어내지 않는다. 모르면 모른다고 적는다."""

SYSTEM_V5 = """
v5 진행 방식:
- 하루는 계획 -> 실행 -> 점검으로 간다. 아침 계획과 체크리스트가 매 걸음 보인다. 체크리스트의 '다음 일'에 집중한다.
- done 에는 evidence(오늘 만들거나 고친 파일 경로, 기억에 적었으면 'memory')를 준다. 증거가 없으면 거절된다.
- 할 수 없는 일은 skip(task, reason)으로 솔직하게 남긴다.
- 파일을 옮기거나 덮어쓰기 전에 read 로 내용을 먼저 확인한다.
- 이미 한 행동은 다시 실행되지 않는다. 막히면 체크리스트의 다른 일로 넘어간다."""

PLAN_V5 = """너는 비서의 '아침 계획' 담당이다. 아래 오늘 할 일, 장기 기억, 지난 회고, 집의 파일 목록을 보고
할 일마다 결과물이 어디에 남아야 하는지(output)와 짧은 단계(steps, 최대 4개)를 정하라.
- 경로는 모두 집(작업 폴더) 맨 위 기준이다. 할 일이나 장기 기억에 적힌 경로는 글자 그대로 옮기고, 다른 폴더 아래로 옮겨 붙이지 않는다.
- output 은 집 안 파일 경로. 결과가 장기 기억이면 'memory'. 장기 기억에 위치 규칙이 있으면 반드시 그 규칙을 따른다.
- 단계는 실제 행동(read, lookup, write, append, move, remember 등)으로 적는다. 파일을 옮기거나 고치기 전에는 read 로 내용을 확인하는 단계를 둔다.
- 모르는 것은 지어내지 말고 '확인 필요'라고 적는다.
JSON 만 출력하라.

## 오늘 할 일
%s

## 장기 기억
%s

## 지난 회고
%s

## 집의 파일 목록
%s"""

CHECK_V5 = """너는 비서의 '점검' 담당이다. 아래 계획, 체크리스트, 최근 행동을 보고 지금 상황을 짧게 판단하라.
- assessment: 무엇이 끝났고 무엇이 막혔는지 한두 문장(같은 행동을 되풀이하고 있다면 그렇다고 적는다).
- next_task: 다음에 할 열린 일의 id.
- next_action: 그 일을 위한 구체적인 다음 행동 하나(이미 한 행동과 다른 것).
JSON 만 출력하라.

## 오늘 할 일
%s

## 아침 계획
%s

## 체크리스트
%s

## 최근 행동과 결과
%s"""


def _json_call(url: str, prompt: str, sch: dict, max_tokens: int = 700) -> dict:
    body = {"model": "x", "messages": [{"role": "user", "content": prompt}], **SAMPLING, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object", "schema": sch}}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(json.loads(r.read())["choices"][0]["message"]["content"])


def make_plan(url: str, ids: list, tasks: str, memory: str, diary: str, files: str) -> list:
    sch = {"type": "object", "required": ["plan"], "properties": {"plan": {"type": "array", "items": {
        "type": "object", "required": ["task", "output", "steps"],
        "properties": {"task": {"type": "string", "enum": ids}, "output": {"type": "string", "maxLength": 120},
                       "steps": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 120}}}}}}}
    return _json_call(url, PLAN_V5 % (tasks, memory, diary, files), sch, 900)["plan"]


def review(url: str, ids: list, tasks: str, plan: str, checklist: str, recent: str) -> dict:
    sch = {"type": "object", "required": ["assessment", "next_task", "next_action"],
           "properties": {"assessment": {"type": "string", "maxLength": 200},
                          "next_task": {"type": "string", "enum": ids or ["(없음)"]},
                          "next_action": {"type": "string", "maxLength": 200}}}
    return _json_call(url, CHECK_V5 % (tasks, plan, checklist, recent), sch, 400)


class Body:
    """허용 행동만 수행하는 몸. 경로는 home 밖으로 나갈 수 없다."""

    def __init__(self, home: Path, mind: Path, llm_url: str, wiki: grounded.Wiki):
        self.home, self.mind, self.llm_url, self.wiki = home.resolve(), mind, llm_url, wiki
        self.evidence = None  # v4 쓰기 전 점검용: 근거 텍스트를 돌려주는 함수(run_day 가 설정)
        self.corrections = 0
        # v5: 오늘 바꾼 파일(완료 증거), 오늘 내용을 본 파일(먼저 보고 행동하기), 오늘 기억에 적었는가
        self.touched, self.seen_files, self.remembered = set(), set(), False
        self.hand_log = []  # v4a: ATANOR 손 호출 결과

    def _p(self, rel: str) -> Path:
        p = (self.home / str(rel)).resolve()
        if p != self.home and self.home not in p.parents:
            raise PermissionError(f"집 밖 경로 금지: {rel}")
        return p

    def execute(self, action: str, a: dict) -> str:
        if action == "list":
            root = self._p(a.get("path", "."))
            items = sorted(str(x.relative_to(self.home)) + ("/" if x.is_dir() else "") for x in root.rglob("*"))[:200]
            return "\n".join(items) or "(비어 있음)"
        if action == "read":
            p = self._p(a["path"])
            text = p.read_text(encoding="utf-8", errors="replace")[:4000]
            self.seen_files.add(p)
            return text
        if action in ("write", "append"):
            p, text = self._p(a["path"]), str(a.get("text", ""))[:8000]
            if "check" in FEAT and self.evidence and text.strip():
                checked = check_write(self.llm_url, self.evidence(), text)
                if checked != text.strip():
                    self.corrections += 1
                    text = checked

            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w" if action == "write" else "a", encoding="utf-8") as f:
                f.write(text if text.endswith("\n") else text + "\n")
            if action == "write":
                self.seen_files.add(p)  # 방금 전체를 쓴 파일은 내용을 안다
            self.touched.add(p)
            return f"{action} 완료: {p.relative_to(self.home)} ({len(text)}자)"
        if action == "move":
            src, dst = self._p(a["src"]), self._p(a["dst"])
            if not src.exists():
                return f"없는 파일: {a['src']}"
            # 없는 대상에 확장자가 없으면 폴더로 본다(move(x, "receipts") 가 파일 이름 바꾸기가 되는 사고 방지).
            if str(a["dst"]).endswith("/") or dst.is_dir() or (not dst.exists() and not dst.suffix):
                dst.mkdir(parents=True, exist_ok=True)
                dst = dst / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                return f"이미 있음(덮어쓰지 않음): {dst.relative_to(self.home)}"
            shutil.move(str(src), str(dst))
            self.touched.add(dst)
            if src in self.seen_files:
                self.seen_files.add(dst)
            return f"이동 완료: {src.relative_to(self.home)} -> {dst.relative_to(self.home)}"
        if action == "mkdir":
            p = self._p(a["path"])
            p.mkdir(parents=True, exist_ok=True)
            self.touched.add(p)
            return "폴더 준비됨"
        if action == "lookup":
            q = str(a["question"])[:300]
            if "leading" in FEAT:
                r = grounded.leading_safe_answer(self.llm_url, q, self.wiki)
            else:
                r = grounded.grounded_answer(self.llm_url, q, self.wiki, guard="guard" in FEAT)
            return f"{r['answer']}  (검색 문서: {', '.join(r['sources'][:3]) or '없음'})"
        if action == "remember":
            with open(self.mind / "memory.md", "a", encoding="utf-8") as f:
                f.write("- " + str(a["text"]).strip().replace("\n", " ")[:500] + "\n")
            self.remembered = True
            return "기억함"
        if action == "organize":
            # 트랙 A R1: ATANOR 손. 기억은 mind/atanor(FRESH 면 날마다 지워짐), 어린 시절 경험(개발 세계에서 한 번 본 시범)은 매번 넣는다.
            sys.path.insert(0, str(CHILDHOOD.parent))
            import hand
            amind = self.mind / "atanor"
            if not (amind / "episodes.jsonl").exists():
                amind.mkdir(parents=True, exist_ok=True)
                shutil.copy(CHILDHOOD, amind / "episodes.jsonl")
            objs = a.get("objects") or []
            objs = [objs] if isinstance(objs, str) else list(objs)
            r = hand.organize(self.home, amind, self.mind.parent / "lab_atanor", objs, str(a.get("dest", "")), f"hand{len(self.hand_log)}")
            self.hand_log.append(r)
            if not r.get("moved") and r.get("why"):
                return f"손 거절: {r['why']}"
            for o in r.get("moved", []):
                self.touched.add(self._p(f"{str(a.get('dest')).strip().strip('/')}/{o.rsplit('/', 1)[-1]}"))
            return (f"손 결과: 옮김 {r.get('moved', [])}, 못 옮김 {r.get('not_moved', [])} "
                    f"(검증: {'목표 달성' if r.get('ok') else '목표 미달'}, 집 행동 {r.get('counts', {}).get('home_actions', 0)})")
        if action == "ask_user":
            return "주인은 지금 자리에 없다. 스스로 판단하되 모르면 '확인 불가'로 남겨라."
        if action == "done":
            return f"완료 표시: {a.get('task')}"
        if action == "skip":
            return f"포기 표시: {a.get('task')}"
        if action == "end_day":
            return "하루를 마침"
        raise ValueError(f"없는 행동: {action}")


def chat(url: str, messages: list, max_tokens: int = 1200, allowed: list | None = None) -> tuple[str, dict]:
    body = {"model": "x", "messages": messages, **SAMPLING, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object", "schema": schema(allowed)}}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"], d.get("timings", {})


CONSOLIDATE = """너는 비서의 '밤의 기억 정리' 담당이다. 아래는 기존 장기 기억과 오늘 실제로 있었던 행동·결과 기록이다.
앞으로 다른 날에도 쓸모 있는 것(주인이 정한 규칙, 주인이 알려 준 사실·선호, 파일 위치 관례, 확인된 사실)만 골라
장기 기억 목록을 새로 써라.
- 형식: 한 줄에 하나, '- ' 로 시작. 최대 30줄.
- 기록에 실제로 나온 것만 쓴다. 하지 않은 일, 추측, 오늘만 의미 있는 진행 상황은 넣지 않는다.
- 기존 장기 기억 중 여전히 유효한 것은 유지한다.
목록만 출력하라.

## 기존 장기 기억
%s

## 오늘의 행동·결과 기록
%s"""


CONSOLIDATE_V3 = """너는 비서의 '밤의 기억 정리' 담당이다. 아래는 기존 장기 기억과 오늘 실제로 있었던 행동·결과 기록이다.
장기 기억에는 다음 세 종류만 남긴다:
 1) 주인이 정한 규칙 (예: 파일 이름·위치 규칙)  2) 주인이 직접 알려 준 사실·선호  3) lookup 결과로 출처와 함께 확인된 사실
다음은 절대 넣지 않는다: 오늘 무엇을 했는지·완료했는지, 파일이 있다/기록되어 있다는 상태 묘사, 걸음 수, 추측, 기록에 없는 내용.
규칙은 주인이 쓴 문장 그대로 옮긴다. 너의 행동에서 규칙을 만들어 내지 않는다.
- 형식: 한 줄에 하나, '- [규칙] ...' / '- [주인 사실] ...' / '- [확인된 사실] ... (출처: 문서)'. 최대 20줄.
- 기존 장기 기억 중 위 세 종류에 맞는 것은 유지한다.
목록만 출력하라.

## 기존 장기 기억
%s

## 오늘의 행동·결과 기록
%s"""


def consolidate(url: str, mind: Path, records: list) -> str:
    """하루 끝에 실제 기록에서 장기 기억을 다시 쓴다. 이전 판은 memory_prev.md 로 남긴다."""
    mem = mind / "memory.md"
    old = mem.read_text(encoding="utf-8") if mem.exists() else "(없음)"
    log = "\n".join(f"- {r['action']} {json.dumps(r['args'], ensure_ascii=False)[:300]} -> {r['result'][:500]}"
                    for r in records if r["action"] not in ("(형식오류)",))[-9000:]
    tmpl = CONSOLIDATE_V3 if "hygiene" in FEAT else CONSOLIDATE
    body = {"model": "x", "messages": [{"role": "user", "content": tmpl % (old, log)}], **SAMPLING,
            "max_tokens": 900, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        text = json.loads(r.read())["choices"][0]["message"]["content"]
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith("- ")][:20 if "hygiene" in FEAT else 30]
    if mem.exists():
        shutil.copy(mem, mind / "memory_prev.md")
    mem.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return "\n".join(lines)


def task_ids(tasks_md: str) -> list:
    return re.findall(r"^- \[([^\]]+)\]", tasks_md, flags=re.M)


def tree(home: Path, limit: int = 60) -> str:
    items = sorted(x.relative_to(home).as_posix() + ("/" if x.is_dir() else "") for x in home.rglob("*"))
    return "\n".join(items[:limit]) + (f"\n... (+{len(items) - limit})" if len(items) > limit else "") or "(비어 있음)"


def tail_text(p: Path, n_chars: int) -> str:
    if not p.exists():
        return "(없음)"
    t = p.read_text(encoding="utf-8", errors="replace")
    return t[-n_chars:] if len(t) > n_chars else t


MEMORY_WORDS = ("memory", "memory.md", "mind/memory.md", "기억", "장기 기억")


class Structure:
    """v5 구조. 아침 계획, 코드가 관리하는 체크리스트(증거가 있어야 완료), 반복 금지, 먼저 보고 행동하기, 점검 호출.
    규칙은 모두 일반 원칙이고 세계의 과제 내용은 모른다(사전 등록 reports/V5_PREREG.md 의 공정성 약속)."""

    def __init__(self, body: Body, ids: list, url: str, stats: dict, log):
        self.body, self.ids, self.url, self.stats, self.log = body, ids, url, stats, log
        self.status = {i: "열림" for i in ids}
        self.plan_text, self.note = "(계획 없음)", ""
        self.executed, self.warned = {}, set()
        self.bad_streak, self.last_check, self.evidence = 0, 0, []
        self.outputs, self.banned, self.blocked_n = {}, {}, {}  # 계획한 결과물 경로, 잠시 금지된 행동 -> 마지막 금지 걸음

    def open_ids(self) -> list:
        return [i for i in self.ids if self.status[i] == "열림"]

    def morning(self, tasks: str, memory: str, diary: str, files: str, plan_path: Path) -> None:
        try:
            plan = make_plan(self.url, self.ids, tasks, memory, diary, files)
            # 계획이 만든 경로가 할 일·기억·집 어디에도 근거가 없으면(그 경로도, 그 상위 폴더도 안 나옴) '확인 필요'로 표시한다.
            # 계획이 경로를 엉뚱한 폴더 아래로 옮겨 붙이면 실행이 그 계획을 그대로 따랐다(본 실행 첫 9B 실행).
            known = (tasks + "\n" + memory + "\n" + files).replace("\\", "/")
            for p in plan:
                out = str(p["output"]).strip().strip("`'\"").replace("\\", "/").lstrip("./").rstrip("/")
                parent = out.rsplit("/", 1)[0] if "/" in out else ""
                if out.lower() not in MEMORY_WORDS and out not in known and parent and parent not in known:
                    p["output"] = f"확인 필요({out}: 할 일·기억에 없는 경로)"
            self.outputs = {p["task"]: p["output"] for p in plan if not p["output"].startswith("확인 필요")}
            self.plan_text = "\n".join(f"- [{p['task']}] 결과물: {p['output']} / 단계: {' -> '.join(p['steps'])}"
                                       for p in plan) or "(계획 없음)"
            self.plan_text += "\n(계획은 참고용이다. 경로가 할 일·장기 기억에 적힌 것과 다르면 할 일·장기 기억을 따른다.)"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            self.stats["errors"] += 1
            self.plan_text = f"(계획 실패: {type(e).__name__})"
        self.log(f"[plan] {self.plan_text[:300]!r}")

    def output_touched(self, tid: str) -> str | None:
        out = str(self.outputs.get(tid, "")).strip().strip("`'\"")
        if out.lower() in MEMORY_WORDS:
            return "memory" if self.body.remembered else None
        try:
            p = self.body._p(out) if out else None
        except Exception:
            return None
        return out if p and p != self.body.home and any(t == p or p in t.parents for t in self.body.touched) else None

    def allowed(self, step: int) -> list:
        """반복이 이어지면 그 행동을 몇 걸음 동안 문법에서 뺀다(모델이 같은 행동을 고를 수 없게)."""
        return [a for a in actions() if self.banned.get(a, 0) < step]

    def checklist(self) -> str:
        lines = []
        for i in self.ids:
            hint = ""
            if self.status[i] == "열림" and (out := self.output_touched(i)):
                hint = f"  <- 계획한 결과물 {out} 이(가) 오늘 바뀌었다. 끝났으면 done(task='{i}', evidence=['{out}'])"
            lines.append(f"- [{i}] {self.status[i]}{hint}")
        made = sorted(t.relative_to(self.body.home).as_posix() for t in self.body.touched)
        lines.append(f"오늘 바꾼 파일: {', '.join(made) or '없음'}{' / 오늘 기억에 적음' if self.body.remembered else ''}")
        nxt = self.open_ids()
        lines.append(f"다음 일: [{nxt[0]}]" if nxt else "모든 일이 끝났다(완료 또는 포기). end_day 로 하루를 마쳐라.")
        return "\n".join(lines)

    def block(self, step: int, max_steps: int) -> str:
        left = max_steps - step + 1
        warn = (f"주의: 걸음이 {left}개 남았다. 열린 일 중 바로 끝낼 수 있는 것부터 하고, 못 하면 skip 하라.\n"
                if left <= 6 and self.open_ids() else "")
        ban = [f"{a}(걸음 {u}까지)" for a, u in self.banned.items() if u >= step]
        if ban:
            warn += f"같은 행동을 되풀이해서 잠시 금지된 행동: {', '.join(ban)}\n"
        return (f"## 아침 계획\n{self.plan_text}\n\n## 체크리스트\n{self.checklist()}\n{warn}\n"
                f"## 점검 메모\n{self.note or '(없음)'}\n\n")

    def key(self, action: str, args: dict) -> str:
        """같은 행동인가. read·list 는 대상이 바뀌었으면 다른 행동으로 본다."""
        k = action + json.dumps(args, ensure_ascii=False, sort_keys=True)
        try:
            if action == "read":
                k += "#" + hashlib.md5(self.body._p(args["path"]).read_bytes()).hexdigest()
            elif action == "list":
                k += "#" + hashlib.md5(tree(self.body.home, 1000).encode()).hexdigest()
        except Exception:
            pass
        return k

    @staticmethod
    def tid(args: dict) -> str:
        return re.sub(r"[\[\]\s]", "", str(args.get("task", "")))

    def gate(self, action: str, args: dict, key: str) -> str | None:
        """실행 전 검사. 막으면 결과 문구, 통과하면 None."""
        b = self.body
        if action not in ("done", "skip", "end_day") and key in self.executed:
            return (f"반복: 이미 한 행동이고 그 뒤 바뀐 것도 없다 -> {self.executed[key][:300]} "
                    "(체크리스트의 다음 일로 넘어가라)")
        try:
            if action == "move":
                src = b._p(args.get("src", ""))
                if src.is_file() and src not in b.seen_files:
                    return f"거절: {args.get('src')} 의 내용을 아직 보지 않았다. 옮기기 전에 read 로 확인하라."
            if action == "write":
                p = b._p(args.get("path", ""))
                cur = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
                if cur.strip() and p not in b.seen_files:
                    return "거절: 이미 있는 파일이다. 덮어쓰기 전에 read 로 내용을 확인하라. 내용을 더하려면 append."
                old = [l.strip() for l in cur.splitlines() if l.strip()]
                lost = [l for l in old if l not in str(args.get("text", ""))]
                if len(old) >= 2 and len(lost) * 2 > len(old) and p not in self.warned:
                    self.warned.add(p)
                    return (f"거절: 기존 {len(old)}줄 중 {len(lost)}줄이 사라진다(예: {lost[0][:60]}). "
                            "더하려면 append 하라. 정말 바꾸려면 같은 write 를 한 번 더 하라.")
        except Exception:
            pass  # 경로 오류는 실행 단계에서 그대로 보고된다
        if action in ("done", "skip"):
            tid = self.tid(args)
            if tid not in self.status:
                return f"{action} 거절: task 는 체크리스트의 id 중 하나여야 한다: {', '.join(self.ids)}"
            if self.status[tid] != "열림":
                return f"{action} 거절: [{tid}] 는 이미 {self.status[tid]}"
            if action == "skip":
                return None if str(args.get("reason", "")).strip() else "skip 거절: reason 이 필요하다"
            ev = args.get("evidence") or []
            if isinstance(ev, str):
                ev = re.split(r"[,\n]", ev)
            self.evidence = []
            for e in (str(x).strip().strip("`'\"") for x in ev):
                if not e:
                    continue
                if e.lower() in MEMORY_WORDS:
                    if b.remembered:
                        self.evidence.append("memory")
                    continue
                try:
                    p = b._p(e)
                    if p.exists() and any(t == p or p in t.parents for t in b.touched):
                        self.evidence.append(e)
                except Exception:
                    pass
            if not self.evidence:
                made = sorted(t.relative_to(b.home).as_posix() for t in b.touched)
                return ("done 거절: 증거가 없다. evidence 에 오늘 만들거나 고친 파일 경로(기억에 적었으면 'memory')를 주어라. "
                        f"오늘 바꾼 파일: {', '.join(made) or '없음'}{' / 오늘 기억에 적음' if b.remembered else ''}")
        return None

    def after(self, action: str, args: dict, key: str, result: str, blocked: bool, step: int) -> bool:
        """실행 뒤 상태 갱신. 점검이 필요하면 True."""
        if blocked:
            self.bad_streak += 1
            self.blocked_n[key] = self.blocked_n.get(key, 0) + 1
            base = action.replace("(거절)", "")
            # 연달아 두 번 막히거나, 같은 행동이 사이를 두고 두 번 막히면 그 행동을 잠시 뺀다
            if (self.bad_streak >= 2 or self.blocked_n[key] >= 2) and base in actions() and base not in ("done", "end_day"):
                self.banned[base] = step + 3
            return self.bad_streak >= 2
        self.bad_streak = 0
        self.executed[key] = result
        if action == "done":
            self.status[self.tid(args)] = f"완료(증거: {', '.join(self.evidence)})"
            return True
        if action == "skip":
            self.status[self.tid(args)] = f"포기({str(args.get('reason', '')).strip()[:60]})"
            return True
        return False

    def check(self, tasks: str, recent: str, step: int) -> None:
        self.last_check, self.bad_streak = step, 0
        if not self.open_ids():
            self.note = ""
            return
        try:
            r = review(self.url, self.open_ids(), tasks, self.plan_text, self.checklist(), recent)
            self.note = f"{r['assessment']} -> 다음: [{r['next_task']}] {r['next_action']}"
        except Exception as e:
            self.stats["errors"] += 1
            self.note = f"(점검 실패: {type(e).__name__})"
        self.stats["checks"] += 1
        self.log(f"[check] {self.note[:200]!r}")


def run_day(root: Path, day: int, date: str, cond: str, llm_url: str, wiki: grounded.Wiki,
            max_steps: int = 25, stop_file: Path | None = None, log=print) -> dict:
    home, mind, logs = root / "home", root / "mind", root / "logs"
    if cond == "FRESH" and mind.exists():
        arch = root / "mind_archive" / f"before_day{day}_{int(time.time())}"
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mind), str(arch))
    mind.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    body = Body(home, mind, llm_url, wiki)
    steplog = logs / f"day{day}.jsonl"
    history, stats = [], {"steps": 0, "errors": 0, "repeats": 0, "denied": 0, "lookups": 0, "remembers": 0,
                          "done": [], "ended": False, "stopped": False, "tok_gen": 0, "sec_llm": 0.0,
                          "end_refused": 0, "memory_lines": 0, "write_corrections": 0,
                          "checks": 0, "rejected": 0, "blocked": 0, "skipped": []}
    ids = task_ids(tail_text(home / "inbox" / "tasks.md", 4000))
    seen, results_seen = set(), {}
    sx = Structure(body, ids, llm_url, stats, lambda m: log(f"[day{day} {cond}] {m}")) if "evidence" in FEAT else None
    if sx and "plan" in FEAT and ids:
        sx.morning(tail_text(home / "inbox" / "tasks.md", 2000), tail_text(mind / "memory.md", 2500),
                   tail_text(mind / "diary.md", 800), tree(home), logs / f"day{day}_plan.json")
    # v4 쓰기 전 점검의 근거: 할 일, 장기 기억, 오늘 읽고 찾은 결과(read/lookup/list). 쓰려는 글 자신은 근거가 아니다.
    body.evidence = lambda: "\n".join(
        [tail_text(home / "inbox" / "tasks.md", 2000), tail_text(mind / "memory.md", 2500)]
        + [f"{h['action']} {json.dumps(h['args'], ensure_ascii=False)[:150]} -> {h['result'][:600]}"
           for h in history if h.get("action") in ("read", "lookup", "list")])
    system = SYSTEM % "\n".join(f"- {v}" for v in actions().values())  # v2~v4 는 ACTIONS 그대로, v4a 는 organize
    if "honesty" in FEAT:
        system += HONESTY_V3
    if sx:
        system = SYSTEM % "\n".join(f"- {v}" for v in actions().values()) + SYSTEM_V5
    for step in range(1, max_steps + 1):
        if stop_file and stop_file.exists():
            stats["stopped"] = True
            log(f"[day{day} {cond}] STOP 파일 발견, 중단")
            break
        recent = "\n".join(f"{h['step']}. {h['action']} {json.dumps(h['args'], ensure_ascii=False)[:200]} -> {h['result'][:400]}"
                           for h in history[-8:]) or "(아직 없음)"
        obs = (f"오늘: day {day}, {date}. 걸음 {step}/{max_steps}.\n\n"
               f"## 오늘 할 일 (inbox/tasks.md)\n{tail_text(home / 'inbox' / 'tasks.md', 2000)}\n"
               + (sx.block(step, max_steps) if sx else f"이미 done 한 일: {', '.join(stats['done']) or '없음'}\n\n") +
               f"## 집의 현재 파일 목록\n{tree(home)}\n\n"
               f"## 장기 기억 (memory.md)\n{tail_text(mind / 'memory.md', 2500)}\n\n"
               f"## 지난 회고 (diary.md 끝부분)\n{tail_text(mind / 'diary.md', 800)}\n\n"
               f"## 오늘 지금까지 한 행동과 결과\n{recent}\n\n다음 행동 하나를 JSON 으로.")
        t0 = time.time()
        try:
            raw, timings = chat(llm_url, [{"role": "system", "content": system}, {"role": "user", "content": obs}],
                                allowed=sx.allowed(step) if sx else None)
            stats["sec_llm"] += time.time() - t0
            stats["tok_gen"] += timings.get("predicted_n", 0) or 0
            d = json.loads(raw)
            action, args, thought = d["action"], d.get("args") or {}, d.get("thought", "")
        except Exception as e:  # 형식 오류도 한 걸음으로 세고 기록한다
            if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
                raise  # 서버가 죽음: 실험 결과가 아니므로 기록하지 않고 실행을 멈춘다(run.py 가 종료 코드 3)
            stats["errors"] += 1
            rec = {"t": round(time.time(), 3), "cond": cond, "day": day, "step": step, "action": "(형식오류)",
                   "args": {}, "result": f"{type(e).__name__}: {e}"[:300], "raw": (locals().get("raw") or "")[:1500]}
            history.append(rec)
            with open(steplog, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log(f"[day{day} {cond}] {step:2d} (형식오류) {rec['result'][:100]}")
            continue
        key = action + json.dumps(args, ensure_ascii=False, sort_keys=True)
        if key in seen and action not in ("list", "done"):
            stats["repeats"] += 1
        seen.add(key)
        undone = sx.open_ids() if sx else [i for i in ids if not any(i in str(d) for d in stats["done"])]
        vkey = sx.key(action, args) if sx else key
        gated = sx.gate(action, args, vkey) if sx else None
        try:
            if gated is not None:
                # v5: 반복은 행동 이름 그대로(결과가 '반복:'), 그 밖의 거절은 '<행동>(거절)' 로 기록한다.
                result = gated
                if gated.startswith("반복:"):
                    stats["blocked"] += 1
                else:
                    stats["rejected"] += 1
                    action = f"{action}(거절)"
            elif key in results_seen and action in ("lookup", "read", "list"):
                # 같은 날 같은 조회를 되풀이하면 다시 실행하지 않고 알려 준다(반복 고리 방지, 두 조건 공통).
                result = f"반복: 이미 같은 행동을 했고 결과는 같다 -> {results_seen[key][:300]} (다른 방법을 시도하라)"
            elif action == "end_day" and undone and stats["end_refused"] < 2:
                # 환경 규칙(두 조건 공통): 남은 일이 있으면 두 번까지 하루 마감을 거절한다.
                stats["end_refused"] += 1
                result = (f"마감 거절: 아직 열린 일이 있다: {', '.join(undone)}. 하거나, 할 수 없으면 skip(task, reason) 하라." if sx else
                          f"마감 거절: 아직 done 하지 않은 일이 있다: {', '.join(undone)}. 하거나, 할 수 없으면 그 이유를 적고 done 하라.")
                action = "end_day(거절)"
            else:
                result = body.execute(action, args)
        except PermissionError as e:
            stats["denied"] += 1
            result = f"거부됨: {e}"
        except Exception as e:
            stats["errors"] += 1
            result = f"오류: {type(e).__name__}: {e}"
        if action in ("lookup", "read", "list") and not result.startswith("반복:"):
            results_seen[key] = result
        stats["steps"] = step
        stats["lookups"] += action == "lookup"
        stats["remembers"] += action == "remember"
        if action == "done":
            stats["done"].append(Structure.tid(args) if sx else str(args.get("task")))
        if action == "skip":
            stats["skipped"].append(Structure.tid(args))
        rec = {"t": round(time.time(), 3), "cond": cond, "day": day, "step": step, "thought": thought,
               "action": action, "args": args, "result": result[:2000]}
        if sx:
            failed = gated is not None or result.startswith(("오류", "거부", "마감 거절"))
            need = sx.after(action, args, vkey, result, failed, step)
            if action != "end_day" and (need or step - sx.last_check >= 8):
                recent12 = "\n".join(f"{h['step']}. {h['action']} {json.dumps(h['args'], ensure_ascii=False)[:150]} -> {h['result'][:250]}"
                                     for h in (history + [rec])[-12:])
                sx.check(tail_text(home / "inbox" / "tasks.md", 2000), recent12, step)
                rec["check"] = sx.note
        history.append(rec)
        with open(steplog, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(mind / "episodes.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log(f"[day{day} {cond}] {step:2d} {action:8s} {json.dumps(args, ensure_ascii=False)[:90]} -> {result[:80]!r}")
        if action == "end_day":
            with open(mind / "diary.md", "a", encoding="utf-8") as f:
                f.write(f"\n## day {day} ({date})\n{str(args.get('diary', '')).strip()[:1500]}\n")
            stats["ended"] = True
            break
    if not stats["stopped"]:
        try:
            mem = consolidate(llm_url, mind, [h for h in history if "action" in h])
            stats["memory_lines"] = len(mem.splitlines())
            log(f"[day{day} {cond}] 밤의 기억 정리: {stats['memory_lines']}줄")
        except Exception as e:
            stats["errors"] += 1
            log(f"[day{day} {cond}] 기억 정리 실패: {e}")
    stats["write_corrections"] = body.corrections
    stats["hand_calls"], stats["hand_moved"] = len(body.hand_log), sum(len(r.get("moved", [])) for r in body.hand_log)
    return stats
