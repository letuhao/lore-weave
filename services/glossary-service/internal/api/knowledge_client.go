package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/observability"
)

// knowledgeHTTPClient is shared across requests; 5 s timeout prevents
// goroutine leaks when knowledge-service is slow or unreachable.
// Phase 6c — traced transport so outbound calls carry a W3C traceparent.
var knowledgeHTTPClient = &http.Client{Timeout: 5 * time.Second, Transport: observability.HTTPTransport(nil)}

// ── C5 (D4-03) wiki-from-KG read shapes ──────────────────────────────────────
//
// The wiki renderer reads an entity's 1-hop KG neighborhood from
// knowledge-service (the entity-to-entity relationship graph lives only
// in Neo4j, keyed by glossary_entity_id). This is a READ-ONLY surface
// (Q2 LOCKED: wiki/enrichment never write Neo4j canonical content here).
//
// `source_type` is derived server-side (knowledge-service) so the H0
// enriched-vs-canon distinction is computed once and travels intact:
//   - "glossary" — authored canon, confidence == 1.0, validated
//   - "enriched" — quarantined makeup, pending and/or confidence < 1.0

type kgNeighborRelation struct {
	Predicate         string  `json:"predicate"`
	SubjectName       *string `json:"subject_name"`
	SubjectKind       *string `json:"subject_kind"`
	ObjectName        *string `json:"object_name"`
	ObjectKind        *string `json:"object_kind"`
	Confidence        float64 `json:"confidence"`
	PendingValidation bool    `json:"pending_validation"`
	SourceType        string  `json:"source_type"`
}

type kgNeighborhood struct {
	Found              bool                 `json:"found"`
	GlossaryEntityID   string               `json:"glossary_entity_id"`
	Name               *string              `json:"name"`
	Kind               *string              `json:"kind"`
	SourceTypes        []string             `json:"source_types"`
	EntitySourceType   string               `json:"entity_source_type"`
	Relations          []kgNeighborRelation `json:"relations"`
	TotalRelations     int                  `json:"total_relations"`
	RelationsTruncated bool                 `json:"relations_truncated"`
}

// fetchWikiNeighborhood calls the knowledge-service internal
// wiki-neighborhood read endpoint for a single glossary entity.
//
// Graceful degradation (Q6 LOCKED): returns (nil, nil) — NOT an error —
// when knowledge-service is unconfigured or unreachable. A nil result
// signals "no KG neighborhood available"; the renderer then produces a
// minimal attribute-only body rather than failing wiki generation. Only
// a genuinely malformed 200 response is unexpected, and that too
// degrades to nil so a single bad entity never aborts a batch.
func (s *Server) fetchWikiNeighborhood(ctx context.Context, ownerUserID, glossaryEntityID uuid.UUID) (*kgNeighborhood, error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		// Knowledge-service not wired — degrade to nil (minimal body).
		return nil, nil
	}

	body, err := json.Marshal(map[string]any{
		"user_id":            ownerUserID.String(),
		"glossary_entity_id": glossaryEntityID.String(),
		"rel_cap":            200,
	})
	if err != nil {
		return nil, nil
	}

	url := fmt.Sprintf("%s/internal/knowledge/wiki-neighborhood", base)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, nil
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}

	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		// Unreachable / timeout — degrade.
		return nil, nil
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		// Auth failure, 5xx, etc. — degrade rather than abort the batch.
		return nil, nil
	}

	var n kgNeighborhood
	if err := json.NewDecoder(res.Body).Decode(&n); err != nil {
		return nil, nil
	}
	return &n, nil
}

