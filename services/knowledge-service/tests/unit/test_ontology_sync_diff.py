"""Lane LC — pure unit tests for the tree-granular sync diff (driver-free).

`_diff_trees` compares two "tree surfaces" (upstream vs project copy, the same
dict shape `_tree_surface` builds) and emits per-child `added` / `modified` /
`removed_upstream` changes at edge/fact/node-kind/vocab granularity (§10-A3).
"""

from __future__ import annotations

from app.db.repositories.ontology_mutations import _diff_trees


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


def test_identical_trees_no_changes():
    s = _surface(edge_types=[_edge("LOVER_OF")], fact_types=[["death", "Death"]])
    assert _diff_trees(s, s) == []


def test_edge_added_upstream():
    up = _surface(edge_types=[_edge("LOVER_OF"), _edge("SWORN_SIBLING_OF")])
    mine = _surface(edge_types=[_edge("LOVER_OF")])
    changes = _diff_trees(up, mine)
    added = [c for c in changes if c["change"] == "added"]
    assert len(added) == 1
    assert added[0]["node_type"] == "edge_type"
    assert added[0]["code"] == "SWORN_SIBLING_OF"


def test_edge_modified_reports_fields_changed():
    up = _surface(edge_types=[_edge("LOVER_OF", label="lover of (updated)", temporal=True)])
    mine = _surface(edge_types=[_edge("LOVER_OF", label="lover of")])
    changes = _diff_trees(up, mine)
    mod = [c for c in changes if c["change"] == "modified"]
    assert len(mod) == 1
    assert set(mod[0]["fields_changed"]) == {"label", "temporal"}


def test_edge_removed_upstream():
    up = _surface(edge_types=[_edge("LOVER_OF")])
    mine = _surface(edge_types=[_edge("LOVER_OF"), _edge("MY_CUSTOM_EDGE")])
    changes = _diff_trees(up, mine)
    removed = [c for c in changes if c["change"] == "removed_upstream"]
    assert [c["code"] for c in removed] == ["MY_CUSTOM_EDGE"]


def test_fact_and_node_kind_pairs_diff():
    up = _surface(
        fact_types=[["death", "Death"], ["betrayal", "Betrayal"]],
        node_kinds=[["character", "required"]],
    )
    mine = _surface(
        fact_types=[["death", "Death"]],
        node_kinds=[["character", "optional"]],
    )
    changes = _diff_trees(up, mine)
    facts = [c for c in changes if c["node_type"] == "fact_type"]
    assert facts[0]["change"] == "added" and facts[0]["code"] == "betrayal"
    nks = [c for c in changes if c["node_type"] == "node_kind"]
    assert nks[0]["change"] == "modified"
    assert nks[0]["fields_changed"] == ["label"]  # pair stores strength under 'label'


def test_vocab_set_added_and_value_modified():
    up = _surface(
        vocab_sets=[
            {
                "code": "drive", "label": "Drive", "description": "", "closed": True,
                "values": [["revenge", "Revenge", {"axis": "conflict"}]],
            }
        ]
    )
    mine = _surface(
        vocab_sets=[
            {
                "code": "drive", "label": "Drive", "description": "", "closed": True,
                "values": [["revenge", "Vengeance", {"axis": "conflict"}]],
            }
        ]
    )
    changes = _diff_trees(up, mine)
    vv = [c for c in changes if c["node_type"] == "vocab_value"]
    assert len(vv) == 1
    assert vv[0]["change"] == "modified"
    assert vv[0]["parent_code"] == "drive"
    assert vv[0]["code"] == "revenge"
    assert "label" in vv[0]["fields_changed"]


def test_vocab_value_added_upstream():
    up = _surface(
        vocab_sets=[
            {
                "code": "drive", "label": "Drive", "description": "", "closed": True,
                "values": [["revenge", "Revenge", {}], ["godhood", "Godhood", {}]],
            }
        ]
    )
    mine = _surface(
        vocab_sets=[
            {
                "code": "drive", "label": "Drive", "description": "", "closed": True,
                "values": [["revenge", "Revenge", {}]],
            }
        ]
    )
    changes = _diff_trees(up, mine)
    vv = [c for c in changes if c["node_type"] == "vocab_value" and c["change"] == "added"]
    assert [c["code"] for c in vv] == ["godhood"]
