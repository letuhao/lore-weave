package api

import "testing"

// DQ-T44 (owner 2026-08-28): "a `deleted=true` (soft-deleted) FILTER on each family's EXISTING
// list/search tool. No new tools." — built here for the glossary-entity family, which is the one
// D-RESTORE-WITH-NO-WAY-TO-SEE-WHAT-IS-RESTORABLE confirmed live.
//
//	THE INVARIANT. `deleted=false` is the search that always shipped; `deleted=true` returns ONLY
//	soft-deleted rows, so glossary_entity_restore can be handed an id.
//
// The ruling names the half that is easy to miss: "its query to stop excluding soft-deleted
// rows". The predicate lives in exactly one function for that reason — four tiers share it, and a
// fix applied to three would be indistinguishable from a fix applied to all four.

func TestDeletedClauseIsTheDefaultWhenNotAsked(t *testing.T) {
	// The default MUST be byte-for-byte the predicate that shipped. A search that started
	// returning deleted entities to ordinary callers would be a data leak wearing a fix's
	// clothes.
	if got := deletedClause(false); got != "e.deleted_at IS NULL" {
		t.Fatalf("default clause changed: %q", got)
	}
}

func TestDeletedClauseSelectsONLYTheRecycleBin(t *testing.T) {
	// Not "also deleted" — ONLY deleted. The caller asking for the bin is looking for an id to
	// restore, and mixing live rows in makes them pick through the wrong list.
	if got := deletedClause(true); got != "e.deleted_at IS NOT NULL" {
		t.Fatalf("deleted clause is not a recycle-bin filter: %q", got)
	}
}

func TestTheTwoClausesArePartitions(t *testing.T) {
	// ANTI-VACUITY. If both branches ever returned the same string the flag would be inert and
	// every test above would still pass.
	if deletedClause(true) == deletedClause(false) {
		t.Fatal("deletedClause ignores its argument — the filter is inert")
	}
}
