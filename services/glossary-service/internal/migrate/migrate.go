package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/domain"
)

const schemaSQL = `
-- Kind catalogue (seeded on startup, read-only in MVP)
CREATE TABLE IF NOT EXISTS entity_kinds (
  kind_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  code        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  description TEXT,
  icon        TEXT NOT NULL DEFAULT '',
  color       TEXT NOT NULL DEFAULT '#6366f1',
  is_default  BOOLEAN NOT NULL DEFAULT true,
  is_hidden   BOOLEAN NOT NULL DEFAULT false,
  sort_order  INT NOT NULL DEFAULT 0,
  genre_tags  TEXT[] NOT NULL DEFAULT '{universal}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attribute_definitions (
  attr_def_id UUID PRIMARY KEY DEFAULT uuidv7(),
  kind_id     UUID NOT NULL REFERENCES entity_kinds(kind_id) ON DELETE CASCADE,
  code        TEXT NOT NULL,
  name        TEXT NOT NULL,
  description TEXT,
  field_type  TEXT NOT NULL DEFAULT 'text',
  is_required BOOLEAN NOT NULL DEFAULT false,
  is_system   BOOLEAN NOT NULL DEFAULT false,
  sort_order  INT NOT NULL DEFAULT 0,
  options     TEXT[],
  UNIQUE(kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_attr_def_kind ON attribute_definitions(kind_id);
-- Migration: add is_system column if missing (idempotent)
ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT false;
-- Mark seeded attributes on system kinds as is_system=true
UPDATE attribute_definitions ad SET is_system = true
FROM entity_kinds ek WHERE ek.kind_id = ad.kind_id AND ek.is_default = true AND ad.is_system = false;

-- Glossary entities (book-level)
CREATE TABLE IF NOT EXISTS glossary_entities (
  entity_id  UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id    UUID NOT NULL,
  kind_id    UUID NOT NULL REFERENCES entity_kinds(kind_id),
  status     TEXT NOT NULL DEFAULT 'draft',
  tags       TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ge_book        ON glossary_entities(book_id);
CREATE INDEX IF NOT EXISTS idx_ge_book_kind   ON glossary_entities(book_id, kind_id);
CREATE INDEX IF NOT EXISTS idx_ge_book_status ON glossary_entities(book_id, status);
CREATE INDEX IF NOT EXISTS idx_ge_book_updated ON glossary_entities(book_id, updated_at DESC);

-- Chapter M:N links
CREATE TABLE IF NOT EXISTS chapter_entity_links (
  link_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id     UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  chapter_id    UUID NOT NULL,
  chapter_title TEXT,
  chapter_index INT,
  relevance     TEXT NOT NULL DEFAULT 'appears',
  note          TEXT,
  added_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(entity_id, chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_cel_entity  ON chapter_entity_links(entity_id);
CREATE INDEX IF NOT EXISTS idx_cel_chapter ON chapter_entity_links(chapter_id);

-- Attribute values (one row per entity per attribute definition)
CREATE TABLE IF NOT EXISTS entity_attribute_values (
  attr_value_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id         UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  attr_def_id       UUID NOT NULL REFERENCES attribute_definitions(attr_def_id),
  original_language TEXT NOT NULL DEFAULT 'zh',
  original_value    TEXT NOT NULL DEFAULT '',
  UNIQUE(entity_id, attr_def_id)
);
CREATE INDEX IF NOT EXISTS idx_eav_entity ON entity_attribute_values(entity_id);

-- Per-attribute translations
CREATE TABLE IF NOT EXISTS attribute_translations (
  translation_id UUID PRIMARY KEY DEFAULT uuidv7(),
  attr_value_id  UUID NOT NULL REFERENCES entity_attribute_values(attr_value_id) ON DELETE CASCADE,
  language_code  TEXT NOT NULL,
  value          TEXT NOT NULL DEFAULT '',
  confidence     TEXT NOT NULL DEFAULT 'draft',
  translator     TEXT,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(attr_value_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_at_attr_value ON attribute_translations(attr_value_id);

-- Evidence (source quotes / summaries)
CREATE TABLE IF NOT EXISTS evidences (
  evidence_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  attr_value_id     UUID NOT NULL REFERENCES entity_attribute_values(attr_value_id) ON DELETE CASCADE,
  chapter_id        UUID,
  chapter_title     TEXT,
  block_or_line     TEXT NOT NULL DEFAULT '',
  evidence_type     TEXT NOT NULL DEFAULT 'quote',
  original_language TEXT NOT NULL DEFAULT 'zh',
  original_text     TEXT NOT NULL DEFAULT '',
  note              TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ev_attr_value ON evidences(attr_value_id);
CREATE INDEX IF NOT EXISTS idx_ev_chapter    ON evidences(chapter_id);

-- Evidence translations
CREATE TABLE IF NOT EXISTS evidence_translations (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  evidence_id   UUID NOT NULL REFERENCES evidences(evidence_id) ON DELETE CASCADE,
  language_code TEXT NOT NULL,
  value         TEXT NOT NULL DEFAULT '',
  confidence    TEXT NOT NULL DEFAULT 'draft',
  UNIQUE(evidence_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_evtr_evidence ON evidence_translations(evidence_id);
`

