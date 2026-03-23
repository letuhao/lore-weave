package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/domain"
)

const schemaSQL = `
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Kind catalogue (seeded on startup, read-only in MVP)
CREATE TABLE IF NOT EXISTS entity_kinds (
  kind_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  attr_def_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind_id     UUID NOT NULL REFERENCES entity_kinds(kind_id) ON DELETE CASCADE,
  code        TEXT NOT NULL,
  name        TEXT NOT NULL,
  description TEXT,
  field_type  TEXT NOT NULL DEFAULT 'text',
  is_required BOOLEAN NOT NULL DEFAULT false,
  sort_order  INT NOT NULL DEFAULT 0,
  options     TEXT[],
  UNIQUE(kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_attr_def_kind ON attribute_definitions(kind_id);

-- Glossary entities (book-level)
CREATE TABLE IF NOT EXISTS glossary_entities (
  entity_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  link_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  attr_value_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id         UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  attr_def_id       UUID NOT NULL REFERENCES attribute_definitions(attr_def_id),
  original_language TEXT NOT NULL DEFAULT 'zh',
  original_value    TEXT NOT NULL DEFAULT '',
  UNIQUE(entity_id, attr_def_id)
);
CREATE INDEX IF NOT EXISTS idx_eav_entity ON entity_attribute_values(entity_id);

-- Per-attribute translations
CREATE TABLE IF NOT EXISTS attribute_translations (
  translation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  evidence_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
				INSERT INTO attribute_definitions(kind_id, code, name, field_type, is_required, sort_order)
				VALUES ($1,$2,$3,$4,$5,$6)`,
				kindID, a.Code, a.Name, a.FieldType, a.IsRequired, a.SortOrder,
			); err != nil {
				return fmt.Errorf("seed attr %s.%s: %w", k.Code, a.Code, err)
			}
		}
	}

	return tx.Commit(ctx)
}
