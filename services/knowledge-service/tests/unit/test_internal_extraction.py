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

from loreweave_extraction.errors import ExtractionError
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


# -- Phase 4b-β: persist-pass2 endpoint ----------------------------


def _persist_body(**overrides):
    """Build a PersistPass2Request payload matching the new endpoint
    contract. Mirrors the shape worker-ai (4b-γ) will send after
    running loreweave_extraction.extract_pass2(...) itself."""
    defaults = {
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "source_type": "chapter",
        "source_id": "ch-1",
        "job_id": str(uuid4()),
        "extraction_model": "test-model",
        "entities": [
            {
                "name": "Alice",
                "kind": "person",
                "aliases": ["Ali"],
                "confidence": 0.95,
                "canonical_name": "alice",
                "canonical_id": "a" * 32,
            },
        ],
        "relations": [],
        "events": [],
        "facts": [],
    }
    defaults.update(overrides)
    return defaults


def _post_persist(client, body, token=_TEST_TOKEN):
    headers = {"X-Internal-Token": token} if token else {}
    return client.post(
        "/internal/extraction/persist-pass2", json=body, headers=headers,
    )


def test_persist_pass2_missing_token_returns_401():
    client = _client()
    resp = _post_persist(client, _persist_body(), token=None)
    assert resp.status_code == 401


def test_persist_pass2_wrong_token_returns_401():
    client = _client()
    resp = _post_persist(client, _persist_body(), token="wrong")
    assert resp.status_code == 401


@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_neo4j_not_configured_returns_503(mock_settings):
    mock_settings.neo4j_uri = ""
    mock_settings.internal_service_token = _TEST_TOKEN
    client = _client()
    resp = _post_persist(client, _persist_body())
    assert resp.status_code == 503


@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_happy_path_returns_write_counts(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
):
    """Phase 4b-β happy path: the endpoint forwards the candidate
    lists to write_pass2_extraction and surfaces its counters in the
    response. Locks the contract worker-ai (4b-γ) will rely on."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post_persist(client, _persist_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_merged"] == 3
    assert data["relations_created"] == 2
    assert data["events_merged"] == 1
    assert data["facts_merged"] == 4
    assert data["evidence_edges"] == 10
    assert data["duration_seconds"] >= 0
    mock_write.assert_called_once()
    # Candidate lists arrived as Pydantic-validated library models
    write_kwargs = mock_write.call_args.kwargs
    assert len(write_kwargs["entities"]) == 1
    assert write_kwargs["entities"][0].name == "Alice"
    assert write_kwargs["extraction_model"] == "test-model"


@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_empty_candidates_lists_still_calls_writer(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
):
    """All four candidate lists empty -> writer still called with
    empty lists. write_pass2_extraction tolerates this and returns a
    zero-counter result (idempotent source upsert only)."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = Pass2WriteResult(
        source_id="ch-empty", entities_merged=0,
        relations_created=0, events_merged=0,
        facts_merged=0, evidence_edges=0,
    )

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    body = _persist_body(entities=[], source_id="ch-empty")
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_merged"] == 0
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["entities"] == []
    assert write_kwargs["relations"] == []
    assert write_kwargs["events"] == []
    assert write_kwargs["facts"] == []


@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_invalid_entity_shape_returns_422(mock_settings):
    """Pydantic validation rejects malformed candidate items so the
    writer never sees garbage — fail fast at the wire boundary."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN

    body = _persist_body(entities=[{"name": "Alice"}])  # missing kind/canonical_id/...
    client = _client()
    resp = _post_persist(client, body)
    assert resp.status_code == 422


def test_persist_pass2_missing_required_field_returns_422():
    """source_id has min_length=1 — empty string rejected."""
    client = _client()
    resp = _post_persist(client, _persist_body(source_id=""))
    assert resp.status_code == 422


@patch("app.routers.internal_extraction.JobLogsRepo")
@patch("app.routers.internal_extraction.get_knowledge_pool")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_default_extraction_model_flows_through(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
    mock_pool, mock_repo_cls,
):
    """Phase 4b-β /review-impl LOW#1 — when caller omits
    `extraction_model`, the schema default `'llm-v1'` flows through
    to write_pass2_extraction. Locks the contract so a future
    schema-default change surfaces in CI."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_repo_cls.return_value.append = AsyncMock()

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    body = _persist_body()
    body.pop("extraction_model")  # use schema default
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["extraction_model"] == "llm-v1"


@patch("app.routers.internal_extraction.JobLogsRepo")
@patch("app.routers.internal_extraction.get_knowledge_pool")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_emits_pass2_write_job_logs_event(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
    mock_pool, mock_repo_cls,
):
    """Phase 4b-β /review-impl MED#1 — persist-pass2 must fire the
    `pass2_write` job_logs event so the FE's JobLogsPanel keeps
    rendering 'extraction complete' entries after worker-ai (4b-γ)
    migrates from extract-item to persist-pass2.

    The event context shape must match pass2_orchestrator's existing
    pass2_write emit (same field names) so dashboards reading
    `event=pass2_write` don't need to learn a new schema.
    """
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT

    mock_repo = MagicMock()
    mock_repo.append = AsyncMock()
    mock_repo_cls.return_value = mock_repo

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    body = _persist_body()
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200
    mock_repo.append.assert_awaited_once()
    # 5th positional arg is the context dict
    context = mock_repo.append.call_args.args[4]
    assert context["event"] == "pass2_write"
    assert context["entities_merged"] == 3
    assert context["relations_created"] == 2
    assert context["events_merged"] == 1
    assert context["facts_merged"] == 4
    assert context["evidence_edges"] == 10
    assert context["duration_ms"] >= 0
    assert context["source_type"] == "chapter"
    assert context["source_id"] == "ch-1"


@patch("app.routers.internal_extraction.JobLogsRepo")
@patch("app.routers.internal_extraction.get_knowledge_pool")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_telemetry_failure_is_non_fatal(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
    mock_pool, mock_repo_cls,
):
    """A job_logs append failure (Postgres hiccup, pool down, etc.)
    must NOT fail the request — best-effort telemetry. The 200
    response with write counts is what worker-ai needs."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT

    mock_repo = MagicMock()
    mock_repo.append = AsyncMock(side_effect=RuntimeError("pg down"))
    mock_repo_cls.return_value = mock_repo

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post_persist(client, _persist_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_merged"] == 3


@patch("app.routers.internal_extraction.JobLogsRepo")
@patch("app.routers.internal_extraction.get_knowledge_pool")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_passes_anchors_to_writer(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
    mock_pool, mock_repo_cls,
):
    """Anchor pre-load reuses _load_anchors_for_extraction; the
    resulting list flows into write_pass2_extraction so candidates
    can be anchored to glossary entries the same way extract-item does."""
    from app.extraction.anchor_loader import Anchor

    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    fake_anchor = MagicMock(spec=Anchor)
    mock_anchors.return_value = [fake_anchor]
    mock_write.return_value = _MOCK_RESULT

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    client = _client()
    resp = _post_persist(client, _persist_body())

    assert resp.status_code == 200
    write_kwargs = mock_write.call_args.kwargs
    assert write_kwargs["anchors"] == [fake_anchor]
