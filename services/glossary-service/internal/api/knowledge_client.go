package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
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
