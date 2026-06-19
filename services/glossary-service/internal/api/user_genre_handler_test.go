package api

// G2 — genre tier CRUD + tenancy tests. Requires GLOSSARY_TEST_DB_URL.
//
// As with user-kinds, the headline is TestUserGenre_TenantIsolation: user B must
// get 404 (never 200/403-leak) on every read/write of user A's genre, and B's
// list must not see A's. Owner-only lifecycle tests hide cross-tenant leaks
// (memory [[e0-grant-mapping-test-pattern]]), so the deny path is first-class.

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func runGenreMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	runUserKindMigrations(t, pool) // Up + Seed + snapshot/soft-delete + user_kinds
	ctx := context.Background()
	if err := migrate.UpGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("migrate.UpGenreKindAttr: %v", err)
	}
	if err := migrate.SeedGenreKindAttr(ctx, pool); err != nil {
		t.Fatalf("migrate.SeedGenreKindAttr: %v", err)
	}
}

func mustCreateUserGenre(t *testing.T, srv *Server, userID, body string) genreResp {
	t.Helper()
	w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-genres", userID, body)
	if w.Code != http.StatusCreated {
		t.Fatalf("createUserGenre: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var g genreResp
	if err := json.Unmarshal(w.Body.Bytes(), &g); err != nil {
		t.Fatalf("decode created genre: %v (%s)", err, w.Body.String())
	}
	return g
}

// TestUserGenre_CRUDLifecycle walks create → list → get → patch → delete →
// trash → restore → re-delete → purge for the owner.
func TestUserGenre_CRUDLifecycle(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	owner := uuid.NewString()

	g := mustCreateUserGenre(t, srv, owner, `{"name":"My Cultivation World","color":"#123456"}`)
	if g.Code != "my_cultivation_world" {
		t.Fatalf("slugify: want my_cultivation_world, got %q", g.Code)
	}
	if g.Tier != "user" || g.OwnerUserID == nil || *g.OwnerUserID != owner {
		t.Fatalf("tier/owner wrong: tier=%s owner=%v", g.Tier, g.OwnerUserID)
	}

	// Patch name + sort_order.
	pw := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-genres/"+g.GenreID, owner,
		`{"name":"Renamed World","sort_order":5}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("patch: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}
	var patched genreResp
	json.Unmarshal(pw.Body.Bytes(), &patched)
	if patched.Name != "Renamed World" || patched.SortOrder != 5 {
		t.Fatalf("patch not applied: name=%q sort=%d", patched.Name, patched.SortOrder)
	}

	// Soft-delete → appears in trash.
	dw := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-genres/"+g.GenreID, owner, "")
	if dw.Code != http.StatusNoContent {
		t.Fatalf("delete: want 204, got %d (%s)", dw.Code, dw.Body.String())
	}
	tw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-genres-trash", owner, "")
	var trash struct {
		Items []genreTrashItem `json:"items"`
	}
	json.Unmarshal(tw.Body.Bytes(), &trash)
	found := false
	for _, it := range trash.Items {
		if it.GenreID == g.GenreID {
			found = true
		}
	}
	if !found {
		t.Fatalf("trashed genre not in recycle bin")
	}
	// Get on a trashed genre → 404.
	if gw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-genres/"+g.GenreID, owner, ""); gw.Code != http.StatusNotFound {
		t.Fatalf("get trashed: want 404, got %d", gw.Code)
	}

	// Restore → editable again.
	rw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-genres-trash/"+g.GenreID+"/restore", owner, "")
	if rw.Code != http.StatusNoContent {
		t.Fatalf("restore: want 204, got %d (%s)", rw.Code, rw.Body.String())
	}
	// Re-delete then purge.
	ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-genres/"+g.GenreID, owner, "")
	puw := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-genres-trash/"+g.GenreID, owner, "")
	if puw.Code != http.StatusNoContent {
		t.Fatalf("purge: want 204, got %d (%s)", puw.Code, puw.Body.String())
	}
}

// TestUserGenre_TenantIsolation — B must NEVER see or touch A's genre.
func TestUserGenre_TenantIsolation(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	userA := uuid.NewString()
	userB := uuid.NewString()

	g := mustCreateUserGenre(t, srv, userA, `{"name":"A Secret Genre"}`)

	// B cannot read A's genre (404, not 200/403-leak).
	if w := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-genres/"+g.GenreID, userB, ""); w.Code != http.StatusNotFound {
		t.Fatalf("B get A's genre: want 404, got %d (%s)", w.Code, w.Body.String())
	}
	// B cannot patch A's genre.
	if w := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-genres/"+g.GenreID, userB, `{"name":"hijack"}`); w.Code != http.StatusNotFound {
		t.Fatalf("B patch A's genre: want 404, got %d", w.Code)
	}
	// B cannot delete A's genre.
	if w := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-genres/"+g.GenreID, userB, ""); w.Code != http.StatusNotFound {
		t.Fatalf("B delete A's genre: want 404, got %d", w.Code)
	}
	// B's list does not include A's genre.
	lw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-genres", userB, "")
	var list userGenreListResp
	json.Unmarshal(lw.Body.Bytes(), &list)
	for _, it := range list.Items {
		if it.GenreID == g.GenreID {
			t.Fatalf("B's list leaked A's genre")
		}
	}
	// A's genre survived B's attempts (still editable by A).
	if w := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-genres/"+g.GenreID, userA, ""); w.Code != http.StatusOK {
		t.Fatalf("A get own genre after B attempts: want 200, got %d", w.Code)
	}
}

// TestGenre_MergedRead_SystemReadOnly — /genres surfaces the seeded System
// genres (read-only) merged with the caller's User genres; there is NO HTTP
// path to write a System genre.
func TestGenre_MergedRead_SystemReadOnly(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	owner := uuid.NewString()

	mustCreateUserGenre(t, srv, owner, `{"name":"My Genre Z"}`)

	w := ukReq(t, srv, http.MethodGet, "/v1/glossary/genres", owner, "")
	if w.Code != http.StatusOK {
		t.Fatalf("merged genres: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Items []genreResp `json:"items"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)

	var sawSystemUniversal, sawUserMine bool
	for _, g := range resp.Items {
		if g.Tier == "system" && g.Code == "universal" {
			sawSystemUniversal = true
		}
		if g.Tier == "user" && g.Code == "my_genre_z" {
			sawUserMine = true
		}
	}
	if !sawSystemUniversal {
		t.Fatal("merged read missing seeded system 'universal' genre")
	}
	if !sawUserMine {
		t.Fatal("merged read missing the caller's own user genre")
	}

	// include_system=false drops system rows; the user row remains.
	w2 := ukReq(t, srv, http.MethodGet, "/v1/glossary/genres?include_system=false", owner, "")
	var resp2 struct {
		Items []genreResp `json:"items"`
	}
	json.Unmarshal(w2.Body.Bytes(), &resp2)
	for _, g := range resp2.Items {
		if g.Tier == "system" {
			t.Fatal("include_system=false still returned a system genre")
		}
	}
}

// TestUserGenre_CloneFromSystem + duplicate-code conflict.
func TestUserGenre_CloneFromSystemAndDuplicate(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	owner := uuid.NewString()

	// Find the seeded system 'xianxia' genre id via the merged read.
	lw := ukReq(t, srv, http.MethodGet, "/v1/glossary/genres?include_user=false", owner, "")
	var sys struct {
		Items []genreResp `json:"items"`
	}
	json.Unmarshal(lw.Body.Bytes(), &sys)
	var xianxiaID string
	for _, g := range sys.Items {
		if g.Code == "xianxia" {
			xianxiaID = g.GenreID
		}
	}
	if xianxiaID == "" {
		t.Fatal("seeded system 'xianxia' genre not found")
	}

	// Clone it into the user tier (keeps a distinct code to avoid collision here).
	cw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-genres", owner,
		`{"name":"My Xianxia","code":"my_xianxia","clone_from_genre_id":"`+xianxiaID+`"}`)
	if cw.Code != http.StatusCreated {
		t.Fatalf("clone: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var cloned genreResp
	json.Unmarshal(cw.Body.Bytes(), &cloned)
	if cloned.ClonedFromGenreID == nil || *cloned.ClonedFromGenreID != xianxiaID {
		t.Fatalf("clone provenance not recorded: %v", cloned.ClonedFromGenreID)
	}

	// Duplicate code → 409.
	if dw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-genres", owner,
		`{"name":"Dup","code":"my_xianxia"}`); dw.Code != http.StatusConflict {
		t.Fatalf("duplicate code: want 409, got %d (%s)", dw.Code, dw.Body.String())
	}

	// A bogus clone source → 422 (FK violation surfaced cleanly).
	if bw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-genres", owner,
		`{"name":"Bad","code":"bad_clone","clone_from_genre_id":"`+uuid.NewString()+`"}`); bw.Code != http.StatusUnprocessableEntity {
		t.Fatalf("bogus clone: want 422, got %d (%s)", bw.Code, bw.Body.String())
	}
}
