package api

// W10-M2 — world-map MCP tools (agent-native map authoring). A world map is a
// worldbuilder's reference map: a base image (uploaded separately) with pins
// (markers) and regions placed at relative [0,1] coords, optionally linked to a
// glossary `location` entity (a SOFT cross-service UUID). Maps are WORLD-scoped and
// OWNER-scoped (worlds have no E0 sharing), so every tool authenticates via the
// envelope identity (mcpUserID) and filters `owner_user_id`. Writes are Tier-A
// DIRECT + reversible (delete the map/marker/region), scope=none — like the world
// tools. Tool names carry the `world_` prefix so ai-gateway federates them (the
// book provider's second allowed namespace, EXTRA_PREFIX_MAP).

import (
	"context"
	"encoding/json"
	"errors"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
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
	WorldID string `json:"world_id" jsonschema:"the world this map belongs to (UUID; you must own it)"`
	Name    string `json:"name" jsonschema:"the map's name, e.g. 'The Northern Realms'"`
}
type worldMapDetail struct {
	MapID          string  `json:"map_id"`
	WorldID        string  `json:"world_id"`
	Name           string  `json:"name"`
	ImageObjectKey *string `json:"image_object_key"`
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
	var mapID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
INSERT INTO world_maps(owner_user_id, world_id, name) VALUES($1,$2,$3) RETURNING id`,
		ownerID, worldID, name).Scan(&mapID); err != nil {
		return nil, worldMapCreateOut{}, errors.New("failed to create map")
	}
	return nil, worldMapCreateOut{Map: worldMapDetail{
		MapID: mapID.String(), WorldID: worldID.String(), Name: name,
	}}, nil
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
}
type regionOut struct {
	RegionID string      `json:"region_id"`
	Name     string      `json:"name"`
	Polygon  [][]float64 `json:"polygon"`
	EntityID *string     `json:"entity_id"`
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
SELECT id, world_id, name, image_object_key FROM world_maps WHERE id=$1 AND owner_user_id=$2`,
		mapID, ownerID).Scan(&mapID, &worldID, &d.Name, &d.ImageObjectKey)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapGetOut{}, errors.New("map not found") // owner-scoped, no oracle
	}
	if err != nil {
		return nil, mapGetOut{}, errors.New("failed to get map")
	}
	d.MapID = mapID.String()
	d.WorldID = worldID.String()

	out := mapGetOut{Map: d, Markers: []markerOut{}, Regions: []regionOut{}}
	// A sub-query / scan / iteration error is a TOOL FAILURE, not an empty result —
	// otherwise a transient DB error on the markers read returns a map with all its
	// pins silently dropped, presented as authoritative (the silent-success bug class).
	mrows, err := s.pool.Query(ctx, `SELECT id, label, x, y, entity_id, marker_type FROM map_markers WHERE map_id=$1 ORDER BY created_at`, mapID)
	if err != nil {
		return nil, mapGetOut{}, errors.New("failed to read markers")
	}
	defer mrows.Close()
	for mrows.Next() {
		var id uuid.UUID
		var m markerOut
		var entityID *uuid.UUID
		if err := mrows.Scan(&id, &m.Label, &m.X, &m.Y, &entityID, &m.MarkerType); err != nil {
			return nil, mapGetOut{}, errors.New("failed to read markers")
		}
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

	rrows, err := s.pool.Query(ctx, `SELECT id, name, polygon, entity_id FROM map_regions WHERE map_id=$1 ORDER BY created_at`, mapID)
	if err != nil {
		return nil, mapGetOut{}, errors.New("failed to read regions")
	}
	defer rrows.Close()
	for rrows.Next() {
		var id uuid.UUID
		var r regionOut
		var polygonJSON []byte
		var entityID *uuid.UUID
		if err := rrows.Scan(&id, &r.Name, &polygonJSON, &entityID); err != nil {
			return nil, mapGetOut{}, errors.New("failed to read regions")
		}
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
SELECT id, world_id, name, image_object_key FROM world_maps
WHERE world_id=$1 AND owner_user_id=$2 ORDER BY created_at DESC`, worldID, ownerID)
	if err != nil {
		return nil, mapListOut{}, errors.New("failed to list maps")
	}
	defer rows.Close()
	maps := make([]worldMapDetail, 0)
	for rows.Next() {
		var id, wid uuid.UUID
		var d worldMapDetail
		if rows.Scan(&id, &wid, &d.Name, &d.ImageObjectKey) == nil {
			d.MapID = id.String()
			d.WorldID = wid.String()
			maps = append(maps, d)
		}
	}
	return nil, mapListOut{Maps: maps}, nil
}

// registerMapTools registers the W10-M2 world-map MCP tools.
func (s *Server) registerMapTools(srv *mcp.Server) {
	addTool(srv, "world_map_create",
		"Create a map in a world you own (a base image with pins + regions). Returns "+
			"the map_id; add pins with world_map_add_marker and areas with "+
			"world_map_add_region. The base image is uploaded separately.",
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
}
