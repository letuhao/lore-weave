package api

// G-C8 — System-tier soft-delete + restore + recycle bin. Proves: a delete DEPRECATES
// (not hard-deletes) and the row leaves live reads but appears in /system-trash; restore
// brings it back; deleting a kind cascade-deprecates its attributes; restoring an
// attribute under a still-deprecated parent is blocked (422); restoring a kind does NOT
// auto-restore its attributes; the recycle-bin + restore HTTP surface is admin:write-gated
// (user/no-token → 401, read-only scope → 403); and the MCP glossary_admin_propose_restore
// tool round-trips through the RS256 confirm path (single-use) and refuses a live row at
// mint time. Requires GLOSSARY_TEST_DB_URL.

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// TestSystemSoftDelete_HTTPCycleAndReadFilter: create → soft-delete → gone from the live
// admin standards read + present in /system-trash → restore → back, and a second restore
// of the now-live row is 404 (not in bin).
func TestSystemSoftDelete_HTTPCycleAndReadFilter(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)
	srv := f.srv
	ctx := context.Background()
	admin := f.mint(uuid.NewString())
	base := "/v1/glossary"

	gcode := "sd_genre_" + uuid.NewString()[:8]
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gcode) }) //nolint:errcheck

	cw := adminReq(t, srv, http.MethodPost, base+"/system-genres", admin, `{"name":"SoftDel","code":"`+gcode+`"}`)
	if cw.Code != http.StatusCreated {
		t.Fatalf("create genre: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var created struct {
		GenreID string `json:"genre_id"`
	}
	_ = json.Unmarshal(cw.Body.Bytes(), &created)

	// delete → soft (row remains, deprecated)
	if dw := adminReq(t, srv, http.MethodDelete, base+"/system-genres/"+created.GenreID, admin, ""); dw.Code != http.StatusNoContent {
		t.Fatalf("delete genre: want 204, got %d (%s)", dw.Code, dw.Body.String())
	}
	var deprecated bool
	pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_genres WHERE code=$1`, gcode).Scan(&deprecated) //nolint:errcheck
	if !deprecated {
		t.Fatal("delete must SOFT-delete (deprecated_at set) — row was hard-deleted or untouched")
	}

	// live admin standards read excludes the deprecated genre (the sweep)
	readBody := `{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"glossary_admin_standards_read","arguments":{}}}`
	rw := f.adminMCP(t, readBody, adminMCPInternalToken, admin)
	if rw.Code != http.StatusOK {
		t.Fatalf("standards read: want 200, got %d", rw.Code)
	}
	if strings.Contains(rw.Body.String(), gcode) {
		t.Errorf("deprecated genre %q leaked into the live admin standards read", gcode)
	}

	// recycle bin lists it
	tw := adminReq(t, srv, http.MethodGet, base+"/system-trash", admin, "")
	if tw.Code != http.StatusOK || !strings.Contains(tw.Body.String(), gcode) {
		t.Fatalf("system-trash should list the deprecated genre: %d (%s)", tw.Code, tw.Body.String())
	}

	// restore → back, deprecated_at cleared
	if rsw := adminReq(t, srv, http.MethodPost, base+"/system-genres/"+created.GenreID+"/restore", admin, ""); rsw.Code != http.StatusOK {
		t.Fatalf("restore genre: want 200, got %d (%s)", rsw.Code, rsw.Body.String())
	}
	pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_genres WHERE code=$1`, gcode).Scan(&deprecated) //nolint:errcheck
	if deprecated {
		t.Fatal("restore must clear deprecated_at")
	}
	// restoring a live row → 404 (not in the bin)
	if rsw := adminReq(t, srv, http.MethodPost, base+"/system-genres/"+created.GenreID+"/restore", admin, ""); rsw.Code != http.StatusNotFound {
		t.Errorf("restore of a live row: want 404 not-in-bin, got %d", rsw.Code)
	}
}

