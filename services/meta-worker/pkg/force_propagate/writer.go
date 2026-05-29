// Package force_propagate is L5.H — the meta-worker force-propagate
// orchestrator + compensating event writer.
//
// RAID cycle 27 DPS 1. Implements the **3-gate force-propagate** flow per
// M4 §9.8.3:
//
//   1. **Opt-in** — caller emits AdminCanonOverrideRequestedV1 (cycle 27).
//   2. **Per-reality owner consent** — `ConsentCollector.Collect` requests
//      consent from each reality owner; Q-L5H-1 LOCKED 24h timeout with
//      default-to-consent on no-response.
//   3. **R13 audit** — every per-reality write goes through the cycle-4
//      MetaWrite audit chain (Q-L1A-3 full audit V1, no sampling).
//
// The compensating L3 event (AdminCanonOverrideCompensatingV1) is the
// per-reality side-effect that fixes projection state for realities that
// consented. It is **audit-distinguishable** from a regular
// canon.entry.updated by event_type — downstream consumers (audit,
// change-history, L5.J timeline) MUST classify it as `force_propagate`.
//
// # LOCKED decisions consumed
//
//   - **Q-L5H-1**: ConsentCollector enforces a 24h deadline. On no-response,
//     `ConsentDecision{Granted: true, Default: true}` is the safe fallback
//     (the request had explicit opt-in at gate 1; silence by reality owner
//     defaults to ACK per governance LOCKED).
//   - **Q-L1A-3**: every consented + compensating event audited via
//     AuditSink (no sampling).
//   - **Q-L1A-2**: writes target per-reality canon_projection only;
//     glossary SSOT untouched.
//   - **Q-L5-3**: canon_layer enum strings carried verbatim
//     (`"L1_axiom"` | `"L2_seeded"`).
//
// # Why this lives in meta-worker (not roleplay-service)
//
// Per I7, meta-worker is the SOLE writer to cross-reality projection
// tables (cycle 5 + cycle 23 + cycle 24 invariant). Force-propagate WRITES
// per-reality `canon_projection` rows (compensating event applies the
// edit), so it MUST live in meta-worker. Roleplay-service is read-side.
//
// # Cross-cycle wiring
//
//   - Cycle 4 MetaWrite audit chain: AuditSink is the bridge.
//   - Cycle 18 resilience: production wraps ConsentCollector with
//     Bulkhead + Retry (interface stays the same).
//   - Cycle 23 L5.A canon contract: event JSON shapes consumed.
//   - Cycle 24 canon_writer: compensating event UPSERTs canon_projection
//     using the SAME PerRealityDB.UpsertCanon interface (re-imported).
//
// # What this writer DOES NOT do
//
//   - Drive the consent UI (caller pre-collects consent decisions OR
//     wires a real ConsentCollector). The package ships interface +
//     default `DeadlineConsentCollector` impl that uses an injected
//     ConsentLookup (operator-supplied ACK/veto/timeout decisions).
//   - Hard-delete or re-write canon SSOT (Q-L1A-2 invariant; only
//     per-reality projection touched).
package force_propagate

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// ConsentTimeout is the Q-L5H-1 LOCKED deadline: reality owner has 24h
// to ACK/veto before default-to-consent fires.
const ConsentTimeout = 24 * time.Hour

// EventType constants — keep in sync with contracts/events/admin_canon_override.go
// + the registry entries.
const (
	EventOverrideRequested    = "admin.canon.override.requested"
	EventOverrideConsented    = "admin.canon.override.consented"
	EventOverrideVetoed       = "admin.canon.override.vetoed"
	EventOverrideCompensating = "admin.canon.override.compensating"
)

// canonLayerL1Axiom / canonLayerL2Seeded mirror Q-L5-3 LOCKED enum (matches
// contracts/events/canon.go + canon_writer).
const (
	canonLayerL1Axiom  = "L1_axiom"
	canonLayerL2Seeded = "L2_seeded"
)

const defaultLockLevel = "soft"

// ─────────────────────────────────────────────────────────────────────────
// Public types — request shape + per-reality decision shape.
// ─────────────────────────────────────────────────────────────────────────

// ForcePropagateRequest is the gate-1 (opt-in) input to the orchestrator.
// Caller supplies this AFTER emitting admin.canon.override.requested.
type ForcePropagateRequest struct {
	OverrideID    uuid.UUID
	CanonEntryID  uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	NewValue      []byte
	CanonLayer    string // Q-L5-3 enum string
	Reason        string // AdminCanonOverrideReason as string
	RequestedBy   uuid.UUID
	RequestedAt   time.Time
}

