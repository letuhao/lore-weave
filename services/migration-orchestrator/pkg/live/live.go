// Package live binds the migration orchestrator's pure logic (pkg/canary +
// pkg/runner) to its real production collaborators, closing
// D-MIGRATE-CLI-LIVE-WIRING (Wave 1 / W1.2):
//
//   - SQLApplier  — runs a migration's UP SQL on each per-reality DB (pgx),
//     resolving the DSN from reality_registry via contracts/realityreg.
//   - MetaCollaborator — the runner's Auditor + StateWriter and the canary's
//     AbortAuditor, all writing through contracts/meta.MetaWrite so every
//     reality_migration_audit / instance_schema_migrations row lands with its
//     meta_write_audit row in the SAME TX (I8).
//   - RunMigration — the productionized S13 canary-drill flow: breaking →
//     canary.Orchestrator (canary → verify gate → fan-out); non-breaking →
//     runner.Runner directly (concurrency cap 10).
//
// Cross-DB non-atomicity (plan review #7): the Applier writes the per-reality
// DB while the audit/state writes hit the META DB. A crash between them can
// desync instance_schema_migrations from the reality's real schema. Recovery is
// the runner's idempotent re-run: the migration SQL is IF-NOT-EXISTS-shaped and
// MarkApplied/MarkFailed are check-then-write (UPDATE if a prior row exists).
package live

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/contracts/realityreg"
	"github.com/loreweave/foundation/sdks/go/metapg"

	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/canary"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/runner"
)

// ─── clock / uuid (mirror capacity-override) ─────────────────────────────────

type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

// ─── SQLApplier — real per-reality SQL application (runner.Applier) ───────────

// SQLApplier runs a migration's UP SQL against each per-reality database. It
// caches one pgx pool per reality and the SQL text per migration. Concurrency-
// safe (the runner calls Apply from up to Concurrency goroutines).
type SQLApplier struct {
	dsn       realityreg.DSNConfig
	routes    map[string]realityreg.Reality // reality_id → routing
	sqlDir    string

	mu       sync.Mutex
	pools    map[string]*pgxpool.Pool
	sqlCache map[string]string
}

// NewSQLApplier builds an applier over a known fleet. `sqlDir` holds
// `<migration_id>.up.sql` files (contracts/migrations/per_reality).
func NewSQLApplier(dsn realityreg.DSNConfig, fleet []realityreg.Reality, sqlDir string) *SQLApplier {
	routes := make(map[string]realityreg.Reality, len(fleet))
	for _, r := range fleet {
		routes[r.ID] = r
	}
	return &SQLApplier{
		dsn:      dsn,
		routes:   routes,
		sqlDir:   sqlDir,
		pools:    map[string]*pgxpool.Pool{},
		sqlCache: map[string]string{},
	}
}

// Apply runs the migration UP SQL on the reality's DB. A Postgres error is a
// permanent failure (not runner.ErrTransient) — a broken migration must fail
// the canary fast, not retry to exhaustion.
func (a *SQLApplier) Apply(ctx context.Context, realityID, migrationID string) (bool, error) {
	sql, err := a.loadSQL(migrationID)
	if err != nil {
		return false, err
	}
	pool, err := a.poolFor(ctx, realityID)
	if err != nil {
		return false, err
	}
	if _, err := pool.Exec(ctx, sql); err != nil {
		return false, fmt.Errorf("apply %s on reality %s: %w", migrationID, realityID, err)
	}
	return true, nil
}

func (a *SQLApplier) loadSQL(migrationID string) (string, error) {
	a.mu.Lock()
	if sql, ok := a.sqlCache[migrationID]; ok {
		a.mu.Unlock()
		return sql, nil
	}
	a.mu.Unlock()
	path := filepath.Join(a.sqlDir, migrationID+".up.sql")
	raw, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return "", fmt.Errorf("read migration sql %s: %w", path, err)
	}
	a.mu.Lock()
	a.sqlCache[migrationID] = string(raw)
	a.mu.Unlock()
	return string(raw), nil
}

