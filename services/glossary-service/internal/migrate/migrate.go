package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/domain"
)

const schemaSQL = `
-- ── SS-4 T1 rename: entity_kinds → system_kinds (explicit system tier) ────────
-- The legacy kind catalogue was named entity_kinds with a global UNIQUE(code),
-- user-mutable via /v1/glossary/kinds* — a multi-tenancy defect (one user's edit
-- changed the kind for everyone). SS-4 makes the system tier an explicit,
-- admin/seed-only table; T2 user_kinds + T3 book_kinds carry user/book scope.
-- A RENAME preserves every FK (glossary_entities.kind_id, the *_attributes FK,
-- entity_kind_aliases, merge_candidates) automatically — no data rewrite. IF
-- EXISTS makes it idempotent + a no-op on a fresh DB (where the CREATE below
-- builds system_kinds directly). MUST run BEFORE the CREATE so an existing DB's
-- data-bearing table is renamed in place rather than shadowed by a new empty one.
ALTER TABLE IF EXISTS entity_kinds         RENAME TO system_kinds;
ALTER TABLE IF EXISTS attribute_definitions RENAME TO system_kind_attributes;

-- Kind catalogue (seeded on startup, read-only in MVP)
CREATE TABLE IF NOT EXISTS system_kinds (
  kind_id     UUID PRIMARY KEY DEFAULT uuidv7(),
  code        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  description TEXT,
  icon        TEXT NOT NULL DEFAULT '',
  color       TEXT NOT NULL DEFAULT '#6366f1',
  is_default  BOOLEAN NOT NULL DEFAULT true,
  is_hidden   BOOLEAN NOT NULL DEFAULT false,
  sort_order  INT NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- genre_tags (the legacy flat-genre TEXT[]) is FULLY RETIRED: not created here, not
-- re-added, and not written by any seed. Genre membership now lives in
-- system_kind_genres (SeedGenreKindAttr derives it from DefaultKinds in Go).
-- UpGlossaryDropLegacyG4 still DROPs the column IF EXISTS as a ONE-TIME cleanup for
-- DBs migrated before this retire. We must NOT re-add it each run: the old
-- ADD-then-DROP cycle on this PERSISTENT table leaked a pg_attribute slot per migration
-- run (Postgres never reclaims dropped-column slots without a table rewrite), which
-- exhausted system_kinds at the 1600-column ceiling and is a restart time-bomb on any
-- long-lived DB. See D-GKA-SYSTEM-KINDS-SLOTS.

CREATE TABLE IF NOT EXISTS system_kind_attributes (
  attr_def_id UUID PRIMARY KEY DEFAULT uuidv7(),
  kind_id     UUID NOT NULL REFERENCES system_kinds(kind_id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS idx_attr_def_kind ON system_kind_attributes(kind_id);
-- Migration: add is_system column if missing (idempotent)
ALTER TABLE system_kind_attributes ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT false;
-- Mark seeded attributes on system kinds as is_system=true
UPDATE system_kind_attributes ad SET is_system = true
FROM system_kinds ek WHERE ek.kind_id = ad.kind_id AND ek.is_default = true AND ad.is_system = false;

-- Glossary entities (book-level)
CREATE TABLE IF NOT EXISTS glossary_entities (
  entity_id  UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id    UUID NOT NULL,
  kind_id    UUID NOT NULL REFERENCES system_kinds(kind_id),
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
  attr_def_id       UUID NOT NULL REFERENCES system_kind_attributes(attr_def_id),
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

-- ── Kind aliases + unknown bucket (kind-resolution epic) ─────────────────────
-- entity_kind_aliases lets a code that ISN'T a kind resolve to one (e.g. a
-- supplement layer's "faction" → "organization"), as DATA not hardcode. The
-- "merge alias" review action inserts a row here. alias_code is globally UNIQUE
-- (a code can't alias two kinds); a code that is also a real kind.code is never
-- inserted (the resolver checks kinds first).
CREATE TABLE IF NOT EXISTS entity_kind_aliases (
  alias_id    UUID PRIMARY KEY DEFAULT uuidv7(),
  alias_code  TEXT NOT NULL UNIQUE,
  kind_id     UUID NOT NULL REFERENCES system_kinds(kind_id) ON DELETE CASCADE,
  created_by  UUID,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kind_aliases_kind ON entity_kind_aliases(kind_id);

-- An entity whose incoming kind_code resolved to nothing is parked under the
-- 'unknown' kind (never dropped) and remembers the code it arrived as, so the
-- review GUI can offer "alias <code> → <kind>" or "create kind from <code>".
ALTER TABLE glossary_entities ADD COLUMN IF NOT EXISTS source_kind_code TEXT;

-- The 'unknown' system kind (the review bucket). Hidden from the normal kind
-- picker; an entity here is awaiting kind triage. Idempotent (ON CONFLICT) so it
-- exists on already-seeded DBs too (Seed() only runs on an empty catalogue).
INSERT INTO system_kinds (code, name, icon, color, is_default, is_hidden, sort_order)
VALUES ('unknown', 'Unknown', '❓', '#94a3b8', true, true, 9999)
ON CONFLICT (code) DO NOTHING;

-- The 'unknown' kind needs at least a name attribute so a parked entity is nameable
-- (createExtractedEntity only writes the name when the kind has a 'name' attr_def),
-- + aliases/description so dedup + the review GUI work. Idempotent.
INSERT INTO system_kind_attributes (kind_id, code, name, field_type, is_required, is_system, sort_order)
SELECT ek.kind_id, v.code, v.name, v.field_type, v.is_required, true, v.sort_order
FROM system_kinds ek
CROSS JOIN (VALUES
  ('name', 'Name', 'text', true, 1),
  ('aliases', 'Aliases', 'tags', false, 2),
  ('description', 'Description', 'textarea', false, 3)
) AS v(code, name, field_type, is_required, sort_order)
WHERE ek.code = 'unknown'
ON CONFLICT (kind_id, code) DO NOTHING;
`

// seedKindAliasesSQL — the DEFAULT kind aliases. Stable, unambiguous synonyms so a
// supplement/extraction layer's vocabulary resolves without manual triage: 'faction'
// is glossary's 'organization'; 'generic' (the freeform fallback) is 'terminology'
// (the concept/entry kind). This is what lets lore-enrichment send its RAW kind and
// drop its hardcoded translation map (kind-alias epic E2). MUST run AFTER Seed() —
// it JOINs the target kinds, which Seed() creates (schemaSQL/Up runs BEFORE Seed, so
// putting this in schemaSQL would no-op on a fresh DB). Idempotent; only inserts when
// the target kind exists; never clobbers an author-created alias (ON CONFLICT).
const seedKindAliasesSQL = `
INSERT INTO entity_kind_aliases (alias_code, kind_id)
SELECT v.alias_code, ek.kind_id
FROM (VALUES ('faction', 'organization'), ('generic', 'terminology')) AS v(alias_code, target_code)
JOIN system_kinds ek ON ek.code = v.target_code
ON CONFLICT (alias_code) DO NOTHING;
`

// SeedKindAliases inserts the default kind aliases. Idempotent; call AFTER Seed()
// (the target kinds must exist). Safe on every startup.
func SeedKindAliases(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, seedKindAliasesSQL); err != nil {
		return fmt.Errorf("seed kind aliases: %w", err)
	}
	return nil
}

