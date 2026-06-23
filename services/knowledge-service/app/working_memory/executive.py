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
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# How many recent turns the prompt is bounded to (chat-service sends the window).
EXECUTIVE_MAX_TURNS = 12

EXECUTIVE_SYSTEM_PROMPT = (
    "You are the silent director of a roleplay/interview session. You are given the "
    "session CHARTER (a FIXED goal, the planned phases, and a checklist) and the recent "
    "turns. Report ONLY the current progress as a JSON object — you do NOT change the "
    "goal. Output exactly:\n"
    '{"phase": <one of the charter phases>, '
    '"covered": [<checklist items demonstrably covered so far, by their exact charter '
    'wording>], '
    '"redirect_hint": <a short in-character nudge to steer back to the goal IF the '
    'conversation has drifted, else null>}\n'
    "Write any prose (redirect_hint) in the charter's language. Output JSON only, no prose."
)


# Per-turn content cap — bound the prompt size so a single pasted wall of text
# can't blow the model context / cost (EXECUTIVE_MAX_TURNS bounds the count).
EXECUTIVE_MAX_TURN_CHARS = 2000


def build_messages(charter: dict, state: dict, recent_turns: list[dict]) -> list[dict]:
    turns = [
        {
            "role": t.get("role", ""),
            "content": (t.get("content", "") or "")[:EXECUTIVE_MAX_TURN_CHARS],
        }
        for t in (recent_turns or [])[-EXECUTIVE_MAX_TURNS:]
    ]
    ctx = {"charter": charter, "current_state": state, "recent_turns": turns}
    user = (
        "Session context:\n"
        + json.dumps(ctx, ensure_ascii=False)
        + "\n\nReturn the updated progress JSON."
    )
    return [
        {"role": "system", "content": EXECUTIVE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def merge_state(charter: dict, old_state: dict, llm_state: dict) -> dict:
    """Merge the LLM's reported progress into a new state — safe-when-wrong.

    `covered` is monotonic (union, dedup-preserving order); `phase` must be a
    charter phase or the prior phase is kept; non-string fields are dropped.
    """
    old_cov = old_state.get("covered") or []
    new_cov = [c for c in (llm_state.get("covered") or []) if isinstance(c, str)]
    covered = list(dict.fromkeys([*old_cov, *new_cov]))  # union, monotonic, ordered

    phases = charter.get("phases") or []
    phase = llm_state.get("phase")
    if phase not in phases:
        phase = old_state.get("phase", "")

    def _str_or_none(v):
        return v if isinstance(v, str) and v.strip() else None

    return {
        "phase": phase,
        "covered": covered,
        "elapsed_min": old_state.get("elapsed_min"),
        "drift_note": _str_or_none(llm_state.get("drift_note")),
        "redirect_hint": _str_or_none(llm_state.get("redirect_hint")),
    }


def _extract_content(job_result: dict | None) -> str:
    messages_out = (job_result or {}).get("messages") or []
    if isinstance(messages_out, list) and messages_out and isinstance(messages_out[0], dict):
        return messages_out[0].get("content", "") or ""
    return ""


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
            input={
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 500,
            },
            chunking=None,
            job_meta={"extractor": "working_memory_executive"},
            transient_retry_budget=1,
        )
    except Exception as exc:  # best-effort: the executive never breaks the caller
        logger.warning("executive: LLM call failed session=%s err=%s", session_id, exc)
        return "llm_failed"

    if getattr(job, "status", None) != "completed":
        return "llm_failed"

    content = _extract_content(getattr(job, "result", None))
    try:
        llm_state = json.loads(content)
        if not isinstance(llm_state, dict):
            raise ValueError("not a JSON object")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("executive: bad JSON session=%s err=%s body=%r", session_id, exc, content[:200])
        return "bad_json"

    new_state = merge_state(block["charter"], block["state"], llm_state)
    await repo.update_state(session_id, new_state)
    return "updated"
