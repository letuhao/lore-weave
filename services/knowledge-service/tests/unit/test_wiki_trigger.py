"""Unit tests for the wiki-gen trigger endpoint (wiki-llm M6).

POST /internal/knowledge/books/{id}/wiki/generate — 202 + job_id on accept,
404 not_indexed, 409 (+existing job_id) on the per-book lock, 400 on no entities.
ProjectsRepo / WikiGenJobsRepo / the redis enqueue are mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.repositories.wiki_gen_jobs import ActiveJobExists, WikiGenJob
from app.middleware.internal_auth import require_internal_token
from app.routers import internal_wiki


def _project():
    return MagicMock(project_id=uuid4())


def _client(projects, *, create_return=None, create_raises=None) -> TestClient:
    app = FastAPI()
    app.include_router(internal_wiki.router)
    app.dependency_overrides[require_internal_token] = lambda: None
    pr = MagicMock()
    pr.list = AsyncMock(return_value=projects)
    app.dependency_overrides[internal_wiki.get_projects_repo] = lambda: pr

    repo = MagicMock()
    if create_raises is not None:
        repo.create = AsyncMock(side_effect=create_raises)
    else:
        repo.create = AsyncMock(return_value=create_return)
    return app, repo


def _body(entity_ids=None):
    return {
        "user_id": str(uuid4()), "model_source": "user_model", "model_ref": "m1",
        "entity_ids": entity_ids if entity_ids is not None else ["e1", "e2"],
    }


def _post(app, repo, body):
    with patch.object(internal_wiki, "WikiGenJobsRepo", return_value=repo), \
         patch.object(internal_wiki, "get_knowledge_pool", return_value=MagicMock()), \
         patch.object(internal_wiki, "enqueue_wiki_gen", new=AsyncMock(return_value="1-0")), \
         patch.object(internal_wiki, "_redis", return_value=MagicMock()):
        return TestClient(app).post(f"/internal/knowledge/books/{uuid4()}/wiki/generate", json=body)


def _job():
    return WikiGenJob(
        job_id=uuid4(), user_id=uuid4(), project_id=uuid4(), book_id=uuid4(),
        status="pending", model_source="user_model", model_ref="m1",
        entity_ids=["e1", "e2"], items_done=[],
    )


def test_trigger_accepts_202():
    job = _job()
    app, repo = _client([_project()], create_return=job)
    resp = _post(app, repo, _body())
    assert resp.status_code == 202
    assert resp.json()["job_id"] == str(job.job_id)


def test_trigger_404_not_indexed():
    app, repo = _client([], create_return=_job())  # no project for the book
    resp = _post(app, repo, _body())
    assert resp.status_code == 404


def test_trigger_409_active_job():
    existing = uuid4()
    app, repo = _client([_project()], create_raises=ActiveJobExists(existing))
    resp = _post(app, repo, _body())
    assert resp.status_code == 409
    assert resp.json()["detail"]["job_id"] == str(existing)


def test_trigger_400_no_entities():
    app, repo = _client([_project()], create_return=_job())
    resp = _post(app, repo, _body(entity_ids=[]))
    assert resp.status_code == 400
