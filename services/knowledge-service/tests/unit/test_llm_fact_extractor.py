"""Unit tests for K17.7 — LLM fact extractor.

Uses FakeProviderClient + pre-built LLMEntityCandidate fixtures to
test extract_facts without network calls. Validates:
  - Happy path with subject resolution + fact_id
  - Empty text → no LLM call
  - Facts without subject (universal claims)
  - Unresolvable subject → None subject_id
  - All fact types
  - Polarity/modality preservation
  - Deduplication by fact_id
  - Idempotent re-run
  - ExtractionError propagation
  - Curly braces in text don't crash
  - Entity alias resolution for subject
  - Empty facts from LLM
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
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_fact_extractor import (
    LLMFactCandidate,
    FactExtractionResponse,
    extract_facts,
)
from app.extraction.llm_json_parser import ExtractionError


# ── FakeProviderClient ───────────────────────────────────────────

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


# ── Fixtures ─────────────────────────────────────────────────────

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
    _make_entity("Jade Seal", "artifact"),
    _make_entity("Iron Gate", "place"),
    _make_entity("Alice", "person", aliases=["Ali"]),
]


def _make_response(*facts: dict[str, Any]) -> str:
    return json.dumps({"facts": list(facts)})


def _fact(
    content: str,
    type: str = "description",
    subject: str | None = None,
    confidence: float = 0.9,
    polarity: str = "affirm",
    modality: str = "asserted",
) -> dict[str, Any]:
    return {
        "content": content,
        "type": type,
        "subject": subject,
        "polarity": polarity,
        "modality": modality,
        "confidence": confidence,
    }


# ── Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_happy_path_three_facts():
    """Basic extraction with subject resolution and fact_id."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("The Jade Seal was priceless.", "description",
                  subject="Jade Seal", confidence=0.95),
            _fact("Kai did not trust Zhao.", "negation",
                  subject="Kai", confidence=0.9,
                  polarity="negate"),
            _fact("The Empire was vast.", "description",
                  subject=None, confidence=0.85),
        )
    )

    result = await extract_facts(
        text="The Jade Seal was priceless. Kai did not trust Zhao. The Empire was vast.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao", "Jade Seal"],
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
    assert r0.content == "The Jade Seal was priceless."
    assert r0.type == "description"
    assert r0.subject == "Jade Seal"
    assert r0.subject_id is not None
    assert r0.confidence == 0.95
    assert r0.fact_id is not None

    r1 = result[1]
    assert r1.polarity == "negate"
    assert r1.type == "negation"
    assert r1.subject_id is not None

    r2 = result[2]
    assert r2.subject is None
    assert r2.subject_id is None
    assert r2.fact_id is not None  # always set


@pytest.mark.asyncio
async def test_empty_text_returns_empty():
    """Empty or whitespace text → no LLM call."""
    fake = FakeProviderClient()

    for text in ["", "   ", "\n"]:
        result = await extract_facts(
            text=text, entities=ENTITIES,
            known_entities=[], user_id=USER_ID,
            project_id=PROJECT_ID, model_source="user_model",
            model_ref="test-model", client=_as_client(fake),
        )
        assert result == []

    assert len(fake.calls) == 0


