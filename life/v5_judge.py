"""agent-v5 판정: reports/V5_PREREG.md 의 기준을 그대로 계산한다.

사용: python life/v5_judge.py [--md reports/V5_RESULT_TABLES.md]
비교: runs/size-<world>-<model>(v4) 대 runs/size-<world>-<model>-v5(v5). 끝까지 돈 실행만 쓴다.
"""
import argparse
import collections
import json
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
MODELS = ["4b-orig", "9b-orig"]
NDAYS = {"v1": 3, "v2": 7}


def key_of(r: dict) -> str:
    # failure_taxonomy.key_of 와 같은 정의(막힌 시도·거절도 센다)
    return r["action"] + json.dumps(r.get("args", {}), ensure_ascii=False, sort_keys=True)


def run_metrics(d: Path, res: dict, world: str) -> dict:
    days = res["days"]
    loop = 0
    for f in (d / "logs").glob("day*.jsonl"):
        if "_plan" in f.name:
            continue
        keys = collections.Counter()
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["action"] != "(형식오류)":
                keys[key_of(r)] += 1
        loop += sum(n - 1 for n in keys.values() if n >= 3)
    rep_ok = sum(bool(days[k]["judge"]["report"]["ok"]) for k in days)
    memo = None
    if world == "v1":
        rc = d / "home" / "receipts"
        memo = sum(any(rc.rglob(n)) if rc.is_dir() else False for n in ("b.txt", "e.txt"))
    return {"ok": sum(days[k]["score"]["ok"] for k in days),
            "halluc": sum(days[k]["score"]["halluc"] for k in days),
            "false_done": sum(len(days[k]["score"].get("false_done", [])) for k in days),
            "loop": loop, "rep_ok": rep_ok, "rep_n": len(days), "memo": memo,
            "steps": sum(days[k]["stats"]["steps"] for k in days),
            "ended": sum(bool(days[k]["stats"].get("ended")) for k in days)}


def load(exp: str, world: str) -> dict:
    out = collections.defaultdict(list)
    for p in sorted((ROOT / "runs" / exp).glob("*/results.json")):
        res = json.loads(p.read_text(encoding="utf-8"))
        if len(res.get("days", {})) < NDAYS[world]:
            continue
        out[res["cond"]].append(run_metrics(p.parent, res, world))
    return out


def boot(a, b, n=10000, seed=0):
    """mean(b) - mean(a) 와 부트스트랩 95% 구간."""
    rnd = random.Random(seed)
    ds = sorted(st.mean(rnd.choices(b, k=len(b))) - st.mean(rnd.choices(a, k=len(a))) for _ in range(n))
    return st.mean(b) - st.mean(a), ds[int(0.025 * n)], ds[int(0.975 * n)]


