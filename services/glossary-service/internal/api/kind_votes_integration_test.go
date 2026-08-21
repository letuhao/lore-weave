package api

// Entity-kind vote regressions. These are DB-backed because both defects sit at
// the transaction/outbox boundary; a pure resolver test cannot see either one.
// They require GLOSSARY_TEST_DB_URL, like the existing extraction integration tests.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func runKindVoteMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	runK2aMigrations(t, pool)
	if err := migrate.RunChain(context.Background(), pool); err != nil {
		t.Fatalf("migrate kind-vote chain: %v", err)
	}
}

func postKindVotes(t *testing.T, srv *Server, token, bookID string, body map[string]any) map[string]any {
	t.Helper()
	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal kind votes: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bookID+"/kind-votes", bytes.NewReader(raw))
	req.Header.Set("X-Internal-Token", token)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("kind-votes: want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var response map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode kind-votes response: %v", err)
	}
	return response
}

func entityVoteLedger(t *testing.T, pool *pgxpool.Pool, entityID uuid.UUID) map[string]int {
	t.Helper()
	rows, err := pool.Query(context.Background(), `
		SELECT kind_id::text, votes FROM entity_kind_votes WHERE entity_id=$1 ORDER BY kind_id`, entityID)
	if err != nil {
		t.Fatalf("read vote ledger: %v", err)
	}
	defer rows.Close()
	ledger := map[string]int{}
	for rows.Next() {
		var kindID string
		var votes int
		if err := rows.Scan(&kindID, &votes); err != nil {
			t.Fatalf("scan vote ledger: %v", err)
		}
		ledger[kindID] = votes
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate vote ledger: %v", err)
	}
	return ledger
}

func cleanupKindVoteBook(pool *pgxpool.Pool, bookID string) {
	ctx := context.Background()
	pool.Exec(ctx, `DELETE FROM outbox_events WHERE payload->>'book_id'=$1`, bookID) //nolint:errcheck
	cleanupExtractBook(pool, bookID)
}

func TestImportKindVotes_DryRunDoesNotPersistVotes(t *testing.T) {
	pool := openTestDB(t)
	runKindVoteMigrations(t, pool)
	ctx := context.Background()
	bookID := uuid.NewString()
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	t.Cleanup(func() { cleanupKindVoteBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "character", "name": "Dry Run Entity"}},
	})

	var entityID uuid.UUID
	var beforeKind uuid.UUID
	if err := pool.QueryRow(ctx, `
		SELECT entity_id, kind_id FROM glossary_entities
		WHERE book_id=$1 AND cached_name='Dry Run Entity'`, bid).Scan(&entityID, &beforeKind); err != nil {
		t.Fatalf("read seeded entity: %v", err)
	}
	beforeLedger := entityVoteLedger(t, pool, entityID)
	var beforeOutbox int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`, entityID).Scan(&beforeOutbox); err != nil {
		t.Fatalf("count seeded outbox rows: %v", err)
	}

	response := postKindVotes(t, srv, token, bookID, map[string]any{
		"apply": false,
		"votes": []map[string]any{{"name": "Dry Run Entity", "kind_code": "location", "votes": 2}},
	})
	if response["applied"] != false || response["entities_touched"] != float64(1) {
		t.Fatalf("dry run response should preview one untouched entity, got %v", response)
	}
	changes, ok := response["changes"].([]any)
	if !ok || len(changes) != 1 {
		t.Fatalf("dry run must preview the re-kind, got changes=%v", response["changes"])
	}

	var afterKind uuid.UUID
	if err := pool.QueryRow(ctx, `SELECT kind_id FROM glossary_entities WHERE entity_id=$1`, entityID).Scan(&afterKind); err != nil {
		t.Fatalf("read entity after dry run: %v", err)
	}
	if afterKind != beforeKind {
		t.Fatalf("dry run changed entity kind: before=%s after=%s", beforeKind, afterKind)
	}
	if afterLedger := entityVoteLedger(t, pool, entityID); !reflect.DeepEqual(afterLedger, beforeLedger) {
		t.Fatalf("dry run persisted vote ledger: before=%v after=%v", beforeLedger, afterLedger)
	}
	var afterOutbox int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`, entityID).Scan(&afterOutbox); err != nil {
		t.Fatalf("count outbox rows after dry run: %v", err)
	}
	if afterOutbox != beforeOutbox {
		t.Fatalf("dry run emitted outbox rows: before=%d after=%d", beforeOutbox, afterOutbox)
	}
}

