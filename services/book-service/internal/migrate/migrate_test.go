package migrate

import (
	"strings"
	"testing"
)

// P1 (2026-05-23) — regression lock for the parts/scenes schema additions.
// Pure string check; real live-DB validation runs at VERIFY (Alice EPUB smoke).
// Catches accidental removal during refactors.

func TestSchemaContainsPartsTable(t *testing.T) {
	if !strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS parts") {
		t.Fatal("schemaSQL missing parts table — P1 hierarchical extraction broke")
	}
	for _, col := range []string{
		"book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE",
		"sort_order      INT  NOT NULL",
		"parse_version   INT  NOT NULL DEFAULT 1",
		"lifecycle_state TEXT NOT NULL DEFAULT 'active'",
		"UNIQUE (book_id, sort_order)",
	} {
		if !strings.Contains(schemaSQL, col) {
			t.Fatalf("parts table missing column/constraint: %q", col)
		}
	}
}

func TestSchemaContainsScenesTable(t *testing.T) {
	if !strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS scenes") {
		t.Fatal("schemaSQL missing scenes table — P1 hierarchical extraction broke")
	}
	for _, col := range []string{
		"chapter_id      UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE",
		"leaf_text       TEXT NOT NULL",
		"content_hash    TEXT NOT NULL",
		"parse_version   INT  NOT NULL DEFAULT 1",
		"lifecycle_state TEXT NOT NULL DEFAULT 'active'",
		"UNIQUE (chapter_id, sort_order)",
	} {
		if !strings.Contains(schemaSQL, col) {
			t.Fatalf("scenes table missing column/constraint: %q", col)
		}
	}
}

func TestSchemaAddsChaptersPartAndStructuralPath(t *testing.T) {
	for _, alter := range []string{
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS part_id UUID",
		"REFERENCES parts(id) ON DELETE SET NULL",
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structural_path TEXT",
	} {
		if !strings.Contains(schemaSQL, alter) {
			t.Fatalf("chapters table missing ALTER: %q", alter)
		}
	}
}

func TestSchemaP1IndexesPresent(t *testing.T) {
	for _, idx := range []string{
		"idx_scenes_chapter_sort_active",
		"idx_scenes_content_hash",
		"idx_chapters_part",
	} {
		if !strings.Contains(schemaSQL, idx) {
			t.Fatalf("missing P1 index: %q", idx)
		}
	}
}

// Idempotency check: every CREATE/ALTER must use IF NOT EXISTS so a
// startup re-run is a no-op. R4 (closed by R-SELF-1) — no DO blocks for
// backfill; only schema additions.
func TestSchemaP1AdditionsAreIdempotent(t *testing.T) {
	// Extract the P1 region by its sentinel.
	const sentinel = "P1 (hierarchical extraction T1) - 2026-05-23"
	idx := strings.Index(schemaSQL, sentinel)
	if idx == -1 {
		t.Fatal("P1 sentinel not found in schemaSQL")
	}
	region := schemaSQL[idx:]
	// Every CREATE TABLE in the region must be `CREATE TABLE IF NOT EXISTS`.
	for _, line := range strings.Split(region, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "CREATE TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("P1 region has non-idempotent CREATE TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "ALTER TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("P1 region has non-idempotent ALTER TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "CREATE INDEX") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("P1 region has non-idempotent CREATE INDEX: %q", trimmed)
		}
	}
	// R-SELF-1: no DO block (no backfill).
	if strings.Contains(region, "DO $$") {
		t.Fatal("P1 region must not contain DO $$ block — R-SELF-1 mandates no backfill")
	}
}

// ── Canon Model CM1 (editorial lifecycle) - 2026-06-04 ──────────────────────