func Up(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		return fmt.Errorf("migrate: %w", err)
	}
	return nil
}

// snapshotSQL adds the entity_snapshot column, the recalculation function,
// five trigger functions, and the triggers themselves.
// All statements are idempotent (IF NOT EXISTS / CREATE OR REPLACE / DROP IF EXISTS).
const snapshotSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS entity_snapshot JSONB;

-- ── Core recalculation function ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION recalculate_entity_snapshot(p_entity_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_snapshot JSONB;
BEGIN
  SELECT jsonb_build_object(
    'schema_version', '1.0',
    'entity_id',      e.entity_id::text,
    'book_id',        e.book_id::text,
    'kind', jsonb_build_object(
      'source', 'system',
      'ref_id', k.kind_id::text,
      'code',   k.code,
      'name',   k.name,
      'icon',   k.icon,
      'color',  k.color
    ),
    'status', e.status,
    'alive',  e.alive,
    'tags',   to_jsonb(e.tags),
    'attributes', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'attr_def_source',   'system',
          'attr_def_ref_id',   ad.attr_def_id::text,
          'attr_value_id',     av.attr_value_id::text,
          'code',              ad.code,
          'name',              ad.name,
          'field_type',        ad.field_type,
          'is_required',       ad.is_required,
          'is_system',         ad.is_system,
          'sort_order',        ad.sort_order,
          'original_language', av.original_language,
          'original_value',    COALESCE(av.original_value, ''),
          'translations', COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'translation_id', t.translation_id::text,
                'language_code',  t.language_code,
                'value',          t.value,
                'confidence',     t.confidence
              ) ORDER BY t.language_code
            )
            FROM attribute_translations t
            WHERE t.attr_value_id = av.attr_value_id
          ), '[]'::jsonb),
          'evidences', COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'evidence_id',       ev.evidence_id::text,
                'evidence_type',     ev.evidence_type,
                'original_language', ev.original_language,
                'original_text',     ev.original_text,
                'chapter_id',        ev.chapter_id::text,
                'chapter_title',     ev.chapter_title,
                'block_or_line',     ev.block_or_line,
                'note',              ev.note
              ) ORDER BY ev.created_at
            )
            FROM evidences ev
            WHERE ev.attr_value_id = av.attr_value_id
          ), '[]'::jsonb)
        ) ORDER BY ad.sort_order
      )
      FROM entity_attribute_values av
      JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
      WHERE av.entity_id = p_entity_id
    ), '[]'::jsonb),
    'chapter_links', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'link_id',       cl.link_id::text,
          'chapter_id',    cl.chapter_id::text,
          'chapter_title', cl.chapter_title,
          'chapter_index', cl.chapter_index,
          'relevance',     cl.relevance,
          'note',          cl.note
        ) ORDER BY cl.chapter_index NULLS LAST, cl.added_at
      )
      FROM chapter_entity_links cl
      WHERE cl.entity_id = p_entity_id
    ), '[]'::jsonb),
    'updated_at',  e.updated_at,
    'snapshot_at', now()
  )
  INTO v_snapshot
  FROM glossary_entities e
  JOIN entity_kinds k ON k.kind_id = e.kind_id
  WHERE e.entity_id = p_entity_id;

  IF v_snapshot IS NULL THEN
    RETURN;
  END IF;

  UPDATE glossary_entities
  SET entity_snapshot = v_snapshot
  WHERE entity_id = p_entity_id
    AND entity_snapshot IS DISTINCT FROM v_snapshot;
