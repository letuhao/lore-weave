package api

// W10-M2 — world-map MCP tools (agent-native map authoring). A world map is a
// worldbuilder's reference map: a base image (uploaded via POST
// /internal/worlds/maps/{map_id}/image — see maps_image.go) with pins (markers) and
// regions placed at relative [0,1] coords, optionally linked to a glossary `location`
// entity (a SOFT cross-service UUID). Maps are WORLD-scoped and OWNER-scoped (worlds
// have no E0 sharing), so every tool authenticates via the envelope identity
// (mcpUserID) and filters `owner_user_id`. Writes are Tier-A DIRECT (scope=none) and
// REVERSIBLE: world_map_delete undoes a create (CASCADE-dropping markers + regions +
// best-effort blob), and world_map_remove_marker / world_map_remove_region undo the
// add_* tools. Tool names carry the `world_` prefix so ai-gateway federates them (the
// book provider's second allowed namespace, EXTRA_PREFIX_MAP).

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// mapOwnerID returns the owner of a map (via world_maps.owner_user_id) so a write
// can confirm the caller owns it. found=false when the map doesn't exist.
func (s *Server) mapOwnerID(ctx context.Context, mapID uuid.UUID) (uuid.UUID, bool, error) {
	var owner uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT owner_user_id FROM world_maps WHERE id=$1`, mapID).Scan(&owner)
	if errors.Is(err, pgx.ErrNoRows) {
		return uuid.Nil, false, nil
	}
	if err != nil {
		return uuid.Nil, false, err
	}
	return owner, true, nil
}

// requireMapOwner resolves the map + confirms the caller owns it, returning a tool
// error otherwise (uniform "map not found" — no existence oracle for a foreign map).
func (s *Server) requireMapOwner(ctx context.Context, mapID, callerID uuid.UUID) error {
	owner, found, err := s.mapOwnerID(ctx, mapID)
	if err != nil {
		return errors.New("failed to resolve map")
	}
	if !found || owner != callerID {
		return errors.New("map not found")
	}
	return nil
}

func parseOptionalEntityID(raw string) (*uuid.UUID, error) {
	if strings.TrimSpace(raw) == "" {
		return nil, nil
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		return nil, errors.New("entity_id must be a UUID")
	}
	return &id, nil
}

// ── world_map_create ─────────────────────────────────────────────────────────
type worldMapCreateIn struct {
	WorldID  string `json:"world_id" jsonschema:"the world this map belongs to (UUID; you must own it)"`
	Name     string `json:"name" jsonschema:"the map's name, e.g. 'The Northern Realms'"`
	ImageRef string `json:"image_ref,omitempty" jsonschema:"optional MinIO object key of an already-uploaded base image (the value returned by the map-image upload route); omit to attach the image later"`
}
type worldMapDetail struct {
	MapID          string  `json:"map_id"`
	WorldID        string  `json:"world_id"`
	Name           string  `json:"name"`
	ImageObjectKey *string `json:"image_object_key"`
	ImageURL       *string `json:"image_url,omitempty"`
	// Version is the map's OCC ETag (S7·2). Bumped on every rename/image PATCH; the map
	// rename route requires If-Match on it (428 absent / 412 stale). Read into every map
	// door so it is never a write-only column.
	Version int `json:"version"`
}

// withImageURL fills ImageURL from ImageObjectKey (a resolved, publicly-servable URL)
// so callers get a ready-to-render link, not just a raw storage key.
func (s *Server) withImageURL(d *worldMapDetail) {
	if d.ImageObjectKey != nil && *d.ImageObjectKey != "" {
		u := s.mediaURL(*d.ImageObjectKey)
		d.ImageURL = &u
	}
}
type worldMapCreateOut struct {
	Map worldMapDetail `json:"map"`
}

func (s *Server) toolWorldMapCreate(ctx context.Context, _ *mcp.CallToolRequest, in worldMapCreateIn) (*mcp.CallToolResult, worldMapCreateOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, worldMapCreateOut{}, errMissingIdentity
	}
	worldID, err := uuid.Parse(in.WorldID)
	if err != nil {
		return nil, worldMapCreateOut{}, errors.New("world_id must be a UUID")
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		return nil, worldMapCreateOut{}, errors.New("name is required")
	}
	// The caller must own the target world (no existence oracle otherwise).
	var worldOK bool
	if err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`, worldID, ownerID).Scan(&worldOK); err != nil {
		return nil, worldMapCreateOut{}, errors.New("failed to resolve world")
	}
	if !worldOK {
		return nil, worldMapCreateOut{}, errors.New("world not found")
	}
	imageRef := strings.TrimSpace(in.ImageRef)
	var mapID uuid.UUID
	var version int
	if err := s.pool.QueryRow(ctx, `
INSERT INTO world_maps(owner_user_id, world_id, name, image_object_key) VALUES($1,$2,$3,$4) RETURNING id, version`,
		ownerID, worldID, name, nullableString(imageRef)).Scan(&mapID, &version); err != nil {
		return nil, worldMapCreateOut{}, errors.New("failed to create map")
	}
	d := worldMapDetail{MapID: mapID.String(), WorldID: worldID.String(), Name: name, Version: version}
	if imageRef != "" {
		d.ImageObjectKey = &imageRef
		s.withImageURL(&d)
	}
	return nil, worldMapCreateOut{Map: d}, nil
}

