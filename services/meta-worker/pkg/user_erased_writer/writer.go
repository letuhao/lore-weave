// Package user_erased_writer is L5.C — the meta-worker user-erased
// consumer / per-reality projection cascade.
//
// RAID cycle 24 DPS 2. Consumes `xreality.user.erased` from the Redis
// Stream (cycle 10 xreality fanout) and propagates the GDPR Art. 17
// erasure across every per-reality projection where the user is
// referenced. The actual KMS crypto-shred is performed by admin-cli at
// the meta-DB level (cycle 3 contracts/meta KMSClient.DestroyKEK); this
// writer is the COMPLEMENTARY per-reality cascade that NULLs / scrubs
// any PII-flavored references in per-reality projections so the user's
// name etc. no longer surface from per-reality reads.
//
// ## Q-L5H-1 (LOCKED) — semantics INVERTED for erasure
//
// The base Q-L5H-1 resolution says force-propagate consent timeout is
// 24h with default-to-consent on no-response. For ERASURE the semantics
// INVERT: **default-to-erase on no-response**. Erasure is the safe
// direction: never leave PII alive when uncertain.
//
// Concretely:
//   - If a reality DB is unreachable, the cascade FAILS the message
//     (NACK) → Redis re-delivers → eventual delivery within the SLA.
//   - If the UserRealityLookup is uncertain whether the user has refs
//     in a particular reality, the writer scrubs ANYWAY (the scrub is
//     idempotent on PII-already-NULL rows; safe to over-call).
//   - If the cascade times out for a reality, NACK (do NOT mark the
//     user's PII as alive in that reality). The audit trail captures
//     every retry attempt (Q-L1A-3 full audit V1).
//
// ## Cross-cycle wiring
//
//   - Cycle 3 PII tables + KMSClient + crypto-shred: the meta-DB
//     pii_kek.destroyed_at write is performed by admin-cli (NOT this
//     writer) when the erasure command runs. This writer is triggered
//     by the xreality.user.erased event that admin-cli publishes
//     AFTER the KEK destruction. Order: KEK destroyed → event emitted
//     → this writer cascades per-reality scrubs.
//   - Cycle 5 pgbouncer per-reality pool: PerRealityDB interface
//     here is satisfied in production by a thin wrapper around
//     contracts/meta DbPoolRegistry.
//   - Cycle 7 L1.J degraded mode: per-reality DB unreachable →
//     NACK → Redis re-delivers. CRITICAL: never silently swallow
//     a scrub failure (Q-L5H-1 inverted: leaving PII alive is the
//     UNSAFE direction).
//   - Cycle 4 MetaWrite audit: every per-reality scrub emits a
//     meta_write_audit row via AuditSink (Q-L1A-3 = NO sampling).
//   - Cycle 10 dispatch.Dispatcher: registers HandleUserErased as the
//     handler for `xreality.user.erased` (REPLACES the V1 skeleton
//     no-op handler from dispatch.NewWithSkeletons).
//
// ## What this writer DOES NOT do
//
//   - Destroy KEK / crypto-shred — admin-cli + cycle-3 KMS adapter.
//   - Hard-delete the user row — meta DB keeps audit trail
//     intact (cycle 3 pii_registry.erased_at marker).
//   - Touch glossary-service authored canon entries (Q-L1A-2: those
//     are SSOT; erasure of authored content is a separate workflow).
package user_erased_writer

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// EventTypeUserErased is the dispatch key.
const EventTypeUserErased = "xreality.user.erased"

// ─────────────────────────────────────────────────────────────────────────
// Event payload model — mirrors XRealityUserErasedV1 in
// contracts/events/xreality.go (cycle 10).
// ─────────────────────────────────────────────────────────────────────────

// UserErasedPayload is the decoded envelope.
type UserErasedPayload struct {
	UserID    uuid.UUID
	ErasedAt  time.Time
	RequestID string
	EventID   uuid.UUID
}

// ─────────────────────────────────────────────────────────────────────────
// Dependency interfaces.
// ─────────────────────────────────────────────────────────────────────────

// ScrubIntent is the per-reality cascade write request. The actual
// projection columns scrubbed are owned by the DB adapter (NULL display
// name, set body_member_* references to [erased], etc.). The writer
// emits the intent; the adapter knows which projection tables in that
// reality reference user PII.
type ScrubIntent struct {
	RealityID uuid.UUID
	UserID    uuid.UUID
	// EventID is the source xreality.user.erased event_id, propagated
	// for audit + idempotency (the DB adapter may use it as a dedupe key).
	EventID   uuid.UUID
	ErasedAt  time.Time
	RequestID string
	IssuedAt  time.Time
}

