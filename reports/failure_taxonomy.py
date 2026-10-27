"""트랙 L 실패 분류(failure taxonomy) — 읽기 전용 분석 스크립트.

대상: runs/exp1 (agent-v2, life-v1), runs/exp2v3 (agent-v3, life-v1), runs/exp3w2 (agent-v3, life-v2), runs/laptop1 (agent-v2, life-v1).
runs/dev*, exp4v4w1, exp5v4w2 는 읽지 않는다.

하는 일
 1) 걸음 단위 탐지기(비배타적): 반복 고리, 차단된 반복, 같은 글 다시 쓰기, 마감 거절, 걸음 소진, 디렉터리 read 오류의 권한 오해,
    없는 경로, 집·주인 질문을 lookup 에 묻기, 복합 질문, 가짜 나라 lookup 의 그럴듯한 오답, 실제 나라 lookup 오답,
    done 오용(없는 id/중복/여러 id/한 일 없이 done), 거짓 완료 회고, 덮어쓰기 손실, 지정 밖 경로에 쓰기, 영수증 오배치,
    지어낸 이름(채점기가 놓치는 '## 고양이 이름\\n맥스' 형식 포함), 먼저 쓰고 나중에 확인, 글 안의 퇴행 반복.
 2) 잃은 점수 하나하나에 주원인 1개를 붙인다(배타적). 거짓 done 은 덧씌우는 표시(overlay)로 따로 센다.
 3) 기억 파일 분석: 최종 memory.md / memory_prev.md(LIFE), mind_archive/before_dayN/memory.md(FRESH: 그날 밤 정리 결과).
    잡음, 중복 줄, 실수→규칙, 자기 인용 '확인된 사실', 모순(모카·모찌, reports·journal 동시 유효).
 4) life-v2 규칙 변경(3·4일차)·사실 정정(5·6일차) 경과표.

사용: PYTHONIOENCODING=utf-8 python failure_taxonomy.py [--runs D:/.../runs] [--cases]
"""
import argparse
import collections
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIFE_DIR = ROOT / "life"
sys.dont_write_bytecode = True  # life\ 에 __pycache__ 를 만들지 않는다(읽기 전용)
sys.path.insert(0, str(LIFE_DIR))  # 세계 정의(world.py, world_v2.py)만 읽는다. 실행 부작용 없음.

EXPS = ["exp1", "exp2v3", "exp3w2", "laptop1"]
WORLD_OF = {"life-v1": "world", "life-v2": "world_v2"}
MAX_STEPS = 25
FICTION_NAMES = ["벨트라니아", "오렐리아", "노르바니아"]
RECEIPT_FILES = {"life-v1": {"a.txt", "c.txt", "d.txt", "f.txt"}, "life-v2": {"a.txt", "c.txt"}}
NONRECEIPT_FILES = {"life-v1": {"b.txt", "e.txt"}, "life-v2": {"b.txt", "d.txt"}}
# 기억이 있어야 풀리는 과제(세계 설계상). report 는 규칙을 기억해야 한다.
MEMORY_DAYS = {"life-v1": {("2", "cat"), ("2", "report"), ("3", "report"), ("3", "gift")},
               "life-v2": {("2", "invite"), ("2", "report"), ("4", "report"), ("4", "cat"), ("6", "card"),
                           ("6", "report"), ("7", "report")}}
ABSTAIN = re.compile(r"확인 ?불가|모름|모르|알 수 없|확인되지 않|unknown|찾지 못|명시되어 있지 않|정보가 없|없습니다", re.I)
NOISE = re.compile(r"걸음|완료|작성되었|업데이트|기록되어|기록되었|존재한다|진행|오늘은|저장되어|처리되|처리함|작성함|생성되었")
OLD_MARK = re.compile(r"예전|이전|옛|바꿨|바뀌|변경|더 이상|아니라|대신")
HOME_Q = re.compile(r"고양이|주인|inbox|파일|영수증|폴더|보고서|\.md|\.txt|서윤|모카|모찌|이름은 무엇")
CLAIM_ALL = re.compile(r"모두 완료|모든 할 일|모두 끝|모두 처리|모두 마쳤|모든 요청|일정이 모두|모든 작업")
NAME_PATS = [re.compile(r"이름\**\s*[:：]\s*\**\s*['\"]?([가-힣A-Za-z]{1,8})"),
             re.compile(r"고양이 이름\s*\**\s*\n+\s*[-*]?\s*([가-힣A-Za-z]{1,8})"),
             re.compile(r"(?:서명|From|보내는 사람)\s*[:：]?\s*([가-힣A-Za-z]{2,8})"),
             re.compile(r"([가-힣]{2,4})(?:야|아)[!,]\s"),
             re.compile(r"(?:고양이|냥이)\s*['\"]([가-힣A-Za-z]{1,8})['\"]"),
             re.compile(r"고양이\S* 이름은\s*['\"]?([가-힣A-Za-z]{2,8}?)['\"]?(?:이다|다|입니다|야)")]
NAME_OK = {"모카", "모찌", "서윤", "확인", "확인불가", "모름", "알", "고양이", "생일", "주인", "친구", "안녕", "우리", "오늘",
           "Claude", "Name", "이름", "냥이", "사랑해", "축하해", "어서", "자", "좋아", "고마워", "미안해", "있잖아", "얘들", "그래",
           "우와", "얘", "와", "친구야", "생일이야", "냥", "하루", "아가", "시작", "준비", "음식", "자기", "선물",
           "이름은", "날이", "생일이", "정보", "미정", "없음", "아직", "정해지지", "없", "pets"}
WORDS_OK_SUFFIX = ("불가",)
# 한 낱말 안에서 한글과 다른 문자(라틴·아랍·한자·키릴·가나)가 섞인 깨진 토큰. 예: '캔berra', '캔برا', '记下한'
MIXED = re.compile(r"[가-힣][A-Za-z؀-ۿ一-鿿Ѐ-ӿ぀-ヿ]|"
                   r"[A-Za-z؀-ۿ一-鿿Ѐ-ӿ぀-ヿ][가-힣]")
FOREIGN = re.compile(r"[؀-ۿ一-鿿Ѐ-ӿ぀-ヿ]")
CAP_LINE = re.compile(r"^[\s\-*#|]*\**([가-힣]{2,8})\**\s*(?:[:|]|\(|의 수도|\n)", re.M)
CAP_STOP = {"수도", "국가", "나라", "출처", "참고", "날짜", "최대", "인구", "면적", "추가", "목록", "도시", "정보", "국가별",
            "카피탈", "생성일", "비고", "요약", "이번", "벨트라니아", "오렐리아", "노르바니아", "확인", "사실", "주의"}
