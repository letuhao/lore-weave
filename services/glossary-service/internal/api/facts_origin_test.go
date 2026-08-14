package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// TestAppendFactOrigin — T37c / SPEC §4.2b. `entity_facts.origin` records WHICH producer
// wrote a fact, so one can retract its own claims without touching another's.
//
// The defect it prevents was measured before it shipped: roles have TWO producers (planforge
// and the studio), both writing `fact_kind='relation'` with a NULL episode. Nothing else told
// them apart, so "close what this plan no longer implies" would have closed the AUTHOR's own
// declarations — silently erasing what a human deliberately said. A stale role is wrong; an
// erased one is gone.
func TestAppendFactOrigin(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)
	if err := migrate.RunChain(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	bid := uuid.MustParse("00000000-0000-0000-0001-0000000a3701")
	adoptTestBook(t, pool, bid)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM entity_facts WHERE book_id=$1`, bid)      //nolint:errcheck
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bid) //nolint:errcheck
	})

	srv, token := newEntitiesListServer(t)
	srv.pool = pool

	charKind := bookKindID(t, pool, bid, "character")
	var entityID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description)
		 VALUES($1,$2,'T37c origin fixture') RETURNING entity_id`,
		bid, charKind).Scan(&entityID); err != nil {
		t.Fatalf("seed entity: %v", err)
	}

	// A DISTINCT value per call. The same value re-asserted later is a write-time dedupe hit
	// (T34/D7: 11.7% of fact rows carried no new information), so it returns the existing fact
	// and writes no row — which would make this test read "origin was not persisted" when the
	// truth is "no second fact was ever created".
	post := func(origin string, ord int64, value string) *httptest.ResponseRecorder {
		body := map[string]any{
			"entity_id": entityID.String(), "fact_kind": "relation",
			"attr_or_predicate": "betrayed", "value": value, "valid_from_ordinal": ord,
		}
		if origin != "" {
			body["origin"] = origin
		}
		raw, _ := json.Marshal(body)
		req := httptest.NewRequest(http.MethodPost,
			"/internal/books/"+bid.String()+"/facts/append", strings.NewReader(string(raw)))
		req.Header.Set("X-Internal-Token", token)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		return w
	}

	// The mark is PERSISTED — a value that round-trips only as far as the handler would let
	// the close path find nothing and report success.
	if w := post("plan", 1_000_000, "Mira"); w.Code != http.StatusOK {
		t.Fatalf("append with origin=plan: got %d, body=%s", w.Code, w.Body.String())
	}
	var origin *string
	if err := pool.QueryRow(ctx,
		`SELECT origin FROM entity_facts WHERE book_id=$1 AND valid_from_ordinal=1000000`,
		bid).Scan(&origin); err != nil {
		t.Fatalf("read back origin: %v", err)
	}
	if origin == nil || *origin != "plan" {
		t.Fatalf("origin not persisted: got %v, want \"plan\"", origin)
	}

	// OMITTED stays NULL — every fact older than chain step 0066 is unmarked, and backfilling
	// them to a guess would be an authorship claim nobody made. An unmarked fact is never
	// anyone's to retract.
	if w := post("", 2_000_000, "Ada"); w.Code != http.StatusOK {
		t.Fatalf("append with no origin: got %d, body=%s", w.Code, w.Body.String())
	}
	if err := pool.QueryRow(ctx,
		`SELECT origin FROM entity_facts WHERE book_id=$1 AND valid_from_ordinal=2000000`,
		bid).Scan(&origin); err != nil {
		t.Fatalf("read back omitted origin: %v", err)
	}
	if origin != nil {
		t.Fatalf("an omitted origin was stored as %q — NULL means unknown, and a guess is an "+
			"authorship claim nobody made", *origin)
	}

	// An UNKNOWN origin is a 400, not a silent write. A fact stored under a misspelt origin is
	// un-retractable and nothing reports it — the exact quiet drift the column exists to remove.
	w := post("planforge", 3_000_000, "Rin")
	if w.Code != http.StatusBadRequest {
		t.Fatalf("a misspelt origin was accepted with %d — it would be stored, never matched "+
			"by the close path, and never reported", w.Code)
	}
	var leaked int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM entity_facts WHERE book_id=$1 AND valid_from_ordinal=3000000`,
		bid).Scan(&leaked); err != nil {
		t.Fatalf("count rejected: %v", err)
	}
	if leaked != 0 {
		t.Fatalf("the rejected append still wrote %d row(s)", leaked)
	}
}
