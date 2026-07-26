package api

// S7·2 — the world-map editor's public write routes. Validation-level tests (no DB) run always;
// the create→update→delete round-trip + the OCC (428/412) + the pointer-rule PATCH need
// BOOK_TEST_DATABASE_URL.

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// ── validation (no DB) ────────────────────────────────────────────────────────

func TestParseIfMatchVersion(t *testing.T) {
	t.Parallel()
	// parseIfMatchVersion is the pure unit behind the map-rename OCC (428 absent / 400 malformed).
	r2 := worldReq(http.MethodPatch, "/x", "", "", nil)
	if _, present, _ := parseIfMatchVersion(r2); present {
		t.Fatal("absent If-Match must report present=false (→428)")
	}
	r3 := worldReq(http.MethodPatch, "/x", "", "", nil)
	r3.Header.Set("If-Match", `"7"`)
	if v, present, valid := parseIfMatchVersion(r3); !present || !valid || v != 7 {
		t.Fatalf("quoted If-Match must parse to 7, got v=%d present=%v valid=%v", v, present, valid)
	}
	r4 := worldReq(http.MethodPatch, "/x", "", "", nil)
	r4.Header.Set("If-Match", "abc")
	if _, present, valid := parseIfMatchVersion(r4); !present || valid {
		t.Fatal("malformed If-Match must report present=true, valid=false (→400)")
	}
}

func TestValidPolygon(t *testing.T) {
	t.Parallel()
	rr := httptest.NewRecorder()
	if validPolygon(rr, [][]float64{{0, 0}, {1, 1}}) {
		t.Fatal("a 2-point polygon must be rejected")
	}
	rr2 := httptest.NewRecorder()
	if validPolygon(rr2, [][]float64{{0, 0}, {1, 0}, {1.5, 1}}) {
		t.Fatal("an out-of-range vertex must be rejected")
	}
	rr3 := httptest.NewRecorder()
	if !validPolygon(rr3, [][]float64{{0, 0}, {1, 0}, {0.5, 1}}) {
		t.Fatal("a valid triangle must pass")
	}
}

func TestPolygonFromAny(t *testing.T) {
	t.Parallel()
	var decoded any
	_ = json.Unmarshal([]byte(`[[0.1,0.2],[0.3,0.4],[0.5,0.6]]`), &decoded)
	poly, err := polygonFromAny(decoded)
	if err != nil || len(poly) != 3 || poly[1][0] != 0.3 {
		t.Fatalf("polygonFromAny round-trip failed: %+v err=%v", poly, err)
	}
	if _, err := polygonFromAny("nope"); err == nil {
		t.Fatal("a non-array polygon must error")
	}
}

func TestAddMarkerREST_InvalidWorldID_400(t *testing.T) {
	t.Parallel()
	s := &Server{secret: []byte(worldSecret)}
	rr := httptest.NewRecorder()
	req := worldReq(http.MethodPost, "/v1/worlds/not-a-uuid/maps/x/markers", `{"label":"a","x":0.1,"y":0.1}`,
		worldJWT(t, uuid.New()), map[string]string{"world_id": "not-a-uuid", "map_id": uuid.New().String()})
	s.addMarkerREST(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for an invalid world_id, got %d", rr.Code)
	}
}

// ── DB round-trip: create → PATCH (OCC + pointer rule) → delete ────────────────