func TestSchemaAddsCanonEditorialColumns(t *testing.T) {
	for _, frag := range []string{
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS editorial_status TEXT NOT NULL DEFAULT 'draft'",
		"CHECK (editorial_status IN ('draft','published'))",
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS published_revision_id UUID",
		"REFERENCES chapter_revisions(id) ON DELETE SET NULL", // dangling-safe on revision purge (adversary LOW-2)
		"CREATE INDEX IF NOT EXISTS idx_chapters_editorial",
		"CREATE TABLE IF NOT EXISTS canon_model_migration",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("canon CM1 schema missing: %q", frag)
		}
	}
	// in_review must NOT be in the CHECK (YAGNI — dropped at sweep LOW-1).
	if strings.Contains(schemaSQL, "in_review") {
		t.Fatal("editorial_status must be draft|published only — in_review was dropped")
	}
}

// The new chapters ALTERs must be idempotent (IF NOT EXISTS) so Up() re-runs
// cleanly — book-service has NO down-migration (adversary-R1#1), so Up()
// idempotency is the rollback story.
func TestSchemaCanonAltersAreIdempotent(t *testing.T) {
	for _, line := range strings.Split(schemaSQL, "\n") {
		ln := strings.TrimSpace(line)
		if strings.HasPrefix(ln, "ALTER TABLE chapters ADD COLUMN") && strings.Contains(ln, "editorial_status") && !strings.Contains(ln, "IF NOT EXISTS") {
			t.Fatalf("editorial_status ALTER missing IF NOT EXISTS: %q", ln)
		}
	}
	for _, frag := range []string{
		"ADD COLUMN IF NOT EXISTS editorial_status",
		"ADD COLUMN IF NOT EXISTS published_revision_id",
		"CREATE INDEX IF NOT EXISTS idx_chapters_editorial",
		"CREATE TABLE IF NOT EXISTS canon_model_migration",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("non-idempotent or missing canon DDL: %q", frag)
		}
	}
}

// The data backfill MUST be marker-gated so it runs exactly once — else a
// post-CM1 draft chapter that gains revisions gets wrongly auto-published on
// the next restart (the BUILD-time bug the marker closes).
func TestBackfillIsMarkerGatedOneTime(t *testing.T) {
	if !strings.Contains(backfillSQL, "IF NOT EXISTS (SELECT 1 FROM canon_model_migration WHERE id = 'cm1_editorial_backfill')") {
		t.Fatal("backfill must be guarded by the canon_model_migration marker (one-time)")
	}
	if !strings.Contains(backfillSQL, "INSERT INTO canon_model_migration (id) VALUES ('cm1_editorial_backfill')") {
		t.Fatal("backfill must record its marker so a re-run is a no-op")
	}
	for _, frag := range []string{
		"UPDATE chapters c",
		"SET editorial_status     = 'published'",
		"published_revision_id = (",
		"ORDER BY r.created_at DESC",
		"WHERE EXISTS (SELECT 1 FROM chapter_revisions r WHERE r.chapter_id = c.id)",
	} {
		if !strings.Contains(backfillSQL, frag) {
			t.Fatalf("backfill missing expected clause: %q", frag)
		}
	}
}

// ── Raw search Phase 1 (lexical leg) - 2026-06-07 ───────────────────────────
// Regression lock for the pg_trgm extension + GIN trigram index. IF NOT EXISTS
// = idempotent (book-service has no down-migration; Up() re-run is rollback).
func TestRawSearchTrigramMigration(t *testing.T) {
	if !strings.Contains(rawSearchExtensionSQL, "CREATE EXTENSION IF NOT EXISTS pg_trgm") {
		t.Fatalf("raw-search must create pg_trgm idempotently, got %q", rawSearchExtensionSQL)
	}
	for _, frag := range []string{
		"CREATE INDEX IF NOT EXISTS idx_chapter_blocks_trgm",
		"ON chapter_blocks USING gin (text_content gin_trgm_ops)",
	} {
		if !strings.Contains(rawSearchIndexSQL, frag) {
			t.Fatalf("raw-search index DDL missing: %q", frag)
		}
	}
	// review-impl MED-1: pg_trgm DDL must NOT live in schemaSQL — a CREATE
	// EXTENSION failure there aborts the whole schema-init transaction on a
	// restricted-privilege role. It must be a best-effort separate Exec.
	if strings.Contains(schemaSQL, "pg_trgm") {
		t.Fatal("pg_trgm DDL must be best-effort in Up(), not in schemaSQL (review-impl MED-1)")
	}
}
