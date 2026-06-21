package api

// G-U2 — per-attribute auto_fill_prompt / translation_hint authoring on the System tier.
// Proves: create persists both fields and the read returns them; a patch of ONLY
// translation_hint preserves auto_fill_prompt (read-modify-write, not a blind overwrite);
// and afp/th are NOT folded into content_hash (an afp/th-only edit leaves the hash
// unchanged → Sync does not fire — the documented Option-B v1 behaviour). Requires
// GLOSSARY_TEST_DB_URL.

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

func TestSystemAttrAIAssist_CreatePatchRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	runMigrations(t, pool)
	ctx := context.Background()
	srv, mint := newAdminTestServer(t, pool)
	admin := mint([]string{"admin:read", "admin:write"})
	user := userHS256(t) // system-attributes READ is user-bearer gated
	base := "/v1/glossary"

	gcode := "u2g_" + uuid.NewString()[:8]
	kcode := "u2k_" + uuid.NewString()[:8]
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM system_kinds  WHERE code=$1`, kcode) //nolint:errcheck
		pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, gcode) //nolint:errcheck
	})

	gw := adminReq(t, srv, http.MethodPost, base+"/system-genres", admin, `{"name":"U2G","code":"`+gcode+`"}`)
	var g struct {
		GenreID string `json:"genre_id"`
	}
	_ = json.Unmarshal(gw.Body.Bytes(), &g)
	kw := adminReq(t, srv, http.MethodPost, base+"/system-kinds", admin, `{"name":"U2K","code":"`+kcode+`"}`)
	var k struct {
		KindID string `json:"kind_id"`
	}
	_ = json.Unmarshal(kw.Body.Bytes(), &k)

	// create with BOTH AI-assistance fields
	aw := adminReq(t, srv, http.MethodPost, base+"/system-attributes-admin", admin,
		`{"kind_id":"`+k.KindID+`","genre_id":"`+g.GenreID+`","name":"Power","code":"power","field_type":"text",`+
			`"auto_fill_prompt":"Fill from the text","translation_hint":"Keep romanized"}`)
	if aw.Code != http.StatusCreated {
		t.Fatalf("create attr: want 201, got %d (%s)", aw.Code, aw.Body.String())
	}
	var created struct {
		AttrID          string  `json:"attr_id"`
		AutoFillPrompt  *string `json:"auto_fill_prompt"`
		TranslationHint *string `json:"translation_hint"`
	}
	_ = json.Unmarshal(aw.Body.Bytes(), &created)
	if created.AutoFillPrompt == nil || *created.AutoFillPrompt != "Fill from the text" ||
		created.TranslationHint == nil || *created.TranslationHint != "Keep romanized" {
		t.Fatalf("create did not persist afp/th: %s", aw.Body.String())
	}

	// content_hash must NOT include afp/th (Option B)
	var hash, wantHash string
	pool.QueryRow(ctx,
		`SELECT content_hash, md5('power'||'|'||'Power') FROM system_attributes WHERE attr_id=$1`, created.AttrID).Scan(&hash, &wantHash) //nolint:errcheck

	// patch translation_hint ONLY → auto_fill_prompt must survive
	pw := adminReq(t, srv, http.MethodPatch, base+"/system-attributes-admin/"+created.AttrID, admin,
		`{"translation_hint":"Translate literally"}`)
	if pw.Code != http.StatusOK {
		t.Fatalf("patch attr: want 200, got %d (%s)", pw.Code, pw.Body.String())
	}

	// read back via the user-gated list and assert the merged state
	rw := adminReq(t, srv, http.MethodGet,
		base+"/system-attributes?kind_id="+k.KindID+"&genre_id="+g.GenreID, user, "")
	if rw.Code != http.StatusOK {
		t.Fatalf("list attrs: want 200, got %d (%s)", rw.Code, rw.Body.String())
	}
	var list struct {
		Items []struct {
			Code            string  `json:"code"`
			AutoFillPrompt  *string `json:"auto_fill_prompt"`
			TranslationHint *string `json:"translation_hint"`
		} `json:"items"`
	}
	_ = json.Unmarshal(rw.Body.Bytes(), &list)
	var found bool
	for _, it := range list.Items {
		if it.Code != "power" {
			continue
		}
		found = true
		if it.AutoFillPrompt == nil || *it.AutoFillPrompt != "Fill from the text" {
			t.Errorf("patch of translation_hint clobbered auto_fill_prompt: %+v", it.AutoFillPrompt)
		}
		if it.TranslationHint == nil || *it.TranslationHint != "Translate literally" {
			t.Errorf("translation_hint not updated: %+v", it.TranslationHint)
		}
	}
	if !found {
		t.Fatalf("attr 'power' not returned by the read: %s", rw.Body.String())
	}

	// the afp/th-only edits left content_hash unchanged (Sync wouldn't fire)
	var afterHash string
	pool.QueryRow(ctx, `SELECT content_hash FROM system_attributes WHERE attr_id=$1`, created.AttrID).Scan(&afterHash) //nolint:errcheck
	if afterHash != hash {
		t.Errorf("content_hash changed on an afp/th-only edit (should be stable, Option B): %q → %q", hash, afterHash)
	}
}
