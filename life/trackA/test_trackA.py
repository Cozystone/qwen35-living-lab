"""Track A 평가기 쪽 시험(TRACK_A_DESIGN.md 4.3). 실행: miniconda python -m pytest -q life/trackA/test_trackA.py"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import world  # noqa: E402
import world_v2  # noqa: E402
import world_dev  # noqa: E402
from collateral import displaced  # noqa: E402
from teacher import TrackATeacher  # noqa: E402
from truth import TASK_TRUTH, hand_solve  # noqa: E402

PY = sys.executable


def _setup(tmp_path, w, upto):
    home = tmp_path / "home"
    for d in range(1, upto + 1):
        w.setup_day(home, d)
    return home


def test_hand_gate_solves_receipts(tmp_path):
    for w in (world, world_v2, world_dev):
        home = tmp_path / w.PROTOCOL_VERSION / "home"
        for d in (1, 2):
            w.setup_day(home, d)
            hand_solve(home, TASK_TRUTH[(w.PROTOCOL_VERSION, d, "receipts")](home))
            assert w.task_ok(w.judge(home, d), "receipts") is True, (w.PROTOCOL_VERSION, d)


def test_teacher_check_confirm_match_judge(tmp_path):
    home = _setup(tmp_path, world, 1)
    t = TrackATeacher(home, world)
    t.begin(1, "receipts", TASK_TRUTH[("life-v1", 1, "receipts")])
    assert t.truth == ["inbox/files/a.txt", "inbox/files/c.txt"] and t.dest == "receipts"
    change = [["o", "kind", "absent"], ["D/o", "kind", "file"]]
    assert t.check({"change": change, "objects": t.truth, "dest": "receipts"}) is True
    assert t.check({"change": change, "objects": t.truth + ["inbox/files/b.txt"], "dest": "receipts"}) is False
    assert t.still_wanted("x") is True and t.confirm("x") is False
    hand_solve(home, {"tool": "move", "objects": t.truth, "dest": "receipts"})
    assert t.confirm("x") is world.task_ok(world.judge(home, 1), "receipts") is True
    t.begin(1, "capitals", None)
    assert t.point("x") == {"objects": [], "dest": None} and t.demonstrate("x", "a", None) == []


def _run(root, *args):
    return subprocess.run([PY, str(HERE / "run_a.py"), "--root", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", env={"PYTHONIOENCODING": "utf-8", "SYSTEMROOT": "C:\\Windows"}, timeout=900)


def test_schema_fresh_and_determinism(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for r in (a, b):
        p = _run(r, "--world", "dev", "--cond", "FRESH", "--teacher", "d1", "--seed", "3")
        assert p.returncode == 0, p.stderr[-2000:]
    res = json.loads((a / "results.json").read_text(encoding="utf-8"))
    assert set(res["days"]) == {"1", "2", "3"} and {"judge", "score", "stats", "wall_sec"} <= set(res["days"]["1"])
    assert "false_done" in res["days"]["1"]["score"] and isinstance(res["displaced"], list)
    assert (a / "mind_archive" / "before_day2").is_dir() and (a / "home" / "receipts").exists() is not None
    strip = lambda p: [{k: v for k, v in json.loads(l).items() if k != "seconds"} for l in p.read_text(encoding="utf-8").splitlines()]
    assert strip(a / "days.jsonl") == strip(b / "days.jsonl")
    import analyze  # 트랙 L 집계기가 수정 없이 읽는다
    runs = {"FRESH": [("x", {**res, "_dir": a})]}
    s = analyze.summarize(runs)
    assert s["FRESH"][0]["total"] == sum(res["days"][k]["score"]["total"] for k in res["days"])


def test_mind_never_imports_truth_or_world():
    code = ("import sys; sys.path.insert(0, r'D:\\ATANOR-experiments\\2026-10-27\\trackA');"
            "import atanor_os.agent.life, atanor_os.world.home_world;"
            "bad=[m for m in sys.modules if m in ('truth','teacher','world','world_v2','world_dev','bridge') or m.startswith('atanor_os.eval') or m.startswith('atanor_os.teach')];"
            "print(bad); assert not bad")
    p = subprocess.run([PY, "-c", code], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


def test_displaced_counts_memo_moves(tmp_path):
    home = _setup(tmp_path, world, 2)
    dests = {"inbox/files/a.txt": "receipts", "inbox/files/c.txt": "receipts"}
    assert displaced(home, world, 2, dests) == []
    hand_solve(home, {"tool": "move", "objects": ["inbox/files/a.txt", "inbox/files/b.txt"], "dest": "receipts"})
    assert displaced(home, world, 2, dests) == ["inbox/files/b.txt"]
