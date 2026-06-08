package migrate

import (
	"context"
	"fmt"

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

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}

	// PG18: add virtual generated column for block count (idempotent)
	_, _ = pool.Exec(ctx, `
		DO $$ BEGIN
			ALTER TABLE chapter_drafts ADD COLUMN block_count INT
				GENERATED ALWAYS AS (jsonb_array_length(body -> 'content')) VIRTUAL;
		EXCEPTION WHEN duplicate_column THEN NULL;
		END $$;
	`)

	// Raw search Phase 1 (lexical leg): pg_trgm + trigram index, best-effort &
	// separate from schemaSQL so a privilege failure can't abort schema init or
	// block startup (review-impl MED-1). Search degrades to 500-on-use if absent.
	_, _ = pool.Exec(ctx, rawSearchExtensionSQL)
	_, _ = pool.Exec(ctx, rawSearchIndexSQL)

	// Canon Model CM1: one-time editorial backfill (marker-gated; idempotent).
	if _, err := pool.Exec(ctx, backfillSQL); err != nil {
		return fmt.Errorf("migrate canon backfill: %w", err)
	}

	// D1-03: trigger function to extract chapter_blocks from Tiptap JSONB
	if _, err := pool.Exec(ctx, triggerSQL); err != nil {
		return fmt.Errorf("migrate trigger: %w", err)
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
`