// PerRealityDB scrubs PII references for the user in the named reality.
// Production binds this to a pgbouncer-fronted *sql.DB (cycle 5);
// tests inject a fake.
//
// MUST be idempotent: re-running with the same UserID against an
// already-scrubbed reality produces no change. Implementation typically
// uses `WHERE ... AND erased_marker IS NULL` guards.
//
// Returns non-nil error on failure (DB unreachable / SQL error). Q-L5H-1
// inverted: caller NACKs on error — leaving PII alive in a reality
// because of a transient failure is UNSAFE.
type PerRealityDB interface {
	ScrubUserRefs(ctx context.Context, in ScrubIntent) error
}

// UserRealityLookup returns the set of reality_ids where the user has
// PII references. Production reads pii_reference_index or similar (cycle
// 3 follow-up); tests inject a fixture.
//
// Q-L5H-1 inverted: when the lookup is UNCERTAIN whether the user
// touched a reality, callers SHOULD include it (over-scrubbing is
// safe; under-scrubbing leaks PII).
type UserRealityLookup interface {
	RealitiesForUser(ctx context.Context, userID uuid.UUID) ([]uuid.UUID, error)
}

// MetaScrubber scrubs the user's PII in META tables (P2/071) — the
// cross-reality player_character_index.pc_name copy that the per-reality
// pc_projection scrub does NOT reach. Production routes it through MetaWrite
// (so each row is self-audited + emits pc.index.status.changed). Called once
// per Handle. MUST be idempotent (re-delivery is safe). A non-nil error → NACK
// (Q-L5H-1 inverted: leaving the PII copy alive is the UNSAFE direction).
type MetaScrubber interface {
	ScrubUserMetaRefs(ctx context.Context, userID uuid.UUID) error
}

// AuditEntry is the per-reality cascade audit record.
type AuditEntry struct {
	EventID    uuid.UUID
	UserID     uuid.UUID
	RealityID  uuid.UUID
	RequestID  string
	ErasedAt   time.Time
	ScrubbedAt time.Time
	Outcome    string // "scrubbed" or "noop_already_scrubbed"
}

// AuditSink is the per-write audit hook. Q-L1A-3 full audit V1.
type AuditSink interface {
	WriteAudit(ctx context.Context, e AuditEntry) error
}

// Clock lets tests inject a deterministic time source.
type Clock interface {
	Now() time.Time
}

type realClock struct{}

func (realClock) Now() time.Time { return time.Now().UTC() }

// ─────────────────────────────────────────────────────────────────────────
// Writer.
// ─────────────────────────────────────────────────────────────────────────

// Writer is the L5.C user-erased per-reality cascade writer.
type Writer struct {
	lookup       UserRealityLookup
	db           PerRealityDB
	audit        AuditSink
	metaScrubber MetaScrubber // optional
	clock        Clock
}

// Config bundles the dependencies.
type Config struct {
	Lookup UserRealityLookup
	DB     PerRealityDB
	Audit  AuditSink
	// MetaScrubber is OPTIONAL (P2/071): when set, Handle also scrubs the
	// user's PII in META tables (the cross-reality player_character_index.pc_name
	// copy) exactly once per event, via MetaWrite (self-audited). nil = skip
	// (back-compat for existing callers/tests that only cascade per-reality).
	MetaScrubber MetaScrubber
	Clock        Clock // optional
}

// New constructs a Writer. All non-Clock/MetaScrubber deps required.
func New(cfg Config) (*Writer, error) {
	if cfg.Lookup == nil {
		return nil, errors.New("user_erased_writer: Lookup nil")
	}
	if cfg.DB == nil {
		return nil, errors.New("user_erased_writer: DB nil")
	}
	if cfg.Audit == nil {
		return nil, errors.New("user_erased_writer: Audit nil")
	}
	clk := cfg.Clock
	if clk == nil {
		clk = realClock{}
	}
	return &Writer{
		lookup:       cfg.Lookup,
		db:           cfg.DB,
		audit:        cfg.Audit,
		metaScrubber: cfg.MetaScrubber,
		clock:        clk,
	}, nil
}

