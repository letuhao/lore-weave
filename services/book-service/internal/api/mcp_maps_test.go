package api

// W10-M2 world-map MCP tools. Validation/coord guards run always; the create →
// marker → region → get round-trip + owner-scoping require BOOK_TEST_DATABASE_URL.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// ── validation (no DB — checks short-circuit before any pool access) ─────────

func TestWorldMapCreate_RequiresName(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapCreate(ctx, nil, worldMapCreateIn{WorldID: uuid.New().String(), Name: "  "}); err == nil {
		t.Fatal("expected an error for an empty map name")
	}
}

func TestWorldMapAddMarker_RejectsOutOfRangeCoords(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	// x > 1 must be rejected BEFORE any DB access (relative-coord invariant).
	if _, _, err := s.toolWorldMapAddMarker(ctx, nil, mapAddMarkerIn{
		MapID: uuid.New().String(), Label: "X", X: 1.5, Y: 0.5,
	}); err == nil {
		t.Fatal("expected an error for x outside [0,1]")
	}
}

func TestWorldMapAddRegion_RejectsTooFewPoints(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapAddRegion(ctx, nil, mapAddRegionIn{
		MapID: uuid.New().String(), Name: "R", Polygon: [][]float64{{0, 0}, {1, 1}},
	}); err == nil {
		t.Fatal("expected an error for a polygon with < 3 points")
	}
}

// ── DB round-trip + owner-scoping ────────────────────────────────────────────

func TestMapAuthoringRoundTrip(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "MapWorld"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	worldID := wout.World.WorldID

	_, mout, err := s.toolWorldMapCreate(ctx, nil, worldMapCreateIn{WorldID: worldID, Name: "The Realms"})
	if err != nil {
		t.Fatalf("world_map_create: %v", err)
	}
	mapID := mout.Map.MapID

	if _, _, err := s.toolWorldMapAddMarker(ctx, nil, mapAddMarkerIn{
		MapID: mapID, Label: "Ironhold", X: 0.3, Y: 0.6, MarkerType: "city",
	}); err != nil {
		t.Fatalf("add_marker: %v", err)
	}
	if _, _, err := s.toolWorldMapAddRegion(ctx, nil, mapAddRegionIn{
		MapID: mapID, Name: "The North", Polygon: [][]float64{{0, 0}, {1, 0}, {0.5, 1}},
	}); err != nil {
		t.Fatalf("add_region: %v", err)
	}

	_, gout, err := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if err != nil {
		t.Fatalf("world_map_get: %v", err)
	}
	if len(gout.Markers) != 1 || gout.Markers[0].Label != "Ironhold" || gout.Markers[0].X != 0.3 {
		t.Fatalf("marker not round-tripped: %+v", gout.Markers)
	}
	if len(gout.Regions) != 1 || gout.Regions[0].Name != "The North" || len(gout.Regions[0].Polygon) != 3 {
		t.Fatalf("region not round-tripped: %+v", gout.Regions)
	}

	_, lout, err := s.toolWorldMapList(ctx, nil, mapListIn{WorldID: worldID})
	if err != nil || len(lout.Maps) != 1 || lout.Maps[0].MapID != mapID {
		t.Fatalf("world_map_list: %v maps=%+v", err, lout.Maps)
	}

	// Owner-scoping: user B can neither read nor write owner A's map.
	ctxB := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapGet(ctxB, nil, mapGetIn{MapID: mapID}); err == nil {
		t.Fatal("user B must NOT read owner A's map")
	}
	if _, _, err := s.toolWorldMapAddMarker(ctxB, nil, mapAddMarkerIn{
		MapID: mapID, Label: "sneaky", X: 0.1, Y: 0.1,
	}); err == nil {
		t.Fatal("user B must NOT add a marker to owner A's map")
	}
}

// ── update-tool validation (no DB — checks short-circuit before pool access) ──

func TestWorldMapUpdate_RequiresUUID(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: "nope"}); err == nil {
		t.Fatal("expected an error for a non-UUID map_id")
	}
}

