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

	var snapshot json.RawMessage
	var revNum int
	if err := s.pool.QueryRow(r.Context(),
		`SELECT snapshot, revision_num FROM entity_revisions WHERE revision_id=$1 AND entity_id=$2`,
		revID, entityID,
	).Scan(&snapshot, &revNum); err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "revision not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "revision fetch failed")
		return
	}

	// Guard against an incomplete snapshot (e.g. a '{}' baseline of an entity that
	// had no entity_snapshot at backfill). Exact-restore would read a MISSING
	// 'attributes' key as "zero attributes" and prune the entity to nothing — a
	// degenerate revision must not be a destructive restore target.
	if !snapshotRestorable(snapshot) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INCOMPLETE_REVISION",
			"revision snapshot is incomplete (no attributes) — cannot restore")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context())

	// Pre-restore fields → the event's `before` snapshot (so the captured restore
	// revision + learning-service see a faithful diff).
	bn, bk, ba, bsd, _ := loadEntityEventFields(r.Context(), tx, entityID)
	before := &EntitySnapshot{Name: bn, Kind: bk, Aliases: ba, ShortDescription: bsd}

	if err := reconcileEntityFromSnapshot(r.Context(), tx, entityID, string(snapshot)); err != nil {
		slog.Error("restoreEntityRevision reconcile", "entity", entityID, "error", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed: "+err.Error())
		return
	}

	// Emit as a USER change so VG-1 captures a KEPT revision (reversible restore)
	// and downstream sync (knowledge / staleness) reconciles.
	an, ak, aa, asd, fok := loadEntityEventFields(r.Context(), tx, entityID)
	if fok {
		payload := buildEntityEventPayload(
			bookID.String(), entityID.String(), an, ak, aa, asd,
			"updated", "user", userID.String(), before,
		)
		if err := emitEntityUpdatedTx(r.Context(), tx, entityID, payload); err != nil {
			slog.Error("restoreEntityRevision emit", "entity", entityID, "error", err)
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore emit failed")
			return
		}
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"restored": true, "entity_id": entityID.String(), "from_revision_num": revNum,
	})
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
		`INSERT INTO entity_attribute_values (attr_value_id, entity_id, attr_def_id, original_language, original_value)
		 SELECT (a->>'attr_value_id')::uuid, $2, (a->>'attr_def_ref_id')::uuid,
		        COALESCE(a->>'original_language','zh'), COALESCE(a->>'original_value','')
		 FROM jsonb_array_elements(COALESCE($1::jsonb->'attributes','[]'::jsonb)) a
		 ON CONFLICT (attr_value_id) DO UPDATE SET
		   original_language = EXCLUDED.original_language, original_value = EXCLUDED.original_value
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
	return nil
}
