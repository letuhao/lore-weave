"""B1(4) T0 — cross-partition unification engine (lexical) unit tests.

Pure clustering (no Neo4j): builds `UnifySeed`s directly and asserts each folded
edge case from the spec — kind-gate (EC-M3), cross-partition-only (EC-M10),
degenerate key (EC-M18), common-name guard (EC-M20), per-method band (EC-M17),
deterministic cluster_id (EC-M22), singleton (EC-M12), N>2 pairwise bridges
(Q3/EC-M8), cluster size + count caps (EC-M7/M11/M21).
"""

from __future__ import annotations

from types import SimpleNamespace

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


def _vseed(pid, eid, name, vec, *, model="bge-m3", kind="character", aliases=()):
    return UnifySeed(
        project_id=pid,
        entity_id=eid,
        name=name,
        kind=kind,
        canonical_name="",
        aliases=tuple(aliases),
        embedding=tuple(float(x) for x in vec),
        embedding_model=model,
    )


class _FakeEmbed:
    """A spy EmbeddingClient: records calls, returns an identical unit vector per text
    (so on-demand-embedded seeds cosine-match an anchored [1,0,0])."""

    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    async def embed(self, *, user_id, model_source, model_ref, texts):
        self.calls.append((model_ref, list(texts)))
        if self._fail:
            raise RuntimeError("boom")
        return SimpleNamespace(
            embeddings=[[1.0, 0.0, 0.0] for _ in texts], dimension=3, model=model_ref
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
        "disagreements": [],
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


# ── T1: semantic signal ──────────────────────────────────────────────────


def test_semantic_matches_renamed_recurrence():
    """T1 gate — two SAME-model, near-identical-vector entities with DIFFERENT names
    (a renamed recurrence lexical can't catch) cluster via semantic at the 'same' band."""
    seeds = [_vseed("P1", "a1", "Aleks", [1, 0, 0]),
             _vseed("P2", "a2", "The Wanderer", [1, 0, 0])]
    out = cluster_seeds(seeds, "semantic")
    assert len(out["unification_clusters"]) == 1
    cl = out["unification_clusters"][0]
    assert cl["method"] == "semantic" and cl["band"] == "same"
    assert out["bridge_edges"][0]["method"] == "semantic"
    assert out["unify_embed_skipped"] == 0


def test_semantic_model_gate_blocks_cross_model():
    """EC-M1 — identical vectors under DIFFERENT embedding_models are never compared;
    with no lexical overlap no cluster forms."""
    seeds = [_vseed("P1", "a1", "Aleks", [1, 0], model="bge-m3"),
             _vseed("P2", "a2", "Wanderer", [1, 0], model="openai-3-small")]
    out = cluster_seeds(seeds, "semantic")
    assert out["unification_clusters"] == []


def test_cross_model_falls_back_to_lexical():
    """EC-M1 — cross-model pairs skip cosine but still match lexically by name."""
    seeds = [_vseed("P1", "a1", "Aleks", [1, 0], model="bge-m3"),
             _vseed("P2", "a2", "Aleks", [1, 0], model="openai-3-small")]
    out = cluster_seeds(seeds, "semantic")
    assert len(out["unification_clusters"]) == 1
    assert out["unification_clusters"][0]["method"] == "by_name"  # semantic gated → lexical


def test_zero_norm_vector_skipped():
    """EC-M19 — a zero-norm vector yields no cosine (no NaN); differing names → no cluster."""
    seeds = [_vseed("P1", "a1", "Zed", [0, 0]), _vseed("P2", "a2", "Qux", [0, 0])]
    out = cluster_seeds(seeds, "semantic")
    assert out["unification_clusters"] == []


def test_semantic_is_primary_when_both_fire():
    """D1 — when name AND vector both match, the recorded method is 'semantic' (primary)."""
    seeds = [_vseed("P1", "a1", "Alice", [1, 0, 0]), _vseed("P2", "a2", "Alice", [1, 0, 0])]
    out = cluster_seeds(seeds, "semantic")
    assert out["unification_clusters"][0]["method"] == "semantic"


# ── T1: Q1=b on-demand embed (in-memory, model-match, spend-cap) ─────────


@pytest.mark.asyncio
async def test_ondemand_embed_uses_anchored_model_in_memory():
    """Q1=b/EC-M14/M16 — a discovered (vector-less) seed is embedded under the ANCHORED
    model, IN MEMORY (only embedding_client.embed is called — no set_entity_embedding)."""
    anchored = _vseed("P1", "a1", "Alice", [1, 0, 0], model="bge-m3")
    discovered = _seed("P2", "a2", "Alice")  # no vector
    client = _FakeEmbed()
    out, skipped = await ku._ondemand_embed(
        [anchored, discovered], embedding_client=client, user_id="u"
    )
    assert skipped == 0
    d = next(s for s in out if s.entity_id == "a2")
    assert d.embedding is not None and d.embedding_model == "bge-m3"
    assert client.calls and client.calls[0][0] == "bge-m3"  # embedded under anchored model


@pytest.mark.asyncio
async def test_ondemand_embed_spend_cap(monkeypatch):
    """EC-M15 — the on-demand embed count is capped; the overflow is reported."""
    monkeypatch.setattr(ku, "UNIFY_ONDEMAND_EMBED_CAP", 1)
    anchored = _vseed("P1", "a1", "Anchor", [1, 0, 0])
    d1 = _seed("P2", "d1", "Bob")
    d2 = _seed("P3", "d2", "Cy")
    out, skipped = await ku._ondemand_embed(
        [anchored, d1, d2], embedding_client=_FakeEmbed(), user_id="u"
    )
    assert skipped == 1  # 2 discovered, cap 1


@pytest.mark.asyncio
async def test_ondemand_embed_no_resolvable_model_degrades(monkeypatch):
    """EC-M14 step 3 — no anchored vector + no user default embed model → skip embed
    (never guess a model); seeds stay vector-less (semantic falls back to lexical)."""
    import app.clients.default_model as dm

    async def _none(user_id, capability="chat"):
        return None

    monkeypatch.setattr(dm, "resolve_user_default_model", _none)
    d1 = _seed("P1", "d1", "Bob")
    d2 = _seed("P2", "d2", "Bob")
    client = _FakeEmbed()
    out, skipped = await ku._ondemand_embed([d1, d2], embedding_client=client, user_id="u")
    assert skipped == 0
    assert all(s.embedding is None for s in out)
    assert client.calls == []  # never embedded — no model to embed under


@pytest.mark.asyncio
async def test_ondemand_embed_failure_degrades_not_raises():
    """EC-M15 — an embed failure degrades that batch to lexical; the tool never fails."""
    anchored = _vseed("P1", "a1", "Anchor", [1, 0, 0])
    d1 = _seed("P2", "d1", "Bob")
    out, skipped = await ku._ondemand_embed(
        [anchored, d1], embedding_client=_FakeEmbed(fail=True), user_id="u"
    )
    assert next(s for s in out if s.entity_id == "d1").embedding is None  # no crash


@pytest.mark.asyncio
async def test_ondemand_embed_then_cluster_matches_discovered():
    """Q1=b end-to-end (pure) — after on-demand embed, a discovered recurrence that
    lexical can't catch ('Al' vs 'Alice') clusters semantically with the anchored one."""
    anchored = _vseed("P1", "a1", "Alice", [1, 0, 0], model="bge-m3")
    discovered = _seed("P2", "a2", "Al")  # lexical: 'al' vs 'alice' → no match
    seeds, skipped = await ku._ondemand_embed(
        [anchored, discovered], embedding_client=_FakeEmbed(), user_id="u"
    )
    out = cluster_seeds(seeds, "semantic", embed_skipped=skipped)
    assert len(out["unification_clusters"]) == 1
    assert out["unification_clusters"][0]["method"] == "semantic"
    assert out["unify_embed_skipped"] == 0


# ── T2: disagreement detection ───────────────────────────────────────────


def _edge(src, tgt, predicate):
    return SimpleNamespace(source=src, target=tgt, predicate=predicate)


def test_disagreement_detected_across_books():
    """T2 gate — the SAME cross-book character asserting DIFFERENT predicates to the
    SAME (unified) target is surfaced as one disagreement (Alice LOVES Bob in A,
    Alice KILLS Bob in B)."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "a2", "Alice"),
             _seed("P1", "b1", "Bob"), _seed("P2", "b2", "Bob")]
    edges = [_edge("a1", "b1", "LOVES"), _edge("a2", "b2", "KILLS")]
    out = cluster_seeds(seeds, "by_name", edges=edges)

    assert len(out["unification_clusters"]) == 2  # Alice + Bob
    dis = out["disagreements"]
    assert len(dis) == 1
    d = dis[0]
    assert {d["predicate_a"], d["predicate_b"]} == {"LOVES", "KILLS"}
    assert {d["project_a"], d["project_b"]} == {"P1", "P2"}
    assert "target_cluster_id" in d
    alice_cid = next(
        c["cluster_id"] for c in out["unification_clusters"]
        if {m["entity_id"] for m in c["members"]} == {"a1", "a2"}
    )
    assert d["cluster_id"] == alice_cid


def test_agreement_not_flagged():
    """The same predicate to the same target across books is agreement, not a
    disagreement (it rides the bridge, no record)."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "a2", "Alice"),
             _seed("P1", "b1", "Bob"), _seed("P2", "b2", "Bob")]
    edges = [_edge("a1", "b1", "LOVES"), _edge("a2", "b2", "LOVES")]
    out = cluster_seeds(seeds, "by_name", edges=edges)
    assert out["disagreements"] == []


def test_no_disagreement_when_targets_not_unified():
    """A conflict needs the SAME (unified) target; edges to different, un-unified
    targets are not a disagreement (documented recall limit — target must unify too)."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "a2", "Alice"),
             _seed("P1", "x1", "Rome"), _seed("P2", "x2", "Paris")]
    edges = [_edge("a1", "x1", "VISITS"), _edge("a2", "x2", "BURNS")]
    out = cluster_seeds(seeds, "by_name", edges=edges)
    assert out["disagreements"] == []


def test_disagreements_empty_without_edges():
    """No edges supplied → no disagreements, but the key is always present when on."""
    seeds = [_seed("P1", "a1", "Alice"), _seed("P2", "a2", "Alice")]
    out = cluster_seeds(seeds, "by_name")
    assert out["disagreements"] == []
