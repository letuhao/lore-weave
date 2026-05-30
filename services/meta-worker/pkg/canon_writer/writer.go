// Package canon_writer is L5.B — the meta-worker canon-update consumer.
//
// RAID cycle 24 DPS 1. Adds REAL handlers for the four `canon.entry.*`
// events shipped in cycle 23 L5.A (`contracts/events/canon.go`). The
// handlers consume the xreality fan-out (per Q-L2-4 naming, cycle 10
// xreality fanout) and UPSERT each event into the cycle-23 L5.D
// `canon_projection` table on every reality subscribed to the source
// `book_id`.
//
// ## I7 sole-writer invariant
//
// `canon_projection` is per-reality (cycle 23 migration 0009 in
// `contracts/migrations/per_reality/`). The I7 invariant says meta-worker
// is the SOLE writer of cross-reality projections. This package registers
// the dispatch handlers that satisfy that invariant — any other service
// touching canon_projection is an I7 violation (caught by the dispatch
// allowlist + a future static lint scan in cycle 25+ when L5.E lands).
//
// ## LOCKED decisions consumed
//
//   - Q-L1A-3 (full audit V1, no sampling): every projection write
//     emits a meta_write_audit row via the injected AuditSink. The
//     sink is wired in production to contracts/meta.MetaWrite()'s audit
//     chain; tests inject an in-memory capture.
//   - Q-L5-3 (single canon_projection table with canon_layer column):
//     the writer extracts canon_layer from the event payload and writes
//     it as a string ("L1_axiom" or "L2_seeded"). The cycle-23 migration
//     CHECK constraint catches drift defensively.
//   - Q-L5A-1 (glossary outbox is a SEPARATE sub-program): this writer
//     does NOT modify services/glossary-service/. It reads ONLY the
//     event payload — the publisher path is glossary-service's concern.
//   - Q-L1A-2 (canon SSOT tables live in glossary DB): this writer
//     writes ONLY to per-reality canon_projection — never to glossary
//     SSOT tables.
//
// ## Cross-cycle wiring
//
//   - Cycle 10 dispatch.Dispatcher (`pkg/dispatch/`): we register
//     real handlers REPLACING the V1 skeleton no-ops.
//   - Cycle 5 pgbouncer per-reality pool (contracts/meta/pool.go):
//     the PerRealityDB interface here is satisfied in production by a
//     thin wrapper around contracts/meta DbPoolRegistry. Tests inject
//     an in-memory fake.
//   - Cycle 7 L1.J degraded mode: PerRealityDB.UpsertCanon failure →
//     return non-nil error → consumer NACKs the message → Redis
//     re-delivers per cycle-10 consumer protocol.
//   - Cycle 4 MetaWrite audit chain: AuditSink is the bridge.
//
// ## What this writer DOES NOT do
//
//   - Cascade read-through from ancestor realities (multiverse §3) —
//     separate path; lands cycle 25+ when L5.K is in scope.
//   - L3-override marker writes — `overridden_by_l3_event_id` is set
//     by a DIFFERENT per-reality handler (NOT canon.* events).
//   - Real Redis Streams I/O — that lives in pkg/consumer (cycle 10).
package canon_writer

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────
// Event payload model — mirrors contracts/events/canon.go (cycle 23 L5.A).
// We re-decode from the dispatched `map[string]any` envelope rather than
// importing the contracts/events package directly to keep the meta-worker
// dispatcher loosely coupled (it works with the on-wire JSON shape only).
// ─────────────────────────────────────────────────────────────────────────

// canonLayerL1Axiom + canonLayerL2Seeded mirror Q-L5-3 LOCKED enum.
const (
	canonLayerL1Axiom  = "L1_axiom"
	canonLayerL2Seeded = "L2_seeded"
)

// defaultLockLevel matches the canon_projection.lock_level column DEFAULT
// from contracts/migrations/per_reality/0009_canon_projection.up.sql.
const defaultLockLevel = "soft"

// canonEventType enumerates the four canon.* event types we route on.
// Matches cycle-23 L5.A event registry entries.
const (
	EventCanonCreated     = "canon.entry.created"
	EventCanonUpdated     = "canon.entry.updated"
	EventCanonPromoted    = "canon.entry.promoted"
	EventCanonDecanonized = "canon.entry.decanonized"
)

// CanonPayload is the decoded envelope body shared across all four event
// types. Field presence varies by event type; the decoder applies
// per-event-type required-field checks.
type CanonPayload struct {
	CanonEntryID     uuid.UUID
	BookID           uuid.UUID
	AttributePath    string
	Value            []byte // canonical JSON bytes from envelope
	CanonLayer       string
	LockLevel        string
	EventID          uuid.UUID // envelope event_id (Q-L3-4 VerificationMeta)
	AggregateVersion uint64    // envelope aggregate_version (Q-L3-4 VerificationMeta)
	RecordedAt       time.Time // envelope recorded_at
}

