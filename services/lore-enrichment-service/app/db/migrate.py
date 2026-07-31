"""Idempotent Postgres DDL for loreweave_lore_enrichment (RAID C2).

Follows the platform house style established by knowledge-service
(`app/db/migrate.py`): a single DDL string with CREATE TABLE IF NOT EXISTS
+ DO $$ blocks for constraint adds, applied on every startup via
`run_migrations(pool)`. No Alembic/goose/flyway — bare SQL via asyncpg.

A matching `run_down_migrations(pool)` drops everything in reverse FK
dependency order (proposal → job → template → grounding_ref →
corpus_chunk → corpus), plus the trigger function, so the up→down→up
round-trip is clean and idempotent (RAID C2/C10 acceptance gate).

H0 INVARIANT (enriched lore != canon) is enforced at the SCHEMA level on
`enrichment_proposal`:
  * `confidence` CHECK (> 0 AND < 1.0) — an enriched proposal can NEVER
    carry canon confidence (glossary canon = 1.0). No default that hits 1.0.
  * `origin` NOT NULL DEFAULT 'enrichment' — never defaults to canon, and a
    BEFORE UPDATE trigger forbids stripping/blanking it (immutable origin).
  * `review_status` CHECK restricts the lifecycle vocabulary; a BEFORE
    UPDATE trigger enforces the legal transition DAG
    (proposed → author_reviewing → approved → promoted | rejected) and the
    promote-only invariant: `promoted_entity_id/by/at` may be populated ONLY
    when status becomes 'promoted', and must be NULL in every other state.
  * Permanent origin markers (`promoted_from_proposal_id`,
    `original_technique`) travel with the row for lifetime traceability of
    "this canon was originally makeup" (OPEN_QUESTIONS_LOCKED H0).

Cross-database FKs are intentionally absent: `user_id` references
loreweave_auth.users, `project_id` mirrors knowledge-service's project
scope, `promoted_entity_id` references a glossary entity — all in other
databases. Validation of those is done in application code (Q3 scoping).
"""

import asyncpg

# ── Lifecycle transition DAG (single source of truth, kept in SQL below) ──
#   proposed         → author_reviewing | rejected
#   author_reviewing → approved | rejected | proposed   (kick-back allowed)
#   approved         → promoted | rejected | author_reviewing
#   promoted         → (terminal)
#   rejected         → (terminal)

