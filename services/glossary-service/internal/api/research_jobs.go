package api

// D-BATCH-RESEARCH-JOB M1 — async batch entity-research job: CRUD + cost estimate.
//
// A job researches up to `max_entities` entities of one book kind on the web (one paid
// BYOK search per entity, reusing researchOneEntity), attaching sourced 'reference'
// evidence. M1 is the create/read surface + a pre-flight estimate; jobs sit `pending`
// until the M2 worker drains them. Lifecycle actions (pause/resume/cancel) land in M2
// with the worker that gives them meaning.
//
// Tenancy: per-book + owner. create/lifecycle = Manage; reads = View. kind_id is a
// book_kinds.book_kind_id (the post-G4 entity kind ref). Cost is capped by entity count
// (web search returns no per-call cost — BYOK); est_cost_usd is INDICATIVE only.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// formatUSD renders a USD amount with the table's numeric(10,4) precision (4 dp).
func formatUSD(v float64) string { return fmt.Sprintf("%.4f", v) }

// parsePositiveQueryInt reads a positive int query param; 0 when absent/invalid/non-positive.
func parsePositiveQueryInt(r *http.Request, key string) int {
	n, err := strconv.Atoi(strings.TrimSpace(r.URL.Query().Get(key)))
	if err != nil || n < 0 {
		return 0
	}
	return n
}

const (
	// webSearchEstUSDPerQuery is an INDICATIVE flat per-search price for the cost estimate
	// only — provider-registry's BYOK web-search returns no real cost, so this never drives
	// billing or a budget cap (the cap is max_entities). Tune as providers' pricing moves.
	webSearchEstUSDPerQuery = 0.01
	// researchJobMaxEntitiesHardCap bounds one job regardless of the requested max_entities
	// — a runaway backstop (a kind with thousands of entities can't be researched in one job).
	researchJobMaxEntitiesHardCap = 500
)

type researchJobView struct {
	JobID           string  `json:"job_id"`
	BookID          string  `json:"book_id"`
	KindID          string  `json:"kind_id"`
	QueryTemplate   string  `json:"query_template"`
	MaxResults      int     `json:"max_results"`
	MaxEntities     int     `json:"max_entities"`
	EstCostUSD      string  `json:"est_cost_usd"`
	Status          string  `json:"status"`
	ItemsTotal      int     `json:"items_total"`
	ItemsProcessed  int     `json:"items_processed"`
	SearchesRun     int     `json:"searches_run"`
	SourcesAttached int     `json:"sources_attached"`
	ErrorMessage    *string `json:"error_message,omitempty"`
	CreatedAt       string  `json:"created_at"`
	UpdatedAt       string  `json:"updated_at"`
	CompletedAt     *string `json:"completed_at,omitempty"`
}

type createResearchJobIn struct {
	QueryTemplate string `json:"query_template"`
	MaxResults    int    `json:"max_results"`
	MaxEntities   int    `json:"max_entities"`
}

// createResearchJob — POST /v1/glossary/books/{book_id}/kinds/{kind_id}/research-jobs.
// Manage-gated. Validates the kind, scopes items_total to the live entity count, and
// inserts a `pending` job. A second live job for the same (book, kind) → 409.
func (s *Server) createResearchJob(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	kindID, ok := parsePathUUID(w, r, "kind_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantManage) {
		return
	}

	var in createResearchJobIn
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "invalid JSON body")
		return
	}
	query := strings.TrimSpace(in.QueryTemplate)
	if query == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "query_template is required")
		return
	}
	if len(query) > 500 {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "query_template must be at most 500 characters")
		return
	}
	maxResults := clampDeepResearchMax(in.MaxResults)
	maxEntities := in.MaxEntities
	if maxEntities <= 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "max_entities must be at least 1")
		return
	}
	if maxEntities > researchJobMaxEntitiesHardCap {
		maxEntities = researchJobMaxEntitiesHardCap
	}

	live, err := s.bookKindIsLive(r.Context(), bookID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind lookup failed")
		return
	}
	if !live {
		writeError(w, http.StatusNotFound, "GLOSS_KIND_NOT_FOUND", "kind not found in this book")
		return
	}
	entityCount, err := s.countLiveEntitiesOfKind(r.Context(), bookID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity count failed")
		return
	}
	itemsTotal := maxEntities
	if entityCount < itemsTotal {
		itemsTotal = entityCount
	}
	if itemsTotal == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_NO_ENTITIES", "this kind has no entities to research")
		return
	}
	estCost := float64(itemsTotal) * webSearchEstUSDPerQuery

	view, err := s.insertResearchJob(r.Context(), bookID, userID, kindID, query, maxResults, maxEntities, itemsTotal, estCost)
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "GLOSS_JOB_EXISTS", "a research job for this kind is already running — cancel it first")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "could not create the research job")
		return
	}
	writeJSON(w, http.StatusCreated, view)
}

// getResearchJob — GET /v1/glossary/books/{book_id}/research-jobs/{job_id}. View-gated
// status poll for the FE. 404 if the job is not in this book (no cross-book oracle).
func (s *Server) getResearchJob(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	jobID, ok := parsePathUUID(w, r, "job_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	view, found, err := s.loadResearchJob(r.Context(), bookID, jobID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "job lookup failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_JOB_NOT_FOUND", "research job not found")
		return
	}
	writeJSON(w, http.StatusOK, view)
}

