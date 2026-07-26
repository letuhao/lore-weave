package api

// S-07 §1 — world_map OCC on the MCP update + the image-upload/rename decoupling.
// DB-gated (real Postgres) like the other *_db_test.go: the whole point is the
// version columns behaving under real UPDATEs, which a mock cannot prove. Gated on
// BOOK_TEST_DATABASE_URL.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// seedS07Map creates a world + a map for `owner` and returns the map id (string) and
// its live version (a fresh map is version 1).
func seedS07Map(t *testing.T, s *Server, ctx context.Context) (string, int) {
	t.Helper()
	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "S07World"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	_, mout, err := s.toolWorldMapCreate(ctx, nil, worldMapCreateIn{WorldID: wout.World.WorldID, Name: "Atlas"})
	if err != nil {
		t.Fatalf("map_create: %v", err)
	}
	if mout.Map.Version != 1 {
		t.Fatalf("fresh map must be version 1, got %d", mout.Map.Version)
	}
	return mout.Map.MapID, mout.Map.Version
}

// TestWorldMapUpdate_OCC — the MCP world_map_update now honours expected_version like
// the REST PATCH's If-Match: a stale version is a conflict (not a blind clobber, not a 404),
// a matching version succeeds, and omitting it is last-write-wins.
func TestWorldMapUpdate_OCC(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)
	mapID, v := seedS07Map(t, s, ctx) // v == 1

	// (a) matching expected_version → succeeds, bumps to 2.
	name1 := "Atlas II"
	_, u1, err := s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: mapID, Name: &name1, ExpectedVersion: &v})
	if err != nil {
		t.Fatalf("update with matching version must succeed: %v", err)
	}
	if u1.Map.Version != 2 || u1.Map.Name != "Atlas II" {
		t.Fatalf("expected name=Atlas II version=2, got name=%q version=%d", u1.Map.Name, u1.Map.Version)
	}

	// (b) a STALE expected_version (still 1, but the map is now 2) → conflict, NOT a 404 and
	// NOT a silent clobber. The error names the current version so the agent re-reads + retries.
	stale := 1
	name2 := "Should Not Land"
	_, _, err = s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: mapID, Name: &name2, ExpectedVersion: &stale})
	if err == nil {
		t.Fatal("stale expected_version must conflict, got nil error")
	}
	if !strings.Contains(err.Error(), "changed elsewhere") || !strings.Contains(err.Error(), "current is 2") {
		t.Fatalf("conflict error must name the current version, got: %v", err)
	}
	// the clobber must NOT have landed — the name is still Atlas II.
	_, g, _ := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if g.Map.Name != "Atlas II" || g.Map.Version != 2 {
		t.Fatalf("a conflicting update must not mutate the map, got name=%q version=%d", g.Map.Name, g.Map.Version)
	}

	// (c) the correct current version → succeeds, bumps to 3.
	cur := 2
	name3 := "Atlas III"
	_, u3, err := s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: mapID, Name: &name3, ExpectedVersion: &cur})
	if err != nil {
		t.Fatalf("update with the current version must succeed: %v", err)
	}
	if u3.Map.Version != 3 {
		t.Fatalf("expected version=3, got %d", u3.Map.Version)
	}

	// (d) NO expected_version → last-write-wins (unchanged legacy behaviour), bumps to 4.
	name4 := "Atlas IV"
	_, u4, err := s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: mapID, Name: &name4})
	if err != nil {
		t.Fatalf("update without a version (LWW) must succeed: %v", err)
	}
	if u4.Map.Version != 4 {
		t.Fatalf("expected version=4, got %d", u4.Map.Version)
	}

	// (e) cross-user with a version still 404s (no existence oracle, tenancy before OCC).
	ctxB := identityCtxForTest(t, uuid.New())
	four := 4
	_, _, err = s.toolWorldMapUpdate(ctxB, nil, mapUpdateIn{MapID: mapID, Name: &name4, ExpectedVersion: &four})
	if err == nil || !strings.Contains(err.Error(), "not found") {
		t.Fatalf("user B must get 'map not found', got: %v", err)
	}
}

// TestMapImageUpload_DecouplesFromRename — the crux of §1: recording an image bumps
// image_version ONLY (never the metadata version), so an image upload cannot invalidate a
// concurrent rename's OCC, and it does not clobber the name.
func TestMapImageUpload_DecouplesFromRename(t *testing.T) {
	s, pool := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)
	mapIDStr, _ := seedS07Map(t, s, ctx)
	mapID := uuid.MustParse(mapIDStr)

	readVersions := func() (int, int) {
		var v, iv int
		if err := pool.QueryRow(ctx,
			`SELECT version, image_version FROM world_maps WHERE id=$1`, mapID).Scan(&v, &iv); err != nil {
			t.Fatalf("read versions: %v", err)
		}
		return v, iv
	}

	v0, iv0 := readVersions()
	if v0 != 1 || iv0 != 1 {
		t.Fatalf("fresh map must be version=1 image_version=1, got version=%d image_version=%d", v0, iv0)
	}

	// Record an image the way the upload handler does (the extracted SQL — same code path).
	w, h := 1024, 768
	imageVersion, err := s.recordMapImage(ctx, mapID, owner, "worlds/maps/x/base.png", &w, &h)
	if err != nil {
		t.Fatalf("recordMapImage: %v", err)
	}
	if imageVersion != 2 {
		t.Fatalf("image upload must bump image_version to 2, got %d", imageVersion)
	}

	// The metadata version is UNTOUCHED — an image upload is not a rename.
	v1, iv1 := readVersions()
	if v1 != 1 {
		t.Fatalf("image upload must NOT bump the metadata version, got version=%d", v1)
	}
	if iv1 != 2 {
		t.Fatalf("image upload must bump image_version to 2, got %d", iv1)
	}

	// Therefore a rename that read version=1 BEFORE the image upload still succeeds — the two
	// concerns never collide (the whole point of §1). Before the fix this would have 412'd.
	name := "Renamed After Image"
	one := 1
	_, u, err := s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: mapIDStr, Name: &name, ExpectedVersion: &one})
	if err != nil {
		t.Fatalf("a rename must not race the image upload, got conflict: %v", err)
	}
	if u.Map.Name != "Renamed After Image" || u.Map.Version != 2 {
		t.Fatalf("rename must land: got name=%q version=%d", u.Map.Name, u.Map.Version)
	}
}