func (a *SQLApplier) poolFor(ctx context.Context, realityID string) (*pgxpool.Pool, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if p, ok := a.pools[realityID]; ok {
		return p, nil
	}
	route, ok := a.routes[realityID]
	if !ok {
		return nil, fmt.Errorf("reality %s not in fleet (no routing)", realityID)
	}
	dsn, err := a.dsn.DSN(route.DBHost, route.DBName)
	if err != nil {
		return nil, fmt.Errorf("resolve dsn for %s: %w", realityID, err)
	}
	p, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, fmt.Errorf("pool for %s: %w", realityID, err)
	}
	a.pools[realityID] = p
	return p, nil
}

// Close releases every per-reality pool.
func (a *SQLApplier) Close() {
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, p := range a.pools {
		p.Close()
	}
	a.pools = map[string]*pgxpool.Pool{}
}

// ─── MetaCollaborator — Auditor + StateWriter + AbortAuditor via MetaWrite ────

// MetaCollaborator routes every audit/state write through contracts/meta.
// MetaWrite, so each row lands with its meta_write_audit row in the same TX (I8).
// One per migration run (the runID groups all of a run's audit rows).
type MetaCollaborator struct {
	cfg   *meta.Config
	pool  *pgxpool.Pool // for the instance_schema_migrations existence read only
	runID uuid.UUID
	actor meta.Actor
}

// NewMetaCollaborator wires the meta config over the meta DB pool.
func NewMetaCollaborator(pool *pgxpool.Pool, allow meta.Allowlist, runID uuid.UUID) *MetaCollaborator {
	return &MetaCollaborator{
		cfg: &meta.Config{
			DB:           metapg.New(pool),
			Allowlist:    allow,
			QueryBuilder: meta.PostgresQueryBuilder{},
			Clock:        sysClock{},
			UUIDGen:      randUUID{},
			// Outbox nil: reality_migration_audit emits migration.audit_recorded,
			// but there is no V1 consumer (matches capacity-override's dropped
			// scaling.event). The meta_write_audit row still lands (I8).
		},
		pool:  pool,
		runID: runID,
		actor: meta.Actor{Type: meta.ActorService, ID: "migration-orchestrator"},
	}
}

// RecordEvent (runner.Auditor) — one reality_migration_audit row per attempt.
func (m *MetaCollaborator) RecordEvent(ctx context.Context, e runner.AuditEvent) error {
	return m.audit(ctx, e.RealityID, e.MigrationID, e.EventType, e.AttemptNumber, e.FailureDetail)
}

// RecordAbort (canary.AbortAuditor) — migration_aborted for a not-attempted reality.
func (m *MetaCollaborator) RecordAbort(ctx context.Context, realityID, migrationID, _ /*runID label*/, reason string) error {
	return m.audit(ctx, realityID, migrationID, "migration_aborted", 1, map[string]any{"reason": reason})
}

func (m *MetaCollaborator) audit(ctx context.Context, realityID, migrationID, eventType string, attempt int, detail map[string]any) error {
	rid, err := uuid.Parse(realityID)
	if err != nil {
		return fmt.Errorf("audit: reality_id %q not a uuid: %w", realityID, err)
	}
	nv := map[string]any{
		"reality_id":     rid,
		"migration_id":   migrationID,
		"run_id":         m.runID,
		"event_type":     eventType,
		"attempt_number": attempt,
		// occurred_at uses the DB default now().
	}
	if len(detail) > 0 {
		b, err := json.Marshal(detail)
		if err != nil {
			return fmt.Errorf("audit: marshal failure_detail: %w", err)
		}
		nv["failure_detail"] = b
	}
	intent := meta.MetaWriteIntent{
		Table:     "reality_migration_audit",
		Operation: meta.OpInsert,
		PK:        map[string]any{"audit_id": m.cfg.UUIDGen.New()},
		NewValues: nv,
		Actor:     m.actor,
		Reason:    "migration audit: " + eventType,
	}
	_, err = meta.MetaWrite(ctx, m.cfg, intent)
	return err
}

// MarkApplied (runner.StateWriter) — final applied state.
func (m *MetaCollaborator) MarkApplied(ctx context.Context, realityID, migrationID string) error {
	return m.markState(ctx, realityID, migrationID, nil)
}

