"""Bind eval judges to provider-registry (LE-PROD-2 P3b).

The eval judge ensemble needs an async ``JudgeFn`` per judge — ``(system, user) ->
raw text`` — backed by a real LLM. This is the production binding: each judge's
``model_ref`` is called through provider-registry ``POST /internal/llm/stream``
(operation=chat), scoped to the model's owner_user_id (BYOK — a model is owned
per-user; a mismatched user_id → 404). NO hardcoded model name — only the opaque
registry ``model_ref``. Extracted from the C15 live-smoke so the eval-run ROUTE and
the smoke share ONE binding.

Degrade: a judge whose call errors simply does not vote (the ensemble tolerates it,
D11) — this helper RAISES on a non-200 so the ensemble's per-judge try/except records
the miss; it never silently returns empty (which would parse as an unjudged item)."""

from __future__ import annotations

import json
from typing import Callable, Mapping

import httpx

from app.eval.judge_usefulness import JudgeFn, JudgeSpec
from app.generation.complete import collect_stream_text

__all__ = ["make_judge_fn_for"]


def make_judge_fn_for(
    provider_registry_url: str,
    internal_token: str,
    owner_by_ref: Mapping[str, str],
    *,
    timeout_s: float = 300.0,
) -> Callable[[JudgeSpec], JudgeFn]:
    """Return ``judge_fn_for(judge) -> JudgeFn`` bound to provider-registry.

    ``owner_by_ref`` maps each judge's ``model_ref`` → its owner_user_id (the BYOK
    scope for the call). ``timeout_s`` is generous to tolerate a JIT model swap."""
    base = provider_registry_url.rstrip("/")

    def judge_fn_for(judge: JudgeSpec) -> JudgeFn:
        async def _fn(system: str, user: str) -> str:
            body = {
                "operation": "chat",
                "model_source": "user_model",
                "model_ref": judge.model_ref,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {
                "X-Internal-Token": internal_token,
                "Content-Type": "application/json; charset=utf-8",
            }
            params = {"user_id": owner_by_ref.get(judge.model_ref, "")}
            timeout = httpx.Timeout(timeout_s, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/internal/llm/stream",
                    headers=headers, params=params, content=content,
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"judge {judge.label} HTTP {resp.status_code}: {resp.text[:160]}"
                )
            return collect_stream_text(resp.text)

        return _fn

    return judge_fn_for
