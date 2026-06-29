package api

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// facts_test.go — white-box DB integration test for the bi-temporal fact core
// (spec §12). Gated on GLOSSARY_TEST_DB_URL (skips otherwise, like the other DB
// integration tests). It ensures the migration chain (incl. 0044/0045) is applied,
// then exercises ingestEpisode / appendFact / maintainChain / retractFacts /
// refreshEAVProjection against an EXISTING entity inside a transaction it rolls
// back, so no test data persists. Verifies the §12 properties the spec mandates:
// idempotent append (C2), ordinal-aware chain, projection follows the open fact,
// and retract chain re-stitch (A3) with the projection re-pointing to the predecessor.
func openFactsTestDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dbURL := os.Getenv("GLOSSARY_TEST_DB_URL")
	if dbURL == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set — skipping facts DB integration test")
	}
	pool, err := pgxpool.New(context.Background(), dbURL)
	if err != nil {
		t.Fatalf("openFactsTestDB: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := migrate.RunChain(context.Background(), pool); err != nil {
		t.Fatalf("migrate chain: %v", err)
	}
	return pool
}

func TestFactCore(t *testing.T) {
	ctx := context.Background()
	pool := openFactsTestDB(t)

	// All mutations happen in one tx we roll back — no persisted test data.
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// Find an existing live entity that has a (non-name) book_attribute on its kind,
	// so refreshEAVProjection can resolve attr_def_id.
	var entityID, bookID uuid.UUID
	var chapterID = uuid.New()
	var attr string
	err = tx.QueryRow(ctx, `
		SELECT ge.entity_id, ge.book_id, ba.code
		FROM glossary_entities ge
		JOIN book_attributes ba ON ba.book_id = ge.book_id AND ba.kind_id = ge.kind_id AND ba.deprecated_at IS NULL
		JOIN book_genres g ON g.genre_id = ba.genre_id
		WHERE ge.deleted_at IS NULL AND ba.code <> 'name'
		ORDER BY ge.entity_id, (g.code = 'universal') DESC
		LIMIT 1`).Scan(&entityID, &bookID, &attr)
	if err == pgx.ErrNoRows {
		t.Skip("no seeded entity with a book_attribute — skipping")
	}
	if err != nil {
		t.Fatalf("pick entity: %v", err)
	}

	if err := acquireFactChainLock(ctx, tx, entityID, attr); err != nil {
		t.Fatalf("chain lock: %v", err)
	}

	// ── ingestEpisode: mint then resume (same chapter+hash) ──
	ep1, minted1, err := ingestEpisode(ctx, tx, bookID, chapterID, 50, "hashA", "wbk-1")
	if err != nil || !minted1 {
		t.Fatalf("ingest episode mint: id=%v minted=%v err=%v", ep1, minted1, err)
	}
	ep2, minted2, err := ingestEpisode(ctx, tx, bookID, chapterID, 50, "hashA", "wbk-1")
	if err != nil {
		t.Fatalf("ingest episode resume: %v", err)
	}
	if minted2 || ep2 != ep1 {
		t.Fatalf("episode should RESUME (same id, minted=false): id1=%v id2=%v minted2=%v", ep1, ep2, minted2)
	}

	// ── appendFact: idempotent natural key (C2) ──
	_, ins1, err := appendFact(ctx, tx, appendFactParams{
		BookID: bookID, EntityID: entityID, FactKind: "attribute", Attr: attr,
		Value: "V1", ValidFrom: 10, SourceEpisodeID: &ep1,
	})
	if err != nil || !ins1 {
		t.Fatalf("append V1: inserted=%v err=%v", ins1, err)
	}
	_, ins2, err := appendFact(ctx, tx, appendFactParams{
		BookID: bookID, EntityID: entityID, FactKind: "attribute", Attr: attr,
		Value: "V1", ValidFrom: 10, SourceEpisodeID: &ep1,
	})
	if err != nil {
		t.Fatalf("append V1 dup: %v", err)
	}
	if ins2 {
		t.Fatalf("re-appending identical fact must be idempotent (inserted=false), got inserted=true")
	}

	// ── appendFact V2@200: ordinal-aware chain V1[10,200) V2[200,inf) ──
	if _, _, err := appendFact(ctx, tx, appendFactParams{
		BookID: bookID, EntityID: entityID, FactKind: "attribute", Attr: attr,
		Value: "V2", ValidFrom: 200, SourceEpisodeID: &ep1,
	}); err != nil {
		t.Fatalf("append V2: %v", err)
	}
	assertChain(t, ctx, tx, entityID, attr, []chainRow{{"V1", 10, ptr(200)}, {"V2", 200, nil}})

	// ── projection follows the OPEN fact (V2) ──
	if err := refreshEAVProjection(ctx, tx, entityID, attr); err != nil {
		t.Fatalf("refresh projection: %v", err)
	}
	if got := currentProjection(t, ctx, tx, entityID, attr); got != "V2" {
		t.Fatalf("projection current = %q, want V2", got)
	}

	// ── retract V2 → restitch → V1 reopens; projection re-points to V1 (A3) ──
	v2id := factID(t, ctx, tx, entityID, attr, "V2")
	chains, err := retractFacts(ctx, tx, []uuid.UUID{v2id}, "retract")
	if err != nil {
		t.Fatalf("retract V2: %v", err)
	}
	if len(chains) != 1 || chains[0].Attr != attr {
		t.Fatalf("retract should report 1 affected chain, got %v", chains)
	}
	assertChain(t, ctx, tx, entityID, attr, []chainRow{{"V1", 10, nil}})
	if err := refreshEAVProjection(ctx, tx, entityID, attr); err != nil {
		t.Fatalf("refresh projection post-retract: %v", err)
	}
	if got := currentProjection(t, ctx, tx, entityID, attr); got != "V1" {
		t.Fatalf("post-retract projection = %q, want V1 (chain re-stitched)", got)
	}

	// rebuildProjectionForEntity is the repair backstop — exercise it for coverage.
	if err := rebuildProjectionForEntity(ctx, tx, entityID); err != nil {
		t.Fatalf("rebuild projection: %v", err)
	}
}

