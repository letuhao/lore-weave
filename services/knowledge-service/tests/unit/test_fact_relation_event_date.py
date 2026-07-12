"""dec-3 (D-KG-INSTORY-EVENTDATE) — in-story-date valid-time on facts + relations.

The KG already carries a chapter-ORDINAL story valid-time axis (F3:
``valid_from_ordinal`` / ``valid_to_ordinal``). This adds the OPTIONAL detected
in-story (narrative) date ``event_date_iso`` as an ADDITIONAL, descriptive
valid-time refinement ALONGSIDE the ordinal axis on ``:Fact`` and
``:RELATES_TO`` — mirroring the existing ``:Event`` C18 field.

These unit tests assert (at the ``run_write`` / Cypher-source seam; the live
Neo4j proof is the integration suite):
  - the field lands on the ``Fact`` / ``Relation`` Pydantic projections,
  - the ON CREATE Cypher persists it + the ON MATCH branch is precision-
    preserving (the longer truncated-ISO wins, mirroring :Event HIGH-1),
  - ``merge_fact`` / ``create_relation`` thread the value (empty → None),
  - it is NULL-safe: an absent date never perturbs the ordinal axis / chain,
  - the read path reads it back and can order facts by it as a SECONDARY key
    (chapter-ordinal stays the PRIMARY, spoiler-safe axis).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.neo4j_repos import facts as fm
from app.db.neo4j_repos import relations as rm
from app.db.neo4j_repos.facts import Fact, merge_fact
from app.db.neo4j_repos.relations import (
    _edge_props_to_relation,
    create_relation,
)

_USER = uuid4()
_SUBJ = "ent-subj-1"
_OBJ = "ent-obj-1"


def _result(record):
    r = MagicMock()
    r.single = AsyncMock(return_value=record)
    return r


# ── Pydantic projection carries the field ───────────────────────────────


def test_fact_model_defaults_event_date_iso_none():
    f = Fact(
        id="f1", user_id=str(_USER), type="milestone",
        content="c", canonical_content="c",
    )
    assert f.event_date_iso is None


def test_fact_model_accepts_event_date_iso():
    f = Fact(
        id="f1", user_id=str(_USER), type="milestone",
        content="c", canonical_content="c", event_date_iso="1880-06",
    )
    assert f.event_date_iso == "1880-06"


def test_relation_model_defaults_event_date_iso_none():
    r = _edge_props_to_relation(
        rel_props={
            "id": "r1", "user_id": str(_USER), "subject_id": _SUBJ,
            "object_id": _OBJ, "predicate": "pursues",
        },
        subject={"name": "A", "kind": "character"},
        object_={"name": "B", "kind": "character"},
    )
    assert r.event_date_iso is None


def test_relation_readback_carries_event_date_iso():
    """A :RELATES_TO node whose properties include event_date_iso round-trips
    it through the edge→Relation projection (read path returns it)."""
    r = _edge_props_to_relation(
        rel_props={
            "id": "r1", "user_id": str(_USER), "subject_id": _SUBJ,
            "object_id": _OBJ, "predicate": "pursues",
            "event_date_iso": "1882-03-15",
        },
        subject={"name": "A", "kind": "character"},
        object_={"name": "B", "kind": "character"},
    )
    assert r.event_date_iso == "1882-03-15"


def test_fact_readback_carries_event_date_iso():
    f = fm._node_to_fact({
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
        "event_date_iso": "1880",
    })
    assert f.event_date_iso == "1880"


# ── Cypher source-scan locks: ON CREATE + precision-preserving ON MATCH ──


def test_merge_fact_cypher_sets_event_date_iso_on_create():
    assert "f.event_date_iso = $event_date_iso" in fm._MERGE_FACT_CYPHER


def test_create_relation_cypher_sets_event_date_iso_on_create():
    assert "r.event_date_iso = $event_date_iso" in rm._CREATE_RELATION_CYPHER


def test_merge_fact_cypher_on_match_is_precision_preserving():
    """ON MATCH must prefer the longer (more precise) ISO when both non-null —
    a less-precise re-mention must not downgrade a stored full date (mirrors
    :Event C18 HIGH-1). A plain coalesce would be the bug."""
    flat = re.sub(r"\s+", " ", fm._MERGE_FACT_CYPHER)
    assert "WHEN $event_date_iso IS NULL THEN f.event_date_iso" in flat
    assert "WHEN f.event_date_iso IS NULL THEN $event_date_iso" in flat
    assert (
        "WHEN size($event_date_iso) > size(f.event_date_iso) "
        "THEN $event_date_iso"
    ) in flat
    assert "coalesce($event_date_iso, f.event_date_iso)" not in flat


def test_create_relation_cypher_on_match_is_precision_preserving():
    flat = re.sub(r"\s+", " ", rm._CREATE_RELATION_CYPHER)
    assert "WHEN $event_date_iso IS NULL THEN r.event_date_iso" in flat
    assert "WHEN r.event_date_iso IS NULL THEN $event_date_iso" in flat
    assert (
        "WHEN size($event_date_iso) > size(r.event_date_iso) "
        "THEN $event_date_iso"
    ) in flat
    assert "coalesce($event_date_iso, r.event_date_iso)" not in flat


def test_event_date_is_additive_not_the_ordinal_axis():
    """The in-story date must NOT be wired into the ordinal-chain primitive — it
    is a refinement, not a replacement. maintain_chain re-derives valid_to from
    the ORDINAL axis only; event_date_iso never appears there."""
    for cy in (fm.MAINTAIN_FACT_CHAIN_CYPHER, rm.MAINTAIN_RELATION_CHAIN_CYPHER):
        assert "event_date_iso" not in cy
        assert "valid_from_ordinal" in cy  # the ordinal axis IS the chain key


# ── merge_fact threads the value (run_write seam) ───────────────────────


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_passes_event_date_iso(mock_run):
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="reaches 黄极境", from_order=500,
        event_date_iso="1880-06-15",
    )
    assert mock_run.await_args_list[0].kwargs["event_date_iso"] == "1880-06-15"


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_empty_event_date_normalizes_to_none(mock_run):
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="x", from_order=1, event_date_iso="",
    )
    assert mock_run.await_args_list[0].kwargs["event_date_iso"] is None


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_absent_date_is_null_safe_with_ordinal_chain(mock_run):
    """No event_date (the dominant case) must NOT disturb the ordinal axis: the
    valid_from_ordinal still flows and maintain_chain still fires."""
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="x", from_order=500,
        subject_id=_SUBJ, maintain_chain=True,
    )
    first = mock_run.await_args_list[0].kwargs
    assert first["event_date_iso"] is None        # absent date
    assert first["valid_from_ordinal"] == 500     # ordinal axis intact
    cyphers = [c.args[1] for c in mock_run.await_args_list]
    assert fm.MAINTAIN_FACT_CHAIN_CYPHER in cyphers  # chain still maintained


# ── create_relation threads the value ───────────────────────────────────


def _rel_record():
    return {
        "rel": {
            "id": "rel-1", "user_id": str(_USER), "subject_id": _SUBJ,
            "object_id": _OBJ, "predicate": "pursues", "confidence": 1.0,
            "valid_from": datetime.now(timezone.utc), "valid_until": None,
            "pending_validation": False,
        },
        "subj": {"name": "A", "kind": "character"},
        "obj": {"name": "B", "kind": "character"},
    }


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_create_relation_passes_event_date_iso(mock_run):
    mock_run.return_value = _result(_rel_record())
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="pursues", object_id=_OBJ, event_date_iso="1882",
    )
    assert mock_run.await_args_list[0].kwargs["event_date_iso"] == "1882"


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_create_relation_empty_event_date_normalizes_to_none(mock_run):
    mock_run.return_value = _result(_rel_record())
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="pursues", object_id=_OBJ, event_date_iso="",
    )
    assert mock_run.await_args_list[0].kwargs["event_date_iso"] is None


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_create_relation_legacy_path_unaffected_by_date(mock_run):
    """No date + no ordinal + no maintain_chain ⇒ still exactly one write; the
    new param defaults to None and never adds a query."""
    mock_run.return_value = _result(_rel_record())
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="ally_of", object_id=_OBJ,
    )
    assert mock_run.await_count == 1
    assert mock_run.await_args_list[0].kwargs["event_date_iso"] is None


# ── read path: optional in-story-date secondary order on facts ──────────


def test_list_facts_order_default_is_ordinal_primary():
    """Default (order_by_event_date=False) keeps the legacy ordering exactly —
    chapter-ordinal `from_order` primary, no event_date key."""
    frag = fm._LIST_FACTS_FOR_ENTITY_ORDER_ORDINAL
    assert frag.startswith("f.from_order ASC")
    assert "event_date_iso" not in frag


def test_list_facts_order_event_date_is_secondary_not_primary():
    """The in-story-date variant keeps `from_order` (chapter ordinal) as the
    PRIMARY key — spoiler-safety is preserved — with event_date_iso a SECONDARY
    tiebreak. Undated facts null-sink via coalesce(..., '')."""
    frag = fm._LIST_FACTS_FOR_ENTITY_ORDER_EVENT_DATE
    assert frag.startswith("f.from_order ASC")  # ordinal still PRIMARY
    assert "coalesce(f.event_date_iso, '') ASC" in frag
    # the date key comes AFTER the ordinal key in the ORDER BY
    assert frag.index("from_order") < frag.index("event_date_iso")


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_read", new_callable=AsyncMock)
async def test_list_facts_for_entity_selects_order_fragment(mock_read):
    """order_by_event_date=True interpolates the event-date ORDER BY; the default
    interpolates the ordinal one. The fragment is from a CLOSED pair (never user
    text)."""
    async def _empty():
        return
        yield  # pragma: no cover

    mock_read.return_value = _empty()
    await fm.list_facts_for_entity(
        MagicMock(), user_id=str(_USER), entity_id=_SUBJ,
        order_by_event_date=True,
    )
    cypher_sent = mock_read.await_args_list[0].args[1]
    assert "coalesce(f.event_date_iso, '') ASC" in cypher_sent

    mock_read.reset_mock()
    mock_read.return_value = _empty()
    await fm.list_facts_for_entity(
        MagicMock(), user_id=str(_USER), entity_id=_SUBJ,
    )
    cypher_default = mock_read.await_args_list[0].args[1]
    assert "event_date_iso" not in cypher_default


# ── WS-2.4 (spec 07 §Q2) — diary recall: days_since_epoch + the date-filtered read ─────────────────

from datetime import date as _date  # noqa: E402


def test_days_since_epoch_is_strictly_increasing_per_day():
    assert fm.days_since_epoch(_date(1970, 1, 1)) == 0
    assert fm.days_since_epoch(_date(1970, 1, 2)) == 1
    d1 = fm.days_since_epoch(_date(2026, 7, 12))
    d2 = fm.days_since_epoch(_date(2026, 7, 13))
    assert d2 == d1 + 1  # one calendar day → +1 ordinal (diary is perfectly ordinal)
    assert d1 > 20000    # sanity: ~56 years of days


@pytest.mark.asyncio
async def test_recall_facts_requires_explicit_project_scope():
    # D16 — recall must never span all of a user's projects (a novel-writing session must not pull work
    # facts). An empty project_id is a hard error, not an all-projects fallback.
    with pytest.raises(ValueError, match="project_id"):
        await fm.recall_facts(MagicMock(), user_id="u1", project_id="")


def test_recall_cypher_filters_by_date_range_and_project_and_about_subject():
    # The read is the net-new capability: a date range on event_date_iso (mirroring :Event), a REQUIRED
    # project filter, and an optional :ABOUT-subject narrow. Assert the query encodes all three.
    q = fm._RECALL_FACTS_CYPHER
    assert "f.project_id = $project_id" in q                       # project-scoped (D16)
    assert "f.event_date_iso >= $event_date_from" in q            # lower bound
    assert "f.event_date_iso <= $event_date_to" in q              # upper bound
    assert "[:ABOUT]->(e:Entity)" in q                            # subject narrow via the ABOUT edge
    assert "coalesce(f.pending_validation, false) = false" in q   # confirmed only (not inbox)


def test_fact_types_tuple_stays_in_lockstep_with_the_literal():
    # WS-2.1/2.4 regression: FACT_TYPES (merge_fact's runtime guard) MUST equal the FactType Literal, or
    # a type valid at queue time (e.g. 'statement') 500s at promote time. Derive, never hand-maintain.
    from typing import get_args
    assert set(fm.FACT_TYPES) == set(get_args(fm.FactType))
    assert "statement" in fm.FACT_TYPES


def test_recall_cypher_matches_subject_by_canonical_name_not_raw_lower():
    # audit MED: the :ABOUT subject is matched by CANONICAL name (honorific/punctuation/CJK folded), not a
    # raw toLower — else "Dr. Smith" (stored canonical "smith") is unrecallable. The Cypher must compare
    # e.canonical_name = $subject_canonical, and recall_facts must canonicalize the input.
    q = fm._RECALL_FACTS_CYPHER
    assert "e.canonical_name = $subject_canonical" in q
    assert "toLower(e.canonical_name)" not in q  # the buggy raw-lower compare is gone


@pytest.mark.asyncio
async def test_recall_facts_canonicalizes_the_subject_name_before_matching(monkeypatch):
    # Prove recall_facts runs the subject through canonicalize_entity_name (so "Dr. Smith" → "smith")
    # and binds it as $subject_canonical — the same transform that stored e.canonical_name at promote.
    captured = {}

    class _Res:
        def __aiter__(self):
            async def _gen():
                if False:
                    yield None
            return _gen()

    async def _fake_run_read(session, cypher, **params):
        captured.update(params)
        return _Res()

    monkeypatch.setattr(fm, "run_read", _fake_run_read)
    await fm.recall_facts(MagicMock(), user_id="u1", project_id="p1", subject_name="Dr. Smith")
    assert captured["subject_canonical"] == "smith", captured.get("subject_canonical")
