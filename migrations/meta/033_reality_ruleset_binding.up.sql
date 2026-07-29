-- 033_reality_ruleset_binding.up.sql
-- Q1 B2 — RLS-A3 early binding, durable: which resolved ruleset a reality is
-- bound to, per epoch, append-only.
-- Source: docs/03_planning/LLM_MMO_RPG/16_ruleset_loader.md §12 (RLS-A3/A13/D6/D18)
--       + docs/03_planning/LLM_MMO_RPG/35_quantity_architecture.md §4.6 (QTY-D9) / §13.2 (QTY-Q6)
-- Written by: whoever creates a reality, or advances its ruleset epoch, via
--   contracts/meta MetaWrite() (I8) — never a direct INSERT.
-- Read by: every node at island Cold -> Hot (doc 16 §12's right-hand column).
--
-- @pii_sensitivity: none (reality_id + a content digest; no user data)
-- @retention_class: system_config
-- @retention_hot: indefinite
-- @erasure_method: retain_legal
-- @legal_basis: legitimate_interest
--
-- Append-only, and enforced by a TRIGGER rather than only by REVOKE.
--
--
-- ── WHY THERE IS NO SEPARATE ORDINAL-ASSIGNMENT LEDGER (answers QTY-Q6) ──────
--
-- QTY-A5 says a declared quantity's ordinal is "never reused on removal", which
-- reads like it implies a durable ordinal ledger. It does not, and building one
-- would be a mistake:
--
--   The ordinal -> identity assignment for epoch N IS the quantity table inside
--   ruleset_N, which is content-addressed, immutable and already durable
--   (RLS-D6/D18). A separate ledger table would be a COPY OF HASHED BYTES INTO
--   UNHASHED ONES — and a copy that is not itself covered by the digest can
--   drift from what the digest says, which is the one thing the digest exists
--   to make impossible.
--
-- What is genuinely missing is not the assignment, it is the HISTORY: to honour
-- never-reuse at an epoch switch you need every ordinal this reality has EVER
-- assigned, not just the ones its current ruleset still declares. That is why
-- this table is one row PER EPOCH and append-only, rather than a mutable
-- `current_ruleset_digest` column on reality_registry. The high-water ordinal is
-- then `max(n)` over the rulesets of all prior epochs — recomputable from the
-- content store, and impossible to disagree with the bytes it is derived from.
--
-- The corollary is that append-only here is LOAD-BEARING, not hygiene: an UPDATE
-- that rewrote an epoch's digest, or a DELETE that dropped an epoch, would erase
-- ordinals that actor state and event payloads still refer to by number.
--
-- ── TENANCY (QTY-D9) ────────────────────────────────────────────────────────
-- Tier: per-reality. Scope key: reality_id. There is no shared row and no global
-- quantity vocabulary (RLS-A6 — identical strings across realities are unrelated
-- by design), so there is nothing here a user could mutate on another's behalf.

CREATE TABLE IF NOT EXISTS reality_ruleset_binding (
    reality_id      UUID            NOT NULL,

    -- RLS-A13: ORDERING, not identity. The first binding is epoch 1, matching
    -- doc 16 §12's "assign epoch 1". Monotonic and gapless per reality (trigger
    -- below) so "all prior epochs" is a range and not a set to be discovered.
    epoch           INT             NOT NULL,

    -- The resolved ruleset's BLAKE3 content digest, 64 lowercase hex. This is
    -- the only thing the load path needs: everything else is fetched from the
    -- content-addressed store by it. Load does NOT re-resolve the layer files.
    ruleset_digest  TEXT            NOT NULL,

    -- Why this epoch exists. Epoch 1 is "reality created"; later epochs carry
    -- the reason the rules changed, which is the human half of the ordered
    -- event doc 16 §9 requires.
    reason          TEXT            NOT NULL,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    PRIMARY KEY (reality_id, epoch),

    -- Shadowed by the gapless trigger for every input a client can send, and
    -- kept anyway because the trigger is not the last line: under
    -- `session_replication_role = replica` (pg_restore --disable-triggers,
    -- logical-replication apply) ORIGIN triggers do not fire and a CHECK still
    -- does. Proven reachable in exactly that mode by
    -- scripts/reality-binding-migration-smoke.sh, rather than asserted — a
    -- constraint nobody has watched fail is a claim, not a guard.
    CONSTRAINT reality_ruleset_binding_epoch_positive CHECK (epoch >= 1),
    CONSTRAINT reality_ruleset_binding_digest_format CHECK (
        ruleset_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT reality_ruleset_binding_reason_nonempty CHECK (length(reason) > 0)
);

-- The load path's only query: "the newest binding for this reality".
CREATE INDEX IF NOT EXISTS idx_reality_ruleset_binding_current
    ON reality_ruleset_binding (reality_id, epoch DESC);

-- Cheap answer to "which realities are running these exact rules?" — the
-- question a rules bug forces someone to ask under time pressure.
CREATE INDEX IF NOT EXISTS idx_reality_ruleset_binding_digest
    ON reality_ruleset_binding (ruleset_digest);

-- ── Append-only + gapless, enforced for EVERY role ──────────────────────────
--
-- The REVOKE below is the repo's usual pattern (see 025_scaling_events), but on
-- its own it would be a guard that does not exist in development: the dev stack
-- has no `app_service_role`, so the REVOKE is skipped and every dev connection
-- keeps UPDATE and DELETE. A trigger holds against every role in every
-- environment, including the superuser a migration runs as, which is the only
-- form in which this guard can be tested where it is written.
--
-- …and the trigger is ENABLE ALWAYS, which was NOT the first draft. An ordinary
-- trigger is an ORIGIN trigger, and `SET session_replication_role = replica` —
-- what `pg_restore --disable-triggers` and logical-replication apply both use —
-- stops ORIGIN triggers firing. Measured on this exact table before the fix: the
-- UPDATE rewrote the digest and the DELETE removed the row, both silently, both
-- reported by the guard as prevented. A guard whose bypass is one documented GUC
-- away is not append-only, it is append-only-by-convention. ENABLE ALWAYS costs
-- nothing here because INSERT is the only operation this table has, so there is
-- no legitimate restore or replication stream carrying an UPDATE or a DELETE for
-- it to refuse.
CREATE OR REPLACE FUNCTION reality_ruleset_binding_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'reality_ruleset_binding is append-only: % refused. A reality''s rules '
        'change by INSERTing the NEXT epoch (RLS-A3 binds once; doc 16 §9 makes '
        'the switch an ordered event). Rewriting or removing an epoch erases '
        'quantity ordinals that committed events still refer to by number '
        '(QTY-A5).',
        TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reality_ruleset_binding_append_only_trg ON reality_ruleset_binding;
CREATE TRIGGER reality_ruleset_binding_append_only_trg
    BEFORE UPDATE OR DELETE ON reality_ruleset_binding
    FOR EACH ROW EXECUTE FUNCTION reality_ruleset_binding_append_only();

ALTER TABLE reality_ruleset_binding
    ENABLE ALWAYS TRIGGER reality_ruleset_binding_append_only_trg;

-- Epoch 1 first, then +1 each time. A row that arrived out of order would make
-- "every prior epoch" a set with holes in it, and the never-reuse high-water
-- mark would be computed over rulesets that were never in force.
--
-- Conservative under concurrency by construction: two racing inserts either
-- collide on the primary key, or the later-numbered one sees a stale maximum
-- and is REFUSED. A race can produce a false rejection, never a false accept.
CREATE OR REPLACE FUNCTION reality_ruleset_binding_epoch_is_next()
RETURNS TRIGGER AS $$
DECLARE
    prev INT;
BEGIN
    SELECT max(epoch) INTO prev
      FROM reality_ruleset_binding
     WHERE reality_id = NEW.reality_id;

    IF prev IS NULL THEN
        IF NEW.epoch <> 1 THEN
            RAISE EXCEPTION
                'reality % has no binding yet, so its first epoch must be 1, not %'
                ' (doc 16 §12: creation assigns epoch 1)',
                NEW.reality_id, NEW.epoch;
        END IF;
    ELSIF NEW.epoch <> prev + 1 THEN
        RAISE EXCEPTION
            'reality % is at epoch %, so the next binding must be epoch %, not %'
            ' — epochs are gapless so that "every prior epoch" is a range',
            NEW.reality_id, prev, prev + 1, NEW.epoch;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reality_ruleset_binding_epoch_is_next_trg ON reality_ruleset_binding;
CREATE TRIGGER reality_ruleset_binding_epoch_is_next_trg
    BEFORE INSERT ON reality_ruleset_binding
    FOR EACH ROW EXECUTE FUNCTION reality_ruleset_binding_epoch_is_next();

-- Defense in depth, and consistency with the other append-only meta tables.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE reality_ruleset_binding FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE reality_ruleset_binding FROM app_admin_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_admin_role does not exist (dev stack); skipping REVOKE';
END $$;

COMMENT ON TABLE reality_ruleset_binding IS
    'Q1 B2 / RLS-A3 — per-epoch reality -> resolved-ruleset binding. Append-only '
    '(trigger-enforced): an epoch''s digest is what the never-reuse high-water '
    'ordinal (QTY-A5) is recomputed from. Answers QTY-Q6: no separate ordinal '
    'ledger — the assignment lives in the hashed ruleset, only the HISTORY is here.';
