package api

// G2c — attribute-definition + kind↔genre-link tests. Requires GLOSSARY_TEST_DB_URL.
// Headline tenancy guards: attach-by-code rejects System/other-tenant kind|genre
// ids (422), and user B can never touch user A's attribute (404) or a kind's links.

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

// systemIDs fetches the seeded system character kind + universal genre ids.
func systemCharUniversal(t *testing.T, srv *Server) (charKind, universalGenre string) {
	t.Helper()
	ctx := context.Background()
	if err := srv.pool.QueryRow(ctx, `SELECT kind_id::text FROM system_kinds WHERE code='character'`).Scan(&charKind); err != nil {
		t.Fatalf("system character kind: %v", err)
	}
	if err := srv.pool.QueryRow(ctx, `SELECT genre_id::text FROM system_genres WHERE code='universal'`).Scan(&universalGenre); err != nil {
		t.Fatalf("system universal genre: %v", err)
	}
	return
}

func TestSystemAttributes_ReadOnlyAndPopulated(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	owner := uuid.NewString()
	charKind, universalGenre := systemCharUniversal(t, srv)

	w := ukReq(t, srv, http.MethodGet,
		"/v1/glossary/system-attributes?kind_id="+charKind+"&genre_id="+universalGenre, owner, "")
	if w.Code != http.StatusOK {
		t.Fatalf("system-attributes read: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	var resp struct {
		Items []attributeResp `json:"items"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	// character lifted 13 attrs into (character, universal) at seed.
	if len(resp.Items) == 0 {
		t.Fatal("system character×universal attributes empty (seed lift missing)")
	}
	for _, a := range resp.Items {
		if a.Tier != "system" {
			t.Fatalf("system-attributes returned a non-system tier: %s", a.Tier)
		}
	}
	// There is NO write route for system attributes (read-only). A POST to the
	// user-attributes endpoint with the SYSTEM kind/genre is rejected below.
}

func TestUserAttribute_AttachByCodeAndTenancy(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	userA := uuid.NewString()
	userB := uuid.NewString()
	charKind, universalGenre := systemCharUniversal(t, srv)

	// A's own user kind + user genre.
	kindA := mustCreateUserKind(t, srv, userA, `{"name":"A Kind"}`)
	genreA := mustCreateUserGenre(t, srv, userA, `{"name":"A Genre"}`)

	mkBody := func(kindID, genreID, name string) string {
		return `{"kind_id":"` + kindID + `","genre_id":"` + genreID + `","name":"` + name + `","field_type":"text"}`
	}

	// Happy path: attach onto A's OWN kind×genre → 201.
	cw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-attributes", userA,
		mkBody(kindA.UserKindID, genreA.GenreID, "Dao Heart"))
	if cw.Code != http.StatusCreated {
		t.Fatalf("create user attr: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var created attributeResp
	json.Unmarshal(cw.Body.Bytes(), &created)
	if created.Tier != "user" || created.Code != "dao_heart" {
		t.Fatalf("created attr wrong: tier=%s code=%s", created.Tier, created.Code)
	}

	// Attach-by-code violations → 422 (a body-validation failure, not 404):
	// (a) SYSTEM kind id.
	if w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-attributes", userA,
		mkBody(charKind, genreA.GenreID, "X")); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("attach to system kind: want 422, got %d (%s)", w.Code, w.Body.String())
	}
	// (b) SYSTEM genre id.
	if w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-attributes", userA,
		mkBody(kindA.UserKindID, universalGenre, "X")); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("attach to system genre: want 422, got %d (%s)", w.Code, w.Body.String())
	}
	// (c) B attaching onto A's kind → 422 (B doesn't own it).
	if w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-attributes", userB,
		mkBody(kindA.UserKindID, genreA.GenreID, "X")); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("B attach to A's kind: want 422, got %d (%s)", w.Code, w.Body.String())
	}

	// Duplicate code on the same kind×genre → 409.
	if w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-attributes", userA,
		mkBody(kindA.UserKindID, genreA.GenreID, "Dao Heart")); w.Code != http.StatusConflict {
		t.Fatalf("dup attr code: want 409, got %d (%s)", w.Code, w.Body.String())
	}

	// Tenancy: B cannot patch or delete A's attribute → 404.
	if w := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-attributes/"+created.AttrID, userB,
		`{"name":"hijack"}`); w.Code != http.StatusNotFound {
		t.Fatalf("B patch A's attr: want 404, got %d (%s)", w.Code, w.Body.String())
	}
	if w := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-attributes/"+created.AttrID, userB, ""); w.Code != http.StatusNotFound {
		t.Fatalf("B delete A's attr: want 404, got %d", w.Code)
	}

	// A can patch + list + delete its own attr.
	if w := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-attributes/"+created.AttrID, userA,
		`{"is_required":true}`); w.Code != http.StatusOK {
		t.Fatalf("A patch own attr: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	lw := ukReq(t, srv, http.MethodGet,
		"/v1/glossary/user-attributes?kind_id="+kindA.UserKindID+"&genre_id="+genreA.GenreID, userA, "")
	var list struct {
		Items []attributeResp `json:"items"`
	}
	json.Unmarshal(lw.Body.Bytes(), &list)
	if len(list.Items) != 1 || !list.Items[0].IsRequired {
		t.Fatalf("A list own attrs: want 1 required, got %d", len(list.Items))
	}
	if w := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-attributes/"+created.AttrID, userA, ""); w.Code != http.StatusNoContent {
		t.Fatalf("A delete own attr: want 204, got %d", w.Code)
	}
}

func TestUserKindGenres_LinkTenancy(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	userA := uuid.NewString()
	userB := uuid.NewString()

	kindA := mustCreateUserKind(t, srv, userA, `{"name":"A Kind For Links"}`)
	g1 := mustCreateUserGenre(t, srv, userA, `{"name":"Link Genre One"}`)
	g2 := mustCreateUserGenre(t, srv, userA, `{"name":"Link Genre Two"}`)

	// PUT the full set {g1, g2} → list shows both.
	pw := ukReq(t, srv, http.MethodPut, "/v1/glossary/user-kinds/"+kindA.UserKindID+"/genres", userA,
		`{"genre_ids":["`+g1.GenreID+`","`+g2.GenreID+`"]}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("put links: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}
	var set struct {
		Items []genreResp `json:"items"`
	}
	json.Unmarshal(pw.Body.Bytes(), &set)
	if len(set.Items) != 2 {
		t.Fatalf("put links: want 2, got %d", len(set.Items))
	}

	// Remove g1, then add it back via the single-link route.
	if w := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-kinds/"+kindA.UserKindID+"/genres/"+g1.GenreID, userA, ""); w.Code != http.StatusNoContent {
		t.Fatalf("delete link: want 204, got %d", w.Code)
	}
	if w := ukReq(t, srv, http.MethodPut, "/v1/glossary/user-kinds/"+kindA.UserKindID+"/genres/"+g1.GenreID, userA, ""); w.Code != http.StatusNoContent {
		t.Fatalf("add link: want 204, got %d (%s)", w.Code, w.Body.String())
	}

	// PUT with a genre NOT owned by A → 422.
	gB := mustCreateUserGenre(t, srv, userB, `{"name":"B Genre"}`)
	if w := ukReq(t, srv, http.MethodPut, "/v1/glossary/user-kinds/"+kindA.UserKindID+"/genres", userA,
		`{"genre_ids":["`+gB.GenreID+`"]}`); w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("put link to B's genre: want 422, got %d (%s)", w.Code, w.Body.String())
	}

	// Tenancy: B cannot list or replace A's kind's links → 404 (doesn't own the kind).
	if w := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds/"+kindA.UserKindID+"/genres", userB, ""); w.Code != http.StatusNotFound {
		t.Fatalf("B list A's kind links: want 404, got %d", w.Code)
	}
	if w := ukReq(t, srv, http.MethodPut, "/v1/glossary/user-kinds/"+kindA.UserKindID+"/genres", userB,
		`{"genre_ids":[]}`); w.Code != http.StatusNotFound {
		t.Fatalf("B replace A's kind links: want 404, got %d", w.Code)
	}
}
