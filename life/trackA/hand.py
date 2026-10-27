"""R1 'ATANOR 손'(TRACK_A_DESIGN.md 3.6): LLM 이 정한 의도 {objects, dest} 를 ATANOR Mind 의 실행부가 계획·실행·검증한다.

말 해석은 하지 않는다(그건 LLM 몫). 브리지가 의도를 ATANOR 의 Goal(목표 리터럴)로 바꾸고 Mind._achieve 에 넘긴다.
- 목표: 대상 o 마다 o 는 없어지고, D/name(o) 는 o 와 같은 내용의 파일. 대상이 아닌 집의 파일은 지킬 것(keep, 바뀌면 안 됨).
- ATANOR 는 도구의 전제조건·효과를 자기 경험(episodes)에서 배운다. 처음이면 실험실 사본에서 실험한다. 기억은 mind_dir 에 남는다.
- 주의: Mind._achieve 는 v24 의 공개 인터페이스가 아니다(설계 문서 5절 위험 8). 코어는 동결이라 동작은 안정적이다.
"""
import sys
from pathlib import Path

ATANOR = Path(r"D:\ATANOR-experiments\2026-10-27\trackA")
if str(ATANOR) not in sys.path:
    sys.path.insert(0, str(ATANOR))
from atanor_os.agent.life import BUDGET, Mind  # noqa: E402
from atanor_os.core.types import Goal, Literal  # noqa: E402
from atanor_os.world.home_world import HomeWorkspace  # noqa: E402


def organize(home: Path, mind_dir: Path, lab: Path, objects: list, dest: str, task_id: str, seed: int = 0) -> dict:
    ws = HomeWorkspace(home, create=False)
    dest = str(dest).strip().strip("/").replace("\\", "/")
    objs = []
    for o in objects:
        o = str(o).strip().lstrip("./").replace("\\", "/")
        try:
            if ws.kind(o) == "file":
                objs.append(o)
        except ValueError:
            pass
    if not objs or not dest:
        return {"ok": False, "why": "옮길 파일이 없거나 목적지가 없다", "moved": [], "counts": {}}
    try:
        ws.path(dest)
    except ValueError as e:
        return {"ok": False, "why": f"목적지 경로 오류: {e}", "moved": [], "counts": {}}
    mind = Mind(ws, mind_dir, lab, user=None, seed=seed)
    st = ws.observe(objs + [dest])
    must, universe = [], set(objs) | {dest}
    for o in objs:
        d_o = f"{dest}/{o.rsplit('/', 1)[-1]}"
        if ws.kind(d_o) != "absent":
            return {"ok": False, "why": f"목적지에 같은 이름이 이미 있다: {d_o}", "moved": [], "counts": {}}
        must += [Literal("kind", (o,), "absent"), Literal("kind", (d_o,), "file"), Literal("hash", (d_o,), st[o]["hash"])]
        universe.add(d_o)
    everything = ws.observe(ws.existing())
    keep = [Literal("hash", (p,), a["hash"]) for p, a in everything.items() if a["kind"] == "file" and p not in objs]
    g = Goal("hand:" + task_id, must, keep, {}, dict(BUDGET), sorted(universe))
    g.selected, g.dest = list(objs), dest
    mind.task_id = task_id
    done = mind._achieve(g, task_id)
    mind.save()
    after = ws.observe(sorted(universe))
    moved = [o for o in objs if after[o]["kind"] == "absent" and after[f"{dest}/{o.rsplit('/', 1)[-1]}"]["hash"] == st[o]["hash"]]
    return {"ok": bool(done), "moved": moved, "not_moved": [o for o in objs if o not in moved], "counts": dict(mind.counts)}
