package migrate

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

const schemaSQL = `
CREATE TABLE IF NOT EXISTS books (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  original_language TEXT,
  summary TEXT,
  lifecycle_state TEXT NOT NULL DEFAULT 'active',
  trashed_at TIMESTAMPTZ,
  purge_eligible_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS book_cover_assets (
  book_id UUID PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
  content_type TEXT NOT NULL,
  byte_size BIGINT NOT NULL DEFAULT 0,
  storage_key TEXT NOT NULL,
  data BYTEA,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE book_cover_assets ADD COLUMN IF NOT EXISTS data BYTEA;
ALTER TABLE books ADD COLUMN IF NOT EXISTS genre_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE books ADD COLUMN IF NOT EXISTS wiki_settings JSONB NOT NULL DEFAULT '{"visibility":"off","community_mode":"off","ai_assist":false,"glossary_exposure":"names","auto_generate":false}';
ALTER TABLE books ADD COLUMN IF NOT EXISTS extraction_profile JSONB;

-- E0 (collaboration-permissions): non-owner grants on a book. The owner is
-- implicit via books.owner_user_id and is NEVER stored here, so an empty
-- table == today's single-owner behavior (AC6 no-regress is free).
CREATE TABLE IF NOT EXISTS book_collaborators (
  book_id    UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL,
  role       TEXT NOT NULL CHECK (role IN ('view','edit','manage')),
  granted_by UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (book_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_book_collab_user ON book_collaborators(user_id);

CREATE TABLE IF NOT EXISTS chapters (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  title TEXT,
  original_filename TEXT NOT NULL,
  original_language TEXT NOT NULL,
  content_type TEXT NOT NULL,
  byte_size BIGINT NOT NULL DEFAULT 0,
  sort_order INT NOT NULL,
  storage_key TEXT NOT NULL,
  lifecycle_state TEXT NOT NULL DEFAULT 'active',
  trashed_at TIMESTAMPTZ,
  purge_eligible_at TIMESTAMPTZ,
  draft_updated_at TIMESTAMPTZ,
  draft_revision_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chapters_unique_slot_lang_active
  ON chapters(book_id, sort_order, original_language)
  WHERE lifecycle_state = 'active';
-- Keyset pagination for the manuscript navigator: ORDER BY sort_order, id per book
-- (the cursor endpoint scans (book_id, sort_order, id) for 10k+ chapter books).
CREATE INDEX IF NOT EXISTS idx_chapters_keyset
  ON chapters(book_id, sort_order, id);

CREATE TABLE IF NOT EXISTS chapter_raw_objects (
  chapter_id UUID PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
  body_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapter_drafts (
  chapter_id UUID PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
  body JSONB NOT NULL,
  draft_format TEXT NOT NULL DEFAULT 'json',
  draft_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  draft_version BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS chapter_revisions (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  body JSONB NOT NULL,
  body_format TEXT NOT NULL DEFAULT 'json',
  message TEXT,
  author_user_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chapter_revisions_chapter
  ON chapter_revisions(chapter_id, created_at DESC);
ALTER TABLE chapter_revisions ADD COLUMN IF NOT EXISTS body_format TEXT NOT NULL DEFAULT 'json';

CREATE TABLE IF NOT EXISTS user_storage_quota (
  owner_user_id UUID PRIMARY KEY,
  used_bytes BIGINT NOT NULL DEFAULT 0,
  quota_bytes BIGINT NOT NULL
);

-- ── chapter_blocks: denormalized text extracted from Tiptap JSONB ────────
CREATE TABLE IF NOT EXISTS chapter_blocks (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  block_index INT NOT NULL,
  block_type TEXT NOT NULL,
  text_content TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  heading_context TEXT,
  attrs JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(chapter_id, block_index)
);
CREATE INDEX IF NOT EXISTS idx_chapter_blocks_chapter ON chapter_blocks(chapter_id);
CREATE INDEX IF NOT EXISTS idx_chapter_blocks_type ON chapter_blocks(block_type);

-- ── outbox_events: transactional outbox for event-driven pipeline ────────
CREATE TABLE IF NOT EXISTS outbox_events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'chapter',
  aggregate_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  retry_count INT NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox_events(created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS block_media_versions (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id      UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  block_id        TEXT NOT NULL,
  version         INT NOT NULL DEFAULT 1,
  action          TEXT NOT NULL,
  changes         TEXT[] NOT NULL DEFAULT '{}',
  media_ref       TEXT,
  prompt_snapshot TEXT DEFAULT '',
  caption_snapshot TEXT DEFAULT '',
  ai_model        TEXT,
  content_type    TEXT,
  size_bytes      BIGINT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bmv_chapter_block
  ON block_media_versions(chapter_id, block_id, version DESC);

-- ── chapter_audio_segments: AI TTS / uploaded audio per block ───────────
CREATE TABLE IF NOT EXISTS chapter_audio_segments (
  segment_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id       UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  block_index      INT NOT NULL,
  source_text      TEXT NOT NULL,
  source_text_hash VARCHAR(64) NOT NULL,
  voice            TEXT NOT NULL,
  provider         TEXT NOT NULL,
  language         TEXT NOT NULL,
  media_key        TEXT NOT NULL,
  duration_ms      INT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audio_seg_lookup
  ON chapter_audio_segments(chapter_id, language, voice, block_index);

-- ── Phase 8H: reading analytics ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reading_progress (
  user_id        UUID NOT NULL,
  book_id        UUID NOT NULL,
  chapter_id     UUID NOT NULL,
  read_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  time_spent_ms  BIGINT NOT NULL DEFAULT 0,
  scroll_depth   DOUBLE PRECISION NOT NULL DEFAULT 0,
  read_count     INT NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, book_id, chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_rp_user_book ON reading_progress(user_id, book_id);

-- ── KG-ML M3 (DD3): per-(user,book) reader-language preference ──────────
-- Server SSOT for the language a user prefers to READ a book in — distinct
-- from UI language (auth.user_preferences.ui_language). Per-(user,book) so it
-- can NEVER become a shared mutable row (tenancy rule); cross-device because it
-- lives in the DB, not localStorage (CLAUDE.md data-persistence rule). Read by
-- knowledge-service language-aware retrieval (M4) + chat/composition consumers
-- (M7) via the /internal/books/{id}/reader-language resolver. No FK to books
-- (matches reading_progress — a soft per-user table; book existence is gated at
-- the handler via canViewOrPublic).
CREATE TABLE IF NOT EXISTS user_book_prefs (
  user_id         UUID NOT NULL,
  book_id         UUID NOT NULL,
  reader_language TEXT NOT NULL,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, book_id)
);

CREATE TABLE IF NOT EXISTS book_views (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id    UUID NOT NULL,
  user_id    UUID,
  session_id TEXT,
  referrer   TEXT,
  viewed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bv_book ON book_views(book_id, viewed_at DESC);

-- ── Phase 9: import jobs for .docx/.epub import ───────────────────────
CREATE TABLE IF NOT EXISTS import_jobs (
  id               UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id          UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  user_id          UUID NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',
  filename         TEXT NOT NULL,
  file_format      TEXT NOT NULL,
  file_size        BIGINT NOT NULL,
  file_storage_key TEXT NOT NULL,
  chapters_created INT NOT NULL DEFAULT 0,
  error            TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_import_jobs_book ON import_jobs(book_id, created_at DESC);

-- P9-02: User favorites
CREATE TABLE IF NOT EXISTS user_favorites (
  user_id    UUID NOT NULL,
  book_id    UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, book_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_book ON user_favorites(book_id);

-- ═══════════════════════════════════════════════════════════════
-- P1 (hierarchical extraction T1) - 2026-05-23
-- Spec: docs/specs/2026-05-23-p1-structural-decomposer.md §D2
--
-- parts + scenes tables for structural decomposition of imported books.
-- chapters.part_id + chapters.structural_path tie chapters into the
-- hierarchy. Legacy chapters: part_id and structural_path stay NULL —
-- P2 extraction code falls back to chapter_drafts.body when no scenes
-- exist (R-SELF-1 fix). NO backfill.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS parts (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  sort_order      INT  NOT NULL,
  title           TEXT,
  path            TEXT NOT NULL,
  parse_version   INT  NOT NULL DEFAULT 1,
  lifecycle_state TEXT NOT NULL DEFAULT 'active',
  trashed_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, sort_order)
);

CREATE TABLE IF NOT EXISTS scenes (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id      UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  book_id         UUID REFERENCES books(id) ON DELETE CASCADE,  -- 22-A1/SC1: NULLABLE, backfilled from chapters
  sort_order      INT  NOT NULL,
  path            TEXT NOT NULL,
  title           TEXT NOT NULL DEFAULT '',                     -- 22-A1: parsed heading (AUTHORED title = outline_node.title)
  leaf_text       TEXT NOT NULL,
  content_hash    TEXT NOT NULL,
  source_scene_id UUID,                                         -- 22-A1/SC2: soft ref → composition outline_node.id (NO FK, non-unique)
  parse_version   INT  NOT NULL DEFAULT 1,
  lifecycle_state TEXT NOT NULL DEFAULT 'active',
  trashed_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_id, sort_order)
);

ALTER TABLE chapters ADD COLUMN IF NOT EXISTS part_id UUID
  REFERENCES parts(id) ON DELETE SET NULL;
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structural_path TEXT;

CREATE INDEX IF NOT EXISTS idx_scenes_chapter_sort_active
  ON scenes(chapter_id, sort_order) WHERE lifecycle_state = 'active';
CREATE INDEX IF NOT EXISTS idx_scenes_content_hash ON scenes(content_hash);
CREATE INDEX IF NOT EXISTS idx_chapters_part ON chapters(part_id)
  WHERE part_id IS NOT NULL;

-- ── Canon Model CM1 (editorial lifecycle) - 2026-06-04 ──────────────────────
-- A chapter is canon only once PUBLISHED. editorial_status gates canonization;
-- published_revision_id pins the immutable chapter_revisions snapshot that IS
-- the canon (decoupled from the live draft). New chapters default 'draft';
-- the one-time backfill (backfillSQL, marker-gated) flips pre-existing
-- chapters with revisions to 'published'. No review-pending state (YAGNI).
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'draft'
  CHECK (editorial_status IN ('draft','published'));
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS published_revision_id UUID
  REFERENCES chapter_revisions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_chapters_editorial ON chapters(book_id, editorial_status);
-- ── 26 IX-3 (index freshness marker) — 2026-07-11 ───────────────────────────
-- last_parsed_revision_id pins the revision the .index/ (scenes) rows were last
-- parsed from. NULL = never parsed (so the IX-3 sweeper's legacy-backfill
-- predicate last_parsed_revision_id IS DISTINCT FROM published_revision_id
-- matches every already-published chapter on its first sweep). A plain UUID (no
-- FK): it names a chapter_revisions.id but a revision purge must not fail on it —
-- a dangling marker just re-triggers a heal. IS DISTINCT FROM
-- published_revision_id on a published chapter means the index is stale.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS last_parsed_revision_id UUID;
-- ── WS-0.2 publish-independent KG indexing — 2026-07-11 ─────────────────────
-- Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.1
--
-- PUBLISH stops gating the knowledge graph. Publish now means only "this is the
-- canonical/shareable version"; INDEXING ("add this to my knowledge") becomes an
-- independent act available on ANY chapter of ANY book kind, draft or published.
-- Writers draft without publishing and still want a glossary/KG; some book kinds
-- (kind='diary') have no publish at all.
--
-- kg_indexed_revision_id = the revision the knowledge layer (and the scene index it
-- depends on) reflects. It is what the reparse sweeper keys on, replacing
-- published_revision_id. A plain UUID with NO FK — deliberately mirroring
-- last_parsed_revision_id above, for the same reason: a revision purge must not fail
-- on it; a dangling pointer just re-triggers a heal. (published_revision_id's FK is
-- ON DELETE SET NULL, which would silently UN-INDEX a chapter on revision GC.)
--
-- kg_exclude = the explicit opt-out that publish-gating used to provide implicitly.
-- PRODUCER-side authoritative (§3.7): knowledge-service cannot see this column, so
-- book-service simply does not set the pointer and does not emit chapter.kg_indexed
-- when it is true.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS kg_indexed_revision_id UUID;
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS kg_exclude BOOLEAN NOT NULL DEFAULT false;
-- Serves the sweeper's hot predicate (kg_indexed_revision_id IS NOT NULL AND
-- kg_exclude = false AND last_parsed IS DISTINCT FROM kg_indexed) and the new
-- kg_indexed filter on GET /internal/books/{id}/chapters.
CREATE INDEX IF NOT EXISTS idx_chapters_kg_indexed
  ON chapters(book_id) WHERE kg_indexed_revision_id IS NOT NULL AND kg_exclude = false;
-- One-row-per-step marker so the data backfill (backfillSQL) runs EXACTLY once,
-- not every startup (book-service has no migration ledger). Without this guard
-- a post-CM1 draft chapter that gains revisions while being written would be
-- wrongly flipped to 'published' on the next restart.
CREATE TABLE IF NOT EXISTS canon_model_migration (
  id         TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- C20 (world container) - 2026-06-14
-- Spec: docs/raid/cycle_briefs/20_world-container-api.md ; G1 + ARCH-REVIEW LOCKED.
--
-- A "world" groups books (book-service-only; lore stays book_id/chapter_id-keyed
-- and rolls up to a world via its books — NO world_id column on glossary/
-- knowledge/composition). books.world_id is a NULLABLE FK (default NULL =
-- standalone book), ON DELETE SET NULL so deleting a world returns its member
-- books to standalone (NEVER cascade-deletes the books). No backfill: existing
-- world_id=NULL books behave exactly as today.
--
-- ARCH-REVIEW LOCK: world creation auto-provisions a HIDDEN "world bible" chapter
-- at sort_order 0 (is_bible flag) so the chapter-keyed lore machinery (glossary
-- chapter_entity_links.chapter_id NOT NULL, knowledge chapter-keyed extraction,
-- composition outline) works prose-less. The is_bible flag marks it hidden.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS worlds (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_worlds_owner ON worlds(owner_user_id, created_at DESC);

ALTER TABLE books ADD COLUMN IF NOT EXISTS world_id UUID
  REFERENCES worlds(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_books_world ON books(world_id)
  WHERE world_id IS NOT NULL;

-- books.is_bible marks the auto-created world-bible CONTAINER book hidden, so it
-- never leaks into the user's normal library, the world's book list, or book
-- counts (the chapter-level is_bible hides the lore anchor; this hides its book).
ALTER TABLE books ADD COLUMN IF NOT EXISTS is_bible BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE chapters ADD COLUMN IF NOT EXISTS is_bible BOOLEAN NOT NULL DEFAULT false;

-- W10-M2 — world maps (a worldbuilder's reference map: a base image + pins/regions
-- linked to location entities). WORLD-scoped (a map spans a world's books; world_id
-- lives here in book-service, G1-clean). Markers/regions reference a glossary
-- location entity by a SOFT cross-service UUID (glossary is a separate DB — no hard
-- FK). The image blob lives in MinIO (image_object_key); the row is authored
-- independently of the image, so markers/regions use relative [0,1] coords. ON DELETE
-- CASCADE from worlds (delete a world → its maps go) and from world_maps (→ markers,
-- regions), so a map is self-cleaning.
CREATE TABLE IF NOT EXISTS world_maps (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id UUID NOT NULL,
  world_id UUID NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  image_object_key TEXT,
  image_w INT,
  image_h INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_world_maps_world ON world_maps(world_id, created_at DESC);

CREATE TABLE IF NOT EXISTS map_markers (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  map_id UUID NOT NULL REFERENCES world_maps(id) ON DELETE CASCADE,
  entity_id UUID,             -- soft cross-service ref → glossary location entity (nullable)
  label TEXT NOT NULL,
  x DOUBLE PRECISION NOT NULL, -- relative [0,1] on the base image (float64 → exact round-trip)
  y DOUBLE PRECISION NOT NULL,
  marker_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_map_markers_map ON map_markers(map_id);

CREATE TABLE IF NOT EXISTS map_regions (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  map_id UUID NOT NULL REFERENCES world_maps(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  polygon JSONB NOT NULL,     -- array of [x,y] relative points
  entity_id UUID,             -- soft cross-service ref → glossary location entity (nullable)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_map_regions_map ON map_regions(map_id);

-- ═══════════════════════════════════════════════════════════════
-- MCP fan-out Tier-W single-use confirm-token ledger - 2026-06-20
-- /review-impl HIGH: the confirm route (confirmBookAction) must be single-use.
-- The stateless kit confirm token carries no jti, so we key on the SHA-256 hash
-- of the full token string. confirmBookAction claims the hash (INSERT … ON
-- CONFLICT DO NOTHING) BEFORE running the effect; a replay within the 10-min TTL
-- hits the PK (0 rows affected) and is refused, so publish/delete/etc. run at
-- most once per token (no duplicate chapter_revisions row, no duplicate
-- chapter.published outbox event). exp is optional metadata for a future janitor.
-- Mirrors provider-registry settings_consumed_tokens. Additive + idempotent —
-- book-service has no down-migration; Up() re-run is the rollback story.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS book_consumed_tokens (
  token_hash  TEXT PRIMARY KEY,
  consumed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  exp         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_book_consumed_tokens_exp ON book_consumed_tokens(exp);

-- ═══════════════════════════════════════════════════════════════
-- RAID C1 (per-book steering store) - 2026-07-02
-- Spec: docs/specs/2026-07-02-raid-loadbearing-decision-records.md §DR-C1
--
-- Author-written per-book rules (story-bible-as-steering; the Cursor-rules /
-- Kiro-steering analog) rendered into matching chat turns by chat-service via
-- GET /internal/books/{book_id}/steering. Tenancy: book_id is the scope key
-- (write = owner + EDIT grantees; read = VIEW grant). UNIQUE(book_id, name)
-- is the SCOPED unique — never UNIQUE(name) (the kinds-bug smell). Caps keep
-- steering tight because it is taxed every turn: body <= 8000 chars (CHECK
-- here) and <= 20 rows/book (soft cap, enforced 422 in the handler — a row
-- count can't live in DDL). inclusion_mode 'auto' is accepted but v1-honest:
-- treated like 'manual' (#name trigger) until the model-pull tool ships.
-- Additive + idempotent — Up() re-run is the rollback story (no ledger).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS book_steering (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  body            TEXT NOT NULL CHECK (char_length(body) <= 8000),
  inclusion_mode  TEXT NOT NULL DEFAULT 'always'
      CHECK (inclusion_mode IN ('always','scene_match','manual','auto')),
  match_pattern   TEXT,
  enabled         BOOLEAN NOT NULL DEFAULT true,
  author_user_id  UUID NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, name)
);
CREATE INDEX IF NOT EXISTS idx_book_steering_book ON book_steering(book_id, created_at);

-- ═══════════════════════════════════════════════════════════════
-- Chapter Browser CB3 (word_count) - 2026-07-04
-- Spec: docs/specs/2026-07-01-writing-studio/15_chapter_browser.md §CB3
--
-- word_count is a denormalized, DB-maintained aggregate over a chapter's
-- chapter_blocks.text_content (multilingual: CJK char-count vs Latin
-- word-split-count, mirroring computeReadingStats' CJK_REGEX heuristic —
-- see fn_word_count_for_text below). Kept fresh by a trigger on
-- chapter_blocks (fn_recompute_chapter_word_count, mirrors the existing
-- fn_extract_chapter_blocks/trg_extract_chapter_blocks shape — same table,
-- same "recompute-parent-on-child-write" pattern, not a new mechanism).
--
-- NEW rows default 0 (never NULL) — backward compatible with every existing
-- INSERT into chapters. EXISTING rows also start at 0 until the batched,
-- marker-gated backfill (backfillWordCounts in migrate.go) runs — a Go loop
-- (not a single giant UPDATE) so a book with thousands of chapters (real dev
-- data: up to ~4200/book) never takes one table-locking statement.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS word_count INT NOT NULL DEFAULT 0;

-- One-row-per-step marker (mirrors canon_model_migration) so the batched
-- backfill runs to completion once, not on every startup. Safe to re-run to
-- completion if interrupted mid-way (recompute is idempotent — no correctness
-- risk, only wasted CPU), so no per-batch checkpointing is needed.
CREATE TABLE IF NOT EXISTS word_count_backfill_migration (
  id         TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- D-CHAPTER-BLOCKS-STALE-EXTRACTION — 2026-07-05
--
-- fn_extract_chapter_blocks read ONLY the client-supplied _text snapshot
-- (addTextSnapshots, frontend/src/lib/tiptap-utils.ts). Every sibling _text-only
-- SQL read was swept to union _text else nested standard-tiptap text leaves
-- (7b9cd4fda), but that sweep missed this WRITE-side trigger — the one thing
-- word_count, lexical search, and chapter export all actually read
-- (chapter_blocks), not the raw body. Any chapter saved without a client _text
-- annotation (import, agent/MCP write, pre-annotation-era save) got
-- permanently-empty chapter_blocks text_content — invisible until word_count/
-- Chapter-Browser export made it visible live. Fixed in fn_extract_chapter_blocks
-- itself (same union); this table gates a ONE-TIME re-extraction backfill
-- (backfillChapterBlocksExtraction) for chapters whose blocks exist but are
-- ALL empty under the old logic.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS chapter_blocks_extraction_backfill_migration (
  id         TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- PDF book import — docs/specs/2026-07-06-pdf-book-import.md
--
-- import_jobs gains pages_per_chunk + caption_images (only meaningful when
-- file_format='pdf'; NULL/false for every pre-existing docx/epub/txt/md job).
-- chapters gains import_job_id (L9 idempotency safeguard) — a redelivered
-- outbox event's per-chunk chapter insert is ON CONFLICT DO NOTHING against
-- (book_id, import_job_id, structural_path), so a worker crash mid-book only
-- loses the in-flight chunk, not the whole import (spec §6.7). Scoped to the
-- PDF path only: import_job_id stays NULL for every existing docx/epub/txt/md
-- chapter, so the partial index touches none of them.
--
-- chapter_page_images is a new per-image asset table (spec §4.4): one row per
-- extracted+deduped embedded image, caption NULL when caption_images=false
-- (L7) or a per-image vision call degraded (never fails the chunk, §6.4/§6.7).
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS pages_per_chunk INT;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS caption_images BOOLEAN NOT NULL DEFAULT false;
-- BYOK model choice for the vision op — only set when caption_images=true.
-- The vision op has no platform default (Provider gateway invariant), so the
-- caller (FE) must supply an explicit vision-capable model.
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS vision_model_source TEXT;
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS vision_model_ref TEXT;

ALTER TABLE chapters ADD COLUMN IF NOT EXISTS import_job_id UUID
  REFERENCES import_jobs(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_chapters_unique_import_job_path
  ON chapters(book_id, import_job_id, structural_path)
  WHERE import_job_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS chapter_page_images (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id  UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  page_number INT NOT NULL,
  storage_key TEXT NOT NULL,
  caption     TEXT,
  model_ref   TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chapter_page_images_chapter ON chapter_page_images(chapter_id);

-- ═══════════════════════════════════════════════════════════════
-- Scene model 22-A1 - 2026-07-10
-- Spec: docs/specs/2026-07-01-writing-studio/22_scene_model_and_crud.md
--
-- scenes gains book_id (SC1 — direct book scope; NULLABLE, backfilled from
-- chapters.book_id by the batched, marker-gated backfillScenesBookID — spec 22
-- explicitly forbids a bare full-table UPDATE, 10k+ chapter books are real),
-- title (parsed heading; the AUTHORED title stays on composition's
-- outline_node.title), and source_scene_id (SC2 amended: the source map — a
-- SOFT ref to composition.outline_node.id, deliberately NO FK because it
-- crosses a service/DB boundary, NULLABLE for undecompiled imports,
-- NON-unique). NO 'origin' column — dropped by the SC5 inversion: every
-- scenes row is parser output, so the column would be a constant.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS book_id UUID
  REFERENCES books(id) ON DELETE CASCADE;
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
ALTER TABLE scenes ADD COLUMN IF NOT EXISTS source_scene_id UUID;

CREATE INDEX IF NOT EXISTS idx_scenes_book_active
  ON scenes(book_id, chapter_id, sort_order) WHERE lifecycle_state = 'active';
CREATE INDEX IF NOT EXISTS idx_scenes_source
  ON scenes(source_scene_id) WHERE source_scene_id IS NOT NULL;

-- One-row-per-step marker (mirrors word_count_backfill_migration) so the
-- batched book_id backfill runs to completion once, not on every startup.
-- Safe to re-run to completion if interrupted — the copy is a pure function
-- of current chapters.book_id (see backfillScenesBookID).
CREATE TABLE IF NOT EXISTS scenes_book_id_backfill_migration (
  id         TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
`

