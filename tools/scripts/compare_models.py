"""원본과 병합본 safetensors 를 텐서 단위로 비교한다.

사용: python compare_models.py <original_dir> <merged_dir>
- 이름/shape/dtype 집합이 같아야 한다.
- MTP(mtp.*) 텐서는 바이트 단위로 동일해야 한다.
- 바뀐 텐서는 Heretic 대상(o_proj / linear_attn.out_proj, down_proj)뿐이어야 한다.
"""
import hashlib
import json
import sys
from pathlib import Path

from safetensors import safe_open

orig, merged = Path(sys.argv[1]), Path(sys.argv[2])


def load(d):
    wm = json.loads((d / "model.safetensors.index.json").read_text(encoding="utf-8"))["weight_map"]
    out = {}
    for shard in sorted(set(wm.values())):
        with safe_open(str(d / shard), framework="numpy") as f:
            for n in f.keys():
                s = f.get_slice(n)
                out[n] = (shard, tuple(s.get_shape()), s.get_dtype())
    return out


def digest(d, shard, name):
    # bf16 은 numpy 로 직접 못 읽으므로 원시 바이트를 해시한다.
    with open(d / shard, "rb") as fh:
        hlen = int.from_bytes(fh.read(8), "little")
        header = json.loads(fh.read(hlen))
        start, end = header[name]["data_offsets"]
        fh.seek(8 + hlen + start)
        return hashlib.sha256(fh.read(end - start)).hexdigest()


a, b = load(orig), load(merged)
problems = []
if set(a) != set(b):
    problems.append(f"name set differs: only_orig={sorted(set(a)-set(b))[:5]} only_merged={sorted(set(b)-set(a))[:5]}")
for n in set(a) & set(b):
    if a[n][1:] != b[n][1:]:
        problems.append(f"shape/dtype differs: {n} {a[n][1:]} vs {b[n][1:]}")

changed, mtp_same = [], 0
for n in sorted(set(a) & set(b)):
    same = digest(orig, a[n][0], n) == digest(merged, b[n][0], n)
    if n.startswith("mtp."):
        if same:
            mtp_same += 1
        else:
            problems.append(f"MTP tensor changed: {n}")
    if not same:
        changed.append(n)

# 선형 어텐션 층의 출력 투영은 o_proj 가 아니라 linear_attn.out_proj 다(Heretic 이 둘 다 attn.o_proj 로 다룸).
ALLOWED = ("o_proj.weight", "linear_attn.out_proj.weight", "down_proj.weight")
unexpected = [n for n in changed if not n.endswith(ALLOWED) or n.startswith("mtp.")]
problems += [f"unexpected change: {n}" for n in unexpected]
layers = sorted({int(n.split(".layers.")[1].split(".")[0]) for n in changed if ".layers." in n})
print(f"tensors={len(a)} changed={len(changed)} mtp_identical={mtp_same}/15 changed_layers={layers}")
for p in problems[:20]:
    print("PROBLEM:", p)
sys.exit(1 if problems else 0)
