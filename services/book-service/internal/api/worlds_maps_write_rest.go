package api

// S7·2 — the world-map editor's public write surface. The read routes (worlds_maps_rest.go) and
// the world_map_* MCP tools existed; the human editor needs first-party REST writes: create/rename/
// delete a map, add/update/delete markers + regions. All mounted under /v1/worlds/{world_id}/maps*
// so requireWorldOwner gates the world from the JWT and every map/marker/region query re-scopes to
// owner_user_id (uniform 404, no existence oracle) — identical tenancy posture to the read routes.
//
// OCC (spec §4.4): the MAP rename/image PATCH is version-gated (If-Match REQUIRED → 428 absent,
// 412 on a stale version with the current row). Markers/regions are last-write-wins — a conscious
// divergence: worlds have no E0 sharing (single-owner), and a marker write is an ABSOLUTE coord /
// whole-polygon replace (idempotent), so a "lost update" just means the later position wins, which
// is the correct semantics for a drag. updated_at is still read so the client can show "edited".

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"
)

// ── R1 · POST /v1/worlds/{world_id}/maps ─────────────────────────────────────
func (s *Server) createMapREST(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	var in struct {
		Name     string `json:"name"`
		ImageRef string `json:"image_ref"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "name is required")
		return
	}
	imageRef := strings.TrimSpace(in.ImageRef)
	var mapID uuid.UUID
	var version int
	// requireWorldOwner already confirmed the world is owned; scope the INSERT to owner_user_id too.
	if err := s.pool.QueryRow(r.Context(), `
INSERT INTO world_maps(owner_user_id, world_id, name, image_object_key) VALUES($1,$2,$3,$4) RETURNING id, version`,
		ownerID, worldID, name, nullableString(imageRef)).Scan(&mapID, &version); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create map")
		return
	}
	d := worldMapDetail{MapID: mapID.String(), WorldID: worldID.String(), Name: name, Version: version}
	if imageRef != "" {
		d.ImageObjectKey = &imageRef
		s.withImageURL(&d)
	}
	writeJSON(w, http.StatusCreated, map[string]any{"map": d})
}

// parseIfMatchVersion reads the If-Match header as an integer version. Absent ⇒ (0,false,false):
// 428 Precondition Required (an OPTIONAL If-Match would make a blind clobber a legal request — the
// arc-inspector lesson). Malformed ⇒ (0,true,false): 400. Strips optional quotes / W/ prefix.
func parseIfMatchVersion(r *http.Request) (version int, present, valid bool) {
	raw := strings.TrimSpace(r.Header.Get("If-Match"))
	if raw == "" {
		return 0, false, false
	}
	raw = strings.TrimPrefix(raw, "W/")
	raw = strings.Trim(raw, `"`)
	raw = strings.TrimSpace(raw)
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0, true, false
	}
	return n, true, true
}

// ── R2 · PATCH /v1/worlds/{world_id}/maps/{map_id} (If-Match:<version>) ───────
func (s *Server) patchMapREST(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	expected, present, valid := parseIfMatchVersion(r)
	if !present {
		writeError(w, http.StatusPreconditionRequired, "MAP_IF_MATCH_REQUIRED", "If-Match: <version> is required")
		return
	}
	if !valid {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "If-Match must be an integer version")
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	setClauses := []string{"updated_at=now()", "version=version+1"}
	args := []any{mapID, ownerID, expected}
	idx := 4
	if v, ok := in["name"]; ok {
		name, _ := v.(string)
		if strings.TrimSpace(name) == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "name cannot be empty")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("name=$%d", idx))
		args = append(args, strings.TrimSpace(name))
		idx++
	}
	if _, ok := in["image_object_key"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("image_object_key=$%d", idx))
		args = append(args, stringFromAny(in["image_object_key"]))
		idx++
	}
	query := fmt.Sprintf(
		`UPDATE world_maps SET %s WHERE id=$1 AND owner_user_id=$2 AND version=$3
		 RETURNING id, world_id, name, image_object_key, version`,
		strings.Join(setClauses, ", "))
	var d worldMapDetail
	var gotMap, gotWorld uuid.UUID
	err := s.pool.QueryRow(r.Context(), query, args...).Scan(&gotMap, &gotWorld, &d.Name, &d.ImageObjectKey, &d.Version)
	if errors.Is(err, pgx.ErrNoRows) {
		// 0 rows: either the map is gone/foreign (404) OR the version mismatched (412). One
		// owner-scoped read disambiguates — a version conflict returns the CURRENT row so the
		// client reseeds and re-applies (never a blind clobber).
		s.mapConflictOr404(w, r, mapID, ownerID)
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update map")
		return
	}
	d.MapID = gotMap.String()
	d.WorldID = gotWorld.String()
	s.withImageURL(&d)
	writeJSON(w, http.StatusOK, map[string]any{"map": d})
}

