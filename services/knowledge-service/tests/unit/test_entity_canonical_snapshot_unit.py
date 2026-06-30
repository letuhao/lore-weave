"""F3 slice 5 — per-entity canonical snapshot (unit-level shape checks).

The full cache lifecycle is the integration test (real Postgres); here we lock
the content-hash key + the Neo4j coverage-staleness-key cypher shape.
"""

from __future__ import annotations

from app.db.neo4j_repos import facts as fm
from app.db.repositories.entity_canonical_snapshots import (
    MAX_FOLD_ATTEMPTS,
    snapshot_content_hash,
)


def test_content_hash_is_stable_sha256():
    import hashlib

    content = "张若尘 is a cultivator who reaches 黄极境 by ch.500."
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert snapshot_content_hash(content) == expected
    # identical content → identical hash (translation/diff cache hit, D8)
    assert snapshot_content_hash(content) == snapshot_content_hash(content)
    # a re-ground that changes content → different hash (cache miss)
    assert snapshot_content_hash(content) != snapshot_content_hash(content + " ")


def test_max_fold_attempts_mirrors_kg_retry_budget():
    assert MAX_FOLD_ATTEMPTS == 3  # mirrors the KG RETRY_BUDGET=3 (B4)


def test_fact_coverage_cypher_is_ordinal_scoped_and_tenant_safe():
    """The staleness key = max(updated_at) over facts valid at/under the ordinal,
    scoped to the entity + tenant. A late fact under the ordinal bumps this →
    snapshot stale (B3)."""
    cy = fm._FACT_COVERAGE_FOR_ENTITY_CYPHER
    assert "max(f.updated_at) AS coverage" in cy
    assert "f.valid_from_ordinal <= $as_of_ordinal" in cy
    assert "f.valid_until IS NULL" in cy            # survivors only
    assert "f.valid_from_ordinal IS NOT NULL" in cy  # positionless excluded
    assert "f.user_id = $user_id" in cy             # tenant-scoped
    assert ":ABOUT]->(e:Entity {id: $entity_id})" in cy