// ── world_map_add_marker ─────────────────────────────────────────────────────
type mapAddMarkerIn struct {
	MapID      string  `json:"map_id" jsonschema:"the map to add a marker to (UUID; you must own it)"`
	Label      string  `json:"label" jsonschema:"the marker's label, e.g. 'Ironhold'"`
	X          float64 `json:"x" jsonschema:"horizontal position on the base image, 0.0 (left) to 1.0 (right)"`
	Y          float64 `json:"y" jsonschema:"vertical position, 0.0 (top) to 1.0 (bottom)"`
	EntityID   string  `json:"entity_id,omitempty" jsonschema:"optional glossary location entity id (UUID) this marker represents"`
	MarkerType string  `json:"marker_type,omitempty" jsonschema:"optional marker kind, e.g. 'city', 'landmark'"`
}
type mapAddMarkerOut struct {
	MarkerID string `json:"marker_id"`
}

func (s *Server) toolWorldMapAddMarker(ctx context.Context, _ *mcp.CallToolRequest, in mapAddMarkerIn) (*mcp.CallToolResult, mapAddMarkerOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapAddMarkerOut{}, errMissingIdentity
	}
	mapID, err := uuid.Parse(in.MapID)
	if err != nil {
		return nil, mapAddMarkerOut{}, errors.New("map_id must be a UUID")
	}
	label := strings.TrimSpace(in.Label)
	if label == "" {
		return nil, mapAddMarkerOut{}, errors.New("label is required")
	}
	if in.X < 0 || in.X > 1 || in.Y < 0 || in.Y > 1 {
		return nil, mapAddMarkerOut{}, errors.New("x and y must be relative coords in [0,1]")
	}
	entityID, err := parseOptionalEntityID(in.EntityID)
	if err != nil {
		return nil, mapAddMarkerOut{}, err
	}
	if err := s.requireMapOwner(ctx, mapID, ownerID); err != nil {
		return nil, mapAddMarkerOut{}, err
	}
	var markerID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
INSERT INTO map_markers(map_id, entity_id, label, x, y, marker_type)
VALUES($1,$2,$3,$4,$5,$6) RETURNING id`,
		mapID, entityID, label, in.X, in.Y, nullableString(in.MarkerType)).Scan(&markerID); err != nil {
		return nil, mapAddMarkerOut{}, errors.New("failed to add marker")
	}
	return nil, mapAddMarkerOut{MarkerID: markerID.String()}, nil
}

// ── world_map_add_region ─────────────────────────────────────────────────────
type mapAddRegionIn struct {
	MapID    string      `json:"map_id" jsonschema:"the map to add a region to (UUID; you must own it)"`
	Name     string      `json:"name" jsonschema:"the region's name, e.g. 'The Shattered Coast'"`
	Polygon  [][]float64 `json:"polygon" jsonschema:"the region outline as an array of [x,y] relative points (each 0.0-1.0); at least 3 points"`
	EntityID string      `json:"entity_id,omitempty" jsonschema:"optional glossary location entity id (UUID) this region represents"`
}
type mapAddRegionOut struct {
	RegionID string `json:"region_id"`
}

func (s *Server) toolWorldMapAddRegion(ctx context.Context, _ *mcp.CallToolRequest, in mapAddRegionIn) (*mcp.CallToolResult, mapAddRegionOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapAddRegionOut{}, errMissingIdentity
	}
	mapID, err := uuid.Parse(in.MapID)
	if err != nil {
		return nil, mapAddRegionOut{}, errors.New("map_id must be a UUID")
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		return nil, mapAddRegionOut{}, errors.New("name is required")
	}
	if len(in.Polygon) < 3 {
		return nil, mapAddRegionOut{}, errors.New("polygon needs at least 3 [x,y] points")
	}
	for _, pt := range in.Polygon {
		if len(pt) != 2 || pt[0] < 0 || pt[0] > 1 || pt[1] < 0 || pt[1] > 1 {
			return nil, mapAddRegionOut{}, errors.New("each polygon point must be [x,y] with x,y in [0,1]")
		}
	}
	entityID, err := parseOptionalEntityID(in.EntityID)
	if err != nil {
		return nil, mapAddRegionOut{}, err
	}
	polygonJSON, err := json.Marshal(in.Polygon)
	if err != nil {
		return nil, mapAddRegionOut{}, errors.New("invalid polygon")
	}
	if err := s.requireMapOwner(ctx, mapID, ownerID); err != nil {
		return nil, mapAddRegionOut{}, err
	}
	var regionID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
INSERT INTO map_regions(map_id, name, polygon, entity_id)
VALUES($1,$2,$3,$4) RETURNING id`,
		mapID, name, polygonJSON, entityID).Scan(&regionID); err != nil {
		return nil, mapAddRegionOut{}, errors.New("failed to add region")
	}
	return nil, mapAddRegionOut{RegionID: regionID.String()}, nil
}

