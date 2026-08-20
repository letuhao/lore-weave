package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #315 — an update with nothing to update, and a rename with no way back.
//
// world_map_update was right about the things it is careful about, all verified live:
//
//	"omitted fields are left unchanged"  a rename left image_object_key untouched
//	OCC                                  expected_version=1 against a version-3 map returned
//	                                     "map changed elsewhere: expected version 1 but current
//	                                     is 3 — re-read the map and retry", naming both versions
//	                                     and prescribing the retry, never a misleading not-found
//
// Two defects.
//
// 1. An EMPTY update bumped the version. With neither name nor image_ref the statement still ran
// `version=version+1`: measured live, a map at version 2 came back at version 3 with every field
// identical. `version` is the OCC token, so a call that changed nothing invalidated every other
// client's held version and made their next write fail with "map changed elsewhere" over a change
// that never happened. toolWorldUpdate — the world rename — already refuses this exact case.
//
// 2. A rename had NO reversal. The response carried no _meta at all, and the prior name was
// neither kept nor returned, so an agent that renamed a map could not put it back. The world
// rename sibling has emitted an undo hint since S-07, and this file's own header calls the map
// writes REVERSIBLE.
func TestAnUpdateThatChangesNothingIsRefused(t *testing.T) {
	fn := mapUpdateBody(t)
	if !strings.Contains(fn, "if in.Name == nil && in.ImageRef == nil {") {
		t.Fatal("an update with no fields is accepted again — it runs version=version+1 and " +
			"consumes an OCC generation, so other clients get a spurious conflict for a change " +
			"that never happened")
	}
	guard := strings.Index(fn, "if in.Name == nil && in.ImageRef == nil {")
	bump := strings.Index(fn, `"version=m.version+1"`)
	if bump < 0 {
		t.Fatal("the version bump literal is gone; this ordering check is looking at nothing")
	}
	if guard > bump {
		t.Error("the refusal comes after the version bump is assembled — it must return before " +
			"any statement is built")
	}
}

// The prior values must come from the UPDATE itself. A read-then-write would leave a window in
// which the values reported as "prior" already belonged to someone else's edit.
func TestThePriorStateComesFromTheUpdateNotASecondRead(t *testing.T) {
	fn := mapUpdateBody(t)
	if !strings.Contains(fn, "FROM world_maps old") {
		t.Fatal("the self-join to the pre-update row is gone")
	}
	if !strings.Contains(fn, "RETURNING m.id, m.world_id, m.name, m.image_object_key, m.version, old.name, old.image_object_key") {
		t.Error("the statement no longer returns both the new and the prior state")
	}
	if !strings.Contains(fn, "m.id=old.id AND m.id=$1 AND m.owner_user_id=$2") {
		t.Error("the self-join or the owner scope changed shape")
	}
	// The OCC predicate has to be qualified once the statement has two aliases, or it becomes
	// ambiguous and the whole tool fails at the database.
	if !strings.Contains(fn, `" AND m.version="`) {
		t.Error("the expected_version predicate is not qualified to the updated alias")
	}
	// So does the version bump on the SET side. This one shipped unqualified, passed every Go
	// test, and only a LIVE call surfaced it: Postgres rejected the statement with `column
	// reference "version" is ambiguous`, and the tool answered "failed to update map" for every
	// rename. A static guard is why it cannot come back.
	if !strings.Contains(fn, `"version=m.version+1"`) {
		t.Error("the version bump is not qualified to the updated alias — with world_maps joined " +
			"twice, an unqualified `version` is ambiguous and Postgres rejects the whole UPDATE")
	}
}

func TestTheRenameCarriesItsOwnUndo(t *testing.T) {
	fn := mapUpdateBody(t)
	if !strings.Contains(fn, `undoResult("world_map_update"`) {
		t.Fatal("a rename emits no undo hint, so the prior name is gone the moment it is replaced")
	}
	for _, field := range []string{`"map_id"`, `"name": priorName`, `"image_ref"`, `"expected_version"`} {
		if !strings.Contains(fn, field) {
			t.Errorf("the undo hint omits %s", field)
		}
	}
}

// image_ref must always be present — "" is what clears a base image on replay. Omitting it for a
// map that had none would leave the NEW image in place and make the undo a partial one, which is
// worse than no undo because the caller believes the map was restored.
func TestTheUndoAlwaysCarriesImageRefIncludingEmpty(t *testing.T) {
	fn := mapUpdateBody(t)
	if !strings.Contains(fn, "if priorImageKey != nil {") || !strings.Contains(fn, `undoArgs["image_ref"] = ""`) {
		t.Error("image_ref is not always set — a map that had no base image would replay without " +
			"clearing the one the update added")
	}
}

// The undo is version-gated on purpose: on a tool that carries an OCC token, an undo that blindly
// overwrites a third party's later edit is precisely what the token exists to prevent.
func TestTheUndoIsGatedOnTheVersionItProduced(t *testing.T) {
	fn := mapUpdateBody(t)
	if !strings.Contains(fn, `"expected_version": d.Version`) {
		t.Error("the undo hint is not gated on the version this call produced — replaying it " +
			"would clobber any edit that landed in between instead of refusing")
	}
}

func mapUpdateBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapUpdate(")
	if i < 0 {
		t.Fatal("toolWorldMapUpdate is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
