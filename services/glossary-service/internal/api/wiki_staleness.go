package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"maps"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT ws.staleness_id, ws.article_id, wa.entity_id,
		       COALESCE(dn.original_value, '') AS display_name,
		       ek.book_kind_id, ek.code, ek.name, ek.icon, ek.color,
		       ws.reason_code, ws.severity, ws.source_ref, wa.generation_status, ws.detected_at
		  FROM wiki_staleness ws
		  JOIN wiki_articles wa ON wa.article_id = ws.article_id
		  JOIN glossary_entities ge ON ge.entity_id = wa.entity_id
		  JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		  LEFT JOIN entity_attribute_values dn ON dn.entity_id = ge.entity_id
		    AND dn.attr_def_id = (
		      SELECT ad.attr_id FROM book_attributes ad
		      JOIN book_genres g ON g.genre_id = ad.genre_id
		      WHERE ad.kind_id = ge.kind_id AND ad.code IN ('name','term')
		      ORDER BY (g.code = 'universal') DESC, ad.sort_order LIMIT 1)
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
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

// dismissWikiStalenessBatch — POST /v1/glossary/books/{book_id}/wiki/staleness/dismiss-batch
// W2 (gap-closure) "Bỏ qua đã chọn": dismiss MANY pending rows at once (owner-gated,
// book-scoped). One UPDATE for the rows + one to clear the per-article "outdated" flag
// for any affected article whose last pending row just went, in a tx.
func (s *Server) dismissWikiStalenessBatch(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	var req struct {
		StalenessIDs []string `json:"staleness_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid JSON body")
		return
	}
	const maxDismissBatch = 500 // a sane ceiling — the feed never realistically has more pending
	if len(req.StalenessIDs) > maxDismissBatch {
		writeError(w, http.StatusRequestEntityTooLarge, "WIKI_BATCH_TOO_LARGE", "too many staleness_ids")
		return
	}
	ids := make([]uuid.UUID, 0, len(req.StalenessIDs))
	for _, raw := range req.StalenessIDs {
		u, perr := uuid.Parse(raw)
		if perr != nil {
			writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid staleness_id")
			return
		}
		ids = append(ids, u)
	}
	if len(ids) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"dismissed": 0})
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		slog.Error("dismissWikiStalenessBatch begin", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	rows, err := tx.Query(r.Context(), `
		UPDATE wiki_staleness SET status='dismissed'
		 WHERE staleness_id = ANY($1) AND status='pending'
		   AND article_id IN (SELECT article_id FROM wiki_articles WHERE book_id=$2)
		RETURNING article_id`,
		ids, bookID)
	if err != nil {
		slog.Error("dismissWikiStalenessBatch update", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	affected := map[uuid.UUID]struct{}{}
	dismissedCount := 0
	for rows.Next() {
		var aid uuid.UUID
		if err := rows.Scan(&aid); err != nil {
			rows.Close()
			slog.Error("dismissWikiStalenessBatch scan", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
		affected[aid] = struct{}{}
		dismissedCount++
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		slog.Error("dismissWikiStalenessBatch rows", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}

	if len(affected) > 0 {
		aids := make([]uuid.UUID, 0, len(affected))
		for aid := range affected {
			aids = append(aids, aid)
		}
		// Clear the denormalized flag for any affected article with no pending rows left.
		if _, err := tx.Exec(r.Context(), `
			UPDATE wiki_articles SET is_knowledge_stale=false
			 WHERE article_id = ANY($1)
			   AND NOT EXISTS (SELECT 1 FROM wiki_staleness
			                    WHERE article_id = wiki_articles.article_id AND status='pending')`,
			aids,
		); err != nil {
			slog.Error("dismissWikiStalenessBatch clear flag", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		slog.Error("dismissWikiStalenessBatch commit", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"dismissed": dismissedCount})
}

// getWikiStalenessDiff — GET /v1/glossary/books/{book_id}/wiki/staleness/{staleness_id}/diff
// W6b-2b — the source change diff for one row: before (the source text captured at
// generation, W6b-2a) vs after (the current source, re-gathered by knowledge through
// the same path → format parity). Owner-gated. {available:false} when there is no
// snapshot (a pre-W6b-2 article) or knowledge can't supply the "after" right now (the
// FE then falls back to the W6b-1 "view source" jump). `block` diffs are approximate
// (their source is a retrieval result). An `after` of "" is a genuine removal.
func (s *Server) getWikiStalenessDiff(w http.ResponseWriter, r *http.Request) {
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
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}

	// Load the row (scoped to the book) → article, its entity, the changed source.
	var articleID, entityID string
	var srcRef []byte
	if err := s.pool.QueryRow(r.Context(), `
		SELECT ws.article_id, wa.entity_id, ws.source_ref
		  FROM wiki_staleness ws JOIN wiki_articles wa ON wa.article_id = ws.article_id
		 WHERE ws.staleness_id = $1 AND wa.book_id = $2`,
		stalenessID, bookID).Scan(&articleID, &entityID, &srcRef); err != nil {
		writeError(w, http.StatusNotFound, "WIKI_NOT_FOUND", "staleness row not found")
		return
	}
	var ref struct {
		SourceType string `json:"source_type"`
		SourceID   string `json:"source_id"`
	}
	_ = json.Unmarshal(srcRef, &ref)
	if ref.SourceType == "" || ref.SourceID == "" {
		writeJSON(w, http.StatusOK, map[string]any{"available": false})
		return
	}

	// before = the captured snapshot. NULL/empty (pre-W6b-2) → no diff.
	var before *string
	_ = s.pool.QueryRow(r.Context(), `
		SELECT source_text FROM wiki_article_source_usage
		 WHERE article_id = $1 AND source_type = $2 AND source_id = $3`,
		articleID, ref.SourceType, ref.SourceID).Scan(&before)
	if before == nil || *before == "" {
		writeJSON(w, http.StatusOK, map[string]any{"available": false})
		return
	}

	// after = knowledge re-gather. A transient failure → no diff (degrade to jump);
	// a successful-but-absent key means the source was genuinely removed (after="").
	texts, err := s.fetchWikiSourceText(r.Context(), bookID, userID, entityID,
		[]map[string]string{{"source_type": ref.SourceType, "source_id": ref.SourceID}})
	if err != nil {
		slog.Error("getWikiStalenessDiff after", "error", err)
		writeJSON(w, http.StatusOK, map[string]any{"available": false})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"available":   true,
		"source_type": ref.SourceType,
		"before":      *before,
		"after":       texts[ref.SourceType+":"+ref.SourceID],
		"approximate": ref.SourceType == "block",
	})
}

// sweepWikiStalenessPublic — POST /v1/glossary/books/{book_id}/wiki/staleness/sweep
// W2 (gap-closure) the FE "Quét lại fingerprint" button: an owner-gated rescan that
// sources the CURRENT recipe versions from knowledge gen-config (the FE/glossary don't
// own them) then runs recipe-drift + kg-drift. Degrades gracefully: knowledge
// unreachable → recipe-drift skipped (recipe_swept=false), kg-drift self-degrades to 0.
func (s *Server) sweepWikiStalenessPublic(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "unauthorized")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}

	// Source the current versions from knowledge (W2: gen-config now carries them).
	var promptV, pipelineV string
	if status, body, err := s.getWikiGenConfig(r.Context()); err == nil && status == http.StatusOK {
		var cfg struct {
			PromptVersion   string `json:"prompt_version"`
			PipelineVersion string `json:"pipeline_version"`
		}
		if json.Unmarshal(body, &cfg) == nil {
			promptV, pipelineV = cfg.PromptVersion, cfg.PipelineVersion
		}
	}

	recipeSwept := promptV != "" && pipelineV != ""
	recipeFlagged := 0
	if recipeSwept {
		var err error
		recipeFlagged, err = s.sweepRecipeDrift(r.Context(), bookID, promptV, pipelineV)
		if err != nil {
			slog.Error("sweepWikiStalenessPublic recipe", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}

	kgFlagged, err := s.sweepKgDrift(r.Context(), bookID, userID)
	if err != nil {
		slog.Error("sweepWikiStalenessPublic kg", "error", err)
		writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"flagged": recipeFlagged, "kg_flagged": kgFlagged, "recipe_swept": recipeSwept,
	})
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
		// Optional: the book owner's id (the Neo4j tenant key). When present the
		// sweep ALSO runs the KG-neighbourhood drift half (D-WIKI-P2-KG-SWEEP) — it
		// must come from the caller since this is an internal-token endpoint with no
		// JWT user. Absent → recipe-drift only.
		UserID string `json:"user_id"`
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

	kgFlagged := 0
	if req.UserID != "" {
		ownerID, perr := uuid.Parse(req.UserID)
		if perr != nil {
			writeError(w, http.StatusBadRequest, "WIKI_BAD_REQUEST", "invalid user_id")
			return
		}
		// sweepKgDrift already degrades a knowledge-service outage to (0, nil); a
		// non-nil error here is a local DB failure.
		kgFlagged, err = s.sweepKgDrift(r.Context(), bookID, ownerID)
		if err != nil {
			slog.Error("sweepWikiStaleness kg", "error", err)
			writeError(w, http.StatusInternalServerError, "WIKI_INTERNAL", "internal error")
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"flagged": flagged, "kg_flagged": kgFlagged})
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
		   -- D-WIKI-P2-SWEEP-DISMISS-RESWEEP: a dismissed drift stays dismissed while its
		   -- SIGNATURE (the from prompt/pipeline version = source_id) is unchanged. Regen
		   -- changes the from-version → a NEW source_id → re-surfaces. The pending-dedup is
		   -- the ON CONFLICT below; this suppresses re-nagging a DISMISSED same-signature row.
		   AND NOT EXISTS (
		     SELECT 1 FROM wiki_staleness d
		      WHERE d.article_id = wa.article_id
		        AND d.reason_code = 'recipe_drift'
		        AND d.status = 'dismissed'
		        AND d.source_ref->>'source_id' =
		            COALESCE(wa.generation_provenance->'build_inputs'->>'prompt_version','') || '/' ||
		            COALESCE(wa.generation_provenance->'build_inputs'->>'pipeline_version','')
		   )
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
		      OR COALESCE(generation_provenance->'build_inputs'->>'pipeline_version','') <> $3 )
		   -- mirror the dismiss-durable guard so a dismissed same-signature article isn't
		   -- re-flagged "outdated" with no feed row (the badge must track the dismissal).
		   AND NOT EXISTS (
		     SELECT 1 FROM wiki_staleness d
		      WHERE d.article_id = wiki_articles.article_id
		        AND d.reason_code = 'recipe_drift'
		        AND d.status = 'dismissed'
		        AND d.source_ref->>'source_id' =
		            COALESCE(wiki_articles.generation_provenance->'build_inputs'->>'prompt_version','') || '/' ||
		            COALESCE(wiki_articles.generation_provenance->'build_inputs'->>'pipeline_version','')
		   )`,
		bookID, promptV, pipelineV,
	); err != nil {
		return inserted, err
	}
	return inserted, nil
}

