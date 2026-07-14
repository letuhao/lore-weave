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
	"time"

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

// TestDiaryEntry_IsADraftNeverAutoPublished_DB locks the spec-11-Q4 invariant Phase 3's
// SCHEDULED distill depends on: the write seam produces a REVIEWABLE DRAFT — never an
// auto-published or auto-confirmed entry. A headless run cannot pass a confirm gate, so an
// unattended distill that could auto-canonize would be a privacy/correctness hole. The entry
// must land as draft (published_revision_id NULL, editorial_status not 'published') and unkept
// (diary_kept_at NULL) until the human reviews + keeps it.
func TestDiaryEntry_IsADraftNeverAutoPublished_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-11", "entry_zone": "UTC",
		"body":         "Shipped the migration; agreed the rollback plan with Priya.",
		"journal_kind": "primary", "language": "en",
	}, true)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create = %d, want 201. body=%s", rr.Code, rr.Body.String())
	}
	ch := entryChapterID(t, rr)

	var editorial string
	var publishedRev, keptAt *string
	if err := pool.QueryRow(ctx,
		`SELECT editorial_status, published_revision_id::text, diary_kept_at::text
		   FROM chapters WHERE id=$1`, ch).Scan(&editorial, &publishedRev, &keptAt); err != nil {
		t.Fatalf("read entry: %v", err)
	}
	if editorial == "published" {
		t.Fatalf("distilled entry editorial_status=%q — must NOT be auto-published", editorial)
	}
	if publishedRev != nil {
		t.Fatalf("distilled entry published_revision_id=%v — must be NULL (draft, not published)", *publishedRev)
	}
	if keptAt != nil {
		t.Fatalf("distilled entry diary_kept_at=%v — must be NULL (unattended distill can't auto-confirm)", *keptAt)
	}
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

// ── B2 (spec 03/06 §Q6) — POST /v1/books/{id}/diary/entries/{chapter_id}/keep ──

func keepDiaryEntry(t *testing.T, s *Server, bookID uuid.UUID, chapterID, caller uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost,
		"/v1/books/"+bookID.String()+"/diary/entries/"+chapterID.String()+"/keep", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestKeepDiaryEntry_ProtectsAgainstReDistillClobber_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-04-01", "body": "The original day.",
	}, true)
	ch := uuid.MustParse(entryChapterID(t, rr))

	// KEEP it → 200 + diary_kept_at set.
	kr := keepDiaryEntry(t, s, diary, ch, owner)
	if kr.Code != http.StatusOK {
		t.Fatalf("keep = %d, want 200. body=%s", kr.Code, kr.Body.String())
	}
	var kept *time.Time
	_ = pool.QueryRow(ctx, `SELECT diary_kept_at FROM chapters WHERE id=$1`, ch).Scan(&kept)
	if kept == nil {
		t.Fatal("diary_kept_at was not set by keep")
	}

	// A re-distill of the SAME day now REFUSES to clobber the kept primary (write seam 409).
	rr2 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-04-01", "body": "A rewrite that must be refused.",
	}, true)
	if rr2.Code != http.StatusConflict || !strings.Contains(rr2.Body.String(), "DIARY_ENTRY_KEPT") {
		t.Fatalf("re-distill after keep = %d %s, want 409 DIARY_ENTRY_KEPT", rr2.Code, rr2.Body.String())
	}

	// Idempotent: keeping again is 200 and does not move the timestamp.
	kr2 := keepDiaryEntry(t, s, diary, ch, owner)
	var kept2 *time.Time
	_ = pool.QueryRow(ctx, `SELECT diary_kept_at FROM chapters WHERE id=$1`, ch).Scan(&kept2)
	if kr2.Code != http.StatusOK || kept2 == nil || !kept2.Equal(*kept) {
		t.Fatalf("re-keep = %d, timestamp moved %v -> %v (want stable)", kr2.Code, kept, kept2)
	}
}

// ── WS-2.6a / D17 leg 1 — POST /v1/books/{id}/diary/entries/{chapter_id}/amend ──

func amendDiaryEntry(t *testing.T, s *Server, bookID, chapterID, caller uuid.UUID, body string) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(map[string]any{"body": body})
	req := httptest.NewRequest(http.MethodPost,
		"/v1/books/"+bookID.String()+"/diary/entries/"+chapterID.String()+"/amend", strings.NewReader(string(b)))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

