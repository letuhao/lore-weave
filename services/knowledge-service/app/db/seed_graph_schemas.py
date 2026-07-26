"""Seed the System-tier KG graph-schema templates (epic 2026-06-20, lane L1).

Idempotent, hash-gated: run on every startup right after run_migrations. Each
system template carries a `content_hash`; we re-seed a template only when it is
absent or its hash changed (template evolved), bumping `schema_version` and
replacing its children in one transaction. System rows are tier-isolated — re-
seeding never touches user/project copies that adopted from them.

Two templates:
  * `general`       — reproduces today's generic extraction ontology (6 entity
                      kinds, the 5 SDK fact types, free-string edges). The safe
                      fallback: a project that never adopts resolves to this →
                      zero behavior change (additive-first).
  * `xianxia-harem` — a genre template for cultivation + harem novels (spec §4):
                      curated edge vocab, the closed 16-value `drive` set, 9
                      narrative fact types, and per-kind adopt strength (M1,
                      LOCKED S0).

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §4.
"""

from __future__ import annotations

import hashlib
import json
import logging

import asyncpg

logger = logging.getLogger(__name__)


# ── template definitions (data, not code) ────────────────────────────
# node_kinds: (kind_code, strength). edge_types: dict per spec §3.2.
# A kind is `required` (gates adopt) or `optional` (warn + triage), M1.

_GENERAL = {
    "code": "general",
    "name": "General (legacy ontology)",
    "description": (
        "Reproduces the original generic extraction ontology — the additive-first "
        "safety net. Projects that never adopt a template resolve here, so behavior "
        "is unchanged. Free-string edges (allow_free_edges)."
    ),
    "allow_free_edges": True,
    # All optional — `general` must never block an adopt.
    "node_kinds": [
        ("person", "optional"),
        ("place", "optional"),
        ("organization", "optional"),
        ("artifact", "optional"),
        ("concept", "optional"),
        ("other", "optional"),
    ],
    "edge_types": [],  # free-string predicates; no closed vocab (legacy behavior)
    "fact_types": [
        ("description", "Description"),
        ("attribute", "Attribute"),
        ("negation", "Negation"),
        ("temporal", "Temporal"),
        ("causal", "Causal"),
    ],
    "vocab_sets": [],
}


def _e(code, label, src, tgt, *, directed=True, temporal=False, cardinality="multi_active"):
    """Compact edge-type builder. provenance_required mirrors `temporal`."""
    return {
        "code": code,
        "label": label,
        "directed": directed,
        "source_node_kinds": src,
        "target_node_kinds": tgt,
        "temporal": temporal,
        "provenance_required": temporal,
        "cardinality": cardinality,
        "description": "",
    }


_C = ["character"]

