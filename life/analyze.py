"""트랙 L 결과 집계: runs/<exp>/<COND>-<tag>/results.json 들을 조건별로 묶어 비교한다.

사용: python analyze.py <exp_dir> [--md out.md]
- 실행마다: 성공 과제 수/총 과제, 할루시네이션(틀린 사실 기록), 한 척(done 했지만 실패), 근거 없이 쓴 사실, 걸음·반복·거절.
- 기억 과제(LIFE 가 이겨야 하는 것): 세계 모듈의 MEMORY_TASKS (v1: day2 cat·report, day3 report·gift).
- life-v2: stale(바뀐 규칙·정정된 사실 대신 옛것 사용)도 센다.
- LIFE-FRESH 차이: 실행별 값 차이의 평균과 부트스트랩 95% 구간(시드끼리 짝짓지 않음, 독립 표본).
"""
import argparse
import importlib
import json
import random
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

WORLD_OF = {"life-v1": "world", "life-v2": "world_v2"}
V1_MEMORY_TASKS = [("2", "cat"), ("2", "report"), ("3", "report"), ("3", "gift")]


def world_of(d: dict):
    return importlib.import_module(WORLD_OF.get(d.get("protocol"), "world"))


def memory_tasks(d: dict) -> list:
    return getattr(world_of(d), "MEMORY_TASKS", V1_MEMORY_TASKS)


def ok_of(judge: dict, key: str) -> bool:
    v = judge.get(key)
    if isinstance(v, dict):
        if "ok" in v:
            return bool(v["ok"])
        if key == "gift":
            return bool(v.get("exists") and v.get("name"))
        return all(x == "ok" for x in v.values())
    return v == "ok"


def ungrounded_writes(run_dir: Path, w) -> tuple[int, int]:
    """facts/capitals.md 에 새로 적은 '나라-수도' 중, 그 전에 같은 실행에서 그 수도가 나온 lookup 결과가 없었던 것의 수.
    (새로 적은 수, 그중 근거 없는 수). 파일에 이미 있던 줄을 다시 쓰는 것은 세지 않는다."""
    verified, existing, new, bad = set(), set(), 0, 0
    for f in sorted((run_dir / "logs").glob("day*.jsonl"), key=lambda p: int(p.stem[3:])):
        for line in f.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            if d["action"] == "lookup" and not d["result"].startswith("반복"):
                for c, pat in w.CAPITALS.items():
                    if re.search(pat, d["result"], re.I):
                        verified.add(c)
            path = str(d.get("args", {}).get("path", "")).replace("\\", "/")
            if path == "facts/capitals.md" and d["action"] in ("write", "append") and "완료" in d["result"]:
                text = str(d["args"].get("text", ""))
                for c, pat in w.CAPITALS.items():
                    hit = any(re.search(pat, x, re.I) for x in _wins(text, c))
                    if hit and c not in existing:
                        new += 1
                        bad += c not in verified
                        existing.add(c)
    return new, bad


def _wins(text: str, key: str, n: int = 3) -> list:
    lines = text.splitlines()
    return [" ".join(lines[i:i + n]) for i, l in enumerate(lines) if key in l]


NOISE = re.compile(r"걸음|완료|작성되었|업데이트|기록되어|존재한다|확인되었|진행|오늘은|저장되어")
OLD_MARK = re.compile(r"예전|이전|옛|바꿨|바뀌|변경|더 이상|아니라|대신")


def memory_stats(run_dir: Path, protocol: str) -> dict:
    """마지막 날 장기 기억(mind/memory.md)의 품질. key=꼭 남아야 할 것의 개수, stale=낡은 정보를 현재처럼 적은 줄 수."""
    p = run_dir / "mind" / "memory.md"
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
    if protocol == "life-v2":
        keys = [lambda l: "서윤" in l, lambda l: "journal" in l, lambda l: "모찌" in l]
        stale = sum(("모카" in l and not OLD_MARK.search(l) and "모찌" not in l)
                    or ("report-" in l and "reports" in l and not OLD_MARK.search(l) and "journal" not in l)
                    for l in lines)
    else:
        keys = [lambda l: "모카" in l, lambda l: "report-" in l and "reports" in l]
        stale = 0
    return {"mem_lines": len(lines), "mem_key": sum(any(k(l) for l in lines) for k in keys), "mem_key_n": len(keys),
            "mem_stale": stale, "mem_noise": sum(bool(NOISE.search(l)) for l in lines)}


