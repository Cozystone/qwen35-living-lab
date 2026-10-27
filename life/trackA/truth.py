"""Track A 진실 명세(평가기 쪽). ATANOR 의 Mind 는 이 모듈을 볼 수 없고, 교사 객체만 닿는다(TRACK_A_DESIGN.md 2.1 (c)).

TASK_TRUTH[(protocol, day, tid)] = fn(home: Path) -> {"tool", "objects", "dest"}
- 영수증 과제: inbox/files/ 바로 아래에서 첫 줄 첫 낱말이 '영수증'인 파일, move, 목적지 receipts.
  (대상은 그날 과제를 시작할 때의 내용으로 계산한다.)
ATTEMPTABLE: ATANOR(home 몸)가 원리상 시도할 수 있는 채점 항목(보고용. 실행 경로에는 넣지 않는다).
hand_solve: 진실 명세를 그대로 실행하는 손 해결사(HAND/ORACLE 게이트).
"""
from pathlib import Path


def head(p: Path) -> str:
    lines = p.read_bytes()[:256].decode("utf-8", errors="replace").splitlines()
    tok = lines[0].split() if lines else []
    return tok[0] if tok else "-"


def receipts(home: Path) -> dict:
    d = home / "inbox" / "files"
    objs = sorted(f"inbox/files/{p.name}" for p in d.iterdir() if p.is_file() and head(p) == "영수증") if d.is_dir() else []
    return {"tool": "move", "objects": objs, "dest": "receipts"}


TASK_TRUTH = {
    ("life-v1", 1, "receipts"): receipts, ("life-v1", 2, "receipts"): receipts,
    ("life-v1-dev", 1, "receipts"): receipts, ("life-v1-dev", 2, "receipts"): receipts,
    ("life-v2", 1, "receipts"): receipts, ("life-v2", 2, "receipts"): receipts,
}

# 채점 항목 단위: (day, judge 키)
ATTEMPTABLE = {
    "life-v1": [("1", "receipts"), ("2", "receipts")],
    "life-v1-dev": [("1", "receipts"), ("2", "receipts")],
    "life-v2": [("1", "receipts"), ("2", "receipts")],
}

# 주인이 메모를 남긴 날(T1-d1 에서 교사가 있는 날)
OWNER_DAYS = {"life-v1": {1}, "life-v1-dev": {1}, "life-v2": {1, 3, 5}}


def hand_solve(home: Path, truth: dict) -> None:
    d = home / truth["dest"]
    d.mkdir(exist_ok=True)
    for o in truth["objects"]:
        src = home / o
        dst = d / src.name
        if not dst.exists():
            src.rename(dst)
