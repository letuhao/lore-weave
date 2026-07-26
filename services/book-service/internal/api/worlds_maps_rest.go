package api

// W10-M8 — the REST surface the maps FE canvas reads. The map DATA already exists (world_maps +
// map_markers + map_regions tables, the world_map_* MCP tools, MinIO base images); the agent can
// build a map, but the browser canvas had no first-party route to LOAD one. These two owner-scoped
// GETs close that: list a world's maps for the picker, then fetch one map with all its pins +
// regions + a ready-to-render image URL for the canvas. Read-only — every mutation stays on the
// Tier-W world_map_* tools (create/add_marker/add_region/…), so this adds no new write surface.
//
// Owner-scoped exactly like listWorldBooks: requireWorldOwner gates the world, and the map query
// re-filters on world_id + owner_user_id so a map from another world (or another user) is a plain
// 404 (anti-oracle — the same posture the world_map_get tool takes).

import (
	"errors"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// listWorldMaps — GET /v1/worlds/{world_id}/maps. Owner-scoped list of a world's maps
// (id, name, image_url) for the canvas's map picker.
func (s *Server) listWorldMaps(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	ctx := r.Context()
	rows, err := s.pool.Query(ctx, `
SELECT id, world_id, name, image_object_key, version
FROM world_maps
WHERE world_id=$1 AND owner_user_id=$2
ORDER BY created_at`, worldID, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list maps")
		return
	}
	defer rows.Close()
	items := make([]worldMapDetail, 0)
	for rows.Next() {
		var mapID, wID uuid.UUID
		var d worldMapDetail
		// A scan error is a FAILURE, not a silently-skipped row: dropping a map on a transient
		// error would present an incomplete list as authoritative (the silent-success bug class,
		// and the pgx discarded-scan-zeroes-row trap this repo has hit).
		if err := rows.Scan(&mapID, &wID, &d.Name, &d.ImageObjectKey, &d.Version); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read maps")
			return
		}
		d.MapID = mapID.String()
		d.WorldID = wID.String()
		s.withImageURL(&d)
		items = append(items, d)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read maps")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": len(items)})
}

// getWorldMapREST — GET /v1/worlds/{world_id}/maps/{map_id}. Owner-scoped map detail with all
// markers + regions + a render-ready image URL, the payload the canvas draws. Mirrors the
// world_map_get MCP tool's assembly (and its strict "a sub-read error is a tool failure, never a
// silently-empty result" posture), but re-scoped to the world_id in the path.
func (s *Server) getWorldMapREST(w http.ResponseWriter, r *http.Request) {
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
	ctx := r.Context()
	var d worldMapDetail
	var gotWorld uuid.UUID
	err := s.pool.QueryRow(ctx, `
SELECT id, world_id, name, image_object_key, version
FROM world_maps
WHERE id=$1 AND world_id=$2 AND owner_user_id=$3`,
		mapID, worldID, ownerID).Scan(&mapID, &gotWorld, &d.Name, &d.ImageObjectKey, &d.Version)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "map not found") // owner+world scoped, no oracle
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to get map")
		return
	}
	d.MapID = mapID.String()
	d.WorldID = gotWorld.String()
	s.withImageURL(&d)

	markers := make([]markerOut, 0)
	mrows, err := s.pool.Query(ctx, `SELECT id, label, x, y, entity_id, marker_type, updated_at FROM map_markers WHERE map_id=$1 ORDER BY created_at`, mapID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read markers")
		return
	}
	defer mrows.Close()
	for mrows.Next() {
		var id uuid.UUID
		var m markerOut
		var entityID *uuid.UUID
		var updatedAt time.Time
		if err := mrows.Scan(&id, &m.Label, &m.X, &m.Y, &entityID, &m.MarkerType, &updatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read markers")
			return
		}
		m.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
		m.MarkerID = id.String()
		if entityID != nil {
			eid := entityID.String()
			m.EntityID = &eid
		}
		markers = append(markers, m)
	}
	if err := mrows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read markers")
		return
	}

	regions := make([]regionOut, 0)
	rrows, err := s.pool.Query(ctx, `SELECT id, name, polygon, entity_id, updated_at FROM map_regions WHERE map_id=$1 ORDER BY created_at`, mapID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read regions")
		return
	}
	defer rrows.Close()
	for rrows.Next() {
		var id uuid.UUID
		var rg regionOut
		var entityID *uuid.UUID
		var updatedAt time.Time
		if err := rrows.Scan(&id, &rg.Name, &rg.Polygon, &entityID, &updatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read regions")
			return
		}
		rg.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
		rg.RegionID = id.String()
		if entityID != nil {
			eid := entityID.String()
			rg.EntityID = &eid
		}
		regions = append(regions, rg)
	}
	if err := rrows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to read regions")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"map": d, "markers": markers, "regions": regions})
}
