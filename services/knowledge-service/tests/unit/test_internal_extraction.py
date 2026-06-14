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


@patch("app.db.neo4j_repos.provenance.cleanup_zero_evidence_nodes", new_callable=AsyncMock)
@patch("app.db.neo4j_repos.provenance.remove_evidence_for_natural_key", new_callable=AsyncMock)
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_retract_uses_natural_key_and_sweeps_on_reextract(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_retract, mock_cleanup,
):
    """CM3b-RETRACT-FIX regression-lock: persist-pass2 retracts via the
    NATURAL-KEY helper (so the right hashed ExtractionSource id is targeted),
    and when the retract removed >0 edges (a re-extract) it sweeps the
    zero-evidence orphans. The pre-fix bug passed the raw source_id to a
    hashed-id MATCH → zero edges removed → canon drift on re-publish."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_retract.return_value = 4  # >0 → this is a re-extract
    mock_cleanup.return_value = MagicMock(total=2)

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    uid, pid = str(uuid4()), str(uuid4())
    body = _persist_body(user_id=uid, project_id=pid, source_type="chapter", source_id="ch-77")
    resp = _post_persist(_client(), body)

    assert resp.status_code == 200
    # Retract called with the NATURAL KEY, NOT the raw source_id alone.
    mock_retract.assert_awaited_once()
    rk = mock_retract.await_args.kwargs
    assert rk["user_id"] == uid
    assert rk["project_id"] == pid
    assert rk["source_type"] == "chapter"
    assert rk["source_id"] == "ch-77"
    # removed=4 (>0) → orphan sweep ran for the same user/project.
    mock_cleanup.assert_awaited_once()
    ck = mock_cleanup.await_args.kwargs
    assert ck["user_id"] == uid
    assert ck["project_id"] == pid


@patch("app.db.neo4j_repos.provenance.cleanup_zero_evidence_nodes", new_callable=AsyncMock)
@patch("app.db.neo4j_repos.provenance.remove_evidence_for_natural_key", new_callable=AsyncMock)
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_first_extract_skips_sweep(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_retract, mock_cleanup,
):
    """First-time extraction (retract removed 0 edges) must NOT run the
    O(project) zero-evidence sweep — there is nothing to sweep, and the
    gate keeps the common bulk-extraction path cheap."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_retract.return_value = 0  # first-time extract → nothing retracted

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    resp = _post_persist(_client(), _persist_body())

    assert resp.status_code == 200
    mock_retract.assert_awaited_once()
    mock_cleanup.assert_not_awaited()  # gated on removed > 0


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


# ── P3 D-P3-EXTRACTION-CALLER-WIRE-UP — /persist-pass2 P3 fields ─────────


def _hierarchy_paths_payload(**overrides):
    defaults = {
        "book_id": str(uuid4()),
        "book_path": "book",
        "book_title": "The Book",
        "part_id": str(uuid4()),
        "part_path": "book/part-1",
        "part_index": 1,
        "part_title": "Part 1",
        "chapter_id": str(uuid4()),
        "chapter_path": "book/part-1/chapter-1",
        "chapter_index": 1,
        "chapter_title": "Chapter 1",
        "scenes": [],
    }
    defaults.update(overrides)
    return defaults


@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_p3_forwards_hierarchy_paths_to_writer(
    mock_settings, mock_write, mock_neo4j, mock_anchors,
):
    """When hierarchy_paths supplied, /persist-pass2 forwards a
    HierarchyPaths dataclass to write_pass2_extraction (D2a Tx)."""
    from app.extraction.hierarchy_writer import HierarchyPaths
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    body = _persist_body(hierarchy_paths=_hierarchy_paths_payload(
        chapter_path="book/part-1/chapter-7", chapter_index=7,
    ))
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200, resp.text
    hp_arg = mock_write.call_args.kwargs["hierarchy_paths"]
    assert isinstance(hp_arg, HierarchyPaths)
    assert hp_arg.chapter_path == "book/part-1/chapter-7"
    assert hp_arg.chapter_index == 7


@patch("app.routers.internal_extraction._get_summary_enqueue")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_p3_enqueues_chapter_summary_when_all_deps_present(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_get_enqueue,
):
    """With hierarchy + embedding model + dimension supplied, the
    endpoint enqueues a `summary.chapter` message."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)
    enqueue_mock = AsyncMock(return_value="msg-id-1")
    mock_get_enqueue.return_value = enqueue_mock

    body = _persist_body(
        hierarchy_paths=_hierarchy_paths_payload(),
        embedding_model_uuid=str(uuid4()),
        embedding_dimension=1024,
        is_last_chapter_of_book=False,
    )
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200, resp.text
    # exactly 1 enqueue (chapter only, not last chapter)
    assert enqueue_mock.await_count == 1
    msg = enqueue_mock.await_args.args[0]
    assert msg.level == "chapter"


@patch("app.routers.internal_extraction._get_summary_enqueue")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_c12_summaries_gated_out_when_not_in_targets(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_get_enqueue,
):
    """C12 — even with all summary deps present, `summaries ∉ targets` skips
    the enqueue entirely."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)
    enqueue_mock = AsyncMock(return_value="msg-id-1")
    mock_get_enqueue.return_value = enqueue_mock

    body = _persist_body(
        hierarchy_paths=_hierarchy_paths_payload(),
        embedding_model_uuid=str(uuid4()),
        embedding_dimension=1024,
        is_last_chapter_of_book=False,
        targets=["entities", "events"],  # no `summaries`
    )
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200, resp.text
    assert enqueue_mock.await_count == 0