DDL = """
-- ═══════════════════════════════════════════════════════════════
-- source_corpus
-- A licensed/owned grounding corpus (e.g. 封神演义, 山海经, Shang–Zhou
-- history). Technique-(b) retrieval (C10) ingests chunks of these and the
-- proposals cite them via cultural_grounding_ref. Per-user/per-project
-- scoped (Q3); no cross-DB FK on user_id.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS source_corpus (
  corpus_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id    UUID NOT NULL,                    -- scope (Q3); no FK (cross-DB)
  user_id       UUID NOT NULL,                    -- scope (Q3); no FK (cross-DB)
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL
    CHECK (kind IN ('fengshen','shanhaijing','history','other')),
  -- C17 WARN-1 (RAID c17 re-cook adversary): license DEFAULTs to 'unknown'
  -- (an INADMISSIBLE value) — fail CLOSED. An ingest that omits a license stamps
  -- 'unknown', which the default-deny licensing gate (app/strategies/licensing.py)
  -- REFUSES, so an un-tagged corpus (e.g. an operator ingesting copyrighted/news
  -- text and forgetting to tag it) can NEVER be silently re-cooked. A genuinely
  -- public-domain corpus must be tagged 'public-domain' EXPLICITLY at ingest. The
  -- earlier 'public-domain' default defeated the module-level default-deny one
  -- layer up (admit-by-omission); 'unknown' restores fail-closed at admission.
  license       TEXT NOT NULL DEFAULT 'unknown',
  provenance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT source_corpus_name_len CHECK (length(name) BETWEEN 1 AND 200)
);

CREATE INDEX IF NOT EXISTS idx_source_corpus_scope
  ON source_corpus(user_id, project_id);

-- ── C17 re-cook LICENSING gate (additive CHECK constraint) ───────────────────
-- Re-cook (technique (d)) takes REAL history/news/reference material and
-- re-contextualises it into the 商周/封神 setting; modern/news material is NOT
-- public-domain and carries a licensing liability. The re-cook strategy
-- (app/strategies/licensing.py) is default-deny: it admits ONLY 'public-domain'
-- / 'public_domain' / 'licensed' sources and REFUSES anything else. This CHECK
-- pins the column to the recognised vocabulary at the SCHEMA level so an
-- ingested corpus can never carry a free-text/garbage license that the
-- default-deny normaliser would silently treat as UNKNOWN. The C2 column DEFAULT
-- is 'unknown' (fail-closed, WARN-1) — an un-tagged corpus is REFUSED by re-cook;
-- the demo corpora (山海经, 封神演义, Shang–Zhou history) are genuinely public-domain
-- and must be tagged 'public-domain' EXPLICITLY at ingest to become re-cookable.
--   * unlicensed / copyrighted / restricted / unknown are PERSISTABLE (so a
--     source can be HONESTLY tagged as not-yet-licensed) but the re-cook
--     application gate REFUSES them — the DB records the truth, the app enforces
--     the policy.
-- Added in a DO $$ block (ADD CONSTRAINT has no IF NOT EXISTS) so it is
-- idempotent + brings an already-deployed table up to schema.
DO $license_chk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_corpus_license_vocab'
  ) THEN
    ALTER TABLE source_corpus
      ADD CONSTRAINT source_corpus_license_vocab
      CHECK (license IN (
        'public-domain', 'public_domain', 'licensed',
        'unlicensed', 'copyrighted', 'restricted', 'unknown'
      ));
  END IF;
END
$license_chk$;

-- ── C17 WARN-1: bring an ALREADY-DEPLOYED table to the fail-closed DEFAULT ────
-- CREATE TABLE IF NOT EXISTS above sets the 'unknown' default only on a FRESH
-- table; a table created before this fix keeps its old 'public-domain' default
-- (admit-by-omission). This idempotent ALTER COLUMN ... SET DEFAULT migrates it in
-- place so an ingest that omits a license fails CLOSED on the running DB too.
-- Existing rows are NOT rewritten (genuinely-PD demo corpora keep their explicit
-- tag); only the default for FUTURE un-tagged inserts changes.
ALTER TABLE source_corpus ALTER COLUMN license SET DEFAULT 'unknown';

-- ── C2 T5: SHARED reference library — project_id nullable (source_corpus) ─────
-- A corpus (and its chunks) with project_id = NULL is a SHARED, public-domain
-- reference corpus readable by ANY project (e.g. the original 封神演义 a fanfic
-- re-cooks, or a history corpus). Retrieval scopes `project_id = $proj OR
-- project_id IS NULL`. Per-project user corpora keep their project_id (unchanged).
-- Idempotent DROP NOT NULL (a no-op once already nullable). The CHUNK table's
-- matching ALTER lives AFTER its CREATE below (it must exist first — a from-scratch
-- migration ran the whole DDL top-to-bottom and a chunk ALTER here would reference a
-- not-yet-created table).
ALTER TABLE source_corpus ALTER COLUMN project_id DROP NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- source_corpus_chunk (RAID C10 — technique-(b) retrieval)
-- A deterministic CJK-aware chunk of a source_corpus text plus its
-- embedding vector. The embedding is obtained by REUSING knowledge-
-- service /internal/embed (provider-registry model_ref) — NEVER a
-- hardcoded model name. `embedding_model_ref` records the resolving
-- model_ref alongside the vector so a silent embedding-model change is
-- DETECTABLE (mixing incomparable vector spaces is a real bug class).
--
-- Vectors are stored as DOUBLE PRECISION[] (the platform does NOT enable
-- pgvector); similarity search is an in-process cosine scorer over a
-- project's chunks (lightweight, no vector-DB service, no heavy dep).
--
-- Idempotency: (corpus_id, chunk_index) is UNIQUE and `content_sha256`
-- lets re-ingest of identical text be a no-op (same text → same chunks,
-- no duplicates, no silent re-embed). Per-project scoped (Q3) via the
-- parent corpus; ON DELETE CASCADE purges chunks with their corpus.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS source_corpus_chunk (
  chunk_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  corpus_id       UUID NOT NULL
    REFERENCES source_corpus(corpus_id) ON DELETE CASCADE,
  project_id      UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)
  chunk_index     INT NOT NULL,                   -- 0-based ordinal (stable id)
  content         TEXT NOT NULL,                  -- the chunk text (CJK, UTF-8)
  content_sha256  TEXT NOT NULL,                  -- hash for idempotent re-ingest
  embedding       DOUBLE PRECISION[],             -- the vector (NULL until embedded)
  embedding_model_ref TEXT,                       -- resolving model_ref (drift guard)
  embedding_dim   INT,                            -- vector dimension (drift guard)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (corpus_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_source_corpus_chunk_corpus
  ON source_corpus_chunk(corpus_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_source_corpus_chunk_scope
  ON source_corpus_chunk(project_id);

-- ── C2 T5 (cont.): chunk project_id nullable — runs AFTER the CREATE above so a
-- from-scratch migration (full DDL top-to-bottom) doesn't ALTER a missing table.
-- Idempotent (no-op once already nullable); brings a deployed chunk table to schema.
ALTER TABLE source_corpus_chunk ALTER COLUMN project_id DROP NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- cultural_grounding_ref
-- The concrete citation anchor a proposal points at: a chunk/locator into
-- a source_corpus plus the excerpt text. C10 populates these; the proposal
-- references one via cultural_grounding_ref_id. ON DELETE CASCADE: purging
-- a corpus removes its anchors. (A proposal's FK to this is ON DELETE SET
-- NULL so a proposal survives anchor cleanup — see enrichment_proposal.)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS cultural_grounding_ref (
  grounding_ref_id UUID PRIMARY KEY DEFAULT uuidv7(),
  corpus_id        UUID NOT NULL
    REFERENCES source_corpus(corpus_id) ON DELETE CASCADE,
  project_id       UUID NOT NULL,                 -- scope (Q3); no FK (cross-DB)
  locator          TEXT NOT NULL,                 -- chapter/chunk/citation locator
  excerpt          TEXT NOT NULL,                 -- the quoted source text
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cultural_grounding_ref_corpus
  ON cultural_grounding_ref(corpus_id);

-- ═══════════════════════════════════════════════════════════════
-- enrichment_template
-- Schema-governed scaffold for an entity-kind: the dimension set to enrich
-- (e.g. location → 历史/地理/文化/features/inhabitants) plus a scaffold body.
-- Versioned so a re-cook can pin the template it was generated under.
-- Not scoped per-user: templates are service-level building blocks.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_template (
  template_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_kind   TEXT NOT NULL,                    -- e.g. 'location'
  dimension_set JSONB NOT NULL DEFAULT '[]'::jsonb,
  scaffold_body TEXT NOT NULL DEFAULT '',
  version       INT NOT NULL DEFAULT 1,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_kind, version)
);

-- ═══════════════════════════════════════════════════════════════
-- enrichment_job
-- One enrichment run for a project. Carries the per-job state machine and
-- cost guardrail fields (C8 owns the transitions; C2 only persists). Per-
-- user/per-project scoped (Q3). `technique` is the strategy id; no model
-- name is stored here (resolved via provider-registry — never hardcoded).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_job (
  job_id          UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id      UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)
  user_id         UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)
  status          TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','estimating','running','paused','completed','failed','cancelled')),
  technique       TEXT NOT NULL
    CHECK (technique IN ('template','retrieval','fabrication','recook','compose_draft')),
  entity_kind     TEXT,                           -- demo: 'location'
  book_id         UUID,                           -- glossary/book scope. Enrichment is
                                                  --   BOOK-bound (the GUI lives in the
                                                  --   book), so this is always set by the
                                                  --   GUI; project_id stays the GENERAL
                                                  --   scope. Nullable (cross-DB, no FK;
                                                  --   legacy rows predate it).
  -- D-JOURNEY-ENRICH-COST-UNITS: these are denominated in REAL TOKENS, not USD
  -- (the per-job cost-cap is a token count per the C1 PO ruling — see app/jobs/
  -- tokens.py / cost.py). The columns were originally misnamed `*_usd`; renamed to
  -- `*_tokens` (a guarded rename below brings already-deployed tables across).
  estimated_cost_tokens NUMERIC(14,2) NOT NULL DEFAULT 0,
  actual_cost_tokens    NUMERIC(14,2) NOT NULL DEFAULT 0,
  max_spend_tokens      NUMERIC(14,2),            -- token cost guardrail (C8)
  proposals_total    INT NOT NULL DEFAULT 0,
  error_message      TEXT,
  started_at      TIMESTAMPTZ,
  paused_at       TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_enrichment_job_scope
  ON enrichment_job(user_id, project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_enrichment_job_active
  ON enrichment_job(status)
  WHERE status IN ('pending','estimating','running','paused');

-- Unified Job Control Plane reconcile source: GET /internal/lore_enrichment/jobs?since=
-- filters enrichment_job by updated_at — index it so the periodic sweep isn't a seq-scan.
CREATE INDEX IF NOT EXISTS idx_enrichment_job_updated_at ON enrichment_job(updated_at);

-- ── D-JOURNEY-ENRICH-COST-UNITS: rename the misnamed *_usd cost columns to *_tokens
-- (they always held TOKEN counts per the C1 PO ruling, never dollars) AND widen them
-- (a token count can exceed the old USD-sized NUMERIC(10,4) ≈ 1M cap). Guarded so an
-- ALREADY-DEPLOYED table is brought across in place (CREATE TABLE IF NOT EXISTS skips
-- the new column names on it), and a FRESH table (already *_tokens) is a no-op. ──────
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='enrichment_job' AND column_name='estimated_cost_usd') THEN
    ALTER TABLE enrichment_job RENAME COLUMN estimated_cost_usd TO estimated_cost_tokens;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='enrichment_job' AND column_name='actual_cost_usd') THEN
    ALTER TABLE enrichment_job RENAME COLUMN actual_cost_usd TO actual_cost_tokens;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='enrichment_job' AND column_name='max_spend_usd') THEN
    ALTER TABLE enrichment_job RENAME COLUMN max_spend_usd TO max_spend_tokens;
  END IF;
END $$;

ALTER TABLE enrichment_job
  ALTER COLUMN estimated_cost_tokens TYPE NUMERIC(14,2),
  ALTER COLUMN actual_cost_tokens    TYPE NUMERIC(14,2),
  ALTER COLUMN max_spend_tokens      TYPE NUMERIC(14,2);

-- ── book scope (additive) ────────────────────────────────────────────────────
-- Enrichment is book-bound; persist the book_id so the review GUI can list a
-- book's jobs/proposals by their always-present book anchor (proposals join here
-- on job_id). project_id remains the GENERAL scope. ADD COLUMN IF NOT EXISTS
-- brings an already-deployed table up to schema (no data loss, no down-migration
-- needed); the index serves the GUI's (user, book) listing.
ALTER TABLE enrichment_job
  ADD COLUMN IF NOT EXISTS book_id UUID;

CREATE INDEX IF NOT EXISTS idx_enrichment_job_book
  ON enrichment_job(user_id, book_id, created_at DESC);

-- ── Compose slice 1: widen the technique vocabulary (+compose_draft) ──────────
-- Mode D (draft expansion) adds a 5th technique 'compose_draft' (tier P1). The
-- inline CHECK above only takes on a FRESH table; an ALREADY-DEPLOYED enrichment_job
-- keeps its old auto-named 4-value CHECK (CREATE TABLE IF NOT EXISTS skips it). This
-- idempotent block migrates a deployed table in place: drop the auto-named
-- enrichment_job_technique_check and add a named _technique_vocab carrying the
-- 5-value vocabulary. Guarded on NOT EXISTS(vocab) so it runs exactly once (no
-- per-startup re-validation churn). Mirrors the source_corpus_license_vocab precedent.
DO $job_tech_vocab$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'enrichment_job_technique_vocab'
  ) THEN
    ALTER TABLE enrichment_job DROP CONSTRAINT IF EXISTS enrichment_job_technique_check;
    ALTER TABLE enrichment_job
      ADD CONSTRAINT enrichment_job_technique_vocab
      CHECK (technique IN ('template','retrieval','fabrication','recook','compose_draft'));
  END IF;
END
$job_tech_vocab$;

-- ═══════════════════════════════════════════════════════════════
-- enrichment_job_request (F-C14-1 / 051) — the request payload needed to
-- RE-DRIVE a cost-cap-paused job from the background resume worker. One row
-- per job, written at create. Holds the targets + provider-registry model_ref
-- UUIDs (NOT secrets) + technique/params — NEVER any enriched/generated content
-- (H0: only the request shape, so the worker can rebuild the runner).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_job_request (
  job_id        UUID PRIMARY KEY
    REFERENCES enrichment_job(job_id) ON DELETE CASCADE,
  request_json  JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- enrichment_proposal — H0 CARRIER (enriched lore != canon)
-- ───────────────────────────────────────────────────────────────
-- The makeup-lore unit awaiting author review. EVERY column that makes it
-- visibly NON-canon is enforced here:
--   * confidence CHECK (> 0 AND < 1.0)  → can never look like canon (1.0)
--   * origin NOT NULL DEFAULT 'enrichment' (immutable via trigger)
--   * review_status lifecycle CHECK + transition trigger
--   * promoted_* populated ONLY at promote (trigger-enforced)
--   * promoted_from_proposal_id / original_technique = permanent origin
--     markers that survive promotion (lifetime "was-makeup" traceability)
-- Per-user/per-project scoped (Q3). job_id FK is in-DB (CASCADE); all other
-- references (promoted_entity_id → glossary, promoted_by → auth user) are
-- cross-DB and intentionally FK-less.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_proposal (
  proposal_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id          UUID NOT NULL
    REFERENCES enrichment_job(job_id) ON DELETE CASCADE,
  project_id      UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)
  user_id         UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)

  entity_kind     TEXT NOT NULL,                  -- e.g. 'location'
  target_ref      TEXT,                           -- the canon entity being enriched
  gap_ref         TEXT,                           -- per-gap dedupe discriminator
                                                  --   (target_ref or canonical_name).
                                                  --   UNIQUE(job_id, gap_ref) makes a
                                                  --   resume/re-run idempotent: the same
                                                  --   gap can persist only ONE proposal
                                                  --   per job (WARN-1 duplicate-proposal fix).
  canonical_name  TEXT,                           -- faithful entity NAME from the Gap
                                                  --   (H0: never makeup content). Used as
                                                  --   the anchor name when target_ref is NULL
                                                  --   (new-entity case) so enriched CONTENT
                                                  --   can never become the canon entity name.
  content         TEXT NOT NULL,                  -- generated lore (Chinese, source-faithful)

  -- ── H0 distinguishing columns ──────────────────────────────────────────
  origin          TEXT NOT NULL DEFAULT 'enrichment'
    CHECK (origin <> '' AND origin <> 'glossary'),   -- never authored-canon origin
  technique       TEXT NOT NULL
    CHECK (technique IN ('template','retrieval','fabrication','recook','compose_draft')),
  provenance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence      NUMERIC(4,3) NOT NULL
    CHECK (confidence > 0 AND confidence < 1.0),      -- H0: never canon (1.0)
  source_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  cultural_grounding_ref_id UUID
    REFERENCES cultural_grounding_ref(grounding_ref_id) ON DELETE SET NULL,

  -- ── lifecycle ──────────────────────────────────────────────────────────
  review_status   TEXT NOT NULL DEFAULT 'proposed'
    CHECK (review_status IN
      ('proposed','author_reviewing','approved','promoted','rejected')),

  -- ── write-back anchor (resolved at write-back, BEFORE/independent of promote) ──
  -- The glossary entity_id resolved/minted when the enriched facts were admitted
  -- to the KG QUARANTINED. Persisted so a retract of a quarantined-never-promoted
  -- proposal can still locate + recycle its anchor (FIX-3 / NIT-3). NOT trigger-
  -- guarded — it may be set in any state (it is not the promotion record).
  writeback_entity_id UUID,                        -- glossary entity (cross-DB, no FK)

  -- ── promotion record (populated ONLY at promote; trigger-enforced) ───────
  promoted_entity_id UUID,                         -- glossary entity (cross-DB, no FK)
  promoted_by        UUID,                         -- auth user (cross-DB, no FK)
  promoted_at        TIMESTAMPTZ,
  -- ── permanent origin markers (survive promotion — H0 lock) ───────────────
  promoted_from_proposal_id UUID,                  -- self-ref kept stable for audit
  original_technique        TEXT,                  -- snapshot of technique at promote

  rejected_reason TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── additive columns (idempotent — bring a pre-existing table up to schema) ──
-- ADD COLUMN IF NOT EXISTS so an already-deployed enrichment_proposal table
-- (created before canonical_name / writeback_entity_id existed) is migrated in
-- place on the next startup, with no data loss and no down-migration needed.
ALTER TABLE enrichment_proposal
  ADD COLUMN IF NOT EXISTS canonical_name TEXT;
ALTER TABLE enrichment_proposal
  ADD COLUMN IF NOT EXISTS writeback_entity_id UUID;
ALTER TABLE enrichment_proposal
  ADD COLUMN IF NOT EXISTS gap_ref TEXT;

-- Per-gap idempotency (WARN-1): at most ONE proposal per (job, gap). A resume
-- or re-run that re-processes an already-persisted gap is a no-op insert (the
-- store does ON CONFLICT DO NOTHING and reloads the existing row), so a job can
-- never DUPLICATE proposals. NULL gap_ref is never written by the runner; the
-- partial index ignores any legacy NULL rows so the constraint adds cleanly to
-- an already-deployed table.
CREATE UNIQUE INDEX IF NOT EXISTS uq_enrichment_proposal_job_gap
  ON enrichment_proposal(job_id, gap_ref)
  WHERE gap_ref IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_enrichment_proposal_job
  ON enrichment_proposal(job_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_enrichment_proposal_scope_status
  ON enrichment_proposal(user_id, project_id, review_status);

-- ── Compose slice 1: widen the proposal technique vocabulary (+compose_draft) ─
-- The runner persists technique=pipeline.technique_value(); a compose_draft (mode D)
-- proposal carries 'compose_draft'. Same idempotent in-place migration as the job
-- table above (drop the deployed auto-named _technique_check, add the 5-value
-- _technique_vocab; guarded NOT EXISTS so it runs once). H0 is untouched — origin
-- stays 'enrichment', confidence < 1.0; only the technique vocabulary widens.
DO $prop_tech_vocab$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'enrichment_proposal_technique_vocab'
  ) THEN
    ALTER TABLE enrichment_proposal DROP CONSTRAINT IF EXISTS enrichment_proposal_technique_check;
    ALTER TABLE enrichment_proposal
      ADD CONSTRAINT enrichment_proposal_technique_vocab
      CHECK (technique IN ('template','retrieval','fabrication','recook','compose_draft'));
  END IF;
END
$prop_tech_vocab$;

-- ═══════════════════════════════════════════════════════════════
-- H0 enforcement trigger — lifecycle DAG + promote-only + origin immutable
-- ───────────────────────────────────────────────────────────────
-- A CHECK constraint cannot see the prior row, so transition legality and
-- the promote-only invariant are enforced in a BEFORE UPDATE trigger. This
-- runs against the REAL DB in the round-trip test (no mock-only false-green).
-- ═══════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION enrichment_proposal_h0_guard()
RETURNS TRIGGER AS $h0$
BEGIN
  -- 1. origin is immutable and may never be blanked or set to canon.
  IF NEW.origin IS DISTINCT FROM OLD.origin THEN
    RAISE EXCEPTION 'H0 violation: origin is immutable (was %, got %)',
      OLD.origin, NEW.origin;
  END IF;

  -- 2. confidence may never reach canon (1.0). (CHECK also guards inserts.)
  IF NEW.confidence >= 1.0 THEN
    RAISE EXCEPTION 'H0 violation: confidence must stay < 1.0 (got %)',
      NEW.confidence;
  END IF;

  -- 3. legal transition DAG.
  IF NEW.review_status IS DISTINCT FROM OLD.review_status THEN
    IF NOT (
      (OLD.review_status = 'proposed'
         AND NEW.review_status IN ('author_reviewing','rejected'))
      OR (OLD.review_status = 'author_reviewing'
         AND NEW.review_status IN ('approved','rejected','proposed'))
      OR (OLD.review_status = 'approved'
         AND NEW.review_status IN ('promoted','rejected','author_reviewing'))
    ) THEN
      RAISE EXCEPTION 'H0 violation: illegal review_status transition % -> %',
        OLD.review_status, NEW.review_status;
    END IF;
  END IF;

  -- 4. promote-only invariant for the promotion record.
  IF NEW.review_status = 'promoted' THEN
    IF NEW.promoted_entity_id IS NULL
       OR NEW.promoted_by IS NULL
       OR NEW.promoted_at IS NULL THEN
      RAISE EXCEPTION
        'H0 violation: promoted requires promoted_entity_id/by/at';
    END IF;
    -- stamp the permanent origin markers at promote time.
    IF NEW.promoted_from_proposal_id IS NULL THEN
      NEW.promoted_from_proposal_id := NEW.proposal_id;
    END IF;
    IF NEW.original_technique IS NULL THEN
      NEW.original_technique := NEW.technique;
    END IF;
  ELSE
    -- not promoted → the promotion record MUST be empty.
    IF NEW.promoted_entity_id IS NOT NULL
       OR NEW.promoted_by IS NOT NULL
       OR NEW.promoted_at IS NOT NULL THEN
      RAISE EXCEPTION
        'H0 violation: promoted_* may only be set when review_status=promoted';
    END IF;
  END IF;

  NEW.updated_at := now();
  RETURN NEW;
END;
$h0$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enrichment_proposal_h0 ON enrichment_proposal;
CREATE TRIGGER trg_enrichment_proposal_h0
  BEFORE UPDATE ON enrichment_proposal
  FOR EACH ROW EXECUTE FUNCTION enrichment_proposal_h0_guard();

-- ═══════════════════════════════════════════════════════════════
-- enrichment_eval_runs (RAID C15 — eval framework, ADDITIVE)
-- ───────────────────────────────────────────────────────────────
-- One row per enrichment-eval run: the weighted sub-scores
-- (schema/canon/anachronism/provenance/usefulness — cultural-fidelity), the
-- weighted composite, the judge-ENSEMBLE agreement (Fleiss κ), and the GATE
-- decision (passed). Mirrors knowledge-service project_embedding_benchmark_runs
-- (load→run→persist to a runs table): immutable scorecard rows, longitudinal
-- improvement space, queryable for "did the latest run for this suite pass?".
--
-- The GATE that guards C16 (fabrication)/C17 (re-cook) reads the LATEST passed
-- row for a (project, suite_version) so P2/P3 cannot activate below threshold.
-- Per-user/per-project scoped (Q3); no model name stored (judges resolve via
-- provider-registry by model_ref — recorded as opaque refs in raw_report only).
-- ADDITIVE: a fresh CREATE TABLE IF NOT EXISTS, no change to any prior table.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_eval_runs (
  eval_run_id      UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id       UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)
  user_id          UUID NOT NULL,                  -- scope (Q3); no FK (cross-DB)
  run_id           TEXT NOT NULL,                  -- caller-supplied id (default ts)
  suite_version    TEXT NOT NULL,                  -- e.g. 'enrichment-v1'
  baseline_version TEXT,                           -- baseline diffed against (nullable)
  n_proposals      INT NOT NULL DEFAULT 0,
  -- weighted sub-scores (each 0..100)
  schema_score        NUMERIC(5,1) NOT NULL DEFAULT 0,
  canon_score         NUMERIC(5,1) NOT NULL DEFAULT 0,
  anachronism_score   NUMERIC(5,1) NOT NULL DEFAULT 0,
  provenance_score    NUMERIC(5,1) NOT NULL DEFAULT 0,
  usefulness_score    NUMERIC(5,1) NOT NULL DEFAULT 0,
  composite        NUMERIC(6,2) NOT NULL DEFAULT 0,
  fleiss_kappa     NUMERIC(5,3),                   -- judge agreement (nullable: <2 judges)
  judge_ensemble_acceptable BOOLEAN NOT NULL DEFAULT false,
  passed           BOOLEAN NOT NULL DEFAULT false, -- the GATE decision
  raw_report       JSONB NOT NULL DEFAULT '{}'::jsonb,  -- full scorecard + gate reasons
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, suite_version, run_id)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_eval_runs_latest
  ON enrichment_eval_runs(project_id, suite_version, created_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- enrichment_book_profile (de-bias C1 — per-book worldview)
-- ───────────────────────────────────────────────────────────────
-- The per-book "enrichment profile" that DE-BIASES generation + verify away
-- from the hardcoded 封神演义 / 商周 / 中文 / 地点 universe. Read at runtime by
-- the prompt builders, the dimension resolver, and the anachronism check; an
-- UNSET book resolves to a NEUTRAL default (language=auto, era OFF) in app code
-- (no row required). Per-BOOK (worldview is a book property); no FK (book_id is
-- cross-DB, like every other id here). ADDITIVE: fresh CREATE TABLE IF NOT EXISTS.
--   * era_policy NULL  → no era constraint → anachronism check OFF (a sci-fi book
--     is never auto-flagged for "modern tech").
--   * anachronism_markers NULL → derive from era_policy (advisory) / OFF; the
--     Fengshen seed populates it with the curated 商周 denylist.
--   * dimension_overrides → per-kind add/remove/relabel/reweight (the dynamic
--     dimension layer); free JSONB (no kind/dimension vocab CHECK — both dynamic).
--   * profile_source → seed | ai_suggested | manual (provenance of the values).
-- No CHECK on language/kind/dimension: they are author/profile-extensible (KB3).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_book_profile (
  book_id              UUID PRIMARY KEY,                 -- the book (cross-DB, no FK)
  worldview            TEXT NOT NULL DEFAULT '',
  language             TEXT NOT NULL DEFAULT 'auto',
  era_policy           TEXT,                             -- NULL = anachronism OFF
  voice                TEXT,
  anachronism_markers  JSONB,                            -- NULL = none; [{term,reason}]
  dimension_overrides  JSONB NOT NULL DEFAULT '{}'::jsonb,
  profile_source       TEXT NOT NULL DEFAULT 'manual'
    CHECK (profile_source IN ('seed','ai_suggested','manual')),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- enrichment_upload (Compose slice 3 — mode F attach-files)
-- ───────────────────────────────────────────────────────────────
-- One uploaded file (.txt/.md/.pdf/.docx/.epub) the author attaches as a
-- grounding source. The raw bytes live in MinIO (storage_key); the EXTRACTED
-- text (+OCR for scanned PDFs) is persisted here so /compose can ingest it as a
-- grounding corpus. Async (F10): the row is created status='processing' on upload
-- and flipped to 'ready'/'failed' when background extraction finishes; GET
-- /uploads/{id} polls. Per-user/book scope (Q3); no FK (cross-DB ids).
-- license_asserted is default-deny — the handler refuses copyrighted/unknown
-- BEFORE storing, so a stored row always carries an admissible license. ADDITIVE.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_upload (
  upload_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id          UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  book_id          UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  project_id       UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  filename         TEXT NOT NULL,
  mime             TEXT NOT NULL DEFAULT '',
  size_bytes       BIGINT NOT NULL DEFAULT 0,
  pages            INT NOT NULL DEFAULT 0,
  extracted_text   TEXT NOT NULL DEFAULT '',
  extracted_chars  INT NOT NULL DEFAULT 0,
  ocr_used         BOOLEAN NOT NULL DEFAULT false,
  license_asserted TEXT NOT NULL DEFAULT 'unknown',
  storage_key      TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing','ready','failed')),
  error_message    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_enrichment_upload_scope
  ON enrichment_upload(user_id, book_id, created_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- enrichment_compose_task (Phase 3 M2) — the durable row for a one-shot
-- interactive LLM task moved OFF the request path. The two compose endpoints
-- (profile/suggest, compose/resolve-intent) used to run their single LLM call
-- inline and return the result; they now create a 'pending' task here, enqueue a
-- trigger on the resume stream, and return 202 + task_id. The resume worker runs
-- the compute and writes result_json; GET /compose-tasks/{id} polls.
--
-- DISTINCT from enrichment_job (gap-fill: C8 state machine, technique CHECK,
-- proposal children, cost-cap pause) — a one-shot suggest/intent fits none of
-- that, so this is a dedicated lightweight table, NOT a new enrichment_job kind.
-- Per-user/project scope (Q3); book_id is the always-present GUI anchor. No FK
-- (cross-DB ids). request_json holds only the request shape (model_ref UUIDs +
-- params + acting user) — NEVER a secret; result_json holds the draft output the
-- author reviews (a suggested profile / a resolved intent). ADDITIVE.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS enrichment_compose_task (
  task_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  kind           TEXT NOT NULL
    CHECK (kind IN ('profile_suggest','intent_resolve')),
  status         TEXT NOT NULL DEFAULT 'pending'
    -- 'cancelled' added for D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL (status-only cancel of a
    -- still-queued one-shot task). Existing DBs widened by the DO $$ block below.
    CHECK (status IN ('pending','running','completed','failed','cancelled')),
  user_id        UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  project_id     UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  book_id        UUID,                            -- GUI anchor (always set today)
  request_json   JSONB NOT NULL,                  -- request shape only (no secret)
  result_json    JSONB,                           -- draft output (author reviews)
  error_message  TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- D-JOBS-P3-LORE-COMPOSE-TASK-CONTROL — widen the status CHECK on an already-deployed
-- table to admit 'cancelled' (status-only cancel). DROP the auto-named inline constraint
-- + ADD a named one (ADD CONSTRAINT has no IF NOT EXISTS) inside a DO $$ block so it is
-- idempotent on every startup. ADDITIVE (only widens the allowed set).
DO $$
BEGIN
  ALTER TABLE enrichment_compose_task DROP CONSTRAINT IF EXISTS enrichment_compose_task_status_check;
  ALTER TABLE enrichment_compose_task DROP CONSTRAINT IF EXISTS enrichment_compose_task_status_vocab;
  ALTER TABLE enrichment_compose_task
    ADD CONSTRAINT enrichment_compose_task_status_vocab
    CHECK (status IN ('pending','running','completed','failed','cancelled'));
END $$;

CREATE INDEX IF NOT EXISTS idx_enrichment_compose_task_scope
  ON enrichment_compose_task(user_id, book_id, created_at DESC);

-- D-M2-COMPOSE-TASK-SWEEPER — a partial index for the stuck-task sweep: the worker
-- periodically scans for rows still ('pending','running') idle past a timeout (a
-- redis-miss at submit, or a crash mid-compute) and re-drives them. The partial
-- predicate keeps the index tiny (terminal rows are excluded), ordered by updated_at
-- so the oldest-stranded LIMITed batch is a cheap index scan. ADDITIVE + idempotent.
CREATE INDEX IF NOT EXISTS idx_enrichment_compose_task_stuck
  ON enrichment_compose_task(updated_at)
  WHERE status IN ('pending','running');

-- ── outbox_events: standard (matches knowledge/composition); relayed by worker-infra
-- to loreweave:events:<aggregate_type>. Unified Job Control Plane P1 — lore-enrichment
-- job-lifecycle JobEvents are written here with aggregate_type='jobs' (→
-- loreweave:events:jobs) in the SAME tx as the enrichment_job / compose_task status
-- change (emit_job_event).
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'lore_enrichment',
  aggregate_id   UUID NOT NULL,
  event_type     TEXT NOT NULL,
  payload        JSONB NOT NULL DEFAULT '{}',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(created_at) WHERE published_at IS NULL;

-- ═══════════════════════════════════════════════════════════════════════════
-- gamegen S0/S2 — the interrogation tier
-- (docs/03_planning/LLM_MMO_RPG/39_progression_generation_pipeline.md §3.3)
--
-- PGN-A1: these are NOT enrichment_proposal. That table is non-canon BY
-- CONSTRUCTION (origin='enrichment', CHECK confidence < 1.0, terminal state
-- 'promoted' -> a glossary entity). This pipeline's output is canon by
-- construction. Sharing a table would make one of those two invariants a lie.
--
-- Scope keys are `owner_user_id` + `book_id` on every table, per CLAUDE.md ›
-- User Boundaries. The name differs from the older C2 tables' `user_id`
-- deliberately: `user_id` there is ambiguous between owner and actor, and these
-- rows carry BOTH (an `approved_by` that is not the owner is the normal case
-- once E0 grants exist).
-- ═══════════════════════════════════════════════════════════════════════════

-- ── gamegen_corpus_seal (S0) ────────────────────────────────────────────────
-- PGN-A14: a citation is VERIFIED against a sealed corpus, never trusted. The
-- seal exists here — ahead of the verifier that will read it — because it is the
-- FK target that makes the requirement STRUCTURAL: `gamegen_answer` cannot store
-- a citation without naming the seal it was checked against (CHECK below). A
-- verifier added later has somewhere to record its result; a verifier never
-- added leaves rows that visibly point at an unverified seal, rather than rows
-- that look complete.
CREATE TABLE IF NOT EXISTS gamegen_corpus_seal (
  seal_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  corpus_id      UUID NOT NULL REFERENCES source_corpus(corpus_id) ON DELETE CASCADE,
  owner_user_id  UUID NOT NULL,
  book_id        UUID,
  -- Over (chunk_id, chunk_index, content) of every chunk, ordered by
  -- chunk_index. Hex, not bytea, so a seal is greppable in a log and diffable by
  -- eye.
  --
  -- Named `corpus_digest`, not `merkle_root` as doc 39 sketches it. A merkle root
  -- buys INCLUSION PROOFS - "chunk 7 was in the sealed set, here is a log-n
  -- path" - and nothing here needs one: a verifier holds the whole corpus and
  -- fetches the chunk directly. Shipping a flat ordered hash under the name
  -- `merkle_root` would be a promise about a structure that is not there, and
  -- the next person to need an inclusion proof would find the field and trust it.
  --
  -- Both this and chunk_count are DERIVED by `seal_corpus`, never accepted from
  -- a caller. A seal is an attestation about what the corpus contained; a
  -- caller-supplied digest is the attestation attesting to itself.
  corpus_digest  TEXT NOT NULL,
  chunk_count    INT NOT NULL,
  sealed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  sealed_by      UUID NOT NULL,
  CONSTRAINT gamegen_seal_digest_hex CHECK (corpus_digest ~ '^[0-9a-f]{64}$'),
  CONSTRAINT gamegen_seal_nonempty CHECK (chunk_count > 0)
);
CREATE INDEX IF NOT EXISTS idx_gamegen_seal_scope
  ON gamegen_corpus_seal(owner_user_id, book_id);
-- One seal per (corpus, root): re-sealing an UNCHANGED corpus is a no-op rather
-- than a new row, so `sealed_at` cannot drift away from the bytes it attests.
CREATE UNIQUE INDEX IF NOT EXISTS uq_gamegen_seal_corpus_root
  ON gamegen_corpus_seal(corpus_id, corpus_digest);

-- The FK target for gamegen_decision's tenant-boundary FK. (job_id, user_id) is
-- already unique - job_id is the PK - so this adds no restriction; it exists
-- because a composite FK needs a matching UNIQUE to point at. Guarded because
-- ADD CONSTRAINT has no IF NOT EXISTS.
DO $job_owner_uq$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_enrichment_job_id_user'
  ) THEN
    ALTER TABLE enrichment_job
      ADD CONSTRAINT uq_enrichment_job_id_user UNIQUE (job_id, user_id);
  END IF;
END
$job_owner_uq$;

-- ── gamegen_decision (S2) — THE APPROVAL UNIT ───────────────────────────────
-- PGN-A11: the unit is the assertion CLASS x target, not the row. The POC's 121
-- normalized rows collapse to ~29 decisions, which is what makes a signature mean
-- something: 29 signatures over 29 reviewed assertions beats 121 over rows nobody
-- read.
CREATE TABLE IF NOT EXISTS gamegen_decision (
  decision_id    UUID PRIMARY KEY DEFAULT uuidv7(),
  -- COMPOSITE, not a plain reference to job_id. A plain FK proves the job
  -- exists, not that it is THIS owner's - and an adversarial probe confirmed the
  -- consequence: user B could create a decision on user A's job. Matching
  -- (job_id, owner_user_id) against (job_id, user_id) makes the tenant boundary
  -- a foreign key rather than a query convention somebody has to remember.
  job_id         UUID NOT NULL,
  owner_user_id  UUID NOT NULL,
  book_id        UUID,
  element_kind   TEXT NOT NULL,
  -- The assertion class ('tier_name_pattern', 'cap_rule', ...) and what it is
  -- asserted ABOUT ('kind:internal_energy'). Free text on purpose: the closed set
  -- lives in the brief (S1), which is version-pinned per element_kind, and a
  -- CHECK here would have to be widened for every new element module.
  question_class TEXT NOT NULL,
  target_ref     TEXT NOT NULL,
  review_status  TEXT NOT NULL DEFAULT 'proposed'
    CHECK (review_status IN ('proposed','approved','rejected')),
  approved_by    UUID,
  approved_at    TIMESTAMPTZ,
  rejected_reason TEXT,
  -- T3, and the reason bulk approval is VISIBLE rather than merely discouraged.
  -- batch_id groups the decisions approved in one click; batch_size records how
  -- many the human was shown. It is checked against the real count by a DEFERRED
  -- constraint trigger below - a stored count that may lie would make T3's
  -- "bulk is visible" a claim rather than a property.
  batch_id       UUID,
  batch_size     INT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- T5 - "a wrong rule is traceable TO A PERSON". An `approved` row with a NULL
  -- `approved_by` breaks that silently: every hop of the chain still resolves and
  -- the last one names nobody. So the state and its evidence move together.
  CONSTRAINT gamegen_decision_status_coherent CHECK (
       (review_status = 'proposed'
        AND approved_by IS NULL AND approved_at IS NULL AND rejected_reason IS NULL)
    OR (review_status = 'approved'
        AND approved_by IS NOT NULL AND approved_at IS NOT NULL AND rejected_reason IS NULL)
    OR (review_status = 'rejected'
        AND rejected_reason IS NOT NULL AND approved_by IS NULL AND approved_at IS NULL)
  ),
  -- A batch is a property of an APPROVAL. Stamping one on a `proposed` row would
  -- pre-declare a click that has not happened.
  CONSTRAINT gamegen_decision_batch_paired CHECK (
    (batch_id IS NULL) = (batch_size IS NULL)
  ),
  CONSTRAINT gamegen_decision_batch_positive CHECK (batch_size IS NULL OR batch_size >= 1),
  CONSTRAINT gamegen_decision_batch_needs_approval CHECK (
    batch_id IS NULL OR review_status = 'approved'
  ),
  -- One decision per assertion class per target per job. Two would let a
  -- reviewer approve and another reject the same assertion with nothing
  -- downstream able to say which won.
  CONSTRAINT uq_gamegen_decision_unit UNIQUE (job_id, question_class, target_ref),
  -- Not redundant with the PK: it is the target of `gamegen_answer`'s COMPOSITE
  -- FK, which is what stops an answer's denormalized job_id AND owner from
  -- disagreeing with its decision's. The owner half is load-bearing - see the
  -- FK comment on gamegen_answer.
  CONSTRAINT uq_gamegen_decision_id_job UNIQUE (decision_id, job_id, owner_user_id),
  CONSTRAINT gamegen_decision_job_fk
    FOREIGN KEY (job_id, owner_user_id)
    REFERENCES enrichment_job(job_id, user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gamegen_decision_scope
  ON gamegen_decision(owner_user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_gamegen_decision_job_status
  ON gamegen_decision(job_id, review_status);
CREATE INDEX IF NOT EXISTS idx_gamegen_decision_batch
  ON gamegen_decision(batch_id) WHERE batch_id IS NOT NULL;

-- ── says[] wellformedness (PGN-A3 + PGN-A14) ────────────────────────────────
-- IMMUTABLE so it can live inside a CHECK. A subquery cannot, which is why this
-- is a function and not an inline NOT EXISTS.
--
-- Three properties, each a real failure that reached this design:
--   1. every element has chunk_id + span + quote. A citation with no span is a
--      citation to a whole document, which verifies nothing.
--   2. a span is [start, end) with start < end. A zero-width span "verifies"
--      against the empty string, i.e. against anything.
--   3. spans within one chunk are DISJOINT. This is the one that kills citing a
--      single span 24 times for 24 tier names - the shape PGN-A14 names
--      explicitly ("the citation count must not be below the item count").
--   4. chunk_id is a UUID. It names a source_corpus_chunk and cannot be an FK
--      (it lives inside JSONB), so the format check is the only thing between a
--      citation and a chunk_id of 'not-a-uuid-at-all' - which a probe stored
--      successfully before this arm existed.
--   5. `length(quote) = end - start`. **This is what pins the UNIT of a span.**
--      The corpus is Chinese, and a byte offset and a character offset differ by
--      3x on every CJK chunk; nothing else in the schema says which one a span
--      is. Postgres `length()` and Python `str` slicing are both CHARACTERS, so
--      the verifier that fetches `content[start:end]` will compare equal-length
--      strings or not at all - and this check makes a byte-offset citation fail
--      NOW, at insert, rather than silently mis-verifying against the wrong
--      substring once the corpus is ingested. (The Multilingual standard's
--      whole class: an English-only assumption that survives every test written
--      in English.)
CREATE OR REPLACE FUNCTION gamegen_says_wellformed(says JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE
AS $says_fn$
DECLARE
  e JSONB;
  f JSONB;
  n INT;
  i INT;
  j INT;
BEGIN
  IF says IS NULL OR jsonb_typeof(says) <> 'array' THEN
    RETURN FALSE;
  END IF;
  n := jsonb_array_length(says);
  FOR i IN 0 .. n - 1 LOOP
    e := says -> i;
    IF jsonb_typeof(e) <> 'object' THEN RETURN FALSE; END IF;
    IF NOT (e ? 'chunk_id' AND e ? 'span' AND e ? 'quote') THEN RETURN FALSE; END IF;
    IF jsonb_typeof(e -> 'span') <> 'array' OR jsonb_array_length(e -> 'span') <> 2 THEN
      RETURN FALSE;
    END IF;
    IF jsonb_typeof(e -> 'span' -> 0) <> 'number'
       OR jsonb_typeof(e -> 'span' -> 1) <> 'number' THEN
      RETURN FALSE;
    END IF;
    IF (e -> 'span' ->> 0)::NUMERIC < 0
       OR (e -> 'span' ->> 0)::NUMERIC >= (e -> 'span' ->> 1)::NUMERIC THEN
      RETURN FALSE;
    END IF;
    IF jsonb_typeof(e -> 'quote') <> 'string' OR length(e ->> 'quote') = 0 THEN
      RETURN FALSE;
    END IF;
    IF jsonb_typeof(e -> 'chunk_id') <> 'string'
       OR (e ->> 'chunk_id') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
      RETURN FALSE;
    END IF;
    -- the unit pin; see note 5 above
    IF length(e ->> 'quote')
       <> ((e -> 'span' ->> 1)::NUMERIC - (e -> 'span' ->> 0)::NUMERIC) THEN
      RETURN FALSE;
    END IF;
    -- disjointness, same chunk only
    FOR j IN 0 .. i - 1 LOOP
      f := says -> j;
      IF (f ->> 'chunk_id') = (e ->> 'chunk_id')
         AND (e -> 'span' ->> 0)::NUMERIC < (f -> 'span' ->> 1)::NUMERIC
         AND (f -> 'span' ->> 0)::NUMERIC < (e -> 'span' ->> 1)::NUMERIC THEN
        RETURN FALSE;
      END IF;
    END LOOP;
  END LOOP;
  RETURN TRUE;
END
$says_fn$;

-- ── gamegen_answer (S2) — the evidence, which is not the click ──────────────
CREATE TABLE IF NOT EXISTS gamegen_answer (
  answer_id      UUID PRIMARY KEY DEFAULT uuidv7(),
  decision_id    UUID NOT NULL,
  job_id         UUID NOT NULL,
  owner_user_id  UUID NOT NULL,
  book_id        UUID,
  question_id    TEXT NOT NULL,
  target_ref     TEXT NOT NULL,

  -- PGN-A3 - two halves, NEVER merged. `says_json` is what a source states, and
  -- must cite a span. `proposed_text` is what the model invented, and cannot. The
  -- moment these are concatenated the author/model distinction is gone
  -- PERMANENTLY: nothing downstream can reconstruct it. Two columns is the whole
  -- mechanism, and it only works because no stage is allowed to merge them.
  says_json      JSONB NOT NULL DEFAULT '[]'::jsonb,
  proposed_text  TEXT,

  -- The ANSWER, as a structured value. `says_json`/`proposed_text` are why it is
  -- the answer; this is the answer.
  --
  -- Doc 39's sketch has only the two evidence columns, and building S3 showed why
  -- that cannot work: with nothing but prose, the fold would have to READ
  -- `proposed_text` and decide that "I'd call it a staged ladder" means
  -- `ProgressionType::Stage` - a model at consolidation, which `PGN-A10` exists to
  -- remove. So the interrogation stage resolves the value, under the human
  -- signature, and S3 stays a pure fold over settled values.
  --
  -- This does NOT re-merge `PGN-A3`'s two halves. Provenance is still exact and
  -- still derivable: says[] non-empty means the value is EXTRACTED and a span
  -- supports it; says[] empty with proposed_text means it was INVENTED. What
  -- changes is only that the fold no longer has to infer the value from the
  -- evidence.
  value_json     JSONB,

  -- PGN-A14 made structural. See gamegen_corpus_seal above.
  verified_against_seal_id UUID REFERENCES gamegen_corpus_seal(seal_id) ON DELETE RESTRICT,

  -- PGN-A4 - "the book does not say" is a COMPLETE answer, and an ACCOUNTABLE
  -- one. It stays one click; the reason is a closed set so an all-not_stated run
  -- (the cheapest path through the gate, at a ~30-45:1 cost gradient) is at least
  -- legible afterwards.
  not_stated        BOOLEAN NOT NULL DEFAULT FALSE,
  not_stated_reason TEXT,

  -- PGN-A9 - hash-linked, not id-linked. S5 recomputes this and refuses a
  -- mismatch. Id-linking is what let an UPDATE retroactively convert an invented
  -- tier into an extracted one with every hop of the chain still green.
  answer_hash    TEXT NOT NULL,
  -- Append-only: an answer is superseded, never edited. Enforced by trigger.
  --
  -- DEFERRABLE, and the reason is the partial unique index below. A supersession
  -- must retire the old answer BEFORE the new one is inserted, or the index sees
  -- two live answers for one (job, question, target) and refuses - so the UPDATE
  -- has to name an answer_id that does not exist yet. Deferring this FK to COMMIT
  -- is what makes that order possible. (Doing it the other way round - insert,
  -- then retire - is what the first implementation did, and it failed exactly
  -- here.)
  superseded_by_answer_id UUID
    REFERENCES gamegen_answer(answer_id) ON DELETE RESTRICT
    DEFERRABLE INITIALLY DEFERRED,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID NOT NULL,

  -- The denormalized job_id AND owner cannot disagree with the decision's.
  --
  -- The owner column in this FK closes a hole an adversarial probe found and
  -- demonstrated: with only (decision_id, job_id) matched, user B could insert an
  -- answer under user A's APPROVED decision, and B's own owner-scoped read then
  -- returned B's invented text joined to A's `approved_by`. B's invention wore
  -- A's signature - which is T5 ("traceable to a person") naming the wrong
  -- person, the one failure mode worse than naming nobody. A second consequence
  -- came free: the partial unique index is not owner-scoped, so B's row also took
  -- the live slot and A's legitimate answer was refused.
  --
  -- Deliberately a foreign key rather than a WHERE clause in the repository:
  -- every read here already filtered on owner and it did not help, because the
  -- rows themselves were inconsistent.
  CONSTRAINT gamegen_answer_decision_fk
    FOREIGN KEY (decision_id, job_id, owner_user_id)
    REFERENCES gamegen_decision(decision_id, job_id, owner_user_id) ON DELETE CASCADE,

  CONSTRAINT gamegen_answer_hash_hex CHECK (answer_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT gamegen_answer_says_wellformed CHECK (gamegen_says_wellformed(says_json)),

  -- An answer that states nothing is not an answer. Without this a row can be
  -- inserted, approved, and consumed while carrying no content at all - and S3's
  -- consumption ledger would faithfully record that it was consumed.
  CONSTRAINT gamegen_answer_says_something CHECK (
    not_stated OR jsonb_array_length(says_json) > 0 OR proposed_text IS NOT NULL
  ),
  -- The value and the silence are exclusive and exhaustive. An answer with
  -- neither is one S3 must fold and has nothing to fold; an answer with both
  -- says "the book does not say" and then says what it says.
  CONSTRAINT gamegen_answer_value_xor_silence CHECK (
    (value_json IS NULL) = not_stated
  ),
  -- PGN-A4: not_stated is exclusive and carries its reason from the closed set.
  CONSTRAINT gamegen_answer_not_stated_shape CHECK (
    NOT not_stated OR (
      jsonb_array_length(says_json) = 0
      AND proposed_text IS NULL
      AND not_stated_reason IS NOT NULL
    )
  ),
  CONSTRAINT gamegen_answer_not_stated_reason_closed CHECK (
    not_stated_reason IS NULL
    OR not_stated_reason IN ('absent_from_corpus','contradicted','out_of_scope')
  ),
  CONSTRAINT gamegen_answer_reason_needs_not_stated CHECK (
    not_stated_reason IS NULL OR not_stated
  ),
  -- PGN-A14: a citation without a seal is a citation nobody could have checked.
  CONSTRAINT gamegen_answer_citation_needs_seal CHECK (
    jsonb_array_length(says_json) = 0 OR verified_against_seal_id IS NOT NULL
  ),
  CONSTRAINT gamegen_answer_no_self_supersede CHECK (
    superseded_by_answer_id IS NULL OR superseded_by_answer_id <> answer_id
  )
);
-- Doc 39 sketches a plain UNIQUE (job_id, question_id, target_ref). That
-- contradicts its own append-only rule in the very next line: a superseding
-- answer carries the SAME triple by definition, so the plain constraint makes
-- supersession impossible and the only way to correct an answer becomes the
-- UPDATE the rule forbids. PARTIAL is the constraint that was meant: exactly one
-- LIVE answer per question per target per job, and any number of superseded ones
-- behind it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_gamegen_answer_live
  ON gamegen_answer(job_id, question_id, target_ref)
  WHERE superseded_by_answer_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_gamegen_answer_decision ON gamegen_answer(decision_id);
CREATE INDEX IF NOT EXISTS idx_gamegen_answer_scope
  ON gamegen_answer(owner_user_id, book_id);

-- ── append-only enforcement (PGN-A9's precondition) ─────────────────────────
-- Exactly ONE transition is legal on an existing answer: superseded_by_answer_id
-- moving from NULL to non-NULL. Everything else - including "fixing a typo in a
-- quote" - is refused, because the hash link is only worth anything if the bytes
-- behind it cannot move.
--
-- Note what is deliberately NOT permitted: un-superseding (non-NULL -> NULL), and
-- re-pointing a supersession. Both would let history be rewritten by a sequence
-- of individually-legal steps.
CREATE OR REPLACE FUNCTION gamegen_answer_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $answer_ao$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION
      'gamegen_answer is append-only: answer % cannot be DELETEd. Supersede it '
      'instead - the audit chain is the product, and a deleted answer takes a '
      'creative structure''s provenance with it', OLD.answer_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF OLD.superseded_by_answer_id IS NOT NULL THEN
    RAISE EXCEPTION
      'gamegen_answer % is already superseded by %; a superseded answer is frozen',
      OLD.answer_id, OLD.superseded_by_answer_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.superseded_by_answer_id IS NULL THEN
    RAISE EXCEPTION
      'gamegen_answer % is append-only: the only legal UPDATE is setting '
      'superseded_by_answer_id. Correct an answer by inserting a new one that '
      'supersedes it', OLD.answer_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  -- Everything else must be byte-identical. Listed field by field rather than
  -- with a row comparison so the error names WHICH field moved; `NEW <> OLD` is
  -- also NULL-poisoned on any nullable column, which would silently pass.
  IF NEW.answer_id  IS DISTINCT FROM OLD.answer_id
     OR NEW.decision_id   IS DISTINCT FROM OLD.decision_id
     OR NEW.job_id        IS DISTINCT FROM OLD.job_id
     OR NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id
     OR NEW.book_id       IS DISTINCT FROM OLD.book_id
     OR NEW.question_id   IS DISTINCT FROM OLD.question_id
     OR NEW.target_ref    IS DISTINCT FROM OLD.target_ref
     OR NEW.says_json     IS DISTINCT FROM OLD.says_json
     OR NEW.proposed_text IS DISTINCT FROM OLD.proposed_text
     OR NEW.value_json    IS DISTINCT FROM OLD.value_json
     OR NEW.verified_against_seal_id IS DISTINCT FROM OLD.verified_against_seal_id
     OR NEW.not_stated        IS DISTINCT FROM OLD.not_stated
     OR NEW.not_stated_reason IS DISTINCT FROM OLD.not_stated_reason
     OR NEW.answer_hash   IS DISTINCT FROM OLD.answer_hash
     OR NEW.created_at    IS DISTINCT FROM OLD.created_at
     OR NEW.created_by    IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION
      'gamegen_answer % is append-only: supersession may set '
      'superseded_by_answer_id and NOTHING else. answer_hash is a promise about '
      'these bytes', OLD.answer_id
      USING ERRCODE = 'restrict_violation';
  END IF;

  RETURN NEW;
END
$answer_ao$;

DROP TRIGGER IF EXISTS trg_gamegen_answer_append_only ON gamegen_answer;
CREATE TRIGGER trg_gamegen_answer_append_only
  BEFORE UPDATE OR DELETE ON gamegen_answer
  FOR EACH ROW EXECUTE FUNCTION gamegen_answer_append_only();

-- ── gamegen_creative_structure (S3) — the fold's output, at rest ────────────
-- PGN-A9's ledger is enforced by `fold()` in memory. It is enforced AGAIN here
-- because the fold is a function and a table is a place: a row written by
-- anything else - a backfill, a repair script, a future S3b - would otherwise
-- carry a ledger nobody checked. The same reason the S2 invariants are CHECKs.
CREATE OR REPLACE FUNCTION gamegen_ledger_is_total(consumption JSONB, refs JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql IMMUTABLE
AS $ledger_fn$
DECLARE
  e JSONB;
  i INT;
BEGIN
  IF jsonb_typeof(consumption) <> 'object' OR jsonb_typeof(refs) <> 'array' THEN
    RETURN FALSE;
  END IF;
  IF jsonb_array_length(refs) = 0 THEN
    RETURN FALSE;  -- a structure folded from no answers is authored by nobody
  END IF;
  -- every ref is [answer_id, answer_hash] and appears in the consumption map
  -- with at least one pointer
  FOR i IN 0 .. jsonb_array_length(refs) - 1 LOOP
    e := refs -> i;
    IF jsonb_typeof(e) <> 'array' OR jsonb_array_length(e) <> 2 THEN RETURN FALSE; END IF;
    IF (e ->> 1) !~ '^[0-9a-f]{64}$' THEN RETURN FALSE; END IF;  -- hash-linked
    IF NOT (consumption ? (e ->> 0)) THEN RETURN FALSE; END IF;
    IF jsonb_typeof(consumption -> (e ->> 0)) <> 'array'
       OR jsonb_array_length(consumption -> (e ->> 0)) = 0 THEN
      RETURN FALSE;
    END IF;
  END LOOP;
  -- and the other direction: no consumed answer without a hash-linked ref, which
  -- is how an answer could be recorded as consumed while nothing pins WHICH
  -- version of it was.
  IF (SELECT count(*) FROM jsonb_object_keys(consumption)) <> jsonb_array_length(refs) THEN
    RETURN FALSE;
  END IF;
  RETURN TRUE;
END
$ledger_fn$;

CREATE TABLE IF NOT EXISTS gamegen_creative_structure (
  structure_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id         UUID NOT NULL,
  owner_user_id  UUID NOT NULL,
  book_id        UUID,
  element_kind   TEXT NOT NULL,
  -- The engine schema the brief was asserted total against
  -- (contracts/progression-schema.json). Carried so a structure folded under one
  -- schema is not silently consumed under another; S1's brief lives in a file, so
  -- there is no brief_id to reference yet.
  schema_fingerprint TEXT NOT NULL,
  content_hash   TEXT NOT NULL,
  body_json      JSONB NOT NULL,
  consumption_json JSONB NOT NULL,
  answer_refs_json JSONB NOT NULL,
  approved_by    UUID,
  approved_at    TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID NOT NULL,

  CONSTRAINT gamegen_structure_job_fk
    FOREIGN KEY (job_id, owner_user_id)
    REFERENCES enrichment_job(job_id, user_id) ON DELETE CASCADE,
  CONSTRAINT gamegen_structure_hash_hex CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT gamegen_structure_ledger_total
    CHECK (gamegen_ledger_is_total(consumption_json, answer_refs_json)),
  -- Content-addressed within a job: re-folding the SAME answers is a no-op, and a
  -- second row for the same hash would make "which structure did S5 read" a
  -- question with two answers.
  CONSTRAINT uq_gamegen_structure UNIQUE (job_id, element_kind, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_gamegen_structure_scope
  ON gamegen_creative_structure(owner_user_id, book_id);

-- ── gamegen_numeric_policy (S4) — where magnitudes come from ────────────────
-- PGN-A15. The FIRST System-tier table in this pipeline: everything before it is
-- per-book. That distinction is the point, and it is encoded here rather than
-- left to the repository, because CLAUDE.md's tenancy rule is that a regular user
-- MUST NOT mutate a System-tier row and "the code does not do that today" is not
-- a boundary.
--
-- The two tiers are exclusive and exhaustive, and the shape of each says what it
-- is for:
--   system: no owner, no book, NO PARENT   — the shipped baseline
--   book:   an owner, a book, and a PARENT — a narrowing of that baseline
--
-- `tier='book' => parent_policy_id IS NOT NULL` is `PGN-A15` as a schema fact: a
-- book policy CANNOT EXIST without something to narrow. You may narrow a shipped
-- baseline; you may not author from scratch. Without it a "book policy" is just a
-- second global policy with extra steps, which is exactly what v1 shipped by
-- declaring no tier at all.
CREATE TABLE IF NOT EXISTS gamegen_numeric_policy (
  policy_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  element_kind    TEXT NOT NULL,
  tier            TEXT NOT NULL CHECK (tier IN ('system','book')),
  policy_version  INT  NOT NULL CHECK (policy_version >= 1),
  -- NULL on a System row: the platform owns it, no user does.
  owner_user_id   UUID,
  book_id         UUID,
  parent_policy_id UUID REFERENCES gamegen_numeric_policy(policy_id) ON DELETE RESTRICT,
  -- The engine schema the bands were authored against. A policy banding a
  -- magnitude set the engine no longer has is one S5 would apply anyway.
  schema_fingerprint TEXT NOT NULL,
  body_json       JSONB NOT NULL,
  policy_hash     TEXT NOT NULL,
  authored_by     UUID NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT gamegen_policy_hash_hex CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT gamegen_policy_tier_shape CHECK (
       (tier = 'system'
        AND owner_user_id IS NULL AND book_id IS NULL AND parent_policy_id IS NULL)
    OR (tier = 'book'
        AND owner_user_id IS NOT NULL AND book_id IS NOT NULL
        AND parent_policy_id IS NOT NULL)
  )
);
-- One System baseline per (element_kind, version), and one book narrowing per
-- (element_kind, book, version). Partial because the two tiers have different
-- identity: a System policy has no book to be unique within.
CREATE UNIQUE INDEX IF NOT EXISTS uq_gamegen_policy_system
  ON gamegen_numeric_policy(element_kind, policy_version) WHERE tier = 'system';
-- owner_user_id is in the key, and a probe is why. Without it, user B writing a
-- policy for user A's book at v1 takes the slot and A's own write fails with a
-- unique violation - a cross-tenant denial reachable by anyone who can guess a
-- book id. (The read is owner-scoped too; this is the write half.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_gamegen_policy_book
  ON gamegen_numeric_policy(element_kind, book_id, owner_user_id, policy_version)
  WHERE tier = 'book';
CREATE INDEX IF NOT EXISTS idx_gamegen_policy_scope
  ON gamegen_numeric_policy(owner_user_id, book_id) WHERE tier = 'book';

-- ── gamegen_candidate (S5) — admission, and the human v1 had none of ────────
-- Doc 39 §7.2: "v1's T3 named a gate at S5 and the schema had nowhere to record
-- that anyone looked." That is the hole this table's review columns close.
--
-- Two verdict properties are structural rather than procedural:
--
--   1. a REFUSED candidate can never be approved. Without the CHECK, "approve
--      it anyway" is one UPDATE away, and every hop before it stays green.
--   2. an ADMITTED candidate must name the digest it admitted, and a refused one
--      must NOT. A digest beside a refusal is something a later stage can pin.
--
-- `engine_schema_version` / `engine_law_version` are NOT NULL because a verdict
-- that does not say which binary produced it is precisely the stale-verdict
-- laundering PGN-A7 exists to stop: a candidate admitted under schema 4 has not
-- been admitted under schema 5.
CREATE TABLE IF NOT EXISTS gamegen_candidate (
  candidate_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  job_id         UUID NOT NULL,
  owner_user_id  UUID NOT NULL,
  book_id        UUID,
  element_kind   TEXT NOT NULL,

  -- The three hashes T2 rests on: shape, numbers, and what they produced.
  structure_hash TEXT NOT NULL,
  policy_hash    TEXT NOT NULL,
  artifact_hash  TEXT NOT NULL,
  repair_round   INT  NOT NULL DEFAULT 0 CHECK (repair_round >= 0),

  verdict        TEXT NOT NULL CHECK (verdict IN ('admitted','refused')),
  -- The ENGINE's own findings, every one of them. Not a paraphrase: `validate`
  -- returns them all so a reviewer does not fix one, re-run, and find another.
  verdict_findings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  progression_digest TEXT,

  -- PGN-A9's second direction, recorded: the leaf pointers S5 actually consumed.
  read_set_json  JSONB NOT NULL,
  -- §7.2's number. Every field the engine will fill because nobody asked, NAMED
  -- with its reason - "you are approving 24 tiers of which 132 fields will be
  -- engine-defaulted" is what turns an invisible hole into something vetoable.
  default_provenance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- PGN-A17, TYPED. Stored even when empty so a repair that happened and a run
  -- that never repaired are different rows rather than the same absence.
  repair_ops_json JSONB NOT NULL DEFAULT '[]'::jsonb,

  engine_schema_version INT NOT NULL,
  engine_law_version    INT NOT NULL,

  -- The S5 human gate.
  review_status  TEXT NOT NULL DEFAULT 'proposed'
    CHECK (review_status IN ('proposed','approved','rejected')),
  approved_by    UUID,
  approved_at    TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by     UUID NOT NULL,

  CONSTRAINT gamegen_candidate_job_fk
    FOREIGN KEY (job_id, owner_user_id)
    REFERENCES enrichment_job(job_id, user_id) ON DELETE CASCADE,
  CONSTRAINT gamegen_candidate_hashes_hex CHECK (
    structure_hash ~ '^[0-9a-f]{64}$' AND policy_hash ~ '^[0-9a-f]{64}$'
    AND artifact_hash ~ '^[0-9a-f]{64}$'
  ),
  -- A refused candidate names no digest; an admitted one must.
  -- `IS NOT NULL` before the regex, and it is load-bearing: `NULL ~ '...'` is
  -- NULL, and a CHECK that evaluates to NULL is SATISFIED in Postgres. The first
  -- version omitted it and an `admitted` row with no digest inserted cleanly —
  -- a verdict about nothing addressable, which is not a verdict S6 can pin.
  CONSTRAINT gamegen_candidate_digest_matches_verdict CHECK (
    (verdict = 'admitted'
     AND progression_digest IS NOT NULL AND progression_digest ~ '^[0-9a-f]{64}$')
    OR (verdict = 'refused' AND progression_digest IS NULL)
  ),
  -- A refusal is not approvable. T3's last hop, and the one v1 left open.
  CONSTRAINT gamegen_candidate_review_coherent CHECK (
       (review_status = 'proposed' AND approved_by IS NULL AND approved_at IS NULL)
    OR (review_status = 'approved' AND approved_by IS NOT NULL
        AND approved_at IS NOT NULL AND verdict = 'admitted')
    OR (review_status = 'rejected' AND approved_by IS NULL AND approved_at IS NULL)
  ),
  -- Content-addressed: the same structure + policy + engine gives the same
  -- candidate. Re-running admission is a no-op, not a second row that makes
  -- "which candidate did S6 pin" a question with two answers.
  CONSTRAINT uq_gamegen_candidate UNIQUE (
    job_id, structure_hash, policy_hash, repair_round, engine_schema_version
  )
);
CREATE INDEX IF NOT EXISTS idx_gamegen_candidate_scope
  ON gamegen_candidate(owner_user_id, book_id);

-- ── batch_size honesty (T3) ─────────────────────────────────────────────────
-- DEFERRABLE INITIALLY DEFERRED, because a batch is written one row at a time:
-- an immediate check would fire on row 1 of 24 and see a count of 1. At COMMIT
-- the whole batch is present.
--
-- This catches BOTH ways the number can lie: writing `batch_size = 1` while
-- approving 24 (understating a bulk click), and adding a 25th decision to a
-- committed batch later (retroactively enlarging an approval that already
-- happened). Without it `batch_size` is a self-reported number, and T3's
-- "bulk is visible" would be a claim rather than a property.
CREATE OR REPLACE FUNCTION gamegen_decision_batch_honest()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $batch_fn$
DECLARE
  actual INT;
BEGIN
  IF NEW.batch_id IS NULL THEN
    RETURN NULL;
  END IF;
  SELECT count(*) INTO actual FROM gamegen_decision WHERE batch_id = NEW.batch_id;
  IF actual <> NEW.batch_size THEN
    RAISE EXCEPTION
      'batch % declares batch_size=% but holds % decisions. The number a reviewer '
      'was shown must equal the number they approved - an understated batch_size '
      'hides a bulk click, and enlarging a committed batch back-dates approval '
      'onto assertions nobody saw', NEW.batch_id, NEW.batch_size, actual
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NULL;
END
$batch_fn$;

DROP TRIGGER IF EXISTS trg_gamegen_decision_batch_honest ON gamegen_decision;
CREATE CONSTRAINT TRIGGER trg_gamegen_decision_batch_honest
  AFTER INSERT OR UPDATE ON gamegen_decision
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION gamegen_decision_batch_honest();
"""


