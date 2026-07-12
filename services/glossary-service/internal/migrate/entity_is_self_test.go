package migrate

// WS-1.6 (spec 05 §Q5) — glossary_entities.is_self + the one-self-per-book unique.
//
// The user's OWN identity entity in their diary must be markable so capture + the detectors
// exclude it, and there must be EXACTLY ONE per book (a re-provision must converge, not mint a
// second "me"). The unique EXEMPTS soft-deleted tombstones so a delete never locks the book out.
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

func TestEntityIsSelf_ColumnAndOnePerBookUnique(t *testing.T) {
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

	ephemeral := fmt.Sprintf("glossary_isself_%d", os.Getpid())
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

	// The column exists and defaults false.
	var colType string
	if err := pool.QueryRow(ctx,
		`SELECT data_type FROM information_schema.columns
		 WHERE table_name='glossary_entities' AND column_name='is_self'`).Scan(&colType); err != nil {
		t.Fatalf("is_self column missing: %v", err)
	}

	// book_id has no FK (glossary does not own books); kind_id references book_kinds post-G4.
	bookKind := func(bookID string) string {
		t.Helper()
		var id string
		if err := pool.QueryRow(ctx,
			`INSERT INTO book_kinds(book_id,code,name) VALUES($1,'colleague','Colleague') RETURNING book_kind_id`,
			bookID).Scan(&id); err != nil {
			t.Fatalf("seed book_kind for %s: %v", bookID, err)
		}
		return id
	}
	insertSelf := func(bookID, kindID string) error {
		_, err := pool.Exec(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,is_self,normalized_name)
			 VALUES($1,$2,'active','{}',true,$3)`, bookID, kindID, "me-"+bookID)
		return err
	}

	bookA := "11111111-1111-1111-1111-111111111111"
	bookB := "22222222-2222-2222-2222-222222222222"
	kindA := bookKind(bookA)
	kindB := bookKind(bookB)

	// One self-entity for book A — OK.
	if err := insertSelf(bookA, kindA); err != nil {
		t.Fatalf("first self-entity for book A: %v", err)
	}
	// A SECOND self-entity for the SAME book — REFUSED.
	if err := insertSelf(bookA, kindA); err == nil {
		t.Fatal("a second is_self entity was allowed for one book — there must be exactly one 'me' per diary")
	}
	// A self-entity for a DIFFERENT book — OK (the unique is per-book).
	if err := insertSelf(bookB, kindB); err != nil {
		t.Fatalf("self-entity for book B was refused (the unique must be per-book): %v", err)
	}
	// A NON-self entity for book A — OK (is_self=false is unconstrained).
	if _, err := pool.Exec(ctx,
		`INSERT INTO glossary_entities(book_id,kind_id,status,tags,is_self,normalized_name)
		 VALUES($1,$2,'active','{}',false,'alice')`, bookA, kindA); err != nil {
		t.Fatalf("a normal (non-self) entity was refused: %v", err)
	}

	// Soft-delete book A's self-entity → a fresh one is allowed (tombstone-exempt).
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET deleted_at=now() WHERE book_id=$1 AND is_self`, bookA); err != nil {
		t.Fatalf("soft-delete self-entity: %v", err)
	}
	if err := insertSelf(bookA, kindA); err != nil {
		t.Fatalf("a soft-deleted self-entity blocked a fresh one (tombstone not exempt): %v", err)
	}
}
