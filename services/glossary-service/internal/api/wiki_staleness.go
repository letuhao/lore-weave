package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// wikiStalenessRow is one pending change-feed entry: the stale article + WHY.
type wikiStalenessRow struct {
	StalenessID      string          `json:"staleness_id"`
	ArticleID        string          `json:"article_id"`
	EntityID         string          `json:"entity_id"`
	DisplayName      string          `json:"display_name"`
	Kind             kindSummary     `json:"kind"`
	ReasonCode       string          `json:"reason_code"`
	Severity         string          `json:"severity"`
	SourceRef        json.RawMessage `json:"source_ref"`
	GenerationStatus *string         `json:"generation_status"`
	DetectedAt       time.Time       `json:"detected_at"`
}

// listWikiStaleness — GET /v1/glossary/books/{book_id}/wiki/staleness
// The §5.3 "Knowledge updates" feed: pending staleness rows for the book, newest
// + highest-severity first (the FE groups by reason). Owner-gated.
func (s *Server) listWikiStaleness(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT ws.staleness_id, ws.article_id, wa.entity_id,
		       COALESCE(dn.original_value, '') AS display_name,
		       ek.kind_id, ek.code, ek.name, ek.icon, ek.color,
		       ws.reason_code, ws.severity, ws.source_ref, wa.generation_status, ws.detected_at
		  FROM wiki_staleness ws
		  JOIN wiki_articles wa ON wa.article_id = ws.article_id
		  JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		  JOIN entity_kinds ek ON ek.kind_id = ge.kind_id
		  LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
		    AND dn.attr_def_id = (
		      SELECT ad.attr_def_id FROM attribute_definitions ad
		      WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
		      ORDER BY ad.sort_order LIMIT 1)
		 WHERE wa.book_id = $1 AND ws.status = 'pending'
		 ORDER BY CASE ws.severity WHEN 'hard' THEN 0 WHEN 'structural' THEN 1 ELSE 2 END,
		          ws.detected_at DESC`,
		bookID)
	if err != nil {
		slog.Error("listWikiStaleness query", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer rows.Close()

	items := []wikiStalenessRow{}
	for rows.Next() {
		var it wikiStalenessRow
		if err := rows.Scan(
			&it.StalenessID, &it.ArticleID, &it.EntityID, &it.DisplayName,
			&it.Kind.KindID, &it.Kind.Code, &it.Kind.Name, &it.Kind.Icon, &it.Kind.Color,
			&it.ReasonCode, &it.Severity, &it.SourceRef, &it.GenerationStatus, &it.DetectedAt,
		); err != nil {
			slog.Error("listWikiStaleness scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		slog.Error("listWikiStaleness rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": len(items)})
}

// dismissWikiStaleness — POST /v1/glossary/books/{book_id}/wiki/staleness/{staleness_id}/dismiss
// "Accept as-is": resolve a pending row WITHOUT regenerating (no spend). Owner-gated
// + book-scoped so a user can't dismiss another book's staleness.
func (s *Server) dismissWikiStaleness(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	stalenessID, ok := parsePathUUID(w, r, "staleness_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}
	var articleID uuid.UUID
	err := s.pool.QueryRow(r.Context(), `
		UPDATE wiki_staleness SET status='dismissed'
		 WHERE staleness_id=$1 AND status='pending'
		   AND article_id IN (SELECT article_id FROM wiki_articles WHERE book_id=$2)
		RETURNING article_id`,
		stalenessID, bookID).Scan(&articleID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "WIKI_STALENESS_NOT_FOUND", "no pending staleness row for this book")
		return
	}
	if err != nil {
		slog.Error("dismissWikiStaleness", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	// Clear the denormalized "outdated" flag once the LAST pending row for the
	// article is dismissed — otherwise the badge would persist after the user
	// accepted everything as-is.
	if _, err := s.pool.Exec(r.Context(), `
		UPDATE wiki_articles SET is_knowledge_stale=false
		 WHERE article_id=$1
		   AND NOT EXISTS (SELECT 1 FROM wiki_staleness
		                    WHERE article_id=$1 AND status='pending')`,
		articleID,
	); err != nil {
		slog.Error("dismissWikiStaleness clear flag", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"staleness_id": stalenessID.String(), "status": "dismissed"})
}

// wiki-llm Phase-2 (§5.2 DEFER, pull tier-2) — the version-drift sweep.
//
// The push consumer (staleness_consumer.go) catches SOURCE changes (entity/chapter
// edits) via events. It cannot see RECIPE drift: a bump of the generation
// prompt/pipeline version means the same inputs would now produce a different
// article (the stale-image-guard lesson — a version hash can't catch behavioural
// drift, so it's an explicit token). This on-demand sweep compares each AI
// article's STORED build_inputs versions against the CURRENT versions (supplied by
// the caller, who owns the live config) and records a `recipe_drift` staleness row
// for the laggards. Glossary-local: no LLM work, no cross-service recompute (the
// KG-neighbourhood recompute is the separate D-WIKI-P2-KG-SWEEP follow-up).

// sweepWikiStaleness — POST /internal/books/{book_id}/wiki/staleness-sweep
// Body: {"prompt_version": "...", "pipeline_version": "..."} (the CURRENT versions).
func (s *Server) sweepWikiStaleness(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req struct {
		PromptVersion   string `json:"prompt_version"`
		PipelineVersion string `json:"pipeline_version"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}
	if req.PromptVersion == "" || req.PipelineVersion == "" {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "prompt_version and pipeline_version required")
		return
	}

	flagged, err := s.sweepRecipeDrift(r.Context(), bookID, req.PromptVersion, req.PipelineVersion)
	if err != nil {
		slog.Error("sweepWikiStaleness", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"flagged": flagged})
}