// WorldsDownSQL is the explicit reversible DDL for the C20 world container.
// book-service has NO migration ledger (Up() idempotency is the normal rollback
// story), but the cycle's acceptance gate exercises a real-PG round-trip
// (up → down → re-up) to prove the additions are cleanly reversible. The world_id
// COLUMN must be dropped BEFORE the worlds TABLE (the FK depends on it); is_bible
// is left in place (additive, harmless on re-up — dropping it orphans no FK).
const WorldsDownSQL = `
ALTER TABLE books DROP COLUMN IF EXISTS world_id;
DROP INDEX IF EXISTS idx_books_world;
DROP TABLE IF EXISTS worlds;
DROP INDEX IF EXISTS idx_worlds_owner;
`

// rawSearchExtensionSQL / rawSearchIndexSQL — lexical leg of raw-search
// (docs/specs/2026-06-07-raw-search.md §3.2). Run as BEST-EFFORT separate Execs
// in Up() (NOT inside schemaSQL) so a DB role lacking CREATE EXTENSION privilege
// degrades search to 500-on-use rather than aborting the whole schema-init
// transaction / blocking startup (review-impl MED-1; mirrors the block_count
// pattern below). Idempotent (IF NOT EXISTS); rollback = DROP INDEX
// idx_chapter_blocks_trgm.
const rawSearchExtensionSQL = `CREATE EXTENSION IF NOT EXISTS pg_trgm`
const rawSearchIndexSQL = `CREATE INDEX IF NOT EXISTS idx_chapter_blocks_trgm
  ON chapter_blocks USING gin (text_content gin_trgm_ops)`

