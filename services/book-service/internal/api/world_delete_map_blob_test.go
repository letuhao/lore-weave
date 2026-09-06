package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #311 — found while proving world_map_get; the defect lives in world_delete.
//
// world_maps.world_id is ON DELETE CASCADE, so deleting a world drops its maps IN THE DATABASE.
// Their base images live in object storage and are removed by application code — code a cascade
// never runs. Measured end to end on a throwaway world:
//
//	base.png in the bucket ............. PRESENT
//	world_delete ....................... {"deleted": true}
//	world_map_get on the cascaded map .. "map not found"  (row really is gone)
//	base.png in the bucket ............. STILL PRESENT
//
// This is not the failed-RemoveObject case #310 covered — no removal was even attempted. It is the
// mechanism behind the orphans measured there: all 3 map base-images in the bucket belonged to
// maps that no longer existed.
//
// The keys must be collected INSIDE the transaction, while the rows still exist, and removed only
// AFTER the commit — a rolled-back delete (a foreign or missing world) must not delete anybody's
// blobs.
func TestWorldDeleteRemovesItsMapsBaseImages(t *testing.T) {
	fn := deleteWorldBody(t)
	if !strings.Contains(fn, "SELECT image_object_key FROM world_maps") {
		t.Fatal("the world delete no longer collects its maps' image keys — every map image in a " +
			"deleted world is orphaned in storage, because the FK cascade drops the rows without " +
			"running any application cleanup")
	}
	if !strings.Contains(fn, "s.minio.RemoveObject(ctx, mediaBucket, k,") {
		t.Error("the collected keys are never removed from storage")
	}
	if strings.Contains(fn, "_ = s.minio.RemoveObject(") {
		t.Error("the removal error is discarded — same invisible leak #310 fixed elsewhere")
	}
	if !strings.Contains(fn, `"object_key", k`) {
		t.Error("a failed removal must log the key, or the leak cannot be cleaned up later")
	}
}

// Ordering is the correctness of this fix. Collect before the DELETE (the rows are the only place
// the keys exist) and remove after the Commit (a rollback must not touch storage).
func TestBlobKeysAreCollectedInTxAndRemovedAfterCommit(t *testing.T) {
	fn := deleteWorldBody(t)
	collect := strings.Index(fn, "SELECT image_object_key FROM world_maps")
	del := strings.Index(fn, "DELETE FROM worlds WHERE id=$1")
	commit := strings.Index(fn, "tx.Commit(ctx)")
	remove := strings.Index(fn, "s.minio.RemoveObject(ctx, mediaBucket, k,")
	if collect < 0 || del < 0 || commit < 0 || remove < 0 {
		t.Fatal("one of collect / delete / commit / remove is missing")
	}
	if !(collect < del) {
		t.Error("the keys are read after the rows are deleted — the read would return nothing")
	}
	if !(commit < remove) {
		t.Error("blobs are removed before the commit — a rolled-back delete would destroy the " +
			"images of a world that still exists")
	}
}

// A miss must remain a no-op. RowsAffected()==0 returns before the commit, so the removal loop is
// unreachable for a world the caller does not own.
func TestAMissedWorldDeleteTouchesNoStorage(t *testing.T) {
	fn := deleteWorldBody(t)
	miss := strings.Index(fn, "return false, nil // not found / not owned")
	remove := strings.Index(fn, "s.minio.RemoveObject(ctx, mediaBucket, k,")
	if miss < 0 {
		t.Fatal("the not-found early return is gone")
	}
	if !(miss < remove) {
		t.Error("the not-found return no longer precedes the storage removal — a delete that " +
			"matched no world could still delete blobs")
	}
}

func deleteWorldBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_worlds_verbs_s07.go")
	i := strings.Index(src, "func (s *Server) deleteWorldWithBiblePurge")
	if i < 0 {
		t.Fatal("deleteWorldWithBiblePurge is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