func TestWorldMapWriteREST_RoundTrip(t *testing.T) {
	s, _ := dbTestServer(t)
	s.secret = []byte(worldSecret)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)
	_, wout, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: "WriteRESTWorld"})
	if err != nil {
		t.Fatalf("world_create: %v", err)
	}
	worldID := wout.World.WorldID

	srv := httptest.NewServer(s.Router())
	defer srv.Close()
	client := srv.Client()
	tok := worldJWT(t, owner)

	do := func(method, path, body string, headers map[string]string) (*http.Response, map[string]any) {
		var req *http.Request
		if body != "" {
			req, _ = http.NewRequest(method, srv.URL+path, strings.NewReader(body))
			req.Header.Set("Content-Type", "application/json")
		} else {
			req, _ = http.NewRequest(method, srv.URL+path, nil)
		}
		req.Header.Set("Authorization", "Bearer "+tok)
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		resp, err := client.Do(req)
		if err != nil {
			t.Fatalf("%s %s: %v", method, path, err)
		}
		var out map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&out)
		resp.Body.Close()
		return resp, out
	}

	// R1 create map.
	resp, body := do(http.MethodPost, "/v1/worlds/"+worldID+"/maps", `{"name":"Atlas"}`, nil)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create map: want 201, got %d", resp.StatusCode)
	}
	mp := body["map"].(map[string]any)
	mapID := mp["map_id"].(string)
	if mp["version"].(float64) != 1 {
		t.Fatalf("new map must be version 1, got %v", mp["version"])
	}

	// R5 add marker.
	resp, body = do(http.MethodPost, "/v1/worlds/"+worldID+"/maps/"+mapID+"/markers",
		`{"label":"Keep","x":0.3,"y":0.6}`, nil)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("add marker: want 201, got %d", resp.StatusCode)
	}
	marker := body["marker"].(map[string]any)
	markerID := marker["marker_id"].(string)
	if marker["updated_at"].(string) == "" {
		t.Fatal("marker must carry a non-empty updated_at")
	}

	// R6 — label-only PATCH must NOT move the pin (the pointer rule).
	resp, body = do(http.MethodPatch, "/v1/worlds/"+worldID+"/maps/"+mapID+"/markers/"+markerID,
		`{"label":"Renamed"}`, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("patch marker(label): want 200, got %d", resp.StatusCode)
	}
	pm := body["marker"].(map[string]any)
	if pm["x"].(float64) != 0.3 || pm["y"].(float64) != 0.6 {
		t.Fatalf("label-only PATCH teleported the pin: %+v", pm)
	}
	if pm["marker_id"].(string) != markerID {
		t.Fatalf("marker_id churned on PATCH: %s -> %s", markerID, pm["marker_id"])
	}

	// R6 — a drag PATCHes the ABSOLUTE coord.
	resp, body = do(http.MethodPatch, "/v1/worlds/"+worldID+"/maps/"+mapID+"/markers/"+markerID,
		`{"x":0.8,"y":0.1}`, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("patch marker(move): want 200, got %d", resp.StatusCode)
	}
	pm = body["marker"].(map[string]any)
	if pm["x"].(float64) != 0.8 || pm["y"].(float64) != 0.1 {
		t.Fatalf("drag PATCH failed: %+v", pm)
	}

	// R2 — rename WITHOUT If-Match → 428.
	resp, _ = do(http.MethodPatch, "/v1/worlds/"+worldID+"/maps/"+mapID, `{"name":"Atlas II"}`, nil)
	if resp.StatusCode != http.StatusPreconditionRequired {
		t.Fatalf("rename without If-Match: want 428, got %d", resp.StatusCode)
	}

	// R2 — stale If-Match → 412 with the current row.
	resp, body = do(http.MethodPatch, "/v1/worlds/"+worldID+"/maps/"+mapID, `{"name":"Atlas II"}`,
		map[string]string{"If-Match": "999"})
	if resp.StatusCode != http.StatusPreconditionFailed {
		t.Fatalf("stale rename: want 412, got %d", resp.StatusCode)
	}
	if body["code"] != "MAP_VERSION_CONFLICT" || body["current"] == nil {
		t.Fatalf("412 must carry MAP_VERSION_CONFLICT + current row, got %+v", body)
	}

	// R2 — correct If-Match → 200, version bumps to 2.
	resp, body = do(http.MethodPatch, "/v1/worlds/"+worldID+"/maps/"+mapID, `{"name":"Atlas II"}`,
		map[string]string{"If-Match": "1"})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("rename with correct If-Match: want 200, got %d", resp.StatusCode)
	}
	if body["map"].(map[string]any)["version"].(float64) != 2 {
		t.Fatalf("rename must bump version to 2, got %v", body["map"].(map[string]any)["version"])
	}

	// R8 add region + R9 reshape.
	resp, body = do(http.MethodPost, "/v1/worlds/"+worldID+"/maps/"+mapID+"/regions",
		`{"name":"Wilds","polygon":[[0,0],[1,0],[0.5,1]]}`, nil)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("add region: want 201, got %d", resp.StatusCode)
	}
	regionID := body["region"].(map[string]any)["region_id"].(string)
	resp, body = do(http.MethodPatch, "/v1/worlds/"+worldID+"/maps/"+mapID+"/regions/"+regionID,
		`{"polygon":[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]]}`, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("reshape region: want 200, got %d", resp.StatusCode)
	}
	if len(body["region"].(map[string]any)["polygon"].([]any)) != 4 {
		t.Fatalf("reshape must persist 4 vertices, got %+v", body["region"])
	}

	// R7/R10 deletes.
	resp, _ = do(http.MethodDelete, "/v1/worlds/"+worldID+"/maps/"+mapID+"/markers/"+markerID, "", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("delete marker: want 200, got %d", resp.StatusCode)
	}
	resp, _ = do(http.MethodDelete, "/v1/worlds/"+worldID+"/maps/"+mapID+"/regions/"+regionID, "", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("delete region: want 200, got %d", resp.StatusCode)
	}

	// Owner-scope: user B cannot delete owner A's map.
	reqB, _ := http.NewRequest(http.MethodDelete, srv.URL+"/v1/worlds/"+worldID+"/maps/"+mapID, nil)
	reqB.Header.Set("Authorization", "Bearer "+worldJWT(t, uuid.New()))
	respB, _ := client.Do(reqB)
	respB.Body.Close()
	if respB.StatusCode != http.StatusNotFound {
		t.Fatalf("user B deleting A's map: want 404, got %d", respB.StatusCode)
	}

	// R3 owner deletes the map.
	resp, _ = do(http.MethodDelete, "/v1/worlds/"+worldID+"/maps/"+mapID, "", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("delete map: want 200, got %d", resp.StatusCode)
	}
}
