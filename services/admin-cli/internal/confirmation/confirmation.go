// Package confirmation enforces R13 §12L.4 typed-confirmation flow.
//
// For Tier-1 destructive commands, the operator MUST type a confirmation
// token that matches a per-command challenge (e.g., the reality name) before
// the framework runs the destructive step.
//
// This package is intentionally I/O-free so tests don't need a TTY. The CLI
// main reads from os.Stdin and calls Check().
package confirmation

import (
	"errors"
	"fmt"
	"strings"
)

// ErrConfirmation is returned by Check on mismatch.
var ErrConfirmation = errors.New("admin-cli/confirmation")

// Check returns nil if entered matches expected (case-sensitive, trimmed).
// Empty expected always fails so we never accept "confirm by pressing enter".
func Check(expected, entered string) error {
	expected = strings.TrimSpace(expected)
	entered = strings.TrimSpace(entered)
	if expected == "" {
		return fmt.Errorf("%w: expected token is empty", ErrConfirmation)
	}
	if expected != entered {
		return fmt.Errorf("%w: mismatch (entered %d chars)", ErrConfirmation, len(entered))
	}
	return nil
}

// ChallengeFor returns the prompt token expected for a given resource. For
// reality commands the challenge is the reality_id itself; per-domain
// challenges can be added as commands need them.
func ChallengeFor(resourceID string) string {
	return strings.TrimSpace(resourceID)
}
