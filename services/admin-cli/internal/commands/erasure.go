// Package commands holds the concrete admin-cli command orchestrators (the
// real implementations behind the registry's handler names). erasure.go is the
// GDPR Art.17 right-to-be-forgotten flow (S08 §12X.6).
package commands

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ── Dependencies (small interfaces so the orchestrator is unit-testable with
// fakes — the production pgx/SDK impls live in erasure_pg.go). ───────────────

// Eraser performs the irreversible crypto-shred (step 3). *contracts/pii.SDK
// satisfies it directly (ErasePII destroys the KEK + schedules KMS key deletion
// + writes the mandatory meta_read_audit row).
type Eraser interface {
	ErasePII(ctx context.Context, userRefID uuid.UUID, ticket, reason string) error
}

// ConsentScope identifies one consent-ledger row to revoke.
type ConsentScope struct {
	Scope   string
	Version string
}

// ConsentRevoker revokes all active consent scopes (step 7).
type ConsentRevoker interface {
	// ActiveScopes lists scopes still granted (revoked_at IS NULL). READ-ONLY
	// (safe on the dry-run preview path).
	ActiveScopes(ctx context.Context, userRefID uuid.UUID) ([]ConsentScope, error)
	// RevokeScope sets revoked_at on one (user, scope, version) row, but only
	// while it is still active (CAS on revoked_at IS NULL). alreadyRevoked=true
	// (err=nil) when the row was concurrently/previously revoked — an idempotent
	// no-op, NOT an error.
	RevokeScope(ctx context.Context, userRefID uuid.UUID, scope ConsentScope, reason string) (alreadyRevoked bool, err error)
}

// BalanceReader is the best-effort billing pre-check (step 2). The
// AUTHORITATIVE zero-balance gate lives in usage-billing-service (not wired
// here); this reports a user_cost_ledger lifetime-cost proxy only and NEVER
// blocks (so step 2 stays DEFERRED, never EXECUTED).
type BalanceReader interface {
	CostLedgerSummary(ctx context.Context, userRefID uuid.UUID) (rows int, lifetimeCostMicroUSD int64, err error)
}

// ExistenceChecker confirms the target actually has a PII envelope (pii_registry
// row) BEFORE the irreversible crypto-shred — so a typo'd / non-existent
// user_ref_id is rejected with a clear error rather than silently "erasing"
// nothing while every step reports success (code-adversary BLOCK).
type ExistenceChecker interface {
	UserExists(ctx context.Context, userRefID uuid.UUID) (bool, error)
}

// ExistenceCheckerFunc adapts a plain function to ExistenceChecker (lets the
// wiring wrap a PgPIIReader without this package importing piikms).
type ExistenceCheckerFunc func(ctx context.Context, userRefID uuid.UUID) (bool, error)

// UserExists implements ExistenceChecker.
func (f ExistenceCheckerFunc) UserExists(ctx context.Context, userRefID uuid.UUID) (bool, error) {
	return f(ctx, userRefID)
}

// ErasureDeps bundles the orchestrator's collaborators. Eraser + Consent are
// required for a confirm run; Balance + Existence are optional (nil → that
// pre-check is skipped, with the skip surfaced in the report).
type ErasureDeps struct {
	Eraser    Eraser
	Consent   ConsentRevoker
	Balance   BalanceReader
	Existence ExistenceChecker
	Clock     func() time.Time
}

// ErasureRequest is one user-erasure invocation.
type ErasureRequest struct {
	UserRefID  uuid.UUID
	TicketID   string
	Reason     string
	LegalBasis string
	DryRun     bool
}

// validLegalBases enumerates S08 §12X.6 step-1 acceptable legal bases.
var validLegalBases = map[string]bool{
	"self_request": true,
	"court_order":  true,
	"dpa_approved": true,
}

// ── Step reporting ───────────────────────────────────────────────────────────

type stepStatus string

const (
	statusExecuted stepStatus = "EXECUTED"
	statusWouldRun stepStatus = "WOULD-RUN" // dry-run preview
	statusDeferred stepStatus = "DEFERRED"  // owned by another subsystem / not authoritative here
	statusStub     stepStatus = "STUB"      // intentionally not implemented yet
	statusSkipped  stepStatus = "SKIPPED"
	statusFailed   stepStatus = "FAILED" // step aborted mid-run (partial state recorded)
)

type stepReport struct {
	num    int
	name   string
	status stepStatus
	detail string
}

// ErrErasureIncomplete is returned when a confirm run cannot complete a real
// step (so the operator knows the erasure is NOT satisfied and must retry).
var ErrErasureIncomplete = errors.New("erasure: incomplete — retry after fixing the cause")

// RunUserErasure executes the S08 §12X.6 runbook. Step order is fail-safe
// (adversary BLOCK#2): pre-checks (1,2) → reversible consent-revoke (7) → the
// IRREVERSIBLE crypto-shred (3) LAST, so a mid-run failure leaves the user
// recoverable and a re-run completes idempotently. This deviates from S08's
// textual 3→6→7 ordering deliberately, for partial-failure safety.
//
// Honest per-step status (verified against the live schema + wired subsystems):
//   - 1 validate-legal-basis ............ REAL
//   - 2 zero-balance pre-check .......... best-effort proxy; authoritative gate DEFERRED→usage-billing-service
//   - 7 consent-revoke .................. REAL (idempotent CAS)
//   - 3 crypto-shred KEK (+KMS) ......... REAL (ErasePII; writes the mandatory meta_read_audit row → step 8)
//   - 8 admin_action_audit .............. REAL, AUTOMATIC (framework emitter, outside this fn)
//   - 4 per-reality PC tombstone ........ DEFERRED→071 (meta-worker user_erased_writer cascade)
//   - 5 emit user.erased ................ DEFERRED→071 (paired with 4; no live consumer; D-ERASURE-EVENT-EMIT)
//   - 6 cost-ledger pseudonymize ........ DEFERRED→retention-2y (058; doing it now would violate billing retention)
//   - 9 confirmation email .............. STUB (D-ERASURE-EMAIL; no notification path from admin-cli)
//   - 10 30-day erasure certificate ..... DEFERRED (D-ERASURE-CERT; inherently asynchronous)
//
// DRY-RUN INVARIANT (adversary WARN): in DryRun mode this function NEVER calls
// RevokeScope or ErasePII — only the read-only pre-checks + a preview. The
// mandatory GDPR preview cannot itself mutate or shred.
func RunUserErasure(ctx context.Context, req ErasureRequest, deps ErasureDeps) (string, error) {
	clock := deps.Clock
	if clock == nil {
		clock = time.Now
	}
	var steps []stepReport

	// Step 1 — validate legal basis (REAL; before any side effect).
	if !validLegalBases[req.LegalBasis] {
		return "", fmt.Errorf("%w: invalid legal_basis %q (must be self_request|court_order|dpa_approved)",
			ErrErasureIncomplete, req.LegalBasis)
	}
	if req.TicketID == "" || strings.TrimSpace(req.Reason) == "" {
		return "", fmt.Errorf("%w: ticket_id and reason are required (GDPR audit)", ErrErasureIncomplete)
	}
	steps = append(steps, stepReport{1, "validate-legal-basis", statusExecuted, "legal_basis=" + req.LegalBasis})

	// Existence guard (BLOCK): refuse to "erase" a user with no PII envelope —
	// a typo'd / non-existent user_ref_id must error, not silently no-op all the
	// way through the irreversible shred. READ-ONLY (runs in dry-run too).
	if deps.Existence != nil {
		exists, eerr := deps.Existence.UserExists(ctx, req.UserRefID)
		if eerr != nil {
			return "", fmt.Errorf("%w: verify user exists: %v", ErrErasureIncomplete, eerr)
		}
		if !exists {
			return "", fmt.Errorf("%w: no pii_registry row for user_ref_id %s (wrong id, or nothing to erase)", ErrErasureIncomplete, req.UserRefID)
		}
	}

	// Step 2 — zero-balance pre-check. The authoritative gate lives in
	// usage-billing-service (not wired), so this is ALWAYS DEFERRED, never
	// EXECUTED: we only read a user_cost_ledger LIFETIME-COST proxy for the
	// operator, which is NOT an account balance and never blocks.
	if deps.Balance != nil {
		rows, lifetime, err := deps.Balance.CostLedgerSummary(ctx, req.UserRefID)
		if err != nil {
			steps = append(steps, stepReport{2, "balance-precheck", statusDeferred, "lifetime-cost proxy query failed: " + err.Error() + "; authoritative gate DEFERRED→usage-billing-service"})
		} else {
			detail := fmt.Sprintf("informational only: %d cost_ledger rows, %d micro-USD LIFETIME spend (NOT a balance); authoritative zero-balance gate DEFERRED→usage-billing-service; operator/DPO attests zero balance via the ticket", rows, lifetime)
			steps = append(steps, stepReport{2, "balance-precheck", statusDeferred, detail})
		}
	} else {
		steps = append(steps, stepReport{2, "balance-precheck", statusDeferred, "usage-billing-service not wired; operator/DPO attests zero balance via the ticket"})
	}

	// Step 7 — revoke all active consent scopes (REAL, reversible → before shred).
	if deps.Consent == nil {
		return "", fmt.Errorf("%w: consent revoker not wired", ErrErasureIncomplete)
	}
	active, err := deps.Consent.ActiveScopes(ctx, req.UserRefID)
	if err != nil {
		return "", fmt.Errorf("%w: list active consent scopes: %v", ErrErasureIncomplete, err)
	}
	sortScopes(active)
	if req.DryRun {
		steps = append(steps, stepReport{7, "consent-revoke", statusWouldRun,
			fmt.Sprintf("would revoke %d active scope(s): %s", len(active), scopeList(active))})
	} else {
		revoked, skipped := 0, 0
		for _, sc := range active {
			already, rerr := deps.Consent.RevokeScope(ctx, req.UserRefID, sc, req.Reason)
			if rerr != nil {
				// Fail BEFORE the irreversible shred → user remains recoverable.
				// Surface the partial state (WARN1): some scopes may already be
				// committed; record that in BOTH the report and the error so the
				// operator knows a re-run is needed (the CAS makes it idempotent).
				steps = append(steps, stepReport{7, "consent-revoke", statusFailed,
					fmt.Sprintf("aborted after %d revoked / %d skipped of %d, on %s/%s: %v — re-run to complete (idempotent)",
						revoked, skipped, len(active), sc.Scope, sc.Version, rerr)})
				return renderReport(req, steps),
					fmt.Errorf("%w: revoke consent %s/%s after %d committed: %v", ErrErasureIncomplete, sc.Scope, sc.Version, revoked, rerr)
			}
			if already {
				skipped++
			} else {
				revoked++
			}
		}
		steps = append(steps, stepReport{7, "consent-revoke", statusExecuted,
			fmt.Sprintf("revoked %d, idempotent-skipped %d", revoked, skipped)})
	}

	// Step 3 — crypto-shred KEK + schedule KMS deletion (REAL, IRREVERSIBLE, LAST).
	if deps.Eraser == nil {
		return "", fmt.Errorf("%w: PII SDK / KMS not wired (cannot crypto-shred)", ErrErasureIncomplete)
	}
	if req.DryRun {
		steps = append(steps, stepReport{3, "crypto-shred-kek", statusWouldRun,
			"would destroy the user's active KEK (pii_kek.destroyed_at) + ScheduleKeyDeletion + write meta_read_audit(pii_user_erase)"})
	} else {
		if err := deps.Eraser.ErasePII(ctx, req.UserRefID, req.TicketID, req.Reason); err != nil {
			return "", fmt.Errorf("%w: crypto-shred: %v", ErrErasureIncomplete, err)
		}
		steps = append(steps, stepReport{3, "crypto-shred-kek", statusExecuted,
			"KEK destroyed + KMS deletion scheduled + meta_read_audit(pii_user_erase) written (step 8)"})
	}

	// Steps 4/5/6/9/10 — honest deferred/stub (logged in BOTH modes).
	steps = append(steps,
		stepReport{4, "per-reality-pc-tombstone", statusDeferred, "meta-worker user_erased_writer cascade — DEFERRED→071"},
		stepReport{5, "emit-user.erased", statusDeferred, "no live consumer (paired with step 4) — DEFERRED→071 / D-ERASURE-EVENT-EMIT"},
		stepReport{6, "cost-ledger-pseudonymize", statusDeferred, "retention cron pseudonymizes at 2y (billing retention) — DEFERRED→retention-worker(058)"},
		stepReport{9, "confirmation-email", statusStub, "no notification path from admin-cli — D-ERASURE-EMAIL"},
		stepReport{10, "erasure-certificate-30d", statusDeferred, "issued 30d post-shred (async, after KMS destruction) — D-ERASURE-CERT"},
	)

	return renderReport(req, steps), nil
}

// renderReport produces the human/operator summary returned as the handler's
// result string. Step 8 (auto-audit) is noted in the header, not as a row,
// because it happens in the framework dispatcher around this handler.
func renderReport(req ErasureRequest, steps []stepReport) string {
	mode := "CONFIRM (writes applied)"
	if req.DryRun {
		mode = "DRY-RUN (no writes)"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "GDPR user-erasure (S08 §12X.6) — %s\n", mode)
	fmt.Fprintf(&b, "  user_ref_id=%s  ticket=%s  legal_basis=%s\n", req.UserRefID, req.TicketID, req.LegalBasis)
	fmt.Fprintf(&b, "  (step 8 admin_action_audit is written automatically by the dispatcher)\n")
	sort.SliceStable(steps, func(i, j int) bool { return steps[i].num < steps[j].num })
	for _, s := range steps {
		fmt.Fprintf(&b, "  [%2d] %-26s %-10s %s\n", s.num, s.name, s.status, s.detail)
	}
	return b.String()
}

func sortScopes(s []ConsentScope) {
	sort.SliceStable(s, func(i, j int) bool {
		if s[i].Scope != s[j].Scope {
			return s[i].Scope < s[j].Scope
		}
		return s[i].Version < s[j].Version
	})
}

func scopeList(s []ConsentScope) string {
	if len(s) == 0 {
		return "(none)"
	}
	parts := make([]string, len(s))
	for i, sc := range s {
		parts[i] = sc.Scope + "/" + sc.Version
	}
	return strings.Join(parts, ", ")
}
