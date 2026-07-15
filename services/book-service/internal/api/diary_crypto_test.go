package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
	crypto "github.com/loreweave/loreweave_crypto"
)

// a fake auth-service that mints+wraps a per-user DEK (like the real internalGetUserDEK) and records
// a DELETE (the crypto-shred).
func fakeAuthDEK(t *testing.T, ring crypto.Keyring, shredded *[]string) *httptest.Server {
	t.Helper()
	deks := map[string][]byte{}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		uid := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/internal/users/"), "/dek")
		switch r.Method {
		case http.MethodGet:
			dek, ok := deks[uid]
			if !ok {
				dek, _ = crypto.NewDEK()
				deks[uid] = dek
			}
			wrapped, ref, _ := crypto.WrapDEK(ring, dek, uid)
			w.Write([]byte(`{"wrapped_dek":"` + wrapped + `","key_ref":"` + ref + `"}`))
		case http.MethodDelete:
			delete(deks, uid)
			*shredded = append(*shredded, uid)
			w.WriteHeader(http.StatusNoContent)
		}
	}))
}

func TestDiaryCrypto_DisabledIsPlaintextPassthrough(t *testing.T) {
	dc := newDiaryCrypto("", "", "", "") // no key → disabled
	if dc.Enabled() {
		t.Fatal("no key ⇒ disabled")
	}
	// decrypt is a pass-through when disabled (rollout tolerance for plaintext rows).
	got, err := dc.decryptBody(context.Background(), uuid.New(), uuid.New(), "plain text", false)
	if err != nil || got != "plain text" {
		t.Fatalf("disabled decrypt must pass through: %q %v", got, err)
	}
}

func TestDiaryCrypto_EncryptRoundTripAndAtRestCiphertext(t *testing.T) {
	kek := "a-dedicated-diary-kek-not-jwt-secret"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	var shredded []string
	srv := fakeAuthDEK(t, ring, &shredded)
	defer srv.Close()

	dc := newDiaryCrypto(srv.URL, "tok", kek, "")
	if !dc.Enabled() {
		t.Fatal("a configured key ⇒ enabled")
	}
	owner, chID := uuid.New(), uuid.New()
	plain := "Met Minh about the migration. 今天很累."

	rawCol, jsonbCol, err := dc.encryptBody(context.Background(), owner, chID, plain)
	if err != nil {
		t.Fatal(err)
	}
	// AT REST: the ciphertext must NOT contain the plaintext prose (a dump leaks nothing).
	if strings.Contains(rawCol, "Minh") || strings.Contains(rawCol, "migration") {
		t.Fatal("body_text ciphertext leaks plaintext")
	}
	if strings.Contains(string(jsonbCol), "Minh") {
		t.Fatal("draft jsonb ciphertext leaks plaintext")
	}
	// the JSONB value is a JSON *string* (so the block-extraction trigger sees body->'content'=NULL).
	if jsonbCol[0] != '"' {
		t.Fatalf("draft jsonb must be a JSON string, got %s", string(jsonbCol[:1]))
	}

	// round-trips back to the plaintext for the FE read.
	got, err := dc.decryptBody(context.Background(), owner, chID, rawCol, true)
	if err != nil {
		t.Fatal(err)
	}
	if got != plain {
		t.Fatalf("decrypt mismatch: %q", got)
	}
}

func TestDiaryCrypto_AADBindsToChapter(t *testing.T) {
	kek := "diary-kek-aad"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	var shredded []string
	srv := fakeAuthDEK(t, ring, &shredded)
	defer srv.Close()
	dc := newDiaryCrypto(srv.URL, "tok", kek, "")
	owner, chID := uuid.New(), uuid.New()

	ct, _, _ := dc.encryptBody(context.Background(), owner, chID, "secret")
	// decrypting under a DIFFERENT chapter id (a moved-row adversary) must FAIL, not return garbage.
	if _, err := dc.decryptBody(context.Background(), owner, uuid.New(), ct, true); err == nil {
		t.Fatal("ciphertext moved to another chapter id must NOT decrypt (AAD binding)")
	}
}

func TestDiaryCrypto_ShredDestroysDEK(t *testing.T) {
	kek := "diary-kek-shred"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	var shredded []string
	srv := fakeAuthDEK(t, ring, &shredded)
	defer srv.Close()
	dc := newDiaryCrypto(srv.URL, "tok", kek, "")
	owner := uuid.New()

	if err := dc.destroyUserDEK(context.Background(), owner); err != nil {
		t.Fatalf("shred: %v", err)
	}
	if len(shredded) != 1 || shredded[0] != owner.String() {
		t.Fatalf("shred did not DELETE the user's DEK at auth: %v", shredded)
	}
}