// tenantAuditSQL — P2·F append-only tenant-boundary audit. A row is written the
// FIRST time a caller crosses into a book they do NOT own (a collaborator read, or
// a denied under-grant / no-grant attempt on an existing book), coalesced to one
// row per (actor, book, outcome) per window (see api/tenant_audit.go). It records
// ONLY ids + a coarse outcome enum — never a free-text detail, path, or payload —
// so there is nothing to scrub (the P2·F "no un-scrubbed field" guarantee is
// structural). Modeled on auth-service's admin_token_issuance_audit / mcp_call_audit
// append-only pattern: UUID PK, denormalized owner for post-deletion forensics,
// outcome CHECK enum, created_at index, REVOKE UPDATE/DELETE. No FK to books: the
// audit trail must OUTLIVE a deleted book (forensics), same rationale as
// mcp_call_audit not FK-ing its key_id.
const tenantAuditSQL = `
CREATE TABLE IF NOT EXISTS tenant_access_audit (
  audit_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  actor_id        UUID NOT NULL,                 -- the crossing (non-owner) caller
  book_id         UUID NOT NULL,                 -- the resource crossed into
  owner_id        UUID NOT NULL,                 -- the tenant boundary owner (denormalized)
  outcome         TEXT NOT NULL CHECK (outcome IN ('granted','denied')),
  coalesce_bucket TIMESTAMPTZ NOT NULL,          -- window start; dedups first-per-window
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- First-per-window coalescing: one row per (actor, book, outcome) per bucket. The
-- emit does ON CONFLICT DO NOTHING against this, so a collaborator paging chapters
-- emits at most one 'granted' row per window instead of one per request.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_audit_window
  ON tenant_access_audit (actor_id, book_id, outcome, coalesce_bucket);

-- Owner-forensics read path: who crossed into my books, newest first.
CREATE INDEX IF NOT EXISTS idx_tenant_audit_owner_created
  ON tenant_access_audit (owner_id, created_at DESC);

-- Append-only: REVOKE UPDATE/DELETE so even a compromised app role can't rewrite
-- the trail. Same dev-stack caveat as auth-service's audit tables — a no-op when
-- connected as the DB owner (dev); production MUST run book-service under
-- app_service_role for this to bite.
DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE tenant_access_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;
`

