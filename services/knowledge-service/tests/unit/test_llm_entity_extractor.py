"""Unit tests for K17.4 — LLM entity extractor (SDK path only).

Phase 4a-δ: legacy ProviderClient path was removed; the extractor now
takes only ``llm_client: LLMClient``. Uses a FakeLLMClient (duck-typed
stand-in for ``app.clients.llm_client.LLMClient``) to drive the
extractor without any network calls. Validates:
  - Happy path with canonical ID stability
  - Empty/whitespace input -> no LLM call
  - Known entities anchoring
  - Deduplication by canonical_id with alias merging
  - Idempotent re-run (same input -> same canonical_ids)
  - All entity kinds
  - ExtractionError propagation (provider / provider_exhausted /
    cancelled stages)
  - Whitespace-only name filtering
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.db.neo4j_repos.canonical import entity_canonical_id
from app.extraction.errors import ExtractionError
from app.extraction.llm_entity_extractor import (
    EntityExtractionResponse,
    LLMEntityCandidate,
    extract_entities,
)
from loreweave_llm.errors import LLMTransientRetryNeededError
from loreweave_llm.models import Job, JobError


# -- FakeLLMClient (duck-typed stand-in for LLMClient) ---------------


class FakeLLMClient:
    """Captures submit_and_wait kwargs + replays a scripted Job.

    Mirrors ``_FakeLLMClientForSummary`` in test_regenerate_summaries.py
    but tailored to the entity_extraction operation envelope."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_job: Any = None
        self.next_exc: Exception | None = None

    def queue_job(
        self,
        *,
        status: str = "completed",
        entities: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        error_message: str = "",
    ) -> None:
        result = {"entities": entities} if entities is not None else None
        error = JobError(code=error_code, message=error_message) if error_code else None
        self.next_job = Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="entity_extraction",
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


# -- Tests -----------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_three_entities():
    """Basic extraction returns three entities with canonical IDs."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Kai", "person", 1.0),
        _entity("Harbin", "place", 0.95),
        _entity("Jade Seal", "artifact", 0.9),
    ])

    result = await extract_entities(
        text="Kai left Harbin carrying the Jade Seal.",
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
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
    fake = FakeLLMClient()

    for text in ["", "   ", "\n\t  "]:
        result = await extract_entities(
            text=text,
            known_entities=[],
            user_id=USER_ID,
            project_id=PROJECT_ID,
            model_source="user_model",
            model_ref="test-model",
            llm_client=_as_client(fake),
        )
        assert result == []

    assert len(fake.calls) == 0  # no LLM calls made


@pytest.mark.asyncio
async def test_known_entities_anchoring():
    """LLM returns 'kai' but known_entities has 'Kai' -> canonical spelling used."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("kai", "person", 0.95),  # lowercase from LLM
    ])

    result = await extract_entities(
        text="kai walked through the forest.",
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].name == "Kai"  # anchored to known spelling


