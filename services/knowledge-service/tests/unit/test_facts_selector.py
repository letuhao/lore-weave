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
    """Classifier extracted no entities → nothing to anchor queries.
    (tool_facts=False isolates the entity-anchored path; the WS-4C tool-fact
    branch is covered separately below.)"""
    intent = _intent(entities=())
    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=intent,
        tool_facts=False,
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
        tool_facts=False,
    )
    assert result.total() == 0


def _tool_fact(content: str, fact_type: str = "decision") -> Fact:
    """A memory_remember / llm_tool_call fact (WS-4C): source-tagged, 0.7."""
    return Fact(
        id=f"tool-{abs(hash(content))}",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        type=fact_type,
        content=content,
        canonical_content=content.lower(),
        confidence=0.7,
        source_types=["llm_tool_call"],
    )


@pytest.mark.asyncio
async def test_tool_facts_admitted_to_current_without_entities(monkeypatch):
    """WS-4C — project-level memory_remember facts are recalled even when the
    message names NO entity, and land in `current`."""
    list_facts = AsyncMock(return_value=[
        _tool_fact("we decided the villain dies in chapter 10"),
        _tool_fact("the user does NOT want a romance subplot", "negation"),
    ])
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type", list_facts,
    )
    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(entities=()),  # no entity anchor
        tool_facts=True,
    )
    # both go to current (each sentence carries its own polarity); negative
    # stays purely entity-anchored so the widened-retry miss-detection is intact.
    assert result.current == [
        "we decided the villain dies in chapter 10",
        "the user does NOT want a romance subplot",
    ]
    assert result.negative == []
    # called with the lower tool floor + the source filter.
    kwargs = list_facts.await_args.kwargs
    assert kwargs["source_type"] == "llm_tool_call"
    assert kwargs["min_confidence"] == 0.7


@pytest.mark.asyncio
async def test_tool_fact_failure_does_not_nuke_entity_anchored_l2(monkeypatch):
    """REGRESSION (/review-impl) — the tool-fact branch is STRICTLY ADDITIVE and runs
    FIRST. An unguarded failure there would propagate out of select_l2_facts, be
    swallowed by Mode 3's _safe_l2_facts, and silently zero the ENTIRE L2 layer.
    A tool-fact failure must degrade to entity-anchored-only."""
    arthur = _entity("Arthur", "e-arthur")
    r1 = _relation("r1", "Arthur", "e-arthur", "trusts", "Lancelot", "e-lan")

    async def boom(*a, **kw):
        # the negation call (type="negation") must still work; only the tool-fact
        # call (source_type set) explodes.
        if kw.get("source_type"):
            raise RuntimeError("neo4j hiccup on the tool-fact query")
        return []

    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[arthur]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[r1]),
    )
    monkeypatch.setattr("app.context.selectors.facts.list_facts_by_type", boom)

    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(hop_count=1),
        tool_facts=True,
    )
    # the relation survived; only the tool facts were lost
    assert result.background == ["Arthur — trusts — Lancelot"]
    assert result.current == []


@pytest.mark.asyncio
async def test_tool_facts_zero_limit_is_skipped_not_fatal(monkeypatch):
    """REGRESSION — an operator setting CONTEXT_L2_TOOL_FACTS_LIMIT=0 to 'disable'
    the feature must not kill L2: list_facts_by_type raises on limit<=0."""
    list_facts = AsyncMock(side_effect=AssertionError("must not query with limit<=0"))
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type", list_facts,
    )
    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(entities=()),
        tool_facts=True,
        tool_facts_limit=0,
    )
    assert result.total() == 0


@pytest.mark.asyncio
async def test_tool_facts_disabled_by_flag(monkeypatch):
    """tool_facts=False skips the branch entirely (kill-switch)."""
    list_facts = AsyncMock(side_effect=AssertionError("must not query tool facts"))
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.list_facts_by_type", list_facts,
    )
    result = await select_l2_facts(
        MagicMock(),
        user_id=USER_ID,
        project_id=PROJECT_ID,
        intent=_intent(entities=()),
        tool_facts=False,
    )
    assert result.total() == 0


# ── M1a: passage→graph anchor bridge ─────────────────────────────────

from app.context.selectors.facts import (  # noqa: E402
    expand_facts_from_passages,
    select_bridge_anchor_names,
)