// migrationLockKey is a fixed application-defined key for the migration advisory
// lock (arbitrary 64-bit constant — the ASCII bytes of "bookmig8"). Distinct from
// glossary-service's key: they share the dev Postgres INSTANCE (advisory locks
// are cluster-wide per database connection), so an accidental key collision would
// needlessly serialize unrelated services' startups.
const migrationLockKey int64 = 0x626f6f6b6d696738

// execGuarded runs an idempotent DDL batch inside a transaction that first takes
// a transaction-scoped advisory lock. This serializes concurrent migration runs
// — parallel `go test` package binaries sharing one dev DB, or two app instances
// starting at once — so overlapping CREATE/ALTER on the same tables queue on a
// single ordered lock instead of deadlocking on table locks acquired in
// different orders (SQLSTATE 40P01). Each batch already ran as one implicit
// transaction via pool.Exec, so wrapping it explicitly is behaviour-preserving;
// uncontended (normal startup) it adds one cheap lock call. The lock releases
// automatically when the transaction commits/rolls back. Mirrors
// glossary-service's migrate.execGuarded (RAID C1 / shared-DB deadlock lesson).
func execGuarded(ctx context.Context, pool *pgxpool.Pool, name, sql string) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("migrate %s: begin: %w", name, err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, migrationLockKey); err != nil {
		return fmt.Errorf("migrate %s: lock: %w", name, err)
	}
	if _, err := tx.Exec(ctx, sql); err != nil {
		return fmt.Errorf("migrate %s: %w", name, err)
	}
	return tx.Commit(ctx)
}

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if err := execGuarded(ctx, pool, "schema", schemaSQL); err != nil {
		return err
	}

	// PG18: add virtual generated column for block count (idempotent).
	// Best-effort (error ignored) — same semantics as before, now serialized.
	_ = execGuarded(ctx, pool, "block-count", `
		DO $$ BEGIN
			ALTER TABLE chapter_drafts ADD COLUMN block_count INT
				GENERATED ALWAYS AS (jsonb_array_length(body -> 'content')) VIRTUAL;
		EXCEPTION WHEN duplicate_column THEN NULL;
		END $$;
	`)

	// Raw search Phase 1 (lexical leg): pg_trgm + trigram index, best-effort &
	// separate from schemaSQL so a privilege failure can't abort schema init or
	// block startup (review-impl MED-1). Search degrades to 500-on-use if absent.
	_ = execGuarded(ctx, pool, "pg-trgm", rawSearchExtensionSQL)
	_ = execGuarded(ctx, pool, "trgm-index", rawSearchIndexSQL)

	// Canon Model CM1: one-time editorial backfill (marker-gated; idempotent).
	if err := execGuarded(ctx, pool, "canon backfill", backfillSQL); err != nil {
		return err
	}

	// WS-0.2: seed kg_indexed_revision_id from published_revision_id (marker-gated).
	// ORDER IS LOAD-BEARING — this MUST run AFTER the CM1 canon backfill above, which
	// is what pins published_revision_id on pre-CM1 legacy chapters. Run it first and
	// those chapters still have a NULL published_revision_id, so they'd get a NULL
	// kg pointer, drop out of the re-keyed sweeper, and their scenes would never be
	// parsed — a silent, permanent hole in the graph that the marker would then make
	// unrecoverable on restart.
	if err := execGuarded(ctx, pool, "kg-indexed backfill", kgIndexedBackfillSQL); err != nil {
		return err
	}

	// D1-03: trigger function to extract chapter_blocks from Tiptap JSONB
	if err := execGuarded(ctx, pool, "trigger", triggerSQL); err != nil {
		return err
	}

	// P2·F: append-only tenant-boundary audit table.
	if err := execGuarded(ctx, pool, "tenant-audit", tenantAuditSQL); err != nil {
		return err
	}

	// D-CHAPTER-BLOCKS-STALE-EXTRACTION: re-fire the (now-fixed) extraction trigger
	// for every chapter whose blocks are stale under the old _text-only logic.
	// Must run BEFORE backfillWordCounts so a fresh install's word_count backfill
	// reads already-corrected chapter_blocks; on an existing install (word_count
	// already backfilled once) each re-touch cascades word_count via
	// fn_recompute_chapter_word_count regardless of that marker.
	if err := backfillChapterBlocksExtraction(ctx, pool); err != nil {
		slog.Error("book-service: chapter_blocks extraction backfill failed; will retry on next startup", "err", err)
	}
	// D-2-PROSE-BLOCKS-BACKFILL: also cover chapters with a draft but ZERO blocks (the case v1 skips).
	if err := backfillChapterBlocksMissing(ctx, pool); err != nil {
		slog.Error("book-service: chapter_blocks missing-blocks backfill failed; will retry on next startup", "err", err)
	}

	// CB3: batched, marker-gated word_count backfill for pre-existing chapters.
	// Best-effort — a failure here must NEVER block book-service startup (word_count
	// simply stays 0 for un-backfilled rows, a graceful degrade, not a hard
	// requirement); the marker stays unset on failure so the next startup retries.
	if err := backfillWordCounts(ctx, pool); err != nil {
		slog.Error("book-service: word_count backfill failed; will retry on next startup", "err", err)
	}

	// 22-A1: batched, marker-gated scenes.book_id backfill from chapters.
	// Best-effort — same degrade story as word_count: a failure must NEVER block
	// book-service startup (book_id simply stays NULL for un-backfilled rows and
	// readers keep resolving scope via chapter_id → chapters.book_id); the marker
	// stays unset on failure so the next startup retries.
	if err := backfillScenesBookID(ctx, pool); err != nil {
		slog.Error("book-service: scenes.book_id backfill (v1) failed; will retry on next startup", "err", err)
	}
	// 22-A5: bumped-marker re-run closes the A1→A5 interim window. A1's write path
	// did NOT set scenes.book_id, so every scene parsed after the v1 marker was
	// stamped but before the A5 write path landed carries book_id NULL permanently,
	// and the v1 marker blocks a rescan. A5 wires the parse writers to set book_id
	// AND runs this one-time sweep under a bumped marker to fill those interim rows.
	// Same best-effort degrade as v1.
	if err := backfillScenesBookIDV2(ctx, pool); err != nil {
		slog.Error("book-service: scenes.book_id backfill (v2) failed; will retry on next startup", "err", err)
	}

	return nil
}

// wordCountBackfillBatchSize — chapters processed per batch. Chosen so a book
// with thousands of chapters (real dev data: up to ~4200/book) never takes one
// giant table-locking UPDATE (spec CB3 / plan risk note).
const wordCountBackfillBatchSize = 500