# Reverse FK dependency order: drop the proposal (refs job + grounding_ref)
# first, then enrichment_job_request (refs job, F-C14-1/051) + the proposal,
# then job, then template, then grounding_ref (refs corpus), then corpus. The
# trigger goes with its table; the function is dropped last.
#   NOTE: enrichment_job_request MUST be dropped before enrichment_job — its
#   job_id FK depends on the job table, so omitting it made `DROP TABLE
#   enrichment_job` fail (DependentObjectsStillExistError) on any DB that had
#   been up-migrated, breaking the down→up round-trip (and the db-test fixture's
#   per-test reset). It was added to the UP DDL but not here.
#   NOTE 2: the gamegen tier drops FIRST and in its own reverse order - answer
#   (refs decision + seal) → decision (refs enrichment_job) → seal (refs
#   source_corpus). Omitting any of them would make `DROP TABLE enrichment_job`
#   and `DROP TABLE source_corpus` fail with DependentObjectsStillExists, which
#   in this service breaks not one test but the whole tests/db tree: its `pool`
#   fixture down-migrates before every test.
DOWN_DDL = """
DROP TRIGGER IF EXISTS trg_gamegen_answer_append_only ON gamegen_answer;
DROP TRIGGER IF EXISTS trg_gamegen_decision_batch_honest ON gamegen_decision;
DROP TABLE IF EXISTS gamegen_candidate;
DROP TABLE IF EXISTS gamegen_numeric_policy;
DROP TABLE IF EXISTS gamegen_creative_structure;
DROP FUNCTION IF EXISTS gamegen_ledger_is_total(JSONB, JSONB);
DROP TABLE IF EXISTS gamegen_answer;
DROP TABLE IF EXISTS gamegen_decision;
DROP TABLE IF EXISTS gamegen_corpus_seal;
DROP FUNCTION IF EXISTS gamegen_answer_append_only();
DROP FUNCTION IF EXISTS gamegen_decision_batch_honest();
DROP FUNCTION IF EXISTS gamegen_says_wellformed(JSONB);
DROP TABLE IF EXISTS enrichment_compose_task;
DROP TABLE IF EXISTS enrichment_upload;
DROP TABLE IF EXISTS enrichment_book_profile;
DROP TABLE IF EXISTS enrichment_eval_runs;
DROP TRIGGER IF EXISTS trg_enrichment_proposal_h0 ON enrichment_proposal;
DROP TABLE IF EXISTS enrichment_proposal;
DROP TABLE IF EXISTS enrichment_job_request;
DROP TABLE IF EXISTS enrichment_job;
DROP TABLE IF EXISTS enrichment_template;
DROP TABLE IF EXISTS cultural_grounding_ref;
DROP TABLE IF EXISTS source_corpus_chunk;
DROP TABLE IF EXISTS source_corpus;
DROP FUNCTION IF EXISTS enrichment_proposal_h0_guard();
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the up-migration. Idempotent (CREATE ... IF NOT EXISTS /
    CREATE OR REPLACE), so it is safe to call on every startup."""
    async with pool.acquire() as conn:
        await conn.execute(DDL)


async def run_down_migrations(pool: asyncpg.Pool) -> None:
    """Drop all C2 objects in reverse FK order. Idempotent (DROP ... IF
    EXISTS), so up→down→up round-trips cleanly with no orphaned objects."""
    async with pool.acquire() as conn:
        await conn.execute(DOWN_DDL)