// MarkFailed (runner.StateWriter) — final failed state with a reason.
func (m *MetaCollaborator) MarkFailed(ctx context.Context, realityID, migrationID, reason string) error {
	return m.markState(ctx, realityID, migrationID, &reason)
}

// markState is check-then-write on instance_schema_migrations (PK =
// reality_id+migration_id). Cold path, one writer per (reality,migration) per
// run, so the non-atomic check→write is safe; this gives idempotent re-runs
// (re-mark after a prior failed/applied row → UPDATE, not a PK-conflict 500).
func (m *MetaCollaborator) markState(ctx context.Context, realityID, migrationID string, failureReason *string) error {
	rid, err := uuid.Parse(realityID)
	if err != nil {
		return fmt.Errorf("markState: reality_id %q not a uuid: %w", realityID, err)
	}
	var exists bool
	if err := m.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM instance_schema_migrations WHERE reality_id=$1 AND migration_id=$2)`,
		rid, migrationID,
	).Scan(&exists); err != nil {
		return fmt.Errorf("markState: existence check: %w", err)
	}
	nv := map[string]any{
		"applied_at":     time.Now().UTC(),
		"applied_by":     "migration-orchestrator",
		"failure_reason": failureReason, // nil clears it on a successful re-run
	}
	op := meta.OpInsert
	if exists {
		op = meta.OpUpdate
	}
	intent := meta.MetaWriteIntent{
		Table:     "instance_schema_migrations",
		Operation: op,
		PK:        map[string]any{"reality_id": rid, "migration_id": migrationID},
		NewValues: nv,
		Actor:     m.actor,
		Reason:    "migration state",
	}
	_, err = meta.MetaWrite(ctx, m.cfg, intent)
	return err
}

// ─── RunMigration — the live dispatch ────────────────────────────────────────

// Verifier runs the post-apply verification suite for a breaking migration's
// canary reality and returns the verdict. V1 has no suite (the production CLI
// injects a fail-closed verifier); the drill injects explicit Pass/Fail.
type Verifier func(ctx context.Context, canaryReality, migrationID string) (ok bool, reason string)

// Options configures a live migration run. The audit/state/abort collaborators
// are taken as interfaces (the production *MetaCollaborator satisfies all three;
// tests inject fakes) so the dispatch logic is unit-testable without a DB.
type Options struct {
	MigrationID string
	Breaking    bool
	Fleet       []realityreg.Reality // realities to migrate (canary included)
	Applier     runner.Applier
	Auditor     runner.Auditor
	StateWriter runner.StateWriter
	Aborter     canary.AbortAuditor
	Concurrency int
	Verifier    Verifier      // breaking only
	GateDelay   time.Duration // breaking only; max wait for the verdict
}

// JobResult is the neutral per-reality outcome (both the runner and canary
// packages have their own Result type; this is the live package's view).
type JobResult struct {
	RealityID string
	Succeeded bool
	Attempts  int
}

// Outcome reports what happened (mirrors canary.CanaryOutcome for both paths).
type Outcome struct {
	Breaking      bool
	Aborted       bool
	AbortReason   string
	CanaryReality string
	Results       []JobResult
}

// runnerDispatcher adapts runner.Runner to canary.Dispatcher (the two packages
// re-declare Job/Result to avoid an import cycle).
type runnerDispatcher struct{ r *runner.Runner }

func (d runnerDispatcher) Run(ctx context.Context, jobs []canary.Job) []canary.Result {
	rjobs := make([]runner.Job, len(jobs))
	for i, j := range jobs {
		rjobs[i] = runner.Job{RealityID: j.RealityID, MigrationID: j.MigrationID, RunID: j.RunID}
	}
	rres := d.r.Run(ctx, rjobs)
	out := make([]canary.Result, len(rres))
	for i, rr := range rres {
		out[i] = canary.Result{
			Job:        canary.Job{RealityID: rr.Job.RealityID, MigrationID: rr.Job.MigrationID, RunID: rr.Job.RunID},
			Succeeded:  rr.Succeeded,
			Attempts:   rr.Attempts,
			FinalError: rr.FinalError,
		}
	}
	return out
}

// RunMigration applies a migration across the fleet. Breaking → canary gate;
// non-breaking → direct runner fan-out under the concurrency cap.
func RunMigration(ctx context.Context, opt Options) (*Outcome, error) {
	if len(opt.Fleet) == 0 {
		return nil, fmt.Errorf("live: empty fleet")
	}
	if opt.Applier == nil || opt.Auditor == nil || opt.StateWriter == nil {
		return nil, fmt.Errorf("live: Applier, Auditor and StateWriter required")
	}
	if opt.Breaking && opt.Aborter == nil {
		return nil, fmt.Errorf("live: Aborter required for breaking migrations")
	}
	conc := opt.Concurrency
	if conc <= 0 {
		conc = runner.DefaultConcurrency
	}
	r, err := runner.New(&runner.Config{
		Concurrency: conc,
		Applier:     opt.Applier,
		Auditor:     opt.Auditor,
		StateWriter: opt.StateWriter,
		Sleeper:     runner.NewRealSleeper(),
	})
	if err != nil {
		return nil, fmt.Errorf("live: runner.New: %w", err)
	}

	ids := make([]string, len(opt.Fleet))
	for i, fr := range opt.Fleet {
		ids[i] = fr.ID
	}

	if !opt.Breaking {
		jobs := make([]runner.Job, len(ids))
		for i, id := range ids {
			jobs[i] = runner.Job{RealityID: id, MigrationID: opt.MigrationID, RunID: "run-" + opt.MigrationID + "-" + id}
		}
		rres := r.Run(ctx, jobs)
		out := &Outcome{Breaking: false, Results: make([]JobResult, len(rres))}
		for i, rr := range rres {
			out.Results[i] = JobResult{RealityID: rr.Job.RealityID, Succeeded: rr.Succeeded, Attempts: rr.Attempts}
		}
		return out, nil
	}

	// Breaking: canary → verify gate → fan-out.
	gate := canary.NewVerificationGate()
	sel := canary.LexicographicSelector{}
	canaryReality, err := sel.Pick(ids)
	if err != nil {
		return nil, fmt.Errorf("live: select canary: %w", err)
	}
	gateDelay := opt.GateDelay
	if gateDelay <= 0 {
		gateDelay = 5 * time.Minute
	}
	verifier := opt.Verifier
	if verifier == nil {
		// Fail-closed default: no verification suite is wired in V1, so a
		// breaking migration must NOT fan out. SRE wires a real verifier when
		// the suite lands (remainder of D-MIGRATE-CLI-LIVE-WIRING).
		verifier = func(context.Context, string, string) (bool, string) {
			return false, "verification_suite_not_wired"
		}
	}
	// The verifier runs out-of-band and signals the gate. If the canary apply
	// fails, the orchestrator aborts at Phase 1 and never reads the gate — the
	// Pass/Fail here is simply ignored (non-blocking send), no goroutine leak.
	go func() {
		if ok, reason := verifier(ctx, canaryReality, opt.MigrationID); ok {
			gate.Pass()
		} else {
			gate.Fail(reason)
		}
	}()

	orch, err := canary.New(&canary.Config{
		Dispatcher:        runnerDispatcher{r: r},
		Selector:          sel,
		Aborter:           opt.Aborter,
		VerificationGate:  gate,
		VerificationDelay: gateDelay,
	})
	if err != nil {
		return nil, fmt.Errorf("live: canary.New: %w", err)
	}
	co, err := orch.Run(ctx, ids, opt.MigrationID)
	if err != nil {
		return nil, err
	}
	out := &Outcome{
		Breaking:      true,
		Aborted:       co.Aborted,
		AbortReason:   co.AbortReason,
		CanaryReality: co.CanaryReality,
	}
	out.Results = append(out.Results, JobResult{
		RealityID: co.CanaryResult.Job.RealityID,
		Succeeded: co.CanaryResult.Succeeded,
		Attempts:  co.CanaryResult.Attempts,
	})
	for _, fr := range co.FanoutResults {
		out.Results = append(out.Results, JobResult{
			RealityID: fr.Job.RealityID, Succeeded: fr.Succeeded, Attempts: fr.Attempts,
		})
	}
	return out, nil
}
