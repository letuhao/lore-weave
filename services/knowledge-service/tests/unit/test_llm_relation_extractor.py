"""Unit tests for K17.5 — LLM relation extractor (SDK path only).

Phase 4a-δ: legacy ProviderClient path was removed; the extractor now
takes only ``llm_client: LLMClient``. Validates:
  - Happy path with entity resolution + relation_id
  - Empty text -> no LLM call
  - Known entities anchoring in subject/object
  - Unresolvable endpoints -> None IDs
  - Predicate normalization
  - Polarity/modality preservation
  - Deduplication by relation_id
  - Idempotent re-run
  - ExtractionError propagation (provider / cancelled / provider_exhausted)
  - Curly braces in text don't crash
  - Entity alias resolution
  - C-LM-STUDIO-FIX null-endpoint filtering
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.db.neo4j_repos.canonical import entity_canonical_id
from app.db.neo4j_repos.relations import relation_id as compute_relation_id
from app.extraction.errors import ExtractionError
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_relation_extractor import (
    LLMRelationCandidate,
    RelationExtractionResponse,
    extract_relations,
    _normalize_predicate,
)
from loreweave_llm.errors import LLMTransientRetryNeededError
from loreweave_llm.models import Job, JobError


# -- FakeLLMClient (duck-typed stand-in for LLMClient) ---------------


class FakeLLMClient:
    """Captures submit_and_wait kwargs + replays a scripted Job for the
    relation_extraction operation."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_job: Any = None
        self.next_exc: Exception | None = None

    def queue_job(
        self,
        *,
        status: str = "completed",
        relations: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        error_message: str = "",
    ) -> None:
        result = {"relations": relations} if relations is not None else None
        error = JobError(code=error_code, message=error_message) if error_code else None
        self.next_job = Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="relation_extraction",
            status=status,  # type: ignore[arg-type]
            result=result,
            error=error,
            submitted_at="2026-04-27T00:00:00Z",
        )

    def queue_exception(self, exc: Exception) -> None:
        self.next_exc = exc

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.next_exc is not None:
            exc = self.next_exc
            self.next_exc = None
            raise exc
        return self.next_job


def _as_client(fake: FakeLLMClient) -> Any:
    return cast(Any, fake)


# -- Fixtures --------------------------------------------------------

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


