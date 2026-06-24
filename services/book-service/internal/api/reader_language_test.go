package api

// KG-ML M3 (DD3) — reader-language preference tests.
//
// Two layers:
//   - nil-pool unit tests: auth/tenancy/validation that short-circuit BEFORE any
//     pool access (so the nil pool is never dereferenced) — these run everywhere.
//   - DB-gated happy-path (BOOK_TEST_DATABASE_URL via dbTestServer): set→get,
//     the AC3 cross-session read, the internal resolver, and clear→null.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// ── validation (pure) ────────────────────────────────────────────────────────

func TestReaderLang_TagRegex(t *testing.T) {
	t.Parallel()
	good := []string{"vi", "zh", "en", "zh-Hant", "pt-BR", "sr-Latn-RS"}
	bad := []string{"", "x", "english", "vi;DROP", "zh_", "1234", "zh--Hant", "v i"}
	for _, g := range good {
		if !langTagRe.MatchString(g) {
			t.Errorf("langTagRe rejected valid tag %q", g)
		}
	}
	for _, b := range bad {
		if langTagRe.MatchString(b) {
			t.Errorf("langTagRe accepted invalid tag %q", b)
		}
	}
}

// ── auth / tenancy (nil pool) ────────────────────────────────────────────────

func TestReaderLang_GetRequiresAuth(t *testing.T) {
	t.Parallel()
	s := mcpTestServer(GrantOwner) // grant irrelevant — no token short-circuits first
	req := httptest.NewRequest(http.MethodGet, "/v1/books/"+uuid.NewString()+"/reader-language", nil)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("no token: got %d want 401", rr.Code)
	}
}

func TestReaderLang_PutRequiresAuth(t *testing.T) {
	t.Parallel()
	s := mcpTestServer(GrantOwner)
	req := httptest.NewRequest(http.MethodPut, "/v1/books/"+uuid.NewString()+"/reader-language",
		strings.NewReader(`{"reader_language":"vi"}`))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("no token: got %d want 401", rr.Code)
	}
}

// A non-grantee on a private book (no SharingInternalURL → visibility "private")
// must 404 on PUT — they cannot even learn the book exists. Mirrors
// TestFavorites_AddDeniesNonGranteePrivateBook; canViewOrPublic returns false
// BEFORE any pool access.
func TestReaderLang_PutDeniesNonGranteePrivateBook(t *testing.T) {
	t.Parallel()
	s := denyServer(GrantNone)
	req := httptest.NewRequest(http.MethodPut, "/v1/books/"+uuid.NewString()+"/reader-language",
		strings.NewReader(`{"reader_language":"vi"}`))
	req.Header.Set("Authorization", "Bearer "+grantMapJWT(t))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("non-grantee PUT on private book: got %d want 404\n%s", rr.Code, rr.Body.String())
	}
}

// A viewer (grant=view) with a malformed tag gets 400 — validation fires after
// the view gate but before the pool write, so the nil pool is never reached.
func TestReaderLang_PutRejectsBadTag(t *testing.T) {
	t.Parallel()
	s := mcpTestServer(GrantView)
	uid := uuid.New()
	req := httptest.NewRequest(http.MethodPut, "/v1/books/"+uuid.NewString()+"/reader-language",
		strings.NewReader(`{"reader_language":"not-a-language-tag-because-way-too-long-xxxx"}`))
	req.Header.Set("Authorization", "Bearer "+mcpJWT(t, uid))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("malformed tag: got %d want 400\n%s", rr.Code, rr.Body.String())
	}
}

// The internal resolver requires the X-Internal-Token (the /internal mount gate).
func TestReaderLang_InternalRequiresToken(t *testing.T) {
	t.Parallel()
	s := mcpTestServer(GrantOwner)
	req := httptest.NewRequest(http.MethodGet,
		"/internal/books/"+uuid.NewString()+"/reader-language?user_id="+uuid.NewString(), nil)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	if rr.Code == http.StatusOK {
		t.Fatalf("internal route without token returned 200 — token gate missing")
	}
}

// ── happy path (DB-gated) ────────────────────────────────────────────────────

type readerLangResp struct {
	BookID         string  `json:"book_id"`
	ReaderLanguage *string `json:"reader_language"`
}