def test_bridge_anchor_names_skips_anchored_dedups_and_caps(monkeypatch):
    """Rank-order, first-seen wins, skip already-anchored, cap — deterministic."""
    # Controlled candidate stream so the test isn't coupled to extract_candidates'
    # proper-noun heuristic — we're testing the dedup/skip/cap logic here.
    per_passage = {
        "p1": ["Dracula", "Harker"],
        "p2": ["Harker", "Mina", "Bistritz"],
    }
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: per_passage[text],
    )
    out = select_bridge_anchor_names(
        ["p1", "p2"],
        already_anchored_names={"dracula"},  # message already anchored Dracula
        max_anchors=2,
    )
    # Dracula skipped (already anchored); Harker first-seen then Mina; cap at 2
    # so Bistritz never makes it. Order preserved = passage rank order.
    assert out == ["Harker", "Mina"]


def test_bridge_anchor_names_empty_passages():
    assert select_bridge_anchor_names([], set()) == []


@pytest.mark.asyncio
async def test_expand_from_passages_happy_path(monkeypatch):
    """Resolve passage anchors → 1-hop expand → new fact strings."""
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: ["Harker"],
    )
    harker = _entity("Harker", "e-harker")
    r1 = _relation("r1", "Harker", "e-harker", "works_for", "Hawkins", "e-hawk")
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[harker]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[r1]),
    )
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["a passage mentioning Harker"],
        already_anchored_names=set(),
        existing_facts=set(),
    )
    assert out == ["Harker — works_for — Hawkins"]


@pytest.mark.asyncio
async def test_expand_dedups_against_existing_facts(monkeypatch):
    """A relation already in the message-anchored facts is NOT re-added."""
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: ["Harker"],
    )
    harker = _entity("Harker", "e-harker")
    r1 = _relation("r1", "Harker", "e-harker", "works_for", "Hawkins", "e-hawk")
    r2 = _relation("r2", "Harker", "e-harker", "knows", "Mina", "e-mina")
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[harker]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=[r1, r2]),
    )
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["Harker"],
        already_anchored_names=set(),
        existing_facts={"Harker — works_for — Hawkins"},  # already present
    )
    assert out == ["Harker — knows — Mina"]  # r1 deduped out


@pytest.mark.asyncio
async def test_expand_dedups_by_entity_id(monkeypatch):
    """Two surface names resolving to the same entity expand it only once."""
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: ["Harker", "Jonathan"],
    )
    harker = _entity("Harker", "e-harker")
    r1 = _relation("r1", "Harker", "e-harker", "works_for", "Hawkins", "e-hawk")
    find_by_name = AsyncMock(return_value=[harker])  # both names → same entity
    find_1hop = AsyncMock(return_value=[r1])
    monkeypatch.setattr("app.context.selectors.facts.find_entities_by_name", find_by_name)
    monkeypatch.setattr("app.context.selectors.facts.find_relations_for_entity", find_1hop)
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["Harker Jonathan"],
        already_anchored_names=set(), existing_facts=set(),
    )
    assert out == ["Harker — works_for — Hawkins"]
    # both names resolved, but the 1-hop expansion ran only ONCE (dedup by id)
    assert find_1hop.await_count == 1


@pytest.mark.asyncio
async def test_expand_skips_unresolved_names(monkeypatch):
    """A candidate that resolves to no entity is skipped, not raised."""
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: ["Ghost"],
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[]),  # no match
    )
    find_1hop = AsyncMock(return_value=[])
    monkeypatch.setattr("app.context.selectors.facts.find_relations_for_entity", find_1hop)
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["Ghost"], already_anchored_names=set(), existing_facts=set(),
    )
    assert out == []
    find_1hop.assert_not_called()


@pytest.mark.asyncio
async def test_expand_caps_total_new_facts(monkeypatch):
    """max_new_facts bounds the output even with many relations."""
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: ["Harker"],
    )
    harker = _entity("Harker", "e-harker")
    many = [
        _relation(f"r{i}", "Harker", "e-harker", f"pred{i}", f"Obj{i}", f"e{i}")
        for i in range(10)
    ]
    monkeypatch.setattr(
        "app.context.selectors.facts.find_entities_by_name",
        AsyncMock(return_value=[harker]),
    )
    monkeypatch.setattr(
        "app.context.selectors.facts.find_relations_for_entity",
        AsyncMock(return_value=many),
    )
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["Harker"], already_anchored_names=set(), existing_facts=set(),
        max_new_facts=3,
    )
    assert len(out) == 3


