"""Lane F (D-KG-LC-REVADOPT-LOSS) — pure unit tests for the re-adopt loss preview.

`compute_adopt_losses(current_surface, incoming_surface)` answers "what will you
LOSE if you re-adopt?". Re-adopt replaces the project's active schema with a fresh
copy of the incoming source (ontology_mutations.adopt deprecates all prior active
project schemas). So any child the CURRENT copy has that the incoming source does
NOT have — or has differently — is silently dropped/overwritten.

It reuses the same tree-diff substrate as sync (_diff_trees), framing `incoming`
as "upstream" and `current` as "mine":
  * removed_upstream = present in current only  → a customization that vanishes (LOSS)
  * modified         = present in both, differs → current value overwritten   (LOSS)
  * added            = present in incoming only → a GAIN, never a loss
"""

from __future__ import annotations

from app.db.repositories.ontology_mutations import compute_adopt_losses


def _surface(**kw) -> dict:
    base = {
        "name": "S",
        "description": "",
        "allow_free_edges": True,
        "node_kinds": [],
        "edge_types": [],
        "fact_types": [],
        "vocab_sets": [],
    }
    base.update(kw)
    return base


def _edge(code, label="l", **kw):
    e = {
        "code": code, "label": label, "directed": True,
        "source_node_kinds": [], "target_node_kinds": [],
        "temporal": False, "provenance_required": False,
        "cardinality": "multi_active", "description": "",
    }
    e.update(kw)
    return e


def test_identical_trees_no_loss():
    s = _surface(edge_types=[_edge("LOVER_OF")])
    assert compute_adopt_losses(current=s, incoming=s) == []


def test_user_only_addition_surfaces_as_loss():
    # current has a custom edge the incoming template lacks → that edge is lost.
    current = _surface(edge_types=[_edge("LOVER_OF"), _edge("MY_CUSTOM_EDGE")])
    incoming = _surface(edge_types=[_edge("LOVER_OF")])
    losses = compute_adopt_losses(current=current, incoming=incoming)
    assert len(losses) == 1
    assert losses[0]["node_type"] == "edge_type"
    assert losses[0]["code"] == "MY_CUSTOM_EDGE"
    assert losses[0]["change"] == "removed_upstream"


def test_modified_child_is_a_loss():
    # current customized LOVER_OF's label; re-adopt overwrites it → loss (modified).
    current = _surface(edge_types=[_edge("LOVER_OF", label="my custom label")])
    incoming = _surface(edge_types=[_edge("LOVER_OF", label="lover of")])
    losses = compute_adopt_losses(current=current, incoming=incoming)
    assert len(losses) == 1
    assert losses[0]["change"] == "modified"
    assert losses[0]["code"] == "LOVER_OF"
    assert "label" in losses[0]["fields_changed"]


def test_incoming_only_addition_is_not_a_loss():
    # incoming brings a NEW edge → a gain, not a loss; nothing reported.
    current = _surface(edge_types=[_edge("LOVER_OF")])
    incoming = _surface(edge_types=[_edge("LOVER_OF"), _edge("NEW_FROM_TEMPLATE")])
    assert compute_adopt_losses(current=current, incoming=incoming) == []


def test_mixed_surfaces_only_losses():
    current = _surface(
        edge_types=[_edge("LOVER_OF"), _edge("CUSTOM_A")],
        fact_types=[["death", "Death"], ["custom_fact", "Custom"]],
        node_kinds=[["character", "required"]],
    )
    incoming = _surface(
        edge_types=[_edge("LOVER_OF"), _edge("NEW_TEMPLATE_EDGE")],
        fact_types=[["death", "Death"]],
        node_kinds=[["character", "optional"]],
    )
    losses = compute_adopt_losses(current=current, incoming=incoming)
    codes = {(c["node_type"], c["code"], c["change"]) for c in losses}
    # CUSTOM_A (edge removed), custom_fact (fact removed), character strength change
    assert ("edge_type", "CUSTOM_A", "removed_upstream") in codes
    assert ("fact_type", "custom_fact", "removed_upstream") in codes
    assert ("node_kind", "character", "modified") in codes
    # NEW_TEMPLATE_EDGE is a gain — not surfaced.
    assert all(c["code"] != "NEW_TEMPLATE_EDGE" for c in losses)


def test_vocab_value_loss():
    current = _surface(
        vocab_sets=[{
            "code": "drive", "label": "Drive", "description": "", "closed": True,
            "values": [["revenge", "Revenge", {}], ["my_drive", "Mine", {}]],
        }]
    )
    incoming = _surface(
        vocab_sets=[{
            "code": "drive", "label": "Drive", "description": "", "closed": True,
            "values": [["revenge", "Revenge", {}]],
        }]
    )
    losses = compute_adopt_losses(current=current, incoming=incoming)
    vv = [c for c in losses if c["node_type"] == "vocab_value"]
    assert [c["code"] for c in vv] == ["my_drive"]
    assert vv[0]["change"] == "removed_upstream"
    assert vv[0]["parent_code"] == "drive"
