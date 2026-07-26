package migrate

// G1 — genre·kind·attribute tiering. Proves UpGenreKindAttr + SeedGenreKindAttr
// build the system-tier standards correctly from the seeded system kinds:
//   - the O3 genre vocabulary (incl. universal + xianxia + mystery),
//   - O4 universal linkage (every kind links to universal),
//   - each kind also links to its declared genre_tags,
//   - every per-kind attribute is lifted into (kind, universal) with a content_hash,
//   - the whole seed is idempotent.
// Runs on its own ephemeral DB for deterministic counts. Needs GLOSSARY_TEST_DB_URL.
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

func TestGenreKindAttr_SeedsTieredStandardsFromSystemKinds(t *testing.T) {
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

	ephemeral := fmt.Sprintf("glossary_g1_gka_%d", os.Getpid())
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

	// Build the prerequisite schema + system-kind seed, then the G1 tables + seed.
	if err := Up(ctx, pool); err != nil {
		t.Fatalf("Up: %v", err)
	}
	if err := Seed(ctx, pool); err != nil {
		t.Fatalf("Seed: %v", err)
	}
	if err := UpUserKinds(ctx, pool); err != nil {
		t.Fatalf("UpUserKinds: %v", err)
	}
	if err := UpGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("UpGenreKindAttr: %v", err)
	}
	if err := SeedGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("SeedGenreKindAttr: %v", err)
	}

	scalar := func(q string, args ...any) int {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx, q, args...).Scan(&n); err != nil {
			t.Fatalf("query %q: %v", q, err)
		}
		return n
	}

	// (O3) the 7 system genres seeded, incl. universal + xianxia + mystery.
	if n := scalar(`SELECT count(*) FROM system_genres`); n != 7 {
		t.Fatalf("system_genres = %d, want 7", n)
	}
	for _, code := range []string{"universal", "fantasy", "xianxia", "romance", "drama", "historical", "mystery"} {
		if n := scalar(`SELECT count(*) FROM system_genres WHERE code=$1`, code); n != 1 {
			t.Fatalf("system genre %q missing (count=%d)", code, n)
		}
	}
	// content_hash populated (non-empty) — Sync depends on it.
	if n := scalar(`SELECT count(*) FROM system_genres WHERE content_hash <> ''`); n != 7 {
		t.Fatalf("system_genres with content_hash = %d, want 7", n)
	}

	// (O4) EVERY system kind links to universal — zero kinds without it.
	if n := scalar(`
		SELECT count(*) FROM system_kinds k
		WHERE NOT EXISTS (
		  SELECT 1 FROM system_kind_genres kg
		  JOIN system_genres g ON g.genre_id = kg.genre_id
		  WHERE kg.kind_id = k.kind_id AND g.code = 'universal')`); n != 0 {
		t.Fatalf("%d system kinds not linked to universal (O4 violated)", n)
	}

	// character (genre_tags={universal}) → exactly 1 link (universal).
	if n := scalar(`
		SELECT count(*) FROM system_kind_genres kg
		JOIN system_kinds k ON k.kind_id = kg.kind_id
		WHERE k.code = 'character'`); n != 1 {
		t.Fatalf("character kind_genres = %d, want 1 (universal)", n)
	}
	// organization (genre_tags={fantasy,drama}) → universal+fantasy+drama = 3 links.
	if n := scalar(`
		SELECT count(*) FROM system_kind_genres kg
		JOIN system_kinds k ON k.kind_id = kg.kind_id
		WHERE k.code = 'organization'`); n != 3 {
		t.Fatalf("organization kind_genres = %d, want 3 (universal+fantasy+drama)", n)
	}

	// character's 13 attrs all lifted into (character, universal), with content_hash.
	charAttrs := scalar(`
		SELECT count(*) FROM system_attributes a
		JOIN system_kinds k  ON k.kind_id  = a.kind_id
		JOIN system_genres g ON g.genre_id = a.genre_id
		WHERE k.code='character' AND g.code='universal'`)
	if charAttrs != 13 {
		t.Fatalf("character×universal attrs = %d, want 13", charAttrs)
	}
	if n := scalar(`SELECT count(*) FROM system_attributes WHERE content_hash = ''`); n != 0 {
		t.Fatalf("%d system_attributes missing content_hash", n)
	}
	// Every lifted attr lives under universal (nothing landed on another genre yet).
	if n := scalar(`
		SELECT count(*) FROM system_attributes a
		JOIN system_genres g ON g.genre_id = a.genre_id
		WHERE g.code <> 'universal'`); n != 0 {
		t.Fatalf("%d system_attributes seeded outside universal (curate pass is deferred)", n)
	}

	// Idempotent: re-running BOTH the migration and the seed neither errors nor
	// duplicates (review-impl finding 3 — assert UpGenreKindAttr re-run directly).
	if err := UpGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("re-UpGenreKindAttr: %v", err)
	}
	if err := SeedGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("re-SeedGenreKindAttr: %v", err)
	}
	if n := scalar(`SELECT count(*) FROM system_genres`); n != 7 {
		t.Fatalf("re-seed changed system_genres count to %d, want 7", n)
	}
	if n := scalar(`
		SELECT count(*) FROM system_attributes a
		JOIN system_kinds k  ON k.kind_id  = a.kind_id
		JOIN system_genres g ON g.genre_id = a.genre_id
		WHERE k.code='character' AND g.code='universal'`); n != charAttrs {
		t.Fatalf("re-seed duplicated character attrs (%d, want %d)", n, charAttrs)
	}
}
