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
