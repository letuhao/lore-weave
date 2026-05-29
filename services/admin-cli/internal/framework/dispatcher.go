// dispatcher.go — framework.Run wraps every command invocation in policy
// checks (auth → impact_classifier → dry_run gate → typed confirmation) and
// audit Before/After/Failure book-ends.
//
// Per cycle 36 design: audit hook lives at the FRAMEWORK level, not per
// command. This guarantees DRY and that no command can ship without auditing.
package framework

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
	"github.com/loreweave/foundation/services/admin-cli/internal/auth"
	"github.com/loreweave/foundation/services/admin-cli/internal/dry_run"
	"github.com/loreweave/foundation/services/admin-cli/internal/impact_classifier"
)

// Handler is the function signature every command exposes.
type Handler func(ctx context.Context, inv Invocation) (string, error)

// Invocation is what the dispatcher hands a handler.
type Invocation struct {
	Command     *Command
	Params      map[string]string
	DryRun      bool
	Confirm     bool
	Actor       string
	ActorRole   string
	Reason      string
	SecondActor string // dual-approval secondary actor (tier-1 only)
}

// Run is the single entry point. ALL admin commands MUST be dispatched
// through this fn so audit + policy gates are uniform.
//
// Order of operations is load-bearing:
//
//  1. auth.Validate(token) → claims, scope check
//  2. impact_classifier.Of(c.ImpactClass) → policy
//  3. dry_run.EnforceGate(...) → reject if missing --dry-run/--confirm
//  4. tier-1: require SecondActor != Actor (double approval)
//  5. tier-1: require Reason (>=10 chars rough sanity)
//  6. audit_emitter.Before(...) → started row
//  7. handler(ctx, inv) → result | err
//  8. audit_emitter.After/Failure(...)
func Run(
	ctx context.Context,
	c *Command,
	inv Invocation,
	token string,
	handler Handler,
	emitter *audit_emitter.Emitter,
) (string, error) {
	if c == nil {
		return "", errors.New("admin-cli: Run: nil command")
	}
	if handler == nil {
		return "", fmt.Errorf("admin-cli: Run: no handler registered for %q (check commands.Register)", c.Name)
	}
	if emitter == nil {
		return "", errors.New("admin-cli: Run: nil audit emitter")
	}

	// 1. auth
	claims, err := auth.Validate(token)
	if err != nil {
		return "", fmt.Errorf("admin-cli: auth: %w", err)
	}
	scope := auth.RequireScopeForTier(string(c.ImpactClass))
	if !claims.HasScope(scope) {
		return "", fmt.Errorf("admin-cli: auth: missing scope %q (have %v)", scope, claims.Scopes)
	}
	inv.Actor = claims.Subject
	inv.ActorRole = claims.Role

	// 2. policy
	policy, err := impact_classifier.Of(string(c.ImpactClass))
	if err != nil {
		return "", fmt.Errorf("admin-cli: impact: %w", err)
	}

	// 3. dry-run gate
	if err := dry_run.EnforceGate(c.Name, c.DryRunRequired, inv.DryRun, inv.Confirm); err != nil {
		return "", err
	}

	// 4. double approval (tier-1 only)
	if policy.RequireDoubleApproval && inv.Confirm {
		if inv.SecondActor == "" || inv.SecondActor == inv.Actor {
			return "", fmt.Errorf("admin-cli: tier-1 command %q requires --second-actor (different from %q)",
				c.Name, inv.Actor)
		}
	}

	// 5. reason sanity (tier-1+2)
	if policy.Tier != impact_classifier.Tier3Informational && len(strings.TrimSpace(inv.Reason)) < 10 {
		return "", fmt.Errorf("admin-cli: %q requires --reason (>=10 chars)", c.Name)
	}

	// 6. audit Before
	action := audit_emitter.Action{
		CommandName:       c.Name,
		Actor:             inv.Actor,
		ActorRole:         inv.ActorRole,
		Reason:            inv.Reason,
		ParamsHash:        hashParams(inv.Params),
		ImpactClass:       string(c.ImpactClass),
		DryRun:            inv.DryRun,
		DoubleApprovalRef: inv.SecondActor,
	}
	action, err = emitter.Before(ctx, action)
	if err != nil {
		return "", err
	}

	// 7. dispatch
	out, hErr := handler(ctx, inv)

	// 8. audit After / Failure
	if hErr != nil {
		_ = emitter.Failure(ctx, action, hashErr(hErr))
		return out, hErr
	}
	if err := emitter.After(ctx, action); err != nil {
		return out, fmt.Errorf("admin-cli: audit-after: %w (command succeeded but audit-after row failed; SRE attention)", err)
	}
	return out, nil
}

// ─── helpers ─────────────────────────────────────────────────────────────────

// hashParams returns SHA-256(normalized params). NEVER hashes raw PII values
// in the clear over the wire — we just want a fingerprint for audit replay.
func hashParams(p map[string]string) string {
	if len(p) == 0 {
		return ""
	}
	keys := make([]string, 0, len(p))
	for k := range p {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	h := sha256.New()
	for _, k := range keys {
		h.Write([]byte(k))
		h.Write([]byte{0})
		h.Write([]byte(p[k]))
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil))
}

func hashErr(e error) string {
	h := sha256.Sum256([]byte(e.Error()))
	return hex.EncodeToString(h[:])
}

// Clock is exposed so tests can pin time.
type Clock func() time.Time