// Handle is the dispatch.Handler for `xreality.user.erased`.
//
// Q-L5H-1 INVERTED semantics:
//   - On lookup error → NACK (do NOT default to no-op; that would leave
//     PII alive in unknown realities).
//   - On per-reality DB error → record the first error, continue
//     attempting remaining realities (each iteration is independent),
//     then return the recorded error → consumer NACKs → Redis
//     re-delivers → eventual delivery.
//   - On audit failure → NACK (Q-L1A-3 = no sampling).
//   - Idempotent: re-delivery against already-scrubbed realities is
//     safe (PerRealityDB.ScrubUserRefs MUST be idempotent).
func (w *Writer) Handle(ctx context.Context, fields map[string]any) error {
	if fields == nil {
		return fmt.Errorf("user_erased_writer: nil fields envelope")
	}
	payload, err := decodePayload(fields)
	if err != nil {
		return fmt.Errorf("user_erased_writer: decode: %w", err)
	}

	realities, err := w.lookup.RealitiesForUser(ctx, payload.UserID)
	if err != nil {
		// Q-L5H-1 INVERTED: lookup uncertainty → NACK, never silent-skip.
		return fmt.Errorf("user_erased_writer: realities-for-user lookup user=%s: %w", payload.UserID, err)
	}

	now := w.clock.Now()
	var firstErr error
	for _, realityID := range realities {
		intent := ScrubIntent{
			RealityID: realityID,
			UserID:    payload.UserID,
			EventID:   payload.EventID,
			ErasedAt:  payload.ErasedAt,
			RequestID: payload.RequestID,
			IssuedAt:  now,
		}
		if err := w.db.ScrubUserRefs(ctx, intent); err != nil {
			if firstErr == nil {
				firstErr = fmt.Errorf("user_erased_writer: scrub reality=%s user=%s: %w",
					realityID, payload.UserID, err)
			}
			continue
		}
		auditEntry := AuditEntry{
			EventID:    payload.EventID,
			UserID:     payload.UserID,
			RealityID:  realityID,
			RequestID:  payload.RequestID,
			ErasedAt:   payload.ErasedAt,
			ScrubbedAt: now,
			Outcome:    "scrubbed",
		}
		if err := w.audit.WriteAudit(ctx, auditEntry); err != nil {
			if firstErr == nil {
				firstErr = fmt.Errorf("user_erased_writer: audit reality=%s user=%s: %w",
					realityID, payload.UserID, err)
			}
		}
	}

	// Meta-side scrub (P2/071): the cross-reality player_character_index.pc_name
	// copy. Once per event, via MetaWrite (self-audited). Idempotent. Runs after
	// the per-reality cascade; a failure NACKs the whole event (Q-L5H-1).
	if w.metaScrubber != nil {
		if err := w.metaScrubber.ScrubUserMetaRefs(ctx, payload.UserID); err != nil {
			if firstErr == nil {
				firstErr = fmt.Errorf("user_erased_writer: meta-scrub user=%s: %w", payload.UserID, err)
			}
		}
	}
	return firstErr
}

// EventTypes returns the single event_type this writer handles.
func EventTypes() []string {
	return []string{EventTypeUserErased}
}

// ─────────────────────────────────────────────────────────────────────────
// Envelope decoder.
// ─────────────────────────────────────────────────────────────────────────

func decodePayload(fields map[string]any) (UserErasedPayload, error) {
	out := UserErasedPayload{}
	uid, err := uuidField(fields, "user_id")
	if err != nil {
		return out, err
	}
	out.UserID = uid

	// event_id from envelope.
	if v, e := uuidField(fields, "event_id"); e == nil {
		out.EventID = v
	}

	// erased_at; tolerate either string or time.Time.
	if t, ok := timeField(fields, "erased_at"); ok {
		out.ErasedAt = t
	} else if t, ok := timeField(fields, "recorded_at"); ok {
		// fallback
		out.ErasedAt = t
	}

	// request_id is optional.
	if s, ok := fields["request_id"].(string); ok {
		out.RequestID = s
	}
	return out, nil
}

// uuidField extracts a UUID from fields[key]. Accepts string or uuid.UUID.
func uuidField(fields map[string]any, key string) (uuid.UUID, error) {
	v, ok := fields[key]
	if !ok {
		return uuid.Nil, fmt.Errorf("missing field %q", key)
	}
	switch x := v.(type) {
	case string:
		if x == "" {
			return uuid.Nil, fmt.Errorf("empty field %q", key)
		}
		u, err := uuid.Parse(x)
		if err != nil {
			return uuid.Nil, fmt.Errorf("invalid uuid in %q: %w", key, err)
		}
		return u, nil
	case uuid.UUID:
		if x == uuid.Nil {
			return uuid.Nil, fmt.Errorf("zero uuid in %q", key)
		}
		return x, nil
	default:
		return uuid.Nil, fmt.Errorf("unsupported type for %q: %T", key, v)
	}
}

// timeField extracts a time.Time. Accepts time.Time or RFC3339 string.
func timeField(fields map[string]any, key string) (time.Time, bool) {
	v, ok := fields[key]
	if !ok {
		return time.Time{}, false
	}
	switch x := v.(type) {
	case time.Time:
		return x, true
	case string:
		t, err := time.Parse(time.RFC3339Nano, x)
		if err == nil {
			return t, true
		}
		t, err = time.Parse(time.RFC3339, x)
		return t, err == nil
	}
	return time.Time{}, false
}
