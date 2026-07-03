"""B1(4) T0 — cross-partition unification engine (lexical) unit tests.

Pure clustering (no Neo4j): builds `UnifySeed`s directly and asserts each folded
edge case from the spec — kind-gate (EC-M3), cross-partition-only (EC-M10),
degenerate key (EC-M18), common-name guard (EC-M20), per-method band (EC-M17),
deterministic cluster_id (EC-M22), singleton (EC-M12), N>2 pairwise bridges
(Q3/EC-M8), cluster size + count caps (EC-M7/M11/M21).
"""

from __future__ import annotations

import pytest

import app.tools.kg_unify as ku
from app.tools.kg_unify import UnifySeed, cluster_seeds


def _seed(pid, eid, name, *, kind="character", canonical_name="", aliases=()):
    return UnifySeed(
        project_id=pid,
        entity_id=eid,
        name=name,
        kind=kind,
        canonical_name=canonical_name,
        aliases=tuple(aliases),
    )


# ── happy path ─────────────────────────────────────────────────────────


def test_two_partition_same_name_one_cluster_one_bridge():
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "a2", "Alice")]
    out = cluster_seeds(seeds, "by_name")

    assert len(out["unification_clusters"]) == 1
    cl = out["unification_clusters"][0]
    assert cl["kind"] == "character"
    assert cl["score"] == 1.0 and cl["band"] == "same"
    assert {m["entity_id"] for m in cl["members"]} == {"a1", "a2"}
    assert cl["method"] == "by_name"

    assert len(out["bridge_edges"]) == 1
    br = out["bridge_edges"][0]
    assert br["predicate"] == "SAME_AS" and br["inferred"] is True
    assert {br["source"], br["target"]} == {"a1", "a2"}
    assert br["score"] == 1.0
    assert out["unify_method"] == "by_name"
    assert out["unify_capped"] is False


def test_kind_gate_blocks_cross_kind():
    """EC-M3 — a same-name character and location never unify."""
    seeds = [_seed("P1", "a1", "Avalon", kind="character"),
             _seed("P2", "a2", "Avalon", kind="location")]
    out = cluster_seeds(seeds, "by_name")
    assert out["unification_clusters"] == []
    assert out["bridge_edges"] == []


def test_cross_partition_only_no_same_partition_bridge():
    """EC-M10 — two entities sharing an alias in the SAME book never bridge; only a
    cross-partition match does."""
    seeds = [
        _seed("P1", "a1", "Alice", aliases=("Ali",)),
        _seed("P1", "a1b", "Alicia", aliases=("Ali",)),  # same partition as a1
        _seed("P2", "z1", "Zed"),
    ]
    out = cluster_seeds(seeds, "by_name")
    # a1 & a1b share an alias but are same-partition → never a bridge; nothing
    # cross-partition matches → no clusters at all.
    assert out["unification_clusters"] == []
    for br in out["bridge_edges"]:
        assert {br["source"], br["target"]} != {"a1", "a1b"}
    assert out["bridge_edges"] == []


def test_empty_normalized_key_skipped():
    """EC-M18 — a name that canonicalizes to empty (pure punctuation) is never a
    match key; two such seeds don't cluster."""
    seeds = [_seed("P1", "x1", "!!!"), _seed("P2", "x2", "???")]
    out = cluster_seeds(seeds, "by_name")
    assert out["unification_clusters"] == []


def test_common_name_needs_extra_alias():
    """EC-M20 — a generic name ('Master') needs an extra shared alias beyond the name
    itself; bare name-equality does not cluster."""
    bare = [_seed("P1", "m1", "Master"), _seed("P2", "m2", "Master")]
    assert cluster_seeds(bare, "by_name")["unification_clusters"] == []

    with_alias = [
        _seed("P1", "m1", "Master", aliases=("Kai",)),
        _seed("P2", "m2", "Master", aliases=("Kai",)),
    ]
    out = cluster_seeds(with_alias, "by_name")
    assert len(out["unification_clusters"]) == 1
    assert out["unification_clusters"][0]["score"] == 1.0