COUNTRIES = ["대한민국", "한국", "미국", "중국", "프랑스", "영국", "독일", "스페인", "모로코", "에콰도르", "네덜란드", "이탈리아",
             "러시아", "인도", "브라질", "멕시코", "노르웨이", "스웨덴", "이집트", "일본", "케냐", "캐나다", "호주", "오스트레일리아",
             "튀르키예", "뉴질랜드"]
RULE_LIKE = re.compile(r"한다\.?$|해\.?$|보관|관리|위치는|저장됩니다|저장한다|정리한다|정리해|규칙|항상|폴더에 저장|진행한다|로 옮긴다")


def norm(p) -> str:
    p = str(p or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    p = re.sub(r"/+", "/", p)
    return p.rstrip("/")


def load_runs(runs_dir: Path):
    out = []
    for e in EXPS:
        for rj in sorted((runs_dir / e).glob("*/results.json")):
            d = json.loads(rj.read_text(encoding="utf-8"))
            w = importlib.import_module(WORLD_OF[d["protocol"]])
            if len(d.get("days", {})) < len(w.DATES):
                continue
            logs = {}
            for k in d["days"]:
                f = rj.parent / "logs" / f"day{k}.jsonl"
                logs[k] = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []
            out.append({"exp": e, "name": rj.parent.name, "dir": rj.parent, "cond": d["cond"], "agent": d["agent"],
                        "protocol": d["protocol"], "w": w, "res": d, "logs": logs})
    return out


# ---------------------------------------------------------------- 걸음 단위 탐지기
def key_of(r):
    return r["action"] + json.dumps(r.get("args", {}), ensure_ascii=False, sort_keys=True)


def write_target(r):
    m = re.match(r"^(write|append) 완료: (.+?) \(\d+자\)", r.get("result", ""))
    return norm(m.group(2)) if m else None


def move_pair(r):
    m = re.match(r"^이동 완료: (.+?) -> (.+)$", r.get("result", ""))
    return (norm(m.group(1)), norm(m.group(2))) if m else None


def task_text(run, day):
    w = run["w"]
    return "\n".join(t for _, t in w.DAYS[int(day)]["tasks"])


def expected_paths(run, day):
    """그날 과제 글에 나온 경로 + 보고서 규칙 경로(세계 규칙). '지정 밖 경로' 판정의 기준."""
    w, day_i = run["w"], int(day)
    paths = set(norm(p) for p in re.findall(r"([A-Za-z_]+/[A-Za-z0-9_.\-]*)", task_text(run, day)))
    date = w.DATES[day_i]
    if run["protocol"] == "life-v2" and day_i >= 3:
        paths.add(f"journal/{date}.md")
    else:
        paths.add(f"reports/report-{date}.md")
    return {p for p in paths if p}


def names_in(text):
    found = []
    for pat in NAME_PATS:
        for m in pat.finditer(text):
            n = m.group(1).strip()
            if n in NAME_OK or n.startswith("확인") or n.endswith(WORDS_OK_SUFFIX) or len(n) < 2:
                continue
            found.append(n)
    return found


def file_state_replay(run):
    """로그의 write/append 결과로 파일 내용을 날마다 재구성한다. 덮어쓰기 손실 탐지용."""
    state, losses = {}, []
    for day in sorted(run["logs"], key=int):
        for r in run["logs"][day]:
            p = write_target(r)
            if not p:
                continue
            text = str(r["args"].get("text", ""))[:8000]
            text = text if text.endswith("\n") else text + "\n"
            old = state.get(p, "")
            if r["action"] == "write":
                old_lines = [l.strip() for l in old.splitlines() if l.strip() and not l.strip().startswith("#")]
                lost = [l for l in old_lines if l not in text]
                if old_lines and lost:
                    losses.append({"day": day, "step": r["step"], "path": p, "lost": lost, "n_old": len(old_lines)})
                state[p] = text
            else:
                state[p] = old + text
    return losses


def step_detectors(run):
    """실행 하나의 걸음 단위 실패 신호들(비배타적). 반환: {이름: 횟수}, 사례 목록."""
    c, cases = collections.Counter(), []
    ids_all = {}
    inv_days = set()
    for day, recs in run["logs"].items():
        ids_all[day] = [t for t, _ in run["w"].DAYS[int(day)]["tasks"]]
    for day in sorted(run["logs"], key=int):
        recs = run["logs"][day]
        st = run["res"]["days"][day]["stats"]
        score = run["res"]["days"][day]["score"]
        ids = ids_all[day]
        state_today = {}
        refused_note_at = None
        note_reads_after_refusal = 0
        keys = collections.Counter()
        writes_per_path = collections.Counter()
        reads_so_far = set()
        touched = set()
        done_seen = collections.Counter()
        prev_denied = False
        for r in recs:
            a, args, res, th = r["action"], r.get("args", {}), r.get("result", ""), r.get("thought", "")
            c["steps"] += 1
            if a == "(형식오류)":
                c["format_error"] += 1
                continue
            k = key_of(r)
            keys[k] += 1
            if res.startswith("반복:"):
                c["repeat_blocked"] += 1
            if keys[k] > 1 and a in ("write", "append"):
                c["identical_rewrite"] += 1
            if keys[k] > 1 and a == "remember":
                c["repeat_remember"] += 1
            if keys[k] > 1 and a == "ask_user":
                c["repeat_ask_user"] += 1
            if a == "end_day(거절)":
                c["end_refused"] += 1
                if re.search(r"\bnote\b", res) and refused_note_at is None:
                    refused_note_at = r["step"]
            if refused_note_at and a == "read" and "note" in str(args.get("path", "")) and res.startswith("반복:"):
                note_reads_after_refusal += 1
            if a == "ask_user":
                c["ask_user"] += 1
            if prev_denied and re.search(r"권한|접근", th):
                c["perm_misread"] += 1
            prev_denied = False
            if res.startswith("거부됨") and "Errno 13" in res:
                c["dir_read_denied"] += 1  # Windows 에서 폴더를 read 하면 '권한 거부'로 보임
                prev_denied = True
            if res.startswith("없는 파일") or "FileNotFoundError" in res:
                c["path_not_found"] += 1
            if MIXED.search(th) or FOREIGN.search(th):
                c["mixed_script_thought"] += 1
            if a in ("write", "append") and (MIXED.search(str(args.get("text", ""))) or
                                             FOREIGN.search(str(args.get("text", "")))):
                c["mixed_script_write"] += 1
                cases.append(("mixed_script_write", day, r["step"],
                              (MIXED.search(str(args["text"])) or FOREIGN.search(str(args["text"]))).group(0)))
            if a == "lookup":
                q = str(args.get("question", ""))
                if re.search(r"인가\?*$|인가요|맞는가|맞나요|있는가|존재하는가", q) and not re.search(r"어디|무엇|누구", q):
                    c["lookup_yesno_q"] += 1  # 예/아니오 유도형 질문(근거화가 엉뚱한 문서로 '네/아니요'를 만들기 쉬움)
                if HOME_Q.search(q):
                    c["lookup_home_q"] += 1
                    cases.append(("lookup_home_q", day, r["step"], q[:80]))
                countries = [x for x in list(getattr(run["w"], "CAPITALS", {}).keys()) + FICTION_NAMES if x in q]
                if len(countries) >= 2:
                    c["lookup_compound"] += 1
                if not res.startswith("반복"):
                    for fn in FICTION_NAMES:
                        if fn in q:
                            c["lookup_fiction"] += 1
                            body = res.split("(검색 문서")[0]
                            if not ABSTAIN.search(body):
                                c["lookup_fiction_misleading"] += 1
                                cases.append(("lookup_fiction_misleading", day, r["step"], res[:100]))
                                if re.search(r"수도는\s*[가-힣A-Za-z]+\s*(\([A-Za-z]+\)\s*)?(입니다|이다|이며)", body):
                                    c["lookup_fiction_capital"] += 1  # 가짜 나라에 실제 수도(오슬로 등)를 붙여 답함
                    for cn, pat in getattr(run["w"], "CAPITALS", {}).items():
                        if cn in q and len(countries) < 2:
                            c["lookup_real"] += 1
                            if not re.search(pat, res.split("(검색 문서")[0], re.I):
                                c["lookup_real_wrong"] += 1
                                cases.append(("lookup_real_wrong", day, r["step"], res[:100]))
            if a == "done":
                tid = str(args.get("task", ""))
                clean = re.sub(r"[\[\]\s]", "", tid)
                if "," in tid:
                    c["done_multi_id"] += 1
                elif clean not in ids:
                    c["done_bad_id"] += 1
                    cases.append(("done_bad_id", day, r["step"], tid[:60]))
                done_seen[clean] += 1
                if done_seen[clean] == 2:
                    c["done_duplicate"] += 1
                # 한 일 없이 done: 그 과제의 대상 경로를 그날 건드린 적이 없음(note 는 read 로 봄)
                target_hit = False
                if clean == "note":
                    target_hit = any("note" in x for x in reads_so_far)
                elif clean == "receipts":
                    target_hit = "MOVE" in touched
                elif clean in ids:
                    pats = {"capitals": "capitals", "fiction": "capitals", "report": "report|journal",
                            "cat": "pets/cat", "catfix": "pets/cat", "gift": "pets/gift", "card": "pets/card",
                            "invite": "letters/invite", "summary": "summary"}
                    target_hit = any(re.search(pats.get(clean, "^$"), t) for t in touched)
                if clean in ids and not target_hit:
                    c["done_before_any_attempt"] += 1
                    cases.append(("done_before_any_attempt", day, r["step"], tid[:40]))
            if a == "read" and not res.startswith(("거부됨", "오류")):
                reads_so_far.add(norm(args.get("path")))
            wt = write_target(r)
            if wt:
                touched.add(wt)
                writes_per_path[wt] += 1
                text = str(args.get("text", ""))
                lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 3]
                dup = collections.Counter(lines)
                if dup and dup.most_common(1)[0][1] >= 3:
                    c["degenerate_text"] += 1
                    cases.append(("degenerate_text", day, r["step"], wt))
                if wt not in expected_paths(run, day):
                    c["offspec_write"] += 1
                    cases.append(("offspec_write", day, r["step"], wt))
                if re.match(r"(pets|letters)/", wt):
                    inv = names_in(text)
                    if inv:
                        c["invented_name_write"] += 1
                        inv_days.add(day)
                        cases.append(("invented_name_write", day, r["step"], f"{wt}: {inv[:3]}"))
                if wt == "pets/cat.txt":
                    extra = [l for l in text.splitlines() if re.search(r"나이|품종|성격|호기심|색|털|좋아|생일|체중", l)]
                    if extra:
                        c["embellished_owner_fact"] += 1  # 주인이 말한 적 없는 고양이 세부(나이 3세 등)를 지어 넣음
                        cases.append(("embellished_owner_fact", day, r["step"], extra[0][:60]))
                if wt == "facts/capitals.md":
                    requested = set(getattr(run["w"], "CAPITALS", {})) | set(FICTION_NAMES)
                    extra = [n for n in COUNTRIES if n in text and n not in requested]
                    if extra:
                        c["unrequested_fact_write"] += 1  # 시키지 않은 나라(에콰도르: 퀘토 등)를 덧붙임
                        cases.append(("unrequested_fact_write", day, r["step"], ",".join(sorted(set(extra)))[:60]))
                # 맞게 써 둔 값을 같은 날 틀린 값으로 덮어씀(되돌림)
                right = _right_value(run, day, wt)
                if right:
                    had = right in state_today.get(wt, "")
                    new = (text if a == "write" else state_today.get(wt, "") + text)
                    if had and right not in new:
                        c["correct_then_overwritten"] += 1
                        cases.append(("correct_then_overwritten", day, r["step"], f"{wt}: -> {text[:30]!r}"))
                    state_today[wt] = new
                else:
                    state_today[wt] = text if a == "write" else state_today.get(wt, "") + text
            mp = move_pair(r)
            if mp:
                touched.add("MOVE")
                src, dst = mp
                fname = src.split("/")[-1]
                ddir = "/".join(dst.split("/")[:-1])
                if fname in RECEIPT_FILES[run["protocol"]] and ddir != "receipts":
                    c["receipt_wrong_folder"] += 1
                    cases.append(("receipt_wrong_folder", day, r["step"], f"{src} -> {dst}"))
                if fname in NONRECEIPT_FILES[run["protocol"]]:
                    c["nonreceipt_moved"] += 1
                    cases.append(("nonreceipt_moved", day, r["step"], f"{src} -> {dst}"))
            if a == "end_day" or a == "end_day(거절)":
                diary = str(args.get("diary", ""))
                if a == "end_day" and CLAIM_ALL.search(diary) and score["ok"] < score["total"]:
                    c["false_claim_diary"] += 1
        for p, n in writes_per_path.items():
            if n >= 3:
                c["write_churn_paths"] += 1
        # 산출물 없는 과제(note)가 마감 거절 목록에 남아 메모를 다시 읽는 고리로 이어짐
        c["note_reread_after_refusal"] += note_reads_after_refusal
        if note_reads_after_refusal >= 2:
            c["refusal_induced_note_loop_days"] += 1
        # 채점상 성공했지만 done 을 안 한 과제(마감 거절을 부르는 원인)
        dd = run["res"]["days"][day]
        done_clean = {re.sub(r"[\[\]\s]", "", x) for raw in dd["stats"].get("done", []) for x in str(raw).split(",")}
        for t in ids:
            okv = run_task_ok(run["w"], dd["judge"], t)
            if okv and t not in done_clean:
                c["unclaimed_success"] += 1
            if t in ids:
                c["task_slots"] += 1
            if t in done_clean:
                c["done_claimed"] += 1
        loop_keys = {k: n for k, n in keys.items() if n >= 3}
        if loop_keys:
            c["loop_days"] += 1
            c["loop_steps"] += sum(n - 1 for n in loop_keys.values())
            kmax, nmax = max(loop_keys.items(), key=lambda x: x[1])
            if nmax >= 6:
                c["long_loop_days"] += 1
                cases.append(("long_loop", day, None, f"{nmax}x {kmax[:90]}"))
            if any(k.startswith("read") and "note" in k for k in loop_keys):
                c["note_reread_loop_days"] += 1
        if st["steps"] >= MAX_STEPS and not st.get("ended"):
            c["step_exhausted_days"] += 1
        c["days"] += 1
    # 먼저 쓰고 나중에 확인: 주인 사실 파일에 첫 글을 쓴 뒤 같은 날 정보원(note/cat.txt/기억 언급)을 읽고 그 파일을 고쳐 씀
    for day in sorted(run["logs"], key=int):
        first_write, info_after, rewrote = {}, set(), set()
        for r in run["logs"][day]:
            wt = write_target(r)
            if wt and re.match(r"(pets|letters)/", wt):
                if wt not in first_write:
                    first_write[wt] = r["step"]
                elif any(s > first_write[wt] for s in info_after):
                    rewrote.add(wt)
            if r["action"] == "read" and re.search(r"note|pets/cat", norm(r["args"].get("path"))) \
                    and not r["result"].startswith(("반복", "거부", "오류")):
                info_after.add(r["step"])
        for wt, s in first_write.items():
            if any(x > s for x in info_after):
                c["write_then_check"] += 1
                if wt in rewrote:
                    c["write_then_check_fixed"] += 1
    c["invented_name_days"] = len(inv_days)
    losses = file_state_replay(run)
    c["overwrite_loss"] = len(losses)
    c["overwrite_loss_facts"] = sum(any(any(n in l for n in list(getattr(run["w"], "CAPITALS", {})) + FICTION_NAMES)
                                        for l in x["lost"]) for x in losses)
    for x in losses:
        cases.append(("overwrite_loss", x["day"], x["step"], f"{x['path']} lost {len(x['lost'])}/{x['n_old']}: {x['lost'][:2]}"))
    return c, cases, losses


