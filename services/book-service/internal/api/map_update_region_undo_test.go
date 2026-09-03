package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #317 — the last of the map update tools, with the same two holes as #315 and #316.
//
// Correct already, verified live: the polygon is validated (at least 3 points, each [x,y] within
// [0,1]) before anything is written, the statement is a single atomic UPDATE joined to world_maps
// on owner_user_id (uniform "region not found", malformed ids rejected), and omitted fields are
// genuinely left alone.
//
// Defects: an empty call succeeded and moved updated_at (…802859Z → …81511Z with every field
// identical), and a rename+reshape returned _meta null, so the region's prior name and outline were
// gone the moment they were replaced.
//
// This one combines both earlier hazards: #314's polygon-as-JSON (replaying the raw bytes sends a
// string where the schema wants an array) and #316's entity asymmetry (a region that had no entity
// cannot be restored by omitting entity_id, because omitted means "leave unchanged").
func TestUpdateRegionRefusesACallWithNothingToChange(t *testing.T) {
	fn := updateRegionBody(t)
	if !strings.Contains(fn, "in.Polygon == nil && in.Name == nil && !in.ClearEntity") {
		t.Fatal("an update with no fields is accepted again — it touches updated_at and reports " +
			"success for a change that did not happen")
	}
	if !strings.Contains(fn, `strings.TrimSpace(in.EntityID) == ""`) {
		t.Error("a rebind-only call would be refused as empty — entity_id is a plain string here")
	}
}

func TestUpdateRegionReturnsThePriorRowFromTheSameStatement(t *testing.T) {
	fn := updateRegionBody(t)
	if !strings.Contains(fn, "FROM world_maps wm, map_regions old") {
		t.Fatal("the self-join to the pre-update region is gone")
	}
	if !strings.Contains(fn, "rg.id=$1 AND rg.id=old.id AND rg.map_id=wm.id AND wm.owner_user_id=$2") {
		t.Error("the join or the owner scope changed shape")
	}
	if !strings.Contains(fn, "old.name, old.polygon, old.entity_id") {
		t.Error("the statement no longer returns the prior state")
	}
	for _, bare := range []string{"RETURNING id,", "RETURNING name,", " name=name", " polygon=polygon"} {
		if strings.Contains(fn, bare) {
			t.Errorf("an unqualified column reference (%q) appeared — with map_regions joined "+
				"twice Postgres rejects the statement as ambiguous, and no Go test can see it", bare)
		}
	}
}

// #314's lesson on this tool's own write path: the polygon column is JSON, and the schema expects
// an array of [x,y] pairs.
func TestThePriorPolygonIsDecodedBeforeItGoesIntoTheHint(t *testing.T) {
	fn := updateRegionBody(t)
	if !strings.Contains(fn, "var priorPolygon [][]float64") ||
		!strings.Contains(fn, "json.Unmarshal(priorPolygonJSON, &priorPolygon)") {
		t.Error("the prior polygon is not decoded — replaying raw JSON bytes would send a string " +
			"where add/update expects an array, and the undo would fail validation")
	}
	if strings.Contains(fn, `"polygon": priorPolygonJSON`) {
		t.Error("the raw JSON bytes are put straight into the hint")
	}
}

// #316's lesson: omitted entity_id means "leave unchanged", so restoring a region that had NO
// entity requires the explicit clear.
func TestTheRegionUndoClearsAnEntityThatWasNotThereBefore(t *testing.T) {
	fn := updateRegionBody(t)
	if !strings.Contains(fn, "if priorEntity != nil {") || !strings.Contains(fn, `undoArgs["clear_entity"] = true`) {
		t.Fatal("a region that had NO entity does not replay clear_entity=true, so the undo would " +
			"silently keep whatever binding this update introduced")
	}
	if !strings.Contains(fn, `undoArgs["entity_id"] = priorEntity.String()`) {
		t.Error("a region that HAD an entity does not replay it, so the binding is lost")
	}
}

func TestTheRegionUndoCarriesNameAndOutline(t *testing.T) {
	fn := updateRegionBody(t)
	for _, want := range []string{`"region_id"`, `"name": priorName`, `"polygon": priorPolygon`} {
		if !strings.Contains(fn, want) {
			t.Errorf("the undo hint omits %s", want)
		}
	}
	if !strings.Contains(fn, `undoResult("world_map_update_region"`) {
		t.Error("the undo replays the wrong tool")
	}
}

// The polygon validation must stay in front of the write. It is the only thing standing between a
// malformed outline and a region the editor cannot render.
func TestThePolygonIsStillValidatedBeforeAnythingIsWritten(t *testing.T) {
	fn := updateRegionBody(t)
	for _, want := range []string{
		`errors.New("polygon needs at least 3 [x,y] points")`,
		`errors.New("each polygon point must be [x,y] with x,y in [0,1]")`,
	} {
		if !strings.Contains(fn, want) {
			t.Errorf("the polygon validation lost %q", want)
		}
	}
	validate := strings.Index(fn, "polygon needs at least 3")
	write := strings.Index(fn, "UPDATE map_regions rg SET")
	if validate < 0 || write < 0 || validate > write {
		t.Error("the polygon is validated after the statement is assembled")
	}
}

func updateRegionBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapUpdateRegion")
	if i < 0 {
		t.Fatal("toolWorldMapUpdateRegion is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
