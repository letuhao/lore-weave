"""Unit tests for K17.4 — LLM entity extractor.

Uses a FakeProviderClient (same duck-typed pattern as
test_llm_json_parser.py) to test extract_entities without any
network calls. Validates:
  - Happy path with canonical ID stability
  - Empty/whitespace input → no LLM call
  - Known entities anchoring
  - Deduplication by canonical_id with alias merging
  - Idempotent re-run (same input → same canonical_ids)
  - All entity kinds
  - ExtractionError propagation from K17.3
  - Whitespace-only name filtering
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from app.clients.provider_client import (
    ChatCompletionResponse,
    ChatCompletionUsage,
    ProviderClient,
    ProviderAuthError,
)
from app.db.neo4j_repos.canonical import entity_canonical_id
from app.extraction.llm_entity_extractor import (
    EntityExtractionResponse,
    LLMEntityCandidate,
    extract_entities,
)
from app.extraction.llm_json_parser import ExtractionError


# ── FakeProviderClient (duck-typed, same pattern as K17.3 tests) ─────


class FakeProviderClient:
    """Pre-seed responses; pops head on each chat_completion call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Any] = []

    def queue_response(self, content: str, model: str = "test-model") -> None:
        self.responses.append(
            ChatCompletionResponse(
                content=content,
                model=model,
                usage=ChatCompletionUsage(),
                raw={},
            )
        )

    def queue_exception(self, exc: Exception) -> None:
        self.responses.append(exc)

    async def chat_completion(self, **kwargs: Any) -> ChatCompletionResponse:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError(
                f"FakeProviderClient ran out of queued responses "
                f"(already had {len(self.calls)} calls)"
            )
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _as_client(fake: FakeProviderClient) -> ProviderClient:
    return cast(ProviderClient, fake)


# ── Fixtures ─────────────────────────────────────────────────────────

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"


def _make_response(*entities: dict[str, Any]) -> str:
    """Build a JSON string matching EntityExtractionResponse schema."""
    return json.dumps({"entities": list(entities)})


def _entity(
    name: str,
    kind: str = "person",
    confidence: float = 0.9,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "confidence": confidence,
        "aliases": aliases or [],
    }


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_three_entities():
    """Basic extraction returns three entities with canonical IDs."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _entity("Kai", "person", 1.0),
            _entity("Harbin", "place", 0.95),
            _entity("Jade Seal", "artifact", 0.9),
        )
    )

    result = await extract_entities(
        text="Kai left Harbin carrying the Jade Seal.",
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 3
    assert len(fake.calls) == 1  # single LLM call

    # Sorted by confidence descending
    assert result[0].name == "Kai"
    assert result[0].kind == "person"
    assert result[0].confidence == 1.0
    assert result[0].canonical_id == entity_canonical_id(
        USER_ID, PROJECT_ID, "Kai", "person"
    )

    assert result[1].name == "Harbin"
    assert result[1].kind == "place"

    assert result[2].name == "Jade Seal"
    assert result[2].kind == "artifact"


@pytest.mark.asyncio
async def test_empty_text_returns_empty_no_llm_call():
    """Empty or whitespace text should return [] without calling LLM."""
    fake = FakeProviderClient()

    for text in ["", "   ", "\n\t  "]:
        result = await extract_entities(
            text=text,
            known_entities=[],
            user_id=USER_ID,
            project_id=PROJECT_ID,
            model_source="user_model",
            model_ref="test-model",
            client=_as_client(fake),
        )
        assert result == []

    assert len(fake.calls) == 0  # no LLM calls made


@pytest.mark.asyncio
async def test_known_entities_anchoring():
    """LLM returns 'kai' but known_entities has 'Kai' → canonical spelling used."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _entity("kai", "person", 0.95),  # lowercase from LLM
        )
    )

    result = await extract_entities(
        text="kai walked through the forest.",
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].name == "Kai"  # anchored to known spelling


