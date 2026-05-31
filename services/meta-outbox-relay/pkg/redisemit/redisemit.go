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
	"bytes"
	"context"
	"encoding/json"
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
//
// Unlike the home stream, the xreality emit PROMOTES the (domain) payload's
// top-level keys to top-level Redis fields (P2/113) — so canonical-envelope
// consumers like meta-worker/user_erased_writer (071), which read top-level
// `user_id`/`erased_at`, work directly. The full raw payload is still attached
// as `payload` for consumers that want the whole object. Reserved envelope
// fields (event_id/event_name/aggregate_id/recorded_at_nanos/payload) win on
// any key collision.
func (e *Emitter) EmitXReality(ctx context.Context, row drain.Row) error {
	if row.XRealityTopic == "" {
		return errors.New("redisemit: EmitXReality called with empty xreality_topic")
	}
	payload := string(row.Payload)
	if payload == "" {
		payload = "{}"
	}
	values := map[string]any{}
	// Promote a flat domain payload's top-level scalar keys to fields. Numbers
	// are decoded with UseNumber so int64 precision survives. Non-object payloads
	// (or a decode error) simply skip promotion — `payload` still carries it.
	if len(row.Payload) > 0 {
		dec := json.NewDecoder(bytes.NewReader(row.Payload))
		dec.UseNumber()
		var obj map[string]any
		if err := dec.Decode(&obj); err == nil {
			for k, v := range obj {
				values[k] = fieldValue(v)
			}
		}
	}
	// Reserved envelope fields win on collision.
	values["event_id"] = row.EventID
	values["event_name"] = row.EventName
	// event_type = the xreality topic, so cross-reality consumers (e.g.
	// meta-worker, whose dispatcher routes by event_type) route EXPLICITLY to
	// the topic's handler instead of relying on the stream-name fallback
	// (P2/071 /review-impl #1; matches the publisher fanout's event_type contract).
	values["event_type"] = row.XRealityTopic
	values["aggregate_id"] = row.AggregateID
	values["recorded_at_nanos"] = row.RecordedAtNanos
	values["payload"] = payload
	return e.xaddValues(ctx, row.XRealityTopic, row.EventID, values)
}

// fieldValue renders a decoded JSON value as a Redis Stream scalar field.
// json.Number → its exact string (no float64 precision loss); strings/bools
// pass through; nested objects/arrays are re-encoded as a JSON string.
func fieldValue(v any) any {
	switch x := v.(type) {
	case string:
		return x
	case json.Number:
		return x.String()
	case bool:
		return x
	case nil:
		return ""
	default:
		b, _ := json.Marshal(x)
		return string(b)
	}
}

func (e *Emitter) xadd(ctx context.Context, stream string, row drain.Row) error {
	// Home stream: generic envelope; the payload is the raw jsonb bytes from
	// meta_outbox passed through verbatim (no remarshal → int64 precision kept).
	// Defensive: a zero-length payload becomes an empty object so a consumer's
	// JSON parse never sees "".
	payload := string(row.Payload)
	if payload == "" {
		payload = "{}"
	}
	return e.xaddValues(ctx, stream, row.EventID, map[string]any{
		"event_id":          row.EventID,
		"event_name":        row.EventName,
		"aggregate_id":      row.AggregateID,
		"payload":           payload,
		"recorded_at_nanos": row.RecordedAtNanos,
	})
}

// xaddValues performs the XADD with the configured MAXLEN cap.
func (e *Emitter) xaddValues(ctx context.Context, stream, eventID string, values map[string]any) error {
	args := &redis.XAddArgs{Stream: stream, Values: values}
	if e.streamMaxLen > 0 {
		args.MaxLen = e.streamMaxLen
		args.Approx = true
	}
	if err := e.rdb.XAdd(ctx, args).Err(); err != nil {
		return fmt.Errorf("redisemit: XADD %s event %s: %w", stream, eventID, err)
	}
	return nil
}
