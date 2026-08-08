// provision_reality_pg.go — SubprocessProvisionInvoker: exec the world-service
// `provision` worker.
//
// Mirrors SubprocessRebuildInvoker (rebuild_projection_pg.go): identifiers go
// as flags, secrets go as env so they never appear on the process table, stdout
// is one JSON object, and the exit code is the verdict.
//
// Difference worth naming: the rebuild invoker inherits os.Environ() and adds
// one variable. This one builds the worker's environment EXPLICITLY from a
// declared struct. Provisioning creates databases, and an inherited
// PROVISION_SHARD_ADMIN_DSN left over in an operator's shell is precisely the
// way a command lands on the wrong Postgres. The worker itself has no
// credential defaults, so a missing field fails closed at exit 2 rather than
// silently targeting whatever was ambient.
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

// ProvisionWorkerEnv is the full set of connection settings the worker needs.
// Every field is required except Password (peer/trust auth is legitimate) and
// SQLDir (the worker defaults it to the in-repo migration directory).
type ProvisionWorkerEnv struct {
	MetaDSN       string
	ShardAdminDSN string
	BridgeURL     string
	BridgeToken   string
	ShardHostPort string
	PGUser        string
	PGPassword    string
	SQLDir        string
}

// Validate reports every missing required field at once.
func (e ProvisionWorkerEnv) Validate() error {
	var missing []string
	for _, f := range []struct {
		name string
		val  string
	}{
		{"PROVISION_META_DSN", e.MetaDSN},
		{"PROVISION_SHARD_ADMIN_DSN", e.ShardAdminDSN},
		{"PROVISION_BRIDGE_URL", e.BridgeURL},
		{"PROVISION_BRIDGE_TOKEN", e.BridgeToken},
		{"PROVISION_SHARD_HOSTPORT", e.ShardHostPort},
		{"PROVISION_PG_USER", e.PGUser},
	} {
		if strings.TrimSpace(f.val) == "" {
			missing = append(missing, f.name)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("%w: provision worker env incomplete: %s",
			ErrInvalidProvision, strings.Join(missing, ", "))
	}
	return nil
}

// environ renders the worker's environment. PATH is carried through so the
// binary can resolve shared libraries / be found by name; nothing else is
// inherited.
func (e ProvisionWorkerEnv) environ() []string {
	env := []string{
		"PROVISION_META_DSN=" + e.MetaDSN,
		"PROVISION_SHARD_ADMIN_DSN=" + e.ShardAdminDSN,
		"PROVISION_BRIDGE_URL=" + e.BridgeURL,
		"PROVISION_BRIDGE_TOKEN=" + e.BridgeToken,
		"PROVISION_SHARD_HOSTPORT=" + e.ShardHostPort,
		"PROVISION_PG_USER=" + e.PGUser,
		"PROVISION_PG_PASSWORD=" + e.PGPassword,
	}
	if s := strings.TrimSpace(e.SQLDir); s != "" {
		env = append(env, "PROVISION_SQL_DIR="+s)
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

// DefaultProvisionTimeout bounds one worker invocation.
//
// There was no bound at all in the first version: `main` builds a
// `context.Background()` with no deadline, and the worker takes a per-shard
// advisory lock and then runs CREATE DATABASE plus fifteen migrations. A worker
// that wedges — or simply waits behind another provision holding the same
// shard's lock — blocked the admin command forever, with no output.
//
// 30 minutes matches what the sibling destructive commands already chose:
// `reality catastrophic-rebuild` defaults its per-reality timeout to 30m and
// `reality rebuild-projection` caps `freeze_timeout` at 30m. Provisioning is
// far quicker; this is a wedge detector, not a performance budget.
const DefaultProvisionTimeout = 30 * time.Minute

// SubprocessProvisionInvoker execs the world-service `provision` binary.
type SubprocessProvisionInvoker struct {
	binPath string
	env     ProvisionWorkerEnv
	timeout time.Duration
}

// NewSubprocessProvisionInvoker binds the worker path + its environment, with
// DefaultProvisionTimeout.
func NewSubprocessProvisionInvoker(binPath string, env ProvisionWorkerEnv) *SubprocessProvisionInvoker {
	return &SubprocessProvisionInvoker{
		binPath: binPath, env: env, timeout: DefaultProvisionTimeout,
	}
}

// WithTimeout overrides the invocation bound (tests use a short one).
func (i *SubprocessProvisionInvoker) WithTimeout(d time.Duration) *SubprocessProvisionInvoker {
	if d > 0 {
		i.timeout = d
	}
	return i
}

var _ ProvisionInvoker = (*SubprocessProvisionInvoker)(nil)

// Provision runs the worker and parses its stdout.
//
// Exit-code contract (worker module docs):
//
//	0 — provisioned, or dry run completed
//	1 — provisioning failed; stdout JSON carries `error`
//	2 — setup/config error; NOTHING was attempted
//
// Exit 2 is surfaced distinctly because it is the operator-actionable one: it
// means the command never touched the database.
func (i *SubprocessProvisionInvoker) Provision(ctx context.Context, req ProvisionRealityRequest) (ProvisionOutcome, error) {
	if err := i.env.Validate(); err != nil {
		return ProvisionOutcome{}, err
	}
	if strings.TrimSpace(i.binPath) == "" {
		return ProvisionOutcome{}, fmt.Errorf("%w: no provision worker binary configured", ErrInvalidProvision)
	}

	args := []string{
		"--reality-id", req.RealityID.String(),
		"--reason", req.Reason,
		"--locale", req.EffectiveLocale(),
		"--deploy-cohort", strconv.Itoa(req.DeployCohort),
	}
	if req.OwnerUserID != uuid.Nil {
		args = append(args, "--owner-user-id", req.OwnerUserID.String())
	}
	if req.DryRun {
		args = append(args, "--dry-run")
	}

	ctx, cancel := context.WithTimeout(ctx, i.timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, i.binPath, args...)
	cmd.Env = i.env.environ()
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	runErr := cmd.Run()

	// Distinguish "we killed it" from "it failed": a timeout leaves the reality
	// in an unknown half-provisioned state, which is an operator action (re-run
	// to resume, or let orphan_scanner find it), not a plain failure.
	if ctx.Err() == context.DeadlineExceeded {
		return ProvisionOutcome{}, fmt.Errorf(
			"%w: worker exceeded %s and was killed for %s — the reality may be half-provisioned; "+
				"re-run to resume on its registered shard, or check orphan_scanner",
			ErrInvalidProvision, i.timeout, req.RealityID)
	}

	var out ProvisionOutcome
	parseErr := json.Unmarshal(bytes.TrimSpace(stdout.Bytes()), &out)

	if runErr != nil {
		var exitErr *exec.ExitError
		if errors.As(runErr, &exitErr) {
			switch exitErr.ExitCode() {
			case 2:
				return ProvisionOutcome{}, fmt.Errorf(
					"%w: worker refused to start (nothing was attempted): %s",
					ErrInvalidProvision, truncate(stderr.String(), 512))
			case 1:
				detail := out.Error
				if detail == "" {
					detail = truncate(stderr.String(), 512)
				}
				return out, fmt.Errorf("%w: provisioning failed: %s", ErrInvalidProvision, detail)
			}
		}
		return ProvisionOutcome{}, fmt.Errorf("%w: worker exec failed: %v (stderr: %s)",
			ErrInvalidProvision, runErr, truncate(stderr.String(), 512))
	}
	if parseErr != nil {
		return ProvisionOutcome{}, fmt.Errorf(
			"%w: worker produced unparseable output %q: %v (stderr: %s)",
			ErrInvalidProvision, truncate(stdout.String(), 256), parseErr, truncate(stderr.String(), 256))
	}
	// The worker echoes the id it acted on; a mismatch means we are reading
	// some other invocation's output and must not report it as this one's.
	if got := strings.TrimSpace(out.RealityID); got != "" && got != req.RealityID.String() {
		return ProvisionOutcome{}, fmt.Errorf(
			"%w: worker reported reality_id %s but %s was requested",
			ErrInvalidProvision, got, req.RealityID)
	}
	return out, nil
}

// ProvisionWorkerEnvFromOS reads the worker environment from this process's env.
// Used by main to wire the production invoker.
func ProvisionWorkerEnvFromOS() ProvisionWorkerEnv {
	return ProvisionWorkerEnv{
		MetaDSN:       os.Getenv("PROVISION_META_DSN"),
		ShardAdminDSN: os.Getenv("PROVISION_SHARD_ADMIN_DSN"),
		BridgeURL:     os.Getenv("PROVISION_BRIDGE_URL"),
		BridgeToken:   os.Getenv("PROVISION_BRIDGE_TOKEN"),
		ShardHostPort: os.Getenv("PROVISION_SHARD_HOSTPORT"),
		PGUser:        os.Getenv("PROVISION_PG_USER"),
		PGPassword:    os.Getenv("PROVISION_PG_PASSWORD"),
		SQLDir:        os.Getenv("PROVISION_SQL_DIR"),
	}
}
