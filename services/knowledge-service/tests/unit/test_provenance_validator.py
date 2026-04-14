"""K11.Z unit tests — provenance write validator.

Acceptance:
  - Every bad-input class rejected with a descriptive reason
  - Known-good inputs pass unchanged
  - 1000-sample fuzz pass: 1000 bad inputs → 1000 errors, 0 false negatives
  - Validator cost < 0.5ms per call (budget check)
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone

import pytest

from app.neo4j.provenance_validator import (
    ProvenanceValidationError,
    validate_provenance,
)


GOOD = {
    "source_refs": ["chunk_abc123", "chunk_def456"],
    "chapter_id": "chap_0001",
    "chunk_id": "chunk_abc123",
    "book_id": "book_42",
    "confidence": 0.87,
    "extracted_at": "2026-04-14T12:00:00Z",
    "extractor_version": "k15.pattern.v1",
    "trace_id": "trc_xyz",
}


# ── happy path ────────────────────────────────────────────────────────


def test_known_good_passes():
    validate_provenance(GOOD)  # no raise


def test_confidence_boundaries_accepted():
    validate_provenance({**GOOD, "confidence": 0.0})
    validate_provenance({**GOOD, "confidence": 1.0})


def test_extracted_at_accepts_datetime_object():
    validate_provenance(
        {**GOOD, "extracted_at": datetime.now(tz=timezone.utc)}
    )


def test_unknown_fields_pass_through():
    validate_provenance({**GOOD, "some_future_field": "whatever"})


# ── string sentinel rejections ────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        "[object Object]",
        "[OBJECT OBJECT]",
        "undefined",
        "null",
        "None",
        "NaN",
        "nan",
    ],
)
def test_sentinel_strings_rejected(bad):
    with pytest.raises(ProvenanceValidationError) as ei:
        validate_provenance({**GOOD, "chunk_id": bad})
    assert ei.value.field == "chunk_id"
    assert "sentinel" in ei.value.reason


def test_empty_string_rejected():
    with pytest.raises(ProvenanceValidationError, match="empty"):
        validate_provenance({**GOOD, "chunk_id": ""})


def test_whitespace_only_rejected():
    with pytest.raises(ProvenanceValidationError, match="empty"):
        validate_provenance({**GOOD, "chunk_id": "   \n\t"})


def test_python_repr_leak_rejected():
    bad = "<app.neo4j.writer.Writer object at 0x7f1234567890>"
    with pytest.raises(ProvenanceValidationError, match="repr leak"):
        validate_provenance({**GOOD, "chunk_id": bad})


def test_non_string_in_string_field_rejected():
    with pytest.raises(ProvenanceValidationError, match="not a string"):
        validate_provenance({**GOOD, "chunk_id": 42})


def test_none_in_string_field_rejected():
    with pytest.raises(ProvenanceValidationError, match="is None"):
        validate_provenance({**GOOD, "chunk_id": None})


# ── source_refs list rejections ───────────────────────────────────────


def test_source_refs_non_list_rejected():
    with pytest.raises(ProvenanceValidationError, match="not a list"):
        validate_provenance({**GOOD, "source_refs": "chunk_1"})


def test_source_refs_empty_list_rejected():
    with pytest.raises(ProvenanceValidationError, match="empty list"):
        validate_provenance({**GOOD, "source_refs": []})


def test_source_refs_indexed_error_location():
    with pytest.raises(ProvenanceValidationError) as ei:
        validate_provenance(
            {**GOOD, "source_refs": ["chunk_good", "[object Object]"]}
        )
    assert ei.value.field == "source_refs[1]"


def test_source_refs_none_element_rejected():
    with pytest.raises(ProvenanceValidationError) as ei:
        validate_provenance({**GOOD, "source_refs": ["chunk_good", None]})
    assert ei.value.field == "source_refs[1]"
    assert "is None" in ei.value.reason


# ── confidence rejections ─────────────────────────────────────────────


@pytest.mark.parametrize("bad", [-0.01, 1.01, -1.0, 2.0])
def test_confidence_out_of_range(bad):
    with pytest.raises(ProvenanceValidationError, match="outside"):
        validate_provenance({**GOOD, "confidence": bad})


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), float("-inf")]
)
def test_confidence_non_finite_rejected(bad):
    with pytest.raises(ProvenanceValidationError, match="non-finite"):
        validate_provenance({**GOOD, "confidence": bad})


def test_confidence_non_numeric_rejected():
    with pytest.raises(ProvenanceValidationError, match="not a number"):
        validate_provenance({**GOOD, "confidence": "0.8"})


def test_confidence_bool_rejected():
    # bool is a subclass of int in Python — explicitly reject.
    with pytest.raises(ProvenanceValidationError, match="not a number"):
        validate_provenance({**GOOD, "confidence": True})


# ── timestamp rejections ──────────────────────────────────────────────


def test_bad_iso_rejected():
    with pytest.raises(ProvenanceValidationError, match="ISO-8601"):
        validate_provenance({**GOOD, "extracted_at": "not a date"})


def test_empty_string_timestamp_rejected():
    with pytest.raises(ProvenanceValidationError, match="ISO-8601"):
        validate_provenance({**GOOD, "extracted_at": ""})


def test_timestamp_non_string_non_datetime_rejected():
    with pytest.raises(ProvenanceValidationError, match="not a datetime"):
        validate_provenance({**GOOD, "extracted_at": 1234567890})


# ── root-level shape ──────────────────────────────────────────────────


def test_non_dict_props_rejected():
    with pytest.raises(ProvenanceValidationError, match="not a dict"):
        validate_provenance("not a dict")  # type: ignore[arg-type]


# ── fuzz + budget ─────────────────────────────────────────────────────


def _bad_sample(rng: random.Random) -> dict:
    """Generate a provenance bag with exactly one bad field."""
    props = dict(GOOD)
    field = rng.choice(
        ["chunk_id", "chapter_id", "source_refs", "confidence", "extracted_at"]
    )
    if field == "source_refs":
        props[field] = rng.choice([[], "string-not-list", ["good", ""]])
    elif field == "confidence":
        props[field] = rng.choice([-0.1, 1.1, float("nan"), "0.9", True])
    elif field == "extracted_at":
        props[field] = rng.choice(["", "not-a-date", 42])
    else:
        props[field] = rng.choice(
            ["", "  ", "[object Object]", "undefined", "None", "NaN",
             "<x.Y object at 0xdeadbeef>", None, 42]
        )
    return props


def test_fuzz_1000_bad_inputs_all_rejected():
    rng = random.Random(42)
    rejected = 0
    for _ in range(1000):
        try:
            validate_provenance(_bad_sample(rng))
        except ProvenanceValidationError:
            rejected += 1
    assert rejected == 1000


def test_latency_budget_under_half_ms():
    # Warm up then measure average over many iterations.
    for _ in range(100):
        validate_provenance(GOOD)

    n = 10_000
    t0 = time.perf_counter()
    for _ in range(n):
        validate_provenance(GOOD)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    per_call_ms = elapsed_ms / n
    assert per_call_ms < 0.5, f"per-call {per_call_ms:.4f}ms exceeds 0.5ms budget"