func TestReaderLang_SetGetClear_DB(t *testing.T) {
	s, pool := dbTestServer(t) // skips when BOOK_TEST_DATABASE_URL unset
	ctx := context.Background()
	owner := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'t') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}
	token := mcpJWT(t, owner)

	put := func(payload string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodPut, "/v1/books/"+bookID.String()+"/reader-language",
			strings.NewReader(payload))
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Content-Type", "application/json")
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		return rr
	}
	get := func() readerLangResp {
		req := httptest.NewRequest(http.MethodGet, "/v1/books/"+bookID.String()+"/reader-language", nil)
		req.Header.Set("Authorization", "Bearer "+token)
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("GET: got %d want 200\n%s", rr.Code, rr.Body.String())
		}
		var resp readerLangResp
		if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
			t.Fatalf("decode GET: %v", err)
		}
		return resp
	}

	// Unset → null.
	if r := get(); r.ReaderLanguage != nil {
		t.Fatalf("unset reader_language = %v, want null", *r.ReaderLanguage)
	}
	// Set vi.
	if rr := put(`{"reader_language":"vi"}`); rr.Code != http.StatusOK {
		t.Fatalf("PUT vi: got %d want 200\n%s", rr.Code, rr.Body.String())
	}
	// AC3 — observed on a *separate* request (cross-device proxy: same user,
	// fresh GET reads the server SSOT, not any per-request state).
	if r := get(); r.ReaderLanguage == nil || *r.ReaderLanguage != "vi" {
		t.Fatalf("after set, GET = %v, want vi", r.ReaderLanguage)
	}
	// Internal resolver returns the same value.
	{
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+bookID.String()+"/reader-language?user_id="+owner.String(), nil)
		req.Header.Set("X-Internal-Token", mcpTestToken)
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("internal GET: got %d want 200\n%s", rr.Code, rr.Body.String())
		}
		var resp readerLangResp
		_ = json.Unmarshal(rr.Body.Bytes(), &resp)
		if resp.ReaderLanguage == nil || *resp.ReaderLanguage != "vi" {
			t.Fatalf("internal resolver = %v, want vi", resp.ReaderLanguage)
		}
	}
	// Update vi → en (upsert path).
	if rr := put(`{"reader_language":"en"}`); rr.Code != http.StatusOK {
		t.Fatalf("PUT en: got %d want 200\n%s", rr.Code, rr.Body.String())
	}
	if r := get(); r.ReaderLanguage == nil || *r.ReaderLanguage != "en" {
		t.Fatalf("after update, GET = %v, want en", r.ReaderLanguage)
	}
	// Clear (empty) → null.
	if rr := put(`{"reader_language":"  "}`); rr.Code != http.StatusOK {
		t.Fatalf("PUT clear: got %d want 200\n%s", rr.Code, rr.Body.String())
	}
	if r := get(); r.ReaderLanguage != nil {
		t.Fatalf("after clear, GET = %v, want null", *r.ReaderLanguage)
	}
}

// Two users keep INDEPENDENT preferences on the same book (per-(user,book)
// scope — no shared mutable row).
func TestReaderLang_PerUserIsolation_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	other := uuid.New()
	var bookID uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO books(owner_user_id,title) VALUES($1,'t') RETURNING id`, owner).Scan(&bookID); err != nil {
		t.Fatalf("seed book: %v", err)
	}

	setLang := func(uid uuid.UUID, lang string) {
		req := httptest.NewRequest(http.MethodPut, "/v1/books/"+bookID.String()+"/reader-language",
			strings.NewReader(`{"reader_language":"`+lang+`"}`))
		req.Header.Set("Authorization", "Bearer "+mcpJWT(t, uid))
		req.Header.Set("Content-Type", "application/json")
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Fatalf("PUT %s for %v: got %d\n%s", lang, uid, rr.Code, rr.Body.String())
		}
	}
	readInternal := func(uid uuid.UUID) *string {
		req := httptest.NewRequest(http.MethodGet,
			"/internal/books/"+bookID.String()+"/reader-language?user_id="+uid.String(), nil)
		req.Header.Set("X-Internal-Token", mcpTestToken)
		rr := httptest.NewRecorder()
		s.Router().ServeHTTP(rr, req)
		var resp readerLangResp
		_ = json.Unmarshal(rr.Body.Bytes(), &resp)
		return resp.ReaderLanguage
	}

	setLang(owner, "vi")
	setLang(other, "en")
	if l := readInternal(owner); l == nil || *l != "vi" {
		t.Fatalf("owner pref = %v, want vi", l)
	}
	if l := readInternal(other); l == nil || *l != "en" {
		t.Fatalf("other pref = %v, want en", l)
	}
}