// mapConflictOr404 resolves whether a failed version-gated PATCH was a missing map (404) or a
// stale version (412 MAP_VERSION_CONFLICT with the current row).
func (s *Server) mapConflictOr404(w http.ResponseWriter, r *http.Request, mapID, ownerID uuid.UUID) {
	var d worldMapDetail
	var gotMap, gotWorld uuid.UUID
	err := s.pool.QueryRow(r.Context(), `
SELECT id, world_id, name, image_object_key, version FROM world_maps WHERE id=$1 AND owner_user_id=$2`,
		mapID, ownerID).Scan(&gotMap, &gotWorld, &d.Name, &d.ImageObjectKey, &d.Version)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "map not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to resolve map")
		return
	}
	d.MapID = gotMap.String()
	d.WorldID = gotWorld.String()
	s.withImageURL(&d)
	writeJSON(w, http.StatusPreconditionFailed, map[string]any{
		"code":    "MAP_VERSION_CONFLICT",
		"message": "this map changed elsewhere — reload and retry",
		"current": d,
	})
}

// ── R3 · DELETE /v1/worlds/{world_id}/maps/{map_id} ──────────────────────────
func (s *Server) deleteMapREST(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	// Grab the blob key for best-effort cleanup while confirming ownership (404 if foreign/missing).
	var imageKey *string
	err := s.pool.QueryRow(r.Context(), `SELECT image_object_key FROM world_maps WHERE id=$1 AND owner_user_id=$2`, mapID, ownerID).Scan(&imageKey)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "map not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to resolve map")
		return
	}
	if _, err := s.pool.Exec(r.Context(), `DELETE FROM world_maps WHERE id=$1 AND owner_user_id=$2`, mapID, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to delete map")
		return
	}
	s.sweepMapImage(r, imageKey)
	writeJSON(w, http.StatusOK, map[string]any{"deleted": true})
}

