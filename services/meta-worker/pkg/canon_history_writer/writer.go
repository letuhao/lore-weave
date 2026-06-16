// Package canon_history_writer is L5.J — the meta-worker timeline-append
// emitter.
//
// RAID cycle 27 DPS 3. Consumes:
//
//   - canon.entry.{created,updated,promoted,decanonized} (cycle 23 L5.A)
//   - admin.canon.override.compensating (cycle 27 L5.H)
//
// and APPENDS one canon.change.recorded entry per delivery to the
// `canon_change_history` table via the cycle 27 L5.J `TimelineAppender`
// trait.
//
// # APPEND-ONLY discipline
//
// This writer holds NO UPDATE or DELETE codepaths. The trait surface
// itself (timeline.TimelineAppender) exposes ONLY Append, so even
// accidental rewrite code wouldn't compile.
//
// The DB-level enforcement (CHECK trigger + REVOKE UPDATE/DELETE) ships
// in `contracts/migrations/glossary/0001_canon_change_history.up.sql`
// and provides defense-in-depth.
//
// # LOCKED decisions consumed
//
//   - **Q-L1A-3**: every appended entry is also written to meta_write_audit
//     via the cycle-4 audit chain (no sampling).
//   - **Q-L1A-2**: writes to glossary DB (canon_change_history table);
//     production binds the TimelineAppender to a glossary-DB INSERT.
//   - **Q-L5-3**: canon_layer enum carried verbatim.
//   - **Q-L5A-1**: services/glossary-service/ NOT modified; the
//     glossary-service sub-program APPLIES the canon_change_history
//     migration when it onboards this writer.
//
// # Cross-cycle wiring
//
//   - Cycle 23 L5.A canon events: consumed.
//   - Cycle 24 canon_writer: companion writer; both run in the same
//     dispatcher loop.
//   - Cycle 27 L5.H force-propagate: admin.canon.override.compensating
//     events also routed through this writer.
//   - Cycle 4 MetaWrite audit: every append audited.
package canon_history_writer

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/contracts/canon/timeline"
)

// Event-type constants — both canon.entry.* (cycle 23) and
// admin.canon.override.compensating (cycle 27) route here.
const (
	EventCanonCreated         = "canon.entry.created"
	EventCanonUpdated         = "canon.entry.updated"
	EventCanonPromoted        = "canon.entry.promoted"
	EventCanonDecanonized     = "canon.entry.decanonized"
	EventOverrideCompensating = "admin.canon.override.compensating"
)

const (
	canonLayerL1Axiom  = "L1_axiom"
	canonLayerL2Seeded = "L2_seeded"
)

// AuditEntry is the audit row shape for canon-history writes (Q-L1A-3).
type AuditEntry struct {
	EventID         uuid.UUID
	EventType       string
	ChangeID        uuid.UUID
	CanonEntryID    uuid.UUID
	BookID          uuid.UUID
	AttributePath   string
	WrittenAt       time.Time
}

// AuditSink interface for the meta-write audit bridge.
type AuditSink interface {
	WriteAudit(ctx context.Context, entry AuditEntry) error
}

// Clock for test injection.
type Clock interface {
	Now() time.Time
}

type realClock struct{}

func (realClock) Now() time.Time { return time.Now().UTC() }

// Writer is the L5.J history appender.
type Writer struct {
	store timeline.TimelineAppender
	audit AuditSink
	clock Clock
}

// Config bundles deps.
type Config struct {
	Store timeline.TimelineAppender
	Audit AuditSink
	Clock Clock
}

// New constructs a Writer.
func New(cfg Config) (*Writer, error) {
	if cfg.Store == nil {
		return nil, errors.New("canon_history_writer: Store nil")
	}
	if cfg.Audit == nil {
		return nil, errors.New("canon_history_writer: Audit nil")
	}
	clk := cfg.Clock
	if clk == nil {
		clk = realClock{}
	}
	return &Writer{store: cfg.Store, audit: cfg.Audit, clock: clk}, nil
}

