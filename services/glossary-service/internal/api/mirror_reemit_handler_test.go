package api

// Tests for POST /internal/books/{book_id}/mirror-reemit — the repair side of the
// glossary→KG mirror (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).
//
// The failure mode this guards is not a crash. It is a repair that reports success and
// emitted nothing, or one that resurrects data the KG is correct not to hold.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func newMirrorReemitServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	token := "mirror-reemit-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

func TestMirrorReemit_RequiresInternalToken(t *testing.T) {
	srv, _ := newMirrorReemitServer(t)
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/00000000-0000-0000-0000-000000000001/mirror-reemit",
		strings.NewReader(`{"entity_ids":["x"]}`))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestMirrorReemit_RejectsEmptyAndOversizedRequests(t *testing.T) {
	srv, token := newMirrorReemitServer(t)
	huge := make([]string, mirrorReemitMaxIDs+1)
	for i := range huge {
		huge[i] = uuid.NewString()
	}
	hugeBody, _ := json.Marshal(mirrorReemitRequest{EntityIDs: huge})

	for _, tc := range []struct {
		name, body string
	}{
		{"not json", `{`},
		{"no ids", `{"entity_ids":[]}`},
		// An unbounded repair is how a "fix everything" call becomes an outbox flood
		// that the relay then ships as one burst.
		{"over the cap", string(hugeBody)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost,
				"/internal/books/00000000-0000-0000-0000-000000000001/mirror-reemit",
				strings.NewReader(tc.body))
			req.Header.Set("X-Internal-Token", token)
			w := httptest.NewRecorder()
			srv.Router().ServeHTTP(w, req)
			if w.Code != http.StatusBadRequest {
				t.Errorf("want 400, got %d body=%s", w.Code, w.Body.String())
			}
		})
	}
}

// TestMirrorReemit_OnlyEmitsForRowsTheEmitPathOWNS is the test that matters. Each id below
// is one the repair must decline, and declining is INVISIBLE without an assertion: the
// endpoint returns 200 either way, and only the outbox says what really happened.
func TestMirrorReemit_OnlyEmitsForRowsTheEmitPathOwns(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bid := uuid.MustParse("00000000-0000-0000-0001-000000000e18")
	otherBook := uuid.MustParse("00000000-0000-0000-0001-000000000e19")
	adoptTestBook(t, pool, bid)
	adoptTestBook(t, pool, otherBook)
	kindID := bookKindID(t, pool, bid, "character")
	otherKindID := bookKindID(t, pool, otherBook, "character")

	seed := func(book uuid.UUID, kind uuid.UUID, name string, deleted bool) string {
		var eid string
		err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,cached_name,deleted_at)
			 VALUES($1,$2,'active','{}',$3,CASE WHEN $4 THEN now() ELSE NULL END)
			 RETURNING entity_id`,
			book, kind, nullIfEmpty(name), deleted,
		).Scan(&eid)
		if err != nil {
			t.Fatalf("seed %q: %v", name, err)
		}
		return eid
	}
	// doc-language-gate: ok -- real book entity names; the mirror's live data is Vietnamese
	repairable := seed(bid, kindID, "Lâm Diệp", false)
	trashed := seed(bid, kindID, "Deleted One", true)
	nameless := seed(bid, kindID, "", false)
	foreign := seed(otherBook, otherKindID, "Someone Else", false)
	absent := uuid.NewString()

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id = ANY($1)`,
			[]string{repairable, trashed, nameless, foreign})
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id = ANY($1)`,
			[]uuid.UUID{bid, otherBook})
	})

	srv, token := newMirrorReemitServer(t)
	srv.pool = pool

	body, _ := json.Marshal(mirrorReemitRequest{EntityIDs: []string{
		repairable, trashed, nameless, foreign, absent, "not-a-uuid",
	}})
	req := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bid.String()+"/mirror-reemit", strings.NewReader(string(body)))
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
	}
	var resp mirrorReemitResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if resp.Reemitted != 1 {
		t.Errorf("reemitted=%d, want exactly 1 (only the live, named, in-book entity)",
			resp.Reemitted)
	}
	if len(resp.SkippedIDs) != 5 {
		t.Errorf("skipped=%v, want all 5 declined ids reported by id — a repair that "+
			"silently does nothing looks exactly like one that worked", resp.SkippedIDs)
	}
	if len(resp.FailedIDs) != 0 {
		t.Errorf("failed=%v, want none", resp.FailedIDs)
	}

	// The response is a claim; the outbox is the fact. Assert against the table.
	countFor := func(entityID string) int {
		var n int
		pool.QueryRow(ctx,
			`SELECT count(*) FROM outbox_events
			  WHERE aggregate_id = $1 AND event_type = $2`,
			entityID, entityUpdatedEvent,
		).Scan(&n)
		return n
	}
	if got := countFor(repairable); got != 1 {
		t.Errorf("the repairable entity got %d outbox row(s), want 1", got)
	}
	for label, id := range map[string]string{
		"soft-deleted (D-OUTBOX-PAYLOAD-TRASH: re-emitting un-deletes it downstream)": trashed,
		"nameless (nothing to MERGE a node from yet)":                                 nameless,
		"another book's entity (scope must come from the row, not the caller)":        foreign,
	} {
		if got := countFor(id); got != 0 {
			t.Errorf("%s: got %d outbox row(s), want 0", label, got)
		}
	}

	// Idempotence: the repair is safe to re-run, which is what makes "just re-emit
	// everything the detector reported" an acceptable operator action.
	w2 := httptest.NewRecorder()
	req2 := httptest.NewRequest(http.MethodPost,
		"/internal/books/"+bid.String()+"/mirror-reemit",
		strings.NewReader(`{"entity_ids":["`+repairable+`"]}`))
	req2.Header.Set("X-Internal-Token", token)
	srv.Router().ServeHTTP(w2, req2)
	if w2.Code != http.StatusOK {
		t.Fatalf("re-run: want 200, got %d", w2.Code)
	}
	if got := countFor(repairable); got != 2 {
		t.Errorf("re-run produced %d total outbox row(s), want 2 — the repair must be "+
			"replayable, and the consumer's MERGE is what makes that harmless", got)
	}
}