func TestBulkExtract_BlockedRekindKeepsGlossaryAndOutboxAligned(t *testing.T) {
	pool := openTestDB(t)
	runKindVoteMigrations(t, pool)
	ctx := context.Background()
	bookID := uuid.NewString()
	bid := uuid.MustParse(bookID)
	adoptTestBook(t, pool, bid)
	t.Cleanup(func() { cleanupKindVoteBook(pool, bookID) })

	srv, token := newEntitiesListServer(t)
	srv.pool = pool
	const name = "Blocked Rekind Entity"
	postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities":        []map[string]any{{"kind_code": "character", "name": name}},
	})

	var sourceID uuid.UUID
	var normalizedName string
	if err := pool.QueryRow(ctx, `
		SELECT entity_id, normalized_name FROM glossary_entities
		WHERE book_id=$1 AND cached_name=$2`, bid, name).Scan(&sourceID, &normalizedName); err != nil {
		t.Fatalf("read source entity: %v", err)
	}
	locationID := bookKindID(t, pool, bid, "location")
	var duplicateID uuid.UUID
	if err := pool.QueryRow(ctx, `
		INSERT INTO glossary_entities (book_id, kind_id, status, cached_name, normalized_name, scope_label)
		VALUES ($1, $2, 'draft', $3, $4, '') RETURNING entity_id`,
		bid, locationID, name, normalizedName).Scan(&duplicateID); err != nil {
		t.Fatalf("forge duplicate target: %v", err)
	}
	if _, err := pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1`, sourceID); err != nil {
		t.Fatalf("clear setup outbox: %v", err)
	}

	response := postExtract(t, srv, token, bookID, map[string]any{
		"source_language": "en",
		"entities": []map[string]any{
			{"kind_code": "location", "name": name},
			{"kind_code": "location", "name": name},
		},
	})
	results, ok := response["entities"].([]any)
	if !ok || len(results) != 2 {
		t.Fatalf("want two extraction results, got %v", response["entities"])
	}
	last, ok := results[1].(map[string]any)
	if !ok {
		t.Fatalf("decode final extraction result: %T", results[1])
	}
	if last["entity_id"] != sourceID.String() || last["status"] != "skipped" || last["kind_code"] != "character" {
		t.Fatalf("blocked re-kind must report the persisted source, got %v", last)
	}

	var sourceKind, conflictID uuid.UUID
	if err := pool.QueryRow(ctx, `
		SELECT kind_id, kind_conflict_id FROM glossary_entities WHERE entity_id=$1`, sourceID).Scan(&sourceKind, &conflictID); err != nil {
		t.Fatalf("read source after blocked re-kind: %v", err)
	}
	if sourceKind != bookKindID(t, pool, bid, "character") || conflictID != locationID {
		t.Fatalf("blocked re-kind state: kind=%s conflict=%s, want character/%s", sourceKind, conflictID, locationID)
	}
	if ledger := entityVoteLedger(t, pool, sourceID); ledger[locationID.String()] != 2 {
		t.Fatalf("location observations were not retained: %v", ledger)
	}
	var events int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`, sourceID).Scan(&events); err != nil {
		t.Fatalf("count blocked-rekind outbox rows: %v", err)
	}
	if events != 0 {
		t.Fatalf("blocked re-kind emitted %d outbox event(s), want 0", events)
	}
	var duplicateStillLive bool
	if err := pool.QueryRow(ctx, `SELECT deleted_at IS NULL FROM glossary_entities WHERE entity_id=$1`, duplicateID).Scan(&duplicateStillLive); err != nil {
		t.Fatalf("read duplicate target: %v", err)
	}
	if !duplicateStillLive {
		t.Fatal("blocked re-kind must not merge or delete the duplicate target")
	}
}
