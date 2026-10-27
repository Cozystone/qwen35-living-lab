"""safetensors 폴더의 텐서 목록(이름/shape/dtype)과 index 무결성을 기록한다.

사용: python inventory.py <model_dir> <out_json>
"""
import json
import sys
from pathlib import Path

from safetensors import safe_open

model_dir = Path(sys.argv[1])
out_path = Path(sys.argv[2])

index = json.loads((model_dir / "model.safetensors.index.json").read_text(encoding="utf-8"))
weight_map: dict[str, str] = index["weight_map"]
shards = sorted(set(weight_map.values()))

problems = []
tensors = {}
total_bytes = 0
for shard in shards:
    path = model_dir / shard
    if not path.exists():
        problems.append(f"missing shard: {shard}")
        continue
    total_bytes += path.stat().st_size
    with safe_open(str(path), framework="numpy") as f:
        for name in f.keys():
            sl = f.get_slice(name)
            tensors[name] = {"shard": shard, "shape": list(sl.get_shape()), "dtype": sl.get_dtype()}

for name, shard in weight_map.items():
    if name not in tensors:
        problems.append(f"in index but not in shards: {name}")
    elif tensors[name]["shard"] != shard:
        problems.append(f"index shard mismatch: {name}")
for name in tensors:
    if name not in weight_map:
        problems.append(f"in shards but not in index: {name}")

params = 0
for t in tensors.values():
    n = 1
    for d in t["shape"]:
        n *= d
    params += n

mtp = sorted(n for n in tensors if n.startswith("mtp.") or ".mtp." in n)
visual = [n for n in tensors if "visual" in n]
summary = {
    "model_dir": str(model_dir),
    "shard_count": len(shards),
    "shard_bytes": total_bytes,
    "tensor_count": len(tensors),
    "param_count": params,
    "mtp_tensor_count": len(mtp),
    "mtp_tensors": {n: tensors[n] for n in mtp},
    "visual_tensor_count": len(visual),
    "problems": problems,
    "tensors": tensors,
}
out_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"shards={len(shards)} bytes={total_bytes} tensors={len(tensors)} params={params:,}")
print(f"mtp={len(mtp)} visual={len(visual)} problems={len(problems)}")
for n in mtp:
    print(f"  {n} {tensors[n]['shape']} {tensors[n]['dtype']}")
for p in problems[:20]:
    print("  PROBLEM:", p)
sys.exit(1 if problems else 0)
