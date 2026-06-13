// Package runner executes conformance cases and maps each outcome to a verdict.
//
// The verdict mapping (plan §2.3) is the heart of S1:
//
//	skip_when predicate matched   → skip   (not applicable on this stack)
//	requires precondition unmet   → notrun (wanted to run, infra absent)
//	exit 0                        → pass
//	exit 1                        → fail   (the only gate-breaking verdict)
//	exit ≥2 / launch error        → notrun (harness/setup error) …
//	  … unless fail_closed_on_setup_error → fail
//
// Environment and Executor are interfaces so the mapping is unit-testable
// without real docker / shells; the OS-backed implementations live alongside.
package runner

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/loreweave/foundation/tests/conformance/internal/catalog"
	"github.com/loreweave/foundation/tests/conformance/internal/verdict"
)

// Environment answers the predicate queries used by requires/skip_when.
type Environment interface {
	// Provides reports whether a precondition is available (e.g. "docker",
	// "foundation-stack", "database_url"). An unmet/unknown requirement → notrun.
	Provides(requirement string) bool
	// Matches reports whether a stack predicate holds (e.g. "single-superuser",
	// "no-provisioner"). A matched predicate → skip. Unknown → does not match.
	Matches(predicate string) bool
}

// Executor runs a case command and returns its process exit code. launchErr is
// non-nil ONLY when the process could not be started (not for a non-zero exit).
// outputTail is a short tail of the case's combined stdout+stderr, used as the
// reason on failure.
type Executor interface {
	Run(ctx context.Context, command []string) (exitCode int, outputTail string, launchErr error)
}

// Runner pairs an environment with an executor.
type Runner struct {
	env         Environment
	exec        Executor
	caseTimeout time.Duration // 0 = no per-case ceiling
}

// New builds a Runner with no per-case timeout.
func New(env Environment, ex Executor) *Runner { return &Runner{env: env, exec: ex} }

// WithCaseTimeout sets a per-case execution ceiling (0 disables it) and returns
// the runner for chaining. A case that exceeds it → notrun ("timed out"), or
// fail if the case/kind is fail-closed.
func (r *Runner) WithCaseTimeout(d time.Duration) *Runner {
	r.caseTimeout = d
	return r
}

// Run executes every case in order and returns one Result per case. Run never
// returns an error — every outcome, including a harness failure, is a verdict.
func (r *Runner) Run(ctx context.Context, cases []catalog.Case) []verdict.Result {
	results := make([]verdict.Result, 0, len(cases))
	for _, c := range cases {
		results = append(results, r.runCase(ctx, c))
	}
	return results
}

func (r *Runner) runCase(parent context.Context, c catalog.Case) verdict.Result {
	start := time.Now()
	mk := func(v verdict.Verdict, reason string) verdict.Result {
		return verdict.Result{
			ID:          c.ID,
			Kind:        string(c.Kind),
			Verdict:     v,
			Reason:      reason,
			Invariant:   c.Invariant,
			Description: c.Description,
			DurationMS:  time.Since(start).Milliseconds(),
		}
	}

	// skip_when (intentional not-applicable) is evaluated before requires
	// (missing infra): a case the stack deliberately doesn't support should read
	// as skip, not notrun.
	for _, pred := range c.SkipWhen {
		if r.env.Matches(pred) {
			return mk(verdict.Skip, "not applicable: "+pred)
		}
	}
	for _, req := range c.Requires {
		if !r.env.Provides(req) {
			return mk(verdict.Notrun, "precondition unmet: "+req)
		}
	}

	ctx := parent
	if r.caseTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(parent, r.caseTimeout)
		defer cancel()
	}
	exitCode, outputTail, launchErr := r.exec.Run(ctx, c.Command)
	if r.caseTimeout > 0 && errors.Is(ctx.Err(), context.DeadlineExceeded) {
		v := verdict.Notrun
		if setupErrIsFail(c) {
			v = verdict.Fail
		}
		return mk(v, fmt.Sprintf("timed out after %s", r.caseTimeout))
	}
	v, reason := classify(c, exitCode, launchErr)
	if v == verdict.Fail && reason == "" {
		reason = outputTail
	}
	return mk(v, reason)
}

// classify is the pure exit-code → verdict mapping (plan §2.3).
func classify(c catalog.Case, exitCode int, launchErr error) (verdict.Verdict, string) {
	if launchErr != nil {
		if setupErrIsFail(c) {
			return verdict.Fail, "launch error: " + launchErr.Error()
		}
		return verdict.Notrun, "harness/setup error: " + launchErr.Error()
	}
	switch exitCode {
	case 0:
		return verdict.Pass, ""
	case 1:
		return verdict.Fail, ""
	default: // exit ≥2, or a signal/kill (negative) — a setup/harness error
		if setupErrIsFail(c) {
			return verdict.Fail, fmt.Sprintf("setup error: exit %d", exitCode)
		}
		return verdict.Notrun, fmt.Sprintf("harness/setup error: exit %d", exitCode)
	}
}

// setupErrIsFail reports whether a setup/harness error (exit ≥2 or a launch
// failure) is a hard fail for this case rather than a lenient notrun.
//
// go-test/rust-test exit ≥2 on a BUILD/compile failure — that is real breakage,
// not "couldn't run" — so those kinds fail-closed by default; a masked build
// failure would otherwise sail through the gate as notrun. lint/live-probe keep
// the lenient notrun default (a missing tool or an absent stack legitimately
// can't run). Any case may force fail-closed via fail_closed_on_setup_error.
func setupErrIsFail(c catalog.Case) bool {
	if c.FailClosedOnSetupError {
		return true
	}
	switch c.Kind {
	case catalog.KindGoTest, catalog.KindRustTest:
		return true
	default:
		return false
	}
}

