package migrate

// C4 / SD-C4 (D-WIKI-PERSON-FLAG) — seed-drift + backfill test for the structural is_person flag.
//
// What must hold after the full ledger chain (step 0054):
//   - the is_person column exists on all three kind tiers (system/user/book);
//   - the seeded REAL-person work kind 'colleague' is is_person=TRUE (system tier);
//   - fiction 'character' is is_person=FALSE (human-amended scope: is_person = REAL person only —
//     a fiction character MUST still get an AI wiki page, so it must NOT be flagged);
//   - the OTHER work kinds (project/meeting/decision/task/jargon/org) are is_person=FALSE (only
//     colleague is a person — 'org' is an organization, not a person, and must stay wiki-eligible);
//   - it is idempotent (a second chain run does not flip anything).
//
// Runs on its own ephemeral DB. Needs GLOSSARY_TEST_DB_URL.
//
// db-safety-gate: file-ok — the DROP DATABASE statements target a THROWAWAY ephemeral DB
// this test CREATEs itself (unique name + PID) via CREATE DATABASE and drops on cleanup;
// they never target the DB named in GLOSSARY_TEST_DB_URL (safe by construction).

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestKindIsPerson_SeedDrift_RealPersonOnly(t *testing.T) {
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

	ephemeral := fmt.Sprintf("glossary_isperson_%d", os.Getpid())
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

	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain: %v", err)
	}

	boolOf := func(q string, args ...any) bool {
		t.Helper()
		var b bool
		if err := pool.QueryRow(ctx, q, args...).Scan(&b); err != nil {
			t.Fatalf("query %q: %v", q, err)
		}
		return b
	}

	// The column exists on all three tiers (a bad ALTER would error here, not just return false).
	for _, tbl := range []string{"system_kinds", "user_kinds", "book_kinds"} {
		var n int
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM information_schema.columns WHERE table_name=$1 AND column_name='is_person'`,
			tbl).Scan(&n); err != nil {
			t.Fatalf("column check %s: %v", tbl, err)
		}
		if n != 1 {
			t.Fatalf("%s.is_person column missing (count=%d)", tbl, n)
		}
	}

	// colleague = TRUE (the real work-person kind), character = FALSE (fiction must still wiki-gen).
	if !boolOf(`SELECT is_person FROM system_kinds WHERE code='colleague'`) {
		t.Error("colleague must be is_person=TRUE (a real person)")
	}
	if boolOf(`SELECT is_person FROM system_kinds WHERE code='character'`) {
		t.Error("fiction 'character' must be is_person=FALSE — else it would be excluded from AI wiki-gen")
	}

	// No OTHER work kind is a person (org is an organization, not a person; it must stay wiki-eligible).
	var leaked int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM system_kinds WHERE is_person AND code <> 'colleague'`).Scan(&leaked); err != nil {
		t.Fatalf("leak check: %v", err)
	}
	if leaked != 0 {
		t.Errorf("%d non-colleague kind(s) wrongly flagged is_person — only colleague is a real person", leaked)
	}

	// The ledger recorded the step; a second run is idempotent (colleague stays true, character false).
	var recorded int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM schema_migrations WHERE name='0054_kind_is_person'`).Scan(&recorded); err != nil {
		t.Fatalf("ledger check: %v", err)
	}
	if recorded != 1 {
		t.Fatalf("ledger did not record 0054_kind_is_person (count=%d)", recorded)
	}
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("second RunChain: %v", err)
	}
	if !boolOf(`SELECT is_person FROM system_kinds WHERE code='colleague'`) {
		t.Error("colleague is_person flipped on re-run (not idempotent)")
	}
	if boolOf(`SELECT is_person FROM system_kinds WHERE code='character'`) {
		t.Error("character is_person flipped on re-run (not idempotent)")
	}
}
