// Package scriptrun is the os/exec implementation of audit_invoker.ScriptRunner.
// It shells out to scripts/event-audit-retention-cron.sh and parses the two
// summary lines the script prints:
//
//	[audit-retention] dropped <N> fully-expired event_audit partitions (...)
//	[audit-retention] deleted non_flagged=<X> flagged=<Y>
package scriptrun

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strconv"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

var (
	reDropped    = regexp.MustCompile(`dropped (\d+) fully-expired`)
	reNonFlagged = regexp.MustCompile(`non_flagged=(\d+)`)
	// `\b` does NOT match inside `non_flagged` (`_` is a word char, so there is
	// no boundary before `flagged`), so this captures the standalone counter.
	reFlagged = regexp.MustCompile(`\bflagged=(\d+)`)
)

// ExecRunner shells out to the audit-retention bash script.
type ExecRunner struct {
	scriptPath string
	bash       string
}

// New binds the script path. bash defaults to "bash" on PATH.
func New(scriptPath string) *ExecRunner {
	return &ExecRunner{scriptPath: scriptPath, bash: "bash"}
}

// Run invokes the script with the reality's DSN + retention knobs, parses the
// counters from stdout, and surfaces a non-zero exit as an error.
//
// The DSN (which carries the password) is passed via the PGURI ENV var, NOT a
// `--db` CLI arg — a credential in argv is visible in the host process list.
// The script reads `DB_URI="${PGURI:-${DATABASE_URL:-}}"`.
func (r *ExecRunner) Run(ctx context.Context, realityID uuid.UUID, dsn string, batchSize, nonFlaggedDays, flaggedDays int) (types.AuditPruneStats, error) {
	cmd := exec.CommandContext(ctx, r.bash, r.scriptPath,
		"--batch-size", strconv.Itoa(batchSize),
		"--non-flagged-days", strconv.Itoa(nonFlaggedDays),
		"--flagged-days", strconv.Itoa(flaggedDays),
	)
	cmd.Env = append(os.Environ(), "PGURI="+dsn)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return types.AuditPruneStats{}, fmt.Errorf("scriptrun: %s failed: %w\n%s", r.scriptPath, err, out)
	}
	return ParseOutput(string(out), realityID), nil
}

// ParseOutput extracts the counters from the script's stdout. Missing lines
// parse to zero (the script always prints both on success).
func ParseOutput(out string, realityID uuid.UUID) types.AuditPruneStats {
	return types.AuditPruneStats{
		RealityID:         realityID,
		PartitionsDropped: firstInt(reDropped, out),
		NonFlaggedDeleted: firstInt(reNonFlagged, out),
		FlaggedDeleted:    firstInt(reFlagged, out),
	}
}

func firstInt(re *regexp.Regexp, s string) int64 {
	m := re.FindStringSubmatch(s)
	if len(m) < 2 {
		return 0
	}
	n, err := strconv.ParseInt(m[1], 10, 64)
	if err != nil {
		return 0
	}
	return n
}
