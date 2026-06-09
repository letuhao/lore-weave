package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// wiki-llm M5 (C5) — the internal writeback for AI-generated wiki articles.
//
// knowledge-service generates an article (TipTap body + provenance) and POSTs it
// here. The CLOBBER-GUARD (§4.6) is the load-bearing invariant: an AI write may
// upsert an article that has NEVER been human-edited (its latest revision is
// 'ai' or the deterministic 'system' stub), but it must NEVER overwrite a human
// edit ('owner'). When a human has touched the article, the AI body is filed as a
// `wiki_suggestion` for the human to review — no data loss either way. The §5.1
// source-usage reverse index + the C7 fingerprint (inside generation_provenance)
// are recorded so the Phase-2 staleness sweep can target this article.

type wikiSourceUsage struct {
	SourceType    string `json:"source_type"` // 'entity' | 'kg' | 'block'
	SourceID      string `json:"source_id"`
	SourceVersion string `json:"source_version"`
}

type wikiWritebackRequest struct {
	EntityID             string          `json:"entity_id"`
	UserID               string          `json:"user_id"` // the user who triggered the gen job
	BodyJSON             json.RawMessage `json:"body_json"`
	GenerationStatus     string          `json:"generation_status"` // generated | needs_review | blocked
	GeneratedBy          string          `json:"generated_by"`      // model_ref / "ai"
	GenerationProvenance json.RawMessage `json:"generation_provenance"`
	SpoilerHorizon       *int            `json:"spoiler_horizon"`
	SourceUsage          []wikiSourceUsage `json:"source_usage"`
}

var validGenerationStatus = map[string]bool{
	"generated": true, "needs_review": true, "blocked": true,
}

