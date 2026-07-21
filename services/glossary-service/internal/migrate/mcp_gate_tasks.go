package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// mcpGateTasksSQL — the durable ext-tasks gate store (D-MCPTASKS-GO-STORE), a mirror of
// book-service's mcp_gate_tasks. One row per pending/terminal human-gate task; persists
// only DATA ({descriptor, owner, payload}) so any replica reconstructs the write via the
// resolver registry (no closure). The PgTaskStore claims a task with an atomic
// input_required→working UPDATE (single-winner across replicas — the double-confirm guard,
// the single-use equivalent of the consumed_tokens jti ledger), then writes the terminal
// outcome.
const mcpGateTasksSQL = `
CREATE TABLE IF NOT EXISTS mcp_gate_tasks (
  task_id          TEXT PRIMARY KEY,                       -- "task_<uuid-hex>" (minted by the app)
  status           TEXT NOT NULL
                     CHECK (status IN ('working','input_required','completed','failed','cancelled')),
  descriptor       TEXT NOT NULL,                          -- the action descriptor = the resolver key
  owner_user_id    UUID NOT NULL,                          -- tenancy scope key (the proposing user)
  payload          JSONB NOT NULL DEFAULT '{}'::jsonb,     -- serializable action data captured at propose-time
  input_requests   JSONB,                                  -- the rich card payload the client renders
  result           JSONB,                                  -- set on completed
  error            TEXT,                                   -- set on failed
  ttl_ms           INTEGER NOT NULL,
  poll_interval_ms INTEGER NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Owner-scoped listing / tenant sweeps (never a global scan).
CREATE INDEX IF NOT EXISTS idx_mcp_gate_tasks_owner ON mcp_gate_tasks (owner_user_id, created_at DESC);
-- TTL sweep of stale non-terminal tasks.
CREATE INDEX IF NOT EXISTS idx_mcp_gate_tasks_status ON mcp_gate_tasks (status, created_at);
`

// UpMcpGateTasks creates the durable ext-tasks gate's PERSISTENT store (multi-replica),
// so the glossary KIND-C gate (action_task_gate.go) resolves a propose on one replica and
// its accept on another exactly once. Idempotent; routed through execGuarded like every
// other chain step.
func UpMcpGateTasks(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "mcp-gate-tasks", mcpGateTasksSQL)
}