// TestSystemSoftDelete_CascadeAndParentGuard: deleting a kind cascade-deprecates its
// attributes; an attribute cannot be restored while its parent is deprecated (422);
// restoring the kind does NOT auto-restore the attribute; then the attribute restores.
func TestSystemSoftDelete_CascadeAndParentGuard(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)
	srv := f.srv
	ctx := context.Background()
	admin := f.mint(uuid.NewString())
	base := "/v1/glossary"

	gcode := "sd_cg_" + uuid.NewString()[:8]
	kcode := "sd_ck_" + uuid.NewString()[:8]
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM system_kinds WHERE code=$1`, kcode)   //nolint:errcheck
		pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gcode)  //nolint:errcheck
	})

	gw := adminReq(t, srv, http.MethodPost, base+"/system-genres", admin, `{"name":"CG","code":"`+gcode+`"}`)
	var g struct {
		GenreID string `json:"genre_id"`
	}
	_ = json.Unmarshal(gw.Body.Bytes(), &g)
	kw := adminReq(t, srv, http.MethodPost, base+"/system-kinds", admin, `{"name":"CK","code":"`+kcode+`"}`)
	var k struct {
		KindID string `json:"kind_id"`
	}
	_ = json.Unmarshal(kw.Body.Bytes(), &k)
	aw := adminReq(t, srv, http.MethodPost, base+"/system-attributes-admin", admin,
		`{"kind_id":"`+k.KindID+`","genre_id":"`+g.GenreID+`","name":"Power","code":"power","field_type":"text"}`)
	if aw.Code != http.StatusCreated {
		t.Fatalf("create attr: want 201, got %d (%s)", aw.Code, aw.Body.String())
	}
	var a struct {
		AttrID string `json:"attr_id"`
	}
	_ = json.Unmarshal(aw.Body.Bytes(), &a)

	// delete the kind → attr cascade-deprecated in the same tx
	if dw := adminReq(t, srv, http.MethodDelete, base+"/system-kinds/"+k.KindID, admin, ""); dw.Code != http.StatusNoContent {
		t.Fatalf("delete kind: want 204, got %d", dw.Code)
	}
	var kindDep, attrDep bool
	pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_kinds WHERE kind_id=$1`, k.KindID).Scan(&kindDep)       //nolint:errcheck
	pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_attributes WHERE attr_id=$1`, a.AttrID).Scan(&attrDep) //nolint:errcheck
	if !kindDep || !attrDep {
		t.Fatalf("kind delete must cascade-deprecate attributes: kind=%v attr=%v", kindDep, attrDep)
	}

	// /review-impl M1: a NEW attribute cannot be created under the soft-deleted kind
	// (would be an invisible orphan that resurfaces on restore) → 422.
	if cw := adminReq(t, srv, http.MethodPost, base+"/system-attributes-admin", admin,
		`{"kind_id":"`+k.KindID+`","genre_id":"`+g.GenreID+`","name":"Orphan","code":"orphan","field_type":"text"}`); cw.Code != http.StatusUnprocessableEntity {
		t.Errorf("create attr under deprecated kind: want 422, got %d (%s)", cw.Code, cw.Body.String())
	}

	// restore the attribute while its parent kind is still deprecated → 422
	if rw := adminReq(t, srv, http.MethodPost, base+"/system-attributes-admin/"+a.AttrID+"/restore", admin, ""); rw.Code != http.StatusUnprocessableEntity {
		t.Fatalf("restore attr under deprecated parent: want 422, got %d (%s)", rw.Code, rw.Body.String())
	}
	// restore the kind — must NOT auto-restore the attribute (option b)
	if rw := adminReq(t, srv, http.MethodPost, base+"/system-kinds/"+k.KindID+"/restore", admin, ""); rw.Code != http.StatusOK {
		t.Fatalf("restore kind: want 200, got %d (%s)", rw.Code, rw.Body.String())
	}
	pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_attributes WHERE attr_id=$1`, a.AttrID).Scan(&attrDep) //nolint:errcheck
	if !attrDep {
		t.Error("restoring a kind must NOT auto-restore its attributes (cascade-restore is per-row, option b)")
	}
	// now the attribute restores (parent live)
	if rw := adminReq(t, srv, http.MethodPost, base+"/system-attributes-admin/"+a.AttrID+"/restore", admin, ""); rw.Code != http.StatusOK {
		t.Fatalf("restore attr after parent live: want 200, got %d (%s)", rw.Code, rw.Body.String())
	}
}

