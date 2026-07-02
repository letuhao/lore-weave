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

// ── C20 (world container) - 2026-06-14 ──────────────────────────────────────
// Regression lock for the worlds table + nullable world_id FK on books + the
// is_bible hidden-chapter flag. Pure string check; real round-trip + live-smoke
// run at VERIFY. Additive (IF NOT EXISTS) — book-service has no down-migration
// ledger; Up() idempotency is the rollback story, WorldsDownSQL is the explicit
// reversible DDL exercised by the VERIFY round-trip (up→down→re-up on real PG).

func TestSchemaContainsWorldsTable(t *testing.T) {
	if !strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS worlds") {
		t.Fatal("schemaSQL missing worlds table — C20 world container broke")
	}
	for _, col := range []string{
		"id UUID PRIMARY KEY DEFAULT uuidv7()",
		"owner_user_id UUID NOT NULL",
		"name TEXT NOT NULL",
		"description TEXT",
		"created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
		"updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
	} {
		if !strings.Contains(schemaSQL, col) {
			t.Fatalf("worlds table missing column: %q", col)
		}
	}
	if !strings.Contains(schemaSQL, "CREATE INDEX IF NOT EXISTS idx_worlds_owner") {
		t.Fatal("worlds missing idx_worlds_owner (owner-scoped list)")
	}
}

// G1 LOCKED: world_id is a NULLABLE FK on books, default NULL, ON DELETE SET NULL.
// Deleting a world SET-NULLs member books (returns them to standalone), NOT cascade.
// The column must be additive (IF NOT EXISTS) so existing world_id=NULL books are
// untouched. A regression to NOT NULL / cascade-delete / backfill is a LOCK breach.
func TestSchemaAddsBooksWorldIDColumn(t *testing.T) {
	for _, frag := range []string{
		"ALTER TABLE books ADD COLUMN IF NOT EXISTS world_id UUID",
		"REFERENCES worlds(id) ON DELETE SET NULL",
		"CREATE INDEX IF NOT EXISTS idx_books_world",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("books world_id DDL missing: %q", frag)
		}
	}
	// MUST NOT be NOT NULL and MUST NOT carry a non-NULL default (no backfill).
	if strings.Contains(schemaSQL, "world_id UUID NOT NULL") {
		t.Fatal("world_id must be NULLABLE (default NULL = standalone) — NOT NULL is a LOCK breach")
	}
	if strings.Contains(schemaSQL, "ON DELETE CASCADE") && strings.Contains(schemaSQL, "REFERENCES worlds(id) ON DELETE CASCADE") {
		t.Fatal("world deletion must SET NULL on member books, never cascade-delete books")
	}
}

// ARCH-REVIEW LOCKED: the auto-created world-bible chapter is HIDDEN. The flag is
// is_bible BOOLEAN DEFAULT false; the lore machinery anchors to this sort_order-0
// chapter. Additive column on chapters.
func TestSchemaAddsChapterIsBibleFlag(t *testing.T) {
	if !strings.Contains(schemaSQL, "ALTER TABLE chapters ADD COLUMN IF NOT EXISTS is_bible BOOLEAN NOT NULL DEFAULT false") {
		t.Fatal("chapters missing is_bible flag — world-bible hidden chapter cannot be marked")
	}
}

// The world-bible CONTAINER book must also carry an is_bible flag so it is hidden
// from the normal library / world book list / counts — else the auto-created
// bible book leaks as a visible junk book (adversary M1).
func TestSchemaAddsBookIsBibleFlag(t *testing.T) {
	if !strings.Contains(schemaSQL, "ALTER TABLE books ADD COLUMN IF NOT EXISTS is_bible BOOLEAN NOT NULL DEFAULT false") {
		t.Fatal("books missing is_bible flag — world-bible container book would leak into the library")
	}
}

// Idempotency: every C20 CREATE/ALTER must use IF NOT EXISTS so an Up() re-run is
// a no-op (book-service has no migration ledger). No DO block / no backfill.
func TestSchemaC20AdditionsAreIdempotent(t *testing.T) {
	const sentinel = "C20 (world container) - 2026-06-14"
	idx := strings.Index(schemaSQL, sentinel)
	if idx == -1 {
		t.Fatal("C20 sentinel not found in schemaSQL")
	}
	region := schemaSQL[idx:]
	for _, line := range strings.Split(region, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "CREATE TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("C20 region has non-idempotent CREATE TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "ALTER TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("C20 region has non-idempotent ALTER TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "CREATE INDEX") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("C20 region has non-idempotent CREATE INDEX: %q", trimmed)
		}
	}
	if strings.Contains(region, "DO $$") {
		t.Fatal("C20 region must not contain a DO $$ block — no backfill (G1 LOCKED)")
	}
}