// The D17 leg-1 proof: amending a KEPT entry writes a new revision with the corrected body AND
// PRESERVES diary_kept_at — unlike the distiller write-seam, which 409s a kept entry. This is the
// "leg 1 is missing and nobody noticed" gap the spec calls out.
func TestAmendDiaryEntry_PreservesKeptAndWritesRevision_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "Minh froze the Q3 budget.",
	}, true)
	ch := uuid.MustParse(entryChapterID(t, rr))
	keepDiaryEntry(t, s, diary, ch, owner) // kept — a re-distill would now 409
	var keptBefore *time.Time
	_ = pool.QueryRow(ctx, `SELECT diary_kept_at FROM chapters WHERE id=$1`, ch).Scan(&keptBefore)
	if keptBefore == nil {
		t.Fatal("precondition: entry should be kept")
	}
	var verBefore int
	_ = pool.QueryRow(ctx, `SELECT draft_version FROM chapter_drafts WHERE chapter_id=$1`, ch).Scan(&verBefore)

	// AMEND the kept entry (the correction) — must succeed (not 409) and preserve kept.
	ar := amendDiaryEntry(t, s, diary, ch, owner, "Alice froze the Q3 budget.")
	if ar.Code != http.StatusOK {
		t.Fatalf("amend a kept entry = %d, want 200. body=%s", ar.Code, ar.Body.String())
	}
	if !strings.Contains(ar.Body.String(), `"kept_preserved":true`) {
		t.Fatalf("amend must report kept_preserved:true, got %s", ar.Body.String())
	}
	// diary_kept_at UNCHANGED (an amendment doesn't un-keep).
	var keptAfter *time.Time
	_ = pool.QueryRow(ctx, `SELECT diary_kept_at FROM chapters WHERE id=$1`, ch).Scan(&keptAfter)
	if keptAfter == nil || !keptAfter.Equal(*keptBefore) {
		t.Fatalf("amend moved/cleared diary_kept_at: %v -> %v (must be preserved)", keptBefore, keptAfter)
	}
	// The SSOT body IS the correction (leg 1) — so a rebuild extracts "Alice", not "Minh".
	var raw string
	_ = pool.QueryRow(ctx, `SELECT body_text FROM chapter_raw_objects WHERE chapter_id=$1`, ch).Scan(&raw)
	if !strings.Contains(raw, "Alice") || strings.Contains(raw, "Minh") {
		t.Fatalf("amended raw body must be the correction (Alice, not Minh), got %q", raw)
	}
	// A new revision was written (audit trail) + the draft version bumped.
	var nRev int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapter_revisions WHERE chapter_id=$1 AND message='user amendment (D17)'`, ch).Scan(&nRev)
	if nRev != 1 {
		t.Fatalf("expected 1 'user amendment' revision, got %d", nRev)
	}
	var verAfter int
	_ = pool.QueryRow(ctx, `SELECT draft_version FROM chapter_drafts WHERE chapter_id=$1`, ch).Scan(&verAfter)
	if verAfter != verBefore+1 {
		t.Fatalf("draft_version = %d, want %d (bumped by the amendment)", verAfter, verBefore+1)
	}
}

// WS-3.7 review M2 — a weekly review is get-or-REPLACE by week (not a supplement that piles up). A
// re-run of the same week's rollup REPLACES the prior review; exactly one 'weekly' chapter results.
func TestDiaryEntry_WeeklyIsGetOrReplace_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	post := func(body string) *httptest.ResponseRecorder {
		return postDiaryEntry(t, s, diary, map[string]any{
			"owner_user_id": owner.String(), "entry_date": "2026-03-15", "journal_kind": "weekly",
			"body": body,
		}, true)
	}
	if r := post("First weekly review."); r.Code != http.StatusOK && r.Code != http.StatusCreated {
		t.Fatalf("first weekly = %d, want 200/201. body=%s", r.Code, r.Body.String())
	}
	if r := post("Second weekly review (a redelivery)."); r.Code != http.StatusOK && r.Code != http.StatusCreated {
		t.Fatalf("second weekly = %d, want 200/201 (replace). body=%s", r.Code, r.Body.String())
	}
	// Exactly ONE weekly chapter for the week — the redelivery replaced, not duplicated.
	var n int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapters
		WHERE book_id=$1 AND entry_date=$2 AND journal_kind='weekly' AND lifecycle_state='active'`,
		diary, "2026-03-15").Scan(&n)
	if n != 1 {
		t.Fatalf("expected 1 weekly chapter (get-or-replace), got %d — M2 duplicate bug", n)
	}
	var raw string
	_ = pool.QueryRow(ctx, `SELECT body_text FROM chapter_raw_objects ro
		JOIN chapters c ON c.id = ro.chapter_id
		WHERE c.book_id=$1 AND c.journal_kind='weekly'`, diary).Scan(&raw)
	if !strings.Contains(raw, "redelivery") {
		t.Fatalf("the weekly body must be the LATEST review, got %q", raw)
	}
}

