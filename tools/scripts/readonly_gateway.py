"""격리된 실험 노트북용 읽기전용 웹 게이트웨이(빌드 PC 에서 실행).

노트북은 외부로 직접 나갈 수 없고(출력 drop), 이 게이트웨이 한 곳에만 HTTP 로 접속한다.
게이트웨이가 대신 HTTPS GET 을 보낸다. CONNECT 터널을 쓰지 않으므로 요청 내용을 전부 검사할 수 있다.

허용: GET /wiki/<lang>/api.php?<query>   (lang = ko | en)
      query 의 action=query 이고 list=search 또는 prop=extracts 인 것만, 파라미터 이름은 허용목록 안에서만.
그 외(다른 메서드·경로·도메인·파라미터, 허용 IP 밖의 클라이언트)는 403. 모든 요청을 JSONL 로 기록.

사용: python readonly_gateway.py --bind 127.0.0.1 --port 8899 --allow 127.0.0.1 [--allow 192.168.0.149] --log logs/gateway.jsonl
grounded.py 는 환경변수 WIKI_GATEWAY=http://<host>:8899 가 있으면 위키백과 대신 이 게이트웨이를 쓴다.
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LANGS = {"ko", "en"}
PARAMS = {"action", "list", "srsearch", "srlimit", "format", "prop", "exintro", "explaintext", "redirects", "titles"}
UA = "Qwen35-Heretic-readonly-gateway/0.1 (local research)"
MIN_INTERVAL = 1.0  # 위키미디어 API 예의: 업스트림 요청 최소 간격(초)


def allowed(path: str) -> tuple[str | None, str]:
    u = urllib.parse.urlsplit(path)
    parts = u.path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "wiki" or parts[1] not in LANGS or parts[2] != "api.php":
        return None, "path"
    q = urllib.parse.parse_qs(u.query, keep_blank_values=True)
    if set(q) - PARAMS:
        return None, f"param {sorted(set(q) - PARAMS)}"
    if q.get("action") != ["query"] or not (q.get("list") == ["search"] or q.get("prop") == ["extracts"]):
        return None, "action"
    return f"https://{parts[1]}.wikipedia.org/w/api.php?{u.query}", "ok"


class Handler(BaseHTTPRequestHandler):
    allow_ips: set[str] = set()
    log_path = None
    last_upstream = 0.0

    def log_event(self, **kw):
        kw.update(t=time.strftime("%Y-%m-%dT%H:%M:%S"), client=self.client_address[0], method=self.command, path=self.path)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(kw, ensure_ascii=False) + "\n")

    def deny(self, why: str):
        self.log_event(result="deny", why=why)
        self.send_response(403)
        self.end_headers()
        self.wfile.write(b"denied\n")

    def do_GET(self):  # noqa: N802
        if self.client_address[0] not in self.allow_ips:
            return self.deny("client ip")
        url, why = allowed(self.path)
        if not url:
            return self.deny(why)
        wait = Handler.last_upstream + MIN_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        Handler.last_upstream = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                body, code = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, code = e.read(), e.code
        self.log_event(result="ok", upstream=code, bytes=len(body))
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reject(self):
        self.deny("method")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_CONNECT = _reject

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--allow", action="append", default=[])
    ap.add_argument("--log", default="logs/gateway.jsonl")
    a = ap.parse_args()
    Handler.allow_ips, Handler.log_path = set(a.allow) or {"127.0.0.1"}, a.log
    print(f"readonly gateway on {a.bind}:{a.port}, clients={sorted(Handler.allow_ips)}, log={a.log}")
    ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()
