"""ARC-I18N — take `language` out of the arc-template identity key.

The same defect motif carried, one table over: `language` sat inside all three
`uq_arc_template_*` indexes, so the same arc in two languages was two unrelated rows,
and `arc_template_repo` filtered on it in `list`/`catalog` — a WHERE clause that can
only SUBTRACT, which is how asking for Vietnamese returns an empty library rather than
a translated one (`D-MOTIF-AUTO-LANGUAGE-ZEROES-RETRIEVAL`, the same shape).

**It had not fired yet, and that is the whole reason to fix it now.** Measured before
the change: 31 rows, 0 system rows, 1 distinct language (`en`), and no caller passing
`language`. So unlike motif — 168 rows for 84 motifs, 84 hand-written Vietnamese
translations to rescue, 55 link edges to repoint — there is **nothing to collapse
here**. This migration is a reshape, not a data rescue.

That also makes the trap sharper, not milder: the moment someone wires the reader's
language into the arc library the way the motif library now does, every user whose UI
is not English gets zero arcs, and the symptom looks like missing data rather than a
filter. Fixing an unexercised defect is cheap exactly once.

Marker-gated (`package_migration`, the `motif_i18n_v1` precedent) so it runs once and
a re-boot is a no-op. Pre-flight is a REFUSAL, not a guess: if a code genuinely exists
in two languages within one tier, collapsing would have to pick a winner, and picking
silently is how you lose an author's work — so it fails loud instead.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)

__all__ = ["run_arc_i18n", "MARKER"]

MARKER = "arc_i18n_v1"

# The identity indexes, de-languaged. `CREATE INDEX IF NOT EXISTS` on an EXISTING name
# is a silent no-op — it does not re-check the definition — so each one is dropped and
# recreated rather than "ensured" (the trap that made the motif reshape a no-op the
# first time it was written).
_RESHAPE_SQL = """
ALTER TABLE arc_template ADD COLUMN IF NOT EXISTS original_language TEXT NOT NULL DEFAULT 'en';
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'arc_template' AND column_name = 'language') THEN
    UPDATE arc_template SET original_language = language;
    ALTER TABLE arc_template DROP COLUMN language;
  END IF;
END $$;

DROP INDEX IF EXISTS uq_arc_template_system;
DROP INDEX IF EXISTS uq_arc_template_user_nobook;
DROP INDEX IF EXISTS uq_arc_template_user;
DROP INDEX IF EXISTS uq_arc_template_book_shared;

CREATE UNIQUE INDEX uq_arc_template_system
  ON arc_template(code)                WHERE owner_user_id IS NULL;
CREATE UNIQUE INDEX uq_arc_template_user_nobook
  ON arc_template(owner_user_id, code) WHERE owner_user_id IS NOT NULL AND book_id IS NULL;
CREATE UNIQUE INDEX uq_arc_template_book_shared
  ON arc_template(book_id, code)       WHERE book_id IS NOT NULL AND book_shared;
"""

# Mirrors `motif_translation` exactly, including WHY the hash is a column and not part
# of the key: an arc template has exactly one current text per language, so a
# hash-in-key would grow unbounded rows and turn the read into a "pick the newest
# matching" subquery instead of a single LEFT JOIN.
_TRANSLATION_SQL = """
CREATE TABLE IF NOT EXISTS arc_template_translation (
  arc_template_id UUID NOT NULL REFERENCES arc_template(id) ON DELETE CASCADE,
  language_code   TEXT NOT NULL,
  name            TEXT NOT NULL,
  summary         TEXT NOT NULL DEFAULT '',
  threads         JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label}]  key MUST match source
  arc_roster      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label,constraints}] key MUST match
  source_content_hash TEXT NOT NULL,
  source          TEXT NOT NULL DEFAULT 'machine' CHECK (source IN ('authored','machine')),
  translated_by   TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (arc_template_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_arc_template_translation_lang
  ON arc_template_translation(language_code);
"""


async def _already_applied(conn: asyncpg.Connection) -> bool:
    return bool(await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM package_migration WHERE marker = $1)", MARKER))


async def _preflight(conn: asyncpg.Connection) -> None:
    """Refuse rather than guess when a code really does exist in two languages.

    De-languaging the key would make those two rows collide, and resolving a collision
    means choosing whose text survives. There is no safe default for that, so the boot
    fails with the offending codes named — an operator merges them deliberately.
    """
    if not await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'arc_template' AND column_name = 'language')"
    ):
        return  # already de-languaged (or a fresh DB) — nothing to collide

    for scope, sql in (
        ("system", "SELECT code, count(DISTINCT language) c FROM arc_template "
                   "WHERE owner_user_id IS NULL GROUP BY code HAVING count(DISTINCT language) > 1"),
        ("user", "SELECT owner_user_id::text || '/' || code AS code, count(DISTINCT language) c "
                 "FROM arc_template WHERE owner_user_id IS NOT NULL AND book_id IS NULL "
                 "GROUP BY owner_user_id, code HAVING count(DISTINCT language) > 1"),
        ("book_shared", "SELECT book_id::text || '/' || code AS code, count(DISTINCT language) c "
                        "FROM arc_template WHERE book_id IS NOT NULL AND book_shared "
                        "GROUP BY book_id, code HAVING count(DISTINCT language) > 1"),
    ):
        rows = await conn.fetch(sql)
        if rows:
            names = ", ".join(r["code"] for r in rows[:10])
            raise RuntimeError(
                f"arc i18n pre-flight: {len(rows)} {scope}-tier arc template code(s) exist in more "
                f"than one language ({names}). De-languaging the identity key would collide them, "
                f"and choosing a winner is not this migration's call — merge them by hand, then "
                f"re-boot."
            )


async def run_arc_i18n(conn: asyncpg.Connection) -> bool:
    """Apply once; return True iff this boot did the work."""
    if await _already_applied(conn):
        return False
    await _preflight(conn)

    before = await conn.fetchval("SELECT count(*) FROM arc_template")
    async with conn.transaction():
        await conn.execute(_RESHAPE_SQL)
        await conn.execute(_TRANSLATION_SQL)
        await conn.execute(
            "INSERT INTO package_migration (marker) VALUES ($1) ON CONFLICT DO NOTHING", MARKER)
    after = await conn.fetchval("SELECT count(*) FROM arc_template")

    # A reshape must not lose a row. Motif's migration legitimately collapsed
    # 168 → 84; this one has nothing to collapse, so any drift is a bug.
    if before != after:
        logger.error("arc i18n: row count moved %d → %d — a reshape must not", before, after)
    logger.info("arc i18n %s applied: %d arc template(s) reshaped", MARKER, after)
    return True