func TestDiaryWordCount(t *testing.T) {
	if n := diaryWordCount("  one   two three  "); n != 3 {
		t.Fatalf("Latin word count = %d, want 3", n)
	}
	if n := diaryWordCount(""); n != 0 {
		t.Fatalf("empty word count = %d, want 0", n)
	}
	// CJK has no word spaces — char-count (excluding punct/space), mirroring the DB heuristic, so a
	// CJK diary doesn't report ~1 word. "今天很累" = 4 chars.
	if n := diaryWordCount("今天很累。"); n != 4 {
		t.Fatalf("CJK word count = %d, want 4 (char count excluding punctuation)", n)
	}
}

func mustDeriveKey(t *testing.T, s string) []byte {
	t.Helper()
	k, err := crypto.DeriveKey(s)
	if err != nil {
		t.Fatal(err)
	}
	return k
}

// ── end-to-end DB: encrypted-at-rest + empty blocks + decrypt round-trip + crypto-shred ──

func TestDiaryEntry_EncryptedAtRestAndShred_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()

	// enable encryption with a fake auth minting per-user DEKs.
	kek := "book-diary-test-kek-not-jwt"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	var shredded []string
	auth := fakeAuthDEK(t, ring, &shredded)
	defer auth.Close()
	s.diaryCrypto = newDiaryCrypto(auth.URL, "tok", kek, "")
	if !s.diaryCrypto.Enabled() {
		t.Fatal("test server must have encryption enabled")
	}

	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	plain := "Confidential: met Alice about the acquisition. 今天很累 déjà vu."

	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-12", "entry_zone": "UTC",
		"body": plain, "journal_kind": "primary", "language": "en",
	}, true)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create = %d, want 201. body=%s", rr.Code, rr.Body.String())
	}
	ch := entryChapterID(t, rr)

	// AT REST: all three prose columns are ciphertext; chapter_blocks is EMPTY (no 4th plaintext copy);
	// body_encrypted true; word_count computed in Go (the trigger would derive 0 from the empty blocks).
	var raw, draft, rev string
	var enc bool
	var blocks, wc int
	if err := pool.QueryRow(ctx, `
SELECT ro.body_text, d.body::text,
       (SELECT rv.body::text FROM chapter_revisions rv WHERE rv.chapter_id=c.id ORDER BY rv.created_at DESC LIMIT 1),
       c.body_encrypted, c.word_count,
       (SELECT count(*) FROM chapter_blocks cb WHERE cb.chapter_id=c.id)
FROM chapters c JOIN chapter_raw_objects ro ON ro.chapter_id=c.id JOIN chapter_drafts d ON d.chapter_id=c.id
WHERE c.id=$1`, ch).Scan(&raw, &draft, &rev, &enc, &wc, &blocks); err != nil {
		t.Fatalf("read at-rest columns: %v", err)
	}
	for name, col := range map[string]string{"body_text": raw, "draft.body": draft, "revision.body": rev} {
		if strings.Contains(col, "Alice") || strings.Contains(col, "acquisition") || strings.Contains(col, "今天") {
			t.Fatalf("%s leaks PLAINTEXT prose at rest: %q", name, col)
		}
	}
	if !enc {
		t.Fatal("body_encrypted must be true for an encrypted write")
	}
	if blocks != 0 {
		t.Fatalf("chapter_blocks must be EMPTY for an encrypted diary (the 4th plaintext copy), got %d", blocks)
	}
	// word_count must be the Go-computed value (the encrypted draft yields empty blocks → the trigger
	// would set 0). Body contains CJK, so diaryWordCount char-counts it (mirrors the DB heuristic).
	if wantWC := diaryWordCount(plain); wc != wantWC || wc == 0 {
		t.Fatalf("word_count must be the Go-computed count %d (not the trigger's 0), got %d", wantWC, wc)
	}

	// ROUND-TRIP: the stored ciphertext decrypts back to the exact plaintext (what listDiaryEntries serves).
	got, err := s.diaryCrypto.decryptBody(ctx, owner, uuid.MustParse(ch), raw, true)
	if err != nil {
		t.Fatalf("decrypt round-trip: %v", err)
	}
	if got != plain {
		t.Fatalf("decrypt mismatch: %q", got)
	}

	// CRYPTO-SHRED: erasing the diary destroys the user's DEK at auth (backup-resistant).
	dr := httptest.NewRequest(http.MethodDelete,
		"/internal/books/"+diary.String()+"/diary/erase?user_id="+owner.String(), nil)
	dr.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	drr := httptest.NewRecorder()
	s.Router().ServeHTTP(drr, dr)
	if drr.Code != http.StatusOK {
		t.Fatalf("erase = %d, want 200. body=%s", drr.Code, drr.Body.String())
	}
	if !strings.Contains(drr.Body.String(), `"dek_shredded":true`) {
		t.Fatalf("erase must crypto-shred the DEK; body=%s", drr.Body.String())
	}
	if len(shredded) != 1 || shredded[0] != owner.String() {
		t.Fatalf("auth did not receive the DEK-shred DELETE for the owner: %v", shredded)
	}
}

