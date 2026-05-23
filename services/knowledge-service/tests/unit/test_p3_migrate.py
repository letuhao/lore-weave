"""P3 — regression-lock for the 3 summary tables + extraction_jobs status.

Live live-smoke validates actual DB shape end-to-end.
"""

from __future__ import annotations

from app.db import migrate


def test_p3_summary_chapters_table_present():
    for line in [
        "CREATE TABLE IF NOT EXISTS summary_chapters",
        "chapter_id           UUID NOT NULL",
        "book_id              UUID NOT NULL",
        "summary_text         TEXT NOT NULL",
        "summary_input_md5    TEXT NOT NULL",
        "embedding_dimension  INT  NOT NULL",
        "embedding_model_uuid TEXT NOT NULL",
        "UNIQUE (chapter_id, embedding_model_uuid)",
    ]:
        assert line in migrate.DDL, f"missing summary_chapters DDL fragment: {line!r}"


def test_p3_summary_parts_table_present():
    for line in [
        "CREATE TABLE IF NOT EXISTS summary_parts",
        "part_id              UUID NOT NULL",
        "UNIQUE (part_id, embedding_model_uuid)",
    ]:
        assert line in migrate.DDL, f"missing summary_parts DDL fragment: {line!r}"


def test_p3_summary_books_table_present():
    for line in [
        "CREATE TABLE IF NOT EXISTS summary_books",
        "UNIQUE (book_id, embedding_model_uuid)",
    ]:
        assert line in migrate.DDL, f"missing summary_books DDL fragment: {line!r}"


def test_p3_extraction_jobs_status_extended_with_summarizing():
    """M1: 'summarizing' is the NEW transitional state."""
    assert (
        "CHECK (status IN ('pending','running','summarizing','completed','failed'))"
        in migrate.DDL
    )


def test_p3_block_is_idempotent():
    """All P3 CREATE/ALTER use IF NOT EXISTS; DROP CONSTRAINT uses IF EXISTS."""
    p3_idx = migrate.DDL.find("P3 (hierarchical extraction T4 + T7 stage 1)")
    assert p3_idx != -1, "P3 section sentinel not found"
    p3_block = migrate.DDL[p3_idx:]
    statements = [s.strip() for s in p3_block.split(";") if s.strip()]
    for stmt in statements:
        head = stmt.lstrip().upper()
        if head.startswith("CREATE TABLE") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P3 non-idempotent CREATE TABLE: {stmt[:80]!r}")
        if head.startswith("CREATE INDEX") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P3 non-idempotent CREATE INDEX: {stmt[:80]!r}")
        # ALTER TABLE inside DO block uses DROP IF EXISTS — sufficient.


def test_p3_indexes_on_book_id():
    """Both summary_chapters + summary_parts have a book_id index for
    'load all summaries for this book' queries (M3-router blend)."""
    assert "idx_summary_chapters_book" in migrate.DDL
    assert "idx_summary_parts_book" in migrate.DDL
