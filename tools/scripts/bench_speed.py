"""llama-server 생성 속도만 짧게 잰다(노트북 MTP on/off 비교용). thinking off, temperature 0.

사용: python bench_speed.py <base_url> <label> <out_json>
프롬프트 4개(한/영/코드/JSON) x max_tokens 256. 첫 요청 전에 워밍업 1회.
"""
import json
import sys
import urllib.request

base, label, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

PROMPTS = [
    ("ko", "광합성이 무엇인지 중학생이 이해할 수 있게 다섯 문장으로 설명해줘."),
    ("en", "Explain the difference between TCP and UDP in exactly four bullet points."),
    ("code", "Write a Python function `is_prime(n: int) -> bool` with a docstring and three doctest examples. Output only one code block."),
    ("json", 'Return ONLY a JSON object with keys "city", "population", "landmarks" (array of 3 strings) for Paris.'),
]


def chat(prompt: str, max_tokens: int) -> dict:
    body = {
        "model": "x",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())


chat("Hi", 8)
rows = []
for pid, prompt in PROMPTS:
    t = chat(prompt, 256).get("timings", {})
    rows.append({"id": pid, "gen_tok_s": t.get("predicted_per_second"), "gen_n": t.get("predicted_n"),
                 "prompt_tok_s": t.get("prompt_per_second"),
                 "draft_n": t.get("draft_n"), "draft_n_accepted": t.get("draft_n_accepted")})
    print(f"[{label}] {pid:5s} gen={rows[-1]['gen_tok_s']:.2f} tok/s n={rows[-1]['gen_n']} "
          f"draft={rows[-1]['draft_n_accepted']}/{rows[-1]['draft_n']}")

gen_n = sum(r["gen_n"] for r in rows)
gen_s = sum(r["gen_n"] / r["gen_tok_s"] for r in rows)
dn = sum(r["draft_n"] or 0 for r in rows)
da = sum(r["draft_n_accepted"] or 0 for r in rows)
summary = {"label": label, "gen_tok_s": round(gen_n / gen_s, 2), "gen_tokens": gen_n,
           "draft_accept_rate": round(da / dn, 3) if dn else None}
json.dump({"summary": summary, "rows": rows}, open(out_path, "w", encoding="utf-8"), indent=1)
print(json.dumps(summary))