@pytest.mark.asyncio
async def test_deduplication_merges_aliases():
    """LLM returns 'Kai' and 'KAI' -> deduplicated into one, alias merged."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Kai", "person", 0.9, aliases=["Kai-kun"]),
        _entity("KAI", "person", 0.95, aliases=["Master Kai"]),
    ])

    result = await extract_entities(
        text="Kai, also known as KAI, entered the room.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
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
    """Same input twice -> same canonical_ids."""
    fake = FakeLLMClient()
    entities_payload = [
        _entity("Kai", "person", 0.9),
        _entity("Harbin", "place", 0.8),
    ]

    fake.queue_job(entities=entities_payload)
    kwargs = dict(
        text="Kai traveled to Harbin.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )
    result1 = await extract_entities(**kwargs)

    fake.queue_job(entities=entities_payload)
    result2 = await extract_entities(**kwargs)

    assert len(result1) == len(result2)
    for c1, c2 in zip(result1, result2):
        assert c1.canonical_id == c2.canonical_id
        assert c1.canonical_name == c2.canonical_name


@pytest.mark.asyncio
async def test_all_entity_kinds():
    """All six entity kinds are accepted."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Kai", "person", 0.9),
        _entity("Harbin", "place", 0.9),
        _entity("Imperial Academy", "organization", 0.9),
        _entity("Jade Seal", "artifact", 0.9),
        _entity("Honor", "concept", 0.8),
        _entity("The Anomaly", "other", 0.7),
    ])

    result = await extract_entities(
        text="Chapter text with many entities.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 6
    kinds = {c.kind for c in result}
    assert kinds == {"person", "place", "organization", "artifact", "concept", "other"}


@pytest.mark.asyncio
async def test_extraction_error_propagation():
    """A failed Job (provider error) surfaces as ExtractionError(stage=provider)."""
    fake = FakeLLMClient()
    fake.queue_job(
        status="failed",
        error_code="LLM_INVALID_REQUEST",
        error_message="invalid API key",
    )

    with pytest.raises(ExtractionError) as exc_info:
        await extract_entities(
            text="Some text to extract.",
            known_entities=[],
            user_id=USER_ID,
            project_id=PROJECT_ID,
            model_source="user_model",
            model_ref="test-model",
            llm_client=_as_client(fake),
        )

    assert exc_info.value.stage == "provider"


@pytest.mark.asyncio
async def test_empty_entities_from_llm():
    """LLM returns empty entities list -> empty result."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[])

    result = await extract_entities(
        text="A paragraph with no named entities at all.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert result == []


@pytest.mark.asyncio
async def test_project_id_none_uses_global_scope():
    """project_id=None produces a different canonical_id than a real project."""
    fake = FakeLLMClient()

    fake.queue_job(entities=[_entity("Kai", "person", 0.9)])
    result_global = await extract_entities(
        text="Kai speaks.",
        known_entities=[],
        user_id=USER_ID,
        project_id=None,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    fake.queue_job(entities=[_entity("Kai", "person", 0.9)])
    result_project = await extract_entities(
        text="Kai speaks.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result_global) == 1
    assert len(result_project) == 1
    assert result_global[0].canonical_id != result_project[0].canonical_id


@pytest.mark.asyncio
async def test_known_entities_passed_in_prompt():
    """Known entities are serialized as JSON in the LLM system prompt."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[_entity("Kai", "person", 0.9)])

    await extract_entities(
        text="Kai enters.",
        known_entities=["Kai", "Harbin"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    # Verify the system prompt sent to the LLM contains the known entities
    assert len(fake.calls) == 1
    messages = fake.calls[0]["input"]["messages"]
    sys_msg = next(m for m in messages if m["role"] == "system")
    assert '["Kai", "Harbin"]' in sys_msg["content"]


@pytest.mark.asyncio
async def test_confidence_ordering():
    """Results are sorted by confidence descending."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Low", "person", 0.5),
        _entity("High", "person", 1.0),
        _entity("Mid", "person", 0.75),
    ])

    result = await extract_entities(
        text="Low, High, and Mid appeared.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    confidences = [c.confidence for c in result]
    assert confidences == [1.0, 0.75, 0.5]


@pytest.mark.asyncio
async def test_r2_i1_text_with_curly_braces_does_not_crash():
    """R2 I1/I7: text or known_entities containing { } must not crash
    load_prompt's str.format_map. Common in code-quoting novels or
    entity names like 'The {Ancient} One'."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Config Server", "artifact", 0.8),
    ])

    result = await extract_entities(
        text='The config was {host: "localhost", port: 8080}.',
        known_entities=["The {Ancient} One"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].name == "Config Server"
    # Verify the curly braces survived into the user message text
    assert len(fake.calls) == 1
    messages = fake.calls[0]["input"]["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "{host:" in user_msg["content"]
    sys_msg = next(m for m in messages if m["role"] == "system")
    assert "{Ancient}" in sys_msg["content"]


@pytest.mark.asyncio
async def test_r2_i12_same_name_different_kind_produces_two_candidates():
    """R2 I3/I12: same display name with different kinds should produce
    two separate candidates (different canonical_id because kind is
    part of the hash)."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Kai", "person", 0.9),
        _entity("Kai", "concept", 0.7),
    ])

    result = await extract_entities(
        text="Kai is both a person and a concept.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 2
    kinds = {c.kind for c in result}
    assert kinds == {"person", "concept"}
    ids = {c.canonical_id for c in result}
    assert len(ids) == 2  # different canonical_ids


@pytest.mark.asyncio
async def test_canonical_name_computed():
    """canonical_name is the output of canonicalize_entity_name."""
    fake = FakeLLMClient()
    fake.queue_job(entities=[
        _entity("Master Kai", "person", 0.9),
    ])

    result = await extract_entities(
        text="Master Kai arrived.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        llm_client=_as_client(fake),
    )

    assert len(result) == 1
    # "Master" is an honorific stripped by canonicalize_entity_name
    assert result[0].canonical_name == "kai"
    assert result[0].name == "Master Kai"  # display name preserved


# -- Phase 4a-α Step 2 — SDK-routed path tests -----------------------


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_happy_path():
    """SDK path returns parsed entities when job completes with valid result."""
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        entities=[
            {"name": "Holmes", "kind": "person", "aliases": ["Sherlock"], "confidence": 0.95},
            {"name": "Baker Street", "kind": "place", "aliases": [], "confidence": 0.8},
        ],
    )
    result = await extract_entities(
        text="Holmes lived at Baker Street.",
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref=USER_ID,  # any UUID-shaped string
        llm_client=cast(Any, fake),
    )
    assert len(result) == 2
    names = {c.name for c in result}
    assert names == {"Holmes", "Baker Street"}
    # Verify operation + job_meta + chunking + 2-message structure
    # (system instructions + user text) per Phase 4a-α-followup.
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["operation"] == "entity_extraction"
    # 4a-α-followup re-enables chunking on the user message; system
    # message is preserved across chunks by the gateway.
    assert call["chunking"] is not None
    assert call["chunking"].strategy == "paragraphs"
    assert call["chunking"].size == 15
    assert call["job_meta"]["extractor"] == "entity"
    # Messages must be 2-element [system, user] so the gateway chunker
    # only chunks the user (text) message — chunks 2..N preserve system
    # instructions verbatim. /review-impl cycle 2 HIGH#1 root cause.
    msgs = call["input"]["messages"]
    assert len(msgs) == 2, f"expected [system, user], got {len(msgs)} messages"
    assert msgs[0]["role"] == "system"
    assert "Entity Extraction" in msgs[0]["content"]
    assert "{known_entities}" not in msgs[0]["content"], (
        "system prompt should have known_entities substituted, not literal"
    )
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Holmes lived at Baker Street."


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_drops_malformed_items():
    """Tolerant parser drops items missing required fields (LOW#11)."""
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        entities=[
            {"name": "Holmes", "kind": "person", "confidence": 0.9},  # valid
            {"kind": "person"},  # missing name
            {"name": "Watson"},  # missing kind
            {"name": "  ", "kind": "person"},  # whitespace-only name
            "not-a-dict",  # wrong type
            {"name": "Moriarty", "kind": "person", "confidence": 1.5},  # confidence clamped
        ],
    )
    result = await extract_entities(
        text="...", known_entities=[],
        user_id=USER_ID, project_id=PROJECT_ID,
        model_source="user_model", model_ref=USER_ID,
        llm_client=cast(Any, fake),
    )
    names = {c.name for c in result}
    assert "Holmes" in names
    assert "Moriarty" in names
    assert "Watson" not in names
    moriarty = next(c for c in result if c.name == "Moriarty")
    assert moriarty.confidence == 1.0  # clamped from 1.5


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_cancelled_raises_with_stage():
    """Per /review-impl MED#3 — cancelled job MUST raise a distinct
    ExtractionError(stage='cancelled') so the orchestrator/runner can
    flip extraction_jobs.status to cancelled (NOT completed-with-zero-
    entities, which would lie to the user about the cancel result)."""
    fake = FakeLLMClient()
    fake.queue_job(status="cancelled")
    with pytest.raises(ExtractionError) as excinfo:
        await extract_entities(
            text="...", known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref=USER_ID,
            llm_client=cast(Any, fake),
        )
    assert excinfo.value.stage == "cancelled"


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_failed_raises_extraction_error():
    """status=failed (non-transient code) raises ExtractionError."""
    fake = FakeLLMClient()
    fake.queue_job(status="failed", error_code="LLM_INVALID_REQUEST", error_message="bad model")
    with pytest.raises(ExtractionError, match="entity_extraction"):
        await extract_entities(
            text="...", known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref=USER_ID,
            llm_client=cast(Any, fake),
        )


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_transient_retry_exhausted_raises():
    """LLMTransientRetryNeededError from SDK bubbles as ExtractionError(provider_exhausted)."""
    fake = FakeLLMClient()
    fake.queue_exception(LLMTransientRetryNeededError(
        "transient retry exhausted",
        job_id="00000000-0000-0000-0000-000000000001",
        underlying_code="LLM_UPSTREAM_ERROR",
    ))
    with pytest.raises(ExtractionError, match="transient retry") as excinfo:
        await extract_entities(
            text="...", known_entities=[],
            user_id=USER_ID, project_id=PROJECT_ID,
            model_source="user_model", model_ref=USER_ID,
            llm_client=cast(Any, fake),
        )
    assert excinfo.value.stage == "provider_exhausted"


# -- Phase 4a-α-followup /review-impl regression locks ---------------


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_chunking_invariant_for_multi_paragraph_input():
    """/review-impl LOW#2 — pin the invariant that the extractor ALWAYS
    sends ChunkingConfig regardless of input length. The gateway decides
    chunk count (chunker may return 1 chunk for short inputs); the
    extractor must always opt in.

    Earlier happy-path test used 1-paragraph text — a regression that
    accidentally set chunking=None on multi-paragraph inputs would not
    be caught there. This test exercises a 30-paragraph input."""
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        entities=[{"name": "Holmes", "kind": "person", "confidence": 0.9}],
    )
    long_text = "\n\n".join(f"Paragraph {i}: Holmes acted." for i in range(30))
    await extract_entities(
        text=long_text,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref=USER_ID,
        llm_client=cast(Any, fake),
    )
    call = fake.calls[0]
    assert call["chunking"] is not None, (
        "extractor must opt-in to chunking regardless of input length"
    )
    assert call["chunking"].strategy == "paragraphs"
    assert call["chunking"].size == 15
    # Verify the user message carries the FULL text (not pre-chunked
    # by knowledge-service — that's the gateway's job).
    user_msg = call["input"]["messages"][1]
    assert user_msg["content"] == long_text


@pytest.mark.asyncio
async def test_extract_entities_via_llm_client_cross_chunk_alias_variant_known_limitation():
    """/review-impl MED#1 — REGRESSION-LOCK for the known cross-chunk
    discovered-entity priming gap.

    System message KNOWN_ENTITIES is preserved across chunks (good), so
    pre-existing graph entities prime every chunk. But entities
    DISCOVERED in chunk N are NOT fed to chunk N+1's prompt — the
    gateway dispatches chunks independently.

    Concrete failure mode: a character introduced as 'Helen Stoner' in
    chunk 0 and referred to as 'Miss Stoner' in chunk 1 would be
    EXTRACTED AS TWO DISTINCT ENTITIES because:
      - chunk 1's LLM never sees 'Helen Stoner' so it can't snap to it
      - aggregator's (name, kind) dedup key won't merge them
      - knowledge-service's _postprocess only anchors against the
        caller-supplied known_entities, not against earlier extractions
        from the same job

    This test pins the limitation by simulating the failure mode at
    the result-shape layer: when the LLM returns name variants of one
    person across chunks, the extractor surfaces both. Phase 6 fix:
    gateway carries chunk-N entities into chunk-N+1 prompt OR
    knowledge-service adds a post-aggregation alias-substring pass."""
    fake = FakeLLMClient()
    fake.queue_job(
        status="completed",
        entities=[
            # Simulates what the gateway aggregator would emit when
            # chunks 0 and 1 each independently extracted the same
            # person under different names.
            {"name": "Helen Stoner", "kind": "person", "confidence": 0.95},
            {"name": "Miss Stoner", "kind": "person", "confidence": 0.9},
        ],
    )
    result = await extract_entities(
        text="(simulated multi-chunk chapter — see test docstring)",
        known_entities=[],  # no prior graph entries to anchor against
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref=USER_ID,
        llm_client=cast(Any, fake),
    )
    # CURRENT BEHAVIOR (4a-α-followup): both variants survive as
    # distinct LLMEntityCandidate rows because canonical_id hashes
    # over the full name. When Phase 6 (or knowledge-service post-
    # aggregation alias merge) lands, this test should FLIP to assert
    # they were merged into one candidate with aliases=['Miss Stoner'].
    names = sorted(c.name for c in result)
    assert names == ["Helen Stoner", "Miss Stoner"], (
        "regression-lock: cross-chunk alias variants currently survive "
        "as distinct entities. If this test fails after a future change, "
        "either Phase 6 cross-chunk priming shipped (good — flip the "
        "assertion to expect a merge) OR a regression silently changed "
        "the dedup contract (bad — investigate)."
    )