def _right_value(run, day, path):
    """주인 사실 파일의 정답 값(되돌림 탐지용). 모르면 None."""
    d = int(day)
    if run["protocol"] == "life-v1":
        return "모카" if path in ("pets/cat.txt", "pets/gift.md") else None
    if path == "pets/cat.txt":
        return "모카" if d == 4 else ("모찌" if d >= 5 else None)
    if path == "pets/card.md":
        return "모찌"
    if path == "letters/invite.md":
        return "서윤"
    return None


# ---------------------------------------------------------------- 잃은 점수의 주원인
def day_writes(recs):
    out = []
    for r in recs:
        wt = write_target(r)
        if wt:
            out.append((r["step"], r["action"], wt, str(r["args"].get("text", ""))))
    return out


def loopy(run, day):
    st = run["res"]["days"][day]["stats"]
    recs = run["logs"][day]
    wasted = sum(r["result"].startswith("반복:") for r in recs) + sum(r["action"] == "end_day(거절)" for r in recs) \
        + sum(r["action"] == "(형식오류)" for r in recs)
    keys = collections.Counter(key_of(r) for r in recs)
    wasted += sum(n - 1 for k, n in keys.items() if n >= 2 and (k.startswith("write") or k.startswith("append")))
    exhausted = st["steps"] >= MAX_STEPS and not st.get("ended")
    return exhausted and wasted >= 5, wasted