_XIANXIA_HAREM = {
    "code": "xianxia-harem",
    "name": "Xianxia · Harem",
    "description": (
        "Genre template for cultivation + harem novels: curated relationship / "
        "cultivation / political edge vocab, the closed 16-value drive vocab, and "
        "narrative state-delta fact types. Anchors character-centric node kinds."
    ),
    "allow_free_edges": True,  # Q2 default; tighten per-project as opt-in
    "node_kinds": [
        # required = structural identity kinds (gate adopt if glossary missing)
        ("character", "required"),
        ("organization", "required"),
        ("location", "required"),
        ("concept", "required"),
        ("technique", "required"),
        # optional = enrichment kinds (warn + triage)
        ("item", "optional"),
        ("event", "optional"),
        ("relationship", "optional"),
    ],
    "edge_types": [
        # Character → Character (invariant kinship/mentorship)
        _e("MASTER_OF", "master of", _C, _C),
        _e("DISCIPLE_OF", "disciple of", _C, _C),
        _e("FAMILY_OF", "family of", _C, _C, directed=False),
        # Character → Character (temporal bonds — the harem/relationship axis)
        _e("LOVER_OF", "lover of", _C, _C, directed=False, temporal=True),
        _e("BETROTHED_TO", "betrothed to", _C, _C, directed=False, temporal=True),
        _e("DAO_COMPANION_OF", "dao companion of", _C, _C, directed=False, temporal=True),
        _e("RIVAL_OF", "rival of", _C, _C, directed=False, temporal=True),
        _e("ENEMY_OF", "enemy of", _C, _C, directed=False, temporal=True),
        _e("ALLY_OF", "ally of", _C, _C, directed=False, temporal=True),
        # Character → Character (temporal — the revenge axis; high provenance)
        _e("KILLED", "killed", _C, _C, temporal=True),
        _e("BETRAYED", "betrayed", _C, _C, temporal=True),
        _e("SAVED", "saved", _C, _C, temporal=True),
        # Character → other
        _e("MEMBER_OF", "member of", _C, ["organization"], temporal=True),
        _e("COMPREHENDS", "comprehends", _C, ["concept"]),
        _e("PRACTICES", "practices", _C, ["technique"]),
        _e("WIELDS", "wields", _C, ["item"]),
        _e("PARTICIPATED_IN", "participated in", _C, ["event"]),
        _e("FROM", "from", _C, ["location"]),
        # the motive map — multiple drives, one dominant (multi_active)
        _e("PURSUES", "pursues", _C, ["concept"], temporal=True, cardinality="multi_active"),
        # Organization / Location
        _e("SUBORDINATE_OF", "subordinate of", ["organization"], ["organization"]),
        _e("ALLIED_WITH", "allied with", ["organization"], ["organization"], directed=False, temporal=True),
        _e("AT_WAR_WITH", "at war with", ["organization"], ["organization"], directed=False, temporal=True),
        _e("PART_OF", "part of", ["location"], ["location"]),
        # Reified relationship node → its participants
        _e("INVOLVES", "involves", ["relationship"], _C),
    ],
    "fact_types": [
        ("realm_change", "Realm change"),
        ("allegiance_shift", "Allegiance shift"),
        ("motivation_shift", "Motivation shift"),
        ("death", "Death"),
        ("breakthrough", "Breakthrough"),
        ("battle_outcome", "Battle outcome"),
        ("betrayal", "Betrayal"),
        ("bloodline_awakening", "Bloodline awakening"),
        ("oath_or_vow", "Oath / vow"),
    ],
    "vocab_sets": [
        {
            "code": "drive",
            "label": "Drive",
            "description": "The character's motivating drive (closed set; extractor assigns, never coins).",
            "closed": True,
            "values": [
                ("godhood", "Godhood", {"axis": "ascension", "has_target": False, "archetype": "ambition"}),
                ("immortality", "Immortality", {"axis": "ascension", "has_target": False, "archetype": "survival"}),
                ("seek_dao", "Seek the Dao", {"axis": "ascension", "has_target": False, "archetype": "enlightenment"}),
                ("seize_treasure", "Seize treasure", {"axis": "acquisition", "has_target": True, "archetype": "greed"}),
                ("revenge", "Revenge", {"axis": "conflict", "has_target": True, "archetype": "vengeance"}),
                ("protect", "Protect", {"axis": "bond", "has_target": True, "archetype": "guardian"}),
                ("love", "Love", {"axis": "bond", "has_target": True, "archetype": "romance"}),
                ("restore_clan", "Restore clan", {"axis": "legacy", "has_target": True, "archetype": "restoration"}),
                ("domination", "Domination", {"axis": "power", "has_target": False, "archetype": "tyranny"}),
                ("uncover_truth", "Uncover truth", {"axis": "knowledge", "has_target": False, "archetype": "seeker"}),
                ("transcendence", "Transcendence", {"axis": "ascension", "has_target": False, "archetype": "enlightenment"}),
                ("usurp_heaven", "Usurp heaven", {"axis": "power", "has_target": True, "archetype": "rebellion"}),
                ("survival", "Survival", {"axis": "survival", "has_target": False, "archetype": "survival"}),
                ("hedonism", "Hedonism", {"axis": "indulgence", "has_target": False, "archetype": "pleasure"}),
                ("bloodlust", "Bloodlust", {"axis": "conflict", "has_target": False, "archetype": "violence"}),
                ("freedom", "Freedom", {"axis": "liberty", "has_target": False, "archetype": "liberation"}),
            ],
        },
    ],
}

_TEMPLATES = [_GENERAL, _XIANXIA_HAREM]


