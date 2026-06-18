// Package metaoutbox is the production meta.OutboxAppender for the driver-clean
// contracts/meta MetaWrite library (P2/101 — D-METAWRITE-OUTBOX-UNWIRED).
//
// MetaWrite emits an allowlisted outbox event in the SAME TX as the data +
// meta_write_audit rows (metawrite.go `if cfg.Outbox != nil`). This appender
// supplies that hand-off: Append INSERTs one row into the meta_outbox table
// (migration 030) using the MetaWrite-supplied meta.Tx — so the outbox row is
// atomic with the write. The dedicated meta-outbox-relay drains meta_outbox to
// Redis (lw.meta.events + the xreality.* bridge).
//
// Driver-clean: this package depends ONLY on contracts/meta's tiny Tx interface
// (Exec) — no pgx — so it composes with metapg (or any meta.DB driver) and
// builds without a database dependency. The payload map is marshalled to JSON
// and passed as a $N::jsonb arg; the meta_outbox CHECK enforces it is an object.
package metaoutbox

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// Appender implements meta.OutboxAppender against the meta_outbox table.
//
// xrealityTopics maps event_name → xreality.<entity>.<verb> topic (loaded from
// events_allowlist.yaml via meta.LoadXRealityTopics). When an emitted event's
// name is present, the appender stamps meta_outbox.xreality_topic so the relay
// ALSO XADDs to that cross-reality topic (feeding per-reality consumers, 071).
// Absent ⇒ NULL ⇒ the event is meta-only.
type Appender struct {
	xrealityTopics map[string]string
}

// New constructs an Appender. xrealityTopics may be nil/empty (no event is
// cross-reality). The map is used read-only; callers should not mutate it after.
func New(xrealityTopics map[string]string) *Appender {
	if xrealityTopics == nil {
		xrealityTopics = map[string]string{}
	}
	return &Appender{xrealityTopics: xrealityTopics}
}

var _ meta.OutboxAppender = (*Appender)(nil)

const insertSQL = `
INSERT INTO meta_outbox (event_id, event_name, aggregate_id, payload, xreality_topic, recorded_at_nanos)
VALUES ($1, $2, $3, $4::jsonb, $5, $6)
`

// Append writes one meta_outbox row inside the supplied (MetaWrite-owned) tx.
// Defensive validation mirrors the table's NOT NULL / CHECK constraints so a
// bad event fails with a clear error instead of a raw SQL constraint violation.
func (a *Appender) Append(ctx context.Context, tx meta.Tx, ev meta.OutboxEvent) error {
	if tx == nil {
		return fmt.Errorf("metaoutbox: nil tx")
	}
	if ev.EventID == uuid.Nil {
		return fmt.Errorf("metaoutbox: event_id is zero")
	}
	if ev.EventName == "" {
		return fmt.Errorf("metaoutbox: event_name is empty")
	}
	// Payload is a JSONB object column with a jsonb_typeof = 'object' CHECK.
	// A nil map marshals to "null" (NOT an object) and would violate the CHECK,
	// so normalise nil → {} before marshalling.
	payload := ev.Payload
	if payload == nil {
		payload = map[string]any{}
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("metaoutbox: marshal payload for %s: %w", ev.EventName, err)
	}

	// nil ⇒ SQL NULL (meta-only event); a present topic ⇒ the cross-reality bridge.
	var topic any
	if t, ok := a.xrealityTopics[ev.EventName]; ok {
		topic = t
	}

	if _, err := tx.Exec(ctx, insertSQL,
		ev.EventID,
		ev.EventName,
		ev.AggregateID,
		string(payloadJSON),
		topic,
		ev.RecordedAt,
	); err != nil {
		return fmt.Errorf("metaoutbox: insert meta_outbox event %s (%s): %w", ev.EventID, ev.EventName, err)
	}
	return nil
}
