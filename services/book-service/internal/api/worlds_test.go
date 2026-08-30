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
	"github.com/loreweave/book-service/internal/config"
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

// ── G4 (W2) internal membership route: parse guards before pool access ──────
// The internal handler is behind the X-Internal-Token middleware (no JWT). Its
// pre-pool guards are the world_id path-param parse AND the user_id query-param
// parse — the latter is the parent-scope vector (a bad/missing user_id must NOT
// reach the ownership query). The ownership-404 + member-list happy paths hit
// the pool and are covered by the W2 cross-service live-smoke.

func TestInternalListWorldBooksInvalidWorldID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/internal/worlds/not-a-uuid/books?user_id="+uuid.New().String(), "", "", map[string]string{"world_id": "not-a-uuid"})
	s.internalListWorldBooks(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid world_id, got %d", rr.Code)
	}
}

// Review #5: prove the new route is INSIDE the requireInternalToken group (a
// future refactor that moved it out would drop the auth). Mount the real router
// and hit the path with no X-Internal-Token → 401 (short-circuits before any
// pool access, so a nil pool is fine).
func TestInternalListWorldBooksRequiresInternalToken(t *testing.T) {
	t.Parallel()
	s := &Server{cfg: &config.Config{InternalServiceToken: "secret-internal-token"}}
	srv := httptest.NewServer(s.Router())
	defer srv.Close()
	resp, err := http.Get(srv.URL + "/internal/worlds/" + uuid.New().String() + "/books?user_id=" + uuid.New().String())
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 without internal token, got %d", resp.StatusCode)
	}
}

