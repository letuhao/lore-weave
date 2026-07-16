"""composition-service schema migration (idempotent, single-DDL house style).

M1: the §1.2 DDL (7 tables + indexes/constraints, all `IF NOT EXISTS`) plus the
built-in `structure_template` seed (6 structures, owner_user_id NULL, idempotent
via deterministic UUIDs + ON CONFLICT DO NOTHING). Applied on every startup —
no migration tool, like knowledge-service. `uuidv7()` is a PG18 built-in.

Cross-DB ids (project_id→knowledge, book_id/chapter_id/*_revision_id→book,
entity ids→glossary, llm_job_id→gateway) carry NO DB FK (§1.4 — validated in
app code). In-DB FKs (outline_node.parent_id, scene_link, generation_job→
outline_node) are fine — same database.

Book-package re-key (spec 25 M0-M3, marker `pkg_rekey_v1`): `book_id` is the
TENANCY scope key on the 13 package tables (`project_id` = the Work PARTITION
key — PM-3); the actor column is `created_by` — STORED, never filtered on
(PM-5; access is the E0 book gate, PM-8). The CREATE TABLE texts below are the
FINAL post-M3 shape, so a fresh DB bootstraps straight into it; an existing DB
converges through app.db.package_rekey (M0 pre-flight BEFORE this DDL — PM-7 —
then the M2 backfill + M3 cutover after it), wired in run_migrations.
"""

import logging

import asyncpg

from app.db.package_rekey import run_package_rekey
from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
-- ── composition_work: Work marker + work-level settings (1:1 with a book project)
-- created_by (25 M3/BPS-1) = the ACTOR stamp — stored, never filtered on; the
-- scope keys are project_id (Work partition) + book_id (tenancy, E0 book gate).
CREATE TABLE IF NOT EXISTS composition_work (
  project_id          UUID PRIMARY KEY,
  created_by          UUID NOT NULL,
  book_id             UUID NOT NULL,
  active_template_id  UUID,
  status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
  version             INT NOT NULL DEFAULT 1,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 25 M3.3: the actor index under its FINAL name. Guarded on the column: on a
-- legacy boot this DDL runs BEFORE the package_rekey M3 rename, so the column
-- may still be user_id here — the rekey creates this index itself right after
-- renaming; this block covers the fresh-DB path and converges every later boot.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'composition_work' AND column_name = 'created_by') THEN
    CREATE INDEX IF NOT EXISTS idx_composition_work_created_by ON composition_work(created_by);
  END IF;
END $$;

-- C16 (WG-3) Work-setup resilience: when knowledge-service is down/5xx during
-- greenfield setup, the Work is created with a LAZY (null) project_id + a backfill
-- marker so writing/Generate is never wall-blocked by an optional dependency. This
-- requires re-keying composition_work off project_id (a null PK is impossible):
--   • add a surrogate `id` PK (uuidv7);
--   • make project_id NULLABLE;
--   • keep the 1:1 (work ⇄ knowledge project) invariant via a PARTIAL unique index
--     over only the BACKED rows (project_id IS NOT NULL) — null rows are exempt;
--   • `pending_project_backfill` marks a greenfield Work awaiting its knowledge
--     project, and a partial-unique index caps it at one pending Work per (book)
--     (25 PM-4 re-key: was per (user,book) — two users' outage-forks must collide,
--     not fork) so a setup retry backfills the SAME row rather than duplicating.
-- All steps are idempotent (IF NOT EXISTS / guarded DO-blocks) so re-boot is safe.
-- GUARD (C23): a DERIVATIVE Work keeps project_id NOT NULL — enforced in app code
-- (routers), NOT relaxed here; this null state is greenfield-only.
ALTER TABLE composition_work ADD COLUMN IF NOT EXISTS id UUID;
ALTER TABLE composition_work ADD COLUMN IF NOT EXISTS pending_project_backfill BOOLEAN NOT NULL DEFAULT false;
-- Backfill the surrogate id for any pre-C16 row, then make it the PK.
UPDATE composition_work SET id = uuidv7() WHERE id IS NULL;
ALTER TABLE composition_work ALTER COLUMN id SET DEFAULT uuidv7();
ALTER TABLE composition_work ALTER COLUMN id SET NOT NULL;
DO $$
BEGIN
  -- Re-point the primary key from project_id → id (only once).
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'composition_work_pkey' AND conrelid = 'composition_work'::regclass
      AND (SELECT array_agg(attname::text ORDER BY attname)
             FROM pg_attribute
            WHERE attrelid = 'composition_work'::regclass
              AND attnum = ANY(conkey)) = ARRAY['project_id']
  ) THEN
    ALTER TABLE composition_work DROP CONSTRAINT composition_work_pkey;
    ALTER TABLE composition_work ADD CONSTRAINT composition_work_pkey PRIMARY KEY (id);
  END IF;
END $$;
ALTER TABLE composition_work ALTER COLUMN project_id DROP NOT NULL;
-- 1:1 work⇄project for BACKED works only (a null project_id is a lazy/greenfield Work).
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_project
  ON composition_work(project_id) WHERE project_id IS NOT NULL;
-- At most one pending-backfill (greenfield, null-project) Work per BOOK (25 PM-4)
-- so a setup retry backfills the same row instead of duplicating. On a legacy DB
-- the old (user_id, book_id) index no-ops this create; package_rekey M3.1 drops +
-- recreates it in this shape.
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_pending
  ON composition_work(book_id) WHERE pending_project_backfill;

-- ── C23 (dị bản M0): derivative copy-on-write substrate. A DERIVATIVE Work points
-- at the SOURCE Work it diverges from (`source_work_id`, in-DB self-ref FK on the
-- surrogate `id`) at a chapter-level `branch_point` (G3). The derivative gets its
-- OWN new knowledge project_id (G2 = its own Neo4j delta partition), NEVER the
-- source's. Spec-only COW: NO chapter clone — the source reference spine stays
-- read-only and the writer adapts manually (LOCKED).
ALTER TABLE composition_work ADD COLUMN IF NOT EXISTS source_work_id UUID
  REFERENCES composition_work(id) ON DELETE SET NULL;
ALTER TABLE composition_work ADD COLUMN IF NOT EXISTS branch_point INT;
CREATE INDEX IF NOT EXISTS idx_composition_work_source
  ON composition_work(source_work_id) WHERE source_work_id IS NOT NULL;
-- 25 PM-4/M3.1: ONE CANONICAL manifest per book — derivatives (source_work_id set)
-- and archived Works are exempt BY DESIGN (dị bản stay N-per-book; archive-and-
-- recreate stays possible). Placed after the C23 ALTERs so source_work_id exists
-- on a fresh bootstrap.
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_book
  ON composition_work(book_id) WHERE source_work_id IS NULL AND status = 'active';
-- ARCH-REVIEW GUARD (C23, reconciled with C16): a DERIVATIVE Work MUST carry a
-- NOT-NULL project_id — a null project_id widens the knowledge timeline endpoint to
-- ALL of a user's projects (cross-project grounding leak). This is a CONDITIONAL
-- constraint, NOT a blanket `SET NOT NULL`: a GREENFIELD Work (source_work_id NULL)
-- MAY still have a null project_id (C16's lazy/backfill path), so the 165 existing
-- null-project rows pass. Idempotent: the DO-block no-ops once the constraint exists.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_derivative_project_required'
      AND conrelid = 'composition_work'::regclass
  ) THEN
    ALTER TABLE composition_work ADD CONSTRAINT chk_derivative_project_required
      CHECK (source_work_id IS NULL OR project_id IS NOT NULL);
  END IF;
END $$;

