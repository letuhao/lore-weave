// services/migration-orchestrator/cmd/canary-drill — S13 (Inc-3) migration
// canary-gated rollout drill, LIVE against real per-reality Postgres DBs.
//
// Drives the REAL canary.Orchestrator + runner.Runner. The Applier runs REAL
// migration SQL against REAL per-reality databases (via `docker exec psql` on the
// scale rig — no pgx dep added to this service module). The VerificationGate is
// injected (no production verification suite exists yet — D-MIGRATE-CLI-LIVE-WIRING),
// so "live" = real runner + real SQL + real per-reality isolation, gate injected.
//
// The migration's two abort paths (canary.go:206 Phase-1 apply, :217 Phase-2 gate)
// are DISTINCT and each gets its own bite. The headline invariant both protect: a
// broken/unverified migration is NEVER fanned out to the rest of the fleet.
//
// Modes:
//
//	-mode apply-abort  The migration is broken for EVERY reality (bad SQL). The
//	                   canary applies it → real SQL fails → orchestrator aborts
//	                   `canary_apply_failed` BEFORE the gate → the rest are NEVER
//	                   attempted (0 fanout migration_started). BITE: a buggy flow that
//	                   ignores CanaryResult.Succeeded fans out anyway → the rest ARE
//	                   attempted → caught.
//	-mode verify-abort The migration applies fine, but post-apply verification fails
//	                   (gate.Fail). Orchestrator aborts `canary_verification_*` → the
//	                   rest are NEVER attempted. BITE: gate.Pass when verification
//	                   should fail → fanout proceeds → the rest ARE attempted → caught.
//	-mode isolation    The migration is good for all but ONE poison fanout reality
//	                   (transient failure → retries to exhaustion). Canary OK, gate
//	                   Pass, fanout runs → the poison reality dead-letters
//	                   (migration_failed, attempts==MaxAttempts) while the rest succeed;
//	                   the runner concurrency cap is respected (peak <= cap).
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/canary"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/runner"
)

const (
	migID    = "l1d-canary-probe"
	goodSQL  = `CREATE TABLE IF NOT EXISTS l1d_probe (id int primary key)`
	badSQL   = `CREATE TABLE l1d_probe (@@@ this is deliberately invalid SQL @@@)`
	probeSQL = `SELECT to_regclass('l1d_probe') IS NOT NULL`
)

var (
	container = "scale-pg-shard-0"
	pgUser    = "foundation"
	dbPrefix  = "l1d_" // db name = l1d_<realityID>
)

// pgApplier runs the migration SQL against the per-reality DB via docker exec psql.
// poison[realityID]=true ⇒ run badSQL (a real Postgres syntax error). When transient
// is set, a poison failure is wrapped in runner.ErrTransient so the runner retries to
// exhaustion (exercises the dead-letter path); otherwise it is a permanent error.
type pgApplier struct {
	poison    map[string]bool
	transient bool
	peak      *runner.PeakConcurrency
}

func (a *pgApplier) Apply(ctx context.Context, realityID, _ string) (bool, error) {
	a.peak.Enter()
	defer a.peak.Exit()
	sql := goodSQL
	if a.poison[realityID] {
		sql = badSQL
	}
	out, err := psql(ctx, dbPrefix+realityID, sql)
	if err != nil {
		if a.transient {
			return false, fmt.Errorf("apply %s: %s: %w", realityID, oneLine(out), runner.ErrTransient)
		}
		return false, fmt.Errorf("apply %s: %s", realityID, oneLine(out))
	}
	return true, nil
}

// recorder implements BOTH runner.Auditor + runner.StateWriter + canary.AbortAuditor
// so the drill can assert on every event the control flow emits.
type recorder struct {
	mu      sync.Mutex
	events  []runner.AuditEvent
	applied []string
	failed  []string
	aborts  []string // realityID@reason
}

func (r *recorder) RecordEvent(_ context.Context, e runner.AuditEvent) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, e)
	return nil
}
func (r *recorder) MarkApplied(_ context.Context, realityID, _ string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.applied = append(r.applied, realityID)
	return nil
}
func (r *recorder) MarkFailed(_ context.Context, realityID, _, reason string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.failed = append(r.failed, realityID+"@"+reason)
	return nil
}
func (r *recorder) RecordAbort(_ context.Context, realityID, _, _, reason string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.aborts = append(r.aborts, realityID+"@"+reason)
	return nil
}

