"""개발 전용 변형 세계 life-v1-dev (TRACK_A_DESIGN.md 3.4: 브리지·몸은 v1 이 아니라 여기서만 다듬는다).

world.py(life-v1) 와 과제·채점은 같고, 영수증 과제의 파일 이름·가게·개수·메모 위치만 다르다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import world as _w  # noqa: E402

PROTOCOL_VERSION = "life-v1-dev"
DATES = _w.DATES
MEMORY_TASKS = getattr(_w, "MEMORY_TASKS", [("2", "cat"), ("2", "report"), ("3", "report"), ("3", "gift")])

FILES = {
    1: {"inbox/files/m1.txt": "메모\n세탁소 화요일\n",
        "inbox/files/r7.txt": "영수증\n가게: 철물점\n품목: 못\n합계: 2,100원\n",
        "inbox/files/r2.txt": "영수증\n가게: 문구점\n품목: 연필\n합계: 900원\n",
        "inbox/files/m9.txt": "메모\n엄마 생신 선물\n"},
    2: {"inbox/files/x5.txt": "영수증\n가게: 꽃집\n품목: 장미\n합계: 12,000원\n",
        "inbox/files/x3.txt": "메모\n은행 들르기\n"},
}
RECEIPTS = {1: ["r2.txt", "r7.txt"], 2: ["x5.txt"]}
MEMOS = {1: ["m1.txt", "m9.txt"], 2: ["x3.txt"]}
DAYS = {d: {"tasks": _w.DAYS[d]["tasks"], "files": {**{k: v for k, v in _w.DAYS[d]["files"].items() if not k.startswith("inbox/files/")},
                                                  **FILES.get(d, {})}} for d in _w.DAYS}


def setup_day(home: Path, day: int) -> None:
    saved = _w.DAYS
    try:
        _w.DAYS = DAYS
        _w.setup_day(home, day)
    finally:
        _w.DAYS = saved


def judge(home: Path, day: int) -> dict:
    r = _w.judge(home, day)
    if day in RECEIPTS:
        r["receipts"] = {"ok": all((home / "receipts" / n).is_file() for n in RECEIPTS[day])
                         and all(not (home / "receipts" / n).exists() and (home / "inbox/files" / n).is_file() for n in MEMOS[day])}
    return r


task_ok, false_done, score = _w.task_ok, _w.false_done, _w.score
