"""B1(4) — cross-partition unification against LIVE Neo4j.

Skipped when `TEST_NEO4J_URI` is unset. Proves the pieces the unit tests can only
fake: the `_SEED_DETAIL_CYPHER` supplementary fetch (name/canonical_name/aliases/
kind/embedding coalesce) and the real per-partition `get_world_subgraph` forest
feed the unifier correctly, producing clusters + bridges + a disagreement, and the
semantic path reads the stored embedding + honours the model gate.

Self-cleaning: every entity is created under a unique `user_id`, DETACH DELETEd in
the `test_user` fixture — no global truncate, safe alongside concurrent work.
"""

from __future__ import annotations

import pytest

from app.db.neo4j_repos.entities import merge_entity, set_entity_embedding
from app.db.neo4j_repos.relations import create_relation, get_world_subgraph
from app.tools.kg_unify import unify_subgraph

pytestmark = pytest.mark.asyncio

_P1 = "kgunify-p1"
_P2 = "kgunify-p2"


async def _seed_two_book_world(session, user_id):
    """Alice + Bob recur across two books; Alice LOVES Bob in book 1 but KILLS him in
    book 2 (a disagreement). Returns the per-book entity ids."""
    ids = {}
    for pid, tag in ((_P1, "1"), (_P2, "2")):
        alice = await merge_entity(
            session, user_id=user_id, project_id=pid, name="Alice",
            kind="character", source_type="book_content", confidence=0.9,
        )
        bob = await merge_entity(
            session, user_id=user_id, project_id=pid, name="Bob",
            kind="character", source_type="book_content", confidence=0.9,
        )
        ids[f"alice{tag}"] = alice.id
        ids[f"bob{tag}"] = bob.id
    # conflicting relations (confidence ≥ subgraph min_confidence 0.8)
    await create_relation(
        session, user_id=user_id, subject_id=ids["alice1"], predicate="LOVES",
        object_id=ids["bob1"], confidence=0.9,
    )
    await create_relation(
        session, user_id=user_id, subject_id=ids["alice2"], predicate="KILLS",
        object_id=ids["bob2"], confidence=0.9,
    )
    return ids


@pytest.fixture
def test_user(neo4j_driver):
    import uuid

    return f"u-kgunify-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
async def _cleanup(neo4j_driver, test_user):
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Entity {user_id: $u}) DETACH DELETE e", u=test_user
        )


async def test_lexical_unify_clusters_bridges_and_disagreement(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        ids = await _seed_two_book_world(session, test_user)
        subgraph = await get_world_subgraph(
            session, user_id=test_user, project_ids=[_P1, _P2], limit=200,
        )
        out = await unify_subgraph(
            session, user_id=test_user, subgraph=subgraph, method="by_name",
        )

    # Alice + Bob each recur across the two books → two clusters, two bridges.
    clusters = {c["kind"]: c for c in out["unification_clusters"]}
    assert len(out["unification_clusters"]) == 2
    member_sets = sorted(
        sorted(m["entity_id"] for m in c["members"])
        for c in out["unification_clusters"]
    )
    assert member_sets == sorted(
        [sorted([ids["alice1"], ids["alice2"]]), sorted([ids["bob1"], ids["bob2"]])]
    )
    assert len(out["bridge_edges"]) == 2
    assert all(b["predicate"] == "SAME_AS" and b["inferred"] for b in out["bridge_edges"])

    # LOVES (book 1) vs KILLS (book 2) on the unified Alice→Bob → one disagreement.
    assert len(out["disagreements"]) == 1
    d = out["disagreements"][0]
    assert {d["predicate_a"], d["predicate_b"]} == {"LOVES", "KILLS"}
    assert "target_cluster_id" in d


async def test_semantic_unify_reads_stored_embedding_and_model_gate(neo4j_driver, test_user):
    dim = 384
    vec = [1.0] + [0.0] * (dim - 1)
    async with neo4j_driver.session() as session:
        ids = await _seed_two_book_world(session, test_user)
        # Anchor identical vectors on both Alice nodes under one model → cosine 1.0.
        for eid in (ids["alice1"], ids["alice2"]):
            ok = await set_entity_embedding(
                session, user_id=test_user, entity_id=eid, embedding=vec,
                embedding_dim=dim, embedding_model="test-model", embedding_version=1,
            )
            assert ok
        subgraph = await get_world_subgraph(
            session, user_id=test_user, project_ids=[_P1, _P2], limit=200,
        )
        # embedding_client=None → no on-demand embed; both Alices are already anchored.
        out = await unify_subgraph(
            session, user_id=test_user, subgraph=subgraph, method="semantic",
            embedding_client=None,
        )

    alice = next(
        c for c in out["unification_clusters"]
        if sorted(m["entity_id"] for m in c["members"]) == sorted([ids["alice1"], ids["alice2"]])
    )
    assert alice["method"] == "semantic"  # matched via the stored vectors (coalesce read)
    assert alice["band"] == "same"
    assert out["unify_embed_skipped"] == 0
