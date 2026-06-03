package commands

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// ── PgLifecycleGate — reality active↔frozen via the meta state machine. ──────

// PgLifecycleGate flips a reality between `active` and `frozen` through
// contracts/meta AttemptStateTransition (CAS on reality_registry.status +
// lifecycle_transition_audit row, same TX). cfg MUST carry a loaded Transitions
// graph + an allowlist permitting reality_registry + lifecycle_transition_audit.
type PgLifecycleGate struct {
	cfg *meta.Config
}

// NewPgLifecycleGate binds the MetaWrite Config (caller owns the pool).
func NewPgLifecycleGate(cfg *meta.Config) *PgLifecycleGate { return &PgLifecycleGate{cfg: cfg} }

var _ LifecycleGate = (*PgLifecycleGate)(nil)

func (g *PgLifecycleGate) transition(ctx context.Context, realityID uuid.UUID, from, to, actor, reason string) error {
	_, err := meta.AttemptStateTransition(ctx, g.cfg, meta.TransitionRequest{
		ResourceType: "reality",
		ResourceID:   realityID.String(),
		FromState:    from,
		ToState:      to,
		Reason:       reason,
		Actor:        meta.Actor{Type: meta.ActorAdmin, ID: actor},
	})
	return err
}

// FreezeForRebuild transitions active → frozen.
func (g *PgLifecycleGate) FreezeForRebuild(ctx context.Context, realityID uuid.UUID, actor, reason string) error {
	if err := g.transition(ctx, realityID, "active", "frozen", actor, reason); err != nil {
		return fmt.Errorf("freeze active→frozen: %w", err)
	}
	return nil
}

// ThawAfterRebuild transitions frozen → active.
func (g *PgLifecycleGate) ThawAfterRebuild(ctx context.Context, realityID uuid.UUID, actor, reason string) error {
	if err := g.transition(ctx, realityID, "frozen", "active", actor, reason); err != nil {
		return fmt.Errorf("thaw frozen→active: %w", err)
	}
	return nil
}

// ── PgProjectionTruncator — TRUNCATE one projection table (per-reality DB). ───

// PgProjectionTruncator TRUNCATEs a projection table in the reality's shard DB.
// The pool is already reality-scoped (resolved by the handler), so realityID is
// only used for the error message. The table name is re-validated against the
// allowlist before interpolation (defense in depth — the dispatcher + the
// orchestrator already validate it).
type PgProjectionTruncator struct {
	pool *pgxpool.Pool
}

// NewPgProjectionTruncator binds the per-reality pool (caller-owned).
func NewPgProjectionTruncator(pool *pgxpool.Pool) *PgProjectionTruncator {
	return &PgProjectionTruncator{pool: pool}
}

var _ ProjectionTruncator = (*PgProjectionTruncator)(nil)

// Truncate runs `TRUNCATE TABLE <projection> RESTART IDENTITY`. projection is
// re-validated against the allowlist (never interpolate an unchecked name).
func (t *PgProjectionTruncator) Truncate(ctx context.Context, realityID uuid.UUID, projection string) error {
	if !IsKnownProjectionTable(projection) {
		return fmt.Errorf("refusing to TRUNCATE unknown table %q", projection)
	}
	// Safe: projection is allowlisted (a fixed identifier set) — no user text.
	if _, err := t.pool.Exec(ctx, fmt.Sprintf("TRUNCATE TABLE %s RESTART IDENTITY", projection)); err != nil {
		return fmt.Errorf("truncate %s (reality %s): %w", projection, realityID, err)
	}
	return nil
}

// ── SubprocessRebuildInvoker — exec the world-service `rebuilder` binary. ─────

// SubprocessRebuildInvoker runs the world-service `rebuilder` worker as a
// subprocess (Q-L3-3). The per-reality DSN is passed via the REALITY_DB_URL env
// (NOT a flag — keeps the password off the process table); reality_id +
// projection go as flags. stdout is the JSON RebuildStats.
type SubprocessRebuildInvoker struct {
	binPath string
	dsn     string
}

// NewSubprocessRebuildInvoker binds the rebuilder binary path + the reality DSN.
func NewSubprocessRebuildInvoker(binPath, dsn string) *SubprocessRebuildInvoker {
	return &SubprocessRebuildInvoker{binPath: binPath, dsn: dsn}
}

var _ RebuildInvoker = (*SubprocessRebuildInvoker)(nil)

// Rebuild execs the rebuilder and parses its stdout RebuildStats. Exit 0 (clean)
// and exit 1 (some aggregates dead-lettered, reflected in stats) both yield a
// parsed stats object — the orchestrator decides based on AggregatesFailed. Any
// other exit code (or unparseable stdout) is a fatal error.
func (i *SubprocessRebuildInvoker) Rebuild(ctx context.Context, realityID uuid.UUID, projection string) (RebuildStats, error) {
	cmd := exec.CommandContext(ctx, i.binPath,
		"--reality-id", realityID.String(),
		"--projection", projection,
	)
	cmd.Env = append(os.Environ(), "REALITY_DB_URL="+i.dsn)
	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	runErr := cmd.Run()

	// Always try to parse stats from stdout first — exit 1 still prints them.
	var stats RebuildStats
	parseErr := json.Unmarshal([]byte(strings.TrimSpace(stdout.String())), &stats)

	if runErr != nil {
		var exitErr *exec.ExitError
		if errors.As(runErr, &exitErr) && exitErr.ExitCode() == 1 && parseErr == nil {
			// Exit 1 = some aggregates dead-lettered; stats are valid and carry
			// AggregatesFailed>0, so the orchestrator leaves the reality frozen.
			return stats, nil
		}
		return RebuildStats{}, fmt.Errorf("rebuilder exec failed: %w (stderr: %s)", runErr, truncate(stderr.String(), 512))
	}
	if parseErr != nil {
		return RebuildStats{}, fmt.Errorf("rebuilder produced unparseable stats %q: %w (stderr: %s)", truncate(stdout.String(), 256), parseErr, truncate(stderr.String(), 256))
	}
	return stats, nil
}

func truncate(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
