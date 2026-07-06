"""Internal dispatch endpoint — Auto-Draft Factory S1 (decision A).

Verifies the thin internal wrapper reuses the public start core, supplies the
project's embedding_model + the campaign's LLM model_ref, builds the
knowledge-side scope_range shape, and enforces the asserted-user/precondition
guards. Calls the handler directly with mocked repos (no app lifespan).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.routers.internal_dispatch import (
    dispatch_extraction,
    dispatch_cancel_extraction,
    dispatch_extraction_status,
    set_campaign_models,
    InternalExtractionPayload,
    InternalCancelPayload,
    SetCampaignModelsPayload,
)
from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS

_GOOD_DIM = next(iter(SUPPORTED_PASSAGE_DIMS))
EMB = UUID("44444444-4444-4444-4444-444444444444")
RR = UUID("55555555-5555-5555-5555-555555555555")

USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PROJ = UUID("99999999-9999-9999-9999-999999999999")
MODEL = UUID("33333333-3333-3333-3333-333333333333")
JOB = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _repos(project):
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=project)
    return projects_repo, AsyncMock(), AsyncMock()


def _project(embedding_model="bge-m3"):
    return SimpleNamespace(embedding_model=embedding_model)


async def test_happy_path_reuses_start_core(mocker):
    start = mocker.patch(
        "app.routers.internal_dispatch._start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    payload = InternalExtractionPayload(
        user_id=USER, scope="chapters", chapter_from=1, chapter_to=5, model_ref=MODEL)

    resp = await dispatch_extraction(PROJ, payload, pr, jr, br)

    assert resp.job_id == JOB
    start.assert_awaited_once()
    body = start.call_args.args[1]
    assert body.embedding_model == "bge-m3"      # from the project
    assert body.llm_model == str(MODEL)          # from the campaign
    assert body.scope_range == {"chapter_range": [1, 5]}
    assert start.call_args.args[2] == USER       # asserted user_id propagated


async def test_no_range_omits_scope_range(mocker):
    start = mocker.patch(
        "app.routers.internal_dispatch._start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL)
    await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert start.call_args.args[1].scope_range is None


async def test_forwards_campaign_id_to_core(mocker):
    """S4a: a campaign-dispatched extraction carries campaign_id into the core
    (→ persisted on extraction_jobs → worker-ai stamps it on provider job_meta)."""
    start = mocker.patch(
        "app.routers.internal_dispatch._start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    camp = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL, campaign_id=camp)
    await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert start.call_args.kwargs["campaign_id"] == camp


# ── E0-4b: caller-pays dispatch (manage-collaborator campaign) ─────────


async def test_owner_self_dispatch_no_caller_owner_paid(mocker):
    """billing_user_id == user_id (or None) → owner path: no caller, body uses
    the project's embedding model (legacy owner-paid)."""
    start = mocker.patch(
        "app.routers.internal_dispatch._start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL, billing_user_id=USER)
    await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert start.call_args.kwargs.get("caller") is None
    assert start.call_args.args[1].embedding_model == "bge-m3"  # project's tag


async def test_collaborator_dispatch_bills_caller_with_own_embedding(mocker):
    """A manage-collaborator's campaign (billing_user_id != owner): user_id stays
    the book/project OWNER (graph partition), but caller=collaborator drives
    billing, and body.embedding_model is the CALLER's own same-model ref (2b's
    core probes + bills it; the stored tag becomes the project's)."""
    start = mocker.patch(
        "app.routers.internal_dispatch._start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    collab = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    payload = InternalExtractionPayload(
        user_id=USER, model_ref=MODEL,
        billing_user_id=collab, billing_embedding_model="collab-bge-m3-ref")
    await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert start.call_args.args[2] == USER                       # graph partition = owner
    assert start.call_args.kwargs["caller"] == collab            # billing = collaborator
    assert start.call_args.args[1].embedding_model == "collab-bge-m3-ref"  # caller's ref


async def test_collaborator_dispatch_missing_billing_embedding_422(mocker):
    mocker.patch(
        "app.routers.internal_dispatch._start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    collab = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL, billing_user_id=collab)
    with pytest.raises(HTTPException) as exc:
        await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "KNOW_NO_BILLING_EMBEDDING"


async def test_public_route_passes_no_campaign_id(mocker):
    """S4a guard: the public start route never sets campaign_id (a user cannot
    tag their job to a campaign). The wrapper delegates with the default None."""
    from app.routers.public import extraction as ext
    core = mocker.patch.object(
        ext, "_start_extraction_job_core",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    body = ext.StartJobRequest(scope="chapters", llm_model=str(MODEL), embedding_model="bge-m3")
    # E0-3 Phase 2b — the dep now yields Principals(owner, caller); owner==caller
    # here is the owner path (no billing). The public route never sets campaign_id.
    # Called via KEYWORDS (not positionally) — the route later gained a
    # `background_tasks: BackgroundTasks` param ahead of `principals` for the
    # D-KG-PASSAGES-NOT-INGESTED backfill, and a positional call silently broke
    # (background_tasks bound to a Principals instance, no `.add_task`).
    from app.auth.grant_deps import Principals
    await ext.start_extraction_job(
        PROJ, body,
        background_tasks=AsyncMock(),
        principals=Principals(owner=USER, caller=USER),
        projects_repo=AsyncMock(), jobs_repo=AsyncMock(),
    )
    # campaign_id not supplied → core uses its default None
    assert core.call_args.kwargs.get("campaign_id") is None
    # owner path → caller forwarded as the owner (no billing split downstream)
    assert core.call_args.kwargs.get("caller") == USER


async def test_project_not_found_404(mocker):
    pr, jr, br = _repos(None)
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL)
    with pytest.raises(HTTPException) as exc:
        await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert exc.value.status_code == 404


async def test_no_embedding_model_422(mocker):
    pr, jr, br = _repos(_project(embedding_model=None))
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL)
    with pytest.raises(HTTPException) as exc:
        await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "KNOW_NO_EMBEDDING_MODEL"


async def test_no_model_ref_422(mocker):
    pr, jr, br = _repos(_project())
    payload = InternalExtractionPayload(user_id=USER, model_ref=None)
    with pytest.raises(HTTPException) as exc:
        await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "KNOW_NO_LLM_MODEL"


# ── D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: extraction-status truth ──────────────

async def test_extraction_status_project_not_found_404():
    pr, jr, br = _repos(None)
    with pytest.raises(HTTPException) as exc:
        await dispatch_extraction_status(PROJ, USER, pr, jr)
    assert exc.value.status_code == 404


async def test_extraction_status_active_when_job_in_flight():
    pr, jr, br = _repos(_project())
    jr.list_active_for_project = AsyncMock(return_value=[SimpleNamespace(status="running")])
    resp = await dispatch_extraction_status(PROJ, USER, pr, jr)
    assert resp.active is True
    assert resp.last_outcome is None
    # active short-circuits — no need to read history
    jr.list_for_project.assert_not_called()


async def test_extraction_status_complete_when_no_active_and_last_complete():
    pr, jr, br = _repos(_project())
    jr.list_active_for_project = AsyncMock(return_value=[])
    jr.list_for_project = AsyncMock(return_value=[SimpleNamespace(status="complete")])
    resp = await dispatch_extraction_status(PROJ, USER, pr, jr)
    assert resp.active is False
    assert resp.last_outcome == "complete"


async def test_extraction_status_none_when_no_jobs_at_all():
    pr, jr, br = _repos(_project())
    jr.list_active_for_project = AsyncMock(return_value=[])
    jr.list_for_project = AsyncMock(return_value=[])
    resp = await dispatch_extraction_status(PROJ, USER, pr, jr)
    assert resp.active is False
    assert resp.last_outcome is None


# ── S5b: set-campaign-models ───────────────────────────────────────────────

def _scm_project(*, embedding_model=None, extraction_status="disabled", rerank_model=None):
    pr = AsyncMock()
    pr.get = AsyncMock(return_value=SimpleNamespace(
        embedding_model=embedding_model,
        extraction_status=extraction_status,
        rerank_model=rerank_model,
    ))
    pr.set_extraction_state = AsyncMock()
    pr.set_rerank_model = AsyncMock()
    return pr


async def test_scm_fresh_project_sets_embedding_no_delete(mocker):
    probe = mocker.patch("app.routers.internal_dispatch.probe_embedding_dimension",
                         new_callable=AsyncMock, return_value=_GOOD_DIM)
    delete = mocker.patch("app.routers.internal_dispatch._delete_project_graph",
                          new_callable=AsyncMock)
    pr = _scm_project(embedding_model=None, extraction_status="disabled")
    resp = await set_campaign_models(
        PROJ, SetCampaignModelsPayload(user_id=USER, embedding_model_ref=EMB), pr)
    assert resp.embedding_changed is True
    assert resp.graph_deleted is False
    assert resp.embedding_model == str(EMB)
    probe.assert_awaited_once()
    delete.assert_not_awaited()           # fresh project → no destructive delete
    pr.set_extraction_state.assert_awaited_once()


async def test_scm_conflict_without_confirm_409(mocker):
    probe = mocker.patch("app.routers.internal_dispatch.probe_embedding_dimension",
                         new_callable=AsyncMock, return_value=_GOOD_DIM)
    pr = _scm_project(embedding_model="old-model", extraction_status="ready")
    with pytest.raises(HTTPException) as exc:
        await set_campaign_models(
            PROJ, SetCampaignModelsPayload(user_id=USER, embedding_model_ref=EMB), pr)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "KNOW_EMBEDDING_CONFLICT"
    probe.assert_not_awaited()            # rejected BEFORE any probe/delete
    pr.set_extraction_state.assert_not_awaited()


async def test_scm_confirm_deletes_graph_then_sets(mocker):
    mocker.patch("app.routers.internal_dispatch.app_settings",
                 SimpleNamespace(neo4j_uri="bolt://x"))
    mocker.patch("app.routers.internal_dispatch.probe_embedding_dimension",
                 new_callable=AsyncMock, return_value=_GOOD_DIM)
    delete = mocker.patch("app.routers.internal_dispatch._delete_project_graph",
                          new_callable=AsyncMock, return_value=7)
    pr = _scm_project(embedding_model="old-model", extraction_status="ready")
    resp = await set_campaign_models(
        PROJ, SetCampaignModelsPayload(
            user_id=USER, embedding_model_ref=EMB, confirm_embedding_change=True), pr)
    assert resp.embedding_changed is True and resp.graph_deleted is True
    delete.assert_awaited_once()
    pr.set_extraction_state.assert_awaited_once()


async def test_scm_rerank_only_no_embedding_touch(mocker):
    probe = mocker.patch("app.routers.internal_dispatch.probe_embedding_dimension",
                         new_callable=AsyncMock)
    pr = _scm_project(embedding_model="m", extraction_status="ready")
    resp = await set_campaign_models(
        PROJ, SetCampaignModelsPayload(user_id=USER, rerank_model_ref=RR), pr)
    assert resp.embedding_changed is False
    assert resp.rerank_model == str(RR)
    probe.assert_not_awaited()            # rerank has no embedding hazard
    pr.set_rerank_model.assert_awaited_once()


async def test_scm_same_embedding_is_noop(mocker):
    probe = mocker.patch("app.routers.internal_dispatch.probe_embedding_dimension",
                         new_callable=AsyncMock)
    pr = _scm_project(embedding_model=str(EMB), extraction_status="ready")
    resp = await set_campaign_models(
        PROJ, SetCampaignModelsPayload(user_id=USER, embedding_model_ref=EMB), pr)
    assert resp.embedding_changed is False
    probe.assert_not_awaited()
    pr.set_extraction_state.assert_not_awaited()


async def test_scm_project_not_found_404():
    pr = AsyncMock()
    pr.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await set_campaign_models(
            PROJ, SetCampaignModelsPayload(user_id=USER, embedding_model_ref=EMB), pr)
    assert exc.value.status_code == 404


async def test_cancel_reuses_core_with_asserted_user(mocker):
    # S3c-2: internal cancel delegates to the public cancel_extraction_job with
    # the asserted user_id (project-scoped).
    cancel = mocker.patch(
        "app.routers.internal_dispatch.cancel_extraction_job",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(job_id=JOB, status="cancelled"))
    pr, jr, _ = _repos(_project())
    resp = await dispatch_cancel_extraction(PROJ, InternalCancelPayload(user_id=USER), pr, jr)
    assert resp["status"] == "cancelled"
    cancel.assert_awaited_once()
    # cancel_extraction_job(project_id, user_id, projects_repo, jobs_repo)
    assert cancel.call_args.args[0] == PROJ
    assert cancel.call_args.args[1] == USER