// ── world_map_get ────────────────────────────────────────────────────────────
type mapGetIn struct {
	MapID string `json:"map_id" jsonschema:"the map to fetch (UUID; you must own it)"`
}
type markerOut struct {
	MarkerID   string  `json:"marker_id"`
	Label      string  `json:"label"`
	X          float64 `json:"x"`
	Y          float64 `json:"y"`
	EntityID   *string `json:"entity_id"`
	MarkerType *string `json:"marker_type"`
	UpdatedAt  string  `json:"updated_at"` // S7·2 — RFC3339 "last touched"; advances on every marker PATCH
}
type regionOut struct {
	RegionID  string      `json:"region_id"`
	Name      string      `json:"name"`
	Polygon   [][]float64 `json:"polygon"`
	EntityID  *string     `json:"entity_id"`
	UpdatedAt string      `json:"updated_at"` // S7·2 — see markerOut.UpdatedAt
}
type mapGetOut struct {
	Map     worldMapDetail `json:"map"`
	Markers []markerOut    `json:"markers"`
	Regions []regionOut    `json:"regions"`
}

func (s *Server) toolWorldMapGet(ctx context.Context, _ *mcp.CallToolRequest, in mapGetIn) (*mcp.CallToolResult, mapGetOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapGetOut{}, errMissingIdentity
	}
	mapID, err := uuid.Parse(in.MapID)
	if err != nil {
		return nil, mapGetOut{}, errors.New("map_id must be a UUID")
	}
	var d worldMapDetail
	var worldID uuid.UUID
	err = s.pool.QueryRow(ctx, `
SELECT id, world_id, name, image_object_key, version FROM world_maps WHERE id=$1 AND owner_user_id=$2`,
		mapID, ownerID).Scan(&mapID, &worldID, &d.Name, &d.ImageObjectKey, &d.Version)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapGetOut{}, errors.New("map not found") // owner-scoped, no oracle
	}
	if err != nil {
		return nil, mapGetOut{}, errors.New("failed to get map")
	}
	d.MapID = mapID.String()
	d.WorldID = worldID.String()
	s.withImageURL(&d)

	out := mapGetOut{Map: d, Markers: []markerOut{}, Regions: []regionOut{}}
	// A sub-query / scan / iteration error is a TOOL FAILURE, not an empty result —
	// otherwise a transient DB error on the markers read returns a map with all its
	// pins silently dropped, presented as authoritative (the silent-success bug class).
	mrows, err := s.pool.Query(ctx, `SELECT id, label, x, y, entity_id, marker_type, updated_at FROM map_markers WHERE map_id=$1 ORDER BY created_at`, mapID)
	if err != nil {
		return nil, mapGetOut{}, errors.New("failed to read markers")
	}
	defer mrows.Close()
	for mrows.Next() {
		var id uuid.UUID
		var m markerOut
		var entityID *uuid.UUID
		var updatedAt time.Time
		if err := mrows.Scan(&id, &m.Label, &m.X, &m.Y, &entityID, &m.MarkerType, &updatedAt); err != nil {
			return nil, mapGetOut{}, errors.New("failed to read markers")
		}
		m.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
		m.MarkerID = id.String()
		if entityID != nil {
			eid := entityID.String()
			m.EntityID = &eid
		}
		out.Markers = append(out.Markers, m)
	}
	if err := mrows.Err(); err != nil {
		return nil, mapGetOut{}, errors.New("failed to read markers")
	}

	rrows, err := s.pool.Query(ctx, `SELECT id, name, polygon, entity_id, updated_at FROM map_regions WHERE map_id=$1 ORDER BY created_at`, mapID)
	if err != nil {
		return nil, mapGetOut{}, errors.New("failed to read regions")
	}
	defer rrows.Close()
	for rrows.Next() {
		var id uuid.UUID
		var r regionOut
		var polygonJSON []byte
		var entityID *uuid.UUID
		var updatedAt time.Time
		if err := rrows.Scan(&id, &r.Name, &polygonJSON, &entityID, &updatedAt); err != nil {
			return nil, mapGetOut{}, errors.New("failed to read regions")
		}
		r.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
		r.RegionID = id.String()
		if err := json.Unmarshal(polygonJSON, &r.Polygon); err != nil {
			return nil, mapGetOut{}, errors.New("failed to read regions")
		}
		if entityID != nil {
			eid := entityID.String()
			r.EntityID = &eid
		}
		out.Regions = append(out.Regions, r)
	}
	if err := rrows.Err(); err != nil {
		return nil, mapGetOut{}, errors.New("failed to read regions")
	}
	return nil, out, nil
}

