"""K18.2 — unit tests for the L2 fact selector."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.context.intent.classifier import Intent, IntentResult
from app.context.selectors.facts import (
    L2FactResult,
    format_relation,
    format_relation_hop,
    select_l2_facts,
)
from app.db.neo4j_repos.entities import Entity
from app.db.neo4j_repos.facts import Fact
from app.db.neo4j_repos.relations import Relation, RelationHop


USER_ID = "user-1"
PROJECT_ID = "project-1"


def _intent(
    intent: Intent = Intent.SPECIFIC_ENTITY,
    entities: tuple[str, ...] = ("Arthur",),
    hop_count: int = 1,
) -> IntentResult:
    return IntentResult(
        intent=intent,
        entities=entities,
        signals=(),
        hop_count=hop_count,
        recency_weight=1.0,
    )


def _entity(name: str, eid: str) -> Entity:
    return Entity(
        id=eid,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name=name,
        canonical_name=name.lower(),
        kind="character",
    )


def _relation(
    rid: str, subj_name: str, subj_id: str,
    predicate: str, obj_name: str, obj_id: str,
) -> Relation:
    return Relation(
        id=rid,
        user_id=USER_ID,
        subject_id=subj_id,
        object_id=obj_id,
        predicate=predicate,
        confidence=0.9,
        subject_name=subj_name,
        subject_kind="character",
        object_name=obj_name,
        object_kind="character",
    )


def _fact(content: str) -> Fact:
    return Fact(
        id=f"fact-{abs(hash(content))}",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        type="negation",
        content=content,
        canonical_content=content.lower(),
        confidence=0.9,
    )


def test_format_relation_standard():
    r = _relation("r1", "Arthur", "e1", "trusts", "Lancelot", "e2")
    assert format_relation(r) == "Arthur — trusts — Lancelot"


def test_format_relation_handles_missing_endpoint_names():
    r = Relation(
        id="r1", user_id=USER_ID,
        subject_id="e1", object_id="e2",
        predicate="trusts", confidence=0.9,
        # endpoint names None — archived peer, etc.
    )
    text = format_relation(r)
    assert "<unknown>" in text
    assert "trusts" in text


def test_format_relation_hop():
    r1 = _relation("r1", "Arthur", "e1", "trusts", "Lancelot", "e2")
    r2 = _relation("r2", "Lancelot", "e2", "loves", "Guinevere", "e3")
    hop = RelationHop(hop1=r1, hop2=r2, via_id="e2", via_name="Lancelot", via_kind="character")
    assert format_relation_hop(hop) == (
        "Arthur — trusts — Lancelot — loves — Guinevere"
    )


@pytest.mark.asyncio
async def test_select_returns_empty_when_no_entities(monkeypatch):
    """Classifier extracted no entities → nothing to anchor queries."""
    intent = _intent(entities=())
    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=intent,
    )
    assert result == L2FactResult()
    assert result.total() == 0


@pytest.mark.asyncio
async def test_select_1hop_for_specific_entity(monkeypatch):
    """Specific-entity intent runs 1-hop only (no 2-hop Cypher)."""
    arthur = _entity("Arthur", "e-arthur")
    r1 = _relation("r1", "Arthur", "e-arthur", "trusts", "Lancelot", "e-lan")

    find_by_name = AsyncMock(return_value=[arthur])
    find_1hop = AsyncMock(return_value=[r1])
    find_2hop = AsyncMock(return_value=[])
    list_facts = AsyncMock(return_value=[])

    monkeypatch.setattr("app.context.selectors.facts.find_entities_by_name", find_by_name)
    monkeypatch.setattr("app.context.selectors.facts.find_relations_for_entity", find_1hop)
    monkeypatch.setattr("app.context.selectors.facts.find_relations_2hop", find_2hop)
    monkeypatch.setattr("app.context.selectors.facts.list_facts_by_type", list_facts)

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(hop_count=1),
    )
    assert result.background == ["Arthur — trusts — Lancelot"]
    assert result.negative == []
    find_1hop.assert_awaited_once()
    find_2hop.assert_not_called()


@pytest.mark.asyncio
async def test_select_2hop_for_relational_intent(monkeypatch):
    """Relational intent (hop_count=2) fires both 1-hop AND 2-hop queries."""
    arthur = _entity("Arthur", "e-arthur")
    r1 = _relation("r1", "Arthur", "e-arthur", "trusts", "Lancelot", "e-lan")
    r2 = _relation("r2", "Lancelot", "e-lan", "loves", "Guinevere", "e-gue")
    hop = RelationHop(
        hop1=r1, hop2=r2,
        via_id="e-lan", via_name="Lancelot", via_kind="character",
    )

    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[arthur]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[r1]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_2hop",
        AsyncMock(return_value=[hop]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type",
        AsyncMock(return_value=[]),
    )

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(intent=Intent.RELATIONAL, hop_count=2),
    )
    assert "Arthur — trusts — Lancelot" in result.background
    assert "Arthur — trusts — Lancelot — loves — Guinevere" in result.background


@pytest.mark.asyncio
async def test_select_2hop_passes_required_hop1_types(monkeypatch):
    """Regression (audit HIGH — facts.py:183): the 2-hop call MUST pass a
    non-empty ``hop1_types``. The repo declares it a required kw-only arg
    with a non-empty guard; omitting it (the original bug) raised
    ``TypeError`` that the Mode-3 ``_safe_l2_facts`` wrapper swallowed,
    silently zeroing the ENTIRE L2 layer (1-hop + negations) for exactly
    the RELATIONAL queries that most need graph reasoning.

    The happy-path test above uses a bare ``AsyncMock`` which accepts ANY
    kwargs and therefore cannot catch this. This stub instead mirrors the
    REAL repo signature (required ``hop1_types`` + non-empty guard), so a
    future drop of the kwarg surfaces as a missing 2-hop path here.
    """
    arthur = _entity("Arthur", "e-arthur")
    r1 = _relation("r1", "Arthur", "e-arthur", "trusts", "Lancelot", "e-lan")
    r2 = _relation("r2", "Lancelot", "e-lan", "loves", "Guinevere", "e-gue")
    hop = RelationHop(
        hop1=r1, hop2=r2,
        via_id="e-lan", via_name="Lancelot", via_kind="character",
    )

    captured: dict = {}

    async def real_signature_2hop(
        session, *, user_id, entity_id, hop1_types,
        hop2_types=None, project_id=None, min_confidence=0.8, limit=100,
    ):
        # Mirror db/neo4j_repos/relations.py::find_relations_2hop exactly.
        if not hop1_types:
            raise ValueError("hop1_types must be a non-empty list")
        captured["hop1_types"] = hop1_types
        return [hop]

    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[arthur]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[r1]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_2hop",
        real_signature_2hop,
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type",
        AsyncMock(return_value=[]),
    )

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(intent=Intent.RELATIONAL, hop_count=2),
    )
    # Both the 1-hop fact AND the 2-hop path must be present — the 2-hop
    # path proves the call did not raise (i.e. hop1_types was supplied).
    assert "Arthur — trusts — Lancelot" in result.background
    assert "Arthur — trusts — Lancelot — loves — Guinevere" in result.background
    # The gate was passed and is non-empty (absent/empty pre-fix).
    assert captured.get("hop1_types"), "2-hop must receive a non-empty hop1_types"
    assert "disciple_of" in captured["hop1_types"]


@pytest.mark.asyncio
async def test_select_2hop_failure_degrades_to_1hop(monkeypatch):
    """A 2-hop failure must NOT discard the 1-hop facts already gathered.

    Before the fix the missing-kwarg TypeError propagated out of
    ``select_l2_facts`` and ``_safe_l2_facts`` returned empty — losing the
    1-hop facts too. The localized try/except now degrades to 1-hop-only.
    """
    arthur = _entity("Arthur", "e-arthur")
    r1 = _relation("r1", "Arthur", "e-arthur", "trusts", "Lancelot", "e-lan")

    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[arthur]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[r1]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_2hop",
        AsyncMock(side_effect=RuntimeError("neo4j blip")),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type",
        AsyncMock(return_value=[]),
    )

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(intent=Intent.RELATIONAL, hop_count=2),
    )
    # 1-hop survived despite the 2-hop crash.
    assert result.background == ["Arthur — trusts — Lancelot"]


@pytest.mark.asyncio
async def test_select_dedupes_relations_across_entities(monkeypatch):
    """A shared relation (A → B) surfaced via A-query AND B-query
    must appear only once."""
    arthur = _entity("Arthur", "e-arthur")
    lancelot = _entity("Lancelot", "e-lan")
    shared = _relation("r1", "Arthur", "e-arthur", "trusts", "Lancelot", "e-lan")

    find_by_name = AsyncMock(side_effect=[[arthur], [lancelot]])
    monkeypatch.setattr("app.context.selectors.facts.find_entities_by_name", find_by_name)
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[shared]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_2hop",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type",
        AsyncMock(return_value=[]),
    )

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(entities=("Arthur", "Lancelot")),
    )
    assert result.background.count("Arthur — trusts — Lancelot") == 1


@pytest.mark.asyncio
async def test_select_negations_filtered_to_mentioned_entities(monkeypatch):
    """Only negative facts that name at least one resolved entity surface."""
    arthur = _entity("Arthur", "e-arthur")

    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[arthur]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_2hop",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type",
        AsyncMock(return_value=[
            _fact("Arthur does not know Morgan"),      # keep — mentions Arthur
            _fact("Galahad does not trust Lancelot"),  # drop — no resolved entity
        ]),
    )

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(entities=("Arthur",)),
    )
    assert result.negative == ["Arthur does not know Morgan"]


@pytest.mark.asyncio
async def test_select_returns_empty_when_name_unresolved(monkeypatch):
    """Entity name doesn't resolve → skip gracefully (absence handler
    K18.5 will record it)."""
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[]),
    )
    # Other repo fns should never be called.
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(side_effect=AssertionError("should not be called")),
    )

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(entities=("NotInGraph",)),
    )
    assert result.total() == 0
