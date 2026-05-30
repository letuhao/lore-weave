package audit_emitter

import (
	"context"
	"encoding/hex"
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

// scrubVersionHashOnly marks the scrubber-quad as the admin-cli hash-only mode:
// admin-cli hashes errors early and never retains the raw text, so
// error_detail_scrubbed holds a documented sentinel, not scrubber-rewritten
// text. Richer scrubbed-error-text retention is DEFERRED (D-ADMINAUDIT-ERROR-TEXT).
const (
	scrubVersionHashOnly = "admincli-hashonly-v1"
	errorTextSentinel    = "[admin-cli: error hash retained; raw text not stored]"
)

// MetaWriteSink persists audit Actions to admin_action_audit via contracts/meta
// MetaWrite() (so the write is itself audited in meta_write_audit, same TX). The
// production Sink. Maps the hash-only Action onto admin_action_audit's columns,
// satisfying every migration-015 CHECK.
//
// Forensic notes (code-review WARNs, accepted):
//   - The admin_action_audit row is the SSOT. The same-TX meta_write_audit COPY
//     of NewValues is run through cfg.Scrubber, whose []byte/JSON handling can
//     lossily rewrite the binary error_detail_raw_hash + the JSON params blob in
//     THAT copy. Correlate the two audit rows via the shared audit_id (PK), not
//     by re-reading the meta_write_audit copy of these columns. (Tracked:
//     D-SCRUB-BINARY-FIDELITY — utf8-aware []byte scrubbing in contracts/meta.)
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
// (Before) Action is a transient marker with no result_kind → skipped; the
// durable record is the final outcome row.
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
	if resultKind == "error" {
		rawHash, err := hex.DecodeString(a.ErrorDetailHash)
		if err != nil || len(rawHash) != 32 {
			return fmt.Errorf("%w: ErrorDetailHash must be 32-byte SHA-256 hex, got %q", ErrAudit, a.ErrorDetailHash)
		}
		newValues["error_detail_raw_hash"] = rawHash
		newValues["error_detail_scrubbed"] = errorTextSentinel
		newValues["scrub_version"] = scrubVersionHashOnly
		newValues["scrubbed_at"] = now
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

// mapResultKind projects Action.Outcome → admin_action_audit.result_kind.
// started → skip (no result_kind); succeeded+DryRun → dry_run; succeeded →
// success; failed → error. Unknown → skip (safe).
func mapResultKind(a Action) (kind string, persist bool) {
	switch a.Outcome {
	case "succeeded":
		if a.DryRun {
			return "dry_run", true
		}
		return "success", true
	case "failed":
		return "error", true
	default: // "started" or unknown
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