// ── R5 · POST /v1/worlds/{world_id}/maps/{map_id}/markers ────────────────────
func (s *Server) addMarkerREST(w http.ResponseWriter, r *http.Request) {
	mapID, ownerID, ok := s.resolveMapRoute(w, r)
	if !ok {
		return
	}
	var in struct {
		Label      string   `json:"label"`
		X          *float64 `json:"x"`
		Y          *float64 `json:"y"`
		EntityID   string   `json:"entity_id"`
		MarkerType string   `json:"marker_type"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	label := strings.TrimSpace(in.Label)
	if label == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "label is required")
		return
	}
	if in.X == nil || in.Y == nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "x and y are required")
		return
	}
	if *in.X < 0 || *in.X > 1 || *in.Y < 0 || *in.Y > 1 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "x and y must be in [0,1]")
		return
	}
	entityID, err := parseOptionalEntityID(in.EntityID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", err.Error())
		return
	}
	// INSERT gated on ownership of the map in ONE atomic statement (a foreign map inserts 0 rows).
	var id uuid.UUID
	var updatedAt time.Time
	err = s.pool.QueryRow(r.Context(), `
INSERT INTO map_markers(map_id, entity_id, label, x, y, marker_type)
SELECT $1,$2,$3,$4,$5,$6 WHERE EXISTS(SELECT 1 FROM world_maps WHERE id=$1 AND owner_user_id=$7)
RETURNING id, updated_at`,
		mapID, entityID, label, *in.X, *in.Y, nullableString(strings.TrimSpace(in.MarkerType)), ownerID).Scan(&id, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "map not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to add marker")
		return
	}
	m := markerOut{MarkerID: id.String(), Label: label, X: *in.X, Y: *in.Y, UpdatedAt: updatedAt.UTC().Format(time.RFC3339Nano)}
	if entityID != nil {
		eid := entityID.String()
		m.EntityID = &eid
	}
	if mt := strings.TrimSpace(in.MarkerType); mt != "" {
		m.MarkerType = &mt
	}
	writeJSON(w, http.StatusCreated, map[string]any{"marker": m})
}

// ── R6 · PATCH .../markers/{marker_id} — THE load-bearing drag route ─────────
func (s *Server) patchMarkerREST(w http.ResponseWriter, r *http.Request) {
	_, ownerID, ok := s.resolveMapRoute(w, r)
	if !ok {
		return
	}
	markerID, ok := parseUUIDParam(w, r, "marker_id")
	if !ok {
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	setClauses := []string{"updated_at=now()"}
	args := []any{markerID, ownerID}
	idx := 3
	// x/y: absolute new coords (a drag). Present-only (the pointer rule) — a relabel-only PATCH
	// must NOT move the pin. Range-validated only when present.
	if v, present := in["x"]; present {
		x, num := numberFromAny(v)
		if !num || x < 0 || x > 1 {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "x must be a number in [0,1]")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("x=$%d", idx))
		args = append(args, x)
		idx++
	}
	if v, present := in["y"]; present {
		y, num := numberFromAny(v)
		if !num || y < 0 || y > 1 {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "y must be a number in [0,1]")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("y=$%d", idx))
		args = append(args, y)
		idx++
	}
	if v, present := in["label"]; present {
		label, _ := v.(string)
		if strings.TrimSpace(label) == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "label cannot be empty")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("label=$%d", idx))
		args = append(args, strings.TrimSpace(label))
		idx++
	}
	if v, present := in["marker_type"]; present {
		setClauses = append(setClauses, fmt.Sprintf("marker_type=$%d", idx))
		args = append(args, stringFromAny(v))
		idx++
	}
	// entity_id: key absent ⇒ leave; null ⇒ unbind; "<uuid>" ⇒ rebind (§4.4 omitted-vs-null).
	if v, present := in["entity_id"]; present {
		if v == nil {
			setClauses = append(setClauses, "entity_id=NULL")
		} else {
			raw, _ := v.(string)
			eid, err := uuid.Parse(strings.TrimSpace(raw))
			if err != nil {
				writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "entity_id must be a UUID or null")
				return
			}
			setClauses = append(setClauses, fmt.Sprintf("entity_id=$%d", idx))
			args = append(args, eid)
			idx++
		}
	}
	query := fmt.Sprintf(`
UPDATE map_markers m SET %s FROM world_maps wm
WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2
RETURNING m.id, m.label, m.x, m.y, m.entity_id, m.marker_type, m.updated_at`, strings.Join(setClauses, ", "))
	var m markerOut
	var id uuid.UUID
	var entityID *uuid.UUID
	var updatedAt time.Time
	err := s.pool.QueryRow(r.Context(), query, args...).Scan(&id, &m.Label, &m.X, &m.Y, &entityID, &m.MarkerType, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "marker not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update marker")
		return
	}
	m.MarkerID = id.String()
	if entityID != nil {
		eid := entityID.String()
		m.EntityID = &eid
	}
	m.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
	writeJSON(w, http.StatusOK, map[string]any{"marker": m})
}

// ── R7 · DELETE .../markers/{marker_id} ──────────────────────────────────────
func (s *Server) deleteMarkerREST(w http.ResponseWriter, r *http.Request) {
	_, ownerID, ok := s.resolveMapRoute(w, r)
	if !ok {
		return
	}
	markerID, ok := parseUUIDParam(w, r, "marker_id")
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
DELETE FROM map_markers m USING world_maps wm
WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2`, markerID, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to remove marker")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "marker not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"removed": true})
}