// Summary aggregates a run's results for the gate decision + human output.
type Summary struct {
	Results []verdict.Result
}

// Summarize wraps results in a Summary.
func Summarize(results []verdict.Result) Summary { return Summary{Results: results} }

// Counts returns the per-verdict tally (all four keys always present).
func (s Summary) Counts() map[verdict.Verdict]int {
	m := map[verdict.Verdict]int{verdict.Pass: 0, verdict.Fail: 0, verdict.Notrun: 0, verdict.Skip: 0}
	for _, r := range s.Results {
		m[r.Verdict]++
	}
	return m
}

// Failed returns the gate-breaking results.
func (s Summary) Failed() []verdict.Result {
	var f []verdict.Result
	for _, r := range s.Results {
		if r.Verdict.GateBreaking() {
			f = append(f, r)
		}
	}
	return f
}

// GateExitCode is 1 iff any result is gate-breaking (Fail), else 0.
func (s Summary) GateExitCode() int {
	if len(s.Failed()) > 0 {
		return 1
	}
	return 0
}

// Render produces a human-readable summary: the headline tally plus one line per
// non-pass result (so notrun/skip/fail are never silent).
func (s Summary) Render() string {
	c := s.Counts()
	var b strings.Builder
	fmt.Fprintf(&b, "conformance: %d pass · %d fail · %d notrun · %d skip (of %d cases)\n",
		c[verdict.Pass], c[verdict.Fail], c[verdict.Notrun], c[verdict.Skip], len(s.Results))
	for _, r := range s.Results {
		if r.Verdict == verdict.Pass {
			continue
		}
		fmt.Fprintf(&b, "  %-6s %s", r.Verdict, r.ID)
		if r.Reason != "" {
			fmt.Fprintf(&b, " — %s", r.Reason)
		}
		b.WriteByte('\n')
	}
	return b.String()
}

// --- OS-backed implementations ---

// OSEnvironment answers predicates against the real host (PATH, env vars, a TCP
// probe of the foundation Postgres). Unknown predicates are conservatively
// "not provided" / "does not match".
type OSEnvironment struct{}

// Provides implements Environment against the host.
func (OSEnvironment) Provides(req string) bool {
	switch req {
	case "docker":
		_, err := exec.LookPath("docker")
		return err == nil
	case "cargo":
		// S6 loom-circuit-breaker is a rust-test (RUSTFLAGS=--cfg loom). On the
		// Go-only bare conformance runner cargo is absent → the case degrades to
		// notrun instead of fail-closed. A Rust-toolchain CI job (or a dev box)
		// provides it.
		_, err := exec.LookPath("cargo")
		return err == nil
	case "k6", "hyperfine", "benchstat", "bencher", "node":
		// S7 perf generators (F2–F5). Absent on the Go-only bare runner → the
		// perf live-probes degrade to notrun instead of fail-closed; the perf
		// CI jobs install them. benchstat also resolves from GOPATH/bin (go
		// install) — LookPath covers that when GOPATH/bin is on PATH.
		_, err := exec.LookPath(req)
		return err == nil
	case "foundation-stack":
		// "the live stack is up" = BOTH the foundation Postgres AND Redis are
		// reachable (publisher-smoke needs both; a PG-only check would
		// false-positive and then fail on Redis). On a bare CI runner neither is
		// booted (open item O1) → unmet → live-probes degrade to notrun rather
		// than running heavyweight compose-up logic.
		return dialOpen(envPort("FOUNDATION_PG_PORT", "55432")) &&
			dialOpen(envPort("FOUNDATION_REDIS_PORT", "56379"))
	case "database_url":
		return os.Getenv("DATABASE_URL") != ""
	default:
		return false
	}
}

// Matches implements Environment against the host.
func (OSEnvironment) Matches(pred string) bool {
	switch pred {
	case "single-superuser":
		return os.Getenv("CONFORMANCE_SINGLE_SUPERUSER") == "1"
	case "no-provisioner":
		return os.Getenv("CONFORMANCE_NO_PROVISIONER") == "1"
	default:
		return false
	}
}

// OSExecutor runs case commands from Dir (the repo root) and captures combined
// stdout+stderr for the failure reason.
type OSExecutor struct {
	Dir string
}

// Run implements Executor against the host.
func (e OSExecutor) Run(ctx context.Context, command []string) (int, string, error) {
	if len(command) == 0 {
		return -1, "", errors.New("empty command")
	}
	cmd := exec.CommandContext(ctx, command[0], command[1:]...)
	cmd.Dir = e.Dir
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &out
	err := cmd.Run()
	tail := outputTail(out.String(), 240)
	if err == nil {
		return 0, tail, nil
	}
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		return ee.ExitCode(), tail, nil
	}
	return -1, tail, err // could not launch the process
}

func outputTail(s string, max int) string {
	s = strings.TrimSpace(s)
	if len(s) <= max {
		return s
	}
	return "…" + s[len(s)-max:]
}

func envPort(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func dialOpen(port string) bool {
	conn, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", port), 750*time.Millisecond)
	if err != nil {
		return false
	}
	_ = conn.Close()
	return true
}