// ── world_map_list ───────────────────────────────────────────────────────────
type mapListIn struct {
	WorldID string `json:"world_id" jsonschema:"the world whose maps to list (UUID; you must own it)"`
}
type mapListOut struct {
	Maps []worldMapDetail `json:"maps"`
}

func (s *Server) toolWorldMapList(ctx context.Context, _ *mcp.CallToolRequest, in mapListIn) (*mcp.CallToolResult, mapListOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapListOut{}, errMissingIdentity
	}
	worldID, err := uuid.Parse(in.WorldID)
	if err != nil {
		return nil, mapListOut{}, errors.New("world_id must be a UUID")
	}
	rows, err := s.pool.Query(ctx, `
SELECT id, world_id, name, image_object_key, version FROM world_maps
WHERE world_id=$1 AND owner_user_id=$2 ORDER BY created_at DESC`, worldID, ownerID)
	if err != nil {
		return nil, mapListOut{}, errors.New("failed to list maps")
	}
	defer rows.Close()
	maps := make([]worldMapDetail, 0)
	for rows.Next() {
		var id, wid uuid.UUID
		var d worldMapDetail
		if rows.Scan(&id, &wid, &d.Name, &d.ImageObjectKey, &d.Version) == nil {
			d.MapID = id.String()
			d.WorldID = wid.String()
			s.withImageURL(&d)
			maps = append(maps, d)
		}
	}
	return nil, mapListOut{Maps: maps}, nil
}

// ── world_map_delete ─────────────────────────────────────────────────────────
type mapDeleteIn struct {
	MapID string `json:"map_id" jsonschema:"the map to delete (UUID; you must own it). CASCADE-removes its markers + regions."`
}
type mapDeleteOut struct {
	Deleted bool `json:"deleted"`
}

func (s *Server) toolWorldMapDelete(ctx context.Context, _ *mcp.CallToolRequest, in mapDeleteIn) (*mcp.CallToolResult, mapDeleteOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapDeleteOut{}, errMissingIdentity
	}
	mapID, err := uuid.Parse(in.MapID)
	if err != nil {
		return nil, mapDeleteOut{}, errors.New("map_id must be a UUID")
	}
	// One owner-scoped read confirms ownership AND grabs the image key for blob
	// cleanup — a foreign/missing map returns the uniform "map not found" (no oracle).
	var imageKey *string
	err = s.pool.QueryRow(ctx, `SELECT image_object_key FROM world_maps WHERE id=$1 AND owner_user_id=$2`, mapID, ownerID).Scan(&imageKey)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapDeleteOut{}, errors.New("map not found")
	}
	if err != nil {
		return nil, mapDeleteOut{}, errors.New("failed to resolve map")
	}
	// FK ON DELETE CASCADE drops markers + regions with the row.
	if _, err := s.pool.Exec(ctx, `DELETE FROM world_maps WHERE id=$1 AND owner_user_id=$2`, mapID, ownerID); err != nil {
		return nil, mapDeleteOut{}, errors.New("failed to delete map")
	}
	// Best-effort blob cleanup: the row is already gone, so a storage hiccup must NOT
	// fail the delete (a stray object is swept, never surfaced as a tool error).
	if imageKey != nil && *imageKey != "" && s.minio != nil {
		_ = s.minio.RemoveObject(ctx, mediaBucket, *imageKey, minio.RemoveObjectOptions{})
	}
	return nil, mapDeleteOut{Deleted: true}, nil
}

