"""P2 — regression-lock for the extraction_leaves schema additions.

Pure string check on app/db/migrate.py DDL. Live live-smoke validates the
actual DB shape end-to-end.
"""

from __future__ import annotations

from app.db import migrate


def test_p2_extraction_leaves_table_present():
    for line in [
        "CREATE TABLE IF NOT EXISTS extraction_leaves",
        "book_id              UUID NOT NULL",
        "scene_id             UUID NOT NULL",
        "leaf_path            TEXT NOT NULL",
        "op                   TEXT NOT NULL",
        "CHECK (op IN ('entity','relation','event','fact'))",
        "task_id              TEXT NOT NULL",
        "CHECK (status IN ('pending','running','completed','failed'))",
        "candidates_jsonb     JSONB",
        "retried_n            INT  NOT NULL DEFAULT 0",
        "extractor_version    TEXT NOT NULL",
        "model_ref            TEXT NOT NULL",
        "UNIQUE (book_id, leaf_path, op)",
    ]:
        assert line in migrate.DDL, f"missing extraction_leaves DDL fragment: {line!r}"


def test_p2_extraction_leaves_raw_cascade():
    for line in [
        "CREATE TABLE IF NOT EXISTS extraction_leaves_raw",
        "extraction_leaf_id UUID PRIMARY KEY REFERENCES extraction_leaves(id) ON DELETE CASCADE",
        "raw_response_jsonb JSONB NOT NULL",
        "raw_token_usage    JSONB NOT NULL",
    ]:
        assert line in migrate.DDL, f"missing extraction_leaves_raw DDL fragment: {line!r}"


def test_p2_indexes_present():
    for idx in [
        "idx_extraction_leaves_task_id",
        "idx_extraction_leaves_pending",
        "idx_extraction_leaves_book",
    ]:
        assert idx in migrate.DDL, f"missing P2 index: {idx}"


def test_p2_knowledge_projects_save_raw_extraction_added():
    assert (
        "ADD COLUMN IF NOT EXISTS save_raw_extraction BOOLEAN NOT NULL DEFAULT false"
        in migrate.DDL
    )


def test_p2_block_is_idempotent():
    """All P2 CREATE/ALTER must use IF NOT EXISTS so a startup re-run is no-op.
    R-SELF-1 from P1 lessons. Multi-line ALTER allowed (IF NOT EXISTS may
    appear on the ADD COLUMN line, not the ALTER TABLE line).
    """
    p2_idx = migrate.DDL.find("P2 (hierarchical extraction T3)")
    assert p2_idx != -1, "P2 section sentinel not found"
    p2_block = migrate.DDL[p2_idx:]
    # Split into statements at semicolons, then check each statement contains the guard.
    statements = [s.strip() for s in p2_block.split(";") if s.strip()]
    for stmt in statements:
        head = stmt.lstrip().upper()
        if head.startswith("CREATE TABLE") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P2 non-idempotent CREATE TABLE: {stmt[:80]!r}")
        if head.startswith("ALTER TABLE") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P2 non-idempotent ALTER TABLE: {stmt[:80]!r}")
        if head.startswith("CREATE INDEX") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P2 non-idempotent CREATE INDEX: {stmt[:80]!r}")
