// provision_reality.go — `admin reality provision` (W3).
//
// The command that CREATES a reality. Every other command in the `reality`
// domain operates on one that already exists; until this shipped, nothing in
// the platform could produce one — the sole caller of the Rust provisioner was
// a drill carrying hardcoded rig credentials and a fabricated capacity
// snapshot.
//
// Division of labour, and it is the point of the design:
//
//   - **Go owns governance.** The framework dispatcher has already validated the
//     admin JWT, checked `admin:write` for tier-2, enforced the dry-run gate,
//     required a reason, and written the `admin_action_audit` "started" row
//     before this file runs. None of that is re-implemented here.
//   - **The Rust worker owns provisioning.** It holds every DSN, takes the
//     per-shard advisory lock, reads live capacity, creates the database and
//     applies migrations. This process never opens the shard.
//
// So the seam is a subprocess, exactly as `rebuild-projection` drives the
// `rebuilder` worker (SubprocessRebuildInvoker): identifiers by flag, secrets by
// env, one JSON object on stdout, exit code as verdict.
package commands

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// ErrInvalidProvision is the sentinel for a malformed provision request.
var ErrInvalidProvision = errors.New("admin-cli: reality provision")

// DefaultProvisionLocale is used when --locale is omitted.
const DefaultProvisionLocale = "en"

// ProvisionRealityRequest is the validated input to the provision flow.
type ProvisionRealityRequest struct {
	// RealityID is CALLER-generated, mirroring the Rust provisioner's own
	// contract ("caller-generated to keep the audit chain coherent",
	// provisioner.rs:54). Because the dispatcher hashes params BEFORE the
	// handler runs, a caller-supplied id is in `admin_action_audit.params_hash`
	// even if provisioning then dies half-way — so an orphaned database is
	// still traceable to the action that ordered it. A worker-generated id
	// would not be.
	RealityID uuid.UUID
	// Locale is BCP-47; empty means DefaultProvisionLocale.
	Locale string
	// DeployCohort is the canary cohort 0..99 (SR05 §12AH.4).
	DeployCohort int
	Actor        string
	Reason       string
	DryRun       bool
	Confirm      bool
	// OwnerUserID is the user who will own the reality. uuid.Nil means the
	// PLATFORM owns it — a real category (an admin provisioning for the
	// platform), not "unknown". The registry stores the tier explicitly as
	// owner_kind, so an unowned reality is declared rather than inferred from
	// a NULL. See migrations/meta/036_reality_ownership.up.sql.
	OwnerUserID uuid.UUID
}

// Validate checks the request shape. The dispatcher separately enforces the
// reason length and the dry-run gate for tier-2 commands; this covers what is
// specific to provisioning.
func (r ProvisionRealityRequest) Validate() error {
	if r.RealityID == uuid.Nil {
		return fmt.Errorf("%w: reality_id must not be the nil UUID", ErrInvalidProvision)
	}
	if r.DeployCohort < 0 || r.DeployCohort > 99 {
		return fmt.Errorf("%w: deploy_cohort=%d out of range 0..99", ErrInvalidProvision, r.DeployCohort)
	}
	if l := strings.TrimSpace(r.Locale); l != "" && !looksLikeBCP47(l) {
		return fmt.Errorf(
			"%w: locale %q is not a well-formed language tag (expected e.g. en, en-US, zh-Hant-TW)",
			ErrInvalidProvision, r.Locale)
	}
	return nil
}

// looksLikeBCP47 accepts the subset of RFC 5646 this platform uses: 2–3 alpha
// primary subtag, then up to three subtags of 2–8 alphanumerics.
//
// The first version of this check tested `len(l) > 35` while REPORTING "is not
// a BCP-47 tag" — so any 35-character string passed validation and reached both
// `reality_registry.locale` and the worker's argv, under a message claiming it
// had been checked. A message that describes a check the code does not perform
// is worse than no check: it tells the next reader the ground is covered.
func looksLikeBCP47(s string) bool {
	parts := strings.Split(s, "-")
	if len(parts) == 0 || len(parts) > 4 {
		return false
	}
	if n := len(parts[0]); n < 2 || n > 3 || !isAlpha(parts[0]) {
		return false
	}
	for _, p := range parts[1:] {
		if n := len(p); n < 2 || n > 8 || !isAlnum(p) {
			return false
		}
	}
	return true
}

func isAlpha(s string) bool {
	for _, r := range s {
		if (r < 'a' || r > 'z') && (r < 'A' || r > 'Z') {
			return false
		}
	}
	return true
}

