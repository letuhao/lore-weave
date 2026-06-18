package migrate

// D-WIKI-SEED-ROBUSTNESS — Seed must be PER-KIND idempotent: a pre-existing kind
// (e.g. the system 'unknown' inserted in Up, or a leftover kind on a shared test DB)
// must NOT make the 12 default kinds skip seeding. Needs GLOSSARY_TEST_DB_URL.

import (
	"context"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

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
		`INSERT INTO entity_kinds(code,name,icon,color,is_default,is_hidden,sort_order)
		 VALUES('zzz_seed_precond','Precond','x','#ffffff',false,true,9998)
		 ON CONFLICT (code) DO NOTHING`,
	); err != nil {
		t.Fatalf("seed precond kind: %v", err)
	}
	t.Cleanup(func() { pool.Exec(ctx, `DELETE FROM entity_kinds WHERE code='zzz_seed_precond'`) })

	if err := Seed(ctx, pool); err != nil {
		t.Fatalf("Seed: %v", err)
	}
	// A default kind (character) must be present despite the pre-existing kind.
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM entity_kinds WHERE code='character'`).Scan(&n); err != nil {
		t.Fatalf("count character: %v", err)
	}
	if n != 1 {
		t.Fatalf("default 'character' not seeded despite a pre-existing kind (count=%d)", n)
	}
	// Its system attribute defs were seeded too (per-kind reconcile, not just the row).
	var attrs int
	pool.QueryRow(ctx,
		`SELECT count(*) FROM attribute_definitions ad JOIN entity_kinds ek ON ek.kind_id=ad.kind_id WHERE ek.code='character'`,
	).Scan(&attrs)
	if attrs == 0 {
		t.Fatal("character attribute_definitions not seeded")
	}

	// Idempotent: a second Seed neither errors nor duplicates.
	if err := Seed(ctx, pool); err != nil {
		t.Fatalf("re-Seed: %v", err)
	}
	pool.QueryRow(ctx, `SELECT count(*) FROM entity_kinds WHERE code='character'`).Scan(&n)
	if n != 1 {
		t.Fatalf("re-Seed duplicated 'character' (count=%d)", n)
	}
}