// TestSystemSoftDelete_RestoreAuthz: the recycle-bin + restore surface is admin:write-only.
func TestSystemSoftDelete_RestoreAuthz(t *testing.T) {
	pool := openTestDB(t)
	runMigrations(t, pool)
	srv, mint := newAdminTestServer(t, pool)
	base := "/v1/glossary"
	admin := mint([]string{"admin:read", "admin:write"})

	gcode := "sd_authz_" + uuid.NewString()[:8]
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gcode) }) //nolint:errcheck
	cw := adminReq(t, srv, http.MethodPost, base+"/system-genres", admin, `{"name":"AZ","code":"`+gcode+`"}`)
	var g struct {
		GenreID string `json:"genre_id"`
	}
	_ = json.Unmarshal(cw.Body.Bytes(), &g)
	adminReq(t, srv, http.MethodDelete, base+"/system-genres/"+g.GenreID, admin, "")

	restoreURL := base + "/system-genres/" + g.GenreID + "/restore"
	cases := []struct {
		name, method, url, token string
		want                     int
	}{
		{"restore user-token", http.MethodPost, restoreURL, userHS256(t), http.StatusUnauthorized},
		{"restore no-token", http.MethodPost, restoreURL, "", http.StatusUnauthorized},
		{"restore read-only", http.MethodPost, restoreURL, mint([]string{"admin:read"}), http.StatusForbidden},
		{"trash user-token", http.MethodGet, base + "/system-trash", userHS256(t), http.StatusUnauthorized},
		{"trash read-only", http.MethodGet, base + "/system-trash", mint([]string{"admin:read"}), http.StatusForbidden},
	}
	for _, c := range cases {
		if w := adminReq(t, srv, c.method, c.url, c.token, ""); w.Code != c.want {
			t.Errorf("%s: want %d, got %d", c.name, c.want, w.Code)
		}
	}
}

// TestAdminMCP_ProposeRestoreRoundTrip: propose restore via /mcp/admin → confirm → row
// live; replay is single-use 422; and proposing a restore of a LIVE row fails at mint.
func TestAdminMCP_ProposeRestoreRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)
	srv := f.srv
	ctx := context.Background()
	admin := f.mint(uuid.NewString())
	base := "/v1/glossary"

	gcode := "sd_mcp_" + uuid.NewString()[:8]
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gcode) }) //nolint:errcheck

	cw := adminReq(t, srv, http.MethodPost, base+"/system-genres", admin, `{"name":"MCP","code":"`+gcode+`"}`)
	var g struct {
		GenreID string `json:"genre_id"`
	}
	_ = json.Unmarshal(cw.Body.Bytes(), &g)
	adminReq(t, srv, http.MethodDelete, base+"/system-genres/"+g.GenreID, admin, "")

	// propose restore (mints an authorityAdmin token, no write)
	call := `{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"glossary_admin_propose_restore",` +
		`"arguments":{"level":"genre","code":"` + gcode + `"}}}`
	w := f.adminMCP(t, call, adminMCPInternalToken, admin)
	if w.Code != http.StatusOK {
		t.Fatalf("propose restore: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	confirmTok := callToolConfirmToken(t, w.Body.String())

	// confirm → 200 + restored
	if cw := f.adminConfirm(t, "/v1/glossary/actions/admin/confirm", confirmTok, admin); cw.Code != http.StatusOK {
		t.Fatalf("confirm restore: want 200, got %d (%s)", cw.Code, cw.Body.String())
	}
	var deprecated bool
	pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_genres WHERE code=$1`, gcode).Scan(&deprecated) //nolint:errcheck
	if deprecated {
		t.Error("confirm restore should clear deprecated_at")
	}
	// replay → single-use 422
	if cw := f.adminConfirm(t, "/v1/glossary/actions/admin/confirm", confirmTok, admin); cw.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay restore: want 422 single-use, got %d", cw.Code)
	}

	// proposing a restore of the now-LIVE row fails at mint (not in the recycle bin)
	w2 := f.adminMCP(t, call, adminMCPInternalToken, admin)
	var resp struct {
		Result struct {
			IsError           bool `json:"isError"`
			StructuredContent struct {
				ConfirmToken string `json:"confirm_token"`
			} `json:"structuredContent"`
		} `json:"result"`
	}
	_ = json.Unmarshal(w2.Body.Bytes(), &resp)
	if !resp.Result.IsError && resp.Result.StructuredContent.ConfirmToken != "" {
		t.Error("propose_restore of a live row should fail (not in the recycle bin)")
	}
}
