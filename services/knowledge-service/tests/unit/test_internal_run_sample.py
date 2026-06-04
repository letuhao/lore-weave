"""Q4b-feed — unit tests for GET /internal/extraction/runs/{run_id}/sample."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.repositories.extraction_run_samples import ExtractionRunSample
from app.main import app

_INTERNAL_TOKEN_HEADER = {"X-Internal-Token": "default_test_token"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _sample(run_id):
    return ExtractionRunSample(
        run_id=run_id, user_id=uuid4(), project_id=uuid4(), book_id=uuid4(),
        config_hash="cfg-1",
        items={
            "entity": [{"name": "Alice", "kind": "person"}],
            "relation": [],
            "event": [{"summary": "fell", "participants": ["Alice"]}],
        },
        source_text="Alice fell down the hole.",
    )


def test_returns_sample_when_present(client: TestClient):
    rid = uuid4()
    with patch(
        "app.routers.internal_extraction.get_knowledge_pool",
        return_value=object(),
    ), patch(
        "app.db.repositories.extraction_run_samples.ExtractionRunSamplesRepo.fetch_sample",
        new=AsyncMock(return_value=_sample(rid)),
    ):
        resp = client.get(
            f"/internal/extraction/runs/{rid}/sample", headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == str(rid)
    assert body["source_text"] == "Alice fell down the hole."
    assert body["items"]["entity"][0]["name"] == "Alice"
    assert body["items"]["event"][0]["summary"] == "fell"


def test_404_when_no_sample(client: TestClient):
    rid = uuid4()
    with patch(
        "app.routers.internal_extraction.get_knowledge_pool",
        return_value=object(),
    ), patch(
        "app.db.repositories.extraction_run_samples.ExtractionRunSamplesRepo.fetch_sample",
        new=AsyncMock(return_value=None),
    ):
        resp = client.get(
            f"/internal/extraction/runs/{rid}/sample", headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 404


def test_requires_internal_token(client: TestClient):
    resp = client.get(f"/internal/extraction/runs/{uuid4()}/sample")
    assert resp.status_code == 401
