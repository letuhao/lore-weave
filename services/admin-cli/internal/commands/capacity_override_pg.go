package commands

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// PgScalingEventWriter persists a capacity override as a scaling_events row via
// contracts/meta MetaWrite (so the write is audited in meta_write_audit, same
// TX). scaling_events is allowlisted to emit scaling.event.recorded, but — like
// PgConsentRevoker — we run with Outbox=nil (no consumer reads it in V1), so the
// event is dropped and the row state is the SSOT. Wire cfg.Outbox if a
// capacity-event consumer ever lands.
type PgScalingEventWriter struct {
	cfg *meta.Config
}

// NewPgScalingEventWriter binds the MetaWrite Config (DB=metapg, allowlist
// permitting scaling_events, scrubber, clock, uuidgen).
func NewPgScalingEventWriter(cfg *meta.Config) *PgScalingEventWriter {
	return &PgScalingEventWriter{cfg: cfg}
}

var _ ScalingEventWriter = (*PgScalingEventWriter)(nil)

// WriteOverride INSERTs one event_type='override' scaling_events row. The 24h
// window is bounded by the caller (RunCapacityOverride) and the migration-025
// CHECK; initiator_type is the enum-valid 'admin'.
func (w *PgScalingEventWriter) WriteOverride(ctx context.Context, ov ScalingOverride) error {
	if w.cfg == nil {
		return fmt.Errorf("capacity-override: nil meta config")
	}
	initiatedBy, err := uuid.Parse(ov.Actor)
	if err != nil {
		return fmt.Errorf("capacity-override: actor %q is not a UUID (admin subjects are UUIDs): %w", ov.Actor, err)
	}
	payload, err := json.Marshal(map[string]any{"hours": ov.Hours})
	if err != nil {
		return fmt.Errorf("capacity-override: marshal payload: %w", err)
	}
	intent := meta.MetaWriteIntent{
		Table:     "scaling_events",
		Operation: meta.OpInsert,
		PK:        map[string]any{"scaling_event_id": w.cfg.UUIDGen.New()},
		NewValues: map[string]any{
			"event_type":          "override",
			"shard_host":          ov.ShardHost,
			"initiated_by":        initiatedBy,
			"initiator_type":      "admin",
			"override_expires_at": ov.ExpiresAt,
			"payload":             payload,
			"reason":              ov.Reason,
			"created_at":          ov.CreatedAt,
		},
		Actor:  meta.Actor{Type: meta.ActorAdmin, ID: ov.Actor},
		Reason: ov.Reason,
	}
	if _, err := meta.MetaWrite(ctx, w.cfg, intent); err != nil {
		return fmt.Errorf("capacity-override: metawrite scaling_events: %w", err)
	}
	return nil
}