def m(xs, k):
    return st.mean(x[k] for x in xs) if xs else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    a = ap.parse_args()
    L = ["# agent-v5 판정 표 (life/v5_judge.py 자동 생성)", ""]
    verdict = {}
    for model in MODELS:
        data = {(w, v): load(f"size-{w}-{model}" + ("-v5" if v == "v5" else ""), w) for w in ("v1", "v2") for v in ("v4", "v5")}
        L += [f"## {model}", "", "| 세계 | 에이전트 | 조건 | 실행 수 | 성공 | 할루시네이션 | 한 척 | 반복 고리 걸음 | 보고서 성공 | 하루 마감 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for (w, v), dd in data.items():
            for cond in ("LIFE", "FRESH"):
                xs = dd.get(cond, [])
                if not xs:
                    continue
                rep = sum(x["rep_ok"] for x in xs) / max(1, sum(x["rep_n"] for x in xs))
                end = sum(x["ended"] for x in xs) / max(1, len(xs) * NDAYS[w])
                L.append(f"| {w} | {v} | {cond} | {len(xs)} | {m(xs, 'ok'):.2f} | {m(xs, 'halluc'):.2f} | {m(xs, 'false_done'):.2f} "
                         f"| {m(xs, 'loop'):.1f} | {rep:.0%} | {end:.0%} |")
        L.append("")
        v4L, v5L = data[("v1", "v4")].get("LIFE", []), data[("v1", "v5")].get("LIFE", [])
        if not (v4L and v5L):
            L += ["(v1 LIFE 실행이 아직 없다)", ""]
            continue
        d, lo, hi = boot([x["ok"] for x in v4L], [x["ok"] for x in v5L])
        p1 = d >= 1.0 and lo > 0
        l4, l5 = m(v4L, "loop"), m(v5L, "loop")
        p2 = l5 <= 0.5 * l4
        rep5 = sum(x["rep_ok"] for x in v5L) / sum(x["rep_n"] for x in v5L)
        p3 = rep5 >= 0.9
        both4 = data[("v1", "v4")].get("LIFE", []) + data[("v1", "v4")].get("FRESH", []) + \
            data[("v2", "v4")].get("LIFE", []) + data[("v2", "v4")].get("FRESH", [])
        both5 = data[("v1", "v5")].get("LIFE", []) + data[("v1", "v5")].get("FRESH", []) + \
            data[("v2", "v5")].get("LIFE", []) + data[("v2", "v5")].get("FRESH", [])
        g1 = m(both5, "halluc") - m(both4, "halluc")
        g2 = m(both5, "false_done") - m(both4, "false_done")
        v5F = data[("v1", "v5")].get("FRESH", [])
        g3 = m(v5L, "ok") - m(v5F, "ok") if v5F else float("nan")
        v5all1 = v5L + v5F
        g4 = sum(x["memo"] for x in v5all1) / (2 * len(v5all1)) if v5all1 else float("nan")
        guards = {"G1": g1 < 0.25, "G2": g2 < 0.25, "G3": g3 > 0, "G4": g4 <= 0.10}
        L += [f"### 판정 ({model})", "",
              f"- P1 성공(v1 LIFE): v4 {m(v4L, 'ok'):.2f} -> v5 {m(v5L, 'ok'):.2f}, 차이 {d:+.2f} (95% {lo:+.2f} ~ {hi:+.2f}) -> {'통과' if p1 else '미달'}",
              f"- P2 반복 고리 걸음(v1 LIFE, 실행당): v4 {l4:.1f} -> v5 {l5:.1f} ({(l5 / l4 - 1) * 100 if l4 else 0:+.0f}%) -> {'통과' if p2 else '미달'}",
              f"- P3 보고서 성공률(v1 LIFE): {rep5:.0%} -> {'통과' if p3 else '미달'}",
              f"- G1 할루시네이션 증가(실행당, 두 세계 LIFE+FRESH): {g1:+.2f} -> {'지킴' if guards['G1'] else '넘음'}",
              f"- G2 한 척 증가(실행당): {g2:+.2f} -> {'지킴' if guards['G2'] else '넘음'}",
              f"- G3 기억 효과(v5 v1 LIFE-FRESH): {g3:+.2f} -> {'지킴' if guards['G3'] else '넘음'}",
              f"- G4 메모를 receipts/ 로 옮긴 비율(v5 v1): {g4:.0%} -> {'지킴' if guards['G4'] else '넘음'}"]
        v4L2, v5L2 = data[("v2", "v4")].get("LIFE", []), data[("v2", "v5")].get("LIFE", [])
        if v4L2 and v5L2:
            d2, lo2, hi2 = boot([x["ok"] for x in v4L2], [x["ok"] for x in v5L2])
            L += [f"- S1 (v2 LIFE 성공): v4 {m(v4L2, 'ok'):.2f} -> v5 {m(v5L2, 'ok'):.2f}, 차이 {d2:+.2f} (95% {lo2:+.2f} ~ {hi2:+.2f}) "
                  f"-> {'통과' if d2 >= 1.0 else '미달'}",
                  f"- S2 (v2 LIFE 반복 고리): v4 {m(v4L2, 'loop'):.1f} -> v5 {m(v5L2, 'loop'):.1f} "
                  f"-> {'통과' if m(v5L2, 'loop') <= 0.5 * m(v4L2, 'loop') else '미달'}"]
        ok_all = p1 and p2 and p3 and all(guards.values())
        verdict[model] = {"pass": ok_all, "p1": p1, "p2": p2, "p3": p3, "guards": all(guards.values())}
        L += [f"- **{model}: {'합격' if ok_all else '불합격'}**", ""]
    if len(verdict) == 2:
        nb = sum(v["pass"] for v in verdict.values())
        if nb == 2:
            final = "합격"
        elif nb == 1 or (all(v["p1"] and v["guards"] for v in verdict.values())):
            final = "부분 합격"
        else:
            final = "불합격"
        L += [f"## 종합 판정: **{final}**", ""]
    text = "\n".join(L)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
