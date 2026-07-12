package api

// WS-0.4 — the "add to knowledge" (index) action.
//
// Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.3.
//
// Publishing no longer gates the knowledge graph. `publish` means only "this is the
// canonical/shareable version"; INDEXING is now an independent, explicit act available
// on ANY chapter of ANY book kind, draft or published. Writers draft without publishing
// and still want a glossary/KG; kind='diary' books never publish at all.
//
// The Tx mirrors mcpPublishChapter's shape (same empty-prose guard, same before-Tx
// parse + draftVersion guard, same scenes upsert) so the two paths cannot drift.
//
// TWO things this action must NEVER do:
//
//   - It must never fire on autosave. `chapter.saved` stays unconsumed by
//     knowledge-service (main.py: "so unreviewed draft prose never canonizes").
//     Indexing happens ONLY on this explicit action. There is deliberately NO
//     idle-debounce (spec §3.3 removed v1's — it was auto-indexing on a timer,
//     precisely the thrash this change claims to prevent).
//
//   - It must never index a kg_exclude'd chapter. kg_exclude is PRODUCER-side
//     authoritative (§3.7): knowledge-service cannot see the column, so book-service
//     simply does not set the pointer and does not emit the event.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// errActionKGExcluded — the chapter is explicitly kept out of the knowledge graph.
// A distinct error (not errActionBadState) so the caller can say WHY, rather than
// returning a generic failure the user cannot act on.
var errActionKGExcluded = errors.New("chapter is excluded from the knowledge graph (kg_exclude)")

// indexResult reports what the index action actually did. `Reused` is load-bearing for
// no-silent-success: re-indexing an unchanged draft is a legitimate no-op, and the
// caller must be able to tell the user "already indexed at this revision" rather than
// implying fresh work happened.
type indexResult struct {
	RevisionID uuid.UUID     `json:"revision_id"`
	Reused     bool          `json:"reused_revision"`
	Reparse    reparseCounts `json:"reparse"`
}

