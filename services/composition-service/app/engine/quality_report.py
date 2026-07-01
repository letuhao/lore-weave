"""Quality Report — surface the planner's advisory judges to the author.

The composition auto-loop already runs `critic` (4-dim craft/continuity) and, per
scene, several other advisory judges — but their output is stashed in
`generation_job.result["_critic"]` and never shown as an actionable, chapter-level
report. And `promise_audit` (does the draft PAY OFF what it set up?) is never run
at all outside the offline eval.

This thin orchestrator runs the two chapter-scopeable judges FRESH over one
assembled chapter and shapes a single read-only report for the M6 Polish gate:

- `critic.judge_prose`   → coherence / voice_match / pacing / canon_consistency + violations
- `promise_audit.audit_promises` → introduced / resolved / dropped promises + dropped_rate

Design (see docs/plans/2026-07-01-quality-report-polish-gate.md):
- **Diagnostic, never applyable.** Promises are phrases (no located span) and critic
  scores are not edits, so the report informs the author — it is NOT a self-heal
  EditProposal and carries no accept/apply affordance (do-no-harm preserved).
- **Fresh, not scraped.** Re-running the critic over the current chapter is correct
  (historical per-scene `_critic` goes stale after edits/stitch) and cheap on a
  local judge model.
- **Degrade-safe.** Both underlying engines already return an empty shape + `error`
  on any LLM/parse failure and never raise; a failure in one leaves the other intact.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.clients.llm_client import LLMClient
from app.engine.critic import judge_prose
from app.engine.promise_audit import (
    _coverage_shape,
    audit_promises,
    extract_tracked_promises,
    score_promise_coverage,
)
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

_CRITIC_DIMS = ("coherence", "voice_match", "pacing", "canon_consistency")


def _empty_critic(err: str = "critic_error") -> dict[str, Any]:
    return {**{d: None for d in _CRITIC_DIMS}, "violations": [], "error": err}


def _empty_promises(err: str = "audit_error") -> dict[str, Any]:
    return {"introduced": [], "resolved": [], "dropped": [], "introduced_count": 0,
            "resolved_count": 0, "dropped_count": 0, "dropped_rate": 0.0, "error": err}


async def _degrade_safe(coro: Awaitable[dict[str, Any]], fallback: dict[str, Any],
                        label: str) -> dict[str, Any]:
    """Await `coro`, coercing an UNEXPECTED exception to `fallback` so one judge's
    failure can't sink the other in the gather. The two engines already handle
    `LLMError` + non-completed status gracefully; this backstops a rarer raise
    (e.g. a malformed completed result parsed outside their try). `CancelledError`
    (BaseException) is deliberately NOT caught, so a real cancel still aborts."""
    try:
        return await coro
    except Exception:  # noqa: BLE001 — advisory; the report degrades, never raises
        logger.warning("quality_report %s judge degraded (unexpected error)", label,
                       exc_info=True)
        return fallback


async def build_quality_report(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    chapter: str, source_language: str = "auto", canon: str | None = None,
    max_tokens_critic: int = 1536, max_tokens_promise: int = 1500,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Run the two chapter-level advisory judges concurrently and shape one report.

    `canon` (the rendered story bible) grounds the critic's `canon_consistency`
    dimension as an established-facts block. Both judges are degrade-safe: this
    never raises for an LLM/parse failure — the failing half returns its empty
    shape with an `error` marker and the report still comes back."""
    profile = BookProfile(source_language=source_language)
    # canon is a rendered multi-line bible; hand it to the critic as a single
    # established-fact so `canon_consistency` has grounding (no structured rules here).
    present_facts = [canon.strip()] if canon and canon.strip() else []

    critic, promises = await asyncio.gather(
        _degrade_safe(
            judge_prose(
                llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                passage=chapter, active_rules=[], present_facts=present_facts,
                profile=profile, max_tokens=max_tokens_critic, trace_id=trace_id,
                cancel_check=cancel_check,
            ),
            _empty_critic(), "critic",
        ),
        _degrade_safe(
            audit_promises(
                llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                arc_text=chapter, source_language=source_language,
                max_tokens=max_tokens_promise, trace_id=trace_id, cancel_check=cancel_check,
            ),
            _empty_promises(), "promises",
        ),
    )
    return {"critic": critic, "promises": promises}