// listResearchJobs — GET /v1/glossary/books/{book_id}/research-jobs[?status=]. View-gated.
func (s *Server) listResearchJobs(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	status := strings.TrimSpace(r.URL.Query().Get("status"))
	jobs, err := s.loadResearchJobs(r.Context(), bookID, status)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "job list failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"jobs": jobs})
}

// researchEstimate — GET /v1/glossary/books/{book_id}/kinds/{kind_id}/research-estimate
// ?max_entities=N. View-gated pre-flight estimate so the FE shows the (indicative) cost
// + the actual entity count BEFORE the user confirms a job. No write.
func (s *Server) researchEstimate(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	kindID, ok := parsePathUUID(w, r, "kind_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	entityCount, err := s.countLiveEntitiesOfKind(r.Context(), bookID, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity count failed")
		return
	}
	planned := entityCount
	if mx := parsePositiveQueryInt(r, "max_entities"); mx > 0 && mx < planned {
		planned = mx
	}
	if planned > researchJobMaxEntitiesHardCap {
		planned = researchJobMaxEntitiesHardCap
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"entity_count":       entityCount,
		"planned_entities":   planned,
		"est_cost_usd":       formatUSD(float64(planned) * webSearchEstUSDPerQuery),
		"per_search_usd":     formatUSD(webSearchEstUSDPerQuery),
		"hard_cap":           researchJobMaxEntitiesHardCap,
		"cost_is_indicative": true,
	})
}

// ── cores ─────────────────────────────────────────────────────────────────────

func (s *Server) bookKindIsLive(ctx context.Context, bookID, kindID uuid.UUID) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM book_kinds WHERE book_id=$1 AND book_kind_id=$2 AND deprecated_at IS NULL)`,
		bookID, kindID).Scan(&exists)
	return exists, err
}

func (s *Server) countLiveEntitiesOfKind(ctx context.Context, bookID, kindID uuid.UUID) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT count(*) FROM glossary_entities WHERE book_id=$1 AND kind_id=$2 AND deleted_at IS NULL`,
		bookID, kindID).Scan(&n)
	return n, err
}

func (s *Server) insertResearchJob(ctx context.Context, bookID, ownerID, kindID uuid.UUID, query string, maxResults, maxEntities, itemsTotal int, estCost float64) (researchJobView, error) {
	var jobID uuid.UUID
	err := s.pool.QueryRow(ctx, `
		INSERT INTO entity_research_jobs
			(book_id, owner_user_id, kind_id, query_template, max_results, max_entities, est_cost_usd, items_total, status)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'pending')
		RETURNING job_id`,
		bookID, ownerID, kindID, query, maxResults, maxEntities, estCost, itemsTotal).Scan(&jobID)
	if err != nil {
		return researchJobView{}, err
	}
	view, _, lerr := s.loadResearchJob(ctx, bookID, jobID)
	return view, lerr
}

// researchJobSelectCols is the shared projection for single + list reads.
const researchJobSelectCols = `job_id, book_id, kind_id, query_template, max_results, max_entities,
	est_cost_usd, status, items_total, items_processed, searches_run, sources_attached,
	error_message, created_at, updated_at, completed_at`

func scanResearchJob(row interface{ Scan(...any) error }) (researchJobView, error) {
	var (
		v           researchJobView
		jobID       uuid.UUID
		bookID      uuid.UUID
		kindID      uuid.UUID
		estCost     float64
		errMsg      *string
		createdAt   time.Time
		updatedAt   time.Time
		completedAt *time.Time
	)
	if err := row.Scan(&jobID, &bookID, &kindID, &v.QueryTemplate, &v.MaxResults, &v.MaxEntities,
		&estCost, &v.Status, &v.ItemsTotal, &v.ItemsProcessed, &v.SearchesRun, &v.SourcesAttached,
		&errMsg, &createdAt, &updatedAt, &completedAt); err != nil {
		return researchJobView{}, err
	}
	v.JobID = jobID.String()
	v.BookID = bookID.String()
	v.KindID = kindID.String()
	v.EstCostUSD = formatUSD(estCost)
	v.ErrorMessage = errMsg
	v.CreatedAt = createdAt.UTC().Format(time.RFC3339)
	v.UpdatedAt = updatedAt.UTC().Format(time.RFC3339)
	if completedAt != nil {
		c := completedAt.UTC().Format(time.RFC3339)
		v.CompletedAt = &c
	}
	return v, nil
}

func (s *Server) loadResearchJob(ctx context.Context, bookID, jobID uuid.UUID) (researchJobView, bool, error) {
	row := s.pool.QueryRow(ctx,
		`SELECT `+researchJobSelectCols+` FROM entity_research_jobs WHERE book_id=$1 AND job_id=$2`,
		bookID, jobID)
	v, err := scanResearchJob(row)
	if isNoRows(err) {
		return researchJobView{}, false, nil
	}
	if err != nil {
		return researchJobView{}, false, err
	}
	return v, true, nil
}

func (s *Server) loadResearchJobs(ctx context.Context, bookID uuid.UUID, status string) ([]researchJobView, error) {
	q := `SELECT ` + researchJobSelectCols + ` FROM entity_research_jobs WHERE book_id=$1`
	args := []any{bookID}
	if status != "" {
		q += ` AND status=$2`
		args = append(args, status)
	}
	q += ` ORDER BY created_at DESC`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]researchJobView, 0)
	for rows.Next() {
		v, err := scanResearchJob(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, rows.Err()
}
