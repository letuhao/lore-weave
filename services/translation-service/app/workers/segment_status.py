"""T2-M2: per-(chapter, target_language, segment) translation status + dirty signal.

A *segment* (T2-M1, `chapter_segments`) is a language-independent block-range of a
chapter. `segment_translations` records, per target language, the segment's
`source_content_hash` AT the time it was translated. A later source edit changes the
segment's `chapter_segments.source_content_hash`; the recorded hash then no longer
matches → the segment is **dirty** (needs re-translation). A segment with no recorded
row is dirty too (never translated for this language).

Pure SQL helpers (take a connection) — reused by the finalize hook (record) and the
status endpoints (compute).
"""
import logging

log = logging.getLogger(__name__)


# A completed FULL-chapter translation covered EVERY current segment at its current
# source hash → upsert one row per segment from chapter_segments. Idempotent on
# (chapter_id, target_language, segment_index); a re-run / dirty-only refresh just
# bumps the hash + translated_at for the segments it re-covered.
_RECORD_SQL = """
INSERT INTO segment_translations
  (chapter_id, target_language, segment_index, source_content_hash,
   chapter_translation_id, translated_at, updated_at)
SELECT cs.chapter_id, $2, cs.segment_index, cs.source_content_hash, $3, now(), now()
FROM chapter_segments cs
WHERE cs.chapter_id = $1
ON CONFLICT (chapter_id, target_language, segment_index)
DO UPDATE SET source_content_hash    = EXCLUDED.source_content_hash,
              chapter_translation_id  = EXCLUDED.chapter_translation_id,
              translated_at           = now(),
              updated_at              = now(),
              -- a fresh (re)translation clears glossary-staleness (T2-M3.2)
              is_glossary_stale       = false
"""

# Per-segment status: current source (chapter_segments) LEFT JOIN the recorded
# translation hash for this language. dirty = no record OR the source changed.
_STATUS_SQL = """
SELECT cs.segment_index        AS segment_index,
       cs.start_block_index    AS start_block_index,
       cs.end_block_index      AS end_block_index,
       cs.token_estimate       AS token_estimate,
       cs.source_content_hash  AS current_hash,
       st.source_content_hash  AS translated_hash,
       st.translated_at        AS translated_at,
       COALESCE(st.is_glossary_stale, false) AS is_glossary_stale
FROM chapter_segments cs
LEFT JOIN segment_translations st
  ON st.chapter_id = cs.chapter_id
 AND st.segment_index = cs.segment_index
 AND st.target_language = $2
WHERE cs.chapter_id = $1
ORDER BY cs.segment_index
"""


async def record_segment_translations(
    conn, chapter_id, target_language: str, chapter_translation_id,
) -> int:
    """Mark every current segment of a chapter as translated at its current source
    hash for `target_language`. Returns the number of segments recorded (0 if the
    chapter has no segments yet)."""
    res = await conn.execute(_RECORD_SQL, chapter_id, target_language, chapter_translation_id)
    # asyncpg command tag → "INSERT 0 <n>"; tolerate a non-str test mock.
    if isinstance(res, str):
        try:
            return int(res.rsplit(" ", 1)[1])
        except (ValueError, IndexError):
            return 0
    return 0


def _is_dirty(current_hash, translated_hash) -> bool:
    return translated_hash is None or translated_hash != current_hash


def scan_glossary_usage(
    segments: list[tuple[int, str]], entity_terms: list[tuple[str, list[str]]],
) -> list[tuple[int, str]]:
    """T2-M3.2 (pure): which glossary entities each segment's SOURCE text references.

    `segments` = [(segment_index, segment_text)]; `entity_terms` = [(entity_id,
    [source_terms])]. An entity is used by a segment if ANY of its source terms is a
    substring of the segment text (mirrors the occurrence scoring in
    build_glossary_context). Language-independent — source terms in source text.
    Returns [(segment_index, entity_id)]."""
    out: list[tuple[int, str]] = []
    for seg_idx, text in segments:
        if not text:
            continue
        for entity_id, terms in entity_terms:
            if entity_id and any(t and t in text for t in terms):
                out.append((seg_idx, entity_id))
    return out


async def record_segment_glossary_usage(
    conn, chapter_id, usage: list[tuple[int, str]],
) -> None:
    """Replace the per-segment glossary-usage rows for a chapter (DELETE-all +
    re-INSERT) so a re-translation re-derives usage from the current source. Caller
    runs this best-effort. `usage` = [(segment_index, entity_id)]."""
    await conn.execute("DELETE FROM segment_glossary_usage WHERE chapter_id=$1", chapter_id)
    if not usage:
        return
    # One round-trip instead of one-INSERT-per-row (a glossary-dense chapter can have
    # many segment×entity pairs). ON CONFLICT DO NOTHING tolerates a (seg, entity) dup.
    await conn.executemany(
        "INSERT INTO segment_glossary_usage (chapter_id, segment_index, entity_id) "
        "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
        [(chapter_id, seg_idx, entity_id) for seg_idx, entity_id in usage],
    )


async def compute_segment_status(conn, chapter_id, target_language: str) -> list[dict]:
    """Per-segment translation status for a chapter+language, ordered by segment_index.

    Each item: segment_index, start_block_index, end_block_index, token_estimate,
    translated (bool), dirty (bool), translated_at (ISO str or None)."""
    rows = await conn.fetch(_STATUS_SQL, chapter_id, target_language)
    out: list[dict] = []
    for r in rows:
        translated_hash = r["translated_hash"]
        ta = r["translated_at"]
        dirty = _is_dirty(r["current_hash"], translated_hash)
        # glossary-staleness only applies to a translated segment (an untranslated one
        # is already dirty). `needs` = the segment should be re-translated for any reason.
        stale = bool(translated_hash is not None and r["is_glossary_stale"])
        out.append({
            "segment_index": r["segment_index"],
            "start_block_index": r["start_block_index"],
            "end_block_index": r["end_block_index"],
            "token_estimate": r["token_estimate"],
            "translated": translated_hash is not None,
            "dirty": dirty,
            "stale": stale,
            "needs": dirty or stale,
            "translated_at": ta.isoformat() if ta is not None else None,
        })
    return out
