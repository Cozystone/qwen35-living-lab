"""Track A 비교표(TRACK_A_DESIGN.md 3.2): ATANOR 실행과 트랙 L LLM 실행을 같은 지표로 놓는다.

사용: python life/trackA/compare.py [--md reports/TRACK_A_M1_TABLES.md]
1차 지표는 시도 가능 부분집합(v1 영수증 1·2일차, /2). 총점(/12)은 함께 내되 ATANOR 는 구조상 2 가 상한이다.
할루시네이션·근거 없는 쓰기는 ATANOR 에서 n/a(글을 쓰지 못함: 0 은 능력이 아니라 무능).
"""
import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import world  # noqa: E402
from collateral import displaced  # noqa: E402
from truth import ATTEMPTABLE  # noqa: E402

ROOT = HERE.parent.parent
TRUTH_DESTS = {rel: "receipts" for d in (1, 2) for rel, text in world.DAYS[d]["files"].items()
               if rel.startswith("inbox/files/") and text.split()[0] == "영수증"}
LLM = [("exp1", "LLM agent-v2 4B Heretic(4슬롯)"), ("exp2v3", "LLM agent-v3 4B Heretic(4슬롯)"),
       ("exp4v4w1", "LLM agent-v4 4B Heretic(4슬롯)"), ("size-v1-4b-orig", "LLM agent-v4 4B 원본"),
       ("size-v1-4b-orig-v5", "LLM agent-v5 4B 원본"), ("size-v1-9b-orig", "LLM agent-v4 9B 원본"),
       ("size-v1-9b-orig-v5", "LLM agent-v5 9B 원본")]


def ok_of(j, key):
    v = j.get(key)
    if isinstance(v, dict):
        return bool(v.get("ok")) if "ok" in v else (bool(v.get("exists") and v.get("name")) if key == "gift"
                                                     else all(x == "ok" for x in v.values()))
    return v == "ok"


def metrics(run_dir: Path, res: dict) -> dict:
    days = res["days"]
    att = sum(ok_of(days[d]["judge"], k) for d, k in ATTEMPTABLE["life-v1"])
    asks = 0
    for f in (run_dir / "logs").glob("day*.jsonl") if (run_dir / "logs").is_dir() else []:
        if "_plan" in f.name:
            continue
        asks += sum(json.loads(l)["action"] == "ask_user" for l in f.read_text(encoding="utf-8").splitlines())
    help_ = sum(sum(days[d]["stats"].get("help", {}).values()) for d in days) if "help" in days["1"]["stats"] else None
    return {"total": sum(days[d]["score"]["ok"] for d in days), "att": att,
            "r1": ok_of(days["1"]["judge"], "receipts"), "r2": ok_of(days["2"]["judge"], "receipts"),
            "false_done": sum(len(days[d]["score"].get("false_done", [])) for d in days),
            "displaced": len(res["displaced"]) if "displaced" in res else len(displaced(run_dir / "home", world, 3, TRUTH_DESTS)),
            "memo_moved": sum(not (run_dir / "home" / "inbox/files" / n).is_file() for n in ("b.txt", "e.txt")),
            "asks": asks, "help": help_,
            "help_d1": sum(days["1"]["stats"].get("help", {}).values()) if "help" in days["1"]["stats"] else None,
            "help_points": sum(days[d]["stats"].get("help", {}).get("point", 0) for d in days),
            "held": sum(days[d]["stats"].get("outcomes", {}).get("held", 0) for d in days),
            "wrong": sum(days[d]["stats"].get("outcomes", {}).get("wrong", 0) for d in days)}


def load(folder: Path, cond: str, pattern="*/results.json") -> list:
    out = []
    for p in sorted(folder.glob(pattern)):
        res = json.loads(p.read_text(encoding="utf-8"))
        if res.get("cond") != cond or len(res.get("days", {})) < 3 or res.get("protocol") != "life-v1":
            continue
        out.append(metrics(p.parent, res))
    return out


