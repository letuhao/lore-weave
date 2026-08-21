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

from loreweave_internal_client import build_internal_client

from app.eval.judge_usefulness import JudgeFn, JudgeSpec
from app.generation.complete import collect_stream_finish_reason, collect_stream_text
from app.llm_budget import max_tokens_for
from app.logging_config import trace_id_var

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
                # This key was ABSENT — the judge ran uncapped, and the budget gate could not
                # see it because the raw-body shape was an unscanned surface. STRUCTURED, not
                # VERDICT: `parse_judge_verdict` accepts a JSON object or nothing, so a clipped
                # verdict is not a shorter answer, it is the proposal silently dropping out of
                # this judge's denominator. See app/llm_budget.py for why the row is a
                # NARROWING rather than an adoption.
                # `target=1`: one proposal per call, so one verdict object. A real count the site
                # holds, not a kwarg passed to satisfy a gate — if the rubric ever batches
                # proposals this number moves with it.
                "max_tokens": max_tokens_for("eval_judge_usefulness", target=1),
            }
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
            params = {"user_id": owner_by_ref.get(judge.model_ref, "")}
            # W5 (ephemeral wave): factory bakes X-Internal-Token + trace. Keep the
            # explicit charset Content-Type per-request — it OVERRIDES the factory's
            # baked `application/json` and is load-bearing for the CJK body.
            async with build_internal_client(
                base, internal_token=internal_token,
                timeout_s=timeout_s, connect_timeout_s=10.0,
                trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.post(
                    f"{base}/internal/llm/stream",
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    params=params, content=content,
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"judge {judge.label} HTTP {resp.status_code}: {resp.text[:160]}"
                )
            # The truncation check the STRUCTURED kind obliges (llm-budget.contract.json,
            # `fatal_kinds_must_check_finish_reason`). Raising rather than returning the
            # clipped text is the point: `_run_one_judge` catches and LOGS the exception, so
            # "we cut the judge off" becomes distinguishable from "the judge emitted prose we
            # could not parse". Both end as `unjudged`, and until now they ended there
            # identically — the same two-states-collapsed-into-one shape as the sweep that
            # could not tell an outage from a clean book.
            if collect_stream_finish_reason(resp.text) == "length":
                raise RuntimeError(
                    f"judge {judge.label} hit the output budget (finish_reason=length); "
                    f"its verdict is truncated, not absent"
                )
            return collect_stream_text(resp.text)

        return _fn

    return judge_fn_for