// seedWorkKindsSQL — WS-1.5 (spec 05 §Q2). The System-tier WORK ontology: the 7 kinds the
// Work Assistant captures from a diary — colleague · project · meeting · decision · task ·
// jargon · org. (Spec §Q2 names the terminology kind "term", but a fiction "term" kind
// already exists with different attrs; this uses the distinct code `jargon` — D-R11 — so the
// two ontologies never collide in the shared catalogue.)
//
// Seeded is_default=false, is_hidden=FALSE (DR-13). NOT default keeps them out of the default
// kind set. NOT hidden is LOAD-BEARING: adoptBookOntologyCore copies system_kinds.is_hidden
// straight into book_kinds when it clones a kind into a book tier, so a HIDDEN system template
// would clone HIDDEN into the diary and the user would never see the work kinds. Novel pickers
// stay clean NOT via is_hidden but because per-book pickers read book_kinds (what the book
// adopted) and a novel never adopts the work codes. Provisioning CLONES these into the diary's
// own tier (the adopt-branch — next WS-1.5 piece).
//
// Idempotent (ON CONFLICT DO NOTHING) and shipped as a NEW ledger step (0052) — NOT edited
// into domain.DefaultKinds, which only seeds an EMPTY catalogue and so would never reach an
// already-migrated DB (spec 05's warning + the ledger's "new seed data needs a new chain
// entry" rule). sort_order 1001+ keeps them after the fiction kinds.
// This runs at step 0052 — AFTER the G4 cutover (0026-0029) that dropped the legacy
// system_kind_attributes table and moved attributes into the TIERED model
// (system_kinds + system_kind_genres + system_attributes, keyed by (kind, genre)). And
// AFTER SeedGenreKindAttr (0025) whose "every kind → universal genre" link ran before these
// kinds existed — so we add BOTH the universal link and the attrs here, mirroring that seed.
const seedWorkKindsSQL = `
-- 1) the 7 work kinds (non-default, NOT hidden — adopt copies is_hidden into the book tier)
INSERT INTO system_kinds (code, name, description, icon, color, is_default, is_hidden, sort_order)
VALUES
  ('colleague', 'Colleague',    'A person you work with',              '👥', '#6366f1', false, false, 1001),
  ('project',   'Project',      'A body of work with a goal',          '📊', '#0ea5e9', false, false, 1002),
  ('meeting',   'Meeting',      'A scheduled discussion',              '📅', '#10b981', false, false, 1003),
  ('decision',  'Decision',     'A choice that was made',              '✅', '#22c55e', false, false, 1004),
  ('task',      'Task',         'An actionable item of work',          '📝', '#f59e0b', false, false, 1005),
  ('jargon',    'Jargon',       'Domain terminology or an acronym',    '📖', '#a855f7', false, false, 1006),
  ('org',       'Organization', 'A company, team, or external org',    '🏢', '#ef4444', false, false, 1007)
ON CONFLICT (code) DO NOTHING;

-- 2) link each work kind → the mandatory 'universal' genre (SeedGenreKindAttr's universal
--    link ran at 0025, before these kinds existed, so it skipped them).
INSERT INTO system_kind_genres (kind_id, genre_id)
SELECT k.kind_id, g.genre_id
FROM system_kinds k JOIN system_genres g ON g.code = 'universal'
WHERE k.code IN ('colleague','project','meeting','decision','task','jargon','org')
ON CONFLICT DO NOTHING;

-- 3) lift name/aliases/description attrs into (kind, universal) — the minimal set the
--    extractor/dedup/review GUI need. content_hash uses the SAME formula SeedGenreKindAttr
--    uses (desc + options empty here), so a cross-tier hash comparison stays consistent.
INSERT INTO system_attributes
  (kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, content_hash)
SELECT k.kind_id, g.genre_id, v.code, v.name, NULL, v.field_type, v.is_required, v.sort_order, NULL::text[],
       md5(v.code||'|'||v.name||'|'||''||'|'||v.field_type||'|'||(v.is_required)::text||'|'||'')
FROM system_kinds k
JOIN system_genres g ON g.code = 'universal'
CROSS JOIN (VALUES
  ('name', 'Name', 'text', true, 1),
  ('aliases', 'Aliases', 'tags', false, 2),
  ('description', 'Description', 'textarea', false, 3)
) AS v(code, name, field_type, is_required, sort_order)
WHERE k.code IN ('colleague','project','meeting','decision','task','jargon','org')
ON CONFLICT (kind_id, genre_id, code) DO NOTHING;
`

// SeedWorkKinds seeds the System-tier work ontology (WS-1.5). Idempotent; a NEW ledger step
// (0052). Seeded is_default=false, is_hidden=FALSE (DR-13 — see seedWorkKindsSQL: a hidden
// template would clone hidden into the diary; novel pickers stay clean via book_kinds, not is_hidden).
func SeedWorkKinds(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, seedWorkKindsSQL); err != nil {
		return fmt.Errorf("seed work kinds: %w", err)
	}
	return nil
}

// migrationLockKey is a fixed application-defined key for the migration advisory
// lock (arbitrary 64-bit constant — the ASCII bytes of "glsxmig8").
const migrationLockKey int64 = 0x676c73786d696738

// execGuarded runs an idempotent DDL batch inside a transaction that first takes
// a transaction-scoped advisory lock. This serializes concurrent migration runs
// — parallel `go test` package binaries sharing one dev DB, or two app instances
// starting at once — so overlapping CREATE/ALTER on the same tables queue on a
// single ordered lock instead of deadlocking on table locks acquired in
// different orders (SQLSTATE 40P01). The whole batch already ran as one implicit
// transaction via pool.Exec, so wrapping it explicitly is behaviour-preserving;
// uncontended (normal startup) it adds one cheap lock call. The lock releases
// automatically when the transaction commits/rolls back.
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
	// P2·F: append-only tenant-boundary audit table.
	return execGuarded(ctx, pool, "tenant-audit", tenantAuditSQL)
}

// tenantAuditSQL — P2·F append-only tenant-boundary audit for glossary. A row is
// written the FIRST time a caller crosses into a book they do NOT own (a
// collaborator reaching book-scoped glossary data, or a denied under-grant),
// coalesced to one row per (actor, book, outcome) per window (see
// api/tenant_audit.go). Unlike book-service, glossary resolves grants via a
// cross-service ResolveAccess that returns only a Level (no book owner), so this
// table records the book_id as the tenant boundary and has NO owner_id column —
// the owner is resolvable from book_id in book-service's DB during forensics.
// Same append-only shape as auth-service's audit tables: UUID PK, outcome CHECK
// enum, created_at index, REVOKE UPDATE/DELETE. No FK to any book row (audit must
// outlive a deleted book).
const tenantAuditSQL = `
CREATE TABLE IF NOT EXISTS tenant_access_audit (
  audit_id        UUID PRIMARY KEY DEFAULT uuidv7(),
  actor_id        UUID NOT NULL,                 -- the crossing (non-owner) caller
  book_id         UUID NOT NULL,                 -- the tenant boundary (owner resolvable in book-service)
  outcome         TEXT NOT NULL CHECK (outcome IN ('granted','denied')),
  coalesce_bucket TIMESTAMPTZ NOT NULL,          -- window start; dedups first-per-window
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_audit_window
  ON tenant_access_audit (actor_id, book_id, outcome, coalesce_bucket);

CREATE INDEX IF NOT EXISTS idx_tenant_audit_book_created
  ON tenant_access_audit (book_id, created_at DESC);

DO $$
BEGIN
    EXECUTE 'REVOKE UPDATE, DELETE ON TABLE tenant_access_audit FROM app_service_role';
EXCEPTION
    WHEN undefined_object THEN
        RAISE NOTICE 'role app_service_role does not exist (dev stack); skipping REVOKE';
END $$;
`

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
      JOIN system_kind_attributes ad ON ad.attr_def_id = av.attr_def_id
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
  JOIN system_kinds k ON k.kind_id = e.kind_id
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
	return execGuarded(ctx, pool, "snapshot", snapshotSQL)
}

// BackfillSnapshots populates entity_snapshot for any entity where it is NULL.
// Idempotent: skips entities that already have a snapshot.
//
// P-K2a-01 (session 46): the previous implementation did one SELECT
// per entity and then N separate `SELECT recalculate_entity_snapshot($1)`
// round-trips. At 10k+ entities that's 10k round-trips with
// round-trip latency dominating. The recalculate function is
// PL/pgSQL and does all its work server-side, so we can drive the
// whole sweep from a single query. One-liner; ~100× faster on a
// 10k-entity catalogue with remote Postgres.
//
// **Transactional semantics change** vs the old N-round-trip version:
// the previous code ran each recalculate as its own autocommit statement,
// so a failure on row K kept rows 1..K-1 committed. This version is a
// single statement — any row that errors rolls back the whole sweep.
// For a one-shot migration over trusted schema this is usually the
// more desirable shape (all-or-nothing), but an operator re-running
// against a mixed catalogue with one broken row needs to identify and
// exclude it before retrying.
func BackfillSnapshots(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, `
		SELECT recalculate_entity_snapshot(entity_id)
		FROM glossary_entities
		WHERE entity_snapshot IS NULL
	`)
	if err != nil {
		return fmt.Errorf("backfill snapshots: %w", err)
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
	return execGuarded(ctx, pool, "soft-delete", softDeleteSQL)
}