// indexChapter pins the chapter's current draft as the revision the knowledge layer
// reflects, parses its scenes, and emits chapter.kg_indexed.
//
// Steps (spec §3.3):
//  1. parse the body BEFORE the Tx (never a cross-service call inside a transaction)
//  2. read the live draft under FOR UPDATE; refuse empty prose; refuse kg_exclude
//  3. snapshot into chapter_revisions — REUSING the latest revision when the draft is
//     byte-identical, so repeated clicks don't spam the revision history
//  4. advance kg_indexed_revision_id
//  5. parse scenes for that revision and advance last_parsed_revision_id
//  6. emit chapter.kg_indexed {book_id, chapter_id, revision_id}
func (s *Server) indexChapter(ctx context.Context, caller, bookID, chID uuid.UUID) (indexResult, error) {
	// (1) Parse before the Tx (IX-2 rule), exactly as publish does.
	prep := s.prepareReparse(ctx, bookID, chID)

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return indexResult{}, err
	}
	defer tx.Rollback(ctx)

	// (2) Read the live draft + the exclusion flag together, under the same lock the
	// publish path takes.
	var curr int64
	var body json.RawMessage
	var format string
	var kgExclude bool
	// publishedRev rides along so the emitted event can carry it: knowledge-service
	// stamps passage `canon = (revision_id == published_revision_id)` (spec §3.7 / P1-8)
	// and would otherwise need a cross-service call back to us to decide it.
	var publishedRev *uuid.UUID
	// priorKG is the pointer BEFORE this action. It is what tells us whether this index
	// actually moves anything — see the `moved` computation below (review-impl P1).
	var priorKG *uuid.UUID
	// FOR UPDATE OF d, c — review-impl: locking only `d` (chapter_drafts) left
	// published_revision_id and kg_exclude read OUTSIDE any lock on `chapters`, so a
	// concurrent publish/unpublish/exclude between this SELECT and the UPDATE ~100 lines
	// below could make the emitted event carry a stale published_revision_id (⇒ a wrong
	// canon flag) or slip past the exclusion check. Lock both rows.
	err = tx.QueryRow(ctx, `
SELECT d.draft_version, d.body, d.draft_format, c.kg_exclude, c.published_revision_id,
       c.kg_indexed_revision_id
FROM chapter_drafts d JOIN chapters c ON c.id = d.chapter_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
FOR UPDATE OF d, c`, chID, bookID).Scan(&curr, &body, &format, &kgExclude, &publishedRev, &priorKG)
	if errors.Is(err, pgx.ErrNoRows) {
		return indexResult{}, errActionTargetGone
	}
	if err != nil {
		return indexResult{}, err
	}

	// kg_exclude is producer-side authoritative (§3.7). Refuse loudly — a silent
	// "success" that indexed nothing is the bug class this repo keeps re-shipping.
	if kgExclude {
		return indexResult{}, errActionKGExcluded
	}

	// Empty-prose guard — the SAME union publish uses (editor `_text` projection OR
	// standard tiptap nested text leaves). Indexing empty prose would enqueue an LLM
	// extraction over nothing.
	var prose string
	_ = tx.QueryRow(ctx, `
SELECT COALESCE((
  SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(($1)::jsonb, '$.content[*]._text') AS x(t)
), '') || COALESCE((
  SELECT string_agg(t #>> '{}', '') FROM jsonb_path_query(($1)::jsonb, '$.**.text') AS y(t)
), '')`, body).Scan(&prose)
	if strings.TrimSpace(prose) == "" {
		return indexResult{}, errActionBadState
	}

	// (3) Revision reuse. "Add to knowledge" is a casual, repeatable click; snapshotting
	// a fresh revision on every click would spam chapter_revisions with identical bodies
	// (and, worse, churn kg_indexed_revision_id so the sweeper re-parses for no reason).
	// jsonb equality (not text equality) so insignificant whitespace/key-order differences
	// in the stored JSON don't defeat the reuse.
	var revID uuid.UUID
	err = tx.QueryRow(ctx, `
SELECT id FROM chapter_revisions
WHERE chapter_id=$1 AND body = $2::jsonb
ORDER BY created_at DESC, id DESC
LIMIT 1`, chID, body).Scan(&revID)
	switch {
	case err == nil:
		// A revision with this exact body already exists — reuse it rather than spamming
		// a duplicate. NOTE this does NOT mean "nothing changed": every save plants a
		// revision row next to the draft, so this branch is hit on a FIRST index too.
	case errors.Is(err, pgx.ErrNoRows):
		if ierr := tx.QueryRow(ctx, `
INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id)
VALUES($1,$2,$3,'index',$4) RETURNING id`, chID, body, format, caller).Scan(&revID); ierr != nil {
			return indexResult{}, ierr
		}
	default:
		return indexResult{}, err
	}

	// ── review-impl P1: "did anything actually change?" is about the POINTER, not the
	// revision row. ──
	//
	// `reused` used to mean "a chapter_revisions row with this body already existed" —
	// but every create/import/PATCH-draft save plants exactly such a row, so it was TRUE
	// even on a chapter's FIRST index. The API reported `reused_revision: true` (which
	// every caller reads as "no-op, nothing to do") while the pointer moved, scenes were
	// re-parsed, and a full LLM extraction was enqueued. The live smoke printed exactly
	// that and I did not question it.
	//
	// The honest question is whether kg_indexed_revision_id MOVES. If it does not, this
	// really is a no-op: the graph already reflects this revision, so we must not emit,
	// must not re-arm extraction, and must not spend (acceptance #10).
	moved := priorKG == nil || *priorKG != revID
	reused := !moved

	// (4) Advance the KG pointer. Publish is NOT touched — a draft chapter stays a draft.
	// The kg_exclude re-check in the WHERE closes the window between the SELECT above and
	// here (another Tx could have set it); it costs nothing and fails closed.
	ct, err := tx.Exec(ctx, `
UPDATE chapters SET kg_indexed_revision_id=$2, updated_at=now()
WHERE id=$1 AND kg_exclude = false`, chID, revID)
	if err != nil {
		return indexResult{}, err
	}
	if ct.RowsAffected() == 0 {
		return indexResult{}, errActionKGExcluded
	}

	// (5) Same-Tx scenes re-parse, on the SAME terms publish uses: only when the parse
	// succeeded AND described the body we are actually pinning. Otherwise leave the
	// marker stale and let the sweeper heal — a parse failure must never block the
	// user's explicit index request (OQ-1).
	var counts reparseCounts
	if prep.ok && prep.draftVersion == curr {
		counts, err = s.upsertChapterScenes(ctx, tx, bookID, chID, prep.structuralPath, prep.tree)
		if err != nil {
			return indexResult{}, err
		}
		if _, err := tx.Exec(ctx, `UPDATE chapters SET last_parsed_revision_id=$2 WHERE id=$1`, chID, revID); err != nil {
			return indexResult{}, err
		}
		// Emit ONLY when the index actually changed. A no-op re-parse must not fire
		// chapter.scenes_reparsed — its consumer invalidates the extraction cache, and
		// re-indexing an unchanged revision is supposed to cost nothing (acceptance #10).
		if counts.changed() {
			// NB: emitScenesReparsed's payload field is named `published_revision_id`
			// (a FROZEN contract, spec 26 IX-10). Post-WS-0.4 it means "the revision the
			// scenes reflect", which may now be a DRAFT revision. The consumer treats it
			// as observability only (it invalidates by chapter_id), so the frozen shape
			// stays valid — but do not read it as "this chapter is published".
			if err := emitScenesReparsed(ctx, tx, bookID, chID, revID, counts.ParseVersion); err != nil {
				return indexResult{}, err
			}
			// SC11-amendment Phase 0 — writer #2 of `scenes.source_scene_id`. A re-parse
			// re-resolves every scene's anchor (`desiredSourceSceneID`), so the spec back-links
			// may have moved. Same tx, same `counts.changed()` guard. A SEPARATE event type from
			// scenes_reparsed on purpose: that one drives knowledge's extraction cache, and
			// widening its meaning would change another service's behaviour by side-effect.
			if err := emitScenesLinked(ctx, tx, bookID, chID); err != nil {
				return indexResult{}, err
			}
		}
	} else {
		slog.WarnContext(ctx, "index: re-parse skipped; index left stale for the sweeper",
			"chapter_id", chID, "parse_ok", prep.ok, "draft_version_match", prep.draftVersion == curr)
	}

	// (6) The NEW event — emitted ONLY when the pointer actually moved.
	//
	// Deliberately NOT chapter.saved (fires on every autosave, carries only {book_id},
	// and is deliberately un-consumed by knowledge-service) and NOT chapter.published
	// (a draft-indexed chapter is not published).
	//
	// review-impl P1 — the `moved` gate is a COST gate. The consumer's keep-LATEST upsert
	// resets `processed_at = NULL` on conflict, so an unconditional emit meant every
	// redundant "Update knowledge" click on unchanged prose re-armed the pending row and
	// drove a full Pass-2 LLM re-extraction of the chapter. Acceptance #10 says re-indexing
	// an unchanged revision costs nothing; without this gate it cost a full extraction.
	//
	// `published_revision_id` is carried so knowledge-service can stamp passage
	// `canon = (revision_id == published_revision_id)` (spec §3.7 / P1-8) WITHOUT a
	// cross-service call back to us. It is nullable: a never-published chapter emits null,
	// and its passages are correctly ingested as canon=false.
	if moved {
		if err := insertOutboxEvent(ctx, tx, "chapter.kg_indexed", chID, map[string]any{
			"book_id":               bookID,
			"chapter_id":            chID,
			"revision_id":           revID,
			"published_revision_id": publishedRev,
		}); err != nil {
			return indexResult{}, err
		}
	} else {
		// Not silent: say why nothing happened. A "success" with no work done must always
		// explain itself, and the caller gets reused_revision=true to surface it.
		slog.InfoContext(ctx, "index: no-op — the knowledge graph already reflects this "+
			"revision; no event emitted, no extraction re-armed, no spend",
			"chapter_id", chID, "revision_id", revID)
	}

	if err := tx.Commit(ctx); err != nil {
		return indexResult{}, err
	}
	return indexResult{RevisionID: revID, Reused: reused, Reparse: counts}, nil
}

