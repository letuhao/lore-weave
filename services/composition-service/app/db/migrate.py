"""composition-service schema migration (idempotent, single-DDL house style).

M1: the §1.2 DDL (7 tables + indexes/constraints, all `IF NOT EXISTS`) plus the
built-in `structure_template` seed (6 structures, owner_user_id NULL, idempotent
via deterministic UUIDs + ON CONFLICT DO NOTHING). Applied on every startup —
no migration tool, like knowledge-service. `uuidv7()` is a PG18 built-in.

Cross-DB ids (project_id→knowledge, book_id/chapter_id/*_revision_id→book,
entity ids→glossary, llm_job_id→gateway) carry NO DB FK (§1.4 — validated in
app code). In-DB FKs (outline_node.parent_id, scene_link, generation_job→
outline_node) are fine — same database.
"""

import logging

import asyncpg

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
-- ── composition_work: Work marker + work-level settings (1:1 with a book project)
CREATE TABLE IF NOT EXISTS composition_work (
  project_id          UUID PRIMARY KEY,
  user_id             UUID NOT NULL,
  book_id             UUID NOT NULL,
  active_template_id  UUID,
  status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  settings            JSONB NOT NULL DEFAULT '{}'::jsonb,
  version             INT NOT NULL DEFAULT 1,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_composition_work_user ON composition_work(user_id);

-- C16 (WG-3) Work-setup resilience: when knowledge-service is down/5xx during
-- greenfield setup, the Work is created with a LAZY (null) project_id + a backfill
-- marker so writing/Generate is never wall-blocked by an optional dependency. This
-- requires re-keying composition_work off project_id (a null PK is impossible):
--   • add a surrogate `id` PK (uuidv7);
--   • make project_id NULLABLE;
--   • keep the 1:1 (work ⇄ knowledge project) invariant via a PARTIAL unique index
--     over only the BACKED rows (project_id IS NOT NULL) — null rows are exempt;
--   • `pending_project_backfill` marks a greenfield Work awaiting its knowledge
--     project, and a partial-unique index caps it at one pending Work per (user,book)
--     so a setup retry backfills the SAME row rather than spawning duplicates.
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
-- At most one pending-backfill (greenfield, null-project) Work per (user,book) so a
-- setup retry backfills the same row instead of duplicating.
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_pending
  ON composition_work(user_id, book_id) WHERE pending_project_backfill;

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
  user_id     UUID NOT NULL,
  project_id  UUID NOT NULL,
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
  user_id           UUID NOT NULL,
  project_id        UUID NOT NULL,
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
  user_id            UUID NOT NULL,
  project_id         UUID NOT NULL,
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

-- ── scene_link: ONLY non-derivable edges
CREATE TABLE IF NOT EXISTS scene_link (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id      UUID NOT NULL,
  project_id   UUID NOT NULL,
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
  user_id     UUID NOT NULL,
  project_id  UUID NOT NULL,
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
  user_id            UUID NOT NULL,
  project_id         UUID NOT NULL,
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
  user_id        UUID NOT NULL,
  project_id     UUID NOT NULL,
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
  user_id                UUID NOT NULL,
  project_id             UUID NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_generation_correction_user ON generation_correction(user_id, created_at DESC);

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
-- Scope = (user, PROJECT, key): the commit endpoint is per-project, so a key
-- reused across projects must NOT replay another project's result (/review-impl).
CREATE TABLE IF NOT EXISTS decompose_commit (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id         UUID NOT NULL,
  project_id      UUID NOT NULL,
  idempotency_key TEXT NOT NULL,
  arc_id          UUID NOT NULL,
  result          JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_decompose_commit_idem ON decompose_commit(user_id, project_id, idempotency_key);
"""

# C23 down-migration (round-trip proof only — the live schema is idempotent-forward
# like knowledge-service, applied on every boot). Drops the dị bản substrate in
# dependency order: the two child tables first, then the GUARD constraint, then the
# two columns + their index. Leaves the C16 re-key + the rest of the schema intact so
# up→down→up restores exactly (no residue). Mirrors book-service C20's WorldsDownSQL.
C23_DOWN_SQL = """
DROP TABLE IF EXISTS entity_override;
DROP TABLE IF EXISTS divergence_spec;
ALTER TABLE composition_work DROP CONSTRAINT IF EXISTS chk_derivative_project_required;
DROP INDEX IF EXISTS idx_composition_work_source;
ALTER TABLE composition_work DROP COLUMN IF EXISTS branch_point;
ALTER TABLE composition_work DROP COLUMN IF EXISTS source_work_id;
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


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the idempotent schema + seed built-in templates. Safe on every start."""
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
        await _seed_builtin_templates(conn)
    logger.info("composition migrate: schema applied + %d built-in templates seeded", len(BUILTIN_TEMPLATES))


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