// backfillWordCounts computes word_count for every pre-existing chapter, in
// small batches ordered by id (chapters.id is a UUIDv7 — time-ordered, so a
// simple keyset `id > lastID ORDER BY id LIMIT N` cursor is a total order with
// no duplicate/skip risk). Marker-gated (word_count_backfill_migration) so a
// fresh install's chapters (which already got a correct word_count from the
// INSERT-time trigger) don't get needlessly recomputed on every startup. Safe
// to re-run to completion if a prior run was interrupted by a crash — the
// computation is a pure function of current data, so repeating it is wasted
// CPU, never a correctness risk.
func backfillWordCounts(ctx context.Context, pool *pgxpool.Pool) error {
	var done bool
	if err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM word_count_backfill_migration WHERE id='wc_backfill_v1')`).Scan(&done); err != nil {
		return fmt.Errorf("check marker: %w", err)
	}
	if done {
		return nil
	}

	var lastID uuid.UUID // zero UUID sorts before every real chapter id
	for {
		rows, err := pool.Query(ctx, `SELECT id FROM chapters WHERE id > $1 ORDER BY id LIMIT $2`, lastID, wordCountBackfillBatchSize)
		if err != nil {
			return fmt.Errorf("fetch batch: %w", err)
		}
		ids := make([]uuid.UUID, 0, wordCountBackfillBatchSize)
		for rows.Next() {
			var id uuid.UUID
			if err := rows.Scan(&id); err != nil {
				rows.Close()
				return fmt.Errorf("scan batch id: %w", err)
			}
			ids = append(ids, id)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return fmt.Errorf("iterate batch: %w", err)
		}
		if len(ids) == 0 {
			break
		}
		lastID = ids[len(ids)-1]

		// Chapters with no blocks (agg has no matching row) simply keep their
		// default word_count=0 — correct for an empty chapter.
		if _, err := pool.Exec(ctx, `
WITH agg AS (
  SELECT chapter_id, string_agg(text_content, ' ' ORDER BY block_index) AS txt
  FROM chapter_blocks WHERE chapter_id = ANY($1)
  GROUP BY chapter_id
)
UPDATE chapters c
SET word_count = fn_word_count_for_text(agg.txt, c.original_language)
FROM agg WHERE c.id = agg.chapter_id
`, ids); err != nil {
			return fmt.Errorf("backfill batch (after id %s): %w", lastID, err)
		}

		if len(ids) < wordCountBackfillBatchSize {
			break // last (partial) batch — no more rows
		}
	}

	if _, err := pool.Exec(ctx, `INSERT INTO word_count_backfill_migration (id) VALUES ('wc_backfill_v1') ON CONFLICT DO NOTHING`); err != nil {
		return fmt.Errorf("mark backfill complete: %w", err)
	}
	return nil
}

// scenesBookIDBackfillBatchSize mirrors wordCountBackfillBatchSize's rationale:
// spec 22 explicitly forbids a bare full-table `UPDATE scenes SET book_id = …`
// (10k+ chapter books are real; that shape takes a full-table lock).
const scenesBookIDBackfillBatchSize = 500

// The two marker ids under which the batched book_id backfill has run. V1 (22-A1)
// filled every scene that pre-dated the column. V2 (22-A5) re-runs the SAME copy
// once more to catch the scenes created in the A1→A5 interim window: A1's write
// path did NOT set book_id, so every scene parsed between the two deploys carries
// book_id NULL permanently, and the V1 marker (already stamped) blocks a rescan.
// A5 wires the parse writers to set book_id AND bumps the marker so this one-time
// sweep closes that window.
const (
	scenesBookIDBackfillMarkerV1 = "scenes_book_id_backfill_v1"
	scenesBookIDBackfillMarkerV2 = "scenes_book_id_backfill_v2"
)

// backfillScenesBookID runs the 22-A1 sweep under the V1 marker. Kept as a named
// entry point (unchanged signature) so its DB-gated tests are untouched.
func backfillScenesBookID(ctx context.Context, pool *pgxpool.Pool) error {
	return runScenesBookIDBackfill(ctx, pool, scenesBookIDBackfillMarkerV1)
}

// backfillScenesBookIDV2 re-runs the same sweep under the V2 marker (22-A5) to
// fill the interim-window rows the V1 marker now shadows. On a fresh install V1
// already filled everything, so V2 finds zero NULL rows and simply stamps.
func backfillScenesBookIDV2(ctx context.Context, pool *pgxpool.Pool) error {
	return runScenesBookIDBackfill(ctx, pool, scenesBookIDBackfillMarkerV2)
}

// runScenesBookIDBackfill copies chapters.book_id onto every scenes row whose
// book_id is still NULL (spec 22-A1/A5 / SC1), in small keyset batches ordered by
// id (scenes.id is a UUIDv7 — time-ordered, so `id > lastID ORDER BY id LIMIT N`
// is a total order with no duplicate/skip risk). The batch query additionally
// filters `book_id IS NULL` so a crash-interrupted run's retry skips already-
// copied rows instead of re-writing them. Marker-gated
// (scenes_book_id_backfill_migration, keyed on `marker`) so completed installs
// skip the scan on every later startup. Safe to re-run to completion: the
// assignment is a pure copy of current chapters.book_id, so repeating it is
// wasted CPU, never a correctness risk — the backfillWordCounts safety argument.
// A scene whose chapter vanished mid-run simply doesn't match the UPDATE ... FROM
// join and keeps NULL (the FK cascade will remove it anyway).
func runScenesBookIDBackfill(ctx context.Context, pool *pgxpool.Pool, marker string) error {
	var done bool
	if err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM scenes_book_id_backfill_migration WHERE id=$1)`, marker).Scan(&done); err != nil {
		return fmt.Errorf("check marker: %w", err)
	}
	if done {
		return nil
	}

	var lastID uuid.UUID // zero UUID sorts before every real scene id
	for {
		rows, err := pool.Query(ctx, `SELECT id FROM scenes WHERE id > $1 AND book_id IS NULL ORDER BY id LIMIT $2`, lastID, scenesBookIDBackfillBatchSize)
		if err != nil {
			return fmt.Errorf("fetch batch: %w", err)
		}
		ids := make([]uuid.UUID, 0, scenesBookIDBackfillBatchSize)
		for rows.Next() {
			var id uuid.UUID
			if err := rows.Scan(&id); err != nil {
				rows.Close()
				return fmt.Errorf("scan batch id: %w", err)
			}
			ids = append(ids, id)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return fmt.Errorf("iterate batch: %w", err)
		}
		if len(ids) == 0 {
			break
		}
		lastID = ids[len(ids)-1]

		if _, err := pool.Exec(ctx, `
UPDATE scenes s
SET book_id = c.book_id
FROM chapters c
WHERE c.id = s.chapter_id AND s.id = ANY($1)
`, ids); err != nil {
			return fmt.Errorf("backfill batch (after id %s): %w", lastID, err)
		}

		if len(ids) < scenesBookIDBackfillBatchSize {
			break // last (partial) batch — no more rows
		}
	}

	if _, err := pool.Exec(ctx, `INSERT INTO scenes_book_id_backfill_migration (id) VALUES ($1) ON CONFLICT DO NOTHING`, marker); err != nil {
		return fmt.Errorf("mark backfill complete: %w", err)
	}
	return nil
}

// chapterBlocksExtractionBackfillBatchSize mirrors wordCountBackfillBatchSize's
// rationale (never one giant table-locking statement).
const chapterBlocksExtractionBackfillBatchSize = 500

// backfillChapterBlocksExtraction re-fires fn_extract_chapter_blocks (via a
// no-op `body = body` UPDATE, which the AFTER UPDATE OF body trigger treats as
// a real fire regardless of whether the value changed) for every chapter whose
// blocks exist but are ALL empty — the exact signature of the old _text-only
// extraction bug (D-CHAPTER-BLOCKS-STALE-EXTRACTION). Scoped to that signature,
// not every chapter_drafts row, so a chapter that's genuinely empty (never had
// prose) is correctly left alone, and a book with thousands of already-correct
// chapters isn't needlessly re-touched. Re-running the extraction is a pure
// function of current draft body content, so repeating it on retry/restart is
// wasted CPU, never a correctness risk — same safety argument as
// backfillWordCounts. Marker-gated so it runs to completion once.
func backfillChapterBlocksExtraction(ctx context.Context, pool *pgxpool.Pool) error {
	var done bool
	if err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM chapter_blocks_extraction_backfill_migration WHERE id='cb_extraction_backfill_v1')`).Scan(&done); err != nil {
		return fmt.Errorf("check marker: %w", err)
	}
	if done {
		return nil
	}

	var lastID uuid.UUID // zero UUID sorts before every real chapter id
	for {
		rows, err := pool.Query(ctx, `
SELECT d.chapter_id
FROM chapter_drafts d
WHERE d.chapter_id > $1
  AND EXISTS (SELECT 1 FROM chapter_blocks cb WHERE cb.chapter_id = d.chapter_id)
  AND NOT EXISTS (
    SELECT 1 FROM chapter_blocks cb
    WHERE cb.chapter_id = d.chapter_id AND cb.text_content IS NOT NULL AND cb.text_content <> ''
  )
