package migrate

// F1 — system-tier attribute descriptions. Proves UpSystemAttrDescriptions:
//   - sets an extraction-ready description on every authored (kind, attr) cell,
//   - leaves the display-key attrs (name/term) untouched,
//   - recomputes content_hash with the EXACT formula the seed uses (so the new hash
//     equals what a fresh seed-with-description would have produced — the parity G5
//     Sync + adopt depend on),
//   - is idempotent (a re-run changes nothing) and non-clobbering (an admin-authored
//     description survives).
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

func TestSystemAttrDescriptions_SeedsDescriptionsAndRefreshesHash(t *testing.T) {
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

	ephemeral := fmt.Sprintf("glossary_f1_attrdesc_%d", os.Getpid())
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

	// Prerequisite chain up to + including the G1 system-attr seed.
	for _, step := range []struct {
		name string
		fn   func(context.Context, *pgxpool.Pool) error
	}{
		{"Up", Up}, {"Seed", Seed}, {"UpUserKinds", UpUserKinds},
		{"UpGenreKindAttr", UpGenreKindAttr}, {"SeedGenreKindAttr", SeedGenreKindAttr},
	} {
		if err := step.fn(ctx, pool); err != nil {
			t.Fatalf("%s: %v", step.name, err)
		}
	}

	scalar := func(q string, args ...any) int {
		t.Helper()
		var n int
		if err := pool.QueryRow(ctx, q, args...).Scan(&n); err != nil {
			t.Fatalf("query %q: %v", q, err)
		}
		return n
	}
	str := func(q string, args ...any) string {
		t.Helper()
		var s string
		if err := pool.QueryRow(ctx, q, args...).Scan(&s); err != nil {
			t.Fatalf("query %q: %v", q, err)
		}
		return s
	}

	// All 93 seeded system_attributes start with an empty description.
	if n := scalar(`SELECT count(*) FROM system_attributes WHERE COALESCE(TRIM(description),'')=''`); n != 93 {
		t.Fatalf("pre-migration empty descriptions = %d, want 93", n)
	}

	// Capture character.aliases' pre-migration hash (empty-description hash) to prove it moves.
	const charAliasHashQ = `
		SELECT sa.content_hash FROM system_attributes sa
		JOIN system_kinds sk ON sk.kind_id=sa.kind_id
		WHERE sk.code='character' AND sa.code='aliases'`
	preHash := str(charAliasHashQ)

	// Run the F1 migration.
	if err := UpSystemAttrDescriptions(ctx, pool); err != nil {
		t.Fatalf("UpSystemAttrDescriptions: %v", err)
	}

	// Exactly the 81 authored cells now carry a description; the 12 display keys
	// (11 × name + terminology's term) remain empty.
	if n := scalar(`SELECT count(*) FROM system_attributes WHERE COALESCE(TRIM(description),'')<>''`); n != 81 {
		t.Fatalf("post-migration non-empty descriptions = %d, want 81", n)
	}
	if n := scalar(`SELECT count(*) FROM system_attributes WHERE code IN ('name','term') AND COALESCE(TRIM(description),'')<>''`); n != 0 {
		t.Fatalf("%d display-key (name/term) attrs got a description — must be skipped", n)
	}

	// A sample cell carries the authored text.
	wantAliases := "Other names, titles, epithets, or nicknames the character is known by."
	if got := str(`
		SELECT sa.description FROM system_attributes sa
		JOIN system_kinds sk ON sk.kind_id=sa.kind_id
		WHERE sk.code='character' AND sa.code='aliases'`); got != wantAliases {
		t.Fatalf("character.aliases description = %q, want %q", got, wantAliases)
	}

	// content_hash MOVED off the empty-description value …
	postHash := str(charAliasHashQ)
	if postHash == preHash {
		t.Fatalf("content_hash did not change after setting description (G5 Sync would stay blind)")
	}
	// … and equals the EXACT seed formula recomputed over the new description — the
	// parity adopt + Sync rely on (md5(code|name|description|field_type|is_required|options)).
	wantHash := str(`
		SELECT md5(sa.code||'|'||sa.name||'|'||COALESCE(sa.description,'')||'|'||sa.field_type||'|'||
		           (sa.is_required)::text||'|'||COALESCE(array_to_string(sa.options,','),''))
		FROM system_attributes sa
		JOIN system_kinds sk ON sk.kind_id=sa.kind_id
		WHERE sk.code='character' AND sa.code='aliases'`)
	if postHash != wantHash {
		t.Fatalf("content_hash %q != seed-formula hash %q (formula drifted from the seed/attrContentHash)", postHash, wantHash)
	}

	// Idempotent: a second run changes nothing (description guard makes it a no-op).
	if err := UpSystemAttrDescriptions(ctx, pool); err != nil {
		t.Fatalf("re-run UpSystemAttrDescriptions: %v", err)
	}
	if again := str(charAliasHashQ); again != postHash {
		t.Fatalf("re-run mutated content_hash (%q != %q) — not idempotent", again, postHash)
	}
	if n := scalar(`SELECT count(*) FROM system_attributes WHERE COALESCE(TRIM(description),'')<>''`); n != 81 {
		t.Fatalf("re-run changed description count to %d, want 81", n)
	}

	// Non-clobbering: an admin-authored description is never overwritten. Hand-edit one
	// cell to a custom value, clear another back to empty, re-run → only the empty one fills.
	if _, err := pool.Exec(ctx, `
		UPDATE system_attributes sa SET description='ADMIN CUSTOM'
		FROM system_kinds sk WHERE sk.kind_id=sa.kind_id AND sk.code='item' AND sa.code='owner'`); err != nil {
		t.Fatalf("admin-edit item.owner: %v", err)
	}
	if err := UpSystemAttrDescriptions(ctx, pool); err != nil {
		t.Fatalf("re-run after admin edit: %v", err)
	}
	if got := str(`
		SELECT sa.description FROM system_attributes sa
		JOIN system_kinds sk ON sk.kind_id=sa.kind_id
		WHERE sk.code='item' AND sa.code='owner'`); got != "ADMIN CUSTOM" {
		t.Fatalf("admin description clobbered: got %q, want 'ADMIN CUSTOM'", got)
	}
}