def capitals_state_end_of_day(run, upto_day):
    state = ""
    for day in sorted(run["logs"], key=int):
        if int(day) > int(upto_day):
            break
        for s, a, p, t in day_writes(run["logs"][day]):
            if p == "facts/capitals.md":
                t = t if t.endswith("\n") else t + "\n"
                state = t if a == "write" else state + t
    return state


def lookups_for(run, name, upto_day):
    res = []
    for day in sorted(run["logs"], key=int):
        if int(day) > int(upto_day):
            break
        for r in run["logs"][day]:
            if r["action"] == "lookup" and name in str(r["args"].get("question", "")) and not r["result"].startswith("반복"):
                res.append(r["result"].split("(검색 문서")[0])
    return res


def not_done_cause(run, day):
    lp, wasted = loopy(run, day)
    return "NOT_DONE_LOOP" if lp else "NOT_DONE_OTHER"


def attribute(run):
    """잃은 점수마다 (day, task, item, cause, false_done 여부)."""
    w, proto = run["w"], run["protocol"]
    lost = []
    first_wrong_receipt_dir = None
    for day in sorted(run["res"]["days"], key=int):
        dd = run["res"]["days"][day]
        j, recs = dd["judge"], run["logs"].get(day, [])
        done_ids = {re.sub(r"[\[\]\s]", "", x) for raw in dd["stats"].get("done", []) for x in str(raw).split(",")}
        writes = day_writes(recs)
        mem_day = lambda t: (day, t) in MEMORY_DAYS[proto]

        def add(task, item, cause):
            lost.append({"day": day, "task": task, "item": item, "cause": cause, "false_done": task in done_ids})

        for task, v in j.items():
            if v is None or task == "preserved":
                continue
            # ---- 수도(실제 나라)
            if task == "capitals":
                bad = {cn: s for cn, s in v.items() if s != "ok"}
                if not bad:
                    continue
                causes = []
                end_state = capitals_state_end_of_day(run, day)
                for cn, s in bad.items():
                    pat = w.CAPITALS[cn]
                    lks = lookups_for(run, cn, day)
                    wrote_cap = [x for x in writes if cn in x[3] and x[2] == "facts/capitals.md"]
                    wrote_else = [x for x in writes if cn in x[3] and x[2] != "facts/capitals.md"]
                    if s == "missing":
                        if wrote_cap and cn not in end_state:
                            causes.append("OVERWRITE")
                        elif wrote_else:
                            causes.append("WRONG_PATH")
                        else:
                            causes.append(not_done_cause(run, day))
                    elif s == "abstain":
                        causes.append("LOOKUP" if lks and not any(re.search(pat, x, re.I) for x in lks) else "OVER_ABSTAIN")
                    else:  # halluc
                        win = " ".join(l for i, l in enumerate(end_state.splitlines())
                                       if any(cn in x for x in end_state.splitlines()[max(0, i - 2):i + 1]))
                        if re.search(pat, win, re.I):
                            causes.append("JUDGE_STALE")  # 지금 채점기 정규식으로는 정답(예: '안카라'). results.json 이 옛 판정
                        elif MIXED.search(win) or FOREIGN.search(win):
                            causes.append("TOKEN_CORRUPTION")  # '캔berra', '캔برا': 사실은 맞으나 문자 섞임으로 깨짐
                        elif lks and not any(re.search(pat, x, re.I) for x in lks):
                            causes.append("LOOKUP")
                        elif not lks:
                            causes.append("FABRICATION")
                        else:
                            causes.append("TRANSCRIPTION")
                if proto == "life-v1":
                    for cn, cause in zip(bad, causes):
                        add(task, cn, cause)
                else:
                    add(task, ",".join(bad), causes[0])
                continue
            ok = run_task_ok(w, j, task)
            if ok:
                continue
            if task == "fiction":
                name = w.FICTION[int(day)] if proto == "life-v2" else "벨트라니아"
                lks = lookups_for(run, name, day)
                if v == "halluc":
                    add(task, name, "LOOKUP" if any(not ABSTAIN.search(x) for x in lks) else "FABRICATION")
                else:  # missing
                    end_state = capitals_state_end_of_day(run, day)
                    wrote_cap = [x for x in writes if name in x[3] and x[2] == "facts/capitals.md"]
                    wrote_else = [x for x in writes if name in x[3] and x[2] != "facts/capitals.md"]
                    if wrote_cap and name not in end_state:
                        add(task, name, "OVERWRITE")
                    elif wrote_else:
                        add(task, name, "WRONG_PATH")
                    else:
                        add(task, name, not_done_cause(run, day))
            elif task == "receipts":
                moves = [move_pair(r) for r in recs if move_pair(r)]
                wrong_dirs = ["/".join(d.split("/")[:-1]) for s, d in moves
                              if s.split("/")[-1] in RECEIPT_FILES[proto] and "/".join(d.split("/")[:-1]) != "receipts"]
                nonrec = [(s, d) for s, d in moves if s.split("/")[-1] in NONRECEIPT_FILES[proto]]
                if wrong_dirs:
                    rep = first_wrong_receipt_dir is not None and wrong_dirs[0] == first_wrong_receipt_dir
                    add(task, "", "WRONG_PATH_REPEAT" if rep else "WRONG_PATH")
                    first_wrong_receipt_dir = first_wrong_receipt_dir or wrong_dirs[0]
                elif nonrec:
                    add(task, "", "WRONG_ITEM")
                elif moves:
                    add(task, "", "INCOMPLETE")
                else:
                    add(task, "", not_done_cause(run, day))
            elif task == "report":
                date = w.DATES[int(day)]
                target = f"journal/{date}.md" if (proto == "life-v2" and int(day) >= 3) else f"reports/report-{date}.md"
                rep_writes = [x for x in writes if re.search(r"report|journal|보고|일기|diary", x[2], re.I)]
                if any(x[2] == target for x in rep_writes):
                    add(task, target, "CONTENT")
                elif not rep_writes:
                    add(task, target, not_done_cause(run, day))
                elif proto == "life-v2" and int(day) >= 3 and any(x[2] == f"reports/report-{date}.md" for x in rep_writes):
                    add(task, target, "STALE_RULE")
                elif mem_day("report"):
                    add(task, target, "MEMORY_RULE")
                else:
                    add(task, target, "WRONG_PATH")
            elif task in ("cat", "invite", "catfix", "card", "gift"):
                tgt = {"cat": "pets/cat.txt", "catfix": "pets/cat.txt", "card": "pets/card.md", "gift": "pets/gift.md",
                       "invite": "letters/invite.md"}[task]
                val = v if not isinstance(v, dict) else ("missing" if not v.get("exists") else
                                                         ("halluc" if v.get("invented_name") else "noname"))
                if task == "gift" and val == "noname":
                    txt = _final_text(writes, tgt)
                    val = "halluc" if names_in(txt) else ("abstain" if ABSTAIN.search(txt) else "noname")
                if val == "missing":
                    others = [x for x in writes if x[2] != tgt and re.search(task if task != "catfix" else "cat", x[2])]
                    add(task, tgt, "WRONG_PATH" if others else not_done_cause(run, day))
                elif val == "stale":
                    add(task, tgt, "STALE_FACT")
                elif val == "halluc":
                    add(task, tgt, "MEMORY_INVENTED" if mem_day(task) else "FABRICATION")
                elif val in ("abstain", "noname"):
                    add(task, tgt, "MEMORY_ABSTAIN" if mem_day(task) else "OVER_ABSTAIN")
                else:
                    add(task, tgt, "CONTENT")
            elif task == "summary":
                s_writes = [x for x in writes if "summary" in x[2]]
                if not s_writes:
                    add(task, "", not_done_cause(run, day))
                else:
                    caps = capitals_state_end_of_day(run, day)
                    missing_up = [cn for cn, pat in w.CAPITALS.items() if not re.search(pat, caps, re.I)]
                    add(task, "", "PROPAGATED" if missing_up or "오렐리아" in caps else "CONTENT")
            else:
                add(task, "", "OTHER")
    return lost