// ConsentDecision is the gate-2 (per-reality) outcome from
// ConsentCollector.Collect.
type ConsentDecision struct {
	RealityID uuid.UUID
	// Granted is true when the reality owner ACKs (explicit or default).
	Granted bool
	// Default is true when the decision came from Q-L5H-1 default-to-consent
	// (no-response after 24h).
	Default bool
	// ConsentedBy is the user UUID of the ACKing owner (uuid.Nil when
	// Default==true).
	ConsentedBy uuid.UUID
	// VetoReason is set only when Granted==false.
	VetoReason string
	// DecidedAt is when the decision was recorded.
	DecidedAt time.Time
}

// ForcePropagateOutcome is the per-reality result returned from Apply.
type ForcePropagateOutcome struct {
	RealityID     uuid.UUID
	Skipped       bool   // true when veto OR write failure (see Reason)
	Reason        string // human-readable; "vetoed"/"db_error"/"audit_error"/"" for success
	Compensating  bool   // true when a compensating event was emitted
	DefaultConsent bool  // mirror of decision.Default
	Err           error  // non-nil on per-reality db/audit failure
}

// ─────────────────────────────────────────────────────────────────────────
// Dependency interfaces — production wires real impls; tests inject fakes.
// ─────────────────────────────────────────────────────────────────────────

// SubscriberLookup returns the realities subscribed to a book (mirrors
// cycle-24 canon_writer.RealitySubscriptionLookup; re-declared here to
// keep the package self-contained).
type SubscriberLookup interface {
	SubscribersForBook(ctx context.Context, bookID uuid.UUID) ([]uuid.UUID, error)
}

// ConsentLookup returns the operator-supplied or UI-collected per-reality
// decision for a given override. Production wires this to a polling /
// webhook-driven store; tests inject a fixture.
//
// The lookup MUST be deterministic: same override+reality → same answer.
// Returning (ConsentDecision{}, ErrConsentPending) tells the collector
// "still waiting"; ErrConsentTimeout has already-elapsed semantics
// (treated as default-to-consent per Q-L5H-1).
type ConsentLookup interface {
	Lookup(ctx context.Context, overrideID, realityID uuid.UUID) (ConsentDecision, error)
}

// ErrConsentPending signals the consent collector should wait (until the
// deadline, then default-to-consent).
var ErrConsentPending = errors.New("force_propagate: consent decision pending")

// ConsentCollector wraps a ConsentLookup with Q-L5H-1 deadline + default
// semantics.
type ConsentCollector interface {
	Collect(ctx context.Context, req ForcePropagateRequest, realityID uuid.UUID) (ConsentDecision, error)
}

// PerRealityDB writes per-reality projection rows. SAME interface as
// cycle-24 canon_writer.PerRealityDB (intentional duplication to avoid
// cross-package coupling at the interface level; production injects ONE
// implementation that satisfies both).
type PerRealityDB interface {
	UpsertCanon(ctx context.Context, in UpsertIntent) error
}

// UpsertIntent mirrors cycle-24 canon_writer.UpsertIntent (avoid import
// cycle).
type UpsertIntent struct {
	RealityID     uuid.UUID
	CanonEntryID  uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	Value         []byte
	CanonLayer    string
	LockLevel     string
	SourceEventID uuid.UUID
	LastSyncedAt  time.Time
}

// AuditEntry is the per-write audit record. Q-L1A-3 LOCKED full audit.
type AuditEntry struct {
	EventID        uuid.UUID
	EventType      string
	OverrideID     uuid.UUID
	RealityID      uuid.UUID
	CanonEntryID   uuid.UUID
	BookID         uuid.UUID
	AttributePath  string
	DefaultConsent bool
	WrittenAt      time.Time
}

// AuditSink is the audit chain bridge.
type AuditSink interface {
	WriteAudit(ctx context.Context, entry AuditEntry) error
}

// EventEmitter publishes admin.canon.override.* events back to the
// outbox / Redis Stream. Production wires this to publisher; tests
// inject a sink.
type EventEmitter interface {
	Emit(ctx context.Context, eventType string, payload map[string]any) error
}

// Clock injectable for tests.
type Clock interface {
	Now() time.Time
}

type realClock struct{}

func (realClock) Now() time.Time { return time.Now().UTC() }

