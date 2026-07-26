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


# Forms that are inherently re-runnable but have NO `IF NOT EXISTS` clause in
# Postgres to grep for. This test is a cheap STATIC backstop; the semantic
# guarantee ("a startup re-run is a clean no-op") is proven by effect in
# tests/integration/db/test_migrations.py::test_migrations_idempotent, which runs
# the real DDL twice against a real Postgres.
#
#   ALTER COLUMN ... SET NOT NULL — re-running on an already-NOT NULL column
#   succeeds as a no-op. Postgres offers no IF NOT EXISTS spelling for it, so the
#   grep below cannot express its idempotency. (WS-0.1: extraction_leaves.chapter_id
#   is backfilled and then pinned NOT NULL so a writer that forgets to set it fails
#   loudly rather than orphaning an unreachable leaf.)
_INHERENTLY_IDEMPOTENT_ALTERS = ("SET NOT NULL",)


def test_p2_block_is_idempotent():
    """All P2 CREATE/ALTER must use IF NOT EXISTS so a startup re-run is no-op.
    R-SELF-1 from P1 lessons. Multi-line ALTER allowed (IF NOT EXISTS may
    appear on the ADD COLUMN line, not the ALTER TABLE line).
    """
    p2_idx = migrate.DDL.find("P2 (hierarchical extraction T3)")
    assert p2_idx != -1, "P2 section sentinel not found"
    # Stop at the next section sentinel (P3 etc.) so the test doesn't
    # pick up later sections' DDL when checking P2's idempotency.
    p3_idx = migrate.DDL.find("P3 (hierarchical extraction", p2_idx)
    p2_block = migrate.DDL[p2_idx:p3_idx] if p3_idx != -1 else migrate.DDL[p2_idx:]
    # Split into statements at semicolons, then check each statement contains the guard.
    statements = [s.strip() for s in p2_block.split(";") if s.strip()]
    for stmt in statements:
        head = stmt.lstrip().upper()
        if head.startswith("CREATE TABLE") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P2 non-idempotent CREATE TABLE: {stmt[:80]!r}")
        if (
            head.startswith("ALTER TABLE")
            and "IF NOT EXISTS" not in stmt.upper()
            and not any(form in stmt.upper() for form in _INHERENTLY_IDEMPOTENT_ALTERS)
        ):
            raise AssertionError(f"P2 non-idempotent ALTER TABLE: {stmt[:80]!r}")
        if head.startswith("CREATE INDEX") and "IF NOT EXISTS" not in stmt.upper():
            raise AssertionError(f"P2 non-idempotent CREATE INDEX: {stmt[:80]!r}")
