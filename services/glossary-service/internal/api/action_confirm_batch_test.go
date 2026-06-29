package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// batchPost posts {child_tokens, enabled_ops?} to a batch endpoint as the fixture user.
func (f *actionFixture) batchPost(t *testing.T, path string, tokens ...string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"child_tokens": tokens})
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+f.jwt)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

// mintKindToken mints a schema_create_kind child token for (user, book) — the common
// single-propose shape a weak model loops, which the batch coalesces into one card.
func (f *actionFixture) mintKindToken(user, book uuid.UUID, code, name string, when time.Time) string {
	params, _ := json.Marshal(kindCreateParams{Code: code, Name: name})
	return mintActionToken(versionTestSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityGrant, UserID: user, BookID: book,
		Descriptor: descSchemaCreateKind, Params: params,
	}, when)
}

func kindCount(t *testing.T, pool *pgxpool.Pool, book uuid.UUID, code string) int {
	t.Helper()
	var n int
	pool.QueryRow(context.Background(),
		`SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code=$2 AND deprecated_at IS NULL`, book, code).Scan(&n)
	return n
}

// One human Apply commits EVERY child token — the coalesce that replaces the N orphaned
// cards (#27/#29/#30). Both kinds are created; the response reports applied=2.
func TestConfirmBatch_RoundTripCommitsAll(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM book_kinds WHERE book_id=$1 AND code IN ('qa_b1','qa_b2')`, f.bookID)
	})
	t1 := f.mintKindToken(f.ownerID, f.bookID, "qa_b1", "Batch One", time.Now())
	t2 := f.mintKindToken(f.ownerID, f.bookID, "qa_b2", "Batch Two", time.Now())

	w := f.batchPost(t, "/v1/glossary/actions/confirm-batch", t1, t2)
	if w.Code != http.StatusOK {
		t.Fatalf("confirm-batch: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var res batchConfirmResult
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if res.Applied != 2 || res.Failed != 0 || res.Skipped != 0 {
		t.Errorf("want applied=2 failed=0 skipped=0, got %+v", res)
	}
	for _, code := range []string{"qa_b1", "qa_b2"} {
		if kindCount(t, pool, f.bookID, code) != 1 {
			t.Errorf("kind %s not created by the batch confirm", code)
		}
	}
}

// A replay of an already-confirmed batch SKIPS every child (idempotent single-use ledger) —
// never a second create. This is the property the orphaned-card UX could not guarantee.
func TestConfirmBatch_ReplaySkipsNeverDoubleApplies(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM book_kinds WHERE book_id=$1 AND code IN ('qa_r1','qa_r2')`, f.bookID)
	})
	t1 := f.mintKindToken(f.ownerID, f.bookID, "qa_r1", "Rep One", time.Now())
	t2 := f.mintKindToken(f.ownerID, f.bookID, "qa_r2", "Rep Two", time.Now())

	if w := f.batchPost(t, "/v1/glossary/actions/confirm-batch", t1, t2); w.Code != http.StatusOK {
		t.Fatalf("first confirm-batch: want 200, got %d", w.Code)
	}
	w := f.batchPost(t, "/v1/glossary/actions/confirm-batch", t1, t2)
	var res batchConfirmResult
	json.Unmarshal(w.Body.Bytes(), &res)
	if res.Skipped != 2 || res.Applied != 0 {
		t.Errorf("replay: want skipped=2 applied=0, got %+v", res)
	}
	for _, code := range []string{"qa_r1", "qa_r2"} {
		if c := kindCount(t, pool, f.bookID, code); c != 1 {
			t.Errorf("replay must not create a 2nd %s: count=%d", code, c)
		}
	}
}

// A batch spanning two books is rejected up front (the suspended run is bound to one book) —
// fail-closed BEFORE any token is consumed, so neither child is burned.
func TestConfirmBatch_MixedBookRejectedNoneConsumed(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM book_kinds WHERE book_id=$1 AND code='qa_mb'`, f.bookID)
	})
	good := f.mintKindToken(f.ownerID, f.bookID, "qa_mb", "Mixed", time.Now())
	foreign := f.mintKindToken(f.ownerID, uuid.New(), "qa_other", "Other Book", time.Now())

	if w := f.batchPost(t, "/v1/glossary/actions/confirm-batch", good, foreign); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("mixed-book: want 422, got %d (%s)", w.Code, w.Body.String())
	}
	// neither consumed: the good token still confirms single
	if w := f.confirm(t, good); w.Code != http.StatusCreated {
		t.Errorf("the good token must be un-burned after a rejected mixed batch: got %d", w.Code)
	}
}

// A child minted for a different user rejects the whole batch (proposer-bound), 403.
func TestConfirmBatch_WrongUserRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	mine := f.mintKindToken(f.ownerID, f.bookID, "qa_wu", "Mine", time.Now())
	theirs := f.mintKindToken(uuid.New(), f.bookID, "qa_wu2", "Theirs", time.Now())
	if w := f.batchPost(t, "/v1/glossary/actions/confirm-batch", mine, theirs); w.Code != http.StatusForbidden {
		t.Fatalf("wrong-user child: want 403, got %d (%s)", w.Code, w.Body.String())
	}
}

// An expired child rejects the whole batch (the bundle was minted in one turn → same TTL).
func TestConfirmBatch_ExpiredChildRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	fresh := f.mintKindToken(f.ownerID, f.bookID, "qa_ex", "Fresh", time.Now())
	stale := f.mintKindToken(f.ownerID, f.bookID, "qa_ex2", "Stale", time.Now().Add(-2*actionTokenTTL))
	if w := f.batchPost(t, "/v1/glossary/actions/confirm-batch", fresh, stale); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expired child: want 422, got %d", w.Code)
	}
}

// Empty child_tokens is a 400 input error (no card should ever post an empty bundle).
func TestConfirmBatch_EmptyRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	if w := f.batchPost(t, "/v1/glossary/actions/confirm-batch"); w.Code != http.StatusBadRequest {
		t.Fatalf("empty batch: want 400, got %d", w.Code)
	}
}

// preview-batch renders every child's CURRENT-state card without consuming a token, and
// concatenates them so the human reviews the whole bundle in one card.
func TestPreviewBatch_AggregatesChildrenWithoutConsuming(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM book_kinds WHERE book_id=$1 AND code IN ('qa_p1','qa_p2')`, f.bookID)
	})
	t1 := f.mintKindToken(f.ownerID, f.bookID, "qa_p1", "Prev One", time.Now())
	t2 := f.mintKindToken(f.ownerID, f.bookID, "qa_p2", "Prev Two", time.Now())

	w := f.batchPost(t, "/v1/glossary/actions/preview-batch", t1, t2)
	if w.Code != http.StatusOK {
		t.Fatalf("preview-batch: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var res batchPreviewResult
	json.Unmarshal(w.Body.Bytes(), &res)
	if res.Children != 2 || res.Descriptor != descBatch {
		t.Errorf("want children=2 descriptor=%s, got %+v", descBatch, res)
	}
	if len(res.PreviewRows) < 2 {
		t.Errorf("want the two children's rows concatenated, got %d rows", len(res.PreviewRows))
	}
	// preview must NOT consume: both tokens still confirm
	if w := f.confirm(t, t1); w.Code != http.StatusCreated {
		t.Errorf("preview burned token 1: confirm got %d", w.Code)
	}
}
