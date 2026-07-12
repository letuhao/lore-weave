package api

// SC11-amendment Phase 0 — the DRIFT-LOCK. No DB, so it can never be skipped into a false green.
//
// WHY THIS EXISTS, and it is not hypothetical: writing Phase 0 I did a census of the writers of
// `scenes.source_scene_id`, concluded there were THREE, and patched two `emitScenesReparsed` call
// sites. There were FOUR — I had missed `reparse_sweeper.go` (the IX-3 sweeper, which re-links a
// book in the BACKGROUND with no user action at all) and `server.go` (PUBLISH — the single most
// common re-parse there is). Only the DB test caught it.
//
// A re-parse re-resolves every scene's anchor, so ANY code path that emits `chapter.scenes_reparsed`
// has, by construction, possibly moved the spec back-links — and must therefore also emit
// `chapter.scenes_linked`, or composition's mirror silently diverges from the truth it mirrors.
//
// So the invariant is mechanical: **in every file, the number of `emitScenesReparsed` call sites
// must not exceed the number of `emitScenesLinked` call sites.** A future fifth re-parse emit
// added without its link event turns this red at once, instead of shipping a book that renders as
// unwritten.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEveryScenesReparsedEmitAlsoEmitsScenesLinked(t *testing.T) {
	files, err := filepath.Glob("*.go")
	if err != nil {
		t.Fatalf("glob: %v", err)
	}

	totalReparsed, totalLinked := 0, 0
	for _, f := range files {
		if strings.HasSuffix(f, "_test.go") {
			continue
		}
		src, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		s := string(src)
		// Count CALL sites only — skip the declarations themselves.
		reparsed := strings.Count(s, "emitScenesReparsed(ctx,") + strings.Count(s, "emitScenesReparsed(r.Context(),")
		linked := strings.Count(s, "emitScenesLinked(ctx,") + strings.Count(s, "emitScenesLinked(r.Context(),")
		totalReparsed += reparsed
		totalLinked += linked

		if reparsed > linked {
			t.Errorf(
				"%s emits chapter.scenes_reparsed %d time(s) but chapter.scenes_linked only %d.\n"+
					"A re-parse re-resolves every scene's anchor, so the spec back-links may have MOVED.\n"+
					"An emit site that stays silent leaves composition's mirror believing prose that exists\n"+
					"was never written. Add emitScenesLinked in the SAME tx, under the SAME counts.changed() guard.",
				f, reparsed, linked)
		}
	}

	// The census itself, pinned. If this number moves, a writer was added or removed — and the
	// person moving it has to think about the mirror.
	if totalReparsed != 4 {
		t.Errorf("found %d emitScenesReparsed call sites, expected 4 "+
			"(kg_index, mcp_actions, reparse_sweeper, server/publish). "+
			"A writer was added or removed — does it emit chapter.scenes_linked too?", totalReparsed)
	}
	if totalLinked < totalReparsed {
		t.Fatalf("scenes_linked call sites (%d) < scenes_reparsed (%d) — a re-parse path is silent", totalLinked, totalReparsed)
	}
}
