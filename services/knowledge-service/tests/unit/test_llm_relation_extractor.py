"""Unit tests for K17.5 — LLM relation extractor.

Uses FakeProviderClient + pre-built LLMEntityCandidate fixtures to
test extract_relations without network calls. Validates:
  - Happy path with entity resolution + relation_id
  - Empty text → no LLM call
  - Known entities anchoring in subject/object
  - Unresolvable endpoints → None IDs
  - Predicate normalization
  - Polarity/modality preservation
  - Deduplication by relation_id
  - Idempotent re-run
  - ExtractionError propagation
  - Curly braces in text don't crash
  - Entity alias resolution
  - Empty relations from LLM
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
from app.db.neo4j_repos.relations import relation_id as compute_relation_id
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_relation_extractor import (
    LLMRelationCandidate,
    RelationExtractionResponse,
    extract_relations,
    _normalize_predicate,
)
from app.extraction.llm_json_parser import ExtractionError


# ── FakeProviderClient ───────────────────────────────────────────────


class FakeProviderClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Any] = []

    def queue_response(self, content: str, model: str = "test-model") -> None:
        self.responses.append(
            ChatCompletionResponse(
                content=content, model=model,
                usage=ChatCompletionUsage(), raw={},
            )
        )

    def queue_exception(self, exc: Exception) -> None:
        self.responses.append(exc)

    async def chat_completion(self, **kwargs: Any) -> ChatCompletionResponse:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("FakeProviderClient exhausted")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _as_client(fake: FakeProviderClient) -> ProviderClient:
    return cast(ProviderClient, fake)


# ── Fixtures ─────────────────────────────────────────────────────────

USER_ID = "test-user-001"
PROJECT_ID = "test-project-001"


def _make_entity(
    name: str,
    kind: str = "person",
    confidence: float = 0.9,
    aliases: list[str] | None = None,
) -> LLMEntityCandidate:
    from app.db.neo4j_repos.canonical import (
        canonicalize_entity_name,
        entity_canonical_id,
    )
    canonical_name = canonicalize_entity_name(name)
    cid = entity_canonical_id(USER_ID, PROJECT_ID, name, kind)
    return LLMEntityCandidate(
        name=name,
        kind=kind,
        aliases=aliases or [],
        confidence=confidence,
        canonical_name=canonical_name,
        canonical_id=cid,
    )


ENTITIES = [
    _make_entity("Kai", "person"),
    _make_entity("Zhao", "person"),
    _make_entity("Imperial Academy", "organization"),
    _make_entity("Alice", "person", aliases=["Ali"]),
    _make_entity("Bob", "person"),
]


def _make_response(*relations: dict[str, Any]) -> str:
    return json.dumps({"relations": list(relations)})


def _rel(
    subject: str,
    predicate: str,
    obj: str,
    confidence: float = 0.9,
    polarity: str = "affirm",
    modality: str = "asserted",
) -> dict[str, Any]:
    return {
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "polarity": polarity,
        "modality": modality,
        "confidence": confidence,
    }


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_three_relations():
    """Basic extraction with entity resolution and relation_id."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _rel("Kai", "works_for", "Imperial Academy", 0.95),
            _rel("Kai", "trusts", "Zhao", 0.9, polarity="negate"),
            _rel("Alice", "knows", "Bob", 0.85),
        )
    )

    result = await extract_relations(
        text="Kai works for the Imperial Academy but doesn't trust Zhao. Alice knows Bob.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao", "Alice", "Bob"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 3
    assert len(fake.calls) == 1

    # Sorted by confidence descending
    r0 = result[0]
    assert r0.subject == "Kai"
    assert r0.predicate == "works_for"
    assert r0.object == "Imperial Academy"
    assert r0.confidence == 0.95
    assert r0.subject_id is not None
    assert r0.object_id is not None
    assert r0.relation_id is not None

    r1 = result[1]
    assert r1.polarity == "negate"
    assert r1.subject_id is not None

    r2 = result[2]
    assert r2.subject == "Alice"
    assert r2.object == "Bob"


@pytest.mark.asyncio
async def test_empty_text_returns_empty():
    """Empty or whitespace text → no LLM call."""
    fake = FakeProviderClient()

    for text in ["", "   ", "\n"]:
        result = await extract_relations(
            text=text, entities=ENTITIES,
            known_entities=[], user_id=USER_ID,
            project_id=PROJECT_ID, model_source="user_model",
            model_ref="test-model", client=_as_client(fake),
        )
        assert result == []

    assert len(fake.calls) == 0


@pytest.mark.asyncio
async def test_unresolvable_endpoints_get_none_ids():
    """Subject/object not in entities → None IDs."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _rel("Unknown Person", "owns", "Mystery Artifact", 0.8),
        )
    )

    result = await extract_relations(
        text="Unknown Person owns Mystery Artifact.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].subject_id is None
    assert result[0].object_id is None
    assert result[0].relation_id is None


def test_predicate_normalization():
    """Predicate should be lowercase snake_case."""
    assert _normalize_predicate("Works For") == "works_for"
    assert _normalize_predicate("married-to") == "married_to"
    assert _normalize_predicate("  ENEMY OF  ") == "enemy_of"
    assert _normalize_predicate("knows") == "knows"
    assert _normalize_predicate("child_of") == "child_of"


def test_predicate_normalization_non_latin():
    """R2 I6/I7: non-ASCII predicates must be preserved, not stripped."""
    assert _normalize_predicate("属于") == "属于"
    assert _normalize_predicate("  관계  ") == "관계"
    assert _normalize_predicate("работает в") == "работает_в"
    # Mixed ASCII + Unicode
    assert _normalize_predicate("is 朋友 of") == "is_朋友_of"


@pytest.mark.asyncio
async def test_polarity_and_modality_preserved():
    """Polarity and modality from LLM response are preserved."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _rel("Kai", "knows", "Zhao", 0.9, polarity="negate", modality="reported"),
        )
    )

    result = await extract_relations(
        text="Someone said Kai doesn't know Zhao.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].polarity == "negate"
    assert result[0].modality == "reported"


@pytest.mark.asyncio
async def test_deduplication_by_relation_id():
    """Same triple twice → deduplicated, higher confidence wins."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _rel("Kai", "works_for", "Imperial Academy", 0.8),
            _rel("Kai", "works_for", "Imperial Academy", 0.95),
        )
    )

    result = await extract_relations(
        text="Kai works for the Imperial Academy.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].confidence == 0.95


@pytest.mark.asyncio
async def test_idempotent_relation_ids():
    """Same input twice → same relation_ids."""
    fake = FakeProviderClient()
    response = _make_response(
        _rel("Kai", "trusts", "Zhao", 0.9),
    )
    fake.queue_response(response)
    fake.queue_response(response)

    kwargs = dict(
        text="Kai trusts Zhao.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    r1 = await extract_relations(**kwargs)
    r2 = await extract_relations(**kwargs)

    assert len(r1) == 1 and len(r2) == 1
    assert r1[0].relation_id == r2[0].relation_id


@pytest.mark.asyncio
async def test_extraction_error_propagation():
    """ProviderAuthError surfaces as ExtractionError."""
    fake = FakeProviderClient()
    fake.queue_exception(ProviderAuthError("bad key"))

    with pytest.raises(ExtractionError) as exc_info:
        await extract_relations(
            text="Some text.", entities=ENTITIES,
            known_entities=[], user_id=USER_ID,
            project_id=PROJECT_ID, model_source="user_model",
            model_ref="test-model", client=_as_client(fake),
        )

    assert exc_info.value.stage == "provider"


@pytest.mark.asyncio
async def test_curly_braces_in_text_do_not_crash():
    """R2 I1/I7: text with {curly braces} must not crash load_prompt."""
    fake = FakeProviderClient()
    fake.queue_response(_make_response(
        _rel("Kai", "owns", "Zhao", 0.8),
    ))

    result = await extract_relations(
        text='Config was {host: "localhost"}. Kai owns something.',
        entities=ENTITIES,
        known_entities=["The {Ancient} One"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    # Verify braces survived into prompt
    messages = fake.calls[0]["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "{host:" in user_msg["content"]


@pytest.mark.asyncio
async def test_entity_alias_resolution():
    """Subject/object resolved via entity alias, not just display name."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _rel("Ali", "knows", "Kai", 0.85),
        )
    )

    result = await extract_relations(
        text="Ali knows Kai well.",
        entities=ENTITIES,  # Alice has alias "Ali"
        known_entities=["Alice", "Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    # "Ali" resolved to Alice's canonical_id
    alice_ent = next(e for e in ENTITIES if e.name == "Alice")
    assert result[0].subject_id == alice_ent.canonical_id
    assert result[0].subject == "Alice"  # display name from entity


@pytest.mark.asyncio
async def test_empty_relations_from_llm():
    """LLM returns empty relations list → empty result."""
    fake = FakeProviderClient()
    fake.queue_response(json.dumps({"relations": []}))

    result = await extract_relations(
        text="A quiet scene with no interactions.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert result == []


@pytest.mark.asyncio
async def test_mixed_resolved_and_unresolved():
    """One relation resolved, one not — both returned."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _rel("Kai", "works_for", "Imperial Academy", 0.95),
            _rel("Stranger", "visits", "Dark Forest", 0.7),
        )
    )

    result = await extract_relations(
        text="Kai works at the Academy. A stranger visited the Dark Forest.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 2
    resolved = next(r for r in result if r.relation_id is not None)
    unresolved = next(r for r in result if r.relation_id is None)
    assert resolved.subject == "Kai"
    assert unresolved.subject_id is None