// internalWriteWikiArticle handles POST /internal/books/{book_id}/wiki/articles.
func (s *Server) internalWriteWikiArticle(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req wikiWritebackRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	entityID, err := uuid.Parse(req.EntityID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_INVALID", "invalid entity_id")
		return
	}
	userID, err := uuid.Parse(req.UserID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_INVALID", "invalid user_id")
		return
	}
	if len(req.BodyJSON) == 0 {
		writeError(w, http.StatusBadRequest, "WIKI_INVALID", "body_json required")
		return
	}
	if !validGenerationStatus[req.GenerationStatus] {
		writeError(w, http.StatusBadRequest, "WIKI_INVALID", "invalid generation_status")
		return
	}

	// The entity must exist in this book (FK is RESTRICT; pre-check for a clean 404).
	var entBook uuid.UUID
	if err := s.pool.QueryRow(r.Context(),
		`SELECT book_id FROM glossary_entities WHERE entity_id=$1 AND deleted_at IS NULL`,
		entityID,
	).Scan(&entBook); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "WIKI_ENTITY_NOT_FOUND", "entity not found")
			return
		}
		slog.Error("writeback entity lookup", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if entBook != bookID {
		writeError(w, http.StatusNotFound, "WIKI_ENTITY_NOT_FOUND", "entity not in book")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck // best-effort rollback on early return

	// Existing article + its latest revision author (the clobber-guard signal).
	var articleID uuid.UUID
	var latestAuthor string
	hasArticle := true
	err = tx.QueryRow(r.Context(),
		`SELECT wa.article_id,
		        COALESCE((SELECT wr.author_type FROM wiki_revisions wr
		                  WHERE wr.article_id = wa.article_id
		                  ORDER BY wr.version DESC LIMIT 1), 'system')
		   FROM wiki_articles wa WHERE wa.entity_id=$1`,
		entityID,
	).Scan(&articleID, &latestAuthor)
	if errors.Is(err, pgx.ErrNoRows) {
		hasArticle = false
	} else if err != nil {
		slog.Error("writeback article lookup", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	// CLOBBER-GUARD (allowlist, fail-safe): an AI write may overwrite ONLY an
	// untouched AI/stub draft ('ai' or the deterministic 'system' seed). ANY other
	// latest author — a human 'owner' edit OR any future/unknown author_type — is
	// NOT clobbered; the AI body is filed as a suggestion for review. The denylist
	// ("overwrite unless 'owner'") would silently clobber a future human-ish type;
	// an allowlist never loses human work when in doubt.
	if hasArticle && latestAuthor != "ai" && latestAuthor != "system" {
		action, err := s.writeWikiSuggestion(r.Context(), tx, articleID, userID, &req)
		if err != nil {
			slog.Error("writeback suggestion", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		s.finishWriteback(w, r, tx, bookID, articleID, entityID, action, req.GenerationStatus)
		return
	}

	// WRITE path: upsert the article (new or AI/stub-owned) + a new 'ai' revision.
	if hasArticle {
		if _, err := tx.Exec(r.Context(), `
			UPDATE wiki_articles
			   SET body_json=$2, generation_status=$3, generated_by=$4,
			       generation_provenance=$5, generated_at=now(),
			       spoiler_horizon=$6, is_knowledge_stale=false, updated_at=now()
			 WHERE article_id=$1`,
			articleID, req.BodyJSON, req.GenerationStatus, req.GeneratedBy,
			req.GenerationProvenance, req.SpoilerHorizon,
		); err != nil {
			slog.Error("writeback update article", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	} else {
		if err := tx.QueryRow(r.Context(), `
			INSERT INTO wiki_articles
			  (entity_id, book_id, body_json, status, generation_status,
			   generated_by, generation_provenance, generated_at, spoiler_horizon)
			VALUES ($1,$2,$3,'draft',$4,$5,$6,now(),$7)
			RETURNING article_id`,
			entityID, bookID, req.BodyJSON, req.GenerationStatus,
			req.GeneratedBy, req.GenerationProvenance, req.SpoilerHorizon,
		).Scan(&articleID); err != nil {
			slog.Error("writeback insert article", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}
	if _, err := tx.Exec(r.Context(), `
		INSERT INTO wiki_revisions (article_id, version, body_json, author_id, author_type, summary)
		VALUES ($1, COALESCE((SELECT MAX(version) FROM wiki_revisions WHERE article_id=$1), 0) + 1,
		        $2, $3, 'ai', 'AI generation')`,
		articleID, req.BodyJSON, userID,
	); err != nil {
		slog.Error("writeback insert revision", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if err := s.replaceSourceUsage(r.Context(), tx, articleID, req.SourceUsage); err != nil {
		slog.Error("writeback source_usage", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	s.finishWriteback(w, r, tx, bookID, articleID, entityID, "written", req.GenerationStatus)
}

// writeWikiSuggestion files the AI body as a pending suggestion (clobber-guard
// path) — the full body + provenance live in diff_json for the human review.
func (s *Server) writeWikiSuggestion(
	ctx context.Context, tx pgx.Tx, articleID, userID uuid.UUID, req *wikiWritebackRequest,
) (string, error) {
	diff, err := json.Marshal(map[string]any{
		"body_json":             req.BodyJSON,
		"generation_provenance": req.GenerationProvenance,
		"generation_status":     req.GenerationStatus,
	})
	if err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO wiki_suggestions (article_id, user_id, diff_json, reason, status)
		VALUES ($1, $2, $3, 'AI regeneration (article has human edits)', 'pending')`,
		articleID, userID, diff,
	); err != nil {
		return "", err
	}
	return "suggestion", nil
}

// replaceSourceUsage rewrites the §5.1 reverse index for the article (delete-then-
// insert so a regen's usage set fully replaces the prior one).
func (s *Server) replaceSourceUsage(
	ctx context.Context, tx pgx.Tx, articleID uuid.UUID, usage []wikiSourceUsage,
) error {
	if _, err := tx.Exec(ctx,
		`DELETE FROM wiki_article_source_usage WHERE article_id=$1`, articleID,
	); err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, u := range usage {
		if u.SourceType == "" || u.SourceID == "" {
			continue
		}
		key := u.SourceType + "\x00" + u.SourceID
		if seen[key] {
			continue // PK is (article_id, source_type, source_id) — dedup defensively
		}
		seen[key] = true
		var ver any
		if u.SourceVersion != "" {
			ver = u.SourceVersion
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO wiki_article_source_usage (article_id, source_type, source_id, source_version)
			VALUES ($1, $2, $3, $4)`,
			articleID, u.SourceType, u.SourceID, ver,
		); err != nil {
			return err
		}
	}
	return nil
}

// finishWriteback emits the wiki.generated outbox event in-tx, commits, and
// writes the response. Shared by the write + suggestion paths.
func (s *Server) finishWriteback(
	w http.ResponseWriter, r *http.Request, tx pgx.Tx,
	bookID, articleID, entityID uuid.UUID, action, genStatus string,
) {
	exec := func(ctx context.Context, sql string, args ...any) error {
		_, e := tx.Exec(ctx, sql, args...)
		return e
	}
	if err := insertWikiGeneratedOutboxEvent(r.Context(), exec, articleID, wikiGeneratedPayload{
		BookID:           bookID.String(),
		ArticleID:        articleID.String(),
		EntityID:         entityID.String(),
		Action:           action,
		GenerationStatus: genStatus,
		EmittedAt:        time.Now().UTC().Format(time.RFC3339),
	}); err != nil {
		slog.Error("writeback emit wiki.generated", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("writeback commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"action":            action,
		"article_id":        articleID.String(),
		"generation_status": genStatus,
	})
}
