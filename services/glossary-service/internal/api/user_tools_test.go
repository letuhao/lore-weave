package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

// T3 — user-tier standards MCP tools. Requires GLOSSARY_TEST_DB_URL.
// Proves: owner-scoped create/patch/delete/restore round-trips across all three
// levels; a non-owner cannot see or mutate another user's library (the tenancy
// chokepoint — owner-only lifecycle tests hide cross-tenant leaks,
// [[e0-grant-mapping-test-pattern]]); patch carries a base_version and 409s on drift;
// restore brings a trashed row back.

func TestUserTool_CreatePatchDeleteRestoreRoundTrip(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	owner := uuid.New()
	octx := ctxWithUser(owner)

	// create genre + kind
	_, g, err := srv.toolUserCreate(octx, nil, userCreateToolIn{Level: "genre", Name: "My Cultivation", Code: "ut_genre"})
	if err != nil || g.Code != "ut_genre" || g.BaseVersion == "" {
		t.Fatalf("create genre: %v %+v", err, g)
	}
	_, k, err := srv.toolUserCreate(octx, nil, userCreateToolIn{Level: "kind", Name: "My Sect", Code: "ut_kind"})
	if err != nil || k.Code != "ut_kind" || k.BaseVersion == "" {
		t.Fatalf("create kind: %v %+v", err, k)
	}
	// attribute attaches to the caller's own kind×genre
	_, a, err := srv.toolUserCreate(octx, nil, userCreateToolIn{
		Level: "attribute", Name: "Realm", Code: "ut_attr", KindCode: "ut_kind", GenreCode: "ut_genre", FieldType: "text",
	})
	if err != nil || a.Code != "ut_attr" {
		t.Fatalf("create attr: %v %+v", err, a)
	}

	// read back the library (+ the cell's attributes)
	_, lib, err := srv.toolUserStandardsRead(octx, nil, userStandardsReadToolIn{KindCode: "ut_kind", GenreCode: "ut_genre"})
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if !hasGenreCode(lib.Genres, "ut_genre") || !hasUserKindCode(lib.Kinds, "ut_kind") || len(lib.Attributes) != 1 {
		t.Fatalf("library read wrong: genres=%d kinds=%d attrs=%d", len(lib.Genres), len(lib.Kinds), len(lib.Attributes))
	}
	// the read must surface base_version on every level so a patch can use the 409 guard
	if lib.Attributes[0].BaseVersion == "" {
		t.Error("attribute read missing base_version")
	}
	for _, gr := range lib.Genres {
		if gr.Code == "ut_genre" && gr.BaseVersion == "" {
			t.Error("genre read missing base_version")
		}
	}

	// patch the genre with the correct base_version → success; hash rotates
	nm := "My Cultivation v2"
	_, pg, err := srv.toolUserPatch(octx, nil, userPatchToolIn{Level: "genre", Code: "ut_genre", BaseVersion: g.BaseVersion, Name: &nm})
	if err != nil || pg.Status != "patched" || pg.BaseVersion == g.BaseVersion {
		t.Fatalf("patch genre: %v %+v (hash should rotate)", err, pg)
	}
	// stale base_version now 409s
	if _, _, err := srv.toolUserPatch(octx, nil, userPatchToolIn{Level: "genre", Code: "ut_genre", BaseVersion: g.BaseVersion, Name: &nm}); err == nil {
		t.Error("stale base_version must 409")
	}

	// patch the attribute (exercises applyUserUpdate on user_attributes — which has NO
	// updated_at column, so touchUpdatedAt must be false or this errors at runtime).
	anm := "Realm v2"
	bad := "select"
	_, pa, err := srv.toolUserPatch(octx, nil, userPatchToolIn{
		Level: "attribute", Code: "ut_attr", KindCode: "ut_kind", GenreCode: "ut_genre",
		BaseVersion: a.BaseVersion, Name: &anm, FieldType: &bad, Options: &[]string{"x", "y"},
	})
	if err != nil || pa.Status != "patched" || pa.BaseVersion == a.BaseVersion {
		t.Fatalf("patch attr: %v %+v (hash should rotate)", err, pa)
	}
	var gotName, gotFt string
	pool.QueryRow(context.Background(), `SELECT name, field_type FROM user_attributes WHERE attr_id=$1`, pa.ID).Scan(&gotName, &gotFt)
	if gotName != anm || gotFt != "select" {
		t.Errorf("attr patch did not apply: name=%q field_type=%q", gotName, gotFt)
	}
	// invalid field_type on attribute patch is rejected
	garbage := "dropdown"
	if _, _, err := srv.toolUserPatch(octx, nil, userPatchToolIn{
		Level: "attribute", Code: "ut_attr", KindCode: "ut_kind", GenreCode: "ut_genre", FieldType: &garbage,
	}); err == nil {
		t.Error("invalid field_type on attr patch must be rejected")
	}

	// delete (trash) the attribute, then restore it
	if _, d, err := srv.toolUserDelete(octx, nil, userDeleteToolIn{Level: "attribute", Code: "ut_attr", KindCode: "ut_kind", GenreCode: "ut_genre"}); err != nil || d.Status != "trashed" {
		t.Fatalf("trash attr: %v %+v", err, d)
	}
	// gone from the live read
	if _, lib2, _ := srv.toolUserStandardsRead(octx, nil, userStandardsReadToolIn{KindCode: "ut_kind", GenreCode: "ut_genre"}); len(lib2.Attributes) != 0 {
		t.Errorf("trashed attr still live: %d", len(lib2.Attributes))
	}
	if _, rr, err := srv.toolUserRestore(octx, nil, userDeleteToolIn{Level: "attribute", Code: "ut_attr", KindCode: "ut_kind", GenreCode: "ut_genre"}); err != nil || rr.Status != "restored" {
		t.Fatalf("restore attr: %v %+v", err, rr)
	}
	if _, lib3, _ := srv.toolUserStandardsRead(octx, nil, userStandardsReadToolIn{KindCode: "ut_kind", GenreCode: "ut_genre"}); len(lib3.Attributes) != 1 {
		t.Errorf("restore did not bring the attr back: %d", len(lib3.Attributes))
	}

	// genre in use can't be trashed (attribute references it)
	if _, _, err := srv.toolUserDelete(octx, nil, userDeleteToolIn{Level: "genre", Code: "ut_genre"}); err == nil {
		t.Error("genre referenced by an attribute must not be trashable")
	}
}

