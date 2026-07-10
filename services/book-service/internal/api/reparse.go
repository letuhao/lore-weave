package api

import (
	"context"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// reparse.go — 26 IX-2/IX-4/IX-5 (Build 26 Phase B, B2). The index writer.
//
// The .index/ (scenes) is honestly-derived: on every publish (and on the IX-3
// sweep) the chapter's pinned body is re-parsed and the scenes rows are
// hash-preservingly upserted. This file is the pure-ish core (a parse client
// call + one in-Tx upsert); the two publish sites (server.go, mcp_actions.go)
// and the sweeper (reparse_sweeper.go) wire it. Nothing here reads or writes a
// composition table — the index points AT the spec, the parser writes only the
// index (§ "What re-parse never does").

// reparseCounts are the IX-4 per-chapter delta counts, returned in the publish
// response's existing envelope (additive `reparse` field) and asserted by tests:
// a re-parse reporting all-zero deltas for a CHANGED revision is a bug
// (silent-success-is-a-bug-not-environment).
type reparseCounts struct {
	Unchanged int `json:"unchanged"`
	Updated   int `json:"updated"`
	Inserted  int `json:"inserted"`
	Deleted   int `json:"deleted"`
	// ParseVersion is the IX-4 CHAPTER SCALAR (MAX(parse_version) over the
	// chapter's active rows after the upsert) — the one value carried by the
	// IX-10 event, the IX-9 canon-markers response, and the IX-8 manifest.
	ParseVersion int `json:"parse_version"`
}

// changed reports whether the upsert touched any row (the IX-4 bump condition).
func (c reparseCounts) changed() bool { return c.Updated+c.Inserted+c.Deleted > 0 }

// parseChapterBody re-parses one chapter's pinned/to-be-pinned Tiptap body via
// knowledge-service /internal/parse (source_format='tiptap', IX-6). Stateless,
// deterministic, NO DB — called BEFORE the publish Tx (IX-2) and never inside
// it. Returns an error the caller treats as "skip the upsert, leave the marker
// stale, let the sweeper heal" (OQ-1): a parse failure never blocks publish.
func (s *Server) parseChapterBody(ctx context.Context, body, lang string) (*parsedTree, error) {
	tree, err := s.parseClientCall(ctx, "tiptap", body, lang, "")
	if err != nil {
		return nil, err
	}
	// The SDK guarantees >=1 part >=1 chapter >=1 scene; a zero-leaf tree would
	// mean the upsert DELETEs every existing row — a destructive no-op we refuse.
	if len(flattenLeaves(tree)) == 0 {
		return nil, fmt.Errorf("parse returned zero leaves")
	}
	return tree, nil
}

// reparsePrep carries the BEFORE-Tx parse result into the publish transaction
// (IX-2). draftVersion is the chapter_drafts.draft_version the parsed body was
// read at; the publish handler re-reads it under FOR UPDATE and only trusts the
// tree when the two match (a concurrent save between the pre-read and the Tx
// makes the parse describe a stale body → skip the upsert, sweeper heals).
type reparsePrep struct {
	tree           *parsedTree
	structuralPath string
	draftVersion   int64
	ok             bool // false ⇒ parse failed OR no draft → caller skips the upsert
}

// prepareReparse reads a chapter's current draft body (+ its version, language,
// and structural_path) with NO lock and parses it via /internal/parse. Runs
// entirely before the publish Tx (IX-2). Any failure returns ok=false: the
// caller pins + publishes as usual and lets the IX-3 sweeper index the chapter
// later — a parse failure never blocks publish (OQ-1).
func (s *Server) prepareReparse(ctx context.Context, bookID, chapterID uuid.UUID) reparsePrep {
	var body string
	var draftVersion int64
	var lang string
	var structuralPath *string
	err := s.pool.QueryRow(ctx, `
SELECT d.body::text, d.draft_version, COALESCE(c.original_language,''), c.structural_path
FROM chapter_drafts d JOIN chapters c ON c.id=d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'`,
		chapterID, bookID).Scan(&body, &draftVersion, &lang, &structuralPath)
	if err != nil {
		return reparsePrep{ok: false}
	}
	sp := ""
	if structuralPath != nil {
		sp = *structuralPath
	}
	tree, perr := s.parseChapterBody(ctx, body, lang)
	if perr != nil {
		return reparsePrep{structuralPath: sp, draftVersion: draftVersion, ok: false}
	}
	return reparsePrep{tree: tree, structuralPath: sp, draftVersion: draftVersion, ok: true}
}

// flattenLeaves collects every scene across the tree in document order. A
// single-chapter tiptap re-parse yields one part / one chapter, but flattening
// is defensive against a multi-part tree.
func flattenLeaves(tree *parsedTree) []parsedScene {
	var out []parsedScene
	for _, p := range tree.Parts {
		for _, c := range p.Chapters {
			out = append(out, c.Scenes...)
		}
	}
	return out
}

// rewriteScenePath rewrites a leaf's path PREFIX from the chapter's
// structural_path (F9), keeping the parser's own trailing "scene-N" segment so
// scene-splitting/path naming stays owned by loreweave_parse alone (SCOPE-4 —
// no second Go path implementation). A single-chapter re-parse produces a
// synthetic "book/part-1/chapter-1/scene-N"; this restores the chapter's true
// coordinates. When structural_path is empty (a typed-only legacy chapter never
// decomposed) there is no prefix to graft, so the parser's path is kept as-is.
func rewriteScenePath(structuralPath, scenePath string) string {
	if structuralPath == "" {
		return scenePath
	}
	leaf := scenePath
	if i := strings.LastIndex(scenePath, "/"); i >= 0 {
		leaf = scenePath[i+1:]
	}
	return structuralPath + "/" + leaf
}

// desiredSourceSceneID applies IX-5's back-link evidence rules in precedence
// order: (1) a valid `data-scene-id` anchor on the leaf's opening heading wins;
// (2) no anchor but the (chapter_id, sort_order) row already existed → keep its
// existing back-link (positional stability — a one-word edit must not sever
// every link in the chapter); (3) otherwise NULL (rendered as "anchor lost" /
// "not planned" by the union join — a visible state, never silent decay).
func desiredSourceSceneID(anchor *string, existing *uuid.UUID) *uuid.UUID {
	if anchor != nil {
		if id, err := uuid.Parse(strings.TrimSpace(*anchor)); err == nil {
			return &id // rule 1
		}
	}
	return existing // rule 2 (existing != nil) or rule 3 (existing == nil → NULL)
}

// existingScene is one active scenes row loaded for the hash-preserving compare.
type existingScene struct {
	id            uuid.UUID
	path          string
	contentHash   string
	sourceSceneID *uuid.UUID
	parseVersion  int
}

// upsertChapterScenes is the IX-4 hash-preserving upsert, keyed on
// (chapter_id, sort_order), run INSIDE the caller's transaction:
//   - identical content_hash + path + back-link  → row UNTOUCHED (id + link kept);
//   - any of those changed                        → in-place UPDATE;
//   - a sort_order beyond the new leaf count       → DELETE (the index is derived
//     and disposable, 22 SC13/D5 — a tombstoned parse leaf has no reader);
//   - a new sort_order                             → INSERT.
//
// Every touched (updated/inserted) row is stamped with a single per-chapter
// bump = MAX(existing parse_version)+1; unchanged rows keep their older stamps,
// so one chapter's rows carry mixed values by design. Returns the IX-4 delta
// counts + the chapter-scalar parse_version (MAX over active rows post-upsert).
//
// Reads all existing rows into memory and closes the cursor BEFORE issuing any
// write — pgx forbids a second operation on a tx while a result set is open.
func (s *Server) upsertChapterScenes(
	ctx context.Context,
	tx pgx.Tx,
	bookID, chapterID uuid.UUID,
	structuralPath string,
	tree *parsedTree,
) (reparseCounts, error) {
	leaves := flattenLeaves(tree)

	rows, err := tx.Query(ctx, `
SELECT id, sort_order, path, content_hash, source_scene_id, parse_version
FROM scenes WHERE chapter_id=$1 AND lifecycle_state='active'`, chapterID)
	if err != nil {
		return reparseCounts{}, fmt.Errorf("load scenes: %w", err)
	}
	existing := map[int]existingScene{}
	maxPV := 0
	for rows.Next() {
		var e existingScene
		var so int
		if scanErr := rows.Scan(&e.id, &so, &e.path, &e.contentHash, &e.sourceSceneID, &e.parseVersion); scanErr != nil {
			rows.Close()
			return reparseCounts{}, fmt.Errorf("scan scene: %w", scanErr)
		}
		existing[so] = e
		if e.parseVersion > maxPV {
			maxPV = e.parseVersion
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return reparseCounts{}, fmt.Errorf("iterate scenes: %w", err)
	}

	bump := maxPV + 1
	var c reparseCounts
	seen := make(map[int]bool, len(leaves))

	for _, leaf := range leaves {
		so := leaf.SortOrder
		seen[so] = true
		newPath := rewriteScenePath(structuralPath, leaf.Path)
		ex, ok := existing[so]
		var existingSSID *uuid.UUID
		if ok {
			existingSSID = ex.sourceSceneID
		}
		desired := desiredSourceSceneID(leaf.AnchorSceneID, existingSSID)

		if ok {
			if ex.contentHash == leaf.ContentHash && ex.path == newPath && uuidPtrEq(ex.sourceSceneID, desired) {
				c.Unchanged++
				continue
			}
			if _, err := tx.Exec(ctx, `
UPDATE scenes SET leaf_text=$2, content_hash=$3, path=$4, source_scene_id=$5,
       parse_version=$6, book_id=$7, updated_at=now()
WHERE id=$1`, ex.id, leaf.LeafText, leaf.ContentHash, newPath, uuidArg(desired), bump, bookID); err != nil {
				return reparseCounts{}, fmt.Errorf("update scene: %w", err)
			}
			c.Updated++
			continue
		}
		// New leaf. title defaults '' (22 A1 parsed-heading is not carried by the
		// SDK scene shape; import inserts it empty too — left untouched here).
		if _, err := tx.Exec(ctx, `
INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version)
VALUES($1,$2,$3,$4,$5,$6,$7,$8)`,
			chapterID, bookID, so, newPath, leaf.LeafText, leaf.ContentHash, uuidArg(desired), bump); err != nil {
			return reparseCounts{}, fmt.Errorf("insert scene: %w", err)
		}
		c.Inserted++
	}

	// Leaves beyond the new count → DELETE (hard; the index is disposable).
	for so, ex := range existing {
		if seen[so] {
			continue
		}
		if _, err := tx.Exec(ctx, `DELETE FROM scenes WHERE id=$1`, ex.id); err != nil {
			return reparseCounts{}, fmt.Errorf("delete scene: %w", err)
		}
		c.Deleted++
	}

	// RB-3: the IX-4 chapter scalar is MAX(parse_version) over ACTIVE scenes — the SAME
	// computation POST …/canon-markers uses (reconcile-by-truth-mirror-producer-predicate).
	// Assuming bump == MAX overstates it on a delete-only reparse (Deleted>0 but no
	// surviving row carries `bump`), so the event/response scalar would exceed what
	// canon-markers reports for the identical committed state. Read the truth instead.
	if err := tx.QueryRow(ctx,
		`SELECT COALESCE(MAX(parse_version),0) FROM scenes WHERE chapter_id=$1 AND lifecycle_state='active'`,
		chapterID).Scan(&c.ParseVersion); err != nil {
		return reparseCounts{}, fmt.Errorf("parse_version scalar: %w", err)
	}
	return c, nil
}

// emitScenesReparsed writes the FROZEN IX-10 outbox event in the caller's Tx
// (same transaction as the index upsert, so the event is provably ordered after
// the rows change). Schema (SCOPE-2, do not extend):
//
//	chapter.scenes_reparsed { book_id, chapter_id, published_revision_id, parse_version }
//
// where parse_version is the IX-4 chapter scalar. Consumer: knowledge's K14
// handler → book-scoped cache invalidation.
func emitScenesReparsed(ctx context.Context, tx pgx.Tx, bookID, chapterID, publishedRevID uuid.UUID, parseVersion int) error {
	return insertOutboxEvent(ctx, tx, "chapter.scenes_reparsed", chapterID, map[string]any{
		"book_id":               bookID,
		"chapter_id":            chapterID,
		"published_revision_id": publishedRevID,
		"parse_version":         parseVersion,
	})
}

// uuidArg maps a *uuid.UUID to a bind arg: nil → SQL NULL, else the value
// (mirrors sceneSourceSceneIDArg — a typed-nil pointer is never bound raw).
func uuidArg(p *uuid.UUID) any {
	if p == nil {
		return nil
	}
	return *p
}

// uuidPtrEq reports whether two nullable uuid refs are equal (both nil = equal).
func uuidPtrEq(a, b *uuid.UUID) bool {
	if a == nil || b == nil {
		return a == b
	}
	return *a == *b
}