END;
$$;

-- ── Trigger functions ─────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION trig_fn_eav_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM recalculate_entity_snapshot(
    CASE WHEN TG_OP = 'DELETE' THEN OLD.entity_id ELSE NEW.entity_id END
  );
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION trig_fn_trans_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_entity_id UUID;
BEGIN
  SELECT entity_id INTO v_entity_id
  FROM entity_attribute_values
  WHERE attr_value_id = CASE WHEN TG_OP = 'DELETE'
                             THEN OLD.attr_value_id
                             ELSE NEW.attr_value_id END;
  IF v_entity_id IS NOT NULL THEN
    PERFORM recalculate_entity_snapshot(v_entity_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION trig_fn_evid_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_entity_id UUID;
BEGIN
  SELECT entity_id INTO v_entity_id
  FROM entity_attribute_values
  WHERE attr_value_id = CASE WHEN TG_OP = 'DELETE'
                             THEN OLD.attr_value_id
                             ELSE NEW.attr_value_id END;
  IF v_entity_id IS NOT NULL THEN
    PERFORM recalculate_entity_snapshot(v_entity_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION trig_fn_cel_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM recalculate_entity_snapshot(
    CASE WHEN TG_OP = 'DELETE' THEN OLD.entity_id ELSE NEW.entity_id END
  );
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION trig_fn_entity_self_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status     IS DISTINCT FROM OLD.status
  OR NEW.alive      IS DISTINCT FROM OLD.alive
  OR NEW.tags       IS DISTINCT FROM OLD.tags
  OR NEW.kind_id    IS DISTINCT FROM OLD.kind_id
  OR NEW.updated_at IS DISTINCT FROM OLD.updated_at
  THEN
    PERFORM recalculate_entity_snapshot(NEW.entity_id);
  END IF;
  RETURN NULL;
END;
$$;

-- ── Triggers (drop-and-recreate for idempotency) ──────────────────────────────

DROP TRIGGER IF EXISTS trig_eav_snapshot          ON entity_attribute_values;
DROP TRIGGER IF EXISTS trig_trans_snapshot         ON attribute_translations;
DROP TRIGGER IF EXISTS trig_evid_snapshot          ON evidences;
DROP TRIGGER IF EXISTS trig_cel_snapshot           ON chapter_entity_links;
DROP TRIGGER IF EXISTS trig_entity_self_snapshot   ON glossary_entities;

CREATE TRIGGER trig_eav_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON entity_attribute_values
  FOR EACH ROW EXECUTE FUNCTION trig_fn_eav_snapshot();

CREATE TRIGGER trig_trans_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON attribute_translations
  FOR EACH ROW EXECUTE FUNCTION trig_fn_trans_snapshot();

CREATE TRIGGER trig_evid_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON evidences
  FOR EACH ROW EXECUTE FUNCTION trig_fn_evid_snapshot();

CREATE TRIGGER trig_cel_snapshot
  AFTER INSERT OR UPDATE OR DELETE ON chapter_entity_links
  FOR EACH ROW EXECUTE FUNCTION trig_fn_cel_snapshot();

CREATE TRIGGER trig_entity_self_snapshot
  AFTER UPDATE ON glossary_entities
  FOR EACH ROW EXECUTE FUNCTION trig_fn_entity_self_snapshot();
`

// UpSnapshot adds the entity_snapshot column, the PL/pgSQL recalculation
// function, and all five triggers. Safe to call on every startup.
func UpSnapshot(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, snapshotSQL); err != nil {
		return fmt.Errorf("migrate snapshot: %w", err)
	}
	return nil
}

// BackfillSnapshots populates entity_snapshot for any entity where it is NULL.
// Idempotent: skips entities that already have a snapshot.
func BackfillSnapshots(ctx context.Context, pool *pgxpool.Pool) error {
	rows, err := pool.Query(ctx,
		`SELECT entity_id FROM glossary_entities WHERE entity_snapshot IS NULL`)
	if err != nil {
		return fmt.Errorf("backfill list: %w", err)
	}
	defer rows.Close()

	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return fmt.Errorf("backfill scan: %w", err)
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	for _, id := range ids {
		if _, err := pool.Exec(ctx,
			`SELECT recalculate_entity_snapshot($1)`, id); err != nil {
			return fmt.Errorf("backfill entity %s: %w", id, err)
		}
	}
	return nil
}

// softDeleteSQL adds deleted_at and permanently_deleted_at columns plus
// partial indexes for the live-query and recycle-bin query paths.
// All statements are idempotent (IF NOT EXISTS).
const softDeleteSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS deleted_at             TIMESTAMPTZ DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS permanently_deleted_at TIMESTAMPTZ DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_kind
  ON glossary_entities(book_id, kind_id)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_status
  ON glossary_entities(book_id, status)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_live_book_updated
  ON glossary_entities(book_id, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_ge_trash_book
  ON glossary_entities(book_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;
`

// UpSoftDelete adds soft-delete columns and supporting partial indexes.
// Safe to call on every startup (idempotent).
func UpSoftDelete(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, softDeleteSQL); err != nil {
		return fmt.Errorf("migrate soft-delete: %w", err)
	}
	return nil
}

// Seed inserts the 12 default entity kinds and their attribute definitions if the
// entity_kinds table is empty. Safe to call on every startup (idempotent).
func Seed(ctx context.Context, pool *pgxpool.Pool) error {
	var count int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM entity_kinds`).Scan(&count); err != nil {
		return fmt.Errorf("seed check: %w", err)
	}
	if count > 0 {
		return nil // already seeded
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("seed tx: %w", err)
	}
	defer tx.Rollback(ctx)

	for _, k := range domain.DefaultKinds {
		var kindID string
		err := tx.QueryRow(ctx, `
			INSERT INTO entity_kinds(code, name, icon, color, is_default, is_hidden, sort_order, genre_tags)
			VALUES ($1,$2,$3,$4,true,false,$5,$6)
			RETURNING kind_id`,
			k.Code, k.Name, k.Icon, k.Color, k.SortOrder, k.GenreTags,
		).Scan(&kindID)
		if err != nil {
			return fmt.Errorf("seed kind %s: %w", k.Code, err)
		}

		for _, a := range k.Attrs {
			if _, err := tx.Exec(ctx, `
				INSERT INTO attribute_definitions(kind_id, code, name, field_type, is_required, is_system, sort_order)
				VALUES ($1,$2,$3,$4,$5,true,$6)`,
				kindID, a.Code, a.Name, a.FieldType, a.IsRequired, a.SortOrder,
			); err != nil {
				return fmt.Errorf("seed attr %s.%s: %w", k.Code, a.Code, err)
			}
		}
	}

	return tx.Commit(ctx)
}

// ── genre groups ─────────────────────────────────────────────────────────────

const genreGroupsSQL = `
CREATE TABLE IF NOT EXISTS genre_groups (
    id          UUID PRIMARY KEY DEFAULT uuidv7(),
    book_id     UUID NOT NULL,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#8b5cf6',
    description TEXT NOT NULL DEFAULT '',
    sort_order  INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(book_id, name)
);
ALTER TABLE genre_groups ALTER COLUMN id SET DEFAULT uuidv7();
CREATE INDEX IF NOT EXISTS idx_genre_groups_book ON genre_groups(book_id);
ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS genre_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS auto_fill_prompt TEXT;
ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS translation_hint TEXT;
`

func UpGenreGroups(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, genreGroupsSQL); err != nil {
		return fmt.Errorf("migrate genre_groups: %w", err)
	}
	return nil
}

// ── wiki articles + revisions ───────────────────────────────────────────────

const wikiSQL = `
CREATE TABLE IF NOT EXISTS wiki_articles (
  article_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id        UUID NOT NULL UNIQUE REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  book_id          UUID NOT NULL,
  body_json        JSONB NOT NULL DEFAULT '{}',
  status           TEXT NOT NULL DEFAULT 'draft',
  template_code    TEXT,
  spoiler_chapters UUID[] NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wa_book   ON wiki_articles(book_id);
CREATE INDEX IF NOT EXISTS idx_wa_entity ON wiki_articles(entity_id);
CREATE INDEX IF NOT EXISTS idx_wa_status ON wiki_articles(book_id, status);

CREATE TABLE IF NOT EXISTS wiki_revisions (
  revision_id  UUID PRIMARY KEY DEFAULT uuidv7(),
  article_id   UUID NOT NULL REFERENCES wiki_articles(article_id) ON DELETE CASCADE,
  version      INT NOT NULL,
  body_json    JSONB NOT NULL,
  author_id    UUID NOT NULL,
  author_type  TEXT NOT NULL DEFAULT 'owner',
  summary      TEXT NOT NULL DEFAULT '',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(article_id, version)
);
CREATE INDEX IF NOT EXISTS idx_wr_article ON wiki_revisions(article_id);
`

func UpWiki(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, wikiSQL); err != nil {
		return fmt.Errorf("migrate wiki: %w", err)
	}
	return nil
}

// ── wiki suggestions ────────────────────────────────────────────────────────

const wikiSuggestionsSQL = `
CREATE TABLE IF NOT EXISTS wiki_suggestions (
  suggestion_id UUID PRIMARY KEY DEFAULT uuidv7(),
  article_id    UUID NOT NULL REFERENCES wiki_articles(article_id) ON DELETE CASCADE,
  user_id       UUID NOT NULL,
  diff_json     JSONB NOT NULL,
  reason        TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'pending',
  reviewer_note TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ws_article ON wiki_suggestions(article_id);
CREATE INDEX IF NOT EXISTS idx_ws_status  ON wiki_suggestions(article_id, status);
`

func UpWikiSuggestions(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, wikiSuggestionsSQL); err != nil {
		return fmt.Errorf("migrate wiki_suggestions: %w", err)
	}
	return nil
}

// ── glossary extraction pipeline ───────────────────────────────────────────

const extractionSQL = `
-- Narrative-level alive flag on entities.
-- Different from status (active/archived) which is system-level.
-- Used by extraction pipeline to filter known entities context.
-- Default = true (assume alive until user marks otherwise).
ALTER TABLE glossary_entities ADD COLUMN IF NOT EXISTS alive BOOLEAN NOT NULL DEFAULT TRUE;

-- Overwrite audit log for extraction pipeline.
-- Tracks old/new values when "overwrite" action replaces existing attribute values.
-- Separate from evidences table (different semantics: audit trail vs source quotes).
CREATE TABLE IF NOT EXISTS extraction_audit_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id   UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  attr_def_id UUID NOT NULL REFERENCES attribute_definitions(attr_def_id),
  chapter_id  UUID,
  old_value   TEXT,
  new_value   TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eal_entity ON extraction_audit_log(entity_id);
`

// UpExtraction adds the alive column to glossary_entities and creates
// the extraction_audit_log table. Safe to call on every startup (idempotent).
func UpExtraction(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, extractionSQL); err != nil {
		return fmt.Errorf("migrate extraction: %w", err)
	}
	return nil
}

// ── evidence chapter_index ──────────────────────────────────────────────────

const evidenceChapterIndexSQL = `
ALTER TABLE evidences ADD COLUMN IF NOT EXISTS chapter_index INT;
CREATE INDEX IF NOT EXISTS idx_ev_chapter_index ON evidences(chapter_index);
`

// UpEvidenceChapterIndex adds the chapter_index column to evidences.
// Safe to call on every startup (idempotent).
func UpEvidenceChapterIndex(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, evidenceChapterIndexSQL); err != nil {
		return fmt.Errorf("migrate evidence_chapter_index: %w", err)
	}
	return nil
}

// ── knowledge-service memory support (Track 1 K2a) ─────────────────────────
//
// Adds columns that the knowledge-service L2 glossary-fallback depends on:
//
//   - short_description TEXT           — user-editable ~150-char summary for
//                                        compact chat context injection.
//   - is_pinned_for_context BOOLEAN    — user-marked "always include" flag.
//   - cached_name TEXT                 — denormalised copy of the entity's
//                                        'name'/'term' attribute, maintained
//                                        by the existing snapshot trigger.
//   - cached_aliases TEXT[]            — denormalised copy of the entity's
//                                        'aliases' attribute (JSON array in
//                                        EAV) as a native Postgres text[].
//   - search_vector tsvector GENERATED — STORED tsvector built from
//                                        cached_name + cached_aliases +
//                                        short_description. Used by the
//                                        /internal/glossary/select-for-context
//                                        tiered selector in K2b.
//
// Source of truth for names/aliases remains entity_attribute_values (EAV);
// cached_name / cached_aliases are a read-optimisation populated whenever
// recalculate_entity_snapshot() runs. The existing triggers on EAV changes
// (trig_eav_snapshot, etc.) pick up the new behaviour for free because the
// recalculation function itself is updated in place via CREATE OR REPLACE.
//
// Uses 'simple' text search config for maximum language coverage (CJK works
// via per-codepoint tokenisation).

const knowledgeMemorySQL = `
-- 1. New columns on glossary_entities
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS short_description       TEXT,
  ADD COLUMN IF NOT EXISTS is_pinned_for_context   BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS cached_name             TEXT,
  ADD COLUMN IF NOT EXISTS cached_aliases          TEXT[] NOT NULL DEFAULT '{}';

-- 2. search_vector is a plain tsvector column (not GENERATED) because
--    Postgres 18 considers the expression
--      to_tsvector('simple', coalesce(cached_name,'') || ...
--                                            array_to_string(cached_aliases,' ')...)
--    non-immutable (array_to_string over a nullable text[] trips the check).
--    It is maintained alongside cached_name / cached_aliases in the
--    recalculate_entity_snapshot() function below — single write path, no
--    additional triggers needed.
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS search_vector tsvector;

CREATE INDEX IF NOT EXISTS idx_ge_search_vector
  ON glossary_entities USING gin(search_vector);

CREATE INDEX IF NOT EXISTS idx_ge_pinned_book
  ON glossary_entities(book_id)
  WHERE is_pinned_for_context AND deleted_at IS NULL;

-- 3. Replace trig_fn_entity_self_snapshot so it ALSO fires when
--    short_description changes. Without this, direct SQL updates to
--    short_description (migrations, backfills, tests) would leave
--    search_vector stale. The normal API PATCH path always bumps
--    updated_at so the existing watch list already covered it, but we
--    defend against non-API writes too.
CREATE OR REPLACE FUNCTION trig_fn_entity_self_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status            IS DISTINCT FROM OLD.status
  OR NEW.alive             IS DISTINCT FROM OLD.alive
  OR NEW.tags              IS DISTINCT FROM OLD.tags
  OR NEW.kind_id           IS DISTINCT FROM OLD.kind_id
  OR NEW.updated_at        IS DISTINCT FROM OLD.updated_at
  OR NEW.short_description IS DISTINCT FROM OLD.short_description
  THEN
    PERFORM recalculate_entity_snapshot(NEW.entity_id);
  END IF;
  RETURN NULL;
END;
$$;

-- 4. Extend recalculate_entity_snapshot to ALSO refresh cached_name +
--    cached_aliases + search_vector. We keep the existing snapshot-building
--    logic but add the cache writes at the end in the same function body.
--    CREATE OR REPLACE preserves the trigger bindings.
CREATE OR REPLACE FUNCTION recalculate_entity_snapshot(p_entity_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_snapshot       JSONB;
  v_cached_name    TEXT;
  v_aliases_raw    TEXT;
  v_cached_aliases TEXT[];
BEGIN
  -- ── Original snapshot build (unchanged) ──────────────────────────────────
  SELECT jsonb_build_object(
    'schema_version', '1.0',
    'entity_id',      e.entity_id::text,
    'book_id',        e.book_id::text,
    'kind', jsonb_build_object(
      'source', 'system',
      'ref_id', k.kind_id::text,
      'code',   k.code,
      'name',   k.name,
      'icon',   k.icon,
      'color',  k.color
    ),
    'status', e.status,
    'alive',  e.alive,
    'tags',   to_jsonb(e.tags),
    'attributes', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'attr_def_source',   'system',
          'attr_def_ref_id',   ad.attr_def_id::text,
          'attr_value_id',     av.attr_value_id::text,
          'code',              ad.code,
          'name',              ad.name,
          'field_type',        ad.field_type,
          'is_required',       ad.is_required,
          'is_system',         ad.is_system,
          'sort_order',        ad.sort_order,
          'original_language', av.original_language,
          'original_value',    COALESCE(av.original_value, ''),
          'translations', COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'translation_id', t.translation_id::text,
                'language_code',  t.language_code,
                'value',          t.value,
                'confidence',     t.confidence
              ) ORDER BY t.language_code
            )
            FROM attribute_translations t
            WHERE t.attr_value_id = av.attr_value_id
          ), '[]'::jsonb),
          'evidences', COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'evidence_id',       ev.evidence_id::text,
                'evidence_type',     ev.evidence_type,
                'original_language', ev.original_language,
                'original_text',     ev.original_text,
                'chapter_id',        ev.chapter_id::text,
                'chapter_title',     ev.chapter_title,
                'block_or_line',     ev.block_or_line,
                'note',              ev.note
              ) ORDER BY ev.created_at
            )
            FROM evidences ev
            WHERE ev.attr_value_id = av.attr_value_id
          ), '[]'::jsonb)
        ) ORDER BY ad.sort_order
      )
      FROM entity_attribute_values av
      JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
      WHERE av.entity_id = p_entity_id
    ), '[]'::jsonb),
    'chapter_links', COALESCE((
      SELECT jsonb_agg(
        jsonb_build_object(
          'link_id',       cl.link_id::text,
          'chapter_id',    cl.chapter_id::text,
          'chapter_title', cl.chapter_title,
          'chapter_index', cl.chapter_index,
          'relevance',     cl.relevance,
          'note',          cl.note
        ) ORDER BY cl.chapter_index NULLS LAST, cl.added_at
      )
      FROM chapter_entity_links cl
      WHERE cl.entity_id = p_entity_id
    ), '[]'::jsonb),
    'updated_at',  e.updated_at,
    'snapshot_at', now()
  )
  INTO v_snapshot
  FROM glossary_entities e
  JOIN entity_kinds k ON k.kind_id = e.kind_id
  WHERE e.entity_id = p_entity_id;

  IF v_snapshot IS NULL THEN
    RETURN;
  END IF;

  -- ── NEW: read name + aliases from EAV for the read-cache ────────────────
  SELECT av.original_value INTO v_cached_name
  FROM entity_attribute_values av
  JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
  WHERE av.entity_id = p_entity_id
    AND ad.code IN ('name','term')
  ORDER BY
    CASE ad.code WHEN 'name' THEN 0 WHEN 'term' THEN 1 ELSE 2 END,
    ad.sort_order
  LIMIT 1;

  SELECT av.original_value INTO v_aliases_raw
  FROM entity_attribute_values av
  JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
  WHERE av.entity_id = p_entity_id AND ad.code = 'aliases'
  LIMIT 1;

  -- aliases are stored as a JSON array string in original_value, e.g.
  -- '["alias1","alias2"]'. Parse defensively: empty / non-JSON → '{}'.
  -- Narrowed exception list — we only want to swallow actual JSON-shape
  -- errors; unexpected failures should still propagate.
  BEGIN
    IF v_aliases_raw IS NULL OR v_aliases_raw = '' THEN
      v_cached_aliases := ARRAY[]::TEXT[];
    ELSE
      v_cached_aliases := ARRAY(
        SELECT jsonb_array_elements_text(v_aliases_raw::jsonb)
      );
    END IF;
  EXCEPTION
    WHEN invalid_text_representation
      OR invalid_parameter_value
      OR datatype_mismatch
      OR data_exception THEN
      v_cached_aliases := ARRAY[]::TEXT[];
  END;

  -- ── Single write: snapshot + cache columns + search_vector ──────────────
  -- No WHERE distinctness guard: a short_description change on its own
  -- leaves cache columns identical, so a guarded write would skip the
  -- row and leave search_vector stale. Recursion via the self-trigger
  -- is prevented because the watched fields (status / alive / tags /
  -- kind_id / updated_at / short_description) are not touched here.
  UPDATE glossary_entities
  SET entity_snapshot = v_snapshot,
      cached_name     = v_cached_name,
      cached_aliases  = COALESCE(v_cached_aliases, ARRAY[]::TEXT[]),
      search_vector   = to_tsvector('simple',
        coalesce(v_cached_name, '') || ' ' ||
        coalesce(array_to_string(v_cached_aliases, ' '), '') || ' ' ||
        coalesce(short_description, ''))
  WHERE entity_id = p_entity_id;