// ── R8 · POST .../regions ────────────────────────────────────────────────────
func (s *Server) addRegionREST(w http.ResponseWriter, r *http.Request) {
	mapID, ownerID, ok := s.resolveMapRoute(w, r)
	if !ok {
		return
	}
	var in struct {
		Name     string      `json:"name"`
		Polygon  [][]float64 `json:"polygon"`
		EntityID string      `json:"entity_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "name is required")
		return
	}
	if !validPolygon(w, in.Polygon) {
		return
	}
	entityID, err := parseOptionalEntityID(in.EntityID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", err.Error())
		return
	}
	polygonJSON, err := json.Marshal(in.Polygon)
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid polygon")
		return
	}
	var id uuid.UUID
	var updatedAt time.Time
	err = s.pool.QueryRow(r.Context(), `
INSERT INTO map_regions(map_id, name, polygon, entity_id)
SELECT $1,$2,$3,$4 WHERE EXISTS(SELECT 1 FROM world_maps WHERE id=$1 AND owner_user_id=$5)
RETURNING id, updated_at`, mapID, name, polygonJSON, entityID, ownerID).Scan(&id, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "map not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to add region")
		return
	}
	rg := regionOut{RegionID: id.String(), Name: name, Polygon: in.Polygon, UpdatedAt: updatedAt.UTC().Format(time.RFC3339Nano)}
	if entityID != nil {
		eid := entityID.String()
		rg.EntityID = &eid
	}
	writeJSON(w, http.StatusCreated, map[string]any{"region": rg})
}

// ── R9 · PATCH .../regions/{region_id} ───────────────────────────────────────
func (s *Server) patchRegionREST(w http.ResponseWriter, r *http.Request) {
	_, ownerID, ok := s.resolveMapRoute(w, r)
	if !ok {
		return
	}
	regionID, ok := parseUUIDParam(w, r, "region_id")
	if !ok {
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	setClauses := []string{"updated_at=now()"}
	args := []any{regionID, ownerID}
	idx := 3
	if v, present := in["polygon"]; present {
		poly, perr := polygonFromAny(v)
		if perr != nil || !validPolygon(w, poly) {
			if perr != nil {
				writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", perr.Error())
			}
			return
		}
		polygonJSON, merr := json.Marshal(poly)
		if merr != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid polygon")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("polygon=$%d", idx))
		args = append(args, polygonJSON)
		idx++
	}
	if v, present := in["name"]; present {
		name, _ := v.(string)
		if strings.TrimSpace(name) == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "name cannot be empty")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("name=$%d", idx))
		args = append(args, strings.TrimSpace(name))
		idx++
	}
	if v, present := in["entity_id"]; present {
		if v == nil {
			setClauses = append(setClauses, "entity_id=NULL")
		} else {
			raw, _ := v.(string)
			eid, err := uuid.Parse(strings.TrimSpace(raw))
			if err != nil {
				writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "entity_id must be a UUID or null")
				return
			}
			setClauses = append(setClauses, fmt.Sprintf("entity_id=$%d", idx))
			args = append(args, eid)
			idx++
		}
	}
	query := fmt.Sprintf(`
UPDATE map_regions rg SET %s FROM world_maps wm
WHERE rg.id=$1 AND rg.map_id=wm.id AND wm.owner_user_id=$2
RETURNING rg.id, rg.name, rg.polygon, rg.entity_id, rg.updated_at`, strings.Join(setClauses, ", "))
	var rg regionOut
	var id uuid.UUID
	var polygonJSON []byte
	var entityID *uuid.UUID
	var updatedAt time.Time
	err := s.pool.QueryRow(r.Context(), query, args...).Scan(&id, &rg.Name, &polygonJSON, &entityID, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "region not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to update region")
		return
	}
	if err := json.Unmarshal(polygonJSON, &rg.Polygon); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read region")
		return
	}
	rg.RegionID = id.String()
	if entityID != nil {
		eid := entityID.String()
		rg.EntityID = &eid
	}
	rg.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
	writeJSON(w, http.StatusOK, map[string]any{"region": rg})
}

// ── R10 · DELETE .../regions/{region_id} ─────────────────────────────────────
func (s *Server) deleteRegionREST(w http.ResponseWriter, r *http.Request) {
	_, ownerID, ok := s.resolveMapRoute(w, r)
	if !ok {
		return
	}
	regionID, ok := parseUUIDParam(w, r, "region_id")
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
DELETE FROM map_regions rg USING world_maps wm
WHERE rg.id=$1 AND rg.map_id=wm.id AND wm.owner_user_id=$2`, regionID, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to remove region")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "region not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"removed": true})
}

