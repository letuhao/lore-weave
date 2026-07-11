package api

// W10-M2 world-map MCP tools. Validation/coord guards run always; the create →
// marker → region → get round-trip + owner-scoping require BOOK_TEST_DATABASE_URL.

import (
	"testing"

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
