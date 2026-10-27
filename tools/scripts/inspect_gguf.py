"""GGUF 메타데이터와 텐서를 검증한다.

사용: python inspect_gguf.py <file.gguf> [expected_block_count]
MTP(nextn) 텐서 이름/shape/type, block_count, nextn_predict_layers, file_type,
파라미터 수, tokenizer/chat template 존재를 출력하고 기대값과 다르면 exit 1.
"""
import sys

from gguf import GGUFReader
from gguf.constants import GGMLQuantizationType, LlamaFileType

path = sys.argv[1]
expected_blocks = int(sys.argv[2]) if len(sys.argv) > 2 else None
r = GGUFReader(path)


def field(name):
    f = r.fields.get(name)
    if f is None:
        return None
    v = f.parts[f.data[0]]
    if f.types and f.types[0].name == "STRING":
        return bytes(v).decode("utf-8", "replace")
    return v.tolist()[0] if hasattr(v, "tolist") else v


arch = field("general.architecture")
ftype = field("general.file_type")
blocks = field(f"{arch}.block_count")
nextn = field(f"{arch}.nextn_predict_layers")
tmpl = field("tokenizer.chat_template")
tok_model = field("tokenizer.ggml.model")
n_vocab = len(r.fields["tokenizer.ggml.tokens"].data) if "tokenizer.ggml.tokens" in r.fields else 0

params = sum(int(t.n_elements) for t in r.tensors)
types: dict[str, int] = {}
for t in r.tensors:
    types[t.tensor_type.name] = types.get(t.tensor_type.name, 0) + 1

mtp_block = blocks - nextn if blocks and nextn else None
mtp = [t for t in r.tensors if mtp_block is not None and t.name.startswith(f"blk.{mtp_block}.")]

print(f"file: {path}")
print(f"general.architecture = {arch}")
print(f"general.file_type = {ftype} ({LlamaFileType(ftype).name if ftype is not None else '-'})")
print(f"{arch}.block_count = {blocks}")
print(f"{arch}.nextn_predict_layers = {nextn}")
print(f"tensors total = {len(r.tensors)}   params = {params:,}")
print(f"tensor types = {types}")
print(f"tokenizer.ggml.model = {tok_model}  vocab = {n_vocab}")
print(f"chat_template = {'present, %d chars' % len(tmpl) if tmpl else 'MISSING'}")
print(f"MTP tensors (blk.{mtp_block}.*) = {len(mtp)}")
for t in mtp:
    print(f"  {t.name:45s} {list(map(int, t.shape))} {t.tensor_type.name}")

problems = []
if expected_blocks is not None and blocks != expected_blocks:
    problems.append(f"block_count {blocks} != {expected_blocks}")
if nextn != 1:
    problems.append(f"nextn_predict_layers {nextn} != 1")
if not mtp:
    problems.append("no MTP tensors")
if not any(".nextn." in t.name for t in mtp):
    problems.append("no nextn.* tensors in MTP block")
if not tmpl:
    problems.append("chat template missing")
for p in problems:
    print("PROBLEM:", p)
sys.exit(1 if problems else 0)
