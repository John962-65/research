#!/usr/bin/env python3
"""会话模型 API 桥：把当前 ZCode 会话中的模型暴露为 OpenAI 兼容端点。

机制：评测进程 POST /v1/chat/completions → 请求落盘 <bridge>/pending/<id>.json →
由会话代理（ Research Copilot 的开发者会话）读取并以 JSON 写入
<bridge>/responses/<id>.response.json（字段：{"id", "content"}）→ 本服务轮询到
响应后按 OpenAI chat.completion 格式返回。

用途：真实模型 A/B/C 对照评测（model="session-agent"）。token 用量为估算值
（字符数/3），如实标注。仅监听 127.0.0.1。
"""
from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BRIDGE = Path("/tmp/rc-bridge")
PENDING = BRIDGE / "pending"
RESPONSES = BRIDGE / "responses"
REQUEST_TIMEOUT_S = 1800.0  # 会话代理作答可能跨多个工具调用
POLL_INTERVAL_S = 0.5

for directory in (PENDING, RESPONSES):
    directory.mkdir(parents=True, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 安静模式：评测会产生数百个请求
        pass

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": "session-agent", "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        messages = payload.get("messages") or []
        request_id = uuid.uuid4().hex[:16]
        (PENDING / f"{request_id}.request.json").write_text(
            json.dumps(
                {"id": request_id, "model": payload.get("model"), "messages": messages, "created_at": time.time()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        deadline = time.time() + REQUEST_TIMEOUT_S
        response_path = RESPONSES / f"{request_id}.response.json"
        while time.time() < deadline:
            if response_path.exists():
                try:
                    answered = json.loads(response_path.read_text(encoding="utf-8"))
                finally:
                    response_path.unlink(missing_ok=True)
                content = str(answered.get("content", ""))
                usage = answered.get("usage") or {
                    "prompt_tokens": sum(len(str(m.get("content") or "")) for m in messages) // 3,
                    "completion_tokens": len(content) // 3,
                    "estimated": True,
                }
                self._json(
                    200,
                    {
                        "id": f"chatcmpl-{request_id}",
                        "object": "chat.completion",
                        "model": payload.get("model") or "session-agent",
                        "choices": [
                            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                        ],
                        "usage": usage,
                    },
                )
                (BRIDGE / "answered.count").write_text(
                    str(int((BRIDGE / "answered.count").read_text() or 0) + 1) if (BRIDGE / "answered.count").exists() else "1",
                    encoding="utf-8",
                )
                return
            time.sleep(POLL_INTERVAL_S)
        self._json(503, {"error": {"message": "session agent did not answer within timeout"}})

    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"session-agent API bridge on http://127.0.0.1:8090/v1 (bridge dir: {BRIDGE})")
    ThreadingHTTPServer(("127.0.0.1", 8090), Handler).serve_forever()
