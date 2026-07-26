"""D-KG-L7-ACTIVATE — stitched live proof of the write-boundary activation.

One real ``write_pass2_extraction`` call against live Neo4j + Postgres with a
CLOSED project schema proves the whole Milestone-A chain at once:

  * an on-schema relation is written AND stamped with ``schema_version`` (Neo4j);
  * an off-schema relation is DROPPED (not written) AND parked to
    ``kg_triage_items`` with the schema version (Postgres) via the real TriageRepo.

The component pieces are also covered in isolation (create_relation stamp in
test_relations_repo, TriageRepo.park in test_kg_triage); this test is the
end-to-end stitch the unit writer tests mock out.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.db.neo4j_repos.relations import relation_id
from app.db.repositories.triage import TriageRepo
from app.extraction.pass2_writer import write_pass2_extraction
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate
from loreweave_extraction.schema_projection import ExtractionSchema


def _entity(name: str) -> LLMEntityCandidate:
    return LLMEntityCandidate(
        name=name, kind="person", aliases=[], confidence=0.9,
        canonical_name=name.lower(), canonical_id=f"eid-{name.lower()}",
    )


def _relation(subject: str, predicate: str, obj: str) -> LLMRelationCandidate:
    # subject_id/object_id are deliberately the SDK's pre-resolution placeholders;
    # the writer's Tier-A.1 chapter-local name repair resolves them to the merged
    # entity ids by name — matching the real extraction path.
    return LLMRelationCandidate(
        subject=subject, predicate=predicate, object=obj,
        subject_id=None, object_id=None,
        polarity="affirm", modality="asserted", confidence=0.9, relation_id=None,
    )


@pytest.mark.asyncio
async def test_L7_persist_closed_schema_stamps_onschema_and_parks_offschema(
    neo4j_driver, pool,
):
    user_id = str(uuid4())
    project_id = str(uuid4())
    schema = ExtractionSchema(
        edge_predicates=("trusts",), allow_free_edges=False,  # CLOSED
        schema_version=42, label=f"{project_id}@v42",
    )
    triage_repo = TriageRepo(pool)

    try:
        async with neo4j_driver.session() as session:
            result = await write_pass2_extraction(
                session,
                user_id=user_id,
                project_id=project_id,
                source_type="chapter",
                source_id="ch-L7",
                job_id=str(uuid4()),
                entities=[_entity("Kai"), _entity("Zhao")],
                relations=[
                    _relation("Kai", "trusts", "Zhao"),         # on-schema
                    _relation("Kai", "forbidden_pred", "Zhao"),  # off-schema → drop+park
                ],
                extraction_model="llm-test",
                schema=schema,
                triage_repo=triage_repo,
            )

            # Only the on-schema edge was written.
            assert result.relations_created == 1

            # The on-schema edge carries the M3 schema_version stamp (Neo4j).
            res = await session.run(
                "MATCH (s:Entity {user_id:$u})-[r:RELATES_TO {predicate:'trusts'}]->(o:Entity) "
                "RETURN r.schema_version AS sv",
                u=user_id,
            )
            rec = await res.single()
            assert rec is not None and rec["sv"] == 42

            # The off-schema edge was NOT written.
            res2 = await session.run(
                "MATCH (:Entity {user_id:$u})-[r:RELATES_TO {predicate:'forbidden_pred'}]->() "
                "RETURN count(r) AS n",
                u=user_id,
            )
            assert (await res2.single())["n"] == 0

        # The off-schema drop was PARKED to kg_triage_items (real Postgres) with
        # the schema version + the edge:<predicate> signature.
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT item_type, signature, schema_version, status "
                "FROM kg_triage_items WHERE user_id=$1 AND project_id=$2",
                UUID(user_id), project_id,
            )
        assert row is not None
        assert row["item_type"] == "unknown_edge_type"
        assert row["signature"] == "edge:forbidden_pred"
        assert row["schema_version"] == 42
        assert row["status"] == "pending"
    finally:
        # Clean up: Neo4j nodes/edges + the parked triage row (the pool fixture's
        # TRUNCATE set does not include kg_triage_items).
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n:Entity {user_id:$u}) DETACH DELETE n", u=user_id,
            )
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM kg_triage_items WHERE project_id=$1", project_id,
            )
