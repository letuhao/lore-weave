package api

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// C20 world container — unit tests for the non-pool-dependent seams (payload
// validation, bible-chapter helpers, the route→need grant mapping, and the
// no-token deny paths that short-circuit before any pool access). The DB-backed
// happy paths (CRUD, move/list, bible-chapter auto-creation) are covered by the
// real-PG cross-service live-smoke at VERIFY — matching the book-service
// server_test.go convention (helper-level + HTTP parsing, NOT pool-backed).

const worldSecret = "world-test-secret-at-least-32-chars-long!"

func worldJWT(t *testing.T, sub uuid.UUID) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   sub.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(worldSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return signed
}

func worldReq(method, target, body, token string, params map[string]string) *http.Request {
	var r *http.Request
	if body == "" {
		r = httptest.NewRequest(method, target, nil)
	} else {
		r = httptest.NewRequest(method, target, bytes.NewBufferString(body))
		r.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	rctx := chi.NewRouteContext()
	for k, v := range params {
		rctx.URLParams.Add(k, v)
	}
	return r.WithContext(context.WithValue(r.Context(), chi.RouteCtxKey, rctx))
}

// ── decodeWorldPayload ──────────────────────────────────────────────────────

func TestDecodeWorldPayload(t *testing.T) {
	t.Parallel()
	desc := "a realm"
	cases := []struct {
		name    string
		body    string
		wantOK  bool
		wantNm  string
		wantDsc *string
	}{
		{"valid name+desc", `{"name":"Cradle","description":"a realm"}`, true, "Cradle", &desc},
		{"valid name only", `{"name":"Cradle"}`, true, "Cradle", nil},
		{"empty name", `{"name":""}`, false, "", nil},
		{"whitespace name", `{"name":"   "}`, false, "", nil},
		{"missing name", `{"description":"x"}`, false, "", nil},
		{"malformed json", `{`, false, "", nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest(http.MethodPost, "/v1/worlds", strings.NewReader(tc.body))
			got, ok := decodeWorldPayload(r)
			if ok != tc.wantOK {
				t.Fatalf("ok=%v want %v", ok, tc.wantOK)
			}
			if ok && got.Name != tc.wantNm {
				t.Fatalf("name=%q want %q", got.Name, tc.wantNm)
			}
			if ok && tc.wantDsc != nil && (got.Description == nil || *got.Description != *tc.wantDsc) {
				t.Fatalf("desc=%v want %v", got.Description, *tc.wantDsc)
			}
		})
	}
}

// ── bibleChapterFilename — deterministic per book ───────────────────────────

func TestBibleChapterFilenameDeterministic(t *testing.T) {
	t.Parallel()
	b := uuid.New()
	if bibleChapterFilename(b) != bibleChapterFilename(b) {
		t.Fatal("bible filename must be deterministic per book (idempotent re-provision)")
	}
	if bibleChapterFilename(b) == bibleChapterFilename(uuid.New()) {
		t.Fatal("bible filename must differ per book")
	}
	if !strings.HasPrefix(bibleChapterFilename(b), "world-bible-") {
		t.Fatalf("unexpected bible filename: %s", bibleChapterFilename(b))
	}
}

// ── bookGrantError — the move/remove route→need mapping (no pool) ────────────

func TestBookGrantError(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name       string
		lvl        GrantLevel
		need       GrantLevel
		wantStatus int
	}{
		{"none → 404 (no oracle)", GrantNone, GrantEdit, http.StatusNotFound},
		{"view below edit → 403", GrantView, GrantEdit, http.StatusForbidden},
		{"edit satisfies edit → ok", GrantEdit, GrantEdit, 0},
		{"manage satisfies edit → ok", GrantManage, GrantEdit, 0},
		{"owner satisfies edit → ok", GrantOwner, GrantEdit, 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			status, _, _ := bookGrantError(tc.lvl, tc.need)
			if status != tc.wantStatus {
				t.Fatalf("status=%d want %d", status, tc.wantStatus)
			}
		})
	}
}

// ── owner-scope: no token → 401 on every world route (short-circuits, no pool) ─

