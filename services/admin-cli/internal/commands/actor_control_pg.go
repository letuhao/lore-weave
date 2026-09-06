// actor_control_pg.go — SubprocessActorControlInvoker: exec the world-service
// `actor-control` worker.
//
// Mirrors SubprocessProvisionInvoker (provision_reality_pg.go): identifiers go
// as flags, secrets go as env so they never appear on the process table, stdout
// is one JSON object, and the exit code is the verdict. Like that one — and
// unlike the older rebuild invoker — the worker's environment is built
// EXPLICITLY from a declared struct rather than inheriting os.Environ(). An
// ambient ACTOR_CONTROL_META_DSN left in an operator's shell is precisely how a
// command lands on the wrong Postgres, and the worker has no credential
// defaults, so a missing field fails closed at exit 2.
package commands

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ActorControlWorkerEnv is the full set of connection settings the worker
// needs. Every field is required except Password (peer/trust auth is
// legitimate).
type ActorControlWorkerEnv struct {
	MetaDSN       string
	BridgeURL     string
	BridgeToken   string
	ShardHostPort string
	PGUser        string
	PGPassword    string
	// MetaAllowlist is the polyglot allowlist path the control plane validates
	// against. Required, not optional: without it the worker cannot BIND the
	// reality, and the bind is the check that stops a grant landing in a frozen
	// world. A defaulted path that happened not to exist would turn that check
	// into a startup error at best and a skipped check at worst.
	MetaAllowlist string
}