func redactDiaryName(t *testing.T, s *Server, bookID, caller uuid.UUID, name string) *httptest.ResponseRecorder {
	t.Helper()
	b, _ := json.Marshal(map[string]any{"name": name})
	req := httptest.NewRequest(http.MethodPost,
		"/v1/books/"+bookID.String()+"/diary/redact", strings.NewReader(string(b)))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

// WS-2.6c source-text leg: redacting a name removes it (whole-word) from every diary entry that mentions
// it, writes an audit revision, is idempotent, and does NOT over-redact a substring (Minhang keeps Minh).
func TestRedactDiaryName_RemovesWholeWordAcrossEntries_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	r1 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-06-01", "body": "Minh froze the budget. Minh left early."}, true)
	ch1 := uuid.MustParse(entryChapterID(t, r1))
	r2 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-06-02", "body": "Alice met Minh in Minhang district."}, true)
	ch2 := uuid.MustParse(entryChapterID(t, r2))
	// An entry that never names Minh — must be untouched (no needless revision).
	r3 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-06-03", "body": "Shipped the redesign."}, true)
	ch3 := uuid.MustParse(entryChapterID(t, r3))

	rr := redactDiaryName(t, s, diary, owner, "Minh")
	if rr.Code != http.StatusOK {
		t.Fatalf("redact = %d, want 200. body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), `"redacted_entries":2`) {
		t.Fatalf("want 2 redacted entries, got %s", rr.Body.String())
	}
	get := func(ch uuid.UUID) string {
		var raw string
		_ = pool.QueryRow(ctx, `SELECT body_text FROM chapter_raw_objects WHERE chapter_id=$1`, ch).Scan(&raw)
		return raw
	}
	// Whole-word "Minh" gone from both; "Minhang" (substring) PRESERVED (no over-redaction).
	if strings.Contains(get(ch1), "Minh") {
		t.Fatalf("ch1 still names Minh: %q", get(ch1))
	}
	b2 := get(ch2)
	if strings.Contains(b2, "Minh ") || strings.Contains(b2, "met Minh") || !strings.Contains(b2, "Minhang") {
		t.Fatalf("ch2 redaction wrong (whole-word only): %q", b2)
	}
	if !strings.Contains(get(ch2), diaryRedactionPlaceholder) {
		t.Fatalf("ch2 should contain the redaction placeholder: %q", get(ch2))
	}
	// The untouched entry got no revision.
	var nRev3 int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapter_revisions WHERE chapter_id=$1 AND message='forget-person redaction (D17)'`, ch3).Scan(&nRev3)
	if nRev3 != 0 {
		t.Fatalf("untouched entry ch3 got %d redaction revisions, want 0", nRev3)
	}
	// Idempotent: a second redact finds nothing.
	rr2 := redactDiaryName(t, s, diary, owner, "Minh")
	if !strings.Contains(rr2.Body.String(), `"redacted_entries":0`) {
		t.Fatalf("second redact should be a no-op, got %s", rr2.Body.String())
	}
}

func TestRedactDiaryName_NonOwnerRefused_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	_ = postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-06-04", "body": "Minh was here."}, true)
	stranger := uuid.New()
	s.resolveBook = func(_ context.Context, _ uuid.UUID, user uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if user == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, owner, "active", nil
	}
	rr := redactDiaryName(t, s, diary, stranger, "Minh")
	if rr.Code != http.StatusForbidden && rr.Code != http.StatusNotFound {
		t.Fatalf("non-owner redact = %d, want 403/404. body=%s", rr.Code, rr.Body.String())
	}
}

func TestAmendDiaryEntry_NonOwnerRefused_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-05-02", "body": "A private entry.",
	}, true)
	ch := uuid.MustParse(entryChapterID(t, rr))
	// A stranger resolves to a non-owner grant → authBook refuses (the diary is never shared).
	stranger := uuid.New()
	s.resolveBook = func(_ context.Context, _ uuid.UUID, user uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if user == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, owner, "active", nil
	}
	ar := amendDiaryEntry(t, s, diary, ch, stranger, "malicious rewrite")
	if ar.Code != http.StatusForbidden && ar.Code != http.StatusNotFound {
		t.Fatalf("non-owner amend = %d, want 403/404 (no leak). body=%s", ar.Code, ar.Body.String())
	}
}

func TestKeepDiaryEntry_NonDiaryChapterIs404_DB(t *testing.T) {
	// journal_kind IS NULL for a novel chapter → the keep UPDATE matches 0 rows → 404.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")
	var chID uuid.UUID
	_ = pool.QueryRow(ctx, `
INSERT INTO chapters(book_id,original_filename,original_language,content_type,sort_order,storage_key,lifecycle_state)
VALUES($1,'c.txt','en','text/plain',1,'k','active') RETURNING id`, novel).Scan(&chID)

	rr := keepDiaryEntry(t, s, novel, chID, owner)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("keep a novel chapter = %d, want 404 (journal_kind NULL → not a diary entry)", rr.Code)
	}
}

func TestKeepDiaryEntry_NonOwnerIsRefused_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-04-02", "body": "private.",
	}, true)
	ch := uuid.MustParse(entryChapterID(t, rr))

	// The diary is owner-only; a stranger resolves to a non-owner grant → authBook refuses.
	s.resolveBook = func(_ context.Context, _ uuid.UUID, user uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if user == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, owner, "active", nil
	}
	kr := keepDiaryEntry(t, s, diary, ch, stranger)
	if kr.Code != http.StatusForbidden && kr.Code != http.StatusNotFound {
		t.Fatalf("non-owner keep = %d, want 403/404 (owner-only)", kr.Code)
	}
	var kept *time.Time
	_ = pool.QueryRow(ctx, `SELECT diary_kept_at FROM chapters WHERE id=$1`, ch).Scan(&kept)
	if kept != nil {
		t.Fatal("a non-owner must not have kept the entry")
	}
}

// ── D-R18 — GET /v1/books/{id}/diary/stats (OWNER-ONLY diary stats) ──

func getDiaryStats(t *testing.T, s *Server, bookID, caller uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/diary/stats", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestDiaryStats_CountsOwnerEntries_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	// Two days, one with a supplement → 3 entries across 2 distinct days.
	_ = postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "day one"}, true)
	_ = postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "extra", "journal_kind": "supplement"}, true)
	_ = postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-03", "body": "day three"}, true)

	rr := getDiaryStats(t, s, diary, owner)
	if rr.Code != http.StatusOK {
		t.Fatalf("stats = %d, want 200. body=%s", rr.Code, rr.Body.String())
	}
	var out struct {
		EntryCount   int    `json:"entry_count"`
		DistinctDays int    `json:"distinct_days"`
		FirstDate    string `json:"first_entry_date"`
		LastDate     string `json:"last_entry_date"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if out.EntryCount != 3 || out.DistinctDays != 2 {
		t.Fatalf("entry_count=%d distinct_days=%d, want 3/2", out.EntryCount, out.DistinctDays)
	}
	if out.FirstDate != "2026-05-01" || out.LastDate != "2026-05-03" {
		t.Fatalf("first/last = %q/%q, want 2026-05-01/2026-05-03", out.FirstDate, out.LastDate)
	}
}

func TestDiaryStats_NonOwnerCannotRead_DB(t *testing.T) {
	// D-R18's REQUIRED no-cross-user-leak proof: only the OWNER sees their diary stats. A diary is
	// never shared, so a stranger resolves to a non-owner grant → authBook refuses (no leak).
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	_ = postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "private"}, true)

	s.resolveBook = func(_ context.Context, _ uuid.UUID, user uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if user == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, owner, "active", nil
	}
	rr := getDiaryStats(t, s, diary, stranger)
	if rr.Code != http.StatusForbidden && rr.Code != http.StatusNotFound {
		t.Fatalf("non-owner diary stats = %d, want 403/404 (no cross-user leak)", rr.Code)
	}
}

