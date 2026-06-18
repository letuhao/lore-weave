package chaos

import (
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// DrillOutcome mirrors the V1+30d `chaos_drills` table outcome column.
type DrillOutcome string

const (
	DrillOutcomeSuccess      DrillOutcome = "success"      // drill completed; SUT held
	DrillOutcomeFailure      DrillOutcome = "failure"      // drill exposed a real bug
	DrillOutcomeAborted      DrillOutcome = "aborted"      // operator stopped mid-drill
	DrillOutcomePreconditionFail DrillOutcome = "precondition_fail" // SUT not in expected state
)

// IsValid mirrors the V1+30d DB CHECK constraint placeholder.
func (o DrillOutcome) IsValid() bool {
	switch o {
	case DrillOutcomeSuccess, DrillOutcomeFailure, DrillOutcomeAborted, DrillOutcomePreconditionFail:
		return true
	}
	return false
}

// DrillEnvironment is the deployment context the drill ran in.
type DrillEnvironment string

const (
	DrillEnvironmentDev     DrillEnvironment = "dev"
	DrillEnvironmentStaging DrillEnvironment = "staging"
	DrillEnvironmentProd    DrillEnvironment = "prod"
)

// IsValid mirrors the V1+30d DB CHECK constraint placeholder.
func (e DrillEnvironment) IsValid() bool {
	switch e {
	case DrillEnvironmentDev, DrillEnvironmentStaging, DrillEnvironmentProd:
		return true
	}
	return false
}

// DrillAuditEntry mirrors the planned (V1+30d) `chaos_drills` meta table
// row. Constructed by the chaos-engine V1+30d at drill completion;
// written via MetaWrite() (cycle 2).
//
// Stable shape NOW so V1+30d schema migration is unambiguous (the
// migration file will land in a separate sub-program; this Go type is
// the SSOT until then).
type DrillAuditEntry struct {
	DrillID            uuid.UUID
	DrillName          string
	HookIDsTriggered   []HookID
	TargetService      string
	TargetShardID      string // optional; empty for service-wide drills
	Environment        DrillEnvironment
	Outcome            DrillOutcome
	StartedAtNanos     int64
	CompletedAtNanos   int64
	OperatorActorID    string
	Notes              string
}

// Validate enforces the planned CHECK constraints in-process.
func (a *DrillAuditEntry) Validate() error {
	if a == nil {
		return errors.New("chaos: nil DrillAuditEntry")
	}
	if a.DrillID == uuid.Nil {
		return errors.New("chaos: drill_id required")
	}
	if a.DrillName == "" {
		return errors.New("chaos: drill_name required")
	}
	if a.TargetService == "" {
		return errors.New("chaos: target_service required")
	}
	if !a.Environment.IsValid() {
		return fmt.Errorf("chaos: invalid environment %q", a.Environment)
	}
	if !a.Outcome.IsValid() {
		return fmt.Errorf("chaos: invalid outcome %q", a.Outcome)
	}
	if a.StartedAtNanos <= 1577836800000000000 {
		return fmt.Errorf("chaos: started_at_nanos must be > 1577836800000000000 (got %d)", a.StartedAtNanos)
	}
	if a.CompletedAtNanos < a.StartedAtNanos {
		return fmt.Errorf("chaos: completed_at_nanos (%d) must be >= started_at_nanos (%d)", a.CompletedAtNanos, a.StartedAtNanos)
	}
	if a.OperatorActorID == "" {
		return errors.New("chaos: operator_actor_id required (audit-trail invariant)")
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────────
// ExampleDrillMetaOutageProbe — ONE example drill class per brief spec.
// Pattern matches the chaos/drills/meta_outage.yaml semantic (cycle 7)
// but expressed as the SDK Drill type the V1+30d chaos-engine will run.
// ─────────────────────────────────────────────────────────────────────

// ExampleDrillMetaOutageProbe is the reference SDK-side drill that
// reproduces the meta_outage drill semantic without yet running it. It
// emits the hook trigger that the L1.J degraded-mode subsystem expects;
// the V1+30d chaos-engine wires this to the kill-container side-effect.
//
// Foundation does NOT execute it this cycle — Q-L4-4 LOCKED. We ship
// the type so the chaos-engine repo can build against a stable shape.
type ExampleDrillMetaOutageProbe struct {
	TargetService string
	Environment   DrillEnvironment
}

// HooksFired returns the deterministic HookIDs this drill would trigger.
// Cross-checked in tests so any drift between SDK + chaos-engine repo is
// caught at compile time.
func (d ExampleDrillMetaOutageProbe) HooksFired() []HookID {
	return []HookID{
		"meta.write.before_pg_query",
		"meta.read.before_pg_query",
	}
}

// AuditTemplate returns an unsigned DrillAuditEntry the chaos-engine
// fills in with timing + outcome at drill completion. UUID + timestamps
// must be set by the caller — this template ONLY captures the
// drill-class identity.
func (d ExampleDrillMetaOutageProbe) AuditTemplate() DrillAuditEntry {
	return DrillAuditEntry{
		DrillName:        "meta_outage",
		TargetService:    d.TargetService,
		Environment:      d.Environment,
		HookIDsTriggered: d.HooksFired(),
	}
}
