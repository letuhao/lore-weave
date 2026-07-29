"""Motif i18n collapse — marker-gated, one-time (`motif_i18n_v1`).

Before: `language` sat inside every motif identity key, so "the same motif in two
languages" was two unrelated rows — 168 system rows for 84 motifs, duplicated
vectors, duplicated link edges, and a measured wrong-language leak into an English
book's scene prompt. See docs/specs/2026-07-29-motif-i18n.md.

After: one row per (tier, code) in its `original_language`; every other language is
a `motif_translation` row resolved with fallback.

Execution shape mirrors `package_rekey` — pre-flight that FAILS LOUD rather than
guessing, then the data move, then the index reshape, all inside one transaction so
a crash re-runs cleanly:

  M0 pre-flight  · a duplicate (code) group in a USER/BOOK tier is NOT auto-merged.
                   Two same-code rows a user authored in two languages may be two
                   different motifs, not translations of each other — only a human
                   can tell. Boot fails with the offending rows named.
                 · a link edge on a losing row that has no counterpart on the keeper
                   would be DESTROYED by the cascade. Verified, never assumed.
  M1 collapse    · keeper = the 'en' row (the platform source language); the losers'
                   text becomes `motif_translation` rows marked source='authored'
                   — the hand-written vi packs are literary Vietnamese and must
                   never be treated as machine output a re-run may overwrite.
                 · motif_application repointed off the losers (measured 0 in dev,
                   done anyway — a defensive repoint costs nothing, a missed FK
                   costs a silently orphaned application).
                 · losers deleted; motif_link cascades (verified redundant in M0).
  M2 reshape     · the 4 identity indexes drop `language`; idx_motif_retrieve too.
                   DROP+CREATE, because `CREATE INDEX IF NOT EXISTS` on an existing
                   name is a silent no-op — the definition would never change.
"""
from __future__ import annotations

import json
import logging

import asyncpg

from app.motif_i18n import extract_translatable, translatable_hash

logger = logging.getLogger(__name__)

_MARKER = "motif_i18n_v1"

