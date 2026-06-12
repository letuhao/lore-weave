"""E0-3 Phase 2a — extraction_jobs billing fields (unit, no DB).

The repo gains three additive BYOK billing columns. These tests lock:
  - `_row_to_job` round-trips the billing columns when present;
  - the model defaults them to None when ABSENT from a row — the list-SELECT
    paths (`list_active`, `list_all_for_user`) build their own column lists that
    do NOT include billing, and must keep validating;
  - `ExtractionJobCreate` accepts the caller's billing identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.repositories.extraction_jobs import (
    ExtractionJob,
    ExtractionJobCreate,
    _row_to_job,
)


def _base_row(**extra) -> dict:
    now = datetime.now(timezone.utc)
    row = dict(
        job_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        scope="chapters",
        scope_range=None,
        status="running",
        llm_model="owner-llm",
        embedding_model="owner-emb",
        max_spend_usd=None,
        items_total=None,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=0,
        started_at=None,
        paused_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
        error_message=None,
        campaign_id=None,
    )
    row.update(extra)
    return row


def test_row_to_job_roundtrips_billing_columns():
    collab = uuid4()
    job = _row_to_job(
        _base_row(
            billing_user_id=collab,
            billing_embedding_model="collab-emb",
            billing_llm_model="collab-llm",
        )
    )
    assert job.billing_user_id == collab
    assert job.billing_embedding_model == "collab-emb"
    assert job.billing_llm_model == "collab-llm"
    # Owner identity (partition + canonical tag) is untouched.
    assert job.embedding_model == "owner-emb"


def test_row_to_job_billing_absent_defaults_to_none():
    """list_active / list_all_for_user omit billing columns from their SELECT;
    the model must still validate (defaults None), not raise."""
    job = _row_to_job(_base_row())  # no billing_* keys at all
    assert job.billing_user_id is None
    assert job.billing_embedding_model is None
    assert job.billing_llm_model is None


def test_create_payload_accepts_billing_identity():
    payload = ExtractionJobCreate(
        project_id=uuid4(),
        scope="chapters",
        llm_model="owner-llm",
        embedding_model="owner-emb",
        billing_user_id=uuid4(),
        billing_embedding_model="collab-emb",
        billing_llm_model="collab-llm",
    )
    assert payload.billing_user_id is not None
    assert payload.billing_embedding_model == "collab-emb"


def test_create_payload_billing_optional():
    payload = ExtractionJobCreate(
        project_id=uuid4(),
        scope="chapters",
        llm_model="owner-llm",
        embedding_model="owner-emb",
    )
    assert payload.billing_user_id is None
    assert payload.billing_llm_model is None


def test_extraction_job_model_billing_defaults():
    """Direct model construction (e.g. fixtures) defaults billing to None."""
    job = ExtractionJob(
        job_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        scope="chapters",
        status="running",
        llm_model="m",
        embedding_model="e",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert job.billing_user_id is None