func TestWorldRoutesRequireAuth(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	wid := uuid.New()
	bid := uuid.New()
	calls := []struct {
		name   string
		fn     func(http.ResponseWriter, *http.Request)
		req    *http.Request
	}{
		{"createWorld", s.createWorld, worldReq(http.MethodPost, "/v1/worlds", `{"name":"X"}`, "", nil)},
		{"listWorlds", s.listWorlds, worldReq(http.MethodGet, "/v1/worlds", "", "", nil)},
		{"getWorld", s.getWorld, worldReq(http.MethodGet, "/v1/worlds/"+wid.String(), "", "", map[string]string{"world_id": wid.String()})},
		{"patchWorld", s.patchWorld, worldReq(http.MethodPatch, "/v1/worlds/"+wid.String(), `{"name":"Y"}`, "", map[string]string{"world_id": wid.String()})},
		{"deleteWorld", s.deleteWorld, worldReq(http.MethodDelete, "/v1/worlds/"+wid.String(), "", "", map[string]string{"world_id": wid.String()})},
		{"moveBook", s.moveBookIntoWorld, worldReq(http.MethodPost, "/v1/worlds/"+wid.String()+"/books", `{"book_id":"`+bid.String()+`"}`, "", map[string]string{"world_id": wid.String()})},
		{"removeBook", s.removeBookFromWorld, worldReq(http.MethodDelete, "/v1/worlds/"+wid.String()+"/books/"+bid.String(), "", "", map[string]string{"world_id": wid.String(), "book_id": bid.String()})},
		{"listWorldBooks", s.listWorldBooks, worldReq(http.MethodGet, "/v1/worlds/"+wid.String()+"/books", "", "", map[string]string{"world_id": wid.String()})},
	}
	for _, c := range calls {
		t.Run(c.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			c.fn(rr, c.req)
			if rr.Code != http.StatusUnauthorized {
				t.Fatalf("%s: expected 401 without token, got %d", c.name, rr.Code)
			}
		})
	}
}

// ── createWorld: authed but invalid body → 400 (validation before pool) ─────

func TestCreateWorldRejectsEmptyName(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	uid := uuid.New()
	rr := httptest.NewRecorder()
	s.createWorld(rr, worldReq(http.MethodPost, "/v1/worlds", `{"name":""}`, worldJWT(t, uid), nil))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty name, got %d", rr.Code)
	}
}

// ── move/remove: authed, bad book_id → 400 BEFORE the pool-backed grant gate. ─
// requireWorldOwner queries the pool, so these use a stub resolver via a Server
// whose requireWorldOwner is satisfied through a fake — but since the world-owner
// check hits the pool, we instead assert the cheap parse guards: an invalid
// world_id URL param 400s before any pool access.

func TestMoveBookInvalidWorldID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	uid := uuid.New()
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodPost, "/v1/worlds/not-a-uuid/books", `{"book_id":"x"}`, worldJWT(t, uid), map[string]string{"world_id": "not-a-uuid"})
	s.moveBookIntoWorld(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid world_id, got %d", rr.Code)
	}
}

func TestRemoveBookInvalidBookID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	uid := uuid.New()
	wid := uuid.New()
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodDelete, "/v1/worlds/"+wid.String()+"/books/not-a-uuid", "", worldJWT(t, uid), map[string]string{"world_id": wid.String(), "book_id": "not-a-uuid"})
	s.removeBookFromWorld(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid book_id, got %d", rr.Code)
	}
}

// ── worldResponse shape — the FE contract (book_count + world_id key) ────────

func TestWorldResponseShape(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	owner := uuid.New()
	desc := "d"
	now := time.Now()
	out := worldResponse(id, owner, "Cradle", &desc, 3, &now, &now)
	if out["world_id"] != id {
		t.Fatal("world_id key missing/mismatch")
	}
	if out["book_count"] != 3 {
		t.Fatalf("book_count=%v want 3", out["book_count"])
	}
	if out["name"] != "Cradle" {
		t.Fatalf("name=%v", out["name"])
	}
}