_MARKER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS package_migration (
  marker     TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# The platform's source language. A system motif authored in anything else is kept
# as-is (its own row stays the keeper) — this only decides WHICH row wins when a
# code exists in several languages.
_SOURCE_LANGUAGE = "en"

_TEXT_COLS = (
    "id, code, original_language, name, summary, emotion_target, "
    "roles, beats, preconditions, effects, examples"
)

# The identity indexes, in their post-collapse shape. Rebuilt unconditionally
# (DROP+CREATE) because IF NOT EXISTS cannot change an existing definition.
_RESHAPE_SQL = """
DROP INDEX IF EXISTS uq_motif_user;
CREATE UNIQUE INDEX uq_motif_user
  ON motif(owner_user_id, code) WHERE owner_user_id IS NOT NULL AND book_id IS NULL;
DROP INDEX IF EXISTS uq_motif_user_book;
CREATE UNIQUE INDEX uq_motif_user_book
  ON motif(owner_user_id, book_id, code) WHERE book_id IS NOT NULL AND NOT book_shared;
DROP INDEX IF EXISTS uq_motif_book_shared;
CREATE UNIQUE INDEX uq_motif_book_shared
  ON motif(book_id, code) WHERE book_shared;
DROP INDEX IF EXISTS uq_motif_system;
CREATE UNIQUE INDEX uq_motif_system
  ON motif(code) WHERE owner_user_id IS NULL;
DROP INDEX IF EXISTS idx_motif_retrieve;
CREATE INDEX idx_motif_retrieve ON motif(status) WHERE status = 'active';
"""


class MotifI18nPreflightError(RuntimeError):
    """A duplicate a human must resolve — never auto-merged."""


async def _preflight_user_tier(conn: asyncpg.Connection) -> None:
    """A user/book-scoped code duplicated across languages is NOT collapsible.

    The system tier is safe to collapse because its rows are known 1:1 translations
    produced by the seeder. A user's two same-code rows carry no such guarantee, and
    merging them would silently destroy one of them.
    """
    rows = await conn.fetch(
        """
        SELECT owner_user_id, book_id, book_shared, code,
               array_agg(original_language ORDER BY original_language) AS langs,
               count(*) AS n
          FROM motif
         WHERE owner_user_id IS NOT NULL
         GROUP BY owner_user_id, book_id, book_shared, code
        HAVING count(*) > 1
        """
    )
    if not rows:
        return
    detail = "; ".join(
        f"owner={r['owner_user_id']} book={r['book_id']} code={r['code']} "
        f"langs={list(r['langs'])}"
        for r in rows[:20]
    )
    raise MotifI18nPreflightError(
        f"motif_i18n M0: {len(rows)} user/book-tier code(s) exist in more than one "
        f"language and cannot be auto-merged (they may be different motifs, not "
        f"translations). Resolve by hand — rename one code, or delete the redundant "
        f"row — then re-boot. Offenders: {detail}"
    )


async def _preflight_links(conn: asyncpg.Connection, losers: dict, keepers: dict) -> None:
    """Refuse to cascade away a link edge the keeper does not already have.

    Deleting a losing row drops its `motif_link` edges via ON DELETE CASCADE. That is
    only safe if every such edge is a duplicate of an edge already present on the
    keeper side. Measured 0 orphans in dev (55 vi edges, 55 en edges, exact mirror) —
    but measured is not the same as guaranteed, so the migration checks its own
    premise rather than trusting a one-time observation.
    """
    if not losers:
        return
    edges = await conn.fetch(
        "SELECT from_motif_id, to_motif_id, kind FROM motif_link "
        "WHERE from_motif_id = ANY($1::uuid[]) OR to_motif_id = ANY($1::uuid[])",
        list(losers),
    )
    existing = {
        (r["from_motif_id"], r["to_motif_id"], r["kind"])
        for r in await conn.fetch("SELECT from_motif_id, to_motif_id, kind FROM motif_link")
    }
    orphans = []
    for e in edges:
        mapped = (
            keepers.get(e["from_motif_id"], e["from_motif_id"]),
            keepers.get(e["to_motif_id"], e["to_motif_id"]),
            e["kind"],
        )
        if mapped[0] == mapped[1] or mapped not in existing:
            orphans.append((e["from_motif_id"], e["to_motif_id"], e["kind"]))
    if orphans:
        raise MotifI18nPreflightError(
            f"motif_i18n M0: {len(orphans)} motif_link edge(s) on a collapsing row have "
            f"no counterpart on the surviving row — the cascade would DESTROY them. "
            f"Re-point them by hand first. Offenders (first 10): {orphans[:10]}"
        )


def _jsonb(value) -> str:
    """asyncpg wants a JSON string for a jsonb parameter."""
    return json.dumps(value, ensure_ascii=False)


async def run_motif_i18n(conn: asyncpg.Connection) -> bool:
    """Collapse per-language motif rows into source + translations. Returns True if
    this boot applied it. Safe and a no-op past its marker; safe on a fresh DB."""
    await conn.execute(_MARKER_TABLE_SQL)
    if await conn.fetchval("SELECT 1 FROM package_migration WHERE marker = $1", _MARKER):
        return False

    async with conn.transaction():
        await _preflight_user_tier(conn)

        # System-tier groups holding more than one language.
        groups = await conn.fetch(
            f"""
            SELECT code, json_agg(json_build_object(
                     'id', id, 'original_language', original_language, 'name', name,
                     'summary', summary, 'emotion_target', emotion_target,
                     'roles', roles, 'beats', beats, 'preconditions', preconditions,
                     'effects', effects, 'examples', examples)) AS rows
              FROM (SELECT {_TEXT_COLS} FROM motif WHERE owner_user_id IS NULL) s
             GROUP BY code
            HAVING count(*) > 1
            """
        )

        keepers: dict = {}   # loser id -> keeper id
        losers: dict = {}    # loser id -> loser payload
        plan = []
        for g in groups:
            rows = g["rows"] if isinstance(g["rows"], list) else json.loads(g["rows"])
            keeper = next(
                (r for r in rows if r["original_language"] == _SOURCE_LANGUAGE), None
            ) or min(rows, key=lambda r: r["original_language"])
            for r in rows:
                if r["id"] == keeper["id"]:
                    continue
                keepers[r["id"]] = keeper["id"]
                losers[r["id"]] = r
                plan.append((keeper, r))

        await _preflight_links(conn, losers, keepers)

        n_tr = 0
        for keeper, loser in plan:
            payload = extract_translatable(loser)
            # The hash records the SOURCE payload this translation was made from, so a
            # later edit to the English motif marks its translations stale rather than
            # silently serving wording that no longer matches.
            await conn.execute(
                """
                INSERT INTO motif_translation (
                  motif_id, language_code, name, summary, emotion_target,
                  roles, beats, preconditions, effects, examples,
                  source_content_hash, source, translated_by)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb,$9::jsonb,$10::jsonb,$11,'authored','seed-pack')
                ON CONFLICT (motif_id, language_code) DO NOTHING
                """,
                keeper["id"], loser["original_language"],
                payload["name"], payload["summary"], payload["emotion_target"] or None,
                _jsonb(payload["roles"]), _jsonb(payload["beats"]),
                _jsonb(payload["preconditions"]), _jsonb(payload["effects"]),
                _jsonb(payload["examples"]),
                translatable_hash(extract_translatable(keeper)),
            )
            n_tr += 1

        n_app = 0
        if losers:
            n_app = await conn.fetchval(
                "WITH upd AS (UPDATE motif_application SET motif_id = m.keeper "
                "  FROM (SELECT unnest($1::uuid[]) AS loser, unnest($2::uuid[]) AS keeper) m "
                " WHERE motif_application.motif_id = m.loser RETURNING 1) "
                "SELECT count(*) FROM upd",
                list(keepers), [keepers[k] for k in keepers],
            )
            await conn.execute("DELETE FROM motif WHERE id = ANY($1::uuid[])", list(losers))

        # M2 — the identity keys can only drop `language` once the duplicates they
        # would otherwise reject are gone, so the reshape runs last.
        await conn.execute(_RESHAPE_SQL)
        await conn.execute(
            "INSERT INTO package_migration (marker) VALUES ($1) ON CONFLICT DO NOTHING",
            _MARKER,
        )

    logger.info(
        "composition migrate: motif_i18n_v1 applied — %d translation(s) lifted, "
        "%d row(s) collapsed, %d application(s) re-pointed",
        n_tr, len(losers), n_app or 0,
    )
    return True
