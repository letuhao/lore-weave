package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #311 — world_map_get is correct, and this is the guard that keeps it correct.
//
// Everything the description promises was verified live, field by field, on a map built for the
// purpose:
//
//	map      map_id / world_id / name / version, plus image_object_key AND image_url after a real
//	         78-byte PNG upload — and the image_url was FETCHED: HTTP 200, 78 bytes, byte-identical
//	         to what went in. A returned link that nobody tried is not a verified link.
//	markers  label, x, y, marker_type, updated_at, entity_id
//	regions  name, polygon — round-tripped exactly ([[0.1,0.1],[0.4,0.1],[0.4,0.4]] in and out)
//	scoping  the same map_id read as a different user returns the uniform "map not found"
//	         (owner-scoped, no existence oracle); a malformed id "map_id must be a UUID"
//
// "all its markers + regions" was measured rather than assumed: 30 markers and 13 regions on one
// map returned 30 and 13, matching map_markers/map_regions exactly. There is no cap, which is the
// property most likely to be "optimised" into a silent truncation later — this loop has already
// found that defect twice elsewhere.
//
// Two control checks that did NOT become findings. world_maps.world_id is ON DELETE CASCADE, so
// deleting a world cannot leave an orphaned map that world_map_list would never surface. And a
// marker accepts an entity_id for a glossary entity that does not exist, reported back verbatim —
// that is the documented SOFT cross-service link, not a dangling-reference bug.
func TestMapGetReadsEveryMarkerAndRegion(t *testing.T) {
	fn := mapGetBody(t)
	for _, q := range []string{"FROM map_markers WHERE map_id=$1", "FROM map_regions WHERE map_id=$1"} {
		i := strings.Index(fn, q)
		if i < 0 {
			t.Fatalf("the child query %q is gone", q)
		}
		// The statement ends at the closing backquote of the raw string.
		stmt := fn[i:]
		if j := strings.Index(stmt, "`"); j > 0 {
			stmt = stmt[:j]
		}
		if strings.Contains(strings.ToUpper(stmt), "LIMIT") {
			t.Errorf("%q now has a LIMIT — the tool says it returns ALL markers + regions, and a "+
				"capped read here is invisible to the caller (no truncated flag, no next cursor)", q)
		}
		if !strings.Contains(stmt, "ORDER BY created_at") {
			t.Errorf("%q lost its ORDER BY — pin order would vary between identical reads", q)
		}
	}
}

// The partial-read guard is the reason a transient database error cannot present a map with its
// pins silently missing. It was already right; this keeps it that way.
func TestAReadFailureIsAToolErrorNotAnEmptyMap(t *testing.T) {
	fn := mapGetBody(t)
	for _, want := range []string{
		`errors.New("failed to read markers")`,
		`errors.New("failed to read regions")`,
	} {
		if strings.Count(fn, want) < 3 {
			t.Errorf("%s appears fewer than 3 times — the query, the row scan and rows.Err() must "+
				"EACH fail the tool; skipping any one of them returns a map whose pins were "+
				"dropped, presented as authoritative", want)
		}
	}
	if !strings.Contains(fn, "mrows.Err()") || !strings.Contains(fn, "rrows.Err()") {
		t.Error("an iteration error is no longer checked — a partial result would be returned as complete")
	}
}

// Empty slices, not nil: markers/regions must serialise as [] so a caller can iterate without a
// null check, and so "no pins" is distinguishable from "field missing".
func TestEmptyCollectionsSerialiseAsLists(t *testing.T) {
	fn := mapGetBody(t)
	if !strings.Contains(fn, "Markers: []markerOut{}") || !strings.Contains(fn, "Regions: []regionOut{}") {
		t.Error("markers/regions are no longer initialised to empty slices — a map with no pins " +
			"would serialise them as null")
	}
}

// Owner scoping lives in the SQL, not in a separate pre-check that a later edit could bypass.
func TestMapGetIsOwnerScopedInTheQueryItself(t *testing.T) {
	fn := mapGetBody(t)
	if !strings.Contains(fn, "FROM world_maps WHERE id=$1 AND owner_user_id=$2") {
		t.Error("the map read is no longer owner-scoped in the query")
	}
	if !strings.Contains(fn, `errors.New("map not found")`) {
		t.Error("a foreign or missing map must return the uniform not-found, never a distinguishable error")
	}
}

func mapGetBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapGet")
	if i < 0 {
		t.Fatal("toolWorldMapGet is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
