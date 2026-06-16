// Package consumer is the meta-worker's XREADGROUP loop.
//
// V1 ships as a SKELETON with an abstract `MessageSource` interface so
// tests can drive messages without a real Redis. Production wiring (cycle
// 11+) binds the real go-redis client.
//
// The consumer is INTENTIONALLY thin — its only job is:
//  1. Pull a batch from the next pending message on `xreality.*` streams.
//  2. Hand each message to `dispatch.Dispatcher.Dispatch`.
//  3. ACK on success; do NOT ACK on dispatch error (Redis Streams will
//     re-deliver after the consumer group's `pending entries list` ages
//     out — operational concern, not consumer code).
//
// The loop maintains a `lastConsumedAt` timestamp the operator can scrape
// via the `lw_meta_worker_lag_seconds` metric (gauge).
package consumer

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
)

// Message is one xreality envelope as decoded from Redis Streams.
type Message struct {
	// Stream is the source stream name (e.g. "xreality.canon.promoted").
	Stream string
	// ID is the Redis Stream entry ID (e.g. "1700000000000-0"). Used by
	// AckedSource.Ack to mark the message processed.
	ID string
	// Fields is the parsed JSON envelope body.
	Fields map[string]any
}

// EventType returns the canonical event_type for this message, preferring
// the envelope's `event_type` field over the stream name (they should
// match — if they don't, the publisher wrote inconsistent data).
func (m Message) EventType() string {
	if v, ok := m.Fields["event_type"].(string); ok && v != "" {
		return v
	}
	return m.Stream
}

// MessageSource is the Redis Streams abstraction. Production binds
// go-redis's XReadGroup; tests drive it from in-memory channels.
//
// Read MUST block (or return zero messages with nil error) until a new
// message is available OR the context is cancelled. Returning an error
// causes the consumer to back off + retry.
//
// AckBatch XACKs MANY ids on ONE stream in a single call. The consume loop
// acks once per stream per batch instead of once per message — the per-message
// XACK round-trip was the I7 single-consumer ceiling (S12: ~22k msgs/s, bound by
// XACK RTT not CPU). A 0-length ids slice is a no-op.
type MessageSource interface {
	Read(ctx context.Context, batchSize int) ([]Message, error)
	AckBatch(ctx context.Context, stream string, ids []string) error
}

// Consumer wires a MessageSource to a Dispatcher.
type Consumer struct {
	source         MessageSource
	dispatcher     *dispatch.Dispatcher
	lastConsumedAt time.Time
}

// New constructs a Consumer. Both args MUST be non-nil; the dispatcher
// MUST pass `ValidateAllowlist` (caller checks at startup).
func New(source MessageSource, d *dispatch.Dispatcher) (*Consumer, error) {
	if source == nil {
		return nil, errors.New("consumer: source nil")
	}
	if d == nil {
		return nil, errors.New("consumer: dispatcher nil")
	}
	return &Consumer{source: source, dispatcher: d}, nil
}

// ProcessOne pulls one batch and dispatches every message in order.
// Returns the per-call stats; the caller invokes ProcessOne in a loop.
//
// Behavior:
//   - Dispatch success → Ack.
//   - Dispatch error → do NOT Ack (Redis Streams re-delivers).
//   - Ack error → log + count, but don't fail the whole call (the
//     message has already been processed; Ack failure is a meta concern).
type ProcessStats struct {
	Read      int
	Dispatched int
	Acked      int
	NoHandler  int
	HandlerErr int
}

// ProcessOne reads one batch (up to batchSize), dispatches every msg, then ACKs
// all successfully-dispatched ids in ONE XACK per stream. Batching the ack (vs
// one round-trip per message) is the S12 I7 ceiling fix: the per-message XACK RTT
// was the single-consumer bottleneck, not CPU.
//
// The re-delivery contract is preserved exactly: only ids whose dispatch returned
// nil are acked; a dispatch error (no-handler / handler error) leaves the message
// un-acked so Redis Streams re-delivers it. An AckBatch error leaves that stream's
// ids un-acked (they re-deliver) and is NOT counted as dispatched/acked.
func (c *Consumer) ProcessOne(ctx context.Context, batchSize int) (ProcessStats, error) {
	stats := ProcessStats{}
	msgs, err := c.source.Read(ctx, batchSize)
	if err != nil {
		return stats, fmt.Errorf("consumer: read: %w", err)
	}
	stats.Read = len(msgs)

	// Group successfully-dispatched ids by stream, preserving first-seen order so
	// the ack order is deterministic.
	ackIDs := map[string][]string{}
	var streamOrder []string
	for _, m := range msgs {
		derr := c.dispatcher.Dispatch(ctx, m.EventType(), m.Fields)
		if derr == nil {
			if _, seen := ackIDs[m.Stream]; !seen {
				streamOrder = append(streamOrder, m.Stream)
			}
			ackIDs[m.Stream] = append(ackIDs[m.Stream], m.ID)
			continue
		}
		if errors.Is(derr, dispatch.ErrNoHandler) {
			stats.NoHandler++
		} else {
			stats.HandlerErr++
		}
	}

	for _, stream := range streamOrder {
		ids := ackIDs[stream]
		if ackErr := c.source.AckBatch(ctx, stream, ids); ackErr != nil {
			// Already processed; leave un-acked so Redis re-delivers. Don't count
			// as dispatched/acked (mirrors the old per-message ack-failure path).
			continue
		}
		// Dispatched is coupled to a successful ack (unchanged semantics).
		stats.Acked += len(ids)
		stats.Dispatched += len(ids)
		c.lastConsumedAt = time.Now()
	}
	return stats, nil
}

// LastConsumedAt exposes the wall-clock time of the most recent successful
// dispatch+ack. Used by the lag-seconds metric.
func (c *Consumer) LastConsumedAt() time.Time { return c.lastConsumedAt }