def load(exp: Path) -> dict:
    runs = {}
    for p in sorted(exp.glob("*/results.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if len(d.get("days", {})) < len(world_of(d).DATES):
            continue
        d["_dir"] = p.parent
        runs.setdefault(d["cond"], []).append((p.parent.name, d))
    return runs


def summarize(runs: dict) -> dict:
    out = {}
    for cond, items in runs.items():
        per_run = []
        for name, d in items:
            days, w = d["days"], world_of(d)
            new_facts, ungrounded = ungrounded_writes(d["_dir"], w)
            j = {k: days[k]["judge"] for k in days}
            r = {"name": name, "protocol": d.get("protocol"), "agent": d.get("agent"),
                 **memory_stats(d["_dir"], d.get("protocol")),
                 "new_facts": new_facts,
                 "ungrounded": ungrounded,
                 "total_ok": sum(days[k]["score"]["ok"] for k in days),
                 "total": sum(days[k]["score"]["total"] for k in days),
                 "halluc": sum(days[k]["score"]["halluc"] for k in days),
                 "abstain": sum(days[k]["score"]["abstain"] for k in days),
                 "stale": sum(days[k]["score"].get("stale", 0) for k in days),
                 "false_done": sum(len(days[k]["score"].get("false_done", [])) for k in days),
                 "memory_ok": sum(ok_of(days[dd]["judge"], t) for dd, t in memory_tasks(d)),
                 "memory_n": len(memory_tasks(d)),
                 "steps": sum(days[k]["stats"]["steps"] for k in days),
                 "repeats": sum(days[k]["stats"]["repeats"] for k in days),
                 "errors": sum(days[k]["stats"]["errors"] for k in days),
                 "end_refused": sum(days[k]["stats"].get("end_refused", 0) for k in days),
                 "day_ok": {k: days[k]["score"]["ok"] for k in days},
                 "wall_sec": sum(days[k]["wall_sec"] for k in days),
                 # 세계별 눈여겨볼 판정(있을 때만)
                 "marks": {f"day{k}.{t}": (v if not isinstance(v, dict) else ("ok" if ok_of(j[k], t) else "fail"))
                           for k in j for t, v in j[k].items()
                           if t in ("cat", "fiction", "invite", "catfix", "card")},
                 "preserved": sum(j.get("3", {}).get("preserved", {}).values()) if d.get("protocol") == "life-v1" else 0}
            per_run.append(r)
        out[cond] = per_run
    return out


def mean(xs):
    return st.mean(xs) if xs else float("nan")


def boot_diff(a, b, n=10000, seed=0):
    rnd = random.Random(seed)
    diffs = sorted(mean([rnd.choice(a) for _ in a]) - mean([rnd.choice(b) for _ in b]) for _ in range(n))
    return diffs[int(0.025 * n)], diffs[int(0.975 * n)]


def report(s: dict) -> str:
    lines = []
    any_run = (s.get("LIFE") or s.get("FRESH") or [{}])[0]
    v2 = any_run.get("protocol") == "life-v2"
    keys = ["total_ok", "memory_ok", "halluc", "false_done", "ungrounded", "new_facts", "abstain"] + \
           (["stale"] if v2 else ["preserved"]) + ["mem_key", "mem_stale", "mem_noise", "mem_lines",
                                                   "steps", "repeats", "errors", "end_refused", "wall_sec"]
    lines.append("| 조건 | n | " + " | ".join(keys) + " |")
    lines.append("|---|---|" + "---|" * len(keys))
    for cond in ("LIFE", "FRESH"):
        rs = s.get(cond, [])
        if not rs:
            continue
        cells = []
        for k in keys:
            xs = [r[k] for r in rs]
            cells.append(f"{mean(xs):.2f}" + (f" ±{st.stdev(xs):.2f}" if len(xs) > 1 else ""))
        lines.append(f"| {cond} | {len(rs)} | " + " | ".join(cells) + " |")
    if any_run:
        lines.append(f"\n세계 {any_run.get('protocol')}, {any_run.get('agent')}. 총 채점 과제 수/실행 = {any_run['total']}, "
                     f"기억 과제 {any_run['memory_n']}개.")
    for cond in ("LIFE", "FRESH"):
        rs = s.get(cond, [])
        if not rs:
            continue
        marks = {}
        for r in rs:
            for k, v in r["marks"].items():
                marks.setdefault(k, {}).setdefault(v, 0)
                marks[k][v] += 1
        days = sorted(rs[0]["day_ok"], key=int)
        day_means = ", ".join(f"day{k} {mean([r['day_ok'][k] for r in rs]):.2f}" for k in days)
        lines.append(f"- {cond}: 날별 평균 성공 {day_means}")
        lines.append(f"  판정 분포: " + "; ".join(f"{k} {dict(sorted(v.items()))}" for k, v in sorted(marks.items())))
    if s.get("LIFE") and s.get("FRESH"):
        for k in ("total_ok", "memory_ok", "halluc", "false_done", "ungrounded") + (("stale",) if v2 else ()):
            a, b = [r[k] for r in s["LIFE"]], [r[k] for r in s["FRESH"]]
            lo, hi = boot_diff(a, b)
            lines.append(f"- LIFE-FRESH {k}: {mean(a) - mean(b):+.2f} (95% 부트스트랩 {lo:+.2f} ~ {hi:+.2f})")
    return "\n".join(lines)


def compare(exp_a: Path, exp_b: Path) -> str:
    """두 실험(예: agent-v2 대 v3)을 조건별로 비교한다."""
    sa, sb = summarize(load(exp_a)), summarize(load(exp_b))
    lines = [f"## {exp_a.name} 대 {exp_b.name}"]
    for cond in ("LIFE", "FRESH"):
        if not (sa.get(cond) and sb.get(cond)):
            continue
        for k in ("total_ok", "memory_ok", "halluc", "false_done", "ungrounded", "stale", "mem_key", "mem_stale",
                  "mem_noise", "mem_lines", "repeats", "end_refused"):
            a, b = [r[k] for r in sb[cond]], [r[k] for r in sa[cond]]
            lo, hi = boot_diff(a, b)
            lines.append(f"- {cond} {k}: {mean(b):.2f} -> {mean(a):.2f} ({mean(a) - mean(b):+.2f}, 95% {lo:+.2f} ~ {hi:+.2f})")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("exp")
    ap.add_argument("--md")
    ap.add_argument("--compare", help="비교할 다른 실험 폴더(앞이 기준)")
    a = ap.parse_args()
    if a.compare:
        text = compare(Path(a.exp), Path(a.compare))
    else:
        text = report(summarize(load(Path(a.exp))))
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n", encoding="utf-8")
