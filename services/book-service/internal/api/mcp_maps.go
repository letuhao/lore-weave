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
	"log/slog"
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
	// K13 (2026-07-23) — idempotency guard against the agent double-firing this Tier-A
	// create; same shape as the N6 chapter guard (mcp_tools_write.go). LIVE-PROBED:
	// two byte-identical calls made two rows. Sequential tool calls make a pre-insert
	// lookup sufficient; no DB unique, since a legitimate same-named sibling is possible.
	{
		var exID uuid.UUID
		var exVer int
		if err := s.pool.QueryRow(ctx,
			`SELECT id, version FROM world_maps WHERE world_id=$1 AND owner_user_id=$2
			   AND lower(name)=lower($3) ORDER BY id LIMIT 1`,
			worldID, ownerID, name).Scan(&exID, &exVer); err == nil {
			return nil, worldMapCreateOut{Map: worldMapDetail{
				MapID: exID.String(), WorldID: worldID.String(), Name: name, Version: exVer,
			}}, nil
		}
	}
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
	// K13 (2026-07-23) — idempotency guard against the agent double-firing this Tier-A
	// create; same shape as the N6 chapter guard (mcp_tools_write.go). LIVE-PROBED:
	// two byte-identical calls made two rows. Sequential tool calls make a pre-insert
	// lookup sufficient; no DB unique, since a legitimate same-named sibling is possible.
	// Keyed on the FULL placement (label + x + y): the same label at a different spot is a
	// legitimate second marker, so only an exact repeat is treated as a double-fire.
	{
		var exID uuid.UUID
		if err := s.pool.QueryRow(ctx,
			`SELECT id FROM map_markers WHERE map_id=$1 AND lower(label)=lower($2)
			   AND x=$3 AND y=$4 ORDER BY id LIMIT 1`,
			mapID, label, in.X, in.Y).Scan(&exID); err == nil {
			return nil, mapAddMarkerOut{MarkerID: exID.String()}, nil
		}
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
	// K13 (2026-07-23) — idempotency guard against the agent double-firing this Tier-A
	// create; same shape as the N6 chapter guard (mcp_tools_write.go). LIVE-PROBED:
	// two byte-identical calls made two rows. Sequential tool calls make a pre-insert
	// lookup sufficient; no DB unique, since a legitimate same-named sibling is possible.
	{
		var exID uuid.UUID
		if err := s.pool.QueryRow(ctx,
			`SELECT id FROM map_regions WHERE map_id=$1 AND lower(name)=lower($2)
			   ORDER BY id LIMIT 1`, mapID, name).Scan(&exID); err == nil {
			return nil, mapAddRegionOut{RegionID: exID.String()}, nil
		}
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
	// The listing query below is owner-scoped, so no map can cross a tenant boundary --
	// but WITHOUT this check a world the caller does not own answered `{"maps": []}`,
	// which is the same sentence as "your world has no maps yet". That is the
	// false-absence class this service already refuses by name four times over
	// (world_get, world_map_get, world_map_delete, world_delete all answer "not
	// found"), and it is worse through an agent than through the UI: the model
	// relays "that world has no maps" to an author whose world is full of them.
	// Owner-scoped existence check, so it is still no oracle for another account.
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`,
		worldID, ownerID).Scan(&exists); err != nil {
		return nil, mapListOut{}, errors.New("failed to list maps")
	}
	if !exists {
		return nil, mapListOut{}, errors.New("world not found")
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
		// #312: a scan error FAILS the tool. Skipping the row instead returned a shorter list
		// presented as the complete set of maps in this world -- the silent-success class that
		// toolWorldMapGet, twenty lines up in this same file, already refuses by name.
		if err := rows.Scan(&id, &wid, &d.Name, &d.ImageObjectKey, &d.Version); err != nil {
			return nil, mapListOut{}, errors.New("failed to list maps")
		}
		d.MapID = id.String()
		d.WorldID = wid.String()
		s.withImageURL(&d)
		maps = append(maps, d)
	}
	// An iteration error (a connection dropped mid-read) truncates the result set. Without this
	// check the caller is handed the prefix as if it were everything.
	if err := rows.Err(); err != nil {
		return nil, mapListOut{}, errors.New("failed to list maps")
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
	// Best-effort blob cleanup: the row is already gone, so a storage hiccup must NOT fail the
	// delete. But it must not vanish either (#310). The discarded error used to be justified with
	// "a stray object is swept" — there is no sweeper. Nothing in this service or any other
	// collects orphaned media objects, so a failure here leaked the object permanently AND
	// silently: no log, no metric, nothing an operator could act on. Measured at the time of the
	// fix: all 3 map base-images in the bucket belonged to maps that no longer exist, and the only
	// way to find that out was to list the bucket by hand. Logging the key turns a permanent
	// invisible leak into a discoverable one; see DQ-28 on whether a sweeper should exist.
	if imageKey != nil && *imageKey != "" && s.minio != nil {
		if err := s.minio.RemoveObject(ctx, mediaBucket, *imageKey, minio.RemoveObjectOptions{}); err != nil {
			slog.WarnContext(ctx, "world_map_delete: orphaned map base image (delete succeeded, blob remains)",
				"map_id", mapID.String(), "object_key", *imageKey, "error", err)
		}
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
	//
	// RETURNING the whole marker (#313), not just a row count. This tool advertises itself as the
	// undo of world_map_add_marker and prescribed the reversal in its own description: "re-add it
	// with the same label + coords to restore". Measured, that recipe is LOSSY — add_marker also
	// carries entity_id and marker_type, so a marker removed at
	// {label Ironhold, x .25, y .75, marker_type city, entity_id ...beef0} came back as
	// {entity_id null, marker_type null} when restored exactly as instructed. The values were not
	// recoverable either: the row was deleted and the response was {removed true} with no _meta at
	// all. So the undo hint now carries every field add_marker accepts, the same shape world_update
	// already uses for its reversal.
	var mapIDOut uuid.UUID
	var label string
	var x, y float64
	var entityID *uuid.UUID
	var markerType *string
	err = s.pool.QueryRow(ctx, `
DELETE FROM map_markers m USING world_maps wm
WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2
RETURNING m.map_id, m.label, m.x, m.y, m.entity_id, m.marker_type`,
		markerID, ownerID).Scan(&mapIDOut, &label, &x, &y, &entityID, &markerType)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapRemoveOut{}, errors.New("marker not found")
	}
	if err != nil {
		return nil, mapRemoveOut{}, errors.New("failed to remove marker")
	}
	undoArgs := map[string]any{
		"map_id": mapIDOut.String(), "label": label, "x": x, "y": y,
	}
	// Only present when set: add_marker treats both as optional, and sending an empty string for
	// entity_id would fail its UUID parse rather than restore anything.
	if entityID != nil {
		undoArgs["entity_id"] = entityID.String()
	}
	if markerType != nil && *markerType != "" {
		undoArgs["marker_type"] = *markerType
	}
	return undoResult("world_map_add_marker", undoArgs), mapRemoveOut{Removed: true}, nil
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
	// RETURNING the whole region (#314), for the reason its twin needed it (#313) and one more:
	// this tool's restore recipe was not merely lossy, it was UNEXECUTABLE. The description said
	// "re-add it with the same polygon to restore", and `name` is a REQUIRED argument of
	// world_map_add_region. Measured live, following it exactly returned
	// `required: missing properties: ["name"]` — and the removal had answered {removed true} with
	// no _meta, so the name and entity_id were gone with nowhere to read them from. The agent's
	// only remaining move would have been to invent a name for the user's region.
	var mapIDOut uuid.UUID
	var name string
	var polygonJSON []byte
	var entityID *uuid.UUID
	err = s.pool.QueryRow(ctx, `
DELETE FROM map_regions rg USING world_maps wm
WHERE rg.id=$1 AND rg.map_id=wm.id AND wm.owner_user_id=$2
RETURNING rg.map_id, rg.name, rg.polygon, rg.entity_id`,
		regionID, ownerID).Scan(&mapIDOut, &name, &polygonJSON, &entityID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, mapRemoveOut{}, errors.New("region not found")
	}
	if err != nil {
		return nil, mapRemoveOut{}, errors.New("failed to remove region")
	}
	// The polygon is stored as JSON. It must go back into the hint as the [[x,y],…] ARRAY that
	// add_region's schema expects, never as a JSON string — replaying a string would fail the
	// array validation, which is exactly the unexecutable-undo this fix exists to end.
	var polygon [][]float64
	if err := json.Unmarshal(polygonJSON, &polygon); err != nil {
		return nil, mapRemoveOut{}, errors.New("failed to remove region")
	}
	undoArgs := map[string]any{
		"map_id": mapIDOut.String(), "name": name, "polygon": polygon,
	}
	if entityID != nil {
		undoArgs["entity_id"] = entityID.String()
	}
	return undoResult("world_map_add_region", undoArgs), mapRemoveOut{Removed: true}, nil
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
	// S-07 §1 — optimistic concurrency, matching the REST PATCH's If-Match. When you read the map
	// (world_map_get) you get its `version`; pass it here and the update is REJECTED if the map
	// changed since (another rename landed). Omit to force blind last-write-wins.
	ExpectedVersion *int `json:"expected_version,omitempty" jsonschema:"the map version you last read; when set, the update is rejected (conflict) if the map changed since. Omit for last-write-wins."`
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
	// #315: refuse a call that changes nothing. Without this the statement still ran
	// `version=version+1`, so an empty update CONSUMED AN OCC GENERATION: measured live, a map at
	// version 2 came back at version 3 with every field identical, which makes every other client
	// holding version 2 fail its next write with "map changed elsewhere" over a change that never
	// happened. The world rename sibling (toolWorldUpdate) already refuses the same way.
	if in.Name == nil && in.ImageRef == nil {
		return nil, mapUpdateOut{}, errors.New("provide name and/or image_ref to update")
	}
	// `m.version+1`, NOT `version+1`: the statement joins world_maps twice, so an unqualified
	// `version` on the right-hand side is AMBIGUOUS and Postgres rejects the whole UPDATE.
	// The Go suite could not see this — it took a live call to surface "failed to update map".
	setClauses := []string{"updated_at=now()", "version=m.version+1"}
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
	// S-07 §1 — thread the OCC predicate when the caller supplied a version. Without it the write
	// is last-write-wins (unchanged behaviour); with it, a stale version matches 0 rows and is
	// disambiguated below into a "changed elsewhere" conflict (mirrors REST's 412), never a 404.
	whereVersion := ""
	if in.ExpectedVersion != nil {
		whereVersion = fmt.Sprintf(" AND version=$%d", idx)
		args = append(args, *in.ExpectedVersion)
		idx++
	}
	// The self-join to `old` returns the PRE-update row alongside the new one (the FROM side reads
	// the statement's snapshot, so it cannot see this UPDATE's own writes). That is what makes the
	// undo hint below possible WITHOUT a second query: a read-then-update would leave a window in
	// which the values reported as "prior" were already someone else's.
	query := fmt.Sprintf(
		`UPDATE world_maps m SET %s FROM world_maps old
		 WHERE m.id=old.id AND m.id=$1 AND m.owner_user_id=$2%s
		 RETURNING m.id, m.world_id, m.name, m.image_object_key, m.version, old.name, old.image_object_key`,
		strings.Join(setClauses, ", "), strings.ReplaceAll(whereVersion, " AND version=", " AND m.version="))
	var d worldMapDetail
	var gotMap, gotWorld uuid.UUID
	var priorName string
	var priorImageKey *string
	err = s.pool.QueryRow(ctx, query, args...).Scan(&gotMap, &gotWorld, &d.Name, &d.ImageObjectKey, &d.Version,
		&priorName, &priorImageKey)
	if errors.Is(err, pgx.ErrNoRows) {
		// 0 rows: either the map is gone/foreign (not found) OR — only when a version was supplied
		// — it was stale. One owner-scoped read disambiguates, so a version conflict reports the
		// CURRENT version (the agent re-reads + retries) instead of a misleading "not found".
		if in.ExpectedVersion != nil {
			var curVersion int
			rerr := s.pool.QueryRow(ctx,
				`SELECT version FROM world_maps WHERE id=$1 AND owner_user_id=$2`, mapID, ownerID).Scan(&curVersion)
			if rerr == nil {
				return nil, mapUpdateOut{}, fmt.Errorf(
					"map changed elsewhere: expected version %d but current is %d — re-read the map and retry",
					*in.ExpectedVersion, curVersion)
			}
		}
		return nil, mapUpdateOut{}, errors.New("map not found") // owner-scoped, no oracle
	}
	if err != nil {
		return nil, mapUpdateOut{}, errors.New("failed to update map")
	}
	d.MapID = gotMap.String()
	d.WorldID = gotWorld.String()
	s.withImageURL(&d)
	// Undo hint (#315): a rename had no reversal at all — the prior name was neither kept nor
	// returned, so an agent that renamed a map could not put it back. The world rename sibling has
	// emitted one since S-07. `image_ref` is always present and is "" when the map had no base
	// image, because that is what CLEARS it on replay; omitting it would leave the new image in
	// place and make the undo a partial one.
	//
	// expected_version is the version this call just produced. The undo therefore REFUSES if
	// anything else touched the map in between, rather than blind-clobbering it — on a tool that
	// carries an OCC token, an undo that silently overwrites a third party's edit is the failure
	// the token exists to prevent.
	undoArgs := map[string]any{
		"map_id": gotMap.String(), "name": priorName, "expected_version": d.Version,
	}
	if priorImageKey != nil {
		undoArgs["image_ref"] = *priorImageKey
	} else {
		undoArgs["image_ref"] = ""
	}
	return undoResult("world_map_update", undoArgs), mapUpdateOut{Map: d}, nil
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
	// #316: refuse a call with nothing to change. Without this it ran, touched updated_at and
	// reported success — measured live, an empty call moved updated_at from …606677Z to …632087Z
	// with every field identical, which the editor renders as "edited". clear_entity counts as a
	// field: unbinding an entity is a real change even though it sets nothing else.
	if in.X == nil && in.Y == nil && in.Label == nil && in.MarkerType == nil &&
		!in.ClearEntity && strings.TrimSpace(in.EntityID) == "" {
		return nil, mapUpdateMarkerOut{}, errors.New(
			"provide at least one of x, y, label, marker_type, entity_id or clear_entity to update")
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
	// `map_markers old` joined alongside so the statement also returns the PRE-update row, which is
	// what the undo hint below is built from — no second read, so no window in which the values
	// reported as "prior" are already someone else's edit. Every column is alias-qualified: with
	// the table joined twice, a bare `label`/`x`/`entity_id` would be ambiguous and Postgres would
	// reject the whole statement (the #315 lesson, which only a live call caught).
	query := fmt.Sprintf(
		`UPDATE map_markers m SET %s FROM world_maps wm, map_markers old
		 WHERE m.id=$1 AND m.id=old.id AND m.map_id=wm.id AND wm.owner_user_id=$2
		 RETURNING m.id, m.label, m.x, m.y, m.entity_id, m.marker_type, m.updated_at,
		           old.label, old.x, old.y, old.entity_id, old.marker_type`,
		strings.Join(setClauses, ", "))
	var mk markerOut
	var id uuid.UUID
	var entityID *uuid.UUID
	var updatedAt time.Time
	var priorLabel string
	var priorX, priorY float64
	var priorEntity *uuid.UUID
	var priorType *string
	err = s.pool.QueryRow(ctx, query, args...).Scan(&id, &mk.Label, &mk.X, &mk.Y, &entityID, &mk.MarkerType, &updatedAt,
		&priorLabel, &priorX, &priorY, &priorEntity, &priorType)
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
	// Undo hint (#316). This tool had none, which put the map tools in a perverse state after
	// #313: the description tells the agent to move a pin with THIS tool rather than remove+add,
	// because the marker_id stays stable — and remove_marker was the one that could be undone.
	//
	// The entity is asymmetric and is where a careless hint would corrupt the marker: replaying
	// entity_id restores a binding, but a marker that had NO entity needs clear_entity=true,
	// because an omitted entity_id means "leave unchanged" and would silently keep whatever this
	// update bound. marker_type is always sent, "" when it was unset, since that is what clears it.
	undoArgs := map[string]any{
		"marker_id": id.String(), "label": priorLabel, "x": priorX, "y": priorY,
	}
	if priorType != nil {
		undoArgs["marker_type"] = *priorType
	} else {
		undoArgs["marker_type"] = ""
	}
	if priorEntity != nil {
		undoArgs["entity_id"] = priorEntity.String()
	} else {
		undoArgs["clear_entity"] = true
	}
	return undoResult("world_map_update_marker", undoArgs), mapUpdateMarkerOut{Marker: mk}, nil
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
	// #317: refuse a call with nothing to change — same shape as #315/#316. Measured live, an
	// empty call moved updated_at from …802859Z to …81511Z with every field identical.
	if in.Polygon == nil && in.Name == nil && !in.ClearEntity && strings.TrimSpace(in.EntityID) == "" {
		return nil, mapUpdateRegionOut{}, errors.New(
			"provide at least one of polygon, name, entity_id or clear_entity to update")
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
	// `map_regions old` joined alongside so the same statement returns the PRE-update row for the
	// undo hint — no second read, hence no window in which the "prior" values are already someone
	// else's. Alias-qualified throughout: map_regions is joined twice, and an unqualified column
	// makes Postgres reject the statement, which #315 proved is invisible to the compiler and to
	// every source-reading test.
	query := fmt.Sprintf(
		`UPDATE map_regions rg SET %s FROM world_maps wm, map_regions old
		 WHERE rg.id=$1 AND rg.id=old.id AND rg.map_id=wm.id AND wm.owner_user_id=$2
		 RETURNING rg.id, rg.name, rg.polygon, rg.entity_id, rg.updated_at,
		           old.name, old.polygon, old.entity_id`,
		strings.Join(setClauses, ", "))
	var rg regionOut
	var id uuid.UUID
	var polygonJSON []byte
	var entityID *uuid.UUID
	var updatedAt time.Time
	var priorName string
	var priorPolygonJSON []byte
	var priorEntity *uuid.UUID
	err = s.pool.QueryRow(ctx, query, args...).Scan(&id, &rg.Name, &polygonJSON, &entityID, &updatedAt,
		&priorName, &priorPolygonJSON, &priorEntity)
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
	// Undo hint (#317). The polygon is DECODED back into [[x,y],…] before it goes into the hint:
	// the column is JSON, and replaying the raw bytes would send a JSON string against a schema
	// expecting an array — the same uncallable undo #314 fixed on the remove path. The entity
	// carries the same asymmetry as #316: a region that had none needs clear_entity=true, because
	// an omitted entity_id means "leave unchanged" and would keep whatever this update bound.
	var priorPolygon [][]float64
	if err := json.Unmarshal(priorPolygonJSON, &priorPolygon); err != nil {
		return nil, mapUpdateRegionOut{}, errors.New("failed to read region")
	}
	undoArgs := map[string]any{
		"region_id": id.String(), "name": priorName, "polygon": priorPolygon,
	}
	if priorEntity != nil {
		undoArgs["entity_id"] = priorEntity.String()
	} else {
		undoArgs["clear_entity"] = true
	}
	return undoResult("world_map_update_region", undoArgs), mapUpdateRegionOut{Region: rg}, nil
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
		"Remove a marker from a map you own. Undoes world_map_add_marker — the result's "+
			"undo_hint carries the removed marker's full state (label, x, y, and its entity_id / "+
			"marker_type when set), so replay that to restore it. Re-adding from the label and "+
			"coords alone drops the entity link and the marker type.",
		lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"remove pin", "delete marker"}),
		s.toolWorldMapRemoveMarker)

	addTool(srv, "world_map_remove_region",
		"Remove a region from a map you own. Undoes world_map_add_region — the result's "+
			"undo_hint carries the removed region's full state (name, polygon, and its entity_id "+
			"when set), so replay that to restore it. The polygon alone is not enough: "+
			"world_map_add_region requires a name.",
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
