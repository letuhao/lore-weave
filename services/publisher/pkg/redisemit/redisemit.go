// Package redisemit is the go-redis implementation of poll_loop.Emitter and
// xreality_fanout.StreamEmitter.
//
// Per L1.K.12 outbox-event-emit-lint, only services/publisher/ may XADD to
// the event streams — this package IS that legitimate emit site.
//
//   - Emitter.Emit   → XADD to the per-reality stream `lw.events.<reality_id>`.
//   - StreamEmitter.XAdd → XADD to an arbitrary stream (the xreality.* topics).
//
// Redis stream field values must be scalars, so map/slice envelope fields
// (payload, metadata) are JSON-encoded to strings before XADD; the
// meta-worker consumer decodes them back.
package redisemit

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

// streamPrefix is the per-reality stream namespace: `lw.events.<reality_id>`.
const streamPrefix = "lw.events."

// Emitter XADDs the per-reality event envelope. maxLen caps the stream with
// approximate trimming (MAXLEN ~ N); 0 disables trimming.
type Emitter struct {
	rdb    redis.Cmdable
	maxLen int64
}

// NewEmitter binds the per-reality emitter to a go-redis client.
func NewEmitter(rdb redis.Cmdable, maxLen int64) *Emitter {
	return &Emitter{rdb: rdb, maxLen: maxLen}
}

// StreamFor returns the per-reality stream name for a reality_id.
func StreamFor(realityID string) string { return streamPrefix + realityID }

// Emit XADDs the row's envelope to `lw.events.<reality_id>`.
func (e *Emitter) Emit(ctx context.Context, row types.OutboxRow) error {
	return xadd(ctx, e.rdb, StreamFor(row.RealityID.String()), e.maxLen, envelopeFields(row))
}

// StreamEmitter XADDs to an arbitrary stream. Satisfies
// xreality_fanout.StreamEmitter (the xreality.<entity>.<verb> topics).
type StreamEmitter struct {
	rdb    redis.Cmdable
	maxLen int64
}

// NewStreamEmitter binds the xreality stream emitter to a go-redis client.
func NewStreamEmitter(rdb redis.Cmdable, maxLen int64) *StreamEmitter {
	return &StreamEmitter{rdb: rdb, maxLen: maxLen}
}

// XAdd writes the supplied fields to the named stream.
func (s *StreamEmitter) XAdd(ctx context.Context, stream string, fields map[string]any) error {
	return xadd(ctx, s.rdb, stream, s.maxLen, fields)
}

// envelopeFields assembles the wire envelope for the per-reality stream.
func envelopeFields(row types.OutboxRow) map[string]any {
	f := map[string]any{
		"event_id":          row.EventID.String(),
		"event_type":        row.EventType,
		"event_version":     row.EventVersion,
		"reality_id":        row.RealityID.String(),
		"aggregate_type":    row.AggregateType,
		"aggregate_id":      row.AggregateID,
		"aggregate_version": row.AggregateVersion,
		"occurred_at":       row.OccurredAt.UTC().Format(time.RFC3339Nano),
		"recorded_at":       row.RecordedAt.UTC().Format(time.RFC3339Nano),
	}
	if row.Payload != nil {
		f["payload"] = row.Payload
	}
	if row.Metadata != nil {
		f["metadata"] = row.Metadata
	}
	return f
}

// xadd scalarizes map/slice fields to JSON strings, then issues the XADD.
func xadd(ctx context.Context, rdb redis.Cmdable, stream string, maxLen int64, fields map[string]any) error {
	values, err := scalarize(fields)
	if err != nil {
		return fmt.Errorf("redisemit: scalarize %s: %w", stream, err)
	}
	args := &redis.XAddArgs{Stream: stream, Values: values}
	if maxLen > 0 {
		args.MaxLen = maxLen
		args.Approx = true
	}
	if err := rdb.XAdd(ctx, args).Err(); err != nil {
		return fmt.Errorf("redisemit: XADD %s: %w", stream, err)
	}
	return nil
}

// scalarize converts non-scalar field values (maps, slices) to JSON strings
// so Redis accepts them; scalars pass through unchanged.
func scalarize(in map[string]any) (map[string]any, error) {
	out := make(map[string]any, len(in))
	for k, v := range in {
		switch vv := v.(type) {
		case nil:
			out[k] = ""
		case string, bool,
			int, int8, int16, int32, int64,
			uint, uint8, uint16, uint32, uint64,
			float32, float64, []byte:
			out[k] = vv
		default:
			b, err := json.Marshal(vv)
			if err != nil {
				return nil, fmt.Errorf("field %q: %w", k, err)
			}
			out[k] = string(b)
		}
	}
	return out, nil
}