// fanoutStarted counts migration_started events whose RunID marks them as fanout
// jobs (RunID prefix "fanout-") — i.e. the migration was ATTEMPTED on a non-canary
// reality. The whole point of the canary gate is to keep this 0 on an abort.
func (r *recorder) fanoutStarted() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	n := 0
	for _, e := range r.events {
		if e.EventType == "migration_started" && strings.HasPrefix(e.RunID, "fanout-") {
			n++
		}
	}
	return n
}

func (r *recorder) countFailed() int { r.mu.Lock(); defer r.mu.Unlock(); return len(r.failed) }

// runnerDispatcher adapts runner.Runner to canary.Dispatcher (the canary + runner
// packages re-declare Job/Result to avoid an import cycle; the live `migrate` cmd
// binds them the same way).
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

type fastSleeper struct{}

func (fastSleeper) Sleep(ctx context.Context, _ time.Duration) {
	select {
	case <-ctx.Done():
	case <-time.After(time.Millisecond):
	}
}

func main() {
	mode := flag.String("mode", "apply-abort", "apply-abort | verify-abort | isolation")
	n := flag.Int("realities", 5, "number of realities (canary = smallest)")
	cap := flag.Int("concurrency", 2, "runner concurrency cap")
	flag.Parse()
	os.Exit(run(*mode, *n, *cap))
}

func run(mode string, n, cap int) int {
	realities := realityIDs(n)
	canaryR := realities[0] // LexicographicSelector picks the smallest

	switch mode {
	case "apply-abort":
		return applyAbort(realities, canaryR, cap)
	case "verify-abort":
		return verifyAbort(realities, canaryR, cap)
	case "isolation":
		return isolation(realities, canaryR, cap)
	default:
		die("unknown mode %q", mode)
		return 2
	}
}

// applyAbort: broken migration everywhere. The canary apply fails → abort before the
// gate → the rest are NEVER attempted. Bite: ignore the canary failure → fanout runs.
func applyAbort(realities []string, canaryR string, cap int) int {
	ctx := context.Background()
	resetDBs(ctx, realities)

	poison := allPoison(realities)
	rec := &recorder{}
	orch := buildOrch(rec, poison, false, cap, nil) // gate unused (apply fails first)

	outcome, err := orch.Run(ctx, realities, migID)
	if err != nil {
		die("orchestrator: %v", err)
	}
	realFanout := rec.fanoutStarted()
	probes := probeCount(ctx, exclude(realities, canaryR))

	// BITE: a buggy flow that ignores CanaryResult.Succeeded and fans out anyway.
	biteRec := &recorder{}
	buggyIgnoreCanaryFail(ctx, realities, canaryR, biteRec, poison, cap)
	biteFanout := biteRec.fanoutStarted()

	pass := outcome.Aborted && outcome.AbortReason == "canary_apply_failed" &&
		len(outcome.FanoutResults) == 0 && realFanout == 0 && probes == 0
	bitePass := biteFanout == len(realities)-1

	fmt.Printf(`{"mode":"apply-abort","aborted":%t,"reason":%q,"fanout_started":%d,"fanout_probes":%d,"bite_fanout_started":%d}`+"\n",
		outcome.Aborted, outcome.AbortReason, realFanout, probes, biteFanout)
	return verdict(pass, bitePass,
		fmt.Sprintf("canary apply failed → abort_canary_apply_failed, %d realities NOT attempted (0 fanout, 0 probes)", len(realities)-1),
		fmt.Sprintf("buggy ignore-canary-fail fanned out to %d realities — the Phase-1 guard is non-vacuous", biteFanout))
}

