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

Idempotency: every row gets a DETERMINISTIC uuid5 id from its `code`; the INSERT
upserts on that id, so re-running migrate is a true no-op (no double-seed across
restarts). `motif_link` edges get a deterministic id too and
`ON CONFLICT (from_motif_id, to_motif_id, kind) DO NOTHING` on the schema UNIQUE.

MOTIF-I18N: a motif is seeded ONCE, in English, and its other languages are
`motif_translation` rows loaded from `seed_motif_packs/translations/<lang>/`.
Translations carry no structure, so they can only re-word a motif, never reshape it.

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
from app.motif_i18n import (
    extract_translatable,
    parse_translation_entry,
    translatable_hash,
)

logger = logging.getLogger(__name__)

# The pack files ship INSIDE the app package (app/db/seed_motif_packs/) so the
# production Docker image — which COPYs only app/, not scripts/ — has the seed data
# at runtime. (R-NODE-P1 caught the original scripts/ location FileNotFound-ing at
# container boot; runtime-required data belongs with the code, not in the dev/CI
# scripts/ dir.)
_PACK_DIR = Path(__file__).resolve().parent / "seed_motif_packs"

# The motif packs (each a JSON array of motif objects) — the SOURCE, authored in
# English. links.json is loaded separately (it is edges, not motifs).
#
# MOTIF-I18N (2026-07-29): there used to be a parallel `*_vi` pack per genre, holding
# a FULL second copy of every motif with `language:"vi"` — a distinct row, a distinct
# id, a distinct vector, a distinct set of link edges. That made "the same motif in
# two languages" two unrelated rows, and an English book's plan pass could and did
# receive the Vietnamese one. The Vietnamese wording now lives in
# `seed_motif_packs/translations/vi/<pack>.json` as a TRANSLATION of the English
# source — same motif, same id, one vector. Its hand-written literary Vietnamese is
# preserved verbatim (source='authored'), never re-machine-translated.
#
# 2026-07-29 GENRE BREADTH (`romance` … `survival`): the first five packs left the library
# covering xianxia/cultivation, revenge, court-intrigue + the genre-agnostic connective
# kinds — and NOTHING else, so a non-cultivation premise got told, in the selector's own
# words, that "the catalog consists entirely of cultivation-genre tropes". Note the packs
# below are tagged generously but do NOT lean on `genre_tags` to be found: measured live,
# 286 of 292 plan runs carry `genre_tags: []` and every active book carries none, so
# `_genre_overlap` is 0.0 in practice and the real matcher is cosine over
# `motif_summary_text` = name + summary + beat labels + beat intents. Those four fields
# are therefore written to be discoverable FROM A PREMISE, not merely labelled correctly.
_MOTIF_PACKS = (
    "cultivation", "revenge", "intrigue", "hooks", "emotion_arcs",
    "romance", "mystery", "rebirth", "wuxia", "survival",
)
_LINKS_PACK = "links"

# Every platform motif is authored in English; `original_language` is not a per-pack
# choice. A pack row may not override it (validated in load_motif_rows).
_SOURCE_LANGUAGE = "en"

# translations/<lang>/<pack>.json — {code: entry}, translatable leaves only.
# See app.motif_i18n for the entry shape and its validator.
_TRANSLATION_DIR = _PACK_DIR / "translations"

# Languages whose translations are HUMAN-written and must never be overwritten by a
# machine re-translation. Everything else under translations/ is machine output from
# scripts/motif_translate.py (still committed, still platform-official).
_AUTHORED_LANGUAGES = frozenset({"vi"})

# Fixed W7 namespace for deterministic uuid5 ids (any constant UUID). Changing this
# would re-key every seed row — do NOT change it once seeded in any environment.
_MOTIF_NS = uuid.UUID("6d0746f0-0000-5000-8000-000000000001")

# System tier: owner NULL, unlisted (D6), embedding NULL (D4), authored.
_SYSTEM_VISIBILITY = "unlisted"

# The BOOT path. It used to be `ON CONFLICT (id) DO NOTHING`, which made a pack edit
# UNDEPLOYABLE: a new `code` inserts fine, but an edit to an EXISTING row is silently dropped
# in every environment that has already seeded it — for good. Proven against the live dev DB
# by writing an "old" summary and running this exact call: the old text survived. So the
# 2026-07-29 content-quality work (rewritten mystery/rebirth summaries, repaired
# effect→precondition handshakes) would have reached nobody, while the JSON in git said
# otherwise — the worst shape of bug this repo keeps re-learning.
#
# Now the update is gated on `source_version` INCREASING, which is the field's existing
# meaning: `motif_sync` already compares an adopted copy's pinned `source_version` against
# upstream to report drift, so bumping it is exactly the "the base changed" signal it is for.
# **Edit a pack row ⇒ bump its `source_version`**, or the edit does not ship.
#
# The scope clause is what keeps this safe: it can only ever touch a SYSTEM (`owner_user_id
# IS NULL`) AUTHORED row. A user's motif — including an adopted copy of one of these — is
# untouchable by the seeder. Content only; `source` and identity are never rewritten. The
# stored vector goes stale on update, which the retrieve path now detects on its own via
# `embedded_summary_hash` (see `_text_unchanged`), so the two fixes compose.
_INSERT_MOTIF_SQL = """
INSERT INTO motif (
  id, owner_user_id, code, original_language, visibility, kind, category, name, summary,
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
WHERE motif.owner_user_id IS NULL
  AND motif.source = 'authored'
  AND coalesce(motif.source_version, 0) < coalesce(EXCLUDED.source_version, 0)
"""