// Seed inserts the 12 default entity kinds and their attribute definitions. Safe to
// call on every startup — PER-KIND idempotent (D-WIKI-SEED-ROBUSTNESS).
//
// The old `count > 0 → skip` guard conflated "any kind exists" with "defaults
// seeded": the system `unknown` kind is inserted in Up() BEFORE Seed runs, so on a
// fresh-but-Up'd DB (and on a shared test DB) count was already 1 → the 12 defaults
// (incl. `character`) never seeded. Per-kind `ON CONFLICT (code) DO NOTHING` reconciles
// any missing default without clobbering an author-customized one (name/icon/color are
// left untouched on conflict) and self-heals a partially-seeded catalogue.
func Seed(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("seed tx: %w", err)
	}
	defer tx.Rollback(ctx)

	for _, k := range domain.DefaultKinds {
		// DO NOTHING (not DO UPDATE) so an author's customized default kind is never
		// clobbered; then read the id (whether just-inserted or pre-existing) for attrs.
		if _, err := tx.Exec(ctx, `
			INSERT INTO system_kinds(code, name, icon, color, is_default, is_hidden, sort_order)
			VALUES ($1,$2,$3,$4,true,false,$5)
			ON CONFLICT (code) DO NOTHING`,
			k.Code, k.Name, k.Icon, k.Color, k.SortOrder,
		); err != nil {
			return fmt.Errorf("seed kind %s: %w", k.Code, err)
		}
		var kindID string
		if err := tx.QueryRow(ctx,
			`SELECT kind_id FROM system_kinds WHERE code=$1`, k.Code,
		).Scan(&kindID); err != nil {
			return fmt.Errorf("seed kind id %s: %w", k.Code, err)
		}

		for _, a := range k.Attrs {
			if _, err := tx.Exec(ctx, `
				INSERT INTO system_kind_attributes(kind_id, code, name, field_type, is_required, is_system, sort_order)
				VALUES ($1,$2,$3,$4,$5,true,$6)
				ON CONFLICT (kind_id, code) DO NOTHING`,
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
ALTER TABLE system_kind_attributes ADD COLUMN IF NOT EXISTS genre_tags TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE system_kind_attributes ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE system_kind_attributes ADD COLUMN IF NOT EXISTS auto_fill_prompt TEXT;
ALTER TABLE system_kind_attributes ADD COLUMN IF NOT EXISTS translation_hint TEXT;
`

func UpGenreGroups(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "genre_groups", genreGroupsSQL)
}

// ── wiki articles + revisions ───────────────────────────────────────────────

const wikiSQL = `
CREATE TABLE IF NOT EXISTS wiki_articles (
  article_id       UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id        UUID NOT NULL UNIQUE REFERENCES glossary_entities(entity_id) ON DELETE RESTRICT,
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

-- Bug-1 fix: archive-redirect pointer for a loser article superseded by a merge
-- winner. The loser's article is kept (revision-preserved) and points at the
-- winner entity, never silently dropped (merge-spec AC4). NULL = live article.
ALTER TABLE wiki_articles ADD COLUMN IF NOT EXISTS superseded_by_entity_id UUID DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_wa_superseded ON wiki_articles(superseded_by_entity_id)
  WHERE superseded_by_entity_id IS NOT NULL;
-- superseded_by points at the merge winner; ON DELETE SET NULL so a later hard-delete
-- of the winner (e.g. via kind-delete) clears the redirect instead of dangling.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'wiki_articles_superseded_by_fkey') THEN
    ALTER TABLE wiki_articles ADD CONSTRAINT wiki_articles_superseded_by_fkey
      FOREIGN KEY (superseded_by_entity_id) REFERENCES glossary_entities(entity_id) ON DELETE SET NULL;
  END IF;
END $$;

-- Bug-2 fix: wiki_articles is a product table — an entity delete must NOT silently
-- cascade-destroy articles + revisions + suggestions. Swap the entity FK
-- CASCADE -> RESTRICT (idempotent, constraint-name-agnostic so it survives a
-- legacy auto-named constraint). kind-delete now removes articles explicitly,
-- emits wiki.deleted, and surfaces a count instead of a silent cascade.
--
-- review-impl fix (2026-07-06): the ORIGINAL guard here checked only whether a
-- constraint NAMED 'wiki_articles_entity_id_fkey' existed — but that is the
-- Postgres-assigned DEFAULT name for an inline REFERENCES FK on this exact
-- column, so the pre-existing CASCADE constraint already carried that name.
-- The guard therefore always saw "already exists" and skipped the swap forever
-- — this migration had NEVER actually applied on an already-live wiki_articles
-- table (only a brand-new CREATE TABLE ever got RESTRICT). Root-caused via
-- TestFK_WikiArticle_RestrictsEntityDelete failing against the real dev/test DB
-- and a live pg_constraint/pg_get_constraintdef inspection confirming CASCADE
-- still in effect. Fixed by checking the FK's ACTUAL delete-action
-- (confdeltype) instead of a name, so this is self-correcting regardless of
-- what the constraint happens to be called.
--
-- Idempotency: scope the lookup to the FK on the entity_id COLUMN specifically —
-- wiki_articles has a SECOND FK to glossary_entities (superseded_by_entity_id,
-- added just above), so a column-agnostic select could target the wrong one.
DO $$
DECLARE c text;
DECLARE deltype "char";
BEGIN
  SELECT conname, confdeltype INTO c, deltype FROM pg_constraint
   WHERE conrelid = 'wiki_articles'::regclass AND contype = 'f'
     AND confrelid = 'glossary_entities'::regclass
     AND conkey = ARRAY[(SELECT attnum FROM pg_attribute
           WHERE attrelid = 'wiki_articles'::regclass
             AND attname = 'entity_id' AND NOT attisdropped)]::smallint[];
  IF c IS NOT NULL AND deltype <> 'r' THEN
    EXECUTE format('ALTER TABLE wiki_articles DROP CONSTRAINT %I', c);
    ALTER TABLE wiki_articles
      ADD CONSTRAINT wiki_articles_entity_id_fkey
      FOREIGN KEY (entity_id) REFERENCES glossary_entities(entity_id) ON DELETE RESTRICT;
  END IF;
END $$;

-- wiki-llm M5 (C6) — AI-generation columns on the article + the §5.1 source-usage
-- reverse index. generation_status: NULL (never AI-generated / human-authored) |
-- 'generated' (clean) | 'needs_review' (verify flags) | 'blocked' (publish-blocked).
-- generation_provenance carries build_inputs (C7 fingerprint) + citations +
-- verify_flags. is_knowledge_stale is flipped by the Phase-2 staleness sweep.
ALTER TABLE wiki_articles
  ADD COLUMN IF NOT EXISTS generation_status     TEXT,
  ADD COLUMN IF NOT EXISTS generated_by          TEXT,
  ADD COLUMN IF NOT EXISTS generation_provenance JSONB,
  ADD COLUMN IF NOT EXISTS generated_at          TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS spoiler_horizon       INT,
  ADD COLUMN IF NOT EXISTS is_knowledge_stale    BOOLEAN NOT NULL DEFAULT false;

-- §5.1 reverse index: which sources (entity attrs / KG facts / chapter blocks) an
-- article was built from, so the Phase-2 staleness sweep can find every article a
-- changed source affects. CASCADE with the article (it's owned provenance).
CREATE TABLE IF NOT EXISTS wiki_article_source_usage (
  article_id     UUID NOT NULL REFERENCES wiki_articles(article_id) ON DELETE CASCADE,
  source_type    TEXT NOT NULL,         -- 'entity' | 'kg' | 'block'
  source_id      TEXT NOT NULL,
  source_version TEXT,                  -- content hash / revision (NULL = unknown)
  PRIMARY KEY (article_id, source_type, source_id)
);
CREATE INDEX IF NOT EXISTS idx_wasu_source ON wiki_article_source_usage(source_type, source_id);
-- wiki-llm W6b-2 — the source text used at generation time (the "before" half of
-- the change diff; the "after" re-gathers live). NULL for pre-W6b-2 rows → no diff
-- (the reader falls back to the W6b-1 "view source" jump). Capped on the writer side.
ALTER TABLE wiki_article_source_usage ADD COLUMN IF NOT EXISTS source_text TEXT;

-- risk #4 — the deterministic stub previously wrote its seed revision as
-- author_type='owner', indistinguishable from a human edit. Migrate legacy stub
-- revisions to 'system' (detected by the stub's fixed summary) so the M5
-- clobber-guard may let an AI regen overwrite a stub but NOT a human edit. New
-- stubs write 'system' directly (generateWikiStubs), so this UPDATE only ever
-- touches legacy rows once (idempotent thereafter).
UPDATE wiki_revisions SET author_type = 'system'
  WHERE author_type = 'owner' AND summary = 'Auto-generated from KG';

-- wiki-llm Phase-2 (§5.2) — the DEFER staleness ledger. When a knowledge source an
-- article was built from changes, the wiki-staleness consumer (push) / sweep (pull)
-- records a row here + flips wiki_articles.is_knowledge_stale — and does ZERO LLM
-- work. The "Knowledge updates" surface (§5.3) drains it; regeneration is always
-- user-gated. reason_code: entity_changed | name_changed | enrichment_changed |
-- merged | chapter_regrounded | citation_broken | recipe_drift.  severity:
-- structural (frame wrong) | content (advisory) | hard (cite points at non-canon).
CREATE TABLE IF NOT EXISTS wiki_staleness (
  staleness_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id   UUID NOT NULL REFERENCES wiki_articles(article_id) ON DELETE CASCADE,
  reason_code  TEXT NOT NULL,
  source_ref   JSONB NOT NULL DEFAULT '{}',   -- {source_type, source_id, event_id, ...}
  severity     TEXT NOT NULL DEFAULT 'content',
  status       TEXT NOT NULL DEFAULT 'pending', -- pending | regenerated | dismissed
  detected_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Idempotent capture: one OPEN (pending) row per (article, reason, source) so an
-- at-least-once event redelivery never piles duplicates. source_id is lifted out of
-- source_ref for the dedup key (an expression index can't be a UNIQUE constraint
-- target directly, so a partial unique index on the expression is used).
CREATE UNIQUE INDEX IF NOT EXISTS uq_wiki_staleness_open
  ON wiki_staleness (article_id, reason_code, (source_ref->>'source_id'))
  WHERE status = 'pending';
-- The "Knowledge updates" feed lists pending rows per book — join via the article.
CREATE INDEX IF NOT EXISTS idx_wiki_staleness_pending
  ON wiki_staleness (article_id) WHERE status = 'pending';
`

func UpWiki(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "wiki", wikiSQL)
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
	return execGuarded(ctx, pool, "wiki_suggestions", wikiSuggestionsSQL)
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
  attr_def_id UUID NOT NULL REFERENCES system_kind_attributes(attr_def_id),
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
	return execGuarded(ctx, pool, "extraction", extractionSQL)
}

// ── evidence chapter_index ──────────────────────────────────────────────────

const evidenceChapterIndexSQL = `
ALTER TABLE evidences ADD COLUMN IF NOT EXISTS chapter_index INT;
CREATE INDEX IF NOT EXISTS idx_ev_chapter_index ON evidences(chapter_index);
`

// UpEvidenceChapterIndex adds the chapter_index column to evidences.
// Safe to call on every startup (idempotent).
func UpEvidenceChapterIndex(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "evidence_chapter_index", evidenceChapterIndexSQL)
}

// ── C4 (K14) — transactional outbox for glossary.entity_updated events ──────
//
// Mirrors the platform outbox pattern already used by book-service
// (services/book-service/internal/api/outbox.go +
// services/worker-infra/internal/tasks/outbox_relay.go). The worker-infra
// outbox-relay polls this table (when glossary is listed in OUTBOX_SOURCES)
// and relays unpublished rows to the Redis Stream
// "loreweave:events:glossary" (aggregate_type='glossary' → MAXLEN 10000).
// knowledge-service's existing consumer then triggers glossary_sync → Neo4j.
//
// ADDITIVE / backward-compatible: a brand-new table + index + notify
// trigger. No existing table, column, or behaviour is altered. If the
// relay never runs (OUTBOX_SOURCES omits glossary), rows simply accumulate
// with published_at IS NULL and are pruned by the standard outbox cleanup —
// the primary entity write is never affected.
const outboxSQL = `
-- outbox_events: same shape as book-service so the worker-infra relay
-- (which is schema-generic) reads it without code changes. Default
-- aggregate_type='glossary' → routes to loreweave:events:glossary.
CREATE TABLE IF NOT EXISTS outbox_events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregate_type TEXT NOT NULL DEFAULT 'glossary',
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

-- pg_notify on insert so the relay can switch from 30s poll to
-- LISTEN/NOTIFY (D1-10) without further migration. Harmless if no
-- listener is attached.
CREATE OR REPLACE FUNCTION fn_outbox_notify()
RETURNS trigger AS $fn$
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

// UpOutbox creates the transactional outbox table + notify trigger used
// by the C4/K14 glossary→KG event pipeline. Idempotent (IF NOT EXISTS /
// CREATE OR REPLACE / duplicate-object guard) — safe on every startup.
func UpOutbox(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "outbox", outboxSQL)
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

-- 3. Replace trig_fn_entity_self_snapshot so it fires on the fields
--    that materially change the snapshot OR the search_vector, and
--    NOT on updated_at alone (T2-close-7 / P-K2a-02 & P-K3-02).
--
--    Why drop the updated_at watch: every API handler bumped updated_at
--    on any write (pin toggle, description PATCH's CTE, etc.), which
--    forced a full recalculate_entity_snapshot rebuild for writes that
--    did not change a single snapshot-source field. The cost: one EAV
--    scan + one evidences scan + one chapter_links scan + one
--    search_vector rebuild per no-op touch.
--
--    Safety: every glossary_entities column that ends up in the
--    snapshot JSONB sourced directly from this table has a specific
--    watch (status / alive / tags / kind_id / short_description).
--    EAV / attribute_translations / evidences / chapter_entity_links
--    have their own dedicated triggers. updated_at is a side-effect
--    of those upstream changes, not a cause, so dropping it cannot
--    miss a real semantic edit.
--
--    Soft-delete defence (review-impl catch): deleted_at and
--    permanently_deleted_at remain on the watch list even though they
--    are not carried in the snapshot JSONB. Without this, a soft-
--    delete or purge of an entity whose EAV state skipped the trigger
--    (raw SQL, import, backup restore) would leave the recycle bin
--    showing stale display data — 91_SS2_SOFT_DELETE_RECYCLE_BIN
--    _DETAILED_DESIGN.md §1 documents this as a required invariant.
--
--    Consequence: snapshot.updated_at now records the last SEMANTIC
--    change rather than the last touch. Callers that want "last
--    touched" (e.g. sorting, audit) should read glossary_entities
--    .updated_at directly. The knowledge-service snapshot consumer
--    does not rely on snapshot.updated_at for freshness — the
--    cached_name / cached_aliases / search_vector columns stay
--    coherent because their write paths remain triggered.
CREATE OR REPLACE FUNCTION trig_fn_entity_self_snapshot()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status                 IS DISTINCT FROM OLD.status
  OR NEW.alive                  IS DISTINCT FROM OLD.alive
  OR NEW.tags                   IS DISTINCT FROM OLD.tags
  OR NEW.kind_id                IS DISTINCT FROM OLD.kind_id
  OR NEW.short_description      IS DISTINCT FROM OLD.short_description
  OR NEW.deleted_at             IS DISTINCT FROM OLD.deleted_at
  OR NEW.permanently_deleted_at IS DISTINCT FROM OLD.permanently_deleted_at
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
      JOIN system_kind_attributes ad ON ad.attr_def_id = av.attr_def_id
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
  JOIN system_kinds k ON k.kind_id = e.kind_id
  WHERE e.entity_id = p_entity_id;

  IF v_snapshot IS NULL THEN
    RETURN;
  END IF;

  -- ── NEW: read name + aliases from EAV for the read-cache ────────────────
  SELECT av.original_value INTO v_cached_name
  FROM entity_attribute_values av
  JOIN system_kind_attributes ad ON ad.attr_def_id = av.attr_def_id
  WHERE av.entity_id = p_entity_id
    AND ad.code IN ('name','term')
  ORDER BY
    CASE ad.code WHEN 'name' THEN 0 WHEN 'term' THEN 1 ELSE 2 END,
    ad.sort_order
  LIMIT 1;

  SELECT av.original_value INTO v_aliases_raw
  FROM entity_attribute_values av
  JOIN system_kind_attributes ad ON ad.attr_def_id = av.attr_def_id
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
	return execGuarded(ctx, pool, "knowledge-memory", knowledgeMemorySQL)
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
	return execGuarded(ctx, pool, "short-desc-auto", shortDescAutoSQL)
}

// ── D-K2a-01 + D-K2a-02: defense-in-depth CHECK constraints ────────────────
//
// The PATCH /v1/glossary/.../entities/{id} handler already:
//   - coerces trimmed-empty string → NULL before write
//   - rejects values longer than 500 runes with 422
//
// These constraints close the gap for writers that bypass the API
// layer — backfill scripts, admin psql sessions, future repo code
// that forgets the coercion step. Same defense-in-depth rationale
// as the `knowledge_summaries_content_len` CHECK on the knowledge-
// service side (K7b).
//
// Both CHECKs live in DO blocks because they cannot be added with
// ADD CONSTRAINT IF NOT EXISTS until Postgres 18 (which we already
// run, but the DO pattern is what the rest of this file uses for
// constraint ops, and it's cheap to keep idempotent by hand).
//
// Before adding the non-empty CHECK we backfill any existing
// empty-string rows to NULL. Postgres rejects an ADD CONSTRAINT
// against a table with violating rows, so without the backfill a
// dev env that persisted a `''` through some pre-coercion code
// path would fail to boot.
//
// The 500-rune cap matches the API handler so users never see a
// 422 from a DB write that wasn't already blocked by the API.
// `length()` on TEXT in Postgres counts characters, not bytes, so
// CJK content gets the same budget as Latin.

const shortDescConstraintsSQL = `
-- Backfill: any empty-string short_description rows become NULL.
-- Matches the API's "trimmed-empty → NULL" coercion retroactively.
UPDATE glossary_entities
  SET short_description = NULL
  WHERE short_description = '';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'glossary_entities_short_desc_non_empty'
  ) THEN
    ALTER TABLE glossary_entities
      ADD CONSTRAINT glossary_entities_short_desc_non_empty
      CHECK (short_description IS NULL OR short_description <> '');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'glossary_entities_short_desc_len'
  ) THEN
    ALTER TABLE glossary_entities
      ADD CONSTRAINT glossary_entities_short_desc_len
      CHECK (short_description IS NULL OR length(short_description) <= 500);
  END IF;
END$$;
`

// UpShortDescConstraints adds the defense-in-depth CHECK constraints
// on glossary_entities.short_description (D-K2a-01 + D-K2a-02).
// Idempotent: backfills empty-string rows to NULL before adding the
// non-empty CHECK so existing dev envs migrate cleanly.
func UpShortDescConstraints(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "short-desc-constraints", shortDescConstraintsSQL)
}

// BackfillShortDescription iterates entities with NULL short_description,
// fetches each one's name + description attribute values + kind name,
// runs the pure shortdesc generator, and writes the result back.
// Honours the auto flag: rows where short_description_auto = false are
// skipped (user has explicitly set or cleared the field).
//
// Uses a keyset cursor on entity_id (`entity_id > $cursor ORDER BY
// entity_id`) so the loop always makes forward progress even if a row's
// UPDATE returns 0 affected (concurrent user write, generator returns
// empty, or any other edge case) — K3-I1 fix. Without the cursor a
// defensive skip on the write path would create a latent infinite loop.
//
// CAS-style: the UPDATE includes `WHERE short_description IS NULL AND
// short_description_auto = true` so concurrent writes from a user PATCH
// during backfill don't get clobbered.
//
// Reads name + description straight from EAV rather than relying on
// cached_name (K3-I2 fix): new entities whose snapshot trigger has not
// yet fired still get a correct name in their fallback.
//
// Honours ctx cancellation between batches so a shutdown signal during
// backfill on a large catalogue doesn't hold connections indefinitely
// (K3-I4 fix).
//
// Idempotent: once all live entities have a short_description, this is
// a no-op. Intended to run in a background goroutine after the service
// starts listening so health checks don't block on a large catalogue.
func BackfillShortDescription(
	ctx context.Context, pool *pgxpool.Pool,
	generate func(name, description, kindName string) string,
) (processed int, err error) {
	const batchSize = 100
	var cursor string // empty string sorts before any valid uuid
	for {
		if err := ctx.Err(); err != nil {
			return processed, err
		}

		rows, qerr := pool.Query(ctx, `
			SELECT e.entity_id::text,
			       COALESCE((
			         SELECT av.original_value
			         FROM entity_attribute_values av
			         JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
			         WHERE av.entity_id = e.entity_id
			           AND ad.code IN ('name','term')
			         ORDER BY CASE ad.code WHEN 'name' THEN 0 WHEN 'term' THEN 1 ELSE 2 END
			         LIMIT 1
			       ), '') AS name,
			       COALESCE((
			         SELECT av.original_value
			         FROM entity_attribute_values av
			         JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
			         WHERE av.entity_id = e.entity_id AND ad.code = 'description'
			         LIMIT 1
			       ), '') AS description,
			       ek.name AS kind_name
			FROM glossary_entities e
			JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
			WHERE e.short_description IS NULL
			  AND e.short_description_auto = true
			  AND e.deleted_at IS NULL
			  AND ($1 = '' OR e.entity_id::text > $1)
			ORDER BY e.entity_id
			LIMIT $2`, cursor, batchSize)
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

		// Advance cursor to the last entity we saw in this batch so the
		// next SELECT starts past it regardless of what the UPDATEs did.
		cursor = batch[len(batch)-1].ID

		for _, t := range batch {
			if err := ctx.Err(); err != nil {
				return processed, err
			}
			sd := generate(t.Name, t.Desc, t.KindName)
			if sd == "" {
				// Defensive: should not happen given the generator
				// contract, but the cursor has already advanced so we
				// won't revisit this row.
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

// ── entity_enrichments (lore-enrichment F-C13-1 + F-C13-2) ─────────────────
//
// The lore-enrichment promote flow used to write enriched lore onto the
// canonical entity's short_description COLUMN (DEFERRED-053 / canon-content).
// The QC review (F-C13-2) found that conflates makeup with the original
// authored canon: once enrichment resolves onto the real canonical entity,
// short_description can no longer be told apart from author-written canon, and
// retract had no clean per-supplement undo (F-C13-1 — it tried to recycle the
// WHOLE entity via a user JWT the service-to-service handler never has).
//
// PO ruling B1 (2026-05-31): glossary is the SINGLE SSOT; enrichment is a
// DISTINGUISHED SUPPLEMENT / `dị bản` (variant) of the original canon — never
// merged into / overwriting it, never a parallel entity. It must stay
// tellable-apart for life. This table is the structural guarantee of that
// separation: enrichment content lives HERE (FK→canonical entity), original
// canon stays in glossary_entities.short_description, untouched.
//
// Design (spec 2026-05-31-enrichment-supplement-canon-model.md, option c):
//   - one row per (entity, dimension, proposal) — a proposal_id keys a variant
//     set, so multiple `dị bản` per (entity, dimension) coexist (UNIQUE key
//     includes proposal_id, NOT just (entity, dimension)).
//   - H0 invariants carried into the schema: confidence < 1.0 (a supplement row
//     can never carry canon confidence), origin <> 'glossary' (never the canon
//     origin), review_status ∈ {proposed, promoted} (never a canon status).
//   - retract = soft-delete (deleted_at), reversible — the canonical entity and
//     its original canon are never touched.
//   - the partial index serves the live read (book_id, entity_id) WHERE not
//     soft-deleted — the wiki/entity supplement section.
//
// Idempotent: CREATE TABLE / INDEX IF NOT EXISTS. uuidv7() is a PG18 native.
const entityEnrichmentsSQL = `
CREATE TABLE IF NOT EXISTS entity_enrichments (
  enrichment_id  UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id      UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  book_id        UUID NOT NULL,
  dimension      TEXT NOT NULL,
  content        TEXT NOT NULL,
  origin         TEXT NOT NULL DEFAULT 'enrichment'
    CHECK (origin <> '' AND origin <> 'glossary'),
  technique      TEXT NOT NULL,
  confidence     NUMERIC(4,3) NOT NULL CHECK (confidence > 0 AND confidence < 1.0),
  proposal_id    UUID NOT NULL,
  review_status  TEXT NOT NULL DEFAULT 'proposed'
    CHECK (review_status IN ('proposed','promoted')),
  promoted_by    UUID,
  promoted_at    TIMESTAMPTZ,
  deleted_at     TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_id, dimension, proposal_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_enrichments_live
  ON entity_enrichments(book_id, entity_id) WHERE deleted_at IS NULL;

-- Provenance backstop (review-impl LOW-6): a 'promoted' supplement row MUST
-- carry the promoter marker. Mirrors the enrichment_proposal promote-only
-- invariant; the handler also returns a clean 400, this is the DB guarantee.
-- Idempotent DO-block (ADD CONSTRAINT IF NOT EXISTS isn't available pre-PG18
-- for the project's historical pattern; kept hand-idempotent for consistency).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'entity_enrichments_promoted_has_marker'
  ) THEN
    ALTER TABLE entity_enrichments
      ADD CONSTRAINT entity_enrichments_promoted_has_marker
      CHECK (review_status <> 'promoted' OR promoted_by IS NOT NULL);
  END IF;
END$$;
`

// UpEntityEnrichments creates the entity_enrichments table that holds the
// lore-enrichment supplement layer (PO ruling B1 / F-C13-1 + F-C13-2).
// Idempotent. Registered in cmd/glossary-service/main.go after the
// short-description migrations (it FKs glossary_entities, which Up() creates).
func UpEntityEnrichments(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-enrichments", entityEnrichmentsSQL)
}

// entityMergeSQL backs mui #1c — entity-resolution/merge. Adds the
// `merged_into_entity_id` audit pointer on glossary_entities and the
// `merge_journal` table. Reversibility model (spec §3.3): the merge
// SOFT-deletes the loser and repoints only NON-conflicting child rows to the
// winner; conflicting rows stay with the (now hidden) loser. The journal
// records exactly which child-row PKs were repointed + the winner's aliases
// value before folding, so un-merge replays them back without row snapshots.
const entityMergeSQL = `
ALTER TABLE glossary_entities
  ADD COLUMN IF NOT EXISTS merged_into_entity_id UUID DEFAULT NULL;

CREATE TABLE IF NOT EXISTS merge_journal (
  journal_id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id                    UUID NOT NULL,
  winner_entity_id           UUID NOT NULL,
  loser_entity_id            UUID NOT NULL,
  repointed_chapter_link_ids UUID[] NOT NULL DEFAULT '{}',
  repointed_eav_ids          UUID[] NOT NULL DEFAULT '{}',
  repointed_enrichment_ids   UUID[] NOT NULL DEFAULT '{}',
  repointed_audit_ids        UUID[] NOT NULL DEFAULT '{}',
  repointed_wiki_article_id  UUID,
  winner_aliases_before      TEXT,
  status                     TEXT NOT NULL DEFAULT 'merged'
    CHECK (status IN ('merged','reverted')),
  merged_by                  UUID,
  merged_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  reverted_at                TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_merge_journal_book  ON merge_journal(book_id);
CREATE INDEX IF NOT EXISTS idx_merge_journal_loser ON merge_journal(loser_entity_id);

-- Bug-1 fix: when BOTH winner+loser have a wiki_article, the loser's is archived
-- in place (superseded_by_entity_id := winner) rather than repointed. Record it
-- so un-merge can clear the archive flag (symmetric with repointed_wiki_article_id).
ALTER TABLE merge_journal ADD COLUMN IF NOT EXISTS superseded_wiki_article_id UUID DEFAULT NULL;
`

// UpEntityMerge creates the merge_journal table + merged_into_entity_id column
// (mui #1c). Idempotent. Register in main.go after UpEntityEnrichments.
func UpEntityMerge(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-merge", entityMergeSQL)
}

// mergeCandidatesSQL backs mui #1c G-cand — the merge-candidate review surface.
// knowledge's coref detector (K-detect) proposes clusters of likely-same
// entities INTO glossary (knowledge=AI compute, glossary=SSOT/curation); the
// human reviews here and confirms via the existing R5 merge endpoint.
// `member_set_key` is the sorted-distinct member-id set joined by ',' — the
// UNIQUE(book_id, member_set_key) makes re-proposing the same cluster
// idempotent, and the conditional upsert (WHERE status='proposed') means a
// dismissed/merged cluster is never resurrected by a later detection pass.
const mergeCandidatesSQL = `
CREATE TABLE IF NOT EXISTS merge_candidates (
  candidate_id               UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id                    UUID NOT NULL,
  kind_id                    UUID NOT NULL REFERENCES system_kinds(kind_id),
  member_entity_ids          UUID[] NOT NULL,
  member_set_key             TEXT NOT NULL,
  suggested_winner_entity_id UUID,
  score                      DOUBLE PRECISION NOT NULL DEFAULT 0,
  evidence_json              JSONB NOT NULL DEFAULT '[]',
  rationale                  TEXT NOT NULL DEFAULT '',
  status                     TEXT NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed','dismissed','merged')),
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_merge_candidates_setkey
  ON merge_candidates(book_id, member_set_key);
CREATE INDEX IF NOT EXISTS idx_merge_candidates_book_status
  ON merge_candidates(book_id, status);
`

// UpMergeCandidates creates the merge_candidates table (mui #1c G-cand).
// Idempotent. Register in main.go after UpEntityMerge.
func UpMergeCandidates(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "merge-candidates", mergeCandidatesSQL)
}

// mergeCandidatesG4SQL repoints merge_candidates.kind_id : system_kinds -> book_kinds,
// part of the G4 entity-layer cutover. A merge candidate's kind_id is derived from its
// member glossary_entities, which after G4 carry book_kinds(book_kind_id) values — so the
// FK must follow the entity layer onto the book tier. The merge_candidates table is created
// (with the legacy system_kinds FK) by UpMergeCandidates, which runs BEFORE book_kinds
// exists; this swap runs AFTER the cutover (book_kinds present, entities truncated, so no
// stale rows to remap). Idempotent: guarded via pg_constraint.
const mergeCandidatesG4SQL = `
ALTER TABLE merge_candidates DROP CONSTRAINT IF EXISTS merge_candidates_kind_id_fkey;
DO $mcg4$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'merge_candidates_kind_id_book_fkey') THEN
    ALTER TABLE merge_candidates
      ADD CONSTRAINT merge_candidates_kind_id_book_fkey
      FOREIGN KEY (kind_id) REFERENCES book_kinds(book_kind_id);
  END IF;
END $mcg4$;
`

// UpMergeCandidatesG4 repoints merge_candidates.kind_id onto the book tier. MUST run AFTER
// UpGlossaryCutoverG4 (book_kinds present + entities truncated). Idempotent.
func UpMergeCandidatesG4(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "merge-candidates-g4", mergeCandidatesG4SQL)
}

// ── SS-4: T2 per-user kinds (user_kinds + user_kind_attributes) ─────────────
//
// The per-user tier of the kind-tiering epic (CLAUDE.md › User Boundaries &
// Tenancy). A user's custom kinds live HERE, scoped by owner_user_id, instead
// of polluting the shared system_kinds catalogue (the multi-tenancy defect the
// epic fixes). UNIQUE(owner_user_id, code) is the scope-keyed constraint that
// replaces the old global UNIQUE(code) smell. Soft-delete + recycle-bin
// (deleted_at / permanently_deleted_at) mirror the SS-2 glossary-entity pattern.
//
// cloned_from_kind_id FK → system_kinds: a T2 kind may be cloned from a T1
// system default (copies its name/icon/color + attribute defs); ON DELETE SET
// NULL so retiring a system kind doesn't cascade-delete a user's clone.
//
// Entities cannot yet be created against a T2 kind — glossary_entities.kind_id
// stays the live system_kinds ref until SS-7 repoints it polymorphically. See
// docs/03_planning/93_SS4_USER_KIND_CRUD_DETAILED_DESIGN.md.
const userKindsSQL = `
CREATE TABLE IF NOT EXISTS user_kinds (
  user_kind_id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id          UUID        NOT NULL,
  code                   TEXT        NOT NULL,
  name                   TEXT        NOT NULL,
  description            TEXT,
  icon                   TEXT        NOT NULL DEFAULT 'box',
  color                  TEXT        NOT NULL DEFAULT '#6366f1',
  -- genre_tags RETIRED (see system_kinds note); UpGlossaryDropLegacyG4 drops it once on
  -- legacy DBs. Not created here so fresh DBs never carry the dead column.
  is_active              BOOLEAN     NOT NULL DEFAULT true,
  cloned_from_kind_id    UUID        REFERENCES system_kinds(kind_id) ON DELETE SET NULL,
  permanently_deleted_at TIMESTAMPTZ,
  deleted_at             TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(owner_user_id, code)
);
CREATE INDEX IF NOT EXISTS idx_uk_owner
  ON user_kinds(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_uk_trash
  ON user_kinds(owner_user_id, deleted_at DESC)
  WHERE deleted_at IS NOT NULL AND permanently_deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS user_kind_attributes (
  attr_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_kind_id UUID        NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  code         TEXT        NOT NULL,
  name         TEXT        NOT NULL,
  description  TEXT,
  field_type   TEXT        NOT NULL DEFAULT 'text',
  is_required  BOOLEAN     NOT NULL DEFAULT false,
  sort_order   INT         NOT NULL DEFAULT 0,
  options      TEXT[],
  deleted_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_uka_kind
  ON user_kind_attributes(user_kind_id) WHERE deleted_at IS NULL;
`

// UpUserKinds creates the T2 per-user kind tables (SS-4). Idempotent
// (CREATE/INDEX IF NOT EXISTS). Register in main.go after the system-kind seed.
func UpUserKinds(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "user-kinds", userKindsSQL)
}

// ── G1: genre·kind·attribute tiering (standards → sovereign instance) ──────────
// Spec: docs/specs/2026-06-19-genre-kind-attribute-tiering.md
// Plan: docs/plans/2026-06-19-genre-kind-attribute-build.md
//
// Genre becomes a first-class TIERED level (system/user/book) alongside kind;
// attributes are keyed by (kind × genre × code). Every reference is a PLAIN
// single-tier FK — no polymorphism (proven by the G0 copy-down spike). This
// migration is ADDITIVE: the legacy genre_tags[] columns, genre_groups, and
// system_kind_attributes stay until their last consumer is retargeted (G4), so
// each milestone's test suite stays green (broken-window is FE-only, R3).
const genreKindAttrSQL = `
-- Genre tier ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_genres (
  genre_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code         TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL,
  icon         TEXT NOT NULL DEFAULT '',
  color        TEXT NOT NULL DEFAULT '#6366f1',
  sort_order   INT  NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL DEFAULT '',   -- Sync (G5) change-detection
  is_default   BOOLEAN NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_genres (
  genre_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id          UUID NOT NULL,
  code                   TEXT NOT NULL,
  name                   TEXT NOT NULL,
  icon                   TEXT NOT NULL DEFAULT '',
  color                  TEXT NOT NULL DEFAULT '#6366f1',
  sort_order             INT  NOT NULL DEFAULT 0,
  content_hash           TEXT NOT NULL DEFAULT '',
  cloned_from_genre_id   UUID REFERENCES system_genres(genre_id) ON DELETE SET NULL,
  permanently_deleted_at TIMESTAMPTZ,
  deleted_at             TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(owner_user_id, code)
);
CREATE INDEX IF NOT EXISTS idx_ug_owner ON user_genres(owner_user_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS book_genres (
  genre_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id       UUID NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  icon          TEXT NOT NULL DEFAULT '',
  color         TEXT NOT NULL DEFAULT '#6366f1',
  sort_order    INT  NOT NULL DEFAULT 0,
  source_ref    TEXT,                       -- 'system:<id>' | 'user:<id>' | NULL(book-native)
  source_hash   TEXT,                       -- content_hash captured at adopt; vs source = "update available"
  deprecated_at TIMESTAMPTZ,                -- boundary independence: remove = deprecate
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_id, code)
);
CREATE INDEX IF NOT EXISTS idx_bg_book ON book_genres(book_id);

-- Book kinds (T3) ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS book_kinds (
  book_kind_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id       UUID NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  icon          TEXT NOT NULL DEFAULT 'box',
  color         TEXT NOT NULL DEFAULT '#6366f1',
  sort_order    INT  NOT NULL DEFAULT 0,
  is_hidden     BOOLEAN NOT NULL DEFAULT false,
  source_ref    TEXT,
  source_hash   TEXT,
  deprecated_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_id, code)
);
CREATE INDEX IF NOT EXISTS idx_bk_book ON book_kinds(book_id);

-- Kind↔genre links (per tier, plain FKs) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_kind_genres (
  kind_id  UUID NOT NULL REFERENCES system_kinds(kind_id) ON DELETE CASCADE,
  genre_id UUID NOT NULL REFERENCES system_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (kind_id, genre_id)
);
CREATE TABLE IF NOT EXISTS user_kind_genres (
  kind_id  UUID NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  genre_id UUID NOT NULL REFERENCES user_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (kind_id, genre_id)
);
CREATE TABLE IF NOT EXISTS book_kind_genres (
  book_id  UUID NOT NULL,
  kind_id  UUID NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  genre_id UUID NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (kind_id, genre_id)
);

-- Attributes (per tier, keyed by kind × genre × code) ───────────────────────────
CREATE TABLE IF NOT EXISTS system_attributes (
  attr_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind_id          UUID NOT NULL REFERENCES system_kinds(kind_id) ON DELETE CASCADE,
  genre_id         UUID NOT NULL REFERENCES system_genres(genre_id) ON DELETE CASCADE,
  code             TEXT NOT NULL,
  name             TEXT NOT NULL,
  description      TEXT,
  field_type       TEXT NOT NULL DEFAULT 'text',
  is_required      BOOLEAN NOT NULL DEFAULT false,
  sort_order       INT  NOT NULL DEFAULT 0,
  options          TEXT[],
  auto_fill_prompt TEXT,
  translation_hint TEXT,
  content_hash     TEXT NOT NULL DEFAULT '',
  UNIQUE(kind_id, genre_id, code)
);
CREATE INDEX IF NOT EXISTS idx_sa_kind_genre ON system_attributes(kind_id, genre_id);

CREATE TABLE IF NOT EXISTS user_attributes (
  attr_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id       UUID NOT NULL,
  kind_id             UUID NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  genre_id            UUID NOT NULL REFERENCES user_genres(genre_id) ON DELETE CASCADE,
  code                TEXT NOT NULL,
  name                TEXT NOT NULL,
  description         TEXT,
  field_type          TEXT NOT NULL DEFAULT 'text',
  is_required         BOOLEAN NOT NULL DEFAULT false,
  sort_order          INT  NOT NULL DEFAULT 0,
  options             TEXT[],
  auto_fill_prompt    TEXT,
  translation_hint    TEXT,
  content_hash        TEXT NOT NULL DEFAULT '',
  cloned_from_attr_id UUID REFERENCES system_attributes(attr_id) ON DELETE SET NULL,
  deleted_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(owner_user_id, kind_id, genre_id, code)
);
CREATE INDEX IF NOT EXISTS idx_ua_kind_genre ON user_attributes(kind_id, genre_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS book_attributes (
  attr_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id          UUID NOT NULL,
  kind_id          UUID NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  genre_id         UUID NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  code             TEXT NOT NULL,
  name             TEXT NOT NULL,
  description      TEXT,
  field_type       TEXT NOT NULL DEFAULT 'text',
  is_required      BOOLEAN NOT NULL DEFAULT false,
  sort_order       INT  NOT NULL DEFAULT 0,
  options          TEXT[],
  auto_fill_prompt TEXT,
  translation_hint TEXT,
  source_ref       TEXT,
  source_hash      TEXT,
  deprecated_at    TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_id, kind_id, genre_id, code)
);
CREATE INDEX IF NOT EXISTS idx_ba_book_kind_genre ON book_attributes(book_id, kind_id, genre_id) WHERE deprecated_at IS NULL;

-- Book genre activation + per-entity genre override (D2) ─────────────────────────
CREATE TABLE IF NOT EXISTS book_active_genres (
  book_id  UUID NOT NULL,
  genre_id UUID NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (book_id, genre_id)
);
CREATE TABLE IF NOT EXISTS entity_genres (
  entity_id UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  genre_id  UUID NOT NULL REFERENCES book_genres(genre_id) ON DELETE CASCADE,
  PRIMARY KEY (entity_id, genre_id)
);
`

// UpGenreKindAttr creates the genre tier, kind↔genre link tables, per-(kind,genre)
// attribute tables, the book tier (kinds/genres/attributes/active-genres), and the
// per-entity genre override. Additive + idempotent. Register after UpUserKinds
// (user_kind_genres / user_attributes FK user_kinds).
func UpGenreKindAttr(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "genre-kind-attr", genreKindAttrSQL)
}

// systemGenreVocabulary is the O3 system-genre vocabulary (the standards-tier
// genre set seeded into system_genres). Derived directly in Go — NOT from the
// (now-dropped) system_kinds.genre_tags column — so the seed survives G4e's
// destructive drops. Order = sort_order (1-based). `universal` is first + O4.
var systemGenreVocabulary = []struct {
	Code, Name, Icon, Color string
}{
	{"universal", "Universal", "🌐", "#64748b"},
	{"fantasy", "Fantasy", "🐉", "#a855f7"},
	{"xianxia", "Xianxia", "⚔️", "#6366f1"},
	{"romance", "Romance", "💕", "#f43f5e"},
	{"drama", "Drama", "🎭", "#f59e0b"},
	{"historical", "Historical", "🏛️", "#0891b2"},
	{"mystery", "Mystery", "🔍", "#10b981"},
}

// SeedGenreKindAttr populates the SYSTEM-tier standards in the tiered tables —
// derived DIRECTLY from domain.DefaultKinds in Go (NOT from the legacy
// system_kinds.genre_tags column / system_kind_attributes table, which G4e
// drops). Run AFTER Seed (needs the system_kinds rows for FK resolution) and
// after UpGenreKindAttr. It writes:
//
//  1. system_genres — the O3 vocabulary (universal + fantasy + xianxia + romance
//     + drama + historical + mystery). content_hash = md5("code|Name").
//  2. system_kind_genres — every kind → `universal` (O4: mandatory, anchors base
//     attrs) plus each of the kind's declared GenreTags that resolves to a seeded
//     genre. A kind missing from DefaultKinds (e.g. the runtime `unknown` kind)
//     still gets its `universal` link via the catch-all pass below.
//  3. system_attributes — every DefaultKind attr lifted into (kind, universal),
//     faithful to current behaviour (all of a kind's attrs apply); moving
//     genre-specific attrs onto their genre is the O1 curate pass (deferred).
//
// Idempotent (ON CONFLICT DO NOTHING): self-heals + never clobbers curation.
// content_hash is set once here and NOT refreshed on re-seed; the admin-edit path
// (G2) owns recomputing it so G5 Sync can detect system-side edits.
func SeedGenreKindAttr(ctx context.Context, pool *pgxpool.Pool) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("seed genre-kind-attr: begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// 1) system genres (O3 vocabulary). content_hash mirrors the prior md5("code|Name").
	for i, g := range systemGenreVocabulary {
		if _, err := tx.Exec(ctx, `
			INSERT INTO system_genres (code, name, icon, color, sort_order, content_hash)
			VALUES ($1,$2,$3,$4,$5, md5($1||'|'||$2))
			ON CONFLICT (code) DO NOTHING`,
			g.Code, g.Name, g.Icon, g.Color, i+1,
		); err != nil {
			return fmt.Errorf("seed system genre %s: %w", g.Code, err)
		}
	}

	// 2a) every kind → universal (O4: mandatory). Catch-all so kinds NOT in
	//     DefaultKinds (e.g. the runtime `unknown` kind) still get the link.
	if _, err := tx.Exec(ctx, `
		INSERT INTO system_kind_genres (kind_id, genre_id)
		SELECT k.kind_id, g.genre_id
		FROM system_kinds k
		JOIN system_genres g ON g.code = 'universal'
		ON CONFLICT DO NOTHING`); err != nil {
		return fmt.Errorf("seed universal kind-genres: %w", err)
	}

	// 2b) each DefaultKind → its declared GenreTags (only those resolving to a
	//     seeded genre) + 3) lift each kind's attrs into (kind, universal).
	for _, k := range domain.DefaultKinds {
		var kindID string
		if err := tx.QueryRow(ctx,
			`SELECT kind_id FROM system_kinds WHERE code=$1`, k.Code,
		).Scan(&kindID); err != nil {
			return fmt.Errorf("seed gka resolve kind %s: %w", k.Code, err)
		}

		for _, tag := range k.GenreTags {
			// Only in-vocabulary tags link (an exotic tag is dropped — the kind
			// still carries its mandatory universal link from 2a).
			if _, err := tx.Exec(ctx, `
				INSERT INTO system_kind_genres (kind_id, genre_id)
				SELECT $1, g.genre_id FROM system_genres g WHERE g.code = $2
				ON CONFLICT DO NOTHING`, kindID, tag,
			); err != nil {
				return fmt.Errorf("seed kind-genre %s/%s: %w", k.Code, tag, err)
			}
		}

		for _, a := range k.Attrs {
			var desc *string // DefaultKinds carry no per-attr description today
			var opts []string
			if len(a.Options) > 0 {
				opts = a.Options
			}
			if _, err := tx.Exec(ctx, `
				INSERT INTO system_attributes
				  (kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, content_hash)
				SELECT $1, g.genre_id, $2, $3, $4, $5, $6::boolean, $7, $8::text[],
				       md5($2||'|'||$3||'|'||coalesce($4,'')||'|'||$5||'|'||($6::boolean)::text||'|'||coalesce(array_to_string($8::text[],','),''))
				FROM system_genres g WHERE g.code = 'universal'
				ON CONFLICT (kind_id, genre_id, code) DO NOTHING`,
				kindID, a.Code, a.Name, desc, a.FieldType, a.IsRequired, a.SortOrder, opts,
			); err != nil {
				return fmt.Errorf("seed system attr %s.%s: %w", k.Code, a.Code, err)
			}
		}
	}

	return tx.Commit(ctx)
}

// glossaryCutoverG4SQL is the G4 destructive cutover (genre·kind·attribute epic).
// It repoints the entity layer onto the BOOK tier (book-local plain FKs — the
// sovereign-instance model) and rewrites the snapshot to read book_kinds /
// book_attributes. Under R2 (full reset) this is a clean teardown, NOT a data
// transform: TRUNCATE … CASCADE clears glossary_entities and everything FK-bound to
// it (chapter_entity_links, entity_attribute_values, entity_genres, evidences,
// attribute_translations, AND the wiki_* tables — CASCADE bypasses their ON DELETE
// RESTRICT, E1). Books re-scaffold via adopt; wiki re-populates as entities return.
//
// DESTRUCTIVE to entity + wiki DATA — gated. Runs only where the migration chain runs
// (the throwaway test DB during build; the dev DB at a deliberate deploy). Idempotent:
// constraint swaps guarded via pg_constraint; CREATE OR REPLACE for the function.
//
// The legacy tables (system_kind_attributes, genre_groups) and the genre_tags columns
// are NOT dropped here — their handlers retarget first; the drops land in the same
// epic once nothing reads them. This keeps the cutover focused on the entity-layer FK.
const glossaryCutoverG4SQL = `
-- 1) Full reset of entity-derived data (required to repoint the FKs cleanly).
--    GUARDED to run EXACTLY ONCE per database: only while the OLD FK
--    (glossary_entities_kind_id_fkey -> system_kinds) still exists, i.e. we have not
--    cut over yet. That constraint is dropped in step 2 below, so on every subsequent
--    startup (migrations re-run each boot; execGuarded has no applied-ledger) this
--    block is skipped — WITHOUT this guard the cutover would TRUNCATE all entities +
--    wiki on every restart (catastrophic data loss in production).
DO $cutover$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'glossary_entities_kind_id_fkey') THEN
    TRUNCATE TABLE glossary_entities CASCADE;
  END IF;
END $cutover$;

-- 2) Repoint glossary_entities.kind_id : system_kinds -> book_kinds (book-local).
ALTER TABLE glossary_entities DROP CONSTRAINT IF EXISTS glossary_entities_kind_id_fkey;
DO $cutover$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'glossary_entities_kind_id_book_fkey') THEN
    ALTER TABLE glossary_entities
      ADD CONSTRAINT glossary_entities_kind_id_book_fkey
      FOREIGN KEY (kind_id) REFERENCES book_kinds(book_kind_id);
  END IF;
END $cutover$;

-- 3) Repoint entity_attribute_values.attr_def_id : system_kind_attributes -> book_attributes.
ALTER TABLE entity_attribute_values DROP CONSTRAINT IF EXISTS entity_attribute_values_attr_def_id_fkey;
DO $cutover$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'eav_attr_def_id_book_fkey') THEN
    ALTER TABLE entity_attribute_values
      ADD CONSTRAINT eav_attr_def_id_book_fkey
      FOREIGN KEY (attr_def_id) REFERENCES book_attributes(attr_id);
  END IF;
END $cutover$;

-- 4) Rewrite the snapshot to the BOOK tier (book_kinds / book_attributes; source 'book').
CREATE OR REPLACE FUNCTION recalculate_entity_snapshot(p_entity_id UUID)
RETURNS void
LANGUAGE plpgsql
AS $snap$
DECLARE
  v_snapshot JSONB;
BEGIN
  SELECT jsonb_build_object(
    'schema_version', '1.0',
    'entity_id',      e.entity_id::text,
    'book_id',        e.book_id::text,
    'kind', jsonb_build_object(
      'source', 'book',
      'ref_id', k.book_kind_id::text,
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
          'attr_def_source',   'book',
          'attr_def_ref_id',   ad.attr_id::text,
          'attr_value_id',     av.attr_value_id::text,
          'code',              ad.code,
          'name',              ad.name,
          'field_type',        ad.field_type,
          'is_required',       ad.is_required,
          'is_system',         false,
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
      JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
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
  JOIN book_kinds k ON k.book_kind_id = e.kind_id
  WHERE e.entity_id = p_entity_id;

  IF v_snapshot IS NULL THEN
    RETURN;
  END IF;

  UPDATE glossary_entities
  SET entity_snapshot = v_snapshot
  WHERE entity_id = p_entity_id
    AND entity_snapshot IS DISTINCT FROM v_snapshot;
END;
$snap$;
`

// UpGlossaryCutoverG4 repoints the entity layer onto the book tier and rewrites the
// snapshot (genre·kind·attribute epic, G4). DESTRUCTIVE to entity + wiki data. Run
// LAST in the chain — after UpGenreKindAttr (needs book_kinds/book_attributes to exist
// as FK targets) and after SeedGenreKindAttr.
func UpGlossaryCutoverG4(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "glossary-cutover-g4", glossaryCutoverG4SQL)
}

// glossaryCutoverG4CacheSQL re-applies the cache+search-aware recalculate_entity_snapshot
// onto the BOOK tier. The cutover (glossaryCutoverG4SQL) rewrites recalculate_entity_snapshot
// to read book_kinds/book_attributes, but using the BASE snapshot body — it drops the
// cached_name / cached_aliases / search_vector maintenance that UpKnowledgeMemory layered on
// (those still joined system_kind_attributes). This step restores that maintenance on the
// book tier, so the read cache + FTS stay populated for book-tier entities. Runs AFTER the
// cutover. Idempotent (CREATE OR REPLACE preserves trigger bindings).
const glossaryCutoverG4CacheSQL = `
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
  -- ── Snapshot build (book tier) ───────────────────────────────────────────
  SELECT jsonb_build_object(
    'schema_version', '1.0',
    'entity_id',      e.entity_id::text,
    'book_id',        e.book_id::text,
    'kind', jsonb_build_object(
      'source', 'book',
      'ref_id', k.book_kind_id::text,
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
          'attr_def_source',   'book',
          'attr_def_ref_id',   ad.attr_id::text,
          'attr_value_id',     av.attr_value_id::text,
          'code',              ad.code,
          'name',              ad.name,
          'field_type',        ad.field_type,
          'is_required',       ad.is_required,
          'is_system',         false,
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
      JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
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
  JOIN book_kinds k ON k.book_kind_id = e.kind_id
  WHERE e.entity_id = p_entity_id;

  IF v_snapshot IS NULL THEN
    RETURN;
  END IF;

  -- ── Read name + aliases from EAV for the read-cache (book tier) ──────────
  SELECT av.original_value INTO v_cached_name
  FROM entity_attribute_values av
  JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
  WHERE av.entity_id = p_entity_id
    AND ad.code IN ('name','term')
  ORDER BY
    CASE ad.code WHEN 'name' THEN 0 WHEN 'term' THEN 1 ELSE 2 END,
    ad.sort_order
  LIMIT 1;

  SELECT av.original_value INTO v_aliases_raw
  FROM entity_attribute_values av
  JOIN book_attributes ad ON ad.attr_id = av.attr_def_id
  WHERE av.entity_id = p_entity_id AND ad.code = 'aliases'
  LIMIT 1;

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

// UpGlossaryCutoverG4Cache restores the cache+search-aware recalculate_entity_snapshot on
// the book tier. MUST run AFTER UpGlossaryCutoverG4 (and after UpKnowledgeMemory, whose
// system-tier version it supersedes). Idempotent.
func UpGlossaryCutoverG4Cache(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "glossary-cutover-g4-cache", glossaryCutoverG4CacheSQL)
}

// glossaryDropLegacyG4SQL is the G4e IRREVERSIBLE drop of the retired genre·kind·
// attribute objects — the last step of the cutover, run ONLY after every reader/
// writer has been retargeted off them (G4d):
//
//   - genre_groups          — legacy per-book genre buckets, replaced by the tiered
//     *_genres + book_active_genres. Its handlers (listGenres/createGenre/…) are
//     retired with the route.
//   - system_kind_attributes — reshaped into system_attributes keyed (kind,genre,code).
//     After the G4 cutover entity_attribute_values.attr_def_id → book_attributes, so
//     nothing FKs this table anymore and it is droppable.
//   - system_kinds.genre_tags / user_kinds.genre_tags — the flat-genre TEXT[] drift,
//     replaced by the *_kind_genres link tables. SeedGenreKindAttr now derives the
//     system standards in Go from DefaultKinds (not from these columns). These columns
//     are FULLY RETIRED upstream (no longer created/re-added/written by Up or Seed), so
//     the DROP here is a ONE-TIME cleanup for legacy DBs — it no longer fights a re-add.
//
// Idempotent: DROP / ALTER … IF EXISTS. genre_groups + system_kind_attributes are still
// whole TABLES that Up/UpGenreGroups re-create each run and this step drops again — that
// is safe (a DROP TABLE + CREATE TABLE recycles pg_attribute cleanly, no slot leak).
// The genre_tags COLUMNS, by contrast, must NOT be re-added each run: ADD-then-DROP on a
// persistent table leaks a dropped-column slot per run toward the 1600 ceiling (fixed —
// the re-add was removed; see D-GKA-SYSTEM-KINDS-SLOTS).
// DESTRUCTIVE — gated (execGuarded), dev DB only (rollback = git revert + re-migrate).
const glossaryDropLegacyG4SQL = `
-- extraction_audit_log.attr_def_id still FKs system_kind_attributes (UpExtraction
-- created it before the cutover). The cutover TRUNCATEd glossary_entities CASCADE so
-- this table is empty; repoint its FK onto book_attributes (the book tier the entity
-- layer now uses) so the legacy table can be dropped. Guarded via pg_constraint.
ALTER TABLE extraction_audit_log DROP CONSTRAINT IF EXISTS extraction_audit_log_attr_def_id_fkey;
DO $eal$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'eal_attr_def_id_book_fkey') THEN
    ALTER TABLE extraction_audit_log
      ADD CONSTRAINT eal_attr_def_id_book_fkey
      FOREIGN KEY (attr_def_id) REFERENCES book_attributes(attr_id);
  END IF;
END $eal$;

DROP TABLE IF EXISTS genre_groups;
DROP TABLE IF EXISTS system_kind_attributes;
ALTER TABLE system_kinds DROP COLUMN IF EXISTS genre_tags;
ALTER TABLE user_kinds   DROP COLUMN IF EXISTS genre_tags;
`

// UpGlossaryDropLegacyG4 drops the retired genre·kind·attribute legacy objects
// (genre_groups, system_kind_attributes) and the genre_tags columns (G4e). MUST run
// LAST in the migration chain — after every consumer retarget (G4d) and after the
// cutover + cache rewrite (so the snapshot fn no longer joins system_kind_attributes).
// Idempotent; DESTRUCTIVE.
func UpGlossaryDropLegacyG4(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "glossary-drop-legacy-g4", glossaryDropLegacyG4SQL)
}

// chapterLinkMentionCountSQL adds the per-chapter mention-frequency column to
// chapter_entity_links (M7 / D-T5.2-WINDOWED-MENTIONS). Additive, forward-only —
// glossary has no down-migration. The UNIQUE(entity_id, chapter_id) is unchanged
// (the count lives WITHIN a chapter, one row per (entity,chapter)); a recount
// upsert overwrites the value via ON CONFLICT … DO UPDATE in the extraction
// writeback. Defaults 0 so existing rows read as "not yet recounted" until the
// producer re-runs (live extraction) or the backfill recount job lands.
const chapterLinkMentionCountSQL = `
ALTER TABLE chapter_entity_links ADD COLUMN IF NOT EXISTS mention_count INT NOT NULL DEFAULT 0;
`

// UpChapterLinkMentionCount adds chapter_entity_links.mention_count. Idempotent.
func UpChapterLinkMentionCount(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "chapter-link-mention-count", chapterLinkMentionCountSQL)
}
