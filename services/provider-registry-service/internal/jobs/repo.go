package jobs

// Phase 2b (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). DB CRUD for the
// `llm_jobs` table. The schema lives in internal/migrate/migrate.go;
// repo functions here are the only sanctioned write path.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/provider-registry-service/internal/billing"
)

// Job is the in-memory representation of an `llm_jobs` row. Field names
// + JSON tags mirror the openapi Job schema so the handler can serialize
// directly.
type Job struct {
	JobID       uuid.UUID       `json:"job_id"`
	OwnerUserID uuid.UUID       `json:"-"`
	Operation   string          `json:"operation"`
	Status      string          `json:"status"`
	ModelSource string          `json:"-"`
	ModelRef    uuid.UUID       `json:"-"`
	Input       json.RawMessage `json:"-"`
	Chunking    json.RawMessage `json:"-"`
	Callback    json.RawMessage `json:"-"`
	JobMeta     json.RawMessage `json:"job_meta,omitempty"`
	TraceID     *string         `json:"trace_id,omitempty"`

	ChunksTotal    *int       `json:"-"`
	ChunksDone     int        `json:"-"`
	TokensUsed     int        `json:"-"`
	LastProgressAt *time.Time `json:"-"`

	Result       json.RawMessage `json:"result,omitempty"`
	ErrorCode    *string         `json:"-"`
	ErrorMessage *string         `json:"-"`
	FinishReason *string         `json:"-"`

	SubmittedAt time.Time  `json:"submitted_at"`
	StartedAt   *time.Time `json:"started_at,omitempty"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
	ExpiresAt   time.Time  `json:"-"`

	// Phase 6a — the usage-billing spend reservation held for this job's
	// pre-flight estimate. NULL for jobs submitted before the guardrail, or
	// via a path that does not reserve (stt multipart). json:"-" — internal.
	ReservationID *uuid.UUID `json:"-"`
}

// Repo wraps the pgx pool with typed CRUD over llm_jobs.
type Repo struct {
	pool *pgxpool.Pool
}

func NewRepo(pool *pgxpool.Pool) *Repo {
	return &Repo{pool: pool}
}

// InsertParams captures the request inputs bundled at submit time.
// Mirrors the openapi SubmitJobRequest.
type InsertParams struct {
	// JobID, when non-nil, is used as the row's primary key. The guardrail
	// pre-flight (doSubmitJob) generates the id up front so it can RESERVE
	// against usage-billing before the row exists; a uuid.Nil falls back to
	// a server-generated uuidv7.
	JobID uuid.UUID

	OwnerUserID uuid.UUID
	Operation   string
	ModelSource string
	ModelRef    uuid.UUID
	Input       any // marshaled to JSONB
	Chunking    any // optional, marshaled to JSONB or NULL
	Callback    any // optional, marshaled to JSONB or NULL
	JobMeta     any // optional, marshaled to JSONB or NULL
	TraceID     string

	// ReservationID, when non-nil, is the usage-billing hold this job will
	// reconcile/release on terminal state (Phase 6a).
	ReservationID *uuid.UUID
}

// Insert creates a pending job row and returns the new job_id.
func (r *Repo) Insert(ctx context.Context, p InsertParams) (uuid.UUID, error) {
	inputJSON, err := json.Marshal(p.Input)
	if err != nil {
		return uuid.Nil, fmt.Errorf("marshal input: %w", err)
	}
	var chunkingJSON, callbackJSON, jobMetaJSON []byte
	if p.Chunking != nil {
		chunkingJSON, err = json.Marshal(p.Chunking)
		if err != nil {
			return uuid.Nil, fmt.Errorf("marshal chunking: %w", err)
		}
	}
	if p.Callback != nil {
		callbackJSON, err = json.Marshal(p.Callback)
		if err != nil {
			return uuid.Nil, fmt.Errorf("marshal callback: %w", err)
		}
	}
	if p.JobMeta != nil {
		jobMetaJSON, err = json.Marshal(p.JobMeta)
		if err != nil {
			return uuid.Nil, fmt.Errorf("marshal job_meta: %w", err)
		}
	}
	var traceID *string
	if p.TraceID != "" {
		traceID = &p.TraceID
	}

	// Use the caller-supplied id when present (guardrail pre-flight reserves
	// before insert); otherwise generate a uuidv7 so ordering still holds.
	jobID := p.JobID
	if jobID == uuid.Nil {
		jobID, err = uuid.NewV7()
		if err != nil {
			return uuid.Nil, fmt.Errorf("generate job_id: %w", err)
		}
	}

	_, err = r.pool.Exec(ctx, `
INSERT INTO llm_jobs (job_id, owner_user_id, operation, model_source, model_ref, input, chunking, callback, job_meta, trace_id, reservation_id)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
`, jobID, p.OwnerUserID, p.Operation, p.ModelSource, p.ModelRef,
		inputJSON, chunkingJSON, callbackJSON, jobMetaJSON, traceID, p.ReservationID)
	if err != nil {
		return uuid.Nil, fmt.Errorf("insert llm_jobs: %w", err)
	}
	return jobID, nil
}

// Get fetches a job by id, scoped to owner_user_id (so callers can't
// peek at other users' jobs even if they guess a UUID). Returns
// pgx.ErrNoRows when not found.
func (r *Repo) Get(ctx context.Context, jobID, ownerUserID uuid.UUID) (*Job, error) {
	const sql = `
SELECT job_id, owner_user_id, operation, status, model_source, model_ref,
       input, chunking, callback, job_meta, trace_id,
       chunks_total, chunks_done, tokens_used, last_progress_at,
       result, error_code, error_message, finish_reason,
       submitted_at, started_at, completed_at, expires_at, reservation_id
FROM llm_jobs
WHERE job_id = $1 AND owner_user_id = $2
`
	row := r.pool.QueryRow(ctx, sql, jobID, ownerUserID)
	job := &Job{}
	err := row.Scan(
		&job.JobID, &job.OwnerUserID, &job.Operation, &job.Status,
		&job.ModelSource, &job.ModelRef,
		&job.Input, &job.Chunking, &job.Callback, &job.JobMeta, &job.TraceID,
		&job.ChunksTotal, &job.ChunksDone, &job.TokensUsed, &job.LastProgressAt,
		&job.Result, &job.ErrorCode, &job.ErrorMessage, &job.FinishReason,
		&job.SubmittedAt, &job.StartedAt, &job.CompletedAt, &job.ExpiresAt,
		&job.ReservationID,
	)
	if err != nil {
		return nil, err
	}
	return job, nil
}

// MarkRunning transitions a pending job to running and stamps started_at.
// Returns the rows-affected count so callers can detect concurrent
// transitions (another worker beat us to the row).
func (r *Repo) MarkRunning(ctx context.Context, jobID uuid.UUID) (int64, error) {
	tag, err := r.pool.Exec(ctx, `
UPDATE llm_jobs
SET status = 'running', started_at = now()
WHERE job_id = $1 AND status = 'pending'
`, jobID)
	if err != nil {
		return 0, fmt.Errorf("mark running: %w", err)
	}
	return tag.RowsAffected(), nil
}

// UpdateProgress mutates progress counters mid-stream. Caller drives
// updates; we don't enforce ordering beyond the row-level write.
func (r *Repo) UpdateProgress(
	ctx context.Context,
	jobID uuid.UUID,
	chunksTotal *int,
	chunksDone, tokensUsed int,
) error {
	_, err := r.pool.Exec(ctx, `
UPDATE llm_jobs
SET chunks_total = COALESCE($2, chunks_total),
    chunks_done = $3,
    tokens_used = $4,
    last_progress_at = now()
WHERE job_id = $1
`, jobID, chunksTotal, chunksDone, tokensUsed)
	if err != nil {
		return fmt.Errorf("update progress: %w", err)
	}
	return nil
}

// Finalize transitions the job to a terminal state. The DB-level
// llm_jobs_terminal_consistency CHECK enforces that completed_at is
// non-NULL on terminal status, so we stamp it here.
// Finalize transitions the job to a terminal state. Returns
// rowsAffected so callers can gate side-effects (notifier emission)
// on actually-took-effect transitions — the WHERE-status='running'
// guard means a late finalize after cancel returns 0 and emits nothing.
func (r *Repo) Finalize(
	ctx context.Context,
	jobID uuid.UUID,
	status string, // 'completed' | 'failed' | 'cancelled'
	result any, // marshaled to JSONB; nil leaves NULL
	errorCode, errorMessage, finishReason string,
) (int64, error) {
	if status != "completed" && status != "failed" && status != "cancelled" {
		return 0, fmt.Errorf("invalid terminal status: %q", status)
	}
	var resultJSON []byte
	var err error
	if result != nil {
		resultJSON, err = json.Marshal(result)
		if err != nil {
			return 0, fmt.Errorf("marshal result: %w", err)
		}
	}
	var ec, em, fr *string
	if errorCode != "" {
		ec = &errorCode
	}
	if errorMessage != "" {
		em = &errorMessage
	}
	if finishReason != "" {
		fr = &finishReason
	}
	// Race protection: only finalize from running. If a DELETE
	// (cancel) flipped status='cancelled' while we were streaming, the
	// goroutine's Finalize must be a no-op — otherwise we'd silently
	// overwrite cancelled → completed. The WHERE clause means a
	// late-arriving Finalize is dropped on the floor, which matches
	// the user-visible semantic ("cancel won").
	tag, err := r.pool.Exec(ctx, `
UPDATE llm_jobs
SET status = $2,
    completed_at = now(),
    result = $3,
    error_code = $4,
    error_message = $5,
    finish_reason = $6
WHERE job_id = $1 AND status = 'running'
`, jobID, status, resultJSON, ec, em, fr)
	if err != nil {
		return 0, fmt.Errorf("finalize: %w", err)
	}
	return tag.RowsAffected(), nil
}

// Cancel transitions a pre-terminal job to cancelled and stamps
// completed_at. Returns rows-affected so caller can distinguish "already
// terminal" (0) from "actually cancelled" (1).
func (r *Repo) Cancel(ctx context.Context, jobID, ownerUserID uuid.UUID) (int64, error) {
	tag, err := r.pool.Exec(ctx, `
UPDATE llm_jobs
SET status = 'cancelled', completed_at = now()
WHERE job_id = $1 AND owner_user_id = $2
  AND status IN ('pending','running')
`, jobID, ownerUserID)
	if err != nil {
		return 0, fmt.Errorf("cancel: %w", err)
	}
	return tag.RowsAffected(), nil
}

// ModelPricing reads a model's pricing JSONB. For a user_model the lookup is
// scoped to ownerUserID. found=false means no such model exists — the caller
// treats that as a 404, distinct from a found-but-unpriced model (whose empty
// pricing makes the estimator fail closed with a 402).
func (r *Repo) ModelPricing(ctx context.Context, modelSource string, ownerUserID, modelRef uuid.UUID) (billing.Pricing, bool, error) {
	var raw []byte
	var err error
	switch modelSource {
	case "user_model":
		err = r.pool.QueryRow(ctx,
			`SELECT pricing FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`,
			modelRef, ownerUserID).Scan(&raw)
	case "platform_model":
		err = r.pool.QueryRow(ctx,
			`SELECT pricing FROM platform_models WHERE platform_model_id=$1`,
			modelRef).Scan(&raw)
	default:
		return billing.Pricing{}, false, fmt.Errorf("unknown model_source %q", modelSource)
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return billing.Pricing{}, false, nil
	}
	if err != nil {
		return billing.Pricing{}, false, fmt.Errorf("model pricing lookup: %w", err)
	}
	var p billing.Pricing
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &p); err != nil {
			return billing.Pricing{}, true, fmt.Errorf("decode pricing: %w", err)
		}
	}
	return p, true, nil
}

// BillingInfo returns the reservation + model identity a finalizing worker
// needs to reconcile/release a job's spend hold. reservationID is nil when
// the job carries no reservation (pre-guardrail rows, or the stt-multipart
// path). found=false means no such job row.
func (r *Repo) BillingInfo(ctx context.Context, jobID uuid.UUID) (reservationID *uuid.UUID, modelSource string, modelRef uuid.UUID, found bool, err error) {
	err = r.pool.QueryRow(ctx,
		`SELECT reservation_id, model_source, model_ref FROM llm_jobs WHERE job_id=$1`,
		jobID).Scan(&reservationID, &modelSource, &modelRef)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, "", uuid.Nil, false, nil
	}
	if err != nil {
		return nil, "", uuid.Nil, false, fmt.Errorf("billing info lookup: %w", err)
	}
	return reservationID, modelSource, modelRef, true, nil
}

// IsTerminal returns true for the three statuses that close out a job.
func IsTerminal(status string) bool {
	return status == "completed" || status == "failed" || status == "cancelled"
}

// MarshalJob produces the openapi Job JSON envelope that GET handlers
// return. Centralized so the handler doesn't recompute progress/result
// shape per-call.
func MarshalJob(job *Job) map[string]any {
	out := map[string]any{
		"job_id":       job.JobID.String(),
		"operation":    job.Operation,
		"status":       job.Status,
		"submitted_at": job.SubmittedAt.UTC().Format(time.RFC3339Nano),
	}
	if job.StartedAt != nil {
		out["started_at"] = job.StartedAt.UTC().Format(time.RFC3339Nano)
	}
	if job.CompletedAt != nil {
		out["completed_at"] = job.CompletedAt.UTC().Format(time.RFC3339Nano)
	}
	if job.TraceID != nil {
		out["trace_id"] = *job.TraceID
	}
	if len(job.JobMeta) > 0 {
		var meta any
		if err := json.Unmarshal(job.JobMeta, &meta); err == nil {
			out["job_meta"] = meta
		}
	}
	progress := map[string]any{
		"chunks_done": job.ChunksDone,
		"tokens_used": job.TokensUsed,
	}
	if job.ChunksTotal != nil {
		progress["chunks_total"] = *job.ChunksTotal
	}
	if job.LastProgressAt != nil {
		progress["last_progress_at"] = job.LastProgressAt.UTC().Format(time.RFC3339Nano)
	}
	out["progress"] = progress
	if len(job.Result) > 0 {
		var r any
		if err := json.Unmarshal(job.Result, &r); err == nil {
			out["result"] = r
		}
	}
	if job.ErrorCode != nil || job.ErrorMessage != nil {
		errObj := map[string]any{}
		if job.ErrorCode != nil {
			errObj["code"] = *job.ErrorCode
		}
		if job.ErrorMessage != nil {
			errObj["message"] = *job.ErrorMessage
		}
		out["error"] = errObj
	}
	return out
}

// guard against pgx.ErrNoRows leaking into typed errors elsewhere.
var ErrNotFound = pgx.ErrNoRows