# Dev-only re-seed: update the curated content of an already-seeded SYSTEM AUTHORED
# row (never a user row, never a non-authored row). Used by reseed=True ONLY.
_RESEED_MOTIF_SQL = """
INSERT INTO motif (
  id, owner_user_id, code, original_language, visibility, kind, category, name, summary,
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

# Platform translations. The conflict rule is the one the whole i18n design hangs on:
# a HUMAN-written translation is never clobbered by machine output. `authored` may
# overwrite anything (a person corrected it); `machine` may only overwrite `machine`.
# Without this, re-running scripts/motif_translate.py over `vi` would silently replace
# hand-written literary Vietnamese with model output — irreversibly, since the packs
# would then be the only copy left.
_INSERT_TRANSLATION_SQL = """
INSERT INTO motif_translation (
  motif_id, language_code, name, summary, emotion_target,
  roles, beats, preconditions, effects, examples,
  source_content_hash, source, translated_by
) VALUES (
  $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb, $11, $12, 'seed-pack'
)
ON CONFLICT (motif_id, language_code) DO UPDATE SET
  name = EXCLUDED.name, summary = EXCLUDED.summary,
  emotion_target = EXCLUDED.emotion_target,
  roles = EXCLUDED.roles, beats = EXCLUDED.beats,
  preconditions = EXCLUDED.preconditions, effects = EXCLUDED.effects,
  examples = EXCLUDED.examples,
  source_content_hash = EXCLUDED.source_content_hash,
  source = EXCLUDED.source, translated_by = EXCLUDED.translated_by,
  updated_at = now()
WHERE motif_translation.source <> 'authored' OR EXCLUDED.source = 'authored'
"""


def _motif_id(code: str) -> uuid.UUID:
    """Deterministic id for a system motif. Same code → same id, so the seed is a true
    no-op across restarts.

    The formula still hashes the literal `en` segment even though language left the
    identity key. That is DELIBERATE and must not be "cleaned up": every already-seeded
    English row in every environment carries `uuid5(ns, "motif|en|<code>")` as its
    primary key. Dropping the segment would mint a second id per code and the seeder
    would insert a duplicate of all 84 — caught only by uq_motif_system, at boot, after
    the migration had already run.
    """
    return uuid.uuid5(_MOTIF_NS, f"motif|{_SOURCE_LANGUAGE}|{code}")


def _link_id(from_code: str, to_code: str, kind: str) -> uuid.UUID:
    """Same reasoning as `_motif_id` — the `en` segment is load-bearing history."""
    return uuid.uuid5(_MOTIF_NS, f"link|{_SOURCE_LANGUAGE}|{from_code}|{to_code}|{kind}")


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
    seen: set[str] = set()
    for pack in _MOTIF_PACKS:
        for raw in _read_pack(pack):
            code = raw.get("code", "")
            if raw.get("language", _SOURCE_LANGUAGE) != _SOURCE_LANGUAGE:
                raise ValueError(
                    f"seed row {code!r} sets language={raw['language']!r}: platform motifs are "
                    f"authored in {_SOURCE_LANGUAGE!r}. Other languages go in "
                    f"seed_motif_packs/translations/<lang>/{pack}.json, not a parallel pack."
                )
            if "owner_user_id" in raw:
                raise ValueError(f"seed row {code!r} must not set owner_user_id (system tier is by omission)")
            for banned in ("embedding", "embedding_model", "embedding_dim", "id"):
                if banned in raw:
                    raise ValueError(f"seed row {code!r} must not set {banned!r} (loader-derived)")
            # Strict write-arg validation (the F0 contract guard). `source` /
            # `source_version` are seed/loader fields, NOT user write-args (they are
            # absent from the ForbidExtra MotifCreateArgs by design — a user-create
            # never stamps lineage), so strip them for the write-arg check.
            create_view = {
                k: v for k, v in raw.items()
                if k not in ("source", "source_version", "language")
            }
            MotifCreateArgs.model_validate(create_view)
            # Row-model round-trip (read shape) with the loader-stamped system fields.
            Motif.model_validate(
                {
                    **{k: v for k, v in raw.items() if k != "language"},
                    "id": _motif_id(code),
                    "owner_user_id": None,
                    "original_language": _SOURCE_LANGUAGE,
                    "visibility": _SYSTEM_VISIBILITY,
                    "source": raw.get("source", "authored"),
                }
            )
            if code in seen:
                raise ValueError(f"duplicate seed code: {code!r}")
            seen.add(code)
            rows.append(raw)
    return rows


def load_translation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Load + VALIDATE every translations/<lang>/<pack>.json. Pure (no DB).

    A translation file may only re-word motifs that exist in the source packs, and may
    only use role/beat keys the source motif actually has — `parse_translation_entry`
    raises otherwise. Both checks matter: an unknown CODE means the file is stale
    against a renamed motif, and an unknown KEY means the wording would silently fail
    to merge while the file on disk still looks complete. Neither is tolerated,
    because both fail invisibly at runtime.

    Missing translations are NOT an error — a language is allowed to be partial, and
    resolution falls back to the English source per leaf.
    """
    by_code = {r["code"]: r for r in rows}
    payload_by_code = {code: extract_translatable(r) for code, r in by_code.items()}
    out: list[dict[str, Any]] = []
    if not _TRANSLATION_DIR.is_dir():
        return out
    for lang_dir in sorted(p for p in _TRANSLATION_DIR.iterdir() if p.is_dir()):
        language = lang_dir.name
        for path in sorted(lang_dir.glob("*.json")):
            with path.open(encoding="utf-8") as fh:
                doc = json.load(fh)
            if not isinstance(doc, dict):
                raise ValueError(
                    f"translation file {language}/{path.name} must be a JSON object "
                    f"keyed by motif code, got {type(doc).__name__}"
                )
            for code, entry in doc.items():
                if code not in by_code:
                    raise ValueError(
                        f"translation {language}/{path.name}: code {code!r} is not a seeded "
                        f"motif (renamed or removed upstream?)"
                    )
                payload = parse_translation_entry(
                    entry, payload_by_code[code], where=f"{language}/{path.name}:{code}"
                )
                out.append(
                    {
                        "motif_id": _motif_id(code),
                        "language_code": language,
                        "payload": payload,
                        # The source text this translation was made from. A later edit to
                        # the English motif changes this hash, which marks the translation
                        # stale on read instead of silently serving mismatched wording.
                        "source_content_hash": translatable_hash(payload_by_code[code]),
                        "source": "authored" if language in _AUTHORED_LANGUAGES else "machine",
                    }
                )
    return out


