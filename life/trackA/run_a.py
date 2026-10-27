"""Track A 실행기: ATANOR 를 트랙 L 세계에서 여러 날 돌리고 날마다 채점한다(run.py 와 같은 모양).

사용: python life/trackA/run_a.py --root <폴더> --world v1|v2|dev --cond LIFE|FRESH --teacher absent|d1|all --seed N [--days 1-3]
결과: <root>/results.json (트랙 L 스키마; life/analyze.py 가 그대로 읽는다), days.jsonl, resumed.jsonl, snap/d*/
"""
import argparse
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import bridge  # noqa: E402
from collateral import displaced  # noqa: E402
from truth import TASK_TRUTH  # noqa: E402

WORLDS = {"v1": "world", "v2": "world_v2", "dev": "world_dev"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--world", choices=list(WORLDS), default="v1")
    ap.add_argument("--cond", choices=["LIFE", "FRESH"], required=True)
    ap.add_argument("--teacher", choices=["absent", "d1", "all"], required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--days")
    a = ap.parse_args()
    world = importlib.import_module(WORLDS[a.world])
    root = Path(a.root)
    if root.exists():
        raise SystemExit(f"root 가 이미 있다(빈 root 에서만 시작): {root}")
    root.mkdir(parents=True)
    days = sorted(world.DATES)
    if a.days:
        lo, hi = (int(x) for x in a.days.split("-"))
        days = [d for d in days if lo <= d <= hi]
    res = {"protocol": world.PROTOCOL_VERSION, "agent": bridge.AGENT, "cond": a.cond, "teacher": a.teacher,
           "sampling": {"seed": a.seed}, "days": {}}
    truth_dests = {}
    for d in days:
        out = bridge.run_day(root, world, d, a.cond, a.teacher, a.seed)
        res["days"][str(d)] = out
        (root / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"[day{d} {a.cond} {a.teacher} s{a.seed}] score={out['score']} help={out['stats']['help']} "
              f"outcomes={out['stats']['outcomes']} resumed={out['stats']['resumed_ok']}/{out['stats']['resumed']}", flush=True)
    for d in days:  # 옮기라고 한 파일의 허용 목적지(부수 피해 예외; 세계가 넣은 내용으로 계산, 채점과 무관)
        spec = world.DAYS[d]
        if (world.PROTOCOL_VERSION, d, "receipts") in TASK_TRUTH:
            truth_dests.update({rel: "receipts" for rel, text in spec["files"].items()
                                if rel.startswith("inbox/files/") and text.split()[0] == "영수증"})
    res["displaced"] = displaced(root / "home", world, days[-1], truth_dests)
    (root / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"displaced={res['displaced']}")


if __name__ == "__main__":
    main()
