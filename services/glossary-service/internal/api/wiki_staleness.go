package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/google/uuid"
)

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
