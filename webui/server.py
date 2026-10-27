"""A small, local-only chat UI for the Qwen3.5-4B-Heretic checkpoints.

The server intentionally binds to 127.0.0.1, so the model is never exposed to
the network.  It has no cloud dependency and loads a selected merged checkpoint
only when the first message is sent.
"""

from __future__ import annotations

import gc
import json
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 7860

MODELS = {
    "t34": ROOT / "merged" / "Qwen3.5-4B-Heretic-t34",
    "t35": ROOT / "merged" / "Qwen3.5-4B-Heretic-t35",
    "t55": ROOT / "merged" / "Qwen3.5-4B-Heretic-t55",
}

state_lock = threading.RLock()
generation_lock = threading.Lock()
model: Any = None
processor: Any = None
loaded_variant: str | None = None
load_status = "ready"
load_error: str | None = None


def model_status() -> dict[str, Any]:
    with state_lock:
        return {
            "status": load_status,
            "loaded_variant": loaded_variant,
            "error": load_error,
            "models": [
                {"id": key, "path": str(path), "available": path.is_dir()}
                for key, path in MODELS.items()
            ],
        }


def unload_model() -> None:
    global model, processor, loaded_variant
    model = None
    processor = None
    loaded_variant = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def ensure_model(variant: str) -> tuple[Any, Any]:
    """Load the selected full Heretic checkpoint, replacing a prior one."""
    global model, processor, loaded_variant, load_status, load_error
    if variant not in MODELS:
        raise ValueError("알 수 없는 모델 변형입니다.")
    model_path = MODELS[variant]
    if not model_path.is_dir():
        raise FileNotFoundError(f"모델 폴더를 찾을 수 없습니다: {model_path}")

    with state_lock:
        if model is not None and processor is not None and loaded_variant == variant:
            return model, processor
        load_status, load_error = "loading", None
        unload_model()

    try:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        new_processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True)
        new_model = AutoModelForImageTextToText.from_pretrained(
            str(model_path),
            torch_dtype=dtype,
            local_files_only=True,
            low_cpu_mem_usage=True,
        ).to(device)
        new_model.eval()
        with state_lock:
            model, processor, loaded_variant = new_model, new_processor, variant
            load_status, load_error = "loaded", None
        return new_model, new_processor
    except Exception as error:
        with state_lock:
            unload_model()
            load_status, load_error = "error", str(error)
        raise


def sse(handler: BaseHTTPRequestHandler, event: dict[str, Any]) -> None:
    message = f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
    handler.wfile.write(message)
    handler.wfile.flush()


def generate(handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
    variant = str(body.get("model", "t34"))
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("대화 메시지가 비어 있습니다.")
    if len(messages) > 30:
        messages = messages[-30:]
    clean_messages = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"system", "user", "assistant"} and isinstance(content, str) and content.strip():
            clean_messages.append({"role": role, "content": content.strip()[:16000]})
    if not clean_messages or clean_messages[-1]["role"] != "user":
        raise ValueError("마지막 메시지는 사용자 메시지여야 합니다.")

    max_tokens = max(32, min(int(body.get("max_tokens", 1024)), 4096))
    temperature = max(0.0, min(float(body.get("temperature", 0.7)), 2.0))
    thinking = bool(body.get("thinking", False))

    if not generation_lock.acquire(blocking=False):
        raise RuntimeError("다른 응답을 생성 중입니다. 잠시 후 다시 시도하세요.")
    try:
        sse(handler, {"type": "status", "message": "모델을 준비하는 중…"})
        active_model, active_processor = ensure_model(variant)
        import torch
        from transformers import TextIteratorStreamer

        prompt = active_processor.apply_chat_template(
            clean_messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=thinking,
        )
        device = next(active_model.parameters()).device
        inputs = active_processor(text=[prompt], return_tensors="pt")
        inputs = {name: value.to(device) for name, value in inputs.items()}
        streamer = TextIteratorStreamer(
            active_processor.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )
        generation_args = {
            **inputs,
            "streamer": streamer,
            "max_new_tokens": max_tokens,
            "do_sample": temperature > 0,
            "temperature": max(temperature, 0.01),
            "top_p": 0.8,
            "top_k": 20,
            "use_cache": True,
        }
        worker = threading.Thread(target=active_model.generate, kwargs=generation_args, daemon=True)
        worker.start()
        sse(handler, {"type": "status", "message": "응답 생성 중"})
        for token in streamer:
            sse(handler, {"type": "token", "token": token})
        worker.join(timeout=5)
        sse(handler, {"type": "done"})
    finally:
        generation_lock.release()


class App(BaseHTTPRequestHandler):
    server_version = "HereticWebUI/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, code: HTTPStatus, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            self.send_json(HTTPStatus.OK, model_status())
            return
        if self.path not in {"/", "/index.html"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        page = (WEB_ROOT / "index.html").read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1_000_000:
                raise ValueError("요청 크기가 올바르지 않습니다.")
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                generate(self, body)
            except Exception as error:
                traceback.print_exc()
                sse(self, {"type": "error", "message": str(error)})
        except Exception as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


if __name__ == "__main__":
    print(f"Heretic Web UI: http://{HOST}:{PORT}")
    print("로컬 전용 서버입니다. 종료하려면 이 창에서 Ctrl+C를 누르세요.")
    ThreadingHTTPServer((HOST, PORT), App).serve_forever()