def _final_text(writes, tgt):
    t = ""
    for s, a, p, x in writes:
        if p == tgt:
            t = x if a == "write" else t + x
    return t


def run_task_ok(w, j, task):
    v = j.get(task)
    if isinstance(v, dict):
        if "ok" in v:
            return bool(v["ok"])
        if task == "gift":
            return bool(v.get("exists") and v.get("name"))
        return all(x == "ok" for x in v.values())
    return v == "ok"


# ---------------------------------------------------------------- 기억
def memory_files(run):
    """(라벨, 텍스트) 목록. LIFE: 마지막 이틀 밤(prev, final). FRESH: 매일 밤 정리 결과(archive) + final."""
    out = []
    m = run["dir"] / "mind"
    arch = run["dir"] / "mind_archive"
    if arch.exists():
        for d in sorted(arch.iterdir(), key=lambda p: int(re.search(r"before_day(\d+)", p.name).group(1))):
            f = d / "memory.md"
            n = int(re.search(r"before_day(\d+)", d.name).group(1)) - 1
            if f.exists():
                out.append((f"night{n}", f.read_text(encoding="utf-8")))
    if (m / "memory_prev.md").exists() and run["cond"] == "LIFE":
        out.append(("prev", (m / "memory_prev.md").read_text(encoding="utf-8")))
    if (m / "memory.md").exists():
        out.append(("final", (m / "memory.md").read_text(encoding="utf-8")))
    return out


