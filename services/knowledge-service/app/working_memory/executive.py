"""The executive — updates working_memory.state from recent turns (M5).

The central-executive loop: read recent chat turns + the current block, ask a
cheap utility model for an updated STATE (never the charter), monotonic-merge
`covered`, and write state via the repo.

Safe-when-wrong BY CONSTRUCTION:
- writes `state` ONLY — the repo has no update_charter, so even a fully
  hallucinated run can never move the goal (EC-1).
- `covered` is **monotonic** — unioned with the prior covered, never shrinks.
- `phase` is accepted only if it is one of the charter's phases, else kept.
- every failure path (no block, no model, LLM error, bad JSON) is a no-op skip
  that returns a status string and never raises (EC-10).

The model is resolved per-user from provider-registry (no hardcoded model).
docs/specs/2026-06-23-interview-roleplay.md.

ACP A1 (RV-H1): the PURE parts — `merge_state` + `build_messages` + the executive
prompt/constants — moved to the shared SDK `loreweave_agent_control.state_merge`.
`run_executive` (the I/O: repo + LLM) stays here and imports them; behavior is
byte-identical (RW-2 golden). `ex.merge_state` / `ex.build_messages` remain
accessible via this module (re-exported) so existing callers/tests are unchanged.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

from loreweave_llm import no_thinking_fields

# ACP A1 — the pure state-merge + prompt-build now live in the SDK; re-exported here.
from loreweave_agent_control.state_merge import (  # noqa: F401 — re-export for callers/tests
    EXECUTIVE_MAX_TURN_CHARS,
    EXECUTIVE_MAX_TURNS,
    EXECUTIVE_SYSTEM_PROMPT,
    build_messages,
    merge_state,
)

logger = logging.getLogger(__name__)

# The executive asks for JSON-only state; a reasoning model must NOT think out loud
# (max_tokens=500 → hidden reasoning would eat the whole budget → empty → bad_json).
_NO_THINKING = no_thinking_fields()


def _extract_content(job_result: dict | None) -> str:
    messages_out = (job_result or {}).get("messages") or []
    if isinstance(messages_out, list) and messages_out and isinstance(messages_out[0], dict):
        return messages_out[0].get("content", "") or ""
    return ""


def _parse_json_object(content: str) -> dict:
    """Parse a JSON object from a model reply that may wrap it in prose or a
    ```json fence. We do NOT use response_format=json_object — lm_studio rejects
    it (only json_schema/text), so the prompt asks for JSON and we extract it.
    Raises ValueError if no object is found."""
    s = (content or "").strip()
    # strip a leading/trailing code fence if present
    if s.startswith("```"):
        s = s.split("```", 2)
        s = s[1] if len(s) > 1 else ""
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        # fall back to the outermost { ... } span
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in reply")
        obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("reply is not a JSON object")
    return obj


async def run_executive(
    *,
    repo,
    llm_client,
    session_id: UUID,
    user_id: UUID,
    model_source: str | None,
    model_ref: str | None,
    recent_turns: list[dict],
) -> str:
    """Run one executive pass. Returns a status string; never raises.

    The model is the SESSION's own model (passed by chat-service) — the user
    already chose it, it's a provider-registry user_model UUID (no hardcoded
    model, no separate default-model capability needed). Statuses:
    no_block | no_model | llm_failed | bad_json | updated.
    """
    block = await repo.get(session_id, user_id)
    if block is None:
        return "no_block"

    if not model_source or not model_ref:
        return "no_model"

    messages = build_messages(block["charter"], block["state"], recent_turns or [])
    try:
        job = await llm_client.submit_and_wait(
            user_id=str(user_id),
            operation="chat",
            model_source=model_source,
            model_ref=model_ref,
            # No response_format: lm_studio rejects json_object (json_schema/text
            # only). The prompt asks for JSON-only; we extract it defensively.
            input={
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 500,
                **_NO_THINKING,
            },
            chunking=None,
            job_meta={"usage_purpose": "working_memory", "extractor": "working_memory_executive"},
            transient_retry_budget=1,
        )
    except Exception as exc:  # best-effort: the executive never breaks the caller
        logger.warning("executive: LLM call failed session=%s err=%s", session_id, exc)
        return "llm_failed"

    if getattr(job, "status", None) != "completed":
        return "llm_failed"

    content = _extract_content(getattr(job, "result", None))
    try:
        llm_state = _parse_json_object(content)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("executive: bad JSON session=%s err=%s body=%r", session_id, exc, content[:200])
        return "bad_json"

    # RV-M6: the read-modify-write is serialized under a per-session advisory lock inside the
    # repo, which RE-READS the current state (not the possibly-stale block["state"] we read
    # before the slow LLM call) and merges under the lock — so two overlapping ticks can't
    # last-writer-clobber. RV-H4: owner-scoped (same user_id we read the block under).
    await repo.apply_state_update(session_id, user_id, block["charter"], llm_state, merge_state)
    return "updated"