// verifyAbort: migration applies fine, but verification fails (gate.Fail) → abort →
// the rest are NEVER attempted. Bite: gate.Pass when it should fail → fanout runs.
func verifyAbort(realities []string, canaryR string, cap int) int {
	ctx := context.Background()
	resetDBs(ctx, realities)

	rec := &recorder{}
	gate := canary.NewVerificationGate()
	gate.Fail("data_check_failed") // verification verdict: the applied migration is bad
	orch := buildOrch(rec, map[string]bool{}, false, cap, gate)

	outcome, err := orch.Run(ctx, realities, migID)
	if err != nil {
		die("orchestrator: %v", err)
	}
	realFanout := rec.fanoutStarted()
	probes := probeCount(ctx, exclude(realities, canaryR))

	// BITE: pass the gate when verification should have failed → fanout proceeds.
	biteRec := &recorder{}
	biteGate := canary.NewVerificationGate()
	biteGate.Pass()
	biteOrch := buildOrch(biteRec, map[string]bool{}, false, cap, biteGate)
	resetDBs(ctx, realities)
	_, _ = biteOrch.Run(ctx, realities, migID)
	biteFanout := biteRec.fanoutStarted()

	pass := outcome.Aborted && strings.HasPrefix(outcome.AbortReason, "canary_verification_") &&
		len(outcome.FanoutResults) == 0 && realFanout == 0 && probes == 0
	bitePass := biteFanout == len(realities)-1

	fmt.Printf(`{"mode":"verify-abort","aborted":%t,"reason":%q,"fanout_started":%d,"fanout_probes":%d,"bite_fanout_started":%d}`+"\n",
		outcome.Aborted, outcome.AbortReason, realFanout, probes, biteFanout)
	return verdict(pass, bitePass,
		fmt.Sprintf("verification FAIL → %s, %d realities NOT attempted (0 fanout, 0 probes)", outcome.AbortReason, len(realities)-1),
		fmt.Sprintf("gate.Pass when it should fail fanned out to %d realities — the Phase-2 gate is load-bearing", biteFanout))
}

// isolation: one poison fanout reality dead-letters (retries exhausted) while the
// rest succeed; the runner concurrency cap is respected.
func isolation(realities []string, canaryR string, cap int) int {
	ctx := context.Background()
	resetDBs(ctx, realities)

	// Poison ONE fanout reality (not the canary) with a transient failure.
	fanout := exclude(realities, canaryR)
	poisonR := fanout[len(fanout)/2]
	rec := &recorder{}
	peak := &runner.PeakConcurrency{}
	orch := buildOrchPeak(rec, map[string]bool{poisonR: true}, true, cap, mustGatePass(), peak)

	outcome, err := orch.Run(ctx, realities, migID)
	if err != nil {
		die("orchestrator: %v", err)
	}

	// The poison reality dead-letters; the rest of the fanout succeed.
	failed := rec.countFailed()
	poisonAttempts := attemptsFor(outcome.FanoutResults, poisonR)
	succeededOthers := 0
	for _, r := range outcome.FanoutResults {
		if r.Job.RealityID != poisonR && r.Succeeded {
			succeededOthers++
		}
	}
	otherProbes := probeCount(ctx, exclude(fanout, poisonR))
	canaryProbe := probeCount(ctx, []string{canaryR})

	pass := outcome.Verified && failed == 1 &&
		poisonAttempts == runner.DefaultMaxAttempts &&
		succeededOthers == len(fanout)-1 &&
		otherProbes == len(fanout)-1 && canaryProbe == 1 &&
		peak.Peak() <= cap && peak.Peak() >= 1

	fmt.Printf(`{"mode":"isolation","verified":%t,"poison":%q,"failed":%d,"poison_attempts":%d,"others_succeeded":%d,"other_probes":%d,"peak_concurrency":%d,"cap":%d}`+"\n",
		outcome.Verified, poisonR, failed, poisonAttempts, succeededOthers, otherProbes, peak.Peak(), cap)
	if !pass {
		fmt.Fprintf(os.Stderr, "FAIL: per-reality isolation broken — expected exactly 1 dead-letter (attempts=%d), %d others succeeded, peak<=%d\n",
			runner.DefaultMaxAttempts, len(fanout)-1, cap)
		return 1
	}
	fmt.Fprintf(os.Stderr, "PASS: poison reality %s dead-lettered after %d attempts; %d others migrated; peak concurrency %d <= cap %d\n",
		poisonR, poisonAttempts, succeededOthers, peak.Peak(), cap)
	return 0
}

// buggyIgnoreCanaryFail models the Phase-1 bug: run the canary, then fan out to the
// rest REGARDLESS of the canary result. Proves the real orchestrator's guard matters.
func buggyIgnoreCanaryFail(ctx context.Context, realities []string, canaryR string, rec *recorder, poison map[string]bool, cap int) {
	peak := &runner.PeakConcurrency{}
	r := mustRunner(rec, &pgApplier{poison: poison, peak: peak}, cap)
	// canary (ignored)
	_ = r.Run(ctx, []runner.Job{{RealityID: canaryR, MigrationID: migID, RunID: "canary-" + migID}})
	// fan out anyway
	var jobs []runner.Job
	for _, rr := range exclude(realities, canaryR) {
		jobs = append(jobs, runner.Job{RealityID: rr, MigrationID: migID, RunID: "fanout-" + migID + "-" + rr})
	}
	_ = r.Run(ctx, jobs)
}

// ── wiring helpers ──────────────────────────────────────────────────────────────

