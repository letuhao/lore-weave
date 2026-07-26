package tasks

// SC11-amendment Phase 0 — the worker-infra half of the DRIFT-LOCK. No DB, so it can never skip
// into a false green.
//
// THE CENSUS WAS WRONG TWICE, AND THIS IS WHY THE TEST EXISTS.
//
// The spec asserted `scenes.source_scene_id` is written in THREE places. The DB test found a FOURTH
// (book-service had four re-parse emit sites, not two — I had missed the IX-3 sweeper and PUBLISH).
// Then `/review-impl` found a FIFTH and a SIXTH, both here:
//
//   worker-infra import (HTML/txt) and import_pdf BOTH insert scenes WITH a parser-recovered
//   `source_scene_id`, and NEITHER emitted anything. They are not covered by the IX-12 write-back,
//   because that only fills NULLs (`WHERE ... source_scene_id IS NULL`) — so a scene that arrives
//   ALREADY ANCHORED is never touched by it.
//
// That is the ROUND-TRIP case: a user exports their book and re-imports it. Every scene arrives
// linked. The write-back skips all of them. Nothing announces the links. Composition's mirror
// renders the ENTIRE re-imported book as unwritten — a confident, wrong, whole-book answer, which
// is the exact failure Phase 0 exists to prevent.
//
// So: **every file in this package that writes `source_scene_id` must also emit
// `chapter.scenes_linked`.** A seventh writer added without its event turns this red immediately,
// instead of shipping a book that renders wrong.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEverySourceSceneIDWriterEmitsScenesLinked(t *testing.T) {
	files, err := filepath.Glob("*.go")
	if err != nil {
		t.Fatalf("glob: %v", err)
	}

	writers := 0
	for _, f := range files {
		if strings.HasSuffix(f, "_test.go") {
			continue
		}
		b, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		s := string(b)

		// A file WRITES the link if it INSERTs or UPDATEs source_scene_id.
		insertsLink := strings.Contains(s, "INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id")
		updatesLink := strings.Contains(s, "UPDATE scenes SET source_scene_id")
		if !insertsLink && !updatesLink {
			continue
		}
		writers++

		if !strings.Contains(s, "emitScenesLinkedTx(") {
			t.Errorf(
				"%s writes scenes.source_scene_id but never calls emitScenesLinkedTx.\n"+
					"A link that no event announces is a link composition's mirror never learns about — "+
					"the book renders as unwritten.\n"+
					"Emit chapter.scenes_linked in the SAME tx as the write (INV-O12).", f)
		}
	}

	// Pin the census. If this moves, someone added or removed a writer — and they have to think
	// about the mirror. (import_processor.go writes it twice: the import INSERT and the IX-12
	// write-back UPDATE. import_processor_pdf.go writes it once.)
	if writers != 2 {
		t.Errorf("found %d file(s) in worker-infra writing source_scene_id, expected 2 "+
			"(import_processor.go, import_processor_pdf.go). A writer was added or removed — "+
			"does it emit chapter.scenes_linked?", writers)
	}
}