-- ── divergence_spec: the dị bản delta declaration (one per derivative Work). The
-- divergence taxonomy (POV shift · character transform · AU — UX §7.1) reduces to
-- `taxonomy` + optional `pov_anchor` (the POV entity for a POV-shift derivative) +
-- added `canon_rule[]` (M0 override scope = entity fields + added canon rules ONLY).
-- `project_id` is the DERIVATIVE's project (cross-DB, no FK); `work_id` is the
-- derivative Work (in-DB FK on the surrogate id).
CREATE TABLE IF NOT EXISTS divergence_spec (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by  UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id  UUID NOT NULL,
  book_id     UUID NOT NULL,   -- tenancy scope key (25 M1/M2; derived via work_id)
  work_id     UUID NOT NULL REFERENCES composition_work(id) ON DELETE CASCADE,
  taxonomy    TEXT NOT NULL DEFAULT 'au' CHECK (taxonomy IN ('pov_shift','character_transform','au')),
  pov_anchor  UUID,
  canon_rule  TEXT[] NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_divergence_spec_work ON divergence_spec(work_id);

-- ── entity_override: per-derivative entity-field overrides (M0 scope = entity
-- FIELDS only; relationship/event overrides are DEFERRED). `target_entity_id` is the
-- overridden entity (cross-DB glossary/knowledge id, no FK); `overridden_fields` is
-- the field→value JSON delta. PERSISTED here; the packer applies it at retrieval in
-- C25 (this cycle does NOT apply overrides — COW persist-only).
CREATE TABLE IF NOT EXISTS entity_override (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by        UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id        UUID NOT NULL,
  book_id           UUID NOT NULL,   -- tenancy scope key (25 M1/M2; derived via work_id)
  work_id           UUID NOT NULL REFERENCES composition_work(id) ON DELETE CASCADE,
  target_entity_id  UUID NOT NULL,
  overridden_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entity_override_work ON entity_override(work_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_override_work_target
  ON entity_override(work_id, target_entity_id);

-- ── structure_template: pluggable story-structure library (global built-ins + user-custom)
CREATE TABLE IF NOT EXISTS structure_template (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID,
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL DEFAULT 'generic',
  beats         JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_structure_template_owner ON structure_template(owner_user_id);

-- ── outline_node: Arc→Chapter→Scene→Beat tree (also = Scene-Graph nodes)
CREATE TABLE IF NOT EXISTS outline_node (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by         UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id         UUID NOT NULL,
  book_id            UUID NOT NULL,   -- tenancy scope key (25 M1/M2, backfilled via the Work)
  parent_id          UUID REFERENCES outline_node(id) ON DELETE CASCADE,
  kind               TEXT NOT NULL CHECK (kind IN ('arc','chapter','scene','beat')),
  rank               TEXT NOT NULL,
  title              TEXT NOT NULL DEFAULT '',
  pov_entity_id      UUID,
  present_entity_ids UUID[] NOT NULL DEFAULT '{}',
  goal               TEXT NOT NULL DEFAULT '',
  beat_role          TEXT,
  status             TEXT NOT NULL DEFAULT 'empty' CHECK (status IN ('empty','outline','drafting','done')),
  chapter_id         UUID,
  tension            SMALLINT,
  story_order        INT,
  synopsis           TEXT NOT NULL DEFAULT '',
  version            INT NOT NULL DEFAULT 1,
  is_archived        BOOLEAN NOT NULL DEFAULT false,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT outline_chapter_required  CHECK (kind NOT IN ('chapter','scene') OR chapter_id IS NOT NULL),
  -- T1.2 Beat Sheet: beat_role may live on a scene OR a chapter (arcs/beats excluded).
  CONSTRAINT outline_beatrole_kind     CHECK (beat_role IS NULL OR kind IN ('scene','chapter'))
);
CREATE INDEX IF NOT EXISTS idx_outline_node_project ON outline_node(project_id) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_outline_node_parent  ON outline_node(parent_id, rank);
CREATE INDEX IF NOT EXISTS idx_outline_node_chapter ON outline_node(chapter_id) WHERE kind = 'scene';
-- #02 manuscript navigator lazy-children: list_children ORDERs BY + keyset-compares
-- `rank COLLATE "C"` (byte order), which a DEFAULT-collation index cannot serve (Postgres
-- would Sort every page). Match the collation so the keyset is an index range-scan for a
-- giant outlined book. `id` is the keyset tiebreak; the partial matches the default query.
CREATE INDEX IF NOT EXISTS idx_outline_node_children_keyset
  ON outline_node(parent_id, rank COLLATE "C", id) WHERE NOT is_archived;
-- D-ARC-ARCHIVE-CHAPTER-STRANDING (spec 32a §B): a recovery slot so archiving an arc can
-- RETURN its member chapters to the unplanned pool (structure_node_id → NULL) while remembering
-- which arc they belonged to, and restore() can re-attach exactly those. Nullable, no backfill.
-- Partial index serves restore()'s reverse lookup (WHERE archived_from_structure_node_id IN subtree).
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS archived_from_structure_node_id UUID;
CREATE INDEX IF NOT EXISTS idx_outline_node_archived_from
  ON outline_node(archived_from_structure_node_id) WHERE archived_from_structure_node_id IS NOT NULL;

-- ── scene_link: ONLY non-derivable edges
CREATE TABLE IF NOT EXISTS scene_link (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by   UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id   UUID NOT NULL,
  book_id      UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  from_node_id UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  to_node_id   UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL DEFAULT 'setup_payoff' CHECK (kind IN ('setup_payoff','custom')),
  label        TEXT NOT NULL DEFAULT '',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scene_link_distinct CHECK (from_node_id <> to_node_id),
  UNIQUE (from_node_id, to_node_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_scene_link_project ON scene_link(project_id);
CREATE INDEX IF NOT EXISTS idx_scene_link_from    ON scene_link(from_node_id);

-- ── canon_rule: author-declared invariants (from/until on the knowledge timeline axis)
CREATE TABLE IF NOT EXISTS canon_rule (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by  UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id  UUID NOT NULL,
  book_id     UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  text        TEXT NOT NULL,
  scope       TEXT NOT NULL DEFAULT 'world' CHECK (scope IN ('world','entity','reveal_gate')),
  entity_id   UUID,
  from_order  INT,
  until_order INT,
  kind        TEXT,
  active      BOOLEAN NOT NULL DEFAULT true,
  version     INT NOT NULL DEFAULT 1,
  is_archived BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_canon_rule_project ON canon_rule(project_id) WHERE active AND NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_canon_rule_entity  ON canon_rule(entity_id) WHERE entity_id IS NOT NULL;

-- ── generation_job: AI generation + critic tracking (base_revision_id = OI-2 staleness guard)
CREATE TABLE IF NOT EXISTS generation_job (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by         UUID NOT NULL,   -- actor stamp (25 M3) — spend stays keyed to the acting caller (BYOK)
  project_id         UUID NOT NULL,
  book_id            UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  outline_node_id    UUID REFERENCES outline_node(id) ON DELETE SET NULL,
  operation          TEXT NOT NULL,
  mode               TEXT NOT NULL DEFAULT 'cowrite' CHECK (mode IN ('cowrite','auto')),
  status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed','cancelled')),
  llm_job_id         UUID,
  input              JSONB NOT NULL DEFAULT '{}'::jsonb,
  result             JSONB,
  critic             JSONB,
  target_chapter_id  UUID,
  base_revision_id   UUID,
  target_revision_id UUID,
  cost_usd           NUMERIC(10,4) NOT NULL DEFAULT 0,
  idempotency_key    TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_generation_job_idem ON generation_job(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_generation_job_project ON generation_job(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generation_job_node    ON generation_job(outline_node_id);
-- Cycle-2 chapter in-flight guard: the per-(project,chapter) guard scans
-- chapter-level jobs by input->>'chapter_id'. Partial expression index over only
-- node-less (chapter-level) jobs keeps it cheap as job history grows (the static
-- outline_node_id IS NULL predicate is plan-matchable; status is filtered after).
CREATE INDEX IF NOT EXISTS idx_generation_job_chapter_inflight
  ON generation_job((input->>'chapter_id')) WHERE outline_node_id IS NULL;
-- Cycle-6 reaper + cycle-2 guard: both scan only NON-terminal jobs by created_at
-- (the global sweep marks stale active jobs failed; the in-flight guard filters
-- active-and-recent). A partial index on the active rows keeps both off a full
-- scan as completed/failed history accumulates.
CREATE INDEX IF NOT EXISTS idx_generation_job_active
  ON generation_job(created_at) WHERE status IN ('pending','running');
-- Unified Job Control Plane reconcile source: GET /internal/composition/jobs?since=
-- filters generation_job by updated_at — index it so the periodic sweep isn't a seq-scan.
CREATE INDEX IF NOT EXISTS idx_generation_job_updated_at ON generation_job(updated_at);

-- ── narrative_thread: the promise/foreshadow/MICE constraint ledger (cycle 14,
-- reasoning-engine spec §5.2/§10.2). ADVISORY (spec D4): a flag + a re-injection
-- signal, NOT a hard commit gate (PAY/DEBT detection is fuzzy). Keyed on
-- project_id (= the Work id, codebase convention for the spec's `work_id`).
-- Lifecycle: open → progressing → paid | dropped. The open/progressing set is
-- the re-injectable "open promises" the reasoning loop carries (F2) + the
-- arc-end unpaid-debt check (foreshadow-drop §7). MICE = kind='mice_thread'
-- with LIFO `nesting_depth` (innermost closes first).
CREATE TABLE IF NOT EXISTS narrative_thread (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by     UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id     UUID NOT NULL,
  book_id        UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  kind           TEXT NOT NULL CHECK (kind IN ('promise','foreshadow','question','mice_thread')),
  status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','progressing','paid','dropped')),
  -- in-DB FKs to outline_node (same DB) — the codebase convention for node refs
  -- (cf. generation_job.outline_node_id). SET NULL on delete so a removed node
  -- leaves the thread intact but un-anchored, not dangling.
  opened_at_node UUID REFERENCES outline_node(id) ON DELETE SET NULL,
  payoff_node    UUID REFERENCES outline_node(id) ON DELETE SET NULL,
  trigger        TEXT NOT NULL DEFAULT '',
  nesting_depth  INT NOT NULL DEFAULT 0,
  priority       SMALLINT NOT NULL DEFAULT 50,
  summary        TEXT NOT NULL DEFAULT '',
  version        INT NOT NULL DEFAULT 1,
  is_archived    BOOLEAN NOT NULL DEFAULT false,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- a payoff_node is only meaningful once the thread is paid.
  CONSTRAINT narrative_thread_payoff_paid CHECK (payoff_node IS NULL OR status = 'paid')
);
CREATE INDEX IF NOT EXISTS idx_narrative_thread_project ON narrative_thread(project_id) WHERE NOT is_archived;
-- the hot read: the open-set re-injected into every primitive (F2).
CREATE INDEX IF NOT EXISTS idx_narrative_thread_open
  ON narrative_thread(project_id, status) WHERE status IN ('open','progressing') AND NOT is_archived;

-- generation_run.state (spec §10.3): persisted ReasoningState for resumable auto
-- runs + the re-injected open-thread set. `generation_run` IS generation_job here.
ALTER TABLE generation_job ADD COLUMN IF NOT EXISTS state JSONB;

-- T1.2 Beat Sheet: relax the legacy scene-only beat_role CHECK so a CHAPTER can
-- also carry a beat_role (manual beat-assign at chapter level). Idempotent: the
-- DO-block no-ops once the new constraint exists (no re-validate on every boot).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'outline_beatrole_kind') THEN
    ALTER TABLE outline_node DROP CONSTRAINT IF EXISTS outline_beatrole_scene;
    ALTER TABLE outline_node ADD CONSTRAINT outline_beatrole_kind
      CHECK (beat_role IS NULL OR kind IN ('scene','chapter'));
  END IF;
END $$;

-- ── generation_correction: the human-gate signal (V1 correction flywheel, §3).
-- ONE row per author correction on a generation. Only GENUINE-AUTHOR-CHOICE kinds
-- are captured (accept-as-is is NOT a correction — §2 H2 self-reinforcement guard).
-- raw_before/raw_after are NULL unless the work opted into capture_correction_prose
-- (§5 — structural + change-magnitude is always captured; verbatim prose is gated).
-- job_id FK is in-DB (same database, §1.4 OK); project_id is cross-DB (no FK).
CREATE TABLE IF NOT EXISTS generation_correction (
  id                     UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by             UUID NOT NULL,   -- actor stamp (25 M3) — the corrector, stored never filtered
  project_id             UUID NOT NULL,
  book_id                UUID NOT NULL,   -- tenancy scope key (25 M1/M2; derived via job_id)
  job_id                 UUID NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE,
  kind                   TEXT NOT NULL CHECK (kind IN ('edit','pick_different','regenerate','reject')),
  chosen_candidate_index INT,
  guidance               TEXT,
  changed_blocks         INT,
  raw_before             TEXT,
  raw_after              TEXT,
  regenerated_to_job_id  UUID REFERENCES generation_job(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- pick_different is meaningless without the candidate it points at.
  CONSTRAINT correction_pick_needs_index CHECK (kind <> 'pick_different' OR chosen_candidate_index IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_generation_correction_job  ON generation_correction(job_id);
-- Name predates the 25 M3 rename (kept so migrated + fresh DBs converge — a RENAME
-- COLUMN cascades an index's definition but not its name). Guarded: on a legacy
-- boot this runs BEFORE the rename, where the column is still user_id and the
-- old-shape index already exists.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'generation_correction' AND column_name = 'created_by') THEN
    CREATE INDEX IF NOT EXISTS idx_generation_correction_user ON generation_correction(created_by, created_at DESC);
  END IF;
END $$;

-- ── outbox_events: standard (matches knowledge-service); relayed → loreweave:events:composition
CREATE TABLE IF NOT EXISTS outbox_events (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'composition',
  aggregate_id   UUID NOT NULL,
  event_type     TEXT NOT NULL,
  payload        JSONB NOT NULL DEFAULT '{}',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ,
  retry_count    INT NOT NULL DEFAULT 0,
  last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(created_at) WHERE published_at IS NULL;

-- ── decompose_commit: exactly-once ledger for A3 decompose-commit (idempotency).
-- A client idempotency_key dedups a double-submit / retried commit so the
-- arc→chapter→scene tree is never persisted twice (D-A3-COMMIT-IDEMPOTENCY). The
-- stored `result` lets a replay return the original ids without re-inserting.
-- project_id is cross-DB (no FK); the unique index is the exactly-once guard.
-- Scope = (PROJECT, key) — 25 PM-10: the per-user leg dropped with the re-key,
-- but the discriminator stays the PROJECT (not the book): a derivative replaying
-- a client key must NOT be handed the SOURCE Work's stored result.
CREATE TABLE IF NOT EXISTS decompose_commit (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by      UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id      UUID NOT NULL,
  book_id         UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  idempotency_key TEXT NOT NULL,
  -- 25 M4.4 (PM-10): arc_id → structure_node_id (the lift re-points legacy values through the map,
  -- then renames the column; the CREATE carries the final name so a fresh DB matches).
  structure_node_id UUID NOT NULL,
  result          JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Final (PM-10) shape; on a legacy DB the old (user_id, project_id, key) index
-- no-ops this create and package_rekey M3.2 drops + recreates it in this shape.
CREATE UNIQUE INDEX IF NOT EXISTS idx_decompose_commit_idem ON decompose_commit(project_id, idempotency_key);

-- ── scene_grounding_pins: LOOM T3.4 — per-scene author steering of the injected
-- grounding context. One row per addressed item (present-entity / canon-rule /
-- lore-source): action='pin' force-keeps it through the budget trim, action=
-- 'exclude' drops it from the pack. Honored by BOTH the grounding preview and the
-- engine generation (same pack() chokepoint) so preview == what the model sees.
-- item_id is a STABLE canonical id (glossary anchor / canon_rule uuid / lore
-- source_id) — NOT a localized label — so a pin survives a reader-language switch
-- or a derivative override. UNIQUE(project, scene, type, id) ⇒ pin⇄exclude flips
-- in place (upsert); a CASCADE drop with the scene leaves no orphan.
CREATE TABLE IF NOT EXISTS scene_grounding_pins (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by      UUID NOT NULL,   -- actor stamp (25 M3) — stored, never filtered on
  project_id      UUID NOT NULL,
  book_id         UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  outline_node_id UUID NOT NULL REFERENCES outline_node(id) ON DELETE CASCADE,
  item_type       TEXT NOT NULL CHECK (item_type IN ('present','canon','lore')),
  item_id         TEXT NOT NULL,
  action          TEXT NOT NULL CHECK (action IN ('pin','exclude')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scene_grounding_pins_item
  ON scene_grounding_pins(project_id, outline_node_id, item_type, item_id);
-- Definition converges with the 25 M3 rename-cascade (created_by leading — the
-- project-scoped reads are served by idx_scene_grounding_pins_item above).
-- Guarded for the legacy pre-rename boot, same as idx_generation_correction_user.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'scene_grounding_pins' AND column_name = 'created_by') THEN
    CREATE INDEX IF NOT EXISTS idx_scene_grounding_pins_scene
      ON scene_grounding_pins(created_by, project_id, outline_node_id);
  END IF;
END $$;

-- ── composition_daily_progress: LOOM T4.2 — server-SSOT writing progress stats.
-- One row per (work, chapter, local-date): `words` is the chapter's TOTAL word
-- count as last reported on that local date (a SNAPSHOT, NOT a delta) — the client
-- reports the active chapter's current word count on save, keyed to its LOCAL date
-- (PO 2026-06-24: snapshot/server-differenced for multi-device correctness). The
-- per-day authored count is then DERIVED server-side by differencing successive
-- snapshots; the per-chapter book total = the sum of each chapter's latest snapshot.
-- PK(user,project,chapter,date) ⇒ the report upsert is IDEMPOTENT per local date
-- (a re-save the same day overwrites that day's snapshot, last-write-wins). `words`
-- is the user's OWN studio stat (per-user predicate everywhere) — no cross-tenant read.
CREATE TABLE IF NOT EXISTS composition_daily_progress (
  user_id        UUID NOT NULL,
  project_id     UUID NOT NULL,
  chapter_id     UUID NOT NULL,
  snapshot_date  DATE NOT NULL,
  words          INT  NOT NULL CHECK (words >= 0),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id, chapter_id, snapshot_date)
);
-- the windowed read (day-words diff + book total) scans by (work, date) across chapters
CREATE INDEX IF NOT EXISTS idx_comp_daily_progress_work_date
  ON composition_daily_progress(user_id, project_id, snapshot_date);

-- ── composition_progress_baseline: LOOM T4.2 — the per-chapter PRE-EXISTING word
-- count captured the FIRST time a chapter is opened after progress tracking starts.
-- It is the reference point the chapter's first daily snapshot diffs against, so a
-- chapter's pre-existing content is NOT counted as "written today" (no enablement
-- spike) while a brand-new chapter (opened at ~0 words) baselines at ~0 and so its
-- writing counts fully from word one. Captured ONCE per chapter (the report upsert is
-- ON CONFLICT DO NOTHING — re-opening a chapter must NOT reset the baseline to its now
-- larger count, which would erase recorded progress). Per-user (own studio stat).
CREATE TABLE IF NOT EXISTS composition_progress_baseline (
  user_id     UUID NOT NULL,
  project_id  UUID NOT NULL,
  chapter_id  UUID NOT NULL,
  words       INT  NOT NULL CHECK (words >= 0),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id, chapter_id)
);

-- ── composition_progress_goal: BE-P2 — the writer's PER-USER daily word goal.
-- The goal used to live in work.settings.daily_goal — a SHARED per-book package row
-- every EDIT grantee could write, so one user's goal became everyone's (the tenancy
-- bug class of the entity_kinds shared-row incident; CLAUDE.md User Boundaries). The
-- daily-progress stats are already per-user; the goal must be too. NO book_id: the
-- siblings above have none, the E0 grant is gated at the router before the repo, and a
-- book_id here would be written-and-never-read (the write-only bug). PK (user, project).
CREATE TABLE IF NOT EXISTS composition_progress_goal (
  user_id     UUID NOT NULL,
  project_id  UUID NOT NULL,
  daily_goal  INT  NOT NULL CHECK (daily_goal >= 0),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id)
);

-- ── style_profile: LOOM T3.5 — per-scope prose-style steering (Density + Pace,
-- 0-100). Scoped work | chapter | scene so a scene can override its chapter which
-- overrides the book default; the packer resolves the MOST SPECIFIC row for the
-- target scene (scene > chapter > work) and threads density/pace into the draft
-- prompts. `scope_id` is the project_id (work), chapter_id (chapter) or outline
-- node_id (scene) — never null, so the PK is clean. SHARED package row (25 M3.4):
-- the PK is package-scoped so a grantee edit UPDATES the shared row in place;
-- created_by is a plain actor stamp OUTSIDE row identity (DA-11).
CREATE TABLE IF NOT EXISTS style_profile (
  created_by  UUID NOT NULL,
  project_id  UUID NOT NULL,
  book_id     UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  scope_type  TEXT NOT NULL CHECK (scope_type IN ('work','chapter','scene')),
  scope_id    UUID NOT NULL,
  density     INT  NOT NULL CHECK (density BETWEEN 0 AND 100),
  pace        INT  NOT NULL CHECK (pace BETWEEN 0 AND 100),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, scope_type, scope_id)
);

-- ── voice_profile: LOOM T3.5 — per-character voice tags (e.g. terse, understatement,
-- no purple prose). Keyed by entity_id (the glossary/knowledge entity); `entity_name`
-- is denormalized so the packer renders the directive without a name lookup. The
-- packer injects a character's tags ONLY when that entity is PRESENT in the scene.
-- `tags` is a JSON array of short strings. SHARED package row (25 M3.4): package-
-- scoped PK, created_by = plain actor stamp outside row identity (DA-11).
CREATE TABLE IF NOT EXISTS voice_profile (
  created_by   UUID NOT NULL,
  project_id   UUID NOT NULL,
  book_id      UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  entity_id    UUID NOT NULL,
  entity_name  TEXT NOT NULL,
  tags         JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, entity_id)
);

-- ── reference_source: LOOM T3.6 — the author's per-Work reference shelf (external
-- influences / passages, with source attribution). composition-OWNED authoring data
-- (NOT knowledge-graph content): the content is embedded via provider-registry
-- /internal/embed and the vector is stored HERE as a plain `real[]` (a reference
-- shelf is small — dozens to low-hundreds of rows — so retrieval is brute-force
-- cosine top-K in app code; no pgvector extension / ivfflat index / fixed-dimension
-- column needed). All rows of a Work share ONE embedding model (work.settings.
-- reference_embed_model_ref, set write-through on first add) so the vectors live in
-- one space. `embedding` is NULL only transiently if an embed failed at insert (the
-- router rejects that path; a null-vector row is simply never a search hit).
-- Package-visible (25 OQ-5): the shelf steers shared generation, so reads key on
-- project_id/book_id behind the E0 book gate; created_by is the actor stamp.
CREATE TABLE IF NOT EXISTS reference_source (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by      UUID NOT NULL,
  project_id      UUID NOT NULL,
  book_id         UUID NOT NULL,   -- tenancy scope key (25 M1/M2)
  title           TEXT NOT NULL DEFAULT '',
  author          TEXT NOT NULL DEFAULT '',
  source_url      TEXT NOT NULL DEFAULT '',
  content         TEXT NOT NULL,
  embedding       REAL[],
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_dim   INT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Definition converges with the 25 M3 rename-cascade (created_by leading; the
-- book-scoped reads are served by idx_reference_source_book above, the
-- project-scoped reads by idx_reference_source_project_read below).
-- Guarded for the legacy pre-rename boot.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'reference_source' AND column_name = 'created_by') THEN
    CREATE INDEX IF NOT EXISTS idx_reference_source_project
      ON reference_source(created_by, project_id, created_at DESC);
  END IF;
END $$;
-- 25 M3.3 rename-cascade perf fix: the actor RENAME cascaded the old
-- idx_reference_source_project to a created_by-LEADING definition (above), so the
-- project-scoped reads that replaced the per-user ones — ReferencesRepo.list(project_id)
-- and search(project_id, …), the latter on pack()'s generation HOT PATH — lost their
-- covering index and now seq-scan. Restore a project-leading read index. Additive +
-- IF NOT EXISTS (project_id is never renamed) so it rides both the fresh and migrated
-- boots, without the created_by column-existence guard the cascade index needs.
CREATE INDEX IF NOT EXISTS idx_reference_source_project_read
  ON reference_source(project_id, created_at DESC);

-- T3.6 — let a scene pin/exclude a reference too. Extend the T3.4 item_type CHECK
-- from ('present','canon','lore') to include 'reference'. Idempotent: the DO-block
-- DROPs + re-ADDs the named constraint only when 'reference' isn't yet allowed (a
-- probe INSERT into the catalog check would be fragile, so we test the constraint
-- definition text). The UNIQUE/scene indexes are unaffected.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'scene_grounding_pins_item_type_check'
      AND conrelid = 'scene_grounding_pins'::regclass
      AND pg_get_constraintdef(oid) LIKE '%reference%'
  ) THEN
    ALTER TABLE scene_grounding_pins DROP CONSTRAINT IF EXISTS scene_grounding_pins_item_type_check;
    ALTER TABLE scene_grounding_pins ADD CONSTRAINT scene_grounding_pins_item_type_check
      CHECK (item_type IN ('present','canon','lore','reference'));
  END IF;
END $$;

-- ════════════════════════════════════════════════════════════════════════════
-- 25 M1 — EXPAND (additive DDL for the book-package re-key; spec 25 lines 190-219).
-- On a LEGACY DB these ALTERs add the columns NULLABLE; package_rekey's M2 backfills
-- them from composition_work and flips NOT NULL. On a FRESH DB the CREATE TABLE
-- texts above already declare book_id NOT NULL, so every statement here no-ops.
-- ════════════════════════════════════════════════════════════════════════════

-- M1.1 · book_id on the 12 BPS-1 tables + generation_correction (nullable until M2)
ALTER TABLE outline_node          ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE scene_link            ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE narrative_thread      ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE canon_rule            ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE style_profile         ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE voice_profile         ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE scene_grounding_pins  ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE divergence_spec       ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE entity_override       ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE reference_source      ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE generation_job        ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE decompose_commit      ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE generation_correction ADD COLUMN IF NOT EXISTS book_id UUID;

-- M1.2 · book-scoped read indexes (partials mirror the existing project ones)
CREATE INDEX IF NOT EXISTS idx_outline_node_book      ON outline_node(book_id)      WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_generation_job_book    ON generation_job(book_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_canon_rule_book        ON canon_rule(book_id)        WHERE active AND NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_narrative_thread_book  ON narrative_thread(book_id)  WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_scene_link_book        ON scene_link(book_id);
CREATE INDEX IF NOT EXISTS idx_reference_source_book  ON reference_source(book_id, created_at DESC);
-- plain (book_id) indexes for the rest, same IF NOT EXISTS shape:
CREATE INDEX IF NOT EXISTS idx_style_profile_book         ON style_profile(book_id);
CREATE INDEX IF NOT EXISTS idx_voice_profile_book         ON voice_profile(book_id);
CREATE INDEX IF NOT EXISTS idx_scene_grounding_pins_book  ON scene_grounding_pins(book_id);
CREATE INDEX IF NOT EXISTS idx_divergence_spec_book       ON divergence_spec(book_id);
CREATE INDEX IF NOT EXISTS idx_entity_override_book       ON entity_override(book_id);
CREATE INDEX IF NOT EXISTS idx_decompose_commit_book      ON decompose_commit(book_id);
CREATE INDEX IF NOT EXISTS idx_generation_correction_book ON generation_correction(book_id);

-- (M1.3 — the structure_node spec tree + the outline_node/motif_application
-- attachment columns — lives in _MOTIF_SCHEMA_SQL below: structure_node FKs
-- arc_template, which is created there, after this block.)

-- 22 SC4 · authored intent, all four field groups (column list owned by 22;
-- exit_state is the SC12 versioned {v:1,…} envelope, validated by the Pydantic
-- model on write — see app/db/models.py SceneExitState).
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS location_entity_id UUID;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS story_time   TEXT;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS conflict     TEXT NOT NULL DEFAULT '';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS outcome      TEXT NOT NULL DEFAULT '';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS value_shift  SMALLINT
  CHECK (value_shift IS NULL OR value_shift BETWEEN -100 AND 100);
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS stakes       TEXT NOT NULL DEFAULT '';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS target_words INT
  CHECK (target_words IS NULL OR target_words > 0);
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS exit_state   JSONB;     -- SC12, {v:1,…}
"""

# C23 down-migration (round-trip proof only — the live schema is idempotent-forward
# like knowledge-service, applied on every boot). Drops the dị bản substrate in
# dependency order: the two child tables first, then the GUARD constraint, then the
# two columns + their index. Leaves the C16 re-key + the rest of the schema intact so
# up→down→up restores exactly (no residue). Mirrors book-service C20's WorldsDownSQL.
# NOTE (25 PM-4): dropping source_work_id implicitly drops uq_composition_work_book
# (its partial predicate references the column); the forward re-run recreates it —
# the round-trip still restores exactly.
C23_DOWN_SQL = """
DROP TABLE IF EXISTS entity_override;
DROP TABLE IF EXISTS divergence_spec;
ALTER TABLE composition_work DROP CONSTRAINT IF EXISTS chk_derivative_project_required;
DROP INDEX IF EXISTS idx_composition_work_source;
ALTER TABLE composition_work DROP COLUMN IF EXISTS branch_point;
ALTER TABLE composition_work DROP COLUMN IF EXISTS source_work_id;
"""

# ════════════════════════════════════════════════════════════════════════════
# NARRATIVE MOTIF LIBRARY (spec §R1.4 + 00-RECONCILE §1 deltas). 2-tier (User-owned
# + System), NO book tier — a motif is book-INDEPENDENT and survives book deletion;
# per-book customization = clone the template. Tenancy is enforced at the DB (the
# partials + the motif_user_owned CHECK + the cross-tier link trigger) — audit B-2/H-2.
# Executed AFTER _SCHEMA_SQL (so outline_node exists before motif_application FKs it).
# ════════════════════════════════════════════════════════════════════════════
_MOTIF_SCHEMA_SQL = """
-- ── motif: the library unit (system tier = owner_user_id NULL, seed/migrate-only;
-- user tier = owner set). `language` is first-class + part of the dedup/embed key
-- (R1.1.3). ONE platform embedding model for ALL motif vectors (embedding_model is a
-- fixed platform id, NOT a per-row/per-user choice — R1.1.2/B-1).
CREATE TABLE IF NOT EXISTS motif (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id   UUID,                                   -- NULL = system (seed/migrate-only); else the creator (attribution + the tenancy backstop)
  book_id         UUID,                                   -- per-book label (D-MOTIF-ADOPT-PER-BOOK); NULL = global user/system tier
  book_shared     BOOLEAN NOT NULL DEFAULT false,         -- D-MOTIF-ADOPT-BOOK-COLLAB-TIER (model B): true = the book's SHARED tier (visible to the book's VIEW-grantees, writable by EDIT-grantees, access = the book grant resolved at the caller — owner is attribution only); false = model-A private label / global / system
  code            TEXT NOT NULL,
  language        TEXT NOT NULL DEFAULT 'en',             -- part of the dedup/embed key (R1.1.3)
  visibility      TEXT NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('private','unlisted','public')),
  kind            TEXT NOT NULL DEFAULT 'sequence'
                    CHECK (kind IN ('sequence','situation','hook','emotion_arc','trope','pattern','scheme')),
  category        TEXT,
  name            TEXT NOT NULL,
  summary         TEXT NOT NULL DEFAULT '',               -- the embedded text
  genre_tags      TEXT[] NOT NULL DEFAULT '{}',
  roles           JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{key, actant, label, constraints}]
  beats           JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{key, label, intent, tension_target, order, reversal?, alliance_shift?}]
  preconditions   JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{text}]
  effects         JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{text}]
  info_asymmetry  JSONB,                                  -- §15.1 scheme {knows,deceived,gap} (nullable, motif-level — conformance reads it)
  annotations     JSONB NOT NULL DEFAULT '{}'::jsonb,     -- RECONCILE D1: template-level scheme/info-asymmetry props (W7 seeds, W5 reads on the motif)
  tension_target  SMALLINT,                               -- overall 1..5
  emotion_target  TEXT,
  examples        JSONB NOT NULL DEFAULT '[]'::jsonb,     -- [{text}] — STRIPPED on imported-derived publish (trigger below)
  abstraction_confidence TEXT,                            -- mined: high|med|low
  source          TEXT NOT NULL DEFAULT 'authored'
                    CHECK (source IN ('authored','mined','adopted','imported')),
  -- B-3 lineage taint: an 'adopted' clone loses the 'imported' source marker, so the
  -- publish-strip trigger (keyed on source='imported') would MISS an adopted clone of
  -- an imported motif and leak its source passages on publish. clone() propagates this
  -- flag down the lineage (src.source='imported' OR src.imported_derived) so the
  -- trigger strips an adopted-from-imported row too — what W1's design expects (W1 §1
  -- "source IN ('imported','adopted'-from-imported)"). 'adopted'-from-AUTHORED stays
  -- false (those examples are legitimately shareable), so the strip is not over-broad.
  imported_derived BOOLEAN NOT NULL DEFAULT false,
  source_ref      TEXT,                                   -- lineage; opaque token on imported-derived publish (B-3)
  source_version  INT,                                    -- N-4 upstream 3-way-diff version pin
  adopted_base    JSONB,                                  -- D-MOTIF-SYNC-3WAY-BASE: snapshot of the upstream's mergeable fields AT adopt time (the true 3-way merge base; NULL = non-adopted)
  embedding       REAL[],                                 -- brute-force cosine (reference_source precedent); NULL at seed (RECONCILE D4, W3 back-fills)
  embedding_model TEXT NOT NULL DEFAULT '',               -- ONE platform model (B-1); no per-row choice
  embedding_dim   INT,
  embedded_summary_hash TEXT,                             -- re-embed staleness guard (motifs are mutable)
  judge_score     NUMERIC(4,3),
  mining_support  INT,
  status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('draft','active','archived')),
  version         INT NOT NULL DEFAULT 1,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- B-2: a both-NULL (system) row must be a published/system row, never a private
  -- orphan. The user-write path additionally server-stamps owner_user_id (app code);
  -- this CHECK is the DB backstop that a private row ALWAYS has an owner.
  CONSTRAINT motif_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private'),
  -- D-MOTIF-ADOPT-BOOK-COLLAB-TIER: a SHARED row must carry a book + a creator (owner) AND stay
  -- private — the public-catalog axis (visibility='public') and the shared-tier axis (book_shared)
  -- are ORTHOGONAL, so a shared row can NEVER leak into global public discovery.
  CONSTRAINT motif_book_shared_shape CHECK (
    NOT book_shared OR (book_id IS NOT NULL AND owner_user_id IS NOT NULL AND visibility = 'private')
  )
);
-- On an EXISTING model-A DB the CREATE TABLE above is a no-op, so the partials below that
-- reference book_shared (D-MOTIF-ADOPT-BOOK-COLLAB-TIER) would fail — add the column FIRST here
-- (idempotent; a no-op on a fresh DB where CREATE TABLE already declared it). The shape CHECK +
-- the model-A re-narrow live in the ALTER block lower down (guarded for existing DBs).
ALTER TABLE motif ADD COLUMN IF NOT EXISTS book_shared BOOLEAN NOT NULL DEFAULT false;
-- tenancy partials keyed incl. language (R1.1.3). A user's GLOBAL tier (book_id NULL) and
-- PER-BOOK labels (book_id set, D-MOTIF-ADOPT-PER-BOOK = model A book-scoped filter) dedup
-- INDEPENDENTLY, so the same source may be adopted globally AND into a book without a false
-- code collision (the confirm path uses clone(), which raises on collision). The read
-- predicate is UNCHANGED — book_id only narrows what the OWNER sees, never widens visibility.
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_user
  ON motif(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL AND book_id IS NULL;
-- model-A private book label: per-(owner,book) dedup, scoped to NOT shared. The SHARED tier
-- (book_shared) dedups per-BOOK instead (uq_motif_book_shared) — one code+language per book
-- across ALL collaborators, so two grantees can't fork the same shared code.
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_user_book
  ON motif(owner_user_id, book_id, code, language) WHERE book_id IS NOT NULL AND NOT book_shared;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_book_shared
  ON motif(book_id, code, language) WHERE book_shared;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_system
  ON motif(code, language)                WHERE owner_user_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_motif_owner  ON motif(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_motif_book   ON motif(book_id)        WHERE book_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_motif_book_shared ON motif(book_id)   WHERE book_shared;
CREATE INDEX IF NOT EXISTS idx_motif_public ON motif(visibility, updated_at DESC) WHERE visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_motif_genre  ON motif USING GIN (genre_tags);
-- retrieval pre-filter (genre ∩ + status + tier predicate) runs in SQL BEFORE loading
-- vectors (audit data-R1). The composite supports the active-status list scan.
CREATE INDEX IF NOT EXISTS idx_motif_retrieve
  ON motif(status, language) WHERE status = 'active';

-- ── motif_link: composition + legal succession + variant (ATU + plot-graph). Cycle
-- guard on precedes/composed_of (H-2) + user edges may not touch system motifs (H-2).
CREATE TABLE IF NOT EXISTS motif_link (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  from_motif_id UUID NOT NULL REFERENCES motif(id) ON DELETE CASCADE,
  to_motif_id   UUID NOT NULL REFERENCES motif(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL CHECK (kind IN ('composed_of','precedes','variant_of')),
  ord           INT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT motif_link_distinct CHECK (from_motif_id <> to_motif_id),
  UNIQUE (from_motif_id, to_motif_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_motif_link_from ON motif_link(from_motif_id, kind, ord);
CREATE INDEX IF NOT EXISTS idx_motif_link_to   ON motif_link(to_motif_id, kind);

-- H-2 same-tier guard + cycle guard (BEFORE INSERT on motif_link). A user-created
-- edge may not span into a system motif (a user must not reshape the shared graph),
-- and a precedes/composed_of insert may not close a cycle. Idempotent via CREATE OR
-- REPLACE; the trigger is (re)attached in a guarded DO-block.
CREATE OR REPLACE FUNCTION motif_link_guard() RETURNS trigger AS $$
DECLARE
  from_owner UUID;  to_owner  UUID;
  from_shared BOOLEAN; to_shared BOOLEAN;
  from_book UUID; to_book UUID;
  same_tier BOOLEAN;
  cyc        BOOLEAN;
BEGIN
  SELECT owner_user_id, book_shared, book_id INTO from_owner, from_shared, from_book
    FROM motif WHERE id = NEW.from_motif_id;
  SELECT owner_user_id, book_shared, book_id INTO to_owner, to_shared, to_book
    FROM motif WHERE id = NEW.to_motif_id;
  -- same-tier rule (D-MOTIF-LINK-SHARED-TIER): a link must stay within ONE tier —
  --   • both SYSTEM (owner NULL, not shared), OR
  --   • both the SAME book's SHARED tier (book_shared AND same book_id; owners MAY differ —
  --     that is the whole point of a collaborator-shared graph), OR
  --   • both the SAME user's PRIVATE tier (same non-null owner, neither shared).
  -- A shared↔private edge (even same owner) is rejected — it would expose a private motif as a
  -- neighbor to the book's grantees (a read leak). shared↔system and cross-book shared are also
  -- rejected (a user must never reshape the shared/system graph beyond their own book's tier).
  -- every arm is kept NULL-safe (a bare `a = b` with a NULL operand yields NULL, and
  -- `IF NOT NULL` would NOT fire — so a user→system link must NOT rely on `owner = owner`).
  same_tier :=
       (from_owner IS NULL AND to_owner IS NULL AND NOT from_shared AND NOT to_shared)
    OR (from_shared AND to_shared
        AND from_book IS NOT NULL AND to_book IS NOT NULL AND from_book = to_book)
    OR (NOT from_shared AND NOT to_shared
        AND from_owner IS NOT NULL AND to_owner IS NOT NULL AND from_owner = to_owner);
  IF NOT same_tier THEN
    RAISE EXCEPTION 'motif_link cross-tier: from(owner=%,shared=%,book=%) to(owner=%,shared=%,book=%)',
      from_owner, from_shared, from_book, to_owner, to_shared, to_book
      USING ERRCODE = 'check_violation';
  END IF;
  -- cycle guard for the ordered edge kinds (variant_of is symmetric-ish, skip).
  IF NEW.kind IN ('precedes','composed_of') THEN
    WITH RECURSIVE walk(node) AS (
      SELECT NEW.to_motif_id
      UNION
      SELECT ml.to_motif_id FROM motif_link ml
        JOIN walk w ON ml.from_motif_id = w.node
       WHERE ml.kind = NEW.kind
    )
    SELECT EXISTS (SELECT 1 FROM walk WHERE node = NEW.from_motif_id) INTO cyc;
    IF cyc THEN
      RAISE EXCEPTION 'motif_link cycle on % via %', NEW.kind, NEW.from_motif_id
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'motif_link_guard_trg') THEN
    CREATE TRIGGER motif_link_guard_trg
      BEFORE INSERT ON motif_link
      FOR EACH ROW EXECUTE FUNCTION motif_link_guard();
  END IF;
END $$;

-- ── motif_application: what was applied where (binding ledger). Per-BOOK scope
-- (R1.1.4 — the anti-repetition cap + "why this scene" trace aggregate ACROSS a
-- book's collaborators). FK SET NULL keeps history if the motif is archived
-- (data-R3). motif_version pins what was bound (edge-F3).
CREATE TABLE IF NOT EXISTS motif_application (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by      UUID NOT NULL,                          -- actor stamp (25 M3/DA-11) — stored, never filtered on
  project_id      UUID NOT NULL,
  book_id         UUID NOT NULL,                          -- R1.1.4 per-book scope
  motif_id        UUID REFERENCES motif(id) ON DELETE SET NULL,
  motif_version   INT,                                    -- the bound version (trace shows bound, not live)
  outline_node_id UUID REFERENCES outline_node(id) ON DELETE CASCADE,
  role_bindings   JSONB NOT NULL DEFAULT '{}'::jsonb,     -- {role_key: glossary_entity_id}
  annotations     JSONB NOT NULL DEFAULT '{}'::jsonb,     -- data-R7 bound info_asymmetry/reversal/alliance_shift
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_motif_application_book_motif ON motif_application(book_id, motif_id);  -- data-R6 anti-repetition hot read
CREATE INDEX IF NOT EXISTS idx_motif_application_node       ON motif_application(outline_node_id);
CREATE INDEX IF NOT EXISTS idx_motif_application_project    ON motif_application(project_id, created_at DESC);
-- H-5 app-guard: outline_node_id MUST belong to project_id (a cross-project bind is
-- rejected). The in-DB FK only proves the node EXISTS, not that it is in THIS project
-- — a BEFORE INSERT trigger closes it at the DB.
CREATE OR REPLACE FUNCTION motif_application_scope_guard() RETURNS trigger AS $$
DECLARE node_project UUID;
BEGIN
  IF NEW.outline_node_id IS NOT NULL THEN
    SELECT project_id INTO node_project FROM outline_node WHERE id = NEW.outline_node_id;
    IF node_project IS NULL OR node_project <> NEW.project_id THEN
      RAISE EXCEPTION 'motif_application outline_node % not in project %',
        NEW.outline_node_id, NEW.project_id USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'motif_application_scope_guard_trg') THEN
    CREATE TRIGGER motif_application_scope_guard_trg
      BEFORE INSERT ON motif_application
      FOR EACH ROW EXECUTE FUNCTION motif_application_scope_guard();
  END IF;
END $$;

-- ── arc_template: multi-thread × motifs over a chapter span (§12.2). SAME 2-tier
-- tenancy as motif (owner set | NULL=system). layout stores a RESOLVED motif_id
-- alongside motif_code (R1.4 — so a clone/apply walks ids, not codes). ONE platform
-- embedding model. F0 ships the table + model only; W10 owns its repo.
CREATE TABLE IF NOT EXISTS arc_template (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID,                                     -- NULL = system (seed/migrate-only)
  code          TEXT NOT NULL,
  language      TEXT NOT NULL DEFAULT 'en',
  visibility    TEXT NOT NULL DEFAULT 'private'
                  CHECK (visibility IN ('private','unlisted','public')),
  name          TEXT NOT NULL,
  summary       TEXT NOT NULL DEFAULT '',
  genre_tags    TEXT[] NOT NULL DEFAULT '{}',
  chapter_span  INT,
  -- 25 M5.2 (BA5/BA10): threads→tracks, arc_roster→roster. The CREATE carries the FINAL names so a
  -- fresh DB matches the post-Deploy-2 shape; a legacy DB (old columns) converges via M5.2's guarded
  -- rename (arc_lift.py). The Pydantic/MCP field names stay threads/arc_roster (arc_template_repo
  -- aliases tracks AS threads on read) until the full BA10 API rename.
  tracks        JSONB NOT NULL DEFAULT '[]'::jsonb,       -- [{key,label}] parallel tracks (was threads)
  layout        JSONB NOT NULL DEFAULT '[]'::jsonb,       -- [{motif_code, motif_id, thread, span_start, span_end, ord, role_hints, triggers?}]
  pacing        JSONB NOT NULL DEFAULT '[]'::jsonb,
  roster        JSONB NOT NULL DEFAULT '[]'::jsonb,       -- [{key, actant, label, constraints[]}] (was arc_roster)
  source        TEXT NOT NULL DEFAULT 'authored'
                  CHECK (source IN ('authored','mined','imported')),
  imported_derived BOOLEAN NOT NULL DEFAULT false,         -- B-3 taint: imported OR adopted-from-imported
  source_ref    TEXT,
  source_version INT,
  embedding     REAL[],
  embedding_model TEXT NOT NULL DEFAULT '',
  embedding_dim INT,
  embedded_summary_hash TEXT,
  status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('draft','active','archived')),
  version       INT NOT NULL DEFAULT 1,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT arc_template_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_user
  ON arc_template(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_system
  ON arc_template(code, language)                WHERE owner_user_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_arc_template_owner  ON arc_template(owner_user_id) WHERE owner_user_id IS NOT NULL;
-- D-ARC-TEMPLATE-BOOK-TIER (34a) — the book-SHARED collaboration tier, MIRRORING the proven
-- motif.book_shared (model B): access = the book grant resolved at the caller (owner is attribution
-- only; an EDIT-grantee who is not the owner may edit; a non-grantee sees nothing). Columns first.
ALTER TABLE arc_template ADD COLUMN IF NOT EXISTS book_id     UUID;
ALTER TABLE arc_template ADD COLUMN IF NOT EXISTS book_shared BOOLEAN NOT NULL DEFAULT false;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'arc_template_book_shared_shape') THEN
    -- both-or-neither shape (identical to motif_book_shared_shape): a shared row carries a book + an
    -- owner + stays visibility='private' (the shared axis and the public-catalog axis are disjoint).
    ALTER TABLE arc_template ADD CONSTRAINT arc_template_book_shared_shape
      CHECK (NOT book_shared OR (book_id IS NOT NULL AND owner_user_id IS NOT NULL AND visibility = 'private'));
  END IF;
END $$;
-- The per-user dedup must now be scoped to book_id IS NULL, so a user's private lib and a book-shared
-- clone of the same code coexist; the shared tier dedups PER BOOK. Create the replacement BEFORE
-- dropping the old (no window with zero uniqueness).
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_user_nobook
  ON arc_template(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL AND book_id IS NULL;
DROP INDEX IF EXISTS uq_arc_template_user;
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_book_shared
  ON arc_template(book_id, code, language) WHERE book_id IS NOT NULL AND book_shared;
CREATE INDEX IF NOT EXISTS idx_arc_template_book ON arc_template(book_id) WHERE book_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_arc_template_public ON arc_template(visibility, updated_at DESC) WHERE visibility = 'public';
CREATE INDEX IF NOT EXISTS idx_arc_template_genre  ON arc_template USING GIN (genre_tags);

-- ── import_source: the 拆文 deconstruct INPUT (§12.3/§12.6). Per-user/per-book tier
-- ONLY — STRUCTURALLY un-shareable: there is NO visibility column (audit B-3 / the
-- copyright split). Raw imported text stays in the user's own store; only the DERIVED
-- abstract template (arc_template/motif) is ever shareable. F0 ships the table; W9
-- owns its repo.
CREATE TABLE IF NOT EXISTS import_source (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,                            -- NEVER NULL (no system import; un-shareable)
  project_id    UUID,                                     -- optional book/project scope (cross-DB, no FK)
  title         TEXT NOT NULL DEFAULT '',
  content       TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_import_source_owner ON import_source(owner_user_id, created_at DESC);

-- ── consumed_tokens (RECONCILE D3, W4-MD3/MD7): the Tier-W confirm-token
-- replay-prevention ledger. NOT tenant-scoped — the jti is server-minted + globally
-- unique (jti = sha256(token_string), MD-7); identity is checked at the confirm
-- endpoint BEFORE the claim (same as knowledge-service's action_tokens). consume()
-- does INSERT … ON CONFLICT (jti) DO NOTHING, True only on the first claim.
CREATE TABLE IF NOT EXISTS consumed_tokens (
  jti          TEXT PRIMARY KEY,
  descriptor   TEXT NOT NULL,
  exp          TIMESTAMPTZ NOT NULL,
  consumed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── B-3 trigger: strip examples[] + opaque-ize source_ref when a motif derived from
-- an import is published. An imported-derived motif going public/unlisted must carry
-- NO source prose (examples) and NO back-readable foreign id. This is a DB trigger,
-- not a prompt — it cannot be bypassed by the LLM/router. Fires on the visibility
-- transition INTO a shared state. RECONCILE D5: the opaque token is the motif's OWN
-- id ('lineage:'||id::text) — it reveals nothing about the source and needs no
-- pgcrypto extension (the §6-C no-extension default).
CREATE OR REPLACE FUNCTION motif_publish_strip() RETURNS trigger AS $$
BEGIN
  IF NEW.visibility IN ('public','unlisted')
     AND (NEW.source = 'imported' OR NEW.imported_derived)   -- B-3: imported OR adopted-from-imported
     AND (TG_OP = 'INSERT' OR OLD.visibility = 'private'
          OR OLD.visibility IS DISTINCT FROM NEW.visibility) THEN
    NEW.examples := '[]'::jsonb;                          -- no source passages leave the workspace
    -- replace any back-readable foreign id with an opaque lineage token (own id).
    IF NEW.source_ref IS NULL OR NEW.source_ref NOT LIKE 'lineage:%' THEN
      NEW.source_ref := 'lineage:' || NEW.id::text;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'motif_publish_strip_trg') THEN
    CREATE TRIGGER motif_publish_strip_trg
      BEFORE INSERT OR UPDATE OF visibility ON motif
      FOR EACH ROW EXECUTE FUNCTION motif_publish_strip();
  END IF;
END $$;

-- ── arc_template B-3 parity (D-W9-ARC-PUBLISH-STRIP): the imported_derived taint column
-- (additive — ALTER for an already-created arc_template) + the publish-strip trigger.
-- arc_template has NO examples column (its free-text is abstracted by the deconstruct
-- scrub at create time), so the trigger's DB-level belt is to opaque-ize source_ref on
-- the publish transition of an imported/adopted-from-imported arc — the same lineage
-- hygiene the motif trigger applies. Cannot be bypassed by the router/LLM.
ALTER TABLE arc_template ADD COLUMN IF NOT EXISTS imported_derived BOOLEAN NOT NULL DEFAULT false;
-- D-MOTIF-SYNC-3WAY-BASE: the merge-base snapshot column (additive ALTER for an existing motif).
ALTER TABLE motif ADD COLUMN IF NOT EXISTS adopted_base JSONB;
-- D-MOTIF-ADOPT-PER-BOOK: the per-book label column + the book-scoped uniqueness partial
-- (additive, for an already-created motif). On an EXISTING DB the base `CREATE UNIQUE INDEX
-- IF NOT EXISTS uq_motif_user` above is a no-op (the index already exists with the OLD
-- predicate, no `book_id IS NULL` clause), so recreate it once when its def lacks book_id.
ALTER TABLE motif ADD COLUMN IF NOT EXISTS book_id UUID;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE indexname = 'uq_motif_user' AND indexdef NOT LIKE '%book_id%'
  ) THEN
    DROP INDEX uq_motif_user;
    CREATE UNIQUE INDEX uq_motif_user
      ON motif(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL AND book_id IS NULL;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_user_book
  ON motif(owner_user_id, book_id, code, language) WHERE book_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_motif_book ON motif(book_id) WHERE book_id IS NOT NULL;
-- D-MOTIF-ADOPT-BOOK-COLLAB-TIER (model B): the shared-tier marker + its per-book dedup, the
-- orthogonality CHECK, and the re-narrowed model-A partial — all additive for an existing motif.
ALTER TABLE motif ADD COLUMN IF NOT EXISTS book_shared BOOLEAN NOT NULL DEFAULT false;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'motif_book_shared_shape') THEN
    ALTER TABLE motif ADD CONSTRAINT motif_book_shared_shape CHECK (
      NOT book_shared OR (book_id IS NOT NULL AND owner_user_id IS NOT NULL AND visibility = 'private')
    );
  END IF;
  -- the model-A partial pre-dates book_shared (its predicate lacks the column) — recreate once so
  -- a shared row and a model-A label of the same (owner,book,code) don't collide on it.
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE indexname = 'uq_motif_user_book' AND indexdef NOT LIKE '%book_shared%'
  ) THEN
    DROP INDEX uq_motif_user_book;
    CREATE UNIQUE INDEX uq_motif_user_book
      ON motif(owner_user_id, book_id, code, language) WHERE book_id IS NOT NULL AND NOT book_shared;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_book_shared
  ON motif(book_id, code, language) WHERE book_shared;
CREATE INDEX IF NOT EXISTS idx_motif_book_shared ON motif(book_id) WHERE book_shared;
CREATE OR REPLACE FUNCTION arc_template_publish_strip() RETURNS trigger AS $$
BEGIN
  IF NEW.visibility IN ('public','unlisted')
     AND (NEW.source = 'imported' OR NEW.imported_derived)
     AND (TG_OP = 'INSERT' OR OLD.visibility = 'private'
          OR OLD.visibility IS DISTINCT FROM NEW.visibility) THEN
    IF NEW.source_ref IS NULL OR NEW.source_ref NOT LIKE 'lineage:%' THEN
      NEW.source_ref := 'lineage:' || NEW.id::text;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'arc_template_publish_strip_trg') THEN
    CREATE TRIGGER arc_template_publish_strip_trg
      BEFORE INSERT OR UPDATE OF visibility ON arc_template
      FOR EACH ROW EXECUTE FUNCTION arc_template_publish_strip();
  END IF;
END $$;

-- ════════════════════════════════════════════════════════════════════════════
-- 25 M1.3 · structure_node (23 A1 "Target data model", DDL text owned by 23 —
-- executed at boot so 25 M4's lift has a target). The saga→arc→sub-arc spec
-- tree, Per-book (BA8: cross-DB id, no FK). Lives HERE (not _SCHEMA_SQL): it
-- FKs arc_template, created above. NO `pacing` column (BPS-3): an arc's curve
-- IS its member scenes' outline_node.tension — a stored second copy is the
-- drift bug in miniature (arc_template keeps `pacing`: a template has no scenes).
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS structure_node (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id         UUID NOT NULL,                              -- BA8: Per-book (cross-DB id, no FK)
  created_by      UUID,                                       -- 23-A3 actor stamp (who authored the arc);
                                                              -- stored, never a scope key / filter (PM-5, DA-11)
  parent_id       UUID REFERENCES structure_node(id) ON DELETE CASCADE,
  kind            TEXT NOT NULL CHECK (kind IN ('saga','arc')),
  depth           SMALLINT NOT NULL DEFAULT 0 CHECK (depth BETWEEN 0 AND 2),
  rank            TEXT NOT NULL,                              -- LexoRank, same scheme as outline_node

  title           TEXT NOT NULL DEFAULT '',
  summary         TEXT NOT NULL DEFAULT '',
  goal            TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'outline'
                    CHECK (status IN ('empty','outline','drafting','done')),

  -- STRUCTURE (BA3) — the thing that was missing
  tracks          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label}]  (was arc_template.threads)
  roster          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key, actant, label, constraints[]}]
  roster_bindings JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {role_key: glossary_entity_id}

  -- PROVENANCE (BA13) — nullable; an arc need not come from a template
  arc_template_id  UUID REFERENCES arc_template(id) ON DELETE SET NULL,
  template_version INT,

  version         INT NOT NULL DEFAULT 1,
  is_archived     BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT structure_saga_is_root CHECK (kind <> 'saga' OR parent_id IS NULL)   -- BA1
);

CREATE INDEX IF NOT EXISTS idx_structure_node_book   ON structure_node(book_id) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_structure_node_parent ON structure_node(parent_id, rank COLLATE "C", id)
  WHERE NOT is_archived;
-- 23-A3: actor stamp for arc authorship. Additive for a DB already migrated by Deploy 1
-- (structure_node shipped without it); the fresh CREATE above carries it. Nullable — a
-- pre-A3 arc has no recorded author, and created_by is never a scope key (PM-5/DA-11).
ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS created_by UUID;

-- BA9 · depth + cycle guard (mirrors motif_application_scope_guard). A subtree
-- reparent recomputes descendant depth in one statement (recursive CTE) inside
-- the same transaction; the trigger validates each row.
CREATE OR REPLACE FUNCTION structure_node_depth_guard() RETURNS trigger AS $$
DECLARE parent_depth SMALLINT; parent_book UUID; walker UUID;
BEGIN
  IF NEW.parent_id IS NULL THEN
    NEW.depth := 0;
  ELSE
    SELECT depth, book_id INTO parent_depth, parent_book FROM structure_node WHERE id = NEW.parent_id;
    IF parent_depth IS NULL THEN
      RAISE EXCEPTION 'structure_node parent % not found', NEW.parent_id USING ERRCODE = 'check_violation';
    END IF;
    IF parent_book <> NEW.book_id THEN            -- cross-book reparent (the H-5 scope-guard lesson)
      RAISE EXCEPTION 'structure_node parent % not in book %', NEW.parent_id, NEW.book_id
        USING ERRCODE = 'check_violation';
    END IF;
    NEW.depth := parent_depth + 1;
    IF NEW.depth > 2 THEN
      RAISE EXCEPTION 'structure_node depth % exceeds saga→arc→sub-arc', NEW.depth
        USING ERRCODE = 'check_violation';
    END IF;
    -- cycle guard: walk ancestors, refuse to find NEW.id
    walker := NEW.parent_id;
    WHILE walker IS NOT NULL LOOP
      IF walker = NEW.id THEN
        RAISE EXCEPTION 'structure_node cycle via %', NEW.id USING ERRCODE = 'check_violation';
      END IF;
      SELECT parent_id INTO walker FROM structure_node WHERE id = walker;
    END LOOP;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'structure_node_depth_guard_trg') THEN
    CREATE TRIGGER structure_node_depth_guard_trg
      BEFORE INSERT OR UPDATE ON structure_node
      FOR EACH ROW EXECUTE FUNCTION structure_node_depth_guard();
  END IF;
END $$;

-- BA2 · chapter-kind outline nodes attach to the spec (the 25 M4 lift populates it)
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS structure_node_id UUID
  REFERENCES structure_node(id) ON DELETE SET NULL;
-- ADD CONSTRAINT has no IF NOT EXISTS — guarded DO-block (house style).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'outline_structure_kind') THEN
    ALTER TABLE outline_node ADD CONSTRAINT outline_structure_kind
      CHECK (structure_node_id IS NULL OR kind = 'chapter');
  END IF;
END $$;

-- 24 PH11 / H1.2 (Plan Hub v2) · chapters-under-arc window. After the 25 M4 lift a
-- chapter node has parent_id NULL and attaches to its arc via structure_node_id, so the
-- existing parent_id-leading idx_outline_node_children_keyset cannot serve the ARC axis.
-- Same collation discipline as that index (rank COLLATE "C", id keyset). QUERY-SIDE
-- REQUIREMENT (asserted by H8.1's EXPLAIN test): a partial index matches only when the
-- query IMPLIES its predicate — Postgres does NOT infer `kind = 'chapter'` from the
-- outline_structure_kind CHECK — so OutlineRepo.list_children_by_structure repeats
-- `AND kind = 'chapter' AND NOT is_archived` VERBATIM (lesson family:
-- postgres-partial-index-on-conflict-predicate-must-match).
CREATE INDEX IF NOT EXISTS idx_outline_node_structure_keyset
  ON outline_node(structure_node_id, rank COLLATE "C", id)
  WHERE NOT is_archived AND kind = 'chapter';

-- 26 IX-11 (D1) · provenance on the spec. `source` distinguishes human authoring from
-- the decompiler's mints and PlanForge's; `decompile_key = '<chapter_id>:<sort_order>'`
-- is 22 SC6's idempotency key. CONSUMED (not a write-only blob): the decompiler's upsert
-- may update only source='decompiled' rows and NEVER overwrites an authored node
-- (skipped_authored). Also lands on structure_node for the arc decompiler (D3).
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'authored';
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS decompile_key TEXT;
ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'authored';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'outline_node_source_check') THEN
    ALTER TABLE outline_node ADD CONSTRAINT outline_node_source_check
      CHECK (source IN ('authored','decompiled','planforge'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'structure_node_source_check') THEN
    ALTER TABLE structure_node ADD CONSTRAINT structure_node_source_check
      CHECK (source IN ('authored','decompiled','planforge'));
  END IF;
END $$;
-- IX-11 idempotency: one LIVE decompiled node per (book, decompile_key). The predicate
-- MUST mirror the decompiler's own idempotency probe, which filters `NOT is_archived`
-- (scene_decompile.materialize_scenes): an archived (soft-deleted) node is invisible to
-- the probe, so a re-run mints a fresh leaf — the index must therefore exempt archived
-- tombstones too, else that re-mint collides with the tombstone and aborts the whole
-- decompile (reconcile-by-truth-mirror-producer-predicate). Partial so authored nodes
-- (decompile_key NULL) are also exempt.
-- Self-heal a DB that already built the index WITHOUT the archived exemption (an
-- IF NOT EXISTS create can't replace a differing predicate — drop the stale one first).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE indexname = 'uq_outline_node_decompile_key'
      AND indexdef NOT ILIKE '%is_archived%'
  ) THEN
    DROP INDEX uq_outline_node_decompile_key;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_outline_node_decompile_key
  ON outline_node(book_id, decompile_key) WHERE decompile_key IS NOT NULL AND NOT is_archived;

-- 23 (M1.3) · bound-arc provenance: replaces annotations->>'arc_template_id'
-- (backfilled + annotation key dropped in 25 M4, deploy 2).
ALTER TABLE motif_application ADD COLUMN IF NOT EXISTS structure_node_id UUID
  REFERENCES structure_node(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_motif_application_structure ON motif_application(structure_node_id);

-- ── plan_run / plan_artifact (PlanForge M3): per-book planning runs. Tenancy
-- (25 OQ-3): reads are book-grant gated (E0 VIEW via book_id; plan_artifact
-- joins through its run); created_by = the acting caller — an actor stamp,
-- stored never filtered on (25 M3/PM-5).
CREATE TABLE IF NOT EXISTS plan_run (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by        UUID NOT NULL,
  book_id           UUID NOT NULL,
  work_id           UUID,
  status            TEXT NOT NULL DEFAULT 'pending',
  mode              TEXT NOT NULL,
  model_ref         UUID,
  source_checksum   TEXT NOT NULL DEFAULT '',
  source_markdown   TEXT NOT NULL DEFAULT '',
  active_job_id     UUID,
  error_detail      TEXT,
  checkpoint_state  JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT plan_run_status_chk CHECK (
    status IN ('pending', 'proposed', 'checkpoint', 'validated', 'compiled', 'failed')
  ),
  CONSTRAINT plan_run_mode_chk CHECK (mode IN ('rules', 'llm'))
);
-- Names predate the 25 M3 rename (a RENAME COLUMN cascades an index's definition
-- but not its name — fresh + migrated DBs converge on these). Safe unguarded:
-- this SQL runs AFTER package_rekey's M3, so created_by exists on every path.
CREATE INDEX IF NOT EXISTS idx_plan_run_owner_book
  ON plan_run(created_by, book_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plan_run_checksum
  ON plan_run(created_by, book_id, source_checksum);
-- Both indexes above LEAD with created_by — a leftover from the pre-OQ-3 per-user
-- key. Post re-key `created_by` is a plain actor stamp (stored, never filtered on)
-- and every read filters on book_id ALONE, which a created_by-leading index cannot
-- serve. This book-leading index is what actually makes the book-keyed reads
-- indexed — incl. the per-chat-turn plan-state probe (run count + latest status).
CREATE INDEX IF NOT EXISTS idx_plan_run_book_created
  ON plan_run(book_id, created_at DESC);

-- BE-4 — soft-archive a plan run (mirrors outline_node/canon_rule/structure_node). Additive; the
-- run is filtered from LIST but restorable. NOT a status: a failed run is still archivable AND
-- restorable, so it cannot ride the status CHECK.
ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_plan_run_book_created_active
  ON plan_run(book_id, created_at DESC) WHERE NOT is_archived;

CREATE TABLE IF NOT EXISTS plan_artifact (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  run_id          UUID NOT NULL REFERENCES plan_run(id) ON DELETE CASCADE,
  created_by      UUID NOT NULL,
  kind            TEXT NOT NULL,
  content         JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT plan_artifact_kind_chk CHECK (
    kind IN ('document', 'analyze', 'spec', 'graph', 'package', 'llm_io', 'validation_report')
  )
);
CREATE INDEX IF NOT EXISTS idx_plan_artifact_run_kind
  ON plan_artifact(run_id, kind, created_at DESC);

-- ══════════════════════════════════════════════════════════════════════════════
-- 27 V2-A — the PlanForge v2 multi-pass compiler's schema (Stage 6 / 00B §6.1).
--
-- A1 · the pass ledger + the genre input.
-- `pass_state` is ONE key per pass_id: {status, decision, artifact_id, job_id,
-- input_fingerprint, bootstrap_proposal_id?, decided_by, decided_at}. Derived
-- values (fresh|stale, pass_cursor, blocked_at) are computed at SERIALIZATION and
-- never stored — a stored derivation is a second source of truth that goes stale
-- the moment an input changes (the whole reason PF-3 keys freshness on an input
-- fingerprint rather than a flag).
ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS pass_state JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS genre_tags JSONB NOT NULL DEFAULT '[]'::jsonb;

-- The two CHECK swaps. Both are ADDITIVE in effect (they only WIDEN the allowed
-- set), but a CHECK cannot be widened in place — it must be dropped and re-added.
-- Per `migration-check-constraint-must-backfill-all-historical-blocks`, the re-add
-- must carry EVERY historical value, not just the new ones: dropping one silently
-- makes existing rows unwritable.
-- Re-added unconditionally: these two tables are small (one row per plan run), so the
-- re-validation cost is negligible, and an unconditional re-add keeps the CHECK's value
-- set in ONE place rather than split between a CREATE TABLE and a guarded migration.
ALTER TABLE plan_run DROP CONSTRAINT IF EXISTS plan_run_status_chk;
ALTER TABLE plan_run ADD CONSTRAINT plan_run_status_chk CHECK (
  status IN ('pending', 'proposed', 'checkpoint', 'validated', 'compiled', 'failed',
             -- v2: a run whose passes are staged but not yet compiled into a package.
             'planned')
);

ALTER TABLE plan_artifact DROP CONSTRAINT IF EXISTS plan_artifact_kind_chk;
ALTER TABLE plan_artifact ADD CONSTRAINT plan_artifact_kind_chk CHECK (
  kind IN (
    -- v1 kinds — every one of them still writable (see the backfill-all rule above).
    'document', 'analyze', 'spec', 'graph', 'package', 'llm_io', 'validation_report',
    -- v2: one artifact kind per compiler pass (PF-3), plus the two reports.
    'motif_plan', 'cast_plan', 'world_plan', 'beat_plan', 'char_arc_plan', 'scene_plan',
    'heal_report', 'link_report',
    -- close-21-28 P-O1a: the rules-mode pre-flight collision report (a mid-book propose held the
    -- auto-compile). Widen-only; every kind above stays writable (the backfill-all rule).
    'preflight'
  )
);

-- A2 · PROVENANCE (PF-9/PF-10) — which run, and which node WITHIN that run's plan,
-- produced this row. The partial UNIQUE is what makes the linker IDEMPOTENT: a
-- re-run of the same pass re-links the same plan node onto the same row instead of
-- minting a duplicate.
--
-- `NOT is_archived` is in the predicate on purpose (partial-unique-index-must-exempt-
-- soft-delete-tombstones): without it, archiving a linked node and re-linking would
-- collide with its own tombstone and the re-link would fail forever.
ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS plan_run_id UUID;
ALTER TABLE structure_node ADD COLUMN IF NOT EXISTS plan_arc_id  TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_structure_node_plan_prov
  ON structure_node(book_id, plan_run_id, plan_arc_id)
  WHERE plan_run_id IS NOT NULL AND plan_arc_id IS NOT NULL AND NOT is_archived;

ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS plan_run_id   UUID;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS plan_event_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_outline_node_plan_prov
  ON outline_node(book_id, plan_run_id, plan_event_id)
  WHERE plan_run_id IS NOT NULL AND plan_event_id IS NOT NULL AND NOT is_archived;

-- A3 · THE ONE NON-ADDITIVE CHANGE — registered as 25 M6.1 (the NC-4 pre-build gate).
--
-- The old CHECK required `chapter_id IS NOT NULL` for chapter AND scene kinds. It was
-- written when every outline row was born FROM an existing manuscript chapter. The
-- compiler links planned nodes BEFORE any manuscript chapter exists (bootstrap stamps
-- chapter_id later), so under the old CHECK **every skeleton-link and scene-link insert
-- fails**. This blocks V2-E entirely; it is not a nicety.
--
-- Re-added INVERTED, with a new NAME for the new semantics (DA-10 — one name, one
-- concept; keeping `outline_chapter_required` for a rule that no longer requires
-- anything would be a lie in the schema). NULL chapter_id now means "PLANNED, NOT YET
-- WRITTEN" — surfaced by BPS-13's affordance, never silent.
--
-- PRE-FLIGHT, per `migration-check-constraint-must-backfill-all-historical-blocks`:
-- the new CHECK forbids a chapter_id on any kind OTHER than chapter/scene. No writer
-- sets one today, but a stray historical row would make the ADD CONSTRAINT fail (or,
-- worse, be silently skipped by a NOT VALID). NULL any such row in the SAME transaction
-- first, so the constraint is provable rather than hoped-for.
-- GUARDED so it runs ONCE, not on every boot. Unguarded, each startup did a full-table UPDATE
-- scan of outline_node and then DROP+ADD the CHECK — which takes an ACCESS EXCLUSIVE lock and
-- re-validates the whole table. On the service's largest table that is a stop-the-world pause on
-- every deploy, for a migration that has already been applied. (The same guard pattern is used ~160
-- lines above for outline_node_source_check.) The block stays atomic, so there is never a window
-- in which the CHECK is absent.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'outline_chapter_written_kinds'
  ) THEN
    -- Pre-flight IN THE SAME transaction as the ADD, so the constraint is provable, not hoped for.
    UPDATE outline_node SET chapter_id = NULL
     WHERE chapter_id IS NOT NULL AND kind NOT IN ('chapter', 'scene');
    ALTER TABLE outline_node DROP CONSTRAINT IF EXISTS outline_chapter_required;
    ALTER TABLE outline_node ADD CONSTRAINT outline_chapter_written_kinds
      CHECK (chapter_id IS NULL OR kind IN ('chapter', 'scene'));
  END IF;
END $$;

-- ── authoring_runs (RAID Wave D2, DR-D): the autonomous authoring-run entity —
-- the §10 dial's level-3/4 run row. One row per gated autonomous drafting run
-- over an approved PlanForge plan. Tenancy (25 OQ-3): book-grant gated (E0 via
-- book_id at the HTTP layer); created_by = the acting caller (plain actor
-- stamp — pause/close cross-user keeps its OWNER escalation). `scope` is the
-- ORDERED chapter-id list (jsonb array of uuid strings — cross-DB book ids, no
-- FK per §1.4); `tool_allowlist` is the C2-allowlist SNAPSHOT declared by the
-- caller at gate time (edge #5 — provenance is the caller's; chat DB is not
-- composition's, see DR-D deviation note); `budget_usd`/`spent_usd` mirror
-- extraction_jobs' max_spend semantics (checked before each unit — the last
-- unit may overshoot by its own cost, like atomic_try_spend's last estimate).
-- `params` carries the drafting-seam inputs (model_source + model_ref user-model
-- UUID — models resolve via provider-registry from the ref, never a literal).
-- `breaker_state` records WHY the run stopped ({reason: budget|unit_failed}).
-- FSM: draft→gated→running→(paused⇄running)→report_ready→closed, running→failed.
CREATE TABLE IF NOT EXISTS authoring_runs (
  run_id          UUID PRIMARY KEY DEFAULT uuidv7(),
  created_by      UUID NOT NULL,
  book_id         UUID NOT NULL,
  plan_run_id     UUID NOT NULL REFERENCES plan_run(id),
  level           SMALLINT NOT NULL CHECK (level IN (3, 4)),
  scope           JSONB NOT NULL DEFAULT '[]'::jsonb,
  budget_usd      NUMERIC(10,4) NOT NULL DEFAULT 0,
  spent_usd       NUMERIC(10,4) NOT NULL DEFAULT 0,
  tool_allowlist  JSONB NOT NULL DEFAULT '[]'::jsonb,
  params          JSONB NOT NULL DEFAULT '{}'::jsonb,
  breaker_state   JSONB NOT NULL DEFAULT '{}'::jsonb,
  status          TEXT NOT NULL DEFAULT 'draft' CHECK (
    status IN ('draft','gated','running','paused','failed','report_ready','closed')
  ),
  current_unit    INT NOT NULL DEFAULT 0,
  error_message   TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- ── D4 durable-driver columns (RAID Wave D4). `driver_id` = the process id of
  -- the driver task currently driving this run; `driver_heartbeat_at` is bumped
  -- once per unit (the per-unit guarded claim). A `running` run whose heartbeat
  -- is older than authoring_heartbeat_stale_secs has NO live driver (service
  -- restarted / task died) and is re-claimable by the periodic sweep — the
  -- stale threshold MUST exceed the worst-case single-unit wall-clock
  -- (authoring_job_poll_timeout_secs) or the sweep would steal a run mid-unit.
  -- `background` is the fg/bg toggle SURFACED to the FE (v1: purely a display/
  -- filter flag — sweep-resume durability applies to BOTH fg and bg runs; the
  -- real fg/bg UX is FE-side later).
  driver_id           TEXT,
  driver_heartbeat_at TIMESTAMPTZ,
  background          BOOLEAN NOT NULL DEFAULT false,
  -- D-AGENT-MODE §20 D4: server-side auto-pause policy — when true (the safe
  -- default), the driver's per-unit guarded claim ALSO pauses the run at each
  -- unit boundary (same code path as the budget/critic breaker stops) instead
  -- of drafting the next unit unconditionally. Moved server-side (not a client
  -- poll) because a run started/resumed headlessly via MCP with no Studio
  -- panel open must still honor "stop and let a human look" by default.
  pause_after_each_unit BOOLEAN NOT NULL DEFAULT true
);
-- Scope fence (edge #11): ONE active run per book — across users too (two runs
-- over the same chapters conflict regardless of who started them). The gate's
-- draft→gated transition maps a violation to 409.
CREATE UNIQUE INDEX IF NOT EXISTS uq_authoring_runs_active_book
  ON authoring_runs(book_id) WHERE status IN ('gated','running','paused');
-- Name predates the 25 M3 rename (fresh + migrated DBs converge; runs after M3).
CREATE INDEX IF NOT EXISTS idx_authoring_runs_owner_book
  ON authoring_runs(created_by, book_id, created_at DESC);
-- D4 additive columns for DBs that created authoring_runs before D4 (the
-- CREATE TABLE above is IF NOT EXISTS — it does not evolve an existing table).
ALTER TABLE authoring_runs ADD COLUMN IF NOT EXISTS driver_id TEXT;
ALTER TABLE authoring_runs ADD COLUMN IF NOT EXISTS driver_heartbeat_at TIMESTAMPTZ;
ALTER TABLE authoring_runs ADD COLUMN IF NOT EXISTS background BOOLEAN NOT NULL DEFAULT false;
-- D-AGENT-MODE additive column for DBs that created authoring_runs before it
-- (same IF-NOT-EXISTS evolution pattern as the D4 columns above).
ALTER TABLE authoring_runs ADD COLUMN IF NOT EXISTS pause_after_each_unit BOOLEAN NOT NULL DEFAULT true;
-- Sweep scan: 'running' runs ordered by heartbeat age (partial — the fleet of
-- non-running runs never pollutes it).
CREATE INDEX IF NOT EXISTS idx_authoring_runs_running_heartbeat
  ON authoring_runs(driver_heartbeat_at) WHERE status = 'running';

-- ── authoring_run_units (RAID Wave D3, DR-D end-gate): the per-unit ledger the
-- driver writes as it drafts — one row per ATTEMPTED scope unit (un-attempted
-- units have no row; the Run Report synthesizes them as 'pending' from scope).
-- `pre_revision_id` = the chapter's LATEST book-service revision captured BEFORE
-- the drafting seam ran (book-service snapshots the NEW body into
-- chapter_revisions on every draft PATCH, so "latest revision" == the pre-run
-- draft content — the reject/Revert-All restore point; NULL = the chapter had no
-- revisions yet, nothing to restore to). `post_revision_id` = the latest revision
-- AFTER the seam (the run's draft — the report's diff anchor; best-effort, NULL
-- when capture failed). `cost_usd` is the unit's contribution to
-- authoring_runs.spent_usd (seam-metered, or the estimate fallback — per-unit
-- costs sum to the run's spend). Review FSM: pending→drafted→(accepted|rejected),
-- pending→failed; accept/reject are guarded OCC updates. Tenancy: no owner
-- column — every read/write JOINs authoring_runs (the parent run's book grant
-- is the units' tenancy; 25 OQ-3).
CREATE TABLE IF NOT EXISTS authoring_run_units (
  run_id           UUID NOT NULL REFERENCES authoring_runs(run_id) ON DELETE CASCADE,
  unit_index       INT NOT NULL,
  chapter_id       UUID NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending','drafted','failed','accepted','rejected')
  ),
  pre_revision_id  UUID,
  post_revision_id UUID,
  cost_usd         NUMERIC(10,4) NOT NULL DEFAULT 0,
  error_message    TEXT,
  -- D5 (RAID Wave D5): the per-unit continuity-critic verdict, written by the
  -- driver AFTER the unit drafts — {severity: ok|warn|severe, summary, cost_usd
  -- [, detail: the raw 4-dim judge_prose critique]}. NULL = not critiqued
  -- (critic disabled via params.critic_enabled=false, unit failed before
  -- drafting, or the run was paused/stolen at the boundary before the critique
  -- — the Run Report shows the gap). severity='severe' also trips the run
  -- breaker (run PAUSED, breaker reason critic_severe — 07S: interrupt on
  -- severe; the human reviews the report and resumes/reverts).
  critic_verdict   JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, unit_index)
);
-- D5 additive column for DBs that created authoring_run_units before D5 (the
-- CREATE TABLE above is IF NOT EXISTS — it does not evolve an existing table).
ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS critic_verdict JSONB;

-- ── plan_bootstrap_proposal (PlanForge auto-bootstrap POC): the
-- propose→record→approve→apply structural-mutation quarantine gate
-- (docs/specs/2026-07-06-planforge-auto-bootstrap.md §3.1). One
-- deterministic/LLM PROPOSE pass computes `diff` ONCE; APPLY performs the
-- real mutations (book-service chapter creation) only after human approval
-- and never re-runs propose. The pending→approved→applying→applied|failed
-- transition is enforced by the repository's conditional
-- `UPDATE ... WHERE status='approved'` claim (no DB trigger for this POC's
-- small 5-state DAG — contrast lore-enrichment-service's `enrichment_proposal`,
-- which has a full trigger-guarded DAG; revisit if this generalizes beyond
-- one consumer). Tenancy: per-book resource, book-grant gated on book_id (25
-- OQ-3); created_by = the acting caller (plain actor stamp — 25 M3/PM-5).
CREATE TABLE IF NOT EXISTS plan_bootstrap_proposal (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  run_id            UUID NOT NULL REFERENCES plan_run(id) ON DELETE CASCADE,
  book_id           UUID NOT NULL,
  created_by        UUID NOT NULL,
  status            TEXT NOT NULL DEFAULT 'pending',
  diff              JSONB NOT NULL,
  applied_results   JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_detail      TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT plan_bootstrap_proposal_status_chk CHECK (
    status IN ('pending', 'approved', 'rejected', 'applying', 'applied', 'failed')
  )
);
CREATE INDEX IF NOT EXISTS idx_plan_bootstrap_proposal_book
  ON plan_bootstrap_proposal(book_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plan_bootstrap_proposal_run
  ON plan_bootstrap_proposal(run_id, created_at DESC);

-- ── arc_conformance_state (26 IX-8, `.runs/`): the durable, INPUT-PINNED latest
-- conformance report per (book, arc). UPSERT-latest — exactly one row per arc; run
-- history stays in generation_job rows (OQ-7). `report` is the full coarse ±deep body
-- the per-arc GET / job already returns; `input_manifest` is the {v:1, chapters:[...],
-- spec:{...}} envelope (per-chapter published_revision_id + parse_version + the spec
-- fingerprints) the READ-time dirty predicate (IX-9) compares against current canon
-- markers + recomputed fingerprints — a POLL-ON-READ derivation, so NO stored dirty bit
-- can itself go stale. FKs structure_node (created above) ON DELETE CASCADE so a deleted
-- arc drops its snapshot (IX-13). New + empty on every DB (25: no backfill). `computed_at`
-- is a server default (now()) — never a client-bound timestamp string (asyncpg-timestamptz
-- lesson). PK (book_id, structure_node_id) leads with book_id, so list_for_book is an
-- index range scan (the status route's per-book read).
CREATE TABLE IF NOT EXISTS arc_conformance_state (
  book_id            UUID NOT NULL,
  structure_node_id  UUID NOT NULL REFERENCES structure_node(id) ON DELETE CASCADE,
  report             JSONB NOT NULL,
  input_manifest     JSONB NOT NULL,
  deep               BOOLEAN NOT NULL DEFAULT false,
  generation_job_id  UUID,
  computed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (book_id, structure_node_id)
);

-- ── SC11 amendment Phase 1 — the WRITTEN VERDICT, maintained on write ───────────────────────
--
-- "Is there prose behind this spec node?" is a manuscript FACT, and book-service already knows it
-- when it writes `scenes.source_scene_id`. Before this it was DERIVED ON READ, twice, on the
-- CLIENT (plan-hub's computeUnionState and the scene-browser's sceneUnion), each with its own
-- partial-read completeness guard — and one of them needed a HIGH-severity fix to get that guard
-- right. It was also invisible to agents: it lived in a `useState` and died with the panel.
--
-- ⚠ READ THIS BEFORE "FIXING" IT: this does NOT re-invert SC2 / DA-3.
--    DA-3 says "the index points at the spec — `scenes.source_scene_id → outline_node.id`, NEVER
--    the reverse", and composition never writes book-service's column. Both still hold.
--    `written_scene_id` is a REGENERABLE CACHE of that pointer's inverse — the same status
--    INV-FACTS gives the EAV projection ("lazy, versioned, regenerable caches — never truth").
--    The AUTHORED anchor remains `scenes.source_scene_id`, owned solely by the index owner.
--    If the two ever disagree, **book-service wins and this column is rebuilt from it** — that is
--    exactly what the reconcile sweeper does. A back-pointer on `outline_node` LOOKS like a DA-3
--    violation and is not; deleting it would silently restore the client-side derivation.
--
-- NOT `status`: that is the AUTHOR's intent (`empty|outline|drafting|done`), it is an agent/author
-- write arg (SC8), and PH16 locks a two-chip desired-vs-actual header. Fusing intent and fact into
-- one column is the drift bug BPS-3 deleted `structure_node.pacing` to prevent — and it would mean
-- an author marking a scene `done` makes an UNWRITTEN scene render as written.
--
-- A LINK (not a bool/timestamp) because the scene-browser needs the resolved id: it distinguishes
-- `anchorLost` (set-but-dangling) from "not yet written" (BPS-13). No FK — cross-DB soft ref.
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS written_scene_id UUID;
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS written_at       TIMESTAMPTZ;
-- WHICH CHAPTER'S PROSE backs this node — and it is NOT the same thing as `chapter_id`.
-- `chapter_id` is the node's OWN spec chapter. `written_chapter_id` is where the prose that backs
-- it actually lives. They come apart in two REAL ways, and a reconcile scoped by the wrong one is
-- broken in both:
--   * NOTHING constrains `scenes.source_scene_id` to a node of the same chapter. Copy prose (with
--     its `data-scene-id` anchor) into another chapter and a scene in chapter A now backs a node
--     whose spec chapter is B. Clearing by `chapter_id` makes the two chapters FIGHT: reconciling B
--     wipes the link, reconciling A restores it, and the mirror never converges.
--   * `chapter_id` is NULL on a PLANNED node — which is most of them (7/7 in the live DB when this
--     was written). A NULL-chapter node that gets written could never be cleared by a chapter-scoped
--     predicate, and `reconcile_book` skips NULLs, so THE SWEEPER WOULD NEVER HEAL IT EITHER.
--     Permanently, silently stale.
-- Clearing by `written_chapter_id` — "the nodes this chapter's prose used to back, and no longer
-- does" — is correct in both cases and needs no chapter_id at all.
ALTER TABLE outline_node ADD COLUMN IF NOT EXISTS written_chapter_id UUID;
-- Partial: only the written nodes. The Hub reads this per book, and a mostly-unwritten book keeps
-- the index tiny.
CREATE INDEX IF NOT EXISTS idx_outline_node_written
  ON outline_node(book_id) WHERE written_scene_id IS NOT NULL;

-- ── 33 · BE-7c (W0-BE1) — a Work-LESS, OWNER-scoped generation_job.
-- motif MINE (scope='corpus'|'book') and arc IMPORT (analyze_reference) are genuinely
-- not Work-bound: there is no composition_work to derive a book_id from. The prior code
-- stamped a synthetic uuid4() project_id, which the create() INSERT…SELECT could not
-- resolve → ReferenceViolationError → the PAID action 500'd after burning the confirm
-- token and reserving the billing hold. The row's scope key for these jobs is its OWNER
-- (`created_by`, already NOT NULL). Make that sayable.
--
-- ADDITIVE ONLY: no row is rewritten. Every existing row keeps both columns non-null and
-- satisfies the first branch of the CHECK below.
ALTER TABLE generation_job ALTER COLUMN project_id DROP NOT NULL;
ALTER TABLE generation_job ALTER COLUMN book_id    DROP NOT NULL;

-- Keep it HONEST: a job is EITHER Work-scoped (both keys) or owner-scoped (neither).
-- A half-null row would be a tenancy hole (a book_id with no project, or vice versa).
-- Deliberately does NOT enumerate operations — an op allowlist here would force a CHECK
-- rewrite on every new Work-less op (the `migration-check-constraint-must-backfill-all-
-- historical-blocks` trap). The OPERATION allowlist lives in the WRITER
-- (generation_jobs.UNBOUND_OPERATIONS), where it can evolve without DDL.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'generation_job_scope_shape') THEN
    ALTER TABLE generation_job ADD CONSTRAINT generation_job_scope_shape CHECK (
      (project_id IS NOT NULL AND book_id IS NOT NULL)
      OR (project_id IS NULL AND book_id IS NULL)
    );
  END IF;
END $$;

-- The owner-scoped read's index (the only query shape over these rows).
CREATE INDEX IF NOT EXISTS idx_generation_job_owner_unbound
  ON generation_job(created_by, created_at DESC) WHERE project_id IS NULL;
"""


# Built-in structure templates (owner_user_id NULL = global). Deterministic ids
# → ON CONFLICT (id) DO NOTHING makes the seed idempotent across restarts. The
# beats drive the M4 packer's beat→scene mapping + the M8 outline view.
BUILTIN_TEMPLATES: list[tuple[str, str, str, list[dict]]] = [
    (
        "0190ce00-0000-7000-8000-000000000001", "Save the Cat", "save_the_cat",
        [
            {"key": "opening_image", "label": "Opening Image", "purpose": "A snapshot of the hero's world + tone before change.", "order": 1},
            {"key": "theme_stated", "label": "Theme Stated", "purpose": "Someone states what the story is really about.", "order": 2},
            {"key": "setup", "label": "Setup", "purpose": "Hero's status quo, flaws, and what's missing.", "order": 3},
            {"key": "catalyst", "label": "Catalyst", "purpose": "The inciting incident that upends the status quo.", "order": 4},
            {"key": "debate", "label": "Debate", "purpose": "Hero hesitates — should they go?", "order": 5},
            {"key": "break_into_two", "label": "Break into Two", "purpose": "Hero commits and enters the new world.", "order": 6},
            {"key": "b_story", "label": "B Story", "purpose": "The relationship/theme subplot begins.", "order": 7},
            {"key": "fun_and_games", "label": "Fun and Games", "purpose": "The promise of the premise — set-pieces.", "order": 8},
            {"key": "midpoint", "label": "Midpoint", "purpose": "A false victory or false defeat raises stakes.", "order": 9},
            {"key": "bad_guys_close_in", "label": "Bad Guys Close In", "purpose": "Pressure mounts internally and externally.", "order": 10},
            {"key": "all_is_lost", "label": "All Is Lost", "purpose": "The lowest point; a 'whiff of death'.", "order": 11},
            {"key": "dark_night", "label": "Dark Night of the Soul", "purpose": "Hero wallows before the breakthrough.", "order": 12},
            {"key": "break_into_three", "label": "Break into Three", "purpose": "The solution synthesizing A and B stories.", "order": 13},
            {"key": "finale", "label": "Finale", "purpose": "Hero executes the plan; world is set right.", "order": 14},
            {"key": "final_image", "label": "Final Image", "purpose": "Mirror of the opening — proof of change.", "order": 15},
        ],
    ),
    (
        "0190ce00-0000-7000-8000-000000000002", "Hero's Journey", "hero_journey",
        [
            {"key": "ordinary_world", "label": "Ordinary World", "purpose": "Hero's normal life before the adventure.", "order": 1},
            {"key": "call_to_adventure", "label": "Call to Adventure", "purpose": "A problem or challenge presents itself.", "order": 2},
            {"key": "refusal_of_the_call", "label": "Refusal of the Call", "purpose": "Hero hesitates or refuses out of fear.", "order": 3},
            {"key": "meeting_the_mentor", "label": "Meeting the Mentor", "purpose": "Hero gains guidance or a tool.", "order": 4},
            {"key": "crossing_the_threshold", "label": "Crossing the Threshold", "purpose": "Hero commits to the special world.", "order": 5},
            {"key": "tests_allies_enemies", "label": "Tests, Allies, Enemies", "purpose": "Hero learns the rules of the new world.", "order": 6},
            {"key": "approach", "label": "Approach to the Inmost Cave", "purpose": "Preparations for the major challenge.", "order": 7},
            {"key": "ordeal", "label": "Ordeal", "purpose": "The central crisis — a brush with death.", "order": 8},
            {"key": "reward", "label": "Reward (Seizing the Sword)", "purpose": "Hero takes the prize after surviving.", "order": 9},
            {"key": "the_road_back", "label": "The Road Back", "purpose": "Consequences chase the hero home.", "order": 10},
            {"key": "resurrection", "label": "Resurrection", "purpose": "Final test; hero is reborn transformed.", "order": 11},
            {"key": "return_with_elixir", "label": "Return with the Elixir", "purpose": "Hero returns changed, with a boon.", "order": 12},
        ],
    ),
    (
        "0190ce00-0000-7000-8000-000000000003", "Story Circle", "story_circle",
        [
            {"key": "you", "label": "You", "purpose": "A character in a zone of comfort.", "order": 1},
            {"key": "need", "label": "Need", "purpose": "But they want something.", "order": 2},
            {"key": "go", "label": "Go", "purpose": "They enter an unfamiliar situation.", "order": 3},
            {"key": "search", "label": "Search", "purpose": "Adapt to it.", "order": 4},
            {"key": "find", "label": "Find", "purpose": "Get what they wanted.", "order": 5},
            {"key": "take", "label": "Take", "purpose": "Pay a heavy price for it.", "order": 6},
            {"key": "return", "label": "Return", "purpose": "Then return to their familiar situation.", "order": 7},
            {"key": "change", "label": "Change", "purpose": "Having changed.", "order": 8},
        ],
    ),
    (
        "0190ce00-0000-7000-8000-000000000004", "Kishōtenketsu", "kishotenketsu",
        [
            {"key": "ki", "label": "Ki (起) — Introduction", "purpose": "Introduce characters, era, and setting.", "order": 1},
            {"key": "sho", "label": "Shō (承) — Development", "purpose": "Develop the situation; no dramatic turns yet.", "order": 2},
            {"key": "ten", "label": "Ten (転) — Twist", "purpose": "An unforeseen turn recontextualizes everything.", "order": 3},
            {"key": "ketsu", "label": "Ketsu (結) — Conclusion", "purpose": "Reconcile the twist into a harmonious close.", "order": 4},
        ],
    ),
    (
        "0190ce00-0000-7000-8000-000000000005", "Web Novel Arc", "web_novel",
        [
            {"key": "hook", "label": "Hook", "purpose": "Open mid-tension; promise the arc's payoff fast.", "order": 1},
            {"key": "establishment", "label": "World / Power Establishment", "purpose": "Stakes, the protagonist's edge, and the goal.", "order": 2},
            {"key": "rising_conflict", "label": "Rising Conflict", "purpose": "Escalating obstacles and rival pressure.", "order": 3},
            {"key": "setback", "label": "Setback / Crisis", "purpose": "A hard loss or trap that raises the cost.", "order": 4},
            {"key": "climax", "label": "Climax / Payoff", "purpose": "The earned turnaround — the chapter the readers waited for.", "order": 5},
            {"key": "resolution", "label": "Resolution & Next-Arc Seed", "purpose": "Bank the win; plant the hook for the next arc.", "order": 6},
        ],
    ),
    (
        "0190ce00-0000-7000-8000-000000000006", "Three-Act (Generic)", "generic",
        [
            {"key": "setup", "label": "Act I — Setup", "purpose": "Establish world, characters, and the inciting incident.", "order": 1},
            {"key": "confrontation", "label": "Act II — Confrontation", "purpose": "Rising action, midpoint, and the low point.", "order": 2},
            {"key": "resolution", "label": "Act III — Resolution", "purpose": "Climax and dénouement.", "order": 3},
        ],
    ),
]


async def _apply_base_schema(conn: asyncpg.Connection) -> None:
    """The base idempotent DDL — injected into the package re-key so its M0
    pre-flight runs BEFORE any DDL (25 PM-7) and its M2/M3 after (one unit)."""
    await conn.execute(_SCHEMA_SQL)


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the idempotent schema + seed built-in templates. Safe on every start.

    Order (25 PM-7): run_package_rekey gates the whole boot — M0 pre-flight
    (aborts LOUDLY before any DDL on a violation) → _SCHEMA_SQL (M1 additive
    DDL rides inline) → the marker-gated M2 backfill + M3 cutover — then the
    motif/plan DDL + seeds as before (their CREATE texts are already the final
    post-M3 shape, and the M3 renames precede them on the migration boot).
    """
    async with pool.acquire() as conn:
        rekeyed = await run_package_rekey(conn, _apply_base_schema)
        if rekeyed:
            logger.info("composition migrate: package re-key pkg_rekey_v1 applied this boot")
        await conn.execute(_MOTIF_SCHEMA_SQL)          # F0: narrative motif library DDL (+ structure_node)
        # B3 (BA2): a CLEAN DB (fresh, or already drained of legacy arc rows) is auto-lifted here —
        # a safe CHECK-tighten with NOTHING to migrate — so fresh + throwaway-test DBs are born
        # consistent and never trip the guard below. Placed AFTER _MOTIF_SCHEMA_SQL because that is
        # where structure_node is created, and run_arc_lift requires it. A DB that still HOLDS
        # arc-kind outline_nodes is a legacy pre-Deploy-2 state: do NOT auto-migrate that (Q2 — the
        # risky data lift stays operator-invoked); `_assert_lift_applied` then fails loud so the
        # operator runs `python -m app.db.arc_lift` deliberately.
        from app.db.arc_lift import run_arc_lift
        has_legacy_arcs = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM outline_node WHERE kind IN ('arc','beat'))"
        )
        if not has_legacy_arcs and await run_arc_lift(conn):
            logger.info("composition migrate: arc lift pkg_lift_v1 applied (clean DB, safe CHECK-tighten)")
        await _assert_lift_applied(conn)               # B3 (BA2): refuse to serve an unlifted DB
        await _backfill_chapter_story_order(conn)      # 24: the reading axis (was never written)
        await _seed_builtin_templates(conn)
        await _seed_motif_packs(conn)                  # F0 adds the CALL; W7 fills the body
    logger.info("composition migrate: schema applied + %d built-in templates seeded", len(BUILTIN_TEMPLATES))


async def _assert_lift_applied(conn: asyncpg.Connection) -> None:
    """B3 (BA2 fail-loud) — this code assumes the arc lift has run: it reads arcs from
    `structure_node`, and `outline_node.kind` is ('chapter','scene'). If the DB carries the
    package re-key (`pkg_rekey_v1`) but NOT the lift (`pkg_lift_v1`), arcs still live in
    `outline_node` under `kind='arc'` and the 4-kind CHECK still stands — code and schema
    DISAGREE, silently: the Plan Hub renders no lanes, and every arc read misses them.

    Refuse to boot rather than serve that mismatch. The assertion travels WITH the
    post-lift-assuming code, so a legitimate Deploy-1 SOAK (which runs the PREVIOUS code,
    without this assertion) is unaffected — only deploying THIS code onto an unlifted,
    rekeyed DB trips it, which is exactly the disagreement to catch. (Q2 SEALED: keep the
    lift operator-invoked; fail loud when the running code assumes it and it hasn't run.)

    Operator fix: `python -m app.db.arc_lift` — safe and a no-op past its marker; on a fresh
    DB it has no arcs to migrate, it just tightens the CHECK and stamps `pkg_lift_v1`.

    `package_migration` is created + `pkg_rekey_v1` stamped by `run_package_rekey`, which runs
    immediately before this — so the table always exists here.
    """
    rows = await conn.fetch(
        "SELECT marker FROM package_migration WHERE marker = ANY($1::text[])",
        ["pkg_rekey_v1", "pkg_lift_v1"],
    )
    markers = {r["marker"] for r in rows}
    if "pkg_rekey_v1" in markers and "pkg_lift_v1" not in markers:
        raise RuntimeError(
            "composition boot REFUSED (B3/BA2): the DB carries the package re-key "
            "(pkg_rekey_v1) but the arc lift (pkg_lift_v1) has NOT run. This build reads arcs "
            "from structure_node and assumes outline_node.kind IN ('chapter','scene'); an "
            "unlifted DB still holds arcs in outline_node. Run `python -m app.db.arc_lift` "
            "before serving."
        )


async def _backfill_chapter_story_order(conn: asyncpg.Connection) -> None:
    """24 — give already-persisted CHAPTER nodes the `story_order` the writer never set.

    `_insert_decomposed_tree` passed `story_order` for scenes but not for their chapter, so every
    chapter node ever written carries NULL. Consequences (all live): the plan-overlay canon anchor
    join (`chapter.story_order = canon_rule.from_order`) never matched, the arc's derived span /
    BA6 contiguity was unresolvable, and the Plan Hub's x-axis fell through to the id tiebreak.

    The chapter's position is recoverable from its OWN scenes, which DO carry it on the strided
    axis (`chapter_sort * 1000 + scene_idx`): floor the chapter's minimum scene order to its stride
    boundary and that IS `chapter_sort * 1000` — the chapter's slot, its scene 0. A chapter with no
    scenes stays NULL: its position is genuinely unknown here (composition has no book-order feed),
    and a NULL sorts last + reads as "unordered" everywhere, which is truthful. A wrong guess (0)
    would silently claim it is the book's FIRST chapter.

    Idempotent (only touches NULLs) and cheap (one UPDATE, indexed on project/parent).
    """
    updated = await conn.execute(
        """
        UPDATE outline_node c
           SET story_order = s.base, updated_at = now()
          FROM (
            SELECT parent_id,
                   (min(story_order) / $1::int) * $1::int AS base
              FROM outline_node
             WHERE kind = 'scene' AND parent_id IS NOT NULL AND story_order IS NOT NULL
               AND NOT is_archived
             GROUP BY parent_id
          ) s
         WHERE c.id = s.parent_id
           AND c.kind = 'chapter'
           AND c.story_order IS NULL
        """,
        STORY_ORDER_CHAPTER_STRIDE,
    )
    if updated and updated != "UPDATE 0":
        logger.info("composition migrate: chapter story_order backfill — %s", updated)


async def _seed_motif_packs(conn: asyncpg.Connection) -> None:
    """F0 frozen call site — DELEGATES to the W7-owned `app.db.seed_motifs` module so
    W7 fills the seed-pack body (the system-tier motif/arc rows) by creating ITS OWN
    new file, never editing this frozen migrate.py. A soft import keeps boot working
    before W7 lands (no-op until then — the C16 'never wall boot on an optional part'
    discipline). System seeds use visibility='unlisted' (RECONCILE D6) so the both-NULL
    rows satisfy the motif_user_owned CHECK; embedding starts NULL (D4 — W3 back-fills
    lazily)."""
    try:
        from app.db.seed_motifs import seed_motif_packs
    except ImportError:
        return  # W7 not landed yet
    await seed_motif_packs(conn)


async def _seed_builtin_templates(conn: asyncpg.Connection) -> None:
    import json

    for tid, name, kind, beats in BUILTIN_TEMPLATES:
        await conn.execute(
            """
            INSERT INTO structure_template (id, owner_user_id, name, kind, beats)
            VALUES ($1, NULL, $2, $3, $4::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            tid, name, kind, json.dumps(beats),
        )
