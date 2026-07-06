"""Stateful /v1/responses chain decision (Provider Context Strategy P2 §4/§5a).

The policy half of the stateful transport: given the provider's declared capabilities
+ the latest assistant turn for this (session, branch), decide whether to run this turn
stateful and — if so — whether to CONTINUE from a stored chain head or ESTABLISH a fresh
chain. Pure + deterministic (the caller does the one DB read + passes the row in), so the
head-validity predicate is unit-testable without a DB.

Correctness core (§5a): a stored response_id is a valid head to CONTINUE from ONLY if it
is the latest assistant turn's id (no intervening stateless/forked turn), the model is
unchanged, no compaction swallowed it, and the accumulated server-side size is under the
window. Any failure ⇒ establish (full context, fresh chain) — which self-heals from DB
truth. Establishing is always safe; continuing on a stale head silently drops context.
"""
from __future__ import annotations

import os


def stateful_enabled() -> bool:
    """The deploy flag, read the SAME way the gateway reads it (§5 flag-consistency):
    chat-service must only send a DELTA when it is certain the gateway will run stateful.
    Default OFF; enable with LLM_STATEFUL_CACHE=1/true/on."""
    return os.getenv("LLM_STATEFUL_CACHE", "").strip().lower() in ("1", "true", "on")


def _trigger_ratio() -> float:
    # single source for the near-window guard (same ratio auto-compaction uses).
    from app.services.compaction import COMPACT_TRIGGER_RATIO

    return COMPACT_TRIGGER_RATIO


def decide_chain(
    *,
    capabilities: dict[str, bool] | None,
    latest_assistant: dict | None,
    current_model_ref: str,
    compacted_before_seq: int | None,
    effective_limit: int | None,
) -> tuple[bool, str | None]:
    """Return ``(use_stateful, previous_response_id)``.

    - ``(False, None)`` — stateless full context (capability absent or flag off).
    - ``(True, None)``  — stateful ESTABLISH: full context, fresh chain (first turn, or a
      head-validity rule failed → re-establish).
    - ``(True, R)``     — stateful CONTINUE: send the delta chained onto head ``R``.

    ``latest_assistant`` is the newest assistant row for (session, branch) or None:
    ``{response_id, model_ref, input_tokens, sequence_num}``.
    """
    caps = capabilities or {}
    if not caps.get("responses_api") or not stateful_enabled():
        return (False, None)

    if latest_assistant is None:
        return (True, None)  # first turn — establish

    head = latest_assistant.get("response_id")
    if not head:
        # §5a rule-1: the most-recent assistant turn was STATELESS (or a concurrent
        # multi-device fork left a null-head newer row) → the provider chain doesn't
        # contain it. Re-establish from DB truth rather than drop that exchange.
        return (True, None)

    # §5a rule-2 — a chain is model-specific.
    if str(latest_assistant.get("model_ref") or "") != str(current_model_ref):
        return (True, None)

    # §5a rule-3 — a compaction that swallowed the head turn invalidates the chain
    # (the server still holds the un-compacted history; re-establish applies the compact).
    head_seq = latest_assistant.get("sequence_num")
    if compacted_before_seq is not None and head_seq is not None and compacted_before_seq > head_seq:
        return (True, None)

    # §5a rule-4 — the accumulated server-side size (the head turn's reported input_tokens)
    # nears the window → re-establish with the (compaction-bounded) current history so the
    # chain doesn't overflow. This is the P2 overflow guard.
    it = latest_assistant.get("input_tokens")
    if effective_limit and it and int(it) > _trigger_ratio() * int(effective_limit):
        return (True, None)

    return (True, head)  # continue from the valid head
