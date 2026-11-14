package api

// Codex review on PR #325 (P2): re-distilling an existing ja/zh/ko diary entry
// as English, with diary encryption DISABLED, left both the entry's word_count
// and the diary's total_words wrong. prepDiaryBody returns wc=-1 in that mode
// ("let the DB trigger compute it"), but the replace path UPDATEs the draft
// BEFORE the chapters row — so fn_recompute_chapter_word_count reads the
// STALE original_language ('ja') and char-counts the English prose (the
// language alone forces the CJK branch), and the chapters UPDATE's
// `word_count=CASE WHEN $7 >= 0 THEN $7 ELSE word_count END` then preserves
// that wrong value. The fix recomputes with the NEW language in the same
// chapters UPDATE.
//
// This test drives the real endpoint twice (ja create, en re-distill) and
// asserts the persisted counts. It FAILS on the pre-fix code (word_count 35,
// the English prose char-counted under 'ja') and passes once the recompute
// uses the new language (word_count 9).
//
// DB-gated on BOOK_TEST_DATABASE_URL (via dbTestServer). Encryption is
// disabled in the test server (no DIARY_ENCRYPTION_KEY in mcpTestServer),
// which is exactly the mode that bites.

import (
	"context"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestDiaryEntry_ReDistillAsEnglish_RecomputesWordCountInNewLanguage_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")

	// First distill: Japanese body. 18 CJK chars, no spaces/punctuation, so the
	// trigger's CJK branch counts 18.
	jaBody := "今日は良い天気でした明日も頑張ります"
	rr1 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "entry_zone": "UTC",
		"body": jaBody, "journal_kind": "primary", "language": "ja",
	}, true)
	if rr1.Code != http.StatusCreated {
		t.Fatalf("ja create = %d, want 201. body=%s", rr1.Code, rr1.Body.String())
	}
	ch := entryChapterID(t, rr1)
	var wc int
	var lang string
	if err := pool.QueryRow(ctx,
		`SELECT word_count, original_language FROM chapters WHERE id=$1`, ch).Scan(&wc, &lang); err != nil {
		t.Fatalf("read entry after ja create: %v", err)
	}
	if wc != 18 || lang != "ja" {
		t.Fatalf("after ja create: word_count=%d lang=%q, want 18/ja (trigger must char-count CJK)", wc, lang)
	}

	// Re-distill the SAME day as English. 9 whitespace-separated words; the
	// prose has 35 letters, so a CJK char-count would report 35.
	enBody := "The quick brown fox jumps over the lazy dog"
	rr2 := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "entry_zone": "UTC",
		"body": enBody, "journal_kind": "primary", "language": "en",
	}, true)
	if rr2.Code != http.StatusOK {
		t.Fatalf("en re-distill = %d, want 200 (replace). body=%s", rr2.Code, rr2.Body.String())
	}
	if err := pool.QueryRow(ctx,
		`SELECT word_count, original_language FROM chapters WHERE id=$1`, ch).Scan(&wc, &lang); err != nil {
		t.Fatalf("read entry after en re-distill: %v", err)
	}
	if lang != "en" {
		t.Fatalf("after en re-distill: original_language=%q, want en", lang)
	}
	if wc != 9 {
		t.Fatalf("after en re-distill: word_count=%d, want 9 (English word count); 35 means the recompute still used the stale 'ja' language", wc)
	}
	// The diary total_words is SUM(word_count) over the diary chapters, so the
	// wrong entry count propagates there too.
	var total int64
	if err := pool.QueryRow(ctx,
		`SELECT COALESCE(sum(word_count),0) FROM chapters WHERE book_id=$1 AND journal_kind IS NOT NULL AND lifecycle_state='active'`,
		diary).Scan(&total); err != nil {
		t.Fatalf("read total_words: %v", err)
	}
	if total != 9 {
		t.Fatalf("diary total_words=%d, want 9", total)
	}
}