// sweepRecipeDrift records a pending `recipe_drift` staleness row for every AI
// article in the book whose stored prompt/pipeline version differs from the
// current ones, and flips is_knowledge_stale. Idempotent on the ledger's
// partial-unique (article, reason, source) index — the source_id is the
// drifted-FROM version pair, so re-running with the same current versions is a
// no-op. Returns the number of staleness rows inserted.
func (s *Server) sweepRecipeDrift(ctx context.Context, bookID uuid.UUID, promptV, pipelineV string) (int, error) {
	tag, err := s.pool.Exec(ctx, `
		INSERT INTO wiki_staleness (article_id, reason_code, source_ref, severity)
		SELECT wa.article_id, 'recipe_drift',
		       jsonb_build_object(
		         'source_type', 'recipe',
		         'source_id',
		           COALESCE(wa.generation_provenance->'build_inputs'->>'prompt_version','') || '/' ||
		           COALESCE(wa.generation_provenance->'build_inputs'->>'pipeline_version',''),
		         'current_prompt_version', $2::text,
		         'current_pipeline_version', $3::text),
		       'content'
		  FROM wiki_articles wa
		 WHERE wa.book_id = $1
		   AND wa.generation_status IS NOT NULL
		   AND ( COALESCE(wa.generation_provenance->'build_inputs'->>'prompt_version','')   <> $2
		      OR COALESCE(wa.generation_provenance->'build_inputs'->>'pipeline_version','') <> $3 )
		ON CONFLICT (article_id, reason_code, (source_ref->>'source_id'))
		  WHERE status = 'pending' DO NOTHING`,
		bookID, promptV, pipelineV,
	)
	if err != nil {
		return 0, err
	}
	inserted := int(tag.RowsAffected())
	if _, err := s.pool.Exec(ctx, `
		UPDATE wiki_articles SET is_knowledge_stale = true
		 WHERE book_id = $1 AND generation_status IS NOT NULL AND is_knowledge_stale = false
		   AND ( COALESCE(generation_provenance->'build_inputs'->>'prompt_version','')   <> $2
		      OR COALESCE(generation_provenance->'build_inputs'->>'pipeline_version','') <> $3 )`,
		bookID, promptV, pipelineV,
	); err != nil {
		return inserted, err
	}
	return inserted, nil
}
