package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #319 — the last tool, and the one the other five were modelled on.
//
// world_update was behaviourally correct, verified live end to end:
//
//	rename + redescribe  undo_hint carried both prior values; replaying it restored
//	                     "TOOLV2 319 throwaway — world update" / "original description" exactly
//	a world with NO description, given one  hint carried description "" and replaying it put the
//	                     column back to NULL, rather than leaving the description this call added
//	no fields            "provide name and/or description to update"
//	whitespace name      "name cannot be empty"
//
// The gap was how it obtained the prior values: a SELECT issued just before the UPDATE. A
// concurrent rename landing in that window made the emitted undo_hint report a value that was no
// longer the prior one, so replaying the undo would set the world to a name it never had at that
// moment and silently revert the other edit to a third value. Worlds are single-owner, so that
// means the same user in two sessions rather than two users — narrow, but this was the last tool
// still doing read-then-write, and #315–#318 replaced exactly this shape everywhere else.
func TestWorldUpdateTakesItsPriorValuesFromTheUpdateItself(t *testing.T) {
	fn := worldUpdateBody(t)
	if !strings.Contains(fn, "FROM worlds old") || !strings.Contains(fn, "RETURNING old.name, old.description") {
		t.Fatal("the prior values no longer come from the UPDATE — a read-then-write window is " +
			"back, and a concurrent rename makes the undo hint report a value that was already stale")
	}
	if !strings.Contains(fn, "w.id=old.id AND w.id=$1 AND w.owner_user_id=$2") {
		t.Error("the self-join or the owner scope changed shape")
	}
	if strings.Contains(fn, "SELECT name, description FROM worlds") {
		t.Error("the pre-read is back alongside the self-join")
	}
}

// The refusals are what stop an empty or destructive call. Both were verified live.
func TestWorldUpdateRefusesEmptyCallsAndEmptyNames(t *testing.T) {
	fn := worldUpdateBody(t)
	if !strings.Contains(fn, "in.Name == nil && in.Description == nil") {
		t.Error("a call with no fields is accepted again")
	}
	if !strings.Contains(fn, `errors.New("name cannot be empty")`) {
		t.Error("a whitespace-only name would blank the world's name")
	}
	// Now a SHARED named error (errNoSuchWorld) — one string for every world tool, so the
	// uniform refusal is structural rather than six copies that could drift.
	if !strings.Contains(fn, "errNoSuchWorld") {
		t.Error("a foreign or missing world must return the uniform not-found")
	}
}

// The description undo has the absent-vs-null asymmetry: "" is what CLEARS it, so a world that had
// no description must replay "" rather than omitting the field, or the undo leaves the description
// this call added. Verified live on a world created without one.
func TestTheDescriptionUndoClearsWhenThereWasNone(t *testing.T) {
	fn := worldUpdateBody(t)
	if !strings.Contains(fn, `priorDescArg = ""`) {
		t.Fatal("a world that had no description does not replay an empty string, so the undo " +
			"would keep the description this update added")
	}
	if !strings.Contains(fn, "if priorDesc != nil {") || !strings.Contains(fn, "priorDescArg = *priorDesc") {
		t.Error("a world that HAD a description does not replay it")
	}
	if !strings.Contains(fn, `"description": priorDescArg`) || !strings.Contains(fn, `"name": priorName`) {
		t.Error("the undo hint no longer carries both prior values")
	}
}

func worldUpdateBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_worlds_verbs_s07.go")
	i := strings.Index(src, "func (s *Server) toolWorldUpdate")
	if i < 0 {
		t.Fatal("toolWorldUpdate is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
