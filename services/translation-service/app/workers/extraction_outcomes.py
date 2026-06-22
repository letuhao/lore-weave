"""Extraction batch-outcome taxonomy (OBS/M2 — INV-F15, INV-O12/13).

The 26-scenario bug in one sentence: a batch that returned 15 entities then had ALL of
them rejected (kind mismatch), or that truncated mid-array, or that errored — all read as
a clean "0 entities, chapter completed". There was no taxonomy distinguishing *legitimately
empty* from *failed*, so total failure was invisible.

This module classifies each batch into a closed status set and derives the chapter status
from its batches. The outcome rows these statuses key are the OBSERVE SSOT (events are a
same-txn projection of them); a reconciliation sweep re-derives job stats from the rows.

Status taxonomy (architecture rev 2 §8.3 / detailed-design §2.3, §4 INV-F15):
    ok                 — produced ≥1 validated entity, clean finish
    empty_valid        — the model correctly returned an empty array (nothing to extract)
    truncated          — finish_reason=length: output cut mid-array, entities LOST
    validation_rejected— produced output but nothing usable (all rejected / unparseable)
    llm_error          — the LLM call itself failed (transient/permanent SDK error, non-completion)
    writeback_failed   — chapter-level: the glossary writeback POST did not land
"""
from __future__ import annotations

import hashlib

OK = "ok"
EMPTY_VALID = "empty_valid"
TRUNCATED = "truncated"
VALIDATION_REJECTED = "validation_rejected"
LLM_ERROR = "llm_error"
WRITEBACK_FAILED = "writeback_failed"

# The statuses that mean "this batch is clean" — a chapter is `completed` only if ALL its
# batches are in this set (INV-F15). Anything else makes the chapter completed_with_errors.
_CLEAN = frozenset({OK, EMPTY_VALID})


def classify_batch(
    *,
    llm_errored: bool,
    parse_ok: bool,
    raw_entity_count: int,
    validated_count: int,
    finish_reason: str | None,
) -> str:
    """Classify one batch's outcome from the signals the worker holds.

    Precedence is deliberate (most-severe / most-informative first):
      1. ``llm_errored``           → the call never produced usable output.
      2. ``finish_reason=='length'``→ TRUNCATED even if some entities were salvaged, because
         later entities were dropped — truncation must not masquerade as ``ok``.
      3. parse failed (no array)   → VALIDATION_REJECTED (unusable output, clean finish).
      4. raw array empty           → EMPTY_VALID (the model correctly found nothing).
      5. raw>0 but none validated  → VALIDATION_REJECTED (all entries rejected).
      6. otherwise                 → OK.
    """
    if llm_errored:
        return LLM_ERROR
    if finish_reason == "length":
        return TRUNCATED
    if not parse_ok:
        return VALIDATION_REJECTED
    if raw_entity_count == 0:
        return EMPTY_VALID
    if validated_count == 0:
        return VALIDATION_REJECTED
    return OK


def chapter_status_from_outcomes(batch_statuses: list[str]) -> str:
    """Derive the chapter status from its batch statuses (INV-F15).

    A chapter with NO batches (no text / all batches skipped before producing an outcome)
    is treated as ``empty_valid`` — nothing to extract is not a failure. A chapter is
    ``completed`` only when EVERY batch is clean ({ok, empty_valid}); otherwise it is
    ``completed_with_errors`` so a silent all-rejected/truncated chapter is no longer
    indistinguishable from a clean one.
    """
    if not batch_statuses:
        return "completed"
    if all(s in _CLEAN for s in batch_statuses):
        return "completed"
    return "completed_with_errors"


def is_clean(status: str) -> bool:
    """True if a batch status counts as clean for the chapter-completion gate."""
    return status in _CLEAN


def reconcile_from_rows(rows: list[tuple]) -> dict:
    """Re-derive a job's stats from its outcome SSOT rows (INV-O12: the rows are truth, the
    counters on extraction_jobs are a cache a mid-update crash can skew). ``rows`` is an
    iterable of ``(chapter_id, status)`` pairs. A chapter is completed only if ALL its
    batches are clean (same gate as `chapter_status_from_outcomes`), so the re-derivation
    can detect + correct a job row that drifted from the batch truth.
    """
    by_status: dict[str, int] = {}
    chapters: dict[str, list[str]] = {}
    for chapter_id, status in rows:
        by_status[status] = by_status.get(status, 0) + 1
        chapters.setdefault(str(chapter_id), []).append(status)
    chapters_completed = sum(1 for ss in chapters.values() if all(is_clean(s) for s in ss))
    return {
        "batches_total": sum(by_status.values()),
        "by_status": by_status,
        "chapters_total": len(chapters),
        "chapters_completed": chapters_completed,
        "chapters_with_errors": len(chapters) - chapters_completed,
    }


def compute_event_id(job_id: str, chapter_id: str, batch_idx: int, content_hash: str) -> str:
    """Redelivery-stable event id (INV-O13): the same (job, chapter, batch, content) always
    hashes to the same id, so a consumer dedups a redelivered projection before aggregating,
    and the SSOT row's UNIQUE(event_id) makes re-recording an idempotent no-op."""
    return hashlib.sha256(
        "|".join([str(job_id), str(chapter_id), str(batch_idx), content_hash]).encode("utf-8")
    ).hexdigest()