ORDER BY d.chapter_id LIMIT $2
`, lastID, chapterBlocksExtractionBackfillBatchSize)
		if err != nil {
			return fmt.Errorf("fetch batch: %w", err)
		}
		ids := make([]uuid.UUID, 0, chapterBlocksExtractionBackfillBatchSize)
		for rows.Next() {
			var id uuid.UUID
			if err := rows.Scan(&id); err != nil {
				rows.Close()
				return fmt.Errorf("scan batch id: %w", err)
			}
			ids = append(ids, id)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return fmt.Errorf("iterate batch: %w", err)
		}
		if len(ids) == 0 {
			break
		}
		lastID = ids[len(ids)-1]

		if _, err := pool.Exec(ctx, `UPDATE chapter_drafts SET body = body WHERE chapter_id = ANY($1)`, ids); err != nil {
			return fmt.Errorf("re-extract batch (after id %s): %w", lastID, err)
		}

		if len(ids) < chapterBlocksExtractionBackfillBatchSize {
			break // last (partial) batch — no more rows
		}
	}

	if _, err := pool.Exec(ctx, `INSERT INTO chapter_blocks_extraction_backfill_migration (id) VALUES ('cb_extraction_backfill_v1') ON CONFLICT DO NOTHING`); err != nil {
		return fmt.Errorf("mark backfill complete: %w", err)
	}
	return nil
}

// backfillChapterBlocksMissing — D-2-PROSE-BLOCKS-BACKFILL (2026-07-15). The v1 backfill above
// only re-extracts chapters whose blocks EXIST but are all empty. A legacy draft with prose but
// ZERO chapter_blocks rows (a pre-trigger write, or a save that predated fn_extract_chapter_blocks)
// slips past it AND past prose_state (which reads chapter_blocks.text_content) — such a chapter
// under-counts as "no prose", which quietly mis-informs the rail's book-state probe. This closes
// that gap: it re-fires the extraction (the same no-op `body = body` UPDATE) for every draft with
// NO blocks at all, so the extraction INSERTs them from the draft's own content.
//
// Measured impact at authoring time was ZERO real rows (0 zero-block chapters carried prose in dev),
// because M0a's save_draft fix + the trigger populate blocks on every write since 2026-07-05. So
// this is a DEFENSIVE close, not a rescue of live data — but it makes prose_state exact for ALL
// chapters, and catches the case for free if it ever arises. Re-firing on a genuinely-empty draft
// is a harmless no-op (empty in, empty out). Marker-gated so it runs once.
func backfillChapterBlocksMissing(ctx context.Context, pool *pgxpool.Pool) error {
	var done bool
	if err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM chapter_blocks_extraction_backfill_migration WHERE id='cb_missing_backfill_v1')`).Scan(&done); err != nil {
		return fmt.Errorf("check missing-blocks marker: %w", err)
	}
	if done {
		return nil
	}
	var lastID uuid.UUID
	for {
		rows, err := pool.Query(ctx, `
SELECT d.chapter_id
FROM chapter_drafts d
WHERE d.chapter_id > $1
  AND NOT EXISTS (SELECT 1 FROM chapter_blocks cb WHERE cb.chapter_id = d.chapter_id)
ORDER BY d.chapter_id LIMIT $2`, lastID, chapterBlocksExtractionBackfillBatchSize)
		if err != nil {
			return fmt.Errorf("fetch missing-blocks batch: %w", err)
		}
		ids := make([]uuid.UUID, 0, chapterBlocksExtractionBackfillBatchSize)
		for rows.Next() {
			var id uuid.UUID
			if err := rows.Scan(&id); err != nil {
				rows.Close()
				return fmt.Errorf("scan missing-blocks id: %w", err)
			}
			ids = append(ids, id)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return fmt.Errorf("iterate missing-blocks batch: %w", err)
		}
		if len(ids) == 0 {
			break
		}
		lastID = ids[len(ids)-1]
		if _, err := pool.Exec(ctx, `UPDATE chapter_drafts SET body = body WHERE chapter_id = ANY($1)`, ids); err != nil {
			return fmt.Errorf("re-extract missing-blocks batch (after id %s): %w", lastID, err)
		}
		if len(ids) < chapterBlocksExtractionBackfillBatchSize {
			break
		}
	}
	if _, err := pool.Exec(ctx, `INSERT INTO chapter_blocks_extraction_backfill_migration (id) VALUES ('cb_missing_backfill_v1') ON CONFLICT DO NOTHING`); err != nil {
		return fmt.Errorf("mark missing-blocks backfill complete: %w", err)
	}
	return nil
}

// backfillSQL — Canon Model CM1 one-time data backfill. Pre-existing chapters
// with >=1 revision are already canon, so flip them to 'published' and pin the
// latest revision; revision-less chapters stay 'draft'. Marker-gated via
// canon_model_migration so it runs EXACTLY ONCE — a post-CM1 draft chapter that
// gains revisions while being written must NEVER be auto-published on restart.
const backfillSQL = `
DO $cm1$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM canon_model_migration WHERE id = 'cm1_editorial_backfill') THEN
    UPDATE chapters c
       SET editorial_status     = 'published',
           published_revision_id = (
             SELECT r.id FROM chapter_revisions r
             WHERE r.chapter_id = c.id
             ORDER BY r.created_at DESC, r.id DESC
             LIMIT 1
           )
     WHERE EXISTS (SELECT 1 FROM chapter_revisions r WHERE r.chapter_id = c.id);
    INSERT INTO canon_model_migration (id) VALUES ('cm1_editorial_backfill');
  END IF;
END $cm1$;
`

// kgIndexedBackfillSQL — WS-0.2 one-time data backfill for publish-independent KG
// indexing. Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.1/§6.
//
// Seeds kg_indexed_revision_id from published_revision_id on today's corpus, so the
// NEW sweeper predicate selects EXACTLY the set the OLD (published-gated) predicate
// selected — no re-parse storm on first sweep, no chapter silently dropping out of
// the graph. Proof (spec §6): the backfill set is exactly the old predicate's set;
// the new predicate keeps lifecycle_state='active' so trashed chapters stay out;
// chapters with a NULL published_revision_id are excluded by both.
//
// ⚠️ MARKER-GATED, and that is load-bearing — NOT mere startup-cost hygiene.
// This statement must run EXACTLY ONCE, not on every boot. If it re-ran, it would
// clobber the user's own decisions:
//
//	kg_exclude retraction (§3.8) clears kg_indexed_revision_id on a chapter the user
//	asked to keep OUT of their knowledge graph. That chapter is still
//	editorial_status='published' with a published_revision_id — so an ungated
//	re-run would RE-SET the pointer on the next restart and silently pull the
//	excluded chapter back into the KG. A privacy decision undone by a reboot.
//
// The `kg_exclude = false` guard below is belt-and-braces for exactly that case; the
// marker is the actual defense (it also makes the behavior independent of restart
// timing, which an "IS NULL"-guarded re-run would not be).
const kgIndexedBackfillSQL = `
DO $kg1$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM canon_model_migration WHERE id = 'kg_indexed_backfill_v1') THEN
    UPDATE chapters
       SET kg_indexed_revision_id = published_revision_id
     WHERE editorial_status      = 'published'
       AND published_revision_id IS NOT NULL
       AND kg_exclude            = false;
    INSERT INTO canon_model_migration (id) VALUES ('kg_indexed_backfill_v1');
  END IF;
END $kg1$;
`