def _rel(
    subject: str | None,
    predicate: str,
    obj: str | None,
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


# -- Tests -----------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_three_relations():
    """Basic extraction with entity resolution and relation_id."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Kai", "works_for", "Imperial Academy", 0.95),
        _rel("Kai", "trusts", "Zhao", 0.9, polarity="negate"),
        _rel("Alice", "knows", "Bob", 0.85),
    ])

    result = await extract_relations(
        text="Kai works for the Imperial Academy but doesn't trust Zhao. Alice knows Bob.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao", "Alice", "Bob"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
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
    """Empty or whitespace text -> no LLM call."""
    fake = FakeLLMClient()

    for text in ["", "   ", "\n"]:
        result = await extract_relations(
            text=text, entities=ENTITIES,
            known_entities=[], user_id=USER_ID,
            project_id=PROJECT_ID, model_source="user_model",
            model_ref="test-model", llm_client=_as_client(fake),
        )
        assert result == []

    assert len(fake.calls) == 0


@pytest.mark.asyncio
async def test_unresolvable_endpoints_get_none_ids():
    """Subject/object not in entities -> None IDs."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Unknown Person", "owns", "Mystery Artifact", 0.8),
    ])

    result = await extract_relations(
        text="Unknown Person owns Mystery Artifact.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
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
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Kai", "knows", "Zhao", 0.9, polarity="negate", modality="reported"),
    ])

    result = await extract_relations(
        text="Someone said Kai doesn't know Zhao.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].polarity == "negate"
    assert result[0].modality == "reported"


@pytest.mark.asyncio
async def test_deduplication_by_relation_id():
    """Same triple twice -> deduplicated, higher confidence wins."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Kai", "works_for", "Imperial Academy", 0.8),
        _rel("Kai", "works_for", "Imperial Academy", 0.95),
    ])

    result = await extract_relations(
        text="Kai works for the Imperial Academy.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].confidence == 0.95


@pytest.mark.asyncio
async def test_idempotent_relation_ids():
    """Same input twice -> same relation_ids."""
    fake = FakeLLMClient()
    payload = [_rel("Kai", "trusts", "Zhao", 0.9)]

    fake.queue_job(relations=payload)
    kwargs = dict(
        text="Kai trusts Zhao.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )
    r1 = await extract_relations(**kwargs)

    fake.queue_job(relations=payload)
    r2 = await extract_relations(**kwargs)

    assert len(r1) == 1 and len(r2) == 1
    assert r1[0].relation_id == r2[0].relation_id


@pytest.mark.asyncio
async def test_extraction_error_propagation():
    """A failed Job (provider error) surfaces as ExtractionError(stage=provider)."""
    fake = FakeLLMClient()
    fake.queue_job(status="failed", error_code="LLM_INVALID_REQUEST", error_message="bad key")

    with pytest.raises(ExtractionError) as exc_info:
        await extract_relations(
            text="Some text.", entities=ENTITIES,
            known_entities=[], user_id=USER_ID,
            project_id=PROJECT_ID, model_source="user_model",
            model_ref="test-model", llm_client=_as_client(fake),
        )

    assert exc_info.value.stage == "provider"


@pytest.mark.asyncio
async def test_curly_braces_in_text_do_not_crash():
    """R2 I1/I7: text with {curly braces} must not crash load_prompt."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Kai", "owns", "Zhao", 0.8),
    ])

    result = await extract_relations(
        text='Config was {host: "localhost"}. Kai owns something.',
        entities=ENTITIES,
        known_entities=["The {Ancient} One"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    # Verify braces survived into prompt (in user message)
    messages = fake.calls[0]["input"]["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "{host:" in user_msg["content"]


@pytest.mark.asyncio
async def test_entity_alias_resolution():
    """Subject/object resolved via entity alias, not just display name."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Ali", "knows", "Kai", 0.85),
    ])

    result = await extract_relations(
        text="Ali knows Kai well.",
        entities=ENTITIES,  # Alice has alias "Ali"
        known_entities=["Alice", "Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    # "Ali" resolved to Alice's canonical_id
    alice_ent = next(e for e in ENTITIES if e.name == "Alice")
    assert result[0].subject_id == alice_ent.canonical_id
    assert result[0].subject == "Alice"  # display name from entity


@pytest.mark.asyncio
async def test_empty_relations_from_llm():
    """LLM returns empty relations list -> empty result."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[])

    result = await extract_relations(
        text="A quiet scene with no interactions.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert result == []


@pytest.mark.asyncio
async def test_mixed_resolved_and_unresolved():
    """One relation resolved, one not — both returned."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("Kai", "works_for", "Imperial Academy", 0.95),
        _rel("Stranger", "visits", "Dark Forest", 0.7),
    ])

    result = await extract_relations(
        text="Kai works at the Academy. A stranger visited the Dark Forest.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 2
    resolved = next(r for r in result if r.relation_id is not None)
    unresolved = next(r for r in result if r.relation_id is None)
    assert resolved.subject == "Kai"
    assert unresolved.subject_id is None


# -- C-LM-STUDIO-FIX: null-endpoint handling -----------------------


@pytest.mark.asyncio
async def test_null_object_relation_is_filtered_not_rejected():
    """C-LM-STUDIO-FIX scope expansion: when LLM emits null object
    instead of dropping the relation (observed in qwen2.5-coder-14b,
    phi-4, gemma-3-27b during C19 quality eval), the schema validation
    must accept null + the postprocess filter must drop the bad
    relation. The other relations in the batch are NOT lost — this
    is the key contract: one bad LLM-emitted relation can't poison
    the whole extraction."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        # Good relation — should survive postprocess.
        _rel("Kai", "works_for", "Imperial Academy", 0.95),
        # Null-object relation — LLM violation of prompt rule;
        # must be silently dropped by postprocess.
        _rel("Tấm", "cries", None, 0.9),
        # Another good relation — still survives.
        _rel("Alice", "knows", "Bob", 0.85),
    ])
    result = await extract_relations(
        text="Some chapter text.",
        entities=ENTITIES,
        known_entities=[],
        user_id="user-1",
        project_id="project-1",
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )
    assert len(result) == 2  # null-object dropped, 2 good ones kept
    subjects = {r.subject for r in result}
    assert subjects == {"Kai", "Alice"}


@pytest.mark.asyncio
async def test_null_subject_relation_is_filtered():
    """Symmetric: null subject also filtered."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel(None, "exists", "Kai", 0.7),
        _rel("Kai", "works_for", "Imperial Academy", 0.95),
    ])
    result = await extract_relations(
        text="x", entities=ENTITIES, known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="test-model",
        llm_client=_as_client(fake),
    )
    assert len(result) == 1
    assert result[0].subject == "Kai"


@pytest.mark.asyncio
async def test_omitted_subject_field_defaults_to_none_then_filtered():
    """If LLM omits the subject field entirely (not just null), Pydantic
    default kicks in (None) and postprocess filters. Same outcome as
    explicit null."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        # Missing 'subject' key entirely.
        {
            "predicate": "loves", "object": "Bob",
            "polarity": "affirm", "modality": "asserted",
            "confidence": 0.6,
        },
        _rel("Kai", "trusts", "Zhao", 0.9),
    ])
    result = await extract_relations(
        text="x", entities=ENTITIES, known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="test-model",
        llm_client=_as_client(fake),
    )
    assert len(result) == 1
    assert result[0].subject == "Kai"


@pytest.mark.asyncio
async def test_all_null_relations_returns_empty():
    """Edge case: every relation has null endpoint -> empty list, no crash."""
    fake = FakeLLMClient()
    fake.queue_job(relations=[
        _rel("x", "y", None, 0.8),
        _rel(None, "z", "w", 0.8),
    ])
    result = await extract_relations(
        text="x", entities=ENTITIES, known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="test-model",
        llm_client=_as_client(fake),
    )
    assert result == []


# -- Phase 4a-β SDK-path tests --------------------------------------


def _make_entity_for_relation(name: str = "Holmes") -> Any:
    return LLMEntityCandidate(
        name=name, kind="person", aliases=[], confidence=0.95,
        canonical_name=name.lower(), canonical_id=f"cid-{name}",
    )


@pytest.mark.asyncio
async def test_extract_relations_via_llm_client_happy_path():
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        relations=[
            {"subject": "Holmes", "predicate": "lives_in", "object": "Baker Street",
             "polarity": "affirm", "modality": "asserted", "confidence": 0.9},
        ],
    )
    result = await extract_relations(
        text="Holmes lives at Baker Street.",
        entities=[_make_entity_for_relation("Holmes"), _make_entity_for_relation("Baker Street")],
        known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
        llm_client=cast(Any, fake),
    )
    assert len(result) == 1
    call = fake.calls[0]
    assert call["operation"] == "relation_extraction"
    assert call["chunking"].strategy == "paragraphs"
    assert call["chunking"].size == 15
    msgs = call["input"]["messages"]
    assert len(msgs) == 2 and msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Holmes lives at Baker Street."