// ── world_map_remove_marker / world_map_remove_region ─────────────────────────
type mapRemoveMarkerIn struct {
	MarkerID string `json:"marker_id" jsonschema:"the marker to remove (UUID; on a map you own)"`
}
type mapRemoveRegionIn struct {
	RegionID string `json:"region_id" jsonschema:"the region to remove (UUID; on a map you own)"`
}
type mapRemoveOut struct {
	Removed bool `json:"removed"`
}

func (s *Server) toolWorldMapRemoveMarker(ctx context.Context, _ *mcp.CallToolRequest, in mapRemoveMarkerIn) (*mcp.CallToolResult, mapRemoveOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapRemoveOut{}, errMissingIdentity
	}
	markerID, err := uuid.Parse(in.MarkerID)
	if err != nil {
		return nil, mapRemoveOut{}, errors.New("marker_id must be a UUID")
	}
	// Owner-scoped via a JOIN to world_maps.owner_user_id — a foreign/missing marker
	// deletes 0 rows → uniform "marker not found" (no cross-owner existence oracle).
	tag, err := s.pool.Exec(ctx, `
DELETE FROM map_markers m USING world_maps wm
WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2`, markerID, ownerID)
	if err != nil {
		return nil, mapRemoveOut{}, errors.New("failed to remove marker")
	}
	if tag.RowsAffected() == 0 {
		return nil, mapRemoveOut{}, errors.New("marker not found")
	}
	return nil, mapRemoveOut{Removed: true}, nil
}

func (s *Server) toolWorldMapRemoveRegion(ctx context.Context, _ *mcp.CallToolRequest, in mapRemoveRegionIn) (*mcp.CallToolResult, mapRemoveOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapRemoveOut{}, errMissingIdentity
	}
	regionID, err := uuid.Parse(in.RegionID)
	if err != nil {
		return nil, mapRemoveOut{}, errors.New("region_id must be a UUID")
	}
	tag, err := s.pool.Exec(ctx, `
DELETE FROM map_regions rg USING world_maps wm
WHERE rg.id=$1 AND rg.map_id=wm.id AND wm.owner_user_id=$2`, regionID, ownerID)
	if err != nil {
		return nil, mapRemoveOut{}, errors.New("failed to remove region")
	}
	if tag.RowsAffected() == 0 {
		return nil, mapRemoveOut{}, errors.New("region not found")
	}
	return nil, mapRemoveOut{Removed: true}, nil
}

// ── world_map_update ─────────────────────────────────────────────────────────
// S7·2 — the NET-NEW UPDATE capability. UPDATE existed at NO layer before this;
// MCP-first governs new agentic logic, so the agent gets a sibling for each PATCH
// route so it can move a pin it placed wrong (instead of remove+add, which churns
// the marker_id and strands on disconnect). Numeric/text fields are POINTERS so a
// relabel-only call does NOT send x=0,y=0 and teleport the pin to (0,0) — the
// pointer rule (spec §4.2). Owner-gated via requireMapOwner / the world_maps JOIN;
// the SQL sets only the provided columns (mirrors patchWorld's dynamic SET).
type mapUpdateIn struct {
	MapID    string  `json:"map_id" jsonschema:"the map to update (UUID; you must own it)"`
	Name     *string `json:"name,omitempty" jsonschema:"new map name; omit to leave unchanged"`
	ImageRef *string `json:"image_ref,omitempty" jsonschema:"new base-image object key (from the upload route); omit to leave unchanged"`
}
type mapUpdateOut struct {
	Map worldMapDetail `json:"map"`
}

