// Package redisemit is the drain.Emitter backed by Redis Streams.
//
// Emit XADDs a meta_outbox row's envelope to the home stream (default
// lw.meta.events); EmitXReality XADDs the same envelope (same event_id, so
// consumers dedupe) to the row's xreality_topic — the cross-reality bridge for
// per-reality consumers (e.g. meta-worker/user_erased_writer, 071).
//
// Per L1.K.12 outbox-event-emit-lint only services/publisher may call XAdd for
// the xreality.* spine topics; this relay is the meta-context's sanctioned
// emitter for the meta_outbox→Redis hand-off (P2/101, Option B).
package redisemit

import (
	"context"
	"errors"
	"fmt"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/drain"
)

// Emitter XADDs to Redis Streams. streamMaxLen caps each stream with approximate
// trimming (0 ⇒ no MAXLEN).
type Emitter struct {
	rdb          *redis.Client
	homeStream   string
	streamMaxLen int64
}

// New constructs an Emitter. homeStream defaults to "lw.meta.events" when empty.
func New(rdb *redis.Client, homeStream string, streamMaxLen int64) (*Emitter, error) {
	if rdb == nil {
		return nil, errors.New("redisemit: nil redis client")
	}
	if homeStream == "" {
		homeStream = "lw.meta.events"
	}
	return &Emitter{rdb: rdb, homeStream: homeStream, streamMaxLen: streamMaxLen}, nil
}

var _ drain.Emitter = (*Emitter)(nil)

// Emit XADDs the row to the home stream.
func (e *Emitter) Emit(ctx context.Context, row drain.Row) error {
	return e.xadd(ctx, e.homeStream, row)
}

// EmitXReality XADDs the row to its xreality_topic (the cross-reality bridge).
func (e *Emitter) EmitXReality(ctx context.Context, row drain.Row) error {
	if row.XRealityTopic == "" {
		return errors.New("redisemit: EmitXReality called with empty xreality_topic")
	}
	return e.xadd(ctx, row.XRealityTopic, row)
}

func (e *Emitter) xadd(ctx context.Context, stream string, row drain.Row) error {
	// Redis Stream field values must be scalars; the payload is already the raw
	// jsonb bytes from meta_outbox — pass it through verbatim (no remarshal, so
	// int64 precision is preserved). Defensive: a zero-length payload becomes an
	// empty object so a consumer's JSON parse never sees "".
	payload := string(row.Payload)
	if payload == "" {
		payload = "{}"
	}
	args := &redis.XAddArgs{
		Stream: stream,
		Values: map[string]any{
			"event_id":          row.EventID,
			"event_name":        row.EventName,
			"aggregate_id":      row.AggregateID,
			"payload":           payload,
			"recorded_at_nanos": row.RecordedAtNanos,
		},
	}
	if e.streamMaxLen > 0 {
		args.MaxLen = e.streamMaxLen
		args.Approx = true
	}
	if err := e.rdb.XAdd(ctx, args).Err(); err != nil {
		return fmt.Errorf("redisemit: XADD %s event %s: %w", stream, row.EventID, err)
	}
	return nil
}
