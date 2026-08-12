package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #313 — a tool that called itself an undo and prescribed a reversal that lost data.
//
// world_map_remove_marker's mechanics were already right: the DELETE joins world_maps and filters
// owner_user_id, so a foreign or missing marker removes 0 rows and returns the uniform "marker not
// found" with no cross-owner existence oracle, and a malformed id returns "marker_id must be a
// UUID".
//
// The reversal was not. The description said: "Undoes world_map_add_marker (re-add it with the
// same label + coords to restore)." add_marker also accepts entity_id and marker_type. Measured
// live, following that recipe exactly:
//
//	before   {label Ironhold, x .25, y .75, marker_type "city", entity_id ...beef0}
//	remove   {"removed": true}   — and NO _meta on the response at all
//	restore  add_marker(label Ironhold, x .25, y .75)   ← what the description says
//	after    {label Ironhold, x .25, y .75, marker_type null, entity_id null}
//
// The glossary link and the marker kind were gone, and unrecoverable: the row was deleted and
// those values had never been returned. An agent doing precisely what the tool told it to do
// destroyed the link between a pin and the entity it represents.
//
// world_update, in the sibling file, already captures prior values and emits undoResult. Same
// shape here.
func TestRemoveMarkerReturnsEverythingNeededToRestoreIt(t *testing.T) {
	fn := removeMarkerBody(t)
	if !strings.Contains(fn, "RETURNING m.map_id, m.label, m.x, m.y, m.entity_id, m.marker_type") {
		t.Fatal("the delete no longer RETURNs the marker's state — once the row is gone the " +
			"entity link and marker type cannot be recovered from anywhere")
	}
	if !strings.Contains(fn, `undoResult("world_map_add_marker"`) {
		t.Error("no undo hint is emitted, so the caller has nothing to replay")
	}
	for _, field := range []string{`"map_id"`, `"label"`, `"x"`, `"y"`, `"entity_id"`, `"marker_type"`} {
		if !strings.Contains(fn, field) {
			t.Errorf("the undo hint omits %s — replaying it would restore a DIFFERENT marker "+
				"from the one that was removed", field)
		}
	}
}

// add_marker parses entity_id as a UUID and rejects a malformed one. Emitting an empty string for
// a marker that had no entity would make the undo hint fail on replay — an undo that errors is
// worse than none, because the caller believes it has one.
func TestOptionalFieldsAreOmittedRatherThanBlank(t *testing.T) {
	fn := removeMarkerBody(t)
	if !strings.Contains(fn, "if entityID != nil {") || !strings.Contains(fn, `undoArgs["entity_id"]`) {
		t.Error("entity_id is not conditionally added; a nil entity would be replayed as an " +
			"empty or null value that add_marker's UUID parse rejects")
	}
	if !strings.Contains(fn, `markerType != nil && *markerType != ""`) {
		t.Error("marker_type is not conditionally added")
	}
}

// The description is what an agent follows. It must not prescribe the lossy recipe again.
func TestTheDescriptionNoLongerPrescribesALossyRestore(t *testing.T) {
	src := mustReadFile(t, "mcp_maps.go")
	if strings.Contains(src, "re-add it with the same label + coords to restore") {
		t.Error("the description tells the agent to restore a marker from label + coords alone, " +
			"which measurably drops entity_id and marker_type")
	}
	if !strings.Contains(src, "undo_hint carries the removed marker's full state") {
		t.Error("the description does not point at the undo_hint, so an agent has no reason to " +
			"look for it")
	}
}

// Ownership must stay in the DELETE itself. A RETURNING clause makes it tempting to read first and
// delete after, which would open a window and a second query to get wrong.
func TestOwnershipStaysInTheDeleteStatement(t *testing.T) {
	fn := removeMarkerBody(t)
	if !strings.Contains(fn, "m.map_id=wm.id AND wm.owner_user_id=$2") {
		t.Error("the delete is no longer owner-scoped through world_maps")
	}
	if !strings.Contains(fn, `errors.New("marker not found")`) {
		t.Error("a foreign or missing marker must return the uniform not-found")
	}
	if strings.Contains(fn, "SELECT") {
		t.Error("a separate SELECT appeared — the state must come from the DELETE's RETURNING, " +
			"or a concurrent removal could return one marker's data for another's deletion")
	}
}

func removeMarkerBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapRemoveMarker")
	if i < 0 {
		t.Fatal("toolWorldMapRemoveMarker is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