func TestInternalListWorldBooksMissingUserID(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	wid := uuid.New()
	rr := httptest.NewRecorder()
	// valid world_id but NO user_id query param → 400 before the pool-backed
	// ownership check (the param can't be skipped to read any world's membership).
	req := worldReq(http.MethodGet, "/internal/worlds/"+wid.String()+"/books", "", "", map[string]string{"world_id": wid.String()})
	s.internalListWorldBooks(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing user_id, got %d", rr.Code)
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
	bibleBook := uuid.New()
	bibleChap := uuid.New()
	out := worldResponse(id, owner, "Cradle", &desc, 3, &bibleBook, &bibleChap, &now, &now)
	if out["world_id"] != id {
		t.Fatal("world_id key missing/mismatch")
	}
	if out["book_count"] != 3 {
		t.Fatalf("book_count=%v want 3", out["book_count"])
	}
	if out["name"] != "Cradle" {
		t.Fatalf("name=%v", out["name"])
	}
	// C20 follow-up: the bible handle (book + sort_order-0 chapter) is now exposed
	// so the FE can anchor lore against the world without learning a chapter id
	// out-of-band (unblocks C21).
	if out["bible_book_id"] != &bibleBook {
		t.Fatalf("bible_book_id=%v want %v", out["bible_book_id"], &bibleBook)
	}
	if out["bible_chapter_id"] != &bibleChap {
		t.Fatalf("bible_chapter_id=%v want %v", out["bible_chapter_id"], &bibleChap)
	}
}

// ── worldResponse: legacy world with no bible book/chapter → null handles ────
// A world predating C20 (or one whose bible provisioning is absent) must still
// serialize gracefully — the bible_* keys are present but null, never a 500.
func TestWorldResponseNullBibleHandles(t *testing.T) {
	t.Parallel()
	id := uuid.New()
	owner := uuid.New()
	now := time.Now()
	out := worldResponse(id, owner, "Legacy", nil, 0, nil, nil, &now, &now)
	v, ok := out["bible_book_id"]
	if !ok {
		t.Fatal("bible_book_id key must be present even when null")
	}
	if bid, isPtr := v.(*uuid.UUID); !isPtr || bid != nil {
		t.Fatalf("bible_book_id should be a nil *uuid.UUID, got %v", v)
	}
	c, ok := out["bible_chapter_id"]
	if !ok {
		t.Fatal("bible_chapter_id key must be present even when null")
	}
	if cid, isPtr := c.(*uuid.UUID); !isPtr || cid != nil {
		t.Fatalf("bible_chapter_id should be a nil *uuid.UUID, got %v", c)
	}
}

// ── the worlds list's `q` — server-side name search ─────────────────────────
//
// WorldPicker loaded one clamped page and filtered it in the browser, so a world past the
// page boundary could not be found by typing its name and the search box gave no sign that
// it had only looked at part of the list. Identical to the library-search defect that was
// filed for six days as a Vietnamese diacritic problem; the cure is the same, and so is the
// half that is easy to forget — the COUNT has to be filtered too.
func TestAppendWorldNameFilter(t *testing.T) {
	t.Parallel()
	owner := "u1"

	t.Run("no query adds no SQL and no args", func(t *testing.T) {
		frag, args := appendWorldNameFilter("", []any{owner})
		if frag != "" {
			t.Fatalf("empty query must add no SQL, got %q", frag)
		}
		if len(args) != 1 {
			t.Fatalf("empty query must append no args, got %d", len(args))
		}
	})

	t.Run("the placeholder names the position the pattern lands at", func(t *testing.T) {
		frag, args := appendWorldNameFilter("Aetheria", []any{owner})
		if frag != " AND w.name ILIKE $2" {
			t.Fatalf("fragment = %q, want $2 (after owner)", frag)
		}
		// $2 must BE the pattern. An off-by-one binds the owner id as the search
		// term and the endpoint silently returns nothing at all.
		if got, want := args[1], "%Aetheria%"; got != want {
			t.Fatalf("args[1] = %v, want %v", got, want)
		}
	})

	t.Run("multi-byte names survive verbatim", func(t *testing.T) {
		for _, q := range []string{"Đế", "封神", "Aetheria"} { // doc-language-gate: ok -- the corpus span the bug was reported against
			_, args := appendWorldNameFilter(q, []any{owner})
			if got, want := args[1], "%"+q+"%"; got != want {
				t.Fatalf("q=%q produced %v, want %v", q, got, want)
			}
		}
	})

	t.Run("LIKE metacharacters are escaped, not honoured", func(t *testing.T) {
		// Without this a user typing `%` matches every world and the search looks
		// like it silently ignored them.
		_, args := appendWorldNameFilter("50%_x", []any{owner})
		if got, want := args[1], `%50\%\_x%`; got != want {
			t.Fatalf("args[1] = %v, want %v", got, want)
		}
	})

	// The half that keeps `total` honest. The page and the COUNT take the SAME
	// fragment; if the count were left unfiltered, `total` would describe the whole
	// library while `items` described the search.
	t.Run("the page and the count share one fragment and one arg prefix", func(t *testing.T) {
		pageFrag, pageArgs := appendWorldNameFilter("Aetheria", []any{owner})
		countFrag, countArgs := appendWorldNameFilter("Aetheria", []any{owner})
		if pageFrag != countFrag {
			t.Fatalf("page and count fragments diverge: %q vs %q", pageFrag, countFrag)
		}
		pageArgs = append(pageArgs, 20, 0) // + limit, offset
		if len(countArgs) != 2 || len(pageArgs) != 4 {
			t.Fatalf("countArgs=%d pageArgs=%d, want 2 and 4", len(countArgs), len(pageArgs))
		}
		for i := range countArgs {
			if countArgs[i] != pageArgs[i] {
				t.Fatalf("arg %d diverges: count=%v page=%v", i, countArgs[i], pageArgs[i])
			}
		}
		// And the fragment must name `w.name`, not a bare `name`: the COUNT aliases
		// `worlds AS w` precisely so this one string works in both queries.
		if !strings.Contains(pageFrag, "w.name") {
			t.Fatalf("fragment %q must qualify the column so both queries can use it", pageFrag)
		}
	})
}

// The WIRING, not the helper. `TestAppendWorldNameFilter` above proves the fragment is
// correct; it went on passing when the COUNT was built without it, because the helper it
// drove was untouched. This drives the function that builds BOTH queries, so a predicate
// that reaches one and not the other is visible.
func TestBuildWorldListQueries(t *testing.T) {
	t.Parallel()
	owner := "u1"

	t.Run("with a query, the predicate reaches BOTH the page and the count", func(t *testing.T) {
		pageSQL, pageArgs, countSQL, countArgs := buildWorldListQueries(owner, "Aetheria", 20, 0)
		if !strings.Contains(pageSQL, "w.name ILIKE") {
			t.Fatalf("page query is missing the name predicate:\n%s", pageSQL)
		}
		// THE REGRESSION THIS EXISTS FOR. An unfiltered count reports `total` over
		// the whole library beside `items` from the search, so the picker says
		// "more matches exist" forever and the user hunts for rows that are not
		// missing — the truncation notice lying in the opposite direction.
		if !strings.Contains(countSQL, "w.name ILIKE") {
			t.Fatalf("COUNT is not filtered — total would describe the library "+
				"while items describe the search:\n%s", countSQL)
		}
		if len(countArgs) != 2 {
			t.Fatalf("count args = %d, want 2 (owner, pattern)", len(countArgs))
		}
		if len(pageArgs) != 4 {
			t.Fatalf("page args = %d, want 4 (owner, pattern, limit, offset)", len(pageArgs))
		}
		for i := range countArgs {
			if countArgs[i] != pageArgs[i] {
				t.Fatalf("arg %d diverges: count=%v page=%v", i, countArgs[i], pageArgs[i])
			}
		}
	})

	t.Run("without a query, neither carries a predicate", func(t *testing.T) {
		pageSQL, pageArgs, countSQL, countArgs := buildWorldListQueries(owner, "", 20, 0)
		if strings.Contains(pageSQL, "ILIKE") || strings.Contains(countSQL, "ILIKE") {
			t.Fatal("an empty q must add no predicate to either query")
		}
		if len(countArgs) != 1 || len(pageArgs) != 3 {
			t.Fatalf("args = count %d / page %d, want 1 and 3", len(countArgs), len(pageArgs))
		}
	})

	t.Run("the LIMIT/OFFSET placeholders follow the pattern, not precede it", func(t *testing.T) {
		// With a search the pattern takes $2, so the page must bind $3/$4. An
		// off-by-one here pages by the search pattern and returns nothing.
		pageSQL, _, _, _ := buildWorldListQueries(owner, "Aetheria", 20, 0)
		if !strings.Contains(pageSQL, "LIMIT $3 OFFSET $4") {
			t.Fatalf("expected LIMIT $3 OFFSET $4 with a search present:\n%s", pageSQL)
		}
		unfiltered, _, _, _ := buildWorldListQueries(owner, "", 20, 0)
		if !strings.Contains(unfiltered, "LIMIT $2 OFFSET $3") {
			t.Fatalf("expected LIMIT $2 OFFSET $3 with no search:\n%s", unfiltered)
		}
	})

	t.Run("the count aliases the table so one fragment serves both", func(t *testing.T) {
		_, _, countSQL, _ := buildWorldListQueries(owner, "Aetheria", 20, 0)
		if !strings.Contains(countSQL, "FROM worlds w") {
			t.Fatalf("the COUNT must alias `worlds AS w` for the shared fragment:\n%s", countSQL)
		}
	})
}