// ── MCP tool (Tier-A) ────────────────────────────────────────────────────────

type indexChapterIn struct {
	BookID    string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter to add to the knowledge graph (UUID)"`
}

type indexChapterOut struct {
	ChapterID  string        `json:"chapter_id"`
	RevisionID string        `json:"revision_id"`
	Reused     bool          `json:"reused_revision"`
	Reparse    reparseCounts `json:"reparse"`
}

// toolBookIndexChapter — "add this chapter to my knowledge graph".
//
// Does NOT publish. Publishing is a separate, unrelated act (book_publish_* / the
// action-confirm path); a chapter can be indexed while staying a draft forever, which
// is the whole point of the change.
func (s *Server) toolBookIndexChapter(ctx context.Context, _ *mcp.CallToolRequest, in indexChapterIn) (*mcp.CallToolResult, indexChapterOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, indexChapterOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, indexChapterOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, indexChapterOut{}, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, indexChapterOut{}, mcpOwnershipError(err)
	}

	res, err := s.indexChapter(ctx, userID, bookID, chID)
	if err != nil {
		switch {
		case errors.Is(err, errActionKGExcluded):
			// Say WHY. A generic failure here would have the agent retry forever.
			return nil, indexChapterOut{}, errors.New(
				"this chapter is excluded from the knowledge graph (kg_exclude); clear the " +
					"exclusion before indexing it")
		case errors.Is(err, errActionBadState):
			return nil, indexChapterOut{}, errors.New("the chapter has no prose to index")
		case errors.Is(err, errActionTargetGone):
			return nil, indexChapterOut{}, errBookNotAccessible
		}
		return nil, indexChapterOut{}, errors.New("failed to index chapter")
	}

	// review-impl P2 — NO undo_hint here, deliberately.
	//
	// It used to advertise book_chapter_set_kg_exclude{kg_exclude:true} as the reverse.
	// That is NOT an undo: it is strictly MORE destructive than the thing it claims to
	// undo. Indexing adds one chapter's facts; kg_exclude retracts the chapter's ENTIRE
	// graph evidence and DELETES all its passages — including anything a previous publish
	// had contributed — and then keeps it out. An agent that dutifully "undoes" an
	// accidental index would destroy knowledge the user never asked to lose.
	//
	// There is no cheap true inverse (we do not snapshot the pre-index graph state), so we
	// advertise none. An honest absence beats a destructive lie.
	return nil, indexChapterOut{
		ChapterID:  chID.String(),
		RevisionID: res.RevisionID.String(),
		Reused:     res.Reused,
		Reparse:    res.Reparse,
	}, nil
}

