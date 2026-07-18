package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"

	crypto "github.com/loreweave/loreweave_crypto"
)

// fakeAuthDEKToggle is fakeAuthDEK with a shred-failure switch (P4): when failShred is set, the DEK
// DELETE returns 500 (a transient auth blip) so the inline shred fails and a pending_dek_shreds row is
// owed; flip it off and the sweeper's retry converges. `deleteAttempts` records EVERY DELETE that
// reached auth (success or fail) so a test can prove the reuse-guard SKIPPED without even attempting one.
func fakeAuthDEKToggle(t *testing.T, ring crypto.Keyring, failShred *bool, deleteAttempts, shredded *[]string) *httptest.Server {
	t.Helper()
	deks := map[string][]byte{}
	var mu sync.Mutex
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		uid := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/internal/users/"), "/dek")
		switch r.Method {
		case http.MethodGet:
			dek, ok := deks[uid]
			if !ok {
				dek, _ = crypto.NewDEK()
				deks[uid] = dek
			}
			wrapped, ref, _ := crypto.WrapDEK(ring, dek, uid)
			_, _ = w.Write([]byte(`{"wrapped_dek":"` + wrapped + `","key_ref":"` + ref + `"}`))
		case http.MethodDelete:
			*deleteAttempts = append(*deleteAttempts, uid)
			if *failShred {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			delete(deks, uid)
			*shredded = append(*shredded, uid)
			w.WriteHeader(http.StatusNoContent)
		}
	}))
}

func eraseDiary(t *testing.T, s *Server, diary, owner uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	dr := httptest.NewRequest(http.MethodDelete,
		"/internal/books/"+diary.String()+"/diary/erase?user_id="+owner.String(), nil)
	dr.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, dr)
	return rr
}

func pendingShredCount(t *testing.T, s *Server, owner uuid.UUID) int {
	t.Helper()
	var n int
	if err := s.pool.QueryRow(context.Background(),
		`SELECT count(*) FROM pending_dek_shreds WHERE owner_user_id=$1`, owner).Scan(&n); err != nil {
		t.Fatalf("count pending: %v", err)
	}
	return n
}

// P4 (D-DIARY-SHRED-OUTBOX-RETRY) — an inline-shred blip leaves a DURABLE owed-shred row, and the
// sweeper RETRIES it to convergence (so a transient auth outage can't leave the DEK alive with a
// decryptable backup).
func TestDekShredSweeper_ConvergesAfterInlineFailure_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	kek := "book-diary-test-kek-not-jwt"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	failShred := true
	var attempts, shredded []string
	auth := fakeAuthDEKToggle(t, ring, &failShred, &attempts, &shredded)
	defer auth.Close()
	s.diaryCrypto = newDiaryCrypto(auth.URL, "tok", kek, "")

	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM pending_dek_shreds WHERE owner_user_id=$1`, owner) })
	if rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "entry_zone": "UTC",
		"body": "secret", "journal_kind": "primary", "language": "en"}, true); rr.Code != http.StatusCreated {
		t.Fatalf("create = %d body=%s", rr.Code, rr.Body.String())
	}

	// (1) erase while the shred FAILS → 200, dek_shredded:false, and a DURABLE pending row is owed.
	rr := eraseDiary(t, s, diary, owner)
	if rr.Code != http.StatusOK || !strings.Contains(rr.Body.String(), `"dek_shredded":false`) {
		t.Fatalf("erase with failing shred: code=%d body=%s", rr.Code, rr.Body.String())
	}
	if pendingShredCount(t, s, owner) != 1 {
		t.Fatal("a failed inline shred must leave a DURABLE pending_dek_shreds row for the sweeper")
	}

	// (2) auth recovers; the sweeper converges the shred and clears the debt.
	failShred = false
	converged, skipped, err := s.sweepPendingShreds(ctx, 10)
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if converged != 1 || skipped != 0 {
		t.Fatalf("sweep want converged=1 skipped=0, got %d/%d", converged, skipped)
	}
	if pendingShredCount(t, s, owner) != 0 {
		t.Fatal("the converged shred's pending row must be cleared")
	}
	if len(shredded) != 1 || shredded[0] != owner.String() {
		t.Fatalf("the sweeper must have retried the DEK-shred for the owner, got %v", shredded)
	}
}

// P4 cold-review HIGH-1 — a 0-row re-erase (the diary was already deleted) must NOT crypto-shred: a
// re-provisioned user has a FRESH DEK that a blind shred would destroy. The inline shred is gated on
// `erased`, so a no-op re-erase attempts no shred.
func TestEraseDiary_ZeroRowReErase_DoesNotShred_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	kek := "book-diary-test-kek-not-jwt"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	failShred := false
	var attempts, shredded []string
	auth := fakeAuthDEKToggle(t, ring, &failShred, &attempts, &shredded)
	defer auth.Close()
	s.diaryCrypto = newDiaryCrypto(auth.URL, "tok", kek, "")

	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM pending_dek_shreds WHERE owner_user_id=$1`, owner) })
	if rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "entry_zone": "UTC",
		"body": "old", "journal_kind": "primary", "language": "en"}, true); rr.Code != http.StatusCreated {
		t.Fatalf("create = %d", rr.Code)
	}
	// first erase: real diary → shred fires.
	if rr := eraseDiary(t, s, diary, owner); !strings.Contains(rr.Body.String(), `"dek_shredded":true`) {
		t.Fatalf("first erase must shred; body=%s", rr.Body.String())
	}
	// user re-provisions + writes → a FRESH DEK is minted for the new content.
	newDiary := seedBookOfKind(t, ctx, pool, owner, "diary")
	if rr := postDiaryEntry(t, s, newDiary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-20", "entry_zone": "UTC",
		"body": "fresh", "journal_kind": "primary", "language": "en"}, true); rr.Code != http.StatusCreated {
		t.Fatalf("re-provision write = %d", rr.Code)
	}
	shredsBefore := len(shredded)
	// re-erase the ORIGINAL (already-deleted) diary id → 0 rows → MUST NOT shred the fresh DEK.
	rr := eraseDiary(t, s, diary, owner)
	if !strings.Contains(rr.Body.String(), `"erased":false`) || !strings.Contains(rr.Body.String(), `"dek_shredded":false`) {
		t.Fatalf("0-row re-erase must be erased:false + dek_shredded:false; body=%s", rr.Body.String())
	}
	if len(shredded) != shredsBefore {
		t.Fatalf("a 0-row re-erase shredded the re-provisioned user's FRESH DEK — data loss (HIGH-1)")
	}
}

