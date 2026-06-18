package service_acl

import (
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// AuditResult mirrors the migration 016 CHECK constraint
// `s2s_audit_result_enum`: one of ok|deny|error|timeout.
type AuditResult string

const (
	AuditResultOK      AuditResult = "ok"
	AuditResultDeny    AuditResult = "deny"
	AuditResultError   AuditResult = "error"
	AuditResultTimeout AuditResult = "timeout"
)

// IsValid mirrors the DB CHECK constraint.
func (r AuditResult) IsValid() bool {
	switch r {
	case AuditResultOK, AuditResultDeny, AuditResultError, AuditResultTimeout:
		return true
	}
	return false
}

// AuditEntry mirrors a `service_to_service_audit` row (migration 016).
// Constructed by EmitAudit; written by the caller through MetaWrite()
// (cycle 2) — this package does not own DB I/O.
type AuditEntry struct {
	AuditID         uuid.UUID
	CallerService   string
	CalleeService   string
	RPCName         string
	PrincipalMode   PrincipalMode
	UserRefID       *uuid.UUID
	Result          AuditResult
	LatencyMillis   int
	TraceID         string
	RequestID       string
	CreatedAtNanos  int64
}

// Validate enforces the migration 016 CHECK constraints in-process so the
// caller fails BEFORE attempting the DB insert (faster + clearer error).
func (a *AuditEntry) Validate() error {
	if a == nil {
		return errors.New("service_acl: nil AuditEntry")
	}
	if a.AuditID == uuid.Nil {
		return errors.New("service_acl: audit_id required")
	}
	if a.CallerService == "" {
		return errors.New("service_acl: caller_service required")
	}
	if a.CalleeService == "" {
		return errors.New("service_acl: callee_service required")
	}
	if a.RPCName == "" {
		return errors.New("service_acl: rpc_name required")
	}
	if !a.PrincipalMode.IsValid() {
		return fmt.Errorf("service_acl: invalid principal_mode %q", a.PrincipalMode)
	}
	if !a.Result.IsValid() {
		return fmt.Errorf("service_acl: invalid result %q", a.Result)
	}
	if a.LatencyMillis < 0 {
		return fmt.Errorf("service_acl: latency_ms must be >= 0 (got %d)", a.LatencyMillis)
	}
	// Mirrors s2s_audit_created_at_nanos_plausible (≥ 2020-01-01).
	if a.CreatedAtNanos <= 1577836800000000000 {
		return fmt.Errorf("service_acl: created_at_nanos must be > 1577836800000000000 (got %d)", a.CreatedAtNanos)
	}
	if a.PrincipalMode == PrincipalRequiresUser && a.UserRefID == nil {
		return errors.New("service_acl: principal_mode requires_user but user_ref_id is nil (matches DB CHECK s2s_audit_user_ref_present_when_required)")
	}
	return nil
}

// AuditWriter is the interface the cycle-2 MetaWrite() wrapper implements.
// Tests use InMemoryAuditWriter.
type AuditWriter interface {
	WriteServiceToServiceAudit(entry AuditEntry) error
}

// InMemoryAuditWriter is a reference implementation used in tests. Real
// production code wraps MetaWrite() — see services/<x>/internal/auth
// callsites once the SVID middleware ships.
type InMemoryAuditWriter struct {
	Entries []AuditEntry
}

// WriteServiceToServiceAudit appends to Entries. Validates the row first
// so the test is guaranteed to see only well-formed rows.
func (w *InMemoryAuditWriter) WriteServiceToServiceAudit(entry AuditEntry) error {
	if err := entry.Validate(); err != nil {
		return err
	}
	w.Entries = append(w.Entries, entry)
	return nil
}

// DecisionToAuditResult is the canonical mapping from a CheckRPCAllowed
// decision to the audit `result` column. Library users SHOULD use this
// rather than inventing their own mapping — keeps dashboards consistent.
func DecisionToAuditResult(d Decision) AuditResult {
	if d.IsAllow() {
		return AuditResultOK
	}
	return AuditResultDeny
}
