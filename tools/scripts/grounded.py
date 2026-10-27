"""검색 근거화 답변: 위키백과를 읽기 전용(GET)으로 검색해 그 자료만으로 답하게 한다.

사용(단독): python grounded.py <llama_server_url> "질문"
- 한글이 있으면 ko.wikipedia, 아니면 en.wikipedia.
- 모델이 검색어를 만들고 -> 위키백과 검색 상위 3개 문서의 요약(intro)을 가져와 -> 자료만 근거로 답한다.
- 자료에 답이 없으면 정확히 "확인 불가" 라고 답하게 한다. 답 끝에 [출처: 문서 제목].
- 웹 응답은 cache_path(JSON)에 저장해 재실행 시 같은 자료를 쓴다(재현성, 요청 최소화).
네트워크 접근은 en/ko.wikipedia.org GET 뿐이다. WIKI_GATEWAY=http://host:port 가 있으면 readonly_gateway.py 경유.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "Qwen35-Heretic-grounding-eval/0.1 (local research; contact: owner of this machine)"
ABSTAIN = "확인 불가"


def chat(base: str, prompt: str, max_tokens: int = 256, system: str | None = None) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": "x", "messages": msgs, "temperature": 0, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


class Wiki:
    def __init__(self, cache_path: Path | None = None):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path and cache_path.exists() else {}

    def _get(self, url: str) -> dict:
        if url not in self.cache:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            for attempt in range(6):
                time.sleep(1.0)  # 위키미디어 API 예의: 순차 요청, 최소 간격
                try:
                    with urllib.request.urlopen(req, timeout=30) as r:
                        self.cache[url] = json.loads(r.read())
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429 or attempt == 5:
                        raise
                    time.sleep(int(e.headers.get("Retry-After") or 0) or 5 * 2 ** attempt)
            if self.cache_path:
                self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        return self.cache[url]

    def search(self, lang: str, query: str, k: int = 3) -> list[dict]:
        gw = os.environ.get("WIKI_GATEWAY")  # 격리 환경: readonly_gateway.py 경유
        api = f"{gw.rstrip('/')}/wiki/{lang}/api.php?" if gw else f"https://{lang}.wikipedia.org/w/api.php?"
        hits = self._get(api + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": query, "srlimit": k, "format": "json"}))
        titles = [h["title"] for h in hits.get("query", {}).get("search", [])]
        if not titles:
            return []
        pages = self._get(api + urllib.parse.urlencode(
            {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1,
             "titles": "|".join(titles), "format": "json"}))["query"]["pages"].values()
        by_title = {p["title"]: p.get("extract", "") for p in pages}
        return [{"title": t, "text": by_title.get(t, "")[:1200]} for t in titles if by_title.get(t)]


def lang_of(text: str) -> str:
    return "ko" if re.search(r"[가-힣]", text) else "en"


def entity_names(base: str, question: str) -> list:
    """질문 속 고유명사(나라·사람·작품 이름)를 질문에 쓰인 글자 그대로 돌려준다. 없으면 [].
    모델이 가짜 이름을 진짜로 고쳐서('스웨도니아' -> '스웨덴') 돌려주는 일이 있어, 질문 문장에 실제로 있는 글자만 받는다(v4b)."""
    out = chat(base, "질문에 고유명사(나라, 사람, 작품, 단체 이름)가 있으면 그 이름을 질문에 쓰인 글자 그대로 한 줄에 하나만 "
                     "출력하라. 고치거나 번역하지 마라. 고유명사가 없으면 NONE 만 출력하라.\n"
                     "예: '호주의 수도는?' -> 호주 / '태양계에서 가장 큰 행성은?' -> NONE\n\n"
                     f"질문: {question}", 32).strip()
    name = out.splitlines()[0].strip().strip("'\"*.") if out else ""
    return [name] if name and name.upper() != "NONE" and len(name) >= 2 and name in question else []


def _mentions(docs: list, names: list) -> bool:
    blob = " ".join(d["title"] + " " + d["text"] for d in docs).lower()
    return any(n.lower() in blob for n in names)


def entity_exists(wiki: "Wiki", lang: str, names: list) -> bool:
    """그 이름 그대로 같은 언어 위키백과를 검색해, 문서에 그 글자가 실제로 나오는가(가짜 대상 거르기)."""
    return any(_mentions(wiki.search(lang, n), [n]) for n in names)


def grounded_answer(base: str, question: str, wiki: Wiki, guard: bool = False) -> dict:
    """guard=True(v4): 검색 문서에 질문의 대상 이름이 실제로 나올 때만 그 문서로 답한다.
    v2 의 영어 보조 검색이 '노르바니아(가상)'에 노르웨이 문서를 가져와 '수도는 오슬로'라고 답한 사고(life-v2 day7) 대응."""
    lang = lang_of(question)
    names = entity_names(base, question) if guard else []
    query = chat(base, f"Write a short Wikipedia search query (2-5 words, in the same language as the question) "
                       f"for finding the answer to this question. Output only the query.\n\nQuestion: {question}", 24)
    query = query.strip().strip('"').splitlines()[0][:100]
    # 모델 검색어만 쓰면 엉뚱한 상위 문서(예: "대한민국 최고 산" -> 대한민국)만 오는 일이 많아 질문 원문 검색과 합친다.
    docs, seen = [], set()
    for d in wiki.search(lang, query) + wiki.search(lang, question):
        if d["title"] not in seen and len(docs) < 5:
            seen.add(d["title"])
            docs.append(d)
    sources = [d["title"] for d in docs]
    if guard and names and not entity_exists(wiki, lang, names):
        # 질문의 고유명사가 그 언어 위키백과 어디에도 그 글자 그대로 없으면, 비슷한 이름의 다른 대상으로 답하지 않는다.
        return {"query": query, "lang": lang, "sources": sources, "en_fallback": False, "entity": names,
                "entity_blocked": True, "answer": f"{ABSTAIN} (위키백과에 '{names[0]}' 이(가) 없음)"}
    answer = _answer_from(base, question, docs)
    fallback = False
    # v2: 한국어 위키백과 검색은 질문형 문장에 약하다. 답을 못 찾으면 영어 위키백과로 한 번 더 찾는다.
    if lang == "ko" and NOT_FOUND.search(answer):
        en_q = chat(base, "Write a short English Wikipedia search query (2-5 words) for finding the answer to "
                          f"this question. Output only the query.\n\nQuestion: {question}", 24)
        en_q = en_q.strip().strip('"').splitlines()[0][:100]
        en_docs = wiki.search("en", en_q)
        if en_docs:
            answer = _answer_from(base, question, en_docs)
            sources, fallback, query = [d["title"] for d in en_docs], True, f"{query} | en: {en_q}"
    return {"query": query, "lang": lang, "sources": sources, "answer": answer, "en_fallback": fallback,
            "entity": names, "entity_blocked": False}


def leading_safe_answer(base: str, question: str, wiki: "Wiki", guard: bool = False) -> dict:
    """v3: 답을 넣어 묻는 질문('X의 수도는 Y인가?')은 제시된 답을 뺀 중립 질문으로 자료를 찾은 뒤 전제를 판정한다.
    유도 질문을 그대로 검색하면 엉뚱한 문서를 근거로 '네'가 나오는 일이 있었다(life 실험 LIFE-s4 day1)."""
    neutral = chat(base, "다음 질문에 답이나 추측이 들어 있으면 그것을 빼고, 무엇을 알아내야 하는지만 묻는 중립적인 질문으로 "
                         "바꿔라. 같은 언어로, 질문 하나만 출력하라.\n예: '호주의 수도는 시드니가 맞나요?' -> '호주의 수도는 어디인가?'\n\n"
                         f"질문: {question}", 64).strip().splitlines()[0][:200]
    found = grounded_answer(base, neutral, wiki, guard=guard)
    if NOT_FOUND.search(found["answer"]):
        return {**found, "neutral": neutral, "answer": f"{ABSTAIN} (중립 질문 '{neutral}' 에 대한 근거를 찾지 못함)"}
    judged = chat(base, f"사실 확인 결과: {found['answer']}\n\n이 결과만 근거로 다음 질문에 답하라. 질문의 전제가 결과와 맞으면 "
                        f"'네', 다르면 '아니요'로 시작하고 올바른 사실을 짧게 덧붙여라. 결과에 판단할 내용이 없으면 '{ABSTAIN}'.\n\n"
                        f"질문: {question}", 96)
    return {**found, "neutral": neutral, "answer": judged}


NOT_FOUND = re.compile(r"확인 ?불가|명시(되어|돼) ?있지 않|자료에 (없|나와 있지 않)")


def _answer_from(base: str, question: str, docs: list) -> str:
    context = "\n\n".join(f"[{d['title']}]\n{d['text']}" for d in docs) or "(검색 결과 없음)"
    prompt = (f"아래 자료만 근거로 질문에 답하라. 자기 기억은 쓰지 마라.\n"
              f"자료에 답이 명시돼 있지 않거나, 질문의 대상이 자료에 없으면 정확히 \"{ABSTAIN}\" 라고만 답하라.\n"
              f"답할 수 있으면 질문과 같은 언어로 짧게 답하고 끝에 [출처: 근거가 된 문서 제목] 을 붙여라.\n\n"
              f"자료:\n{context}\n\n질문: {question}")
    return chat(base, prompt, 128)


if __name__ == "__main__":
    r = grounded_answer(sys.argv[1], sys.argv[2], Wiki())
    print(json.dumps(r, ensure_ascii=False, indent=1))