const triggerSQL = `
-- ── fn_extract_chapter_blocks: UPSERT blocks from Tiptap JSON ────────────
CREATE OR REPLACE FUNCTION fn_extract_chapter_blocks()
RETURNS TRIGGER AS $fn$
DECLARE
  _max_idx INT;
BEGIN
  -- 1. UPSERT blocks. Per-node text prefers the editor's _text snapshot
  -- (addTextSnapshots, frontend/src/lib/tiptap-utils.ts), else joins the node's
  -- nested standard-tiptap text leaves ($.**.text) — the SAME union already
  -- applied to every sibling _text-only read (getInternalChapterRevisionText/
  -- getRevision/revisionForCompare/lexicalSearchCanonSQL, 7b9cd4fda) but missed
  -- here: a _text-only extraction left ANY chapter written without that client
  -- annotation (import, agent/MCP write, pre-annotation-era save) with permanently
  -- empty chapter_blocks — word_count/search/export all read this table, not the
  -- raw body, so the gap was invisible until those features shipped.
  -- strict jsonpath mode (not the default lax): lax mode's automatic array-unwrap
  -- double-visits a single-text-node block (heading/paragraph, the overwhelmingly
  -- common case) via **, silently DUPLICATING every such block's extracted text —
  -- caught live re-testing this exact fix; the same latent bug existed in all 4
  -- pre-existing call sites above and is fixed there too in this same change.
  INSERT INTO chapter_blocks (chapter_id, block_index, block_type, text_content, content_hash, attrs)
  SELECT
    NEW.chapter_id,
    (x.ord - 1),
    x.elem->>'type',
    COALESCE(n.node_text, ''),
    encode(sha256(COALESCE(n.node_text, '')::bytea), 'hex'),
    x.elem->'attrs'
  FROM jsonb_array_elements(NEW.body -> 'content') WITH ORDINALITY AS x(elem, ord)
  CROSS JOIN LATERAL (
    SELECT COALESCE(
      x.elem->>'_text',
      NULLIF((SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(x.elem, 'strict $.**.text') AS y(t)), '')
    ) AS node_text
  ) n
  WHERE x.elem->>'type' IS NOT NULL
  ON CONFLICT (chapter_id, block_index)
  DO UPDATE SET
    block_type   = EXCLUDED.block_type,
    text_content = EXCLUDED.text_content,
    content_hash = EXCLUDED.content_hash,
    attrs        = EXCLUDED.attrs,
    updated_at   = CASE
      WHEN chapter_blocks.content_hash = EXCLUDED.content_hash
      THEN chapter_blocks.updated_at
      ELSE now()
    END;

  -- 2. Delete blocks beyond new document length
  SELECT count(*) INTO _max_idx
  FROM jsonb_array_elements(NEW.body -> 'content') AS x(elem);

  DELETE FROM chapter_blocks
  WHERE chapter_id = NEW.chapter_id AND block_index >= _max_idx;

  -- 3. Fill heading_context (nearest preceding heading)
  UPDATE chapter_blocks cb SET
    heading_context = sub.ctx
  FROM (
    SELECT
      id,
      MAX(CASE WHEN block_type = 'heading' THEN text_content END)
        OVER (PARTITION BY chapter_id ORDER BY block_index
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ctx
    FROM chapter_blocks
    WHERE chapter_id = NEW.chapter_id
  ) sub
  WHERE cb.id = sub.id AND cb.chapter_id = NEW.chapter_id;

  RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

-- ── Trigger: fire after INSERT or UPDATE of body on chapter_drafts ────────
DO $$ BEGIN
  CREATE TRIGGER trg_extract_chapter_blocks
    AFTER INSERT OR UPDATE OF body ON chapter_drafts
    FOR EACH ROW
    EXECUTE FUNCTION fn_extract_chapter_blocks();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── fn_outbox_notify: pg_notify when new outbox event inserted ───────────
-- ── WS-1.1 · books.kind — the privacy lock (spec 03, T29/T30) — 2026-07-12 ──
--
-- kind is NOT cosmetic and NOT a UI hint. kind='diary' is the PRIVACY LOCK: every egress
-- guard in spec 09 (sharing, wiki, public-MCP, notifications, catalog, export, collaborator
-- grants) keys on it. If kind can be changed after creation — or missed on a create path —
-- the lock silently opens and a private diary becomes shareable.
--
-- So it is enforced in the DATABASE, not by convention:
--   1. A CHECK constrains the closed set.
--   2. A BEFORE UPDATE trigger REFUSES to let kind change. The only "enforcement" available
--      otherwise would be a convention that nobody adds kind to the two dynamic UPDATE
--      builders in server.go — and a convention is exactly what fails at 2am.
--
-- is_bible STAYS: it is the orthogonal hidden-from-counts flag, not a kind. (There is also a
-- chapters.is_bible; this backfill touches BOOKS ONLY. Do not invent a chapter kind.)
ALTER TABLE books ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'novel'
  CHECK (kind IN ('novel','document','lore','diary'));

-- Explicit backfill: a DEFAULT never revisits existing rows (the
-- add-column-if-not-exists-never-revisits-a-bad-default class). Pre-existing world-bibles
-- must become 'lore' HERE, in the same migration that teaches createWorldCore to set
-- kind='lore' — otherwise pre-migration bibles are lore and post-migration ones are novel.
--
-- ⚠️ MARKER-GATED (review-impl Phase 1). This UPDATE is a novel->lore transition, and the
-- kind-immutability trigger created just below it FORBIDS exactly that. On the first boot
-- the trigger does not exist yet, so the backfill runs cleanly. But schemaSQL runs on
-- EVERY boot, and from the second boot the trigger is already installed — so if a single
-- is_bible+novel row ever exists at that moment (an old-code bible, a manual insert, a
-- restored partial backup), this UPDATE would fire the trigger, RAISE, and abort the whole
-- migration → the service will not start. Gating it once removes the landmine entirely and
-- matches every other data backfill in this file.
DO $bible$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM canon_model_migration WHERE id = 'kind_is_bible_lore_backfill_v1') THEN
    UPDATE books SET kind = 'lore' WHERE is_bible = true AND kind = 'novel';
    INSERT INTO canon_model_migration (id) VALUES ('kind_is_bible_lore_backfill_v1');
  END IF;
END $bible$;

CREATE INDEX IF NOT EXISTS idx_books_kind ON books(owner_user_id, kind);

-- ONE active diary book per user (WS-1.4 provisioning step 1, spec 02 §Q2.1). Provisioning
-- is a retryable, concurrent fan-out (two devices open /assistant at once, a BFF call is
-- retried); its get-or-create matches on (owner_user_id, kind='diary', active). Without a
-- DB-level unique, two concurrent provisions race into TWO diary books and the user's
-- assistant memory silently splits in half — the exact split-brain the knowledge-side
-- one-per-user is_assistant unique prevents. Partial + active-only so a TRASHED diary
-- (E14: restore-vs-reprovision) does not block making a fresh one (the
-- partial-unique-must-exempt-tombstones lesson). Any ON CONFLICT targeting this must repeat
-- the predicate EXACTLY (the partial-index/ON-CONFLICT-predicate lesson).
CREATE UNIQUE INDEX IF NOT EXISTS uq_books_one_active_diary_per_user
  ON books(owner_user_id)
  WHERE kind = 'diary' AND lifecycle_state = 'active';

-- kind is IMMUTABLE. Changing a book's kind would strip its privacy lock (diary -> novel
-- makes a private diary publishable). To get a different kind, create a different book.
CREATE OR REPLACE FUNCTION fn_books_kind_immutable()
RETURNS TRIGGER AS $fn$
BEGIN
  IF NEW.kind IS DISTINCT FROM OLD.kind THEN
    RAISE EXCEPTION
      'books.kind is immutable (attempted % -> %). kind is the privacy lock: every egress '
      'guard keys on it, so changing it would silently make private content shareable. '
      'Create a new book instead.', OLD.kind, NEW.kind
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
  CREATE TRIGGER trg_books_kind_immutable
    BEFORE UPDATE ON books
    FOR EACH ROW
    EXECUTE FUNCTION fn_books_kind_immutable();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── WS-1.3 · diary entry columns (spec 01 §4.3, D9) — 2026-07-12 ──
--
-- A diary entry IS a chapter (that is the whole point of books.kind — the entire book
-- workspace, editor and chapter machinery is reused). These columns are diary-only and
-- nullable everywhere else.
--
-- entry_date — the LOCAL day the entry is about. It has NO timezone semantics at the DB
-- layer, deliberately: the distiller computes it from the user's IANA zone + day-cutoff
-- BEFORE the insert. Storing a timestamptz and deriving the day later would let a user who
-- flies to another timezone silently re-bucket their history.
--
-- journal_kind — 'primary' is THE entry for that day; 'supplement' is an extra one the user
-- added later. Only ONE primary per (book, day): "End my day" on a phone and a laptop at
-- the same moment must converge, not mint two entries. The partial unique index is what
-- makes that a database fact rather than a hope.
--
-- diary_kept_at — an ORTHOGONAL column, NOT a third value on editorial_status. Widening
-- editorial_status (today CHECK IN ('draft','published')) would break the reparse sweeper's
-- gate and the CM1 canon backfill, and it would contradict "a diary has no publish concept"
-- — the whole reason kind='diary' exists. Orthogonal sidesteps every existing consumer.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS entry_date DATE;
-- WS-3.7 (review M2): 'weekly' is a get-or-replace review kind. Fresh DBs get it inline; existing DBs
-- get it via the DROP+ADD below (ADD COLUMN IF NOT EXISTS is a no-op once the column exists, so the
-- inline CHECK never widens on an existing table — the migration-CHECK-must-revisit lesson).
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS journal_kind TEXT
  CHECK (journal_kind IS NULL OR journal_kind IN ('primary','supplement','weekly','reflection'));
-- D-REFLECTION-WIRE: 'reflection' is a get-or-replace weekly reflection draft (like 'weekly').
-- DROP+re-ADD re-widens an ALREADY-migrated DB (an add-if-absent would skip the re-widen — the
-- recurring CHECK-migration trap).
ALTER TABLE chapters DROP CONSTRAINT IF EXISTS chapters_journal_kind_check;
ALTER TABLE chapters ADD CONSTRAINT chapters_journal_kind_check
  CHECK (journal_kind IS NULL OR journal_kind IN ('primary','supplement','weekly','reflection'));
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS diary_kept_at TIMESTAMPTZ;
-- WS-1.8 (spec 06 §Q3/T21) — the IANA zone in effect when entry_date was computed, stored for
-- auditability. entry_date has no timezone semantics at the DB layer (the distiller resolves the
-- local day before the insert); entry_zone records WHICH zone produced it so a later zone change
-- is auditable and a spring-forward/DST question can be answered. NULL for pre-WS-1.8 entries.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS entry_zone TEXT;
-- C5 / SD-C5 (P-12) — diary encryption-at-rest marker. TRUE ⇒ this diary entry's prose columns
-- (chapter_raw_objects.body_text + chapter_drafts.body + chapter_revisions.body) hold AES-GCM
-- ciphertext under the owner's per-user DEK (AAD "chapter:<id>"), and chapter_blocks is empty for it.
-- FALSE (default) ⇒ plaintext (a pre-C5 entry, or a deployment with no DIARY_ENCRYPTION_KEY). The
-- flag disambiguates the format so decrypt-on-read tolerates both during the forward-encrypt rollout.
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS body_encrypted BOOLEAN NOT NULL DEFAULT false;

-- C5 / SD-C5 (cold-review HIGH-1) — the plaintext-bypass guard. Diary prose is encrypted at rest ONLY
-- when written through the diary write seam (upsert/amend/redact), which SET LOCAL loreweave.diary_write
-- and stores ciphertext. A GENERIC chapter-write path (an editor tool handed a diary chapter id, an
-- import into a diary book) would store PLAINTEXT prose into a kind='diary' chapter — defeating
-- encryption-at-rest. This BEFORE trigger REFUSES any write to a diary chapter's prose columns that is
-- NOT flagged as coming from the seam. One enforcement point catches every bypass (app tool, HTTP
-- handler, or future code) — far more robust than guarding N call sites. Novels (kind<>'diary') pass.
CREATE OR REPLACE FUNCTION fn_guard_diary_prose_write() RETURNS TRIGGER AS $guard$
BEGIN
  IF current_setting('loreweave.diary_write', true) IS DISTINCT FROM 'on'
     AND EXISTS (SELECT 1 FROM chapters c JOIN books b ON b.id = c.book_id
                 WHERE c.id = NEW.chapter_id AND b.kind = 'diary') THEN
    RAISE EXCEPTION 'a diary chapter''s body is written only through the diary endpoints (C5 encryption-at-rest); a generic write would store plaintext'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $guard$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_guard_diary_prose_drafts ON chapter_drafts;
CREATE TRIGGER trg_guard_diary_prose_drafts BEFORE INSERT OR UPDATE OF body ON chapter_drafts
  FOR EACH ROW EXECUTE FUNCTION fn_guard_diary_prose_write();
DROP TRIGGER IF EXISTS trg_guard_diary_prose_raw ON chapter_raw_objects;
CREATE TRIGGER trg_guard_diary_prose_raw BEFORE INSERT OR UPDATE OF body_text ON chapter_raw_objects
  FOR EACH ROW EXECUTE FUNCTION fn_guard_diary_prose_write();
DROP TRIGGER IF EXISTS trg_guard_diary_prose_rev ON chapter_revisions;
CREATE TRIGGER trg_guard_diary_prose_rev BEFORE INSERT OR UPDATE OF body ON chapter_revisions
  FOR EACH ROW EXECUTE FUNCTION fn_guard_diary_prose_write();

-- ONE primary entry per day, per book. The predicate must repeat EXACTLY in any
-- ON CONFLICT that targets it (the repo's partial-index/ON-CONFLICT lesson), and it must
-- exempt trashed rows or a deleted entry would block ever writing that day again (the
-- partial-unique-must-exempt-tombstones lesson).
CREATE UNIQUE INDEX IF NOT EXISTS uq_chapters_primary_entry_per_day
  ON chapters(book_id, entry_date)
  WHERE journal_kind = 'primary' AND lifecycle_state = 'active';

-- The diary timeline read: "my entries, newest first".
CREATE INDEX IF NOT EXISTS idx_chapters_entry_date
  ON chapters(book_id, entry_date DESC) WHERE entry_date IS NOT NULL;

-- ── WS-1.2 · EGRESS GUARD #1: a diary can never be shared (spec 09, D16) ──
--
-- There are already TWO grant paths (invite-by-email and grant-by-user-id), and a third
-- will appear. Guarding the handlers means the guard drifts the moment someone adds path
-- four — and the failure is silent: a collaborator simply gains read access to a private
-- diary, which looks exactly like a normal, intentional share.
--
-- So the lock lives in the DATABASE, where it covers every path that exists and every path
-- anyone writes later. A diary is single-owner by construction.
CREATE OR REPLACE FUNCTION fn_no_collaborators_on_diary()
RETURNS TRIGGER AS $fn$
DECLARE
  _kind TEXT;
BEGIN
  SELECT kind INTO _kind FROM books WHERE id = NEW.book_id;
  IF _kind = 'diary' THEN
    RAISE EXCEPTION
      'a diary cannot be shared: it is private to its owner by construction. '
      '(book %, attempted collaborator %)', NEW.book_id, NEW.user_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
  CREATE TRIGGER trg_no_collaborators_on_diary
    BEFORE INSERT OR UPDATE ON book_collaborators
    FOR EACH ROW
    EXECUTE FUNCTION fn_no_collaborators_on_diary();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION fn_outbox_notify()
RETURNS TRIGGER AS $fn$
BEGIN
  PERFORM pg_notify('outbox_events', NEW.id::text);
  RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
  CREATE TRIGGER trg_outbox_notify
    AFTER INSERT ON outbox_events
    FOR EACH ROW
    EXECUTE FUNCTION fn_outbox_notify();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── fn_word_count_for_text: multilingual word-count heuristic (CB3) ──────
-- Ports computeReadingStats' CJK_REGEX heuristic (useBookReaderContent.ts)
-- to Postgres: CJK-detected text (the same Unicode ranges — CJK Unified
-- Ideographs, Hiragana, Katakana, Hangul, fullwidth forms — OR an explicit
-- ja/zh/ko chapter language) counts CHARACTERS excluding whitespace/
-- punctuation; everything else counts WHITESPACE-SPLIT WORDS. POSIX
-- [[:space:][:punct:]] approximates the TS regex's \s\p{P} classes closely
-- enough for a browse-list estimate (not required to be byte-identical to
-- the frontend's own live reading-time estimate). IMMUTABLE + pure (no
-- table access) so it's usable in both the trigger and the batched backfill
-- without duplicating the classification logic in two places.
CREATE OR REPLACE FUNCTION fn_word_count_for_text(_text TEXT, _lang TEXT)
RETURNS INT AS $fn$
DECLARE
  _is_cjk BOOLEAN;
BEGIN
  _text := COALESCE(_text, '');
  _is_cjk := (_text ~ '[　-鿿가-힯＀-￯]') OR (_lang IN ('ja', 'zh', 'ko'));
  IF _is_cjk THEN
    RETURN char_length(regexp_replace(_text, '[[:space:][:punct:]]', '', 'g'));
  ELSIF trim(_text) = '' THEN
    RETURN 0;
  ELSE
    RETURN array_length(regexp_split_to_array(trim(_text), '\s+'), 1);
  END IF;
END;
$fn$ LANGUAGE plpgsql IMMUTABLE;

-- ── fn_recompute_chapter_word_count: recompute parent chapter's word_count ──
-- Mirrors fn_extract_chapter_blocks' "denormalized aggregate kept fresh by a
-- trigger on chapter_blocks" shape. Fires AFTER INSERT/DELETE/UPDATE OF
-- text_content (NOT heading_context-only updates — that column-restriction
-- avoids a redundant recompute on fn_extract_chapter_blocks' 3rd internal
-- statement, which only touches heading_context). Runs once per affected
-- chapter_blocks row; by the time the LAST row of a multi-row statement
-- fires, all of that statement's changes are already visible (Postgres
-- advances the command-id between row-trigger invocations), so the final
-- recompute is correct even though earlier invocations are redundant.
-- AFTER-trigger return value is ignored — RETURN NULL is valid for both
-- row-insert/update and row-delete invocations.
CREATE OR REPLACE FUNCTION fn_recompute_chapter_word_count()
RETURNS TRIGGER AS $fn$
DECLARE
  _chapter_id UUID;
  _agg_text   TEXT;
  _lang       TEXT;
BEGIN
  _chapter_id := COALESCE(NEW.chapter_id, OLD.chapter_id);

  SELECT string_agg(text_content, ' ' ORDER BY block_index) INTO _agg_text
  FROM chapter_blocks WHERE chapter_id = _chapter_id;

  SELECT original_language INTO _lang FROM chapters WHERE id = _chapter_id;

  -- A missing chapter row (e.g. mid-cascade-delete: chapters row already
  -- gone, chapter_blocks rows cascading after it) makes this UPDATE match
  -- zero rows — harmless no-op, not an error.
  UPDATE chapters SET word_count = fn_word_count_for_text(_agg_text, _lang)
  WHERE id = _chapter_id;

  RETURN NULL;
END;
$fn$ LANGUAGE plpgsql;

DO $$ BEGIN
  CREATE TRIGGER trg_recompute_chapter_word_count
    AFTER INSERT OR DELETE OR UPDATE OF text_content ON chapter_blocks
    FOR EACH ROW
    EXECUTE FUNCTION fn_recompute_chapter_word_count();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
`