@patch("app.routers.internal_extraction._get_summary_enqueue")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_c12_summaries_enqueued_when_in_targets(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_get_enqueue,
):
    """C12 — `summaries ∈ targets` (and deps present) enqueues as normal."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)
    enqueue_mock = AsyncMock(return_value="msg-id-1")
    mock_get_enqueue.return_value = enqueue_mock

    body = _persist_body(
        hierarchy_paths=_hierarchy_paths_payload(),
        embedding_model_uuid=str(uuid4()),
        embedding_dimension=1024,
        is_last_chapter_of_book=False,
        targets=["entities", "events", "summaries"],
    )
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200, resp.text
    assert enqueue_mock.await_count == 1


@patch("app.routers.internal_extraction._get_summary_enqueue")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_p3_last_chapter_also_enqueues_part_and_book(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_get_enqueue,
):
    """is_last_chapter_of_book=True fires chapter + N parts + book = 2+N total."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)
    enqueue_mock = AsyncMock(return_value="msg-id")
    mock_get_enqueue.return_value = enqueue_mock

    body = _persist_body(
        hierarchy_paths=_hierarchy_paths_payload(),
        embedding_model_uuid=str(uuid4()),
        embedding_dimension=1024,
        is_last_chapter_of_book=True,
        book_parts=[
            [str(uuid4()), "book/part-1", "1"],
            [str(uuid4()), "book/part-2", "2"],
        ],
    )
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200, resp.text
    # 1 chapter + 2 parts + 1 book = 4 enqueues
    assert enqueue_mock.await_count == 4
    levels = [call.args[0].level for call in enqueue_mock.await_args_list]
    assert levels == ["chapter", "part", "part", "book"]


