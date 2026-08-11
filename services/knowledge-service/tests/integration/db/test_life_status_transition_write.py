"""D-T32-ALIVE-NO-FACTS — the write site, against a live graph.

The unit tests around `StatusTransition` pin the MODEL. They passed with the
conversion at the write site deliberately broken, which is NV-1 exactly: a check
that cannot fail is a claim in the costume of evidence. This is the one that reaches
the code that actually does the arithmetic.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import merge_entity, upsert_glossary_anchor
from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE
from app.extraction.pass2_writer import write_pass2_extraction
from loreweave_extraction.canonical import canonicalize_entity_name, entity_canonical_id
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate, StatusEffect


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-t32-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=user_id)


def _entity(name: str, user_id: str, project_id: str) -> LLMEntityCandidate:
    """The status resolver matches against the CHAPTER's extracted entities (and the
    anchor index), not against whatever is already in the graph — so a death is only
    attributable to someone this chapter actually named."""
    return LLMEntityCandidate(
        name=name, kind="character", aliases=[], confidence=0.9,
        canonical_name=canonicalize_entity_name(name),
        canonical_id=entity_canonical_id(
            user_id=user_id, project_id=project_id, name=name, kind="character"),
    )


def _death_event(name: str) -> LLMEventCandidate:
    return LLMEventCandidate(
        name=f"{name} falls", kind="death",
        summary=f"{name} is slain at the bridge.",
        confidence=0.9, participants=[name], participant_ids=[None],
        location=None, time_cue=None, event_id=f"ev-{name.lower()}",
        status_effects=[StatusEffect(entity_ref=name, status="gone")],
    )


@pytest.mark.asyncio
async def test_the_reported_ordinal_is_a_CHAPTER_not_an_event_order(
    neo4j_driver, test_user,
):
    """THE arithmetic. The graph's status axis is `event_order`
    (chapter × STRIDE + idx); `entity_facts.valid_from_ordinal` is a chapter ordinal.
    Both are plain ints, so reporting the wrong one positions the fact ~1M chapters
    into the book and nothing anywhere complains."""
    P, CH = "p-t32", 5
    async with neo4j_driver.session() as session:
        ent = await merge_entity(session, user_id=test_user, project_id=P,
                                 name="Kai", kind="character", source_type="book_content")
        # Anchor it — an unanchored node has no glossary id to address a fact with.
        await upsert_glossary_anchor(
            session, user_id=test_user, project_id=P, glossary_entity_id="g-kai",
            name="Kai", kind="character")

        result = await write_pass2_extraction(
            session, user_id=test_user, project_id=P,
            source_type="chapter", source_id="ch-5", job_id="j-1",
            entities=[_entity("Kai", test_user, P)], relations=[],
            events=[_death_event("Kai")], facts=[],
            extraction_model="test", anchors=[], chapter_index=CH,
        )

    assert result.statuses_merged == 1, "the graph transition must still be written"
    assert len(result.status_transitions) == 1, (
        "an anchored death must be reported for the glossary fact SSOT")
    tr = result.status_transitions[0]
    assert tr.status == "gone"
    assert tr.chapter_ordinal == CH, (
        f"reported {tr.chapter_ordinal}; an event_order would be "
        f"~{CH * EVENT_ORDER_CHAPTER_STRIDE} and would place the fact a million "
        f"chapters into the book")
    assert tr.chapter_ordinal < EVENT_ORDER_CHAPTER_STRIDE, "sanity: not on the event axis"
    assert ent.id  # the graph node still exists under its own id


@pytest.mark.asyncio
async def test_an_UNANCHORED_death_is_written_to_the_graph_but_not_reported(
    neo4j_driver, test_user,
):
    """`entity_facts.entity_id` is an FK to `glossary_entities`, so a
    discovered-but-unanchored node has nothing to hang a fact on. It must still get
    its `:EntityStatus` — the graph is not gated on the author having curated it.

    Measured 2026-08-11: 0 of the dev graph's 21 status rows were anchored, which is
    why a backfill of the existing ones was impossible and this producer had to run
    at the write moment instead."""
    P, CH = "p-t32", 3
    async with neo4j_driver.session() as session:
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Bob", kind="character", source_type="book_content")
        result = await write_pass2_extraction(
            session, user_id=test_user, project_id=P,
            source_type="chapter", source_id="ch-3", job_id="j-2",
            entities=[_entity("Bob", test_user, P)], relations=[],
            events=[_death_event("Bob")], facts=[],
            extraction_model="test", anchors=[], chapter_index=CH,
        )

    assert result.statuses_merged == 1, "the graph transition is NOT gated on an anchor"
    assert result.status_transitions == [], (
        "an unanchored entity has no glossary id — reporting one would send a fact "
        "to an FK that does not resolve")
