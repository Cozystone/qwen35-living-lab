"""날마다 facts/capitals.md 를 기록(write/append)으로 다시 만들어, 현재 채점 기준으로 사실 판정을 다시 센다.

사용: python recount_facts.py <exp_dir>
결과 판정은 날이 끝난 시점 기준(judge 와 같음). 채점 기준(world.CAPITALS)을 고친 뒤 과거 실행을 다시 셀 때 쓴다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world  # noqa: E402

COUNTRIES = {1: ("캐나다", "호주", "튀르키예"), 2: ("뉴질랜드",), 3: ()}


def replay(logs: Path):
    caps = ""
    for day in (1, 2, 3):
        for line in (logs / f"day{day}.jsonl").read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            path = str(d.get("args", {}).get("path", "")).replace("\\", "/")
            if path == "facts/capitals.md" and d["action"] in ("write", "append") and "완료" in d["result"]:
                t = str(d["args"].get("text", ""))
                t = t if t.endswith("\n") else t + "\n"
                caps = t if d["action"] == "write" else caps + t
        yield day, caps


if __name__ == "__main__":
    tally = {}
    for logs in sorted(Path(sys.argv[1]).glob("*/logs")):
        run = logs.parent.name
        cond = run.split("-")[0]
        for day, caps in replay(logs):
            for c in COUNTRIES[day]:
                s = world._capital_status(caps, c)
                tally[(cond, s)] = tally.get((cond, s), 0) + 1
                if s == "halluc":
                    print(run, f"day{day}", c, "|", (world._capital_line(caps, c) or "")[:70])
    print({f"{k[0]}:{k[1]}": v for k, v in sorted(tally.items())})
