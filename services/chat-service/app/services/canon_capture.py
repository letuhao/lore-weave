"""WS-4C Half A — post-turn canon auto-capture.

Spec: docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md

Closes the F4 write side. Every Nth assistant turn we hand the exchange to
glossary-service's `/internal/books/{book_id}/capture-canon`, which extracts the entities
the turn newly NAMED and lands them in the book's existing review inbox as `draft` +
`ai-suggested` entities.

**Never canon.** A draft is invisible to L1/L2 auto-recall until a human promotes it, and a
name the human rejected carries an `ai-rejected` tombstone that glossary refuses to
re-propose. Capture proposes; the human decides.

Why this closes the gap: the durable, always-auto-recalled store is the GLOSSARY (re-read
into the context block every turn), not `memory_remember` (0.7-confidence, rate-limited,
confirm-gated). So a name coined at turn 3 survives to turn 40 iff it reached the glossary.
Before this, that only happened when the model *chose* to call a write tool.

Design notes worth keeping:

- **No chat-side dedup.** `proposeNewEntity` dedups by `(kind, name-or-alias, scope_label)`
  inside a per-book advisory-locked transaction. Pre-filtering here against the TTL-stale,
  name-only known-entity cache would be a second, weaker, drifting dedup key.
- **Server-resolved book_id only.** The caller must pass the book_id that knowledge-service
  resolved from the session's project — never the FE-supplied `editor_context.book_id`.
  glossary grant-checks it regardless (defense in depth), but chat must not *ask* to write
  into a book the user merely named.
- **Best-effort, always.** Every failure is swallowed. Capture runs after `RUN_FINISHED`;
  nothing it does may surface to the user or delay the next turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from app.client.glossary_capture_client import get_canon_capture_client
from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "CaptureContext",
    "CaptureDecision",
    "should_capture",
    "run_canon_capture",
    "maybe_capture_canon",
    "persist_capture_status",
]


async def persist_capture_status(pool, session_id, decision: "CaptureDecision") -> None:
    """WS-1.6 (spec 05 §Q7) — persist the per-turn capture decision on the session so the
    assistant home strip can render capture visibly ON or OFF *with a reason*
    ({"fire": bool, "reason": str}).

    The decision was computed and logged every turn but discarded by the caller. A status
    that is computed-but-not-surfaced is the silent-no-op "collecting" chip this repo has
    shipped twice — the home strip must be able to READ it, not just trust that capture is on.

    Best-effort, like capture itself (runs after RUN_FINISHED): a persist failure must never
    surface to the user or delay the next turn.
    """
    try:
        await pool.execute(
            "UPDATE chat_sessions SET capture_status = $2::jsonb WHERE session_id = $1::uuid",
            str(session_id),
            json.dumps({"fire": decision.fire, "reason": decision.reason}),
        )
    except Exception:  # noqa: BLE001 — best-effort; never break the turn
        logger.warning(
            "failed to persist capture_status for session %s", session_id, exc_info=True
        )

# asyncio only holds a WEAK reference to a running task. A capture can run for
# `canon_capture_timeout_s` (90s by default), so a bare `create_task(...)` whose Task object
# nobody keeps is eligible for garbage collection mid-flight — the capture would vanish
# silently, and only under memory pressure, which is the worst way to find a bug. Hold a
# strong reference until the task completes.
_pending: set[asyncio.Task] = set()


@dataclass(frozen=True)
class CaptureContext:
    """The three turn-scoped facts capture needs, resolved in `stream_response` and threaded
    into the post-turn block (which lives in a different function).

    `book_id` MUST be the book knowledge-service resolved from the session's own project —
    never the FE-supplied `editor_context.book_id`. It is None on a multi-project turn (a
    union of projects has no single book to capture into) and when grounding is off.
    """

    book_id: str | None
    project_enables: bool
    grounding_enabled: bool


@dataclass(frozen=True)
class CaptureDecision:
    """Why capture will or won't run this turn. `reason` is logged every turn — a setting
    whose effective value and source are invisible is the "silently-off" bug class."""

    fire: bool
    reason: str


def should_capture(
    *,
    deploy_allows: bool,
    project_enables: bool,
    grounding_enabled: bool,
    book_id: str | None,
    assistant_turn_count: int | None,
    exchange_chars: int,
    every_n_turns: int,
    min_chars: int,
) -> CaptureDecision:
    """The pure gate. `effective = AND(deploy ceiling, per-project user setting)`, then the
    cheap turn-shape conditions. Ordered most-decisive first so the logged reason names the
    single thing a user would have to change."""
    if not deploy_allows:
        return CaptureDecision(False, "deploy_ceiling_off")
    if not project_enables:
        return CaptureDecision(False, "project_setting_off")
    if not grounding_enabled:
        # The user turned grounding OFF for this turn. Capture is a WRITE into the same
        # knowledge layer they just opted out of, so we opt out too. Deliberate scope, not
        # an oversight — and stated here rather than left to fall out of the fact that chat
        # only resolves the book id on the grounding path.
        return CaptureDecision(False, "grounding_disabled")
    if not book_id:
        # No book ⇒ no glossary to capture into. A general (bookless) chat, a
        # multi-project turn, or an unresolved project all land here.
        return CaptureDecision(False, "no_book")
    if assistant_turn_count is None:
        return CaptureDecision(False, "no_turn_count")
    if every_n_turns <= 0 or assistant_turn_count % every_n_turns != 0:
        return CaptureDecision(False, "off_cadence")
    if exchange_chars < min_chars:
        # "ok", "go on", "yes" — nothing was established; don't spend a model call.
        return CaptureDecision(False, "exchange_too_short")
    return CaptureDecision(True, "fire")


def maybe_capture_canon(
    *,
    ctx: CaptureContext | None,
    user_id: str,
    assistant_turn_count: int | None,
    user_message: str,
    assistant_message: str,
    model_ref: str | None,
) -> CaptureDecision:
    """Decide, log, and — only if the gate says fire — spawn the capture task.

    stream_service's post-turn block calls exactly this, so the decision, the logging and
    the spawn are one testable unit rather than three lines buried in a 4000-line function.
    Returns the decision (the caller ignores it; the tests do not).

    `ctx is None` ⇒ the caller never resolved a capture context (today: the tool-confirm
    RESUME path, which rebuilds no knowledge context). Fail CLOSED — an unresolved context
    must never be read as "capture into whatever book".

    Settings are read HERE, not at import, so a test can patch the ceiling.
    """
    if ctx is None:
        logger.debug("canon capture: fire=False reason=no_capture_context")
        return CaptureDecision(False, "no_capture_context")
    decision = should_capture(
        deploy_allows=settings.canon_capture_enabled,
        project_enables=ctx.project_enables,
        grounding_enabled=ctx.grounding_enabled,
        book_id=ctx.book_id,
        assistant_turn_count=assistant_turn_count,
        exchange_chars=len(user_message) + len(assistant_message),
        every_n_turns=settings.canon_capture_every_n_turns,
        min_chars=settings.canon_capture_min_chars,
    )
    # Logged EVERY turn, fire or not: a setting whose effective value and source are
    # invisible is exactly the "grounding always-on / reasoning silently-off" bug class.
    logger.info(
        "canon capture: fire=%s reason=%s (deploy=%s project=%s book=%s turn=%s)",
        decision.fire, decision.reason, settings.canon_capture_enabled,
        ctx.project_enables, ctx.book_id, assistant_turn_count,
    )
    if decision.fire and ctx.book_id:
        task = asyncio.create_task(
            run_canon_capture(
                user_id=user_id,
                book_id=ctx.book_id,
                user_message=user_message,
                assistant_message=assistant_message,
                model_ref=model_ref,
            )
        )
        _pending.add(task)
        task.add_done_callback(_pending.discard)
    return decision


async def run_canon_capture(
    *,
    user_id: str,
    book_id: str,
    user_message: str,
    assistant_message: str,
    model_ref: str | None = None,
) -> None:
    """Fire one capture. Best-effort: never raises, never retries (the next cadence tick is
    the retry). Spawned via `asyncio.create_task` from the post-turn block."""
    cap = settings.canon_capture_max_chars_per_side
    exchange = f"User:\n{user_message[:cap]}\n\nAssistant:\n{assistant_message[:cap]}"
    try:
        result = await get_canon_capture_client().capture(
            book_id=book_id, owner_user_id=user_id, source_text=exchange, model_ref=model_ref,
        )
    except Exception:  # noqa: BLE001 — post-turn side effect; a failure must not escape
        logger.warning("canon capture failed for book %s", book_id, exc_info=True)
        return
    if result is None:
        return  # the client already logged the reason
    created = result.get("created") or []
    logger.info(
        "canon capture: book=%s created=%d skipped=%s failed=%s names=%s",
        book_id, len(created), result.get("skipped"), result.get("failed"),
        [c.get("name") for c in created][:10],
    )
