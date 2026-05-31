package api

// Tests for the lore-enrichment supplement layer (F-C13-1 + F-C13-2 / B1):
//   - T1: the entity_enrichments migration creates the table + H0 constraints.
//   - T2: POST/DELETE /internal/.../enrichments handlers (added below).
//
// Unit tests (no DB) run always. DB integration tests require
// GLOSSARY_TEST_DB_URL and skip otherwise (openTestDB).

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// runEnrichmentMigrations applies the full chain the enrichment supplement path
// needs: the canon-content chain (base + outbox + short-desc, so glossary
// entities + the emit insert work) PLUS UpEntityEnrichments (the table itself).
func runEnrichmentMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	runCanonContentMigrations(t, pool)
	if err := migrate.UpEntityEnrichments(context.Background(), pool); err != nil {
		t.Fatalf("migrate.UpEntityEnrichments: %v", err)
	}
}

// ── T1: schema shape ────────────────────────────────────────────────────────

// TestEntityEnrichments_MigrationCreatesTable proves the migration creates the
// table and its live-read partial index on a fresh DB.
func TestEntityEnrichments_MigrationCreatesTable(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runEnrichmentMigrations(t, pool)

	var tableExists bool
	pool.QueryRow(ctx, `SELECT EXISTS (
		SELECT 1 FROM information_schema.tables
		WHERE table_name = 'entity_enrichments')`).Scan(&tableExists)
	if !tableExists {
		t.Fatal("entity_enrichments table was not created")
	}

	var idxExists bool
	pool.QueryRow(ctx, `SELECT EXISTS (
		SELECT 1 FROM pg_indexes
		WHERE indexname = 'idx_entity_enrichments_live')`).Scan(&idxExists)
	if !idxExists {
		t.Error("idx_entity_enrichments_live partial index was not created")
	}
}

// TestEntityEnrichments_RejectsCanonConfidence is an H0 backstop: a supplement
// row can NEVER carry canon confidence (1.0). The CHECK fires at the DB layer
// regardless of what any app/handler does.
func TestEntityEnrichments_RejectsCanonConfidence(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runEnrichmentMigrations(t, pool)
	eid := seedIdentityOnlyEntity(t, pool, "00000000-0000-0000-0002-000000000001", "蓬萊")

	_, err := pool.Exec(ctx,
		`INSERT INTO entity_enrichments(entity_id,book_id,dimension,content,technique,confidence,proposal_id)
		 VALUES($1,$2,'历史','x','retrieval',1.0,$3)`,
		eid, "00000000-0000-0000-0002-000000000001", "00000000-0000-0000-0002-0000000000aa")
	if err == nil {
		t.Fatal("INSERT with confidence=1.0 must be rejected by the H0 CHECK, but it succeeded")
	}
}

// TestEntityEnrichments_RejectsGlossaryOrigin is an H0 backstop: a supplement
// row's origin can never be the canon origin ('glossary').
func TestEntityEnrichments_RejectsGlossaryOrigin(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runEnrichmentMigrations(t, pool)
	eid := seedIdentityOnlyEntity(t, pool, "00000000-0000-0000-0002-000000000002", "蓬萊")

	_, err := pool.Exec(ctx,
		`INSERT INTO entity_enrichments(entity_id,book_id,dimension,content,origin,technique,confidence,proposal_id)
		 VALUES($1,$2,'历史','x','glossary','retrieval',0.30,$3)`,
		eid, "00000000-0000-0000-0002-000000000002", "00000000-0000-0000-0002-0000000000ab")
	if err == nil {
		t.Fatal("INSERT with origin='glossary' must be rejected by the H0 CHECK, but it succeeded")
	}
}

// TestEntityEnrichments_AllowsMultipleVariantsPerDimension proves the `dị bản`
// model: two DIFFERENT proposals may both enrich the same (entity, dimension)
// — but the SAME proposal cannot duplicate a (entity, dimension) row.
func TestEntityEnrichments_AllowsMultipleVariantsPerDimension(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runEnrichmentMigrations(t, pool)
	bookID := "00000000-0000-0000-0002-000000000003"
	eid := seedIdentityOnlyEntity(t, pool, bookID, "蓬萊")

	ins := func(proposalID string) error {
		_, err := pool.Exec(ctx,
			`INSERT INTO entity_enrichments(entity_id,book_id,dimension,content,technique,confidence,proposal_id)
			 VALUES($1,$2,'历史','变体','retrieval',0.30,$3)`,
			eid, bookID, proposalID)
		return err
	}

	if err := ins("00000000-0000-0000-0002-0000000000b1"); err != nil {
		t.Fatalf("first variant insert failed: %v", err)
	}
	// Different proposal, same (entity, dimension) → allowed (a second `dị bản`).
	if err := ins("00000000-0000-0000-0002-0000000000b2"); err != nil {
		t.Fatalf("second variant (different proposal) must be allowed: %v", err)
	}
	// Same proposal again, same (entity, dimension) → UNIQUE violation.
	if err := ins("00000000-0000-0000-0002-0000000000b1"); err == nil {
		t.Fatal("duplicate (entity,dimension,proposal_id) must violate the UNIQUE key, but it succeeded")
	}
}