func isAlnum(s string) bool {
	for _, r := range s {
		alpha := (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z')
		if !alpha && (r < '0' || r > '9') {
			return false
		}
	}
	return true
}

// EffectiveLocale resolves the locale actually sent to the worker.
func (r ProvisionRealityRequest) EffectiveLocale() string {
	if l := strings.TrimSpace(r.Locale); l != "" {
		return l
	}
	return DefaultProvisionLocale
}

// ShardSlot is one shard's live occupancy as the worker measured it:
// `Total` is the declared cap from `shard_utilization`, `Used` is a live count
// over `reality_registry`. Surfaced so a dry-run shows the operator the real
// numbers rather than asserting a shard was "available".
type ShardSlot struct {
	Shard string `json:"shard"`
	Used  int64  `json:"used"`
	Total int64  `json:"total"`
}

// ProvisionOutcome is the worker's stdout JSON. Both modes emit the same shape;
// `WouldProvision` and `Shards` are populated on a dry run, `Steps` and `DBName`
// on a real one.
type ProvisionOutcome struct {
	Mode           string      `json:"mode"`
	RealityID      string      `json:"reality_id"`
	Shard          string      `json:"shard"`
	DBName         string      `json:"db_name"`
	Steps          int         `json:"steps"`
	WouldProvision bool        `json:"would_provision"`
	Error          string      `json:"error"`
	Shards         []ShardSlot `json:"shards"`
}

// ProvisionInvoker runs the provision worker. The production implementation
// (SubprocessProvisionInvoker) execs the world-service `provision` binary;
// tests stub it.
type ProvisionInvoker interface {
	Provision(ctx context.Context, req ProvisionRealityRequest) (ProvisionOutcome, error)
}

// ProvisionRealityDeps bundles the collaborators.
type ProvisionRealityDeps struct {
	Invoker ProvisionInvoker
}

// RunProvisionReality validates, invokes the worker, and renders the operator
// summary.
//
// Note this does NOT short-circuit the dry run in Go, unlike
// RunRebuildProjection. A provision dry run has something real to report —
// which shard was chosen and how full every shard actually is — and only the
// worker can read it. Answering from Go would mean asserting a placement
// nothing measured, which is the drill's defect in a new location.
func RunProvisionReality(ctx context.Context, req ProvisionRealityRequest, deps ProvisionRealityDeps) (string, error) {
	if err := req.Validate(); err != nil {
		return "", err
	}
	if deps.Invoker == nil {
		return "", fmt.Errorf("%w: no invoker configured", ErrInvalidProvision)
	}

	out, err := deps.Invoker.Provision(ctx, req)
	if err != nil {
		return "", err
	}

	// "No capacity" is diagnosed FIRST: that outcome legitimately names no shard,
	// so the shard guard below would otherwise report it as a contract failure.
	if req.DryRun && !out.WouldProvision {
		return "", fmt.Errorf("%w: no shard has capacity for %s: %s",
			ErrInvalidProvision, req.RealityID, out.Error)
	}

	// A report naming no shard is not a report. This is the defect the live run
	// caught and the code did not: a renamed JSON key left `shard` empty and the
	// command printed "provisioned on shard " with exit 0. The key was fixed;
	// the GUARD was missing, so a stale binary or a changed output contract would
	// print it again. Checked in BOTH modes, before either summary is built.
	if strings.TrimSpace(out.Shard) == "" {
		return "", fmt.Errorf(
			"%w: worker reported no shard for %s — refusing to report a placement it did not name "+
				"(stale worker binary, or a changed output contract?)",
			ErrInvalidProvision, req.RealityID)
	}

	if req.DryRun {
		return fmt.Sprintf(
			"reality provision DRY-RUN — would create reality %s on shard %s as database %s (locale=%s, cohort=%d).\nLive capacity: %s\nNothing was written.",
			req.RealityID, out.Shard, out.DBName, req.EffectiveLocale(), req.DeployCohort,
			formatShards(out.Shards),
		), nil
	}

	// A worker that exits 0 must have produced a database name; treat a blank
	// one as a failure rather than reporting a success we cannot point at.
	if strings.TrimSpace(out.DBName) == "" {
		return "", fmt.Errorf("%w: worker reported success for %s but named no database",
			ErrInvalidProvision, req.RealityID)
	}
	return fmt.Sprintf(
		"reality %s provisioned on shard %s as database %s (%d steps, locale=%s, cohort=%d).",
		req.RealityID, out.Shard, out.DBName, out.Steps, req.EffectiveLocale(), req.DeployCohort,
	), nil
}

// formatShards renders the live capacity table for the dry-run summary.
func formatShards(shards []ShardSlot) string {
	if len(shards) == 0 {
		return "(no shards reported)"
	}
	parts := make([]string, 0, len(shards))
	for _, s := range shards {
		parts = append(parts, fmt.Sprintf("%s %d/%d", s.Shard, s.Used, s.Total))
	}
	return strings.Join(parts, ", ")
}
