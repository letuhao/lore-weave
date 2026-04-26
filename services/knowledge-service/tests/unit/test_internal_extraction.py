"""K16.6a — Unit tests for internal extract-item endpoint.

Mocks the Pass 2 orchestrator and Neo4j session to test request
validation, routing (chapter vs chat_turn), and response shaping.

Phase 4a-δ: router catches ``ExtractionError`` and maps stage values:
  - ``stage="provider_exhausted"`` -> 502 (retryable)
  - all other stages -> 422 (non-retryable)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.extraction.errors import ExtractionError
from app.extraction.pass2_writer import Pass2WriteResult


_TEST_TOKEN = "default_test_token"

_MOCK_RESULT = Pass2WriteResult(
    source_id="src-1",
    entities_merged=3,
    relations_created=2,
    events_merged=1,
    facts_merged=4,
    evidence_edges=10,
    skipped_missing_endpoint=0,
)


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _post(client, body, token=_TEST_TOKEN):
    headers = {"X-Internal-Token": token} if token else {}
    return client.post("/internal/extraction/extract-item", json=body, headers=headers)


def _chapter_body(**overrides):
    defaults = {
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "item_type": "chapter",
        "source_type": "chapter",
        "source_id": "ch-1",
        "job_id": str(uuid4()),
        "model_ref": "test-model",
        "chapter_text": "Alice was beginning to get very tired.",
    }
    defaults.update(overrides)
    return defaults


def _chat_body(**overrides):
    defaults = {
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "item_type": "chat_turn",
        "source_type": "chat_turn",
        "source_id": "turn-1",
        "job_id": str(uuid4()),
        "model_ref": "test-model",
        "user_message": "Who is Alice?",
        "assistant_message": "Alice is the protagonist.",
    }
    defaults.update(overrides)
    return defaults


# -- Auth -----------------------------------------------------------


def test_missing_token_returns_401():
    client = _client()
    resp = _post(client, _chapter_body(), token=None)
    assert resp.status_code == 401


def test_wrong_token_returns_401():
    client = _client()
    resp = _post(client, _chapter_body(), token="wrong")
    assert resp.status_code == 401


# -- Chapter extraction --------------------------------------------


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_llm_client")
@patch("app.routers.internal_extraction.extract_pass2_chapter")
@patch("app.routers.internal_extraction.settings")
def test_chapter_extraction_success(
    mock_settings, mock_extract, mock_llm, mock_neo4j,
):
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_extract.return_value = _MOCK_RESULT
    mock_llm.return_value = MagicMock()

    # Mock neo4j_session as async context manager
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post(client, _chapter_body())
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_merged"] == 3
    assert data["relations_created"] == 2
    assert data["events_merged"] == 1
    assert data["facts_merged"] == 4
    assert data["duration_seconds"] >= 0
    mock_extract.assert_called_once()


def test_chapter_without_text_returns_422():
    client = _client()
    body = _chapter_body(chapter_text=None)
    # Need Neo4j configured to get past the 503 check
    with patch("app.routers.internal_extraction.settings") as ms:
        ms.neo4j_uri = "bolt://localhost:7687"
        ms.internal_service_token = _TEST_TOKEN
        with patch("app.routers.internal_extraction.neo4j_session") as mn:
            mock_session = AsyncMock()
            mn.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mn.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.routers.internal_extraction.get_llm_client"):
                resp = _post(client, body)
    assert resp.status_code == 422


# -- Chat turn extraction ------------------------------------------


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_llm_client")
@patch("app.routers.internal_extraction.extract_pass2_chat_turn")
@patch("app.routers.internal_extraction.settings")
def test_chat_turn_extraction_success(
    mock_settings, mock_extract, mock_llm, mock_neo4j,
):
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_extract.return_value = _MOCK_RESULT
    mock_llm.return_value = MagicMock()

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post(client, _chat_body())
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_merged"] == 3
    mock_extract.assert_called_once()


def test_chat_turn_without_messages_returns_422():
    client = _client()
    body = _chat_body(user_message=None, assistant_message=None)
    with patch("app.routers.internal_extraction.settings") as ms:
        ms.neo4j_uri = "bolt://localhost:7687"
        ms.internal_service_token = _TEST_TOKEN
        with patch("app.routers.internal_extraction.neo4j_session") as mn:
            mock_session = AsyncMock()
            mn.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mn.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("app.routers.internal_extraction.get_llm_client"):
                resp = _post(client, body)
    assert resp.status_code == 422


# -- Neo4j not configured ------------------------------------------


@patch("app.routers.internal_extraction.settings")
def test_neo4j_not_configured_returns_503(mock_settings):
    mock_settings.neo4j_uri = ""
    mock_settings.internal_service_token = _TEST_TOKEN
    client = _client()
    resp = _post(client, _chapter_body())
    assert resp.status_code == 503


# -- Validation ----------------------------------------------------


def test_empty_model_ref_returns_422():
    client = _client()
    resp = _post(client, _chapter_body(model_ref=""))
    assert resp.status_code == 422


def test_empty_source_id_returns_422():
    client = _client()
    resp = _post(client, _chapter_body(source_id=""))
    assert resp.status_code == 422


# -- ExtractionError stage mapping ---------------------------------


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_llm_client")
@patch("app.routers.internal_extraction.extract_pass2_chapter")
@patch("app.routers.internal_extraction.settings")
def test_provider_exhausted_returns_502(
    mock_settings, mock_extract, mock_llm, mock_neo4j,
):
    """Phase 4a-δ: stage='provider_exhausted' -> retryable 502."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_extract.side_effect = ExtractionError(
        "transient retry exhausted",
        stage="provider_exhausted",
    )
    mock_llm.return_value = MagicMock()

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post(client, _chapter_body())
    assert resp.status_code == 502
    data = resp.json()
    assert data["detail"]["retryable"] is True
    assert "transient" in data["detail"]["error"]


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_llm_client")
@patch("app.routers.internal_extraction.extract_pass2_chapter")
@patch("app.routers.internal_extraction.settings")
def test_provider_error_returns_422(
    mock_settings, mock_extract, mock_llm, mock_neo4j,
):
    """Phase 4a-δ: stage='provider' -> non-retryable 422."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_extract.side_effect = ExtractionError(
        "invalid API key",
        stage="provider",
    )
    mock_llm.return_value = MagicMock()

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post(client, _chapter_body())
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["retryable"] is False
    assert "API key" in data["detail"]["error"]


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_llm_client")
@patch("app.routers.internal_extraction.extract_pass2_chapter")
@patch("app.routers.internal_extraction.settings")
def test_cancelled_extraction_returns_422(
    mock_settings, mock_extract, mock_llm, mock_neo4j,
):
    """Phase 4a-δ: stage='cancelled' -> non-retryable 422 (operator
    cancellation is terminal — no benefit to retrying)."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_extract.side_effect = ExtractionError(
        "extraction cancelled",
        stage="cancelled",
    )
    mock_llm.return_value = MagicMock()

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post(client, _chapter_body())
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["retryable"] is False
