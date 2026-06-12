"""E0-3 Phase 2a — BYOK dual-identity resolution helpers (worker-ai).

The eff_* helpers pick the CALLER's billing identity at provider-call sites and
the OWNER's at every graph/storage site; assert_billing_complete is the fail-safe
that refuses to run a job whose billing identity is partial (which would charge
the owner's key for one of the two provider calls).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.runner import (
    BillingConfigError,
    JobRow,
    assert_billing_complete,
    eff_billing_user,
    eff_embed_ref,
    eff_llm_ref,
)


def _job(**overrides) -> JobRow:
    defaults = dict(
        job_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        scope="chapters",
        scope_range=None,
        status="running",
        llm_model="owner-llm-ref",
        embedding_model="owner-emb-ref",
        max_spend_usd=Decimal("10.00"),
        items_total=5,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=Decimal("0"),
    )
    defaults.update(overrides)
    return JobRow(**defaults)


# ── owner-triggered (billing NULL) ⇒ owner identity everywhere ────────


def test_eff_helpers_owner_path_returns_owner_identity():
    job = _job()
    assert eff_billing_user(job) == job.user_id
    assert eff_llm_ref(job) == "owner-llm-ref"
    assert eff_embed_ref(job) == "owner-emb-ref"


# ── collaborator (billing set) ⇒ caller identity at provider sites ────


def test_eff_helpers_collaborator_path_returns_billing_identity():
    collab = uuid4()
    job = _job(
        billing_user_id=collab,
        billing_llm_model="collab-llm-ref",
        billing_embedding_model="collab-emb-ref",
    )
    assert eff_billing_user(job) == collab
    assert eff_llm_ref(job) == "collab-llm-ref"
    assert eff_embed_ref(job) == "collab-emb-ref"
    # Graph partition + storage tag MUST stay the owner's, never the billing id.
    assert job.user_id != collab
    assert job.embedding_model == "owner-emb-ref"


def test_eff_ref_helpers_ignore_orphan_ref_without_billing_user():
    """review-impl MED-1: a billing REF without a billing_user_id is incoherent
    (the ref resolves under the owner). The resolvers gate on the IDENTITY, so an
    orphan ref is ignored and the owner's ref is used — staying consistent with
    the submit_and_wait contextvar (which keys off billing_user_id)."""
    job = _job(
        billing_user_id=None,
        billing_llm_model="orphan-llm",
        billing_embedding_model="orphan-emb",
    )
    assert eff_llm_ref(job) == "owner-llm-ref"
    assert eff_embed_ref(job) == "owner-emb-ref"
    assert eff_billing_user(job) == job.user_id


# ── fail-safe: partial billing identity must never run ────────────────


def test_assert_billing_complete_passes_for_owner_job():
    assert_billing_complete(_job())  # billing all None → no raise


def test_assert_billing_complete_passes_when_both_refs_present():
    assert_billing_complete(
        _job(
            billing_user_id=uuid4(),
            billing_llm_model="x",
            billing_embedding_model="y",
        )
    )


@pytest.mark.parametrize(
    "missing",
    [
        dict(billing_llm_model=None, billing_embedding_model="y"),
        dict(billing_llm_model="x", billing_embedding_model=None),
        dict(billing_llm_model=None, billing_embedding_model=None),
    ],
)
def test_assert_billing_complete_raises_on_partial_identity(missing):
    job = _job(billing_user_id=uuid4(), **missing)
    with pytest.raises(BillingConfigError):
        assert_billing_complete(job)