func TestWorldMapUpdateMarker_RejectsOutOfRangeCoords(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	bad := 1.5
	// x > 1 must be rejected BEFORE any DB access (relative-coord invariant).
	if _, _, err := s.toolWorldMapUpdateMarker(ctx, nil, mapUpdateMarkerIn{
		MarkerID: uuid.New().String(), X: &bad,
	}); err == nil {
		t.Fatal("expected an error for x outside [0,1]")
	}
}

func TestWorldMapUpdateRegion_RejectsTooFewPoints(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	// A present-but-degenerate polygon (< 3 pts) is rejected; nil polygon would be "leave unchanged".
	if _, _, err := s.toolWorldMapUpdateRegion(ctx, nil, mapUpdateRegionIn{
		RegionID: uuid.New().String(), Polygon: [][]float64{{0, 0}, {1, 1}},
	}); err == nil {
		t.Fatal("expected an error for a polygon with < 3 points")
	}
}

// ── UPDATE round-trip: the pointer rule + version bump + unbind (needs DB) ──────
func TestMapUpdateRoundTrip(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "UpdWorld"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	_, mout, err := s.toolWorldMapCreate(ctx, nil, worldMapCreateIn{WorldID: wout.World.WorldID, Name: "Atlas"})
	if err != nil {
		t.Fatalf("map_create: %v", err)
	}
	mapID := mout.Map.MapID
	// M1 — a freshly-created map reads version=1 (the migration/DEFAULT round-trips).
	if mout.Map.Version != 1 {
		t.Fatalf("fresh map must be version 1, got %d", mout.Map.Version)
	}

	entity := uuid.New()
	_, mk, err := s.toolWorldMapAddMarker(ctx, nil, mapAddMarkerIn{
		MapID: mapID, Label: "Keep", X: 0.30, Y: 0.60, EntityID: entity.String(),
	})
	if err != nil {
		t.Fatalf("add_marker: %v", err)
	}

	// M1 — the marker round-trips a non-empty updated_at.
	_, g0, _ := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if len(g0.Markers) != 1 || g0.Markers[0].UpdatedAt == "" {
		t.Fatalf("marker updated_at must round-trip non-empty, got %+v", g0.Markers)
	}

	// 🔴 The pointer rule — a LABEL-ONLY update must NOT move the pin to (0,0).
	newLabel := "Renamed"
	if _, _, err := s.toolWorldMapUpdateMarker(ctx, nil, mapUpdateMarkerIn{MarkerID: mk.MarkerID, Label: &newLabel}); err != nil {
		t.Fatalf("update_marker(label-only): %v", err)
	}
	_, g1, _ := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if g1.Markers[0].X != 0.30 || g1.Markers[0].Y != 0.60 {
		t.Fatalf("label-only update TELEPORTED the pin (pointer-rule bug): got x=%v y=%v", g1.Markers[0].X, g1.Markers[0].Y)
	}
	if g1.Markers[0].Label != "Renamed" {
		t.Fatalf("label not updated: %+v", g1.Markers[0])
	}
	if g1.Markers[0].MarkerID != mk.MarkerID {
		t.Fatalf("marker_id churned on update: %s -> %s", mk.MarkerID, g1.Markers[0].MarkerID)
	}
	if g1.Markers[0].EntityID == nil || *g1.Markers[0].EntityID != entity.String() {
		t.Fatalf("entity tie must survive a label-only update, got %+v", g1.Markers[0].EntityID)
	}

	// A coord update (a drag) moves the ABSOLUTE position keeping the same marker_id.
	nx, ny := 0.80, 0.10
	if _, _, err := s.toolWorldMapUpdateMarker(ctx, nil, mapUpdateMarkerIn{MarkerID: mk.MarkerID, X: &nx, Y: &ny}); err != nil {
		t.Fatalf("update_marker(move): %v", err)
	}
	_, g2, _ := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if g2.Markers[0].X != 0.80 || g2.Markers[0].Y != 0.10 || g2.Markers[0].MarkerID != mk.MarkerID {
		t.Fatalf("drag PATCH failed: %+v", g2.Markers[0])
	}

	// clear_entity unbinds without deleting the pin.
	if _, _, err := s.toolWorldMapUpdateMarker(ctx, nil, mapUpdateMarkerIn{MarkerID: mk.MarkerID, ClearEntity: true}); err != nil {
		t.Fatalf("update_marker(clear_entity): %v", err)
	}
	_, g3, _ := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if len(g3.Markers) != 1 || g3.Markers[0].EntityID != nil {
		t.Fatalf("clear_entity must unbind but keep the pin, got %+v", g3.Markers)
	}

	// world_map_update — rename bumps version.
	rename := "Atlas II"
	_, uout, err := s.toolWorldMapUpdate(ctx, nil, mapUpdateIn{MapID: mapID, Name: &rename})
	if err != nil {
		t.Fatalf("world_map_update: %v", err)
	}
	if uout.Map.Name != "Atlas II" || uout.Map.Version != 2 {
		t.Fatalf("rename must set name + bump version to 2, got name=%q version=%d", uout.Map.Name, uout.Map.Version)
	}

	// Region reshape keeps the region_id.
	_, rg, err := s.toolWorldMapAddRegion(ctx, nil, mapAddRegionIn{
		MapID: mapID, Name: "Wilds", Polygon: [][]float64{{0, 0}, {1, 0}, {0.5, 1}},
	})
	if err != nil {
		t.Fatalf("add_region: %v", err)
	}
	newPoly := [][]float64{{0.1, 0.1}, {0.9, 0.1}, {0.9, 0.9}, {0.1, 0.9}}
	_, rout, err := s.toolWorldMapUpdateRegion(ctx, nil, mapUpdateRegionIn{RegionID: rg.RegionID, Polygon: newPoly})
	if err != nil {
		t.Fatalf("update_region(reshape): %v", err)
	}
	if rout.Region.RegionID != rg.RegionID || len(rout.Region.Polygon) != 4 {
		t.Fatalf("reshape failed: %+v", rout.Region)
	}

	// Owner-scoping: user B cannot update owner A's marker/region/map.
	ctxB := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapUpdateMarker(ctxB, nil, mapUpdateMarkerIn{MarkerID: mk.MarkerID, Label: &newLabel}); err == nil {
		t.Fatal("user B must NOT update owner A's marker")
	}
	if _, _, err := s.toolWorldMapUpdate(ctxB, nil, mapUpdateIn{MapID: mapID, Name: &rename}); err == nil {
		t.Fatal("user B must NOT rename owner A's map")
	}
}

