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
	"github.com/loreweave/foundation/services/admin-cli/internal/confirmation"
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

	SecondActorToken string // the second actor's OWN signed token (PRR-43 dual-actor)
	ConfirmToken     string // typed-confirmation token (PRR-44; tier-1 RequireTypedConfirm)
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

	// 4. double approval (tier-1 only) — the second actor must present their
	// OWN validated token (PRR-43); a name string alone is forgeable by a
	// single operator.
	if policy.RequireDoubleApproval && inv.Confirm {
		if inv.SecondActor == "" || inv.SecondActor == inv.Actor {
			return "", fmt.Errorf("admin-cli: tier-1 command %q requires --second-actor (different from %q)",
				c.Name, inv.Actor)
		}
		secondClaims, serr := auth.Validate(inv.SecondActorToken)
		if serr != nil {
			return "", fmt.Errorf("admin-cli: tier-1 command %q requires a valid --second-actor-token: %w", c.Name, serr)
		}
		if secondClaims.Subject != inv.SecondActor {
			return "", fmt.Errorf("admin-cli: --second-actor-token subject %q does not match --second-actor %q", secondClaims.Subject, inv.SecondActor)
		}
		if secondClaims.Subject == inv.Actor {
			return "", fmt.Errorf("admin-cli: second actor must differ from primary actor %q", inv.Actor)
		}
		if !secondClaims.HasScope(scope) {
			return "", fmt.Errorf("admin-cli: second actor %q lacks required scope %q", secondClaims.Subject, scope)
		}
	}

	// 4b. typed confirmation (tier-1 RequireTypedConfirm) — operator must re-type
	// the target resource value, proving intent on the specific target (PRR-44,
	// R13 §12L.4). Only gates the real --confirm run, not --dry-run.
	if policy.RequireTypedConfirm && inv.Confirm {
		challenge := confirmChallenge(c, inv.Params)
		if cerr := confirmation.Check(challenge, inv.ConfirmToken); cerr != nil {
			return "", fmt.Errorf("admin-cli: %q typed-confirmation required — pass --confirm-token=%q: %w", c.Name, challenge, cerr)
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

	// 8. audit After / Failure. Pass the RAW error text — the emitter hashes it
	// (correlation) AND carries it to the MetaWriteSink, which scrubs it into the
	// audit row (099 D-ADMINAUDIT-ERROR-TEXT). The raw text is never persisted.
	if hErr != nil {
		_ = emitter.Failure(ctx, action, hErr.Error())
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

// Clock is exposed so tests can pin time.
type Clock func() time.Time

// confirmChallenge derives the typed-confirmation token an operator must
// re-type for a destructive command (PRR-44): the value of the command's
// primary target-resource param, falling back to the command name. Re-typing
// the specific target prevents an accidental destructive --confirm.
func confirmChallenge(c *Command, params map[string]string) string {
	for _, key := range []string{
		"reality_id", "reality", "target_id", "id", "character_id",
		"user_ref_id", "npc_id", "shard_id", "projection",
	} {
		if v := strings.TrimSpace(params[key]); v != "" {
			return v
		}
	}
	return c.Name
}
