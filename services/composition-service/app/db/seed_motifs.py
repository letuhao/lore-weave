"""W7 — system-tier motif seed packs (idempotent loader).

THE SYSTEM-WRITE CHOKEPOINT (audit B-2): this is the ONLY code path that writes a
system-tier motif (owner_user_id IS NULL). It is called exactly once from F0's
`run_migrations()` via the frozen `migrate._seed_motif_packs` hook (a soft import),
at service boot, after the schema + the built-in structure templates. No router /
MCP tool / worker calls it — so a both-NULL row can be born nowhere else.

Seed contract (00-RECONCILE §1):
  - D6  system rows use `visibility='unlisted'` so the both-NULL row satisfies the
        `motif_user_owned` CHECK (owner NULL ⇒ visibility <> 'private').
  - D4  rows seed with `embedding = NULL`, `embedding_model = ''`; W3 lazily
        back-fills the platform vector on first retrieval-touch (NOT here — the
        migrate tx must never wall boot on provider-registry, the C16 lesson).
  - D1  scheme `info_asymmetry` lands on BOTH the dedicated `info_asymmetry` JSONB
        column (the conformance judge reads it) and `annotations` (template-level
        props W5 reads on the motif).

Idempotency: every row gets a DETERMINISTIC uuid5 id from (code, language); the
INSERT is `ON CONFLICT (id) DO NOTHING`, so re-running migrate is a true no-op
(no double-seed across restarts). `motif_link` edges get a deterministic id too and
`ON CONFLICT (from_motif_id, to_motif_id, kind) DO NOTHING` on the schema UNIQUE.

`source='authored'` on every row (curated, never 'imported') — so the B-3
publish-strip trigger never fires on a seed row, and the examples are guaranteed
author-written (no source prose; the copyright guard, §6).
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import asyncpg

from app.db.models import Motif, MotifCreateArgs

logger = logging.getLogger(__name__)

# The pack files live next to this module's data dir (W7-owned, disjoint).
_PACK_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_motif_packs"

# The motif packs (each a JSON array of motif objects). links.json is loaded
# separately (it is edges, not motifs).
_MOTIF_PACKS = ("cultivation", "revenge", "intrigue", "hooks", "emotion_arcs")
_LINKS_PACK = "links"

# Fixed W7 namespace for deterministic uuid5 ids (any constant UUID). Changing this
# would re-key every seed row — do NOT change it once seeded in any environment.
_MOTIF_NS = uuid.UUID("6d0746f0-0000-5000-8000-000000000001")

# System tier: owner NULL, unlisted (D6), embedding NULL (D4), authored.
_SYSTEM_VISIBILITY = "unlisted"

_INSERT_MOTIF_SQL = """
INSERT INTO motif (
  id, owner_user_id, code, language, visibility, kind, category, name, summary,
  genre_tags, roles, beats, preconditions, effects, info_asymmetry, annotations,
  tension_target, emotion_target, examples, source, source_version
) VALUES (
  $1, NULL, $2, $3, $4, $5, $6, $7, $8,
  $9, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb,
  $16, $17, $18::jsonb, $19, $20
)
ON CONFLICT (id) DO NOTHING
"""

# Dev-only re-seed: update the curated content of an already-seeded SYSTEM AUTHORED
# row (never a user row, never a non-authored row). Used by reseed=True ONLY.
_RESEED_MOTIF_SQL = """
INSERT INTO motif (
  id, owner_user_id, code, language, visibility, kind, category, name, summary,
  genre_tags, roles, beats, preconditions, effects, info_asymmetry, annotations,
  tension_target, emotion_target, examples, source, source_version
) VALUES (
  $1, NULL, $2, $3, $4, $5, $6, $7, $8,
  $9, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb,
  $16, $17, $18::jsonb, $19, $20
)
ON CONFLICT (id) DO UPDATE SET
  kind = EXCLUDED.kind, category = EXCLUDED.category, name = EXCLUDED.name,
  summary = EXCLUDED.summary, genre_tags = EXCLUDED.genre_tags,
  roles = EXCLUDED.roles, beats = EXCLUDED.beats,
  preconditions = EXCLUDED.preconditions, effects = EXCLUDED.effects,
  info_asymmetry = EXCLUDED.info_asymmetry, annotations = EXCLUDED.annotations,
  tension_target = EXCLUDED.tension_target, emotion_target = EXCLUDED.emotion_target,
  examples = EXCLUDED.examples, source_version = EXCLUDED.source_version,
  updated_at = now()