END;
$$;
`

// UpKnowledgeMemory applies the K2a (knowledge-service glossary fallback)
// schema additions: short_description, is_pinned_for_context, cached_name,
// cached_aliases, search_vector (generated tsvector). Also replaces
// recalculate_entity_snapshot() so the existing snapshot triggers also
// maintain the cache columns. Idempotent.
func UpKnowledgeMemory(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, knowledgeMemorySQL); err != nil {
		return fmt.Errorf("migrate knowledge-memory: %w", err)
	}
	return nil
}

// ── K3: short_description_auto flag ────────────────────────────────────────
//
// Adds a boolean tracking whether the current short_description was
// produced by the auto-generator (TRUE, default) or set explicitly by a
// user via PATCH (FALSE). The patchEntity handler flips this to FALSE
// on explicit user writes; the patchAttributeValue handler regenerates
// short_description only when this flag is TRUE.
//
// Ideally this would have shipped with K2a, but K2a was already merged
// when the K3 plan formalised the auto vs manual distinction, so it
// ships as a separate step.

const shortDescAutoSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS short_description_auto BOOLEAN NOT NULL DEFAULT true;
`

// UpShortDescAuto adds the short_description_auto flag column. Idempotent.
func UpShortDescAuto(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, shortDescAutoSQL); err != nil {
		return fmt.Errorf("migrate short-desc-auto: %w", err)
	}
	return nil
}