// ── delete / remove validation (no DB — checks short-circuit before pool access) ──

func TestWorldMapDelete_RequiresUUID(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapDelete(ctx, nil, mapDeleteIn{MapID: "nope"}); err == nil {
		t.Fatal("expected an error for a non-UUID map_id")
	}
}

func TestWorldMapRemoveMarker_RequiresUUID(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapRemoveMarker(ctx, nil, mapRemoveMarkerIn{MarkerID: "nope"}); err == nil {
		t.Fatal("expected an error for a non-UUID marker_id")
	}
}

func TestWorldMapRemoveRegion_RequiresUUID(t *testing.T) {
	t.Parallel()
	s := &Server{}
	ctx := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapRemoveRegion(ctx, nil, mapRemoveRegionIn{RegionID: "nope"}); err == nil {
		t.Fatal("expected an error for a non-UUID region_id")
	}
}

// ── image-upload REST validation (no DB / no MinIO — pre-storage guards) ──────

func mapImageReq(t *testing.T, mapID, userID string) *http.Request {
	t.Helper()
	url := "/internal/worlds/maps/" + mapID + "/image"
	if userID != "" {
		url += "?user_id=" + userID
	}
	req := httptest.NewRequest(http.MethodPost, url, nil)
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("map_id", mapID)
	return req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
}

func TestUploadWorldMapImage_BadUserID_400(t *testing.T) {
	t.Parallel()
	s := &Server{}
	rr := httptest.NewRecorder()
	s.uploadWorldMapImage(rr, mapImageReq(t, uuid.New().String(), "")) // no user_id
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("want 400 for a missing user_id, got %d", rr.Code)
	}
}

