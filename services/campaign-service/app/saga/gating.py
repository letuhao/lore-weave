"""Saga gating — the load-bearing pure logic of S1.

`next_dispatches(...)` decides which `(chapter, stage)` work to dispatch on a
reconcile tick, given a campaign's gating mode and its per-chapter projection.
It is a **pure function** (no DB, no I/O) so the dispatch policy — the part most
likely to harbour a costly bug (double-dispatch = double-spend) — is exhaustively
unit-testable in isolation.

Two gating modes (decision B, PO-locked):

  * **phase_barrier** — highest quality. Hold ALL translation until EVERY
    in-scope chapter's knowledge stage is *settled* (done|skipped, or
    permanently failed) so the glossary is stable before any chapter is
    translated.
  * **cold_start** — interleaved. A chapter's translation may start as soon as
    *that chapter's* knowledge stage is terminal-success, without waiting for
    the rest of the book (lower quality, bootstraps the glossary as it goes).

Stage-status vocabulary: `pending | dispatched | done | failed | skipped`.

Predicates (decision J — the projection is the single source of truth):
  * **terminal-success** (`done|skipped`) — a chapter's predecessor reached this
    before its dependent stage may run.
  * **settled** — terminal-success, OR `failed` with attempts exhausted. A
    settled stage will see no more work; a `failed` row with retries remaining
    is NOT settled (the driver will re-dispatch it).
  * Only `pending` or `failed` (with attempts remaining) stages are dispatched;
    `dispatched|done|skipped` are never re-dispatched.
  * `eval` is OBSERVED (rides `translation.quality`), never dispatched.
"""

from __future__ import annotations

from dataclasses import dataclass

_TERMINAL_SUCCESS = {"done", "skipped"}
_DISPATCHABLE = {"pending", "failed"}


@dataclass(frozen=True)
class ChapterState:
    """Minimal projection slice the gate reasons over (one campaign_chapters row)."""
    chapter_id: str
    knowledge_status: str
    translation_status: str
    knowledge_attempts: int
    translation_attempts: int


@dataclass(frozen=True)
class Dispatch:
    """A single unit of work to dispatch: run `stage` for `chapter_id`."""
    chapter_id: str
    stage: str  # "knowledge" | "translation"


@dataclass(frozen=True)
class StageFailure:
    """A `(chapter, stage)` that has exhausted its attempts — caller marks failed."""
    chapter_id: str
    stage: str


@dataclass(frozen=True)
class GatingResult:
    dispatches: list[Dispatch]
    exhausted: list[StageFailure]


def _is_settled(status: str, attempts: int, max_attempts: int) -> bool:
    """No more work will happen for this stage."""
    if status in _TERMINAL_SUCCESS:
        return True
    if status == "failed" and attempts >= max_attempts:
        return True
    return False


def _is_dispatchable(status: str, attempts: int, max_attempts: int) -> bool:
    return status in _DISPATCHABLE and attempts < max_attempts


def _knowledge_barrier_open(states: list[ChapterState], max_attempts: int) -> bool:
    """phase_barrier readiness: every chapter's knowledge stage is settled."""
    return all(
        _is_settled(s.knowledge_status, s.knowledge_attempts, max_attempts)
        for s in states
    )


def next_dispatches(
    *,
    gating_mode: str,
    chapters: list[ChapterState],
    stages: list[str],
    max_attempts: int,
    max_inflight: int,
) -> GatingResult:
    """Compute the dispatches for one reconcile tick.

    `stages` is the campaign's stage list (e.g. ['knowledge','translation','eval']);
    a stage absent from it is never dispatched. `max_inflight` bounds the number
    of dispatches returned per tick (S1's simple fairness window; S3 adds the
    real per-provider governor). A negative `max_inflight` means unbounded.
    """
    want_knowledge = "knowledge" in stages
    want_translation = "translation" in stages

    dispatches: list[Dispatch] = []
    exhausted: list[StageFailure] = []

    # ── knowledge stage ──────────────────────────────────────────────────
    if want_knowledge:
        for s in chapters:
            if s.knowledge_status not in _DISPATCHABLE:
                continue
            if s.knowledge_attempts >= max_attempts:
                exhausted.append(StageFailure(s.chapter_id, "knowledge"))
            else:
                dispatches.append(Dispatch(s.chapter_id, "knowledge"))

    # ── translation stage ────────────────────────────────────────────────
    if want_translation:
        barrier_open = (not want_knowledge) or _knowledge_barrier_open(
            chapters, max_attempts
        )
        for s in chapters:
            if s.translation_status not in _DISPATCHABLE:
                continue
            # Translation depends on THIS chapter's knowledge being done.
            if want_knowledge and s.knowledge_status not in _TERMINAL_SUCCESS:
                continue
            # phase_barrier additionally holds until the WHOLE book is settled.
            if gating_mode == "phase_barrier" and not barrier_open:
                continue
            if s.translation_attempts >= max_attempts:
                exhausted.append(StageFailure(s.chapter_id, "translation"))
            else:
                dispatches.append(Dispatch(s.chapter_id, "translation"))

    if max_inflight >= 0:
        dispatches = dispatches[:max_inflight]
    return GatingResult(dispatches=dispatches, exhausted=exhausted)


def is_complete(*, chapters: list[ChapterState], stages: list[str], max_attempts: int) -> bool:
    """True when every in-scope chapter is settled for every dispatchable stage
    (knowledge/translation). eval is advisory. A campaign with zero chapters is
    trivially complete."""
    want_knowledge = "knowledge" in stages
    want_translation = "translation" in stages
    for s in chapters:
        if want_knowledge and not _is_settled(
            s.knowledge_status, s.knowledge_attempts, max_attempts
        ):
            return False
        if want_translation and not _is_settled(
            s.translation_status, s.translation_attempts, max_attempts
        ):
            return False
    return True