def _empty_coverage(err: str = "coverage_error") -> dict[str, Any]:
    return {"coverage": [], "tracked_count": 0, "introduced_count": 0, "paid_count": 0,
            "progressing_count": 0, "abandoned_count": 0, "absent_count": 0,
            "pay_rate": 0.0, "sustained_rate": 0.0, "abandon_rate": 0.0, "error": err}


# The whole assembled book overflows a single score call on a real multi-chapter book
# (D-QUALITY-COVERAGE-CHUNK, confirmed by E2E: score returned `coverage_unavailable` → all
# "absent" on the 12-ch book). So we WINDOW the prose and score each window against the SAME
# fixed promise set, then merge per-promise by the STRONGEST engagement seen anywhere in the
# book: paid (resolved somewhere) > progressing (still live) > abandoned (dropped) > absent.
_COVERAGE_WINDOW_CHARS = 12000
_VERDICT_RANK = {"absent": 0, "abandoned": 1, "progressing": 2, "paid": 3}


def _split_windows(text: str, budget: int) -> list[str]:
    """Split prose into ≤`budget`-char windows on paragraph boundaries (the endpoint joins
    chapters with a blank line, so windows are chapter/paragraph-aligned). A single paragraph
    larger than the budget becomes its own (over-budget) window rather than being cut mid-line."""
    paras = text.split("\n\n")
    windows: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paras:
        if cur and cur_len + len(p) > budget:
            windows.append("\n\n".join(cur))
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += len(p) + 2
    if cur:
        windows.append("\n\n".join(cur))
    return windows or [text]


async def _score_windowed(llm, *, user_id, model_source, model_ref, promises, windows,
                          source_language, trace_id, cancel_check) -> dict[str, Any]:
    """Score the fixed promise set against each window and merge by strongest engagement.
    A window that degrades (its own `error`) contributes nothing; if EVERY window degrades
    the whole thing is `coverage_unavailable` (honest — no fabricated verdicts)."""
    best: dict[str, str] = {p: "absent" for p in promises}
    any_ok = False
    for w in windows:
        cov = await score_promise_coverage(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            promises=promises, arc_text=w, source_language=source_language,
            trace_id=trace_id, cancel_check=cancel_check)
        if cov.get("error"):
            continue
        any_ok = True
        for item in cov.get("coverage", []):
            p, v = item.get("promise"), item.get("verdict")
            if p in best and _VERDICT_RANK.get(v, 0) > _VERDICT_RANK[best[p]]:
                best[p] = v
    if not any_ok:
        return _coverage_shape(promises, ["absent"] * len(promises), error="coverage_unavailable")
    return _coverage_shape(promises, [best[p] for p in promises])


async def build_promise_coverage(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    premise: str, plan_text: str, book_text: str, source_language: str = "auto",
    window_chars: int = _COVERAGE_WINDOW_CHARS,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict[str, Any]:
    """Book/arc-level promise coverage (promise_audit v2). Derives a STABLE tracked-promise
    set from the SPEC (premise + rendered outline plan — NOT the prose, so it doesn't reward
    a book for merely surfacing more promises), then scores the assembled book prose against
    that fixed set: paid / progressing / abandoned / absent per promise + pay/sustained/abandon
    rates. Answers "does the finished book pay off what the outline promised?" — the book-level
    sibling of the per-chapter dropped-promise audit.

    Degrade-safe: `extract_tracked_promises` returns [] on failure ⇒ `score_promise_coverage`
    returns its no-tracked-promises shape; an unexpected raise (the narrow parse window the
    underlying `_chat` leaves) degrades to the empty-coverage shape. `CancelledError`
    (BaseException) still propagates, so a real cancel aborts."""
    try:
        promises = await extract_tracked_promises(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            premise=premise, plan_text=plan_text, source_language=source_language,
            trace_id=trace_id, cancel_check=cancel_check)
        if not promises:
            # no spec promises → the shape's no-tracked path (score handles [] the same way)
            return _coverage_shape([], [], error="no_tracked_promises")
        windows = _split_windows(book_text, window_chars)
        if len(windows) <= 1:
            # small book — one score call, no windowing overhead
            return await score_promise_coverage(
                llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
                promises=promises, arc_text=book_text, source_language=source_language,
                trace_id=trace_id, cancel_check=cancel_check)
        return await _score_windowed(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            promises=promises, windows=windows, source_language=source_language,
            trace_id=trace_id, cancel_check=cancel_check)
    except Exception:  # noqa: BLE001 — advisory; degrade, never raise (cancel still propagates)
        logger.warning("promise_coverage degraded (unexpected error)", exc_info=True)
        return _empty_coverage()