def _content_hash(tpl: dict) -> str:
    """Stable hash of a template's semantic surface (drives Sync + re-seed gate)."""
    return hashlib.sha256(json.dumps(tpl, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# Advisory-lock namespace for system-template seeding. Concurrent replicas at
# cold start would otherwise both SELECT-miss then INSERT → unique violation on
# idx_kg_graph_schemas_scope_code → a crashed startup (review-impl HIGH). Each
# template serializes on (this ns, hashtext(code)) for the txn duration.
_SEED_LOCK_NS = 0x4B47  # 'KG'


async def _seed_one(conn: asyncpg.Connection, tpl: dict) -> str:
    """Insert/update one system template + children in a transaction. Returns action.

    The existence check runs INSIDE the txn, after a per-template advisory lock,
    so two replicas racing on an empty table serialize: the loser blocks, then
    sees the row + matching hash → skip (no unique violation, no crash).
    """
    chash = _content_hash(tpl)
    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock($1, hashtext($2))", _SEED_LOCK_NS, tpl["code"]
        )
        existing = await conn.fetchrow(
            """
            SELECT schema_id, content_hash, schema_version
            FROM kg_graph_schemas
            WHERE scope = 'system' AND scope_id IS NULL AND code = $1
            """,
            tpl["code"],
        )
        if existing and existing["content_hash"] == chash:
            return "skip"

        if existing:
            schema_id = existing["schema_id"]
            await conn.execute(
                """
                UPDATE kg_graph_schemas
                SET name = $2, description = $3, allow_free_edges = $4,
                    content_hash = $5, schema_version = schema_version + 1,
                    updated_at = now()
                WHERE schema_id = $1
                """,
                schema_id, tpl["name"], tpl["description"], tpl["allow_free_edges"], chash,
            )
            # Replace children (cascade drops vocab_values + below).
            await conn.execute("DELETE FROM kg_edge_types WHERE schema_id = $1", schema_id)
            await conn.execute("DELETE FROM kg_fact_types WHERE schema_id = $1", schema_id)
            await conn.execute("DELETE FROM kg_schema_node_kinds WHERE schema_id = $1", schema_id)
            await conn.execute("DELETE FROM kg_vocab_sets WHERE schema_id = $1", schema_id)
            action = "update"
        else:
            schema_id = await conn.fetchval(
                """
                INSERT INTO kg_graph_schemas
                  (scope, scope_id, code, name, description, allow_free_edges, content_hash)
                VALUES ('system', NULL, $1, $2, $3, $4, $5)
                RETURNING schema_id
                """,
                tpl["code"], tpl["name"], tpl["description"], tpl["allow_free_edges"], chash,
            )
            action = "insert"

        for code, strength in tpl["node_kinds"]:
            await conn.execute(
                "INSERT INTO kg_schema_node_kinds (schema_id, kind_code, strength) VALUES ($1, $2, $3)",
                schema_id, code, strength,
            )
        for e in tpl["edge_types"]:
            await conn.execute(
                """
                INSERT INTO kg_edge_types
                  (schema_id, code, label, directed, source_node_kinds, target_node_kinds,
                   temporal, provenance_required, cardinality, description)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                schema_id, e["code"], e["label"], e["directed"],
                e["source_node_kinds"], e["target_node_kinds"],
                e["temporal"], e["provenance_required"], e["cardinality"], e["description"],
            )
        for code, label in tpl["fact_types"]:
            await conn.execute(
                "INSERT INTO kg_fact_types (schema_id, code, label) VALUES ($1, $2, $3)",
                schema_id, code, label,
            )
        for vs in tpl["vocab_sets"]:
            vocab_set_id = await conn.fetchval(
                """
                INSERT INTO kg_vocab_sets (schema_id, code, label, description, closed)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING vocab_set_id
                """,
                schema_id, vs["code"], vs["label"], vs["description"], vs["closed"],
            )
            for vcode, vlabel, vmeta in vs["values"]:
                await conn.execute(
                    "INSERT INTO kg_vocab_values (vocab_set_id, code, label, metadata) VALUES ($1, $2, $3, $4)",
                    vocab_set_id, vcode, vlabel, json.dumps(vmeta),
                )
    return action


async def seed_system_graph_schemas(pool: asyncpg.Pool) -> dict[str, str]:
    """Seed both system templates. Idempotent. Returns {code: action} for logging."""
    results: dict[str, str] = {}
    async with pool.acquire() as conn:
        for tpl in _TEMPLATES:
            results[tpl["code"]] = await _seed_one(conn, tpl)
    changed = {k: v for k, v in results.items() if v != "skip"}
    if changed:
        logger.info("KG ontology seed: %s", changed)
    return results