@pytest.mark.asyncio
async def test_extract_relations_via_llm_client_drops_malformed():
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        relations=[
            {"subject": "Holmes", "predicate": "lives_in", "object": "Baker Street", "confidence": 0.9},  # valid
            {"subject": "Watson"},  # missing predicate
            {"predicate": "knows"},  # tolerated null subject/object (postprocess filters)
            "not-a-dict",
        ],
    )
    result = await extract_relations(
        text="...", entities=[_make_entity_for_relation("Holmes"), _make_entity_for_relation("Baker Street")],
        known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
        llm_client=cast(Any, fake),
    )
    # postprocess filters null endpoints — only Holmes/Baker Street survives
    preds = [c.predicate for c in result]
    assert "lives_in" in preds


@pytest.mark.asyncio
async def test_extract_relations_via_llm_client_cancelled_raises():
    fake = FakeLLMClient()
    fake.queue_job(status="cancelled")
    with pytest.raises(ExtractionError) as exc:
        await extract_relations(
            text="...", entities=[], known_entities=[],
            user_id="user-1", project_id="project-1",
            model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
            llm_client=cast(Any, fake),
        )
    assert exc.value.stage == "cancelled"


@pytest.mark.asyncio
async def test_extract_relations_via_llm_client_transient_retry_exhausted_raises():
    """LLMTransientRetryNeededError from SDK bubbles as ExtractionError(provider_exhausted)."""
    fake = FakeLLMClient()
    fake.queue_exception(LLMTransientRetryNeededError(
        "transient retry exhausted",
        job_id="00000000-0000-0000-0000-000000000001",
        underlying_code="LLM_UPSTREAM_ERROR",
    ))
    with pytest.raises(ExtractionError, match="transient retry") as excinfo:
        await extract_relations(
            text="...", entities=[], known_entities=[],
            user_id="user-1", project_id="project-1",
            model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
            llm_client=cast(Any, fake),
        )
    assert excinfo.value.stage == "provider_exhausted"


@pytest.mark.asyncio
async def test_extract_relations_via_llm_client_chunking_invariant_for_multi_paragraph_input():
    """/review-impl LOW#4 — pin the invariant that the extractor ALWAYS
    sends ChunkingConfig regardless of input length. Mirrors entity
    extractor's regression-lock from 4a-α-followup."""
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        relations=[{"subject": "A", "predicate": "knows", "object": "B",
                    "polarity": "affirm", "modality": "asserted", "confidence": 0.9}],
    )
    long_text = "\n\n".join(f"Paragraph {i}: A knows B." for i in range(30))
    await extract_relations(
        text=long_text,
        entities=[_make_entity_for_relation("A"), _make_entity_for_relation("B")],
        known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
        llm_client=cast(Any, fake),
    )
    call = fake.calls[0]
    assert call["chunking"] is not None
    assert call["chunking"].strategy == "paragraphs"
    assert call["chunking"].size == 15
    user_msg = call["input"]["messages"][1]
    assert user_msg["content"] == long_text
