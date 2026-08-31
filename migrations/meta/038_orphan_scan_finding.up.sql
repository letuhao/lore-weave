-- 038 — orphan_scan_finding (W5-REMEDIATE).
--
-- WHY NOT `reality_close_audit`, WHICH R13 NAMES
-- ----------------------------------------------
-- `R13 §12L` says marked-partial rows get a `reality_close_audit` row with
-- reason `orphan_partial_provision`. The table cannot hold one, and this was
-- found by reading the schema rather than the design:
--
--   * `event_type` is a CLOSED enum of six CLOSE-lifecycle values
--     (close_initiated … dropped). `orphan_partial_provision` is not among
--     them, so the design doc and the constraint have disagreed since 005.
--   * `reality_id` is NOT NULL — and an UNTRACKED DATABASE, the finding class
--     that matters most (capacity counts registry rows, so a database no row
--     claims is invisible to the planner), has no reality by definition.
--
-- Widening that enum and nulling that column would turn a close-lifecycle audit
-- into a general-purpose one. These are not close events; they are scan
-- results.
--
-- SHAPE: STATE, NOT HISTORY — the `projection_drift_state` pattern
-- ---------------------------------------------------------------
-- Keyed by the DATABASE, because that is the one thing every finding class
-- names. Upserted per scan, so a persistent orphan is one row that ages rather
-- than a row per run; `first_seen_at` is what tells an operator whether this
-- appeared minutes or weeks ago. A finding that clears is DELETED — the table
-- answers "what is wrong now", and the record of a reality that genuinely
-- closed is `reality_close_audit`'s job.
--
-- THREE CONSTRAINTS, EACH REACHABLE
-- ---------------------------------
-- The consistency rule is written as two implications with DISJOINT
-- antecedents, so an unknown class satisfies both and falls through to the
-- enum. Migration 036's first draft wrote the equivalent rule as one
-- disjunction and thereby made its enum unreachable — a check that cannot fire
-- (`NV-1`, and its hardest shape: an adjacent decision defeating it). The
-- binding constraint for each malformed row:
--
--   ('orphan_untracked_database', <uuid>)  -> untracked_has_no_reality
--   ('orphan_partial_provision',  NULL)    -> tracked_has_a_reality
--   ('wizard', NULL) and ('wizard', <uuid>) -> class_enum
--
-- @pii_sensitivity: none — no user reference and no user-authored content. The
--   columns are a shard hostname, a generated database name, a reality id and a
--   finding class. `detail` is scanner-generated triage context (a status, an
--   age in hours, a boolean); nothing operator- or user-authored reaches it, and
--   the scanner is the only writer.
-- @retention_class: operational_state
-- @retention_hot: until_the_finding_clears — the scanner DELETEs a row the
--   moment the condition it describes is gone, so retention is bounded by the
--   problem's lifetime rather than by a clock.
-- @erasure_method: not_applicable — nothing here identifies a person, so a user
--   erasure has nothing to remove. Deliberately NOT a hard_delete claim: an
--   erasure method naming a deleter that does not exist is the "promise nothing
--   keeps" that migration 036 shipped and `TestMetaMigrationsDeclareAn
--   ImplementedErasure` now catches.
-- @legal_basis: legitimate_interest (operating the platform)

CREATE TABLE IF NOT EXISTS orphan_scan_finding (
    shard_host    TEXT        NOT NULL,
    db_name       TEXT        NOT NULL,
    -- NULL exactly when the finding is an untracked database.
    reality_id    UUID        NULL,
    finding_class TEXT        NOT NULL,
    -- Operator-facing context (age, status, whether the database exists).
    -- Deliberately unconstrained: it is a human-readable detail, never a
    -- second source of truth for anything the columns above already carry.
    detail        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT orphan_scan_finding_pkey PRIMARY KEY (shard_host, db_name),

    CONSTRAINT orphan_scan_finding_class_enum CHECK (
        finding_class IN (
            'orphan_partial_provision',
            'orphan_missing_database',
            'orphan_untracked_database',
            'orphan_drop_eligible'
        )
    ),

    -- An untracked database has no reality. That is what makes it untracked.
    CONSTRAINT orphan_scan_finding_untracked_has_no_reality CHECK (
        finding_class <> 'orphan_untracked_database' OR reality_id IS NULL
    ),

    -- Every other class names a registry row, so it must carry its id.
    -- Antecedent is the explicit three-way list, NOT the negation of the class
    -- above, so an unknown class satisfies this and reaches the enum.
    CONSTRAINT orphan_scan_finding_tracked_has_a_reality CHECK (
        finding_class NOT IN (
            'orphan_partial_provision',
            'orphan_missing_database',
            'orphan_drop_eligible'
        ) OR reality_id IS NOT NULL
    )
);

-- "What is wrong on this shard, oldest first" — the reaper's worklist.
CREATE INDEX IF NOT EXISTS idx_orphan_scan_finding_shard_first_seen
    ON orphan_scan_finding (shard_host, first_seen_at);

COMMENT ON TABLE orphan_scan_finding IS
    'Current output of orphan_scanner: what is wrong on a shard right now. Upserted per scan, rows deleted when the finding clears. Not an event log — see reality_close_audit for close-lifecycle history.';
COMMENT ON COLUMN orphan_scan_finding.reality_id IS
    'NULL iff finding_class = orphan_untracked_database (a database no registry row claims).';
