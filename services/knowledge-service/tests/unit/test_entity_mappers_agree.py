"""T17 A21 — the AGE adapter's Entity mapper and the repo layer's must agree.

They did not. `age_graph_store._to_entity` named 14 keys explicitly and the model has 21, so
seven were dropped on every read through the port: `version`, `user_edited`, `auto_created`,
`mention_count`, `evidence_count`, `created_at`, `updated_at`.

Measured on the live AGE graph before the fix — the SAME entity, both paths:

    field         repo(AGE session)          port(AgeGraphStore)
    created_at    2026-08-22 12:01:04.349    None      <-- DIVERGES
    updated_at    2026-08-22 12:01:04.349    None      <-- DIVERGES

The other five agreed only because that row held defaults; they were latent, not absent.
`version` is the one that matters most: it is the OCC token, and `_node_to_entity` carries a
`/review-impl HIGH lock` about what drifting it costs (FE reads 1, sends If-Match=1, Cypher
compares 0, 412 forever).

Two mappers for one domain object is the drift; this is the mechanism against it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.adapters.age_graph_store import _to_entity as age_map
from app.db.neo4j_repos.entities import _node_to_entity as neo_map


def _row(**over) -> dict:
    row = {
        "id": "e-1", "user_id": "u-1", "project_id": "p-1",
        "name": "Kai", "canonical_name": "kai", "kind": "person",
        "aliases": ["K"], "canonical_version": 2, "source_types": ["chapter"],
        "confidence": 0.75, "glossary_entity_id": "g-1", "anchor_score": 0.5,
        "archived_at": None, "archive_reason": None,
        # the seven the AGE mapper used to drop
        "version": 7, "user_edited": True, "auto_created": True,
        "mention_count": 12, "evidence_count": 3,
        "created_at": datetime(2026, 8, 22, 12, 1, 4, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 23, 9, 4, 49, tzinfo=timezone.utc),
    }
    row.update(over)
    return row


def test_the_two_entity_mappers_agree():
    """Every field, not a sampled few — a sampled comparison is how seven went unnoticed."""
    row = _row()
    a, n = age_map(dict(row)), neo_map(dict(row))
    differing = {f: (getattr(a, f), getattr(n, f))
                 for f in type(a).model_fields if getattr(a, f) != getattr(n, f)}
    assert not differing, f"the AGE and Neo4j Entity mappers disagree on {differing}"


def test_the_mapper_carries_the_seven_fields_it_used_to_DROP():
    """The control that would have caught the original defect.

    `test_the_two_entity_mappers_agree` alone could be satisfied by BOTH mappers dropping the
    same seven, which is agreement without correctness. This asserts the values arrive.
    """
    e = age_map(_row())
    assert e.version == 7 and e.user_edited is True and e.auto_created is True
    assert e.mention_count == 12 and e.evidence_count == 3
    assert e.created_at is not None and e.updated_at is not None


def test_a_NULL_version_still_coalesces_to_the_repo_layers_value():
    """Live AGE vertices really do hold `version = NULL`, so this is load-bearing.

    The value must match every Cypher `coalesce(e.version, N)` in the repo layer — the
    `/review-impl HIGH lock` on `_node_to_entity`. Asserted against that mapper rather than
    against the literal 1, so the two cannot drift apart silently.
    """
    row = _row(version=None, auto_created=None)
    assert age_map(dict(row)).version == neo_map(dict(row)).version
    assert age_map(dict(row)).auto_created == neo_map(dict(row)).auto_created


def test_properties_the_model_does_not_declare_are_IGNORED_not_fatal():
    """Live vertices carry five undeclared keys; pass-through must not raise on them."""
    row = _row(origin="extraction", source_type="chapter", pending_validation=False,
               original_technique=None, promoted_from_proposal_id=None)
    assert age_map(row).id == "e-1"


def test_an_entity_with_NO_IDENTITY_is_refused_by_both():
    """Neither mapper may invent an id. The AGE one used to default it to ""."""
    for mapper in (age_map, neo_map):
        with pytest.raises(Exception):
            mapper({"name": "Kai"})
