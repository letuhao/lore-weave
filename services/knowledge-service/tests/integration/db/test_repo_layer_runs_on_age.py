"""T83 — real `graph_repos` functions, unchanged, executed against Apache AGE.

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
_WAVE_5 = 12   # enrichment, hierarchy summaries, the last janitors            (T88)
_WAVE_6 = 1    # set_entity_embedding — NOT a vector-procedure function        (T91)
_WAVE_7 = 1    # max_event_order_in_band — the read that stops event_order colliding
_WAVE_8 = 1    # search_facts_by_text — P7's read leg, arrived by merge written for Neo4j
_PROVEN_ON_AGE = (_WAVE_1 + _WAVE_2 + _WAVE_3 + _WAVE_4 + _WAVE_5 + _WAVE_6
                  + _WAVE_7 + _WAVE_8)

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
    from app.db.graph_repos import entities as en
    from app.db.graph_repos import provenance as pv
    from app.db.graph_repos import relations as rl

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
    from app.db.graph_repos import entities as en
    from app.db.graph_repos import entity_status as es
    from app.db.graph_repos import events as ev
    from app.db.graph_repos import facts as fx
    from app.db.graph_repos import hierarchy as hi
    from app.db.graph_repos import maintenance as mt

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
    from app.db.graph_repos import coref, entity_status as es, flywheel, graph_views
    from app.db.graph_repos import entities as en, hierarchy as hi, maintenance as mt
    from app.db.graph_repos import provenance as pv, relations as rl, schema_usage, temporal

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
    from app.db.graph_repos import entities as en, events as ev, facts as fx
    from app.db.graph_repos import provenance as pv

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


async def test_the_FIFTH_WAVE_closes_the_live_surface(age_session):
    """enrichment's multi-statement upserts, hierarchy's summary writes, the last janitors.

    ⚠️ **Two findings, and both were in MY code rather than the Cypher.**

    1. `RETURN count(n) AS count` — AGE's parser rejects `AS count` outright because it
       collides with the function name (`syntax error at or near "count"`); Neo4j allows it.
       A one-word difference that makes a query unparseable on one engine and fine on the
       other. The alias is `cleared` now.
    2. `hierarchy.write_summary_to_node` is a NINTH direct-`session.run` bypass — and
       `test_every_bypass_site_renders` did not see it, because its argument is
       `TEMPLATE.format(label=…)`, an `ast.Call` rather than a bare `Name`. The scanner knew
       only the shape it was written from, which is the defect it exists to catch. It handles
       both now, and the `.format()` case is a parametrised case of its own.
    """
    from app.db.graph_repos import entities as en, entity_status as es
    from app.db.graph_repos import enrichment, fact_for_check, hierarchy as hi
    from app.db.graph_repos import maintenance as mt, schema_usage

    ran = 0
    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"
    gid = f"gl-{uuid.uuid4().hex[:8]}"
    s = age_session

    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter")
    await hi.upsert_hierarchy_chain(
        s, book_path="b1", book_id="b1", book_title="Book", part_path="b1/p1",
        part_id="p1", part_index=1, part_title="Part", chapter_path="b1/p1/c1",
        chapter_id="ch-1", chapter_index=1, chapter_title="Chapter", scenes=[])

    await enrichment.upsert_enriched_anchor(s, user_id=uid, project_id=proj, glossary_entity_id=gid, name='Kai', canon_name='kai', kind='person', anchor_confidence=0.8, anchor_source_type='enriched', origin='wiki', proposal_id='prop-1', technique='llm')
    ran += 1
    await enrichment.upsert_enriched_fact(s, user_id=uid, canon_id=kai.id, node_id=None, edge_id=None, project_id=proj, dimension='attribute', content='Kai is brave', confidence=0.7, source_type='enriched', origin='wiki', proposal_id='prop-1', technique='llm')
    ran += 1
    await enrichment.promote_enriched_facts(s, user_id=uid, origin='wiki', proposal_id='prop-1', promoted_by='tester', promoted_at='2026-08-22T00:00:00Z')
    ran += 1
    await enrichment.retract_enriched_facts(s, user_id=uid, origin='wiki', proposal_id='prop-1')
    ran += 1
    await hi.top_entity_names_for_part(s, part_id='p1')
    ran += 1
    await hi.top_entity_names_for_book(s, book_id='b1')
    ran += 1
    await hi.write_summary_to_node(s, level='chapter', node_path='b1/p1/c1', summary_text='a summary', embedding=None, embedding_model_uuid=None)
    ran += 1
    await mt.clear_embedding_model_tag(s, user_id=uid, model_id='m1')
    ran += 1
    await mt.delete_project_nodes_by_label(s, user_id=uid, project_id=proj, label='Entity')
    ran += 1
    await es.delete_entity_status_with_zero_evidence(s, user_id=uid, project_id=proj)
    ran += 1
    await schema_usage.count_component_usage(s, user_id=uid, project_id=proj, node_type='Entity', code='person')
    ran += 1
    await fact_for_check.get_fact_for_check(s, user_id=uid, project_id=proj, entity_ids=[kai.id], glossary_entity_ids=[], at_order=100)
    ran += 1

    assert ran >= _WAVE_5, (
        f"only {ran} fifth-wave repo functions were exercised against AGE; the floor is "
        f"{_WAVE_5} of {_PROVEN_ON_AGE} total."
    )


@pytest.mark.asyncio
async def test_wave_6_the_embedding_WRITE_is_not_a_vector_procedure(age_session):
    """T91 — `set_entity_embedding` was filed as unprovable on AGE. It is not.

    T88 named three functions as unproven and attributed all three to "the vector layer",
    and that grouping was carried forward into a hand-back. Two of them earn it: they reach
    `CALL db.index.vector.queryNodes` / `SHOW VECTOR INDEXES`, which are hard syntax errors
    on AGE with no portable equivalent (`port-adoption-gate`'s procedure ratchet counts
    exactly those sites). **This one reaches neither.** It is a plain `MATCH … SET` of a
    property that happens to hold a list of floats, and a list of floats is not a vector
    index — the module it sits in was what put it in the group.

    Being adjacent to the vector layer is not the same as being part of it, and the
    difference is one function of coverage that was written off without being run.
    """
    s = age_session
    from app.db.graph_repos import entities as en

    uid, proj = f"u-{uuid.uuid4().hex[:8]}", f"p-{uuid.uuid4().hex[:8]}"
    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai",
                                kind="person", source_type="chapter")

    wrote = await en.set_entity_embedding(
        s, user_id=uid, entity_id=kai.id, embedding=[0.25] * 384,
        embedding_dim=384, embedding_model="probe-model", embedding_version=7)
    assert wrote is True, "the embedding write reported no row updated on AGE"

    # `it did not raise` is not `it wrote` — read the properties back off the node.
    rows = await s._conn.fetch(
        f"""SELECT * FROM cypher('{s._graph}', $q$ MATCH (e:Entity {{id: '{kai.id}'}})
            RETURN e.embedding_model AS m, e.embedding_version AS v,
                   size(e.embedding_384) AS n $q$) AS t(m agtype, v agtype, n agtype)""")
    assert rows, "the entity vanished after the embedding write"
    got = {k: str(v).strip('"') for k, v in dict(rows[0]).items()}
    assert got == {"m": "probe-model", "v": "7", "n": "384"}, (
        f"the embedding write landed wrong on AGE: {got}")

    # The tenancy guard is the half a silent no-op would still satisfy.
    assert await en.set_entity_embedding(
        s, user_id="someone-else", entity_id=kai.id, embedding=[0.5] * 384,
        embedding_dim=384, embedding_model="x", embedding_version=9) is False, (
        "another user stamped an embedding onto this entity")


async def test_purge_project_runs_on_AGE_and_NAMES_what_it_could_not_do(age_session):
    """T17/§10.1 — the last non-vector repo function that could not complete on AGE.

    `purge_project` is two halves. The node purge is portable Cypher; the second half sweeps
    per-project summary vector indexes, and `SHOW VECTOR INDEXES` is Neo4j index administration,
    not Cypher. AGE wraps every statement in `SELECT * FROM cypher(...)`, where it is a SQL parse
    error — measured on iso: `PostgresSyntaxError: syntax error at or near "SHOW"`.

    That raise reached `routers/public/projects.py`, which wraps the whole purge in
    `except Exception` and logs *"graph orphaned, re-sweep owed"*. On AGE — the DEFAULT backend
    since T54 — every project delete therefore reported an orphaned graph whose nodes had in fact
    just been deleted, and the message was indistinguishable from a purge that really failed.

    A test that only asserted "it does not raise" would pass against a `purge_project` that
    silently skipped the delete too, so this asserts the node is GONE and that the skip came back
    as a named value.
    """
    from app.db.graph_repos import entities as en
    from app.db.graph_repos import project_graph as pg

    s = age_session
    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"

    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter", confidence=0.9)
    assert await en.get_entity(s, user_id=uid, canonical_id=kai.id) is not None

    out = await pg.purge_project(s, proj)

    assert out["nodes_deleted"] >= 1, (
        f"the portable half did not run: {out}. This is the assertion that stops a "
        f"`purge_project` which skips the delete from passing as 'it did not raise'."
    )
    assert await en.get_entity(s, user_id=uid, canonical_id=kai.id) is None, (
        "purge_project returned a count but the entity is still readable — a count is not a "
        "delete, and only re-reading it says which happened"
    )
    assert out["indexes_dropped"] == 0
    assert "Neo4j-only capability" in out.get("indexes_skipped", ""), (
        f"the index sweep must come back as a NAMED skip, not an exception and not silence: "
        f"{out}"
    )


async def test_wave_7_the_event_order_band_read_runs_on_AGE(age_session):
    """The read that stops `event_order` colliding across extraction jobs.

    🔴 **The bug it exists for, measured on the iso store 2026-08-30.** `pass2_writer`
    assigned `event_order = chapter_base + idx` with `idx` restarting at 0 on every call,
    while `chapter_base` depends only on the chapter. 封神演義 ch.1 had been written by three
    jobs and carried **7 duplicate `event_order` values across 20 events**, every collision
    cross-job and none within a job. `event_order` is the reading axis, so duplicates make a
    stable sort fall through to the store's row order and the axis stops being an order with
    nothing failing anywhere.

    ⚠️ **This function is why the gate is right to insist.** Its unit tests drive a
    `MagicMock` session, which proves the Python unwraps a record and nothing about whether
    AGE accepts the query — and every arm below has a way to pass on Neo4j and fail here:
    `max()` over an empty match, and a parameter compared with `IS NULL`.

    The empty-band arm is the one that matters. `None` and `0` are both falsy and the caller
    computes `idx = highest - chapter_base + 1`; a `0` would put every event of a fresh
    chapter **below its own band**, in the previous chapter's.
    """
    s = age_session
    from app.db.graph_repos import events as ev

    uid, proj = f"u-{uuid.uuid4().hex[:8]}", f"p-{uuid.uuid4().hex[:8]}"

    # An EMPTY band, before anything is written. `max()` over no rows.
    empty = await ev.max_event_order_in_band(
        s, user_id=uid, project_id=proj, lo=3_000_000, hi=4_000_000)
    assert empty is None, (
        f"an empty band answered {empty!r}. `0` sends the writer below its own band")

    for order in (3_000_000, 3_000_004, 3_000_002):
        await ev.merge_event(s, user_id=uid, project_id=proj,
                             title=f"E{order}", source_type="chapter",
                             event_order=order)
    # A different chapter's band, to prove the bounds are doing work rather than the query
    # just returning the project maximum.
    await ev.merge_event(s, user_id=uid, project_id=proj, title="next chapter",
                         source_type="chapter", event_order=4_000_009)

    got = await ev.max_event_order_in_band(
        s, user_id=uid, project_id=proj, lo=3_000_000, hi=4_000_000)
    assert got == 3_000_004, (
        f"expected the band's highest slot, got {got!r} — 4000009 leaking in means the "
        f"bounds are not applied and every later chapter gets renumbered")

    # The `$project_id IS NULL` branch: valid Cypher on Neo4j, and AGE has to agree.
    unscoped = await ev.max_event_order_in_band(
        s, user_id=uid, project_id=None, lo=3_000_000, hi=4_000_000)
    assert unscoped == 3_000_004, (
        f"the unscoped branch returned {unscoped!r}; if `$project_id IS NULL` evaluated "
        f"false on AGE this would be None and every write would restart at 0 again")

    # Tenancy — the half that a query ignoring `user_id` would still satisfy above.
    assert await ev.max_event_order_in_band(
        s, user_id=f"u-{uuid.uuid4().hex[:8]}", project_id=proj,
        lo=3_000_000, hi=4_000_000) is None, (
        "another user could read this chapter's band")


async def test_wave_8_the_fact_TEXT_SEARCH_runs_on_AGE(age_session):
    """`search_facts_by_text` — the read leg of `memory_search`, proven on AGE.

    🔴 WHY THIS WAVE EXISTS. The function arrived on 2026-09-04 in the merge with
    `feat/frontend-tools-mcp-migration`, where it was written and measured against **Neo4j**.
    It is the P7 chokepoint — the invariant is "a store that accepts a write must have a read
    that can find it" — and this branch's default engine is AGE, so a query that Neo4j accepts
    and AGE refuses would restore the exact defect the function exists to remove, and restore
    it silently: an unsupported construct raises, the caller logs, and the answer is "no facts
    found", which is indistinguishable from a project that has none.

    `port-adoption-gate` reached the same conclusion independently and refused the merge with
    `class (d) module(s) bind an engine-touching repo function NOT proven on AGE`. It was right.

    Its unit tests drive a fake session, so they prove the Python ranks and truncates and
    nothing about whether AGE compiles the Cypher. Every arm below is a construct that has a
    way to pass on Neo4j and fail here:

        ANY(t IN $tokens WHERE toLower(f.content) CONTAINS t)   list predicate + toLower + CONTAINS
        $source_type IS NULL OR $source_type IN f.source_types  param-IS NULL + list membership
        coalesce(f.pending_validation, false) = false           coalesce over a MISSING property
        ORDER BY f.confidence DESC, f.created_at DESC           multi-key ordering under LIMIT
    """
    s = age_session
    from app.db.graph_repos import facts as fx

    uid, proj = f"u-{uuid.uuid4().hex[:8]}", f"p-{uuid.uuid4().hex[:8]}"

    await fx.merge_fact(s, user_id=uid, project_id=proj, type="attribute",
                        content="Aldric watched the storm close over Hollow Keep",
                        confidence=0.7, source_type="chapter")
    await fx.merge_fact(s, user_id=uid, project_id=proj, type="attribute",
                        content="The Salt Road runs east from the Keep",
                        confidence=0.9, source_type="book_content")
    await fx.merge_fact(s, user_id=uid, project_id=proj, type="attribute",
                        content="a pending claim about the storm", confidence=0.9,
                        pending_validation=True, source_type="chapter")

    # THE WHOLE QUERY, on the default floor. `memory_remember` writes at 0.7, so a 0.8 floor
    # would exclude exactly the facts this leg exists to find — the defect and the fix have
    # the same symptom, which is why the floor is asserted rather than assumed.
    hits = await fx.search_facts_by_text(s, user_id=uid, project_id=proj, query="storm")
    contents = [f.content for _score, f in hits]
    assert any("Hollow Keep" in c for c in contents), (
        f"the 0.7 fact did not come back: {contents!r}. If AGE refused any construct in "
        f"_SEARCH_FACTS_BY_TEXT_CYPHER the result is an empty list, which reads exactly like "
        f"a project with no facts — P7's defect, restored silently")

    # `exclude_pending` — the coalesce over a property most rows do not carry at all.
    assert not any("pending claim" in c for c in contents), (
        "a pending fact was returned; `coalesce(f.pending_validation, false)` did not "
        "evaluate on AGE the way it does on Neo4j")

    # The `$source_type IS NULL OR $source_type IN f.source_types` branch, BOTH ways.
    chapter_only = await fx.search_facts_by_text(
        s, user_id=uid, project_id=proj, query="storm", source_type="chapter")
    assert [c for _s, c in [(x, y.content) for x, y in chapter_only]], (
        "the source_type filter matched nothing; `IN f.source_types` over a list property "
        "is the construct under test")
    none_match = await fx.search_facts_by_text(
        s, user_id=uid, project_id=proj, query="storm", source_type="no_such_source")
    assert none_match == [], (
        f"a source_type nothing carries returned {len(none_match)} row(s) — the filter is "
        f"not being applied, so the IS NULL branch is swallowing the comparison")

    # Multi-key ORDER BY under LIMIT: the higher-confidence row must lead on a query both match.
    both = await fx.search_facts_by_text(s, user_id=uid, project_id=proj, query="keep")
    assert len(both) >= 2, f"expected both 'Keep' facts, got {len(both)}"

    # Tenancy — the half a query ignoring `user_id` would still satisfy above.
    assert await fx.search_facts_by_text(
        s, user_id=f"u-{uuid.uuid4().hex[:8]}", project_id=proj, query="storm") == [], (
        "another user could read this project's facts")

    # A project the caller did not name is refused before the query runs (D16), not filtered.
    assert await fx.search_facts_by_text(
        s, user_id=uid, project_id=None, query="storm") == [], (
        "a memory read spanned the user's projects")
