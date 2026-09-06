package api

// Tests for GET /internal/books/{book_id}/mirror-truth-ids — the truth side of the
// glossary→KG mirror anti-join (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).
//
// Unit tests (no DB) run always. The DB test requires GLOSSARY_TEST_DB_URL and skips
// otherwise — which is exactly why the predicate DRIFT test below is a pure unit test:
// the one assertion that must never be skipped is the one binding this enumeration to
// the emit path, and an env-gated test that skips is a green suite that lies.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func newMirrorTruthServer(t *testing.T) (*Server, string) {
	t.Helper()
	srv := newExportServer(t, nil)
	token := "mirror-truth-test-token"
	srv.cfg.InternalServiceToken = token
	return srv, token
}

// ── the drift guard ──────────────────────────────────────────────────
//
// The whole point of this endpoint is that it answers "which entities does the emit path
// consider to exist?" — the PRODUCER's own predicate. `reconcile-by-truth` has already
// cost this repo a bug by asking downstream a narrower proxy question than the producer
// asked itself. If either query stops being built from the shared fragment, the detector
// starts reporting correct rows as divergent (or misses lost ones) and NOTHING else would
// notice, because both queries would still be perfectly valid SQL.
func TestMirrorTruthSharesTheProducerPredicate(t *testing.T) {
	// Deliberately a SUFFIX/whole-clause check, not `Contains`. A containment assertion
	// passes when a side ADDS a condition — `... AND e.deleted_at IS NULL AND e.alive`
	// still contains the fragment — and narrowing is precisely the drift that breaks a
	// reconciler: the detector then reports rows as missing that will never be emitted,
	// and the count can never reach zero. (Caught by biting this test: the containment
	// form was vacuous against exactly the mutation it existed to catch.)
	if !strings.HasSuffix(strings.TrimSpace(entityEventFieldsSQL),
		"WHERE e.entity_id = $1 AND "+mirrorTruthPredicate) {
		t.Errorf("the emit-side read's lifecycle clause is no longer exactly "+
			"mirrorTruthPredicate:\n%s", entityEventFieldsSQL)
	}
	if !strings.Contains(mirrorTruthIDsSQL,
		"WHERE e.book_id = $1 AND "+mirrorTruthPredicate+"\n") {
		t.Errorf("the mirror-truth enumeration's lifecycle clause is no longer exactly "+
			"mirrorTruthPredicate:\n%s", mirrorTruthIDsSQL)
	}
	// The specific narrower proxy that would be wrong here. `alive` is a STORY flag: a
	// narratively dead character still emits and is still a graph node, so filtering on
	// it would report every dead-but-correctly-mirrored entity as an orphan, forever.
	if strings.Contains(mirrorTruthIDsSQL, "alive") {
		t.Errorf("mirror-truth-ids filters `alive` — that is entity-ids' predicate, "+
			"not the emit path's:\n%s", mirrorTruthIDsSQL)
	}
	// Both must resolve the kind through the same join, or an entity whose kind row is
	// missing would be emitted-but-unenumerable (or the reverse).
	for name, q := range map[string]string{
		"entityEventFieldsSQL": entityEventFieldsSQL,
		"mirrorTruthIDsSQL":    mirrorTruthIDsSQL,
	} {
		if !strings.Contains(q, "JOIN book_kinds k ON k.book_kind_id = e.kind_id") {
			t.Errorf("%s: kind join drifted — the two sides must agree on which rows "+
				"resolve a kind at all:\n%s", name, q)
		}
	}
}

// ── auth + validation (no DB) ────────────────────────────────────────

func TestMirrorTruthIDs_RequiresInternalToken(t *testing.T) {
	srv, _ := newMirrorTruthServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/00000000-0000-0000-0000-000000000001/mirror-truth-ids", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no token: want 401, got %d", w.Code)
	}
}

func TestMirrorTruthIDs_BadUUIDReturns400(t *testing.T) {
	srv, token := newMirrorTruthServer(t)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/not-a-uuid/mirror-truth-ids", nil)
	req.Header.Set("X-Internal-Token", token)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("bad uuid: want 400, got %d", w.Code)
	}
}

// ── the predicate, against a real database ───────────────────────────

type mirrorTruthTestResp struct {
	Items []struct {
		EntityID string `json:"entity_id"`
		KindCode string `json:"kind_code"`
		HasName  bool   `json:"has_name"`
	} `json:"items"`
	NextOffset *int `json:"next_offset"`
}

