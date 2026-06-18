package api

// SS-4 — T2 per-user kind CRUD integration tests. Requires GLOSSARY_TEST_DB_URL.
//
// The headline test is TestUserKind_TenantIsolation: user B must get 404 (never
// 200/403-leak) on every read/write of user A's kind, and B's list must not see
// A's kinds. Owner-only lifecycle tests hide cross-tenant leaks (the E0 lesson,
// memory [[e0-grant-mapping-test-pattern]]), so the deny-path is asserted first-class.

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/migrate"
)

func runUserKindMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	// Up + Seed (creates system_kinds + the 12 defaults that clone reads) + the
	// snapshot/soft-delete chain, then the SS-4 user_kinds tables.
	runK2aMigrations(t, pool)
	if err := migrate.UpUserKinds(context.Background(), pool); err != nil {
		t.Fatalf("migrate.UpUserKinds: %v", err)
	}
}

// ukReq fires an authenticated request as the given user and returns the recorder.
func ukReq(t *testing.T, srv *Server, method, url, userID, body string) *httptest.ResponseRecorder {
	t.Helper()
	var r *http.Request
	if body == "" {
		r = httptest.NewRequest(method, url, nil)
	} else {
		r = httptest.NewRequest(method, url, bytes.NewReader([]byte(body)))
	}
	r.Header.Set("Authorization", "Bearer "+makeExportToken(t, userID))
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, r)
	return w
}