// ── WS-1.10 — GET /v1/books/{id}/diary/entries (OWNER-ONLY list for the home timeline + review) ──

func listDiaryEntries(t *testing.T, s *Server, bookID, caller uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/diary/entries", nil)
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, caller))
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

type diaryEntryRow struct {
	ChapterID   string `json:"chapter_id"`
	EntryDate   string `json:"entry_date"`
	Body        string `json:"body"`
	JournalKind string `json:"journal_kind"`
	Kept        bool   `json:"kept"`
	WordCount   int    `json:"word_count"`
}

func TestListDiaryEntries_ReturnsBodyAndDateNewestFirst_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	_ = postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "the earlier day"}, true)
	rr2 := postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-03", "body": "Met Minh about the Q3 budget freeze."}, true)
	newestID := entryChapterID(t, rr2)

	rr := listDiaryEntries(t, s, diary, owner)
	if rr.Code != http.StatusOK {
		t.Fatalf("list = %d, want 200. body=%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Entries []diaryEntryRow `json:"entries"`
		Count   int             `json:"count"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v (body=%s)", err, rr.Body.String())
	}
	if out.Count != 2 || len(out.Entries) != 2 {
		t.Fatalf("count=%d entries=%d, want 2/2", out.Count, len(out.Entries))
	}
	// Newest-first: the 05-03 entry leads, and it carries the correct entry_date + the real body
	// (so the review can render + PROVE the date in one call), and it is NOT yet kept.
	first := out.Entries[0]
	if first.EntryDate != "2026-05-03" {
		t.Fatalf("newest entry_date=%q, want 2026-05-03", first.EntryDate)
	}
	if first.ChapterID != newestID {
		t.Fatalf("newest chapter_id=%q, want %q", first.ChapterID, newestID)
	}
	if !strings.Contains(first.Body, "Minh about the Q3 budget") {
		t.Fatalf("newest body=%q, want it to contain the distilled prose", first.Body)
	}
	if first.Kept {
		t.Fatalf("a freshly-distilled entry must not be kept until the user keeps it")
	}

	// After a KEEP (B2), the entry reads back kept=true — the review reflects the change.
	kr := keepDiaryEntry(t, s, diary, uuid.MustParse(newestID), owner)
	if kr.Code != http.StatusOK {
		t.Fatalf("keep = %d, want 200. body=%s", kr.Code, kr.Body.String())
	}
	rr = listDiaryEntries(t, s, diary, owner)
	_ = json.Unmarshal(rr.Body.Bytes(), &out)
	if !out.Entries[0].Kept {
		t.Fatalf("after keep, the newest entry must read kept=true")
	}
}

// ── D-R27 — DELETE /internal/books/{book_id}/diary/erase (hard row-delete of the diary) ──

func eraseDiaryBook(t *testing.T, s *Server, bookID, userID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodDelete,
		"/internal/books/"+bookID.String()+"/diary/erase?user_id="+userID.String(), nil)
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestEraseDiaryBook_HardDeletesBookAndChapters_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "Met Minh about the budget.",
	}, true)
	chID := entryChapterID(t, rr)

	// Erase.
	er := eraseDiaryBook(t, s, diary, owner)
	if er.Code != http.StatusOK {
		t.Fatalf("erase = %d, want 200. body=%s", er.Code, er.Body.String())
	}

	// The book row is GONE (hard-deleted, not soft-trashed).
	var nBooks int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM books WHERE id=$1`, diary).Scan(&nBooks)
	if nBooks != 0 {
		t.Fatalf("book rows after erase = %d, want 0 (hard-deleted)", nBooks)
	}
	// The chapter + its content cascade-deleted (ON DELETE CASCADE).
	var nCh, nRaw int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapters WHERE book_id=$1`, diary).Scan(&nCh)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM chapter_raw_objects WHERE chapter_id=$1`, chID).Scan(&nRaw)
	if nCh != 0 || nRaw != 0 {
		t.Fatalf("after erase: chapters=%d raw_objects=%d, want 0/0 (cascade)", nCh, nRaw)
	}
}

