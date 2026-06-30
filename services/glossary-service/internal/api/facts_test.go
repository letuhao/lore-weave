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
	if err := reconcileEpisode(ctx, tx, ep1); err != nil {
		t.Fatalf("reconcile episode: %v", err)
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
	chains, err := retractFacts(ctx, tx, bookID, []uuid.UUID{v2id}, "retract")
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

// TestFactSameOrdinalConflict verifies MED-1: two DIFFERENT values for one single-valued
// attr at the SAME chapter ordinal resolve last-write-wins (the prior is invalidated, not
// left as a second open fact), so exactly one fact is open and the projection is
// deterministic. The SAME value re-appended is idempotent (no spurious invalidation).
func TestFactSameOrdinalConflict(t *testing.T) {
	ctx := context.Background()
	pool := openFactsTestDB(t)
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var entityID, bookID uuid.UUID
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

	mk := func(val string) {
		if _, _, err := appendFact(ctx, tx, appendFactParams{
			BookID: bookID, EntityID: entityID, FactKind: "attribute", Attr: attr,
			Value: val, ValidFrom: 100,
		}); err != nil {
			t.Fatalf("append %s@100: %v", val, err)
		}
	}
	mk("AAA") // first value at ch.100
	mk("BBB") // conflicting different value at the SAME ordinal → must supersede AAA

	// exactly ONE open fact, and it is the last writer (BBB)
	assertChain(t, ctx, tx, entityID, attr, []chainRow{{"BBB", 100, nil}})
	if err := refreshEAVProjection(ctx, tx, entityID, attr); err != nil {
		t.Fatalf("refresh: %v", err)
	}
	if got := currentProjection(t, ctx, tx, entityID, attr); got != "BBB" {
		t.Fatalf("projection = %q, want BBB (last-write-wins, deterministic)", got)
	}

	// re-appending the SAME current value is idempotent — does not invalidate BBB.
	mk("BBB")
	assertChain(t, ctx, tx, entityID, attr, []chainRow{{"BBB", 100, nil}})
}

// TestFactChainLockSerializes verifies MED-2: the per-(entity,attr) advisory lock
// SERIALIZES the same chain (a second holder is blocked) while leaving a DISJOINT chain
// free (the within-book parallelism the §12.7.8 lock model restores).
func TestFactChainLockSerializes(t *testing.T) {
	ctx := context.Background()
	pool := openFactsTestDB(t)
	entityID := uuid.New()
	attr := "lockcheck"

	tx1, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin tx1: %v", err)
	}
	defer tx1.Rollback(ctx) //nolint:errcheck
	if err := acquireFactChainLock(ctx, tx1, entityID, attr); err != nil {
		t.Fatalf("tx1 acquire: %v", err)
	}

	tx2, err := pool.Begin(ctx) // a DIFFERENT pooled connection → real lock contention
	if err != nil {
		t.Fatalf("begin tx2: %v", err)
	}
	defer tx2.Rollback(ctx) //nolint:errcheck

	var gotSame bool
	if err := tx2.QueryRow(ctx,
		`SELECT pg_try_advisory_xact_lock($1, hashtext($2))`,
		factChainLockNS, entityID.String()+":"+attr).Scan(&gotSame); err != nil {
		t.Fatalf("tx2 try same: %v", err)
	}
	if gotSame {
		t.Fatal("second tx acquired the SAME chain lock while held — not serialized")
	}

	var gotOther bool
	if err := tx2.QueryRow(ctx,
		`SELECT pg_try_advisory_xact_lock($1, hashtext($2))`,
		factChainLockNS, entityID.String()+":other_attr").Scan(&gotOther); err != nil {
		t.Fatalf("tx2 try disjoint: %v", err)
	}
	if !gotOther {
		t.Fatal("disjoint chain lock should be FREE (within-book parallelism)")
	}
}

// TestMergeFactChains verifies F1f (§12.4.1): the fact-chain merge repoints ALL loser
// facts, resolves a same-ordinal conflict deterministically (newest wins), and is EXACTLY
// reversible via the journalled moved + invalidated ids.
func TestMergeFactChains(t *testing.T) {
	ctx := context.Background()
	pool := openFactsTestDB(t)
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// two live entities in one book
	var bookID, winner, loser uuid.UUID
	rows, err := tx.Query(ctx, `
		SELECT book_id, entity_id FROM glossary_entities
		WHERE deleted_at IS NULL
		  AND book_id = (SELECT book_id FROM glossary_entities WHERE deleted_at IS NULL
		                 GROUP BY book_id HAVING count(*) >= 2 LIMIT 1)
		LIMIT 2`)
	if err != nil {
		t.Fatalf("pick entities: %v", err)
	}
	var ids []uuid.UUID
	for rows.Next() {
		var b, e uuid.UUID
		if err := rows.Scan(&b, &e); err != nil {
			rows.Close()
			t.Fatalf("scan: %v", err)
		}
		bookID = b
		ids = append(ids, e)
	}
	rows.Close()
	if len(ids) < 2 {
		t.Skip("need a book with >=2 live entities")
	}
	winner, loser = ids[0], ids[1]

	app := func(ent uuid.UUID, attr, val string, vf int64) {
		if err := acquireFactChainLock(ctx, tx, ent, attr); err != nil {
			t.Fatalf("lock: %v", err)
		}
		if _, _, err := appendFact(ctx, tx, appendFactParams{
			BookID: bookID, EntityID: ent, FactKind: "attribute", Attr: attr, Value: val, ValidFrom: vf,
		}); err != nil {
			t.Fatalf("append %s/%s: %v", ent, attr, err)
		}
	}
	// winner: mtk1=W@10 ; loser: mtk1=L@10 (same-ordinal conflict, L appended later=newer) + mtk2=X@5
	app(winner, "mtk1", "W", 10)
	app(loser, "mtk1", "L", 10)
	app(loser, "mtk2", "X", 5)

	moved, invalidated, err := mergeFactChains(ctx, tx, winner, loser)
	if err != nil {
		t.Fatalf("mergeFactChains: %v", err)
	}
	if len(moved) != 2 { // L@10 + X@5
		t.Fatalf("moved = %d, want 2", len(moved))
	}
	if len(invalidated) != 1 { // W@10 loses the same-ordinal tiebreak to the newer L@10
		t.Fatalf("invalidated = %d, want 1 (the tiebreak loser)", len(invalidated))
	}
	// winner now owns the merged chains: mtk1 open = L (newest), mtk2 open = X
	assertChain(t, ctx, tx, winner, "mtk1", []chainRow{{"L", 10, nil}})
	assertChain(t, ctx, tx, winner, "mtk2", []chainRow{{"X", 5, nil}})
	// loser has no live facts
	var loserLive int
	if err := tx.QueryRow(ctx, `SELECT count(*) FROM entity_facts WHERE entity_id=$1`, loser).Scan(&loserLive); err != nil {
		t.Fatalf("loser count: %v", err)
	}
	if loserLive != 0 {
		t.Fatalf("loser should own 0 facts after merge, has %d", loserLive)
	}

	// REVERT: exactly restore both sides
	if err := revertFactChains(ctx, tx, winner, loser, moved, invalidated); err != nil {
		t.Fatalf("revertFactChains: %v", err)
	}
	assertChain(t, ctx, tx, winner, "mtk1", []chainRow{{"W", 10, nil}}) // W restored + un-invalidated
	assertChain(t, ctx, tx, loser, "mtk1", []chainRow{{"L", 10, nil}})  // L back on loser
	assertChain(t, ctx, tx, loser, "mtk2", []chainRow{{"X", 5, nil}})
}

