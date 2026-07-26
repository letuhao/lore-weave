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
	// Language (S6, optional): augment each entity's aliases with its per-language
	// alias SET (source ∪ target, deduped). Omitted → source aliases only.
	Language string `json:"language"`
}

// composePerLanguageAliases augments each item's CachedAliases with the per-language
// alias SET (the `aliases` attr's translation in `language`, a JSON array) when
// `language` is set. Source ∪ target, de-duped. Best-effort — a query error leaves the
// source aliases untouched (context enrichment must never break the turn). Used by both
// internal context endpoints (select-for-context + entities/by-ids).
func (s *Server) composePerLanguageAliases(ctx context.Context, bookID uuid.UUID, items []glossaryEntityForContext, language string) {
	language = strings.TrimSpace(language)
	if language == "" || len(items) == 0 {
		return
	}
	ids := make([]uuid.UUID, 0, len(items))
	idx := make(map[string]int, len(items))
	for i, it := range items {
		if id, err := uuid.Parse(it.EntityID); err == nil {
			ids = append(ids, id)
			idx[it.EntityID] = i
		}
	}
	if len(ids) == 0 {
		return
	}
	rows, err := s.pool.Query(ctx, `
		SELECT e.entity_id, t.value
		FROM glossary_entities e
		JOIN entity_attribute_values av ON av.entity_id = e.entity_id
		JOIN book_attributes ba ON ba.attr_id = av.attr_def_id
		JOIN attribute_translations t ON t.attr_value_id = av.attr_value_id
		WHERE e.book_id = $1 AND e.entity_id = ANY($2::uuid[])
		  AND ba.code = 'aliases' AND t.language_code = $3 AND t.value != ''`,
		bookID, ids, language)
	if err != nil {
		return // best-effort
	}
	defer rows.Close()
	for rows.Next() {
		var eid, val string
		if rows.Scan(&eid, &val) != nil {
			continue
		}
		var langAliases []string
		if json.Unmarshal([]byte(val), &langAliases) != nil {
			continue
		}
		if i, ok := idx[eid]; ok {
			items[i].CachedAliases = dedupStrings(append(append([]string{}, items[i].CachedAliases...), langAliases...))
		}
	}
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
		// T2-polish-2a: parsePathUUID writes the error itself; count
		// the outcome here so dashboards see invalid path UUIDs.
		SelectForContextTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}

	var req selectForContextRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		SelectForContextTotal.WithLabelValues(OutcomeInvalidBody).Inc()
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	resp, err := s.selectGlossaryForContext(r.Context(), bookID, req)
	if err != nil {
		SelectForContextTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", err.Error())
		return
	}
	// S6: augment aliases with the requested language's alias set (best-effort).
	s.composePerLanguageAliases(r.Context(), bookID, resp.Entities, req.Language)
	SelectForContextTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, resp)
}

// selectGlossaryForContext is the non-HTTP core of the tiered selector
// (pinned → exact → fts → recent, with per-call entity/token budgets). It trims
// + clamps the request itself, so the internal HTTP endpoint and the
// glossary_search MCP tool get identical bounds. The caller is responsible for
// any ownership check — this layer trusts that book access was authorised
// upstream (the MCP tool calls checkGrant first; the internal HTTP route
// is X-Internal-Token gated).
func (s *Server) selectGlossaryForContext(ctx context.Context, bookID uuid.UUID, req selectForContextRequest) (selectForContextResponse, error) {
	req.Query = strings.TrimSpace(req.Query)
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

	// Parse exclude_ids as UUIDs — invalid entries are silently dropped to stay
	// forgiving with callers that might pass strings from a cache.
	excluded := make([]uuid.UUID, 0, len(req.ExcludeIDs))
	for _, e := range req.ExcludeIDs {
		if u, err := uuid.Parse(e); err == nil {
			excluded = append(excluded, u)
		}
	}

	selected := make([]glossaryEntityForContext, 0, req.MaxEntities)
	seen := make(map[string]struct{}, req.MaxEntities)
	// `excludedList` MUST be non-nil — pgx serializes a nil []uuid.UUID as SQL
	// NULL, and `NOT (entity_id = ANY(NULL))` evaluates to NULL for every row,
	// filtering out all matches.
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
			return false
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
	result := func() selectForContextResponse {
		return selectForContextResponse{Entities: selected, TotalTokensEstimate: tokensUsed}
	}

	if err := s.queryPinnedTier(ctx, bookID, excludedList, pinnedCap, add); err != nil {
		return selectForContextResponse{}, fmt.Errorf("pinned query failed: %w", err)
	}
	if budgetExhausted() {
		return result(), nil
	}

	hadQuery := req.Query != ""
	if hadQuery {
		if err := s.queryExactTier(ctx, bookID, excludedList, req.Query, remaining(), add); err != nil {
			return selectForContextResponse{}, fmt.Errorf("exact query failed: %w", err)
		}
		if budgetExhausted() {
			return result(), nil
		}
		if err := s.queryFTSTier(ctx, bookID, excludedList, req.Query, remaining(), add); err != nil {
			return selectForContextResponse{}, fmt.Errorf("fts query failed: %w", err)
		}
		if budgetExhausted() {
			return result(), nil
		}
	}

	// Tier 3 recent fallback: only when no query was given (general snapshot) or
	// a query produced zero results (avoid an empty context).
	if !hadQuery || len(selected) == 0 {
		if err := s.queryRecentTier(ctx, bookID, excludedList, remaining(), add); err != nil {
			return selectForContextResponse{}, fmt.Errorf("recent query failed: %w", err)
		}
	}

	return result(), nil
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
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
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
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
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
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
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
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
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