func TestEraseDiaryBook_RefusesForeignOwnerAndNonDiary_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")

	// A STRANGER's user_id must not delete the owner's diary (owner-scoped in the DELETE predicate).
	_ = eraseDiaryBook(t, s, diary, stranger)
	var n int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM books WHERE id=$1`, diary).Scan(&n)
	if n != 1 {
		t.Fatalf("stranger erased the owner's diary (rows=%d, want 1) — CROSS-TENANT DELETE", n)
	}
	// A NOVEL (kind<>'diary') is never hard-deleted through this route (the kind='diary' guard).
	_ = eraseDiaryBook(t, s, novel, owner)
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM books WHERE id=$1`, novel).Scan(&n)
	if n != 1 {
		t.Fatalf("the diary-erase route deleted a NOVEL (rows=%d, want 1) — kind guard failed", n)
	}
}

func TestListDiaryEntries_NonOwnerCannotRead_DB(t *testing.T) {
	// Same no-cross-user-leak posture as diaryStats: a diary is never shared, so a non-owner is
	// refused — the entries' bodies never leak to another user.
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	stranger := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	_ = postDiaryEntry(t, s, diary, map[string]any{"owner_user_id": owner.String(), "entry_date": "2026-05-01", "body": "private prose"}, true)

	s.resolveBook = func(_ context.Context, _ uuid.UUID, user uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		if user == owner {
			return GrantOwner, owner, "active", nil
		}
		return GrantNone, owner, "active", nil
	}
	rr := listDiaryEntries(t, s, diary, stranger)
	if rr.Code != http.StatusForbidden && rr.Code != http.StatusNotFound {
		t.Fatalf("non-owner diary entries = %d, want 403/404 (no cross-user leak)", rr.Code)
	}
}
