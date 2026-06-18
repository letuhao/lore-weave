from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, Query
import asyncpg

from ..deps import get_db
from ..grant_deps import GrantLevel, require_book_grant
from ..models import (
    BookCoverageResponse, ChapterCoverage, CoverageCell,
    SegmentCoverageChapter, SegmentCoverageResponse,
)

router = APIRouter(prefix="/v1/translation", tags=["translation-coverage"])


# T2-M3 (A+D): per (book, language) per-chapter segment counts for the matrix badge +
# drill-down summary. Book chapters come from chapter_translations (chapter_segments
# carries no book_id); each chapter's current segments LEFT JOIN the recorded
# translation hash for this language. dirty = source changed (or never translated);
# stale = a translated segment whose glossary entity changed (T2-M3.2);
# needs = dirty ∪ stale.
_SEGMENT_COVERAGE_SQL = """
WITH book_chapters AS (
  SELECT DISTINCT chapter_id FROM chapter_translations
  WHERE book_id = $1 AND target_language = $2
)
SELECT cs.chapter_id AS chapter_id,
       COUNT(*)                                                    AS segment_total,
       COUNT(*) FILTER (WHERE st.source_content_hash IS NOT NULL)  AS translated_count,
       COUNT(*) FILTER (
         WHERE st.source_content_hash IS NULL
            OR st.source_content_hash <> cs.source_content_hash
       )                                                           AS dirty_count,
       COUNT(*) FILTER (
         WHERE st.source_content_hash IS NOT NULL
           AND COALESCE(st.is_glossary_stale, false)
       )                                                           AS stale_count,
       COUNT(*) FILTER (
         WHERE st.source_content_hash IS NULL
            OR st.source_content_hash <> cs.source_content_hash
            OR COALESCE(st.is_glossary_stale, false)
       )                                                           AS needs_count
FROM chapter_segments cs
JOIN book_chapters bc ON bc.chapter_id = cs.chapter_id
LEFT JOIN segment_translations st
  ON st.chapter_id = cs.chapter_id
 AND st.segment_index = cs.segment_index
 AND st.target_language = $2
GROUP BY cs.chapter_id
ORDER BY cs.chapter_id
"""


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


@router.get("/books/{book_id}/segment-coverage", response_model=SegmentCoverageResponse)
async def get_segment_coverage(
    book_id: UUID,
    target_language: str = Query(...),
    _grant: UUID = Depends(require_book_grant(GrantLevel.VIEW)),
    db: asyncpg.Pool = Depends(get_db),
):
    """T2-M3: per-chapter segment counts for a book+language — powers the matrix
    "N changed" badge and the drill-down summary. A chapter with no segments built
    yet simply doesn't appear (run the rebuild/backfill)."""
    rows = await db.fetch(_SEGMENT_COVERAGE_SQL, book_id, target_language)
    chapters = [
        SegmentCoverageChapter(
            chapter_id=r["chapter_id"],
            segment_total=r["segment_total"],
            translated_count=r["translated_count"],
            dirty_count=r["dirty_count"],
            stale_count=r["stale_count"],
            needs_count=r["needs_count"],
        )
        for r in rows
    ]
    return SegmentCoverageResponse(
        book_id=book_id, target_language=target_language, chapters=chapters,
    )