def load_link_edges(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Load the precedes/composed_of edges from links.json and resolve from/to codes
    to seeded ids. Raises on a dangling edge (a code not in the loaded packs) or a
    composed_of parent that is not a `kind='pattern'` motif. Pure (no DB).

    MOTIF-I18N: this used to emit one edge PER language, wiring a parallel `vi` copy of
    the whole graph (55 duplicate edges for 55 real ones). With one row per motif there
    is one graph — a motif's relationships are a property of the motif, not of the
    language you happen to read it in."""
    kind_by_code = {r["code"]: r.get("kind", "sequence") for r in rows}
    edges: list[dict[str, Any]] = []
    for e in _read_pack(_LINKS_PACK):
        frm, to, kind = e["from_code"], e["to_code"], e["kind"]
        if frm not in kind_by_code:
            raise ValueError(f"link from_code {frm!r} not a seeded motif")
        if to not in kind_by_code:
            raise ValueError(f"link to_code {to!r} not a seeded motif")
        if kind not in ("composed_of", "precedes", "variant_of"):
            raise ValueError(f"link kind {kind!r} invalid")
        if kind == "composed_of" and kind_by_code[frm] != "pattern":
            raise ValueError(f"composed_of parent {frm!r} must be kind='pattern'")
        edges.append(
            {
                "id": _link_id(frm, to, kind),
                "from_id": _motif_id(frm),
                "to_id": _motif_id(to),
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
    translations = load_translation_rows(rows)
    insert_sql = _RESEED_MOTIF_SQL if reseed else _INSERT_MOTIF_SQL

    async with conn.transaction():
        for raw in rows:
            code = raw["code"]
            await conn.execute(
                insert_sql,
                _motif_id(code),                                 # $1 id (deterministic)
                code,                                            # $2 code
                _SOURCE_LANGUAGE,                                # $3 original_language
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
        for t in translations:
            p = t["payload"]
            await conn.execute(
                _INSERT_TRANSLATION_SQL,
                t["motif_id"], t["language_code"],
                p["name"], p["summary"], p["emotion_target"] or None,
                _j(p["roles"]), _j(p["beats"]), _j(p["preconditions"]),
                _j(p["effects"]), _j(p["examples"]),
                t["source_content_hash"], t["source"],
            )

    n = await conn.fetchval("SELECT count(*) FROM motif WHERE owner_user_id IS NULL")
    langs = sorted({t["language_code"] for t in translations})
    logger.info(
        "composition migrate: %d system motifs + %d link edges + %d translations "
        "across %d language(s) %s seeded",
        n, len(edges), len(translations), len(langs), langs,
    )
    return n