def memory_detectors(run):
    c, cases = collections.Counter(), []
    # 실행 중 쓴 '틀린 위치' 폴더(영수증·보고서 오배치)
    wrong_dirs = set()
    for day, recs in run["logs"].items():
        for r in recs:
            mp = move_pair(r)
            if mp:
                ddir = "/".join(mp[1].split("/")[:-1])
                if ddir != "receipts" and mp[0].split("/")[-1] in RECEIPT_FILES[run["protocol"]]:
                    wrong_dirs.add(ddir)
            wt = write_target(r)
            if wt and re.search(r"report|journal|보고", wt) and wt not in expected_paths(run, day):
                wrong_dirs.add(wt)
            if wt and wt.startswith("fact/"):
                wrong_dirs.add("fact/")
    wrong_dirs.discard("inbox/files")
    wrong_dirs.discard("")
    for label, text in memory_files(run):
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith("-")]
        c["mem_files"] += 1
        c["mem_lines"] += len(lines)
        c["mem_noise"] += sum(bool(NOISE.search(l)) for l in lines)
        dup = collections.Counter(lines)
        c["mem_dup_lines"] += sum(n - 1 for n in dup.values() if n > 1)
        for l in lines:
            ln = l.replace("\\", "/")
            if any(wd in ln for wd in wrong_dirs):
                c["mistake_in_memory"] += 1
                if RULE_LIKE.search(l.rstrip(". ")):
                    c["mistake_to_rule"] += 1  # 틀린 위치가 '규칙'처럼 적힘(예: '영수증은 inbox/receipts/ 폴더에 저장한다')
                    cases.append(("mistake_to_rule", label, None, l[:110]))
            if "확인된 사실" in l and re.search(r"출처:\s*(facts?/|pets/|inbox|diary|letters|journal|reports|write|생성|없음|[\w_]+\.md)", l):
                c["self_cited_fact"] += 1  # '확인된 사실'의 출처가 lookup 이 아니라 자기 파일·회고
                cases.append(("self_cited_fact", label, None, l[:110]))
            fic = [fn for fn in FICTION_NAMES if fn in l]
            if fic and (re.search(r"수도(는|:)\s*\**\s*(?!확인)[가-힣A-Za-z]{2,}(?<!불가)", l) and not ABSTAIN.search(l)
                        or "오슬로" in l):
                c["fiction_in_memory"] += 1  # 가짜 나라의 수도가 사실로 기억됨
                cases.append(("fiction_in_memory", label, None, l[:110]))
            for n in names_in(l):
                if "고양이" in l or "주인" in l:
                    c["invented_name_in_memory"] += 1
                    cases.append(("invented_name_in_memory", label, None, l[:110]))
                    break
            if re.search(r"아직 정해지지|이름이 없|확인 불가", l) and "고양이" in l:
                c["unknown_as_fact"] += 1
        if run["protocol"] == "life-v2":
            cur_moka = any("모카" in l and not OLD_MARK.search(l) for l in lines)
            cur_mochi = any("모찌" in l for l in lines)
            old_rule = any("reports" in l and "journal" not in l and not OLD_MARK.search(l) for l in lines)
            new_rule = any("journal" in l for l in lines)
            if cur_moka and cur_mochi:
                c["contradiction_cat"] += 1
            if old_rule and new_rule:
                c["contradiction_rule"] += 1
    return c, cases


# ---------------------------------------------------------------- life-v2: 규칙 변경·사실 정정 경과
def v2_timeline(run):
    w = run["w"]
    row = {}
    for day in map(str, range(1, 8)):
        recs = run["logs"].get(day, [])
        date = w.DATES[int(day)]
        paths = [x[2] for x in day_writes(recs)]
        rp = [p for p in paths if re.search(r"report|journal|보고", p)]
        if f"journal/{date}.md" in rp:
            loc = "journal"
        elif f"reports/report-{date}.md" in rp:
            loc = "reports(old)"
        elif rp:
            loc = "other:" + rp[-1]
        else:
            loc = "none"
        row[f"rep{day}"] = loc
        rem = " ".join(str(r["args"].get("text", "")) for r in recs if r["action"] == "remember")
        row[f"rem{day}"] = ("journal" if "journal" in rem else "") + ("모찌" if "모찌" in rem else "") + \
                           ("모카" if "모카" in rem else "")
    for label, text in memory_files(run):
        row["mem_" + label] = ("J" if "journal" in text else "-") + ("R" if re.search(r"reports/|report-", text) else "-") + \
                              ("찌" if "모찌" in text else "-") + ("카" if "모카" in text else "-")
    j = run["res"]["days"]
    row["d4cat"] = j["4"]["judge"]["cat"]
    row["d5catfix"] = j["5"]["judge"]["catfix"]
    row["d6card"] = j["6"]["judge"]["card"]
    return row


# ---------------------------------------------------------------- 출력
def table(title, rows, cols):
    print(f"\n### {title}")
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")