// TestSplitFactsByEpisode verifies F1f split (§12.4.2): facts cited to the split-off
// episode move to the new entity as a NEW transaction-time event (originals invalidated
// with reason 'split', fresh facts opened on the new entity), and facts from other
// episodes stay on the source.
func TestSplitFactsByEpisode(t *testing.T) {
	ctx := context.Background()
	pool := openFactsTestDB(t)
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var bookID, source, newEntity uuid.UUID
	rows, err := tx.Query(ctx, `
		SELECT book_id, entity_id FROM glossary_entities
		WHERE deleted_at IS NULL
		  AND book_id = (SELECT book_id FROM glossary_entities WHERE deleted_at IS NULL
		                 GROUP BY book_id HAVING count(*) >= 2 LIMIT 1)
		LIMIT 2`)
	if err != nil {
		t.Fatalf("pick entities: %v", err)
	}
	var ids []uuid.UUID
	for rows.Next() {
		var b, e uuid.UUID
		if err := rows.Scan(&b, &e); err != nil {
			rows.Close()
			t.Fatalf("scan: %v", err)
		}
		bookID = b
		ids = append(ids, e)
	}
	rows.Close()
	if len(ids) < 2 {
		t.Skip("need a book with >=2 live entities")
	}
	source, newEntity = ids[0], ids[1]

	ep1, _, err := ingestEpisode(ctx, tx, bookID, uuid.New(), 10, "spE1", "")
	if err != nil {
		t.Fatalf("ep1: %v", err)
	}
	ep2, _, err := ingestEpisode(ctx, tx, bookID, uuid.New(), 20, "spE2", "")
	if err != nil {
		t.Fatalf("ep2: %v", err)
	}
	app := func(attr, val string, vf int64, ep uuid.UUID) {
		_ = acquireFactChainLock(ctx, tx, source, attr)
		if _, _, err := appendFact(ctx, tx, appendFactParams{
			BookID: bookID, EntityID: source, FactKind: "attribute", Attr: attr, Value: val, ValidFrom: vf,
			SourceEpisodeID: &ep,
		}); err != nil {
			t.Fatalf("append %s: %v", attr, err)
		}
	}
	app("spa1", "V1", 10, ep1) // cited to ep1 → will split out
	app("spa2", "V2", 20, ep2) // cited to ep2 → stays on source

	moved, err := splitFactsByEpisode(ctx, tx, bookID, source, newEntity, []uuid.UUID{ep1})
	if err != nil {
		t.Fatalf("split: %v", err)
	}
	if moved != 1 {
		t.Fatalf("moved = %d, want 1", moved)
	}
	// new entity now owns spa1; source no longer has spa1 live but keeps spa2
	assertChain(t, ctx, tx, newEntity, "spa1", []chainRow{{"V1", 10, nil}})
	assertChain(t, ctx, tx, source, "spa2", []chainRow{{"V2", 20, nil}})
	var srcA1Live int
	if err := tx.QueryRow(ctx, `
		SELECT count(*) FROM entity_facts
		WHERE entity_id=$1 AND attr_or_predicate='spa1' AND invalidated_at IS NULL`, source).Scan(&srcA1Live); err != nil {
		t.Fatalf("src spa1 live: %v", err)
	}
	if srcA1Live != 0 {
		t.Fatalf("source should have 0 live spa1 facts after split, has %d", srcA1Live)
	}
	// the original is invalidate-not-deleted with reason 'split' (audit intact)
	var splitReason int
	if err := tx.QueryRow(ctx, `
		SELECT count(*) FROM entity_facts
		WHERE entity_id=$1 AND attr_or_predicate='spa1' AND invalidated_reason='split'`, source).Scan(&splitReason); err != nil {
		t.Fatalf("split reason: %v", err)
	}
	if splitReason != 1 {
		t.Fatalf("expected 1 invalidated-with-reason-split original, got %d", splitReason)
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