@pytest.mark.asyncio
async def test_deduplication_merges_aliases():
    """LLM returns 'Kai' and 'KAI' → deduplicated into one, alias merged."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _entity("Kai", "person", 0.9, aliases=["Kai-kun"]),
            _entity("KAI", "person", 0.95, aliases=["Master Kai"]),
        )
    )

    result = await extract_entities(
        text="Kai, also known as KAI, entered the room.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    # Higher confidence wins
    assert result[0].confidence == 0.95
    # Both aliases present + the alternate spelling
    assert "Kai-kun" in result[0].aliases
    assert "Master Kai" in result[0].aliases
    assert "KAI" in result[0].aliases


@pytest.mark.asyncio
async def test_idempotent_canonical_ids():
    """Same input twice → same canonical_ids."""
    fake = FakeProviderClient()
    response = _make_response(
        _entity("Kai", "person", 0.9),
        _entity("Harbin", "place", 0.8),
    )
    fake.queue_response(response)
    fake.queue_response(response)

    kwargs = dict(
        text="Kai traveled to Harbin.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    result1 = await extract_entities(**kwargs)
    result2 = await extract_entities(**kwargs)

    assert len(result1) == len(result2)
    for c1, c2 in zip(result1, result2):
        assert c1.canonical_id == c2.canonical_id
        assert c1.canonical_name == c2.canonical_name


@pytest.mark.asyncio
async def test_all_entity_kinds():
    """All six entity kinds are accepted."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _entity("Kai", "person", 0.9),
            _entity("Harbin", "place", 0.9),
            _entity("Imperial Academy", "organization", 0.9),
            _entity("Jade Seal", "artifact", 0.9),
            _entity("Honor", "concept", 0.8),
            _entity("The Anomaly", "other", 0.7),
        )
    )

    result = await extract_entities(
        text="Chapter text with many entities.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 6
    kinds = {c.kind for c in result}
    assert kinds == {"person", "place", "organization", "artifact", "concept", "other"}


@pytest.mark.asyncio
async def test_extraction_error_propagation():
    """ProviderAuthError from K17.3 surfaces as ExtractionError."""
    fake = FakeProviderClient()
    fake.queue_exception(
        ProviderAuthError("invalid API key")
    )

    with pytest.raises(ExtractionError) as exc_info:
        await extract_entities(
            text="Some text to extract.",
            known_entities=[],
            user_id=USER_ID,
            project_id=PROJECT_ID,
            model_source="user_model",
            model_ref="test-model",
            client=_as_client(fake),
        )

    assert exc_info.value.stage == "provider"


@pytest.mark.asyncio
async def test_empty_entities_from_llm():
    """LLM returns empty entities list → empty result."""
    fake = FakeProviderClient()
    fake.queue_response(json.dumps({"entities": []}))

    result = await extract_entities(
        text="A paragraph with no named entities at all.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert result == []


@pytest.mark.asyncio
async def test_project_id_none_uses_global_scope():
    """project_id=None produces a different canonical_id than a real project."""
    fake = FakeProviderClient()
    response = _make_response(_entity("Kai", "person", 0.9))
    fake.queue_response(response)
    fake.queue_response(response)

    result_global = await extract_entities(
        text="Kai speaks.",
        known_entities=[],
        user_id=USER_ID,
        project_id=None,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )
    result_project = await extract_entities(
        text="Kai speaks.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result_global) == 1
    assert len(result_project) == 1
    assert result_global[0].canonical_id != result_project[0].canonical_id


@pytest.mark.asyncio
async def test_known_entities_passed_in_prompt():
    """Known entities are serialized as JSON in the LLM prompt."""
    fake = FakeProviderClient()
    fake.queue_response(_make_response(_entity("Kai", "person", 0.9)))

    await extract_entities(
        text="Kai enters.",
        known_entities=["Kai", "Harbin"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    # Verify the user_prompt sent to the LLM contains the known entities
    assert len(fake.calls) == 1
    messages = fake.calls[0]["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert '["Kai", "Harbin"]' in user_msg["content"]


@pytest.mark.asyncio
async def test_confidence_ordering():
    """Results are sorted by confidence descending."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _entity("Low", "person", 0.5),
            _entity("High", "person", 1.0),
            _entity("Mid", "person", 0.75),
        )
    )

    result = await extract_entities(
        text="Low, High, and Mid appeared.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    confidences = [c.confidence for c in result]
    assert confidences == [1.0, 0.75, 0.5]


@pytest.mark.asyncio
async def test_canonical_name_computed():
    """canonical_name is the output of canonicalize_entity_name."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _entity("Master Kai", "person", 0.9),
        )
    )

    result = await extract_entities(
        text="Master Kai arrived.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    # "Master" is an honorific stripped by canonicalize_entity_name
    assert result[0].canonical_name == "kai"
    assert result[0].name == "Master Kai"  # display name preserved
