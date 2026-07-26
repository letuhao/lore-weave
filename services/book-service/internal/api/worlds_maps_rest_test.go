package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// ── validation (no DB — parseUUIDParam short-circuits before any pool access) ──

func TestListWorldMaps_InvalidWorldID_400(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/v1/worlds/not-a-uuid/maps", "", worldJWT(t, uuid.New()),
		map[string]string{"world_id": "not-a-uuid"})
	s.listWorldMaps(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid world_id, got %d", rr.Code)
	}
}

func TestGetWorldMap_InvalidMapID_400(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	world := uuid.New().String()
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodGet, "/v1/worlds/"+world+"/maps/not-a-uuid", "", worldJWT(t, uuid.New()),
		map[string]string{"world_id": world, "map_id": "not-a-uuid"})
	s.getWorldMapREST(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid map_id, got %d", rr.Code)
	}
}

// ── round-trip + owner-scope (needs BOOK_TEST_DATABASE_URL) ───────────────────
//
// Seed a world + map + marker + region through the authoring TOOLS, then read them back through the
// REST canvas routes the FE uses — proving the two GETs return exactly what the tools wrote, and
// that a non-owner is a plain 404 (no cross-tenant leak / existence oracle).
func TestWorldMapsREST_RoundTripAndOwnerScope(t *testing.T) {
	s, _ := dbTestServer(t)
	s.secret = []byte(worldSecret) // align with worldJWT so requireWorldOwner authenticates the REST call
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "MapRESTWorld"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	worldID := wout.World.WorldID
	_, mout, err := s.toolWorldMapCreate(ctx, nil, worldMapCreateIn{WorldID: worldID, Name: "Atlas"})
	if err != nil {
		t.Fatalf("map_create: %v", err)
	}
	mapID := mout.Map.MapID
	if _, _, err := s.toolWorldMapAddMarker(ctx, nil, mapAddMarkerIn{
		MapID: mapID, Label: "Keep", X: 0.2, Y: 0.5, MarkerType: "city",
	}); err != nil {
		t.Fatalf("add_marker: %v", err)
	}
	if _, _, err := s.toolWorldMapAddRegion(ctx, nil, mapAddRegionIn{
		MapID: mapID, Name: "Wilds", Polygon: [][]float64{{0, 0}, {1, 0}, {0.5, 1}},
	}); err != nil {
		t.Fatalf("add_region: %v", err)
	}

	srv := httptest.NewServer(s.Router())
	defer srv.Close()
	client := srv.Client()

	get := func(path, token string) (*http.Response, error) {
		req, _ := http.NewRequest(http.MethodGet, srv.URL+path, nil)
		req.Header.Set("Authorization", "Bearer "+token)
		return client.Do(req)
	}

	// list
	resp, err := get("/v1/worlds/"+worldID+"/maps", worldJWT(t, owner))
	if err != nil {
		t.Fatalf("list GET: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("list expected 200, got %d", resp.StatusCode)
	}
	var listBody struct {
		Items []map[string]any `json:"items"`
		Total int              `json:"total"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&listBody)
	resp.Body.Close()
	if listBody.Total != 1 || len(listBody.Items) != 1 || listBody.Items[0]["map_id"] != mapID {
		t.Fatalf("expected exactly the one seeded map, got %+v", listBody)
	}

	// detail
	resp2, err := get("/v1/worlds/"+worldID+"/maps/"+mapID, worldJWT(t, owner))
	if err != nil {
		t.Fatalf("detail GET: %v", err)
	}
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("detail expected 200, got %d", resp2.StatusCode)
	}
	var detail struct {
		Map     map[string]any   `json:"map"`
		Markers []map[string]any `json:"markers"`
		Regions []map[string]any `json:"regions"`
	}
	_ = json.NewDecoder(resp2.Body).Decode(&detail)
	resp2.Body.Close()
	if len(detail.Markers) != 1 || detail.Markers[0]["label"] != "Keep" {
		t.Fatalf("marker not round-tripped through REST: %+v", detail.Markers)
	}
	if len(detail.Regions) != 1 || detail.Regions[0]["name"] != "Wilds" {
		t.Fatalf("region not round-tripped through REST: %+v", detail.Regions)
	}

	// owner-scope: a different user gets 404 (world isn't theirs), never the map
	respB, err := get("/v1/worlds/"+worldID+"/maps/"+mapID, worldJWT(t, uuid.New()))
	if err != nil {
		t.Fatalf("user-B detail GET: %v", err)
	}
	respB.Body.Close()
	if respB.StatusCode != http.StatusNotFound {
		t.Fatalf("user B must get 404 on owner A's map, got %d", respB.StatusCode)
	}
}
