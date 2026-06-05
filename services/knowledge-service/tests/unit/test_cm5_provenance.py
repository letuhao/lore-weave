"""CM5 — provenance hint validation on the persist-pass2 request model.

The node-level threading (write_pass2_extraction → merge_*) is covered in
test_pass2_writer; the `provenances` ARRAY accumulate (ON CREATE / ON MATCH
dedupe-append Cypher) is integration-only (needs a real Neo4j) and is folded
into D-CANON-CYCLE0-LIVE-SMOKE. Here we lock the request contract.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.internal_extraction import PersistPass2Request


def _base(**over):
    return {
        "user_id": uuid4(),
        "source_type": "chapter",
        "source_id": "ch-1",
        "job_id": uuid4(),
        **over,
    }


def test_provenance_defaults_to_human_authored():
    req = PersistPass2Request(**_base())
    assert req.provenance == "human_authored"


def test_provenance_accepts_the_aligned_vocab():
    for v in ("human_authored", "ai_assisted", "enrichment"):
        assert PersistPass2Request(**_base(provenance=v)).provenance == v


def test_provenance_rejects_out_of_vocab_value():
    with pytest.raises(ValidationError):
        PersistPass2Request(**_base(provenance="totally_made_up"))


# ── /review-impl #1: the new `provenances` node property must not break reads ──
# The read-path converters (`_node_to_*`) validate ALL node properties against
# the Entity/Event/Fact models, which have NO `provenances` field. This locks
# the safe-drop behaviour (Pydantic `extra='ignore'`): a future `extra='forbid'`
# /`allow` would 500/leak every read once CM5 stamps provenances — and every
# OTHER fake node omits the property, so only THIS test would catch it.

def test_node_to_entity_tolerates_provenances_property():
    from app.db.neo4j_repos.entities import _node_to_entity
    ent = _node_to_entity({
        "id": "e1", "user_id": "u1", "name": "Kai", "canonical_name": "kai",
        "kind": "person", "provenances": ["human_authored", "ai_assisted"],
    })
    assert ent.id == "e1"
    assert not hasattr(ent, "provenances")  # dropped on read (V0 = write-only)


def test_node_to_event_tolerates_provenances_property():
    from app.db.neo4j_repos.events import _node_to_event
    ev = _node_to_event({
        "id": "ev1", "user_id": "u1", "title": "Duel", "canonical_title": "duel",
        "provenances": ["ai_assisted"],
    })
    assert ev.id == "ev1"


def test_node_to_fact_tolerates_provenances_property():
    from app.db.neo4j_repos.facts import _node_to_fact
    f = _node_to_fact({
        "id": "f1", "user_id": "u1", "type": "milestone",
        "content": "Kai wins", "canonical_content": "kai wins",
        "provenances": ["human_authored"],
    })
    assert f.id == "f1"
