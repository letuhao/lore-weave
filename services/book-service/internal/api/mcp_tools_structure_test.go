package api

// Unit coverage for the manuscript-structure tool's pure logic (docs/specs/2026-07-22-manuscript-
// structure-tool.md). The DB + cross-service (composition internal routes) behavior is proven by the
// live cross-service smoke at VERIFY and the A/B measurement — here we pin the deterministic pieces:
// the composition-status → uniform-error mapping and the reorder-Undo prior-order snapshot.

import (
	"errors"
	"net/http"
	"strings"
	"testing"
)

func TestCompWriteErr_Mapping(t *testing.T) {
	cases := []struct {
		status int
		want   string // substring
	}{
		{0, "composition is unavailable"},                       // transport failure → retryable
		{http.StatusServiceUnavailable, "composition is unavailable"}, // 503 → retryable
		{http.StatusConflict, "EXACTLY the book's active parts"},      // 409 → fail-closed reorder
		{http.StatusInternalServerError, "failed to"},                 // anything else → generic
	}
	for _, c := range cases {
		err := compWriteErr(c.status, "create the part")
		if err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("compWriteErr(%d) = %v, want substring %q", c.status, err, c.want)
		}
	}
	// TOOLV2 LOOP #138 — 404 used to map to errBookNotAccessible on a "no owner oracle" rationale.
	// Measured live: book_structure_part_archive with an absent part_id, on a book the caller had
	// been writing all session, answered "book not accessible". Every caller of compWriteErr runs
	// AFTER the book's EDIT grant has passed, so the book is accessible by definition and there is
	// no oracle left to protect — composition's 404 is about the part or chapter it was given.
	// This is the seventh site of that false-noun class in this service.
	if !errors.Is(compWriteErr(http.StatusNotFound, "x"), errStructureTargetNotInBook) {
		t.Errorf("compWriteErr(404) must name the structure TARGET, not the book")
	}
	if errors.Is(compWriteErr(http.StatusNotFound, "x"), errBookNotAccessible) {
		t.Errorf("compWriteErr(404) blames the book again")
	}
	// The mapper cannot tell a part from a chapter, so it must say so rather than pick one and be
	// wrong half the time — and it still has to name a satisfier the caller can act on.
	if msg := errStructureTargetNotInBook.Error(); !strings.Contains(msg, "part or chapter") ||
		!strings.Contains(msg, "book_structure_read") {
		t.Errorf("the structure error must admit the ambiguity and name its satisfier: %q", msg)
	}
}

func TestActivePartIDsBySort_OnlyActive_KeepsOrder(t *testing.T) {
	parts := []structurePartInput{
		{PartID: "p1", SortOrder: 0, Active: true},
		{PartID: "p2", SortOrder: 1, Active: false}, // archived — must be dropped from the Undo order
		{PartID: "p3", SortOrder: 2, Active: true},
	}
	got := activePartIDsBySort(parts)
	if len(got) != 2 || got[0] != "p1" || got[1] != "p3" {
		t.Errorf("activePartIDsBySort = %v, want [p1 p3] (active only, order preserved)", got)
	}
}

