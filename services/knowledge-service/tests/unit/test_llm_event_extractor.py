"""Unit tests for K17.6 — LLM event extractor.

Uses FakeProviderClient + pre-built LLMEntityCandidate fixtures to
test extract_events without network calls. Validates:
  - Happy path with participant resolution + event_id
  - Empty text → no LLM call
  - Unresolvable participants → None IDs
  - Event kind preservation
  - Deduplication by event_id
  - Idempotent re-run
  - ExtractionError propagation
  - Curly braces in text don't crash
  - Entity alias resolution for participants
  - Empty events from LLM
  - Events without participants are dropped
  - Location and time_cue preservation
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
from app.extraction.llm_event_extractor import (
    LLMEventCandidate,
    EventExtractionResponse,
    extract_events,
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
    _make_entity("Harbin", "place"),
    _make_entity("Iron Gate", "place"),
    _make_entity("Alice", "person", aliases=["Ali"]),
]


def _make_response(*events: dict[str, Any]) -> str:
    return json.dumps({"events": list(events)})


def _event(
    name: str,
    kind: str = "action",
    participants: list[str] | None = None,
    location: str | None = None,
    time_cue: str | None = None,
    summary: str = "Something happened.",
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "participants": participants or [],
        "location": location,
        "time_cue": time_cue,
        "summary": summary,
        "confidence": confidence,
    }


# ── Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_happy_path_two_events():
    """Basic extraction with participant resolution and event_id."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event(
                "Kai leaves Harbin", "travel",
                participants=["Kai"],
                location="Harbin", time_cue="at dawn",
                summary="Kai departs from Harbin.",
                confidence=0.95,
            ),
            _event(
                "Battle at Iron Gate", "battle",
                participants=["Zhao"],
                location="Iron Gate", time_cue="later that day",
                summary="Zhao fights rebels at the Iron Gate.",
                confidence=0.9,
            ),
        )
    )

    result = await extract_events(
        text="At dawn, Kai left Harbin. Later that day, Zhao battled at the Iron Gate.",
        entities=ENTITIES,
        known_entities=["Kai", "Zhao", "Harbin", "Iron Gate"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 2
    assert len(fake.calls) == 1

    # Sorted by confidence descending
    r0 = result[0]
    assert r0.name == "Kai leaves Harbin"
    assert r0.kind == "travel"
    assert r0.participants == ["Kai"]
    assert r0.participant_ids[0] is not None
    assert r0.location == "Harbin"
    assert r0.time_cue == "at dawn"
    assert r0.confidence == 0.95
    assert r0.event_id is not None

    r1 = result[1]
    assert r1.kind == "battle"
    assert r1.participants == ["Zhao"]
    assert r1.event_id is not None


@pytest.mark.asyncio
async def test_empty_text_returns_empty():
    """Empty or whitespace text → no LLM call."""
    fake = FakeProviderClient()

    for text in ["", "   ", "\n"]:
        result = await extract_events(
            text=text, entities=ENTITIES,
            known_entities=[], user_id=USER_ID,
            project_id=PROJECT_ID, model_source="user_model",
            model_ref="test-model", client=_as_client(fake),
        )
        assert result == []

    assert len(fake.calls) == 0


@pytest.mark.asyncio
async def test_unresolvable_participants_get_none_ids():
    """Participants not in entities → None IDs, event_id=None."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event("Stranger arrives", "action",
                   participants=["Unknown Person"],
                   summary="A stranger arrives."),
        )
    )

    result = await extract_events(
        text="A stranger arrives in town.",
        entities=ENTITIES,
        known_entities=[],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].participant_ids == [None]
    # event_id is always set (hashed from display names, not resolved IDs)
    assert result[0].event_id is not None


@pytest.mark.asyncio
async def test_all_event_kinds():
    """All eight event kinds are accepted."""
    fake = FakeProviderClient()
    kinds = ["action", "dialogue", "battle", "travel",
             "discovery", "death", "birth", "other"]
    events = [
        _event(f"Event {k}", k, participants=["Kai"],
               summary=f"A {k} event.", confidence=0.9)
        for k in kinds
    ]
    fake.queue_response(_make_response(*events))

    result = await extract_events(
        text="Many things happened to Kai.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 8
    result_kinds = {c.kind for c in result}
    assert result_kinds == set(kinds)


@pytest.mark.asyncio
async def test_deduplication_by_event_id():
    """Same event twice → deduplicated, higher confidence wins."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event("Kai leaves Harbin", "travel",
                   participants=["Kai"], summary="Kai departs.", confidence=0.8),
            _event("Kai leaves Harbin", "travel",
                   participants=["Kai"], summary="Kai departs.", confidence=0.95),
        )
    )

    result = await extract_events(
        text="Kai left Harbin.",
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
async def test_idempotent_event_ids():
    """Same input twice → same event_ids."""
    fake = FakeProviderClient()
    response = _make_response(
        _event("Kai leaves Harbin", "travel",
               participants=["Kai"], summary="Kai departs.", confidence=0.9),
    )
    fake.queue_response(response)
    fake.queue_response(response)

    kwargs = dict(
        text="Kai left Harbin.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    r1 = await extract_events(**kwargs)
    r2 = await extract_events(**kwargs)

    assert len(r1) == 1 and len(r2) == 1
    assert r1[0].event_id == r2[0].event_id


@pytest.mark.asyncio
async def test_extraction_error_propagation():
    """ProviderAuthError surfaces as ExtractionError."""
    fake = FakeProviderClient()
    fake.queue_exception(ProviderAuthError("bad key"))

    with pytest.raises(ExtractionError) as exc_info:
        await extract_events(
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
        _event("Kai acts", "action", participants=["Kai"],
               summary="Kai does something."),
    ))

    result = await extract_events(
        text='Config was {host: "localhost"}. Kai acted.',
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
async def test_entity_alias_resolution_for_participants():
    """Participants resolved via entity alias."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event("Ali meets Kai", "dialogue",
                   participants=["Ali", "Kai"],
                   summary="Ali talks to Kai."),
        )
    )

    result = await extract_events(
        text="Ali met Kai at the gate.",
        entities=ENTITIES,  # Alice has alias "Ali"
        known_entities=["Alice", "Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    alice_ent = next(e for e in ENTITIES if e.name == "Alice")
    # "Ali" resolved to Alice
    assert result[0].participants[0] == "Alice"
    assert result[0].participant_ids[0] == alice_ent.canonical_id


@pytest.mark.asyncio
async def test_empty_events_from_llm():
    """LLM returns empty events list → empty result."""
    fake = FakeProviderClient()
    fake.queue_response(json.dumps({"events": []}))

    result = await extract_events(
        text="A quiet scene.",
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
async def test_events_without_participants_are_dropped():
    """Events with empty participant list are dropped (prompt rule 2)."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event("Something happened", "action",
                   participants=[], summary="No one involved."),
            _event("Kai acted", "action",
                   participants=["Kai"], summary="Kai did something."),
        )
    )

    result = await extract_events(
        text="Something happened. Kai acted.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].name == "Kai acted"


@pytest.mark.asyncio
async def test_location_and_time_cue_preserved():
    """Location and time_cue from LLM response are preserved."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event("Kai travels", "travel",
                   participants=["Kai"],
                   location="Harbin",
                   time_cue="at dawn",
                   summary="Kai travels at dawn."),
        )
    )

    result = await extract_events(
        text="At dawn, Kai traveled to Harbin.",
        entities=ENTITIES,
        known_entities=["Kai", "Harbin"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].location == "Harbin"
    assert result[0].time_cue == "at dawn"


@pytest.mark.asyncio
async def test_mixed_resolved_and_unresolved_participants():
    """Event with both resolved and unresolved participants."""
    fake = FakeProviderClient()
    fake.queue_response(
        _make_response(
            _event("Meeting at the gate", "dialogue",
                   participants=["Kai", "Stranger"],
                   summary="Kai meets a stranger."),
        )
    )

    result = await extract_events(
        text="Kai met a stranger at the gate.",
        entities=ENTITIES,
        known_entities=["Kai"],
        user_id=USER_ID,
        project_id=PROJECT_ID,
        model_source="user_model",
        model_ref="test-model",
        client=_as_client(fake),
    )

    assert len(result) == 1
    assert result[0].participant_ids[0] is not None  # Kai resolved
    assert result[0].participant_ids[1] is None       # Stranger not
    assert result[0].event_id is not None  # at least one resolved


# ── C18 event_date validation ──────────────────────────────────────


def test_llm_event_event_date_truncated_iso_accepted():
    """C18: _LLMEvent accepts year-only, year-month, full date."""
    from app.extraction.llm_event_extractor import _LLMEvent
    for v in ("1880", "1880-06", "1880-06-15"):
        ev = _LLMEvent(
            name="x", kind="action", participants=["a"],
            summary="s", confidence=0.9, event_date=v,
        )
        assert ev.event_date == v


def test_llm_event_event_date_malformed_coerced_to_none():
    """C18: invalid date strings (free-text leak from LLM, missing
    leading zeros, fictional eras) coerce to None instead of
    rejecting the whole event. The rest of the event metadata is
    still useful."""
    from app.extraction.llm_event_extractor import _LLMEvent
    for bad in ("summer 1880", "TA 3019", "1880-13", "1880-06-32",
                "1880-6", "1880/06/15", "", "not a date"):
        ev = _LLMEvent(
            name="x", kind="action", participants=["a"],
            summary="s", confidence=0.9, event_date=bad,
        )
        assert ev.event_date is None, f"{bad!r} should coerce to None"


def test_llm_event_event_date_default_none():
    """C18: omitting event_date defaults to None (back-compat — pre-C18
    LLM responses without the field still parse)."""
    from app.extraction.llm_event_extractor import _LLMEvent
    ev = _LLMEvent(
        name="x", kind="action", participants=["a"],
        summary="s", confidence=0.9,
    )
    assert ev.event_date is None