// Validate reports every missing required field at once.
func (e ActorControlWorkerEnv) Validate() error {
	var missing []string
	for _, f := range []struct {
		name string
		val  string
	}{
		{"ACTOR_CONTROL_META_DSN", e.MetaDSN},
		{"ACTOR_CONTROL_BRIDGE_URL", e.BridgeURL},
		{"ACTOR_CONTROL_BRIDGE_TOKEN", e.BridgeToken},
		{"ACTOR_CONTROL_SHARD_HOSTPORT", e.ShardHostPort},
		{"ACTOR_CONTROL_PG_USER", e.PGUser},
		{"ACTOR_CONTROL_META_ALLOWLIST", e.MetaAllowlist},
	} {
		if strings.TrimSpace(f.val) == "" {
			missing = append(missing, f.name)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("%w: actor-control worker env incomplete: %s",
			ErrInvalidActorControl, strings.Join(missing, ", "))
	}
	return nil
}

// environ renders the worker's environment. PATH is carried through so the
// binary can resolve shared libraries / be found by name; nothing else is
// inherited.
func (e ActorControlWorkerEnv) environ() []string {
	env := []string{
		"ACTOR_CONTROL_META_DSN=" + e.MetaDSN,
		"ACTOR_CONTROL_BRIDGE_URL=" + e.BridgeURL,
		"ACTOR_CONTROL_BRIDGE_TOKEN=" + e.BridgeToken,
		"ACTOR_CONTROL_SHARD_HOSTPORT=" + e.ShardHostPort,
		"ACTOR_CONTROL_PG_USER=" + e.PGUser,
		"ACTOR_CONTROL_PG_PASSWORD=" + e.PGPassword,
		"ACTOR_CONTROL_META_ALLOWLIST=" + e.MetaAllowlist,
	}
	if p := os.Getenv("PATH"); p != "" {
		env = append(env, "PATH="+p)
	}
	// Windows needs SYSTEMROOT for socket initialisation; without it the
	// worker cannot open a TCP connection at all.
	if sr := os.Getenv("SYSTEMROOT"); sr != "" {
		env = append(env, "SYSTEMROOT="+sr)
	}
	return env
}

// DefaultActorControlTimeout bounds one worker invocation.
//
// Two minutes, not the thirty `reality provision` uses. That bound is sized for
// a command that takes a per-shard advisory lock and then runs CREATE DATABASE
// plus fifteen migrations. This one opens two pools, reads one row, and posts
// once to the bridge. A thirty-minute bound on work that takes under a second
// is a wedge detector that never detects: the operator's terminal would hang
// for half an hour on a bridge that is simply unreachable.
const DefaultActorControlTimeout = 2 * time.Minute

// SubprocessActorControlInvoker execs the world-service `actor-control` binary.
type SubprocessActorControlInvoker struct {
	binPath string
	env     ActorControlWorkerEnv
	timeout time.Duration
}

// NewSubprocessActorControlInvoker binds the worker path + its environment,
// with DefaultActorControlTimeout.
func NewSubprocessActorControlInvoker(binPath string, env ActorControlWorkerEnv) *SubprocessActorControlInvoker {
	return &SubprocessActorControlInvoker{binPath: binPath, env: env, timeout: DefaultActorControlTimeout}
}

// WithTimeout overrides the invocation bound (tests use a short one).
func (i *SubprocessActorControlInvoker) WithTimeout(d time.Duration) *SubprocessActorControlInvoker {
	if d > 0 {
		i.timeout = d
	}
	return i
}

var _ ActorControlInvoker = (*SubprocessActorControlInvoker)(nil)

// workerArgs renders the flags for one request.
//
// Separate from Run so the argv contract is testable without exec'ing anything.
// That matters more here than for provision: three ops share one binary, and
// the difference between them is entirely in which flags are present.
func workerArgs(req ActorControlRequest) []string {
	args := []string{
		"--op", string(req.Op),
		"--reality-id", req.RealityID.String(),
		"--reason", req.Reason,
	}
	if req.ActorID != uuid.Nil {
		args = append(args, "--actor-id", req.ActorID.String())
	}
	if req.UserRefID != uuid.Nil {
		args = append(args, "--user-ref-id", req.UserRefID.String())
	}
	if req.ExpectedUserRefID != uuid.Nil {
		args = append(args, "--expected-user-ref-id", req.ExpectedUserRefID.String())
	}
	if req.EntityID > 0 {
		args = append(args, "--entity-id", strconv.FormatInt(req.EntityID, 10))
	}
	if req.DryRun {
		args = append(args, "--dry-run")
	}
	return args
}

// Run execs the worker and parses its stdout.
//
// Exit-code contract (worker module docs):
//
//	0 — the operation succeeded, or the dry run completed
//	1 — refused or failed; stdout JSON carries `error` and `conflict`
//	2 — setup/config error; NOTHING was attempted
//
// Exit 1 is parsed rather than treated as opaque, because `conflict` is the
// field that tells an operator whether to reload and decide or to go look at
// the bridge. Exit 2 is surfaced distinctly because it means the command never
// touched a database.
func (i *SubprocessActorControlInvoker) Run(ctx context.Context, req ActorControlRequest) (ActorControlOutcome, error) {
	if err := i.env.Validate(); err != nil {
		return ActorControlOutcome{}, err
	}
	if strings.TrimSpace(i.binPath) == "" {
		return ActorControlOutcome{}, fmt.Errorf("%w: no actor-control worker binary configured",
			ErrInvalidActorControl)
	}

	ctx, cancel := context.WithTimeout(ctx, i.timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, i.binPath, workerArgs(req)...)
	cmd.Env = i.env.environ()
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	runErr := cmd.Run()

	if ctx.Err() == context.DeadlineExceeded {
		return ActorControlOutcome{}, fmt.Errorf(
			"%w: worker exceeded %s and was killed for reality %s — the binding may or may not "+
				"have been written; re-read before retrying",
			ErrInvalidActorControl, i.timeout, req.RealityID)
	}

	var out ActorControlOutcome
	parseErr := json.Unmarshal(bytes.TrimSpace(stdout.Bytes()), &out)

	if runErr != nil {
		var exitErr *exec.ExitError
		if errors.As(runErr, &exitErr) {
			switch exitErr.ExitCode() {
			case 2:
				return ActorControlOutcome{}, fmt.Errorf(
					"%w: worker refused to start (nothing was attempted): %s",
					ErrInvalidActorControl, truncate(stderr.String(), 512))
			case 1:
				detail := out.Error
				if detail == "" {
					detail = truncate(stderr.String(), 512)
				}
				if out.Conflict {
					return out, fmt.Errorf(
						"%w: REFUSED — %s. This is a statement about the world, not a failure; "+
							"reload and decide rather than retrying",
						ErrInvalidActorControl, detail)
				}
				return out, fmt.Errorf("%w: %s failed: %s", ErrInvalidActorControl, req.Op, detail)
			}
		}
		return ActorControlOutcome{}, fmt.Errorf("%w: worker exec failed: %v (stderr: %s)",
			ErrInvalidActorControl, runErr, truncate(stderr.String(), 512))
	}
	if parseErr != nil {
		return ActorControlOutcome{}, fmt.Errorf(
			"%w: worker produced unparseable output %q: %v (stderr: %s)",
			ErrInvalidActorControl, truncate(stdout.String(), 256), parseErr,
			truncate(stderr.String(), 256))
	}
	// The worker echoes the ids it acted on; a mismatch means we are reading
	// some other invocation's output and must not report it as this one's.
	if got := strings.TrimSpace(out.RealityID); got != "" && got != req.RealityID.String() {
		return ActorControlOutcome{}, fmt.Errorf(
			"%w: worker reported reality_id %s but %s was requested",
			ErrInvalidActorControl, got, req.RealityID)
	}
	if req.ActorID != uuid.Nil {
		if got := strings.TrimSpace(out.ActorID); got != "" && got != req.ActorID.String() {
			return ActorControlOutcome{}, fmt.Errorf(
				"%w: worker reported actor_id %s but %s was requested",
				ErrInvalidActorControl, got, req.ActorID)
		}
	}
	return out, nil
}

// ActorControlWorkerEnvFromOS reads the worker environment from this process's
// env. Used by main to wire the production invoker.
func ActorControlWorkerEnvFromOS() ActorControlWorkerEnv {
	return ActorControlWorkerEnv{
		MetaDSN:       os.Getenv("ACTOR_CONTROL_META_DSN"),
		BridgeURL:     os.Getenv("ACTOR_CONTROL_BRIDGE_URL"),
		BridgeToken:   os.Getenv("ACTOR_CONTROL_BRIDGE_TOKEN"),
		ShardHostPort: os.Getenv("ACTOR_CONTROL_SHARD_HOSTPORT"),
		PGUser:        os.Getenv("ACTOR_CONTROL_PG_USER"),
		PGPassword:    os.Getenv("ACTOR_CONTROL_PG_PASSWORD"),
		MetaAllowlist: os.Getenv("ACTOR_CONTROL_META_ALLOWLIST"),
	}
}
