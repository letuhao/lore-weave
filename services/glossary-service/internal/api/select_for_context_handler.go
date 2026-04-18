package api

// POST /internal/books/{book_id}/select-for-context
//
// Tiered glossary selector used by the knowledge-service L2 fallback
// (KSA §4.2.5). Runs a sequence of queries against glossary_entities
// deduping across tiers and respecting per-call entity / token budgets.
//
// Trust model: the caller is authenticated via X-Internal-Token
// (requireInternalToken middleware on the /internal/ route group).
// user_id is sent in the body but not re-verified here — glossary-service
// has no user_id column on glossary_entities; ownership flows through
// book ownership which is assumed to be validated by the caller
// (knowledge-service) before issuing the request.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// ── request / response types ────────────────────────────────────────────────

type selectForContextRequest struct {
	UserID      string   `json:"user_id"`
	Query       string   `json:"query"`
	MaxEntities int      `json:"max_entities"`
	MaxTokens   int      `json:"max_tokens"`
	ExcludeIDs  []string `json:"exclude_ids"`
}

type glossaryEntityForContext struct {
	EntityID         string   `json:"entity_id"`
	CachedName       *string  `json:"cached_name"`
	CachedAliases    []string `json:"cached_aliases"`
	ShortDescription *string  `json:"short_description"`
	KindCode         string   `json:"kind_code"`
	IsPinned         bool     `json:"is_pinned"`
	Tier             string   `json:"tier"`
	RankScore        float64  `json:"rank_score"`
}

type selectForContextResponse struct {
	Entities            []glossaryEntityForContext `json:"entities"`
	TotalTokensEstimate int                        `json:"total_tokens_estimate"`
}

const (
	pinnedCap          = 10
	defaultMaxEntities = 20
	hardMaxEntities    = 200
	defaultMaxTokens   = 1000
	hardMaxTokens      = 10000
	// dedupeCushion: each tier's SQL LIMIT is bumped by this amount so
	// that rows already selected by earlier tiers (and therefore skipped
	// by the dedupe check in `add`) don't starve the remaining slot
	// count. Without the cushion, heavy tier overlap can cause the
	// selector to under-fill.
	dedupeCushion = 5
	tierPinned    = "pinned"
	tierExact     = "exact"
	tierFTS       = "fts"
	tierRecent    = "recent"
)

// ── token estimation ────────────────────────────────────────────────────────

func estimateEntityTokens(e *glossaryEntityForContext) int {
	var size int
	if e.CachedName != nil {
		size += len(*e.CachedName)
	}
	for _, a := range e.CachedAliases {
		size += len(a) + 1
	}
	if e.ShortDescription != nil {
		size += len(*e.ShortDescription)
	}
	if size == 0 {
		return 1
	}
	// Rough 1-token-per-4-bytes heuristic (matches knowledge-service).
	t := size / 4
	if t < 1 {
		t = 1
	}
	return t
}

// ── handler ─────────────────────────────────────────────────────────────────

