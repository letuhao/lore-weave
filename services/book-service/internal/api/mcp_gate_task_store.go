package api

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// newTaskUUIDHex mints the dashless-uuid suffix of a task id (parity with the kit's
// in-memory store: "task_" + hex).
func newTaskUUIDHex() string {
	return strings.ReplaceAll(uuid.NewString(), "-", "")
}

// PgTaskStore is the PERSISTENT, multi-replica implementation of lwmcp.TaskStore
// (D-MCPTASKS-GO-STORE). It backs the durable ext-tasks human gate with the
// `mcp_gate_tasks` table so a propose on one replica and its accept on another (or
// after a restart/deploy) resolve the SAME task exactly once. It persists only DATA
// ({descriptor, owner_user_id, payload}); the write to run on accept is the resolver
// registered for the descriptor (reconstructed on any replica — no closure). The
// accept is a single-winner atomic UPDATE (input_required→working), so two concurrent
// accepts can't both run the resolver (the double-commit guard).
//
// Only ProvideInput runs the (possibly slow) resolver, and it uses the caller's ctx so
// a client disconnect / turn-abort propagates into the real write. Create/Get/Cancel
// are sub-millisecond single-row queries against the PK; they use a bounded background
// context (the M1a interface intentionally keeps them ctx-free — see the resolver-registry
// note in the plan) so they never hang a startup or a poll.
type PgTaskStore struct {
	pool      *pgxpool.Pool
	resolvers lwmcp.TaskResolverRegistry
}

// NewPgTaskStore binds the store to the pool + the resolver registry (descriptor → the
// write to run on accept), mirroring NewInMemoryTaskStore.
func NewPgTaskStore(pool *pgxpool.Pool, resolvers lwmcp.TaskResolverRegistry) *PgTaskStore {
	if resolvers == nil {
		resolvers = lwmcp.TaskResolverRegistry{}
	}
	return &PgTaskStore{pool: pool, resolvers: resolvers}
}

// bgCtx bounds the fast metadata queries so a wedged DB can't hang startup/polling.
func bgCtx() (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), 10*time.Second)
}

func mustJSON(v any) []byte {
	if v == nil {
		return []byte("null")
	}
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("null")
	}
	return b
}

// scanTask reads a full task row into an lwmcp.Task. The jsonb columns arrive as []byte.
func scanTask(row pgx.Row) (*lwmcp.Task, error) {
	var (
		t                            lwmcp.Task
		payloadB, inputReqB, resultB []byte
		errMsg                       *string
	)
	if err := row.Scan(&t.TaskID, &t.Status, &t.Descriptor, &t.OwnerUserID,
		&payloadB, &inputReqB, &resultB, &errMsg, &t.TTLMs, &t.PollIntervalMs,
		&t.CreatedAt, &t.UpdatedAt); err != nil {
		return nil, err
	}
	if len(payloadB) > 0 {
		_ = json.Unmarshal(payloadB, &t.Payload)
	}
	if len(inputReqB) > 0 {
		_ = json.Unmarshal(inputReqB, &t.InputRequests)
	}
	if len(resultB) > 0 {
		_ = json.Unmarshal(resultB, &t.Result)
	}
	if errMsg != nil {
		t.ErrorMsg = *errMsg
	}
	return &t, nil
}

const pgTaskCols = `task_id, status, descriptor, owner_user_id, payload, input_requests,
	result, error, ttl_ms, poll_interval_ms, created_at, updated_at`

func (s *PgTaskStore) Create(descriptor, ownerUserID string, payload map[string]any, inputRequests any, ttlMs int) (*lwmcp.Task, error) {
	if descriptor == "" {
		return nil, errors.New("task descriptor is required")
	}
	if ttlMs <= 0 {
		ttlMs = lwmcp.DefaultTaskTTLMs
	}
	taskID := "task_" + newTaskUUIDHex()
	ctx, cancel := bgCtx()
	defer cancel()
	row := s.pool.QueryRow(ctx, `
		INSERT INTO mcp_gate_tasks
			(task_id, status, descriptor, owner_user_id, payload, input_requests, ttl_ms, poll_interval_ms)
		VALUES ($1, 'input_required', $2, $3, $4::jsonb, $5::jsonb, $6, $7)
		RETURNING `+pgTaskCols,
		taskID, descriptor, ownerUserID, mustJSON(payload), mustJSON(inputRequests),
		ttlMs, lwmcp.DefaultPollIntervalMs)
	return scanTask(row)
}

func (s *PgTaskStore) Get(taskID string, now time.Time) (*lwmcp.Task, error) {
	if now.IsZero() {
		now = time.Now()
	}
	ctx, cancel := bgCtx()
	defer cancel()
	t, err := scanTask(s.pool.QueryRow(ctx, `SELECT `+pgTaskCols+` FROM mcp_gate_tasks WHERE task_id=$1`, taskID))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, lwmcp.ErrTaskNotFound
	}
	if err != nil {
		return nil, err
	}
	// Lazy TTL lapse: a non-terminal task past its TTL becomes failed/task_expired
	// (the token_expired analogue) so the client stops polling and the model re-proposes.
	if !lwmcp.IsTaskTerminal(t.Status) && t.Expired(now) {
		if lapsed, uerr := scanTask(s.pool.QueryRow(ctx, `
			UPDATE mcp_gate_tasks SET status='failed', error='task_expired', updated_at=now()
			WHERE task_id=$1 AND status NOT IN ('completed','failed','cancelled')
			RETURNING `+pgTaskCols, taskID)); uerr == nil {
			return lapsed, nil
		}
	}
	return t, nil
}