// ─────────────────────────────────────────────────────────────────────────
// Dependency interfaces — production wires real SQL/audit; tests inject
// in-memory fakes (see writer_test.go).
// ─────────────────────────────────────────────────────────────────────────

// UpsertIntent is the per-reality projection write request.
type UpsertIntent struct {
	RealityID     uuid.UUID
	CanonEntryID  uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	Value         []byte
	CanonLayer    string
	LockLevel     string
	SourceEventID uuid.UUID
	// AggregateVersion + SourceEventID populate the canon_projection
	// VerificationMeta block (event_id + aggregate_version, NOT NULL per
	// migration 0009 Q-L3-4). The adapter writes SourceEventID to BOTH
	// source_event_id and the event_id VerificationMeta column.
	AggregateVersion uint64
	LastSyncedAt     time.Time
}

// PerRealityDB upserts a canon_projection row in the named reality's DB.
// Production binds this to a pgbouncer-fronted *sql.DB via cycle-5
// contracts/meta/pool.go DbPoolRegistry; tests use the FakePerRealityDB
// from writer_test.go.
//
// UpsertCanon returns a non-nil error when the per-reality DB is
// unreachable (cycle 7 L1.J degraded mode) — the consumer NACKs and
// Redis re-delivers.
type PerRealityDB interface {
	UpsertCanon(ctx context.Context, in UpsertIntent) error
}

// RealitySubscriptionLookup returns the list of reality_ids that subscribe
// to a given book_id (i.e. realities whose canon_projection should
// receive this canon update). Production reads from reality_registry meta
// table (filter status IN ('active','frozen')); tests inject a fixture.
type RealitySubscriptionLookup interface {
	SubscribersForBook(ctx context.Context, bookID uuid.UUID) ([]uuid.UUID, error)
}

// AuditEntry is the canon-projection-write audit record. Production
// translates this to a contracts/meta MetaWriteAuditRow (Q-L1A-3 full
// audit V1, no sampling).
type AuditEntry struct {
	EventID       uuid.UUID
	EventType     string
	RealityID     uuid.UUID
	CanonEntryID  uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	WrittenAt     time.Time
}

// AuditSink is the per-write audit hook. Q-L1A-3 LOCKED: every write
// is audited, no sampling.
type AuditSink interface {
	WriteAudit(ctx context.Context, entry AuditEntry) error
}

// Clock lets tests inject a deterministic time source.
type Clock interface {
	Now() time.Time
}

// realClock is the production Clock binding.
type realClock struct{}

// Now returns wall-clock time.
func (realClock) Now() time.Time { return time.Now().UTC() }

// ─────────────────────────────────────────────────────────────────────────
// Writer.
// ─────────────────────────────────────────────────────────────────────────

// Writer is the L5.B canon-projection writer. One instance lives in the
// meta-worker process; it registers handlers with the cycle-10
// dispatcher.
type Writer struct {
	subscribers RealitySubscriptionLookup
	db          PerRealityDB
	audit       AuditSink
	clock       Clock
}

// Config bundles the dependencies.
type Config struct {
	Subscribers RealitySubscriptionLookup
	DB          PerRealityDB
	Audit       AuditSink
	// Clock is optional; default = real wall-clock.
	Clock Clock
}

// New constructs a Writer. All non-Clock deps are required.
func New(cfg Config) (*Writer, error) {
	if cfg.Subscribers == nil {
		return nil, errors.New("canon_writer: Subscribers nil")
	}
	if cfg.DB == nil {
		return nil, errors.New("canon_writer: DB nil")
	}
	if cfg.Audit == nil {
		return nil, errors.New("canon_writer: Audit nil")
	}
	clk := cfg.Clock
	if clk == nil {
		clk = realClock{}
	}
	return &Writer{
		subscribers: cfg.Subscribers,
		db:          cfg.DB,
		audit:       cfg.Audit,
		clock:       clk,
	}, nil
}