// Handle is the dispatcher entry-point. Decodes the envelope, builds
// the timeline.Entry, appends via the store, writes the audit row.
//
// Returning non-nil tells the consumer to NACK.
func (w *Writer) Handle(ctx context.Context, fields map[string]any) error {
	if fields == nil {
		return errors.New("canon_history_writer: nil fields")
	}
	eventType, _ := fields["event_type"].(string)
	if !isHandledEventType(eventType) {
		return fmt.Errorf("canon_history_writer: unsupported event_type %q", eventType)
	}

	entry, err := decode(eventType, fields, w.clock.Now())
	if err != nil {
		return fmt.Errorf("canon_history_writer: decode %s: %w", eventType, err)
	}

	if err := w.store.Append(ctx, entry); err != nil {
		return fmt.Errorf("canon_history_writer: append: %w", err)
	}

	if err := w.audit.WriteAudit(ctx, AuditEntry{
		EventID:       uuid.New(),
		EventType:     eventType,
		ChangeID:      entry.ChangeID,
		CanonEntryID:  entry.CanonEntryID,
		BookID:        entry.BookID,
		AttributePath: entry.AttributePath,
		WrittenAt:     entry.RecordedAt,
	}); err != nil {
		return fmt.Errorf("canon_history_writer: audit: %w", err)
	}
	return nil
}

// EventTypes returns the 5 event types this writer registers for.
func EventTypes() []string {
	return []string{
		EventCanonCreated,
		EventCanonUpdated,
		EventCanonPromoted,
		EventCanonDecanonized,
		EventOverrideCompensating,
	}
}

func isHandledEventType(t string) bool {
	switch t {
	case EventCanonCreated, EventCanonUpdated, EventCanonPromoted, EventCanonDecanonized, EventOverrideCompensating:
		return true
	}
	return false
}

func decode(eventType string, fields map[string]any, now time.Time) (timeline.Entry, error) {
	out := timeline.Entry{
		ChangeID:        uuid.New(),
		SourceEventType: eventType,
		RecordedAt:      now,
	}
	var err error
	out.BookID, err = uuidField(fields, "book_id")
	if err != nil {
		return out, err
	}
	out.CanonEntryID, err = uuidField(fields, "canon_entry_id")
	if err != nil {
		return out, err
	}
	if v, e := uuidField(fields, "event_id"); e == nil {
		out.SourceEventID = v
	} else {
		// Synthesize when absent so the audit chain has SOMETHING to
		// reference. The contract doc allows this — source_event_id is
		// for "best-effort" trace; the ChangeID is the SSOT identifier.
		out.SourceEventID = uuid.New()
	}
	out.AttributePath, _ = stringField(fields, "attribute_path")

	// canon_layer extraction varies per event_type.
	layer := ""
	switch eventType {
	case EventCanonPromoted:
		if v, ok := fields["to_layer"].(string); ok {
			layer = v
		}
	default:
		if v, ok := fields["canon_layer"].(string); ok {
			layer = v
		}
	}
	if !isValidCanonLayer(layer) {
		layer = canonLayerL2Seeded
	}
	out.CanonLayer = layer

	// Value extraction (best-effort).
	if v, ok := fields["new_value"]; ok {
		out.NewValue = anyToBytes(v)
	} else if v, ok := fields["value"]; ok {
		out.NewValue = anyToBytes(v)
	}
	if v, ok := fields["old_value"]; ok {
		out.OldValue = anyToBytes(v)
	}

	// Kind classification.
	switch eventType {
	case EventOverrideCompensating:
		out.Kind = timeline.CanonChangeKindForcePropagate
		if r, e := uuidField(fields, "reality_id"); e == nil {
			out.RealityID = r
		}
	default:
		out.Kind = timeline.CanonChangeKindAuthored
	}
	return out, nil
}

func isValidCanonLayer(s string) bool {
	return s == canonLayerL1Axiom || s == canonLayerL2Seeded
}

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
		return uuid.Parse(x)
	case uuid.UUID:
		if x == uuid.Nil {
			return uuid.Nil, fmt.Errorf("zero field %q", key)
		}
		return x, nil
	}
	return uuid.Nil, fmt.Errorf("unsupported type for %q: %T", key, v)
}

func stringField(fields map[string]any, key string) (string, error) {
	v, ok := fields[key]
	if !ok {
		return "", nil
	}
	s, ok := v.(string)
	if !ok {
		return "", nil
	}
	return s, nil
}

func anyToBytes(v any) []byte {
	switch x := v.(type) {
	case []byte:
		return x
	case string:
		return []byte(x)
	}
	return nil
}