func (s *Server) toolWorldMapUpdate(ctx context.Context, _ *mcp.CallToolRequest, in mapUpdateIn) (*mcp.CallToolResult, mapUpdateOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapUpdateOut{}, errMissingIdentity
	}
	mapID, err := uuid.Parse(in.MapID)
	if err != nil {
		return nil, mapUpdateOut{}, errors.New("map_id must be a UUID")
	}
	setClauses := []string{"updated_at=now()", "version=version+1"}
	args := []any{mapID, ownerID}
	idx := 3
	if in.Name != nil {
		name := strings.TrimSpace(*in.Name)
		if name == "" {
			return nil, mapUpdateOut{}, errors.New("name cannot be empty")
		}
		setClauses = append(setClauses, fmt.Sprintf("name=$%d", idx))
		args = append(args, name)
		idx++
	}
	if in.ImageRef != nil {
		setClauses = append(setClauses, fmt.Sprintf("image_object_key=$%d", idx))
		args = append(args, nullableString(strings.TrimSpace(*in.ImageRef)))
		idx++
	}
	query := fmt.Sprintf(
		`UPDATE world_maps SET %s WHERE id=$1 AND owner_user_id=$2 RETURNING id, world_id, name, image_object_key, version`,
		strings.Join(setClauses, ", "))
	var d worldMapDetail
	var gotMap, gotWorld uuid.UUID
	err = s.pool.QueryRow(ctx, query, args...).Scan(&gotMap, &gotWorld, &d.Name, &d.ImageObjectKey, &d.Version)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapUpdateOut{}, errors.New("map not found") // owner-scoped, no oracle
	}
	if err != nil {
		return nil, mapUpdateOut{}, errors.New("failed to update map")
	}
	d.MapID = gotMap.String()
	d.WorldID = gotWorld.String()
	s.withImageURL(&d)
	return nil, mapUpdateOut{Map: d}, nil
}

// ── world_map_update_marker ──────────────────────────────────────────────────
type mapUpdateMarkerIn struct {
	MarkerID    string   `json:"marker_id" jsonschema:"the marker to update (UUID; on a map you own)"`
	X           *float64 `json:"x,omitempty" jsonschema:"new horizontal position 0.0-1.0; omit to leave unchanged (a drag sends the ABSOLUTE new x)"`
	Y           *float64 `json:"y,omitempty" jsonschema:"new vertical position 0.0-1.0; omit to leave unchanged"`
	Label       *string  `json:"label,omitempty" jsonschema:"new label; omit to leave unchanged"`
	EntityID    string   `json:"entity_id,omitempty" jsonschema:"rebind to this glossary/KG location entity (UUID); empty = leave unchanged unless clear_entity"`
	ClearEntity bool     `json:"clear_entity,omitempty" jsonschema:"true = unbind the entity tie (set entity_id NULL)"`
	MarkerType  *string  `json:"marker_type,omitempty" jsonschema:"new marker kind, e.g. 'city'; omit to leave unchanged"`
}
type mapUpdateMarkerOut struct {
	Marker markerOut `json:"marker"`
}

func (s *Server) toolWorldMapUpdateMarker(ctx context.Context, _ *mcp.CallToolRequest, in mapUpdateMarkerIn) (*mcp.CallToolResult, mapUpdateMarkerOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapUpdateMarkerOut{}, errMissingIdentity
	}
	markerID, err := uuid.Parse(in.MarkerID)
	if err != nil {
		return nil, mapUpdateMarkerOut{}, errors.New("marker_id must be a UUID")
	}
	setClauses := []string{"updated_at=now()"}
	args := []any{markerID, ownerID}
	idx := 3
	if in.X != nil {
		if *in.X < 0 || *in.X > 1 {
			return nil, mapUpdateMarkerOut{}, errors.New("x must be in [0,1]")
		}
		setClauses = append(setClauses, fmt.Sprintf("x=$%d", idx))
		args = append(args, *in.X)
		idx++
	}
	if in.Y != nil {
		if *in.Y < 0 || *in.Y > 1 {
			return nil, mapUpdateMarkerOut{}, errors.New("y must be in [0,1]")
		}
		setClauses = append(setClauses, fmt.Sprintf("y=$%d", idx))
		args = append(args, *in.Y)
		idx++
	}
	if in.Label != nil {
		label := strings.TrimSpace(*in.Label)
		if label == "" {
			return nil, mapUpdateMarkerOut{}, errors.New("label cannot be empty")
		}
		setClauses = append(setClauses, fmt.Sprintf("label=$%d", idx))
		args = append(args, label)
		idx++
	}
	if in.MarkerType != nil {
		setClauses = append(setClauses, fmt.Sprintf("marker_type=$%d", idx))
		args = append(args, nullableString(strings.TrimSpace(*in.MarkerType)))
		idx++
	}
	// entity: clear wins; else a non-empty id rebinds; else leave untouched (§4.4 omitted-vs-null).
	if in.ClearEntity {
		setClauses = append(setClauses, "entity_id=NULL")
	} else if strings.TrimSpace(in.EntityID) != "" {
		entityID, perr := parseOptionalEntityID(in.EntityID)
		if perr != nil {
			return nil, mapUpdateMarkerOut{}, perr
		}
		setClauses = append(setClauses, fmt.Sprintf("entity_id=$%d", idx))
		args = append(args, entityID)
		idx++
	}
	// Owner-scoped via a JOIN to world_maps.owner_user_id — a foreign/missing marker updates 0
	// rows → uniform "marker not found". Atomic single statement (no read-then-write race).
	query := fmt.Sprintf(
		`UPDATE map_markers m SET %s FROM world_maps wm
		 WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2
		 RETURNING m.id, m.label, m.x, m.y, m.entity_id, m.marker_type, m.updated_at`,
		strings.Join(setClauses, ", "))
	var mk markerOut
	var id uuid.UUID
	var entityID *uuid.UUID
	var updatedAt time.Time
	err = s.pool.QueryRow(ctx, query, args...).Scan(&id, &mk.Label, &mk.X, &mk.Y, &entityID, &mk.MarkerType, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapUpdateMarkerOut{}, errors.New("marker not found")
	}
	if err != nil {
		return nil, mapUpdateMarkerOut{}, errors.New("failed to update marker")
	}
	mk.MarkerID = id.String()
	if entityID != nil {
		eid := entityID.String()
		mk.EntityID = &eid
	}
	mk.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
	return nil, mapUpdateMarkerOut{Marker: mk}, nil
}