// wiki-llm M6 — the LLM-generation delegate. When a wiki-generate request carries
// a model_ref, glossary delegates to knowledge-service's batch generator instead
// of rendering the deterministic stub. Unlike the read above this is NOT a
// degrade-to-nil path: the user asked to generate, so the upstream status
// (202 accept / 409 active-job / 404 not-indexed) is PROPAGATED to the caller.
func (s *Server) triggerWikiGeneration(
	ctx context.Context, bookID, userID uuid.UUID,
	modelSource, modelRef string, entityIDs []string, maxSpendUSD *float64,
	reviseModelSource, reviseModelRef string,
) (status int, respBody []byte, err error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		return 0, nil, fmt.Errorf("knowledge-service not configured")
	}
	payload := map[string]any{
		"user_id":      userID.String(),
		"model_source": modelSource,
		"model_ref":    modelRef,
		"entity_ids":   entityIDs,
	}
	if maxSpendUSD != nil {
		payload["max_spend_usd"] = *maxSpendUSD
	}
	// W5 — forward the optional revise-model override only when set (both keys
	// together or neither), so knowledge sees null → prose-model fallback.
	if reviseModelRef != "" {
		payload["revise_model_ref"] = reviseModelRef
		payload["revise_model_source"] = reviseModelSource
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return 0, nil, err
	}
	url := fmt.Sprintf("%s/internal/knowledge/books/%s/wiki/generate", base, bookID.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer res.Body.Close()
	respBody, _ = io.ReadAll(io.LimitReader(res.Body, 1<<16))
	return res.StatusCode, respBody, nil
}

// getWikiGenJob fetches the latest wiki-gen job status for (book, user) from
// knowledge-service. Like the trigger this PROPAGATES the upstream status (200
// status body / 404 no-job) rather than degrading — the FE poll needs the real
// code to distinguish "no job yet" (404) from a live job.
func (s *Server) getWikiGenJob(
	ctx context.Context, bookID, userID uuid.UUID,
) (status int, respBody []byte, err error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		return 0, nil, fmt.Errorf("knowledge-service not configured")
	}
	url := fmt.Sprintf("%s/internal/knowledge/books/%s/wiki/job?user_id=%s",
		base, bookID.String(), userID.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return 0, nil, err
	}
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer res.Body.Close()
	respBody, _ = io.ReadAll(io.LimitReader(res.Body, 1<<16))
	return res.StatusCode, respBody, nil
}

// getWikiGenConfig fetches the flat per-article wiki-gen cost estimate from
// knowledge-service (D-WIKI-P2B-COST-ESTIMATE). PROPAGATES the upstream status+body
// (a read the FE needs verbatim); errors when knowledge-service is unconfigured.
func (s *Server) getWikiGenConfig(ctx context.Context) (status int, respBody []byte, err error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		return 0, nil, fmt.Errorf("knowledge-service not configured")
	}
	url := fmt.Sprintf("%s/internal/knowledge/wiki/gen-config", base)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return 0, nil, err
	}
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer res.Body.Close()
	respBody, _ = io.ReadAll(io.LimitReader(res.Body, 1<<16))
	return res.StatusCode, respBody, nil
}

// fetchKgHashes asks knowledge-service to recompute the CURRENT kg_neighborhood_hash
// for each entity (D-WIKI-P2-KG-SWEEP). Knowledge reuses the exact generation render
// path so the hash compares byte-for-byte with the stored one; entities whose KG is
// unavailable are OMITTED by knowledge (not empty-hashed). Unlike fetchWikiNeighborhood
// this does NOT degrade-to-nil silently — it returns an error so the sweep can SKIP
// the KG half rather than flag false drift (the caller decides; ownerID = Neo4j tenant).
func (s *Server) fetchKgHashes(
	ctx context.Context, bookID, ownerID uuid.UUID, entityIDs []string,
) (map[string]string, error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		return nil, fmt.Errorf("knowledge-service not configured")
	}
	body, err := json.Marshal(map[string]any{
		"user_id":    ownerID.String(),
		"entity_ids": entityIDs,
	})
	if err != nil {
		return nil, err
	}
	url := fmt.Sprintf("%s/internal/knowledge/books/%s/wiki/kg-hashes", base, bookID.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("kg-hashes: knowledge returned %d", res.StatusCode)
	}
	var parsed struct {
		Hashes map[string]string `json:"hashes"`
	}
	if err := json.NewDecoder(res.Body).Decode(&parsed); err != nil {
		return nil, err
	}
	return parsed.Hashes, nil
}

