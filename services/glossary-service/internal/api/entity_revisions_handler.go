package api

// VG-2 (D-GLOSSARY-VERSIONING) — glossary entity history + restore.
//
//	GET  /v1/glossary/books/{book_id}/entities/{entity_id}/revisions
//	GET  /v1/glossary/books/{book_id}/entities/{entity_id}/revisions/{rev_id}
//	POST /v1/glossary/books/{book_id}/entities/{entity_id}/revisions/{rev_id}/restore
//
// Revisions are captured ASYNC by the VG-1 projection consumer; these endpoints
// browse them and restore an entity to a chosen revision. Restore is an EXACT
// reconcile (prune-then-upsert per table, id-preserving) so evidences /
// chapter-links / Neo4j anchors keyed on attr_value_id/translation_id stay valid.
// The restore is itself a user change → it emits glossary.entity_updated
// (actor=user) so VG-1 captures a new (kept) revision, making restore reversible.

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

const entityRevisionsListCap = 200

type entityRevisionSummary struct {
	RevisionID  string  `json:"revision_id"`
	RevisionNum int     `json:"revision_num"`
	Op          string  `json:"op"`
	ActorType   string  `json:"actor_type"`
	ActorID     *string `json:"actor_id,omitempty"`
	CreatedAt   string  `json:"created_at"`
}