// ── world_map_update_region ──────────────────────────────────────────────────
type mapUpdateRegionIn struct {
	RegionID    string      `json:"region_id" jsonschema:"the region to update (UUID; on a map you own)"`
	Polygon     [][]float64 `json:"polygon,omitempty" jsonschema:"new outline as [x,y] relative points (>=3, each 0.0-1.0); omit to leave the shape unchanged"`
	Name        *string     `json:"name,omitempty" jsonschema:"new name; omit to leave unchanged"`
	EntityID    string      `json:"entity_id,omitempty" jsonschema:"rebind to this glossary/KG location entity (UUID); empty = leave unchanged unless clear_entity"`
	ClearEntity bool        `json:"clear_entity,omitempty" jsonschema:"true = unbind the entity tie (set entity_id NULL)"`
}
type mapUpdateRegionOut struct {
	Region regionOut `json:"region"`
}

func (s *Server) toolWorldMapUpdateRegion(ctx context.Context, _ *mcp.CallToolRequest, in mapUpdateRegionIn) (*mcp.CallToolResult, mapUpdateRegionOut, error) {
	ownerID, ok := mcpUserID(ctx)
	if !ok {
		return nil, mapUpdateRegionOut{}, errMissingIdentity
	}
	regionID, err := uuid.Parse(in.RegionID)
	if err != nil {
		return nil, mapUpdateRegionOut{}, errors.New("region_id must be a UUID")
	}
	setClauses := []string{"updated_at=now()"}
	args := []any{regionID, ownerID}
	idx := 3
	if in.Polygon != nil {
		if len(in.Polygon) < 3 {
			return nil, mapUpdateRegionOut{}, errors.New("polygon needs at least 3 [x,y] points")
		}
		for _, pt := range in.Polygon {
			if len(pt) != 2 || pt[0] < 0 || pt[0] > 1 || pt[1] < 0 || pt[1] > 1 {
				return nil, mapUpdateRegionOut{}, errors.New("each polygon point must be [x,y] with x,y in [0,1]")
			}
		}
		polygonJSON, merr := json.Marshal(in.Polygon)
		if merr != nil {
			return nil, mapUpdateRegionOut{}, errors.New("invalid polygon")
		}
		setClauses = append(setClauses, fmt.Sprintf("polygon=$%d", idx))
		args = append(args, polygonJSON)
		idx++
	}
	if in.Name != nil {
		name := strings.TrimSpace(*in.Name)
		if name == "" {
			return nil, mapUpdateRegionOut{}, errors.New("name cannot be empty")
		}
		setClauses = append(setClauses, fmt.Sprintf("name=$%d", idx))
		args = append(args, name)
		idx++
	}
	if in.ClearEntity {
		setClauses = append(setClauses, "entity_id=NULL")
	} else if strings.TrimSpace(in.EntityID) != "" {
		entityID, perr := parseOptionalEntityID(in.EntityID)
		if perr != nil {
			return nil, mapUpdateRegionOut{}, perr
		}
		setClauses = append(setClauses, fmt.Sprintf("entity_id=$%d", idx))
		args = append(args, entityID)
		idx++
	}
	query := fmt.Sprintf(
		`UPDATE map_regions rg SET %s FROM world_maps wm
		 WHERE rg.id=$1 AND rg.map_id=wm.id AND wm.owner_user_id=$2
		 RETURNING rg.id, rg.name, rg.polygon, rg.entity_id, rg.updated_at`,
		strings.Join(setClauses, ", "))
	var rg regionOut
	var id uuid.UUID
	var polygonJSON []byte
	var entityID *uuid.UUID
	var updatedAt time.Time
	err = s.pool.QueryRow(ctx, query, args...).Scan(&id, &rg.Name, &polygonJSON, &entityID, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapUpdateRegionOut{}, errors.New("region not found")
	}
	if err != nil {
		return nil, mapUpdateRegionOut{}, errors.New("failed to update region")
	}
	if err := json.Unmarshal(polygonJSON, &rg.Polygon); err != nil {
		return nil, mapUpdateRegionOut{}, errors.New("failed to read region")
	}
	rg.RegionID = id.String()
	if entityID != nil {
		eid := entityID.String()
		rg.EntityID = &eid
	}
	rg.UpdatedAt = updatedAt.UTC().Format(time.RFC3339Nano)
	return nil, mapUpdateRegionOut{Region: rg}, nil
}