type setKGExcludeIn struct {
	BookID    string `json:"book_id" jsonschema:"the book the chapter belongs to (UUID)"`
	ChapterID string `json:"chapter_id" jsonschema:"the chapter to include/exclude (UUID)"`
	KGExclude bool   `json:"kg_exclude" jsonschema:"true = keep this chapter OUT of the knowledge graph and RETRACT anything already extracted from it; false = allow it to be indexed again (does not re-index by itself)"`
}

type setKGExcludeOut struct {
	ChapterID string `json:"chapter_id"`
	KGExclude bool   `json:"kg_exclude"`
}

func (s *Server) toolBookSetKGExclude(ctx context.Context, _ *mcp.CallToolRequest, in setKGExcludeIn) (*mcp.CallToolResult, setKGExcludeOut, error) {
	userID, ok := mcpUserID(ctx)
	if !ok {
		return nil, setKGExcludeOut{}, errMissingIdentity
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, setKGExcludeOut{}, errors.New("book_id must be a UUID")
	}
	chID, err := uuid.Parse(in.ChapterID)
	if err != nil {
		return nil, setKGExcludeOut{}, errors.New("chapter_id must be a UUID")
	}
	if _, err := s.mcpRequireGrant(ctx, bookID, userID, GrantEdit); err != nil {
		return nil, setKGExcludeOut{}, mcpOwnershipError(err)
	}
	if err := s.setChapterKGExclude(ctx, bookID, chID, in.KGExclude); err != nil {
		if errors.Is(err, errActionTargetGone) {
			return nil, setKGExcludeOut{}, errBookNotAccessible
		}
		return nil, setKGExcludeOut{}, errors.New("failed to set kg_exclude")
	}
	undo := undoResult("book_chapter_set_kg_exclude", map[string]any{
		"book_id": bookID.String(), "chapter_id": chID.String(), "kg_exclude": !in.KGExclude,
	})
	return undo, setKGExcludeOut{ChapterID: chID.String(), KGExclude: in.KGExclude}, nil
}

