"""C11 — unit tests for the cursor codec used by
``ExtractionJobsRepo.list_all_for_user``.

The SQL-level pagination is exercised by integration tests against a
real Postgres. These unit tests cover the codec (pure functions) +
the public exception type that surfaces as router 422.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.db.repositories.extraction_jobs import (
    CursorDecodeError,
    _decode_cursor,
    _encode_cursor,
)


_JOB_ID = UUID("01957000-7000-7000-8000-000000000001")
_CREATED = datetime(2026, 4, 1, 12, 30, 45, 123000, tzinfo=timezone.utc)
_COMPLETED = datetime(2026, 4, 2, 8, 15, 0, 456000, tzinfo=timezone.utc)


def test_roundtrip_with_completed_at():
    """Encoding + decoding produces the exact same tuple for the
    common history case (completed_at present)."""
    raw = _encode_cursor(
        completed_at=_COMPLETED, created_at=_CREATED, job_id=_JOB_ID,
    )
    c, r, j = _decode_cursor(raw)
    assert c == _COMPLETED
    assert r == _CREATED
    assert j == _JOB_ID


def test_roundtrip_with_null_completed_at():
    """Active group encoding: completed_at is None. Codec preserves
    the null so the history seek predicate can treat it correctly."""
    raw = _encode_cursor(
        completed_at=None, created_at=_CREATED, job_id=_JOB_ID,
    )
    c, r, j = _decode_cursor(raw)
    assert c is None
    assert r == _CREATED
    assert j == _JOB_ID


def test_decode_rejects_invalid_base64():
    """Garbled payloads surface as CursorDecodeError so the router
    can 422 instead of crashing."""
    with pytest.raises(CursorDecodeError):
        _decode_cursor("!@#$%^not-valid-base64")


def test_decode_rejects_non_object_payload():
    """Payload must be a JSON object — bare lists / strings are
    rejected."""
    import base64
    bad = base64.urlsafe_b64encode(b'["not", "an", "object"]').decode("ascii")
    with pytest.raises(CursorDecodeError):
        _decode_cursor(bad)


def test_decode_rejects_missing_required_fields():
    """Missing 'r' or 'j' keys fail fast — better than silently
    producing None tiebreaks that would skip rows."""
    import base64
    bad = base64.urlsafe_b64encode(b'{"c": null}').decode("ascii")
    with pytest.raises(CursorDecodeError):
        _decode_cursor(bad)


def test_decode_rejects_bad_uuid():
    """job_id field that isn't a valid UUID → CursorDecodeError."""
    import base64
    bad = base64.urlsafe_b64encode(
        b'{"c": null, "r": "2026-04-01T12:30:00", "j": "not-a-uuid"}',
    ).decode("ascii")
    with pytest.raises(CursorDecodeError):
        _decode_cursor(bad)


def test_decode_rejects_bad_datetime():
    """Malformed ISO timestamp → CursorDecodeError instead of a
    deep traceback."""
    import base64
    bad = base64.urlsafe_b64encode(
        b'{"c": null, "r": "not-a-date", "j": "'
        + str(_JOB_ID).encode()
        + b'"}',
    ).decode("ascii")
    with pytest.raises(CursorDecodeError):
        _decode_cursor(bad)
