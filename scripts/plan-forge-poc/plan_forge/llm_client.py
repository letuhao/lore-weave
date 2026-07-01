"""Direct LM Studio OpenAI-compatible client for PlanForge POC."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-qat"

NO_THINK_EXTRA = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


class LMStudioClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        io_dir: Path | None = None,
        timeout_s: float = 600.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("PLANFORGE_LM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("PLANFORGE_LM_MODEL", DEFAULT_MODEL)
        self.io_dir = io_dir
        self.timeout_s = timeout_s
        self._seq = 0

    def health_check(self) -> dict[str, Any]:
        r = requests.get(f"{self.base_url}/models", timeout=30)
        r.raise_for_status()
        return r.json()

    def chat(
        self,
        *,
        step: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 8000,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **NO_THINK_EXTRA,
        }
        t0 = time.perf_counter()
        r = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=self.timeout_s,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        body = r.json()
        content = body["choices"][0]["message"]["content"]
        self._log_io(step, payload, body, elapsed_ms)
        return content

    def _log_io(self, step: str, request: dict[str, Any], response: dict[str, Any], elapsed_ms: int) -> None:
        if self.io_dir is None:
            return
        self.io_dir.mkdir(parents=True, exist_ok=True)
        self._seq += 1
        user_msg = request["messages"][1]["content"]
        record = {
            "seq": self._seq,
            "step": step,
            "model": self.model,
            "elapsed_ms": elapsed_ms,
            "prompt_chars": len(user_msg),
            "prompt_sha256": hashlib.sha256(user_msg.encode("utf-8")).hexdigest(),
            "usage": response.get("usage"),
            "request_messages_preview": {
                "system": request["messages"][0]["content"][:500],
                "user_head": user_msg[:800],
                "user_tail": user_msg[-800:] if len(user_msg) > 800 else "",
            },
            "response_content": response["choices"][0]["message"]["content"],
        }
        path = self.io_dir / f"{self._seq:03d}_{step}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