// ── REST ─────────────────────────────────────────────────────────────────────

// postChapterIndex — POST /v1/books/{book_id}/chapters/{chapter_id}/index
//
// "Add this chapter to my knowledge graph." Available on a DRAFT chapter; publishing
// is not required and is not implied.
func (s *Server) postChapterIndex(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	res, err := s.indexChapter(r.Context(), caller, bookID, chID)
	if err != nil {
		s.writeActionEffectError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id":      chID,
		"revision_id":     res.RevisionID,
		"reused_revision": res.Reused,
		"reparse":         res.Reparse,
	})
}

// putChapterKGExclude — PUT /v1/books/{book_id}/chapters/{chapter_id}/kg-exclude
//
// Body: {"kg_exclude": true|false}. Setting true RETRACTS: it clears the pointer and
// emits chapter.kg_excluded so knowledge-service removes what it already extracted.
func (s *Server) putChapterKGExclude(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	var in struct {
		KGExclude *bool `json:"kg_exclude"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.KGExclude == nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION", "kg_exclude (boolean) is required")
		return
	}
	if err := s.setChapterKGExclude(r.Context(), bookID, chID, *in.KGExclude); err != nil {
		s.writeActionEffectError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id": chID,
		"kg_exclude": *in.KGExclude,
	})
}

// setChapterKGExclude toggles the chapter's knowledge-graph exclusion.
//
// Setting it TRUE also clears kg_indexed_revision_id and emits chapter.kg_excluded, so
// the knowledge side can RETRACT what it already extracted (spec §3.8 / P1-7). Without
// that, the toggle would be a lie: facts extracted from a chapter the user later marks
// "keep out of my knowledge graph" would simply stay in the graph.
//
// Setting it FALSE only re-opens the chapter to indexing — it does NOT silently
// re-index. Re-entering the graph must be an explicit act (the user clicks "add to
// knowledge" again), because a toggle that silently re-ingests is a privacy surprise.
func (s *Server) setChapterKGExclude(ctx context.Context, bookID, chID uuid.UUID, exclude bool) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var ct pgconn.CommandTag
	if exclude {
		ct, err = tx.Exec(ctx, `
UPDATE chapters SET kg_exclude=true, kg_indexed_revision_id=NULL, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`, chID, bookID)
	} else {
		ct, err = tx.Exec(ctx, `
UPDATE chapters SET kg_exclude=false, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`, chID, bookID)
	}
	if err != nil {
		return err
	}
	if ct.RowsAffected() == 0 {
		return errActionTargetGone
	}

	if exclude {
		// The retraction signal. knowledge-service reuses its existing unpublish retract
		// path (remove_evidence_for_natural_key + delete_passages_for_source) — the
		// primitive already exists and was built for exactly this symmetry.
		if err := insertOutboxEvent(ctx, tx, "chapter.kg_excluded", chID, map[string]any{
			"book_id": bookID, "chapter_id": chID,
		}); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}