func (s *PgTaskStore) ProvideInput(ctx context.Context, taskID string, inputs map[string]any) (*lwmcp.Task, error) {
	// A decline short-circuits to cancelled WITHOUT running the resolver — atomically,
	// only while still awaiting input.
	if isDecline(inputs) {
		qctx, cancel := bgCtx()
		defer cancel()
		t, err := scanTask(s.pool.QueryRow(qctx, `
			UPDATE mcp_gate_tasks SET status='cancelled', updated_at=now()
			WHERE task_id=$1 AND status='input_required'
			RETURNING `+pgTaskCols, taskID))
		if err == nil {
			return t, nil
		}
		if errors.Is(err, pgx.ErrNoRows) {
			return s.notWaitingOrNotFound(qctx, taskID)
		}
		return nil, err
	}

	// CLAIM: input_required → working, single-winner across replicas. Excludes an
	// expired task (its TTL lapsed). The RETURNING gives us the durable data to resolve.
	claimCtx, cancel := bgCtx()
	claimed, err := scanTask(s.pool.QueryRow(claimCtx, `
		UPDATE mcp_gate_tasks SET status='working', updated_at=now()
		WHERE task_id=$1 AND status='input_required'
		  AND (EXTRACT(EPOCH FROM (now()-created_at)) * 1000) < ttl_ms
		RETURNING `+pgTaskCols, taskID))
	if errors.Is(err, pgx.ErrNoRows) {
		res, nerr := s.notWaitingOrNotFound(claimCtx, taskID)
		cancel()
		return res, nerr
	}
	cancel()
	if err != nil {
		return nil, err
	}

	// Run the resolver OUTSIDE any transaction, on the CALLER's ctx (a slow real write
	// respects client disconnect). Looked up by descriptor from the startup registry —
	// reconstructed here from the persisted {descriptor, owner, payload}, never a closure.
	resolver := s.resolvers[claimed.Descriptor]
	var result any
	var runErr error
	if resolver == nil {
		runErr = errors.New("no resolver registered for descriptor " + claimed.Descriptor)
	} else {
		result, runErr = resolver(ctx, claimed.OwnerUserID, claimed.Payload, inputs)
	}

	// Write the terminal outcome. We own the 'working' claim (Cancel only touches
	// input_required), so no status guard is needed.
	wctx, wcancel := bgCtx()
	defer wcancel()
	status := "completed"
	var errStr *string
	if runErr != nil {
		status = "failed"
		m := runErr.Error()
		errStr = &m
	}
	return scanTask(s.pool.QueryRow(wctx, `
		UPDATE mcp_gate_tasks SET status=$2, result=$3::jsonb, error=$4, updated_at=now()
		WHERE task_id=$1
		RETURNING `+pgTaskCols, taskID, status, mustJSON(result), errStr))
}

func (s *PgTaskStore) Cancel(taskID string) (*lwmcp.Task, error) {
	ctx, cancel := bgCtx()
	defer cancel()
	// Cancel only a task still awaiting input — a 'working' task is mid-resolve and must
	// reach its real outcome (cooperative cancel, per the ext-tasks spec).
	t, err := scanTask(s.pool.QueryRow(ctx, `
		UPDATE mcp_gate_tasks SET status='cancelled', updated_at=now()
		WHERE task_id=$1 AND status='input_required'
		RETURNING `+pgTaskCols, taskID))
	if err == nil {
		return t, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return nil, err
	}
	// Already terminal (idempotent — return current) or working / not found.
	cur, gerr := scanTask(s.pool.QueryRow(ctx, `SELECT `+pgTaskCols+` FROM mcp_gate_tasks WHERE task_id=$1`, taskID))
	if errors.Is(gerr, pgx.ErrNoRows) {
		return nil, lwmcp.ErrTaskNotFound
	}
	if gerr != nil {
		return nil, gerr
	}
	return cur, nil // terminal → idempotent; working → cooperative (unchanged)
}

// notWaitingOrNotFound distinguishes a missing task (ErrTaskNotFound) from one that is
// no longer awaiting input (terminal / already-claimed / expired → ErrTaskNotWaiting),
// lazily lapsing an expired task to failed first (parity with the in-memory Get).
func (s *PgTaskStore) notWaitingOrNotFound(ctx context.Context, taskID string) (*lwmcp.Task, error) {
	cur, err := scanTask(s.pool.QueryRow(ctx, `SELECT `+pgTaskCols+` FROM mcp_gate_tasks WHERE task_id=$1`, taskID))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, lwmcp.ErrTaskNotFound
	}
	if err != nil {
		return nil, err
	}
	if !lwmcp.IsTaskTerminal(cur.Status) && cur.Expired(time.Now()) {
		_, _ = s.pool.Exec(ctx, `
			UPDATE mcp_gate_tasks SET status='failed', error='task_expired', updated_at=now()
			WHERE task_id=$1 AND status NOT IN ('completed','failed','cancelled')`, taskID)
	}
	return nil, lwmcp.ErrTaskNotWaiting
}

func isDecline(inputs map[string]any) bool {
	if inputs == nil {
		return false
	}
	if act, _ := inputs["action"].(string); act == "decline" {
		return true
	}
	if acc, present := inputs["accepted"].(bool); present && !acc {
		return true
	}
	return false
}
