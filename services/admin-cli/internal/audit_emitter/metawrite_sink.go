package audit_emitter

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// adminActionAuditTable is the meta table this Sink writes (allowlisted).
const adminActionAuditTable = "admin_action_audit"

// commandVersion stamps admin_action_audit.command_version (CHECK length>0).
// A const until a real per-command version source exists.
const commandVersion = "1.0.0"

// MetaWriteSink persists audit Actions to admin_action_audit via contracts/meta
// MetaWrite() (so the write is itself audited in meta_write_audit, same TX). The
// production Sink. Maps an Action onto admin_action_audit's columns, satisfying
// every migration-015/032 CHECK. On a failed outcome the RAW handler error
// (Action.ErrorDetailRaw) is scrubbed here into the scrubber-quad (099); a
// 'started' row is persisted for destructive/griefing commands (098).
//
// Forensic notes (code-review WARNs, accepted):
//   - The admin_action_audit row is the SSOT. The same-TX meta_write_audit COPY
//     of NewValues is run through cfg.Scrubber. As of D-SCRUB-BINARY-FIDELITY the
//     scrubber passes BINARY []byte (e.g. error_detail_raw_hash) through verbatim
//     (only valid-UTF-8 text is regex-scrubbed), so the binary hash is no longer
//     mutated in the copy; still correlate the two audit rows via the shared
//     audit_id (PK) rather than re-reading either column's copy.
//   - admin_action_audit.created_at_nanos and the meta_write_audit row's own
//     created_at_nanos are stamped from independent Clock reads, so they may
//     differ sub-millisecond. Correlate via audit_id, not timestamp.
type MetaWriteSink struct {
	cfg *meta.Config
}

// NewMetaWriteSink wires the Sink to a MetaWrite Config (DB=metapg, allowlist
// permitting admin_action_audit, scrubber, clock, uuidgen).
func NewMetaWriteSink(cfg *meta.Config) *MetaWriteSink { return &MetaWriteSink{cfg: cfg} }

var _ Sink = (*MetaWriteSink)(nil)

// Write maps an Action → admin_action_audit INSERT via MetaWrite. The "started"
// (Before) Action persists as a 'started' row for destructive/griefing commands
// (098 forensic trace) and is skipped for read/informational tiers; the durable
// outcome row (success/dry_run/error) is always written.
func (s *MetaWriteSink) Write(ctx context.Context, a Action) error {
	resultKind, persist := mapResultKind(a)
	if !persist {
		return nil // "started" / unknown → no admin_action_audit row
	}

	actorID, err := uuid.Parse(a.Actor)
	if err != nil {
		// Production admin subjects are UUIDs (074/075 JWT sub = user_ref_id);
		// a non-UUID actor (e.g. a dev-token subject) must never reach the
		// audited path — main refuses dev tokens when META_DATABASE_URL is set.
		return fmt.Errorf("%w: actor_id %q is not a UUID", ErrAudit, a.Actor)
	}

	params, err := json.Marshal(paramsEnvelope(a))
	if err != nil {
		return fmt.Errorf("%w: marshal parameters: %v", ErrAudit, err)
	}
	// result captures the timing the schema has no dedicated columns for
	// (created_at_nanos is the audit-write instant, not the command's
	// start/finish). Outcome itself lives in result_kind.
	resultMap := map[string]any{}
	if !a.StartedAt.IsZero() {
		resultMap["started_at_unix"] = a.StartedAt.Unix()
	}
	if !a.FinishedAt.IsZero() {
		resultMap["finished_at_unix"] = a.FinishedAt.Unix()
	}
	result, err := json.Marshal(resultMap)
	if err != nil {
		return fmt.Errorf("%w: marshal result: %v", ErrAudit, err)
	}

	now := time.Now()
	if s.cfg != nil && s.cfg.Clock != nil {
		now = time.Unix(0, s.cfg.Clock.NowUnixNano())
	}

	newValues := map[string]any{
		"command_name":     a.CommandName,
		"command_version":  commandVersion,
		"actor_id":         actorID,
		"actor_type":       string(meta.ActorAdmin), // admin-cli human command (the role lives in parameters)
		"parameters":       params,
		"result":           result,
		"result_kind":      resultKind,
		"created_at_nanos": now.UnixNano(),
	}

	// Scrubber-quad: ALL four on error, NONE otherwise (015 CHECKs).
	// 099 D-ADMINAUDIT-ERROR-TEXT: scrub the RAW handler error → real
	// scrubber-rewritten text + hash + ruleset version + timestamp, instead of
	// the old hash-only sentinel. cfg.Scrubber (RegexScrubber) redacts the 7 PII
	// pattern classes, so no raw PII reaches the audit row.
	if resultKind == "error" {
		sf := s.cfg.Scrubber.Scrub(a.ErrorDetailRaw)
		if len(sf.RawHash) != 32 {
			return fmt.Errorf("%w: scrubber RawHash must be 32-byte SHA-256, got %d bytes", ErrAudit, len(sf.RawHash))
		}
		newValues["error_detail_raw_hash"] = sf.RawHash
		newValues["error_detail_scrubbed"] = sf.Scrubbed
		newValues["scrub_version"] = sf.Version
		newValues["scrubbed_at"] = sf.ScrubbedAt
	}

	intent := meta.MetaWriteIntent{
		Table:     adminActionAuditTable,
		Operation: meta.OpInsert,
		PK:        map[string]any{"audit_id": s.cfg.UUIDGen.New()},
		NewValues: newValues,
		Actor:     meta.Actor{Type: meta.ActorAdmin, ID: a.Actor}, // for the same-TX meta_write_audit row (TEXT actor_id)
		Reason:    a.Reason,
	}
	if _, err := meta.MetaWrite(ctx, s.cfg, intent); err != nil {
		return fmt.Errorf("%w: metawrite admin_action_audit: %v", ErrAudit, err)
	}
	return nil
}

