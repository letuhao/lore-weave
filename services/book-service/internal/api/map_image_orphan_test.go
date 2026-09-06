package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #310 — "a stray object is swept" described a sweeper that does not exist.
//
// world_map_delete does everything it advertises, proven live end to end: a map created in a
// throwaway world with one marker and one region deleted cleanly ({"deleted": true}), the marker
// and region rows went with it via FK cascade (1/1 → 0/0), a re-delete and a foreign id both
// answered the uniform "map not found", a malformed id "map_id must be a UUID", and — with a real
// 78-byte PNG uploaded through the internal route — the base image was gone from the bucket after
// the delete (worlds/maps/<id>/base.png: PRESENT → REMOVED).
//
// The defect was what happens when that blob delete FAILS. The error was discarded outright, with
// a comment justifying it: "a stray object is swept, never surfaced as a tool error". There is no
// sweeper. Nothing in book-service or any other service collects orphaned media objects — the only
// sweepers here are dek_shred_sweeper and reparse_sweeper, neither of which touches storage. So a
// failure leaked the object permanently AND silently: no log, no metric, nothing an operator could
// act on.
//
// It is not hypothetical. Measured against the live bucket: all 3 map base-images present in
// storage belong to maps that no longer exist in world_maps. (The 11 rows carrying an
// image_object_key are unit-test fixtures pointing at the literal key "worlds/maps/x/base.png",
// not uploads.) The only way to discover any of it was to list the bucket by hand.
//
// Failing the delete would be wrong — the row is already gone. Logging the key is what turns a
// permanent invisible leak into a discoverable one.
func TestMapImageCleanupFailureIsNotDiscarded(t *testing.T) {
	for _, site := range []struct{ file, fn string }{
		{"mcp_maps.go", "toolWorldMapDelete"},
		{"worlds_maps_write_rest.go", "sweepMapImage"},
		{"maps_image.go", "uploadWorldMapImage"},
	} {
		src := mustReadFile(t, site.file)
		if strings.Contains(src, "_ = s.minio.RemoveObject(") {
			t.Errorf("%s: a map-image RemoveObject error is discarded again — nothing sweeps "+
				"orphaned media, so the object leaks permanently with no record", site.file)
		}
		if !strings.Contains(src, "slog.WarnContext(") {
			t.Errorf("%s: no warning is emitted when the blob cleanup fails, so the leak is "+
				"invisible to an operator", site.file)
		}
		if !strings.Contains(src, `"object_key"`) {
			t.Errorf("%s: the log does not carry object_key — a leak you cannot name is a leak "+
				"you cannot clean up", site.file)
		}
	}
}

// The failure must stay non-fatal. The row is already deleted (or, on upload, already repointed),
// so returning an error here would report a failure for work that succeeded.
func TestBlobCleanupFailureStillReturnsSuccess(t *testing.T) {
	src := mustReadFile(t, "mcp_maps.go")
	i := strings.Index(src, "func (s *Server) toolWorldMapDelete")
	if i < 0 {
		t.Fatal("toolWorldMapDelete is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	cleanup := fn[strings.Index(fn, "RemoveObject"):]
	if strings.Contains(cleanup, "return nil, mapDeleteOut{}, errors.New") {
		t.Error("a failed blob cleanup now fails the whole delete — the map row is already gone, " +
			"so the caller would be told the delete failed when it succeeded")
	}
	if !strings.Contains(fn, "mapDeleteOut{Deleted: true}") {
		t.Error("the success return is gone")
	}
}

// The claim that justified the discard must not come back. A comment asserting a mechanism that
// does not exist is how this survived review in the first place.
func TestNoCodeClaimsAnOrphanSweeperExists(t *testing.T) {
	for _, f := range []string{"mcp_maps.go", "worlds_maps_write_rest.go", "maps_image.go"} {
		if strings.Contains(mustReadFile(t, f), "is swept, never surfaced") {
			t.Errorf("%s: the 'a stray object is swept' justification is back, and there is still "+
				"no sweeper to do it", f)
		}
	}
}
