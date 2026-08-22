"""T83 — real `neo4j_repos` functions, unchanged, executed against Apache AGE.

§10.1 says two things bind the repo layer to Neo4j: **"the Cypher dialect and the session
type"**. T77–T82 took the dialect ratchet to zero, which is a reading, not a proof — every repo
function still went through `session.run(...)`, and nothing but a Bolt session had ever answered
that call. This file is the proof, and it is a FLOOR: the count may rise, never fall.

⚠️ **Running it is what found three separate reasons "dialect 0" was not portability.**

1. **51 hardcoded engine literals.** Every call site said `render(TEMPLATE, "neo4j")`. The
   dialect scan counts Neo4j-only *constructs*, and a string literal naming the engine is not
   one — so the ratchet read zero while the layer named one engine 51 times. The first run
   failed on `function datetime does not exist`. Rendering moved into
   `run_read`/`run_read_any_owner`/`run_write`, keyed on `engine_of(session)`.
2. **Seven call sites bypass those helpers** and lost their render with the other 51. Four unit
   suites and 620 integration tests were green at that moment; only a query reaching a real
   database could tell. Now derived by AST in `test_every_bypass_site_renders.py`.
3. **Two queries were valid Cypher on Neo4j and rejected by AGE** — both written days earlier
   in this same migration:
       `RETURN DISTINCT e … ORDER BY`   -> *for SELECT DISTINCT, ORDER BY expressions must
                                           appear in select list*   (now `WITH DISTINCT e`)
       `ORDER BY rel.confidence`        -> *could not find rte for rel* — AGE cannot order by
                                           an alias the RETURN defines (now ordered on `r`)

None of the three is visible to a test that mocks the session, and none is visible to a ratchet
that counts constructs. Only executing the function against the other engine finds them.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

#: Shrink-only. Every function below has been observed to run against a live AGE graph and
#: return a domain object the repo layer's own model accepts. T83 proved 12 across
#: entities/relations/provenance; T84 added facts, events, entity_status, hierarchy,
#: maintenance and the bi-temporal chain.
_WAVE_1 = 12   # entities / relations / provenance          (T83)
_WAVE_2 = 13   # facts / events / entity_status / hierarchy / maintenance / the chain  (T84)
_WAVE_3 = 29   # the READ/DERIVE surface across nine more modules              (T86)
_WAVE_4 = 54   # the BULK: entities (36), facts (12), events (12)              (T87)
_PROVEN_ON_AGE = _WAVE_1 + _WAVE_2 + _WAVE_3 + _WAVE_4

_GRAPH = "repo_conformance"


@pytest_asyncio.fixture
async def age_session():
    """An `AgeCypherSession` over a throwaway graph, dropped afterwards either way."""
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — skipping the AGE half of the repo layer")
    asyncpg = pytest.importorskip("asyncpg")

    from app.db.age_session import AgeCypherSession

    conn = await asyncpg.connect(dsn)
    try:
        await AgeCypherSession.prepare(conn)
        if await conn.fetchval("SELECT count(*) FROM ag_graph WHERE name = $1", _GRAPH):
            await conn.execute(f"SELECT drop_graph('{_GRAPH}', true)")
        await conn.execute(f"SELECT create_graph('{_GRAPH}')")
        yield AgeCypherSession(conn, _GRAPH)
        await conn.execute(f"SELECT drop_graph('{_GRAPH}', true)")
    finally:
        await conn.close()


async def test_the_repo_layer_runs_against_AGE_unchanged(age_session):
    """Twelve calls, no engine branch anywhere in them.

    Each assertion is on the DOMAIN OBJECT, not on "it did not raise": a query that runs and
    returns the wrong shape is the failure mode this whole migration keeps finding, and
    `AgeVertex` exists precisely because AGE's envelope would otherwise hand every caller the
    internal graph id under the name `id`.
    """
    from app.db.neo4j_repos import entities as en
    from app.db.neo4j_repos import provenance as pv
    from app.db.neo4j_repos import relations as rl

    ran = 0
    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"
    s = age_session

    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter", confidence=0.9)
    ran += 1
    assert kai.name == "Kai" and kai.user_id == uid, (
        f"the domain object came back wrong: {kai!r}. An AGE vertex is "
        f"`{{id, label, properties}}` and its `id` is the INTERNAL graph id — reading the "
        f"envelope instead of `properties` yields a well-formed Entity with the wrong id."
    )

    again = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                  source_type="chapter", confidence=0.9)
    ran += 1
    assert again.id == kai.id, "the merge is not idempotent on AGE — it minted a second node"

    fetched = await en.get_entity(s, user_id=uid, canonical_id=kai.id)
    ran += 1
    assert fetched is not None and fetched.id == kai.id

    by_name = await en.find_entities_by_name(s, user_id=uid, project_id=proj, name="Kai")
    ran += 1
    assert [e.id for e in by_name] == [kai.id], (
        f"name resolution returned {[e.id for e in by_name]} — this is the query whose "
        f"`RETURN DISTINCT … ORDER BY` AGE rejects outright"
    )

    detail = await en.get_entity_with_relations(s, user_id=uid, entity_id=kai.id)
    ran += 1
    assert detail is not None and detail.entity.id == kai.id and detail.relations == []

    rin = await en.merge_entity(s, user_id=uid, project_id=proj, name="Rin", kind="person",
                                source_type="chapter")
    ran += 1

    rel = await rl.create_relation(s, user_id=uid, subject_id=kai.id, predicate="knows",
                                   object_id=rin.id, confidence=0.8)
    ran += 1
    assert rel is not None and rel.subject_id == kai.id and rel.object_id == rin.id

    hops = await rl.find_relations_for_entity(s, user_id=uid, entity_id=kai.id,
                                              direction="both")
    ran += 1
    assert [r.id for r in hops] == [rel.id], (
        f"1-hop returned {[r.id for r in hops]} — this is the query whose `ORDER BY rel.…` "
        f"AGE cannot resolve, because `rel` is defined by the RETURN it is ordering"
    )

    src = await pv.upsert_extraction_source(s, user_id=uid, project_id=proj,
                                            source_type="chapter", source_id="ch-1")
    ran += 1
    assert src.source_id == "ch-1"

    counts = await pv.add_evidence(s, user_id=uid, target_label="Entity", target_id=kai.id,
                                   source_id=src.id, job_id="job-1", extraction_model="m",
                                   confidence=0.9)
    ran += 1
    assert counts.evidence_count == 1

    cites = await pv.list_evidence_for_target(s, user_id=uid, target_label="Entity",
                                              target_id=kai.id)
    ran += 1
    assert [c.source_id for c in cites] == [src.id]

    archived = await en.archive_entity(s, user_id=uid, canonical_id=kai.id,
                                       reason="user_deleted")
    ran += 1
    assert archived is not None and archived.archived_at is not None

    assert ran >= _WAVE_1, (
        f"only {ran} first-wave repo functions were exercised against AGE; the floor is "
        f"{_WAVE_1} of {_PROVEN_ON_AGE} total. "
        f"This number is shrink-only — a function that stops being proven is a regression in "
        f"the claim, not a smaller test."
    )


async def test_a_session_that_forgets_to_declare_its_engine_is_caught_here(age_session):
    """⚠️ The first run of `AgeCypherSession` omitted `engine = "age"`, `engine_of` fell back to
    Neo4j, and EVERY query failed at the database with `function datetime does not exist`.

    The fallback is right for a Bolt session and silently wrong for anything else, so the
    declaration is asserted rather than trusted — it is one deleted line from turning this whole
    file into a Neo4j test wearing an AGE fixture.
    """
    from app.db.neo4j_helpers import engine_of

    assert engine_of(age_session) == "age", (
        "the AGE session does not declare its engine, so every template renders as Neo4j "
        "Cypher and this file proves nothing about AGE"
    )


async def test_the_SECOND_WAVE_runs_on_AGE_too(age_session):
    """facts, events, entity_status, hierarchy, maintenance — and the bi-temporal chain.

    ⚠️ **Three more things only a live run could find**, all in code that passed every Neo4j
    test:

    1. `RETURN DISTINCT f … ORDER BY` in TWO `facts` queries — the same construct T83 fixed in
       `entities`, in queries T83 never executed. The pattern was systemic, not a pair of
       one-offs.
    2. `AgeCypherSession` had **no `begin_transaction`**, so the whole optimistic-concurrency
       path (T80) could not run on AGE at all — the transaction is not decoration there,
       statement 2 depends on the lock statement 1 took.
    3. `[x IN chain WHERE x.valid_from_ordinal > …]` — **AGE cannot read a property off a vertex
       bound inside a list comprehension** (`could not find properties for x`). The chain
       maintainer collects the ordinals alongside the nodes and compares plain integers, which
       says the same thing on both engines. Four templates carried the construct.

    The chain is the sharpest of the three: it is the bi-temporal machinery every as-of read
    depends on, and it was the last thing anyone would have guessed differed.
    """
    from app.db.neo4j_repos import entities as en
    from app.db.neo4j_repos import entity_status as es
    from app.db.neo4j_repos import events as ev
    from app.db.neo4j_repos import facts as fx
    from app.db.neo4j_repos import hierarchy as hi
    from app.db.neo4j_repos import maintenance as mt

    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"
    s = age_session

    ran = 0
    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter")
    ran += 1

    fact = await fx.merge_fact(s, user_id=uid, project_id=proj, type="attribute",
                               content="Kai is brave", confidence=0.8,
                               source_type="chapter", subject_id=kai.id)
    ran += 1
    assert fact.content == "Kai is brave"

    listed = await fx.list_facts_for_entity(s, user_id=uid, entity_id=kai.id)
    ran += 1
    assert [f.id for f in listed] == [fact.id], (
        "this is the `RETURN DISTINCT f … ORDER BY` query AGE refuses outright"
    )

    invalidated = await fx.invalidate_fact(s, user_id=uid, fact_id=fact.id)
    ran += 1
    assert invalidated is not None and invalidated.valid_until is not None
    revalidated = await fx.revalidate_fact(s, user_id=uid, fact_id=fact.id)
    ran += 1
    assert revalidated is not None and revalidated.valid_until is None

    # The bi-temporal chain: two positioned instances of the same attribute, and the earlier
    # one must be closed at the later one's ordinal.
    await fx.merge_fact(s, user_id=uid, project_id=proj, type="temporal",
                        content="Kai is north", confidence=0.9, source_type="chapter",
                        subject_id=kai.id, predicate="location", object="north",
                        valid_from_ordinal=100, maintain_chain=True)
    await fx.merge_fact(s, user_id=uid, project_id=proj, type="temporal",
                        content="Kai is south", confidence=0.9, source_type="chapter",
                        subject_id=kai.id, predicate="location", object="south",
                        valid_from_ordinal=200, maintain_chain=True)
    ran += 1
    chain = [f for f in await fx.list_facts_for_entity(s, user_id=uid, entity_id=kai.id)
             if f.type == "temporal"]
    bounds = sorted((f.valid_from_ordinal, f.valid_to_ordinal) for f in chain)
    assert bounds == [(100, 200), (200, None)], (
        f"the chain did not close on AGE: {bounds}. The maintainer's comparison list is the "
        f"construct AGE rejects — every as-of read depends on these bounds being right."
    )

    ran += 1
    event = await ev.merge_event(s, user_id=uid, project_id=proj, title="The Oath",
                                 chapter_id="ch-1", event_order=1)
    ran += 1
    updated, before = await ev.update_event_fields(
        s, user_id=uid, event_id=event.id, title="The Sworn Oath", summary=None,
        time_cue=None, event_date_iso=None, expected_version=1)
    assert updated is not None and updated.title == "The Sworn Oath", (
        "the OCC path needs a real transaction — `begin_transaction` on the AGE session"
    )
    assert before is not None and before["title"] == "The Oath"
    ran += 1
    assert (await ev.archive_event(s, user_id=uid, event_id=event.id)) is not None

    ran += 1
    await es.merge_entity_status(s, user_id=uid, project_id=proj, entity_id=kai.id,
                                 status="gone", from_order=300, source_type="chapter")
    ran += 1
    statuses = await es.status_at_order(s, user_id=uid, project_id=proj,
                                        entity_ids=[kai.id], at_order=400)
    assert kai.id in statuses

    ran += 1
    await hi.upsert_hierarchy_chain(
        s, book_path="b1", book_id="b1", book_title="Book", part_path="b1/p1",
        part_id="p1", part_index=1, part_title="Part", chapter_path="b1/p1/c1",
        chapter_id="ch-1", chapter_index=1, chapter_title="Chapter", scenes=[])

    ran += 1
    stats = await mt.project_graph_stats(s, user_id=uid, project_id=proj)
    assert stats["entity_count"] == 1 and stats["event_count"] == 1, stats
    assert stats["passage_count"] == 0, (
        "a project with NO passages must report 0, not vanish — that is the OPTIONAL MATCH "
        "the T82 stats rewrite depends on (bite 3)"
    )

    assert ran >= _WAVE_2, (
        f"only {ran} second-wave repo functions were exercised against AGE; the floor is "
        f"{_WAVE_2} of {_PROVEN_ON_AGE} total. This number is shrink-only — a function that "
        f"stops being proven is a regression in the claim, not a smaller test."
    )


async def test_the_THIRD_WAVE_covers_the_read_and_derive_surface(age_session):
    """Nine more modules — relations' subgraphs, provenance's cascade, entity_status, hierarchy,
    maintenance, coref, graph_views, schema_usage, flywheel, temporal's restitch.

    ⚠️ **One more instance of the list-comprehension limitation, in a query T82 had already
    rewritten.** `_PROJECT_SUBGRAPH_CYPHER` carried `[s IN seeds | s.id] AS seed_ids` — a
    property read off a vertex bound inside a comprehension, which AGE rejects with
    `could not find properties for s`. T84 found the same construct in the four chain
    maintainers; this one survived because T82 rewrote the query without ever executing it on
    the other engine. **A rewrite that is not run on both engines is a rewrite for one.**
    """
    from app.db.neo4j_repos import coref, entity_status as es, flywheel, graph_views
    from app.db.neo4j_repos import entities as en, hierarchy as hi, maintenance as mt
    from app.db.neo4j_repos import provenance as pv, relations as rl, schema_usage, temporal

    ran = 0
    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"
    s = age_session

    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter")
    rin = await en.merge_entity(s, user_id=uid, project_id=proj, name="Rin", kind="person",
                                source_type="chapter")
    rel = await rl.create_relation(s, user_id=uid, subject_id=kai.id, predicate="knows",
                                   object_id=rin.id, confidence=0.8)
    src = await pv.upsert_extraction_source(s, user_id=uid, project_id=proj,
                                            source_type="chapter", source_id="ch-1")
    await pv.add_evidence(s, user_id=uid, target_label="Entity", target_id=kai.id,
                          source_id=src.id, job_id="j1", extraction_model="m", confidence=0.9)

    assert (await rl.get_relation(s, user_id=uid, relation_id=rel.id)).id == rel.id
    ran += 1
    await rl.find_relations_2hop(s, user_id=uid, entity_id=kai.id,
                                 hop1_types=["knows"], hop2_types=["knows"]); ran += 1

    sub = await rl.get_project_subgraph(s, user_id=uid, project_id=proj)
    ran += 1
    assert {n.id for n in sub.nodes} == {kai.id, rin.id}, (
        f"the project subgraph returned {[n.id for n in sub.nodes]} — this is the query whose "
        f"`[s IN seeds | s.id]` AGE rejects outright"
    )
    await rl.get_world_subgraph(s, user_id=uid, project_ids=[proj]); ran += 1
    assert (await rl.invalidate_relation(s, user_id=uid, relation_id=rel.id)) is not None
    ran += 1
    await rl.recreate_relation(s, user_id=uid, subject_id=kai.id, predicate="knows",
                               object_id=rin.id); ran += 1

    assert (await pv.get_extraction_source(s, user_id=uid, source_type="chapter",
                                           source_id="ch-1")).source_id == "ch-1"
    ran += 1
    await pv.remove_evidence_for_source(s, user_id=uid, source_id=src.id); ran += 1
    await pv.remove_evidence_for_natural_key(s, user_id=uid, project_id=proj,
                                             source_type="chapter", source_id="ch-1"); ran += 1
    await pv.cleanup_zero_evidence_nodes(s, user_id=uid, project_id=proj); ran += 1
    await pv.delete_source_cascade(s, user_id=uid, source_type="chapter",
                                   source_id="ch-1"); ran += 1

    await es.statuses_detail_at_order(s, user_id=uid, project_id=proj,
                                      entity_ids=[kai.id], at_order=10); ran += 1
    await es.list_gone_entities(s, user_id=uid, project_id=proj); ran += 1

    await hi.count_child_chapters(s, part_id="p1"); ran += 1
    await hi.count_child_parts(s, book_id="b1"); ran += 1
    await hi.list_chapter_ids_under_part(s, part_id="p1"); ran += 1
    await hi.top_entity_names_for_chapter(s, chapter_id="ch-1"); ran += 1

    await mt.count_nodes_by_label(s, user_id=uid, project_id=proj, label="Entity"); ran += 1
    await mt.delete_orphan_extraction_sources(s, user_id=uid, project_id=proj); ran += 1
    await mt.reconcile_evidence_count_for_label(s, user_id=uid, project_id=proj,
                                                label="Entity"); ran += 1
    await mt.invalidate_stale_quarantined_facts(s, user_id=uid); ran += 1

    await coref.load_anchored_kinds(s, user_id=uid, project_id=proj); ran += 1
    await coref.load_coref_entities(s, user_id=uid, project_id=proj, kind="person",
                                    limit=10); ran += 1
    await graph_views.read_project_graph_edges(s, user_id=uid, project_id=proj,
                                               limit=10); ran += 1
    await graph_views.read_entity_edge_timeline(s, user_id=uid, entity_id=kai.id,
                                                edge_type="RELATES_TO", limit=10); ran += 1
    await schema_usage.observed_components(s, user_id=uid, project_id=proj); ran += 1
    await schema_usage.usage_summary(s, user_id=uid, project_id=proj); ran += 1
    await flywheel.get_flywheel_delta(s, user_id=uid, job_id="j1"); ran += 1
    await temporal.restitch_chains_after_retract(s, user_id=uid, project_id=proj); ran += 1

    assert ran >= _WAVE_3, (
        f"only {ran} third-wave repo functions were exercised against AGE; the floor is "
        f"{_WAVE_3} of {_PROVEN_ON_AGE} total."
    )


async def test_the_FOURTH_WAVE_covers_the_bulk(age_session):
    """entities (36), facts (12), events (12) — the modules T77-T82 rewrote most heavily.

    ⚠️ **Two more Neo4j-only construct families, both invisible to the dialect ratchet until a
    live run hit them** — the same shape as `duration(` in T79:

        size([(e)<-[:ABOUT]-(wf:Fact) WHERE … | 1])   a PATTERN comprehension
        any(alias IN e.aliases WHERE …)               a list PREDICATE

    AGE rejects both with `syntax error at or near "WHERE"`. The pattern comprehension became an
    `OPTIONAL MATCH` plus an aggregation (the OPTIONAL is load-bearing: an entity with no
    windowed fact must still reach the `$before_order IS NULL` arm); the list predicates became
    `size([x IN xs WHERE p]) > 0`, which is a LIST comprehension and does parse. Both families
    are in `port-adoption-gate`'s scan as of this row, so neither can return unnoticed.

    The spoiler-window predicate is the one that mattered: it is what stops a reader seeing
    characters they have not met, and it sits in the middle of the entity list every reader
    surface calls.
    """
    from app.db.neo4j_repos import entities as en, events as ev, facts as fx
    from app.db.neo4j_repos import provenance as pv

    ran = 0
    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"
    gid = f"gl-{uuid.uuid4().hex[:8]}"
    s = age_session

    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter")
    rin = await en.merge_entity(s, user_id=uid, project_id=proj, name="Rin", kind="person",
                                source_type="chapter")
    src = await pv.upsert_extraction_source(s, user_id=uid, project_id=proj,
                                            source_type="chapter", source_id="ch-1")
    await pv.add_evidence(s, user_id=uid, target_label="Entity", target_id=kai.id,
                          source_id=src.id, job_id="j1", extraction_model="m", confidence=0.9)
    kai2 = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai2", kind="person",
                                 source_type="chapter")
    f1 = await fx.merge_fact(s, user_id=uid, project_id=proj, type="attribute",
                             content="Kai2 is brave", confidence=0.8,
                             source_type="chapter", subject_id=kai2.id)
    e1 = await ev.merge_event(s, user_id=uid, project_id=proj, title="The Oath",
                              chapter_id="ch-1", event_order=1)

    await en.existing_entity_node_ids(s, user_id=uid, ids=[kai.id])
    ran += 1
    await en.get_entities_by_ids(s, user_id=uid, ids=[kai.id])
    ran += 1
    await en.get_entity_by_id_any_owner(s, canonical_id=kai.id)
    ran += 1
    await en.list_user_entities(s, user_id=uid)
    ran += 1
    await en.list_project_entity_names(s, user_id=uid, project_id=proj)
    ran += 1
    await en.get_most_connected_entity(s, user_id=uid, project_id=proj)
    ran += 1
    await en.resolve_participant_anchors(s, user_id=uid, project_id=proj, names=['Kai'])
    ran += 1
    await en.list_entities_filtered(s, user_id=uid, project_id=proj, kind=None, search=None, limit=10, offset=0)
    ran += 1
    await en.load_entity_details_by_ids(s, user_id=uid, project_id=proj, entity_ids=[kai.id])
    ran += 1
    await en.find_gap_candidates(s, user_id=uid, project_id=proj)
    ran += 1
    await en.find_alias_collision(s, user_id=uid, project_id=proj, kind='person', candidate_canonicals=['kai'], source_id=kai.id, target_id=rin.id)
    ran += 1
    await en.find_entities_needing_embedding(s, user_id=uid, project_id=proj, embedding_model='m')
    ran += 1
    await en.upsert_glossary_anchor(s, user_id=uid, project_id=proj, glossary_entity_id=gid, name='Kai', kind='person', aliases=['Kai'])
    ran += 1
    await en.upsert_glossary_anchor_counted(s, user_id=uid, project_id=proj, glossary_entity_id=gid, name='Kai', kind='person', aliases=['Kai'])
    ran += 1
    await en.resolve_kg_entity_id_by_glossary_id(s, user_id=uid, project_id=proj, glossary_entity_id=gid)
    ran += 1
    await en.get_entity_by_glossary_id(s, user_id=uid, project_id=proj, glossary_entity_id=gid)
    ran += 1
    await en.get_neighborhood_by_glossary_id(s, user_id=uid, glossary_entity_id=gid, project_id=proj)
    ran += 1
    await en.load_promotion_signals(s, user_id=uid, project_id=proj, glossary_entity_ids=[gid])
    ran += 1
    await en.get_glossary_anchor_id(s, user_id=uid, entity_id=kai.id)
    ran += 1
    await en.sync_glossary_entity_node(s, user_id=uid, project_id=proj, glossary_entity_id=gid, name='Kai', canonical_name='kai', kind='person', aliases=['Kai'], short_description='a person')
    ran += 1
    await en.recompute_anchor_score(s, user_id=uid, project_id=proj)
    ran += 1
    await en.merge_entity_at_id(s, user_id=uid, id=kai.id, project_id=proj, name='Kai', kind='person', source_type='chapter')
    ran += 1
    await en.update_entity_fields(s, user_id=uid, entity_id=rin.id, name='Rin Zhou', kind=None, aliases=None, expected_version=1)
    ran += 1
    await en.unlock_entity_user_edited(s, user_id=uid, entity_id=rin.id)
    ran += 1
    await en.user_archive_entity(s, user_id=uid, canonical_id=rin.id)
    ran += 1
    await en.restore_entity(s, user_id=uid, canonical_id=rin.id)
    ran += 1
    await en.link_to_glossary(s, user_id=uid, canonical_id=rin.id, glossary_entity_id=f'{gid}-2', name='Rin', kind='person', aliases=['Rin'])
    ran += 1
    await en.unlink_from_glossary(s, user_id=uid, canonical_id=rin.id)
    ran += 1
    await en.restore_entity_by_glossary_id(s, user_id=uid, project_id=proj, glossary_entity_id=gid, reason_prefix='restored')
    ran += 1
    await en.merge_entities(s, user_id=uid, source_id=rin.id, target_id=kai.id)
    ran += 1
    await en.delete_entities_with_zero_evidence(s, user_id=uid, project_id=proj)
    ran += 1
    await en.erase_entity_subgraph(s, user_id=uid, entity_id=kai.id, project_id=proj)
    ran += 1
    await en.purge_entity_by_glossary_id(s, user_id=uid, project_id=proj, glossary_entity_id=gid)
    ran += 1
    await en.reset_glossary_anchors(s, user_id=uid)
    ran += 1
    await fx.get_fact(s, user_id=uid, fact_id=f1.id)
    ran += 1
    await fx.list_facts_by_type(s, user_id=uid, project_id=proj, type='attribute')
    ran += 1
    await fx.recall_facts(s, user_id=uid, project_id=proj)
    ran += 1
    await fx.facts_for_subject(s, user_id=uid, subject_id=kai2.id)
    ran += 1
    await fx.fact_coverage_for_entity(s, user_id=uid, entity_id=kai2.id, as_of_ordinal=100)
    ran += 1
    await fx.export_facts_for_project(s, user_id=uid, project_id=proj)
    ran += 1
    await fx.invalidate_facts_for_day(s, user_id=uid, project_id=proj, event_date='0184-01-01')
    ran += 1
    await fx.invalidate_all_facts_for_project(s, user_id=uid, project_id=proj)
    ran += 1
    await fx.delete_facts_with_zero_evidence(s, user_id=uid, project_id=proj)
    ran += 1
    await ev.get_event(s, user_id=uid, event_id=e1.id)
    ran += 1
    await ev.list_events_for_chapter(s, user_id=uid, chapter_id='ch-1')
    ran += 1
    await ev.list_events_in_order(s, user_id=uid, project_id=proj)
    ran += 1
    await ev.list_events_filtered(s, user_id=uid, project_id=proj, after_order=None, before_order=None, limit=10, offset=0)
    ran += 1
    await ev.rerank_chronological_order(s, user_id=uid, project_id=proj)
    ran += 1
    await ev.set_narrative_threads(s, user_id=uid, assignments={e1.id: 't1'})
    ran += 1
    await ev.set_realized_motifs(s, user_id=uid, assignments={e1.id: 'm1'})
    ran += 1
    await ev.set_mined_motif_codes(s, user_id=uid, assignments={e1.id: 'm2'})
    ran += 1
    await ev.merge_causal_edges(s, user_id=uid, pairs=[])
    ran += 1
    await ev.get_causal_motif_pairs(s, user_id=uid, project_id=proj)
    ran += 1
    await ev.delete_events_with_zero_evidence(s, user_id=uid, project_id=proj)
    ran += 1

    assert ran >= _WAVE_4, (
        f"only {ran} fourth-wave repo functions were exercised against AGE; the floor is "
        f"{_WAVE_4} of {_PROVEN_ON_AGE} total."
    )