// wikiGenJobAction drives a resume/cancel on a wiki-gen job. ``action`` is the
// path verb ("resume" | "cancel"); the user_id travels in the body so
// knowledge-service can re-assert ownership. PROPAGATES the upstream status
// (202/200 ok · 404 not-owner · 409 wrong-state).
func (s *Server) wikiGenJobAction(
	ctx context.Context, bookID, userID, jobID uuid.UUID, action string,
) (status int, respBody []byte, err error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		return 0, nil, fmt.Errorf("knowledge-service not configured")
	}
	body, err := json.Marshal(map[string]any{"user_id": userID.String()})
	if err != nil {
		return 0, nil, err
	}
	url := fmt.Sprintf("%s/internal/knowledge/books/%s/wiki/job/%s/%s",
		base, bookID.String(), jobID.String(), action)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer res.Body.Close()
	respBody, _ = io.ReadAll(io.LimitReader(res.Body, 1<<16))
	return res.StatusCode, respBody, nil
}

// fetchWikiSourceText (W6b-2b) — the CURRENT source text per source (the change-diff
// "after"), re-gathered by knowledge through the same context path as generation.
// Returns the {key→text} map; errors when knowledge is unconfigured/unreachable or
// returns non-200 (the caller then degrades to no-diff).
func (s *Server) fetchWikiSourceText(
	ctx context.Context, bookID, userID uuid.UUID, entityID string, sources []map[string]string,
) (map[string]string, error) {
	base := strings.TrimRight(s.cfg.KnowledgeServiceURL, "/")
	if base == "" {
		return nil, fmt.Errorf("knowledge-service not configured")
	}
	body, err := json.Marshal(map[string]any{
		"user_id": userID.String(), "entity_id": entityID, "sources": sources,
	})
	if err != nil {
		return nil, err
	}
	url := fmt.Sprintf("%s/internal/knowledge/books/%s/wiki/source-text", base, bookID.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := knowledgeHTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("source-text upstream %d", res.StatusCode)
	}
	var out struct {
		Texts map[string]string `json:"texts"`
	}
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out.Texts, nil
}

// badEntityIDError marks an invalid client-supplied entity id so the handler can
// map it to a 400 (rather than a generic 500).
type badEntityIDError struct{ id string }

func (e *badEntityIDError) Error() string { return "invalid entity_id: " + e.id }

// parseEntityUUIDs validates client-supplied entity ids are well-formed UUIDs,
// returning a badEntityIDError (→ 400) on the first malformed one.
func parseEntityUUIDs(explicit []string) ([]string, error) {
	ids := make([]string, 0, len(explicit))
	for _, raw := range explicit {
		id, err := uuid.Parse(raw)
		if err != nil {
			return nil, &badEntityIDError{id: raw}
		}
		ids = append(ids, id.String())
	}
	return ids, nil
}

