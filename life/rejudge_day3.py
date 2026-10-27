"""3일차(마지막 날) 판정을 최종 home 상태로 다시 매긴다. 채점기(world.judge)를 고친 뒤 과거 실행에 적용.

사용: python rejudge_day3.py <exp_dir> ...   (results.json 의 days['3'] judge/score 를 갱신, 이전 값은 judge_old 로 보존)
1·2일차는 이후 날의 변경 때문에 최종 상태로 다시 매길 수 없다(그쪽은 recount_facts.py 로 기록 재생).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world  # noqa: E402

for exp in sys.argv[1:]:
    for res in sorted(Path(exp).glob("*/results.json")):
        d = json.loads(res.read_text(encoding="utf-8"))
        day = d["days"].get("3")
        if not day:
            continue
        j = world.judge(res.parent / "home", 3)
        s = world.score(j)
        s["false_done"] = world.false_done(j, day["stats"]["done"])
        if day["judge"] != j:
            day.setdefault("judge_old", day["judge"])
            print(f"{res.parent.name}: fiction {day['judge'].get('fiction')} -> {j['fiction']}, "
                  f"gift invented {j['gift'].get('invented_name')}, halluc {day['score']['halluc']} -> {s['halluc']}")
        day["judge"], day["score"] = j, s
        res.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