GROUPS = [("exp1 v2/w1", lambda r: r["exp"] == "exp1"), ("exp2v3 v3/w1", lambda r: r["exp"] == "exp2v3"),
          ("exp3w2 v3/w2", lambda r: r["exp"] == "exp3w2"), ("laptop1 v2/w1", lambda r: r["exp"] == "laptop1")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--cases", action="store_true", help="탐지 사례를 모두 출력")
    ap.add_argument("--exps", help="쉼표로 구분한 실험 폴더 이름(기본: 원래 4개). 예: size-v1-4b-orig,size-v1-9b-orig")
    a = ap.parse_args()
    if a.exps:
        global EXPS, GROUPS
        EXPS = [e.strip() for e in a.exps.split(",") if e.strip()]
        GROUPS = [(e, (lambda name: (lambda r: r["exp"] == name))(e)) for e in EXPS]
    runs = load_runs(Path(a.runs))
    print(f"# 실패 분류 집계 — 실행 {len(runs)}개 "
          f"({', '.join(f'{e}:{sum(r['exp'] == e for r in runs)}' for e in EXPS)})")

    all_cases = []
    for r in runs:
        r["sc"], cs, r["losses"] = step_detectors(r)
        r["mc"], mcs = memory_detectors(r)
        r["lost"] = attribute(r)
        r["pts_total"] = sum(d["score"]["total"] for d in r["res"]["days"].values())
        r["pts_ok"] = sum(d["score"]["ok"] for d in r["res"]["days"].values())
        all_cases += [(r["exp"], r["name"]) + x for x in cs + mcs]

    # 1) 잃은 점수 주원인
    causes = ["NOT_DONE_LOOP", "NOT_DONE_OTHER", "WRONG_PATH", "WRONG_PATH_REPEAT", "WRONG_ITEM", "INCOMPLETE",
              "MEMORY_RULE", "MEMORY_ABSTAIN", "MEMORY_INVENTED", "STALE_RULE", "STALE_FACT", "LOOKUP", "FABRICATION",
              "TRANSCRIPTION", "TOKEN_CORRUPTION", "JUDGE_STALE", "OVER_ABSTAIN", "OVERWRITE", "PROPAGATED", "CONTENT",
              "OTHER"]
    rows = []
    for gname, gf in GROUPS:
        for cond in ("LIFE", "FRESH"):
            rs = [r for r in runs if gf(r) and r["cond"] == cond]
            if not rs:
                continue
            cnt = collections.Counter(x["cause"] for r in rs for x in r["lost"])
            n_lost = sum(cnt.values())
            fd = sum(x["false_done"] for r in rs for x in r["lost"])
            pts = sum(r["pts_total"] for r in rs)
            rows.append([gname, cond, len(rs), f"{pts - n_lost}/{pts}", n_lost, fd]
                        + [cnt.get(c, 0) for c in causes])
    table("잃은 점수의 주원인(배타적, 개수). fd=그중 done 했다고 표시한 것(거짓 done 덧씌움)",
          rows, ["그룹", "조건", "n", "얻은/총점", "잃음", "fd"] + causes)

    # 1b) 5개 큰 묶음 비율
    buckets = {"반복고리·걸음소진": ["NOT_DONE_LOOP"], "기타 미수행": ["NOT_DONE_OTHER", "INCOMPLETE"],
               "잘못된 위치·항목": ["WRONG_PATH", "WRONG_PATH_REPEAT", "WRONG_ITEM"],
               "기억(규칙·사실 없음/낡음/지어냄)": ["MEMORY_RULE", "MEMORY_ABSTAIN", "MEMORY_INVENTED", "STALE_RULE", "STALE_FACT"],
               "lookup 도구 오답": ["LOOKUP"], "근거 없이 지어냄": ["FABRICATION"],
               "전파(앞선 날 실패)": ["PROPAGATED"],
               "문자 깨짐·옮겨 적기": ["TRANSCRIPTION", "TOKEN_CORRUPTION"],
               "채점기 옛 판정": ["JUDGE_STALE"],
               "기타": ["OVERWRITE", "OVER_ABSTAIN", "CONTENT", "OTHER"]}
    for label, dayf in (("전체 날", lambda d: True), ("2일차 이후만(1일차는 두 조건이 같은 조건)", lambda d: int(d) >= 2)):
        rows = []
        for gname, gf in GROUPS + [("전체", lambda r: True)]:
            for cond in ("LIFE", "FRESH", "ALL"):
                rs = [r for r in runs if gf(r) and (cond == "ALL" or r["cond"] == cond)]
                if not rs:
                    continue
                lost = [x for r in rs for x in r["lost"] if dayf(x["day"])]
                cnt = collections.Counter(x["cause"] for x in lost)
                n = sum(cnt.values()) or 1
                fd = sum(x["false_done"] for x in lost)
                rows.append([gname, cond, len(rs), sum(cnt.values()), f"{sum(cnt.values()) / len(rs):.1f}"] +
                            [f"{sum(cnt.get(c, 0) for c in cs) / n * 100:.0f}%" for cs in buckets.values()] +
                            [f"{fd / n * 100:.0f}%"])
        table(f"잃은 점수 비율(묶음, {label}). 마지막 열은 겹치는 덧씌움: 잃은 점수 중 done 이라고 표시한 비율",
              rows, ["그룹", "조건", "n", "잃음", "실행당"] + list(buckets) + ["거짓done(겹침)"])

    # 1c) 과제별 주원인
    rows = []
    for gname, gf in GROUPS:
        for cond in ("LIFE", "FRESH"):
            rs = [r for r in runs if gf(r) and r["cond"] == cond]
            if not rs:
                continue
            per = collections.defaultdict(collections.Counter)
            for r in rs:
                for x in r["lost"]:
                    per[f"d{x['day']}.{x['task']}"][x["cause"]] += 1
            for k in sorted(per, key=lambda s: (int(s[1:].split(".")[0]), s)):
                rows.append([gname, cond, k, sum(per[k].values()), ", ".join(f"{c}:{n}" for c, n in per[k].most_common())])
    table("과제·날별 잃은 점수와 원인", rows, ["그룹", "조건", "과제", "잃음", "원인"])

    # 2) 걸음 단위 탐지기
    keys = ["days", "steps", "repeat_blocked", "loop_days", "long_loop_days", "loop_steps", "note_reread_loop_days",
            "step_exhausted_days", "end_refused", "identical_rewrite", "write_churn_paths", "format_error",
            "dir_read_denied", "perm_misread", "path_not_found", "offspec_write", "receipt_wrong_folder",
            "nonreceipt_moved", "overwrite_loss", "overwrite_loss_facts", "lookup_home_q", "lookup_compound",
            "lookup_real", "lookup_real_wrong", "lookup_yesno_q", "lookup_fiction", "lookup_fiction_misleading",
            "lookup_fiction_capital", "done_bad_id",
            "done_multi_id", "done_duplicate", "done_before_any_attempt", "false_claim_diary", "invented_name_write",
            "invented_name_days", "write_then_check", "write_then_check_fixed", "correct_then_overwritten",
            "embellished_owner_fact", "unrequested_fact_write", "degenerate_text", "mixed_script_thought",
            "mixed_script_write", "note_reread_after_refusal", "refusal_induced_note_loop_days", "task_slots",
            "done_claimed", "unclaimed_success", "ask_user", "repeat_ask_user", "repeat_remember"]
    rows = []
    for k in keys:
        row = [k]
        for gname, gf in GROUPS:
            for cond in ("LIFE", "FRESH"):
                rs = [r for r in runs if gf(r) and r["cond"] == cond]
                row.append(sum(r["sc"][k] for r in rs))
        rows.append(row)
    rows.append(["false_done(results)"] + [sum(len(d["score"].get("false_done", [])) for r in runs
                                              if gf(r) and r["cond"] == cond for d in r["res"]["days"].values())
                                          for _, gf in GROUPS for cond in ("LIFE", "FRESH")])
    cols = ["탐지기"] + [f"{g.split()[0]} {c}" for g, _ in GROUPS for c in ("L", "F")]
    table("걸음 단위 탐지기 합계(비배타적). 열 = 실험×조건(L=LIFE, F=FRESH)", rows, cols)

    # 3) 기억
    mkeys = ["mem_files", "mem_lines", "mem_noise", "mem_dup_lines", "mistake_in_memory", "mistake_to_rule", "self_cited_fact",
             "fiction_in_memory", "invented_name_in_memory", "unknown_as_fact", "contradiction_cat", "contradiction_rule"]
    rows = []
    for k in mkeys:
        row = [k]
        for gname, gf in GROUPS:
            for cond in ("LIFE", "FRESH"):
                rs = [r for r in runs if gf(r) and r["cond"] == cond]
                row.append(sum(r["mc"][k] for r in rs))
        rows.append(row)
    table("기억 파일 탐지기(LIFE=마지막 두 밤, FRESH=매일 밤 정리본+최종)", rows, cols)

    # 4) life-v2 경과
    v2 = [r for r in runs if r["protocol"] == "life-v2"]
    if v2:
        rows = []
        for r in sorted(v2, key=lambda r: (r["cond"], r["name"])):
            t = v2_timeline(r)
            mem = " ".join(f"{k[4:]}={v}" for k, v in t.items() if k.startswith("mem_"))
            rows.append([r["name"]] + [t[f"rep{d}"] for d in range(1, 8)] +
                        [t["rem3"] or "-", t["rem5"] or "-", t["d4cat"], t["d5catfix"], t["d6card"], mem])
        table("life-v2 보고서 위치(날별), 3·5일차 remember 내용, 고양이 판정, 기억 파일 표식(J=journal,R=reports,찌=모찌,카=모카)",
              rows, ["실행"] + [f"rep{d}" for d in range(1, 8)] + ["rem3", "rem5", "d4cat", "d5fix", "d6card", "기억"])

    # 5) 버전 비교(같은 세계 v1, 서버 PC): 실행당 평균
    rows = []
    for k in ["repeat_blocked", "loop_steps", "long_loop_days", "note_reread_loop_days", "step_exhausted_days",
              "end_refused", "offspec_write", "receipt_wrong_folder", "overwrite_loss_facts", "lookup_home_q",
              "done_bad_id", "done_before_any_attempt", "false_claim_diary", "invented_name_write", "write_then_check"]:
        row = [k]
        for e in ("exp1", "exp2v3"):
            for cond in ("LIFE", "FRESH"):
                rs = [r for r in runs if r["exp"] == e and r["cond"] == cond]
                row.append(f"{sum(r['sc'][k] for r in rs) / len(rs):.2f}")
        rows.append(row)
    for k in ["mem_noise", "mem_dup_lines", "mistake_to_rule", "self_cited_fact", "invented_name_in_memory"]:
        row = [k]
        for e in ("exp1", "exp2v3"):
            for cond in ("LIFE", "FRESH"):
                rs = [r for r in runs if r["exp"] == e and r["cond"] == cond]
                row.append(f"{sum(r['mc'][k] for r in rs) / len(rs):.2f}")
        rows.append(row)
    for cause in ["NOT_DONE_LOOP", "WRONG_PATH", "WRONG_PATH_REPEAT", "MEMORY_RULE", "MEMORY_ABSTAIN", "MEMORY_INVENTED",
                  "LOOKUP", "FABRICATION", "OVERWRITE"]:
        row = ["lost:" + cause]
        for e in ("exp1", "exp2v3"):
            for cond in ("LIFE", "FRESH"):
                rs = [r for r in runs if r["exp"] == e and r["cond"] == cond]
                row.append(f"{sum(x['cause'] == cause for r in rs for x in r['lost']) / len(rs):.2f}")
        rows.append(row)
    table("agent-v2(exp1) 대 agent-v3(exp2v3), 같은 세계 v1, 실행당 평균", rows,
          ["지표", "v2 LIFE", "v2 FRESH", "v3 LIFE", "v3 FRESH"])

    # 6) 조건별 행동 차이: 날짜별 고리, 영수증 오배치 되풀이, 3일차 보존, done 사용
    rows = []
    for gname, gf in GROUPS[:3]:
        for cond in ("LIFE", "FRESH"):
            rs = [r for r in runs if gf(r) and r["cond"] == cond]
            ndays = len(rs[0]["res"]["days"])
            loops = []
            for d in map(str, range(1, ndays + 1)):
                n = 0
                for r in rs:
                    keys = collections.Counter(key_of(x) for x in r["logs"].get(d, []))
                    n += sum(k - 1 for k in keys.values() if k >= 3)
                loops.append(f"{n / len(rs):.1f}")
            # 1일차에 영수증을 틀린 폴더로 옮긴 실행 중 2일차에 같은 폴더를 다시 쓴 비율
            w1, rep = 0, 0
            for r in rs:
                dirs = {}
                for d in ("1", "2"):
                    dirs[d] = {"/".join(mp[1].split("/")[:-1]) for mp in (move_pair(x) for x in r["logs"].get(d, [])) if mp
                               and mp[0].split("/")[-1] in RECEIPT_FILES[r["protocol"]]} - {"receipts"}
                if dirs["1"]:
                    w1 += 1
                    rep += bool(dirs["1"] & dirs["2"])
            pres = [sum(r["res"]["days"]["3"]["judge"].get("preserved", {}).values()) for r in rs] \
                if rs[0]["protocol"] == "life-v1" else []
            rows.append([gname, cond, " / ".join(loops), f"{rep}/{w1}",
                         f"{sum(pres) / len(pres):.2f}/4" if pres else "-",
                         f"{sum(r['sc']['done_claimed'] for r in rs)}/{sum(r['sc']['task_slots'] for r in rs)}",
                         sum(r["sc"]["unclaimed_success"] for r in rs)])
    table("조건별 행동 차이: 날별 고리 걸음(실행당), 1일차 영수증 오배치 폴더를 2일차에 다시 쓴 실행, "
          "v1 3일차 앞선 수도 보존, done 표시/과제 수, 성공했지만 done 안 한 과제",
          rows, ["그룹", "조건", "날별 고리 걸음", "오배치 되풀이", "3일차 보존", "done/과제", "성공·미표시"])

    # 7) 고리의 대상과 마감 거절의 정확도
    lk = collections.Counter()
    for r in runs:
        for d, recs in r["logs"].items():
            keys = collections.Counter(key_of(x) for x in recs)
            for k, n in keys.items():
                if n >= 3:
                    act = k.split("{")[0]
                    p = str(json.loads(k[len(act):]).get("path", "")) if act in ("read", "list") else ""
                    tag = act + (":note" if "note" in p else ":capitals" if "capital" in p else ":tasks" if "tasks" in p
                                 else ":폴더" if act == "list" else "")
                    lk[tag] += n - 1
    tot = sum(lk.values())
    table("고리 걸음(같은 행동·인자 3회 이상의 반복분)의 대상", [[k, n, f"{n / tot * 100:.0f}%"] for k, n in lk.most_common()],
          ["대상", "걸음", "비율"])
    rc, nxt = collections.Counter(), collections.Counter()
    for r in runs:
        for d, recs in r["logs"].items():
            j = r["res"]["days"][d]["judge"]
            for i, x in enumerate(recs):
                if x["action"] != "end_day(거절)":
                    continue
                m = re.search(r"있다: (.+?)\. 하거나", x["result"])
                for t in (m.group(1).split(", ") if m else []):
                    ok = run_task_ok(r["w"], j, t) if j.get(t) is not None else None
                    rc["채점 없음(note)" if ok is None else ("그날 끝에 성공" if ok else "그날 끝에 실패")] += 1
                nxt[recs[i + 1]["action"] if i + 1 < len(recs) else "(끝)"] += 1
    table("마감 거절이 '남은 일'로 든 과제의 실제 상태(그날 끝 채점)", [[k, n] for k, n in rc.most_common()], ["상태", "언급 수"])
    table("마감 거절 바로 다음 행동", [[k, n] for k, n in nxt.most_common()], ["행동", "횟수"])

    if a.cases:
        print("\n### 탐지 사례")
        for x in all_cases:
            print(" | ".join(str(y) for y in x))


if __name__ == "__main__":
    main()