@patch("app.routers.internal_extraction._get_summary_enqueue")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_p3_skips_enqueue_when_embedding_deps_missing(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_get_enqueue,
):
    """hierarchy_paths supplied but no embedding info → no enqueue."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)
    enqueue_mock = AsyncMock()
    mock_get_enqueue.return_value = enqueue_mock

    body = _persist_body(
        hierarchy_paths=_hierarchy_paths_payload(),
        # embedding_model_uuid / embedding_dimension intentionally omitted
    )
    client = _client()
    resp = _post_persist(client, body)

    assert resp.status_code == 200, resp.text
    enqueue_mock.assert_not_called()


@patch("app.routers.internal_extraction._get_summary_enqueue")
@patch("app.routers.internal_extraction._load_anchors_for_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.write_pass2_extraction", new_callable=AsyncMock)
@patch("app.routers.internal_extraction.settings")
def test_persist_pass2_p3_enqueue_failure_does_not_500(
    mock_settings, mock_write, mock_neo4j, mock_anchors, mock_get_enqueue,
):
    """Best-effort: Redis enqueue failure must not roll back the
    already-committed Postgres + Neo4j writes."""
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.internal_service_token = _TEST_TOKEN
    mock_anchors.return_value = []
    mock_write.return_value = _MOCK_RESULT
    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)
    enqueue_mock = AsyncMock(side_effect=RuntimeError("redis down"))
    mock_get_enqueue.return_value = enqueue_mock

    body = _persist_body(
        hierarchy_paths=_hierarchy_paths_payload(),
        embedding_model_uuid=str(uuid4()),
        embedding_dimension=1024,
    )
    client = _client()
    resp = _post_persist(client, body)

    # Endpoint still returns 200 — write succeeded; only enqueue failed.
    assert resp.status_code == 200, resp.text


# ── P3 — /internal/extraction/summarize-message ─────────────────────────


def _summarize_message_body(**overrides):
    defaults = {
        "level": "chapter",
        "node_path": "book/part-1/chapter-3",
        "node_id": str(uuid4()),
        "book_id": str(uuid4()),
        "user_id": str(uuid4()),
        "project_id": str(uuid4()),
        "job_id": str(uuid4()),
        "model_ref": "gemma-4-26b",
        "embedding_model_uuid": str(uuid4()),
        "embedding_dimension": 1024,
        "retry_at_epoch": 0.0,
        "retried_n": 0,
    }
    defaults.update(overrides)
    return defaults


def _post_summarize_message(client, body, token=_TEST_TOKEN):
    headers = {"X-Internal-Token": token} if token else {}
    return client.post(
        "/internal/extraction/summarize-message", json=body, headers=headers,
    )


def test_summarize_message_requires_internal_token():
    client = _client()
    resp = _post_summarize_message(client, _summarize_message_body(), token=None)
    assert resp.status_code == 401


def test_summarize_message_validates_level_enum():
    client = _client()
    body = _summarize_message_body(level="paragraph")  # not in chapter/part/book
    resp = _post_summarize_message(client, body)
    assert resp.status_code == 422


def test_summarize_message_validates_embedding_dimension_positive():
    client = _client()
    body = _summarize_message_body(embedding_dimension=0)
    resp = _post_summarize_message(client, body)
    assert resp.status_code == 422


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_knowledge_pool")
@patch("app.routers.internal_extraction._get_summary_enqueue")
def test_summarize_message_dispatches_to_processor(
    mock_get_enqueue, mock_get_pool, mock_neo4j,
):
    """Happy path: router builds deps, calls process_summarize_message,
    returns SummaryProcessResult JSON."""
    from app.jobs.summary_processor import SummaryProcessResult
    expected_summary_id = uuid4()

    # Stub process_summarize_message at import site.
    fake_result = SummaryProcessResult(
        level="chapter",
        node_id="node-1",
        cache_hit=False,
        race_winner=True,
        re_enqueued=False,
        skipped_retry_exhausted=False,
        summary_id=expected_summary_id,
    )

    async def _fake_process(msg, deps):
        # Confirm deps wiring — message_id round-trip + all 5 fields present.
        assert deps.knowledge_pool is mock_get_pool.return_value
        assert deps.summary_enqueue is mock_get_enqueue.return_value
        assert deps.embedding_client is not None
        assert deps.llm_client is not None
        assert deps.neo4j_session is not None
        return fake_result

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.jobs.summary_processor.process_summarize_message",
        side_effect=_fake_process,
    ):
        client = _client()
        body = _summarize_message_body(node_id="node-1")
        resp = _post_summarize_message(client, body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["level"] == "chapter"
    assert data["node_id"] == "node-1"
    assert data["race_winner"] is True
    assert data["summary_id"] == str(expected_summary_id)


@patch("app.routers.internal_extraction.neo4j_session")
@patch("app.routers.internal_extraction.get_knowledge_pool")
@patch("app.routers.internal_extraction._get_summary_enqueue")
def test_summarize_message_returns_re_enqueued_flag(
    mock_get_enqueue, mock_get_pool, mock_neo4j,
):
    """D9 defensive-failure path: processor re-enqueues, router surfaces flag."""
    from app.jobs.summary_processor import SummaryProcessResult

    async def _fake_process(msg, deps):
        return SummaryProcessResult(
            level="part", node_id="p1",
            cache_hit=False, race_winner=False,
            re_enqueued=True, skipped_retry_exhausted=False,
            summary_id=None,
        )

    mock_session = AsyncMock()
    mock_neo4j.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_neo4j.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.jobs.summary_processor.process_summarize_message",
        side_effect=_fake_process,
    ):
        client = _client()
        body = _summarize_message_body(level="part", node_id="p1")
        resp = _post_summarize_message(client, body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["re_enqueued"] is True
    assert data["summary_id"] is None


@patch("app.routers.internal_extraction.get_knowledge_pool")
def test_summarize_message_pool_unavailable_returns_503(mock_get_pool):
    """Knowledge pool init failure → 503 (matches existing pattern in
    internal_summarize.py)."""
    mock_get_pool.side_effect = RuntimeError("pool not initialized")
    client = _client()
    resp = _post_summarize_message(client, _summarize_message_body())
    assert resp.status_code == 503


def test_embedding_adapter_unwraps_first_vector():
    """Adapter bridges EmbeddingClient.embed (batch) → single-vector return."""
    from app.routers.internal_extraction import _EmbeddingAdapter
    from app.clients.embedding_client import EmbeddingResult
    import asyncio

    real = MagicMock()
    real.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[[0.1, 0.2, 0.3]], dimension=3, model="bge-m3",
    ))
    user_id = uuid4()
    adapter = _EmbeddingAdapter(real, user_id=user_id)
    vec = asyncio.run(adapter.embed(text="hello", model_uuid="model-uuid-1"))

    assert vec == [0.1, 0.2, 0.3]
    real.embed.assert_awaited_once_with(
        user_id=user_id, model_source="user_model",
        model_ref="model-uuid-1", texts=["hello"],
    )


def test_embedding_adapter_raises_on_empty_vector():
    """Defensive: real client should never return an empty result, but
    if it does, surface as RuntimeError so the worker retries."""
    from app.routers.internal_extraction import _EmbeddingAdapter
    from app.clients.embedding_client import EmbeddingResult
    import asyncio

    real = MagicMock()
    real.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[[]], dimension=0, model="bge-m3",
    ))
    adapter = _EmbeddingAdapter(real, user_id=uuid4())
    with pytest.raises(RuntimeError, match="empty vector"):
        asyncio.run(adapter.embed(text="x", model_uuid="m"))
