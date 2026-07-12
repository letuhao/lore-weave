package api

// WS-1.8 (spec 06 §Q5/§Q6/§Q10) — POST /internal/books/{book_id}/diary/entry, the distiller's
// write seam. The invariants that matter and are proven here against a real DB:
//   - primary-per-day is idempotent + REPLACES (never a second entry, never appended content);
//   - two concurrent same-day writes COALESCE on the advisory lock (§Q6);
//   - a KEPT entry is never clobbered — the caller must supplement (§Q6);
//   - the entry can only land in the caller's own kind='diary' book (DR-12 discipline);
//   - an empty body is rejected (a low-signal day writes NO entry, §Q11), and the route is
//     internal-token-gated.
//
// DB-gated on BOOK_TEST_DATABASE_URL (via dbTestServer).

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
)

func postDiaryEntry(t *testing.T, s *Server, bookID uuid.UUID, body map[string]any, withToken bool) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/internal/books/"+bookID.String()+"/diary/entry", strings.NewReader(string(b)))
	req.Header.Set("Content-Type", "application/json")
	if withToken {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func entryChapterID(t *testing.T, rr *httptest.ResponseRecorder) string {
	t.Helper()
	var out struct {
		ChapterID string `json:"chapter_id"`
		Created   bool   `json:"created"`
		Replaced  bool   `json:"replaced"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (body=%s)", err, rr.Body.String())
	}
	return out.ChapterID
}

func TestDiaryEntry_PrimaryIsIdempotentAndReplaces_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	// First distill CREATES the day's primary entry.
	rr1 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-10", "entry_zone": "UTC",
		"body": "Met Minh about the API redesign.", "journal_kind": "primary", "language": "en",
	}, true)
	if rr1.Code != http.StatusCreated {
		t.Fatalf("first distill = %d, want 201. body=%s", rr1.Code, rr1.Body.String())
	}
	ch1 := entryChapterID(t, rr1)

	// The row really is a primary entry for that day, with the audit zone stored.
	var jk, zone string
	var ed string
	if err := pool.QueryRow(ctx,
		`SELECT journal_kind, entry_zone, entry_date::text FROM chapters WHERE id=$1`, ch1).
		Scan(&jk, &zone, &ed); err != nil {
		t.Fatalf("read entry: %v", err)
	}
	if jk != "primary" || zone != "UTC" || ed != "2026-03-10" {
		t.Fatalf("entry journal_kind=%q zone=%q date=%q, want primary/UTC/2026-03-10", jk, zone, ed)
	}

	// Re-distill the SAME day → 200, SAME chapter, body REPLACED (draft_version bumped), and
	// still exactly ONE primary for the day (never appended, never duplicated).
	rr2 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-10",
		"body": "Met Minh about the API redesign. Decided to ship v2 next week.", "journal_kind": "primary",
	}, true)
	if rr2.Code != http.StatusOK {
		t.Fatalf("re-distill = %d, want 200 (replace). body=%s", rr2.Code, rr2.Body.String())
	}
	if ch2 := entryChapterID(t, rr2); ch2 != ch1 {
		t.Fatalf("re-distill created a DIFFERENT chapter (%s -> %s) — must replace in place", ch1, ch2)
	}
	var nPrimary, draftVer int
	_ = pool.QueryRow(ctx,
		`SELECT count(*) FROM chapters WHERE book_id=$1 AND entry_date='2026-03-10' AND journal_kind='primary' AND lifecycle_state='active'`,
		diary).Scan(&nPrimary)
	_ = pool.QueryRow(ctx, `SELECT draft_version FROM chapter_drafts WHERE chapter_id=$1`, ch1).Scan(&draftVer)
	if nPrimary != 1 {
		t.Fatalf("primary entries for the day = %d, want exactly 1", nPrimary)
	}
	if draftVer != 2 {
		t.Fatalf("draft_version = %d after one replace, want 2 (the body was replaced, not appended)", draftVer)
	}
	// The raw body reflects the LATEST distill (replaced, not the original).
	var raw string
	_ = pool.QueryRow(ctx, `SELECT body_text FROM chapter_raw_objects WHERE chapter_id=$1`, ch1).Scan(&raw)
	if !strings.Contains(raw, "ship v2 next week") {
		t.Fatalf("raw body was not replaced with the latest distill: %q", raw)
	}
}

func TestDiaryEntry_ConcurrentSameDayCoalesce_DB(t *testing.T) {
	// Two devices "End my day" at the same instant → exactly ONE primary entry (§Q6 advisory lock).
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	const n = 8
	var wg sync.WaitGroup
	codes := make([]int, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			rr := postDiaryEntry(t, s, diary, map[string]any{
				"owner_user_id": owner.String(), "entry_date": "2026-03-11",
				"body": "A busy day.", "journal_kind": "primary",
			}, true)
			codes[i] = rr.Code
		}(i)
	}
	wg.Wait()

	for i, c := range codes {
		if c != http.StatusOK && c != http.StatusCreated {
			t.Fatalf("caller %d got %d, want 200/201", i, c)
		}
	}
	var nPrimary int
	_ = pool.QueryRow(ctx,
		`SELECT count(*) FROM chapters WHERE book_id=$1 AND entry_date='2026-03-11' AND journal_kind='primary' AND lifecycle_state='active'`,
		diary).Scan(&nPrimary)
	if nPrimary != 1 {
		t.Fatalf("concurrent same-day writes produced %d primary entries, want exactly 1", nPrimary)
	}
}

func TestDiaryEntry_KeptPrimaryIsNotClobbered_DB(t *testing.T) {
	// Post-confirm: once the user KEEPS a day (diary_kept_at set), a re-distill must NOT overwrite
	// it — it 409s so the caller writes a supplement instead (§Q6).
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "body": "Original kept entry.",
	}, true)
	ch := entryChapterID(t, rr)
	if _, err := pool.Exec(ctx, `UPDATE chapters SET diary_kept_at=now() WHERE id=$1`, ch); err != nil {
		t.Fatalf("mark kept: %v", err)
	}

	rr2 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "body": "A rewrite that must be refused.",
	}, true)
	if rr2.Code != http.StatusConflict || !strings.Contains(rr2.Body.String(), "DIARY_ENTRY_KEPT") {
		t.Fatalf("re-distill of a kept day = %d %s, want 409 DIARY_ENTRY_KEPT", rr2.Code, rr2.Body.String())
	}
	// The kept body is untouched.
	var raw string
	_ = pool.QueryRow(ctx, `SELECT body_text FROM chapter_raw_objects WHERE chapter_id=$1`, ch).Scan(&raw)
	if !strings.Contains(raw, "Original kept entry") {
		t.Fatalf("the kept entry was clobbered: %q", raw)
	}
}

func TestDiaryEntry_SupplementCreatesASecondChapter_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	_ = postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-13", "body": "The primary.", "journal_kind": "primary",
	}, true)
	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-13", "body": "An extra thought.", "journal_kind": "supplement",
	}, true)
	if rr.Code != http.StatusCreated {
		t.Fatalf("supplement = %d, want 201. body=%s", rr.Code, rr.Body.String())
	}
	var nPrimary, nSupp int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapters WHERE book_id=$1 AND entry_date='2026-03-13' AND journal_kind='primary' AND lifecycle_state='active'`, diary).Scan(&nPrimary)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapters WHERE book_id=$1 AND entry_date='2026-03-13' AND journal_kind='supplement' AND lifecycle_state='active'`, diary).Scan(&nSupp)
	if nPrimary != 1 || nSupp != 1 {
		t.Fatalf("primary=%d supplement=%d, want 1/1", nPrimary, nSupp)
	}
}

func TestDiaryEntry_RejectsNonDiaryWrongOwnerEmptyAndNoToken_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")

	base := func(over map[string]any) map[string]any {
		m := map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-03-14", "body": "x"}
		for k, v := range over {
			m[k] = v
		}
		return m
	}

	// A novel book → 409 BOOK_NOT_DIARY (assistant memory never lands in a shareable book).
	if rr := postDiaryEntry(t, s, novel, base(nil), true); rr.Code != http.StatusConflict || !strings.Contains(rr.Body.String(), "BOOK_NOT_DIARY") {
		t.Fatalf("novel target = %d %s, want 409 BOOK_NOT_DIARY", rr.Code, rr.Body.String())
	}
	// A body-supplied owner who does NOT own the diary → 403.
	if rr := postDiaryEntry(t, s, diary, base(map[string]any{"owner_user_id": stranger.String()}), true); rr.Code != http.StatusForbidden {
		t.Fatalf("wrong owner = %d, want 403. body=%s", rr.Code, rr.Body.String())
	}
	// Empty body → 400 (a low-signal day writes no entry, not a blank one).
	if rr := postDiaryEntry(t, s, diary, base(map[string]any{"body": "  "}), true); rr.Code != http.StatusBadRequest {
		t.Fatalf("empty body = %d, want 400. body=%s", rr.Code, rr.Body.String())
	}
	// No internal token → 401 (the guard fires before any work).
	if rr := postDiaryEntry(t, s, diary, base(nil), false); rr.Code != http.StatusUnauthorized {
		t.Fatalf("no token = %d, want 401", rr.Code)
	}
}
