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
  estimated_cost_usd NUMERIC(10,4) NOT NULL DEFAULT 0,
  actual_cost_usd    NUMERIC(10,4) NOT NULL DEFAULT 0,
  max_spend_usd      NUMERIC(10,4),               -- cost guardrail (C8)
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
    CHECK (status IN ('pending','running','completed','failed')),
  user_id        UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  project_id     UUID NOT NULL,                   -- scope (Q3); no FK (cross-DB)
  book_id        UUID,                            -- GUI anchor (always set today)
  request_json   JSONB NOT NULL,                  -- request shape only (no secret)
  result_json    JSONB,                           -- draft output (author reviews)
  error_message  TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
DOWN_DDL = """
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
