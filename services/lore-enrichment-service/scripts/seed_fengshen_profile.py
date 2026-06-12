"""Seed the Fengshen demo book's enrichment_book_profile (de-bias C1, T3).

The de-bias makes generation/verify/dimensions PROFILE-driven (NEUTRAL default =
anachronism OFF, language auto). To keep the 封神演义 demo byte-equivalent to its
pre-de-bias behavior, seed its book a profile carrying the OLD hardcoded values:
worldview 商周·封神演义, language zh, the 商周 era policy + the FENGSHEN anachronism
denylist (lifted from canon_verify), and the 原著 voice.

Idempotent: INSERT ... ON CONFLICT (book_id) DO UPDATE — safe to re-run. The
book_id is supplied by arg/env (NOT hardcoded — it is demo data, not source).

Usage:
    python -m scripts.seed_fengshen_profile <book_id>
    FENGSHEN_DEMO_BOOK_ID=<uuid> python -m scripts.seed_fengshen_profile

DSN: settings.database_url (the lore-enrichment DB).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import UUID

import asyncpg

from app.config import settings
from app.verify.canon_verify import FENGSHEN_ANACHRONISM_MARKERS

# The Fengshen profile = the pre-de-bias hardcoded values (no regression).
_WORLDVIEW = "《封神演义》原著"
_LANGUAGE = "zh"
_ERA_POLICY = "商周·封神纪元：不得出现后世朝代、近现代器物、外来宗教"
_VOICE = "文言-白话皆可，须与原著语气一致"


def _markers_json() -> str:
    """FENGSHEN_ANACHRONISM_MARKERS → the JSONB [{term, reason}] shape the
    profile reader (`_parse_markers`) expects."""
    return json.dumps(
        [{"term": t, "reason": r} for t, r in FENGSHEN_ANACHRONISM_MARKERS],
        ensure_ascii=False,
    )


async def seed(book_id: UUID) -> None:
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO enrichment_book_profile (
                    book_id, worldview, language, era_policy, voice,
                    anachronism_markers, dimension_overrides, profile_source
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, '{}'::jsonb, 'seed')
                ON CONFLICT (book_id) DO UPDATE SET
                    worldview = EXCLUDED.worldview,
                    language = EXCLUDED.language,
                    era_policy = EXCLUDED.era_policy,
                    voice = EXCLUDED.voice,
                    anachronism_markers = EXCLUDED.anachronism_markers,
                    profile_source = 'seed',
                    updated_at = now()
                """,
                book_id, _WORLDVIEW, _LANGUAGE, _ERA_POLICY, _VOICE, _markers_json(),
            )
        print(f"seeded Fengshen profile for book {book_id} "
              f"(lang={_LANGUAGE}, {len(FENGSHEN_ANACHRONISM_MARKERS)} anachronism markers)")
    finally:
        await pool.close()


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FENGSHEN_DEMO_BOOK_ID")
    if not raw:
        sys.exit("usage: python -m scripts.seed_fengshen_profile <book_id> "
                 "(or set FENGSHEN_DEMO_BOOK_ID)")
    asyncio.run(seed(UUID(raw)))


if __name__ == "__main__":
    main()
