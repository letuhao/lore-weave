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
	// 404 maps to the shared uniform not-accessible sentinel (no owner oracle).
	if !errors.Is(compWriteErr(http.StatusNotFound, "x"), errBookNotAccessible) {
		t.Errorf("compWriteErr(404) must be errBookNotAccessible (uniform, no oracle)")
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

