from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends
import asyncpg

from ..deps import get_db
from ..grant_deps import GrantLevel, require_book_grant
from ..models import BookCoverageResponse, ChapterCoverage, CoverageCell

router = APIRouter(prefix="/v1/translation", tags=["translation-coverage"])


@router.get("/books/{book_id}/coverage", response_model=BookCoverageResponse)
async def get_book_coverage(
    book_id: UUID,
    # E0-4a view gate + D-E0-4-F shared per-book view: the matrix shows ALL of the
    # book's translations (drop owner_user_id; book_id still scopes → IDOR-safe).
    _grant: UUID = Depends(require_book_grant(GrantLevel.VIEW)),
    db: asyncpg.Pool = Depends(get_db),
):
    """
    Returns a chapter × language coverage matrix for a book.
    Each cell shows: version_count, latest_status, has_active, active_version_num.
    Also returns known_languages — all languages seen in any translation for this book.
    """
    rows = await db.fetch(
        """
        SELECT
          ct.chapter_id,
          ct.target_language,
          COUNT(*)                                                            AS version_count,
          (SELECT status
             FROM chapter_translations ct2
            WHERE ct2.chapter_id    = ct.chapter_id
              AND ct2.target_language = ct.target_language
            ORDER BY ct2.created_at DESC
            LIMIT 1)                                                         AS latest_status,
          (SELECT version_num
             FROM chapter_translations ct2
            WHERE ct2.chapter_id    = ct.chapter_id
              AND ct2.target_language = ct.target_language
            ORDER BY ct2.created_at DESC
            LIMIT 1)                                                         AS latest_version_num,
          actv.chapter_translation_id                                        AS active_ct_id,
          (SELECT version_num
             FROM chapter_translations ct3
            WHERE ct3.id = actv.chapter_translation_id)                      AS active_version_num,
          -- M6b-2: the active version's staleness (what the reader sees); fall
          -- back to the latest version when no version is active yet.
          COALESCE(
            (SELECT is_glossary_stale
               FROM chapter_translations ct4
              WHERE ct4.id = actv.chapter_translation_id),
            (SELECT is_glossary_stale
               FROM chapter_translations ct5
              WHERE ct5.chapter_id      = ct.chapter_id
                AND ct5.target_language = ct.target_language
              ORDER BY ct5.created_at DESC
              LIMIT 1),
            false
          )                                                                  AS is_glossary_stale
        FROM chapter_translations ct
        LEFT JOIN active_chapter_translation_versions actv
          ON actv.chapter_id      = ct.chapter_id
         AND actv.target_language = ct.target_language
        WHERE ct.book_id       = $1
        GROUP BY ct.chapter_id, ct.target_language, actv.chapter_translation_id
        ORDER BY ct.chapter_id, ct.target_language
        """,
        book_id,
    )

    # Build chapter → {language → CoverageCell} map
    chapter_map: dict[str, dict[str, CoverageCell]] = {}
    known_langs: set[str] = set()

    for row in rows:
        cid = str(row["chapter_id"])
        lang = row["target_language"]
        known_langs.add(lang)

        if cid not in chapter_map:
            chapter_map[cid] = {}

        chapter_map[cid][lang] = CoverageCell(
            has_active=row["active_ct_id"] is not None,
            active_version_num=row["active_version_num"],
            latest_version_num=row["latest_version_num"],
            latest_status=row["latest_status"],
            version_count=row["version_count"],
            is_glossary_stale=row["is_glossary_stale"],
        )

    coverage = [
        ChapterCoverage(chapter_id=UUID(cid), languages=langs)
        for cid, langs in chapter_map.items()
    ]

    return BookCoverageResponse(
        book_id=book_id,
        coverage=coverage,
        known_languages=sorted(known_langs),
    )
