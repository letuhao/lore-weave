// Package dry_run implements the --dry-run safety wrapper.
//
// Tier-1 destructive commands MUST be invoked with --dry-run before --confirm
// is accepted (the framework Run() checks Registry.DryRunRequired). dry_run
// records the predicted impact (rows touched, downstream side effects) so the
// operator can compare a real run's outcome against the prediction.
package dry_run

import (
	"errors"
	"fmt"
	"strings"
)

// Plan is the predicted impact returned by a dry-run.
type Plan struct {
	Command         string
	PredictedRows   int64
	PredictedSteps  []string // ordered list of side-effects
	Warnings        []string
	WriteBlockedOK  bool // true means the dry-run successfully blocked all writes
}

// ErrDryRun signals a dry-run gate violation.
var ErrDryRun = errors.New("admin-cli/dry_run")

// EnforceGate is called by the framework before invoking a destructive
// command. If the command requires dry-run AND the operator did not pass
// --dry-run AND did not pass --confirm, the gate refuses.
func EnforceGate(commandName string, dryRunRequired, dryRun, confirm bool) error {
	if !dryRunRequired {
		return nil
	}
	if !dryRun && !confirm {
		return fmt.Errorf("%w: command %q requires --dry-run (preview) or --confirm (proceed)",
			ErrDryRun, commandName)
	}
	return nil
}

// Format returns a human-readable summary of a Plan.
func (p Plan) Format() string {
	var b strings.Builder
	fmt.Fprintf(&b, "DRY-RUN: %s\n", p.Command)
	fmt.Fprintf(&b, "  predicted rows touched: %d\n", p.PredictedRows)
	if len(p.PredictedSteps) > 0 {
		fmt.Fprintf(&b, "  predicted steps:\n")
		for _, s := range p.PredictedSteps {
			fmt.Fprintf(&b, "    - %s\n", s)
		}
	}
	if len(p.Warnings) > 0 {
		fmt.Fprintf(&b, "  warnings:\n")
		for _, w := range p.Warnings {
			fmt.Fprintf(&b, "    ! %s\n", w)
		}
	}
	fmt.Fprintf(&b, "  write-blocked: %v\n", p.WriteBlockedOK)
	return b.String()
}