func TestUploadWorldMapImage_NoStorage_503(t *testing.T) {
	t.Parallel()
	s := &Server{} // s.minio == nil
	rr := httptest.NewRecorder()
	s.uploadWorldMapImage(rr, mapImageReq(t, uuid.New().String(), uuid.New().String()))
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503 when media storage is unconfigured, got %d", rr.Code)
	}
}

// ── delete + remove + CASCADE + image_ref round-trip (needs BOOK_TEST_DATABASE_URL) ──

func TestMapDeleteRemoveAndImageRefRoundTrip(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "DelWorld"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	worldID := wout.World.WorldID

	// image_ref on create is stored + resolved to a URL.
	_, mout, err := s.toolWorldMapCreate(ctx, nil, worldMapCreateIn{
		WorldID: worldID, Name: "The Realms", ImageRef: "worlds/maps/seed/base.png",
	})
	if err != nil {
		t.Fatalf("world_map_create: %v", err)
	}
	if mout.Map.ImageObjectKey == nil || *mout.Map.ImageObjectKey != "worlds/maps/seed/base.png" {
		t.Fatalf("image_ref not stored: %+v", mout.Map)
	}
	if mout.Map.ImageURL == nil || *mout.Map.ImageURL == "" {
		t.Fatalf("image_url not resolved when an image is set: %+v", mout.Map)
	}
	mapID := mout.Map.MapID

	_, mk, err := s.toolWorldMapAddMarker(ctx, nil, mapAddMarkerIn{MapID: mapID, Label: "Ironhold", X: 0.3, Y: 0.6})
	if err != nil {
		t.Fatalf("add_marker: %v", err)
	}
	_, rg, err := s.toolWorldMapAddRegion(ctx, nil, mapAddRegionIn{
		MapID: mapID, Name: "The North", Polygon: [][]float64{{0, 0}, {1, 0}, {0.5, 1}},
	})
	if err != nil {
		t.Fatalf("add_region: %v", err)
	}

	// Owner-scoping: user B can neither remove A's marker nor A's region.
	ctxB := identityCtxForTest(t, uuid.New())
	if _, _, err := s.toolWorldMapRemoveMarker(ctxB, nil, mapRemoveMarkerIn{MarkerID: mk.MarkerID}); err == nil {
		t.Fatal("user B must NOT remove owner A's marker")
	}
	if _, _, err := s.toolWorldMapRemoveRegion(ctxB, nil, mapRemoveRegionIn{RegionID: rg.RegionID}); err == nil {
		t.Fatal("user B must NOT remove owner A's region")
	}

	// Owner removes the region; the marker stays for the CASCADE check below.
	_, rmr, err := s.toolWorldMapRemoveRegion(ctx, nil, mapRemoveRegionIn{RegionID: rg.RegionID})
	if err != nil || !rmr.Removed {
		t.Fatalf("remove_region: %v removed=%v", err, rmr.Removed)
	}
	_, gout, err := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID})
	if err != nil || len(gout.Regions) != 0 || len(gout.Markers) != 1 {
		t.Fatalf("after remove_region: err=%v regions=%d markers=%d", err, len(gout.Regions), len(gout.Markers))
	}

	// Delete the map; its remaining marker must CASCADE away.
	_, dout, err := s.toolWorldMapDelete(ctx, nil, mapDeleteIn{MapID: mapID})
	if err != nil || !dout.Deleted {
		t.Fatalf("world_map_delete: %v deleted=%v", err, dout.Deleted)
	}
	mid := uuid.MustParse(mapID)
	var markerCount int
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM map_markers WHERE map_id=$1`, mid).Scan(&markerCount); err != nil {
		t.Fatalf("cascade count: %v", err)
	}
	if markerCount != 0 {
		t.Fatalf("map delete did not CASCADE markers: %d remain", markerCount)
	}

	// The deleted map is unreadable, and a re-delete is a uniform not-found (no oracle).
	if _, _, err := s.toolWorldMapGet(ctx, nil, mapGetIn{MapID: mapID}); err == nil {
		t.Fatal("a deleted map must not be readable")
	}
	if _, _, err := s.toolWorldMapDelete(ctx, nil, mapDeleteIn{MapID: mapID}); err == nil {
		t.Fatal("re-deleting a gone map must return not found")
	}
}