// Handle is the dispatch.Handler for all four canon.* event types.
// The dispatcher routes by event_type; this single handler branches on
// the event_type stored in fields["event_type"] to apply per-event
// projection logic.
//
// Returning a non-nil error tells the consumer to NACK (cycle 7 L1.J:
// transient per-reality DB failures retry via Redis re-delivery).
func (w *Writer) Handle(ctx context.Context, fields map[string]any) error {
	if fields == nil {
		return fmt.Errorf("canon_writer: nil fields envelope")
	}
	eventType, _ := fields["event_type"].(string)
	switch eventType {
	case EventCanonCreated, EventCanonUpdated, EventCanonPromoted, EventCanonDecanonized:
		// fall through to processing
	default:
		return fmt.Errorf("canon_writer: unsupported event_type %q", eventType)
	}

	payload, err := decodeCanonPayload(eventType, fields)
	if err != nil {
		// Bad envelope = permanent decode failure. Returning error NACKs;
		// operator triages the poison message. We intentionally do NOT
		// distinguish here — a poison message MUST stop the stream until
		// triaged (per cycle 10 dispatch ErrNoHandler discipline).
		return fmt.Errorf("canon_writer: decode %s: %w", eventType, err)
	}

	subs, err := w.subscribers.SubscribersForBook(ctx, payload.BookID)
	if err != nil {
		return fmt.Errorf("canon_writer: subscribers lookup book=%s: %w", payload.BookID, err)
	}

	now := w.clock.Now()
	var firstErr error
	for _, realityID := range subs {
		intent := UpsertIntent{
			RealityID:        realityID,
			CanonEntryID:     payload.CanonEntryID,
			BookID:           payload.BookID,
			AttributePath:    payload.AttributePath,
			Value:            payload.Value,
			CanonLayer:       payload.CanonLayer,
			LockLevel:        payload.LockLevel,
			SourceEventID:    payload.EventID,
			AggregateVersion: payload.AggregateVersion,
			LastSyncedAt:     now,
		}
		if err := w.db.UpsertCanon(ctx, intent); err != nil {
			// Cycle 7 L1.J degraded mode: per-reality DB unreachable.
			// Return the FIRST error so the consumer NACKs and retries
			// the WHOLE message. Subsequent realities retry on
			// re-delivery (idempotent UPSERT on canon_entry_id PK).
			if firstErr == nil {
				firstErr = fmt.Errorf("canon_writer: upsert reality=%s book=%s entry=%s: %w",
					realityID, payload.BookID, payload.CanonEntryID, err)
			}
			continue
		}
		// Q-L1A-3 full audit V1 — every successful write audited.
		auditEntry := AuditEntry{
			EventID:       payload.EventID,
			EventType:     eventType,
			RealityID:     realityID,
			CanonEntryID:  payload.CanonEntryID,
			BookID:        payload.BookID,
			AttributePath: payload.AttributePath,
			WrittenAt:     now,
		}
		if err := w.audit.WriteAudit(ctx, auditEntry); err != nil {
			// Audit failure is critical (Q-L1A-3 = NO sampling). Returning
			// nil here would silently swallow audit drops, breaking the
			// "every write audited" invariant. NACK so the operator sees it.
			if firstErr == nil {
				firstErr = fmt.Errorf("canon_writer: audit reality=%s entry=%s: %w",
					realityID, payload.CanonEntryID, err)
			}
		}
	}
	return firstErr
}

