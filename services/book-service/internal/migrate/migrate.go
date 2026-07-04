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
  sort_order      INT  NOT NULL,
  path            TEXT NOT NULL,
  leaf_text       TEXT NOT NULL,
  content_hash    TEXT NOT NULL,
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

	// D1-03: trigger function to extract chapter_blocks from Tiptap JSONB
	if err := execGuarded(ctx, pool, "trigger", triggerSQL); err != nil {
		return err
	}

	// CB3: batched, marker-gated word_count backfill for pre-existing chapters.
	// Best-effort — a failure here must NEVER block book-service startup (word_count
	// simply stays 0 for un-backfilled rows, a graceful degrade, not a hard
	// requirement); the marker stays unset on failure so the next startup retries.
	if err := backfillWordCounts(ctx, pool); err != nil {
		slog.Error("book-service: word_count backfill failed; will retry on next startup", "err", err)
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

const triggerSQL = `
-- ── fn_extract_chapter_blocks: UPSERT blocks from Tiptap JSON ────────────
CREATE OR REPLACE FUNCTION fn_extract_chapter_blocks()
RETURNS TRIGGER AS $fn$
DECLARE
  _max_idx INT;
BEGIN
  -- 1. UPSERT blocks from JSON_TABLE reading _text snapshots
  INSERT INTO chapter_blocks (chapter_id, block_index, block_type, text_content, content_hash, attrs)
  SELECT
    NEW.chapter_id,
    (jt.block_index - 1),
    jt.block_type,
    COALESCE(jt.text_content, ''),
    encode(sha256(COALESCE(jt.text_content, '')::bytea), 'hex'),
    jt.block_attrs
  FROM JSON_TABLE(
    NEW.body, '$.content[*]'
    COLUMNS (
      block_index FOR ORDINALITY,
      block_type  TEXT  PATH '$.type',
      text_content TEXT PATH '$._text',
      block_attrs JSONB PATH '$.attrs'
    )
  ) AS jt
  WHERE jt.block_type IS NOT NULL
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
  FROM JSON_TABLE(NEW.body, '$.content[*]' COLUMNS (i FOR ORDINALITY)) AS jt;

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