WHERE motif.owner_user_id IS NULL AND motif.source = 'authored'
"""

_INSERT_LINK_SQL = """
INSERT INTO motif_link (id, from_motif_id, to_motif_id, kind, ord)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (from_motif_id, to_motif_id, kind) DO NOTHING
"""


def _motif_id(code: str, language: str) -> uuid.UUID:
    """Deterministic id from (code, language) — the schema's dedup/embed key. Same
    input → same id, so the seed is idempotent across restarts; an en and a vi row
    of the same code get distinct ids (no collision on uq_motif_system)."""
    return uuid.uuid5(_MOTIF_NS, f"motif|{language}|{code}")


def _link_id(from_code: str, to_code: str, kind: str, language: str) -> uuid.UUID:
    return uuid.uuid5(_MOTIF_NS, f"link|{language}|{from_code}|{to_code}|{kind}")


def _read_pack(name: str) -> list[dict[str, Any]]:
    path = _PACK_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"seed pack {name}.json must be a JSON array, got {type(data)}")
    return data


def load_motif_rows() -> list[dict[str, Any]]:
    """Load + VALIDATE every pack motif. Returns the raw dicts (id-less); raises on a
    schema-invalid row. Pure (no DB) so the unit tests reuse it.

    Each row is validated TWICE: against `MotifCreateArgs` (the strict write-arg model
    — validates roles/beats sub-shapes, tension 1..5, rejects extra keys) and as a
    `Motif` row model (the read shape) — so a pack row matches the F0 contract on both
    the write and read side. A system seed must NOT carry `owner_user_id` (tier is by
    OMISSION + the NULL default) nor `embedding*` (W3 owns the platform embed)."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pack in _MOTIF_PACKS:
        for raw in _read_pack(pack):
            code = raw.get("code", "")
            language = raw.get("language", "en")
            if "owner_user_id" in raw:
                raise ValueError(f"seed row {code!r} must not set owner_user_id (system tier is by omission)")
            for banned in ("embedding", "embedding_model", "embedding_dim", "id"):
                if banned in raw:
                    raise ValueError(f"seed row {code!r} must not set {banned!r} (loader-derived)")
            # Strict write-arg validation (the F0 contract guard). `source` /
            # `source_version` are seed/loader fields, NOT user write-args (they are
            # absent from the ForbidExtra MotifCreateArgs by design — a user-create
            # never stamps lineage), so strip them for the write-arg check.
            create_view = {k: v for k, v in raw.items() if k not in ("source", "source_version")}
            MotifCreateArgs.model_validate(create_view)
            # Row-model round-trip (read shape) with the loader-stamped system fields.
            Motif.model_validate(
                {
                    **raw,
                    "id": _motif_id(code, language),
                    "owner_user_id": None,
                    "visibility": _SYSTEM_VISIBILITY,
                    "source": raw.get("source", "authored"),
                }
            )
            key = (code, language)
            if key in seen:
                raise ValueError(f"duplicate seed (code, language): {key}")
            seen.add(key)
            rows.append(raw)
    return rows


def load_link_edges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Load the precedes/composed_of edges from links.json and resolve from/to codes
    to seeded ids. Raises on a dangling edge (a code not in the loaded packs) or a
    composed_of parent that is not a `kind='pattern'` motif. Pure (no DB)."""
    by_code: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_code[r["code"]] = r
    edges: list[dict[str, Any]] = []
    for e in _read_pack(_LINKS_PACK):
        frm, to, kind = e["from_code"], e["to_code"], e["kind"]
        if frm not in by_code:
            raise ValueError(f"link from_code {frm!r} not a seeded motif")
        if to not in by_code:
            raise ValueError(f"link to_code {to!r} not a seeded motif")
        if kind not in ("composed_of", "precedes", "variant_of"):
            raise ValueError(f"link kind {kind!r} invalid")
        if kind == "composed_of" and by_code[frm].get("kind") != "pattern":
            raise ValueError(f"composed_of parent {frm!r} must be kind='pattern'")
        # All seeded motifs are 'en' for the first cut (D1); resolve in that language.
        lang_from = by_code[frm].get("language", "en")
        lang_to = by_code[to].get("language", "en")
        edges.append(
            {
                "id": _link_id(frm, to, kind, lang_from),
                "from_id": _motif_id(frm, lang_from),
                "to_id": _motif_id(to, lang_to),
                "kind": kind,
                "ord": e.get("ord"),
            }
        )
    return edges


def _j(value: Any) -> str:
    return json.dumps(value if value is not None else None)


async def seed_motif_packs(conn: asyncpg.Connection, *, reseed: bool = False) -> int:
    """Idempotently seed the system-tier motif library + its link edges.

    Called once from `migrate.run_migrations` (production boot always passes
    reseed=False). `reseed=True` is a DEV-ONLY path (a CLI / re-author loop) that
    UPDATEs already-seeded SYSTEM AUTHORED rows in place (never a user row) so an
    edited pack is re-applied; production never uses it.

    Returns the number of system-tier motif rows present after seeding (for the
    migrate log line)."""
    rows = load_motif_rows()
    edges = load_link_edges(rows)
    insert_sql = _RESEED_MOTIF_SQL if reseed else _INSERT_MOTIF_SQL

    async with conn.transaction():
        for raw in rows:
            code = raw["code"]
            language = raw.get("language", "en")
            await conn.execute(
                insert_sql,
                _motif_id(code, language),                       # $1 id (deterministic)
                code,                                            # $2 code
                language,                                        # $3 language
                _SYSTEM_VISIBILITY,                              # $4 visibility (D6)
                raw.get("kind", "sequence"),                     # $5 kind
                raw.get("category"),                             # $6 category
                raw["name"],                                     # $7 name
                raw.get("summary", ""),                          # $8 summary
                list(raw.get("genre_tags", [])),                 # $9 genre_tags TEXT[]
                _j(raw.get("roles", [])),                         # $10 roles
                _j(raw.get("beats", [])),                         # $11 beats
                _j(raw.get("preconditions", [])),                # $12 preconditions
                _j(raw.get("effects", [])),                       # $13 effects
                _j(raw.get("info_asymmetry")),                   # $14 info_asymmetry (NULL if absent)
                _j(raw.get("annotations", {})),                  # $15 annotations (D1)
                raw.get("tension_target"),                       # $16 tension_target
                raw.get("emotion_target"),                       # $17 emotion_target
                _j(raw.get("examples", [])),                     # $18 examples
                raw.get("source", "authored"),                   # $19 source (authored)
                raw.get("source_version"),                       # $20 source_version
            )
            # owner_user_id / embedding / embedding_model are NOT passed → NULL / '' (D4).
        for e in edges:
            await conn.execute(
                _INSERT_LINK_SQL, e["id"], e["from_id"], e["to_id"], e["kind"], e["ord"],
            )

    n = await conn.fetchval("SELECT count(*) FROM motif WHERE owner_user_id IS NULL")
    logger.info("composition migrate: %d system motifs + %d link edges seeded", n, len(edges))
    return n