// registerMapTools registers the W10-M2 world-map MCP tools.
func (s *Server) registerMapTools(srv *mcp.Server) {
	addTool(srv, "world_map_create",
		"Create a map in a world you own (a base image with pins + regions). Returns "+
			"the map_id; add pins with world_map_add_marker and areas with "+
			"world_map_add_region, and delete it with world_map_delete. Pass image_ref if "+
			"you already have an uploaded base-image key; otherwise the image is uploaded "+
			"afterward via the map-image upload route.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"new map", "create map", "world map"}),
		s.toolWorldMapCreate)

	addTool(srv, "world_map_add_marker",
		"Place a pin on a map you own at a relative position (x,y each 0.0-1.0), "+
			"optionally linked to a glossary location entity.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"add pin", "place marker", "map marker"}),
		s.toolWorldMapAddMarker)

	addTool(srv, "world_map_add_region",
		"Outline a region on a map you own as a polygon of relative [x,y] points, "+
			"optionally linked to a glossary location entity.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"add region", "draw area", "map region"}),
		s.toolWorldMapAddRegion)

	addTool(srv, "world_map_get",
		"Fetch one map you own with all its markers + regions (positions, labels, and "+
			"any linked location entities).",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"open map", "show map", "map detail"}),
		s.toolWorldMapGet)

	addTool(srv, "world_map_list",
		"List the maps in a world you own.",
		lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, []string{"maps", "list maps", "world maps"}),
		s.toolWorldMapList)

	addTool(srv, "world_map_delete",
		"Delete a map you own — removes the map, its base image, and all its markers + "+
			"regions. Undoes world_map_create.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"delete map", "remove map"}),
		s.toolWorldMapDelete)

	addTool(srv, "world_map_remove_marker",
		"Remove a marker from a map you own. Undoes world_map_add_marker (re-add it with "+
			"the same label + coords to restore).",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"remove pin", "delete marker"}),
		s.toolWorldMapRemoveMarker)

	addTool(srv, "world_map_remove_region",
		"Remove a region from a map you own. Undoes world_map_add_region (re-add it with "+
			"the same polygon to restore).",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"remove region", "delete area"}),
		s.toolWorldMapRemoveRegion)

	// S7·2 — the NET-NEW UPDATE tools (MCP-first parity for the update capability that
	// existed at no layer before). Fields are POINTERS so a partial update never zeroes an
	// omitted field (a label-only update must not teleport the pin to 0,0).
	addTool(srv, "world_map_update",
		"Rename a map you own or repoint its base image. Provide only the fields you want to "+
			"change (name and/or image_ref); omitted fields are left unchanged.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"rename map", "update map", "map image"}),
		s.toolWorldMapUpdate)

	addTool(srv, "world_map_update_marker",
		"Move, relabel, rebind, or retype a marker on a map you own. Pass the ABSOLUTE new x/y "+
			"to move a pin (a stable marker_id — never remove+add). Provide only the fields you "+
			"want to change; set clear_entity=true to unbind its location entity.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"move pin", "drag marker", "relabel marker", "rebind marker"}),
		s.toolWorldMapUpdateMarker)

	addTool(srv, "world_map_update_region",
		"Reshape, rename, or rebind a region on a map you own. Pass a new polygon (>=3 [x,y] "+
			"points) to reshape it; provide only the fields you want to change; set "+
			"clear_entity=true to unbind its location entity.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"reshape region", "rename region", "rebind region"}),
		s.toolWorldMapUpdateRegion)
}