// BackfillShortDescription iterates entities with NULL short_description,
// fetches each one's description attribute value + kind name, runs the
// pure shortdesc generator, and writes the result back. Honours the
// auto flag: rows where short_description_auto = false are skipped
// (user has explicitly set or cleared the field).
//
// CAS-style: the UPDATE includes `WHERE short_description IS NULL` so
// concurrent writes from a user PATCH during backfill don't get
// clobbered.
//
// Idempotent: once all live entities have a short_description, this
// is a no-op.
//
// Intended to run in a background goroutine after the service starts
// listening so health checks don't block on a large catalogue.
func BackfillShortDescription(
	ctx context.Context, pool *pgxpool.Pool,
	generate func(name, description, kindName string) string,
) (processed int, err error) {
	const batchSize = 100
	for {
		rows, qerr := pool.Query(ctx, `
			SELECT e.entity_id,
			       COALESCE(e.cached_name, '') AS name,
			       COALESCE((
			         SELECT av.original_value
			         FROM entity_attribute_values av
			         JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
			         WHERE av.entity_id = e.entity_id AND ad.code = 'description'
			         LIMIT 1
			       ), '') AS description,
			       ek.name AS kind_name
			FROM glossary_entities e
			JOIN entity_kinds ek ON ek.kind_id = e.kind_id
			WHERE e.short_description IS NULL
			  AND e.short_description_auto = true
			  AND e.deleted_at IS NULL
			ORDER BY e.created_at
			LIMIT $1`, batchSize)
		if qerr != nil {
			return processed, fmt.Errorf("backfill-shortdesc list: %w", qerr)
		}

		type task struct {
			ID       string
			Name     string
			Desc     string
			KindName string
		}
		var batch []task
		for rows.Next() {
			var t task
			if err := rows.Scan(&t.ID, &t.Name, &t.Desc, &t.KindName); err != nil {
				rows.Close()
				return processed, fmt.Errorf("backfill-shortdesc scan: %w", err)
			}
			batch = append(batch, t)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return processed, err
		}
		if len(batch) == 0 {
			return processed, nil
		}

		for _, t := range batch {
			sd := generate(t.Name, t.Desc, t.KindName)
			if sd == "" {
				continue
			}
			// CAS: only overwrite if still NULL and still auto.
			tag, uerr := pool.Exec(ctx, `
				UPDATE glossary_entities
				SET short_description = $1
				WHERE entity_id = $2
				  AND short_description IS NULL
				  AND short_description_auto = true`,
				sd, t.ID)
			if uerr != nil {
				return processed, fmt.Errorf("backfill-shortdesc update %s: %w", t.ID, uerr)
			}
			if tag.RowsAffected() == 1 {
				processed++
			}
		}
	}
}

// BackfillKnowledgeMemory populates cached_name / cached_aliases for any
// entity where they are NULL/empty by calling recalculate_entity_snapshot.
// Idempotent: once an entity has a cached_name, subsequent runs are no-ops.
func BackfillKnowledgeMemory(ctx context.Context, pool *pgxpool.Pool) error {
	rows, err := pool.Query(ctx,
		`SELECT entity_id FROM glossary_entities WHERE cached_name IS NULL`)
	if err != nil {
		return fmt.Errorf("backfill-km list: %w", err)
	}
	defer rows.Close()

	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return fmt.Errorf("backfill-km scan: %w", err)
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	for _, id := range ids {
		if _, err := pool.Exec(ctx,
			`SELECT recalculate_entity_snapshot($1)`, id); err != nil {
			return fmt.Errorf("backfill-km entity %s: %w", id, err)
		}
	}
	return nil
}
