"""protocol_A1.json 동결(TRACK_A_DESIGN.md 3.4). 실행 전에 한 번 쓰고, 실행 뒤 check 로 바뀌지 않았는지 확인한다."""
import hashlib, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ATANOR = Path(r"D:\ATANOR-experiments\2026-10-27\trackA")

def tree_sha(folder):
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(folder).as_posix().encode()); h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()

def sha(p):
    return hashlib.sha256(Path(p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()

def record():
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ATANOR, capture_output=True, text=True).stdout.strip()
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=ATANOR, capture_output=True).stdout
    return {
        "name": "track-A M1", "frozen_before_run": True,
        "worlds": {n: sha(HERE.parent / f"{n}.py") for n in ("world", "world_v2")} | {"world_dev": sha(HERE / "world_dev.py")},
        "atanor": {"worktree": str(ATANOR), "branch": "trackA", "base_commit": base,
                   "uncommitted_diff_sha256": hashlib.sha256(diff.replace(b"\r\n", b"\n")).hexdigest(),
                   "new_files": {"world/home_world.py": sha(ATANOR / "atanor_os/world/home_world.py"),
                                 "tests/test_home_world.py": sha(ATANOR / "atanor_os/tests/test_home_world.py")},
                   **{f"src_{d}": tree_sha(ATANOR / "atanor_os" / d) for d in ("agent", "core", "world", "teach")}},
        "bridge": {f: sha(HERE / f) for f in ("bridge.py", "teacher.py", "truth.py", "collateral.py", "run_a.py")},
        "run": {"world": "v1", "lang": "ko", "conds": ["LIFE", "FRESH"], "teachers": ["absent", "d1"], "seeds": list(range(1, 12)),
                "owner_days": {"life-v1": [1]}, "determinism_gate": "seed 1 twice per condition, days.jsonl identical without seconds",
                "gates": ["atanor pytest -m 'not learning and not timing' (125 passed, 1 xfailed)", "life/trackA/test_trackA.py 5 passed",
                          "hand_solve receipts v1/v2/dev = judge ok"]},
        "predictions": "reports/TRACK_A_DESIGN.md 2.5 (written before any run)",
    }

if __name__ == "__main__":
    out = HERE / "protocol_A1.json"
    if sys.argv[1:] == ["check"]:
        old, new = json.loads(out.read_text(encoding="utf-8")), record()
        diffs = [k for k in ("worlds", "atanor", "bridge") if old[k] != new[k]]
        print("UNCHANGED" if not diffs else f"CHANGED: {diffs}"); sys.exit(1 if diffs else 0)
    out.write_text(json.dumps(record(), ensure_ascii=False, indent=1), encoding="utf-8"); print(out.read_text(encoding="utf-8")[:1500])