// Tenancy: user B cannot see or mutate user A's user-tier library.
func TestUserTool_TenantIsolation(t *testing.T) {
	pool := openTestDB(t)
	srv := newExportServer(t, pool)
	runGenreMigrations(t, pool)
	a, b := uuid.New(), uuid.New()
	actx, bctx := ctxWithUser(a), ctxWithUser(b)

	if _, _, err := srv.toolUserCreate(actx, nil, userCreateToolIn{Level: "genre", Name: "A Secret", Code: "ut_iso"}); err != nil {
		t.Fatalf("A create: %v", err)
	}
	// B's library does not contain A's genre
	if _, lib, _ := srv.toolUserStandardsRead(bctx, nil, userStandardsReadToolIn{}); hasGenreCode(lib.Genres, "ut_iso") {
		t.Error("B must not see A's genre")
	}
	// B cannot patch A's genre (resolves only within B's tier → not found)
	nm := "hijacked"
	if _, _, err := srv.toolUserPatch(bctx, nil, userPatchToolIn{Level: "genre", Code: "ut_iso", Name: &nm}); err == nil {
		t.Error("B must not patch A's genre")
	}
	// B cannot trash A's genre
	if _, _, err := srv.toolUserDelete(bctx, nil, userDeleteToolIn{Level: "genre", Code: "ut_iso"}); err == nil {
		t.Error("B must not delete A's genre")
	}
	// A's genre is untouched and still live
	if _, lib, _ := srv.toolUserStandardsRead(actx, nil, userStandardsReadToolIn{}); !hasGenreCode(lib.Genres, "ut_iso") {
		t.Error("A's genre must survive B's attempts")
	}
}

// Missing caller identity is rejected before any query (defense in depth).
func TestUserTool_MissingIdentity(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolUserStandardsRead(context.Background(), nil, userStandardsReadToolIn{}); err == nil {
		t.Error("missing identity must be rejected")
	}
	if _, _, err := s.toolUserCreate(context.Background(), nil, userCreateToolIn{Level: "genre", Name: "X"}); err == nil {
		t.Error("missing identity must be rejected on create")
	}
}

func hasGenreCode(gs []userGenreRow, code string) bool {
	for _, g := range gs {
		if g.Code == code {
			return true
		}
	}
	return false
}

func hasUserKindCode(ks []userKindBrief, code string) bool {
	for _, k := range ks {
		if k.Code == code {
			return true
		}
	}
	return false
}
