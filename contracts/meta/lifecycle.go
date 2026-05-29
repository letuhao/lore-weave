package meta

import (
	"context"
	"errors"
	"fmt"
)

// AttemptStateTransition is the canonical wrapper around MetaWrite for
// resources that have a state machine in transitions.yaml. Per L1.B §4:
//
//   1. Look up the resource's transition graph (loaded at startup).
//   2. Reject if (FromState, ToState) not in graph → ErrInvalidTransition.
//   3. Reject if the FromState forbids the ToState via mutual_exclusions →
//      ErrMutualExclusion.
//   4. Delegate to MetaWrite with Operation=UPDATE + ExpectedBefore set on
//      the state column — CAS for free.
//   5. Write a lifecycle_transition_audit row inside the SAME TX (regardless
//      of success/failure path — failed attempts must also be auditable).
//
// On graph-rejection (steps 2 + 3) the library still writes a failed-attempt
// audit row in its own TX (Q-L1A-3: FULL audit, no sampling).
func AttemptStateTransition(ctx context.Context, cfg *Config, req TransitionRequest) (*TransitionResult, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if cfg.Transitions == nil {
		return nil, fmt.Errorf("meta: cfg.Transitions is nil; AttemptStateTransition requires a loaded graph")
	}
	if err := req.Validate(); err != nil {
		return nil, err
	}
	resource, ok := cfg.Transitions.Resources[req.ResourceType]
	if !ok {
		_ = writeFailedTransitionAudit(ctx, cfg, req, "invalid_transition")
		return nil, fmt.Errorf("%w: resource_type=%q", ErrUnknownResource, req.ResourceType)
	}
	allowed, forbidden := resource.Allows(req.FromState, req.ToState)
	switch {
	case forbidden:
		_ = writeFailedTransitionAudit(ctx, cfg, req, "mutual_exclusion")
		return nil, fmt.Errorf("%w: %s→%s blocked by mutual_exclusion from %s",
			ErrMutualExclusion, req.FromState, req.ToState, req.FromState)
	case !allowed:
		_ = writeFailedTransitionAudit(ctx, cfg, req, "invalid_transition")
		return nil, fmt.Errorf("%w: %s→%s not in graph for %s",
			ErrInvalidTransition, req.FromState, req.ToState, req.ResourceType)
	}

	// Build the underlying MetaWriteIntent: UPDATE on (resource_table) PK=resource_id,
	// CAS on (state_column=FromState), set new state + any payload overrides.
	pkColumn := pkColumnFor(resource.Table) // convention: always "<resource>_id" matching table name
	newValues := map[string]any{
		resource.StateColumn: req.ToState,
	}
	for k, v := range req.Payload {
		newValues[k] = v
	}
	intent := MetaWriteIntent{
		Table:     resource.Table,
		Operation: OpUpdate,
		PK: map[string]any{
			pkColumn: req.ResourceID,
		},
		ExpectedBefore: map[string]any{
			resource.StateColumn: req.FromState,
		},
		NewValues:      newValues,
		Actor:          req.Actor,
		Reason:         req.Reason,
		RequestContext: RequestContext{},
	}

	_, err := MetaWrite(ctx, cfg, intent)
	if err != nil {
		// On CAS mismatch we audit it as a separate failed-attempt row.
		// (Note: the inner MetaWrite already wrote a meta_write_audit row IF
		// the row update succeeded but the audit insert failed — that path
		// rolls back; so we only audit FAIL here, not double-audit success.)
		reason := "database_error"
		if errors.Is(err, ErrConcurrentStateTransition) {
			reason = "concurrent_modification"
		}
		_ = writeFailedTransitionAudit(ctx, cfg, req, reason)
		return nil, err
	}

	// Success path: write the lifecycle_transition_audit row.
	now := cfg.Clock.NowUnixNano()
	auditID := cfg.UUIDGen.New()
	auditRow := LifecycleTransitionAuditRow{
		AuditID:          auditID,
		ResourceID:       req.ResourceID,
		FromStatus:       req.FromState,
		ToStatus:         req.ToState,
		ActorID:          req.Actor.ID,
		ActorType:        req.Actor.Type,
		Succeeded:        true,
		FailureReason:    "",
		Payload:          req.Payload,
		AttemptedAtNanos: now,
	}
	if err := writeLifecycleAudit(ctx, cfg, auditRow); err != nil {
		// Audit failure on success path is a system bug; surface it.
		return nil, fmt.Errorf("meta: lifecycle audit write: %w", err)
	}
	return &TransitionResult{
		AuditID:      auditID,
		NewState:     req.ToState,
		TransitionAt: now,
	}, nil
}