// wiki-llm Phase-2 (D-WIKI-P2-KG-SWEEP) — the KG-neighbourhood drift half of the
// pull sweep. The push consumer + recipe-drift sweep can't see a Neo4j relationship
// change (GAP A: KG edits emit no event), and the current neighbourhood lives in
// knowledge-service. This asks knowledge to recompute each article's CURRENT
// kg_neighborhood_hash — by the SAME render path as generation, so an unchanged
// neighbourhood matches byte-for-byte — and records a `kg_drift` row for the ones
// whose stored hash differs. ownerID is the Neo4j tenant key. Idempotent on the
// ledger's partial-unique (article, reason, drifted-from hash). A knowledge-service
// failure degrades to (0, nil): a best-effort sweep skips the KG half rather than
// failing the whole sweep or flagging false drift (PO Q2).
//
// Parity couplings (both inherited from the wiki-gen trigger, untested here): the
// current hash matches the stored one only while (a) the orchestrator gathers KG with
// DEFAULT_KG_LIMIT (the knowledge endpoint hardcodes the same default) and (b) the
// book resolves to the SAME project the article was generated under — single project
// per book/user. A custom kg_limit or a multi-project book could false-flag; see
// D-WIKI-P2-KG-SWEEP-PROJECT-PARITY.
func (s *Server) sweepKgDrift(ctx context.Context, bookID, ownerID uuid.UUID) (int, error) {
	type article struct {
		articleID  uuid.UUID
		entityID   string
		storedHash string
	}
	rows, err := s.pool.Query(ctx, `
		SELECT wa.article_id, wa.entity_id::text,
		       COALESCE(wa.generation_provenance->'build_inputs'->>'kg_neighborhood_hash','')
		  FROM wiki_articles wa
		 WHERE wa.book_id = $1 AND wa.generation_status IS NOT NULL
		   AND wa.generation_provenance->'build_inputs' ? 'kg_neighborhood_hash'`,
		bookID)
	if err != nil {
		return 0, err
	}
	var arts []article
	entitySet := make(map[string]struct{})
	for rows.Next() {
		var a article
		if err := rows.Scan(&a.articleID, &a.entityID, &a.storedHash); err != nil {
			rows.Close()
			return 0, err
		}
		arts = append(arts, a)
		entitySet[a.entityID] = struct{}{}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}
	if len(arts) == 0 {
		return 0, nil
	}

	entityIDs := make([]string, 0, len(entitySet))
	for id := range entitySet {
		entityIDs = append(entityIDs, id)
	}
	// Fetch current hashes in bounded chunks. The kg-hashes endpoint does one Neo4j
	// read per entity, so a single huge request can exceed the knowledge client's
	// timeout and silently skip the WHOLE sweep. Chunking keeps each call bounded and
	// limits a transient failure's blast radius to one chunk (the rest still flag,
	// PO Q2 degrade — a failed/absent chunk just leaves those entities unchecked).
	const kgChunk = 50
	current := make(map[string]string, len(entityIDs))
	for start := 0; start < len(entityIDs); start += kgChunk {
		end := min(start+kgChunk, len(entityIDs))
		part, err := s.fetchKgHashes(ctx, bookID, ownerID, entityIDs[start:end])
		if err != nil {
			slog.Warn("sweepKgDrift: kg-hashes chunk failed, skipping", "error", err)
			continue
		}
		maps.Copy(current, part)
	}

	flagged := 0
	for _, a := range arts {
		cur, ok := current[a.entityID]
		// A missing current hash (knowledge omitted the entity — KG unavailable — or
		// its chunk failed), an unchanged hash, or no stored baseline → not drift.
		// Only a present, DIFFERENT current hash is a genuine KG change.
		if a.storedHash == "" || !ok || cur == a.storedHash {
			continue
		}
		// D-WIKI-P2-SWEEP-DISMISS-RESWEEP: kg_drift's signature is (storedHash → cur).
		// source_id keys only on storedHash, so fold current_hash into the dismiss guard:
		// a dismissed row stays dismissed only while BOTH match (same baseline, same drifted-
		// to hash); a NEW current hash (cur changed) is a genuinely new drift → re-surfaces.
		tag, err := s.pool.Exec(ctx, `
			INSERT INTO wiki_staleness (article_id, reason_code, source_ref, severity)
			SELECT $1, 'kg_drift',
			       jsonb_build_object('source_type','kg','source_id',$2::text,'current_hash',$3::text),
			       'content'
			 WHERE NOT EXISTS (
			   SELECT 1 FROM wiki_staleness d
			    WHERE d.article_id = $1
			      AND d.reason_code = 'kg_drift'
			      AND d.status = 'dismissed'
			      AND d.source_ref->>'source_id' = $2::text
			      AND d.source_ref->>'current_hash' = $3::text
			 )
			ON CONFLICT (article_id, reason_code, (source_ref->>'source_id'))
			  WHERE status = 'pending' DO NOTHING`,
			a.articleID, a.storedHash, cur)
		if err != nil {
			return flagged, err
		}
		// Only (re-)flag the article when a fresh pending row was actually inserted — a
		// dismiss-suppressed or already-pending drift must not re-raise the "outdated" badge.
		if tag.RowsAffected() == 1 {
			flagged++
			if _, err := s.pool.Exec(ctx,
				`UPDATE wiki_articles SET is_knowledge_stale = true
				  WHERE article_id = $1 AND is_knowledge_stale = false`,
				a.articleID,
			); err != nil {
				return flagged, err
			}
		}
	}
	return flagged, nil
}
