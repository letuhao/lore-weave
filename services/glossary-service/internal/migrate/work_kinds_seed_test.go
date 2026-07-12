package migrate

// WS-1.5 (spec 05 §Q2) — the System-tier WORK ontology seed (ledger step 0052).
//
// What must hold: the 7 work kinds exist after the migration chain; they are HIDDEN + NOT
// default (so a novelist's kind picker never shows them); each has the minimal name/aliases/
// description attrs; and the whole thing is idempotent (a second chain run adds no duplicates).
//
// Runs on its own ephemeral DB. Needs GLOSSARY_TEST_DB_URL.

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var workKindCodes = []string{"colleague", "project", "meeting", "decision", "task", "jargon", "org"}

func TestSeedWorkKinds_HiddenSystemTemplate_Idempotent(t *testing.T) {
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

	ephemeral := fmt.Sprintf("glossary_workkinds_%d", os.Getpid())
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

	// The full ledger chain — proves step 0052 is wired and runs.
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain: %v", err)
	}

	scalar := func(q string, args ...any) int {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx, q, args...).Scan(&n); err != nil {
			t.Fatalf("query %q: %v", q, err)
		}
		return n
	}

	// All 7 work kinds present, and HIDDEN + NOT default (so no novelist picker shows them).
	for _, code := range workKindCodes {
		if n := scalar(`SELECT count(*) FROM system_kinds WHERE code=$1 AND is_hidden AND NOT is_default`, code); n != 1 {
			t.Fatalf("work kind %q not seeded as a hidden non-default system template (count=%d)", code, n)
		}
		// Each is linked to the universal genre and has the minimal name/aliases/description
		// attrs in the tiered system_attributes table (post-G4 model).
		if n := scalar(
			`SELECT count(*) FROM system_kind_genres kg JOIN system_kinds k ON k.kind_id=kg.kind_id
			 JOIN system_genres g ON g.genre_id=kg.genre_id
			 WHERE k.code=$1 AND g.code='universal'`, code); n != 1 {
			t.Fatalf("work kind %q not linked to the universal genre (count=%d)", code, n)
		}
		if n := scalar(
			`SELECT count(*) FROM system_attributes a JOIN system_kinds k ON k.kind_id=a.kind_id
			 WHERE k.code=$1 AND a.code IN ('name','aliases','description')`, code); n != 3 {
			t.Fatalf("work kind %q is missing its name/aliases/description attrs (count=%d)", code, n)
		}
	}

	// The ledger recorded the step.
	if n := scalar(`SELECT count(*) FROM schema_migrations WHERE name='0052_seed_work_kinds'`); n != 1 {
		t.Fatalf("ledger did not record 0052_seed_work_kinds (count=%d)", n)
	}

	// A NOVELIST'S picker (default, non-hidden kinds) must NOT contain any work kind — the
	// whole point of seeding them hidden.
	if n := scalar(
		`SELECT count(*) FROM system_kinds WHERE code = ANY($1) AND is_default AND NOT is_hidden`,
		workKindCodes); n != 0 {
		t.Fatalf("%d work kind(s) leaked into the default/visible picker — they must be hidden templates", n)
	}

	// Idempotent: a second chain run adds no duplicate kinds or attrs.
	before := scalar(`SELECT count(*) FROM system_kinds WHERE code = ANY($1)`, workKindCodes)
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("second RunChain: %v", err)
	}
	after := scalar(`SELECT count(*) FROM system_kinds WHERE code = ANY($1)`, workKindCodes)
	if before != 7 || after != 7 {
		t.Fatalf("work-kind count not stable across re-run: before=%d after=%d, want 7/7", before, after)
	}
}
