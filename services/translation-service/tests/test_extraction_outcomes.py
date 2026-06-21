"""Tests for the OBS/M2 batch-outcome taxonomy (INV-F15, INV-O12/13).

The bug these guard against: a batch that returned entities then had them all rejected, or
truncated mid-array, or errored, all read as a clean "0 entities, chapter completed". The
taxonomy + chapter-status derivation make those states distinct and visible.
"""
from app.workers.extraction_outcomes import (
    EMPTY_VALID,
    LLM_ERROR,
    OK,
    TRUNCATED,
    VALIDATION_REJECTED,
    chapter_status_from_outcomes,
    classify_batch,
    compute_event_id,
    reconcile_from_rows,
)


def test_classify_ok():
    assert classify_batch(llm_errored=False, parse_ok=True, raw_entity_count=3,
                          validated_count=3, finish_reason="stop") == OK


def test_classify_empty_valid():
    # Model returned an empty array — legitimately nothing to extract.
    assert classify_batch(llm_errored=False, parse_ok=True, raw_entity_count=0,
                          validated_count=0, finish_reason="stop") == EMPTY_VALID


def test_classify_validation_rejected_all_filtered():
    # Model returned 5 entities; all rejected (kind mismatch) → NOT empty_valid.
    assert classify_batch(llm_errored=False, parse_ok=True, raw_entity_count=5,
                          validated_count=0, finish_reason="stop") == VALIDATION_REJECTED


def test_classify_validation_rejected_unparseable():
    # Clean finish but no JSON array could be parsed → unusable output.
    assert classify_batch(llm_errored=False, parse_ok=False, raw_entity_count=0,
                          validated_count=0, finish_reason="stop") == VALIDATION_REJECTED


def test_truncated_wins_even_with_salvaged_entities():
    # finish=length means later entities were LOST — must not read as ok.
    assert classify_batch(llm_errored=False, parse_ok=True, raw_entity_count=4,
                          validated_count=4, finish_reason="length") == TRUNCATED


def test_llm_error_takes_precedence():
    assert classify_batch(llm_errored=True, parse_ok=False, raw_entity_count=0,
                          validated_count=0, finish_reason=None) == LLM_ERROR


def test_chapter_status_all_clean_is_completed():
    assert chapter_status_from_outcomes([OK, EMPTY_VALID, OK]) == "completed"


def test_chapter_status_any_dirty_is_with_errors():
    assert chapter_status_from_outcomes([OK, VALIDATION_REJECTED]) == "completed_with_errors"
    assert chapter_status_from_outcomes([TRUNCATED]) == "completed_with_errors"
    assert chapter_status_from_outcomes([LLM_ERROR, OK]) == "completed_with_errors"


def test_chapter_status_no_batches_is_completed():
    # Nothing to extract (no batches produced an outcome) is not a failure.
    assert chapter_status_from_outcomes([]) == "completed"


def test_event_id_is_stable_and_distinct():
    a = compute_event_id("job", "chap", 0, "hash1")
    b = compute_event_id("job", "chap", 0, "hash1")
    c = compute_event_id("job", "chap", 1, "hash1")  # different batch
    d = compute_event_id("job", "chap", 0, "hash2")  # different content
    assert a == b           # redelivery-stable (INV-O13)
    assert a != c and a != d


def test_reconcile_from_rows_rederives_chapter_completion():
    # chapter A: 2 clean batches → completed. chapter B: 1 clean + 1 truncated → with-errors.
    rows = [
        ("A", OK), ("A", EMPTY_VALID),
        ("B", OK), ("B", TRUNCATED),
    ]
    stats = reconcile_from_rows(rows)
    assert stats["batches_total"] == 4
    assert stats["chapters_total"] == 2
    assert stats["chapters_completed"] == 1   # only A is all-clean
    assert stats["chapters_with_errors"] == 1
    assert stats["by_status"][OK] == 2
    assert stats["by_status"][TRUNCATED] == 1