// P4 REUSE-GUARD — if the user re-provisions a diary and writes NEW content after the erase (the
// "erase & start fresh" path), the sweeper must NOT blind-shred the now-reused DEK (that would destroy
// the new content). It resolves the row WITHOUT shredding.
func TestDekShredSweeper_SkipsReusedDEK_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	kek := "book-diary-test-kek-not-jwt"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	failShred := true
	var attempts, shredded []string
	auth := fakeAuthDEKToggle(t, ring, &failShred, &attempts, &shredded)
	defer auth.Close()
	s.diaryCrypto = newDiaryCrypto(auth.URL, "tok", kek, "")

	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, `DELETE FROM pending_dek_shreds WHERE owner_user_id=$1`, owner)
	})
	if rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "entry_zone": "UTC",
		"body": "old secret", "journal_kind": "primary", "language": "en"}, true); rr.Code != http.StatusCreated {
		t.Fatalf("create = %d", rr.Code)
	}
	if rr := eraseDiary(t, s, diary, owner); rr.Code != http.StatusOK {
		t.Fatalf("erase = %d", rr.Code)
	}
	if pendingShredCount(t, s, owner) != 1 {
		t.Fatal("expected a pending shred after the failed inline shred")
	}
	attemptsBefore := len(attempts)

	// The user RE-PROVISIONS a fresh diary and writes NEW content (created after the erase → reused DEK).
	// Use the real write path so the chapter's created_at is now() (> the erase's requested_at).
	newDiary := seedBookOfKind(t, ctx, pool, owner, "diary")
	if rr := postDiaryEntry(t, s, newDiary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-20", "entry_zone": "UTC",
		"body": "brand new secret", "journal_kind": "primary", "language": "en"}, true); rr.Code != http.StatusCreated {
		t.Fatalf("seed fresh diary content = %d body=%s", rr.Code, rr.Body.String())
	}

	// The sweeper must SKIP (never shred the reused DEK) and resolve the row — no new DELETE to auth.
	converged, skipped, err := s.sweepPendingShreds(ctx, 10)
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if converged != 0 || skipped != 1 {
		t.Fatalf("reuse-guard: want converged=0 skipped=1, got %d/%d", converged, skipped)
	}
	if pendingShredCount(t, s, owner) != 0 {
		t.Fatal("the skipped (reused) row must be resolved, not left to spin")
	}
	if len(attempts) != attemptsBefore {
		t.Fatalf("the reuse-guard must skip BEFORE attempting a shred; got %d new DELETE attempts", len(attempts)-attemptsBefore)
	}
	if len(shredded) != 0 {
		t.Fatalf("the reused DEK must NEVER be shredded, got %v", shredded)
	}
}
