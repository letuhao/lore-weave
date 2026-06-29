"""F3 slice 3 — extraction drives the story-time close + retract re-stitch.

Asserts that ``write_pass2_extraction`` opts into the ordinal-aware interval
close (Path A close-prior) by passing ``maintain_chain=True`` +
``valid_from_ordinal=chapter_base`` to both ``create_relation`` and
``merge_fact``, and that the retract re-stitch routine has the right shape.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.db.neo4j_repos import temporal as tm
from app.extraction.pass2_writer import write_pass2_extraction
from loreweave_extraction.extractors.fact import LLMFactCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate

_USER = str(uuid4())


def _entity_cand(name, kind="character"):
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


@pytest.mark.asyncio
async def test_writer_drives_maintain_chain_on_relations_and_facts():
    """The extraction writeback opts into the ordinal-aware close: create_relation
    + merge_fact both get maintain_chain=True and valid_from_ordinal=chapter_base
    (= chapter_index × stride)."""
    from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE

    rel_calls: list[dict] = []
    fact_calls: list[dict] = []

    async def _fake_create_relation(session, **kwargs):
        rel_calls.append(kwargs)
        from app.db.neo4j_repos.relations import Relation
        return Relation(
            id="r1", user_id=_USER, subject_id=kwargs["subject_id"],
            object_id=kwargs["object_id"], predicate=kwargs["predicate"],
        )

    async def _fake_merge_fact(session, **kwargs):
        fact_calls.append(kwargs)
        from app.db.neo4j_repos.facts import Fact
        return Fact(
            id="f1", user_id=_USER, type=kwargs["type"],
            content=kwargs["content"], canonical_content=kwargs["content"],
        )

    # Resolve both endpoints + the fact subject to the same merged entity so the
    # relation/fact actually get written (not cascade-skipped).
    async def _fake_resolve(session, anchor_index, **kwargs):
        from app.db.neo4j_repos.entities import Entity
        # deterministic id per name so subject/object differ
        eid = "ent-" + kwargs["name"].lower()
        return Entity(
            id=eid, user_id=_USER, name=kwargs["name"],
            canonical_name=kwargs["name"].lower(), kind=kwargs["kind"],
        )

    async def _fake_add_evidence(session, **kwargs):
        return None

    async def _fake_source(session, **kwargs):
        from app.db.neo4j_repos.provenance import ExtractionSource
        return ExtractionSource(
            id="src1", user_id=_USER, source_type="chapter", source_id="ch1",
        )

    with patch("app.extraction.pass2_writer.create_relation", _fake_create_relation), \
         patch("app.extraction.pass2_writer.merge_fact", _fake_merge_fact), \
         patch("app.extraction.pass2_writer.resolve_or_merge_entity", _fake_resolve), \
         patch("app.extraction.pass2_writer.add_evidence", _fake_add_evidence), \
         patch("app.extraction.pass2_writer.upsert_extraction_source", _fake_source):
        await write_pass2_extraction(
            AsyncMock(),
            user_id=_USER, project_id="p1",
            source_type="chapter", source_id="ch1", job_id="job1",
            entities=[_entity_cand("Kai"), _entity_cand("Zhao")],
            relations=[LLMRelationCandidate(
                subject="Kai", predicate="member_of", object="Zhao",
                subject_id="ent-kai", object_id="ent-zhao", confidence=0.9,
                polarity="affirm", modality="asserted", relation_id="rel-x",
            )],
            facts=[LLMFactCandidate(
                type="milestone", content="Kai reaches a milestone",
                subject="Kai", subject_id="ent-kai", confidence=0.9,
                polarity="affirm", modality="asserted", fact_id="fid-x",
            )],
            chapter_index=42,  # → chapter_base = 42 × stride
        )

    expected_base = 42 * EVENT_ORDER_CHAPTER_STRIDE
    assert len(rel_calls) == 1
    assert rel_calls[0]["maintain_chain"] is True
    assert rel_calls[0]["valid_from_ordinal"] == expected_base
    assert len(fact_calls) == 1
    assert fact_calls[0]["maintain_chain"] is True
    # merge_fact unifies valid_from_ordinal with from_order; the writer passes
    # from_order=chapter_base, so the fact's story bound is the same ordinal.
    assert fact_calls[0]["from_order"] == expected_base


def test_restitch_cypher_rederives_from_survivors_ordinal_order():
    """The retract re-stitch re-derives valid_to over survivors by
    valid_from_ordinal — the A3 chain-restitch, using the same single
    maintenance algorithm (next survivor's valid_from), never a wall-clock."""
    for cy in (
        tm._RESTITCH_ALL_FACT_CHAINS_CYPHER,
        tm._RESTITCH_ALL_RELATION_CHAINS_CYPHER,
    ):
        assert "valid_until IS NULL" in cy            # survivors only
        assert "valid_from_ordinal IS NOT NULL" in cy  # positionless excluded
        assert "valid_from_ordinal ASC" in cy
        assert "nxt.valid_from_ordinal" in cy          # close = next survivor
        assert "$open_ceiling" in cy
        assert "$user_id" in cy                         # tenant-scoped
    # fact chain groups by (entity, type); relation chain by (subject, predicate)
    assert "f.type AS attr" in tm._RESTITCH_ALL_FACT_CHAINS_CYPHER
    assert "r.predicate AS predicate" in tm._RESTITCH_ALL_RELATION_CHAINS_CYPHER


@pytest.mark.asyncio
async def test_restitch_returns_total_facts_plus_relations():
    sess = AsyncMock()
    fact_res = AsyncMock()
    fact_res.single = AsyncMock(return_value={"restitched": 3})
    rel_res = AsyncMock()
    rel_res.single = AsyncMock(return_value={"restitched": 2})
    with patch("app.db.neo4j_repos.temporal.run_write",
               new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [fact_res, rel_res]
        total = await tm.restitch_chains_after_retract(
            sess, user_id=_USER, project_id="p1",
        )
    assert total == 5
