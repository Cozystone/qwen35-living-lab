"""트랙 L 실행기: 조건(LIFE/FRESH) 하나로 여러 날을 돌리고 날마다 채점한다.

사용: python run.py --root <조건 폴더> --cond LIFE|FRESH --days 1-3 [--world v1|v2] [--agent v2|v3] --llm http://127.0.0.1:8080 [--gateway http://host:8899]
결과: <root>/results.json (날마다 judge + score + 행동 통계), <root>/logs/day*.jsonl
같은 root 로 다시 실행하면 이어서(세계와 기억이 남은 상태로) 진행한다. 새로 시작하려면 빈 root 를 쓴다.
"""
import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "trackA"))
import agent  # noqa: E402
import grounded  # noqa: E402

WORLDS = {"v1": "world", "v2": "world_v2", "dev": "world_dev"}  # dev: life/trackA/world_dev.py(개발 전용)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--cond", choices=["LIFE", "FRESH"], required=True)
    ap.add_argument("--days", default="1-3")
    ap.add_argument("--llm", default="http://127.0.0.1:8080")
    ap.add_argument("--gateway", default=os.environ.get("WIKI_GATEWAY"))
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--stop-file", default="/srv/lab/STOP")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--agent", choices=["v2", "v3", "v4", "v5", "v4a"], default="v2")
    ap.add_argument("--world", choices=list(WORLDS), default="v1")
    ap.add_argument("--web-cache", help="위키백과 응답 캐시 파일(기본 <root>/web_cache.json). 여러 실행이 공유하면 빠르다")
    a = ap.parse_args()
    world = importlib.import_module(WORLDS[a.world])
    agent.set_version(a.agent)
    agent.SAMPLING = {"temperature": a.temperature, **({"seed": a.seed} if a.seed is not None else {})}
    if a.gateway:
        os.environ["WIKI_GATEWAY"] = a.gateway
    root = Path(a.root)
    root.mkdir(parents=True, exist_ok=True)
    lo, hi = (int(x) for x in a.days.split("-")) if "-" in a.days else (int(a.days), int(a.days))
    wiki = grounded.Wiki(Path(a.web_cache) if a.web_cache else root / "web_cache.json")
    res_path = root / "results.json"
    results = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {
        "protocol": world.PROTOCOL_VERSION, "agent": agent.AGENT_VERSION, "cond": a.cond,
        "sampling": agent.SAMPLING, "days": {}}

    def log(msg):
        print(msg, flush=True)

    for day in range(lo, hi + 1):
        world.setup_day(root / "home", day)
        t0 = time.time()
        try:
            stats = agent.run_day(root, day, world.DATES[day], a.cond, a.llm, wiki, a.max_steps,
                                  Path(a.stop_file), log)
        except OSError as e:
            if isinstance(getattr(e, "reason", None), ConnectionRefusedError):
                log(f"SERVER DOWN at day{day}: {e}")
                sys.exit(3)
            raise
        j = world.judge(root / "home", day)
        s = world.score(j)
        s["false_done"] = world.false_done(j, stats["done"])
        results["days"][str(day)] = {"judge": j, "score": s, "stats": stats, "wall_sec": round(time.time() - t0, 1)}
        res_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"[day{day} {a.cond}] score={s} stats={ {k: stats[k] for k in ('steps','errors','repeats','denied','lookups','remembers','ended')} }")
        if stats["stopped"]:
            break


if __name__ == "__main__":
    main()