// cold-review HIGH-1 — a GENERIC (non-seam) write to a diary chapter's prose must be REFUSED by the DB
// guard, so no code path can store plaintext into a diary chapter (the "a dump leaks nothing" guarantee
// is unconditional). A novel chapter is unaffected.
func TestDiaryProseGuard_RefusesNonSeamWrite_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	kek := "book-diary-test-kek-not-jwt-secret-32chars"
	ring := crypto.NewKeyring(mustDeriveKey(t, kek))
	var shredded []string
	auth := fakeAuthDEK(t, ring, &shredded)
	defer auth.Close()
	s.diaryCrypto = newDiaryCrypto(auth.URL, "tok", kek, "")

	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-16", "entry_zone": "UTC",
		"body": "secret", "journal_kind": "primary", "language": "en",
	}, true)
	if rr.Code != http.StatusCreated {
		t.Fatalf("seed write = %d: %s", rr.Code, rr.Body.String())
	}
	ch := entryChapterID(t, rr)

	// A direct, UN-flagged UPDATE of the diary chapter's draft body (what a generic editor tool would do)
	// must be REFUSED by trg_guard_diary_prose_drafts — otherwise it would store plaintext at rest.
	_, err := pool.Exec(ctx, `UPDATE chapter_drafts SET body='{"leak":"plaintext"}'::jsonb WHERE chapter_id=$1`, ch)
	if err == nil {
		t.Fatal("HIGH-1: a non-seam write to a diary chapter's draft was ALLOWED — plaintext could be stored at rest")
	}
	if !strings.Contains(err.Error(), "diary") {
		t.Fatalf("expected the diary-prose guard to raise, got: %v", err)
	}

	// A NOVEL chapter's draft write is NOT blocked (the guard only fires for kind='diary').
	novel := seedBookOfKind(t, ctx, pool, owner, "novel")
	var novelCh uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state)
		 VALUES($1,'ch','ch.txt','en','text/plain',0,1,'k','active') RETURNING id`, novel).Scan(&novelCh); err != nil {
		t.Fatalf("seed novel chapter: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO chapter_drafts(chapter_id,body,draft_format,draft_updated_at,draft_version) VALUES($1,'{"a":1}'::jsonb,'json',now(),1)`,
		novelCh); err != nil {
		t.Fatalf("a novel chapter draft write must NOT be blocked by the diary guard: %v", err)
	}
}

// cold-review MED-4 — a DEK failure mid-write must FAIL CLOSED: abort the tx, persist NO row, never a
// plaintext fallback. Proven for the CREATE flow with a fake auth that 503s (no KEK configured).
func TestDiaryWrite_FailsClosedOnDEKUnavailable_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	// a fake auth that always 503s (no KEK) — the DEK can never be fetched.
	auth := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer auth.Close()
	s.diaryCrypto = newDiaryCrypto(auth.URL, "tok", "book-diary-test-kek-not-jwt-secret-32chars", "")

	owner := uuid.New()
	diary := seedBookOfKind(t, ctx, pool, owner, "diary")
	rr := postDiaryEntry(t, s, diary, map[string]any{
		"owner_user_id": owner.String(), "entry_date": "2026-03-17", "entry_zone": "UTC",
		"body": "must never be stored as plaintext", "journal_kind": "primary", "language": "en",
	}, true)
	if rr.Code != http.StatusInternalServerError || !strings.Contains(rr.Body.String(), "DIARY_ENCRYPT_UNAVAILABLE") {
		t.Fatalf("a DEK failure must fail closed with DIARY_ENCRYPT_UNAVAILABLE, got %d: %s", rr.Code, rr.Body.String())
	}
	// NOTHING persisted — the tx rolled back (no chapter, no plaintext prose anywhere).
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM chapters WHERE book_id=$1`, diary).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 0 {
		t.Fatalf("a failed-closed write must leave NO chapter row, found %d", n)
	}
}
