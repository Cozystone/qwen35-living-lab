"""Track A 브리지: ATANOR life 코어(v24)를 트랙 L 세계의 집에서 하루 살게 한다(TRACK_A_DESIGN.md 2.1).

하루 = world.setup_day(home) -> FRESH 이면 mind/ 보관 -> tasks.md 의 '- [id] 문장' 줄마다 Mind.do(문장 원문)
      -> 주인이 있는 날이면 보류한 일 다시 꺼내기(resume) -> world.judge / score / false_done -> results.json(트랙 L 스키마).
정직성 규칙: 과제를 거르지 않는다(시도할 수 없는 과제도 넘긴다). Mind 는 judge·truth 를 보지 않는다(교사만 닿는다).
"""
import json
import re
import shutil
import sys
import time
from pathlib import Path

ATANOR = Path(r"D:\ATANOR-experiments\2026-10-27\trackA")
if str(ATANOR) not in sys.path:
    sys.path.insert(0, str(ATANOR))
from atanor_os.agent.life import Mind  # noqa: E402
from atanor_os.world.home_world import HomeWorkspace  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teacher import TrackATeacher  # noqa: E402
from truth import OWNER_DAYS, TASK_TRUTH  # noqa: E402

AGENT = "atanor-life-v24/home-1/bridge-1"
TASK_LINE = re.compile(r"^- \[([^\]]+)\] (.*)$", re.M)


def run_day(root: Path, world, day: int, cond: str, teacher_mode: str, seed: int) -> dict:
    root = Path(root)
    home_p, mind_p, lab_p = root / "home", root / "mind", root / "lab"
    ws = HomeWorkspace(home_p, create=not home_p.exists())
    world.setup_day(home_p, day)
    if cond == "FRESH" and mind_p.exists():
        arch = root / "mind_archive" / f"before_day{day}"
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mind_p), str(arch))
    proto = world.PROTOCOL_VERSION
    owner = teacher_mode == "all" or (teacher_mode == "d1" and day in OWNER_DAYS.get(proto, set()))
    teacher = TrackATeacher(home_p, world)
    lines = TASK_LINE.findall((home_p / "inbox" / "tasks.md").read_text(encoding="utf-8"))
    rows, claimed, t_day = [], [], time.time()
    totals = {"home_actions": 0, "lab_actions": 0}

    def one(k, tid, sentence, task_id, d0, resume_goal=None):
        teacher.begin(d0, tid, TASK_TRUTH.get((proto, d0, tid)))
        h0, t0 = dict(teacher.help), time.time()
        mind = Mind(ws, mind_p, lab_p, user=teacher if owner else None, seed=seed * 1000 + day * 10 + k)
        r = mind.resume(resume_goal) if resume_goal else mind.do(sentence, task_id)
        helped = {q: teacher.help[q] - h0.get(q, 0) for q in teacher.help if teacher.help[q] - h0.get(q, 0)}
        counts = dict(mind.counts)
        return r, helped, counts, round(time.time() - t0, 2)

    for k, (tid, sentence) in enumerate(lines):
        r, helped, counts, sec = one(k, tid, sentence, f"d{day}-{tid}", day)
        claim = r.get("achieved") is True
        if claim:
            claimed.append(tid)
        rows.append({"day": day, "tid": tid, "command": sentence, "owner": owner, "agent": r, "claim": claim,
                     "help": helped, "counts": counts, "seconds": sec})
    resumed = []
    if owner:  # 주인이 있는 날: 지난날 보류한 일을 꺼낸다(life_gen.resume_goals 와 같은 방식)
        probe = Mind(ws, mind_p, lab_p, user=teacher, seed=seed * 1000 + day * 10 + 9)
        for j, g in enumerate(probe.pending_goals()):
            m = re.match(r"d(\d+)-(.+)$", g["id"])
            d0, tid = int(m.group(1)), m.group(2)
            r, helped, counts, sec = one(9 - j, tid, g["command"], g["id"], d0, resume_goal=g)
            resumed.append({"day": day, "goal": g["id"], "from_day": d0, "tid": tid, "agent": r, "help": helped,
                            "counts": counts, "seconds": sec,
                            "ok": r is not None and teacher.world.task_ok(teacher.world.judge(home_p, d0), tid) is True})
    j = world.judge(home_p, day)
    s = world.score(j)
    s["false_done"] = world.false_done(j, claimed)
    help_total = {}
    for row in rows + resumed:
        for q, n in row["help"].items():
            help_total[q] = help_total.get(q, 0) + n
    for row in rows + resumed:
        c = row["counts"]
        totals["home_actions"] += c.get("home_actions", 0)
        totals["lab_actions"] += c.get("lab_actions", 0) + c.get("rehearsal_actions", 0)
    outcomes = {}
    for row in rows:
        ok = world.task_ok(j, row["tid"])
        a = row["agent"]
        row["outcome"] = "success" if ok else ("wrong" if a.get("achieved") is not None and a.get("achieved") is not False
                                               else "held")
        outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
    stats = {"steps": totals["home_actions"], "errors": 0, "repeats": 0, "denied": 0, "lookups": 0, "remembers": 0,
             "done": claimed, "ended": True, "stopped": False, "end_refused": 0, "help": help_total,
             "outcomes": outcomes, "lab_actions": totals["lab_actions"], "resumed": len(resumed),
             "resumed_ok": sum(x["ok"] for x in resumed), "owner": owner}
    with open(root / "days.jsonl", "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    if resumed:
        with open(root / "resumed.jsonl", "a", encoding="utf-8") as f:
            for row in resumed:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    snap = root / "snap" / f"d{day}"
    for part in ("home", "mind"):
        if (root / part).exists():
            shutil.copytree(root / part, snap / part, dirs_exist_ok=True)
    return {"judge": j, "score": s, "stats": stats, "wall_sec": round(time.time() - t_day, 1)}
