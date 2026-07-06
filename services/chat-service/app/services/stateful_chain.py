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
    Default ON — stateful prompt caching is the industry standard (99% cache on the
    re-sent tool/history prefix, reasoning fully controllable, degrade-safe E1). Disable
    platform-wide with LLM_STATEFUL_CACHE=0/false/off. Only providers declaring the
    responses_api capability (openai / lm_studio) ever go stateful; all others stay on the
    unified chat/completions path regardless."""
    return os.getenv("LLM_STATEFUL_CACHE", "").strip().lower() not in ("0", "false", "off")


def _trigger_ratio() -> float:
    # single source for the near-window guard (same ratio auto-compaction uses).
    from app.services.compaction import COMPACT_TRIGGER_RATIO

    return COMPACT_TRIGGER_RATIO


def _max_chain_tokens() -> int | None:
    """P3 §9 — an OPTIONAL hard cap on the stateful chain's accumulated server-side size,
    independent of the model's declared window. A provider may load a model with a
    smaller `n_ctx` than `context_length` advertises, and the stateful chain ACCUMULATES
    (unlike stateless, which the compaction keeps ~32K), so a conservative deploy cap
    bounds it below the real window. `LLM_STATEFUL_MAX_CHAIN_TOKENS` (unset ⇒ no extra
    cap, rule-4 uses only ratio×effective_limit). The re-establish it forces sends the
    compaction-bounded history, resetting the accumulation."""
    v = os.getenv("LLM_STATEFUL_MAX_CHAIN_TOKENS", "").strip()
    if v.isdigit() and int(v) > 0:
        return int(v)
    return None


def decide_chain(
    *,
    capabilities: dict[str, bool] | None,
    latest_assistant: dict | None,
    current_model_ref: str,
    compacted_before_seq: int | None,
    effective_limit: int | None,
) -> tuple[bool, str | None, str]:
    """Return ``(use_stateful, previous_response_id, reason)``.

    - ``(False, None, "stateless")`` — stateless full context (capability absent / flag off).
    - ``(True, None, <reestablish reason>)`` — stateful ESTABLISH: full context, fresh chain.
    - ``(True, R, "continue")`` — stateful CONTINUE: send the delta chained onto head ``R``.

    ``reason`` is surfaced on the contextBudget frame (Inspector §9) so a re-chain is
    visible + attributable. ``latest_assistant`` is the newest assistant row for
    (session, branch) or None: ``{response_id, model_ref, input_tokens, sequence_num,
    context_size}``.
    """
    caps = capabilities or {}
    if not caps.get("responses_api") or not stateful_enabled():
        return (False, None, "stateless")

    if latest_assistant is None:
        return (True, None, "establish_first")  # first turn

    head = latest_assistant.get("response_id")
    if not head:
        # §5a rule-1: the most-recent assistant turn was STATELESS (or a concurrent
        # multi-device fork left a null-head newer row) → the provider chain doesn't
        # contain it. Re-establish from DB truth rather than drop that exchange.
        return (True, None, "reestablish_stateless_prev")

    # §5a rule-2 — a chain is model-specific.
    if str(latest_assistant.get("model_ref") or "") != str(current_model_ref):
        return (True, None, "reestablish_model_switch")

    # §5a rule-3 — a compaction that swallowed the head turn invalidates the chain
    # (the server still holds the un-compacted history; re-establish applies the compact).
    head_seq = latest_assistant.get("sequence_num")
    if compacted_before_seq is not None and head_seq is not None and compacted_before_seq > head_seq:
        return (True, None, "reestablish_compaction")

    # §5a rule-4 — the accumulated server-side size nears the window → re-establish with
    # the (compaction-bounded) current history so the chain doesn't overflow. P3 §9: use
    # the TRUE single-call context size (`context_size`), NOT the summed tool-loop
    # `input_tokens` (which counts the chain N times for an N-iteration turn and would
    # fire ~N× too early → re-establish thrashing). Fall back to input_tokens only if the
    # size wasn't recorded (pre-P3 rows).
    size = latest_assistant.get("context_size") or latest_assistant.get("input_tokens")
    if size:
        thresholds = []
        if effective_limit:
            thresholds.append(_trigger_ratio() * int(effective_limit))
        cap = _max_chain_tokens()
        if cap:
            thresholds.append(cap)  # conservative deploy cap, independent of the window
        if thresholds and int(size) > min(thresholds):
            return (True, None, "reestablish_window")

    return (True, head, "continue")  # continue from the valid head