func mustCreateUserKind(t *testing.T, srv *Server, userID, body string) userKindDetailResp {
	t.Helper()
	w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds", userID, body)
	if w.Code != http.StatusCreated {
		t.Fatalf("createUserKind: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var d userKindDetailResp
	if err := json.Unmarshal(w.Body.Bytes(), &d); err != nil {
		t.Fatalf("decode created kind: %v (%s)", err, w.Body.String())
	}
	return d
}

// TestUserKind_CRUDLifecycle walks the full owner happy-path: create → list →
// get → patch → add attr → patch attr → delete attr → soft-delete → trash →
// restore → re-delete → purge.
func TestUserKind_CRUDLifecycle(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runUserKindMigrations(t, pool)
	owner := uuid.NewString()

	kind := mustCreateUserKind(t, srv, owner,
		`{"name":"My Faction","description":"d","color":"#123456","genre_tags":["fantasy"]}`)
	if kind.Code != "my_faction" {
		t.Fatalf("slugify: want code my_faction, got %q", kind.Code)
	}
	if kind.OwnerUserID != owner {
		t.Fatalf("owner: want %s, got %s", owner, kind.OwnerUserID)
	}

	// List includes it.
	lw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds", owner, "")
	if lw.Code != http.StatusOK {
		t.Fatalf("list: want 200, got %d (%s)", lw.Code, lw.Body.String())
	}
	var list userKindListResp
	json.Unmarshal(lw.Body.Bytes(), &list)
	if list.Total < 1 {
		t.Fatalf("list total: want >=1, got %d", list.Total)
	}

	// Get detail.
	gw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds/"+kind.UserKindID, owner, "")
	if gw.Code != http.StatusOK {
		t.Fatalf("get: want 200, got %d (%s)", gw.Code, gw.Body.String())
	}

	// Patch name + is_active.
	pw := ukReq(t, srv, http.MethodPatch, "/v1/glossary/user-kinds/"+kind.UserKindID, owner,
		`{"name":"Renamed Faction","is_active":false}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("patch: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}
	var patched userKindDetailResp
	json.Unmarshal(pw.Body.Bytes(), &patched)
	if patched.Name != "Renamed Faction" || patched.IsActive {
		t.Fatalf("patch not applied: name=%q is_active=%v", patched.Name, patched.IsActive)
	}

	// Add an attribute.
	aw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds/"+kind.UserKindID+"/attributes", owner,
		`{"name":"Leader","field_type":"text","is_required":true}`)
	if aw.Code != http.StatusCreated {
		t.Fatalf("add attr: want 201, got %d (%s)", aw.Code, aw.Body.String())
	}
	var attr userKindAttrResp
	json.Unmarshal(aw.Body.Bytes(), &attr)
	if attr.Code != "leader" || !attr.IsRequired {
		t.Fatalf("attr: want code leader/required, got %q/%v", attr.Code, attr.IsRequired)
	}

	// Patch the attribute.
	apw := ukReq(t, srv, http.MethodPatch,
		"/v1/glossary/user-kinds/"+kind.UserKindID+"/attributes/"+attr.AttrID, owner,
		`{"is_required":false,"field_type":"textarea"}`)
	if apw.Code != http.StatusOK {
		t.Fatalf("patch attr: want 200, got %d (%s)", apw.Code, apw.Body.String())
	}

	// Delete the attribute (no entity data → no force needed).
	adw := ukReq(t, srv, http.MethodDelete,
		"/v1/glossary/user-kinds/"+kind.UserKindID+"/attributes/"+attr.AttrID, owner, "")
	if adw.Code != http.StatusNoContent {
		t.Fatalf("delete attr: want 204, got %d (%s)", adw.Code, adw.Body.String())
	}

	// Soft-delete the kind.
	dw := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-kinds/"+kind.UserKindID, owner, "")
	if dw.Code != http.StatusNoContent {
		t.Fatalf("delete kind: want 204, got %d (%s)", dw.Code, dw.Body.String())
	}
	// Gone from the live list, GET now 404.
	if gw2 := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds/"+kind.UserKindID, owner, ""); gw2.Code != http.StatusNotFound {
		t.Fatalf("get after delete: want 404, got %d", gw2.Code)
	}
	// Appears in trash.
	tw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds-trash", owner, "")
	if tw.Code != http.StatusOK {
		t.Fatalf("trash list: want 200, got %d (%s)", tw.Code, tw.Body.String())
	}
	var trash struct {
		Items []userKindTrashItem `json:"items"`
	}
	json.Unmarshal(tw.Body.Bytes(), &trash)
	foundInTrash := false
	for _, it := range trash.Items {
		if it.UserKindID == kind.UserKindID {
			foundInTrash = true
		}
	}
	if !foundInTrash {
		t.Fatalf("deleted kind not in trash")
	}

	// Restore → live again.
	rw := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds-trash/"+kind.UserKindID+"/restore", owner, "")
	if rw.Code != http.StatusNoContent {
		t.Fatalf("restore: want 204, got %d (%s)", rw.Code, rw.Body.String())
	}
	if gw3 := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds/"+kind.UserKindID, owner, ""); gw3.Code != http.StatusOK {
		t.Fatalf("get after restore: want 200, got %d", gw3.Code)
	}

	// Delete + purge → permanently gone (restore now 404).
	ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-kinds/"+kind.UserKindID, owner, "")
	purgeW := ukReq(t, srv, http.MethodDelete, "/v1/glossary/user-kinds-trash/"+kind.UserKindID, owner, "")
	if purgeW.Code != http.StatusNoContent {
		t.Fatalf("purge: want 204, got %d (%s)", purgeW.Code, purgeW.Body.String())
	}
	if rw2 := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds-trash/"+kind.UserKindID+"/restore", owner, ""); rw2.Code != http.StatusNotFound {
		t.Fatalf("restore after purge: want 404, got %d", rw2.Code)
	}
}

// TestUserKind_TenantIsolation is the mandated cross-tenant deny test: user B
// must NOT see, read, or mutate user A's kind, and B's list must exclude it.
func TestUserKind_TenantIsolation(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runUserKindMigrations(t, pool)
	alice := uuid.NewString()
	bob := uuid.NewString()

	kind := mustCreateUserKind(t, srv, alice, `{"name":"Alice Secret Kind"}`)
	attr := func() userKindAttrResp {
		w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds/"+kind.UserKindID+"/attributes", alice,
			`{"name":"secret"}`)
		var a userKindAttrResp
		json.Unmarshal(w.Body.Bytes(), &a)
		return a
	}()

	base := "/v1/glossary/user-kinds/" + kind.UserKindID
	// Every cross-tenant access by Bob must be 404 (not 200, not a 403 that leaks existence).
	denies := []struct {
		name, method, url, body string
	}{
		{"get", http.MethodGet, base, ""},
		{"patch", http.MethodPatch, base, `{"name":"hijack"}`},
		{"delete", http.MethodDelete, base, ""},
		{"add-attr", http.MethodPost, base + "/attributes", `{"name":"x"}`},
		{"patch-attr", http.MethodPatch, base + "/attributes/" + attr.AttrID, `{"name":"x"}`},
		{"delete-attr", http.MethodDelete, base + "/attributes/" + attr.AttrID, ""},
	}
	for _, d := range denies {
		w := ukReq(t, srv, d.method, d.url, bob, d.body)
		if w.Code != http.StatusNotFound {
			t.Errorf("bob %s: want 404, got %d (%s)", d.name, w.Code, w.Body.String())
		}
	}

	// Bob's list must not include Alice's kind.
	lw := ukReq(t, srv, http.MethodGet, "/v1/glossary/user-kinds", bob, "")
	if lw.Code != http.StatusOK {
		t.Fatalf("bob list: want 200, got %d (%s)", lw.Code, lw.Body.String())
	}
	var list userKindListResp
	json.Unmarshal(lw.Body.Bytes(), &list)
	for _, it := range list.Items {
		if it.UserKindID == kind.UserKindID {
			t.Fatalf("TENANT LEAK: bob's list contains alice's kind %s", kind.UserKindID)
		}
	}

	// Alice's kind is untouched after Bob's attempts (still readable, name intact).
	gw := ukReq(t, srv, http.MethodGet, base, alice, "")
	var still userKindDetailResp
	json.Unmarshal(gw.Body.Bytes(), &still)
	if gw.Code != http.StatusOK || still.Name != "Alice Secret Kind" {
		t.Fatalf("alice's kind altered by bob: code=%d name=%q", gw.Code, still.Name)
	}
}

// TestUserKind_CloneFromSystem proves cloning a T1 system kind copies its
// attribute definitions into the new user kind.
func TestUserKind_CloneFromSystem(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runUserKindMigrations(t, pool)
	owner := uuid.NewString()

	charKindID := kindIDByCode(t, pool, "character") // 13 seeded attrs
	kind := mustCreateUserKind(t, srv, owner,
		`{"name":"My Character","clone_from_kind_id":"`+charKindID+`"}`)

	if kind.ClonedFromKindID == nil || *kind.ClonedFromKindID != charKindID {
		t.Fatalf("cloned_from not recorded: %v", kind.ClonedFromKindID)
	}
	if len(kind.Attributes) == 0 {
		t.Fatalf("clone copied no attributes")
	}
	// The character kind's required 'name' attr must have come across.
	hasName := false
	for _, a := range kind.Attributes {
		if a.Code == "name" {
			hasName = true
		}
	}
	if !hasName {
		t.Fatalf("clone missing the 'name' attribute from the T1 character kind")
	}
}

// TestUserKind_DuplicateCode409 proves the per-user UNIQUE(owner_user_id, code)
// surfaces as a clean 409, while a DIFFERENT user may reuse the same code.
func TestUserKind_DuplicateCode409(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runUserKindMigrations(t, pool)
	alice := uuid.NewString()
	bob := uuid.NewString()

	mustCreateUserKind(t, srv, alice, `{"code":"dup_kind","name":"Dup"}`)

	// Same code, same owner → 409.
	w := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds", alice, `{"code":"dup_kind","name":"Dup2"}`)
	if w.Code != http.StatusConflict {
		t.Fatalf("duplicate code same owner: want 409, got %d (%s)", w.Code, w.Body.String())
	}

	// Same code, DIFFERENT owner → allowed (scope key is owner_user_id, not global).
	w2 := ukReq(t, srv, http.MethodPost, "/v1/glossary/user-kinds", bob, `{"code":"dup_kind","name":"Bob Dup"}`)
	if w2.Code != http.StatusCreated {
		t.Fatalf("same code different owner: want 201, got %d (%s)", w2.Code, w2.Body.String())
	}
}