def boot(a, b, n=10000, seed=0):
    rnd = random.Random(seed)
    ds = sorted(st.mean(rnd.choices(b, k=len(b))) - st.mean(rnd.choices(a, k=len(a))) for _ in range(n))
    return st.mean(b) - st.mean(a), ds[int(0.025 * n)], ds[int(0.975 * n)]


def determinism(m1: Path) -> list:
    bad = []
    for r in sorted(m1.glob("*-s1r")):
        a = m1 / r.name[:-1]
        strip = lambda p: [{k: v for k, v in json.loads(l).items() if k != "seconds"} for l in p.read_text(encoding="utf-8").splitlines()]
        if strip(a / "days.jsonl") != strip(r / "days.jsonl"):
            bad.append(r.name)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    a = ap.parse_args()
    m1 = ROOT / "runs" / "A" / "m1"
    rows = []
    for t, label in (("absent", "ATANOR v24 T0 주인 부재"), ("d1", "ATANOR v24 T1 1일차만 진실 교사")):
        for c in ("LIFE", "FRESH"):
            xs = [metrics(p.parent, json.loads(p.read_text(encoding="utf-8")))
                  for p in sorted(m1.glob(f"{c}-{t}-s*/results.json")) if not p.parent.name.endswith("r")]
            rows.append((label, c, xs, True))
    for exp, label in LLM:
        for c in ("LIFE", "FRESH"):
            xs = load(ROOT / "runs" / exp, c)
            if xs:
                rows.append((label, c, xs, False))
    L = ["# 트랙 A M1 비교표 (life/trackA/compare.py 자동 생성)", "",
         f"결정성 게이트(시드 1 재실행, days.jsonl 비교): {'통과' if not determinism(m1) else '실패 ' + str(determinism(m1))}", "",
         "| 시스템 | 조건 | 실행 수 | **영수증 부분집합 /2** | 1일차 영수증 | 2일차 영수증 | 총점 /12 | 한 척 | 세계 파일 이탈 | 메모 이동 | 도움(ATANOR 교사 호출 / LLM ask_user) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    m = lambda xs, k: st.mean(x[k] for x in xs)
    for label, c, xs, is_a in rows:
        help_s = f"{m(xs, 'help'):.1f} (1일차 {m(xs, 'help_d1'):.1f}, point {m(xs, 'help_points'):.1f})" if is_a else f"ask_user {m(xs, 'asks'):.1f}"
        L.append(f"| {label} | {c} | {len(xs)} | **{m(xs, 'att'):.2f}** | {sum(x['r1'] for x in xs)}/{len(xs)} | "
                 f"{sum(x['r2'] for x in xs)}/{len(xs)} | {m(xs, 'total'):.2f} | {m(xs, 'false_done'):.2f} | "
                 f"{m(xs, 'displaced'):.2f} | {m(xs, 'memo_moved'):.2f} | {help_s} |")
    L += ["", "## 차이 (영수증 부분집합, 부트스트랩 95%)", ""]
    get = {(lab, c): xs for lab, c, xs, _ in rows}
    pairs = [(("LLM agent-v4 4B 원본", "LIFE"), ("ATANOR v24 T0 주인 부재", "LIFE"), "T0 대 T0 (정직한 맞대기)"),
             (("LLM agent-v4 4B 원본", "LIFE"), ("ATANOR v24 T1 1일차만 진실 교사", "LIFE"), "참고: 교사 있는 ATANOR 대 교사 없는 LLM"),
             (("LLM agent-v4 9B 원본", "LIFE"), ("ATANOR v24 T1 1일차만 진실 교사", "LIFE"), "참고: 9B 와"),
             (("ATANOR v24 T1 1일차만 진실 교사", "FRESH"), ("ATANOR v24 T1 1일차만 진실 교사", "LIFE"), "ATANOR 기억 효과(LIFE-FRESH)")]
    for base, other, name in pairs:
        if base in get and other in get:
            d, lo, hi = boot([x["att"] for x in get[base]], [x["att"] for x in get[other]])
            L.append(f"- {name}: {other[0]} {other[1]} − {base[0]} {base[1]} = {d:+.2f} (95% {lo:+.2f} ~ {hi:+.2f})")
    text = "\n".join(L)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