// impactTier1Destructive / impactTier2Griefing mirror framework.ImpactClass
// string values (kept as literals to avoid an import cycle — framework imports
// this package).
const (
	impactTier1Destructive = "tier-1-destructive"
	impactTier2Griefing    = "tier-2-griefing"
)

// mapResultKind projects Action.Outcome → admin_action_audit.result_kind.
// succeeded+DryRun → dry_run; succeeded → success; failed → error.
//
// started → persisted as 'started' ONLY for tier-1-destructive / tier-2-griefing
// commands (098 D-ADMINAUDIT-INPROGRESS): a destructive command killed AFTER the
// framework Before hook but BEFORE its terminal hook then still leaves a durable
// forensic row. Read/informational tiers skip the started row (it would only
// double low-value audit volume). Unknown outcome → skip (safe).
func mapResultKind(a Action) (kind string, persist bool) {
	switch a.Outcome {
	case "succeeded":
		if a.DryRun {
			return "dry_run", true
		}
		return "success", true
	case "failed":
		return "error", true
	case "started":
		if a.ImpactClass == impactTier1Destructive || a.ImpactClass == impactTier2Griefing {
			return "started", true
		}
		return "", false
	default: // unknown
		return "", false
	}
}

// paramsEnvelope is the hash-only parameters JSONB: preserves the forensic
// fingerprint without retaining raw params (admin-cli hashes early). Empty when
// no hash (omits the key so it's not a misleading {"params_hash":""}).
func paramsEnvelope(a Action) map[string]any {
	out := map[string]any{}
	if a.ParamsHash != "" {
		out["params_hash"] = a.ParamsHash
	}
	if a.ActorRole != "" {
		out["actor_role"] = a.ActorRole // the role (admin/sre/founder) — not an actor_type
	}
	if a.ImpactClass != "" {
		out["impact_class"] = a.ImpactClass // tier — no dedicated column; kept for forensics
	}
	if a.DoubleApprovalRef != "" {
		out["double_approval_ref"] = a.DoubleApprovalRef
	}
	return out
}
