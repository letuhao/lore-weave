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
    InternalExtractionPayload,
)

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
        "app.routers.internal_dispatch.start_extraction_job",
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
        "app.routers.internal_dispatch.start_extraction_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=JOB))
    pr, jr, br = _repos(_project())
    payload = InternalExtractionPayload(user_id=USER, model_ref=MODEL)
    await dispatch_extraction(PROJ, payload, pr, jr, br)
    assert start.call_args.args[1].scope_range is None


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
