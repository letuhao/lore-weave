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
    # CM3b: 'chapters_pending' = the worker-ai coalescing drainer scope.
    assert (
        "scope IN ('chapters','chat','glossary_sync','all','chapters_pending')"
        in DDL
    )


def test_extraction_jobs_status_check_constraint():
    # Cycle 10: the full status vocabulary the code actually emits — incl.
    # 'summarizing' (M1) AND 'paused'/'cancelled'/'complete' (state machine +
    # worker-ai). Both the inline CREATE constraint and the M1 ALTER carry it.
    assert (
        "status IN ('pending','running','paused','summarizing','complete','failed','cancelled')"
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


def test_projects_alter_adds_tool_calling_enabled():
    """K21.12-BE (design D9) — the per-project tool-calling toggle.
    NOT NULL DEFAULT true so a project row that predates the column
    reads back enabled (the model default in models.py is the other
    half of that contract). Idempotent ADD COLUMN IF NOT EXISTS so
    run_migrations stays safe on every startup."""
    assert (
        "ADD COLUMN IF NOT EXISTS tool_calling_enabled BOOLEAN NOT NULL DEFAULT true"
        in DDL
    )


def test_projects_alter_adds_canon_capture_enabled_defaulting_off():
    """WS-4C Half A — the per-project canon auto-capture toggle is OPT-IN.

    DEFAULT **false**, deliberately NOT tool_calling_enabled's default-true:
    capture is ambient spend on the user's own paid model, so the toggle is the
    consent and must start un-granted. `models.py`'s `canon_capture_enabled: bool
    = False` is the other half of that contract.

    An earlier revision of this branch shipped `DEFAULT true`, which back-filled every
    existing row to true; `ADD COLUMN IF NOT EXISTS` never revisits a column, so the
    literal change alone would leave those projects opted IN and silently spending
    (observed for real: 21/21 dev projects). The guarded, self-disarming block keys on
    the column's own default as a version marker and normalizes the rows exactly once.
    All three parts must survive, or a redeploy re-enables paid capture."""
    assert (
        "ADD COLUMN IF NOT EXISTS canon_capture_enabled BOOLEAN NOT NULL DEFAULT false"
        in DDL
    )
    assert "SELECT column_default = 'true' INTO _bad_default" in DDL, "the version marker"
    assert "UPDATE knowledge_projects SET canon_capture_enabled = false" in DDL, "the normalization"
    assert "ALTER COLUMN canon_capture_enabled SET DEFAULT false" in DDL, "the disarm"
    assert (
        "ADD COLUMN IF NOT EXISTS canon_capture_enabled BOOLEAN NOT NULL DEFAULT true"
        not in DDL
    ), "capture must never default ON — that charges every project for a feature nobody asked for"


def test_projects_alter_adds_world_id():
    """G4 (world-level project) — world_id binds a world's dedicated
    knowledge partition to its bible book. Additive nullable column +
    partial index; FK-by-convention to book-service worlds.id (cross-DB,
    no SQL FK). Idempotent ADD COLUMN IF NOT EXISTS."""
    assert "ADD COLUMN IF NOT EXISTS world_id UUID" in DDL
    assert (
        "idx_knowledge_projects_world\n  ON knowledge_projects(world_id) "
        "WHERE world_id IS NOT NULL" in DDL
    )
    # cross-DB convention: no SQL FK to a worlds table (it lives in book-service)
    assert "REFERENCES worlds" not in DDL


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

    # Strip `-- ...` line comments FIRST — a comment mentioning "CREATE TABLE" in prose (e.g. "the
    # CREATE TABLE above only runs on a fresh DB") is not a statement and must not trip the scan
    # (the hygiene-grep-matches-comments false-positive class).
    ddl_no_comments = re.sub(r"--[^\n]*", "", DDL)

    bare_create_table = re.findall(
        r"CREATE TABLE (?!IF NOT EXISTS)", ddl_no_comments
    )
    assert bare_create_table == [], f"non-idempotent CREATE TABLE: {bare_create_table}"

    bare_create_index = re.findall(
        r"CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", ddl_no_comments
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


def test_knowledge_projects_embedding_provider_id_dropped():
    """D-EMB-CLEANUP-01: the K12.3 embedding_provider_id column on
    knowledge_projects was never populated/read/plumbed (not in
    _SELECT_COLS, every writer passed None). The cycle-3 fix retired
    the logical-name concept and kept embedding_model + a separate
    embedding_dimension column, so this column was vestigial.

    Regression-lock: assert (a) the DROP COLUMN block is present in DDL
    on knowledge_projects and (b) the SAME-NAMED column on
    project_embedding_benchmark_runs (a different, actively-used table)
    is NOT touched — defense against future cleanups that conflate the
    two columns by name."""
    # (a) drop block present on knowledge_projects.
    assert (
        "ALTER TABLE knowledge_projects" in DDL
        and "DROP COLUMN IF EXISTS embedding_provider_id" in DDL
    ), "knowledge_projects.embedding_provider_id DROP block missing"
    # (b) The benchmark_runs column is still alive. Use the same regex
    # scope as test_benchmark_runs_no_cross_db_fk_on_provider — find the
    # CREATE TABLE body and assert the column is declared inside it.
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS project_embedding_benchmark_runs\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None, "benchmark_runs table missing — wrong cleanup target"
    body = m.group(1)
    assert any(
        "embedding_provider_id" in line for line in body.splitlines()
    ), "benchmark_runs.embedding_provider_id was wrongly dropped"


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


# ── C14b — sweeper_state resumable-cursor table ────────────────────


def test_sweeper_state_table_present():
    """C14b — `sweeper_state` wraps a resumable per-user cursor for
    tenant-wide offline sweepers (reconcile_evidence_count_scheduler
    today; future sweepers keyed on their own sweeper_name PK).
    Regression-lock against a migration that drops the table."""
    assert "CREATE TABLE IF NOT EXISTS sweeper_state" in DDL


def test_sweeper_state_schema_shape():
    """C14b — scoped columns: sweeper_name TEXT PK, last_user_id UUID
    (nullable for 'cursor cleared' state), last_scope JSONB NOT NULL
    DEFAULT '{}' (escape hatch for per-user-per-sub-scope iteration),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS sweeper_state\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None, "sweeper_state table body not found"
    body = m.group(1)
    assert "sweeper_name  TEXT PRIMARY KEY" in body
    assert "last_user_id  UUID" in body
    assert "last_scope    JSONB NOT NULL DEFAULT '{}'::jsonb" in body
    assert "updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()" in body


def test_sweeper_state_no_cross_db_fk():
    """C14b — `last_user_id` has no FK on users (users table lives in
    auth-service; cross-DB FKs forbidden). Repo tests exercise the
    upsert without a FK-violation path."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS sweeper_state\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    # No `REFERENCES` clause anywhere in the body.
    assert "REFERENCES" not in body, (
        "sweeper_state must not declare an FK to users "
        "(cross-DB forbidden)"
    )


# ── C16-BUILD — knowledge_summary_spending table ───────────────────


def test_summary_spending_table_present():
    """C16 closes D-K20α-01 BUILD-blocker. Regression-lock against
    a future migration that drops the table."""
    assert "CREATE TABLE IF NOT EXISTS knowledge_summary_spending" in DDL


def test_summary_spending_check_constraint_global_only():
    """C16-BUILD CLARIFY decision Q1/Option α — `scope_type` restricted
    to 'global' only (project-scope regen reuses K16.11). Adding new
    scope values requires migrating both the CHECK and
    summary_spending.py's ScopeType Literal in one PR."""
    assert "scope_type   TEXT NOT NULL CHECK (scope_type IN ('global'))" in DDL


def test_summary_spending_pk_includes_month_key():
    """PK shape (user_id, scope_type, month_key) — month rollover is
    in-place via new-row insert (a new month_key creates a new row,
    no UPDATE chain). Same pattern as sweeper_state."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS knowledge_summary_spending\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None, "knowledge_summary_spending table body not found"
    body = m.group(1)
    assert "PRIMARY KEY (user_id, scope_type, month_key)" in body


def test_summary_spending_no_cross_db_fk():
    """No FK on user_id — users live in auth-service (cross-DB
    forbidden convention shared across all knowledge-service tables)."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS knowledge_summary_spending\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert "REFERENCES" not in body, (
        "knowledge_summary_spending must not declare an FK to users "
        "(cross-DB forbidden)"
    )


def test_summary_spending_user_month_index():
    """check_user_monthly_budget hot path: SUM(spent_usd) WHERE
    user_id=$1 AND month_key=$2. Composite index covers it."""
    assert "idx_summary_spending_user_month" in DDL
    assert "ON knowledge_summary_spending(user_id, month_key)" in DDL


# ── C17 entity_alias_map regression locks ──────────────────────────


def test_entity_alias_map_table_present():
    """Source-scan lock for the C17 alias-redirect table. A future
    migration that drops or renames it would silently break post-merge
    extraction redirect — the lookup gates on this exact table name."""
    assert "CREATE TABLE IF NOT EXISTS entity_alias_map" in DDL


def test_entity_alias_map_pk_shape():
    """Composite PK = covering index for the resolver hot path
    (lookup-before-SHA-hash on every extracted entity)."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS entity_alias_map\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None, "entity_alias_map table body not found"
    body = m.group(1)
    assert (
        "PRIMARY KEY (user_id, project_scope, kind, canonical_alias)"
        in body
    )


def test_entity_alias_map_check_constraint_on_reason():
    """CHECK locks reason vocabulary in sync with the Pydantic Literal
    in entity_alias_map.py (closed enum). Adding a value requires
    coordinated update of both."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS entity_alias_map\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert "CHECK (reason IN ('merge', 'backfill'))" in body


def test_entity_alias_map_no_cross_db_fk():
    """No FK on user_id (auth-service) or target_entity_id (Neo4j) —
    cross-DB references forbidden."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS entity_alias_map\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert "REFERENCES" not in body


def test_entity_alias_map_target_index():
    """Reverse-lookup index for list_for_entity (FE display + audit)."""
    assert "idx_entity_alias_map_target" in DDL
    assert "ON entity_alias_map(target_entity_id)" in DDL


# ── K21-C — memory_remember confirmation gate + pending-facts table ────


def test_projects_alter_adds_memory_remember_confirm():
    """K21-C (design D4) — the per-project memory_remember confirmation
    gate. NOT NULL DEFAULT false so it is OPT-IN: a project row that
    predates the column reads back off and keeps writing facts directly
    (the model default in models.py is the other half of that
    contract). Idempotent ADD COLUMN IF NOT EXISTS so run_migrations
    stays safe on every startup."""
    assert (
        "ADD COLUMN IF NOT EXISTS memory_remember_confirm "
        "BOOLEAN NOT NULL DEFAULT false" in DDL
    )


def test_pending_facts_table_present():
    """K21-C (design D5) — knowledge_pending_facts is the transient
    queue for memory_remember facts awaiting user confirmation. A
    future migration that drops or renames it would silently break the
    confirm/reject flow — the repo + endpoints gate on this exact
    table name."""
    assert "CREATE TABLE IF NOT EXISTS knowledge_pending_facts" in DDL


def test_pending_facts_schema_shape():
    """K21-C (design D5) — scoped columns: pending_fact_id UUID PK
    (uuidv7), user_id UUID NOT NULL, project_id UUID nullable
    (no-project chats can queue), session_id TEXT NULLABLE (WS-2.1 — a
    DIARY fact has no chat session), fact_type TEXT NOT NULL, fact_text
    TEXT NOT NULL, created_at TIMESTAMPTZ."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS knowledge_pending_facts\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None, "knowledge_pending_facts table body not found"
    body = m.group(1)
    assert "pending_fact_id  UUID PRIMARY KEY DEFAULT uuidv7()" in body
    assert "user_id          UUID NOT NULL" in body
    # project_id nullable — a no-project chat can still queue a fact.
    assert "project_id       UUID," in body
    # WS-2.1 — session_id is NULLABLE now (a diary fact has no session). It must NOT be NOT NULL.
    assert "session_id       TEXT," in body
    assert "session_id       TEXT NOT NULL" not in body
    assert "fact_type        TEXT NOT NULL" in body
    assert "fact_text        TEXT NOT NULL" in body
    assert "created_at       TIMESTAMPTZ NOT NULL DEFAULT now()" in body
    # WS-2.2 — the structured s/p/o + event_date + provenance + dedup + tombstone are added by later
    # ALTER/CREATE statements (outside this CREATE TABLE body, which only runs on a fresh DB).
    assert "ADD COLUMN IF NOT EXISTS subject" in DDL
    assert "ADD COLUMN IF NOT EXISTS event_date  DATE" in DDL
    assert "ADD COLUMN IF NOT EXISTS provenance" in DDL
    assert "CREATE TABLE IF NOT EXISTS knowledge_rejected_facts" in DDL


def test_pending_facts_fact_type_check_constraint():
    """K21-C — fact_type CHECK locks the vocabulary in sync with the
    Neo4j FactType closed enum + the PendingFact Pydantic model. A
    drift would let an unknown type reach merge_fact's own validation
    and 500. WS-2.1 added 'statement' (the diary's coarse fact kind)."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS knowledge_pending_facts\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert (
        "CHECK (fact_type IN ('decision','preference','milestone','negation','statement'))"
        in body
    )
    # The idempotent widen (for an already-migrated DB) must ADD the same 5-value CHECK.
    assert "'negation','statement'))" in DDL


def test_pending_facts_no_cross_db_fk():
    """K21-C — no FK on user_id (auth-service, cross-DB). project_id is
    intentionally FK-free too: it is nullable and the public endpoints
    enforce authority via user_id, so an in-DB FK buys nothing here."""
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS knowledge_pending_facts\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert "REFERENCES" not in body


def test_pending_facts_user_list_index():
    """K21-C — list path is WHERE user_id=$1 [AND session_id=$2]
    ORDER BY created_at. The (user_id, created_at) composite index
    serves both the all-sessions and per-session variants."""
    assert "idx_knowledge_pending_facts_user" in DDL
    assert "ON knowledge_pending_facts(user_id, created_at)" in DDL


def test_event_text_translations_table_present():
    """KG-TL M3 — the on-demand event-text translation cache. Glossary-shaped:
    (event_id, field, language_code) PK, machine|verified confidence, source_hash
    guard, no cross-DB FK (event_id is a Neo4j node id)."""
    assert "CREATE TABLE IF NOT EXISTS event_text_translations" in DDL
    assert "PRIMARY KEY (event_id, field, language_code)" in DDL
    assert "CHECK (field IN ('summary','time_cue','title'))" in DDL
    assert "CHECK (confidence IN ('machine','verified'))" in DDL


def test_event_text_translations_no_cross_db_fk_and_purge_index():
    import re
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS event_text_translations\s*\((.*?)\);",
        DDL, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    # event_id is a Neo4j node id; user_id/project_id are cross-DB → no FK.
    assert "REFERENCES" not in body
    assert "source_hash" in body
    # AC-T7 purge-cascade lookup by project.
    assert "idx_event_text_translations_project" in DDL
