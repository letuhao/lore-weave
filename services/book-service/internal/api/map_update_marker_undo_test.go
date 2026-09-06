package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #316 — the tool you are told to prefer was the one you could not undo.
//
// world_map_update_marker was already right about the hard parts, verified live: it is a single
// atomic statement joined to world_maps on owner_user_id (uniform "marker not found"), the numeric
// fields are POINTERS so a relabel-only call does not send x=0,y=0 and teleport the pin to the
// corner, x/y are range-checked, and clear_entity genuinely unbinds (entity_id came back null).
//
// Two defects, both shared with #315.
//
// 1. An empty call succeeded. With nothing to set the statement still ran and touched updated_at —
// measured live, …606677Z became …632087Z with every field identical, which the editor renders as
// "edited".
//
// 2. A move had NO reversal: _meta was null, so the pin's prior position (0.25, 0.75) and label
// ("Ironhold") were gone the moment they were replaced. That is perverse in context — the tool's
// own description says to move a pin with THIS tool rather than remove+add "(a stable marker_id —
// never remove+add)", and after #313 remove_marker WAS the one that could be undone. The correct
// tool was the unrecoverable one.
func TestUpdateMarkerRefusesACallWithNothingToChange(t *testing.T) {
	fn := updateMarkerBody(t)
	if !strings.Contains(fn, "in.X == nil && in.Y == nil && in.Label == nil && in.MarkerType == nil") {
		t.Fatal("an update with no fields is accepted again — it touches updated_at and reports " +
			"success for a change that did not happen")
	}
	// clear_entity is a real change even though it sets nothing else. Leaving it out of the guard
	// would break the one call whose whole purpose is to unbind an entity.
	if !strings.Contains(fn, "!in.ClearEntity") {
		t.Error("clear_entity is not counted as a field, so unbinding an entity would be refused " +
			"as an empty update")
	}
	if !strings.Contains(fn, `strings.TrimSpace(in.EntityID) == ""`) {
		t.Error("a rebind-only call would be refused as empty — entity_id is a plain string here, " +
			"so it must be tested for emptiness, not for nil")
	}
}

// The prior state must come from the UPDATE itself, and every column must be alias-qualified:
// map_markers is joined twice, and #315 proved that an unqualified reference makes Postgres reject
// the whole statement — invisible to the compiler and to every source-reading test.
func TestUpdateMarkerReturnsThePriorRowFromTheSameStatement(t *testing.T) {
	fn := updateMarkerBody(t)
	if !strings.Contains(fn, "FROM world_maps wm, map_markers old") {
		t.Fatal("the self-join to the pre-update marker is gone")
	}
	if !strings.Contains(fn, "m.id=$1 AND m.id=old.id AND m.map_id=wm.id AND wm.owner_user_id=$2") {
		t.Error("the join or the owner scope changed shape")
	}
	if !strings.Contains(fn, "old.label, old.x, old.y, old.entity_id, old.marker_type") {
		t.Error("the statement no longer returns the prior state")
	}
	for _, bare := range []string{"RETURNING id,", "RETURNING label,", " label=label", " x=x"} {
		if strings.Contains(fn, bare) {
			t.Errorf("an unqualified column reference (%q) appeared — with map_markers joined "+
				"twice Postgres rejects the statement as ambiguous, and no Go test can see it", bare)
		}
	}
}

// The entity is where a careless undo corrupts the marker rather than restoring it.
func TestTheUndoClearsAnEntityThatWasNotThereBefore(t *testing.T) {
	fn := updateMarkerBody(t)
	if !strings.Contains(fn, "if priorEntity != nil {") || !strings.Contains(fn, `undoArgs["clear_entity"] = true`) {
		t.Fatal("a marker that had NO entity does not replay clear_entity=true — an omitted " +
			"entity_id means 'leave unchanged', so the undo would silently keep whatever binding " +
			"this update introduced")
	}
	if !strings.Contains(fn, `undoArgs["entity_id"] = priorEntity.String()`) {
		t.Error("a marker that HAD an entity does not replay it, so the binding is lost")
	}
	// Sending both would be contradictory, and clear_entity wins in the handler — the undo would
	// always unbind.
	both := strings.Contains(fn, `undoArgs["clear_entity"] = true`) && strings.Contains(fn, `undoArgs["entity_id"]`)
	if both && !strings.Contains(fn, "} else {") {
		t.Error("clear_entity and entity_id are not mutually exclusive in the hint; clear_entity " +
			"wins in the handler, so every undo would unbind the entity")
	}
}

// marker_type must always be present: "" is what clears it, and omitting it leaves whatever the
// update set — a partial undo that reports success.
func TestTheUndoAlwaysCarriesMarkerTypeIncludingEmpty(t *testing.T) {
	fn := updateMarkerBody(t)
	if !strings.Contains(fn, `undoArgs["marker_type"] = ""`) {
		t.Error("marker_type is not sent when the marker had none, so the undo would leave the " +
			"type this update added")
	}
}

// Position and label are the whole point of a move, and x/y must survive as numbers.
func TestTheUndoCarriesThePriorPositionAndLabel(t *testing.T) {
	fn := updateMarkerBody(t)
	for _, want := range []string{`"label": priorLabel`, `"x": priorX`, `"y": priorY`, `"marker_id"`} {
		if !strings.Contains(fn, want) {
			t.Errorf("the undo hint omits %s — a moved pin could not be put back", want)
		}
	}
	if !strings.Contains(fn, `undoResult("world_map_update_marker"`) {
		t.Error("the undo replays the wrong tool")
	}
}

func updateMarkerBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapUpdateMarker")
	if i < 0 {
		t.Fatal("toolWorldMapUpdateMarker is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