// TestMirrorTruthIDs_Predicate seeds one row of each lifecycle shape the detector has to
// tell apart, and asserts the enumeration classifies all four correctly. Three of the four
// are rows a naive enumeration gets wrong:
//
//	named + alive    → present, has_name=true   (the ordinary case)
//	named + NOT alive→ present, has_name=true   (entity-ids drops it; the KG holds it)
//	nameless         → present, has_name=FALSE  (the consumer skips it BY DESIGN)
//	soft-deleted     → ABSENT                   (the KG should not hold it either)
func TestMirrorTruthIDs_Predicate(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	runK2aMigrations(t, pool)

	bid := uuid.MustParse("00000000-0000-0000-0001-000000000e17")
	bookID := bid.String()
	adoptTestBook(t, pool, bid)
	kindID := bookKindID(t, pool, bid, "character")

	// cached_name is written directly: it is the column the emit path reads (maintained
	// by the snapshot trigger in production), and this test is about the enumeration
	// predicate, not about the trigger that fills it.
	seed := func(name string, alive bool, deleted bool) string {
		var eid string
		err := pool.QueryRow(ctx,
			`INSERT INTO glossary_entities(book_id,kind_id,status,tags,cached_name,alive,deleted_at)
			 VALUES($1,$2,'active','{}',$3,$4,CASE WHEN $5 THEN now() ELSE NULL END)
			 RETURNING entity_id`,
			bid, kindID, nullIfEmpty(name), alive, deleted,
		).Scan(&eid)
		if err != nil {
			t.Fatalf("seed %q: %v", name, err)
		}
		return eid
	}
	ordinary := seed("Lâm Diệp", true, false) // doc-language-gate: ok -- real book entity name; the mirror's live data is Vietnamese
	dead := seed("Lâm Trạch", false, false)   // doc-language-gate: ok -- real book entity name; the mirror's live data is Vietnamese
	nameless := seed("", true, false)
	trashed := seed("Deleted One", true, true)

	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM glossary_entities WHERE book_id=$1`, bid)
	})

	srv, token := newMirrorTruthServer(t)
	srv.pool = pool

	fetch := func(query string) mirrorTruthTestResp {
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+bookID+"/mirror-truth-ids"+query, nil)
		req.Header.Set("X-Internal-Token", token)
		w := httptest.NewRecorder()
		srv.Router().ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("want 200, got %d body=%s", w.Code, w.Body.String())
		}
		var r mirrorTruthTestResp
		if err := json.Unmarshal(w.Body.Bytes(), &r); err != nil {
			t.Fatalf("decode: %v", err)
		}
		return r
	}

	got := map[string]bool{} // entity_id → has_name
	page := fetch("")
	for _, it := range page.Items {
		got[it.EntityID] = it.HasName
		if it.KindCode != "character" {
			t.Errorf("%s: kind_code=%q, want character", it.EntityID, it.KindCode)
		}
	}
	if page.NextOffset != nil {
		t.Errorf("one page of 3 rows should not report next_offset=%v", *page.NextOffset)
	}

	if hasName, ok := got[ordinary]; !ok || !hasName {
		t.Errorf("named+alive: present=%v has_name=%v, want present with a name", ok, hasName)
	}
	if hasName, ok := got[dead]; !ok || !hasName {
		t.Errorf("named+DEAD: present=%v has_name=%v — a narratively dead character is "+
			"still emitted and still a graph node; dropping it here manufactures an orphan",
			ok, hasName)
	}
	if hasName, ok := got[nameless]; !ok || hasName {
		t.Errorf("nameless: present=%v has_name=%v, want present with has_name=false — "+
			"the consumer skips it by design, and a detector that cannot see the row "+
			"cannot tell 'not yet nameable' from 'lost'", ok, hasName)
	}
	if _, ok := got[trashed]; ok {
		t.Error("soft-deleted entity was enumerated as truth — the KG should not hold it, " +
			"so reporting it would make the divergence count un-closable")
	}
	if len(got) != 3 {
		t.Errorf("want exactly 3 enumerated rows, got %d: %v", len(got), got)
	}

	// Paging is peek-ahead with an EXPLICIT next_offset — a silent cap here under-reports
	// the divergence, which is the one failure a detector must not have.
	first := fetch("?limit=2")
	if len(first.Items) != 2 || first.NextOffset == nil || *first.NextOffset != 2 {
		t.Fatalf("limit=2 page 1: items=%d next_offset=%v", len(first.Items), first.NextOffset)
	}
	second := fetch("?limit=2&offset=2")
	if len(second.Items) != 1 || second.NextOffset != nil {
		t.Fatalf("limit=2 page 2: items=%d next_offset=%v", len(second.Items), second.NextOffset)
	}
}
