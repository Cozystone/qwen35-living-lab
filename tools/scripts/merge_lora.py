"""Heretic LoRA 어댑터를 공식 BF16 원본 safetensors에 shard 단위로 병합한다.

원본의 모든 텐서(mtp.*, visual 포함)를 그대로 복사하고, LoRA 대상 가중치만
W' = W + (alpha/r) * B @ A 로 교체한다. 전체 모델을 RAM에 올리지 않는다.
MTP 텐서는 원본에서 그대로 복사되므로 이름/shape/dtype이 원본과 동일하게 보존된다.

사용: python merge_lora.py <original_dir> <adapter_dir> <out_dir>
"""
import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

orig = Path(sys.argv[1])
adapter = Path(sys.argv[2])
out = Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)

cfg = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
scaling = cfg["lora_alpha"] / cfg["r"]
lora = load_file(str(adapter / "adapter_model.safetensors"))

# PEFT 이름: base_model.model.<orig_prefix>.lora_A.weight -> <orig_prefix>.weight
pairs: dict[str, dict[str, torch.Tensor]] = {}
for k, v in lora.items():
    for part in ("lora_A", "lora_B"):
        tag = f".{part}."
        if tag in k:
            base = k.split(tag)[0]
            assert base.startswith("base_model.model."), k
            base = base[len("base_model.model."):] + ".weight"
            pairs.setdefault(base, {})[part] = v
assert all(len(p) == 2 for p in pairs.values())

index = json.loads((orig / "model.safetensors.index.json").read_text(encoding="utf-8"))
weight_map = index["weight_map"]
missing = [k for k in pairs if k not in weight_map]
if missing:
    sys.exit(f"LoRA 대상이 원본에 없음 (이름 매핑 실패): {missing[:5]}")
print(f"scaling={scaling} targets={len(pairs)}")

merged = 0
max_rel = 0.0
for shard in sorted(set(weight_map.values())):
    tensors = {}
    with safe_open(str(orig / shard), framework="pt") as f:
        meta = f.metadata()
        for name in f.keys():
            t = f.get_tensor(name)
            if name in pairs:
                A = pairs[name]["lora_A"].float()
                B = pairs[name]["lora_B"].float()
                W = t.float()
                assert (B.shape[0], A.shape[1]) == tuple(W.shape), (name, W.shape)
                delta = (B @ A) * scaling
                max_rel = max(max_rel, (delta.norm() / W.norm()).item())
                t = (W + delta).to(t.dtype)
                merged += 1
            tensors[name] = t.contiguous()
    save_file(tensors, str(out / shard), metadata=meta or {"format": "pt"})
    print(f"  {shard}: {len(tensors)} tensors")
    del tensors

assert merged == len(pairs), (merged, len(pairs))
for p in orig.iterdir():
    if p.is_file() and not p.name.endswith(".safetensors") and p.name not in (".gitattributes",):
        shutil.copy2(p, out / p.name)
print(f"merged={merged} max_relative_delta_norm={max_rel:.5f}")