@pytest.mark.asyncio
async def test_facts_without_subject_are_valid():
    """Facts with subject=null are kept (universal claims)."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("The Empire was vast.", "description",
                  subject=None, confidence=0.9),
        )
    )

    result = await extract_facts(
        text="The Empire was vast.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].subject is None
    assert result[0].subject_id is None


@pytest.mark.asyncio
async def test_unresolvable_subject_keeps_display_name():
    """Subject not in entities → subject_id=None, display name preserved."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("The Unknown King was mighty.", "description",
                  subject="Unknown King", confidence=0.8),
        )
    )

    result = await extract_facts(
        text="The Unknown King was mighty.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].subject == "Unknown King"
    assert result[0].subject_id is None


@pytest.mark.asyncio
async def test_all_fact_types():
    """All five fact types are accepted."""
    fake = FakeProviderClient()
    types = ["description", "attribute", "negation", "temporal", "causal"]
    facts = [
        _fact(f"Fact about {t}.", t, subject="Kai", confidence=0.9)
        for t in types
    ]
    fake.queue_response(_make_response(*facts))

    result = await extract_facts(
        text="Many facts about Kai.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 5
    result_types = {c.type for c in result}
    assert result_types == set(types)


@pytest.mark.asyncio
async def test_polarity_and_modality_preserved():
    """Polarity and modality from LLM response are preserved."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("Alice claimed the Seal was fake.", "description",
                  subject="Jade Seal", confidence=0.7,
                  polarity="affirm", modality="reported"),
        )
    )

    result = await extract_facts(
        text="Alice claimed the Seal was fake.",
        entities=ENTITIES,
        known_entities=["Alice", "Jade Seal"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].polarity == "affirm"
    assert result[0].modality == "reported"


@pytest.mark.asyncio
async def test_deduplication_by_fact_id():
    """Same fact twice → deduplicated, higher confidence wins."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("The Jade Seal was priceless.", "description",
                  subject="Jade Seal", confidence=0.8),
            _fact("The Jade Seal was priceless.", "description",
                  subject="Jade Seal", confidence=0.95),
        )
    )

    result = await extract_facts(
        text="The Jade Seal was priceless.",
        entities=ENTITIES,
        known_entities=["Jade Seal"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].confidence == 0.95


@pytest.mark.asyncio
async def test_idempotent_fact_ids():
    """Same input twice → same fact_ids."""
    fake = FakeProviderClient()
    response = _make_response(
        _fact("Kai is brave.", "attribute", subject="Kai", confidence=0.9),
    )
    fake.queue_response(response)
    fake.queue_response(response)

    kwargs = dict(
        text="Kai is brave.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    r1 = await extract_facts(**kwargs)
    r2 = await extract_facts(**kwargs)

    assert len(r1) == 1 and len(r2) == 1
    assert r1[0].fact_id == r2[0].fact_id


@pytest.mark.asyncio
async def test_extraction_error_propagation():
    """ProviderAuthError surfaces as ExtractionError."""
    fake = FakeProviderClient()
    fake.queue_exception(ProviderAuthError("bad key"))

    with pytest.raises(ExtractionError) as exc_info:
        await extract_facts(
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
        _fact("Kai is brave.", "attribute", subject="Kai"),
    ))

    result = await extract_facts(
        text='Config was {host: "localhost"}. Kai is brave.',
        entities=ENTITIES,
        known_entities=["The {Ancient} One"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    messages = fake.calls[0]["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "{host:" in user_msg["content"]


@pytest.mark.asyncio
async def test_entity_alias_resolution_for_subject():
    """Subject resolved via entity alias."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("Ali is kind.", "attribute", subject="Ali"),
        )
    )

    result = await extract_facts(
        text="Ali is kind.",
        entities=ENTITIES,  # Alice has alias "Ali"
        known_entities=["Alice"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    alice_ent = next(e for e in ENTITIES if e.name == "Alice")
    assert result[0].subject == "Alice"
    assert result[0].subject_id == alice_ent.canonical_id


@pytest.mark.asyncio
async def test_empty_facts_from_llm():
    """LLM returns empty facts list → empty result."""
    fake = FakeProviderClient()
    fake.queue_response(json.dumps({"facts": []}))

    result = await extract_facts(
        text="A quiet passage with no facts.",
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
async def test_empty_content_facts_are_skipped():
    """R2 I3: Facts with empty or whitespace-only content are dropped."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("", "description", subject="Kai", confidence=0.9),
            _fact("   ", "attribute", subject="Kai", confidence=0.8),
            _fact("Kai is brave.", "attribute", subject="Kai", confidence=0.7),
        )
    )

    result = await extract_facts(
        text="Kai is brave.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].content == "Kai is brave."


@pytest.mark.asyncio
async def test_whitespace_variant_dedup():
    """R2 I4: Facts differing only in whitespace produce same fact_id → dedup."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _fact("Kai  is   brave.", "attribute", subject="Kai", confidence=0.8),
            _fact("Kai is brave.", "attribute", subject="Kai", confidence=0.95),
        )
    )

    result = await extract_facts(
        text="Kai is brave.",
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


# ── Phase 4a-β SDK-path tests ────────────────────────────────────────


from typing import Any, cast


class FakeLLMClientForFacts:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_job: Any = None

    def queue_job(self, *, status: str, facts: list[dict[str, Any]] | None = None,
                  error_code: str | None = None, error_message: str = "") -> None:
        from loreweave_llm.models import Job, JobError
        result = {"facts": facts} if facts is not None else None
        error = JobError(code=error_code, message=error_message) if error_code else None
        self.next_job = Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="fact_extraction",
            status=status,  # type: ignore[arg-type]
            result=result,
            error=error,
            submitted_at="2026-04-27T00:00:00Z",
        )

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.next_job


def _make_entity_for_fact(name: str = "Holmes") -> Any:
    from app.extraction.llm_entity_extractor import LLMEntityCandidate
    return LLMEntityCandidate(
        name=name, kind="person", aliases=[], confidence=0.95,
        canonical_name=name.lower(), canonical_id=f"cid-{name}",
    )


@pytest.mark.asyncio
async def test_extract_facts_via_llm_client_happy_path():
    fake = FakeLLMClientForFacts()
    fake.queue_job(
        status="completed",
        facts=[
            {"content": "Holmes is a detective.", "type": "description",
             "subject": "Holmes", "polarity": "affirm", "modality": "asserted",
             "confidence": 0.9},
        ],
    )
    result = await extract_facts(
        text="Holmes is a detective.",
        entities=[_make_entity_for_fact("Holmes")],
        known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
        llm_client=cast(Any, fake),
    )
    assert len(result) == 1
    call = fake.calls[0]
    assert call["operation"] == "fact_extraction"
    assert call["chunking"].size == 15
    msgs = call["input"]["messages"]
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"


@pytest.mark.asyncio
async def test_extract_facts_via_llm_client_drops_malformed():
    fake = FakeLLMClientForFacts()
    fake.queue_job(
        status="completed",
        facts=[
            {"content": "Holmes is brilliant.", "type": "description", "confidence": 0.9},  # ✓
            {"type": "description"},  # ✗ missing content
            {"content": "  ", "type": "description"},  # ✗ whitespace-only
            {"content": "Bad type", "type": "INVALID_TYPE"},  # ✗ FactType not in Literal
            # /review-impl LOW#5 — explicit-null type
            {"content": "Null type", "type": None},  # ✗
        ],
    )
    result = await extract_facts(
        text="...", entities=[],
        known_entities=[],
        user_id="user-1", project_id="project-1",
        model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
        llm_client=cast(Any, fake),
    )
    contents = [c.content for c in result]
    assert "Holmes is brilliant." in contents
    assert "Bad type" not in contents
    assert "Null type" not in contents  # LOW#5 — explicit-null type dropped


@pytest.mark.asyncio
async def test_extract_facts_via_llm_client_cancelled_raises():
    fake = FakeLLMClientForFacts()
    fake.queue_job(status="cancelled")
    with pytest.raises(ExtractionError) as exc:
        await extract_facts(
            text="...", entities=[], known_entities=[],
            user_id="user-1", project_id="project-1",
            model_source="user_model", model_ref="00000000-0000-0000-0000-000000000001",
            llm_client=cast(Any, fake),
        )
    assert exc.value.stage == "cancelled"


@pytest.mark.asyncio
async def test_extract_facts_via_llm_client_chunking_invariant_for_multi_paragraph_input():
    """/review-impl LOW#4 — pin the invariant that the extractor ALWAYS
    sends ChunkingConfig regardless of input length."""
    fake = FakeLLMClientForFacts()
    fake.queue_job(
        status="completed",
        facts=[{"content": "X is Y.", "type": "description", "subject": None,
                "polarity": "affirm", "modality": "asserted", "confidence": 0.9}],
    )
    long_text = "\n\n".join(f"Paragraph {i}: X is Y." for i in range(30))
    await extract_facts(
        text=long_text, entities=[],
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