func buildOrch(rec *recorder, poison map[string]bool, transient bool, cap int, gate *canary.VerificationGate) *canary.Orchestrator {
	return buildOrchPeak(rec, poison, transient, cap, gate, &runner.PeakConcurrency{})
}

func buildOrchPeak(rec *recorder, poison map[string]bool, transient bool, cap int, gate *canary.VerificationGate, peak *runner.PeakConcurrency) *canary.Orchestrator {
	r := mustRunner(rec, &pgApplier{poison: poison, transient: transient, peak: peak}, cap)
	cfg := &canary.Config{
		Dispatcher:        runnerDispatcher{r: r},
		Selector:          canary.LexicographicSelector{},
		Aborter:           rec,
		VerificationGate:  gate,
		VerificationDelay: 10 * time.Second,
	}
	orch, err := canary.New(cfg)
	if err != nil {
		die("canary.New: %v", err)
	}
	return orch
}

func mustRunner(rec *recorder, app runner.Applier, cap int) *runner.Runner {
	r, err := runner.New(&runner.Config{
		Concurrency: cap,
		Applier:     app,
		Auditor:     rec,
		StateWriter: rec,
		Sleeper:     fastSleeper{},
		BaseBackoff: time.Millisecond,
	})
	if err != nil {
		die("runner.New: %v", err)
	}
	return r
}

func mustGatePass() *canary.VerificationGate {
	g := canary.NewVerificationGate()
	g.Pass()
	return g
}

// ── DB helpers (docker exec psql — real SQL on real per-reality DBs) ──────────────

func resetDBs(ctx context.Context, realities []string) {
	for _, r := range realities {
		db := dbPrefix + r
		admExec(ctx, fmt.Sprintf("DROP DATABASE IF EXISTS %s WITH (FORCE)", db))
		admExec(ctx, fmt.Sprintf("CREATE DATABASE %s", db))
	}
}

func probeCount(ctx context.Context, realities []string) int {
	n := 0
	for _, r := range realities {
		out, err := psql(ctx, dbPrefix+r, probeSQL)
		if err == nil && strings.Contains(out, "t") {
			n++
		}
	}
	return n
}

// psql runs a statement in a per-reality DB. ON_ERROR_STOP makes a bad statement a
// non-zero exit (real SQL failure surfaces as err).
func psql(ctx context.Context, db, sql string) (string, error) {
	cmd := exec.CommandContext(ctx, "docker", "exec", "-i", container,
		"psql", "-tA", "-v", "ON_ERROR_STOP=1", "-U", pgUser, "-d", db, "-c", sql)
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func admExec(ctx context.Context, sql string) {
	cmd := exec.CommandContext(ctx, "docker", "exec", "-i", container,
		"psql", "-q", "-v", "ON_ERROR_STOP=1", "-U", pgUser, "-d", "foundation", "-c", sql)
	if out, err := cmd.CombinedOutput(); err != nil {
		die("admin psql failed: %s: %v", oneLine(string(out)), err)
	}
}

// ── small utils ──────────────────────────────────────────────────────────────────

func realityIDs(n int) []string {
	ids := make([]string, n)
	for i := range n {
		ids[i] = fmt.Sprintf("r%03d", i)
	}
	sort.Strings(ids)
	return ids
}

func allPoison(realities []string) map[string]bool {
	m := make(map[string]bool, len(realities))
	for _, r := range realities {
		m[r] = true
	}
	return m
}

func exclude(all []string, drop string) []string {
	out := make([]string, 0, len(all))
	for _, r := range all {
		if r != drop {
			out = append(out, r)
		}
	}
	return out
}

func attemptsFor(results []canary.Result, realityID string) int {
	for _, r := range results {
		if r.Job.RealityID == realityID {
			return r.Attempts
		}
	}
	return -1
}

func verdict(pass, bitePass bool, passMsg, biteMsg string) int {
	if !pass {
		fmt.Fprintf(os.Stderr, "FAIL: %s — did NOT hold\n", passMsg)
		return 1
	}
	if !bitePass {
		fmt.Fprintf(os.Stderr, "FAIL(bite vacuous): the buggy flow did NOT misbehave — the check cannot fail; %s\n", biteMsg)
		return 1
	}
	fmt.Fprintf(os.Stderr, "PASS: %s\nPASS(bite): %s\n", passMsg, biteMsg)
	return 0
}

func oneLine(s string) string { return strings.Join(strings.Fields(s), " ") }

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "canary-drill: "+format+"\n", a...)
	os.Exit(2)
}
