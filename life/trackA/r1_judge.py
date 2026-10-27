"""R1 판정(reports/R1_PREREG.md): agent-v4a(ATANOR 손) 대 agent-v4, 4B 원본, 세계 v1.

사용: python life/trackA/r1_judge.py [--md reports/R1_RESULT_TABLES.md]
"""
import argparse
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from compare import ROOT, boot, load  # noqa: E402

EXPS = [("size-v1-4b-orig", "4B agent-v4"), ("size-v1-4b-orig-r1", "4B agent-v4a (ATANOR 손)"),
        ("size-v1-9b-orig", "9B agent-v4"), ("size-v1-9b-orig-r1", "9B agent-v4a (ATANOR 손, 보조)")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    a = ap.parse_args()
    data = {(e, c): load(ROOT / "runs" / e, c) for e, _ in EXPS for c in ("LIFE", "FRESH")}
    m = lambda xs, k: st.mean(x[k] for x in xs) if xs else float("nan")
    L = ["# R1 ATANOR 손 판정 표 (life/trackA/r1_judge.py 자동 생성)", "",
         "| 시스템 | 조건 | 실행 수 | 영수증 부분집합 /2 | 1일차 | 2일차 | 총점 /12 | 한 척 | 세계 파일 이탈 | 메모 이동 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for e, label in EXPS:
        for c in ("LIFE", "FRESH"):
            xs = data[(e, c)]
            if xs:
                L.append(f"| {label} | {c} | {len(xs)} | {m(xs, 'att'):.2f} | {sum(x['r1'] for x in xs)}/{len(xs)} | "
                         f"{sum(x['r2'] for x in xs)}/{len(xs)} | {m(xs, 'total'):.2f} | {m(xs, 'false_done'):.2f} | "
                         f"{m(xs, 'displaced'):.2f} | {m(xs, 'memo_moved'):.2f} |")
    b, r = data[("size-v1-4b-orig", "LIFE")], data[("size-v1-4b-orig-r1", "LIFE")]
    if b and r:
        d, lo, hi = boot([x["att"] for x in b], [x["att"] for x in r])
        h1 = d >= 0.25 and lo > 0
        bb = b + data[("size-v1-4b-orig", "FRESH")]
        rr = r + data[("size-v1-4b-orig-r1", "FRESH")]
        h2 = m(rr, "displaced") <= 0.5 * m(bb, "displaced")
        g1 = m(r, "total") > m(b, "total") - 1.0
        g2 = m(rr, "false_done") - m(bb, "false_done") < 0.25
        dt, lot, hit = boot([x["total"] for x in b], [x["total"] for x in r])
        verdict = "합격" if h1 and h2 and g1 and g2 else ("부분" if h2 and g1 and g2 else "불합격")
        L += ["", "## 판정 (4B)", "",
              f"- H1 영수증 부분집합(LIFE): {m(b, 'att'):.2f} -> {m(r, 'att'):.2f}, 차이 {d:+.2f} (95% {lo:+.2f} ~ {hi:+.2f}) -> {'통과' if h1 else '미달'}",
              f"- H2 세계 파일 이탈(LIFE+FRESH, 실행당): {m(bb, 'displaced'):.2f} -> {m(rr, 'displaced'):.2f} -> {'통과' if h2 else '미달'}",
              f"- G1 총점(LIFE): {m(b, 'total'):.2f} -> {m(r, 'total'):.2f} (차이 {dt:+.2f}, 95% {lot:+.2f} ~ {hit:+.2f}) -> {'지킴' if g1 else '넘음'}",
              f"- G2 한 척(LIFE+FRESH): {m(bb, 'false_done'):.2f} -> {m(rr, 'false_done'):.2f} -> {'지킴' if g2 else '넘음'}",
              f"- 참고: 메모 이동(LIFE+FRESH) {m(bb, 'memo_moved'):.2f} -> {m(rr, 'memo_moved'):.2f}",
              f"- **판정: {verdict}**"]
    text = "\n".join(L)
    print(text)
    if a.md:
        Path(a.md).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
