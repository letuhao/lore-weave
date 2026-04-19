"""K10.1/K10.2/K10.3 — laptop-friendly DDL smoke test.

The real migration contract is exercised by
`tests/integration/db/test_migrations.py` against a live Postgres.
This unit test is the offline safety net: it parses the DDL *string*
and asserts the shape survives refactors (table names, indexes, CHECK
constraints, cross-DB FK rule, idempotency markers).

Runs in milliseconds, needs no DB.
"""

from __future__ import annotations

from app.db.migrate import DDL


def test_extraction_pending_table_present():
    assert "CREATE TABLE IF NOT EXISTS extraction_pending" in DDL
    # UNIQUE(project_id, event_id) is the idempotent-queueing invariant.
    assert "UNIQUE (project_id, event_id)" in DDL


def test_extraction_pending_partial_index():
    assert "idx_extraction_pending_unprocessed" in DDL
    assert "WHERE processed_at IS NULL" in DDL


def test_extraction_jobs_table_present():
    assert "CREATE TABLE IF NOT EXISTS extraction_jobs" in DDL


def test_extraction_jobs_scope_check_constraint():
    assert "scope IN ('chapters','chat','glossary_sync','all')" in DDL


def test_extraction_jobs_status_check_constraint():
    assert (
        "status IN ('pending','running','paused','complete','failed','cancelled')"
        in DDL
    )


def test_extraction_jobs_indexes():
    assert "idx_extraction_jobs_project" in DDL
    assert "idx_extraction_jobs_active" in DDL
    # The active-jobs partial index is the hot path for the job runner.
    assert "WHERE status IN ('pending','running','paused')" in DDL


def test_extraction_jobs_cost_tracking_uses_numeric_not_float():
    # Float rounding would silently lose fractions of a cent per write.
    for col in ("max_spend_usd", "cost_spent_usd"):
        assert f"{col}    NUMERIC(10,4)" in DDL or f"{col}     NUMERIC(10,4)" in DDL


def test_extraction_errors_table_present():
    assert "CREATE TABLE IF NOT EXISTS extraction_errors" in DDL
    assert "error_type" in DDL
    assert "value_preview" in DDL  # truncated — never full blob


def test_extraction_errors_type_enum():
    assert (
        "error_type IN ('provenance_validation','extractor_crash',"
        "'timeout','llm_refusal','unknown')"
    ) in DDL


def test_projects_alter_adds_budget_columns():
    # K10.3 diff. K1.2 already added embedding_model / extraction_config /
    # cost_usd — the ALTER here must only add the columns that didn't
    # exist in Track 1, otherwise IF NOT EXISTS is a no-op (fine) but the
    # intent gets muddied.
    for col in (
        "monthly_budget_usd",
        "current_month_spent_usd",
        "current_month_key",
        "stat_entity_count",
        "stat_fact_count",
        "stat_event_count",
        "stat_glossary_count",
        "stat_updated_at",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in DDL, f"missing column: {col}"


def test_no_cross_db_fk_on_user_id():
    # The module header is explicit: user_id references a different DB,
    # so no FK. A regression that adds `REFERENCES users` would crash at
    # migration time against a real loreweave_knowledge DB.
    assert "REFERENCES users" not in DDL


def test_project_fk_cascades_on_delete():
    # When a project is purged, its extraction queue / jobs / errors
    # must go with it — otherwise orphaned rows reference a dead project.
    assert DDL.count(
        "REFERENCES knowledge_projects(project_id) ON DELETE CASCADE"
    ) >= 3  # pending, jobs, errors (and any future tables)


def test_all_create_statements_are_idempotent():
    # Track 1 house style: run_migrations is called on every startup.
    # Every CREATE must use IF NOT EXISTS or be wrapped in a DO $$ block.
    import re

    bare_create_table = re.findall(
        r"CREATE TABLE (?!IF NOT EXISTS)", DDL
    )
    assert bare_create_table == [], f"non-idempotent CREATE TABLE: {bare_create_table}"

    bare_create_index = re.findall(
        r"CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", DDL
    )
    assert bare_create_index == [], f"non-idempotent CREATE INDEX: {bare_create_index}"


# ── K17.9.1 — project_embedding_benchmark_runs ─────────────────────────────


def test_benchmark_runs_table_present():
    assert (
        "CREATE TABLE IF NOT EXISTS project_embedding_benchmark_runs" in DDL
    )


def test_benchmark_runs_unique_constraint():
    """Re-running the harness with the same (project, model, run_id)
    must fail on the UNIQUE rather than silently duplicating."""
    assert "UNIQUE (project_id, embedding_model, run_id)" in DDL


def test_benchmark_runs_latest_query_index():
    """Latest-run-per-project query must hit an index, not a seq scan.
    Covering index includes embedding_model so filter-by-model is also
    fast (K12.4 picker uses it when a user switches models)."""
    assert "idx_benchmark_runs_project_latest" in DDL
    assert "(project_id, embedding_model, created_at DESC)" in DDL


def test_benchmark_runs_project_fk_cascades():
    """When a project is deleted, its benchmark history is worthless —
    cascade the delete like the other extraction_* tables do."""
    # Increase the cascade-count floor to 4 now that a fourth table
    # references knowledge_projects(project_id).
    assert DDL.count(
        "REFERENCES knowledge_projects(project_id) ON DELETE CASCADE"
    ) >= 4


def test_benchmark_runs_no_cross_db_fk_on_provider():
    """embedding_provider_id points to a row in provider-registry's
    own database — no cross-DB FK allowed (same rule as user_id /
    book_id). A regression adding the FK would crash migrations."""
    # The column is declared but no REFERENCES clause follows it.
    import re
    # Find the benchmark_runs table body.
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS project_embedding_benchmark_runs\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None, "benchmark_runs table not found"
    body = m.group(1)
    # embedding_provider_id line must not be followed by a REFERENCES.
    prov_line = [
        line for line in body.splitlines()
        if "embedding_provider_id" in line
    ]
    assert prov_line, "embedding_provider_id column missing"
    assert "REFERENCES" not in prov_line[0], (
        "cross-DB FK on embedding_provider_id — lives in provider-registry"
    )


def test_benchmark_runs_passed_is_not_null():
    """The `passed` bit is the extraction-enable gate. Nullable would
    let the FE wait forever on 'unknown'."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS project_embedding_benchmark_runs\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    passed_line = [
        line for line in body.splitlines()
        if line.strip().startswith("passed ")
    ]
    assert passed_line, "passed column missing"
    assert "NOT NULL" in passed_line[0]


def test_benchmark_runs_raw_report_jsonb_with_default():
    """raw_report is NOT NULL with an empty-object default so queries
    don't need to guard against NULL when digging into the payload."""
    assert "raw_report             JSONB NOT NULL DEFAULT '{}'::jsonb" in DDL