def test_alias_overlap_yields_likely_band():
    """EC-M17 — different canonical names but a shared alias cluster at a 'likely'
    band with an alias-only (sub-1.0) score."""
    seeds = [
        _seed("P1", "a1", "Alice", aliases=("Ali",)),
        _seed("P2", "a2", "Alicia", aliases=("Ali",)),
    ]
    out = cluster_seeds(seeds, "by_name")
    assert len(out["unification_clusters"]) == 1
    cl = out["unification_clusters"][0]
    assert cl["band"] == "likely"
    assert 0.5 <= cl["score"] < 1.0
    assert out["bridge_edges"][0]["score"] < 1.0


def test_singleton_not_in_clusters():
    """EC-M12 — an entity with no cross-partition match is not a cluster."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "b1", "Bob")]
    out = cluster_seeds(seeds, "by_name")
    assert out["unification_clusters"] == []
    assert out["bridge_edges"] == []


def test_deterministic_cluster_id():
    """EC-M22 — the ephemeral cluster_id is a stable hash of sorted member ids."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "a2", "Alice")]
    id1 = cluster_seeds(list(seeds), "by_name")["unification_clusters"][0]["cluster_id"]
    id2 = cluster_seeds(list(reversed(seeds)), "by_name")["unification_clusters"][0]["cluster_id"]
    assert id1 == id2
    assert id1.startswith("uc_") and len(id1) == 3 + 16


def test_n_partitions_pairwise_bridges():
    """Q3/EC-M8 — 3 partitions of the same entity → one 3-member cluster + 3
    pairwise SAME_AS bridges."""
    seeds = [_seed(f"P{i}", f"a{i}", "Alice") for i in range(1, 4)]
    out = cluster_seeds(seeds, "by_name")
    assert len(out["unification_clusters"]) == 1
    assert len(out["unification_clusters"][0]["members"]) == 3
    assert len(out["bridge_edges"]) == 3  # k=3 → C(3,2)=3 pairwise
    for br in out["bridge_edges"]:
        assert br["predicate"] == "SAME_AS"


def test_cluster_size_cap_drops_oversize(monkeypatch):
    """EC-M7 — a cluster spanning more partitions than the size cap is dropped (a weak
    transitive chain can't silently glue distinct entities)."""
    monkeypatch.setattr(ku, "UNIFY_MAX_CLUSTER_SIZE", 2)
    seeds = [_seed(f"P{i}", f"a{i}", "Alice") for i in range(1, 4)]  # 3 > cap 2
    out = cluster_seeds(seeds, "by_name")
    assert out["unification_clusters"] == []


def test_cluster_count_cap_keeps_highest_confidence(monkeypatch):
    """EC-M11/M21 — with the cluster cap at 1, the higher-confidence cluster survives
    and unify_capped is flagged."""
    monkeypatch.setattr(ku, "UNIFY_MAX_CLUSTERS", 1)
    seeds = [
        # exact-match cluster (score 1.0)
        _seed("P1", "x1", "Alice"), _seed("P2", "x2", "Alice"),
        # alias-only cluster (score 0.5)
        _seed("P1", "y1", "Borin", aliases=("Bo",)),
        _seed("P2", "y2", "Boren", aliases=("Bo",)),
    ]
    out = cluster_seeds(seeds, "by_name")
    assert len(out["unification_clusters"]) == 1
    assert out["unify_capped"] is True
    assert out["unification_clusters"][0]["band"] == "same"  # the 1.0 one kept


def test_under_two_partitions_is_empty():
    """A bridge is cross-partition by definition; a single partition can't unify."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P1", "a2", "Alice2")]
    out = cluster_seeds(seeds, "by_name")
    assert out == {
        "unification_clusters": [],
        "bridge_edges": [],
        "unify_method": "by_name",
        "unify_capped": False,
    }


def test_canonical_name_field_used_when_present():
    """norm_key prefers the stored canonical_name over recomputing from name."""
    seeds = [
        _seed("P1", "a1", "Alice Smith", canonical_name="alice"),
        _seed("P2", "a2", "Alice Jones", canonical_name="alice"),
    ]
    out = cluster_seeds(seeds, "by_name")
    assert len(out["unification_clusters"]) == 1
    assert out["unification_clusters"][0]["score"] == 1.0