func (s *Server) internalSelectForContext(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}

	var req selectForContextRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	req.Query = strings.TrimSpace(req.Query)

	// Clamp budgets.
	if req.MaxEntities <= 0 {
		req.MaxEntities = defaultMaxEntities
	}
	if req.MaxEntities > hardMaxEntities {
		req.MaxEntities = hardMaxEntities
	}
	if req.MaxTokens <= 0 {
		req.MaxTokens = defaultMaxTokens
	}
	if req.MaxTokens > hardMaxTokens {
		req.MaxTokens = hardMaxTokens
	}

	// Parse and validate exclude_ids as UUIDs — invalid entries are
	// silently dropped to stay forgiving with upstream callers that
	// might pass strings from cache.
	excluded := make([]uuid.UUID, 0, len(req.ExcludeIDs))
	for _, s := range req.ExcludeIDs {
		if u, err := uuid.Parse(s); err == nil {
			excluded = append(excluded, u)
		}
	}

	ctx := r.Context()

	selected := make([]glossaryEntityForContext, 0, req.MaxEntities)
	seen := make(map[string]struct{}, req.MaxEntities)
	// `excludedList` mirrors `seen` as a deterministic []uuid.UUID slice
	// so each tier's NOT-ANY filter sees a stable value (map iteration
	// order is randomized, which would otherwise churn Postgres's plan
	// cache). MUST be non-nil — pgx serializes a nil []uuid.UUID as SQL
	// NULL, and `NOT (entity_id = ANY(NULL))` evaluates to NULL for
	// every row, filtering out all matches.
	excludedList := make([]uuid.UUID, 0, len(excluded)+req.MaxEntities)
	excludedList = append(excludedList, excluded...)
	for _, u := range excluded {
		seen[u.String()] = struct{}{}
	}
	tokensUsed := 0

	add := func(row glossaryEntityForContext, tier string, rank float64) bool {
		if _, dup := seen[row.EntityID]; dup {
			return false
		}
		row.Tier = tier
		row.RankScore = rank
		tokens := estimateEntityTokens(&row)
		if tokensUsed+tokens > req.MaxTokens && len(selected) > 0 {
			return false // budget exhausted; stop accumulating
		}
		seen[row.EntityID] = struct{}{}
		if u, err := uuid.Parse(row.EntityID); err == nil {
			excludedList = append(excludedList, u)
		}
		selected = append(selected, row)
		tokensUsed += tokens
		return len(selected) < req.MaxEntities
	}

	remaining := func() int {
		r := req.MaxEntities - len(selected)
		if r <= 0 {
			return 0
		}
		return r + dedupeCushion
	}

	budgetExhausted := func() bool {
		return len(selected) >= req.MaxEntities || tokensUsed >= req.MaxTokens
	}

	// ── Tier 0: pinned ─────────────────────────────────────────────────────
	if err := s.queryPinnedTier(ctx, bookID, excludedList, pinnedCap, add); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "pinned query failed")
		return
	}
	if budgetExhausted() {
		s.writeContextResponse(w, selected, tokensUsed)
		return
	}

	// ── Tier 1 + Tier 2 only run when there is a query ────────────────────
	hadQuery := req.Query != ""
	if hadQuery {
		if err := s.queryExactTier(ctx, bookID, excludedList, req.Query, remaining(), add); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "exact query failed")
			return
		}
		if budgetExhausted() {
			s.writeContextResponse(w, selected, tokensUsed)
			return
		}

		if err := s.queryFTSTier(ctx, bookID, excludedList, req.Query, remaining(), add); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "fts query failed")
			return
		}
		if budgetExhausted() {
			s.writeContextResponse(w, selected, tokensUsed)
			return
		}
	}

	// ── Tier 3: recent fallback. Only runs when:
	//    (a) no query was given — caller wants a general "what's in this
	//        book" snapshot (chat with no user turn yet), or
	//    (b) a query was given but produced zero results — last-resort
	//        filler to avoid returning an empty context.
	// Running it unconditionally (earlier behaviour) polluted relevant
	// query results with random recently-edited entities.
	if !hadQuery || len(selected) == 0 {
		if err := s.queryRecentTier(ctx, bookID, excludedList, remaining(), add); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "recent query failed")
			return
		}
	}

	s.writeContextResponse(w, selected, tokensUsed)
}

func (s *Server) writeContextResponse(w http.ResponseWriter, selected []glossaryEntityForContext, tokens int) {
	writeJSON(w, http.StatusOK, selectForContextResponse{
		Entities:            selected,
		TotalTokensEstimate: tokens,
	})
}

// ── tier queries ────────────────────────────────────────────────────────────

const selectCols = `
  e.entity_id, e.cached_name, e.cached_aliases, e.short_description,
  ek.code AS kind_code, e.is_pinned_for_context
`

func (s *Server) scanContextRow(rows pgx.Rows, extraRank *float64) (glossaryEntityForContext, error) {
	var row glossaryEntityForContext
	if extraRank != nil {
		if err := rows.Scan(
			&row.EntityID, &row.CachedName, &row.CachedAliases,
			&row.ShortDescription, &row.KindCode, &row.IsPinned, extraRank,
		); err != nil {
			return row, err
		}
	} else {
		if err := rows.Scan(
			&row.EntityID, &row.CachedName, &row.CachedAliases,
			&row.ShortDescription, &row.KindCode, &row.IsPinned,
		); err != nil {
			return row, err
		}
	}
	if row.CachedAliases == nil {
		row.CachedAliases = []string{}
	}
	return row, nil
}

