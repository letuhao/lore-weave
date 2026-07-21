package migrate

import (
	"strings"
	"testing"
)

// P1 (2026-05-23) — regression lock for the parts/scenes schema additions.
// Pure string check; real live-DB validation runs at VERIFY (Alice EPUB smoke).
// Catches accidental removal during refactors.
//
// db-safety-gate: file-ok — asserts migration DDL text (schema + down-SQL strings) with
// strings.Contains/Index; this file executes NO statement against any database. The live
// DB-gated tests are the separate *_db_test.go files (testsafe-guarded).

// C-merge C4 — the parts table is RETIRED. schemaSQL must NOT create it, and the one-time drop must
// retire the pre-existing table + chapters.part_id (structure_node_id is the SSOT link now).
func TestSchemaRetiresPartsTable(t *testing.T) {
	if strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS parts") {
		t.Fatal("schemaSQL still creates the retired parts table — C4 removed it")
	}
	for _, drop := range []string{
		"ALTER TABLE chapters DROP COLUMN IF EXISTS part_id",
		"DROP TABLE IF EXISTS parts CASCADE",
	} {
		if !strings.Contains(c4DropPartsSQL, drop) {
			t.Fatalf("c4DropPartsSQL missing retire step: %q", drop)
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

// P2·F review MED-3 — pin the tenant_access_audit coalesce index columns. The api
// insert's ON CONFLICT tuple must match THIS index exactly, or a real insert raises
// "no unique constraint matching" at runtime. Book has no real-PG harness (glossary
// proves the live effect), so this string guard + the api-package ON-CONFLICT-tuple
// assertion together lock the two sides so they can't drift apart silently.
func TestSchemaTenantAuditCoalesceIndex(t *testing.T) {
	for _, want := range []string{
		"CREATE TABLE IF NOT EXISTS tenant_access_audit",
		"outcome         TEXT NOT NULL CHECK (outcome IN ('granted','denied'))",
		"CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_audit_window",
		"ON tenant_access_audit (actor_id, book_id, outcome, coalesce_bucket)",
		"REVOKE UPDATE, DELETE ON TABLE tenant_access_audit FROM app_service_role",
	} {
		if !strings.Contains(tenantAuditSQL, want) {
			t.Fatalf("tenantAuditSQL missing required clause: %q", want)
		}
	}
}

func TestSchemaAddsChaptersStructuralPathAndStructureNode(t *testing.T) {
	for _, alter := range []string{
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structural_path TEXT",
		// C-merge: the chapter→structure link (no FK — cross-service id). part_id is retired (C4).
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structure_node_id UUID",
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
		"idx_chapters_structure_node", // C-merge (part_id index retired at C4)
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

// ── WS-0.2 publish-independent KG indexing — 2026-07-11 ─────────────────────

func TestSchemaAddsKGIndexingColumns(t *testing.T) {
	for _, frag := range []string{
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS kg_indexed_revision_id UUID",
		"ALTER TABLE chapters ADD COLUMN IF NOT EXISTS kg_exclude BOOLEAN NOT NULL DEFAULT false",
		"CREATE INDEX IF NOT EXISTS idx_chapters_kg_indexed",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("WS-0.2 schema missing: %q", frag)
		}
	}
}

// kg_indexed_revision_id must be a PLAIN UUID with NO foreign key — deliberately
// mirroring last_parsed_revision_id, NOT published_revision_id.
//
// published_revision_id's FK is `ON DELETE SET NULL`. If the KG pointer carried the
// same FK, a revision purge (GC of old chapter_revisions) would silently NULL it —
// i.e. silently UN-INDEX the chapter from the knowledge graph, with no event and no
// way to notice. A dangling plain UUID instead just re-triggers a heal on the next
// sweep, which is the same dangling-safe rationale last_parsed_revision_id documents.
func TestKGIndexedRevisionHasNoForeignKey(t *testing.T) {
	i := strings.Index(schemaSQL, "ADD COLUMN IF NOT EXISTS kg_indexed_revision_id")
	if i == -1 {
		t.Fatal("kg_indexed_revision_id ALTER not found")
	}
	// The statement ends at the first semicolon after the column name.
	stmt := schemaSQL[i:]
	if j := strings.Index(stmt, ";"); j != -1 {
		stmt = stmt[:j]
	}
	if strings.Contains(strings.ToUpper(stmt), "REFERENCES") {
		t.Fatalf("kg_indexed_revision_id must NOT have an FK (a revision purge with "+
			"ON DELETE SET NULL would silently un-index the chapter): %q", stmt)
	}
}

// The backfill must be marker-gated so it runs EXACTLY ONCE. An ungated re-run would
// re-set kg_indexed_revision_id on a chapter whose kg_exclude retraction had cleared
// it — silently pulling a chapter the user removed from their KG back into it on the
// next restart. (The live proof is TestKGIndexedBackfillIsMarkerGatedAnd... in
// kg_indexed_db_test.go; this is the cheap static lock.)
func TestKGIndexedBackfillIsMarkerGated(t *testing.T) {
	for _, frag := range []string{
		"canon_model_migration WHERE id = 'kg_indexed_backfill_v1'",
		"INSERT INTO canon_model_migration (id) VALUES ('kg_indexed_backfill_v1')",
		"kg_exclude            = false", // belt-and-braces guard inside the UPDATE
	} {
		if !strings.Contains(kgIndexedBackfillSQL, frag) {
			t.Fatalf("kg_indexed backfill missing marker/guard: %q", frag)
		}
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
	// Scoped to the BOOKS column: world_maps.world_id (W10-M2) is legitimately
	// `NOT NULL REFERENCES worlds(id) ON DELETE CASCADE` — a map MUST belong to a
	// world and is dropped with it — so the lock check must not naively match any
	// `world_id UUID NOT NULL` / `REFERENCES worlds(id) ON DELETE CASCADE` in the schema.
	if strings.Contains(schemaSQL, "books ADD COLUMN IF NOT EXISTS world_id UUID NOT NULL") {
		t.Fatal("books.world_id must be NULLABLE (default NULL = standalone) — NOT NULL is a LOCK breach")
	}
	// The books FK is asserted `ON DELETE SET NULL` by the fragment check above; a
	// regression to a books cascade would drop that fragment (already a failure).
	if strings.Contains(schemaSQL, "books ADD COLUMN IF NOT EXISTS world_id UUID\n  REFERENCES worlds(id) ON DELETE CASCADE") {
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

// ── Chapter Browser CB3 (word_count) - 2026-07-04 ───────────────────────────
// Regression lock for the word_count column, its batched backfill marker
// table, and the recompute trigger/function. Real-PG trigger behavior (CJK
// vs Latin counting, insert/update/delete recompute) is covered by the
// DB-gated tests in the api package (word_count_db_test.go); these are pure
// string checks so they run on a machine with no DB.

func TestSchemaAddsWordCountColumn(t *testing.T) {
	if !strings.Contains(schemaSQL, "ALTER TABLE chapters ADD COLUMN IF NOT EXISTS word_count INT NOT NULL DEFAULT 0") {
		t.Fatal("chapters missing word_count column, or it isn't NOT NULL DEFAULT 0 (backward-compat requirement — existing rows must never end up NULL)")
	}
	if !strings.Contains(schemaSQL, "CREATE TABLE IF NOT EXISTS word_count_backfill_migration") {
		t.Fatal("schemaSQL missing word_count_backfill_migration marker table")
	}
}

func TestTriggerContainsWordCountFunctions(t *testing.T) {
	for _, frag := range []string{
		"CREATE OR REPLACE FUNCTION fn_word_count_for_text(_text TEXT, _lang TEXT)",
		"CREATE OR REPLACE FUNCTION fn_recompute_chapter_word_count()",
		"CREATE TRIGGER trg_recompute_chapter_word_count",
		"AFTER INSERT OR DELETE OR UPDATE OF text_content ON chapter_blocks",
	} {
		if !strings.Contains(triggerSQL, frag) {
			t.Fatalf("triggerSQL missing word_count fragment: %q", frag)
		}
	}
}

// The trigger must be restricted to `UPDATE OF text_content` — NOT a bare
// `UPDATE ON chapter_blocks` — so fn_extract_chapter_blocks' 3rd internal
// statement (heading_context-only UPDATE) doesn't trigger a redundant
// recompute of every chapter on every draft save.
func TestWordCountTriggerRestrictedToTextContentUpdates(t *testing.T) {
	if strings.Contains(triggerSQL, "AFTER INSERT OR UPDATE OR DELETE ON chapter_blocks") {
		t.Fatal("trg_recompute_chapter_word_count must not fire on bare UPDATE (heading_context-only changes) — restrict to UPDATE OF text_content")
	}
}

// CJK detection must reuse the exact Unicode ranges from useBookReaderContent.ts'
// CJK_REGEX (CJK Unified Ideographs U+3000-9FFF, Hangul U+AC00-D7AF, fullwidth
// forms U+FF00-FFEF) — a drifted range would silently miscount for some scripts.
func TestWordCountCJKRangesMatchFrontendRegex(t *testing.T) {
	if !strings.Contains(triggerSQL, "[　-鿿가-힯＀-￯]") {
		t.Fatal("fn_word_count_for_text's CJK character class must match useBookReaderContent.ts' CJK_REGEX exactly")
	}
	if !strings.Contains(triggerSQL, "_lang IN ('ja', 'zh', 'ko')") {
		t.Fatal("fn_word_count_for_text must also treat ja/zh/ko chapter language as CJK, mirroring computeReadingStats")
	}
}

// Idempotency: the CB3 additions must use IF NOT EXISTS / OR REPLACE so an
// Up() re-run is a no-op (book-service has no migration ledger).
func TestSchemaWordCountAdditionsAreIdempotent(t *testing.T) {
	const sentinel = "Chapter Browser CB3 (word_count) - 2026-07-04"
	idx := strings.Index(schemaSQL, sentinel)
	if idx == -1 {
		t.Fatal("CB3 sentinel not found in schemaSQL")
	}
	region := schemaSQL[idx:]
	for _, line := range strings.Split(region, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "CREATE TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("CB3 region has non-idempotent CREATE TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "ALTER TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("CB3 region has non-idempotent ALTER TABLE: %q", trimmed)
		}
	}
}

// ── Scene model 22-A1 (scenes book scope + source map) - 2026-07-10 ──────────
// Regression lock for the three scenes columns (book_id/title/source_scene_id),
// the two indexes, and the batched-backfill marker table (spec 22 §SC1/SC2/SC5).
// The scenes ALTERs + indexes had ZERO coverage. Pure string checks (no DB) in the
// P1/CB3 house style; real-PG backfill behavior is covered by the api package's
// DB-gated scenes tests.

func TestSchemaScene22A1Columns(t *testing.T) {
	for _, frag := range []string{
		"ALTER TABLE scenes ADD COLUMN IF NOT EXISTS book_id UUID",
		"ALTER TABLE scenes ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''",
		"ALTER TABLE scenes ADD COLUMN IF NOT EXISTS source_scene_id UUID",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("scenes 22-A1 column ALTER missing: %q", frag)
		}
	}
	// SC1: book_id is a direct book-scope FK, cascade-deleted with the book.
	if !strings.Contains(schemaSQL,
		"ALTER TABLE scenes ADD COLUMN IF NOT EXISTS book_id UUID\n  REFERENCES books(id) ON DELETE CASCADE") {
		t.Fatal("scenes.book_id must be a REFERENCES books(id) ON DELETE CASCADE FK (SC1)")
	}
	// SC1: the added book_id must be NULLABLE (backfilled from chapters.book_id by
	// the batched marker-gated backfill) — a NOT NULL add would break existing rows.
	if strings.Contains(schemaSQL, "ADD COLUMN IF NOT EXISTS book_id UUID NOT NULL") {
		t.Fatal("scenes.book_id must be added NULLABLE (backfilled), never NOT NULL")
	}
}

func TestSchemaScene22A1Indexes(t *testing.T) {
	for _, frag := range []string{
		"CREATE INDEX IF NOT EXISTS idx_scenes_book_active",
		"ON scenes(book_id, chapter_id, sort_order) WHERE lifecycle_state = 'active'",
		"CREATE INDEX IF NOT EXISTS idx_scenes_source",
		"ON scenes(source_scene_id) WHERE source_scene_id IS NOT NULL",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("scenes 22-A1 index missing: %q", frag)
		}
	}
}

func TestSchemaScenesBackfillMarkerTable(t *testing.T) {
	for _, frag := range []string{
		"CREATE TABLE IF NOT EXISTS scenes_book_id_backfill_migration",
		"id         TEXT PRIMARY KEY",
		"applied_at TIMESTAMPTZ NOT NULL DEFAULT now()",
	} {
		if !strings.Contains(schemaSQL, frag) {
			t.Fatalf("scenes backfill marker table missing: %q", frag)
		}
	}
}

// SC5 inversion dropped the 'origin' column (every scenes row is parser output, so
// the column would be a constant). A future agent must not re-add it. "origin"
// appears legitimately in the 22-A1 COMMENT ("NO 'origin' column"), so scope the
// check to the scenes CREATE TABLE body + the scenes ALTERs, not the whole schema.
func TestSchemaScenesHasNoOriginColumn(t *testing.T) {
	start := strings.Index(schemaSQL, "CREATE TABLE IF NOT EXISTS scenes (")
	if start == -1 {
		t.Fatal("scenes CREATE TABLE not found in schemaSQL")
	}
	body := schemaSQL[start:]
	if end := strings.Index(body, ");"); end != -1 {
		body = body[:end]
	}
	for _, line := range strings.Split(body, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "origin") {
			t.Fatalf("scenes must NOT have an 'origin' column (dropped by the SC5 inversion): %q", line)
		}
	}
	if strings.Contains(schemaSQL, "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS origin") {
		t.Fatal("scenes 'origin' column must not be re-added via ALTER (SC5 inversion)")
	}
}

// Idempotency: every 22-A1 CREATE/ALTER uses IF NOT EXISTS so an Up() re-run is a
// no-op (book-service has no migration ledger). The region runs from the sentinel
// to the end of schemaSQL (22-A1 is the last block in it).
func TestSchemaScene22A1AdditionsAreIdempotent(t *testing.T) {
	const sentinel = "Scene model 22-A1 - 2026-07-10"
	idx := strings.Index(schemaSQL, sentinel)
	if idx == -1 {
		t.Fatal("22-A1 sentinel not found in schemaSQL")
	}
	region := schemaSQL[idx:]
	for _, line := range strings.Split(region, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "CREATE TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("22-A1 region has non-idempotent CREATE TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "ALTER TABLE") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("22-A1 region has non-idempotent ALTER TABLE: %q", trimmed)
		}
		if strings.HasPrefix(trimmed, "CREATE INDEX") && !strings.Contains(trimmed, "IF NOT EXISTS") {
			t.Fatalf("22-A1 region has non-idempotent CREATE INDEX: %q", trimmed)
		}
	}
}
