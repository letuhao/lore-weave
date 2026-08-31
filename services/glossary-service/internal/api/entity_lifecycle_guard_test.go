package api

// Phase 0 of the knowledge-architecture refactor — the two glossary-side lifecycle
// guards that the debt register recorded as CLOSED and that were still open at
// df18e9049 (`D-ENTITY-EXISTS-GUARD`, `D-OUTBOX-PAYLOAD-TRASH`).
//
// Both are BYPASS bugs: the write that trashes an entity lands, and then some other
// path behaves as if it never happened. So each test below asserts the EFFECT on a
// real Postgres — a refusal that costs nothing, and an emission that does not
// happen — and each carries its positive control in the same test, because "no row
// appeared" is a claim any broken fixture also satisfies.
//
// Requires GLOSSARY_TEST_DB_URL; skips otherwise (openTestDB).

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/migrate"
)

// TestDeletedEntity_CanonicalTranslationRefusedAndSpendsNothing locks T1.
//
// entityExistsInBook guards eight per-entity routes; canonical-translation is the
// one that spends money, because a cache miss claims a row and launches a paid
// machine-translation fill. Before the fix a trashed entity sailed through the
// guard and bought a translation of content the author had deleted.
func TestDeletedEntity_CanonicalTranslationRefusedAndSpendsNothing(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)
	// canonical_snapshot_translations lives in the ledger chain, not in the K2a set
	// newVersionFixture applies. RunChain is idempotent (append-only ledger).
	if err := migrate.RunChain(ctx, pool); err != nil {
		t.Fatalf("migrate chain: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM canonical_snapshot_translations WHERE entity_id=$1`, f.entityID) //nolint:errcheck
	})

	// getCanonicalContent degrades to short_description when no folded snapshot
	// exists — enough content for the fill path to be reachable, which is what makes
	// the negative assertion meaningful.
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET short_description='A fierce youth of Chentang Pass' WHERE entity_id=$1`,
		f.entityID); err != nil {
		t.Fatalf("seed short_description: %v", err)
	}

	// Stub translation-service — every call here is a paid MT call in production.
	var mtCalls int
	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mtCalls++
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"translated_text": "translated"}) //nolint:errcheck
	}))
	defer stub.Close()
	f.srv.cfg.TranslationServiceURL = stub.URL

	getTranslation := func() *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+f.bookID.String()+"/entities/"+f.entityID.String()+
				"/canonical-translation?lang=en", nil)
		req.Header.Set("X-Internal-Token", "tok")
		req.Header.Set("X-User-Id", uuid.NewString())
		w := httptest.NewRecorder()
		f.srv.Router().ServeHTTP(w, req)
		return w
	}
	claimRows := func() int {
		var n int
		pool.QueryRow(ctx,
			`SELECT count(*) FROM canonical_snapshot_translations WHERE entity_id=$1`,
			f.entityID).Scan(&n) //nolint:errcheck
		return n
	}

	// ── the bug: trashed entity, translation requested ──
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, f.entityID); err != nil {
		t.Fatalf("soft-delete: %v", err)
	}

	if w := getTranslation(); w.Code != http.StatusNotFound {
		t.Fatalf("canonical-translation on a trashed entity: want 404, got %d (%s)",
			w.Code, w.Body.String())
	}
	// The claim row is the single-flight ticket: exactly one row is inserted per
	// launched fill, so zero rows proves no fill was launched — a causal assertion
	// that does not race the background goroutine.
	if n := claimRows(); n != 0 {
		t.Errorf("a refused request must claim no translation row, got %d", n)
	}
	if mtCalls != 0 {
		t.Errorf("a refused request must spend no MT call, got %d", mtCalls)
	}

	// ── the control: restore it, and the SAME request now works ──
	// Without this the test would still pass if the route were broken for every
	// entity, live or not — which would prove nothing about liveness.
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET deleted_at=NULL WHERE entity_id=$1`, f.entityID); err != nil {
		t.Fatalf("restore: %v", err)
	}
	if w := getTranslation(); w.Code != http.StatusOK {
		t.Fatalf("canonical-translation on a LIVE entity: want 200, got %d (%s)",
			w.Code, w.Body.String())
	}
	if n := claimRows(); n != 1 {
		t.Fatalf("a live request must claim exactly 1 translation row, got %d "+
			"(the 404 above is only meaningful if this path is otherwise reachable)", n)
	}
}

// TestDeletedEntity_EditEmitsNoOutboxEvent locks T3.
//
// apply-edit carries no liveness guard of its own, so a trashed entity can still be
// edited — and every edit used to publish `glossary.entity_updated`, which made
// knowledge-service re-embed and re-anchor the entity. The deletion was silently
// reversed inside the consumer's index. The emission is what must stop here; whether
// the edit itself should be refused is a separate decision (Phase 4, T27).
func TestDeletedEntity_EditEmitsNoOutboxEvent(t *testing.T) {
	pool := openTestDB(t)
	ctx := context.Background()
	f := newVersionFixture(t, pool)
	t.Cleanup(func() {
		pool.Exec(ctx, `DELETE FROM outbox_events WHERE aggregate_id=$1`, f.entityID) //nolint:errcheck
	})

	events := func() int {
		var n int
		pool.QueryRow(ctx,
			`SELECT count(*) FROM outbox_events WHERE aggregate_id=$1 AND event_type='glossary.entity_updated'`,
			f.entityID).Scan(&n) //nolint:errcheck
		return n
	}
	edit := func(t *testing.T, name string) *httptest.ResponseRecorder {
		t.Helper()
		base := f.currentVersion(t, pool)
		body := `{"base_version":"` + base + `","attributes":[{"attr_value_id":"` +
			f.nameAttrVal.String() + `","original_value":"` + name + `"}]}`
		req := httptest.NewRequest(http.MethodPost,
			"/v1/glossary/books/"+f.bookID.String()+"/entities/"+f.entityID.String()+"/apply-edit",
			bytes.NewBufferString(body))
		req.Header.Set("Authorization", "Bearer "+f.token)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		f.srv.Router().ServeHTTP(w, req)
		return w
	}

	// ── the control first: a live edit DOES publish ──
	if w := edit(t, "Nezha II"); w.Code != http.StatusOK {
		t.Fatalf("live apply-edit: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if n := events(); n != 1 {
		t.Fatalf("a live edit must emit exactly 1 entity_updated, got %d", n)
	}

	// ── the bug: trash it, then edit it again ──
	if _, err := pool.Exec(ctx,
		`UPDATE glossary_entities SET deleted_at=now() WHERE entity_id=$1`, f.entityID); err != nil {
		t.Fatalf("soft-delete: %v", err)
	}
	// The response code is NOT asserted, deliberately. apply-edit carries no liveness
	// guard, so it commits the edit and then 500s on its own post-commit read-back
	// (loadEntityDetail filters `deleted_at IS NULL`) — measured identical with this
	// fix reverted, so it is pre-existing and orthogonal. Whether a trashed entity is
	// editable at all is a command-contract decision and belongs to T27, not here.
	// What matters for T3 is that the committed edit publishes NOTHING.
	w := edit(t, "Nezha III")
	t.Logf("apply-edit on a trashed entity returned %d (pre-existing, see T27): %s",
		w.Code, w.Body.String())
	if n := events(); n != 1 {
		t.Errorf("editing a trashed entity must publish nothing — entity_updated count "+
			"went %d→%d, which re-anchors a deleted entity downstream", 1, n)
	}
}