func (s *Server) queryPinnedTier(
	ctx context.Context, bookID uuid.UUID, exclude []uuid.UUID, limit int,
	add func(glossaryEntityForContext, string, float64) bool,
) error {
	query := fmt.Sprintf(`
		SELECT %s
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		  AND e.is_pinned_for_context = true
		  AND NOT (e.entity_id = ANY($2::uuid[]))
		ORDER BY e.updated_at DESC
		LIMIT $3`, selectCols)
	rows, err := s.pool.Query(ctx, query, bookID, exclude, limit)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		row, err := s.scanContextRow(rows, nil)
		if err != nil {
			return err
		}
		if !add(row, tierPinned, 1.0) {
			break
		}
	}
	return rows.Err()
}

func (s *Server) queryExactTier(
	ctx context.Context, bookID uuid.UUID, exclude []uuid.UUID, q string, limit int,
	add func(glossaryEntityForContext, string, float64) bool,
) error {
	if limit <= 0 {
		return nil
	}
	query := fmt.Sprintf(`
		SELECT %s
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		  AND NOT (e.entity_id = ANY($2::uuid[]))
		  AND (
		    lower(e.cached_name) = lower($3)
		    OR EXISTS (
		      SELECT 1 FROM unnest(e.cached_aliases) a
		      WHERE lower(a) = lower($3)
		    )
		  )
		ORDER BY e.updated_at DESC
		LIMIT $4`, selectCols)
	rows, err := s.pool.Query(ctx, query, bookID, exclude, q, limit)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		row, err := s.scanContextRow(rows, nil)
		if err != nil {
			return err
		}
		if !add(row, tierExact, 0.9) {
			break
		}
	}
	return rows.Err()
}

func (s *Server) queryFTSTier(
	ctx context.Context, bookID uuid.UUID, exclude []uuid.UUID, q string, limit int,
	add func(glossaryEntityForContext, string, float64) bool,
) error {
	if limit <= 0 {
		return nil
	}
	// D-T2-02: ts_rank_cd (cover density) is higher-quality than the
	// frequency-only ts_rank for multi-word queries; for single-word
	// queries it degrades to equivalent semantics so we don't lose
	// anything. Normalization flag 33 = 1|32:
	//   1  → divide by (1 + log(doc_len))  — stops long descriptions
	//                                        from outranking short-name
	//                                        matches
	//   32 → scale to [0,1] via rank / (rank + 1) — bounded output for
	//                                              future cross-tier
	//                                              score blending
	// search_vector is a tsvector with positions (default); ts_rank_cd
	// requires positions, which we already have.
	query := fmt.Sprintf(`
		SELECT %s,
		       ts_rank_cd(e.search_vector, plainto_tsquery('simple', $3), 33) AS rank
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		  AND NOT (e.entity_id = ANY($2::uuid[]))
		  AND e.search_vector @@ plainto_tsquery('simple', $3)
		ORDER BY rank DESC
		LIMIT $4`, selectCols)
	rows, err := s.pool.Query(ctx, query, bookID, exclude, q, limit)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var rank float64
		row, err := s.scanContextRow(rows, &rank)
		if err != nil {
			return err
		}
		if !add(row, tierFTS, float64(rank)) {
			break
		}
	}
	return rows.Err()
}

func (s *Server) queryRecentTier(
	ctx context.Context, bookID uuid.UUID, exclude []uuid.UUID, limit int,
	add func(glossaryEntityForContext, string, float64) bool,
) error {
	if limit <= 0 {
		return nil
	}
	query := fmt.Sprintf(`
		SELECT %s
		FROM glossary_entities e
		JOIN entity_kinds ek ON ek.kind_id = e.kind_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		  AND NOT (e.entity_id = ANY($2::uuid[]))
		ORDER BY e.updated_at DESC
		LIMIT $3`, selectCols)
	rows, err := s.pool.Query(ctx, query, bookID, exclude, limit)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		row, err := s.scanContextRow(rows, nil)
		if err != nil {
			return err
		}
		if !add(row, tierRecent, 0.1) {
			break
		}
	}
	return rows.Err()
}
