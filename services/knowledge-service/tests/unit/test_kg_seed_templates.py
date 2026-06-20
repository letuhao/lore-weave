"""L1 unit tests — the seeded System graph-schema templates match the S0 locks.

No DB: validates the in-memory template definitions (the data the seed writes)
against the spec §4 + the S0 decisions (M1 per-kind strength, Q2 free edges,
Q3 fact-types). Catches drift between the locked design and the seed content.
"""

from __future__ import annotations

from app.db.seed_graph_schemas import (
    _GENERAL,
    _TEMPLATES,
    _XIANXIA_HAREM,
    _content_hash,
)


def _kinds(tpl):
    return {code: strength for code, strength in tpl["node_kinds"]}


def _edge_codes(tpl):
    return {e["code"] for e in tpl["edge_types"]}


# ── general (legacy ontology / additive-first fallback) ───────────────
def test_general_is_free_edge_and_legacy_kinds():
    assert _GENERAL["code"] == "general"
    assert _GENERAL["allow_free_edges"] is True  # Q2
    assert _edge_codes(_GENERAL) == set()  # free-string predicates, no closed vocab
    assert set(_kinds(_GENERAL)) == {"person", "place", "organization", "artifact", "concept", "other"}
    # general must NEVER gate an adopt → every kind optional.
    assert all(s == "optional" for s in _kinds(_GENERAL).values())


def test_general_fact_types_are_the_legacy_sdk_set():
    codes = {c for c, _ in _GENERAL["fact_types"]}
    assert codes == {"description", "attribute", "negation", "temporal", "causal"}


# ── xianxia-harem (VCTĐ template) ─────────────────────────────────────
def test_xianxia_node_kind_strength_split_matches_M1_lock():
    kinds = _kinds(_XIANXIA_HAREM)
    required = {k for k, s in kinds.items() if s == "required"}
    optional = {k for k, s in kinds.items() if s == "optional"}
    assert required == {"character", "organization", "location", "concept", "technique"}
    assert optional == {"item", "event", "relationship"}


def test_xianxia_fact_types_are_the_nine_locked():
    codes = {c for c, _ in _XIANXIA_HAREM["fact_types"]}
    assert codes == {
        "realm_change", "allegiance_shift", "motivation_shift", "death", "breakthrough",
        "battle_outcome", "betrayal", "bloodline_awakening", "oath_or_vow",
    }


def test_xianxia_drive_vocab_is_closed_with_16_values():
    drive = next(v for v in _XIANXIA_HAREM["vocab_sets"] if v["code"] == "drive")
    assert drive["closed"] is True
    codes = {c for c, _, _ in drive["values"]}
    assert len(codes) == 16
    assert {"revenge", "seek_dao", "transcendence", "godhood", "freedom"} <= codes
    # every drive carries the {axis, has_target, archetype} metadata (spec §3.4)
    for _, _, meta in drive["values"]:
        assert {"axis", "has_target", "archetype"} <= set(meta)


def test_xianxia_has_core_relationship_edges():
    codes = _edge_codes(_XIANXIA_HAREM)
    for required_edge in ("MASTER_OF", "LOVER_OF", "KILLED", "BETRAYED", "MEMBER_OF", "PURSUES"):
        assert required_edge in codes


def test_xianxia_temporal_and_cardinality_flags():
    by_code = {e["code"]: e for e in _XIANXIA_HAREM["edge_types"]}
    # revenge axis + bonds are temporal; kinship is invariant.
    assert by_code["LOVER_OF"]["temporal"] is True
    assert by_code["KILLED"]["temporal"] is True
    assert by_code["MASTER_OF"]["temporal"] is False
    # PURSUES (the motive map) is multi_active — multiple drives, one dominant.
    assert by_code["PURSUES"]["cardinality"] == "multi_active"
    # temporal edges require provenance (mirror flag).
    assert by_code["KILLED"]["provenance_required"] is True


def test_edge_node_kinds_reference_declared_kinds():
    """Every edge's source/target kinds must be a declared node-kind of the template."""
    declared = set(_kinds(_XIANXIA_HAREM))
    for e in _XIANXIA_HAREM["edge_types"]:
        for k in e["source_node_kinds"] + e["target_node_kinds"]:
            assert k in declared, f"{e['code']} references undeclared kind {k}"


# ── seed mechanics ────────────────────────────────────────────────────
def test_content_hash_is_deterministic_and_distinct():
    assert _content_hash(_GENERAL) == _content_hash(_GENERAL)
    assert _content_hash(_GENERAL) != _content_hash(_XIANXIA_HAREM)


def test_both_templates_present():
    assert {t["code"] for t in _TEMPLATES} == {"general", "xianxia-harem"}
