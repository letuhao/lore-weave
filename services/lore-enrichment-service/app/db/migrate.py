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
  license       TEXT NOT NULL DEFAULT 'public-domain',
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
-- default-deny normaliser would silently treat as UNKNOWN. The C2 default
-- 'public-domain' (hyphen) is admitted; the demo corpora (山海经, 封神演义,
-- Shang–Zhou history) are genuinely public-domain and keep that default.
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
    CHECK (technique IN ('template','retrieval','fabrication','recook')),
  entity_kind     TEXT,                           -- demo: 'location'
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
    CHECK (technique IN ('template','retrieval','fabrication','recook')),
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
"""


# Reverse FK dependency order: drop the proposal (refs job + grounding_ref)
# first, then job, then template, then grounding_ref (refs corpus), then
# corpus. The trigger goes with its table; the function is dropped last.
DOWN_DDL = """
DROP TABLE IF EXISTS enrichment_eval_runs;
DROP TRIGGER IF EXISTS trg_enrichment_proposal_h0 ON enrichment_proposal;
DROP TABLE IF EXISTS enrichment_proposal;
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
