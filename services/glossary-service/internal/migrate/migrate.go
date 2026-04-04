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
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id     UUID NOT NULL,
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#8b5cf6',
    description TEXT NOT NULL DEFAULT '',
    sort_order  INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(book_id, name)
);
CREATE INDEX IF NOT EXISTS idx_genre_groups_book ON genre_groups(book_id);
ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS genre_tags TEXT[] NOT NULL DEFAULT '{}';
`

func UpGenreGroups(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, genreGroupsSQL); err != nil {
		return fmt.Errorf("migrate genre_groups: %w", err)
	}
	return nil
}
