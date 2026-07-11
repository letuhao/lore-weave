package api

// WS-0.3 — the six-writer hygiene lock.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.2.
//
// The red team's P0-1 on spec v1: it updated ONE of SIX writers of
// published_revision_id, and never even named worker-infra — a SECOND service that
// writes book-service's `chapters` table directly. The failure mode is nasty and
// delayed: a writer that pins published_revision_id but not kg_indexed_revision_id
// produces a chapter that is INVISIBLE to the re-keyed reparse sweeper forever, so its
// scenes are never parsed, extraction_leaves has no scene to key on, and KG extraction
// silently degrades. Worse, the WS-0.2 migration backfill masks it on the EXISTING
// corpus — so a smoke test on today's data passes while every FUTURE import is broken.
//
// A code-reading review cannot hold that invariant. This test can. It is the
// "one name for one concept" drift lock the repo keeps re-learning.
//
// TWO rules, and the second is as important as the first:
//
//	1. A statement that SETS published_revision_id to a VALUE (publish) MUST also set
//	   kg_indexed_revision_id — else the chapter never reaches the graph.
//
//	2. A statement that SETS published_revision_id = NULL (unpublish) MUST NOT touch
//	   kg_indexed_revision_id — spec §3.8 + acceptance #9: unpublish is an EDITORIAL
//	   act, and the user's explicit "add to knowledge" request must SURVIVE it.
//	   Retraction is kg_exclude's job, not unpublish's. (See RUN-STATE D-R5: the
//	   implementation plan said the opposite; the spec won.)

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// Every service that writes book-service's `chapters` table. worker-infra is here
// because it reaches into book-service's DB directly — the blast radius the v1 spec
// missed entirely.
var kgWriterRoots = []string{
	filepath.Join("..", "..", "..", "book-service"),
	filepath.Join("..", "..", "..", "worker-infra"),
}

var (
	// published_revision_id = $N  → a publish (pins a real revision)
	rePublishWrite = regexp.MustCompile(`published_revision_id\s*=\s*\$\d+`)
	// published_revision_id = NULL → an unpublish
	reUnpublishWrite = regexp.MustCompile(`(?i)published_revision_id\s*=\s*NULL`)
)

// isWriteContext reports whether the match at index i sits in a SET clause (a WRITE)
// rather than a WHERE clause (a READ predicate).
//
// This distinction is load-bearing: reparse_sweeper.go legitimately READS
// `WHERE ... published_revision_id = $2` as its concurrent-republish guard. Treating
// that as an unfixed writer would be a false positive — and a hygiene test that cries
// wolf gets weakened or deleted, which is how these locks die.
//
// Heuristic: look back a bounded window and compare the nearest preceding SET vs WHERE.
func isWriteContext(src string, i int) bool {
	start := i - 400
	if start < 0 {
		start = 0
	}
	seg := strings.ToUpper(src[start:i])
	return strings.LastIndex(seg, "SET ") > strings.LastIndex(seg, "WHERE")
}

// enclosingSetClause returns the SET clause containing index i — from the nearest
// preceding "SET" to the statement's WHERE / end-of-literal. This is the region that
// must (or must not) mention kg_indexed_revision_id.
func enclosingSetClause(src string, i int) string {
	start := i - 400
	if start < 0 {
		start = 0
	}
	if s := strings.LastIndex(strings.ToUpper(src[start:i]), "SET "); s != -1 {
		start += s
	}
	rest := src[i:]
	end := len(rest)
	if j := strings.IndexAny(rest, "`;"); j != -1 {
		end = j
	}
	if j := strings.Index(strings.ToUpper(rest[:end]), "WHERE"); j != -1 {
		end = j
	}
	return src[start : i+end]
}

func TestEveryPublishWriterAlsoSetsTheKGPointer(t *testing.T) {
	checked := 0
	unpublishChecked := 0

	for _, root := range kgWriterRoots {
		err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if info.IsDir() || !strings.HasSuffix(path, ".go") {
				return nil
			}
			if strings.HasSuffix(path, "_test.go") {
				return nil
			}
			// internal/migrate is migration code, not a runtime writer: the CM1 backfill
			// deliberately pins published_revision_id and leaves the KG pointer to the
			// separate, marker-gated kgIndexedBackfillSQL that runs after it (WS-0.2).
			// It has its own live tests (kg_indexed_db_test.go).
			if strings.Contains(filepath.ToSlash(path), "/internal/migrate/") {
				return nil
			}

			raw, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			src := string(raw)

			// Rule 1 — a publish must carry the KG pointer.
			for _, loc := range rePublishWrite.FindAllStringIndex(src, -1) {
				if !isWriteContext(src, loc[0]) {
					continue // a WHERE predicate (e.g. the sweeper's concurrent guard), not a write
				}
				stmt := enclosingSetClause(src, loc[0])
				if !strings.Contains(stmt, "kg_indexed_revision_id") {
					t.Errorf(
						"%s: a writer pins published_revision_id but NOT kg_indexed_revision_id.\n"+
							"That chapter will be invisible to the re-keyed reparse sweeper forever:\n"+
							"scenes never parsed → no scene_id for extraction_leaves → the chapter\n"+
							"silently never enters the knowledge graph. The WS-0.2 backfill masks this\n"+
							"on existing data, so it would ship green.\n"+
							"Add kg_indexed_revision_id to this statement (spec §3.2).\n"+
							"  statement: %s",
						path, strings.Join(strings.Fields(stmt), " "),
					)
					continue
				}
				checked++
			}

			// Rule 2 — an unpublish must NOT touch the KG pointer (spec §3.8, acceptance #9).
			for _, loc := range reUnpublishWrite.FindAllStringIndex(src, -1) {
				if !isWriteContext(src, loc[0]) {
					continue
				}
				stmt := enclosingSetClause(src, loc[0])
				if strings.Contains(stmt, "kg_indexed_revision_id") {
					t.Errorf(
						"%s: an UNPUBLISH also clears kg_indexed_revision_id.\n"+
							"Unpublish is an EDITORIAL act — 'publish' now means only 'this is the\n"+
							"canonical version'. A user who clicked 'Add to knowledge' and later\n"+
							"unpublished for editorial reasons must NOT silently lose their index\n"+
							"request (spec §3.8, acceptance #9). Retraction is kg_exclude's job.\n"+
							"  statement: %s",
						path, strings.Join(strings.Fields(stmt), " "),
					)
					continue
				}
				unpublishChecked++
			}
			return nil
		})
		if err != nil {
			t.Fatalf("walk %s: %v", root, err)
		}
	}

	// Guard against the test silently passing because it found nothing (a refactor
	// moves the SQL, the regex stops matching, and this test becomes a no-op that
	// reports green forever — the exact class it exists to prevent).
	if checked < 6 {
		t.Fatalf("expected >= 6 publish writers of published_revision_id (spec §2.1 names "+
			"exactly six: mcp_actions, server, parse, import, worker-infra import_processor, "+
			"worker-infra import_processor_pdf), found %d — the scan is not reaching them, "+
			"so this hygiene lock is not actually guarding anything", checked)
	}
	if unpublishChecked < 2 {
		t.Fatalf("expected >= 2 unpublish writers (mcp_actions + server), found %d — the "+
			"unpublish half of the lock is not guarding anything", unpublishChecked)
	}
	t.Logf("hygiene OK: %d publish writers all set kg_indexed_revision_id; "+
		"%d unpublish writers all leave it alone", checked, unpublishChecked)
}