// WorldsDownSQL must cleanly reverse C20: drop the world_id column FIRST (it
// depends on worlds), then the worlds table. is_bible stays (additive, harmless on
// re-up; dropping it would orphan no FK). Round-trip (up→down→re-up) is exercised
// on real PG at VERIFY; this asserts the DDL ordering so the round-trip can't
// fail on a dangling FK.
func TestWorldsDownSQLOrdering(t *testing.T) {
	for _, frag := range []string{
		"ALTER TABLE books DROP COLUMN IF EXISTS world_id",
		"DROP TABLE IF EXISTS worlds",
	} {
		if !strings.Contains(WorldsDownSQL, frag) {
			t.Fatalf("WorldsDownSQL missing reversible DDL: %q", frag)
		}
	}
	colIdx := strings.Index(WorldsDownSQL, "DROP COLUMN IF EXISTS world_id")
	tblIdx := strings.Index(WorldsDownSQL, "DROP TABLE IF EXISTS worlds")
	if colIdx == -1 || tblIdx == -1 || colIdx > tblIdx {
		t.Fatal("WorldsDownSQL must drop the world_id column BEFORE the worlds table (FK ordering)")
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

// ── MCP fan-out Tier-W single-use confirm-token ledger - 2026-06-20 ─────────
// Regression lock for book_consumed_tokens (/review-impl HIGH). The confirm route
// keys single-use on token_hash (PK); a replay hits the PK and is refused. Mirrors
// provider-registry settings_consumed_tokens. Additive + idempotent (IF NOT EXISTS).
// ── RAID C1 (per-book steering store) - 2026-07-02 ──────────────────────────
// Regression lock for book_steering (DR-C1). Pure string check; real-PG
// coverage runs in the api package's DB-gated steering tests. Additive +
// idempotent — Up() re-run is the rollback story.

func TestSchemaContainsBookSteeringTable(t *testing.T) {
	if !strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS book_steering") {
		t.Fatal("schemaSQL missing book_steering — RAID C1 steering store broke")
	}
	for _, frag := range []string{
		"book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE",
		"body            TEXT NOT NULL CHECK (char_length(body) <= 8000)",
		"CHECK (inclusion_mode IN ('always','scene_match','manual','auto'))",
		"match_pattern   TEXT",
		"enabled         BOOLEAN NOT NULL DEFAULT true",
		"author_user_id  UUID NOT NULL",
		"UNIQUE (book_id, name)",
		"CREATE INDEX IF NOT EXISTS idx_book_steering_book",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("book_steering missing fragment: %q", frag)
		}
	}
	// Tenancy lock: the unique MUST be scoped to book_id — a bare UNIQUE(name)
	// is the shared-mutable-row smell (CLAUDE.md kinds bug).
	if strings.Contains(schemaSQL, "name            TEXT NOT NULL UNIQUE") {
		t.Fatal("book_steering.name must be UNIQUE(book_id, name), never globally unique")
	}
}

// Idempotency: every C1 CREATE in the steering region uses IF NOT EXISTS so an
// Up() re-run is a no-op. No DO block / no backfill.
func TestSchemaC1SteeringAdditionsAreIdempotent(t *testing.T) {
	const sentinel = "RAID C1 (per-book steering store) - 2026-07-02"
	idx := strings.Index(schemaSQL, sentinel)
	if idx == -1 {
		t.Fatal("C1 sentinel not found in schemaSQL")
	}
	region := schemaSQL[idx:]
	for _, line := range strings.Split(region, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "CREATE TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("C1 region has non-idempotent CREATE TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "ALTER TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("C1 region has non-idempotent ALTER TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "CREATE INDEX") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("C1 region has non-idempotent CREATE INDEX: %q", trimmed)
		}
	}
	if strings.Contains(region, "DO $$") {
		t.Fatal("C1 region must not contain a DO $$ block — no backfill")
	}
}

func TestSchemaContainsConsumedTokensTable(t *testing.T) {
	if !strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS book_consumed_tokens") {
		t.Fatal("schemaSQL missing book_consumed_tokens — Tier-W single-use replay guard broke")
	}
	for _, frag := range []string{
		"token_hash  TEXT PRIMARY KEY",
		"consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()",
		"exp         TIMESTAMPTZ",
		"CREATE INDEX IF NOT EXISTS idx_book_consumed_tokens_exp ON book_consumed_tokens(exp)",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("book_consumed_tokens missing fragment: %q", frag)
		}
	}
}