# ── multilingual M4 fix: sentence-junk filter + resolve-then-cap ──────────────
# The passage→graph bridge reuses `extract_candidates` (a user-MESSAGE proper-noun
# extractor) over passage PROSE. On Vietnamese (corpus 019f1783) that stream is
# dominated by quoted dialogue sentences + sentence-initial common words, which a
# plain cap-then-resolve wasted anchor slots on (1/6 resolved). These guard the two
# bridge-local mitigations.


def test_bridge_drops_quoted_sentence_candidates(monkeypatch):
    """A quoted-dialogue-sentence candidate is filtered before it eats a cap slot,
    while real (short, punctuation-free) names survive — incl. multi-token vi names."""
    per_passage = {
        "p1": [
            "Không thể... không thể để nó nuốt chửng mình!",  # quoted sentence → drop
            "Một",                                              # kept (resolves later, harmless)
            "Lâm Chấn Nhạc",                                    # real name → keep
        ],
        "p2": [
            "Cửu U Ma Cơ",     # 4-token name, no interior sentence punct → keep
            "Coutts & Co.",    # trailing abbrev dot (no following space) → keep
        ],
    }
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: per_passage[text],
    )
    out = select_bridge_anchor_names(["p1", "p2"], set(), max_anchors=10)
    assert "Không thể... không thể để nó nuốt chửng mình!" not in out
    assert "Lâm Chấn Nhạc" in out
    assert "Cửu U Ma Cơ" in out
    assert "Coutts & Co." in out


@pytest.mark.asyncio
async def test_expand_resolve_then_cap_junk_does_not_starve(monkeypatch):
    """Unresolvable junk ranked ABOVE two real names must not consume the anchor
    budget: with max_anchors=2 both real entities still expand (cap-then-resolve
    would have stopped at the junk and returned nothing)."""
    # 5 junk candidates (unresolvable) then 2 real names, all within one passage.
    cands = ["Một", "Sự", "Không", "Thần", "Giọng", "Lin", "Kai"]
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: cands,
    )
    lin = _entity("Lin", "e-lin")
    kai = _entity("Kai", "e-kai")

    async def _resolve(session, *, user_id, project_id, name):
        return {"Lin": [lin], "Kai": [kai]}.get(name, [])  # only Lin/Kai resolve

    monkeypatch.setattr("app.context.selectors.facts.find_entities_by_name", _resolve)
    r_lin = _relation("r1", "Lin", "e-lin", "mentor_of", "Kai", "e-kai")
    r_kai = _relation("r2", "Kai", "e-kai", "member_of", "Sect", "e-sect")
    rels = {"e-lin": [r_lin], "e-kai": [r_kai]}

    async def _one_hop(session, *, user_id, project_id, entity_id, min_confidence, limit):
        return rels.get(entity_id, [])

    monkeypatch.setattr("app.context.selectors.facts.find_relations_for_entity", _one_hop)
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["prose"], already_anchored_names=set(), existing_facts=set(),
        max_anchors=2,
    )
    # Both real names resolved & expanded despite 5 junk candidates ranked first.
    assert out == ["Lin — mentor_of — Kai", "Kai — member_of — Sect"]


@pytest.mark.asyncio
async def test_expand_resolved_anchor_cap_bounds_expansion(monkeypatch):
    """max_anchors bounds RESOLVED anchors: with 3 resolvable names but
    max_anchors=1, only the first is expanded."""
    cands = ["Aaa", "Bbb", "Ccc"]
    monkeypatch.setattr(
        "app.context.selectors.facts.extract_candidates",
        lambda text, **kw: cands,
    )
    ents = {n: [_entity(n, f"e-{n}")] for n in cands}

    async def _resolve(session, *, user_id, project_id, name):
        return ents.get(name, [])

    one_hop = AsyncMock(return_value=[_relation("r", "X", "e-x", "knows", "Y", "e-y")])
    monkeypatch.setattr("app.context.selectors.facts.find_entities_by_name", _resolve)
    monkeypatch.setattr("app.context.selectors.facts.find_relations_for_entity", one_hop)
    out = await expand_facts_from_passages(
        MagicMock(),
        user_id=USER_ID, project_id=PROJECT_ID,
        passage_texts=["prose"], already_anchored_names=set(), existing_facts=set(),
        max_anchors=1,
    )
    assert one_hop.await_count == 1  # only ONE anchor expanded
    assert len(out) == 1