type chainRow struct {
	value string
	vf    int64
	vt    *int64
}

func assertChain(t *testing.T, ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, attr string, want []chainRow) {
	t.Helper()
	rows, err := q.Query(ctx, `
		SELECT value, valid_from_ordinal, valid_to_ordinal FROM entity_facts
		WHERE entity_id = $1 AND attr_or_predicate = $2 AND invalidated_at IS NULL
		ORDER BY valid_from_ordinal`, entityID, attr)
	if err != nil {
		t.Fatalf("query chain: %v", err)
	}
	defer rows.Close()
	var got []chainRow
	for rows.Next() {
		var r chainRow
		if err := rows.Scan(&r.value, &r.vf, &r.vt); err != nil {
			t.Fatalf("scan chain: %v", err)
		}
		got = append(got, r)
	}
	if len(got) != len(want) {
		t.Fatalf("chain length = %d, want %d (%+v)", len(got), len(want), got)
	}
	for i := range want {
		if got[i].value != want[i].value || got[i].vf != want[i].vf || !eqPtr(got[i].vt, want[i].vt) {
			t.Fatalf("chain[%d] = %+v, want %+v", i, got[i], want[i])
		}
	}
}

func currentProjection(t *testing.T, ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, attr string) string {
	t.Helper()
	var v string
	err := q.QueryRow(ctx, `
		SELECT eav.original_value FROM entity_attribute_values eav
		JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		WHERE eav.entity_id = $1 AND ba.code = $2`, entityID, attr).Scan(&v)
	if err != nil {
		t.Fatalf("read projection: %v", err)
	}
	return v
}

func factID(t *testing.T, ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, attr, value string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	if err := q.QueryRow(ctx, `
		SELECT fact_id FROM entity_facts
		WHERE entity_id = $1 AND attr_or_predicate = $2 AND value = $3 AND invalidated_at IS NULL
		LIMIT 1`, entityID, attr, value).Scan(&id); err != nil {
		t.Fatalf("factID(%s): %v", value, err)
	}
	return id
}

func ptr(i int64) *int64 { return &i }
func eqPtr(a, b *int64) bool {
	if a == nil || b == nil {
		return a == b
	}
	return *a == *b
}