// resolveDelegateEntityIDs picks the entity ids for an LLM wiki-gen delegate.
// When the caller supplies explicit ids (single-article REGENERATE, M7b-2b) those
// are validated AND **scoped to this book** — a client must not regenerate an
// entity from another book/user. The batch path (resolveWikiGenEntities) is
// already book-scoped; mirroring it here means the owner gate covers explicit ids
// too, not just the downstream writeback guard (/review-impl F1). A tampered or
// foreign id is silently filtered out (→ empty slice → the handler's action:none),
// not leaked as "exists / not". Otherwise it falls back to resolving by kind.
//
// Returns (ids, totalMatched): `totalMatched` is the count of candidate
// entities the selection would cover WITHOUT the limit, so a caller can detect
// silent truncation (D-WIKI-M7B-GEN-LIMIT — a book with >limit entities of a
// kind generated only the first `limit` and the banner read "done"). For the
// explicit-id (single-article regenerate) path there is no truncation concept,
// so totalMatched == len(ids).
func (s *Server) resolveDelegateEntityIDs(
	ctx context.Context, bookID uuid.UUID, explicit []string, kindCodes []string, limit int,
) ([]string, int, error) {
	if len(explicit) > 0 {
		parsed, err := parseEntityUUIDs(explicit)
		if err != nil {
			return nil, 0, err
		}
		rows, err := s.pool.Query(ctx,
			// PP-4 (spec 08 R6) — never LLM-generate a wiki biography for a REAL PERSON, even on the
			// explicit single-entity "Regenerate" path. C4/SD-C4: filter the STRUCTURAL is_person flag,
			// not the literal code, so a renamed/custom real-person kind is also excluded (fiction
			// 'character' is is_person=false, so it still generates).
			`SELECT ge.entity_id::text FROM glossary_entities ge
			 JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
			 WHERE ge.book_id=$1 AND ge.entity_id = ANY($2::uuid[])
			   AND ge.deleted_at IS NULL AND ge.status='active'
			   AND NOT ek.is_person`,
			bookID, parsed)
		if err != nil {
			return nil, 0, err
		}
		defer rows.Close()
		var ids []string
		for rows.Next() {
			var id string
			if err := rows.Scan(&id); err != nil {
				return nil, 0, err
			}
			ids = append(ids, id)
		}
		if err := rows.Err(); err != nil {
			return nil, 0, err
		}
		return ids, len(ids), nil
	}
	return s.resolveWikiGenEntities(ctx, bookID, kindCodes, limit)
}

// resolveWikiGenEntities lists the candidate entity ids for an LLM wiki-gen
// delegate: active, non-deleted entities in the book, optionally filtered by
// kind, bounded by limit. The clobber-guard (M5) protects any human-edited
// article downstream, so this selects ALL matching entities (not only ones
// without an article) — the LLM may regenerate a stub.
//
// The second return is the total number of matching entities IGNORING the
// limit (D-WIKI-M7B-GEN-LIMIT), computed by the same predicate so the handler
// can tell the FE how many were dropped by the cap.
func (s *Server) resolveWikiGenEntities(
	ctx context.Context, bookID uuid.UUID, kindCodes []string, limit int,
) ([]string, int, error) {
	// PP-4 (spec 08 R6) — the LLM delegate is the AI-BIOGRAPHY path; never generate a wiki page for a
	// REAL PERSON, even in a wiki-eligible book (cross-book/merged case). PP-3 already blocks the whole
	// diary; this closes the delegate leak PP-4 targets. C4/SD-C4: filter the STRUCTURAL is_person flag
	// (a renamed/custom real-person kind is also excluded; fiction 'character' is_person=false, so it
	// still generates).
	where := `WHERE ge.book_id = $1 AND ge.deleted_at IS NULL AND ge.status = 'active' AND NOT ek.is_person`
	args := []any{bookID}
	if len(kindCodes) > 0 {
		where += ` AND ek.code = ANY($2)`
		args = append(args, kindCodes)
	}
	base := `FROM glossary_entities ge
		JOIN book_kinds ek ON ek.book_kind_id = ge.kind_id
		` + where

	var totalMatched int
	if err := s.pool.QueryRow(ctx,
		`SELECT count(*) `+base, args...,
	).Scan(&totalMatched); err != nil {
		return nil, 0, err
	}

	rows, err := s.pool.Query(ctx,
		fmt.Sprintf(`SELECT ge.entity_id::text `+base+` ORDER BY ge.created_at LIMIT %d`, limit),
		args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, 0, err
		}
		ids = append(ids, id)
	}
	return ids, totalMatched, rows.Err()
}
