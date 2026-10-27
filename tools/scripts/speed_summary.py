"""eval/<label>.json 들의 평균 tok/s, 드래프트 수락률, 응답 일치(MTP 기준 비교용)를 출력한다.
사용: python speed_summary.py <label> [<label> ...]   (첫 label 을 응답 비교 기준으로 쓴다)"""
import json
import sys

base = None
for label in sys.argv[1:]:
    d = json.load(open(f"eval/{label}.json", encoding="utf-8"))["results"]
    tps = [r["tok_s"] for r in d if r["tok_s"]]
    dn = sum(r["draft_n"] or 0 for r in d)
    da = sum(r["draft_n_accepted"] or 0 for r in d)
    same = "" if base is None else f" same_as_{sys.argv[1]}={sum(a['response'] == b['response'] for a, b in zip(base, d))}/{len(d)}"
    base = base or d
    print(f"{label:22s} mean_tok_s={sum(tps)/len(tps):7.1f} draft_accept={da}/{dn}" + same)