// EventTypes returns the four canon.* event types this writer handles.
// Caller (main.go wiring) iterates and calls dispatcher.Register for each.
func EventTypes() []string {
	return []string{
		EventCanonCreated,
		EventCanonUpdated,
		EventCanonPromoted,
		EventCanonDecanonized,
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Envelope decoder.
// ─────────────────────────────────────────────────────────────────────────

// decodeCanonPayload extracts the CanonPayload from a generic dispatched
// envelope. Field naming matches contracts/events/canon.go JSON tags.
//
// Required fields for ALL events: canon_entry_id, book_id.
// Required field for created/updated: canon_layer, attribute_path.
// promoted carries to_layer (we map to canon_layer for projection).
// decanonized requires no value.
//
// Decode failures return errInvalidPayload which the caller wraps.
func decodeCanonPayload(eventType string, fields map[string]any) (CanonPayload, error) {
	out := CanonPayload{}
	var err error

	out.CanonEntryID, err = uuidField(fields, "canon_entry_id")
	if err != nil {
		return out, err
	}
	out.BookID, err = uuidField(fields, "book_id")
	if err != nil {
		return out, err
	}

	// event_id is on the envelope (cycle 10 publisher protocol) — not in
	// the payload struct itself. We accept either name for flexibility.
	if v, e := uuidField(fields, "event_id"); e == nil {
		out.EventID = v
	}

	// aggregate_version is on the envelope (publisher protocol). After the
	// Redis round-trip it arrives as a string; tolerate string/number.
	out.AggregateVersion = uint64Field(fields, "aggregate_version")

	// recorded_at / created_at / updated_at — pick whichever the event
	// type provided.
	for _, k := range []string{"recorded_at", "created_at", "updated_at", "promoted_at", "decanonized_at"} {
		if t, ok := timeField(fields, k); ok {
			out.RecordedAt = t
			break
		}
	}

	switch eventType {
	case EventCanonCreated, EventCanonUpdated:
		out.AttributePath, err = stringField(fields, "attribute_path")
		if err != nil {
			return out, err
		}
		out.CanonLayer, err = stringField(fields, "canon_layer")
		if err != nil {
			return out, err
		}
		if !isValidCanonLayer(out.CanonLayer) {
			return out, fmt.Errorf("invalid canon_layer %q (Q-L5-3: must be L1_axiom or L2_seeded)", out.CanonLayer)
		}
		out.LockLevel, _ = stringField(fields, "lock_level")
		if out.LockLevel == "" {
			out.LockLevel = defaultLockLevel
		}
		// value is either []byte (raw JSON) or any (encoded later by writer).
		if v, ok := fields["value"]; ok {
			out.Value = anyToBytes(v)
		} else if eventType == EventCanonUpdated {
			// updated carries new_value
			if v, ok := fields["new_value"]; ok {
				out.Value = anyToBytes(v)
			}
		}
	case EventCanonPromoted:
		// promoted: to_layer becomes canon_layer (L2_seeded → L1_axiom).
		toLayer, err := stringField(fields, "to_layer")
		if err != nil {
			return out, err
		}
		if !isValidCanonLayer(toLayer) {
			return out, fmt.Errorf("invalid to_layer %q (Q-L5-3)", toLayer)
		}
		out.CanonLayer = toLayer
		// attribute_path may be absent on promotion; default to empty (writer
		// applies UPDATE keyed on canon_entry_id only).
		out.AttributePath, _ = stringField(fields, "attribute_path")
		out.LockLevel, _ = stringField(fields, "lock_level")
		if out.LockLevel == "" {
			out.LockLevel = defaultLockLevel
		}
	case EventCanonDecanonized:
		// decanonized: tombstone semantics owned by Q-L5A-1 sub-program.
		// Foundation reads attribute_path if present; layer left empty
		// (Q-L5A-1 handles tombstone marker — for V1 we keep the row).
		out.AttributePath, _ = stringField(fields, "attribute_path")
		out.LockLevel = "archived"
		// canon_layer must still be valid for the CHECK; default to L2 if
		// the event payload omits it. The Q-L5A-1 sub-program will refine.
		layer, _ := stringField(fields, "canon_layer")
		if !isValidCanonLayer(layer) {
			layer = canonLayerL2Seeded
		}
		out.CanonLayer = layer
	default:
		return out, fmt.Errorf("unsupported event_type %q", eventType)
	}
	return out, nil
}

// isValidCanonLayer enforces Q-L5-3.
func isValidCanonLayer(s string) bool {
	return s == canonLayerL1Axiom || s == canonLayerL2Seeded
}

// uuidField extracts a UUID from fields[key]. Accepts string ("xxx-xxx")
// or uuid.UUID. Empty/missing returns an error.
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

// stringField extracts a string from fields[key]. Empty/missing returns
// an error.
func stringField(fields map[string]any, key string) (string, error) {
	v, ok := fields[key]
	if !ok {
		return "", fmt.Errorf("missing field %q", key)
	}
	s, ok := v.(string)
	if !ok || s == "" {
		return "", fmt.Errorf("invalid string in %q", key)
	}
	return s, nil
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

// uint64Field extracts a uint64 from fields[key]. Tolerates the types a
// value can arrive as: native int/int64/uint64/float64 (in-memory dispatch)
// or string (after a Redis Streams round-trip). Missing/unparseable → 0.
func uint64Field(fields map[string]any, key string) uint64 {
	v, ok := fields[key]
	if !ok {
		return 0
	}
	switch x := v.(type) {
	case uint64:
		return x
	case int64:
		if x < 0 {
			return 0
		}
		return uint64(x)
	case int:
		if x < 0 {
			return 0
		}
		return uint64(x)
	case float64:
		if x < 0 {
			return 0
		}
		return uint64(x)
	case string:
		n, err := strconv.ParseUint(x, 10, 64)
		if err != nil {
			return 0
		}
		return n
	}
	return 0
}

// anyToBytes coerces a value to canonical JSON []byte. A []byte/string is
// returned as-is (already JSON from the wire). Anything else — most importantly
// a map/slice, which is what `value` decodes to AFTER the publisher's payload
// is JSON-round-tripped through Redis Streams (the fanout nests payload as a
// JSON string, the consumer json.Unmarshal-s it back into a Go map) — is
// re-marshalled to JSON so the canon VALUE actually reaches canon_projection
// instead of being silently dropped to NULL. Returns nil only on a non-
// marshalable value (caller treats nil as absent → 'null'::jsonb).
func anyToBytes(v any) []byte {
	switch x := v.(type) {
	case nil:
		return nil
	case []byte:
		return x
	case string:
		return []byte(x)
	}
	b, err := json.Marshal(v)
	if err != nil {
		return nil
	}
	return b
}
