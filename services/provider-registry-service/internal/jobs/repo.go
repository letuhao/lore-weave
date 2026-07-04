package jobs

// Phase 2b (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). DB CRUD for the
// `llm_jobs` table. The schema lives in internal/migrate/migrate.go;
// repo functions here are the only sanctioned write path.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strconv"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/provider-registry-service/internal/billing"
)

// #32 — per-payload byte cap for the traced request/response stored on usage_outbox.
// Bounds Redis-event size + the encrypted usage_logs column volume. Tunable via env.
var usagePayloadCapBytes = func() int {
	if v := os.Getenv("LLM_USAGE_PAYLOAD_CAP_BYTES"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return 16384
}()

// truncatePayload returns b as a string capped at capBytes, backing off to a valid
// UTF-8 rune boundary (a mid-rune cut would be invalid UTF-8 → Postgres TEXT rejects
// the INSERT). Empty in → empty out (caller stores NULL). The marker keeps it obvious
// in the trace that the payload was clipped.
func truncatePayload(b []byte, capBytes int) string {
	if len(b) == 0 {
		return ""
	}
	if len(b) <= capBytes {
		return string(b)
	}
	cut := capBytes
	for cut > 0 && !utf8.RuneStart(b[cut]) {
		cut--
	}
	return string(b[:cut]) + fmt.Sprintf("…[truncated %d bytes]", len(b)-cut)
}

// nullIfEmpty maps "" → NULL so an absent payload/status doesn't store an empty string.
func nullIfEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// PgxPool is the subset of *pgxpool.Pool that Repo + UsageRelay use. Declaring it
// as an interface lets tests inject pgxmock (PgxPoolIface) while production passes
// the real *pgxpool.Pool. Both satisfy these four signatures.
type PgxPool interface {
	Begin(ctx context.Context) (pgx.Tx, error)
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

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
	pool PgxPool
}

func NewRepo(pool PgxPool) *Repo {
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

// JobDispatch is the minimal set of fields the queue consumer needs to (re)run
// Process from a job_id — no owner scoping (the internal consumer trusts the row
// the submit handler already owner-verified + persisted).
type JobDispatch struct {
	OwnerUserID uuid.UUID
	Operation   string
	ModelSource string
	ModelRef    uuid.UUID
	Input       json.RawMessage
	Chunking    json.RawMessage
	Status      string
}

// LoadForProcess reads the dispatch fields for a queued job. Used by the Commit-3
// consumer pool: it loads by job_id (the message carries only the id) and runs
// Process. Returns pgx.ErrNoRows if the row is gone (consumer acks + drops).
func (r *Repo) LoadForProcess(ctx context.Context, jobID uuid.UUID) (*JobDispatch, error) {
	d := &JobDispatch{}
	err := r.pool.QueryRow(ctx, `
SELECT owner_user_id, operation, model_source, model_ref, input, chunking, status
FROM llm_jobs WHERE job_id = $1
`, jobID).Scan(&d.OwnerUserID, &d.Operation, &d.ModelSource, &d.ModelRef,
		&d.Input, &d.Chunking, &d.Status)
	if err != nil {
		return nil, err
	}
	return d, nil
}

// ResolveConcurrency resolves a job's concurrency CLASS — the key the governor +
// queue serialize on — and that class's per-credential cap. The key is the
// provider_credential_id (so all jobs sharing one BYOK credential share its
// limit, regardless of provider kind). limit ≤ 0 means UNLIMITED (NULL
// max_concurrency → request-as-demand; the backend infra is the only limiter).
// found=false → model gone (caller acks+drops). Platform models have no
// per-user credential → keyed by platform_model_id, always unlimited.
func (r *Repo) ResolveConcurrency(ctx context.Context, modelSource string, ownerUserID, modelRef uuid.UUID) (key string, limit int, ok bool, err error) {
	var credID uuid.UUID
	var maxConc *int
	switch modelSource {
	case "user_model":
		err = r.pool.QueryRow(ctx, `
SELECT pc.provider_credential_id, pc.max_concurrency
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2`,
			modelRef, ownerUserID).Scan(&credID, &maxConc)
	case "platform_model":
		// Platform models are shared/cloud — no per-user credential, no cap.
		// Key by the model id so the (unlimited) class is still distinct.
		return "platform:" + modelRef.String(), 0, true, nil
	default:
		return "", 0, false, fmt.Errorf("unknown model_source %q", modelSource)
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return "", 0, false, nil
	}
	if err != nil {
		return "", 0, false, fmt.Errorf("resolve concurrency: %w", err)
	}
	if maxConc != nil && *maxConc > 0 {
		limit = *maxConc
	}
	return credID.String(), limit, true, nil
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

// UsageOutbox is the model-level usage a completed job spent. The worker fills
// it from the result `usage` block × model pricing (cost may be nil — media /
// unpriced). Written transactionally with the finalize in FinalizeWithUsageOutbox.
type UsageOutbox struct {
	ModelSource  string
	ModelRef     uuid.UUID
	Operation    string
	InputTokens  int
	OutputTokens int
	CostUSD      *float64 // nil → cost unresolvable (stored NULL)
	// #32 — full-logging fields. RequestStatus is "success" (completed) | "failed" |
	// "cancelled". RequestPayload/ResponsePayload are the truncated job input/result
	// (tracing artifact; usage-billing encrypts them). Empty string ⇒ stored NULL.
	RequestStatus   string
	RequestPayload  string
	ResponsePayload string
}

// TerminalOutbox is the LLM re-arch Phase 1 terminal-event payload written to
// job_event_outbox in the SAME tx as a terminal transition (completed | failed |
// cancelled). The relay XADDs it to loreweave:events:llm_job_terminal so a caller
// resumes on it. job_id / owner / status / campaign_id are known in the finalize
// tx; this carries only the extra correlation + summary fields. Kind is
// best-effort (provider kind, used by the Commit-3 queue for routing) — empty is
// fine for Commit 1 since consumers key on job_id, not kind.
type TerminalOutbox struct {
	Operation     string
	Kind          string
	CostUSD       *float64 // nil → unresolvable / non-completed (stored NULL)
	ErrorCode     string
	ErrorMessage  string
	CorrelationID string
}

// insertUsageOutbox writes one usage_outbox audit row inside the caller's tx (#32).
// Shared by FinalizeWithUsageOutbox (worker terminal path) and Cancel (user-cancel
// path) so EVERY terminal call — including a cancellation — produces a usage-billing
// audit row, and both paths attach the same UTF-8-safe-truncated request/response
// payloads + request_status. cost may be nil (cancelled/unpriced → stored NULL).
func insertUsageOutbox(
	ctx context.Context, tx pgx.Tx,
	jobID, ownerUserID uuid.UUID, campaignID, mcpKeyID *uuid.UUID,
	modelSource string, modelRef uuid.UUID, operationLabel string,
	inTok, outTok int, cost *float64, requestStatus string,
	inputJSON, resultJSON []byte,
) error {
	reqPayload := truncatePayload(inputJSON, usagePayloadCapBytes)
	respPayload := truncatePayload(resultJSON, usagePayloadCapBytes)
	// mcp_key_id (public-MCP per-key spend attribution, H-C/PUB-11) is carried alongside
	// the #32 audit columns (request_status + payloads); both migrations add their columns
	// to usage_outbox, so the merged row records BOTH the public-key attribution and the
	// traceable payload/status.
	_, err := tx.Exec(ctx, `
INSERT INTO usage_outbox
  (request_id, owner_user_id, campaign_id, mcp_key_id, model_source, model_ref,
   operation, input_tokens, output_tokens, cost_usd,
   request_status, request_payload, response_payload)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
`, jobID, ownerUserID, campaignID, mcpKeyID, modelSource, modelRef,
		operationLabel, inTok, outTok, cost,
		nullIfEmpty(requestStatus), nullIfEmpty(reqPayload), nullIfEmpty(respPayload))
	return err
}

// insertJobEventOutbox writes one job_event_outbox row inside the caller's tx.
// Shared by FinalizeWithUsageOutbox (worker terminal path) and Cancel (cancel
// handler) so both emit the same durable, per-job-correlated terminal event.
func insertJobEventOutbox(
	ctx context.Context, tx pgx.Tx,
	jobID, ownerUserID uuid.UUID, operation, status, kind string,
	costUSD *float64, errorCode, errorMessage string,
	campaignID *uuid.UUID, correlationID string,
) error {
	var ec, em, corr *string
	if errorCode != "" {
		ec = &errorCode
	}
	if errorMessage != "" {
		em = &errorMessage
	}
	if correlationID != "" {
		corr = &correlationID
	}
	_, err := tx.Exec(ctx, `
INSERT INTO job_event_outbox
  (job_id, owner_user_id, operation, status, kind,
   cost_usd, error_code, error_message, campaign_id, correlation_id)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
`, jobID, ownerUserID, operation, status, kind,
		costUSD, ec, em, campaignID, corr)
	return err
}

// FinalizeWithUsageOutbox is the worker's terminal-path finalize (S4b, decision
// C). It does the same status transition as Finalize AND — only when the
// transition actually takes effect (rows=1) on a COMPLETED job with a non-nil
// usage — writes one `usage_outbox` row in the SAME tx, so a relay can deliver
// usage exactly-once (at-least-once + request_id dedup downstream). campaign_id
// is parsed from the job's own job_meta (the S4a correlation tag) inside the tx.
//
// usage may be nil (failed/cancelled, or no resolvable tokens) → no outbox row.
// Returns rowsAffected so the caller gates the notifier exactly as before.
func (r *Repo) FinalizeWithUsageOutbox(
	ctx context.Context,
	jobID uuid.UUID,
	ownerUserID uuid.UUID,
	status string,
	result any,
	errorCode, errorMessage, finishReason string,
	usage *UsageOutbox,
	term *TerminalOutbox,
) (int64, error) {
	if status != "completed" && status != "failed" && status != "cancelled" {
		return 0, fmt.Errorf("invalid terminal status: %q", status)
	}
	var resultJSON []byte
	if result != nil {
		var err error
		if resultJSON, err = json.Marshal(result); err != nil {
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

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("finalize+outbox: begin: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// Same race guard as Finalize (WHERE status='running'); RETURNING job_meta so
	// we can stamp the outbox row with the job's campaign_id in this tx. No row
	// matched ⇒ a cancel beat us → no transition, no outbox (matches notifier gate).
	// #32 — RETURNING input too: the immutable request payload the worker truncates
	// into the usage_outbox row (no extra query; same tx).
	var jobMeta []byte
	var inputJSON []byte
	err = tx.QueryRow(ctx, `
UPDATE llm_jobs
SET status = $2, completed_at = now(), result = $3,
    error_code = $4, error_message = $5, finish_reason = $6
WHERE job_id = $1 AND status = 'running'
RETURNING job_meta, input
`, jobID, status, resultJSON, ec, em, fr).Scan(&jobMeta, &inputJSON)
	if errors.Is(err, pgx.ErrNoRows) {
		if cerr := tx.Commit(ctx); cerr != nil {
			return 0, fmt.Errorf("finalize+outbox: commit (no-op): %w", cerr)
		}
		return 0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("finalize+outbox: update: %w", err)
	}

	// campaign_id (the S4a correlation tag) stamps BOTH outbox rows; parse once.
	campaignID := parseJobMetaCampaignID(jobMeta)
	// mcp_key_id (H-C/PUB-11 per-key spend attribution) rides the same job_meta tag
	// into the usage_outbox row → usage stream → usage_logs. NULL for first-party jobs.
	mcpKeyID := ParseJobMetaMcpKeyID(jobMeta)

	// #32 — emit a usage_outbox row for EVERY terminal status the worker provides a
	// usage for (not just completed) so usage-billing audits every call. The worker
	// sets usage on all terminal statuses now; cost/tokens are 0/nil for non-completed
	// and RequestStatus distinguishes them (usage_logs is audit-only — enforcement is
	// the guardrail, untouched). Payloads are filled HERE from the immutable input +
	// the result (both in this tx), UTF-8-safe truncated, so a call can be traced.
	// mcp_key_id (public-MCP per-key attribution) rides the same insert (NULL first-party).
	if usage != nil {
		// bug #24: the usage-billing `purpose` (the human label in the Usage GUI)
		// is derived from this `operation` column. But `operation` is overloaded —
		// it ALSO selects the worker's result aggregator + cost estimate + budget
		// salvage, so every background-job caller submits operation="chat" (the
		// chat-shaped result they parse) and was therefore mislabeled "chat". The
		// caller's real intent rides job_meta.usage_purpose; prefer it for the
		// billing label only, leaving the job's real operation untouched. Fail-soft
		// (absent/malformed → fall back to the operation), mirroring campaign_id.
		operationLabel := usage.Operation
		if p := parseJobMetaUsagePurpose(jobMeta); p != "" {
			operationLabel = p
		}
		if err := insertUsageOutbox(ctx, tx, jobID, ownerUserID, campaignID, mcpKeyID,
			usage.ModelSource, usage.ModelRef, operationLabel,
			usage.InputTokens, usage.OutputTokens, usage.CostUSD, usage.RequestStatus,
			inputJSON, resultJSON); err != nil {
			return 0, fmt.Errorf("finalize+outbox: insert outbox: %w", err)
		}
	}

	// LLM re-arch Phase 1 — durable terminal event on EVERY transition (not just
	// completed+usage), in the same tx, so a caller resumes on it via the relay.
	if term != nil {
		if err := insertJobEventOutbox(ctx, tx, jobID, ownerUserID,
			term.Operation, status, term.Kind, term.CostUSD,
			term.ErrorCode, term.ErrorMessage, campaignID, term.CorrelationID); err != nil {
			return 0, fmt.Errorf("finalize+outbox: insert job_event: %w", err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("finalize+outbox: commit: %w", err)
	}
	return 1, nil
}

// parseJobMetaCampaignID extracts job_meta.campaign_id (the S4a correlation tag)
// as a UUID. Nil-tolerant on EVERY failure (absent / non-object / non-string /
// bad-uuid) — a malformed tag must never fail a billing-critical finalize; it
// just yields an un-attributed (campaign_id NULL) usage row.
func parseJobMetaCampaignID(jobMeta []byte) *uuid.UUID {
	if len(jobMeta) == 0 {
		return nil
	}
	var m map[string]any
	if err := json.Unmarshal(jobMeta, &m); err != nil {
		return nil
	}
	raw, ok := m["campaign_id"].(string)
	if !ok || raw == "" {
		return nil
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		return nil
	}
	return &id
}

// parseJobMetaUsagePurpose extracts job_meta.usage_purpose (bug #24) — the
// caller's human label for the Usage GUI's `purpose` column, decoupled from the
// overloaded `operation`. Returns "" (→ caller falls back to the real operation)
// on EVERY failure: absent, non-object, non-string, or a value that isn't a
// safe label. The charset gate (lowercase alnum + underscore, 1..48 chars,
// leading letter) keeps an untrusted job_meta from injecting arbitrary text
// into a billing audit row — a malformed label must never break a finalize.
func parseJobMetaUsagePurpose(jobMeta []byte) string {
	if len(jobMeta) == 0 {
		return ""
	}
	var m map[string]any
	if err := json.Unmarshal(jobMeta, &m); err != nil {
		return ""
	}
	raw, ok := m["usage_purpose"].(string)
	if !ok || !isSafeUsagePurpose(raw) {
		return ""
	}
	return raw
}

// isSafeUsagePurpose reports whether s is a safe snake_case label: 1..48 chars,
// leading lowercase letter, then lowercase letters / digits / underscores.
func isSafeUsagePurpose(s string) bool {
	if len(s) == 0 || len(s) > 48 {
		return false
	}
	for i, r := range s {
		switch {
		case r >= 'a' && r <= 'z':
		case i > 0 && (r == '_' || (r >= '0' && r <= '9')):
		default:
			return false
		}
	}
	return true
}

// ParseJobMetaMcpKeyID extracts job_meta.mcp_key_id (the public-MCP-key spend
// attribution tag, H-C/PUB-11) as a UUID. Exported so the submit handler can
// reuse it for the PUB-12 BYOK-only gate. Nil-tolerant on EVERY failure
// (absent / non-object / non-string / bad-uuid), mirroring parseJobMetaCampaignID:
// a malformed tag must never fail a billing-critical finalize — it just yields an
// un-attributed (mcp_key_id NULL) usage row. Its presence means the call
// originated at the public MCP edge (first-party traffic never sets it).
func ParseJobMetaMcpKeyID(jobMeta []byte) *uuid.UUID {
	if len(jobMeta) == 0 {
		return nil
	}
	var m map[string]any
	if err := json.Unmarshal(jobMeta, &m); err != nil {
		return nil
	}
	raw, ok := m["mcp_key_id"].(string)
	if !ok || raw == "" {
		return nil
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		return nil
	}
	return &id
}

// ParseJobMetaSpendCap extracts job_meta.spend_cap_usd (the public key's per-key
// USD sub-cap, H-K) as a float. The SDK carrier writes it as a JSON number, so it
// decodes to float64. Nil-tolerant on EVERY failure (absent / non-object /
// non-number / negative): a malformed cap must never fail submit — it just means
// no per-key cap is enforced for this job (the owner guardrail still applies).
// Only meaningful alongside a non-nil ParseJobMetaMcpKeyID (public-key traffic).
func ParseJobMetaSpendCap(jobMeta []byte) *float64 {
	if len(jobMeta) == 0 {
		return nil
	}
	var m map[string]any
	if err := json.Unmarshal(jobMeta, &m); err != nil {
		return nil
	}
	v, ok := m["spend_cap_usd"].(float64)
	if !ok || v < 0 {
		return nil
	}
	return &v
}

// Cancel transitions a pre-terminal job to cancelled and stamps
// completed_at. Returns rows-affected so caller can distinguish "already
// terminal" (0) from "actually cancelled" (1).
//
// LLM re-arch Phase 1: on a real transition it ALSO writes the durable
// terminal-event outbox row in the SAME tx (RETURNING operation + job_meta so
// the event carries the operation + campaign_id), so a cancel emits the same
// canonical llm.job_terminal event a normal finalize does. kind is left empty
// (best-effort; consumers key on job_id).
func (r *Repo) Cancel(ctx context.Context, jobID, ownerUserID uuid.UUID) (int64, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("cancel: begin: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// #32 — RETURNING model_source/model_ref + input/result too so a cancellation
	// also produces a usage-billing audit row (the worker's FinalizeWithUsageOutbox
	// never runs for a user-cancel: it's gated WHERE status='running', which this
	// UPDATE already flipped to 'cancelled').
	var operation, modelSource string
	var modelRef uuid.UUID
	var jobMeta, inputJSON, resultJSON []byte
	err = tx.QueryRow(ctx, `
UPDATE llm_jobs
SET status = 'cancelled', completed_at = now()
WHERE job_id = $1 AND owner_user_id = $2
  AND status IN ('pending','running')
RETURNING operation, model_source, model_ref, job_meta, input, result
`, jobID, ownerUserID).Scan(&operation, &modelSource, &modelRef, &jobMeta, &inputJSON, &resultJSON)
	if errors.Is(err, pgx.ErrNoRows) {
		// Not found OR already terminal — no transition, no event.
		if cerr := tx.Commit(ctx); cerr != nil {
			return 0, fmt.Errorf("cancel: commit (no-op): %w", cerr)
		}
		return 0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("cancel: %w", err)
	}

	campaignID := parseJobMetaCampaignID(jobMeta)
	mcpKeyID := ParseJobMetaMcpKeyID(jobMeta)
	// #32 — audit the cancelled call (cost 0, request_status='cancelled') with the
	// traced request/response payloads, mirroring the worker terminal path's label
	// override so the Usage GUI purpose matches. mcp_key_id attributes a cancelled
	// public-MCP job (NULL first-party).
	operationLabel := operation
	if p := parseJobMetaUsagePurpose(jobMeta); p != "" {
		operationLabel = p
	}
	if err := insertUsageOutbox(ctx, tx, jobID, ownerUserID, campaignID, mcpKeyID,
		modelSource, modelRef, operationLabel, 0, 0, nil, "cancelled",
		inputJSON, resultJSON); err != nil {
		return 0, fmt.Errorf("cancel: insert outbox: %w", err)
	}
	if err := insertJobEventOutbox(ctx, tx, jobID, ownerUserID,
		operation, "cancelled", "", nil, "", "", campaignID, ""); err != nil {
		return 0, fmt.Errorf("cancel: insert job_event: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("cancel: commit: %w", err)
	}
	return 1, nil
}

// FinalizeStreamStatus is the BILLING-NEUTRAL terminal write for an M3 streaming
// observability row (the chat disconnect-cancel job-row). Unlike
// FinalizeWithUsageOutbox it writes NO usage outbox and NO token totals — the
// streaming path's own guard.settle / stream_billing stays the sole billing
// authority (the row carries reservation_id = NULL), so finalizing here cannot
// double-count. Guarded on status='running' so it never clobbers a 'cancelled'
// already set by Cancel (an explicit DELETE that raced the stream's own exit):
// rows==0 then means a concurrent cancel won, which is correct + idempotent.
func (r *Repo) FinalizeStreamStatus(
	ctx context.Context, jobID uuid.UUID, status, finishReason string,
) (int64, error) {
	tag, err := r.pool.Exec(ctx, `
UPDATE llm_jobs
SET status = $2, completed_at = now(), finish_reason = $3
WHERE job_id = $1 AND status = 'running'
`, jobID, status, finishReason)
	if err != nil {
		return 0, fmt.Errorf("finalize stream status: %w", err)
	}
	return tag.RowsAffected(), nil
}

// SweepStuckRunning is the §5.6 truth-sweeper backstop (D-PHASE1-RUNNING-SWEEPER):
// a job that crashed mid-Process is left `running` and is NOT recovered by queue
// redelivery (Process's pending-only gate). This bulk-fails any `running` job
// whose last_progress_at is older than olderThan — a job that's actively
// streaming bumps last_progress_at per chunk, so only a genuinely STALLED job is
// swept (a legit long multi-chunk job keeps progressing). Each swept job gets a
// durable terminal-event row in the SAME tx so its caller (campaign) resumes and
// can rerun-failed. Returns the count swept.
func (r *Repo) SweepStuckRunning(ctx context.Context, olderThan time.Duration) (int, error) {
	cutoff := -olderThan.Seconds() // negative → "now() + (-secs) = now() - secs"
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("sweep: begin: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	rows, err := tx.Query(ctx, `
UPDATE llm_jobs
SET status='failed', completed_at=now(),
    error_code='LLM_STUCK_TIMEOUT',
    error_message='job stalled in running with no progress past the sweep threshold'
WHERE status='running'
  AND COALESCE(last_progress_at, started_at) < now() + make_interval(secs => $1)
RETURNING job_id, owner_user_id, operation, job_meta
`, cutoff)
	if err != nil {
		return 0, fmt.Errorf("sweep: update: %w", err)
	}
	type swept struct {
		jobID, owner uuid.UUID
		operation    string
		campaignID   *uuid.UUID
	}
	var batch []swept
	for rows.Next() {
		var s swept
		var jobMeta []byte
		if err := rows.Scan(&s.jobID, &s.owner, &s.operation, &jobMeta); err != nil {
			rows.Close()
			return 0, fmt.Errorf("sweep: scan: %w", err)
		}
		s.campaignID = parseJobMetaCampaignID(jobMeta)
		batch = append(batch, s)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, fmt.Errorf("sweep: rows: %w", err)
	}
	for _, s := range batch {
		if err := insertJobEventOutbox(ctx, tx, s.jobID, s.owner, s.operation, "failed",
			"", nil, "LLM_STUCK_TIMEOUT", "swept: stalled in running", s.campaignID, ""); err != nil {
			return 0, fmt.Errorf("sweep: insert job_event: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("sweep: commit: %w", err)
	}
	return len(batch), nil
}

// PurgeExpiredJobs DELETEs terminal (completed/failed/cancelled) llm_jobs whose
// expires_at has passed — the plaintext input/result retention sweep designed at
// migrate.go:143 (partial index idx_llm_jobs_expires_at). Whole-row DELETE, NOT a
// column-purge: the durable audit copy lives (encrypted) in usage_logs (readable
// post-P0-1), and GET /{v1,internal}/llm/jobs/{id} cleanly 404s a purged row
// (consumers tolerate 404), whereas a column-purge would serve a confusing partial
// row. Safe against dispatch: `input` is never API-returned and LoadForProcess
// reads pending-only, so a terminal purge can't collide with a running job.
//
// Bounded by batchSize (ctid IN (SELECT … LIMIT $1)) so a backlog can't take one
// giant table lock; the caller loops until a batch comes back short. The status
// filter is load-bearing — dropping it would delete live running/pending work.
func (r *Repo) PurgeExpiredJobs(ctx context.Context, batchSize int) (int, error) {
	tag, err := r.pool.Exec(ctx, `
DELETE FROM llm_jobs
WHERE ctid IN (
  SELECT ctid FROM llm_jobs
  WHERE status IN ('completed','failed','cancelled')
    AND expires_at < now()
  ORDER BY expires_at
  LIMIT $1
)
`, batchSize)
	if err != nil {
		return 0, fmt.Errorf("purge expired: %w", err)
	}
	return int(tag.RowsAffected()), nil
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

// EstimateModelInfo reads a model's pricing JSONB AND its provider_kind in a
// single row — the S5a estimate oracle needs both (price + a cloud/local badge).
// It mirrors ModelPricing's found-vs-unpriced contract (found=false → 404 at the
// caller, distinct from found-but-empty-pricing → unpriced). Kept separate from
// ModelPricing so that method's two other callers (jobs_handler reserve, worker
// reconcile) are untouched. For a user_model the lookup is owner-scoped.
func (r *Repo) EstimateModelInfo(ctx context.Context, modelSource string, ownerUserID, modelRef uuid.UUID) (billing.Pricing, string, bool, error) {
	var raw []byte
	var providerKind string
	var err error
	switch modelSource {
	case "user_model":
		err = r.pool.QueryRow(ctx,
			`SELECT pricing, provider_kind FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`,
			modelRef, ownerUserID).Scan(&raw, &providerKind)
	case "platform_model":
		err = r.pool.QueryRow(ctx,
			`SELECT pricing, provider_kind FROM platform_models WHERE platform_model_id=$1`,
			modelRef).Scan(&raw, &providerKind)
	default:
		return billing.Pricing{}, "", false, fmt.Errorf("unknown model_source %q", modelSource)
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return billing.Pricing{}, "", false, nil
	}
	if err != nil {
		return billing.Pricing{}, "", false, fmt.Errorf("model estimate-info lookup: %w", err)
	}
	var p billing.Pricing
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &p); err != nil {
			return billing.Pricing{}, providerKind, true, fmt.Errorf("decode pricing: %w", err)
		}
	}
	return p, providerKind, true, nil
}

// ModelContextLength reads a model's registered context window (tokens).
// Used by the D-EXTRACTION-CONTEXT-FIX-STAGE-4 preflight to reject 400
// requests whose input + max_tokens would overflow the model's loaded
// context. Returns (0, true, nil) when the model exists but
// context_length is NULL — preflight then skips the fit check (legacy
// rows, platform models, or providers without a known limit).
// found=false → 404 at caller (mirrors ModelPricing's contract).
//
// platform_models do NOT have a context_length column (admin-curated
// + presumed safe); this method returns (0, true, nil) for them so
// preflight skips the fit check. The pricing lookup already verifies
// the platform model exists.
func (r *Repo) ModelContextLength(ctx context.Context, modelSource string, ownerUserID, modelRef uuid.UUID) (int, bool, error) {
	if modelSource == "platform_model" {
		return 0, true, nil
	}
	if modelSource != "user_model" {
		return 0, false, fmt.Errorf("unknown model_source %q", modelSource)
	}
	var ctxLen *int
	err := r.pool.QueryRow(ctx,
		`SELECT context_length FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`,
		modelRef, ownerUserID).Scan(&ctxLen)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, false, nil
	}
	if err != nil {
		return 0, false, fmt.Errorf("model context_length lookup: %w", err)
	}
	if ctxLen == nil {
		return 0, true, nil
	}
	return *ctxLen, true, nil
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