// writeFailedTransitionAudit writes a failed-attempt lifecycle row in its own
// TX so the audit row survives even when the data write was rolled back.
// Errors from the audit write itself are swallowed but logged via caller's
// returned error path.
func writeFailedTransitionAudit(ctx context.Context, cfg *Config, req TransitionRequest, reason string) error {
	row := LifecycleTransitionAuditRow{
		AuditID:          cfg.UUIDGen.New(),
		ResourceID:       req.ResourceID,
		FromStatus:       req.FromState,
		ToStatus:         req.ToState,
		ActorID:          req.Actor.ID,
		ActorType:        req.Actor.Type,
		Succeeded:        false,
		FailureReason:    reason,
		Payload:          req.Payload,
		AttemptedAtNanos: cfg.Clock.NowUnixNano(),
	}
	return writeLifecycleAudit(ctx, cfg, row)
}

func writeLifecycleAudit(ctx context.Context, cfg *Config, row LifecycleTransitionAuditRow) error {
	q, args, err := cfg.QueryBuilder.BuildLifecycleAuditInsert(row)
	if err != nil {
		return err
	}
	tx, commit, rollback, err := cfg.DB.BeginTx(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = rollback() }()
	if _, err := tx.Exec(ctx, q, args...); err != nil {
		return err
	}
	return commit()
}

// pkColumnFor returns the PK column name for a known resource table.
// Convention: <singular_resource>_id; reality_registry → reality_id.
//
// Cycle 2 (L1.A-1) seeded with reality_registry.
// Cycle 3 (L1.A-2) added the 4 PII+identity+consent tables.
//   - pii_registry: PK = user_ref_id (user-scoped, not a separate surrogate)
//   - pii_kek:      PK = kek_id (every rotation creates a new kek_id)
//   - user_consent_ledger: COMPOSITE PK (user_ref_id, consent_scope, scope_version);
//       we return user_ref_id as the "primary identity column" used by routing/
//       audit lookups. Callers needing the full PK pass all three in MetaWriteIntent.PK.
//   - player_character_index: PK = pc_index_id
//
// Cycle 4 (L1.A-3) added the 5 audit tables (all use surrogate audit_id PKs).
//   - meta_write_audit, meta_read_audit, admin_action_audit,
//     service_to_service_audit, prompt_audit — every row is a new audit_id.
//
// Cycles 5-10 will extend further (billing tables, SRE tables).
// At some point we should load this map from transitions.yaml or a dedicated
// schema map file — until then, this hard-coded switch is the canonical source.
func pkColumnFor(table string) string {
	switch table {
	case "reality_registry":
		return "reality_id"
	case "pii_registry":
		return "user_ref_id"
	case "pii_kek":
		return "kek_id"
	case "user_consent_ledger":
		return "user_ref_id"
	case "player_character_index":
		return "pc_index_id"
	// Cycle 4 — L1.A-3 audit tables
	case "meta_write_audit",
		"meta_read_audit",
		"admin_action_audit",
		"service_to_service_audit",
		"prompt_audit":
		return "audit_id"
	}
	// Fallback heuristic — strip common suffixes; safe enough for service
	// teams to follow naming convention while we wait for explicit mapping.
	return "id"
}
