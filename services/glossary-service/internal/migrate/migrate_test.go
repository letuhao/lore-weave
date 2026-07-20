package migrate

// D-WIKI-SEED-ROBUSTNESS — Seed must be PER-KIND idempotent: a pre-existing kind
// (e.g. the system 'unknown' inserted in Up, or a leftover kind on a shared test DB)
// must NOT make the 12 default kinds skip seeding. Needs GLOSSARY_TEST_DB_URL.
//
// db-safety-gate: file-ok — TestUp_RenamesLegacyEntityKindsPreservingData runs on a
// THROWAWAY ephemeral DB it CREATEs itself (its DROP DATABASE targets only that ephemeral,
// never the DB in GLOSSARY_TEST_DB_URL); the other tests' cleanups are code-scoped
// (DELETE … WHERE code=…).

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// TestUp_RenamesLegacyEntityKindsPreservingData proves the SS-4 T1 rename
// (entity_kinds → system_kinds, attribute_definitions → system_kind_attributes)
// migrates an EXISTING pre-SS-4 database in place — the data-bearing legacy
// tables are RENAMED (rows + FKs preserved), not shadowed by new empty tables.
// This is the one real data-loss risk of the rename, so it gets a dedicated
// test on its own ephemeral DB (the precondition — legacy tables present,
// system_kinds absent — can't be set up on the shared seed-test DB).
func TestUp_RenamesLegacyEntityKindsPreservingData(t *testing.T) {
	dbURL := os.Getenv("GLOSSARY_TEST_DB_URL")
	if dbURL == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set")
	}
	ctx := context.Background()

	base, err := url.Parse(dbURL)
	if err != nil {
		t.Fatalf("parse url: %v", err)
	}
	maint := *base
	maint.Path = "/postgres"

	admin, err := pgxpool.New(ctx, maint.String())
	if err != nil {
		t.Fatalf("admin pool: %v", err)
	}
	defer admin.Close()

	ephemeral := fmt.Sprintf("glossary_ss4_rename_%d", os.Getpid())
	// Drop any leftover from a prior aborted run, then create fresh.
	_, _ = admin.Exec(ctx, `DROP DATABASE IF EXISTS `+pgx.Identifier{ephemeral}.Sanitize()+` WITH (FORCE)`)
	if _, err := admin.Exec(ctx, `CREATE DATABASE `+pgx.Identifier{ephemeral}.Sanitize()); err != nil {
		t.Fatalf("create ephemeral db: %v", err)
	}
	t.Cleanup(func() {
		c, err := pgxpool.New(context.Background(), maint.String())
		if err != nil {
			return
		}
		defer c.Close()
		_, _ = c.Exec(context.Background(), `DROP DATABASE IF EXISTS `+pgx.Identifier{ephemeral}.Sanitize()+` WITH (FORCE)`)
	})

	target := *base
	target.Path = "/" + ephemeral
	pool, err := pgxpool.New(ctx, target.String())
	if err != nil {
		t.Fatalf("ephemeral pool: %v", err)
	}
	defer pool.Close()

	// Simulate a pre-SS-4 DB: the legacy tables with rows + the FK between them.
	// Columns mirror the original schemaSQL so the post-rename CREATE IF NOT
	// EXISTS no-ops without needing to add a missing column.
	if _, err := pool.Exec(ctx, `
		CREATE TABLE entity_kinds (
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
		CREATE TABLE attribute_definitions (
		  attr_def_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
		  kind_id     UUID NOT NULL REFERENCES entity_kinds(kind_id) ON DELETE CASCADE,
		  code        TEXT NOT NULL,
		  name        TEXT NOT NULL,
		  field_type  TEXT NOT NULL DEFAULT 'text',
		  is_required BOOLEAN NOT NULL DEFAULT false,
		  sort_order  INT NOT NULL DEFAULT 0,
		  UNIQUE(kind_id, code)
		);
		INSERT INTO entity_kinds(code,name) VALUES ('legacy_marker','Legacy Marker');
		INSERT INTO attribute_definitions(kind_id, code, name)
		  SELECT kind_id, 'legacy_attr', 'Legacy Attr' FROM entity_kinds WHERE code='legacy_marker';
	`); err != nil {
		t.Fatalf("seed legacy tables: %v", err)
	}

	if err := Up(ctx, pool); err != nil {
		t.Fatalf("Up (rename migration): %v", err)
	}

	// The legacy row survived the rename, reachable under the NEW table name.
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM system_kinds WHERE code='legacy_marker'`).Scan(&n); err != nil {
		t.Fatalf("count system_kinds: %v", err)
	}
	if n != 1 {
		t.Fatalf("legacy kind row lost in rename (count=%d, want 1)", n)
	}
	// The dependent attribute row + its FK survived (rename preserves FKs).
	var attrN int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM system_kind_attributes ad
		 JOIN system_kinds k ON k.kind_id = ad.kind_id
		 WHERE ad.code='legacy_attr' AND k.code='legacy_marker'`,
	).Scan(&attrN); err != nil {
		t.Fatalf("count system_kind_attributes: %v", err)
	}
	if attrN != 1 {
		t.Fatalf("legacy attr row/FK lost in rename (count=%d, want 1)", attrN)
	}
	// The old names are gone — no split-brain leftover empty table.
	var reg *string
	if err := pool.QueryRow(ctx, `SELECT to_regclass('public.entity_kinds')::text`).Scan(&reg); err != nil {
		t.Fatalf("to_regclass entity_kinds: %v", err)
	}
	if reg != nil {
		t.Fatalf("legacy entity_kinds table still present after rename (=%q)", *reg)
	}

	// Idempotent: a second Up (now the IF EXISTS rename is a no-op) must not error.
	if err := Up(ctx, pool); err != nil {
		t.Fatalf("re-Up not idempotent: %v", err)
	}
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM system_kinds WHERE code='legacy_marker'`).Scan(&n); err != nil {
		t.Fatalf("re-count system_kinds: %v", err)
	}
	if n != 1 {
		t.Fatalf("re-Up disturbed the migrated row (count=%d, want 1)", n)
	}
}

func TestSeed_ReconcilesDefaultsDespitePreExistingKindAndIsIdempotent(t *testing.T) {
	url := os.Getenv("GLOSSARY_TEST_DB_URL")
	if url == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatalf("pool: %v", err)
	}
	defer pool.Close()

	if err := Up(ctx, pool); err != nil {
		t.Fatalf("Up: %v", err)
	}
	// Force the bug precondition: a non-default kind already exists, so the OLD
	// `count > 0 → return` guard would have skipped seeding the defaults entirely.
	if _, err := pool.Exec(ctx,
		`INSERT INTO system_kinds(code,name,icon,color,is_default,is_hidden,sort_order)
		 VALUES('zzz_seed_precond','Precond','x','#ffffff',false,true,9998)
		 ON CONFLICT (code) DO NOTHING`,
	); err != nil {
		t.Fatalf("seed precond kind: %v", err)
	}
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM system_kinds WHERE code='zzz_seed_precond'`) })

	if err := Seed(ctx, pool); err != nil {
		t.Fatalf("Seed: %v", err)
	}
	// A default kind (character) must be present despite the pre-existing kind.
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM system_kinds WHERE code='character'`).Scan(&n); err != nil {
		t.Fatalf("count character: %v", err)
	}
	if n != 1 {
		t.Fatalf("default 'character' not seeded despite a pre-existing kind (count=%d)", n)
	}
	// Its system attribute defs were seeded too (per-kind reconcile, not just the row).
	var attrs int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM system_kind_attributes ad JOIN system_kinds ek ON ek.kind_id=ad.kind_id WHERE ek.code='character'`,
	).Scan(&attrs)
	if attrs == 0 {
		t.Fatal("character system_kind_attributes not seeded")
	}

	// Idempotent: a second Seed neither errors nor duplicates.
	if err := Seed(ctx, pool); err != nil {
		t.Fatalf("re-Seed: %v", err)
	}
	pool.QueryRow(ctx, `SELECT count(*) FROM system_kinds WHERE code='character'`).Scan(&n)
	if n != 1 {
		t.Fatalf("re-Seed duplicated 'character' (count=%d)", n)
	}
}