// authEntityRevision runs the shared auth + grant + entity-in-book checks and
// returns (bookID, entityID, userID, ok). `need` is the minimum grant: reads
// pass GrantView; the mutating restore passes GrantEdit (else a view-only
// collaborator could write via restore — /review-impl HIGH).
func (s *Server) authEntityRevision(w http.ResponseWriter, r *http.Request, need grantclient.GrantLevel) (uuid.UUID, uuid.UUID, uuid.UUID, bool) {
	var zero uuid.UUID
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return zero, zero, zero, false
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return zero, zero, zero, false
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, need) {
		return zero, zero, zero, false
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return zero, zero, zero, false
	}
	var inBook bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2)`,
		entityID, bookID,
	).Scan(&inBook); err != nil || !inBook {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found in book")
		return zero, zero, zero, false
	}
	return bookID, entityID, userID, true
}

func (s *Server) listEntityRevisions(w http.ResponseWriter, r *http.Request) {
	_, entityID, _, ok := s.authEntityRevision(w, r, grantclient.GrantView)
	if !ok {
		return
	}
	items, err := s.queryEntityRevisions(r.Context(), entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revisions query failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"revisions": items})
}

func (s *Server) getEntityRevision(w http.ResponseWriter, r *http.Request) {
	_, entityID, _, ok := s.authEntityRevision(w, r, grantclient.GrantView)
	if !ok {
		return
	}
	revID, ok := parsePathUUID(w, r, "rev_id")
	if !ok {
		return
	}
	var (
		revNum    int
		op        string
		actorType string
		actorID   *uuid.UUID
		createdAt string
		snapshot  json.RawMessage
	)
	if err := s.pool.QueryRow(r.Context(), `
		SELECT revision_num, op, actor_type, actor_id, created_at::text, snapshot
		FROM entity_revisions WHERE revision_id=$1 AND entity_id=$2`,
		revID, entityID,
	).Scan(&revNum, &op, &actorType, &actorID, &createdAt, &snapshot); err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "revision not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revision query failed")
		return
	}
	resp := map[string]any{
		"revision_id": revID.String(), "revision_num": revNum, "op": op,
		"actor_type": actorType, "created_at": createdAt, "snapshot": snapshot,
	}
	if actorID != nil {
		resp["actor_id"] = actorID.String()
	}
	writeJSON(w, http.StatusOK, resp)
}

func (s *Server) restoreEntityRevision(w http.ResponseWriter, r *http.Request) {
	bookID, entityID, userID, ok := s.authEntityRevision(w, r, grantclient.GrantEdit)
	if !ok {
		return
	}
	revID, ok := parsePathUUID(w, r, "rev_id")
	if !ok {
		return
	}
	revNum, err := s.restoreEntityRevisionCore(r.Context(), bookID, entityID, userID, revID)
	switch {
	case errors.Is(err, errRevisionNotFound):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "revision not found")
		return
	case errors.Is(err, errRevisionIncomplete):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INCOMPLETE_REVISION",
			"revision snapshot is incomplete (no attributes) — cannot restore")
		return
	case errors.Is(err, errDuplicateName):
		writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_NAME",
			"restoring this revision's name would duplicate another entity in this book")
		return
	case err != nil:
		slog.Error("restoreEntityRevision", "entity", entityID, "error", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"restored": true, "entity_id": entityID.String(), "from_revision_num": revNum,
	})
}

// restore sentinels (shared by the HTTP handler + the glossary_propose_restore_revision
// confirm effect).
var (
	errRevisionNotFound   = errors.New("revision not found")              // → 404 / re-proposable
	errRevisionIncomplete = errors.New("revision snapshot is incomplete") // → 422
)

// restoreEntityRevisionCore restores an entity to a chosen revision's snapshot (exact,
// id-preserving reconcile) and emits the change as a USER edit so VG-1 captures a kept
// (reversible) revision. Returns the restored-from revision_num. Grant + entity-in-book
// are the CALLER's concern. Single source of truth for the HTTP restore handler and the
// confirm effect.
func (s *Server) restoreEntityRevisionCore(ctx context.Context, bookID, entityID, userID, revID uuid.UUID) (int, error) {
	var snapshot json.RawMessage
	var revNum int
	if err := s.pool.QueryRow(ctx,
		`SELECT snapshot, revision_num FROM entity_revisions WHERE revision_id=$1 AND entity_id=$2`,
		revID, entityID,
	).Scan(&snapshot, &revNum); err != nil {
		if err == pgx.ErrNoRows {
			return 0, errRevisionNotFound
		}
		return 0, err
	}

	// Guard against an incomplete snapshot (e.g. a '{}' baseline of an entity that
	// had no entity_snapshot at backfill). Exact-restore would read a MISSING
	// 'attributes' key as "zero attributes" and prune the entity to nothing — a
	// degenerate revision must not be a destructive restore target.
	if !snapshotRestorable(snapshot) {
		return 0, errRevisionIncomplete
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// Pre-restore fields → the event's `before` snapshot (so the captured restore
	// revision + learning-service see a faithful diff).
	bn, bk, ba, bsd, _ := loadEntityEventFields(ctx, tx, entityID)
	before := &EntitySnapshot{Name: bn, Kind: bk, Aliases: ba, ShortDescription: bsd}

	if err := reconcileEntityFromSnapshot(ctx, tx, entityID, string(snapshot)); err != nil {
		return 0, err
	}

	// Emit as a USER change so VG-1 captures a KEPT revision (reversible restore)
	// and downstream sync (knowledge / staleness) reconciles.
	an, ak, aa, asd, fok := loadEntityEventFields(ctx, tx, entityID)
	if fok {
		payload := buildEntityEventPayload(
			bookID.String(), entityID.String(), an, ak, aa, asd,
			"updated", "user", userID.String(), before,
		)
		if err := emitEntityUpdatedTx(ctx, tx, entityID, payload); err != nil {
			return 0, err
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return revNum, nil
}

// snapshotRestorable reports whether a revision snapshot is a complete, restorable
// entity state — a JSON object carrying the 'attributes' key. A degenerate '{}'
// (e.g. a backfill baseline of an entity that had no entity_snapshot) lacks it and
// must NOT be restored, or exact-restore would prune the entity to nothing.
func snapshotRestorable(snapshot []byte) bool {
	var m map[string]json.RawMessage
	if err := json.Unmarshal(snapshot, &m); err != nil {
		return false
	}
	_, ok := m["attributes"]
	return ok
}

// reconcileEntityFromSnapshot makes the live entity EXACTLY match the snapshot
// (id-preserving). Per table: PRUNE rows absent from the snapshot, THEN UPSERT the
// snapshot's rows. Prune-before-upsert ordering avoids the UNIQUE-key conflicts
// (entity_id+attr_def_id / attr_value_id+language_code / entity_id+chapter_id).
// `kind_id` is intentionally NOT reverted (a kind reassignment is a separate
// structural op). Runs inside the caller's transaction.
func reconcileEntityFromSnapshot(ctx context.Context, tx pgx.Tx, entityID uuid.UUID, snapshot string) error {
	stmts := []string{
		// 1. Entity-level fields.
		`UPDATE glossary_entities SET
		   status = COALESCE($1::jsonb->>'status', status),
		   alive = COALESCE(($1::jsonb->>'alive')::bool, alive),
		   tags = COALESCE(ARRAY(SELECT jsonb_array_elements_text(COALESCE($1::jsonb->'tags','[]'::jsonb))), '{}'),
		   deleted_at = CASE WHEN $1::jsonb->>'status' = 'active' THEN NULL ELSE deleted_at END,
		   updated_at = now()
		 WHERE entity_id = $2`,

		// 2-3. Attribute values: prune then upsert.
		`DELETE FROM entity_attribute_values WHERE entity_id = $2
		   AND attr_value_id NOT IN (
		     SELECT (a->>'attr_value_id')::uuid
		     FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a)`,
		// MERGE/M5 — a revision restore is a deliberate human curation action, so the
		// restored SOURCE values are marked 'verified': they reflect a state the user
		// explicitly chose, and the verified-clobber guard then protects them from a later
		// machine re-extraction silently overwriting the restore. (Snapshots predate the
		// confidence column, so we cannot faithfully restore the captured trust tier; the
		// human's restore intent justifies 'verified' regardless — empties can still fill.)
		`INSERT INTO entity_attribute_values (attr_value_id, entity_id, attr_def_id, original_language, original_value, confidence)
		 SELECT (a->>'attr_value_id')::uuid, $2, (a->>'attr_def_ref_id')::uuid,
		        COALESCE(a->>'original_language','zh'), COALESCE(a->>'original_value',''), 'verified'
		 FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a
		 ON CONFLICT (attr_value_id) DO UPDATE SET
		   original_language = EXCLUDED.original_language, original_value = EXCLUDED.original_value,
		   confidence = 'verified'
		 WHERE entity_attribute_values.entity_id = $2`,

		// 4-5. Translations: prune then upsert.
		`DELETE FROM attribute_translations
		 WHERE attr_value_id IN (SELECT attr_value_id FROM entity_attribute_values WHERE entity_id = $2)
		   AND translation_id NOT IN (
		     SELECT (t->>'translation_id')::uuid
		     FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a,
		          jsonb_array_elements(COALESCE(a->'translations','[]'::jsonb)) t)`,
		`INSERT INTO attribute_translations (translation_id, attr_value_id, language_code, value, confidence)
		 SELECT (t->>'translation_id')::uuid, (a->>'attr_value_id')::uuid, t->>'language_code',
		        COALESCE(t->>'value',''), COALESCE(t->>'confidence','draft')
		 FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a,
		      jsonb_array_elements(COALESCE(a->'translations','[]'::jsonb)) t
		 WHERE (a->>'attr_value_id')::uuid IN (SELECT attr_value_id FROM entity_attribute_values WHERE entity_id = $2)
		 ON CONFLICT (translation_id) DO UPDATE SET
		   language_code = EXCLUDED.language_code, value = EXCLUDED.value, confidence = EXCLUDED.confidence`,

		// 6-7. Evidences: prune then upsert.
		`DELETE FROM evidences
		 WHERE attr_value_id IN (SELECT attr_value_id FROM entity_attribute_values WHERE entity_id = $2)
		   AND evidence_id NOT IN (
		     SELECT (ev->>'evidence_id')::uuid
		     FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a,
		          jsonb_array_elements(COALESCE(a->'evidences','[]'::jsonb)) ev)`,
		`INSERT INTO evidences (evidence_id, attr_value_id, chapter_id, chapter_title, block_or_line,
		                        evidence_type, original_language, original_text, note)
		 SELECT (ev->>'evidence_id')::uuid, (a->>'attr_value_id')::uuid, NULLIF(ev->>'chapter_id','')::uuid,
		        ev->>'chapter_title', COALESCE(ev->>'block_or_line',''), COALESCE(ev->>'evidence_type','quote'),
		        COALESCE(ev->>'original_language','zh'), COALESCE(ev->>'original_text',''), ev->>'note'
		 FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a,
		      jsonb_array_elements(COALESCE(a->'evidences','[]'::jsonb)) ev
		 WHERE (a->>'attr_value_id')::uuid IN (SELECT attr_value_id FROM entity_attribute_values WHERE entity_id = $2)
		 ON CONFLICT (evidence_id) DO UPDATE SET
		   chapter_id = EXCLUDED.chapter_id, chapter_title = EXCLUDED.chapter_title,
		   block_or_line = EXCLUDED.block_or_line, evidence_type = EXCLUDED.evidence_type,
		   original_language = EXCLUDED.original_language, original_text = EXCLUDED.original_text,
		   note = EXCLUDED.note`,

		// 8-9. Chapter links: prune then upsert.
		`DELETE FROM chapter_entity_links WHERE entity_id = $2
		   AND link_id NOT IN (
		     SELECT (cl->>'link_id')::uuid
		     FROM jsonb_array_elements(COALESCE($1::jsonb->'chapter_links','[]'::jsonb)) cl)`,
		`INSERT INTO chapter_entity_links (link_id, entity_id, chapter_id, chapter_title, chapter_index, relevance, note)
		 SELECT (cl->>'link_id')::uuid, $2, (cl->>'chapter_id')::uuid, cl->>'chapter_title',
		        NULLIF(cl->>'chapter_index','')::int, COALESCE(cl->>'relevance','appears'), cl->>'note'
		 FROM jsonb_array_elements(COALESCE($1::jsonb->'chapter_links','[]'::jsonb)) cl
		 ON CONFLICT (link_id) DO UPDATE SET
		   chapter_id = EXCLUDED.chapter_id, chapter_title = EXCLUDED.chapter_title,
		   chapter_index = EXCLUDED.chapter_index, relevance = EXCLUDED.relevance, note = EXCLUDED.note
		 WHERE chapter_entity_links.entity_id = $2`,
	}
	for _, q := range stmts {
		if _, err := tx.Exec(ctx, q, snapshot, entityID); err != nil {
			return err
		}
	}
	// D-GLOSSARY-MULTIROW slice 2 — rebuild per-item child rows from the restored list
	// values (verified — a restore is human curation). The upserted EAVs' items were stale;
	// orphan items of pruned EAVs are gone via the FK ON DELETE CASCADE.
	if err := resyncEntityListItems(ctx, tx, entityID, "verified"); err != nil {
		return err
	}
	// D-GLOSSARY-ST-DEDUP M3a: a restore can change the name/term to a prior value;
	// re-stamp the app-maintained dedup key (idempotent — no-op when unchanged).
	if err := refreshEntityDedupKey(ctx, tx, entityID); err != nil {
		return err
	}
	return nil
}