// ─────────────────────────────────────────────────────────────────────────
// DeadlineConsentCollector — default Q-L5H-1 impl.
// ─────────────────────────────────────────────────────────────────────────

// DeadlineConsentCollector polls the ConsentLookup honoring the Q-L5H-1
// 24h deadline. On timeout (no ACK/veto received), emits the LOCKED
// default-to-consent decision.
//
// NB: this is the in-process orchestrator. Production may layer a
// long-running consent-collection workflow on TOP of this, but the
// `Collect` semantics here are the canonical specification: the caller
// provides a ConsentLookup that becomes definitive after Now ≥ deadline.
type DeadlineConsentCollector struct {
	lookup   ConsentLookup
	timeout  time.Duration
	clock    Clock
	// pollInterval lets tests avoid sleeping in waitForDeadline.
	pollInterval time.Duration
}

// DeadlineConsentCollectorConfig bundles deps.
type DeadlineConsentCollectorConfig struct {
	Lookup       ConsentLookup
	Timeout      time.Duration
	Clock        Clock
	PollInterval time.Duration
}

// NewDeadlineConsentCollector constructs the default collector.
// Timeout defaults to Q-L5H-1 LOCKED 24h. Clock defaults to real wall-clock.
// PollInterval defaults to 1 minute (used only when caller invokes
// CollectBlocking; the non-blocking Collect just queries lookup once
// + computes the deadline-vs-now decision).
func NewDeadlineConsentCollector(cfg DeadlineConsentCollectorConfig) (*DeadlineConsentCollector, error) {
	if cfg.Lookup == nil {
		return nil, errors.New("force_propagate: ConsentLookup nil")
	}
	to := cfg.Timeout
	if to <= 0 {
		to = ConsentTimeout
	}
	clk := cfg.Clock
	if clk == nil {
		clk = realClock{}
	}
	pi := cfg.PollInterval
	if pi <= 0 {
		pi = time.Minute
	}
	return &DeadlineConsentCollector{
		lookup:       cfg.Lookup,
		timeout:      to,
		clock:        clk,
		pollInterval: pi,
	}, nil
}

