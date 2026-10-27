"""Track A 진실 교사(TRACK_A_DESIGN.md 2.3). ATANOR life_teacher.Teacher 의 질문 형식을 그대로 받되,
깊은 경로(inbox/files/a.txt)와 트랙 L 채점기를 쓰도록 새로 썼다.

- confirm 은 world.task_ok(world.judge(home, day), tid) 와 같은 함수다. 확인과 채점이 갈라질 수 없다.
- 진실 명세가 없는 과제(수도, 보고서 등)는 point -> 대상 없음, demonstrate -> 단계 없음.
- explain 은 한국어(KO) 모드에서 답이 없다(None). 직역(EN) 모드는 M1b.
"""
from collections import Counter
from pathlib import Path


def name_of(p: str) -> str:
    return p.rsplit("/", 1)[-1]


class TrackATeacher:
    def __init__(self, home: Path, world):
        self.home, self.world = Path(home), world
        self.help = Counter()
        self.day, self.tid, self.truth, self.dest = None, None, [], None

    def begin(self, day: int, tid: str, truth_fn=None):
        self.day, self.tid = day, tid
        t = truth_fn(self.home) if truth_fn else None
        self.truth = sorted(t["objects"]) if t else []
        self.dest = t["dest"] if t else None
        self.tool = t["tool"] if t else None

    def _ok(self) -> bool:
        return self.world.task_ok(self.world.judge(self.home, self.day), self.tid) is True

    def explain(self, word):
        self.help["explain"] += 1
        return None

    def point(self, command):
        self.help["point"] += 1
        return {"objects": list(self.truth), "dest": self.dest}

    def _steps(self, objs):
        if not self.tool:
            return []
        return [("mkdir", (self.dest,))] + [(self.tool, (o, f"{self.dest}/{name_of(o)}")) for o in objs]

    def demonstrate(self, command, o, dest):
        self.help["demonstrate"] += 1
        return self._steps([o]) if o in self.truth else []

    def demonstrate_goal(self, goal):
        self.help["demonstrate_goal"] += 1
        return self._steps(self.truth)

    def check(self, proposal):
        """ATANOR Teacher.check 와 같은 판정(바뀌는 kind 로 도구를 읽음), 경로만 D/name(o)."""
        self.help["check"] += 1
        ch = {(it[0], it[1], it[2]) for it in proposal["change"] if len(it) == 3}
        gone = ("o", "kind", "absent") in ch
        arrives = any(r == "D/o" and k == "kind" for r, k, _ in ch)
        tool = "move" if gone and arrives else "copy" if arrives else "delete" if gone else None
        return bool(self.tool) and tool == self.tool and sorted(proposal["objects"]) == self.truth \
            and (proposal["dest"] or None) == self.dest

    def confirm(self, command):
        self.help["confirm"] += 1
        return self._ok()

    def still_wanted(self, command):
        self.help["recall"] += 1
        return not self._ok()
