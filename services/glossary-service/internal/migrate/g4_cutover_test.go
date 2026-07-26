package migrate

// G4 regression — the cutover's TRUNCATE must run EXACTLY ONCE per database.
// Migrations re-run on every service boot and execGuarded has no applied-ledger, so
// an unguarded `TRUNCATE glossary_entities CASCADE` in the cutover would wipe ALL
// entities + wiki on every restart (catastrophic production data loss). This proves
// the guard: after the cutover, seed an entity, re-run the cutover (simulating a
// second boot), and assert the entity SURVIVES. Needs GLOSSARY_TEST_DB_URL.
//
// db-safety-gate: file-ok — the DROP DATABASE statements target a THROWAWAY ephemeral DB
// ephemeralPool CREATEs itself (unique name + PID, proven throwaway via
// testsafe.EnsureThrowawayDB) and drops on cleanup — never the DB in GLOSSARY_TEST_DB_URL.
// The `TRUNCATE glossary_entities CASCADE` mentioned above is prose in this doc comment,
// not an executed statement.

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/testsafe"
)

func ephemeralPool(t *testing.T, tag string) *pgxpool.Pool {
	t.Helper()
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

	name := fmt.Sprintf("glossary_%s_tmp_%d", tag, os.Getpid())
	// Layer-3 safety guard (mirrors book-service testsafe): refuse to CREATE/DROP unless
	// the target is a recognizable throwaway DB, so a broken ephemeral setup can never
	// destroy a real service DB — the pool handed back is proven throwaway before any DDL.
	if err := testsafe.EnsureThrowawayDB(name); err != nil {
		t.Fatal(err)
	}
	_, _ = admin.Exec(ctx, `DROP DATABASE IF EXISTS `+pgx.Identifier{name}.Sanitize()+` WITH (FORCE)`)
	if _, err := admin.Exec(ctx, `CREATE DATABASE `+pgx.Identifier{name}.Sanitize()); err != nil {
		t.Fatalf("create ephemeral db: %v", err)
	}
	t.Cleanup(func() {
		c, err := pgxpool.New(context.Background(), maint.String())
		if err != nil {
			return
		}
		defer c.Close()
		_, _ = c.Exec(context.Background(), `DROP DATABASE IF EXISTS `+pgx.Identifier{name}.Sanitize()+` WITH (FORCE)`)
	})

	target := *base
	target.Path = "/" + name
	pool, err := pgxpool.New(ctx, target.String())
	if err != nil {
		t.Fatalf("ephemeral pool: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestGlossaryCutoverG4_GuardPreventsRepeatTruncate(t *testing.T) {
	pool := ephemeralPool(t, "g4cut")
	ctx := context.Background()

	// Minimal production-order chain up to + including the cutover.
	for _, m := range []struct {
		name string
		fn   func(context.Context, *pgxpool.Pool) error
	}{
		{"Up", Up}, {"Seed", Seed}, {"UpSnapshot", UpSnapshot}, {"UpSoftDelete", UpSoftDelete},
		{"UpUserKinds", UpUserKinds}, {"UpGenreKindAttr", UpGenreKindAttr},
		{"SeedGenreKindAttr", SeedGenreKindAttr}, {"UpGlossaryCutoverG4", UpGlossaryCutoverG4},
	} {
		if err := m.fn(ctx, pool); err != nil {
			t.Fatalf("%s: %v", m.name, err)
		}
	}

	// Scaffold a minimal book ontology + one entity on the BOOK tier.
	bookID := uuid.New()
	var genreID, bookKindID, entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO book_genres(book_id,code,name) VALUES($1,'universal','Universal') RETURNING genre_id`,
		bookID).Scan(&genreID); err != nil {
		t.Fatalf("seed book genre: %v", err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO book_active_genres(book_id,genre_id) VALUES($1,$2)`, bookID, genreID); err != nil {
		t.Fatalf("activate genre: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO book_kinds(book_id,code,name) VALUES($1,'character','Character') RETURNING book_kind_id`,
		bookID).Scan(&bookKindID); err != nil {
		t.Fatalf("seed book kind: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags) VALUES($1,$2,'active','{}') RETURNING entity_id`,
		bookID, bookKindID).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}

	// Re-run the cutover — simulates a second service boot. The guard must skip the
	// TRUNCATE (the old system_kinds FK is already gone), so the entity survives.
	if err := UpGlossaryCutoverG4(ctx, pool); err != nil {
		t.Fatalf("re-run cutover: %v", err)
	}
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&n); err != nil {
		t.Fatalf("count entity: %v", err)
	}
	if n != 1 {
		t.Fatalf("entity wiped by cutover re-run (TRUNCATE guard failed): want 1, got %d", n)
	}

	// Sanity: the FK was repointed to book_kinds (the cutover did happen).
	var fk bool
	if err := pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='glossary_entities_kind_id_book_fkey')`).Scan(&fk); err != nil {
		t.Fatalf("fk check: %v", err)
	}
	if !fk {
		t.Fatal("book-tier FK glossary_entities_kind_id_book_fkey missing — cutover did not complete")
	}
}