// ── shared helpers ───────────────────────────────────────────────────────────

// resolveMapRoute parses world_id + map_id and gates the world by owner (the marker/region routes
// nest under a map). Returns the map id + resolved owner. The marker/region query then re-scopes to
// the owner via a JOIN so a marker on a foreign map is a uniform not-found.
func (s *Server) resolveMapRoute(w http.ResponseWriter, r *http.Request) (uuid.UUID, uuid.UUID, bool) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	return mapID, ownerID, true
}

// validPolygon enforces >=3 points, each a [x,y] pair in [0,1]. Writes a 400 and returns false on
// failure so the caller can just `if !validPolygon(...) { return }`.
func validPolygon(w http.ResponseWriter, polygon [][]float64) bool {
	if len(polygon) < 3 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "polygon needs at least 3 [x,y] points")
		return false
	}
	for _, pt := range polygon {
		if len(pt) != 2 || pt[0] < 0 || pt[0] > 1 || pt[1] < 0 || pt[1] > 1 {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "each polygon point must be [x,y] with x,y in [0,1]")
			return false
		}
	}
	return true
}

// numberFromAny extracts a float64 from a decoded JSON value (json.Number decodes to float64).
func numberFromAny(v any) (float64, bool) {
	f, ok := v.(float64)
	return f, ok
}

// polygonFromAny converts a decoded JSON `[[x,y],…]` (a []any of []any of float64) into [][]float64.
func polygonFromAny(v any) ([][]float64, error) {
	arr, ok := v.([]any)
	if !ok {
		return nil, errors.New("polygon must be an array of [x,y] points")
	}
	out := make([][]float64, 0, len(arr))
	for _, ptRaw := range arr {
		ptArr, ok := ptRaw.([]any)
		if !ok || len(ptArr) != 2 {
			return nil, errors.New("each polygon point must be [x,y]")
		}
		x, xok := ptArr[0].(float64)
		y, yok := ptArr[1].(float64)
		if !xok || !yok {
			return nil, errors.New("polygon coordinates must be numbers")
		}
		out = append(out, []float64{x, y})
	}
	return out, nil
}

// sweepMapImage removes a map's base-image object best-effort (the row is already gone, so a
// storage hiccup must never surface as a failed delete).
func (s *Server) sweepMapImage(r *http.Request, imageKey *string) {
	if imageKey != nil && *imageKey != "" && s.minio != nil {
		_ = s.minio.RemoveObject(r.Context(), mediaBucket, *imageKey, minio.RemoveObjectOptions{})
	}
}
