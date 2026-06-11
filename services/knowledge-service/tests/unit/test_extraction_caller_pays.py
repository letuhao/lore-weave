"""E0-3 Phase 2b — caller-pays extraction route (collaborator dual identity).

When a book collaborator (caller != owner) starts extraction, the route must:
  - dimension-guard the caller's embedding ref against the project's vector space
    (409 on mismatch / unresolved / project-unconfigured);
  - persist billing_* = the caller's identity, but store embedding_model = the
    project's canonical tag (search filter), NOT the caller's ref;
  - keep the benchmark gate owner/project-scoped (the project's model);
  - debit the CALLER's monthly budget (their key pays), while the project budget
    stays the owner's.
Owner path (caller None or == owner) ⇒ billing NULL (legacy single identity).

Tests call ``_start_extraction_job_core`` directly with mocked repos + a patched
pool so the inline INSERT args can be asserted.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.clients.embedding_client import EmbeddingError
from app.db.models import Project
from app.db.repositories.extraction_jobs import ExtractionJob
from app.jobs.budget import BudgetCheck
from app.routers.public import extraction as ext

_OWNER = uuid4()
_COLLAB = uuid4()
_PROJECT = uuid4()
_JOB = uuid4()
_PROJECT_EMB = "project-canonical-emb"   # owner's ref == project's tag
_PROJECT_DIM = 1024


def _project(**ov) -> Project:
    base = dict(
        project_id=_PROJECT, user_id=_OWNER, name="P", description="",
        project_type="translation", book_id=uuid4(), instructions="",
        extraction_enabled=False, extraction_status="disabled",
        embedding_model=_PROJECT_EMB, embedding_dimension=_PROJECT_DIM,
        extraction_config={}, estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"), is_archived=False, version=1,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    base.update(ov)
    return Project(**base)


def _job_stub() -> ExtractionJob:
    return ExtractionJob(
        job_id=_JOB, user_id=_OWNER, project_id=_PROJECT, scope="all",
        status="running", llm_model="m", embedding_model=_PROJECT_EMB,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


def _body(embedding_model="collab-emb-ref", llm_model="collab-llm-ref"):
    return ext.StartJobRequest(
        scope="all", llm_model=llm_model, embedding_model=embedding_model,
        max_spend_usd=Decimal("10.00"),
    )


def _repos(project):
    pr = AsyncMock()
    pr.get = AsyncMock(return_value=project)
    pr.set_extraction_state = AsyncMock(return_value=project)
    jr = AsyncMock()
    jr.list_active = AsyncMock(return_value=[])
    jr.get = AsyncMock(return_value=_job_stub())
    br = AsyncMock()
    br.get_latest = AsyncMock(return_value=MagicMock(passed=True, run_id="r", recall_at_3=0.9))
    return pr, jr, br


@asynccontextmanager
async def _noop_ctx(*a, **k):
    yield


def _patched_pool():
    """Mock pool whose conn.fetchrow records the INSERT args."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"job_id": _JOB})
    conn.execute = AsyncMock()
    conn.transaction = _noop_ctx
    pool = MagicMock()
    pool.acquire = lambda: _noop_ctx_conn(conn)
    return pool, conn


def _noop_ctx_conn(conn):
    @asynccontextmanager
    async def _cm():
        yield conn
    return _cm()


async def _run_core(*, project, caller, body=None, dim=_PROJECT_DIM, dim_exc=None):
    pr, jr, br = _repos(project)
    pool, conn = _patched_pool()
    probe = AsyncMock(side_effect=dim_exc) if dim_exc else AsyncMock(return_value=dim)
    allowed = BudgetCheck(allowed=True, reason="ok")
    with patch.object(ext, "get_knowledge_pool", return_value=pool), \
         patch.object(ext, "probe_embedding_dimension", probe), \
         patch.object(ext, "can_start_job", AsyncMock(return_value=allowed)), \
         patch.object(ext, "check_user_monthly_budget", AsyncMock(return_value=allowed)) as user_budget:
        job = await ext._start_extraction_job_core(
            _PROJECT, body or _body(), _OWNER, pr, jr, br, caller=caller,
        )
    return job, conn, user_budget, probe


def _insert_args(conn):
    """The INSERT is the fetchrow call whose query contains INSERT INTO."""
    for call in conn.fetchrow.call_args_list:
        if "INSERT INTO extraction_jobs" in call.args[0]:
            return call.args
    raise AssertionError("INSERT not called")


# ── collaborator happy path ───────────────────────────────────────────


async def test_collaborator_persists_billing_and_project_storage_tag():
    _job, conn, user_budget, probe = await _run_core(project=_project(), caller=_COLLAB)
    args = _insert_args(conn)
    # args: query, user_id(owner), project_id, scope, scope_range, llm_model,
    #       embedding_model(STORAGE), max_spend, items_total, campaign_id,
    #       billing_user_id, billing_embedding_model, billing_llm_model
    assert args[1] == _OWNER                       # partition stays the owner
    assert args[6] == _PROJECT_EMB                 # STORED tag = project's canonical
    assert args[10] == _COLLAB                     # billing_user_id = caller
    assert args[11] == "collab-emb-ref"            # billing embedding = caller's ref
    assert args[12] == "collab-llm-ref"            # billing llm = caller's ref
    # dimension probed under the CALLER's credentials
    assert probe.await_args.args[0] == _COLLAB
    # the caller's monthly budget is the one debited
    assert user_budget.await_args.args[1] == _COLLAB


async def test_collaborator_dimension_mismatch_409():
    with pytest.raises(HTTPException) as exc:
        await _run_core(project=_project(), caller=_COLLAB, dim=768)  # != 1024
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "embedding_model_mismatch"


async def test_collaborator_unresolved_ref_409():
    with pytest.raises(HTTPException) as exc:
        await _run_core(
            project=_project(), caller=_COLLAB,
            dim_exc=EmbeddingError("no such model", retryable=False),
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "embedding_model_unresolved"


async def test_collaborator_project_without_embedding_409():
    with pytest.raises(HTTPException) as exc:
        await _run_core(
            project=_project(embedding_model=None, embedding_dimension=None),
            caller=_COLLAB,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "project_embedding_unconfigured"


# ── owner path: billing stays NULL ────────────────────────────────────


@pytest.mark.parametrize("caller", [None, _OWNER])
async def test_owner_path_billing_null(caller):
    body = _body(embedding_model=_PROJECT_EMB, llm_model="owner-llm")
    _job, conn, user_budget, probe = await _run_core(
        project=_project(), caller=caller, body=body,
    )
    args = _insert_args(conn)
    assert args[6] == _PROJECT_EMB        # storage tag = body's (== project's)
    assert args[10] is None               # billing_user_id NULL
    assert args[11] is None
    assert args[12] is None
    probe.assert_not_awaited()            # no dimension guard on the owner path
    assert user_budget.await_args.args[1] == _OWNER  # owner's wallet