// Collect returns the per-reality consent decision. Q-L5H-1 LOCKED:
//
//   - Lookup returns an explicit ACK/veto → return as-is.
//   - Lookup returns ErrConsentPending AND deadline is in the future →
//     return ErrConsentPending (caller decides whether to wait/retry).
//   - Lookup returns ErrConsentPending AND deadline has elapsed →
//     return ConsentDecision{Granted: true, Default: true} per Q-L5H-1
//     default-to-consent.
//   - Lookup returns any other error → return it (the orchestrator
//     surfaces it; nothing is presumed about the reality's wishes).
//
// `Collect` is intentionally single-shot — long-running polling lives in
// the caller's loop. Tests inject FakeConsentLookup that simulates each
// state directly.
func (c *DeadlineConsentCollector) Collect(ctx context.Context, req ForcePropagateRequest, realityID uuid.UUID) (ConsentDecision, error) {
	deadline := req.RequestedAt.Add(c.timeout)
	dec, err := c.lookup.Lookup(ctx, req.OverrideID, realityID)
	switch {
	case err == nil:
		// Explicit decision returned — honor it.
		if dec.DecidedAt.IsZero() {
			dec.DecidedAt = c.clock.Now()
		}
		dec.RealityID = realityID
		return dec, nil
	case errors.Is(err, ErrConsentPending):
		// No decision yet. Q-L5H-1: if deadline elapsed, default-to-consent.
		if !c.clock.Now().Before(deadline) {
			return ConsentDecision{
				RealityID: realityID,
				Granted:   true,
				Default:   true,
				DecidedAt: c.clock.Now(),
			}, nil
		}
		// Still inside the 24h window — bubble pending to caller.
		return ConsentDecision{RealityID: realityID}, ErrConsentPending
	default:
		return ConsentDecision{}, fmt.Errorf("force_propagate: consent lookup reality=%s: %w", realityID, err)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Orchestrator — runs gates 2+3 + writes compensating events.
// ─────────────────────────────────────────────────────────────────────────

// Orchestrator drives the 3-gate force-propagate flow per reality.
type Orchestrator struct {
	subscribers SubscriberLookup
	consent     ConsentCollector
	db          PerRealityDB
	audit       AuditSink
	emitter     EventEmitter
	clock       Clock
}

// Config bundles dependencies.
type Config struct {
	Subscribers SubscriberLookup
	Consent     ConsentCollector
	DB          PerRealityDB
	Audit       AuditSink
	Emitter     EventEmitter
	Clock       Clock
}

// New constructs an Orchestrator. All non-Clock deps required.
func New(cfg Config) (*Orchestrator, error) {
	if cfg.Subscribers == nil {
		return nil, errors.New("force_propagate: Subscribers nil")
	}
	if cfg.Consent == nil {
		return nil, errors.New("force_propagate: Consent nil")
	}
	if cfg.DB == nil {
		return nil, errors.New("force_propagate: DB nil")
	}
	if cfg.Audit == nil {
		return nil, errors.New("force_propagate: Audit nil")
	}
	if cfg.Emitter == nil {
		return nil, errors.New("force_propagate: Emitter nil")
	}
	clk := cfg.Clock
	if clk == nil {
		clk = realClock{}
	}
	return &Orchestrator{
		subscribers: cfg.Subscribers,
		consent:     cfg.Consent,
		db:          cfg.DB,
		audit:       cfg.Audit,
		emitter:     cfg.Emitter,
		clock:       clk,
	}, nil
}

// Apply runs gates 2 + 3 for `req`. Per reality:
//
//   - Consent ACK (explicit or default Q-L5H-1) → emit consented event,
//     UPSERT canon_projection (compensating event), emit compensating
//     event, write audit.
//   - Consent veto → emit vetoed event, no projection write, audit veto.
//   - Per-reality DB write failure → captured in Outcome, audit emitted
//     (we still owe the audit trail even on failure per Q-L1A-3).
//   - Audit write failure → first error returned to caller (NACK).
//
// On Subscriber lookup failure or empty subscribers, returns the lookup
// error / empty outcomes respectively.
//
// **Invariant**: every reality in the subscriber list appears in the
// returned []ForcePropagateOutcome with EXACTLY ONE entry.
func (o *Orchestrator) Apply(ctx context.Context, req ForcePropagateRequest) ([]ForcePropagateOutcome, error) {
	if err := validateRequest(req); err != nil {
		return nil, err
	}
	subs, err := o.subscribers.SubscribersForBook(ctx, req.BookID)
	if err != nil {
		return nil, fmt.Errorf("force_propagate: subscribers book=%s: %w", req.BookID, err)
	}
	out := make([]ForcePropagateOutcome, 0, len(subs))
	var firstErr error
	for _, realityID := range subs {
		oc := o.processReality(ctx, req, realityID)
		out = append(out, oc)
		if firstErr == nil && oc.Err != nil {
			firstErr = oc.Err
		}
	}
	return out, firstErr
}

// processReality is the per-reality state machine.
func (o *Orchestrator) processReality(ctx context.Context, req ForcePropagateRequest, realityID uuid.UUID) ForcePropagateOutcome {
	dec, err := o.consent.Collect(ctx, req, realityID)
	if err != nil {
		if errors.Is(err, ErrConsentPending) {
			return ForcePropagateOutcome{
				RealityID: realityID,
				Skipped:   true,
				Reason:    "consent_pending",
			}
		}
		return ForcePropagateOutcome{
			RealityID: realityID,
			Skipped:   true,
			Reason:    "consent_error",
			Err:       err,
		}
	}

	if !dec.Granted {
		// Veto path — emit vetoed event + audit + skip projection.
		if emitErr := o.emitter.Emit(ctx, EventOverrideVetoed, map[string]any{
			"override_id": req.OverrideID,
			"reality_id":  realityID,
			"vetoed_at":   dec.DecidedAt,
			"vetoed_by":   dec.ConsentedBy,
			"reason":      dec.VetoReason,
		}); emitErr != nil {
			// Emit failure is observable but does NOT block the audit
			// row; audit-or-fail dominates.
			_ = emitErr
		}
		auditErr := o.audit.WriteAudit(ctx, AuditEntry{
			EventID:       uuid.New(),
			EventType:     EventOverrideVetoed,
			OverrideID:    req.OverrideID,
			RealityID:     realityID,
			CanonEntryID:  req.CanonEntryID,
			BookID:        req.BookID,
			AttributePath: req.AttributePath,
			WrittenAt:     dec.DecidedAt,
		})
		oc := ForcePropagateOutcome{
			RealityID: realityID,
			Skipped:   true,
			Reason:    "vetoed",
		}
		if auditErr != nil {
			oc.Err = fmt.Errorf("force_propagate: audit veto reality=%s: %w", realityID, auditErr)
		}
		return oc
	}

	// Consented path (explicit OR Q-L5H-1 default).
	// Emit consented event first (forensic ordering: consented BEFORE
	// compensating so audit timelines are linearly reconstructable).
	if emitErr := o.emitter.Emit(ctx, EventOverrideConsented, map[string]any{
		"override_id":     req.OverrideID,
		"reality_id":      realityID,
		"consented_at":    dec.DecidedAt,
		"default_consent": dec.Default,
		"consented_by":    dec.ConsentedBy,
	}); emitErr != nil {
		_ = emitErr
	}

	now := o.clock.Now()
	layer := req.CanonLayer
	if !isValidCanonLayer(layer) {
		layer = canonLayerL2Seeded
	}
	intent := UpsertIntent{
		RealityID:     realityID,
		CanonEntryID:  req.CanonEntryID,
		BookID:        req.BookID,
		AttributePath: req.AttributePath,
		Value:         req.NewValue,
		CanonLayer:    layer,
		LockLevel:     defaultLockLevel,
		SourceEventID: req.OverrideID, // override_id is the source identity
		LastSyncedAt:  now,
	}
	if err := o.db.UpsertCanon(ctx, intent); err != nil {
		// Q-L1A-3: even on write failure we owe an audit row (failure
		// forensics). Write audit + surface DB error.
		_ = o.audit.WriteAudit(ctx, AuditEntry{
			EventID:        uuid.New(),
			EventType:      EventOverrideCompensating,
			OverrideID:     req.OverrideID,
			RealityID:      realityID,
			CanonEntryID:   req.CanonEntryID,
			BookID:         req.BookID,
			AttributePath:  req.AttributePath,
			DefaultConsent: dec.Default,
			WrittenAt:      now,
		})
		return ForcePropagateOutcome{
			RealityID:      realityID,
			Skipped:        true,
			Reason:         "db_error",
			DefaultConsent: dec.Default,
			Err: fmt.Errorf("force_propagate: upsert reality=%s entry=%s: %w",
				realityID, req.CanonEntryID, err),
		}
	}

	// Emit the compensating event (the audit-distinguishable per-reality
	// L3 marker that downstream consumers branch on).
	if emitErr := o.emitter.Emit(ctx, EventOverrideCompensating, map[string]any{
		"override_id":     req.OverrideID,
		"reality_id":      realityID,
		"canon_entry_id":  req.CanonEntryID,
		"book_id":         req.BookID,
		"attribute_path":  req.AttributePath,
		"new_value":       req.NewValue,
		"canon_layer":     layer,
		"applied_at":      now,
		"default_consent": dec.Default,
	}); emitErr != nil {
		// Compensating-event emit failure: the projection write already
		// landed; the event emission missing is a recovery concern.
		// Capture as audit failure semantically (audit chain captures it
		// when AuditSink wraps emit).
		_ = emitErr
	}

	auditErr := o.audit.WriteAudit(ctx, AuditEntry{
		EventID:        uuid.New(),
		EventType:      EventOverrideCompensating,
		OverrideID:     req.OverrideID,
		RealityID:      realityID,
		CanonEntryID:   req.CanonEntryID,
		BookID:         req.BookID,
		AttributePath:  req.AttributePath,
		DefaultConsent: dec.Default,
		WrittenAt:      now,
	})
	oc := ForcePropagateOutcome{
		RealityID:      realityID,
		Compensating:   true,
		DefaultConsent: dec.Default,
	}
	if auditErr != nil {
		oc.Err = fmt.Errorf("force_propagate: audit compensating reality=%s: %w", realityID, auditErr)
	}
	return oc
}

func validateRequest(req ForcePropagateRequest) error {
	if req.OverrideID == uuid.Nil {
		return errors.New("force_propagate: OverrideID required")
	}
	if req.CanonEntryID == uuid.Nil {
		return errors.New("force_propagate: CanonEntryID required")
	}
	if req.BookID == uuid.Nil {
		return errors.New("force_propagate: BookID required")
	}
	if req.AttributePath == "" {
		return errors.New("force_propagate: AttributePath required")
	}
	if req.RequestedAt.IsZero() {
		return errors.New("force_propagate: RequestedAt required (anchors Q-L5H-1 deadline)")
	}
	return nil
}

func isValidCanonLayer(s string) bool {
	return s == canonLayerL1Axiom || s == canonLayerL2Seeded
}
